# Pre-Context Listeners Cannot Simply Be Declared as Regular Beans

When starting a Spring Boot application, we may want to observe when the application begins running, inspect the early configuration environment, or handle a startup failure. Spring Boot publishes **application events** for these milestones. However, several events occur **before the `ApplicationContext` is created**. At that point, there is no complete Spring container yet to scan `@Component` classes, invoke `@Bean` methods, or register `@EventListener` methods.

Therefore, a listener that needs to receive these very early events **cannot simply be declared as a regular Spring bean**. It must be registered directly with `SpringApplication`, via `SpringApplicationBuilder`, or through a listener auto-discovery mechanism supported by Spring Boot.

This lesson distinguishes those startup phases, shows how to register listeners on time, and covers when to use an alternative mechanism such as `ApplicationContextInitializer`, `EnvironmentPostProcessor`, or `ApplicationRunner`.

## 1. Two Lifecycles to Distinguish

Spring Boot orchestrates startup using `SpringApplication`. During that process, it creates the `Environment`, builds the `ApplicationContext`, registers bean definitions, refreshes the context, and executes runners.

From an event listener's perspective, there are two phases:

1. **Before the context is created or ready:** `SpringApplication` is already active, yet application beans cannot be used as ordinary dependencies.
2. **After the context is initialized and refreshed:** beans have been created according to lifecycle rules, so listeners that are Spring beans can participate in appropriate events.

Overview diagram:

~~~text
main(String[] args)
         |
         v
SpringApplication.run(...)
         |
         v
ApplicationStartingEvent            <-- Context does not exist yet
         |
         v
Prepare Environment
         |
         v
ApplicationEnvironmentPreparedEvent <-- Context does not exist yet
         |
         v
Create ApplicationContext
         |
         v
ApplicationContextInitializedEvent   <-- Context exists, config not fully loaded
         |
         v
Load config sources and bean definitions
         |
         v
ApplicationPreparedEvent             <-- Context not yet refreshed
         |
         v
Refresh ApplicationContext
         |
         v
ApplicationStartedEvent              <-- Context refreshed
         |
         v
Run ApplicationRunner / CommandLineRunner
         |
         v
ApplicationReadyEvent                <-- Boot finished startup process
~~~

`ApplicationFailedEvent` may appear if startup fails. Depending on when the failure occurs, the application context **may not be created yet**, may be created but not refreshed, or may already exist. Hence, listeners needing to catch errors at all stages should also be registered early.

This is a conceptual sequence of common events; Spring Boot also includes detailed bootstrap, logging, and availability events depending on the version.

## 2. Key Startup Events

Spring Boot provides several event types in `org.springframework.boot.context.event`:

| Event | General Timing | Can You Rely Solely on a Bean Listener? |
|---|---|---|
| `ApplicationStartingEvent` | Right at the start of execution, before Environment/context preparation | **No** |
| `ApplicationEnvironmentPreparedEvent` | Environment is prepared for use, but context is not created yet | **No** |
| `ApplicationContextInitializedEvent` | Context created and initializers run, before full config loading | Should not rely on bean listener |
| `ApplicationPreparedEvent` | Context present, config sources loaded, not yet refreshed | Should not rely on bean listener |
| `ApplicationStartedEvent` | Context refresh finished, before runners execute | Can use Spring bean listener |
| `ApplicationReadyEvent` | After runners complete | Can use Spring bean listener |
| `ApplicationFailedEvent` | When startup fails | Register early to cover pre-context failures too |

For `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`, the reason is clear: **there is no context yet for application beans to receive events**. For events immediately after the context is created, bean listeners are also not guaranteed to be loaded or registered in time. Most cases needing to observe these milestones should use listeners registered on `SpringApplication` from the beginning.

Do not confuse `ApplicationStartedEvent` with `ApplicationReadyEvent`: the first occurs when the context has refreshed before runners execute; the second occurs after Boot finishes executing runners.

## 3. Why Aren't @Component or @Bean Enough for Very Early Events?

A common way to register a listener is annotating a class with `@Component`:

~~~java
package com.example.catalog.startup;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

This works for `ApplicationReadyEvent`. Spring discovers `ReadyListener` while processing configuration, instantiates the bean, and registers it to receive events once the context is ready.

However, if changed to:

~~~java
@Component
public class TooLateListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Application is starting");
    }
}
~~~

then the class is only instantiated as a bean **when the context processes component scanning**, whereas `ApplicationStartingEvent` was already published earlier. Events do not wait for beans to be created and then replay for them.

Similarly, declaring:

~~~java
@Configuration(proxyBeanMethods = false)
class ListenerConfiguration {

    @Bean
    ApplicationListener<ApplicationEnvironmentPreparedEvent> earlyListener() {
        return event -> System.out.println("Environment prepared");
    }
}
~~~

does not solve the issue. `@Bean` methods are only processed by Spring when the context starts loading configuration, after early environment events have already occurred.

The same limitation applies to `@EventListener` methods:

~~~java
@Component
class EarlyEventMethods {

    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        System.out.println("Starting");
    }
}
~~~

`@EventListener` is processed via Spring bean infrastructure after the context is built. It does not register this method with `SpringApplication`'s initial event broadcaster before the context exists.

**Rule:** If an event can occur before Spring instantiates listener beans, register the listener using a mechanism that exists before the context.

## 4. Method 1: SpringApplication.addListeners(...)

The most direct approach is instantiating the listener in Java and registering it before calling `run()`.

Suppose an application needs to observe `ApplicationEnvironmentPreparedEvent`.

### 4.1. Writing the Listener

~~~java
package com.example.catalog.startup;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {

        String appName = event.getEnvironment()
                .getProperty("spring.application.name", "unnamed");

        System.out.println("Preparing application: " + appName);
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

The listener uses the `Environment` available on the event. It needs no `@Component` and requires no Spring dependency injection.

### 4.2. Registering Before run()

~~~java
package com.example.catalog;

import com.example.catalog.startup.EarlyEnvironmentListener;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CatalogApplication.class);

        application.addListeners(new EarlyEnvironmentListener());
        application.run(args);
    }
}
~~~

The sequence now becomes:

~~~text
new SpringApplication(CatalogApplication.class)
             |
             v
addListeners(new EarlyEnvironmentListener())
             |
             v
run(args)
             |
             v
SpringApplication publishes ApplicationEnvironmentPreparedEvent
             |
             v
EarlyEnvironmentListener already present -> receives event
             |
             v
Continues to create ApplicationContext afterward
~~~

This is the key difference: the listener already exists **before `run()` starts the startup steps**, so it can receive events even though the context does not exist yet.

### 4.3. Why Doesn't @Autowired Work?

An object constructed with:

~~~java
new EarlyEnvironmentListener()
~~~

is a plain Java object added to `SpringApplication`'s listener list. It does not become a managed bean merely by being registered this way.

Therefore, do not design it like this:

~~~java
public final class EarlyEnvironmentListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Autowired
    private AuditService auditService; // Not injected just via addListeners.

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        auditService.recordStartup();
    }
}
~~~

`auditService` will not be automatically injected into an object created with `new`; moreover, at `ApplicationStartingEvent`, the `AuditService` bean has not even been created yet.

For early listeners, rely on data provided by the event, simple Java dependencies passed explicitly to the constructor, or bootstrap services designed for that phase. Do not attempt to look up business services via `ApplicationContext.getBean(...)` before the context exists.

## 5. Method 2: SpringApplicationBuilder.listeners(...)

If the application uses `SpringApplicationBuilder` to configure startup, listeners can be registered right in the builder chain:

~~~java
import com.example.catalog.startup.EarlyEnvironmentListener;
import org.springframework.boot.builder.SpringApplicationBuilder;

public class CatalogLauncher {

    public static void main(String[] args) {
        new SpringApplicationBuilder(CatalogApplication.class)
                .listeners(new EarlyEnvironmentListener())
                .run(args);
    }
}
~~~

`listeners(...)` places the listener onto `SpringApplication` while the builder configures the application, prior to execution.

This option is helpful when the program already uses the builder to configure profiles, sources, web application type, or a context hierarchy.

**Do not confuse with `@Bean`:** Builder listeners are registered at the bootstrap level. A listener bean declared in `@Configuration` is still instantiated per the context lifecycle.

If the application builds multiple contexts with the builder, identify which application the listener is registered on and which context emits the event. Startup events can involve multiple contexts, so listeners should not assume only a single startup event occurs across the whole JVM.

## 6. Method 3: Auto-Registering Listeners via META-INF/spring.factories

For a library or starter that does not control the host application's `main()`, requiring users to write `application.addListeners(...)` in every project can be inconvenient.

Spring Boot supports discovering certain listeners from the `META-INF/spring.factories` resource inside a JAR. They can be registered under the key `org.springframework.context.ApplicationListener`.

Example library layout:

~~~text
shared-startup-library/
└── src/main/
    ├── java/
    │   └── com/example/startup/
    │       └── StartupDiagnosticsListener.java
    └── resources/
        └── META-INF/
            └── spring.factories
~~~

Listener:

~~~java
package com.example.startup;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartupDiagnosticsListener
        implements ApplicationListener<ApplicationStartingEvent> {

    public StartupDiagnosticsListener() {
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Spring Boot startup has begun");
    }
}
~~~

Contents of `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupDiagnosticsListener
~~~

When the JAR containing this resource is on the runtime classpath, Boot can load the listener via its factory loading mechanism and register it early enough for the corresponding application events.

If there are multiple listeners, comma-separated class names can be declared in that property:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupDiagnosticsListener,\
com.example.startup.EarlyEnvironmentListener
~~~

Declared classes must support instantiation by the factory loader; a public no-args constructor is the simplest, most compatible choice for this example. Do not expect them to receive constructor injection like regular beans.

### 6.1. spring.factories Differs from AutoConfiguration.imports

In modern Spring Boot, a library's auto-configurations can be registered via:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

However, that file publishes **auto-configuration classes**. It does not replace registering early `ApplicationListener` implementations via `spring.factories`.

| Resource | Role |
|---|---|
| `META-INF/spring.factories`, key `org.springframework.context.ApplicationListener` | Registers listeners at the bootstrap level |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Publishes auto-configuration classes for Boot to process |
| `@Component` on a listener | Registers a listener bean when context/component scanning runs |

If a library needs to observe `ApplicationStartingEvent`, it cannot simply declare an auto-configuration with a `@Bean` method returning a listener and expect the first event: auto-configuration itself is processed after startup has already begun.

## 7. Example Listener for ApplicationStartingEvent

`ApplicationStartingEvent` occurs very early. At this moment there is no `ApplicationContext`, nor a fully prepared `Environment` for looking up properties as in later stages.

An appropriate listener should only do simple work:

~~~java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        String[] args = event.getArgs();

        System.out.println(
                "Spring Boot is starting; argument count = " + args.length
        );
    }
}
~~~

Registration:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new EarlyStartupListener());
app.run(args);
~~~

Do not access databases, call remote APIs, look up service beans, or use context objects here.

If you need to hook into early logging infrastructure, examine Spring Boot's logging/bootstrap mechanisms instead of trying to use a logger bean or service that does not exist yet. Also avoid printing raw command-line arguments if they could contain tokens, passwords, or secrets.

## 8. Example Listener for ApplicationEnvironmentPreparedEvent

`ApplicationEnvironmentPreparedEvent` is useful when you need to observe `ConfigurableEnvironment` before the application context is created.

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentInspectionListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {

        var environment = event.getEnvironment();

        boolean featureEnabled = environment.getProperty(
                "app.feature.enabled",
                Boolean.class,
                false
        );

        System.out.println("Feature enabled: " + featureEnabled);
    }
}
~~~

Register the listener before `run()` just like in the previous example.

### 8.1. Distinguishing an Existing Environment from a Fully Processed Environment

The event tells you the `Environment` exists, yet **the order among listeners and configuration processing steps still matters**. Depending on the version, configuration sources, and event listener order, a property source might not be loaded or added yet at the exact moment your listener executes.

If your listener needs to see properties provided by another Environment processing step, check execution order and design your bootstrap setup accordingly. Do not assert that all `application.yml` files, remote configuration, or custom property sources are guaranteed ready at every event milestone and every order value.

When only observing configuration, prefer side-effect-free logic. If you must add a property source to the Environment, `EnvironmentPostProcessor` usually expresses that responsibility more clearly than a general listener.

## 9. Early Listeners Can Receive ApplicationFailedEvent

`ApplicationFailedEvent` is published when Boot encounters an error while running. If you want to record errors that occur even before the context is created, you need a listener registered prior to startup:

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        System.err.println(
                "Application failed: " + failure.getClass().getSimpleName()
        );
    }
}
~~~

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new StartupFailureListener());
app.run(args);
~~~

Depending on the failure stage, `event.getApplicationContext()` may be `null` or reference an unready context. Do not rely on fetching beans from the context to handle early startup errors.

A listener recording failures does not replace Spring Boot's startup error handling and exit code processing. A listener can also throw its own errors; therefore, logic inside a failure listener should stay simple and avoid throwing exceptions that mask the root cause.

## 10. Listener Registration Methods and When They Take Effect

| Registration Method | Present Before Context Creation? | Best Suited For |
|---|---|---|
| `SpringApplication.addListeners(listener)` before `run()` | Yes | Very early events, application-controlled launcher |
| `SpringApplicationBuilder.listeners(listener)` | Yes, when builder configures the app | Apps using builder or multiple contexts |
| `META-INF/spring.factories` with `ApplicationListener` | Yes, via Boot factory loading | Libraries/starters needing auto-registration |
| `@Component` implementing `ApplicationListener<E>` | No | Events after the bean has been registered |
| `@Bean` returning `ApplicationListener<E>` | No | Events once context is appropriately configured |
| `@EventListener` method on a bean | No | Events published after context listener infrastructure is active |

An event already published before a listener bean exists will not automatically be replayed simply because the bean is registered later.

If the same listener class is both declared in `spring.factories` and registered via `@Component` or `@Bean`, multiple listener instances can be created and cause unpredictable behavior. Pick one appropriate registration model to avoid handling the same event twice.

## 11. Listener Execution Order: Ordered and @Order

When multiple listeners receive the same event, ordering can matter. Spring supports `Ordered` and `@Order` in compatible event multicasting mechanisms.

Example:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class AuditEnvironmentListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,
                   Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Inspecting prepared environment");
    }
}
~~~

By `Ordered` convention, smaller values have higher precedence and execute before larger values. `Ordered.HIGHEST_PRECEDENCE` indicates very high priority, while `Ordered.LOWEST_PRECEDENCE` indicates low priority.

Keep in mind:

- Ordering applies to the invocation sequence of listeners on a multicaster that supports sorting; it does not make a bean listener exist before context creation.
- Do not arbitrarily pick extreme high precedence if the listener needs results from other listeners/processors.
- Boot has critical internal listeners for preparing the Environment and logging; custom listeners must be careful with ordering when depending on those steps.
- Ordinary startup event listeners run synchronously during event dispatch; heavy work can slow down startup.

If you need data at a later lifecycle milestone, move to the appropriate event instead of tweaking `@Order` to access beans that do not exist yet.

## 12. ApplicationContextInitializer: Context Exists, Not Yet Refreshed

There are situations requiring intervention **after the context is created but before refresh**. In those cases, `ApplicationContextInitializer` is a better tool than `ApplicationStartingEvent`.

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public final class CatalogContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String appName = context.getEnvironment()
                .getProperty("spring.application.name", "catalog");

        System.out.println("Initializing context for " + appName);
    }
}
~~~

Register before run:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addInitializers(new CatalogContextInitializer());
app.run(args);
~~~

When the initializer is called, the context object already exists. However, the context **has not completed refresh**, so it should not be treated as a full container expecting all service/repository beans to be ready.

Comparison:

| Extension Point | Timing | Suitable Data Sources |
|---|---|---|
| `ApplicationStartingEvent` listener | Very early, no complete Environment/context yet | Startup arguments and available metadata |
| `ApplicationEnvironmentPreparedEvent` listener | Environment exists, no context yet | Environment and bootstrap metadata |
| `ApplicationContextInitializer` | Context created, not yet refreshed | Context object, Environment, appropriate bean factory metadata |
| Spring bean `@EventListener` | After listener bean has been registered | Bean dependencies and matching event |

`ApplicationContextInitializer` can also be registered via Boot-supported bootstrap mechanisms. However, a `@Component` bean implementing initializer will not automatically substitute for an initializer that must run before component scanning occurs.

## 13. EnvironmentPostProcessor: Changing Configuration Sources Very Early

If the requirement is adding or adjusting property sources before context creation, Spring Boot provides `EnvironmentPostProcessor`.

Example illustrating a property source containing module defaults:

~~~java
package com.example.catalog.startup;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class CatalogDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> defaults = Map.of(
                "app.catalog.enabled", "true"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogDefaults", defaults)
        );
    }
}
~~~

Register in `META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.catalog.startup.CatalogDefaultsEnvironmentPostProcessor
~~~

`addLast` places the property source at lower precedence than preceding sources, fitting a set of defaults. This is a simplified setup example; in production, you must control `EnvironmentPostProcessor` ordering and impact on the configuration system.

The purpose of `EnvironmentPostProcessor` is modifying Environment configuration. If you only want to record a startup milestone, `ApplicationListener` can be simpler. If you only want to inspect beans after the application runs, use a later-stage listener or runner.

## 14. Distinguishing Event Listeners from Runners

`ApplicationRunner` and `CommandLineRunner` are called by Boot **after context refresh completes**, yet **before `ApplicationReadyEvent`**.

Example:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Running startup data task");
    }
}
~~~

Runners are ordinary Spring beans, so constructor injection works as expected:

~~~java
@Component
public class StartupDataLoader implements ApplicationRunner {

    private final CatalogService catalogService;

    public StartupDataLoader(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.initializeReferenceData();
    }
}
~~~

This is the right choice when business operations depend on instantiated beans. It cannot stand in for `ApplicationStartingEvent` because runners are invoked at a much later milestone.

Selection table:

| Need | Usually Appropriate Tool |
|---|---|
| Know when `SpringApplication` begins running | Early-registered listener for `ApplicationStartingEvent` |
| Read Environment before context is created | Listener for `ApplicationEnvironmentPreparedEvent` |
| Add property sources during bootstrap | `EnvironmentPostProcessor` |
| Customize context right after creation, before refresh | `ApplicationContextInitializer` |
| Run tasks using Spring services/repositories after refresh | `ApplicationRunner` or `CommandLineRunner` |
| Know Boot finished running runners | Listener for `ApplicationReadyEvent` |
| Track failures even without a context | Early-registered `ApplicationFailedEvent` listener |

No single listener fits every kind of startup work. Each extension point sits at a distinct milestone in the lifecycle.

## 15. Logging, I/O, and Errors in Early Listeners

An early listener runs while the application is still in bootstrap. Therefore, do not assume:

- Loggers and logging configuration are finalized as they are once the application is ready.
- All property sources already contain their final values.
- AOP mechanisms like `@Transactional` or `@Async` are active for the listener.
- Databases, HTTP clients, or repositories can be injected from the context.
- The listener has a default transaction or request scope.
- You can block startup with a long network call without affecting readiness.

If a listener throws an exception during a critical startup stage, startup can be aborted. Keep logic lightweight, idempotent where needed, and apply a clear error policy.

Also avoid writing secrets, access tokens, passwords, or the full Environment/command-line arguments directly to logs. For startup diagnostics, log only non-sensitive metadata.

### Example to Avoid

~~~java
public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
    // Do not use an early listener to run DB-dependent business logic.
    // orderRepository.deleteAll();
    // remoteService.warmUp();
}
~~~

Those two dependencies are unlikely to exist when this event fires. If you need warm-up or migrations, use an appropriate mechanism after the container has all beans and dependencies ready.

## 16. Events Across Multiple Contexts and Duplicate Listener Execution

In applications with parent–child contexts or using `SpringApplicationBuilder` to create multiple applications, application events can involve multiple distinct contexts.

Spring `ApplicationContext` forwards events from child up to parent. If a listener is registered in both parent and child, or a global listener is attached to multiple `SpringApplication` instances, a single event can be observed multiple times depending on architecture.

When handling listeners in multi-context environments:

1. Identify which launcher or `SpringApplication` owns the listener.
2. Check whether the event belongs to the context the listener cares about.
3. Avoid initializing shared resources multiple times upon duplicate events.
4. If a listener handles `ContextRefreshedEvent` or `ApplicationReadyEvent`, do not assume the JVM emits only one event across all contexts.

If you need a single application-wide startup action, choose a clear registration point and lifecycle, and build in idempotence where appropriate.

## 17. Testing Pre-Context Listeners

A unit test calling `onApplicationEvent(...)` directly only tests handling logic given an event object. It does not prove the listener is actually registered at the right bootstrap moment.

To verify early registration, run a minimal Spring Boot application in a test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

class EarlyListenerRegistrationTest {

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfiguration {
    }

    @Test
    void programmaticListenerReceivesEnvironmentEvent() {
        AtomicInteger received = new AtomicInteger();

        SpringApplication app =
                new SpringApplication(MinimalConfiguration.class);

        app.setWebApplicationType(WebApplicationType.NONE);

        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> received.incrementAndGet()
        );

        try (ConfigurableApplicationContext context = app.run()) {
            assertThat(received.get()).isEqualTo(1);
        }
    }
}
~~~

The test uses a non-web context to minimize dependencies. The listener is registered before `app.run()`, and the assertion verifies `ApplicationEnvironmentPreparedEvent` was received.

To test the `spring.factories` mechanism, ensure the resource is on the test runtime classpath and the listener class is genuinely discovered by Boot factory loading. Write a test launching a minimal application and verifying an observable trace from the listener. Do not conclude `spring.factories` is correct simply because the listener class compiles.

### Scenarios Worth Testing

- Listeners via `addListeners` receive `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.
- Listeners that are solely `@Component` beans are not expected to receive pre-context events.
- Listeners registered via `spring.factories` work when the library is on the runtime classpath.
- `ApplicationReadyEvent` runs after runners as expected.
- Failure listeners handle pre-context errors when applicable.
- When listener ordering matters, verify with real events/bootstrap setup rather than guessing from `@Order`.

## 18. Common Errors

| Symptom | Cause to Check | How to Handle |
|---|---|---|
| `ApplicationStartingEvent` listener with `@Component` never runs | Bean is created after the event already fired | Register with `addListeners`, builder, or `spring.factories` |
| `@EventListener` method misses early environment event | Annotation listener infrastructure is not active yet | Use `ApplicationListener<E>` registered before run |
| Listener has `@Autowired` but field is `null` | Object was constructed with `new` and is not Spring-managed | Use event data or move bean-dependent logic to a later stage |
| Library listener does not run | Wrong `spring.factories` key/path, resource not packaged, or missing runtime JAR | Check metadata, packaging, and runtime classpath |
| AutoConfiguration.imports does not receive first event | Auto-configuration loads config while context is being built | Use `ApplicationListener` metadata in `spring.factories` |
| Listener reads property but value is missing | Property source not loaded yet or processing order mismatch | Check phase and listener ordering; consider `EnvironmentPostProcessor` |
| Listener executes repeatedly | Registered multiple times or multiple contexts/event propagation | Check registration locations and event source |
| Startup fails when listener runs | Early exception or I/O disrupted bootstrap | Minimize side effects, handle errors intentionally |
| Listener tries to use repository and cannot find it | Repository bean does not exist yet in startup phase | Use a runner, ready listener, or later lifecycle |

## 19. Design Principles

**Choose the right timing.** If you only need to know when the application starts or when the Environment is prepared, use a listener registered before `run()`. If you need to interact with services/repositories, wait until the context has refreshed.

**Do not rely on the bean registry before it exists.** `@Component`, `@Bean`, and `@EventListener` shine once Spring processes context beans; they do not automatically solve events occurring beforehand.

**Register listeners at the appropriate level.** Applications controlling `main()` can use `SpringApplication.addListeners`; builder-based applications can use `listeners(...)`; libraries/starters can use `spring.factories`.

**Keep early listeners small and independent.** Only use information provided by the event and safe bootstrap dependencies. Avoid business services, heavy I/O, or assumptions about proxies, transactions, and request scope.

**Use the right extension point for the right job.** `EnvironmentPostProcessor` for property sources, `ApplicationContextInitializer` for pre-refresh context, runners for post-refresh work, `ApplicationReadyEvent` for the application-ready milestone.

**Test with the real startup flow.** Instantiating a listener manually in a unit test and invoking it does not prove it is registered at the right phase.

Remember: **`SpringApplication` starts publishing events before `ApplicationContext` and Spring beans exist**. Consequently, listeners needing `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent` must be present from the bootstrap phase. Register them via `addListeners`, `SpringApplicationBuilder.listeners`, or `spring.factories`. Regular bean listeners remain the right choice for later events, once the container can instantiate, manage, and register them.
