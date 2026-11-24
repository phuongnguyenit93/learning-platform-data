# Reading `SpringApplication.run` as a Sequence of Stages

A Spring Boot application can have an entry point as short as just two important lines:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

Looking at this code snippet, beginners can easily assume that `run` just "creates a Spring object and starts a server". In reality, `SpringApplication.run(...)` **orchestrates an ordered sequence of stages**, from preparing the configuration environment, building the `ApplicationContext`, registering bean definitions, refreshing the context, to invoking startup tasks and signaling that the application is ready.

Reading this sequence accurately helps answer practical questions: "Why can't I read a bean during the `Environment` preparation stage?", "Does `@PostConstruct` happen before or after `ApplicationRunner`?", "Why do I already see the `Started` log even though the application is not ready yet?", and "If a runner throws an exception, does `run` return a context or not?".

**Scope:** This lesson uses the Spring Boot **3.3.x** model, running on Java 17 or later. The classes and events in the lesson are real APIs; the stage descriptions serve as a mental model for reading the control flow, not a guarantee that every internal step always has a single identical method name across all versions.

## 1. Overview Map: From `main` to a Ready Application

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    |  [1] Start, register, and notify early listeners
    |      ApplicationStartingEvent
    |
    |  [2] Prepare Environment and configuration sources
    |      ApplicationEnvironmentPreparedEvent
    |
    |  [3] Create and configure ApplicationContext (not yet refreshed)
    |      ApplicationContextInitializedEvent
    |
    |  [4] Load configuration sources / BeanDefinitions
    |      ApplicationPreparedEvent
    |
    |  [5] Refresh ApplicationContext
    |      Instantiate eager singletons; apply post-processors
    |      Start embedded web server if it is a web application
    |      ContextRefreshedEvent and web server events if applicable
    |
    |  [6] Context has finished refreshing
    |      ApplicationStartedEvent
    |      LivenessState.CORRECT
    |
    |  [7] Run ApplicationRunner / CommandLineRunner
    |
    |  [8] Publish ApplicationReadyEvent
    |      ReadinessState.ACCEPTING_TRAFFIC
    |
    v
Return ConfigurableApplicationContext to the caller of run(...)
~~~

If an error causes startup to fail, the happy path does not complete the diagram: Spring Boot handles the error, may publish `ApplicationFailedEvent`, closes already-created resources, and lets the exception propagate out of `run`. There is no guarantee that `ApplicationReadyEvent` will be published or that a context will be returned.

The most important point is **three distinct milestones**:

- **Context created:** An appropriate `ApplicationContext` object exists, which does not yet guarantee it contains fully initialized beans.
- **Context refreshed:** Main Spring container initialization has completed; `ApplicationStartedEvent` occurs before the runners.
- **Application has passed the runners:** `ApplicationReadyEvent` and the readiness signal occur toward the end of the startup sequence.

In an application without a web server, this entire sequence still takes place: Spring Boot still creates the context, processes beans, and runs runners; it simply omits the HTTP port-opening stage.

## 2. What Work Does `SpringApplication` Perform?

`SpringApplication` is the **startup orchestrator**; `ApplicationContext` is the **Spring container** that holds metadata and manages beans once created.

A standard entry-point example:

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

`@SpringBootApplication` provides Spring Boot configuration, enables auto-configuration, and scans components within the appropriate package scope. It does not replace the startup process itself; it is the `run` call that initiates the stages of creating and refreshing the context.

There are two conceptually equivalent ways to invoke it:

~~~java
// Use the convenience method for default configuration:
SpringApplication.run(MyApplication.class, args);

// Or create an instance to customize before running:
SpringApplication application = new SpringApplication(MyApplication.class);
application.run(args);
~~~

The two snippets above are **two alternative entry-point approaches**, not meant to be placed sequentially in the same `main`. When using the second approach, you can call `addListeners(...)`, `addInitializers(...)`, `setBannerMode(...)`, or configure the application type before `run` starts.

The result on the success path is a `ConfigurableApplicationContext`. This is an active Spring context; calling code can retrieve beans, inspect state, and close the context when it is responsible for managing its lifecycle. `run` **does not return a `SpringApplication` instance and does not return an HTTP status code**.

## 3. Stage 1 — Starting and Publishing `ApplicationStartingEvent`

When `run` starts, Spring Boot prepares startup support components and notifies early listeners. `ApplicationStartingEvent` is published **before `Environment` and `ApplicationContext` are ready**.

At this point:

- You can observe that Spring Boot has started running.
- You cannot yet assume Spring beans exist for `@Autowired`.
- You cannot yet read application configuration through an `Environment` belonging to the newly created context, because the context does not exist yet.

To catch these very early events, register listeners **before calling `run`**:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(event -> {
    // Event handling logic must match the received event type.
});
application.run(args);
~~~

This is an illustrative example showing where to register; the full runnable example later uses a variable typed as `ApplicationListener<ApplicationEvent>` and filters for specific events.

**Do not** create a `@Component` bean and expect it to catch every event from the very beginning. Such a bean only appears after context loading and initialization have progressed far enough. That is why Spring Boot provides the ability to register listeners directly on `SpringApplication`.

## 4. Stage 2 — Preparing `Environment` and Configuration

`Environment` aggregates property sources and profile information needed to build the application. During the preparation stage, Spring Boot handles mechanisms related to:

- Application arguments such as `--server.port=9090`, `--spring.profiles.active=dev`.
- JVM system properties, environment variables, and configuration declared in files.
- `application.properties`/`application.yml` files and profile-specific configuration through Spring Boot's configuration processing mechanism.
- Determining properties that control `SpringApplication` behavior and conditions needed for later stages.

`ApplicationEnvironmentPreparedEvent` signals that the required environment has been prepared **before the context is created**. Listeners at this stage can inspect or modify property sources per the API contract, but **must not expect to retrieve beans from the context**.

Example run:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --demo.message=hello"
~~~

When the default configuration enables command-line argument processing, `demo.message` can later be read with:

~~~java
String value = environment.getProperty("demo.message", "missing");
~~~

The line above is **an expression inside code where `Environment` is provided**; it is not a standalone `javac` program. The expected value is `hello` when no higher-precedence source overrides it.

**Timing distinction:** "`Environment` exists" does not mean "all beans have been created". Annotations such as `@Value`, `@ConfigurationProperties`, and auto-configuration conditions can use information from `Environment` during subsequent container-building stages.

## 5. Stage 3 — Creating and Preparing `ApplicationContext`

Once `Environment` is ready, Spring Boot selects and creates an appropriate context type. Common types in Spring Boot 3.3 include:

| Application type | Common default context type | Meaning |
| --- | --- | --- |
| Servlet web, e.g., with Spring MVC | `AnnotationConfigServletWebServerApplicationContext` | Manages beans and the embedded servlet server lifecycle |
| Reactive web | `AnnotationConfigReactiveWebServerApplicationContext` | Manages beans and the reactive server lifecycle |
| No web server | `AnnotationConfigApplicationContext` | Manages beans for background/CLI programs/libraries running as applications |

The actual type also depends on the classpath, `WebApplicationType`, and customizations provided by the application. Do not infer the context type merely from the project name.

At this stage, Spring Boot attaches `Environment` and required components, invokes registered `ApplicationContextInitializer` instances, and then publishes `ApplicationContextInitializedEvent`. **The context has been created but not yet refreshed, and bean definitions from application sources have not yet been fully loaded.**

An `ApplicationContextInitializer<ConfigurableApplicationContext>` can configure some properties of the context **before refresh**:

~~~java
application.addInitializers(context ->
        context.getEnvironment()
                .getPropertySources()
                .addFirst(new org.springframework.core.env.MapPropertySource(
                        "startupOverride",
                        java.util.Map.of("demo.initialized", "yes"))));
~~~

This snippet belongs to customizing the `SpringApplication application` object created in `main`; it must be placed **before `application.run(args)`**. It is a technical example to recognize the stage: even without creating application beans yet, you can still add a `PropertySource`. In real usage, consider configuration precedence order and avoid adding high-priority sources arbitrarily.

## 6. Stage 4 — Loading Bean Definitions and Preparing for Refresh

After the context is prepared, Spring Boot loads initial configuration sources and turns them into **`BeanDefinition`** instances: descriptions of how to create, configure, and manage beans. Sources typically start from the main class annotated with `@SpringBootApplication` and expand via component scanning, `@Configuration`, `@Bean` methods, and auto-configuration.

`ApplicationPreparedEvent` is published **after initial bean definitions have been loaded, but before refresh begins**.

This is an important boundary:

| Concept | Explanation |
| --- | --- |
| `BeanDefinition` | Recipe/descriptor telling Spring a bean's type, how to create it, and required configuration metadata |
| Actual bean object | Instance created from the bean definition, put through initialization steps and lifecycle management |
| `refresh()` | Stage where the container finalizes management mechanisms and instantiates required beans |

Therefore, **having a `BeanDefinition` does not mean every instance already exists**. If a program tries to look up or instantiate beans too early in a listener, it may encounter an unready container state or alter the intended initialization order.

Also remember that **auto-configuration is not a "secret process running after the application is ready"**: it participates in processing bean definitions and building the container, before the application reaches the `Started`/`Ready` events.

## 7. Stage 5 — `refresh()`: The Spring Container Is Actually Initialized

When `refresh` is called on `ApplicationContext`, Spring Framework orchestrates the container's steps. Several points are worth recognizing conceptually:

1. Prepare the bean factory and foundational context components.
2. Process `BeanFactoryPostProcessor` instances or related variants to finalize bean definitions; this step can strongly affect component scanning, configuration, and auto-configuration.
3. Register and apply `BeanPostProcessor` instances for bean creation/initialization, including mechanisms for dependency injection, proxying, or annotation processing.
4. Instantiate **non-lazy** singletons that the container needs to initialize early, resolve dependencies, and invoke lifecycle callbacks such as `@PostConstruct` as appropriate.
5. Complete the refresh process, activate context lifecycle components, and publish `ContextRefreshedEvent`.

This list describes the **conceptual meaning**, without trying to mirror every internal Spring Framework call verbatim. Specifically, beans declared as lazy or only requested later may **not yet be created when refresh completes**.

In web applications, creating and starting an embedded web server such as Tomcat or a reactive server is tied to the web context's refresh lifecycle. You can observe `ServletWebServerInitializedEvent` or `ReactiveWebServerInitializedEvent` when the respective server is ready at the web-server level.

### Why Does `@PostConstruct` Usually Run Before `ApplicationRunner`?

`@PostConstruct` is an initialization callback **of a single bean**. For a singleton bean created during refresh, this callback executes during instance preparation, before the context signals that refresh is complete. `ApplicationRunner`, by contrast, is invoked by Spring Boot **after `ApplicationStartedEvent`**. Thus, for a non-lazy bean created during refresh, the usual order is:

~~~text
Create bean -> Inject dependencies -> @PostConstruct
    -> ContextRefreshedEvent
    -> ApplicationStartedEvent
    -> ApplicationRunner / CommandLineRunner
    -> ApplicationReadyEvent
~~~

However, you should not state that "every `@PostConstruct` runs before every runner": a lazy bean may only be created when it is requested later. This is an important exception for reading logs accurately.

### Why Doesn't "Tomcat Opened Its Port" Equal "Application Ready"?

The web server can enter an active state during refresh, **before runners finish**. When you have readiness probes and traffic routers, rely on appropriate readiness/health signals rather than checking only that the TCP port is open.

## 8. Stage 6 — `ApplicationStartedEvent` and Liveness State

After successfully refreshing the context, Spring Boot publishes **`ApplicationStartedEvent`**. This milestone occurs **before invoking `ApplicationRunner` and `CommandLineRunner`**.

Right after the started milestone, Spring Boot publishes an `AvailabilityChangeEvent` corresponding to `LivenessState.CORRECT` in the standard availability mechanism. Meaning: the container has passed a major milestone and the application is considered alive; this is **not proof that post-context tasks have finished**.

Distinguish these four signals:

| Signal | Milestone when it occurs | What can be concluded |
| --- | --- | --- |
| `Starting ...` log | Early stage | Spring Boot has begun starting up |
| `ContextRefreshedEvent` | When refresh completes | The container has completed the refresh process |
| `ApplicationStartedEvent` | After refresh, before runners | The main context initialized successfully |
| `ApplicationReadyEvent` | After runners | The `SpringApplication` lifecycle has completed runner tasks |

The `Started MyApplication in ...` log message is generally tied to the started milestone and **does not mean `ApplicationReadyEvent` has been published**. In addition, the log can be disabled with `spring.main.log-startup-info=false`; the lifecycle events still occur.

## 9. Stage 7 — Running `ApplicationRunner` and `CommandLineRunner`

This is where Spring Boot invokes registered runner beans to perform work right after the context refreshes. Both interfaces support startup tasks, differing in their input argument types:

~~~java
@Bean
ApplicationRunner inspectArgs() {
    return args -> {
        System.out.println(args.getOptionNames());
        System.out.println(args.getNonOptionArgs());
    };
}

@Bean
CommandLineRunner inspectRawArgs() {
    return args -> {
        System.out.println(java.util.Arrays.toString(args));
    };
}
~~~

The two beans above are **code snippets used inside a `@Configuration`/`@SpringBootApplication` class with appropriate imports**. `ApplicationRunner` receives `ApplicationArguments` already parsed by Spring Boot; `CommandLineRunner` receives the raw `String[]` array in order.

Runners can use beans injected from the container. When there are multiple runners, execution order can be controlled with `@Order` or `Ordered`. Without an explicit ordering definition, do not design business logic assuming runner A will always run before runner B.

If a runner throws an unhandled exception, the `run` process is treated as a startup failure: the ready event will **not** be published on the success path, even though the context refreshed earlier. This is a common cause of the situation where "the `Started` log appeared, yet the program still reports a startup error".

Avoid doing heavy, unbounded work inside a runner if the goal is for the application to accept traffic quickly. A runner that blocks forever will delay `ApplicationReadyEvent`; design background work and operational signals according to your system's needs.

## 10. Stage 8 — `ApplicationReadyEvent`, Readiness, and the Return Value

Once the runners finish successfully, Spring Boot publishes **`ApplicationReadyEvent`**. Immediately afterward, the standard availability mechanism publishes **`ReadinessState.ACCEPTING_TRAFFIC`**.

In traffic-routing contexts, `ReadinessState.ACCEPTING_TRAFFIC` is a stronger signal than "the port is open", because it reflects the readiness milestone managed by Spring Boot. Still, a real-world application may need dedicated health checks to evaluate databases, message queues, dependent services, or business conditions.

At the end of the happy path, `SpringApplication.run(...)` returns an active **`ConfigurableApplicationContext`**. Read it as follows:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

System.out.println(context.isActive());
~~~

This is illustrative code inside `main` with import `org.springframework.context.ConfigurableApplicationContext`. If there are no errors and the context remains active, the line above prints:

~~~text
true
~~~

Do not confuse **"`run` returns"** with **"the JVM must exit"**. A web application typically keeps running because the background server is active; a CLI application with no background tasks may exit on its own when no non-daemon threads remain to keep the program alive. For an application managing its own context, you can call `context.close()` to release resources when appropriate.

## 11. Hands-on Example: Observing the Real Event Sequence

The following example uses **Java 17 and Spring Boot 3.3.x**, running **without a web server** so each milestone is easy to see without being obscured by Tomcat logs. It registers a listener **before `run`**, filters for the Spring Boot events to observe, adds an `ApplicationRunner`, and prints the context status after `run` returns.

### Project Structure

~~~text
startup-stages-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/StartupStagesDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'startup-stages-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
~~~

The project requires a Gradle version compatible with Spring Boot 3.3 and access to the dependency repository for the initial download. If your existing project already uses the Spring Boot plugin, use the version matching your project rather than adding duplicate plugin configuration. If the project has a Gradle Wrapper, prefer running with the project's wrapper; if no wrapper has been generated yet, you can use an installed Gradle binary to run `gradle bootRun`.

File `src/main/java/com/example/runtime/StartupStagesDemo.java`:

~~~java
package com.example.runtime;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupStagesDemo {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StartupStagesDemo.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        ApplicationListener<ApplicationEvent> trace = event -> {
            boolean milestone =
                    event instanceof ApplicationStartingEvent
                    || event instanceof ApplicationEnvironmentPreparedEvent
                    || event instanceof ApplicationContextInitializedEvent
                    || event instanceof ApplicationPreparedEvent
                    || event instanceof ApplicationStartedEvent
                    || event instanceof ApplicationReadyEvent;

            if (milestone) {
                System.out.println("EVENT " + event.getClass().getSimpleName());
            }
        };

        application.addListeners(trace);

        ConfigurableApplicationContext context = application.run(args);
        System.out.println("RETURN contextActive=" + context.isActive());
        context.close();
    }

    @Bean
    ApplicationRunner printRunner() {
        return args -> System.out.println("RUNNER ApplicationRunner");
    }
}
~~~

**Why does the example only catch six events?** `ApplicationEvent` is a broad parent type. During refresh, Spring Framework also publishes events like `ContextRefreshedEvent`, and Spring Boot adds `AvailabilityChangeEvent`. To keep the output easy to follow and deterministically ordered, the example prints only selected milestones; the other events are still processed normally by the framework.

### Running and Reading the Output

In the project directory, if you already have the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Or run with an installed Gradle if there is no wrapper yet:

~~~bash
gradle bootRun
~~~

The lines **printed by the example code**, in the expected order on a successful run, are:

~~~text
EVENT ApplicationStartingEvent
EVENT ApplicationEnvironmentPreparedEvent
EVENT ApplicationContextInitializedEvent
EVENT ApplicationPreparedEvent
EVENT ApplicationStartedEvent
RUNNER ApplicationRunner
EVENT ApplicationReadyEvent
RETURN contextActive=true
~~~

This is **the output printed by the application itself**, excluding Gradle task messages, other logging output, or elapsed time. There are no web server logs because `WebApplicationType.NONE` was set.

Compare the lines:
1. `ApplicationStartingEvent` comes first because startup has just been announced.
2. `ApplicationEnvironmentPreparedEvent` precedes `ApplicationContextInitializedEvent` because configuration must be prepared before building the context.
3. `ApplicationPreparedEvent` precedes `ApplicationStartedEvent` because the context refresh step sits between them.
4. `ApplicationStartedEvent` appears **before** the runner line.
5. `ApplicationReadyEvent` appears **after** the runner, and the `RETURN` line only appears once `run` completes.

### Trying Variations to See the Boundaries

- Remove `application.setLogStartupInfo(false)`: you may see additional INFO-level startup logs, but **the order of `EVENT`/`RUNNER`/`RETURN` lines does not change**.
- Replace `application.setWebApplicationType(WebApplicationType.NONE)` with an appropriate web type **when the project has the required web dependency**: the overall sequence preserves its meaning, with web server initialization added during refresh.
- Add `throw new IllegalStateException("runner failed");` inside the `ApplicationRunner` lambda body **only to experiment in a learning environment**: the program no longer prints `ApplicationReadyEvent`/`RETURN` on the success path, and Spring Boot reports a startup failure. Remove the throwing line after observing.
- Try subscribing to `ApplicationStartingEvent` using an `@EventListener` bean created in the context: it cannot observe this early event during a normal startup because the listener bean itself does not exist yet when the event is published.

## 12. Finding the Right Place to Hook Into the Startup Sequence

Catching the right milestone helps you handle the right task and reduces code that relies on implicit ordering.

| Need | Commonly suitable extension point | Reason |
| --- | --- | --- |
| Observe when Spring Boot first starts | Early-registered `ApplicationListener<ApplicationStartingEvent>` | `Environment` and context do not exist yet |
| Add/adjust property sources before container construction | `ApplicationEnvironmentPreparedEvent` listener or supported configuration mechanism | `Environment` exists, beans have not been created yet |
| Customize the context object before refresh | `ApplicationContextInitializer` | Acts right after the context is created |
| Add bean definitions in a framework-supported way | `@Configuration`, `@Bean`, auto-configuration, `BeanDefinitionRegistryPostProcessor` when truly needed | Matches the bean definition management stage |
| Per-bean initialization | Constructor, dependency injection, `@PostConstruct` | Tied to the bean creation lifecycle |
| Run one-time work after the container refreshes | `ApplicationRunner` or `CommandLineRunner` | Beans are provided; order can be controlled with `@Order` |
| React when the application finishes runners | `ApplicationReadyEvent` | Observes Spring Boot's ready milestone |
| Observe startup failure | `ApplicationFailedEvent`, failure analysis reporting | Failure path does not reach the ready event |

Avoid writing long-running logic inside listeners because many listeners are invoked synchronously on the default thread. Blocking work can delay the time to reach readiness or cause startup to fail if an unhandled exception escapes.

## 13. When `run` Fails: Locating the Stopped Stage

Not all startup exceptions originate at the same spot. When troubleshooting errors, read logs according to the last completed stage:

| Observed symptom | Stage to inspect first | Example |
| --- | --- | --- |
| No `ApplicationEnvironmentPreparedEvent` | Beginning of flow, early listeners, or environment preparation | Very early setup error, listener throws exception |
| `EnvironmentPrepared` present, no `Prepared` | Context preparation/creation, loading configuration sources | Configuration source error or context construction issue |
| `Prepared` present, no `Started` | `refresh`, bean factory, bean creation, web server | Missing dependency, bean creation failure, server port in use |
| `Started` present, no `Ready` | Runners, late listeners, post-refresh tasks | `ApplicationRunner`/`CommandLineRunner` throws exception |
| `Ready` reached, then business error occurs | After startup has passed | Request error, background task error, connection drop after ready |

This table is a **triage guide**, not a complete root-cause classifier. Listeners themselves can throw exceptions, logging may be disabled, and some errors can occur after the last observed event milestone.

For startup failures, Spring Boot typically uses `ApplicationFailedEvent` and failure analysis to report errors. When running via Gradle, separate Gradle build/configuration errors from errors inside the application JVM; use the stack trace and root cause to diagnose rather than relying solely on event milestones.

Important: if a runner fails, **the fact that the context finished refreshing earlier does not mean the overall `run` call succeeded**. On the failure branch, Spring Boot can perform cleanup and throw the exception; code after `SpringApplication.run(...)` in `main` will not execute as on the normal flow.

## 14. Common Misconceptions

**Misconception 1: "`run` only starts Tomcat."** It is the orchestrator for every kind of Spring Boot application, including CLI apps without Tomcat.

**Misconception 2: "`ApplicationContextInitializedEvent` means all beans are ready."** At that point the context has just been configured and initializers have run; loading bean definitions and refreshing still lie ahead.

**Misconception 3: "Once `BeanDefinition` is loaded, beans are already created."** A bean definition is a descriptor. Instances are created according to container conditions and timing; lazy beans may be created later.

**Misconception 4: "`ApplicationStartedEvent` is the event for starting `main`."** The name is easily misunderstood. In Spring Boot 3.3, the early event is `ApplicationStartingEvent`; `ApplicationStartedEvent` occurs **after refresh**, before runners.

**Misconception 5: "`ApplicationReadyEvent` occurs as soon as the HTTP port opens."** The port can open during the refresh stage; ready comes after the runners.

**Misconception 6: "An `@EventListener` bean catches every startup event."** Events occurring before the context creates beans require early-registered listeners, for example via `SpringApplication.addListeners`.

**Misconception 7: "`@PostConstruct` is the right place to access any external system."** This callback belongs to the bean lifecycle and can affect the refresh process. For initialization tasks after the container is ready, consider a runner; for long-running background work, use explicit lifecycle/task management mechanisms.

**Misconception 8: "Seeing `Started ...` alone means traffic can be served."** The started log signals one milestone; readiness to accept traffic also depends on runners and system readiness/health.

**Misconception 9: "`run` always returns a context, even when startup fails."** If an exception escapes the startup process, the call does not return normally. You must handle failures rather than assuming a context can always be obtained.

## 15. Knowledge Self-Check

1. Question: `ApplicationEnvironmentPreparedEvent` has fired, but `ApplicationContextInitializedEvent` has not. **Can you retrieve a bean using `context.getBean(...)` yet?** No: the context has not been created at the time of the environment event.
2. Question: `ApplicationPreparedEvent` has fired. **Can you conclude that all singletons have finished initializing?** No: `refresh` has not completed yet.
3. Question: `ApplicationStartedEvent` has fired, and runners are about to run. **Has `ApplicationReadyEvent` fired yet?** No.
4. Question: A runner waits on an external task for a long time. **Which milestone is delayed?** `ApplicationReadyEvent` and the readiness state for accepting traffic.
5. Question: You only need to log the profile name from an early stage. **Which extension point should you choose?** A listener for `ApplicationEnvironmentPreparedEvent`, because `Environment` exists at that point.
6. Question: A CLI application has finished running all runners. **Why might the program exit immediately?** There is no web server or other threads to keep the JVM alive; completing the startup sequence does not by itself force the process to stay alive forever.
7. Question: `@PostConstruct` on a lazy bean runs after `ApplicationReadyEvent` has been published. **Is that a contradiction?** No: a lazy bean can be instantiated for the first time after ready.

Once you can explain on your own why the three milestones **`Environment prepared` → `Context refreshed/Started` → `Runners completed/Ready`** are distinct, you have a reliable map for reading source code, placing logs, choosing extension points, and isolating Spring Boot startup failures.

### References

- Spring Boot 3.3.13 — `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `SpringApplication`, Application Events and Listeners, Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — `ApplicationContext` and Bean Lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
