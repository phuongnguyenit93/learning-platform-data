# ApplicationStartingEvent and ApplicationEnvironmentPreparedEvent

Spring Boot publishes application events throughout the startup process. Some events appear very early, before the ApplicationContext is created or refreshed. Two important events in this phase are `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`.

They allow listeners to observe two distinct milestones: when the application has just begun running, and when the Environment for the ApplicationContext has been prepared. Understanding their publication timing, accessible data, and listener registration methods helps place bootstrap logic in the right spot.

## 1. ApplicationStartingEvent

`ApplicationStartingEvent` belongs to package `org.springframework.boot.context.event`. Spring Boot publishes this event at the beginning of `SpringApplication.run()`, before the application's Environment and ApplicationContext are created.

At this time, you can record that startup has begun, but you cannot rely on:

- The application's ApplicationContext.
- Business beans.
- An Environment prepared with all application configuration sources.
- Configuration values loaded from `application.yml` and profiles.

This event suits very early tasks, such as recording a startup timestamp, initializing context-independent bootstrap observability, or collecting information that does not depend on application configuration.

Do not use this event to read application properties or fetch services from the Spring container, because those components are not ready yet.

## 2. ApplicationEnvironmentPreparedEvent

Spring Boot publishes `ApplicationEnvironmentPreparedEvent` when the Environment is prepared for the ApplicationContext, before the context itself is created. Publishing this event also triggers Environment-preparation listeners, including the listener that invokes `EnvironmentPostProcessor` implementations.

A listener can obtain the Environment from the event:

~~~java
ConfigurableEnvironment environment =
        event.getEnvironment();
~~~

The Environment provides access to:

- Existing property sources.
- Configuration values such as `spring.application.name`.
- Active profiles and default profiles.
- Environment attributes used to determine application configuration.

For example, you can read the application name and profiles:

~~~java
String applicationName = environment.getProperty(
        "spring.application.name",
        "unnamed"
);

String[] activeProfiles = environment.getActiveProfiles();
~~~

However, this is still the stage before the ApplicationContext is created. Listeners cannot fetch business beans from the context yet. If you need to register beans, use Spring's configuration mechanisms; if you need to add to or adjust the Environment during preparation, consider `EnvironmentPostProcessor`.

### Note on Config Data and Listener Ordering

Spring Boot processes the Environment through multiple steps and `EnvironmentPostProcessor` implementations. When `ApplicationEnvironmentPreparedEvent` is published, Boot's dedicated listener invokes these processors. The Config Data mechanism, including loading `application.yml`, profile-specific files, and config imports, participates in this Environment preparation phase.

`ApplicationEnvironmentPreparedEvent` marks the point where the Environment has been created and entered into context preparation. If a listener needs to observe results produced by a specific EnvironmentPostProcessor, listener order must be explicitly defined. Do not assume every listener sees the exact same Environment state if they are ordered at different points during event dispatch.

If the goal is to modify the Environment before configuration conditions or Config Data are processed, `EnvironmentPostProcessor` is the dedicated extension point. Using a listener to alter the Environment requires careful attention to execution order and event timing.

## 3. Comparing the Two Events

| Criterion | ApplicationStartingEvent | ApplicationEnvironmentPreparedEvent |
|---|---|---|
| Timing | Beginning of SpringApplication execution | When Environment is created and enters preparation |
| Application Environment | Not yet available | Accessible via the event |
| ApplicationContext | Not yet created | Not yet created |
| Business beans | Not yet available | Not yet available |
| Suitable work | Recording start milestone, standalone bootstrap | Reading Environment info, observing configuration |
| Can be used to get beans | No | No |

Abbreviated startup flow:

~~~text
SpringApplication.run()
        |
        v
ApplicationStartingEvent
        |
        v
Create and prepare Environment
        |
        v
ApplicationEnvironmentPreparedEvent
        |
        v
EnvironmentPostProcessor / Config Data
(invoked by Boot's listener in order)
        |
        v
Create ApplicationContext
        |
        v
ApplicationContextInitializer
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
refresh()
~~~

The diagram highlights the key milestones. Environment processing and event dispatch may involve multiple ordered listeners; when you need to intervene at a precise moment, use the extension point designed for that stage.

## 4. Registering Listeners for Early Events

Because both events are published before application beans are created, you cannot rely on a `@Component` class or an `@EventListener` method on a bean to catch them. Listeners must be registered with `SpringApplication` before calling `run()`, or discovered via the Spring factories mechanism.

For example, a listener observing both events:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartupListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("Application startup is beginning");
            return;
        }

        if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
            String applicationName = prepared.getEnvironment().getProperty(
                    "spring.application.name",
                    "unnamed"
            );

            String[] activeProfiles =
                    prepared.getEnvironment().getActiveProfiles();

            System.out.println("Application: " + applicationName);
            System.out.println(
                    "Active profiles: "
                            + String.join(", ", activeProfiles)
            );
        }
    }
}
~~~

Registering the listener before launch:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

When `run()` begins, the listener is already in `SpringApplication`'s listener list, so it can receive early events. This registration approach fits well when the application owns the main class and wants explicit control over which listeners are used.

Multiple listeners can be registered:

~~~java
application.addListeners(
        new EarlyStartupListener(),
        new StartupMetricsListener()
);
~~~

If a listener only needs one event type, it can implement the interface with that specific event type:

~~~java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

Using a specific type lets the compiler clearly express which event the listener handles.

## 5. Registering Listeners via Spring Factories

A library can declare its own listener so applications using the library discover it automatically. With Spring Boot, it can be declared in the `META-INF/spring.factories` resource:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.bootstrap.EarlyStartupListener
~~~

Spring Boot uses `SpringFactoriesLoader` to discover listeners under the corresponding key. When packaging the library, verify that the file is placed at the right path inside the JAR and that the fully qualified class name is exact.

This mechanism is useful when writing a library or starter that needs to observe early events without requiring applications to instantiate the listener in their main class.

Distinguish the two registration forms:

- `SpringApplication.addListeners(...)`: the application proactively registers listener instances.
- `META-INF/spring.factories`: a library publishes implementations for Spring Boot to discover.

For very early events, listeners must be registered before `SpringApplication.run()` publishes the corresponding event. Registering a listener after the application is already running will not replay previously published events to it.

## 6. Subsequent Events During Startup

After the first two events, Spring Boot continues publishing events marking different stages:

| Event | Timing | Available Components |
|---|---|---|
| `ApplicationContextInitializedEvent` | Context created and initializers run, before bean definitions load | Context exists; Environment and context metadata are accessible |
| `ApplicationPreparedEvent` | Bean definitions loaded, right before refresh | Context and bean definitions are prepared |
| `ContextRefreshedEvent` | ApplicationContext finishes refresh | Beans have been created per the refresh process |
| `ApplicationStartedEvent` | Context refreshed, before running ApplicationRunner and CommandLineRunner | Beans are ready; runners have not finished |
| `ApplicationReadyEvent` | After runners finish | Spring Boot signals the application is ready |
| `ApplicationFailedEvent` | Startup fails | Error details and context if a context was already created |

The first two events do not replace later ones. Choose the event based on the actual state your logic requires.

For example:

- Only need to mark that the application began starting: `ApplicationStartingEvent`.
- Need to read the Environment before the context is created: `ApplicationEnvironmentPreparedEvent`.
- Need to know initializers have finished: `ApplicationContextInitializedEvent`.
- Need to observe bean definitions loaded before refresh: `ApplicationPreparedEvent`.
- Need to run work after context refresh: `ApplicationStartedEvent` or a runner depending on requirements.
- Need to know Spring Boot's startup workflow has completed: `ApplicationReadyEvent`.

### ApplicationStartedEvent and ApplicationReadyEvent

These two events are easy to confuse. `ApplicationStartedEvent` is published after the context refreshes, but before `ApplicationRunner` and `CommandLineRunner` execute. `ApplicationReadyEvent` is published after runners complete and serves as Spring Boot's application-level readiness signal.

If work requires beans that have been created but does not need to wait for runners, consider `ApplicationStartedEvent`. If you need to act on or observe the state after runners, use `ApplicationReadyEvent`.

Do not use early events to run long tasks or call external systems unless the work is essential for bootstrap. Listeners running during startup can prolong startup time and cause startup to fail if they throw exceptions.

## 7. ApplicationListener and @EventListener

Spring offers two common ways to handle application events.

### ApplicationListener

`ApplicationListener<E>` is an event-typed interface. You can register a listener directly with `SpringApplication` to receive early events:

~~~java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Handle the starting milestone.
    }
}
~~~

This approach suits events published before the ApplicationContext is created or before beans are loaded.

### @EventListener

`@EventListener` is an annotation placed on a bean method:

~~~java
@Component
public class ReadyEventHandler {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

A bean containing this method is only registered when the context processes bean definitions and creates the bean. Therefore, this approach suits events published after the context already holds the listener bean, such as `ApplicationReadyEvent`.

Do not place `@EventListener` inside a bean to handle `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, because the bean has not been created yet when those events fire. Use an early listener registered with `SpringApplication`.

## 8. Things to Watch Out for When Handling Startup Events

### Do Not Assume the Environment Exists in ApplicationStartingEvent

This event fires before the application's Environment is prepared. If you need to read properties, wait for `ApplicationEnvironmentPreparedEvent` or use an appropriate extension point.

### Do Not Assume the ApplicationContext Exists in ApplicationEnvironmentPreparedEvent

The Environment exists, but the context has not been created yet. Listeners cannot fetch business beans from the context at this stage.

### Do Not Register Listeners Too Late

Listeners must be added before events fire. Calling `addListeners()` after `run()` does not replay earlier events.

### Do Not Perform Heavy Work Inside Listeners

Listeners execute synchronously during event dispatch. Slow I/O, network calls, or long processing can lengthen startup. Only run what is necessary for that stage and set explicit timeouts if performing external operations.

### Specify Listener Order When Observing Results from Another Listener

Multiple listeners can receive the same event. If one listener depends on Environment changes made by another listener, declare the order using `Ordered` or `@Order` per the supported mechanism and test the outcome. Do not rely on incidental classpath order or component scan order.

### Handle Startup Errors Intentionally

If a listener throws an exception during startup, the application may fail to start. If the error represents a mandatory condition, throw an exception with a clear message. If it is only telemetry or logging, isolate failures in the observability code so a secondary operation does not break startup.

## 9. Testing Listeners and Event Order

You can test listeners by launching a test `SpringApplication` and collecting the event sequence. A simple listener can append event names to a list or log:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public class StartupEventRecorder
        implements ApplicationListener<ApplicationEvent> {

    private final List<String> events = new ArrayList<>();

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            events.add("starting");
        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            events.add("environment-prepared");
        } else if (event instanceof ApplicationContextInitializedEvent) {
            events.add("context-initialized");
        } else if (event instanceof ApplicationPreparedEvent) {
            events.add("prepared");
        } else if (event instanceof ApplicationStartedEvent) {
            events.add("started");
        } else if (event instanceof ApplicationReadyEvent) {
            events.add("ready");
        }
    }

    public List<String> getEvents() {
        return List.copyOf(events);
    }
}
~~~

In an integration test, register the recorder with `SpringApplication` before running. After startup finishes, verify the order of key milestones:

~~~text
starting
environment-prepared
context-initialized
prepared
started
ready
~~~

When writing tests, keep in mind that additional events may be published in special scenarios such as parent/child contexts or launching multiple contexts. Assert the necessary ordering relationships rather than assuming every application emits only one event across its entire lifecycle.

## 10. Workflow for Choosing the Right Event

When you need to react to a startup stage, determine the minimum state your logic requires:

1. If you only need to know that startup has begun, use `ApplicationStartingEvent`.
2. If you need to read the Environment before the context is created, use `ApplicationEnvironmentPreparedEvent`.
3. If you need to customize the Environment before Config Data, consider `EnvironmentPostProcessor`.
4. If you need to customize the context before refresh, consider `ApplicationContextInitializer`.
5. If you need to process bean definitions, use `BeanFactoryPostProcessor` at the right refresh stage.
6. If you need business beans to be ready, choose an event or runner after refresh.
7. Register listeners before the event fires and define ordering if listeners depend on one another.
8. Keep listeners fast, handle errors predictably, and avoid accessing beans before the context is ready.

`ApplicationStartingEvent` marks when Spring Boot begins launching; `ApplicationEnvironmentPreparedEvent` marks when the Environment is available to prepare the ApplicationContext. Distinguishing these two milestones helps you read configuration at the right time, register listeners properly, and place bootstrap work in the appropriate phase of the Spring Boot lifecycle.
