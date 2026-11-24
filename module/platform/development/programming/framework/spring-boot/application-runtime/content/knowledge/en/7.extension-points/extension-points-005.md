# SpringApplicationRunListener and Run Callbacks

## 1. What is SpringApplicationRunListener, and why understand it?

A Spring Boot application typically starts with:

```java
SpringApplication.run(DemoApplication.class, args);
```

This call looks short, yet internally it encompasses many stages: building environment configuration, choosing and creating `ApplicationContext`, loading bean definitions, calling `refresh()` on the context, running `ApplicationRunner` or `CommandLineRunner`, and announcing that the application is ready. In practice, you sometimes need to **observe or participate at these early moments**, before application beans exist.

`org.springframework.boot.SpringApplicationRunListener` is **the extension point for a single `SpringApplication.run(...)` invocation**. Spring Boot locates implementations of this interface via `SpringFactoriesLoader`, creates one instance per run, and invokes the corresponding callbacks throughout the startup sequence.

Imagine three layers of responsibility:

1. **`SpringApplication`** orchestrates a single startup run and handles success or failure.
2. **`SpringApplicationRunListener`** receives milestones of the `run` flow itself: started running, `Environment` prepared, context prepared, bean sources loaded, started, runners finished, or failed with an error.
3. **`ApplicationContext`** manages beans, configuration, events, and resources once constructed; many of the earliest callbacks occur **before the context is fully usable**.

Normal applications **are not required** to write a custom `SpringApplicationRunListener`. Spring Boot already provides a key internal implementation named `EventPublishingRunListener` to turn run milestones into events such as `ApplicationStartingEvent`, `ApplicationReadyEvent`, and so on. This extension point is useful when building shared infrastructure, measuring startup duration, preparing very early bootstrap data, or integrating startup observability under a clearly ordered contract.

**Distinction:** a listener's `ready(...)` callback only signals a milestone in the `run` sequence. It does not replace health checks, deployment environment readiness probes, or confirmation that all external services are available.

## 2. Standard callback sequence on successful startup

In Spring Boot **3.3.x**, the methods to remember are:

```text
SpringApplication.run(args)
    |
    v
starting(bootstrapContext)
    |
    v
Prepare and finalize Environment
    |
    v
environmentPrepared(bootstrapContext, environment)
    |
    v
Create and prepare ApplicationContext
    |
    v
contextPrepared(context)
    |
    v
Load sources / bean definitions into context
    |
    v
contextLoaded(context)
    |
    v
refresh() ApplicationContext
    |  - BeanFactoryPostProcessor, BeanPostProcessor
    |  - instantiate appropriate singletons
    |  - start web server when running a web app
    v
started(context, timeTaken)
    |
    v
Invoke ApplicationRunner / CommandLineRunner
    |
    v
ready(context, timeTaken)
    |
    v
SpringApplication.run returns context
```

If any stage during `run` throws an exception, Spring Boot enters the failure-handling path and can call:

```text
failed(context, exception)
```

**`failed(...)` is the error branch, not a step called after `ready(...)` on a successful startup path.** For failures occurring very early, the `context` passed to `failed` may be `null`.

Full table:

| Callback in Spring Boot 3.3 | Timing | Available data | Suitable tasks |
| --- | --- | --- | --- |
| `starting(ConfigurableBootstrapContext)` | At the very start of `run` | Bootstrap context; application `Environment` not fully prepared yet | Record start timestamp, lightweight bootstrap initialization |
| `environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment)` | After environment preparation, before creating application context | `Environment` and configuration sources prepared for this stage | Read required profiles/properties, observe non-sensitive config |
| `contextPrepared(ConfigurableApplicationContext)` | Context just created and prepared, before loading sources | Context object and linked environment | Observe context type, perform appropriate early setup |
| `contextLoaded(ConfigurableApplicationContext)` | Bean sources loaded into context, **before `refresh`** | Bean definitions loaded per preparation flow | Controlled metadata inspection, record pre-refresh milestone |
| `started(ConfigurableApplicationContext, Duration)` | Context refreshed, before running runners | Context initialized; startup duration if measured | Observe started context, record startup metrics |
| `ready(ConfigurableApplicationContext, Duration)` | After runners, immediately before `run` finishes | `ApplicationRunner` and `CommandLineRunner` completed successfully | Confirm boot run phase completed, measure time to ready |
| `failed(ConfigurableApplicationContext, Throwable)` | When startup fails | Throwable; context may be `null` | Safely record error diagnostics for telemetry |

These callbacks are declared as **default methods** on the interface in Spring Boot 3.3. Implementations only need to override the milestones they care about; the table remains helpful for understanding the complete lifecycle.

## 3. Exact Spring Boot 3.3 API signatures

The relevant methods, condensed into a single readable interface:

```java
public interface SpringApplicationRunListener {

    default void starting(ConfigurableBootstrapContext bootstrapContext) { }

    default void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) { }

    default void contextPrepared(ConfigurableApplicationContext context) { }

    default void contextLoaded(ConfigurableApplicationContext context) { }

    default void started(
            ConfigurableApplicationContext context,
            Duration timeTaken) { }

    default void ready(
            ConfigurableApplicationContext context,
            Duration timeTaken) { }

    default void failed(
            ConfigurableApplicationContext context,
            Throwable exception) { }
}
```

This is a **signature summary**, omitting imports, Javadoc, and library internals. When writing real code, import:

```java
import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
```

Pay close attention to version changes:

- Spring Boot 3.3 uses `starting(ConfigurableBootstrapContext)`, **not** the legacy `starting()`.
- `environmentPrepared(...)` takes **two** parameters, including `ConfigurableBootstrapContext`, **not** the single-parameter `ConfigurableEnvironment` signature from very old versions.
- `started` and `ready` both include `Duration timeTaken`; the single context-parameter signature is no longer the override signature in 3.3.
- Instead of the `finished(...)` callback from Spring Boot 1.x documentation, Spring Boot 3.3 distinguishes `ready(...)` and `failed(...)`.

When the IDE reports "method does not override or implement", check the exact Spring Boot dependency version and current signatures before randomly renaming callbacks.

## 4. What can and cannot be done at each milestone?

### 4.1. starting: the earliest point

`starting(...)` occurs right as `SpringApplication.run(...)` begins. At this moment there is **no `ApplicationContext` yet** for calling `getBean(...)`; `application.properties` configuration has not gone through full `Environment` preparation either.

Should be used to:

- Record a starting timestamp for timing measurements.
- Initialize bootstrap resources genuinely needed before the context, if any and with lifecycle understood.
- Attach limited bootstrap data instead of trying to access business beans.

Should not be used to:

- Call beans with `@Autowired`.
- Assume final active profiles have been determined.
- Execute long network tasks or business logic.
- Assume the logging system is ready with full configuration in every environment.

`ConfigurableBootstrapContext` is an object dedicated to bootstrap infrastructure. It supports registering and retrieving bootstrap objects prepared before the context is finalized. **It is not a full `ApplicationContext` or `BeanFactory`**, so `bootstrapContext.get(...)` (when used) does not behave like normal bean lookup.

### 4.2. environmentPrepared: reading config before context exists

`environmentPrepared(bootstrapContext, environment)` is called once the environment has been prepared by Spring Boot for this run and **before creating the context**.

Example:

```java
@Override
public void environmentPrepared(
        ConfigurableBootstrapContext bootstrapContext,
        ConfigurableEnvironment environment) {

    String name = environment.getProperty(
            "spring.application.name", "unnamed");
    System.out.println("Application name = " + name);
}
```

This is a **method snippet placed inside a class implementing `SpringApplicationRunListener`**, not a standalone Java program. It can read properties or profiles within appropriate bounds.

Some details:

- `ConfigurableEnvironment` lets you inspect `PropertySources`, active profiles, and property resolution.
- Configuration may originate from files, environment variables, system properties, command-line arguments, and sources introduced during bootstrap.
- Avoid printing all of `environment.getPropertySources()` or environment variables. They may contain secrets.
- Do not assume every setting can be changed arbitrarily here without affecting the consistency of components that already ran earlier.
- `EnvironmentPostProcessor` is the more specialized extension point if the main goal is **adding or modifying a PropertySource** during environment preparation.

### 4.3. contextPrepared: context exists, sources not loaded yet

At `contextPrepared(context)`, `SpringApplication` has created and prepared the context, and applied applicable `ApplicationContextInitializer` instances in internal order. However, **primary bean sources have not yet been loaded into the context as in the next step of the sequence**.

Reasonable actions:

- Observe the context class name.
- Record a bootstrap milestone.
- Use early context configuration capabilities cautiously when truly building framework infrastructure.

Actions to avoid:

```java
// Wrong expectation if the bean has not been registered/created yet:
MyService service = context.getBean(MyService.class);
service.run();
```

There is no guarantee this bean exists at `contextPrepared`. If you need to customize the context before refresh, `ApplicationContextInitializer` usually has clearer semantics and is designed for that job.

### 4.4. contextLoaded: definitions present, not refreshed yet

`contextLoaded(context)` is called after application sources have been loaded and **before `refresh()`**. This is a moment where "loaded" is especially easy to confuse with "initialized".

In the pre-refresh phase:

- Bean definitions may already be registered.
- Singletons are not guaranteed to be instantiated.
- `BeanFactoryPostProcessor` and `BeanPostProcessor` have not finished their refresh work.
- Beans using `@ConfigurationProperties`, proxies, auto-configuration, or lifecycle callbacks should not yet be treated as ready for runtime use.

Therefore, do not arbitrarily invoke business logic or `getBean(...)` inside `contextLoaded`. Instantiating beans prematurely can bypass framework processing steps those beans must go through.

### 4.5. started: refresh complete, runners not run yet

`started(context, timeTaken)` indicates that the context has been refreshed and the application has completed its main initialization phase, **but `ApplicationRunner` and `CommandLineRunner` have not been called yet**.

This milestone can be used to record post-refresh timing or observe created configuration. However, a task inside a runner might still need to create tables, validate data, or prepare partial state; `started` cannot be used as proof that all startup work is done.

`Duration timeTaken` may be `null` if timing data is unavailable. Do not immediately call `timeTaken.toMillis()` while ignoring this possibility.

### 4.6. ready: after runners, right before run returns

`ready(context, timeTaken)` is called after Spring Boot finishes running runners in a successful startup run, right before `SpringApplication.run(...)` completes.

Interpret this milestone as: **the `run` sequence has reached a successful conclusion**. It does not assert that all external connections are healthy, queues are drained, or load balancers are routing traffic to the instance.

To observe readiness in a deployment environment, use appropriate health/readiness signals. An `ApplicationReadyEvent` is also published around the corresponding time via Spring Boot's event listener mechanism.

### 4.7. failed: receiving errors from any possible stage

`failed(context, exception)` can be called when an exception occurs across many stages: environment preparation, context creation, refresh, running runners, and so on.

- `exception` is the error Spring Boot is handling.
- `context` **can be `null`** if failure occurred before context creation.
- `ready` will not be reached on that failing path.
- Use this error to capture additional diagnostics; do not silently swallow the exception or try to keep running a half-initialized application.

If failure handling inside this callback throws another exception, the original cause may be obscured or error handling complicated. Keep handling lightweight, free of new exceptions, and free of leaked credentials.

## 5. Registering SpringApplicationRunListener via spring.factories

A critical technical distinction is that **SpringApplicationRunListener is loaded by `SpringFactoriesLoader` from the classpath very early in startup**. Simply adding `@Component` to the class is not enough for Boot to select it as a run listener.

Example application layout:

```text
src/
  main/
    java/
      demo/startup/
        DemoApplication.java
        TraceRunListener.java
    resources/
      META-INF/
        spring.factories
      application.properties
```

Contents of `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.startup.TraceRunListener
```

The key in the file is **the fully qualified interface name** `org.springframework.boot.SpringApplicationRunListener`. The value is **the fully qualified class name** of the implementation.

Spring Boot uses `SpringFactoriesLoader` to find and instantiate registered listeners. Each call to `run(...)` gets a fresh instance of `SpringApplicationRunListener` for that startup run.

**Mandatory constructor:** the implementation must provide a **public constructor** taking `SpringApplication` and `String[]` (in that exact order). This differs sharply from a bean created via regular injection.

```java
public TraceRunListener(SpringApplication application, String[] args) {
    // Store relevant info or initialize lightweight infrastructure.
}
```

Do not use a zero-argument constructor or a constructor taking only `ApplicationContext` expecting `SpringFactoriesLoader` to inject it like Spring IoC. Before context creation is reached, Spring IoC is not ready to do that anyway.

**Distinction from registering `ApplicationListener`**: to register an `ApplicationListener` through `spring.factories`, the key is `org.springframework.context.ApplicationListener`. The two keys serve two different interfaces. A class implementing `SpringApplicationRunListener` is not automatically an `ApplicationListener<ApplicationEvent>`, and vice versa.

If building a shared library, `META-INF/spring.factories` should be packaged inside the library JAR. When that library is on the classpath, the loader can discover its registration. This causes the startup hook to affect multiple applications, so clarify version compatibility and avoid unnecessary side effects.

## 6. Runnable example with Spring Boot 3.3 and Java 17+

This example uses **Spring Boot 3.3**, Java 17 or newer, and the `spring-boot-starter` dependency. It uses an application without a web server to focus on observing startup; the same listener type still works when the application is `SERVLET` or `REACTIVE`.

### 6.1. SpringApplicationRunListener class

Create `src/main/java/demo/startup/TraceRunListener.java`:

```java
package demo.startup;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

public final class TraceRunListener implements SpringApplicationRunListener {

    private final int argumentCount;

    public TraceRunListener(SpringApplication application, String[] args) {
        this.argumentCount = args.length;
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("RUN LISTENER: starting, args=" + argumentCount);
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        String name = environment.getProperty(
                "spring.application.name", "unnamed");
        System.out.println("RUN LISTENER: environmentPrepared, app=" + name);
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("RUN LISTENER: contextPrepared, type="
                + context.getClass().getSimpleName());
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("RUN LISTENER: contextLoaded");
    }

    @Override
    public void started(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN LISTENER: started, elapsed="
                + formatDuration(timeTaken));
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN LISTENER: ready, elapsed="
                + formatDuration(timeTaken));
    }

    @Override
    public void failed(
            ConfigurableApplicationContext context, Throwable exception) {
        System.out.println("RUN LISTENER: failed, cause="
                + exception.getClass().getSimpleName()
                + ", contextPresent=" + (context != null));
    }

    private static String formatDuration(Duration duration) {
        return duration == null ? "unknown" : duration.toMillis() + "ms";
    }
}
```

Design explanation:

- Both the class and constructor are `public` so the loader can instantiate it.
- The constructor takes `SpringApplication` and `String[]`. The example only stores the **count** of arguments rather than printing argument values, since they could contain sensitive information.
- Early callbacks do not call beans because the context is not ready.
- `contextPrepared(...)` only reads the context **class name**; it does not call `getBean`.
- `started` and `ready` handle `Duration == null`.
- `failed` checks whether context is null.
- `System.out.println` is used to illustrate the sequence. In real systems, choose logging/telemetry matching operational requirements, especially during stages before logging is fully configured.

The `SpringApplication application` parameter in the constructor is unused in this example; it must still be kept to match the signature.

### 6.2. Entry point and runner

Create `src/main/java/demo/startup/DemoApplication.java`:

```java
package demo.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            System.out.println("APPLICATION RUNNER: called");

            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("demonstration failure");
            }
        };
    }
}
```

`ApplicationRunner` is invoked **after `started` and before `ready`**. Checking the `--demo.fail` option lets us deliberately trigger an error inside the runner to observe the `failed` callback.

Configuration `src/main/resources/application.properties`:

```properties
spring.application.name=run-listener-demo
spring.main.web-application-type=none
```

With `NONE`, the application does not open an HTTP port; this does not change the fundamental callback sequence of `SpringApplicationRunListener`.

In `src/main/resources/META-INF/spring.factories`, register:

```properties
org.springframework.boot.SpringApplicationRunListener=demo.startup.TraceRunListener
```

Example dependency in `build.gradle` of **a project using the Spring Boot Gradle plugin**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

To run with the project's Gradle wrapper:

```bash
./gradlew bootRun
```

Or after building an executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/<actual-jar-name>.jar
```

The second line is **illustrative syntax**: replace `<actual-jar-name>` with the real filename produced by `bootJar`, without keeping angle brackets. With Maven, use the corresponding build/run commands.

### 6.3. Successful path output

When running without `--demo.fail`, the lines printed by the example code appear in this relative order:

```text
RUN LISTENER: starting, args=0
RUN LISTENER: environmentPrepared, app=run-listener-demo
RUN LISTENER: contextPrepared, type=AnnotationConfigApplicationContext
RUN LISTENER: contextLoaded
RUN LISTENER: started, elapsed=<elapsed-ms>
APPLICATION RUNNER: called
RUN LISTENER: ready, elapsed=<elapsed-ms>
```

The `<elapsed-ms>` placeholders are illustrative because actual timings vary by machine; the code prints milliseconds or `unknown` if duration is not provided. Spring Boot may print banners, logs, and other lines in between. Do not use the example to claim that full stdout consists only of the seven lines above.

With `spring.main.web-application-type=none` and no web classpath, the default context name is typically `AnnotationConfigApplicationContext`. If the project supplies a custom `ApplicationContextFactory`, the name may differ.

Important meaning of the order:

- The first two callbacks run when there is no context yet.
- `contextPrepared` then `contextLoaded` run before refresh.
- `started` proves refresh reached the end, though runners have not run yet.
- `ready` appears once runners have completed successfully.

### 6.4. Error branch output in runner

To produce a controlled failure:

```bash
./gradlew bootRun --args='--demo.fail'
```

If using a shell that does not support single quotes as above, adjust quoting syntax for your environment. You can pass `--demo.fail=true` and `ApplicationArguments.containsOption("demo.fail")` will still recognize it.

The relevant output lines look like:

```text
RUN LISTENER: starting, args=1
RUN LISTENER: environmentPrepared, app=run-listener-demo
RUN LISTENER: contextPrepared, type=AnnotationConfigApplicationContext
RUN LISTENER: contextLoaded
RUN LISTENER: started, elapsed=<elapsed-ms>
APPLICATION RUNNER: called
RUN LISTENER: failed, cause=IllegalStateException, contextPresent=true
```

`ready` **is not called** on this failure path. The exception thrown by the runner causes `SpringApplication.run` to fail; Gradle may report the run task failed or the JVM exits with a non-zero exit code. This is the expected result of the failure experiment, not a ready application.

The exception type seen by `failed` may differ when errors arise at other stages or are wrapped by the framework; do not rely on the `IllegalStateException` name for all failures.

## 7. EventPublishingRunListener and relationship with SpringApplicationEvent

Spring Boot uses an internal implementation named:

```text
org.springframework.boot.context.event.EventPublishingRunListener
```

It serves as the bridge between `SpringApplicationRunListener` callbacks and the **Spring application events** system. When a callback runs, the internal listener publishes the corresponding event so matching `ApplicationListener<?>` instances can receive notifications.

| Callback | Corresponding Boot event typically published |
| --- | --- |
| `starting` | `ApplicationStartingEvent` |
| `environmentPrepared` | `ApplicationEnvironmentPreparedEvent` |
| `contextPrepared` | `ApplicationContextInitializedEvent` |
| `contextLoaded` | `ApplicationPreparedEvent` |
| `started` | `ApplicationStartedEvent` |
| `ready` | `ApplicationReadyEvent` |
| `failed` | `ApplicationFailedEvent` |

These are **events published by Boot to observe progress**, distinct from directly invoking your run listener's methods. If an application has both a custom `TraceRunListener` and the internal event-publishing listener, both participate in the milestones; you do not need to republish the events listed above yourself.

Beyond this sequence, there are Spring Framework events like `ContextRefreshedEvent` and web server events like `ServletWebServerInitializedEvent` or `ReactiveWebServerInitializedEvent`. They can occur during the refresh phase, and **not all of them correspond to dedicated `SpringApplicationRunListener` callbacks**.

**Why does this distinction matter?** `ApplicationStartingEvent` is published before `ApplicationContext` exists. An application bean like:

```java
@Component
class LateEventListener {

    @EventListener
    void onStarting(ApplicationStartingEvent event) {
        // Do not rely on a @Component bean to receive this ultra-early event.
    }
}
```

cannot be considered a reliable way to receive ultra-early events, because the bean has not been instantiated at the time of publication. The snippet above illustrates the problem, requires matching imports, and should not be used as an implementation mechanism.

To receive early events, register an `ApplicationListener` **before `run(...)`** or use `spring.factories` under the proper `ApplicationListener` key.

## 8. Distinguishing SpringApplicationRunListener from other extension points

These APIs all relate to startup, but they are not completely interchangeable:

| Tool | When does it operate? | Main role |
| --- | --- | --- |
| `SpringApplicationRunListener` | Multiple milestones throughout `SpringApplication.run`, including pre-context and failure | Run-level tracking/orchestration |
| `ApplicationListener<ApplicationEvent>` | When an event is published and the listener is registered | Reacting to published events |
| `@EventListener` on a bean | After listener processing and bean are ready; depends on event | Reacting to events from an application bean |
| `ApplicationContextInitializer` | When context has been created, before refresh and primary sources loading | Early context configuration |
| `EnvironmentPostProcessor` | During environment preparation phase | Customizing property sources, profiles, or environment |
| `BeanFactoryPostProcessor` | During refresh, before most regular beans are instantiated | Adjusting bean definitions |
| `BeanPostProcessor` | During each bean's initialization lifecycle | Processing, proxying, or customizing beans |
| `ApplicationRunner` / `CommandLineRunner` | After refresh and before ready | Running bean-based initialization work |
| `ApplicationReadyEvent` listener | At the end of a successful startup | Reacting when Spring Boot completes the run flow |
| `ApplicationStartup` / Actuator startup | Collects startup step metrics when configured | Analyzing startup cost, not a replacement for all callbacks |

For example, if the need is to **load a new PropertySource**, `EnvironmentPostProcessor` usually states the intent more clearly than `SpringApplicationRunListener`. If the need is to **run a data-verification query after beans are built**, `ApplicationRunner` is usually the right phase. If you need to **catch an exception during `run` even before the context is formed**, a run listener's `failed(...)` has an advantage.

### 8.1. Do not confuse addListeners with a run listener

The API:

```java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addListeners(new SomeApplicationListener());
application.run(args);
```

is for `org.springframework.context.ApplicationListener`. It is not a mechanism to register an arbitrary `SpringApplicationRunListener` via an overload. For custom run listeners, use `META-INF/spring.factories` per the `SpringFactoriesLoader` contract.

### 8.2. Do not confuse contextPrepared with contextLoaded

These two callbacks are very close, yet belong to **different stages**:

```text
Create context
  -> apply relevant initializers
  -> contextPrepared
  -> load sources/bean definitions
  -> contextLoaded
  -> refresh
```

If your task needs instantiated beans, **both milestones are still too early**. Choose a runner, an appropriate event, or bean lifecycle callbacks instead of forcing `getBean(...)` to run here.

### 8.3. Do not confuse started with ready

`started(...)` arrives **before** runners, and `ready(...)` arrives **after** runners. If a runner fails:

```text
started -> runner -> exception -> failed
                    |
                    +-- no ready
```

Thus, a startup observability dashboard should not count `started` as "application ready" when the system needs all runners to complete. Conversely, `ready` is the end of Spring Boot's `run`, not a replacement for long-term health/readiness probes.

## 9. Startup timing: using Duration meaningfully

The final two callbacks on the success path accept `Duration timeTaken`:

```java
@Override
public void started(
        ConfigurableApplicationContext context, Duration timeTaken) {
    if (timeTaken != null) {
        System.out.println("Startup ms=" + timeTaken.toMillis());
    }
}

@Override
public void ready(
        ConfigurableApplicationContext context, Duration timeTaken) {
    if (timeTaken != null) {
        System.out.println("Ready ms=" + timeTaken.toMillis());
    }
}
```

These are **overridden/implemented methods inside the listener**, with the imports shown in section 3.

Explanation:

- `started` marks the point after context refresh succeeds, before runners.
- `ready` marks the point after runners and right as `run` completes.
- The difference between the two measurements can reflect runner work and other steps between the two milestones, though it should not be treated as a pure measurement of a single runner if multiple hooks or tasks execute in between.
- `Duration` represents elapsed time, not a wall-clock date/time. Use `Instant` or an appropriate clock if you need explicit timestamps.
- If you need detailed profiling across hundreds of bean initialization steps, use the `ApplicationStartup`, `BufferingApplicationStartup`, or Actuator startup endpoint infrastructure when configured. A run listener only gives coarse milestones.

When collecting metrics in production, avoid blocking the bootstrap thread to send network requests inside a callback. It is better to record lightweight data and hand it off to the telemetry pipeline once active.

## 10. BootstrapContext: why is there a context before BeanFactory exists?

In the first two callbacks, instead of `ApplicationContext`, the interface provides `ConfigurableBootstrapContext`. This object supports preparing **data or resources needed from a very early stage** and passing them across bootstrap steps using Boot's supported mechanism.

Distinguish them:

| `ConfigurableBootstrapContext` | `ApplicationContext` |
| --- | --- |
| Available very early during startup | Created only after `Environment` is prepared |
| Intended for bootstrap components with their own lifecycle | Intended for the bean container and application |
| Not used like Spring IoC's `getBean(...)` | Provides `getBean(...)`, injection, and lifecycle |
| Has bootstrap instance registration/lookup mechanism | Has BeanFactory, bean definitions, and scopes |
| Can be closed/finalized per the bootstrap flow | Lives for the application context lifecycle |

When a resource genuinely must be shared between environment preparation and context construction, you can examine bootstrap registry/context APIs such as `register(...)` or `addCloseListener(...)` per the official JavaDoc of the version in use. However, using them requires understanding creation/closing order and resource ownership. **Do not turn the bootstrap context into a dumping ground for business singletons**.

If you only need to read a few settings in `environmentPrepared`, using `ConfigurableEnvironment` is enough. Do not build complex bootstrap infrastructure when there is no need.

## 11. How to verify SpringFactoriesLoader found the listener

If the `TraceRunListener` code is valid yet no `RUN LISTENER` lines appear, check from the root:

1. The file must be at the exact path `src/main/resources/META-INF/spring.factories`, with exact name and matching case.
2. The key must be `org.springframework.boot.SpringApplicationRunListener`. Do not accidentally write `org.springframework.context.ApplicationListener`.
3. The value must be the **fully qualified class name** (`demo.startup.TraceRunListener`), matching the declared package.
4. The class must be `public` and have a **public `(SpringApplication, String[])` constructor**, not only a default constructor.
5. The class must be on the actual application's **runtime classpath**.
6. Check whether an old, un-repackaged JAR is being executed.
7. If integrating from a library, confirm the library's `META-INF/spring.factories` file is preserved in the artifact or classpath rather than dropped during repackaging.
8. If loading fails, read the exception from `SpringFactoriesLoader` and the root stack trace; do not "fix" it by adding `@Component`.

Inspect the resource inside an executable JAR using an illustrative command:

```bash
jar tf build/libs/app.jar
```

Look for in the output:

```text
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/demo/startup/TraceRunListener.class
```

For an actual JAR filename, replace `app.jar` with your built artifact. The two entries above are **expected examples** when the listener lives directly in application sources; if the listener is supplied by a dependency JAR, it will reside inside that dependency under `BOOT-INF/lib/...` of the executable Boot JAR.

When using Gradle `bootRun`, resources are loaded from runtime classpath directories/classes rather than necessarily requiring `BOOT-INF/classes`.

## 12. Errors in callbacks and the risk of breaking startup

`SpringApplicationRunListener` runs directly on the Boot-orchestrated startup thread. This gives strong intervention power, so errors in callbacks can break startup.

**Example of what not to do:**

```java
@Override
public void starting(ConfigurableBootstrapContext bootstrapContext) {
    // Long synchronous DB or HTTP call when Environment
    // and ApplicationContext are not yet fully prepared.
    callRemoteService();
}
```

This is an **illustrative counterexample**, not a standalone compilable snippet: `callRemoteService()` is intentionally an undefined method. The lesson is to avoid network or bean dependencies in hooks that are too early.

When extending infrastructure:

- Ensure callbacks are **fast and predictable**. Do not block startup because an external observability service is temporarily unreachable.
- Do not hold `ApplicationContext` references in long-lived static fields, which easily causes classloader and resource leaks in tests or reload environments.
- Do not assume there is only one `run` call in the entire JVM: tests, context hierarchies, or other bootstrap setups may create multiple instances.
- Do not store unsynchronized mutable shared state across multiple instances or contexts.
- Do not print passwords, API tokens, URLs containing credentials, or full command-line arguments to logs.
- `failed(...)` must be safe when context is `null`. Do not try to call `context.getBean(...)` to log errors.
- If a callback throws an exception, Boot's error handling may invoke additional failure callbacks; avoid throwing new errors inside `failed(...)`.
- When adding multiple run listeners, control ordering via Spring Boot's appropriate ordering mechanism when needed; **do not rely on accidental class listing order on the classpath**.

In particular, avoid using listeners to "patch" problems that have dedicated APIs. Bean configuration normally fits `@Configuration`; loading properties fits `EnvironmentPostProcessor`; post-ready logic fits `ApplicationRunner` or events.

## 13. Comparing three moments commonly needed in applications

Suppose an application needs three tasks: reading an environment label to name logs, registering beans, and initializing data.

| Need | Suggested timing | Reason |
| --- | --- | --- |
| Read profile/config info to attach startup diagnostic labels | `environmentPrepared` or dedicated extension point | Environment already exists; beans do not need to be created yet |
| Add/modify bean definitions before singletons are instantiated | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | These are the infrastructure APIs dedicated to bean definitions |
| Run data initialization using a repository bean | `ApplicationRunner` or `CommandLineRunner` | Context has refreshed, regular beans are ready |
| Measure total time to ready | `ready` with `Duration` | After runners and at the end of the startup flow |
| Observe exceptions even if context creation did not finish | `failed` | Exception is provided and nullable context is allowed |
| Check service health during operation | Health/readiness indicator | Runtime data, not just a one-time startup state |

From this table, you should not use `started` to run a long migration: if it fails, the startup flow is stalled or fails in a poorly suited hook; using dedicated schema/migration tooling is much clearer. Likewise, do not put business processing into `ready` merely because it is the last callback.

## 14. Verifying alongside events and runners: practice method

### Practice A: predict callback order

Run the example in section 6 and answer **before looking at the output**:

- Which listener appears first: `contextLoaded` or `started`?
- Does `ApplicationRunner` run before or after `ready`?
- If the `contextPrepared` callback has run, is a repository bean guaranteed to have been created?
- Why can `starting` not reliably read `spring.application.name` from the loaded environment?
- When running with `--demo.fail`, which callbacks still appear and which disappear?

Then compare the output of lines printed by `TraceRunListener` and `ApplicationRunner`. Distinguish Spring Boot's logs/banners from the lines produced by the example code.

### Practice B: changing the application type

If you replace `spring.main.web-application-type=none` with a valid web app having the web starter and server factory dependencies, observe `contextPrepared` printing a different context name, while **the callback order retains the same meaning**. For Spring Boot 3.3's default Servlet web app, the name may be `AnnotationConfigServletWebServerApplicationContext`. For a matching reactive web app, it may be `AnnotationConfigReactiveWebServerApplicationContext`.

Do not force `SERVLET` without Servlet server infrastructure and then treat a missing-bean error as "broken" run listener behavior. The listener still reflects Boot's process, while creating a web context requires the right dependencies.

### Practice C: early error vs. error inside a runner

In a test environment, compare two errors:

1. Error from a runner via `--demo.fail`: context was refreshed; `started` appears; `failed` appears; `ready` does not appear.
2. Initialization error before context completion: depending on where it fails, `contextPrepared` or `contextLoaded` may not appear; `failed` must handle `context == null` as well.

Do not try to provoke failures by breaking production dependencies or configuration; only experiment inside an isolated demo application.

### Practice D: comparing ApplicationListener

Create an `ApplicationListener<ApplicationReadyEvent>` registered before `run` or via `spring.factories` under the exact key `org.springframework.context.ApplicationListener`. Compare when `ApplicationReadyEvent` is received against the `ready` callback of `SpringApplicationRunListener`.

Answer: which one is a direct callback on the run listener interface, and which one is an event published by `EventPublishingRunListener`? Why is there no need to define both if the goal is only to log "ready"?

## 15. Troubleshooting and diagnostics table

| Symptom | Possible cause | How to check / fix |
| --- | --- | --- |
| No callbacks run at all | `spring.factories` not packaged, wrong key, or wrong class name | Check runtime classpath, JAR entries, and full key |
| Startup fails to instantiate listener | Missing `public (SpringApplication, String[])` constructor or non-public class | Fix constructor signature to match Boot 3.3 |
| IDE complains `@Override` is invalid | Used Spring Boot 1.x/2.x signature instead of 3.3 | Compare against 3.3 `SpringApplicationRunListener` JavaDoc |
| `getBean(...)` fails inside `contextLoaded` | Context not refreshed yet, beans not created | Move bean-dependent logic to a runner or appropriate lifecycle hook |
| `getProperty(...)` returns unexpected value in `starting` | Environment is not fully prepared yet | Read in `environmentPrepared` or an appropriate extension point |
| `started` appears but `ready` does not | Runner or final startup step threw an error | Check exception and `failed`; do not report READY |
| `failed` itself throws `NullPointerException` | Context not created yet while code dereferences it | Check `context != null` before using it |
| Two places both announce startup | Logging in both run listener and `ApplicationListener`/Boot logs | Pick one primary metric/log source, avoid duplicate logging |
| Slow callback delays startup | Synchronous HTTP/DB calls inside hook | Move to an appropriate mechanism, measure cost, and bound blocking |
| Tests log startup multiple times | Multiple contexts or multiple `run` invocations | Understand per-run instance scope; inspect test lifecycle |
| Failed to receive ultra-early event with `@EventListener` bean | Bean does not exist yet when early event fires | Register listener early via API or `spring.factories` |
| `ready` observed yet endpoint still unresponsive | Runtime, routing, network, or downstream health issue | Check readiness/health and network port independently |

A practical troubleshooting workflow:

1. Check the Spring Boot dependency and **same-version JavaDoc** to confirm signatures.
2. Verify `META-INF/spring.factories` is present on the runtime classpath.
3. Verify class visibility and the public constructor; read the root exception if the loader fails.
4. Log a safe milestone in `starting` and `environmentPrepared` without printing secrets.
5. Observe the last callback that ran; combine with the stack trace to pinpoint the failing phase.
6. If failure occurred after `started`, inspect runners and near-end hooks before blaming refresh.
7. Never downgrade startup failures to "minor warnings" when the application actually fails operational prerequisites.

## 16. Key principles to remember

1. **`SpringApplicationRunListener` is a hook for a single `SpringApplication.run`**, loaded via `SpringFactoriesLoader` from `META-INF/spring.factories`.
2. **The required constructor is `public (SpringApplication, String[])`**; do not expect component scanning or BeanFactory injection to instantiate this listener.
3. **Success sequence:** `starting → environmentPrepared → contextPrepared → contextLoaded → started → runners → ready`; on error, execution enters `failed`.
4. **`started` differs from `ready`**: started precedes runners, ready follows runners.
5. **`contextPrepared` and `contextLoaded` are both pre-refresh**; do not invoke business beans there.
6. **`failed` must tolerate a null context** when errors happen very early.
7. **`EventPublishingRunListener` is the bridge to `Application*Event`**; `ApplicationListener` is a different API.
8. Use this listener for infrastructure needing startup milestones. For environment config, bean definitions, and post-refresh tasks, prefer their dedicated extension points.
9. When analyzing startup, cross-check callbacks, events, runners, and health/readiness. Each tells **a different kind of truth** about application state.

### Official documentation

- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html): signatures, invocation timing, and constructor requirements.
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `run` lifecycle, listener and initializer configuration.
- [Spring Boot 3.3 — EventPublishingRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/EventPublishingRunListener.html): bridge between callbacks and application events.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): event sequence during startup.
