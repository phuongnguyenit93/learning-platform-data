# ApplicationContextInitializedEvent: Event After Applying ApplicationContextInitializer

## 1. Position of the Event in the Spring Boot Lifecycle

A Spring Boot program may have already **created an `ApplicationContext` object** yet still not loaded bean definitions, initialized singletons, or become ready to serve requests. Before doing those things, `SpringApplication` gives `ApplicationContextInitializer` instances a chance to customize the context. **Right after the initializers have run**, Spring Boot emits `ApplicationContextInitializedEvent`.

That is precisely what the event name means: **the context has been prepared and initializers have been applied**, not that the whole application is "initialized" in the sense of having business beans, databases, controllers, and a web server.

Imagine a classroom:

- Spring Boot **picks the room** and unlocks the door: creating `ApplicationContext`.
- An organizer **arranges desks and sets up the whiteboard**: running `ApplicationContextInitializer`.
- Someone confirms **the room is prepared**: `ApplicationContextInitializedEvent`.
- Only then are **equipment lists and students brought in**: loading bean definitions.
- Finally, **equipment is installed and turned on**: `refresh()`, creating beans and starting components.
- Class can begin once all required steps complete: application ready.

This lesson uses the APIs of **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. We will explain the event, its position, available APIs, how to register listeners **at the right time**, key limitations, and a complete program to observe it.

**Key takeaway to keep in mind:** `ApplicationContextInitializedEvent` is an **early startup event**, emitted **after initializers and before loading application bean definitions**. It is not the bean-initialization event, not `ContextRefreshedEvent`, and not `ApplicationReadyEvent`.

## 2. Timeline: Context Exists Before Beans

The diagram illustrates the typical execution path of `SpringApplication.run(...)`:

```text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       +-- ApplicationStartingEvent
       |
       +-- Prepare Environment, process startup config
       +-- ApplicationEnvironmentPreparedEvent
       |
       +-- SELECT / CREATE ConfigurableApplicationContext
       |
       +-- Attach Environment, prepare context
       |
       +-- applyInitializers(context)
       |       |
       |       +-- initializer A.initialize(context)
       |       +-- initializer B.initialize(context)
       |       +-- ... in sorted initializer order
       |
       +-- ApplicationContextInitializedEvent   <=== LESSON FOCUS
       |       |
       |       +-- Context exists
       |       +-- Initializers have run
       |       +-- Primary bean definitions not loaded yet
       |       +-- Not refreshed yet
       |
       +-- Finish bootstrap preparation / load primary sources
       +-- ApplicationPreparedEvent
       |
       +-- context.refresh()
       |       |
       |       +-- BeanFactoryPostProcessor, BeanPostProcessor
       |       +-- Create non-lazy singletons, inject dependencies
       |       +-- Initialize web infrastructure if present
       |       +-- ContextRefreshedEvent
       |
       +-- ApplicationStartedEvent
       +-- LivenessState.CORRECT
       |
       +-- ApplicationRunner / CommandLineRunner
       |
       +-- ApplicationReadyEvent
       +-- ReadinessState.ACCEPTING_TRAFFIC
```

The diagram focuses on the **order of Spring Boot's main milestones**. Internal operations for bootstrap, Environment, web server, and listeners have their own detailed hook points; do not treat the diagram as an exhaustive list of every framework call.

### 2.1. This Event Occurs Before `refresh()`

`ConfigurableApplicationContext.refresh()` is the critical process that processes the BeanFactory, bean definitions, post-processors, and normal singleton instantiation. `ApplicationContextInitializedEvent` is emitted **before** that step.

With standard `ApplicationContext` implementations based on `AbstractApplicationContext`, when catching this event:

```text
context != null
context.isActive() == false
```

This is normal because the context has not been `refresh()`ed yet. Do not infer that the context is broken just because `isActive()` is still `false`. The active flag takes on its different meaning after refresh or close.

### 2.2. Understanding "No Bean Definitions Yet" Accurately

Spring Boot documentation defines this event's timing as **before bean definitions are loaded**. Specifically, this means Boot has not yet loaded the **primary sources**, `@SpringBootApplication`, `@Configuration`, `@ComponentScan`, and application definitions along the standard path.

Do not write an assertion that **`BeanFactory.getBeanDefinitionCount()` must equal 0** in every situation. A custom context or integration may already have added infrastructure metadata or registered definitions manually earlier. The stable rule to remember is that **you cannot assume all application bean definitions are loaded and cannot call business beans as you would after refresh**.

## 3. Differences Among Context Creation, Initializer, Event, and Refresh

| Milestone | Object or work already present | What cannot be assumed yet |
| --- | --- | --- |
| Context creation | `ConfigurableApplicationContext` instance of the appropriate type | No active application beans yet |
| Applying `ApplicationContextInitializer` | Context available for initial configuration edits | `refresh()` has not occurred yet |
| Emitting `ApplicationContextInitializedEvent` | **All initializers for this startup run have been applied in order** | Primary bean definitions not loaded yet, not refreshed |
| Emitting `ApplicationPreparedEvent` | Bean definitions from primary sources loaded | Not refreshed and regular singletons not created yet |
| `ContextRefreshedEvent` | `refresh()` has completed for the context | Boot may not have finished running runners yet |
| `ApplicationStartedEvent` | Spring Boot has refreshed the context | `ApplicationRunner`/`CommandLineRunner` not called yet |
| `ApplicationReadyEvent` | Runners have completed successfully | Does not guarantee external dependencies stay healthy forever |

Therefore, seeing the word `Initialized` in the event name is not proof that the entire application is ready to accept traffic.

## 4. How Is `ApplicationContextInitializer` Applied?

The Spring Framework interface has the concise signature:

```java
@FunctionalInterface
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
```

This is an **illustrative contract signature**, not a Java file you define yourself: the real interface is `org.springframework.context.ApplicationContextInitializer`.

`SpringApplication` collects initializers registered directly or through library mechanisms, sorts them via `Ordered`/`@Order`, and invokes each `initialize(context)` **before loading primary sources and refreshing the context**. They are used for early customization: adding a `PropertySource`, listener, BeanFactory post-processor, or valid context settings.

Example initializer adding a default property:

```java
ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
        context -> {
            MapPropertySource defaults = new MapPropertySource(
                    "earlyDefaults",
                    Map.of("demo.label", "initialized-first"));
            context.getEnvironment()
                    .getPropertySources()
                    .addLast(defaults);
        };
```

This is a snippet placed in `main` or `SpringApplication` setup code; it requires imports for `ApplicationContextInitializer`, `ConfigurableApplicationContext`, `MapPropertySource`, and `java.util.Map`. `addLast` adds a low-precedence source so properties from higher-precedence config sources can still override it.

**Connection to the event:** after `initialize(...)` finishes, a listener receiving `ApplicationContextInitializedEvent` can read:

```java
String label = event.getApplicationContext()
        .getEnvironment()
        .getProperty("demo.label");
```

If no other property source overrides it, the value is `initialized-first`. This proves that the initializer was applied **before the event was emitted**.

### 4.1. "After Initializer" Does Not Mean "After Bean Injection"

Initializers run when the application context has just come into existence. They are not created by Boot as regular business beans from `@ComponentScan`. Here, `context.getBean(MyService.class)`, `@Autowired` on beans, `@PostConstruct`, and regular repositories are not guaranteed to exist yet.

Use an initializer for **preparing the container**, use `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` to modify metadata at the right phase, and use `ApplicationRunner` or lifecycle beans for business work depending on ready beans.

## 5. API of `ApplicationContextInitializedEvent`

The main class is:

```java
org.springframework.boot.context.event.ApplicationContextInitializedEvent
```

It extends `SpringApplicationEvent` and exposes the following information:

| API | Meaning | Notes |
| --- | --- | --- |
| `event.getApplicationContext()` | Gets the `ConfigurableApplicationContext` being prepared | Not refreshed yet; can read Environment/register early customizations |
| `event.getSpringApplication()` | Gets the `SpringApplication` emitting the event | Do not use to recursively invoke `run()` inside startup |
| `event.getArgs()` | Gets the argument array passed to `SpringApplication.run(...)` | May contain sensitive information; avoid printing verbatim |
| `event.getTimestamp()` | Event creation timestamp | Not total startup duration |
| `event.getSource()` | Event source per `ApplicationEvent` | Do not replace `getApplicationContext()` by casting source to context |

The constructor of `ApplicationContextInitializedEvent` accepts `SpringApplication`, `String[] args`, and `ConfigurableApplicationContext`. In normal applications, **do not manually instantiate and publish** this event: it is a milestone emitted by `SpringApplication` during startup.

### 5.1. What Type Is the Context Here?

With the default context factory, it depends on `WebApplicationType`:

- `NONE`: typically `AnnotationConfigApplicationContext`.
- `SERVLET`: typically `AnnotationConfigServletWebServerApplicationContext`.
- `REACTIVE`: typically `AnnotationConfigReactiveWebServerApplicationContext`.

In all cases you receive a `ConfigurableApplicationContext` so listeners can work with common APIs. A custom factory may be used, so do not cast the context to Servlet or Reactive types without checking first.

### 5.2. Environment Exists, but Early Choices Have Already Happened

`SpringApplication` prepares `Environment` before creating the context. A listener at this milestone can normally read `spring.application.name`, profiles, command-line properties, and prepared properties.

However, **adding a new property** during this event does not make Boot revisit all earlier decisions. For instance, Boot has already selected and created the context type; putting `spring.main.web-application-type=reactive` into `Environment` here **does not automatically replace** an already created Servlet context.

Similarly, if a property must affect the **already-completed ConfigData loading**, use an appropriate mechanism **before** the context-creation phase instead of waiting for `ApplicationContextInitializedEvent`.

## 6. Catching the Event Properly: Register the Listener Before Run

This is the easiest part to get wrong. Because `ApplicationContextInitializedEvent` occurs **before Spring builds beans**, the surest way to receive it is to register `ApplicationListener` with `SpringApplication` **before `run(...)`**.

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationContextInitializedEvent> listener =
        event -> System.out.println(
                "Context type: "
                        + event.getApplicationContext()
                               .getClass()
                               .getSimpleName());

app.addListeners(listener);
app.run(args);
```

The snippet above is **illustrative code inside `main`**, assuming `MyApplication` is a `@SpringBootApplication` class, and requiring imports for `SpringApplication`, `ApplicationListener`, and `ApplicationContextInitializedEvent`.

### 6.1. Why Does `@EventListener` in a Bean Usually Miss It?

The following snippet compiles, yet is **not the right way to receive this startup event**:

```java
@Component
class TooLateListener {

    @EventListener
    void observe(ApplicationContextInitializedEvent event) {
        System.out.println("I expect the early event");
    }
}
```

This example exists **only to explain the timing error** and requires importing `@Component`, `@EventListener`, and the event class. The `TooLateListener` bean must be instantiated by Spring and have its event listener adapter registered during refresh, **after `ApplicationContextInitializedEvent` has already been emitted**. So do not rely on that method to catch the early event of the current startup.

The same applies to a listener declared solely as `@Bean ApplicationListener<ApplicationContextInitializedEvent>` in a regular `@Configuration`: that bean also arrives too late.

### 6.2. Listeners Can Be Registered via `SpringApplicationBuilder`

```java
new SpringApplicationBuilder(MyApplication.class)
        .listeners((ApplicationListener<ApplicationContextInitializedEvent>)
                event -> System.out.println("Context initialized"))
        .run(args);
```

This is a different **`main` snippet**; do not run it simultaneously with `app.run(...)` above. It requires importing `SpringApplicationBuilder`, `ApplicationListener`, and the event class. `SpringApplicationBuilder.listeners(...)` helps when configuring multi-tier applications or when you want a fluent API.

### 6.3. Using `META-INF/spring.factories` When Writing a Library

If you want a listener to be loaded even when other applications do not edit `main`, you can package the listener class in a JAR along with:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.context.ApplicationListener=\
com.example.early.ContextInitializedLogger
```

And the class:

```java
package com.example.early;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public final class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        System.out.println("Early context: "
                + event.getApplicationContext().getClass().getSimpleName());
    }
}
```

This is a **complete Java file** at `src/main/java/com/example/early/ContextInitializedLogger.java`; it has no `main` of its own. When the library is on the classpath and Boot loads `ApplicationListener` implementations via its factory mechanism, the listener is registered early enough to catch the event.

**Note:** `spring.factories` here holds the `org.springframework.context.ApplicationListener` key. Do not conflate it with `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, which declares Spring Boot 3.x auto-configurations.

Avoid registering the same listener twice via both `spring.factories` and `addListeners(...)`, especially if the listener performs side effects or writes resources.

## 7. Complete Hands-On Example: Proving Initializers Run Before the Event

This example uses **a single Spring Boot program**, Java 17+, Spring Boot 3.3.x. We explicitly choose `WebApplicationType.NONE` to skip starting a web server and focus on lifecycle ordering.

**File:** `src/main/java/com/example/early/InitializedEventDemoApplication.java`

```java
package com.example.early;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class InitializedEventDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitializedEventDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
                context -> {
                    context.getEnvironment().getPropertySources().addLast(
                            new MapPropertySource(
                                    "demoInitializerDefaults",
                                    Map.of("demo.message", "from-initializer")));
                    System.out.println("1 INITIALIZER");
                };
        app.addInitializers(initializer);

        ApplicationListener<ApplicationContextInitializedEvent> initialized =
                event -> {
                    ConfigurableApplicationContext context =
                            event.getApplicationContext();
                    System.out.println("2 CONTEXT_INITIALIZED active="
                            + context.isActive());
                    System.out.println("3 CONTEXT_INITIALIZED message="
                            + context.getEnvironment().getProperty("demo.message"));
                };
        app.addListeners(initialized);

        ApplicationListener<ApplicationPreparedEvent> prepared =
                event -> System.out.println("4 PREPARED active="
                        + event.getApplicationContext().isActive());
        app.addListeners(prepared);

        ApplicationListener<ApplicationStartedEvent> started =
                event -> System.out.println("5 STARTED active="
                        + event.getApplicationContext().isActive());
        app.addListeners(started);

        ApplicationListener<ApplicationReadyEvent> ready =
                event -> System.out.println("7 READY active="
                        + event.getApplicationContext().isActive());
        app.addListeners(ready);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("8 RUN_RETURNED active="
                    + context.isActive());
        }
    }

    @Bean
    ApplicationRunner showMessage(Environment environment) {
        return arguments -> System.out.println(
                "6 RUNNER message=" + environment.getProperty("demo.message"));
    }
}
```

### 7.1. Project Configuration

Assume the project uses Spring Boot Gradle plugin 3.3.x, proper dependency management, and Java 17+ configured. Minimum dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

No `spring-boot-starter-web`, database, or HTTP endpoint is required. If the project contains multiple main classes, specify `com.example.early.InitializedEventDemoApplication` to `bootRun`/the plugin to avoid launching the wrong class.

### 7.2. Running the Program

```bash
./gradlew bootRun
```

On Windows CMD use `gradlew.bat bootRun`; in PowerShell use `.\gradlew.bat bootRun`.

If the project contains only the example's main class, default Boot detection can determine the main class. Spring Boot banner/INFO logs may appear between the lines below.

### 7.3. Observed Output on Successful Startup

Lines printed by the program itself, in order:

```text
1 INITIALIZER
2 CONTEXT_INITIALIZED active=false
3 CONTEXT_INITIALIZED message=from-initializer
4 PREPARED active=false
5 STARTED active=true
6 RUNNER message=from-initializer
7 READY active=true
8 RUN_RETURNED active=true
```

**Checking each milestone:**

- Line **1**: the initializer adds `demoInitializerDefaults` to `Environment`. It executes before the event.
- Line **2**: `ApplicationContextInitializedEvent` has been emitted and the context exists, but is not refreshed yet (`active=false`).
- Line **3**: the same listener reads the property added by the initializer, proving the early change is already active in `Environment`.
- Line **4**: `ApplicationPreparedEvent` occurs after Boot loads bean definitions, yet the context is still unrefreshed.
- Line **5**: `ApplicationStartedEvent` occurs after refresh, so the context is now active.
- Line **6**: `ApplicationRunner` is a bean created/injected after refresh; the runner reads the same property again.
- Line **7**: `ApplicationReadyEvent` appears after the runner.
- Line **8**: `app.run(args)` returns the context; `try` closes the context right after printing that line.

Try overriding the property via a startup argument:

```bash
./gradlew bootRun --args='--demo.message=from-command-line'
```

Because `demoInitializerDefaults` was added using `addLast(...)`, lines 3 and 6 normally show `from-command-line`: the command-line source has higher precedence. Use `gradlew.bat bootRun --args="--demo.message=from-command-line"` in Windows CMD; quoting rules depend on the shell.

The example prints only the state of the **context**—do not interpret `active=true` as HTTP readiness: this application does not open an HTTP server. For web applications, Spring Boot readiness has its own milestone, and health probes are needed to check request paths.

### 7.4. Why Use `try-with-resources`?

`ConfigurableApplicationContext` implements `AutoCloseable`, allowing `try (...)`. When exiting `try`, the context is closed and the beans/resources it manages are cleaned up per lifecycle. Closing after `run` **does not change** the order of events already printed.

If `app.run(...)` itself throws an error before returning, `try` has not yet acquired a resource; Spring Boot handles startup failure separately. Do not assume cleanup callbacks run on JVM crashes, `SIGKILL`, or power loss.

## 8. Advanced Example: Verifying All Initializers Have Run

Suppose there are two initializers: one creates the `demo.phase` property, and the other adds a different property. `ApplicationContextInitializedEvent` occurs after Boot invokes **the initializers registered for that run**, so a listener can inspect the **combined** result.

```java
ApplicationContextInitializer<ConfigurableApplicationContext> first =
        context -> context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "firstDefaults", Map.of("demo.phase", "prepared")));

ApplicationContextInitializer<ConfigurableApplicationContext> second =
        context -> context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "secondDefaults", Map.of("demo.source", "custom")));

app.addInitializers(first, second);
```

This is a snippet to add inside `main`; it requires the same imports as the complete example. An `ApplicationContextInitializedEvent` listener can read both `demo.phase` and `demo.source`. However, **exact ordering between initializers matters** if the second initializer needs to read the result of the first initializer.

### 8.1. Using Ordered to Express Dependencies

A class-based initializer can implement `Ordered`:

```java
package com.example.early;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public final class FirstInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("First initializer completed");
    }
}
```

The code above is a **complete class** that is not used until you register it via `app.addInitializers(new FirstInitializer())` or an equivalent mechanism. Smaller order values are sorted earlier. You can use `@Order` on the class; avoid relying on incidental ordering between initializers that share the same order value.

An `ApplicationContextInitializedEvent` listener does not run between initializer 1 and 2: it sits **after the initializer group**. If you genuinely need "after initializer A but before initializer B," design the ordering or abstractions of the initializers themselves rather than trying to insert this event between them.

## 9. What Is Appropriate in the Listener and What to Avoid?

### 9.1. Potentially Appropriate Tasks

At this milestone, an early listener may:

- Record the **context type** (`NONE`/`SERVLET`/`REACTIVE` at the runtime class level).
- Inspect configuration properties added to Environment by initializers.
- Validate non-sensitive prepared metadata and fail early when required configuration is missing.
- Register additional listeners on `ConfigurableApplicationContext` for events **that will occur later**, when justified.
- Add metadata or a BeanFactory post-processor following the proper contract before refresh.
- Write brief diagnostic logs to verify startup order.

Example adding a listener for a future event:

```java
ApplicationListener<ApplicationContextInitializedEvent> early =
        event -> event.getApplicationContext()
                .addApplicationListener((ContextRefreshedEvent refreshed) ->
                        System.out.println("Context refreshed later"));
```

This snippet requires importing `ApplicationListener`, `ApplicationContextInitializedEvent`, and `org.springframework.context.event.ContextRefreshedEvent`. The listener is registered on the context **before refresh**, so it can receive `ContextRefreshedEvent` later. If multiple contexts exist, verify the identity of the emitting context before performing one-time side effects.

### 9.2. Things Not to Do

**Do not retrieve business beans:**

```java
MyService service = event.getApplicationContext().getBean(MyService.class);
```

This is a **badly timed** example, assuming `MyService` is a bean created via `@ComponentScan`. At this milestone, application definitions have not been loaded yet; calling `getBean` can fail and break startup.

**Do not manually call `refresh()` or `close()`.** Spring Boot owns the startup sequence. Calling these two methods inside the listener can corrupt bean loading and context state.

**Do not perform slow network/file I/O or infinite retries.** Standard startup listeners run synchronously on the event-publishing path; a blocking listener blocks the entire startup. Business tasks requiring services after refresh should move to `ApplicationRunner` or an appropriate lifecycle mechanism.

**Do not use this event to reverse an earlier startup decision.** For example, changing `spring.main.web-application-type` now will not rebuild the already-created context; changing properties tied to config-loading phases may already be too late.

**Do not print arguments containing secrets.** `event.getArgs()` may include usernames, tokens, passwords, or internal endpoints; if debugging is needed, log only non-sensitive information or a filtered key list.

## 10. Comparing with Neighboring Events

| Event | ApplicationContext created? | Initializers executed? | Primary bean definitions loaded? | Refreshed? |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | No | No | No | No |
| `ApplicationEnvironmentPreparedEvent` | No | No (application context initializers) | No | No |
| **`ApplicationContextInitializedEvent`** | **Yes** | **Yes** | **No** | **No** |
| `ApplicationPreparedEvent` | Yes | Yes | Yes | No |
| `ContextRefreshedEvent` | Yes | Yes | Yes | Yes |
| `ApplicationStartedEvent` | Yes | Yes | Yes | Yes |
| `ApplicationReadyEvent` | Yes | Yes | Yes | Yes, runners also executed |

The `ApplicationEnvironmentPreparedEvent` row refers to `ApplicationContextInitializer`; **`BootstrapRegistryInitializer`** instances belong to a different bootstrap phase and may have run earlier. Do not conflate the two initializer types just because both names include "initializer."

### 10.1. `ApplicationContextInitializedEvent` vs. `ApplicationPreparedEvent`

This is an easily confused pair:

- **Initialized**: context created, `ApplicationContextInitializer` finished, bean definitions **not yet** loaded.
- **Prepared**: Boot has loaded definitions from primary sources into the context, but has **not yet** called `refresh()`.

If the goal is solely to inspect values put into Environment by initializers, **Initialized** is enough. If you need to work with **bean definition metadata loaded from sources**, **Prepared** or refresh-phase post-processors are more appropriate.

### 10.2. `ApplicationContextInitializedEvent` vs. `ContextRefreshedEvent`

`ContextRefreshedEvent` is a Spring Framework event after `refresh()`; it reflects that the context has built its BeanFactory and initialized non-lazy beans. `ApplicationContextInitializedEvent` comes **before** that step and belongs to Spring Boot's own startup event sequence.

In parent/child context hierarchies, a `ContextRefreshedEvent` can propagate to ancestor contexts, so listeners may see multiple events. Check context identity if logic applies only to one context.

### 10.3. This Event vs. `BootstrapContextClosedEvent`

`BootstrapContextClosedEvent` closes the scope of **BootstrapRegistry/BootstrapContext** and can transfer early-prepared resources into the application context. It is **different** from the Initialized event, which states that `ApplicationContextInitializer` instances have run.

In Spring Boot 3.3's standard startup path, closing the bootstrap context happens around the stage when the context is prepared, before loading primary sources and refreshing. Do not infer that "BootstrapContextClosedEvent means ApplicationContext has closed": `ApplicationContext` is preparing to enter its own lifecycle.

### 10.4. Initialized vs. Readiness

Spring Boot marks `LivenessState.CORRECT` after `ApplicationStartedEvent` and `ReadinessState.ACCEPTING_TRAFFIC` after `ApplicationReadyEvent`. `ApplicationContextInitializedEvent` occurs before both milestones, so it is not a signal for a load balancer to send requests to the instance.

## 11. Customizing Beans: Choosing the Right Extension Point

Many people want to "add a bean really early" and think they should do it in `ApplicationContextInitializedEvent`. Distinguish these goals:

| Goal | Appropriate mechanism | Why |
| --- | --- | --- |
| Add config properties for context construction | `ApplicationContextInitializer` or an appropriate Environment processor | Available before BeanFactory refresh |
| Observe that initializers applied successfully | `ApplicationContextInitializedEvent` | Confirms the milestone right after the initializer group |
| Register a BeanFactory post-processor to run during refresh | `ApplicationContextInitializer` + `addBeanFactoryPostProcessor(...)` | Runs in the proper metadata phase before singleton creation |
| Create/modify bean definitions based on loaded metadata | `BeanDefinitionRegistryPostProcessor` | Has the contract to work with definitions |
| Customize bean instances or proxies | `BeanPostProcessor` | Runs around the bean lifecycle |
| Run logic after beans are ready | `ApplicationRunner`/`CommandLineRunner` | Already past refresh |
| Catch application-wide ready notification | `ApplicationReadyEvent` listener | After runners |
| Control resource teardown | `@PreDestroy`, `SmartLifecycle`, or destroy method | Proper shutdown phase, not the Initialized event |

### 11.1. Example Registering an Early Post-Processor

```java
ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
        context -> context.addBeanFactoryPostProcessor(beanFactory -> {
            System.out.println("Bean definitions in refresh phase: "
                    + beanFactory.getBeanDefinitionCount());
        });
```

This is a snippet requiring imports for the initializer interface and configurable context. Calling `addBeanFactoryPostProcessor(...)` here **only registers** the callback; the lambda body will be invoked **later during `refresh()`**, while the BeanFactory is being processed. Do not confuse "registering" with "executing immediately inside the initializer."

### 11.2. Why Not Manually Register Business Beans Arbitrarily?

At the Initialized event, the context is not refreshed yet; technical APIs exist for early registration, yet they depend on context/BeanFactory types. If you need normal runtime beans, `@Bean`, `@Component`, auto-configuration, or a `BeanDefinitionRegistryPostProcessor` is usually clearer and lets the container manage the lifecycle properly.

Instantiating objects externally and calling `registerSingleton(...)` can bypass bean creation steps such as injection, post-processing, and container destroy callbacks. Use it only when you fully understand ownership, ordering, and consequences; the Initialized event **does not automatically turn something into a complete bean**.

## 12. Listener Ordering and Startup Cost

`ApplicationContextInitializedEvent` is an early `SpringApplicationEvent`. Boot uses its startup event mechanism before the application context finishes refreshing; listeners registered on `SpringApplication` have the chance to receive the event.

By default, listeners typically run synchronously on the event-publishing thread. Consequently:

- Listeners doing heavy work lengthen startup time.
- Unhandled exceptions can cause `SpringApplication.run(...)` to fail.
- When multiple listeners handle the same event, ordering can be influenced by `Ordered`/`@Order`; do not rely on incidental order.
- Events are not a queue mechanism guaranteeing retries, transactional delivery, or durable data transmission.
- Keep logs short, perform lightweight checks, and leave long-running work until after beans are usable.

If you need accurate startup timing measurements, use startup instrumentation such as `ApplicationStartup` or framework metrics rather than treating `event.getTimestamp()` as total startup completion time.

## 13. What Happens If Startup Fails?

There are three distinct failure groups:

1. **Error inside an initializer:** `initialize(...)` throws an exception so execution may stop **before emitting `ApplicationContextInitializedEvent`**. Listeners for this event will not receive confirmation.
2. **Error inside an Initialized listener:** the exception can propagate back into the startup sequence and Boot handles the failure; reaching `ApplicationPreparedEvent` or `ApplicationReadyEvent` is not guaranteed.
3. **Error during bean loading/refresh/runners:** the Initialized event may already have succeeded, yet the application still fails to start later.

Therefore, **observing `ApplicationContextInitializedEvent` is not proof that startup PASSED**. If you need general startup failure handling, register a listener early for `ApplicationFailedEvent`. Depending on when the error occurred, the failure event may or may not have a context; do not access beans unconditionally.

For missing required configuration, failing fast with a clear message is usually better than silently swallowing exceptions and letting the application run misconfigured. Also avoid printing secrets in stack traces or diagnostics.

### 13.1. Example Lightweight Property Validation

```java
ApplicationListener<ApplicationContextInitializedEvent> validate =
        event -> {
            String name = event.getApplicationContext()
                    .getEnvironment()
                    .getProperty("spring.application.name");
            if (name == null || name.isBlank()) {
                throw new IllegalStateException(
                        "Missing required spring.application.name");
            }
        };
```

This snippet can be placed in `main` and registered with `app.addListeners(validate)`. It is appropriate **only if `spring.application.name` is genuinely a mandatory requirement defined by your application**; Spring Boot does not require every project to configure this property.

## 14. Can a Process Receive the Event Multiple Times?

Multiple `SpringApplication` instances or contexts can exist in the same JVM—for example, parent/child hierarchies, integration tests creating multiple contexts, or modules running multiple applications. Each `SpringApplication.run(...)` call can emit its own event.

Hence you should not write a listener assuming "there is strictly one `ApplicationContextInitializedEvent` in the entire process." When you need to handle events only for a target context, compare identity against the appropriate context reference or distinguish `event.getSpringApplication()` within orchestration you control.

If a global listener is registered via `spring.factories`, control side effects so it does not duplicate operations when the same library appears across multiple applications or contexts. Storing a JVM-wide `static boolean initialized` flag is usually not the right solution when multiple independent runs exist.

## 15. Scenarios and Practical Questions

### Scenario A — Need to Know Whether a Property Just Added by an Initializer Is Present

Register an `ApplicationContextInitializedEvent` listener early and read from `event.getApplicationContext().getEnvironment()`. If the property can only come from the initializer, this check helps detect whether the initializer was unregistered or ran in the wrong order.

**Do not** use `@EventListener` on a runtime bean to catch this ultra-early milestone.

### Scenario B — Want to Use a Repository to Check Essential Data

Do not retrieve a repository in an Initialized listener. The container has not refreshed and beans are not ready yet. Move the check to an `ApplicationRunner`, or the lifecycle of a well-designed bean; Spring Boot only emits ready once runners complete successfully.

### Scenario C — Want to Change Context Type from Servlet to Reactive

Set `WebApplicationType` via `SpringApplication.setWebApplicationType(...)` or startup configuration before the context is created. The Initialized listener already receives **a concrete context instance**; updating a property inside the listener does not make Boot re-select the context type.

### Scenario D — Want to Modify a Bean Definition from `@Configuration`

Wait until the phase where definitions are loaded or use `BeanDefinitionRegistryPostProcessor`. At the Initialized event, primary sources have not been loaded yet; looking for service bean definitions there is premature.

### Scenario E — Want to Know Whether the Application Can Serve HTTP Requests Yet

Check `ApplicationReadyEvent` and the deployment platform's readiness/health checks. `ApplicationContextInitializedEvent` only proves that the early context configuration step finished.

### Scenario F — Want to Catch the Event in a Library Without Forcing Apps to Edit main

Install `ApplicationListener<ApplicationContextInitializedEvent>` via `META-INF/spring.factories`. Ensure the class has an appropriate constructor, is on the runtime classpath, and handles invocations idempotently if registered across multiple contexts.

## 16. Misconceptions and Troubleshooting

| Misconception or error encountered | Accurate explanation | Resolution |
| --- | --- | --- |
| "The name Initialized means beans have been created." | Only context initializers have run, before loading bean definitions. | Compare with `ApplicationPreparedEvent` and `ContextRefreshedEvent`. |
| `@EventListener` on `@Component` does not receive the event. | Bean listeners are created too late. | Use `app.addListeners(...)` or `spring.factories`. |
| `getBean(MyService.class)` fails in an early listener. | Bean definitions have not been loaded/refreshed yet. | Move to a runner or appropriate lifecycle hook. |
| `isActive()` returns `false` in the callback. | Context has not `refresh()`ed yet; this is valid state. | Do not treat `false` as startup failed at this milestone. |
| Property added by an initializer does not appear. | Initializer not registered, wrong order, or overridden by a higher-precedence source. | Verify `addInitializers`, `Ordered`, and property sources. |
| Property changed, yet context type did not change. | Boot already chose/created the context before this event. | Configure web type at an earlier phase. |
| Saw Initialized event, yet app still fails startup. | Error can happen later during bean loading, refresh, or runners. | Inspect the root exception and `ApplicationFailedEvent`. |
| Listener prints raw `getArgs()` and leaks tokens. | Arguments may carry secrets. | Log only filtered information, never all raw args. |
| Startup command hangs at the event. | Listener performs slow I/O or retries and runs synchronously. | Add timeouts and move heavy work to an appropriate mechanism. |
| Registered listener via `@Bean` and missed the event. | `@Bean` is processed during refresh, too late. | Register the listener before `run`. |
| Saw the event multiple times and suspected a loop. | Multiple `SpringApplication`/contexts or duplicate listener registration. | Check context identity, registration sources, and lifecycle. |
| Listener calls `context.refresh()` to get beans. | Calling refresh out of phase breaks Boot's startup sequence. | Let `SpringApplication` manage refresh. |

## 17. Practical Implementation Checklist

1. Correctly distinguish **context created**, **initializers applied**, **definitions loaded**, **context refreshed**, and **application ready**.
2. Verify the listener is registered **before `SpringApplication.run(...)`**.
3. If relying on properties set by initializers, verify initializer order and `PropertySource` precedence.
4. Do not retrieve business beans in `ApplicationContextInitializedEvent`.
5. Do not run slow I/O or infinite retries in early startup listeners.
6. Do not treat `isActive()==false` at this milestone as an error.
7. Do not use the Initialized event to change `SpringApplication` selections already applied earlier.
8. If you only need bean definition metadata, pick `ApplicationPreparedEvent` or a BeanFactory post-processor.
9. If you need repositories/services, wait for refresh and use a runner or suitable lifecycle bean.
10. When startup fails, find the root exception and distinguish failures in initializers, listeners, definition loading, refresh, or runners.
11. When multiple contexts exist, verify the event belongs to the right `SpringApplication`/context.
12. Do not log secrets or mutate business state inside diagnostic-only listeners.
13. With the sample code, confirm the sequence `INITIALIZER → CONTEXT_INITIALIZED → PREPARED → STARTED → RUNNER → READY`.

## 18. Core Takeaways

```text
CREATE Context
     |
APPLY ApplicationContextInitializer
     |
ApplicationContextInitializedEvent   <-- sees initializer results
     |
LOAD Bean Definitions
     |
ApplicationPreparedEvent
     |
REFRESH Context
     |
ApplicationStartedEvent
     |
Runner
     |
ApplicationReadyEvent
```

`ApplicationContextInitializedEvent` is a checkpoint confirming **an early container preparation phase has completed**. It can read `Environment` and context metadata, but **business beans are not yet available for use**. To catch the event, register the listener on `SpringApplication` before running. To execute work that depends on beans, choose a later extension point.

## Reference Documentation (Spring Boot 3.3)

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationContextInitializedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot 3.3 — ApplicationPreparedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
