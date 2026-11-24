# ApplicationStartingEvent Before Environment and Full Context Exist

## 1. Objectives

`ApplicationStartingEvent` is one of the earliest signals in the Spring Boot startup lifecycle. Spring Boot emits this event **right after `SpringApplication.run(...)` starts, after registering listeners/initializers, but before `Environment` and `ApplicationContext` are ready**. It is useful for observing when Spring Boot actually begins bootstrapping and for setting up certain infrastructure integrations required very early.

The tricky part of this topic is not listener syntax, but **lifecycle boundaries**:

- When the event is emitted, a `SpringApplication` instance, runtime arguments, and a bootstrap context for the early phase already exist.
- At that moment, **there is no complete `ConfigurableEnvironment` yet to read profiles/properties via Spring Boot's mechanism**.
- **There is no complete `ApplicationContext` yet** to look up beans, inject `@Autowired`, run `@Bean` methods, or access a web server.
- Therefore, a listener that wants to receive this event must be registered **before calling `run()`**, or via the `META-INF/spring.factories` loader mechanism; declaring the listener as a regular bean is too late.

A practical question: why does placing `@EventListener(ApplicationStartingEvent.class)` inside a `@Component` fail to see the event? Because `@Component` only becomes a bean after the context is built and bean definitions are processed; `ApplicationStartingEvent` has already occurred before that.

## 2. Where Does ApplicationStartingEvent Sit?

From the moment Java runs `main()` until Spring Boot signals readiness, there are multiple independent milestones. In a typical `SpringApplication` run, the key event sequence is:

~~~text
JVM invokes main(String[] args)
   |
   +-- new SpringApplication(YourApplication.class)
   +-- Register ApplicationListener, initializer ...
   |
   +-- application.run(args)
         |
         +-- ApplicationStartingEvent                <== FOCUS
         |      Environment NOT ready yet
         |      ApplicationContext NOT ready yet
         |
         +-- Prepare ConfigurableEnvironment
         +-- ApplicationEnvironmentPreparedEvent
         |      Environment available, context not created yet
         |
         +-- Create ApplicationContext
         +-- Run ApplicationContextInitializer
         +-- ApplicationContextInitializedEvent
         |      Context created/initially customized; bean definitions not loaded yet
         |
         +-- Load bean definitions
         +-- ApplicationPreparedEvent
         |      Bean definitions loaded; context not refreshed yet
         |
         +-- ApplicationContext.refresh()
         |      BeanFactoryPostProcessor, BeanPostProcessor,
         |      bean initialization, possible web server startup ...
         |
         +-- ApplicationStartedEvent
         |      Context refreshed; runners not executed yet
         |
         +-- ApplicationRunner and CommandLineRunner
         |
         +-- ApplicationReadyEvent
         +-- ReadinessState.ACCEPTING_TRAFFIC
         |
         v
       run(...) succeeds
~~~

This is a high-level diagram based on Spring Boot 3.5. In a web application, `WebServerInitializedEvent` and Spring Framework's refresh event also occur. If startup encounters an error, `ApplicationFailedEvent` may be published instead of continuing to the ready state.

**Do not confuse** the moment this event is emitted with when Java `main()` begins: if you have Java statements before `application.run(args)`, those statements execute before `ApplicationStartingEvent`. This is a *SpringApplication* event, not the very first callback of the entire JVM.

## 3. What Information Can Be Obtained Directly from ApplicationStartingEvent?

In Spring Boot 3.5, `ApplicationStartingEvent` belongs to the `org.springframework.boot.context.event` package and extends `SpringApplicationEvent`.

| API | Meaning | Limitations to know |
| --- | --- | --- |
| `event.getSpringApplication()` | The `SpringApplication` instance currently running | Internal state may still change; do not assume all settings are finalized |
| `event.getArgs()` | The `String[]` argument array passed to `run(args)` | These are raw arguments; not processed property sources yet |
| `event.getBootstrapContext()` | `ConfigurableBootstrapContext` serving bootstrap-phase dependencies | Not an `ApplicationContext` or runtime bean registry |
| `event.getTimestamp()` | Event creation timestamp (from `ApplicationEvent`) | Not the time the entire application became ready |
| `event.getSource()` | Event source object, in this case associated with `SpringApplication` | Does not replace context-access APIs |

With `getArgs()`, the following code is valid inside the listener:

~~~java
String[] args = event.getArgs();
int count = args.length;
~~~

This is an illustrative snippet inside a listener that has received `ApplicationStartingEvent`, not a standalone program.

**Practical warning:** command-line arguments may contain passwords, access tokens, sensitive URIs, or private data. The example here prints only the **argument count**, not the full contents. In production, you should not log `Arrays.toString(event.getArgs())` without redacting sensitive data first.

### Having No Environment Does Not Mean Java Has No Configuration at All

`System.getenv("NAME")` and `System.getProperty("name")` are Java APIs; they can be called before Spring Boot starts. However, they are **not equivalent** to `Environment.getProperty(...)`, which applies `PropertySource` precedence, profiles, command-line arguments, and other Spring merging rules.

For example, the `--demo.flag=on` argument may already be present in `event.getArgs()`, but at `ApplicationStartingEvent` you should not assume it can be read through a final `Environment`. Once `ApplicationEnvironmentPreparedEvent` is emitted, `event.getEnvironment()` becomes the proper API to inspect properties prepared for this startup.

### Bootstrap Context Exists, Regular Beans Do Not

Since Spring Boot 2.4, the event provides `getBootstrapContext()`. The bootstrap context allows early startup integrations to register and retrieve dependencies by type without needing an `ApplicationContext` yet. This fits very early needs such as Config Data integrations.

However, **the bootstrap registry is not a BeanFactory**. When you write:

~~~java
var bootstrap = event.getBootstrapContext();
boolean available = bootstrap.isRegistered(EarlyDependency.class);
~~~

`EarlyDependency` is a hypothetical type and this snippet only illustrates the API. You must not infer from `isRegistered(...)` that a Spring bean of the same type already exists, or that all application configuration is ready. If a dependency needs to be created in the bootstrap context, register it with `BootstrapRegistryInitializer` at the right stage; do not try to force `@Autowired` here.

## 4. Registering the Listener at the Right Time

### 4.1. SpringApplication.addListeners(...) — Common Approach When You Own main()

To catch `ApplicationStartingEvent`, create `SpringApplication` and add the listener **before calling `run()`**:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        System.out.println("Early startup event received");
    }
);
application.run(args);
~~~

This is an **illustrative snippet inside `main()`**, not a standalone runnable program: it requires a `MyApplication` class along with imports for `SpringApplication`, `ApplicationListener`, and `ApplicationStartingEvent`. A complete runnable example is in Section 6.

If using `SpringApplicationBuilder`, you can configure listeners via the builder's `listeners(...)` method before launching. Both approaches rely on the rule of **registering before the first event is emitted**.

The convenience call:

~~~java
SpringApplication.run(MyApplication.class, args);
~~~

still starts the application normally, but it does not let you attach a programmatic listener right before `run` if you do not instantiate `SpringApplication` yourself first. Registration via `spring.factories` can be used when you do not own the entry point.

### 4.2. META-INF/spring.factories — Approach for Auto-Loaded Integrations

If you write a library whose listener must be registered even when another application uses the static `SpringApplication.run(...)`, Spring Boot supports registration via a classpath file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Example contents:

~~~properties
org.springframework.context.ApplicationListener=com.example.early.EarlyStartingListener
~~~

The class `com.example.early.EarlyStartingListener` must implement `ApplicationListener<ApplicationStartingEvent>`, be instantiable by the loader, and have no constructor injection dependency on application beans. The package/class name in the configuration is an **example** and must be replaced with your actual class.

Example Java class for that file:

~~~java
package com.example.early;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("EARLY_LISTENER_RECEIVED");
    }
}
~~~

This is a **syntactically complete Java file**, but it only runs inside a Spring Boot application that has the `spring-boot` dependency and registers it via `spring.factories` or an equivalent mechanism. It has no `main()`.

Only use both `spring.factories` and `addListeners(...)` for the same instance when you fully understand the registration mechanism, so you avoid unintended duplicate processing. Do not confuse the `org.springframework.context.ApplicationListener` key with the `AutoConfiguration.imports` mechanism meant for auto-configuration.

### 4.3. Why Are @Component and @EventListener Unsuitable?

The following two patterns **cannot be relied on to receive `ApplicationStartingEvent`**:

~~~java
@Component
class LateListener {
    @EventListener
    void onStart(ApplicationStartingEvent event) {
        System.out.println("TOO LATE");
    }
}
~~~

This is an **illustrative, non-standalone snippet** (requires annotation/class imports). `@Component` and `@EventListener` are processed only after the container can scan and instantiate beans. `ApplicationStartingEvent` occurs before the context exists, so a bean-registered listener cannot go back in time to receive it.

Similarly, do not expect:

~~~java
@Bean
ApplicationListener<ApplicationStartingEvent> myListener() {
    return event -> System.out.println("too late");
}
~~~

to be invoked for the early startup event. This snippet illustrates a listener **declared as a bean after the event has already occurred**. A bean listener can still be appropriate for events arriving later, but not for the very first milestone.

## 5. Clearly Distinguishing Similarly Named Events

| Event | Emission milestone | Has Environment? | Has ApplicationContext? | Completed work? |
| --- | --- | --- | --- | --- |
| `ApplicationStartingEvent` | Start of `run`, listeners/initializers registered | No | No | Main startup not processed yet |
| `ApplicationEnvironmentPreparedEvent` | Environment prepared | Yes, via event | No | Initial property sources prepared |
| `ApplicationContextInitializedEvent` | Context created and initializers invoked | Yes | Yes, bean definitions not loaded yet | Initial context setup |
| `ApplicationPreparedEvent` | Bean definitions loaded, before refresh | Yes | Yes, not refreshed yet | Bean definitions prepared |
| `ApplicationStartedEvent` | Context refresh succeeded | Yes | Yes, refreshed | Runners have not executed yet |
| `ApplicationReadyEvent` | Runners completed successfully | Yes | Yes | Boot-managed startup phase completed |
| `ApplicationFailedEvent` | Startup failed | Depends on failure stage | May not exist yet | Normal subsequent milestones not guaranteed |

These events are not interchangeable names. A common mistake is reading the word "Starting" and thinking `ApplicationStartingEvent` is equivalent to `ApplicationStartedEvent` or `ApplicationReadyEvent`.

- **Starting**: just beginning, before Spring `Environment` and context exist.
- **Started**: context has refreshed, but runners have not run yet.
- **Ready**: runners have completed and Boot transitions to the ready state in the normal lifecycle.

In a Servlet/Reactive application, a "web server started" log line is also not equivalent to `ApplicationStartingEvent`. The embedded server can only start during web context preparation/refresh, which is much later than the first event.

### ContextStartedEvent Is Not ApplicationStartedEvent

Spring Framework has a `ContextStartedEvent` emitted by `ApplicationContext.start()`. It is **not equivalent** to Spring Boot's `ApplicationStartedEvent`. Do not design listeners based on similar names; check which package the event belongs to and which mechanism emits it.

### @PostConstruct and Runners Are Also Late Milestones

`@PostConstruct` is processed when a bean is initialized, meaning `ApplicationContext` has already started instantiating beans. `ApplicationRunner` and `CommandLineRunner` run after context refresh. Neither is suitable if your goal is to receive `ApplicationStartingEvent` itself.

## 6. Complete Runnable Java 17+ Example: Recording the Event Sequence

The goal of this example is to observe **event ordering** while demonstrating the difference between when `Environment` does not exist yet and when `Environment` is ready. The code uses Spring Boot 3.5.x and Java 17+, without starting an HTTP server so stdout remains easy to read.

### 6.1. Create a Maven Project

Use Maven and JDK 17 or newer compatible with Spring Boot 3.5. Create the following structure:

~~~text
early-event-demo/
├─ pom.xml
└─ src/main/java/com/example/earlyevent/
   └─ EarlyEventApplication.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>early-event-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

To ensure stable imports, `pom.xml` pins a specific Spring Boot 3.5.x version. If your project uses another version, check the corresponding APIs and dependencies, especially when using Spring Boot 4.

### 6.2. Complete Java File

**File `src/main/java/com/example/earlyevent/EarlyEventApplication.java`:**

~~~java
package com.example.earlyevent;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EarlyEventApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyEventApplication.class);

        // A non-web application: does not open a server/port.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Must register before run() emits the Starting event.
        application.addListeners(new TimelineListener());

        application.run(args);
    }

    @Bean
    ApplicationRunner sampleRunner() {
        return args -> System.out.println("06_RUNNER");
    }

    static final class TimelineListener
            implements ApplicationListener<SpringApplicationEvent> {

        @Override
        public void onApplicationEvent(SpringApplicationEvent event) {

            if (event instanceof ApplicationStartingEvent starting) {
                System.out.println(
                        "01_STARTING args=" + starting.getArgs().length
                        + " bootstrap="
                        + (starting.getBootstrapContext() != null));

            } else if (event instanceof ApplicationEnvironmentPreparedEvent env) {
                String flag = env.getEnvironment()
                        .getProperty("demo.flag", "unset");
                System.out.println("02_ENVIRONMENT flag=" + flag);

            } else if (event instanceof ApplicationContextInitializedEvent) {
                System.out.println("03_CONTEXT_INITIALIZED");

            } else if (event instanceof ApplicationPreparedEvent) {
                System.out.println("04_CONTEXT_PREPARED");

            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("05_APPLICATION_STARTED");

            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("07_APPLICATION_READY");

            } else if (event instanceof ApplicationFailedEvent) {
                System.out.println("APPLICATION_FAILED");
            }
        }
    }
}
~~~

This is a **standalone Java file inside the Spring Boot Maven project described above**; all required imports are present. It uses pattern matching for `instanceof` (available since Java 16), so Java 17 compiles it cleanly.

`TimelineListener` is written to accept `SpringApplicationEvent` and branch by subtype. Because the listener is instantiated in Java before `run()`, no bean injection is needed for it to work. `@Bean sampleRunner()` lives in the main configuration and runs only during the runner phase, after `ApplicationStartedEvent` has been emitted.

**Note on `bootstrap=true`:** the print statement only shows that `getBootstrapContext()` returns a non-null reference. That **does not** mean Spring has created a full `ApplicationContext` or business beans yet.

### 6.3. Compile and Run

Inside the `early-event-demo` directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

You can also build an executable archive:

~~~bash
mvn package
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar
~~~

If the project was generated via Spring Initializr and includes a Maven Wrapper, use `./mvnw spring-boot:run` on Linux/macOS or `.\\mvnw.cmd spring-boot:run` in Windows PowerShell.

**The lines produced by the example code itself**, when run without command-line arguments, appear in this order:

~~~text
01_STARTING args=0 bootstrap=true
02_ENVIRONMENT flag=unset
03_CONTEXT_INITIALIZED
04_CONTEXT_PREPARED
05_APPLICATION_STARTED
06_RUNNER
07_APPLICATION_READY
~~~

This is the **order of lines printed by the example itself**, not the entire console output: the banner, Maven messages, and internal logs may appear in between. `ApplicationFailedEvent` does not appear in a successful run. With `WebApplicationType.NONE`, the process may exit once the runner completes.

If you run the JAR with an argument:

~~~bash
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar --demo.flag=on
~~~

then the first two lines printed by the code change to:

~~~text
01_STARTING args=1 bootstrap=true
02_ENVIRONMENT flag=on
~~~

Lines `03`–`07` keep the same order. That is the key observation: **the first event sees a raw argument**, whereas at `ApplicationEnvironmentPreparedEvent`, Spring has already populated the `demo.flag` property into `Environment`.

### 6.4. Explaining Each Milestone in the Example

1. **`01_STARTING`**: the listener was registered directly on `SpringApplication`. The first event occurs when neither the configuration environment nor the main context exists yet; only the corresponding bootstrap information is available.
2. **`02_ENVIRONMENT`**: Spring Boot has created and configured the initial `Environment`; properties can be read via `env.getEnvironment()`.
3. **`03_CONTEXT_INITIALIZED`**: the context has been created and `ApplicationContextInitializer` instances have been invoked, but bean definitions have not been loaded yet.
4. **`04_CONTEXT_PREPARED`**: bean definitions have been loaded, but the context has not refreshed yet; you cannot assume business singletons are initialized.
5. **`05_APPLICATION_STARTED`**: Spring Boot has finished refreshing the context, but has not run the runners yet.
6. **`06_RUNNER`**: the method from the `ApplicationRunner` bean executes in the post-refresh phase.
7. **`07_APPLICATION_READY`**: Boot emits the event when runners finish; immediately afterward it signals readiness accepting according to the normal lifecycle.

The goal of this lesson is **not** to log startup at all costs. The example uses `System.out` for illustration because Spring Boot's logging system is also in early setup at `ApplicationStartingEvent`. In real systems, use logging/instrumentation APIs appropriate to the active stage and avoid depending on properties or logger beans that do not exist yet.

## 7. What You Should and Should Not Do at ApplicationStartingEvent

The event is emitted very early, and listeners run **synchronously by default**. If a listener hangs, the entire startup can be delayed.

| Need | Suitable at StartingEvent? | How to implement |
| --- | --- | --- |
| Mark the start time of startup | Yes | Record a lightweight marker or timing metric without sensitive data |
| Inspect the number of run arguments | Yes | `event.getArgs().length`; do not log secrets directly |
| Access properties via `ConfigurableEnvironment` | Not yet | Wait for `ApplicationEnvironmentPreparedEvent` or use `EnvironmentPostProcessor` |
| Call `ApplicationContext.getBean()` | No | Wait until the context and required beans are created |
| Use `@Autowired` in this listener | Should not rely on it | Instantiate the listener in Java, pulling very early dependencies only from supported bootstrap APIs |
| Create HTTP endpoints or check listening web ports | No | Wait for web context refresh / web server event |
| Run database migrations or initialize business caches | Not the default place | Use appropriate migration/lifecycle mechanisms or runners |
| Register startup dependencies before `Environment` | Has a dedicated mechanism | Use `BootstrapRegistryInitializer` and the bootstrap context |
| Access merged Spring profiles | Not yet | Wait for the Environment prepared event |
| Make network calls without timeouts or block long | High risk | Decouple initialization steps and set clear timeout/failure policies |

**Rule:** listeners for early events should perform brief work with minimal dependencies and no complex side effects. If processing may take long or needs beans, pick a later, lifecycle-appropriate extension point.

### Should You Modify SpringApplication from the Listener?

`event.getSpringApplication()` returns the `SpringApplication` instance. However, the Javadoc warns that the object's internal state may change later. If you need to configure startup, **configure `SpringApplication` explicitly before `run()`** whenever possible; do not rely on mutating unstable state in the first event.

Similarly, avoid resetting static global state every time `ApplicationStartingEvent` appears: in tests or a single process, multiple application/context runs can occur, causing the callback to fire multiple times and leaking state across runs.

## 8. Interacting with Bootstrap Context and EnvironmentPostProcessor

Some configuration integrations need dependencies **before Environment exists**. Spring Boot supports `BootstrapRegistryInitializer` to register suppliers before the Environment preparation code needs them. The first event can access `ConfigurableBootstrapContext`.

Illustrative example (placed in `main()`, assuming class `EarlyResource` already exists):

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addBootstrapRegistryInitializer(registry ->
    registry.registerIfAbsent(
        EarlyResource.class,
        context -> new EarlyResource()
    )
);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        boolean registered = event.getBootstrapContext()
                .isRegistered(EarlyResource.class);
        System.out.println("registered=" + registered);
    }
);

app.run(args);
~~~

This is a **non-standalone illustrative snippet**: `MyApplication`, `EarlyResource`, and imports are not defined. It shows that **the bootstrap registry is a separate channel** usable early on, which does not mean `EarlyResource` is already a bean in `ApplicationContext`.

`EnvironmentPostProcessor` is the right extension point for modifying or adding `PropertySource` entries while `Environment` is being prepared. Writing an `ApplicationStartingEvent` listener and manually reimplementing property source resolution often breaks precedence order, profiles, and config-data loading.

Likewise, if you need to customize the context after creation but before refresh, use `ApplicationContextInitializer`; if you need code to run after the context is ready, use a runner. Each extension point has its own place—do not try to turn StartingEvent into the place where every application task lives.

### Distinguishing Early Events and Bootstrap Dependencies

- **`ApplicationStartingEvent`** says "the SpringApplication run has started," informing listeners of a startup milestone.
- **`BootstrapRegistryInitializer`** says "register dependencies/suppliers for the bootstrap phase."
- **`ApplicationEnvironmentPreparedEvent`** says "Environment has been prepared and can be accessed/modified via its API."
- **`ApplicationContextInitializer`** says "the context has been created and can be customized before refresh."

Events and extension points do not replace each other; one is for **observing milestones**, while the other provides a **contract to mutate state** at the right moment.

## 9. What Happens If a Listener Throws an Error?

A listener invoked early is part of the startup path. If it throws an unhandled exception, `SpringApplication.run()` can fail before the main context is even created. Spring Boot may emit `ApplicationFailedEvent`, but you should not assume every ultra-early failure has a full `ApplicationContext` or bean-lifecycle cleanup available.

Anti-pattern example:

~~~java
app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event -> {
        remoteService.connectWithoutTimeout();
    }
);
~~~

This is **non-standalone pseudocode**: `app` and `remoteService` are hypothetical objects. It illustrates the immediate danger: network operations can block startup, and the service might even need `Environment`—which does not exist yet—to find its URL or credentials.

If an operation is mandatory before the application serves traffic, clarify:

1. At what stage can the resource be created without beans or Environment?
2. Is there an official extension point for this requirement?
3. If the operation fails, should it fail startup, retry with a bound, or degrade gracefully?
4. How is the resource released if bootstrap fails before refresh?
5. Could it accidentally log secrets or trigger duplicate side effects during tests/restarts?

These questions help you pick the right lifecycle hook instead of cramming business initialization into the first event.

## 10. Testing and Practical Observation

### 10.1. Observing the Event Properly

If `ApplicationStartingEvent` does not appear in logs, check listener registration first:

- With `addListeners`, the call must come **before `application.run(args)`**.
- With `spring.factories`, the file must be at `META-INF/spring.factories`, with key `org.springframework.context.ApplicationListener`, and its value must be a compiled, loadable class.
- With `@Component` or `@EventListener`, do not expect to receive the first event because beans appear too late.
- If the application has multiple `SpringApplication`/context instances or restarts multiple times in tests, you may see multiple events; distinguish the runs before treating it as a bug.
- If console output mixes in Spring Boot logs, filter by your application's markers to evaluate the sequence rather than expecting lines to be adjacent.

### 10.2. Distinguishing Event Occurrence from Application State

An application can emit `ApplicationStartingEvent` and then fail immediately while preparing `Environment`. That **does not** prove the application started successfully or opened its web port.

Only after `ApplicationStartedEvent` is there a lifecycle guarantee that the context has refreshed. `ApplicationReadyEvent` comes later, after runners. For traffic-serving systems, use readiness probes and proper monitoring rather than taking a StartingEvent marker as liveness or readiness.

### 10.3. Argument-Changing Experiment

Run twice:

~~~bash
mvn spring-boot:run
~~~

Then build the JAR and try:

~~~bash
mvn package
java -jar target/early-event-demo-0.0.1-SNAPSHOT.jar --demo.flag=on
~~~

Explain the change from `args=0` to `args=1`, and from `flag=unset` to `flag=on`. The event order remains valid because event types reflect phases within `run`, whereas property values reflect the inputs of each specific run.

When using the Maven `spring-boot:run` plugin and passing application arguments, you can use the plugin's run-arguments configuration, whereas `java -jar ... --demo.flag=on` in the example avoids quoting differences across operating systems.

## 11. Common Errors and Fixes

| Problem | Cause | Resolution |
| --- | --- | --- |
| Bean listener does not receive `ApplicationStartingEvent` | Beans are initialized after the event | Register using `SpringApplication.addListeners`, the builder, or `spring.factories` |
| `@EventListener` does not run at the early stage | The annotation requires Spring container processing | Switch to `ApplicationListener<ApplicationStartingEvent>` registered before run |
| Attempting to call `event.getApplicationContext()` | `ApplicationStartingEvent` has no main context | Choose a later event with a context accessor, such as `ApplicationContextInitializedEvent` |
| `@Autowired` in an early listener is null/unavailable | Listener is created before bean injection runs | Avoid bean injection; use simple values or the bootstrap registry within scope |
| Reading `Environment` from StartingEvent | `Environment` is not prepared yet | Wait for `ApplicationEnvironmentPreparedEvent` |
| Logging all args exposes secrets | `getArgs()` contains raw inputs that may be sensitive | Measure only safe metadata or redact before logging |
| Getting `getBootstrapContext()` and calling `getBean()` | Bootstrap context is not a BeanFactory | Use the bootstrap registry/context by type or wait for the Spring context |
| Having the listener perform long I/O | Listeners run on the synchronous startup path by default | Keep processing light; use an appropriate lifecycle hook with timeouts |
| Seeing more events than expected | Multiple `SpringApplication` instances, parent/child contexts, or duplicate registration | Distinguish event sources and registration paths |
| Treating `ApplicationStartedEvent` as the end of runners | This event arrives before runners | Wait for `ApplicationReadyEvent` to confirm startup completion |
| Treating StartingEvent as liveness/readiness | Event only indicates the start of the run process | Observe health/readiness after the context develops |
| Confusing `ContextStartedEvent` with `ApplicationStartedEvent` | Framework and Boot events have different contracts | Check package/type and lifecycle per the Javadoc |

## 12. Review Questions and Exercises

**Question 1.** Why can Spring Boot emit `ApplicationStartingEvent` before `Environment` exists?

**Answer:** Boot can create `SpringApplication`, register listeners/initializers, and emit the early event using its own startup machinery. `Environment` and `ApplicationContext` are prepared in subsequent steps.

**Question 2.** Can `event.getArgs()` be used to read `--server.port=9090`?

**Answer:** You can inspect raw arguments as a `String[]`, but the full `Environment`/property-source precedence mechanism does not exist yet. Do not infer the actual web port from the raw string when other configurations may apply; use appropriate later APIs/milestones.

**Question 3.** Why does a `@Component` containing `@EventListener(ApplicationStartingEvent.class)` fail to receive the first event?

**Answer:** The context does not exist yet to perform component scanning and bean creation, so a bean-based listener is registered too late.

**Question 4.** `getBootstrapContext()` returns a non-null object; does that mean `ApplicationContext` is ready?

**Answer:** No. The bootstrap context is a separate registry/dependency container for early startup, not the Spring ApplicationContext.

**Question 5.** How do `ApplicationStartingEvent` and `ApplicationStartedEvent` differ?

**Answer:** Starting is emitted very early before Environment/context; Started is emitted after context refresh succeeds and before runners.

**Question 6.** If an early listener throws an exception, can you rely on `@PreDestroy` of business beans to clean up all resources?

**Answer:** No. Beans that have not been created yet may have no cleanup callbacks; resources allocated manually in the early stage need an explicit management and cleanup policy.

**Exercise A — change registration method:** Move the listener in Section 6 into a separate top-level class, register it via `META-INF/spring.factories`, and go back to `SpringApplication.run(EarlyEventApplication.class, args)` in `main`. Verify `01_STARTING` still appears. Make sure only one registration mechanism is active so output remains clear.

**Exercise B — distinguish Environment and args:** Run the program with `--demo.flag=on` and observe the argument count at StartingEvent and the property value at EnvironmentPreparedEvent. Try omitting the argument to see the default value.

**Exercise C — failure handling:** Intentionally have an `ApplicationRunner` throw an exception, then track which events appeared and which did not. Conclude why Starting/Started cannot substitute for Ready.

**Exercise D — bootstrap dependency:** Register a lightweight supplier with `addBootstrapRegistryInitializer` and use `getBootstrapContext().isRegistered(Type.class)` inside StartingEvent. Explain why the type has a registration while a bean of the same type does not exist yet.

## 13. Official Documentation and Takeaways

Documentation to consult according to the exact Spring Boot version you use:

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).
- [Spring Boot 3.5 — ApplicationStartingEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html).
- [Spring Boot 3.5 — SpringApplicationEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/SpringApplicationEvent.html).
- [Spring Boot 3.5 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html).
- [Spring Framework — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html).

**Points to remember:**

1. `ApplicationStartingEvent` is a very early signal **after listener/initializer registration**, **before Environment and ApplicationContext are available**.
2. `SpringApplication`, `String[] args`, and `ConfigurableBootstrapContext` can be referenced at this point; this does not mean runtime beans already exist.
3. To catch early events, you must **register the listener before `run()`** or via `META-INF/spring.factories`; a bean listener cannot catch this event.
4. Need prepared properties? Use `ApplicationEnvironmentPreparedEvent`. Need the context? Use the corresponding context milestone. Need post-refresh code? Use a runner or late event.
5. Do not confuse Starting, Started, and Ready: they belong to different phases and answer different operational questions.
6. Early listeners should be lightweight, have minimal dependencies, avoid logging secrets, and avoid I/O that could stall startup.
7. For genuine bootstrap dependencies, prefer `BootstrapRegistryInitializer` and supported bootstrap mechanisms instead of forcing Spring bean injection early.
