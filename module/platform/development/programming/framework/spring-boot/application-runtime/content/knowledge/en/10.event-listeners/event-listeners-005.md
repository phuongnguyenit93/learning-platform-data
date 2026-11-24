# Why Bean-Based Listeners Do Not Receive Very Early Spring Boot Events

## 1. A Common Issue

In Spring Boot, applications often observe events using `@EventListener` or a bean implementing `ApplicationListener<E>`:

```java
@Component
public class MyStartupListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("Application is starting");
    }
}
```

Developers expect to see the log line as soon as the application starts, yet in practice the method may **never be invoked** during that startup run. This is usually not because `@EventListener` is broken, component scanning is misconfigured, or Spring Boot dropped the event. **The event was published before the listener bean was created, discovered, and registered**.

There are two distinct concepts:

- **Event publication**: Spring Boot dispatches an event object to the listener broadcaster that exists at that moment.
- **Listener registration**: the broadcaster knows which listeners are eligible to receive events. Having a class annotated with `@Component` or a method with `@EventListener` in source code **does not mean** the listener is present from the very first moment of the process.

For a super-early event like `ApplicationStartingEvent`, the application does not even have an `ApplicationContext` yet to scan `@Component`, instantiate beans, or process `@EventListener`. To listen to them, you must register the listener **before calling `SpringApplication.run(...)`**, for instance with:

1. `SpringApplication.addListeners(...)`.
2. `SpringApplicationBuilder.listeners(...)`.
3. `META-INF/spring.factories` with key `org.springframework.context.ApplicationListener`.

This is a matter of **when the listener exists**, not merely the event type or annotation style.

## 2. Three Objects to Distinguish

| Object | Role | When is it ready? |
| --- | --- | --- |
| `SpringApplication` | Coordinates the startup process and holds early-registered listeners | Exists as soon as `new SpringApplication(...)` is constructed |
| `ApplicationContext` | Container managing beans, events, environment, resources, and lifecycle | Created after environment preparation; refreshed later |
| Bean listener (`@Component`/`@Bean`/`@EventListener`) | Receives events once the container discovers and registers the corresponding listener | Typically only after the appropriate context creation/refresh process |

When calling:

```java
SpringApplication.run(DemoApplication.class, args);
```

this code creates a `SpringApplication` and invokes `run` in one short statement. The program still passes through multiple phases; **there is no guarantee that bean listeners exist when SpringApplication publishes the earliest events**.

By contrast, the following creates a plain Java listener **before** bootstrap begins:

```java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.addListeners(new EarlyBootListener());
app.run(args);
```

Here `EarlyBootListener` is an object instantiated with `new` and registered on `SpringApplication`; it **does not need to wait for Spring IoC to create beans** in order to receive early events. Once the context is initialized, Spring Boot also transfers previously registered application listeners into the context's event publication mechanism for subsequent stages.

## 3. Startup Event Timeline

In Spring Boot 3.3.x, the typical sequence is:

```text
main(String[] args)
    |
    | Create SpringApplication, register early listeners
    v
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |      Environment not prepared yet; no ApplicationContext yet
    |
    +-- ApplicationEnvironmentPreparedEvent
    |      Environment prepared; ApplicationContext not created yet
    |
    +-- Create ApplicationContext
    +-- Apply ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent
    |      Context exists; primary sources/bean definitions not loaded yet
    |
    +-- Load configuration sources / bean definitions
    +-- ApplicationPreparedEvent
    |      Definitions loaded; not refreshed yet
    |
    +-- refresh() ApplicationContext
    |      Register post-processors and bean event listeners
    |      Instantiate required singletons, complete refresh
    |      ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    |      Context refreshed, runners not run yet
    +-- AvailabilityChangeEvent: LivenessState.CORRECT
    |
    +-- ApplicationRunner and CommandLineRunner
    |
    +-- ApplicationReadyEvent
    +-- AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
    |
    v
run(...) returns context

If startup fails:
    +-- ApplicationFailedEvent (depending on timing, context may not exist yet)
```

This diagram highlights **significant milestones**. It omits logging setup, auto-configuration details, startup hooks, and other context/web server events.

### Comparison Table: Can a Bean-Based Listener Receive It?

| Event | State when published | Does a listener registered only as a bean/`@EventListener` usually receive it? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Before `Environment` and context | **No** — no listener beans exist yet |
| `ApplicationEnvironmentPreparedEvent` | Environment exists, no context yet | **No** |
| `ApplicationContextInitializedEvent` | Fresh context exists, primary bean definitions not loaded | **No** |
| `ApplicationPreparedEvent` | Definitions loaded, not refreshed and listener bean registration incomplete | **No**, during normal bootstrap |
| `ContextRefreshedEvent` | Refresh nearly complete, event infrastructure ready | Usually **yes**, if the listener bean is properly registered |
| `ApplicationStartedEvent` | After refresh, before runners | Usually **yes** |
| `ApplicationReadyEvent` | After runners | Usually **yes** |
| `ApplicationFailedEvent` | Failure can occur at any stage | **Not guaranteed**: early errors can occur before listener beans exist |

Do not interpret the third column as a 100% guarantee across every configuration. A bean excluded by `@Profile`, outside component scan, or failing initialization still cannot receive events. Conversely, framework authors can register listeners manually earlier than beans. This table describes **ordinary bean declarations** in default `SpringApplication.run(...)`.

**Easy point of confusion:** at `ApplicationPreparedEvent`, *bean definitions may already exist*, yet **listener bean instances and `@EventListener` processing are still incomplete**. A `BeanDefinition` is metadata on "how to create a bean," not a listener instance already registered in the event multicaster.

## 4. Why Don't @Component or @Bean Solve Very Early Events?

Bean registration typically goes through this flow:

```text
Class definitions / configuration on classpath
             |
             v
ApplicationContext is created
             |
             v
Component scanning / load bean definitions
             |
             v
refresh() and process BeanFactoryPostProcessors
             |
             v
Instantiate required beans; process BeanPostProcessors
             |
             v
Register listener interfaces and @EventListener methods
             |
             v
Bean listeners receive events published from this point onward
```

There are two common cases:

**Case A — Bean implementing ApplicationListener:**

```java
@Component
public class BeanStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("bean observed starting");
    }
}
```

Even with the exact generic type and overridden method, the bean still typically **does not receive `ApplicationStartingEvent`** because that event was published before component scanning.

**Case B — @EventListener method:**

```java
@Component
public class AnnotatedListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("annotation observed starting");
    }
}
```

`@EventListener` is not a tool that "registers immediately when the JVM loads the class." Annotated methods are discovered and registered by Spring context infrastructure during context initialization. Therefore, this method is also too late for `ApplicationStartingEvent`.

Both snippets only illustrate registration styles; they require imports for `@Component`, `ApplicationListener`, `ApplicationStartingEvent`, or `@EventListener` and must sit in a valid Spring project. **Simply switching from `@EventListener` to implementing the interface does not fix the issue** if the instance is still created by the IoC container.

### @Bean Has the Same Problem

```java
@Configuration
public class ListenerConfig {

    @Bean
    ApplicationListener<ApplicationStartingEvent> startingListener() {
        return event -> System.out.println("bean @Bean observed starting");
    }
}
```

This is still **a bean** created when the context processes configuration—too late for `ApplicationStartingEvent`. Do not confuse **a `@Bean` creating a listener inside the container** with **`new Listener()` registered on `SpringApplication` before `run`**.

## 5. Approach 1 — SpringApplication.addListeners(...) Before Run

This is the clearest approach when a listener serves a single entrypoint and you control the `main(...)` method.

The following example uses Java 17+ and Spring Boot 3.3.x. A single listener can observe multiple events in the `SpringApplicationEvent` family.

**File `src/main/java/demo/early/EarlyBootListener.java`:**

```java
package demo.early;

import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyBootListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println("external: "
                + event.getClass().getSimpleName());
    }
}
```

**File `src/main/java/demo/early/EarlyEventsApplication.java`:**

```java
package demo.early;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(EarlyEventsApplication.class);

        // Register BEFORE run(): no need for Spring to create a bean.
        app.addListeners(new EarlyBootListener());

        app.run(args);
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("runner: executed");
    }
}
```

**File `src/main/java/demo/early/BeanEventsObserver.java`:**

```java
package demo.early;

import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BeanEventsObserver {

    @EventListener
    public void tooEarlyStarting(ApplicationStartingEvent event) {
        System.out.println("bean: ApplicationStartingEvent");
    }

    @EventListener
    public void tooEarlyPrepared(ApplicationPreparedEvent event) {
        System.out.println("bean: ApplicationPreparedEvent");
    }

    @EventListener
    public void afterRefresh(ApplicationStartedEvent event) {
        System.out.println("bean: ApplicationStartedEvent");
    }

    @EventListener
    public void whenReady(ApplicationReadyEvent event) {
        System.out.println("bean: ApplicationReadyEvent");
    }
}
```

In this example, **all four `@EventListener` methods are syntactically valid**; the first two do not print during normal startup because they are registered after their corresponding events have already been published.

**File `src/main/resources/application.properties`:**

```properties
spring.application.name=early-events-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

Setting `NONE` allows the experiment to run without an HTTP server. `logging.level.root=ERROR` reduces regular logs; it does not affect the `System.out.println(...)` lines in the example.

### Building and Running

A minimal `build.gradle` can be:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
```

`settings.gradle`:

```groovy
rootProject.name = 'early-events-demo'
```

In a project with a compatible Gradle wrapper, run:

```bash
./gradlew bootRun
```

Or package with `./gradlew bootJar` and run `java -jar` with the generated JAR name. This is a Spring Boot program, **not** a plain Java program that can be compiled with `javac` without Spring dependencies.

### Expected Output

In a default successful run, the events observed by `EarlyBootListener` appear in order:

```text
external: ApplicationStartingEvent
external: ApplicationEnvironmentPreparedEvent
external: ApplicationContextInitializedEvent
external: ApplicationPreparedEvent
external: ApplicationStartedEvent
external: ApplicationReadyEvent
```

This is **the order of lines prefixed with `external:`**. Lines from `BeanEventsObserver` and the runner may interleave among the later lines; do not treat the block above as the entire contiguous stdout.

Other notable lines:

```text
bean: ApplicationStartedEvent
runner: executed
bean: ApplicationReadyEvent
```

Where:

- `bean: ApplicationStartedEvent` appears **before** `runner: executed`.
- `bean: ApplicationReadyEvent` appears **after** `runner: executed`.
- `bean: ApplicationStartingEvent` and `bean: ApplicationPreparedEvent` do not appear on the standard startup path of this example.
- The order between two listeners receiving the same specific event can be influenced by ordering/registration; do not write tests relying on an arbitrary position of `external: ApplicationStartedEvent` relative to `bean: ApplicationStartedEvent`.
- The system may print additional logs or Gradle messages. Compare only the lines printed by the demo itself; do not claim they represent the entire stdout.

Spring Boot `3.3.13` is a version in the 3.3 branch used to reproduce the example; this is not a recommendation to pick an out-of-support version for a new project. When using your organization's current version, re-verify the corresponding APIs and compatibility.

### Why Does an External Non-Bean Listener Also Receive Late Events?

`app.addListeners(new EarlyBootListener())` supplies the instance directly to `SpringApplication` **before execution begins**. The startup event publisher can notify this listener from the very first event. Spring Boot also transfers eligible early-registered listeners into the `ApplicationContext` event broadcaster once the context is loaded, so the listener can continue observing late events.

That **does not turn this instance into an autowired service bean in the usual way**. Do not expect `EarlyBootListener` constructor or fields to receive injection like a `@Component` when you instantiated it yourself with `new`.

## 6. Approach 2 — Early Registration via META-INF/spring.factories

This is a useful option if the listener belongs to an infrastructure library and you want it auto-discovered whenever the library is on the runtime classpath, regardless of which entrypoint calls `SpringApplication.run(...)`.

Create the file:

```text
src/main/resources/META-INF/spring.factories
```

Content:

```properties
org.springframework.context.ApplicationListener=demo.early.EarlyBootListener
```

With this file, simplify the entrypoint back to:

```java
package demo.early;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EarlyEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(EarlyEventsApplication.class, args);
    }
}
```

This is an **alternative** to the entrypoint in Section 5; do not place two public class declarations with the same name in one file. To keep the runner from Section 5, keep that runner bean in another `@Configuration` class, or keep the `@Bean` method inside the entrypoint while changing how the listener is registered.

**Do not accidentally register the same listener via both `addListeners` and `spring.factories`**. When both paths create separate instances, event lines may appear twice, or listener side effects may run repeatedly.

### Conditions for SpringFactoriesLoader to Instantiate the Listener

- The file must have the exact path `META-INF/spring.factories` on the runtime classpath.
- The key must be **`org.springframework.context.ApplicationListener`**, not another interface name.
- The value must be the fully qualified class name, with the right package and class.
- The implementation must be loadable and have a suitable constructor for the loader to instantiate it—typically a **public no-arg constructor** for a simple `ApplicationListener` like `EarlyBootListener`.
- Any dependencies needed by the listener must be available during early startup.
- Do not assume Spring IoC provides `@Autowired` for a listener instantiated by the loader.

Resource packaging in an executable Spring Boot JAR typically looks like:

```text
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/demo/early/EarlyBootListener.class
```

Verify with `jar tf` on the JAR actually produced by the build. If the listener lives in a library JAR, `spring.factories` will reside in that dependency JAR rather than necessarily in the application's `BOOT-INF/classes`.

**Do not confuse mechanisms:** Spring Boot 3 moved many auto-configuration mechanisms to `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, yet registering a very early `ApplicationListener` in this lesson can still be done via **`META-INF/spring.factories`** under the `ApplicationListener` key. The two metadata files serve different purposes.

### ApplicationListener Differs from SpringApplicationRunListener

`SpringApplicationRunListener` is an interface hooking the steps `starting(...)`, `environmentPrepared(...)`, `contextPrepared(...)`, `contextLoaded(...)`, `started(...)`, `ready(...)`, and `failed(...)`. It is also loaded very early via `SpringFactoriesLoader`, but uses a **different key**:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.early.CustomRunListener
```

This is an **illustrative line for a different mechanism**, not configuration to add to the `EarlyBootListener` example. `CustomRunListener` must implement `SpringApplicationRunListener` and have a standard constructor `(SpringApplication, String[])`. By contrast, `EarlyBootListener` only implements `ApplicationListener<SpringApplicationEvent>` and needs no special run-listener constructor.

If you only want to **receive `ApplicationStartingEvent`**, the simplest way is an early-registered `ApplicationListener<ApplicationStartingEvent>`. There is no need to implement a full `SpringApplicationRunListener`.

## 7. Approach 3 — SpringApplicationBuilder.listeners(...)

When creating the application via `SpringApplicationBuilder`, you can declare listeners before `run`:

```java
new SpringApplicationBuilder(EarlyEventsApplication.class)
        .listeners(new EarlyBootListener())
        .run(args);
```

This snippet requires importing `org.springframework.boot.builder.SpringApplicationBuilder`. It is an **alternative startup option** to `SpringApplication.addListeners(...)`, not a call added after the application has already finished running.

In principle, the listener must be registered before the bootstrap flow publishes the first event. If you do:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(EarlyEventsApplication.class, args);

// By now it is too late for ApplicationStartingEvent.
context.addApplicationListener(new EarlyBootListener());
```

the newly added listener can only receive future events from the context; past events **are not replayed automatically**. `ApplicationContext` does not provide a default historical queue for startup events.

## 8. Phases in Which Spring Boot Registers and Publishes Events

To understand this deeply, we can split the event flow into two phases.

### Phase A: Before ApplicationContext Is Ready

Spring Boot has an internal run listener, typically `EventPublishingRunListener`. It knows about listeners registered before `run(...)` and uses an initial event multicaster to send early notifications.

```text
new SpringApplication(...)
      |
      +-- Early-registered listeners exist:
      |      addListeners / SpringFactoriesLoader
      |
      v
run()
      |
      +-- ApplicationStartingEvent
      +-- ApplicationEnvironmentPreparedEvent
      +-- ApplicationContextInitializedEvent
      +-- ApplicationPreparedEvent
      |
      v
ApplicationContext proceeds to refresh
```

At that point, listener beans cannot be retrieved from a context that does not exist or has not refreshed yet. Hence these events are sent to the **early listener set**, without waiting for the bean container to be built first.

### Phase B: Once the Context Refreshes

When Spring runs refresh, bean- and annotation-based listener discovery and registration mechanisms are set up. Subsequent events can then be published through the `ApplicationContext`'s event infrastructure.

```text
ApplicationContext.refresh()
      |
      +-- Prepare ApplicationEventMulticaster
      +-- Register ApplicationListener beans
      +-- Discover @EventListener methods
      +-- Instantiate singletons and complete refresh
      |
      v
ContextRefreshedEvent
ApplicationStartedEvent
ApplicationReadyEvent
...
```

This diagram explains the two phases conceptually; in the framework source code, listener registration, singleton creation, and multicaster initialization follow more detailed ordering.

**Key conclusion:** before refresh, events cannot wait for an uncreated `@Component` bean. After refresh, that same bean can receive events **published from the point it has been registered**. Registering a listener does not cause `ApplicationStartingEvent` to be re-sent from the beginning.

## 9. Why Doesn't ApplicationPreparedEvent Usually Reach Beans Either?

A tricky question is: `ApplicationPreparedEvent` is published **after bean definitions have been loaded**, so why do bean listeners still miss it?

We must distinguish:

- **Bean definition exists:** the container knows the metadata for how to create the bean.
- **Bean instance is created:** Spring has run the constructor/factory method and appropriate injection steps.
- **Listener is registered with the event infrastructure:** the multicaster knows which instance or method to dispatch events to.

`ApplicationPreparedEvent` occurs **before refresh**. With typical `@Component` and `@EventListener` registration, the infrastructure that completes bean creation and listener registration has not yet reached the necessary stage.

```text
Bean definition loaded
       !=
Listener bean created
       !=
Listener registered to receive events
```

That is why `ApplicationPreparedEvent` can appear in `EarlyBootListener`'s log from `addListeners(...)`, while there is no corresponding log from `BeanEventsObserver.tooEarlyPrepared(...)`.

If you need to handle a task **before refresh**, consider:

- An `ApplicationListener<ApplicationPreparedEvent>` **registered before run** just to observe that milestone.
- `ApplicationContextInitializer` if you need to customize the created context before refresh and before loading primary sources.
- `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` when you need to adjust bean definitions using the purpose-built extension points.

Do not force a business bean to instantiate early just to listen for `ApplicationPreparedEvent`, as doing so can bypass post-processors and Spring's remaining lifecycle assumptions.

## 10. Choosing the Right Approach for Your Need

| Need | What to choose | Avoid |
| --- | --- | --- |
| Observe right when Boot starts running | Listener registered via `addListeners` or `spring.factories` for `ApplicationStartingEvent` | `@EventListener` bean expecting to be created immediately |
| Read prepared configuration before context | Early listener receiving `ApplicationEnvironmentPreparedEvent` | `@Autowired Environment` from a bean that does not exist yet |
| Add `PropertySource`s or adjust environment very early | An appropriate `EnvironmentPostProcessor` | Abusing controller/service beans |
| Customize context before refresh | An appropriate `ApplicationContextInitializer` | Calling `getBean` early on an unrefreshed context |
| Observe the pre-refresh milestone | Early listener receiving `ApplicationPreparedEvent` | Relying on `@Component` just because definitions exist |
| Run work needing repository/service beans after refresh | `ApplicationRunner` / `CommandLineRunner` | Running business logic inside `ApplicationStartingEvent` |
| Log startup after refresh | `@EventListener(ApplicationStartedEvent)` | Writing an overly early hook when unnecessary |
| Run logic after runners finish | `@EventListener(ApplicationReadyEvent)` | Treating `ApplicationStartedEvent` as already ready |
| Observe errors that may occur before context | Early listener receiving `ApplicationFailedEvent` | Relying solely on late-created bean listeners |
| Monitor long-term health after startup | Actuator health/readiness probes | Treating a one-time startup event as continuous monitoring |

Small applications rarely need very early hooks. Overly aggressive hooks increase startup complexity, make failures harder to trace, and tightly couple the program to Spring Boot bootstrap internals.

## 11. ApplicationFailedEvent: A Case Requiring Special Care

`ApplicationFailedEvent` occurs when `SpringApplication.run(...)` fails. However, **failure timing is not fixed**:

- Configuration or environment fails before the context is created.
- Context creation or loading bean definitions fails.
- A bean fails to initialize during `refresh()`.
- A runner throws an exception after the context has refreshed.

If the listener is only a bean, in the earlier cases **there is no guarantee the listener was built and registered**. Even when the context exists yet is inactive or refresh failed, do not assume every `@EventListener` finished registering.

An early listener can handle lightweight failure reporting:

```java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable cause = event.getException();
        String type = cause.getClass().getSimpleName();

        System.err.println("Startup failure: " + type);
    }
}
```

This is source code for `EarlyFailureListener.java`; add the appropriate package declaration and register it **before run** via `app.addListeners(new EarlyFailureListener())` or `spring.factories`. It does not need to access `ApplicationContext`, making it suitable when failures happen very early.

Keep failure callbacks simple:

- Do not call repositories, missing beans, or network APIs just to ship logs while the application is already failing.
- Do not print passwords, tokens, sensitive paths, or full command-line arguments.
- Do not throw another exception from the listener that masks the original failure.
- Do not assume `event.getApplicationContext()` always returns a context; the event may fire before a context was created.
- Consider recording the exception type and logging the stack trace via logging/diagnostics once available.

**There is no default event replay mechanism.** A bean listener created after a startup error has occurred cannot be used to "catch up" on that `ApplicationFailedEvent`.

## 12. Timing of ApplicationStartedEvent and ApplicationReadyEvent

The distinction between these two late events is also frequently overlooked:

**`ApplicationStartedEvent`:** published when the context has finished refreshing, **before** Spring Boot invokes `ApplicationRunner` and `CommandLineRunner`.

**`ApplicationReadyEvent`:** published **after** the runners complete successfully, right around when `run(...)` returns.

Example runner printing a log:

```java
@Bean
ApplicationRunner initializeCache() {
    return args -> {
        System.out.println("runner: loading cache");
        // Actual data initialization code if needed.
    };
}
```

A bean receiving `ApplicationStartedEvent` is invoked **before** `runner: loading cache`. A bean receiving `ApplicationReadyEvent` is invoked **after** that line if the runner succeeds.

Thus, if a bean-based listener receives `ApplicationReadyEvent` but not `ApplicationStartingEvent`, that is **correct behavior given registration timing**, not an inconsistency or random behavior.

One more detail: Spring Boot publishes `AvailabilityChangeEvent` to reflect `LivenessState` and `ReadinessState` at relevant milestones. Do not equate them with "pre-context" events. Bean listeners can observe availability changes once the context is ready.

## 13. Does an Early-Registered ApplicationListener Need to Be a Bean?

**No.** `SpringApplication.addListeners(new X())` already supplies a Java instance to Boot's event mechanism. There is no need to annotate `X` with `@Component` for it to work.

If you both annotate class `X` with `@Component` and manually call `new X()` during early registration, the program risks creating **two separate instances**. Consequences can include:

- The listener receives late events twice once both instances are registered.
- Data stored in one instance differs from the other instance.
- Autowired fields are populated only on the bean, not on the manually instantiated object.
- Cleanup and lifecycles of the two instances differ.

For listeners registered via `spring.factories`, the loader infrastructure also instantiates them separately and does not automatically reuse a singleton bean from the IoC container.

**Safe approach:** if a listener purely observes bootstrap events, keep it stateless or maintain small self-managed state. If the goal requires business beans, choose a bean listener for late events or combine with a cleanly designed intermediate mechanism instead of mixing two registration styles.

## 14. Ordering and Threading: Notes Affecting Reliability

### Ordering Among Multiple Listeners

Spring supports ordering via `Ordered` and `@Order` where appropriate. However, **do not rely on arbitrary classpath order or `@Component` declaration order** to drive business logic.

If two listeners both receive `ApplicationReadyEvent` and both update a resource, one listener running before the other should not be an implicit dependency. Instead, organize an orchestrating service with explicit ordering, or use appropriate lifecycle/runner infrastructure.

### Are Events Synchronous?

Under standard behavior, Spring listeners are invoked **synchronously on the event-publishing thread**. For very early bootstrap events, a long-blocking listener can slow down or fail the entire startup process.

`@Async` cannot be treated as a default fix for all early events: before context refresh, executor beans and async proxies may not exist yet. In particular, a listener instantiated directly via `new` does not automatically receive bean proxy capabilities.

**Good design:** early callbacks should be fast, have minimal dependencies, avoid unbounded network I/O, and avoid lengthy business work. Tasks needing beans or transactions should be moved to runners, lifecycle services, or a dedicated architecture.

### Parent/Child Contexts Can Emit Multiple Events

In a multi-`ApplicationContext` setup, events originating from a child context can propagate to parent contexts. A single listener may observe multiple events of the same type across different contexts. When filtering is needed, inspect the event's context and the context the listener is responsible for, rather than relying only on `getClass().getSimpleName()`.

This is distinct from missing early events, yet it is another key reason why event-counting tests must define their scope.

## 15. Common Mistakes and Diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `@EventListener(ApplicationStartingEvent)` does not run | Bean did not exist when event was published | Register listener before `run` |
| `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` does not run | Bean factory not created/refreshed yet | Use `addListeners` or `spring.factories` |
| `ApplicationPreparedEvent` does not reach bean despite definitions existing | Bean definition is not a registered listener instance | Use an early listener or a pre-refresh extension point |
| `ApplicationStartedEvent` received, `ApplicationStartingEvent` missed | Two events at two different milestones | Normal behavior; no annotation change needed |
| Listener from `spring.factories` does not run | Wrong key, path, class name, or constructor/packaging | Check `META-INF/spring.factories` on runtime classpath |
| Listener runs twice | Duplicate registration across `addListeners`, `spring.factories`, and bean | Pick one mechanism; inspect instances |
| Listener needs `@Autowired` but it is `null` | Listener created via `new`/loader, not an IoC bean | Do not inject beans during very early events |
| Listener breaks startup | Exception or blocking operation inside listener | Keep early callbacks simple; handle errors properly |
| Startup failure listener misses `ApplicationFailedEvent` | Failure occurred before listener bean was initialized | Register failure listener before `run` |
| `@EventListener(ApplicationReadyEvent)` does not run | Runner failed or startup did not finish | Inspect exceptions/`ApplicationFailedEvent` first |
| Test counts more events than expected | Multiple contexts or hierarchy in test | Target a specific context/run in the test |
| Registering listener after `run` misses Starting | Past events are not stored for replay | Register before the next run; do not wait for replay |
| Reading properties in `ApplicationStartingEvent` finds them missing | `Environment` not prepared yet | Choose `ApplicationEnvironmentPreparedEvent` or `EnvironmentPostProcessor` |
| Switched to `SpringApplicationRunListener` and listener fails to instantiate | Wrong constructor/key for run listener | Check Javadoc: run listeners have a different constructor contract |

Specific diagnostic workflow:

1. Identify the **event type** and **when it is published**.
2. Identify whether the listener was created via `new`, `spring.factories`, or the IoC container.
3. Check whether the listener was registered **before the event was published**.
4. If it is a bean, confirm the bean is scanned/registered, profiles/conditions match, and startup refresh succeeded.
5. For `@EventListener`, confirm the method has a Spring-supported signature and annotation processing infrastructure is active.
6. For `spring.factories`, verify the file actually sits on the **runtime** classpath, not only in sources.
7. If late events are missing too, check whether the app finished starting and whether an exception occurred midway.
8. Check for duplicate registration, context hierarchies, or a custom event multicaster altering counts or order.
9. Write a simple event-collecting test to distinguish "Spring did not publish" from "listener was not registered."

## 16. Testing Very Early Events Properly

You can verify a listener independently of a large application with a small class that registers itself before `run`:

```java
package demo.early;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class RecordingApplication {

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        ApplicationListener<SpringApplicationEvent> listener =
                event -> events.add(event.getClass().getSimpleName());

        SpringApplication app = new SpringApplication(RecordingApplication.class);
        app.setWebApplicationType(org.springframework.boot.WebApplicationType.NONE);
        app.addListeners(listener);

        try (var context = app.run(args)) {
            // No web server needed; observe after run() completes.
        }

        System.out.println(events.contains("ApplicationStartingEvent"));
        System.out.println(events.contains("ApplicationReadyEvent"));
    }
}
```

With a successful application startup and the listener configuration above, the two lines printed by the checks at the end are:

```text
true
true
```

In practice, Spring Boot banners/logs also appear. `ArrayList` in the example suits the default synchronous mechanism and demo thread; if using a custom async multicaster, consider concurrent access and assertion timing.

**Why not rely solely on `@SpringBootTest`?** The test framework may create, cache, or reuse contexts differently from running `main()` directly. When verifying pre-context events, a test can construct a `SpringApplication` with early-registered listeners and explicitly run/close the context; avoid tests opening extra servers or leaking resources.

Milestones worth asserting in tests:

- After the listener is added, **before `run`**: the list contains no events yet.
- During `run`: `ApplicationStartingEvent` is recorded before later events.
- After a successful `run`: `ApplicationReadyEvent` is present.
- If a runner throws an error: there is no `ApplicationReadyEvent` for that failed run; an early listener can receive `ApplicationFailedEvent`.
- When a listener is only a bean, do not expect it to observe the four early events in the Section 3 table.

Do not claim that a bean listener "receives no application events at all." It can still receive `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, and post-refresh business events.

## 17. Self-Check Exercises

1. A `@Component` class implements `ApplicationListener<ApplicationStartingEvent>`, yet prints no log. Does that prove the class was not component-scanned? What should you check first?
2. Why can `ApplicationPreparedEvent` fail to reach an `@EventListener` bean even though bean definitions have been loaded?
3. How do `ApplicationStartedEvent` and `ApplicationReadyEvent` differ with respect to runners?
4. If you register `new EarlyBootListener()` via `addListeners`, will Spring automatically inject a repository into the listener's constructor?
5. What is the `spring.factories` key for receiving events via `ApplicationListener`? How does it differ from the key for `SpringApplicationRunListener`?
6. Can you retroactively receive `ApplicationEnvironmentPreparedEvent` by registering a listener after `SpringApplication.run`? Why or why not?
7. Why should a listener receiving `ApplicationFailedEvent` from a very early error avoid accessing the context as if it is guaranteed to exist?
8. Why should you avoid executing a slow database query during `ApplicationStartingEvent`?
9. If a listener is registered via both `spring.factories` and `addListeners`, what can happen to the callback invocation count?
10. When is `EnvironmentPostProcessor` more appropriate than an application event listener?

### Conclusion

**Spring Boot publishes very early events before the IoC container can create listener beans.** Therefore, `@Component`, `@Bean`, and `@EventListener` do not guarantee reception of `ApplicationStartingEvent`, `ApplicationEnvironmentPreparedEvent`, `ApplicationContextInitializedEvent`, or `ApplicationPreparedEvent` on the standard startup path.

When you need to listen for those events, **create and register the `ApplicationListener` before `SpringApplication.run`**, via `addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or `META-INF/spring.factories`. When you only need to react after beans are ready, a bean-based listener is simpler and more appropriate. Choose the extension point based on **the exact timing and dependencies truly needed**, rather than trying to force one listener style across the entire lifecycle.

### Official References

- [Spring Boot 3.3 — SpringApplication, Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): event sequence and early listener registration.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `addListeners(...)` and the bootstrap flow.
- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html): run-level hooks, distinct from `ApplicationListener`.
- [Spring Framework — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation): `@EventListener` behavior once the bean context exists.
