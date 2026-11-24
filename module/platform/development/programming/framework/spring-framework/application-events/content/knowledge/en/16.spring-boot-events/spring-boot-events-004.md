# ApplicationContextInitializedEvent in Spring Boot

`ApplicationContextInitializedEvent` is an **early startup event** in Spring Boot, belonging to the `SpringApplicationEvent` hierarchy. Spring Boot publishes this event once the `ApplicationContext` has been created and prepared and `ApplicationContextInitializer`s have been invoked, **but before Spring Boot loads bean definitions from the main application sources**.

It answers the question: **"Has Spring finished creating and preliminarily configuring the context, before starting to load the application's bean definitions?"** This event does not mean dependency injection is complete, beans are ready, the web server is running, or the application can accept requests.

This is a **Spring Boot** event, with the fully qualified type `org.springframework.boot.context.event.ApplicationContextInitializedEvent`. It differs from pure Spring Framework `ApplicationContext` lifecycle events such as `ContextRefreshedEvent`.

## 1. Exact Position in the Startup Process

Typical path when calling `SpringApplication.run(...)`:

```text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  |     (start; Environment and ApplicationContext not yet prepared)
  |
  +-- Create/prepare Environment
  +-- ApplicationEnvironmentPreparedEvent
  |     (Environment available; ApplicationContext not yet created)
  |
  +-- Create ApplicationContext
  +-- Assign Environment and prepare context
  +-- Invoke ApplicationContextInitializers
  |
  +-- ApplicationContextInitializedEvent  <-- THIS TOPIC
  |     (context preliminarily initialized; application bean definitions not yet loaded)
  |
  +-- Load bean definitions from configuration / application sources
  +-- ApplicationPreparedEvent
  |     (bean definitions loaded, not yet refreshed)
  |
  +-- Refresh ApplicationContext
  |     (process bean definitions, create required singletons...)
  +-- ApplicationStartedEvent
  |     (refresh complete; ApplicationRunner / CommandLineRunner not yet run)
  |
  +-- Run ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
        (application is considered ready to accept requests)
```

Milestones may also be accompanied by internal events, availability states, and web-server-specific events. The diagram focuses on the key milestones to distinguish usage timing.

| Event | Context Exists? | Bean Definitions from App Sources Loaded? | Context Refreshed? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | No | No | No |
| `ApplicationEnvironmentPreparedEvent` | No | No | No |
| **`ApplicationContextInitializedEvent`** | **Yes** | **No** | **No** |
| `ApplicationPreparedEvent` | Yes | Yes | No |
| `ApplicationStartedEvent` | Yes | Yes | Yes |
| `ApplicationReadyEvent` | Yes | Yes | Yes |

The phrase "bean definitions not yet loaded" here refers to the stage where Spring Boot **has not yet loaded the application's regular bean definition sources**. Do not write tests assuming `getBeanDefinitionCount() == 0`: preparation steps, initializers, or custom infrastructure may already register some definitions before this point.

## 2. Event Contents and Important APIs

The `ApplicationContextInitializedEvent` type extends `SpringApplicationEvent` and provides:

- `getApplicationContext()`: returns the `ConfigurableApplicationContext` that has been created and preliminarily initialized.
- `getSpringApplication()` (inherited): returns the `SpringApplication` executing the startup process.
- `getArgs()` (inherited): returns the initial command-line arguments used to start.

The constructor used by Spring Boot has the form:

```java
public ApplicationContextInitializedEvent(
        SpringApplication application,
        String[] args,
        ConfigurableApplicationContext context);
```

This is an **illustrative API signature**, not a command to create the event manually. In normal applications, Spring Boot is responsible for publishing the event.

At this stage, a listener can observe:

```java
ConfigurableApplicationContext context = event.getApplicationContext();
String appName = context.getEnvironment()
        .getProperty("spring.application.name");
boolean refreshed = context.isActive();
```

This is an **illustrative code snippet**, assuming variable `event` is declared in an appropriately typed listener. `Environment` has already been attached to the context, so reading prepared properties is valid. `context.isActive()` is normally still `false` at this milestone because `refresh()` has not happened yet. However, do not attempt to use `context.getBean(...)` for business beans that have not yet been defined/created.

An `ApplicationContextInitializer` is something that **runs before** the event. If an initializer adds a `PropertySource`, an `ApplicationContextInitializedEvent` listener can observe that change. This is the most useful connection between the two mechanisms.

## 3. How to Register a Listener Without Missing the Early Event

Because the event is published **before Spring Boot loads bean definitions from the application**, listeners based on beans created by `@Component`, `@Bean`, or `@EventListener` **usually do not exist yet to receive the event**. The right approach is to register the listener directly with `SpringApplication` **before calling `run()`**.

### 3.1. Direct Registration with `SpringApplication.addListeners(...)`

```java
SpringApplication app = new SpringApplication(MyBootApplication.class);
app.addListeners(new MyEarlyListener());
app.run(args);
```

`MyEarlyListener` must implement `ApplicationListener<ApplicationContextInitializedEvent>`. Spring Boot collects this listener before starting the run, so it can receive early startup events, including `ApplicationContextInitializedEvent`.

### 3.2. Using `SpringApplicationBuilder.listeners(...)`

```java
new SpringApplicationBuilder(MyBootApplication.class)
        .listeners(new MyEarlyListener())
        .run(args);
```

This is the equivalent approach when starting an application via the builder, often useful for customizing `SpringApplication` or building a context hierarchy.

### 3.3. Automatic Registration via `META-INF/spring.factories`

If building a library that needs to receive startup events across multiple applications, you can declare the listener in:

```text
src/main/resources/META-INF/spring.factories
```

Example contents:

```properties
org.springframework.context.ApplicationListener=example.boot.events.MyEarlyListener
```

`example.boot.events.MyEarlyListener` here is an **illustrative class name**; replace it with the real class name that has a suitable constructor. Spring Boot can load listeners declared here right when constructing `SpringApplication`. This is the early-listener registration mechanism documented by Spring Boot; do not confuse it with the auto-configuration import mechanism.

If the listener is only for a single application, `addListeners(...)` is usually simpler and easier to control.

### 3.4. Why Might `@EventListener` Inside `@Component` Miss the Event?

The following code may look reasonable, but it is not the right way to observe early events:

```java
@Component
class TooLateListener {
    @EventListener
    void initialized(ApplicationContextInitializedEvent event) {
        System.out.println("Context initialized");
    }
}
```

This is an **illustrative snippet**. `@EventListener` is processed during the bean/context lifecycle. When `ApplicationContextInitializedEvent` is published, Spring Boot **has not yet loaded application bean configurations**, so `TooLateListener` is usually not yet registered as a listener for that event. Do not interpret the absence of logs as "Spring Boot did not publish the event."

The proper choice is to create a standalone `ApplicationListener` and register it early, or switch to a later event if the logic requires initialized beans.

## 4. Runnable Java 17+ Example: Initializer Runs Before the Event

A Spring Boot example without a web server, avoiding database dependencies and without needing Spring MVC. The program intentionally prints marker lines at initializer/event time and after `run()` completes.

Maven project structure:

```text
context-initialized-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── boot/
                    └── events/
                        └── ContextInitializedDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>context-initialized-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.boot.events.ContextInitializedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/example/boot/events/ContextInitializedDemo.java`:

```java
package example.boot.events;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication(proxyBeanMethods = false)
public class ContextInitializedDemo {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextInitializedDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ApplicationContextInitializer<ConfigurableApplicationContext> initializer =
                context -> {
                    context.getEnvironment().getPropertySources().addFirst(
                            new MapPropertySource(
                                    "demo-initializer",
                                    Map.of("demo.stage", "initializer-ran")));
                    System.out.println("initializer: property added");
                };
        app.addInitializers(initializer);

        // Register before run(), without waiting for bean scanning.
        app.addListeners(new EarlyContextListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("after-run: active=" + context.isActive());
            System.out.println("after-run: property=" +
                    context.getEnvironment().getProperty("demo.stage"));
        }
    }

    public static final class EarlyContextListener
            implements ApplicationListener<ApplicationContextInitializedEvent> {

        @Override
        public void onApplicationEvent(ApplicationContextInitializedEvent event) {
            ConfigurableApplicationContext context = event.getApplicationContext();

            System.out.println("initialized: property=" +
                    context.getEnvironment().getProperty("demo.stage"));
            System.out.println("initialized: active=" + context.isActive());
        }
    }
}
```

In the `context-initialized-demo` directory, run (requires JDK 17+, Maven, and ability to download dependencies on first run):

```bash
mvn -q compile exec:java
```

Lines **printed by the program itself**, in exact order (ignoring logs that may appear from Spring/SLF4J/Maven):

```text
initializer: property added
initialized: property=initializer-ran
initialized: active=false
after-run: active=true
after-run: property=initializer-ran
```

Analysis:

1. `app.addInitializers(initializer)` configures an `ApplicationContextInitializer` that adds property `demo.stage`. When Spring Boot invokes the initializer, the program prints the first line.
2. Immediately after the initializer stage, Spring Boot publishes `ApplicationContextInitializedEvent`. `EarlyContextListener` was registered via `addListeners(...)` so it is called; it reads `demo.stage=initializer-ran`.
3. `initialized: active=false` shows that the context has not been refreshed when the listener runs. A context object exists, yet business beans are not ready.
4. Once `app.run(args)` finishes, the context has refreshed; `after-run: active=true`. The property added by the initializer remains accessible.

The example uses a static listener class implementing the interface with a **specific event type**. This helps Spring identify which event type to listen for and avoids accidentally processing unrelated startup events. The listener class does not need `@Component`.

## 5. How Do `ApplicationContextInitializer` and `ApplicationContextInitializedEvent` Differ?

The names are similar, but their roles differ:

| Component | Nature | Timing | Used For |
| --- | --- | --- | --- |
| `ApplicationContextInitializer<ConfigurableApplicationContext>` | Context configuration callback | Invoked by Spring Boot while preparing the context | Proactively modifying the context early per the initializer contract |
| `ApplicationContextInitializedEvent` | Preliminary initialization milestone event | **After** calling initializers, before loading bean definitions from the app | Observing, verifying, and recording info after the initializer step |
| `ApplicationPreparedEvent` | Later startup event | After loading bean definitions, before refresh | Observing the stage where definitions are loaded but not yet fully instantiated |
| `ApplicationReadyEvent` | Near-end startup event | After refresh and runners | Starting work that genuinely needs the application to be ready |

**When you need to configure the context before the bean-loading step**, `ApplicationContextInitializer` usually expresses the intent clearest. Although an event listener can access `ConfigurableApplicationContext`, do not turn the listener into a place performing many hard-to-control internal mutations.

For instance, when verifying a property just added by an initializer, `ApplicationContextInitializedEvent` fits well. If you want to register specialized bean definitions before refresh, consider official extension APIs such as `ApplicationContextInitializer`, `BeanDefinitionRegistryPostProcessor`, or auto-configuration suitable for the customization type; do not rely on accidental ordering between listeners.

If you need to run logic depending on `@Autowired` services, completed database migrations, or endpoints actively serving traffic, choose a later milestone such as `ApplicationRunner`/`CommandLineRunner` or `ApplicationReadyEvent` depending on the requirement. Early events do not guarantee those dependencies exist.

## 6. When Should It Be Applied?

Some valuable purposes for `ApplicationContextInitializedEvent`:

- **Verifying context preparation state:** confirming an initializer attached expected properties, profiles, or markers.
- **Logging early startup diagnostics:** printing context ID, context type, application name, or safe properties to locate configuration issues before refresh.
- **Recording a startup milestone:** measuring/annotating a point in the startup lifecycle, as long as the callback is lightweight and avoids unready application beans.
- **Detecting that a custom initializer took effect:** separating context modification (initializer) from observation (listener).

Example reading bean-independent information:

```java
@Override
public void onApplicationEvent(ApplicationContextInitializedEvent event) {
    ConfigurableApplicationContext context = event.getApplicationContext();

    String name = context.getEnvironment()
            .getProperty("spring.application.name", "(unnamed)");
    System.out.println("initializing: " + name);
}
```

This is an **illustrative method snippet** placed inside a class implementing `ApplicationListener<ApplicationContextInitializedEvent>`. Reading properties and logging are safe under the lifecycle contract. Do not log passwords/tokens or secret contents from `Environment`.

## 7. Limitations and Common Mistakes

### 7.1. Confusing "Initialized" with "Refreshed" or "Ready"

The event name contains "Initialized", yet this is **neither** `ApplicationStartedEvent` **nor** `ApplicationReadyEvent`. At this point, Spring Boot has not loaded source bean definitions and has not refreshed the context. Beans from `@Configuration`, `@ComponentScan`, or auto-configuration have not been initialized as in a running application.

Calling `context.getBean(OrderService.class)` here can trigger `NoSuchBeanDefinitionException` or errors from accessing beans too early. Do not infer from the presence of a few infrastructure beans that the entire application is ready.

### 7.2. Registering the Listener Too Late

A `@Component` containing `@EventListener` is only processed when the application loads/refreshes bean definitions; therefore it is unsuitable for catching this very early event.

Fix: register an `ApplicationListener<ApplicationContextInitializedEvent>` instance via `SpringApplication.addListeners(...)` before `run()`, via `SpringApplicationBuilder.listeners(...)`, or via `META-INF/spring.factories`.

### 7.3. Slowing Down or Failing Startup

Early listeners usually run synchronously on the startup thread. Long tasks, network waits, large file reads, or wait loops in a listener can prolong startup. Unhandled exceptions can cause `SpringApplication.run(...)` to fail and lead to `ApplicationFailedEvent` handling. Perform only short, deterministic operations that do not depend on uninitialized systems.

### 7.4. Confusing Timing for Reading `Environment`

At `ApplicationContextInitializedEvent`, `Environment` is already prepared and attached to the context. If you only want to intervene in `Environment` before the context is created, `ApplicationEnvironmentPreparedEvent` is an earlier milestone. If you want to inspect values added by `ApplicationContextInitializer`, use this initialized event.

### 7.5. Counting Bean Definitions to Infer the Entire Lifecycle

The official description states Spring Boot has not loaded bean definitions from application sources, which **does not mean every registry at this moment is completely empty**. Initializers or parts of infrastructure can register bean definitions earlier. Thus, an assertion on `getBeanDefinitionCount()` may depend on specific configuration and is not a true/false criterion of the event.

### 7.6. Receiving Multiple Times with a Context Hierarchy

If an application uses multiple `SpringApplication`s or a parent/child context structure, a listener may receive multiple events of the same type from different contexts. Do not assume one event receipt always equals one JVM startup. You can check `event.getApplicationContext()`, context ID, or the startup source to differentiate and avoid duplicate task execution.

### 7.7. Confusing `ApplicationContextInitializedEvent` with Spring Framework Events

`ContextRefreshedEvent` appears once `ApplicationContext` has refreshed and can be published again if a context refreshes multiple times. `ApplicationContextInitializedEvent` is an **early Spring Boot startup milestone**; it is not published merely because custom code creates and refreshes a standalone `AnnotationConfigApplicationContext` without `SpringApplication`.

### 7.8. Relying on Undocumented Listener Ordering

If multiple early listeners are independent and require execution order, consider Spring's `Ordered` or `@Order` mechanism where appropriate; do not rely on class name order or accidental behavior. When a callback needs data produced by an initializer, place the configuration responsibility in the initializer, since the lifecycle guarantees **initializers run before `ApplicationContextInitializedEvent`**.

## 8. Properly Testing the Event

Testing should happen at two levels:

**Unit:** construct a mock/synthetic `ApplicationContextInitializedEvent` with `SpringApplication` and `ConfigurableApplicationContext` to verify that the listener reads properties, logs, or updates counters properly. This tests only **listener logic**, without proving Boot publishes the event at the exact timing.

**Startup integration:** launch a small `SpringApplication` as in the example, register the initializer and listener before `run()`, and verify the sequence:

1. Initializer runs first and creates the marker.
2. Listener receives the marker after the initializer runs.
3. At the initialized event, the context is not yet refreshed.
4. After `run()`, the context is active and the property remains present.

When testing with JUnit, record markers into a list and assert their order instead of asserting against logs. `Thread.sleep(...)` is unnecessary because the startup callbacks in this example are invoked synchronously.

You can create a listener class that simply counts `ApplicationContextInitializedEvent` to verify the event is published **once per context/run cycle** in a simple application model. In applications with a context hierarchy, "once per entire application" no longer holds universally.

## 9. Self-Assessment

1. **When a listener receives `ApplicationContextInitializedEvent`, can it retrieve business beans with `context.getBean(...)`?** No, because Spring Boot has not loaded application bean definitions and the context has not refreshed yet.
2. **Does `ApplicationContextInitializer` run before or after the event?** **Before**. The event signals that the initializer stage has completed.
3. **Can `@Component` with `@EventListener` be used to reliably receive this event?** No. Beans registered from application sources are typically processed later.
4. **Where should a listener be registered to receive this event?** Via `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or `META-INF/spring.factories`.
5. **Does the initialized event mean the web server is ready?** No. Look at post-refresh milestones and `ApplicationReadyEvent` if you need to know the application is ready to serve traffic.

## 10. References

- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot 3.3 Javadoc — ApplicationContextInitializedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationContextInitializedEvent.html)
- [Spring Boot Reference — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html#howto.application.customize-the-environment-or-application-context)
- [Spring Framework Javadoc — ApplicationContextInitializer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
