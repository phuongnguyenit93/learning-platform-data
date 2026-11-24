# ApplicationContextInitializedEvent and ApplicationPreparedEvent

Spring Boot publishes several application events during startup. Two important events in the stage before the context is refreshed are `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent`. Both indicate that the application has passed a preparation milestone, but they occur at different times and the context is in different states.

- `ApplicationContextInitializedEvent` is published after the `ApplicationContext` has been created, the `Environment` has been attached to the context, and `ApplicationContextInitializer` instances have run, but before primary configuration sources are loaded as bean definitions.
- `ApplicationPreparedEvent` is published after the application's configuration sources have been loaded into the context and the context is ready to refresh, but before the refresh process starts.

Understanding these two milestones helps you know when you can observe the context, when bean definitions begin to appear, why a listener bean using `@EventListener` does not receive very early events, and which extension point to use to modify startup configuration.

This lesson targets Spring Boot 3.x. Some internal details may vary across versions, but the meaning of both events and their positions in the startup lifecycle are foundational for reading logs, writing listeners, and diagnosing startup failures.

## 1. Position of the Two Events in the Startup Lifecycle

When `SpringApplication.run(...)` is called, Spring Boot prepares the environment, creates the application context, loads configuration sources, refreshes the context, and only then executes runners and marks the application ready.

General sequence:

~~~mermaid
flowchart TD
    A["SpringApplication.run()"] --> B["ApplicationStartingEvent"]
    B --> C["Prepare Environment"]
    C --> D["ApplicationEnvironmentPreparedEvent"]
    D --> E["Create ApplicationContext"]
    E --> F["Run ApplicationContextInitializer"]
    F --> G["ApplicationContextInitializedEvent"]
    G --> H["Load application sources / initial bean definitions"]
    H --> I["ApplicationPreparedEvent"]
    I --> J["ApplicationContext.refresh()"]
    J --> K["Configuration processing, component scan, @Bean"]
    K --> L["Create singletons and finish ContextRefreshedEvent"]
    L --> M["ApplicationStartedEvent"]
    M --> N["ApplicationRunner / CommandLineRunner"]
    N --> O["ApplicationReadyEvent"]
~~~

Both events occur before `refresh()`. They do not mean the application is already serving requests or that all beans are ready.

| Event | Publication Milestone | Key State |
| --- | --- | --- |
| `ApplicationContextInitializedEvent` | After the context is created and initializers have run | Context has an Environment and has been prepared by initializers; application sources are not yet loaded |
| `ApplicationPreparedEvent` | After application sources are loaded, immediately before refresh | Context is ready for refresh; initial source bean definitions are registered |
| `ContextRefreshedEvent` | When refresh completes | Context is refreshed and regular eager singletons are initialized |
| `ApplicationStartedEvent` | After refresh, before runners | Context has started; runners have not completed |
| `ApplicationReadyEvent` | After runners complete | Application has completed the startup phase and is ready to receive traffic per Boot's lifecycle |

The event names look similar and are easy to confuse. Remember that *Initialized* is the milestone after context initializers, whereas *Prepared* is the milestone after application sources are loaded and before refresh.

## 2. What Is ApplicationContextInitializedEvent?

`ApplicationContextInitializedEvent` belongs to package `org.springframework.boot.context.event`. Spring Boot publishes this event when:

1. The `ApplicationContext` has been created.
2. The `Environment` has been set on the context.
3. `ApplicationContextInitializer` instances have been invoked.
4. Application sources have not yet been loaded into the context as bean definitions.

The event provides the context via `getApplicationContext()`. Thus, a listener can observe the context and environment at a very early point.

### 2.1. What Is Already Available at This Point?

Typically, a listener can:

- Read `context.getId()` and context information.
- Read active/default profiles via `context.getEnvironment()`.
- Inspect properties already loaded into the Environment.
- Observe changes made by `ApplicationContextInitializer`.
- Log or collect diagnostic information about the startup phase.

Example reading profiles:

~~~java
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Active profiles: "
                        + String.join(
                                ",",
                                context.getEnvironment().getActiveProfiles()
                        )
        );
    }
}
~~~

The listener above does not need to be a Spring bean. It can be registered directly with `SpringApplication` before calling `run`.

### 2.2. Application Bean Definitions Are Not Yet Loaded

At the time `ApplicationContextInitializedEvent` is published, Spring Boot has not loaded primary application sources into the context. Therefore, you should not expect classes declared via `@SpringBootApplication`, component scanning, or `@Bean` methods to be full bean definitions yet.

The context may already contain infrastructure or bean definitions registered explicitly by an initializer. Hence, you should not claim the bean factory is always empty. The important point is that **the application's primary configuration sources have not been loaded at this milestone**.

If you need to register definitions or alter the context structure before application sources are loaded, `ApplicationContextInitializer` is usually a better extension point than waiting for the event and modifying the context.

### 2.3. This Event Does Not Mean Beans Have Been Created

`ApplicationContextInitializedEvent` occurs before `refresh()`. Regular eager singletons have not been created and `@PostConstruct` callbacks have not run.

Avoid calling `context.getBean(...)` to retrieve application services at this moment. The bean definition might not exist yet; even if an initializer registered a definition, eagerly instantiating a bean too early can alter the lifecycle order the application expects.

## 3. What Is ApplicationPreparedEvent?

`ApplicationPreparedEvent` also belongs to package `org.springframework.boot.context.event`. It is published when `SpringApplication` has finished preparing the `ApplicationContext` and the context is ready to be refreshed.

At this point:

- The Environment has been prepared and attached to the context.
- Application sources have been loaded into the context.
- Initial bean definitions from sources have been registered.
- The context has not been refreshed yet.
- Full configuration processing, bean instantiation, and lifecycle callbacks have not completed.

Listeners receive the context via `event.getApplicationContext()`.

Example:

~~~java
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class ApplicationPreparedLogger
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("Prepared context: " + context.getId());
        System.out.println(
                "Initial bean definition count: "
                        + context.getBeanFactory().getBeanDefinitionCount()
        );
    }
}
~~~

The snippet reads the bean definition count to observe the preparation stage. The actual number depends on the context type, sources, and initializers; do not use a fixed count as a business condition.

### 3.1. What Does "Application Sources Have Been Loaded" Mean?

When running:

~~~java
@SpringBootApplication
public class DemoApplication {
}
~~~

class `DemoApplication` is passed to `SpringApplication` as a primary source. During the loading phase, Spring registers that source class in the bean factory as configuration to be processed.

However, distinguish between **registering source configuration** and **finishing all configuration processing**. Steps such as reading `@Configuration`, processing `@ComponentScan`, finding components, and registering `@Bean` methods normally happen during refresh, via bean factory post-processors such as `ConfigurationClassPostProcessor`.

Therefore, at `ApplicationPreparedEvent`:

- You can observe the loaded source bean definitions.
- You should not assume every component in scanned packages has been registered.
- You should not assume every `@Bean` method has been invoked.
- You should not assume services/repositories/controllers have been instantiated.
- You should not call business beans to perform startup work.

### 3.2. Prepared Is Not Synonymous with Ready

`ApplicationPreparedEvent` occurs before refresh. The application has not finished creating beans, the web server is not necessarily started, and `ApplicationRunner`/`CommandLineRunner` have not run.

If the goal is to perform an action after the entire context has refreshed, look at `ApplicationStartedEvent`, `ApplicationReadyEvent`, or the corresponding lifecycle API instead of using the prepared event.

## 4. Direct Comparison of the Two Events

| Criterion | ApplicationContextInitializedEvent | ApplicationPreparedEvent |
| --- | --- | --- |
| Context created | Yes | Yes |
| Environment attached to context | Yes | Yes |
| ApplicationContextInitializer run | Yes | Yes |
| Application sources loaded | No | Yes |
| Initial source bean definitions registered | Not yet via source loading | Yes |
| Component scan completed | No | Cannot be assumed; usually processed during refresh |
| `@Bean` methods invoked | No | Cannot be assumed |
| Context refreshed | No | No |
| Regular eager singletons ready | No | No |
| Good for observing | Context after initializers | Context after loading sources |
| Extension point to modify context | ApplicationContextInitializer | Typically initializer or appropriate bean factory post-processor |

You can remember them with two sentences:

- `ApplicationContextInitializedEvent`: the context has been created and initializers have run; application configuration sources have not been loaded yet.
- `ApplicationPreparedEvent`: configuration sources have been loaded; the context is awaiting refresh.

## 5. Why Must Listeners Be Registered Before the Context Creates Beans?

This is a critical point when handling these two very early events.

A listener implementing `ApplicationListener<ApplicationContextInitializedEvent>` or `ApplicationListener<ApplicationPreparedEvent>` must be known to Spring Boot **before the corresponding events are published**.

The simplest approach is registering them directly on `SpringApplication`:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        );

        application.run(args);
    }
}
~~~

`addListeners(...)` accepts `ApplicationListener` instances. When Spring Boot publishes startup events, the listeners are already registered and can receive events at the right moment.

This approach is clean for demonstrations and useful when the launcher needs explicit control over listeners.

### 5.1. Registering via META-INF/spring.factories

A library may want to register a listener automatically when placed on the classpath. With Spring Boot, application listeners can be declared in the file:

~~~text
META-INF/spring.factories
~~~

Example contents:

~~~properties
org.springframework.context.ApplicationListener=\
com.acme.bootstrap.ContextInitializedLogger,\
com.acme.bootstrap.ApplicationPreparedLogger
~~~

This file sits in the resources directory of the library JAR. Spring Boot uses the SpringFactoriesLoader mechanism to discover the listed listeners.

Version note:

- Spring Boot 3 uses `AutoConfiguration.imports` to register auto-configuration classes.
- `spring.factories` still plays a role for certain extension points such as `ApplicationListener` and `ApplicationContextInitializer`.
- Do not mistakenly move listeners into `AutoConfiguration.imports`; that file is for the auto-configuration list.

A library should carefully weigh side effects when auto-registering startup listeners. A listener loaded on the classpath can run in every application using the library, even when an application does not want that behavior.

### 5.2. Registering via SpringApplicationBuilder

If using the builder:

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .listeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        )
        .run(args);
~~~

This approach is convenient when the launcher configures a parent/child context or needs a fluent configuration chain. For a simple application, `SpringApplication.addListeners` is clear enough.

## 6. Why Doesn't @EventListener in a Bean Receive These Two Events?

You might try:

~~~java
@Component
public class StartupEventBean {

    @EventListener
    public void onContextInitialized(
            ApplicationContextInitializedEvent event) {
        // Typically does not receive this very early event.
    }

    @EventListener
    public void onApplicationPrepared(ApplicationPreparedEvent event) {
        // Also does not receive this pre-refresh event.
    }
}
~~~

The reason is that `@EventListener` relies on beans and Spring context annotation processing. The bean containing these methods is only discovered/instantiated during refresh. `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent` were already published before that point.

The same principle applies to a `@Component` class implementing `ApplicationListener`: if the class is only discovered through component scanning, it is likewise not ready to receive events published before component scanning takes place.

Distinguish the two groups:

| Registration Method | Can Receive Pre-Refresh Events? | Reason |
| --- | --- | --- |
| `SpringApplication.addListeners(...)` | Yes | Listener is registered before run |
| `META-INF/spring.factories` with ApplicationListener | Yes | Listener is loaded by Spring Boot during preparation |
| `@Component` implementing ApplicationListener | Should not be relied upon | Component scanning happens during refresh |
| Bean with `@EventListener` method | No | Listener method is registered from a bean inside the context |
| `ApplicationContextInitializer` | Not an event listener | Callback invoked directly during context preparation |

`@EventListener` is great for events published while the application is already running, such as domain/application events, or context events where the listener bean is already registered before the event occurs. For early startup events, use early-registered listeners.

## 7. How Does ApplicationContextInitializer Differ from ApplicationContextInitializedEvent?

The two names look very similar, yet one is an **extension callback** and the other is a **notification event**.

`ApplicationContextInitializer`:

- Is an interface with an `initialize(context)` method.
- Is invoked by SpringApplication during context preparation.
- Can customize the context before application sources are loaded.
- Can be registered via `SpringApplication.addInitializers(...)` or the appropriate factories mechanism.

`ApplicationContextInitializedEvent`:

- Is an application event published after initializers have run.
- Lets listeners observe the context state at that milestone.
- Is not a callback Spring invokes to ask listeners to modify the context.

Initializer example:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class StartupContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("demo-application-context");
        // Can register additional bean definitions or prepare the context
        // according to bootstrap requirements.
    }
}
~~~

Registration:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.addInitializers(new StartupContextInitializer());
application.addListeners(new ContextInitializedLogger());

application.run(args);
~~~

When `ApplicationContextInitializedEvent` is published, the listener can observe the context after the initializer has done its work.

### 7.1. When to Use an Initializer?

Use `ApplicationContextInitializer` if you need to:

- Modify or prepare the context before loading application sources.
- Register a bean definition at a very early stage.
- Configure part of the context setup before refresh.
- Integrate a framework that requires a standard callback during bootstrap.

Use `ApplicationContextInitializedEvent` if you need to:

- Record the milestone that the context has been created.
- Inspect the Environment after initializers run.
- Collect diagnostic information.
- Signal another early-registered infrastructure listener.

Do not use an event listener solely to do work for which an initializer already provides a clear contract.

## 8. How Does ApplicationPreparedEvent Differ from BeanFactoryPostProcessor?

`ApplicationPreparedEvent` indicates that the context is ready to refresh and application sources have been loaded. However, if the goal is to intervene in bean definitions or metadata before beans are created, Spring has more specialized extension points.

### 8.1. BeanFactoryPostProcessor

`BeanFactoryPostProcessor` operates on the bean factory after bean definitions have been loaded, but before regular singletons are instantiated.

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.stereotype.Component;

@Component
public class DefinitionInspector implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        String[] names = beanFactory.getBeanDefinitionNames();

        for (String name : names) {
            // Inspect bean definition metadata.
        }
    }
}
~~~

This example illustrates the lifecycle position. In practice, do not add a processor just to log every bean; you can use the condition report, Actuator, or appropriate diagnostic tools.

### 8.2. BeanDefinitionRegistryPostProcessor

If you need to register additional bean definitions before regular bean factory post-processors run, you can use `BeanDefinitionRegistryPostProcessor`:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class ExtraDefinitionRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {
        // Register additional BeanDefinitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        // Process the bean factory after the registry phase.
    }
}
~~~

This is a specialized extension point for the bean definition registry. Registering the processor must follow the proper lifecycle so Spring discovers it during refresh; do not arbitrarily instantiate processors by calling `getBean` inside `ApplicationPreparedEvent`.

### 8.3. Choosing the Right Tool

| Need | Appropriate Mechanism |
| --- | --- |
| Modify context before sources are loaded | `ApplicationContextInitializer` |
| Observe context after initializers run | `ApplicationContextInitializedEvent` |
| Observe context after sources are loaded, before refresh | `ApplicationPreparedEvent` |
| Modify bean definitions/metadata during refresh | `BeanDefinitionRegistryPostProcessor` or `BeanFactoryPostProcessor` |
| Create beans conditionally based on classpath/properties | Auto-configuration and conditions |
| Perform tasks after context refresh | `ApplicationStartedEvent`, runners, or appropriate lifecycle |
| Perform tasks after runners complete | `ApplicationReadyEvent` |

## 9. Observing Bean Definitions in ApplicationPreparedEvent

A listener can read metadata from the bean factory without requiring bean creation:

~~~java
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class BeanDefinitionCountListener
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var beanFactory = event.getApplicationContext().getBeanFactory();

        System.out.println(
                "Bean definitions at prepared stage: "
                        + beanFactory.getBeanDefinitionCount()
        );

        for (String name : beanFactory.getBeanDefinitionNames()) {
            System.out.println("Definition: " + name);
        }
    }
}
~~~

This is a metadata-reading operation. The list at this stage might not yet reflect the final result of component scanning and configuration class processing.

If you want to know exactly which beans component scanning registered, observe after configuration classes are processed during refresh, or inspect the context after refresh. Do not use the definition count at the prepared event as the final bean count.

### 9.1. Why Not Call getBean at This Stage?

Calling `getBean` before refresh can:

- Fail to find the bean because its definition has not been registered yet.
- Trigger premature instantiation outside the normal lifecycle.
- Create an incomplete dependency graph.
- Cause post-processors or proxies not to be applied as expected.
- Fail when a bean needs infrastructure that is only prepared during refresh.

If you need to read metadata, use `getBeanDefinition` or bean factory APIs at the appropriate level. If you need to use actual objects, wait for a stage after refresh.

## 10. Relationship with Other Startup Events

These two events sit within a longer chain of events. Knowing neighboring milestones helps you pick the right moment for a task.

| Event | When Published | What It Is Used For |
| --- | --- | --- |
| `ApplicationStartingEvent` | When SpringApplication begins running | Record startup very early |
| `ApplicationEnvironmentPreparedEvent` | Environment has been prepared | Observe environment before context creation |
| `ApplicationContextInitializedEvent` | Context created and initializers run | Observe context after initializers |
| `ApplicationPreparedEvent` | Sources loaded, before refresh | Observe context awaiting refresh |
| `ContextRefreshedEvent` | Context refresh completes | React to the context's refresh lifecycle |
| `WebServerInitializedEvent` | Web server has been initialized | Retrieve server info such as actual port |
| `ApplicationStartedEvent` | After refresh, before runners | Know the context has started |
| `ApplicationReadyEvent` | After runners | Know the application completed startup |
| `ApplicationFailedEvent` | Startup fails | Record startup error |

Events may be published during the same startup run while serving different purposes. For instance, if you need the actual port of the embedded server, `ApplicationPreparedEvent` is too early; observe `WebServerInitializedEvent`. If you need to run a task after runners finish, use `ApplicationReadyEvent`.

### 10.1. ContextRefreshedEvent Is Not ApplicationPreparedEvent

`ContextRefreshedEvent` is published when the context has refreshed. By this point, configuration class processing and bean factory post-processing have taken place, regular eager singletons have been instantiated, and initialization callbacks have run.

`ApplicationPreparedEvent` only signals that the context is ready to refresh. It does not guarantee that business beans are usable yet.

### 10.2. ApplicationStartedEvent and ApplicationReadyEvent

`ApplicationStartedEvent` is published after context refresh completes, but before `ApplicationRunner` and `CommandLineRunner` execute.

`ApplicationReadyEvent` is published after runners finish. This is typically the right milestone if work needs initialized beans and completed startup runners.

Do not use the prepared event for work requiring database clients, repositories, a web server, or fully initialized services.

## 11. Complete Example: Registering and Logging Both Events

The example consists of a minimal Boot application and two standalone listeners.

### 11.1. Application Class

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        );

        application.run(args);
    }
}
~~~

### 11.2. Listener for ApplicationContextInitializedEvent

~~~java
package com.example.demo.bootstrap;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("[ContextInitialized]");
        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Profiles: "
                        + String.join(
                                ",",
                                context.getEnvironment().getActiveProfiles()
                        )
        );
    }
}
~~~

### 11.3. Listener for ApplicationPreparedEvent

~~~java
package com.example.demo.bootstrap;

import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class ApplicationPreparedLogger
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("[ApplicationPrepared]");
        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Initial definitions: "
                        + context.getBeanFactory().getBeanDefinitionCount()
        );
    }
}
~~~

The two listener classes do not need `@Component` because they are instantiated and registered directly in the launcher. They can receive events before Spring creates application beans.

### 11.4. Illustrative Log Output

~~~text
[ContextInitialized]
Context id: application
Profiles: local

[ApplicationPrepared]
Context id: application
Initial definitions: 1
...
Started DemoApplication
~~~

The bean definition count in this example is illustrative; it varies by sources, initializers, and version. The ordering of the two events is what matters: context initialized is published before application prepared.

## 12. Testing the Order of the Two Events

You can verify both events using a real `SpringApplication` in a test. There is no need to start a web server if only testing the startup lifecycle; setting the web type to `NONE` keeps the test concise.

JUnit 5 example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.ConfigurableApplicationContext;

class StartupEventsTest {

    @Configuration(proxyBeanMethods = false)
    static class TestApplication {
    }

    @Test
    void publishesContextInitializedBeforeApplicationPrepared() {
        List<String> observed = new ArrayList<>();

        SpringApplication application =
                new SpringApplication(TestApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationContextInitializedEvent>)
                        event -> observed.add("context-initialized"),
                (ApplicationListener<ApplicationPreparedEvent>)
                        event -> observed.add("application-prepared")
        );

        try (ConfigurableApplicationContext context = application.run()) {
            assertThat(context.isActive()).isTrue();
        }

        assertThat(observed).containsSubsequence(
                "context-initialized",
                "application-prepared"
        );
    }
}
~~~

The test demonstrates registering listeners before calling `run` and asserting event publication order. The project needs appropriate test dependencies, such as the Spring Boot test starter for JUnit and AssertJ via dependency management.

### 12.1. Testing That an Initializer Runs Before ContextInitializedEvent

You can add an initializer that sets a marker:

~~~java
application.addInitializers(context -> {
    context.getEnvironment().setActiveProfiles("test");
});
~~~

Inside the `ApplicationContextInitializedEvent` listener, read active profiles and verify that profile `test` has been set.

This test verifies the order of the initializer callback and the event. When changing the Environment for production configuration goals, choose the proper extension point for altering properties/profiles; this example mainly illustrates the lifecycle.

### 12.2. Testing ApplicationPreparedEvent Is Not Where to Check Bean Readiness

Do not write tests that call `context.getBean(MyService.class)` inside a prepared listener and treat that as startup verification. Such tests can force premature bean instantiation and no longer verify normal lifecycle behavior.

If the goal is to test beans after refresh, obtain beans from the context after `application.run()` completes. If the goal is to inspect bean definitions, use bean factory APIs or test a `BeanFactoryPostProcessor`.

## 13. Using Early Events for Startup Diagnostics

Both events are very helpful when you need to know which milestone the application reached before an error occurred.

### 13.1. Recording the Prepared Environment

In `ApplicationContextInitializedEvent`, you can record:

- Context ID.
- Active profiles.
- Default profiles.
- Selected non-sensitive properties.
- Environment name or startup mode.

Do not log passwords, tokens, private keys, or the entire Environment because that can leak secrets.

### 13.2. Recording Initial Source Definitions

In `ApplicationPreparedEvent`, you can record:

- Context ID.
- Initial bean definition count.
- List of primary sources if managed by the application.
- Non-sensitive startup configuration info.
- Timestamp right before refresh.

This data helps distinguish whether an error occurred before loading sources, during refresh, or after the application became ready.

### 13.3. Do Not Replace the Condition Report with Early Listeners

If you need to know why an auto-configuration did not match, Spring Boot's condition evaluation report or debug mode is usually more helpful than manually listing bean definitions in the prepared event.

Early listeners can record startup milestones and environment state, but they do not automatically provide full conclusions about every condition evaluated during refresh.

## 14. Common Mistakes

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Listener does not receive ApplicationContextInitializedEvent | Listener was only registered via component scan or @EventListener | Register before run with addListeners or spring.factories |
| Listener does not receive ApplicationPreparedEvent | Listener bean did not exist yet when event was published | Use an early-registered ApplicationListener |
| Calling getBean in ContextInitializedEvent fails | Application sources have not been loaded yet | Use an initializer or wait until after refresh |
| Calling a service in ApplicationPreparedEvent errors | Context not refreshed, bean may not be created yet | Wait for ApplicationStartedEvent/Ready or use the right extension point |
| Component-scanned bean missing in prepared event | Configuration class processing occurs during refresh | Observe after refresh or use a bean factory post-processor |
| Assuming ApplicationPreparedEvent means server opened its port | Confusing prepared with web server initialized | Monitor WebServerInitializedEvent |
| Listener invoked twice in multi-context app | Parent/child context or multiple SpringApplications | Log context ID and identify which context owns the event |
| Listener slows down startup | Performing I/O or heavy work inside early callbacks | Move work to an appropriate lifecycle/runner |
| Flaky tests due to static listener state | Using shared mutable state across context runs | Use per-test state and close contexts |
| Property change has no effect | Intervened after expected property binding/condition stage or wrong order | Use EnvironmentPostProcessor or configure earlier |

### 14.1. Listener Not Discovered

Check whether the listener was registered before `SpringApplication.run`. If using `spring.factories`, verify the file sits at the proper resource path inside the JAR and the key is `org.springframework.context.ApplicationListener`.

Do not place a listener in a scanned package and expect it to receive events published before component scanning.

### 14.2. Calling Beans Too Early

Both `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent` occur before refresh. Do not use them to access repositories, services, or clients that require completed bean lifecycles.

If work needs objects, use a runner or post-refresh event. If work only needs metadata, read bean definitions instead of instantiating beans.

### 14.3. Confusing Multiple Contexts

An application may create multiple contexts, such as parent/child or separate test contexts. A listener registered at the SpringApplication level can observe events from the corresponding context creation flow. When logging, include the context ID or identity so you do not mistake events from different contexts for duplicate events in the same context.

## 15. Choosing an Extension Point by Timing

Start with the question "what do I need to do and before which milestone must it happen?":

| Requirement | Timing / Mechanism to Use |
| --- | --- |
| Modify Environment before creating context | `EnvironmentPostProcessor` |
| Prepare context before loading application sources | `ApplicationContextInitializer` |
| Observe context after initializers run | `ApplicationContextInitializedEvent` |
| Observe context after loading sources, before refresh | `ApplicationPreparedEvent` |
| Register/modify bean definitions during refresh | `BeanDefinitionRegistryPostProcessor` |
| Adjust bean metadata before creating singletons | `BeanFactoryPostProcessor` |
| React when context finishes refreshing | `ContextRefreshedEvent` |
| Run task after context starts, before runners | `ApplicationStartedEvent` |
| Run task after runners finish | `ApplicationReadyEvent` or appropriate runner |
| Manage start/stop of components by phase | `SmartLifecycle` |

Some extension points are invoked very early and can heavily affect startup. Choose the minimal mechanism that meets the requirement and keep callback work brief with controllable error handling.

## 16. Practice Exercises

### Exercise 1 — Record Both Events

Create two classes implementing `ApplicationListener` for `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent`. Register them using `SpringApplication.addListeners`. Run the application and record the order of appearance.

### Exercise 2 — Observe an Initializer

Create an `ApplicationContextInitializer` to set a profile or context ID. In `ApplicationContextInitializedEvent`, read back the value just set. Explain why the listener can observe that change.

### Exercise 3 — Compare Bean Definitions

In `ApplicationPreparedEvent`, log the initial number of bean definitions. After `application.run()` finishes, log the definition count again. Explain why the two numbers can differ.

### Exercise 4 — Demonstrate That @EventListener Arrives Too Late

Create a component with an `@EventListener` method receiving `ApplicationPreparedEvent`. Compare it with a listener added via `SpringApplication.addListeners`. Observe which listener receives the event and explain the component scan lifecycle.

### Exercise 5 — Choose Extension Points

Given three requirements:

1. Add a property source before auto-configuration conditions are evaluated.
2. Register a bean definition before refresh.
3. Log when the context has refreshed and services can be used.

Choose an extension point for each requirement and explain why the two early events are not suitable for every task.

## 17. Key Takeaways

`ApplicationContextInitializedEvent` is published after Spring Boot creates the `ApplicationContext`, attaches the Environment, and invokes `ApplicationContextInitializer` instances, but before application sources are loaded. It is suitable for observing the context after initializers and recording early startup info.

`ApplicationPreparedEvent` is published after application sources have been loaded and the context is ready to refresh. Initial source bean definitions have been registered, but the context has not refreshed yet; configuration class processing, component scanning, `@Bean` registration, and regular singleton instantiation are not complete. It is suitable for observing the milestone right before refresh, not for calling business services.

Both events must be listened to with an `ApplicationListener` registered early via `SpringApplication.addListeners` or the `spring.factories` mechanism. Beans discovered only via component scanning and `@EventListener` methods are normally registered too late to receive them.

If you need to modify the context, use `ApplicationContextInitializer`; if you need to modify bean definitions during refresh, use a bean factory post-processor; if you need ready services, wait until after refresh or after runners as needed. Choosing the right lifecycle milestone keeps startup observable, testable, and free of premature bean creation.
