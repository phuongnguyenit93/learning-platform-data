# ApplicationPreparedEvent in the Spring Boot Startup Lifecycle

## 1. What Is ApplicationPreparedEvent?

`ApplicationPreparedEvent` is a **Spring Boot application event** in package `org.springframework.boot.context.event`. The event is published during `SpringApplication.run(...)` once the `ApplicationContext` has been created, the configuration `Environment` is usable, and initial bean definition sources have been loaded, **but before the context runs `refresh()`**.

Key message to remember: **prepared is not synonymous with refreshed, started, or ready**. This is the midpoint between building the application structure and fully instantiating beans.

In terms of Java type, `ApplicationPreparedEvent extends SpringApplicationEvent`. The event object provides:

- `getApplicationContext()`: the `ConfigurableApplicationContext` about to be refreshed.
- `getSpringApplication()`: the `SpringApplication` that is starting up.
- `getArgs()`: the program arguments array passed when calling `run(...)`.
- `getTimestamp()`: the time the event was created according to the `ApplicationEvent` mechanism.

The event is published automatically by Spring Boot; applications normally **should not manually call** `publishEvent(new ApplicationPreparedEvent(...))`. It is a startup milestone of `SpringApplication`, not a custom domain event defined by a service.

## 2. Exact Timing in the Spring Boot Event Sequence

In a typical Spring Boot 3.5 startup flow, the notable event sequence is:

```text
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |      No complete Environment or ApplicationContext yet
    |
    +-- ApplicationEnvironmentPreparedEvent
    |      Environment prepared; context not yet created
    |
    +-- ApplicationContextInitializedEvent
    |      Context created, initializers have run;
    |      application bean definition sources not yet loaded
    |
    +-- load configuration sources / initial bean definitions
    |
    +-- ApplicationPreparedEvent       <== THIS TOPIC
    |      Context available, Environment available;
    |      not yet refreshed, beans not guaranteed to be initialized
    |
    +-- refresh ApplicationContext
    |      BeanFactoryPostProcessors, configuration, singleton creation...
    |      ContextRefreshedEvent and related initialization events
    |
    +-- ApplicationStartedEvent
    |      Context refreshed; runners not yet invoked
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |      Runners completed; application reaches ready milestone
    |
    +-- SpringApplication.run(...) returns context
```

Other events may occur between milestones, such as `WebServerInitializedEvent` in web applications, and `AvailabilityChangeEvent`s marking liveness/readiness. The diagram depicts only relevant milestones; do not treat it as a complete list of every internal callback.

Summary table:

| Event | Context Exists? | Refreshed? | Meaning |
| --- | --- | --- | --- |
| `ApplicationEnvironmentPreparedEvent` | No | No | Environment available to inspect/modify |
| `ApplicationContextInitializedEvent` | Yes | No | Initializers have run; bean sources not yet loaded |
| **`ApplicationPreparedEvent`** | **Yes** | **No** | Initial configuration sources/bean definitions loaded |
| `ApplicationStartedEvent` | Yes | Yes | Refresh done, runners not yet executed |
| `ApplicationReadyEvent` | Yes | Yes | Runners executed, application ready milestone reached |

One easily misunderstood point: at the `ApplicationPreparedEvent` stage, some **bean definitions** exist, yet you cannot infer that **all singletons, `@Bean` method beans, or auto-configurations are ready**. Much of `@Configuration` processing, `BeanFactoryPostProcessor` execution, and singleton creation belongs to the upcoming `refresh()` process itself. Do not take the name "Prepared" as a promise that it is safe to retrieve every bean for use.

## 3. What State Is the Context In When Receiving the Event?

Assuming the listener receives the event during a normal startup:

- `event.getApplicationContext()` returns the actual application context, not `null`.
- `context.getEnvironment()` is available to read configurations such as `demo.mode`, property sources, or active profiles.
- Initial configuration/bean definition sources have been loaded into the context by Boot; you can **inspect metadata** when truly needed.
- `context.isActive()` for standard `AbstractApplicationContext` implementations is still `false` before the refresh step starts.
- Calling `context.getBean(MyService.class)` cannot be assumed to succeed. The bean factory may not have gone through post-processing, initialized post-processor beans, or created singletons yet.
- Web server, application runners, post-refresh initialization tasks, traffic-handling infrastructure, and readiness **are not yet considered ready**.

Comparing three concepts:

**Bean definitions loaded:** Spring knows about certain source definitions of beans or configuration classes to be used.

**Beans initialized:** Spring has actually instantiated objects, resolved dependencies, and executed appropriate initialization callbacks.

**Application ready:** The context has refreshed and related startup steps, including runners, have finished. This state aligns with `ApplicationReadyEvent`, not `ApplicationPreparedEvent`.

Therefore, `ApplicationPreparedEvent` is very useful for **observing bootstrap state**, not as a signal allowing invocation of all application business logic.

## 4. Registering the Listener Early Enough

### Recommended Approach: SpringApplication.addListeners Before run()

Instead of relying solely on `@EventListener` on a Spring bean, register the listener before Boot begins starting up:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(
        (ApplicationListener<ApplicationPreparedEvent>) event -> {
            var context = event.getApplicationContext();
            System.out.println(context.getEnvironment().getProperty("app.mode"));
        });
application.run(args);
```

This is an **excerpt**, not a full program; a runnable example is in section 5. The rule is that `addListeners(...)` must be called **before** `run(...)`. If called after the application has already finished running, you will miss the prepared event for that startup run.

If using the builder, you can register via `SpringApplicationBuilder.listeners(...)` before calling `run(...)`.

### Registering via META-INF/spring.factories

When building a library that needs to automatically receive events across multiple applications, Spring Boot supports declaring listeners under key `org.springframework.context.ApplicationListener` in `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.context.ApplicationListener=com.example.boot.PreparedAuditListener
```

Class `com.example.boot.PreparedAuditListener` must be packaged on the classpath, have a suitable constructor for Spring to instantiate, and implement `ApplicationListener<ApplicationPreparedEvent>`. This is only an illustrative configuration: the class name must be replaced with your project's actual class.

### Should You Use @Bean or @EventListener?

`@Bean` and `@EventListener` are a good pattern for events occurring **after the bean factory has been refreshed**. However, `ApplicationPreparedEvent` occurs **before refresh**, so a listener existing solely as a regular bean may **not be discovered or instantiated in time**. To receive this event reliably, prefer a listener registered directly with `SpringApplication` or `spring.factories`.

In particular, do not try to call `getBean()` inside a prepared listener just to trigger another listener: it can cause beans to be instantiated prematurely, bypassing post-processing that Spring must perform during `refresh()`.

## 5. Runnable Maven + Java 17 Example

This example uses Spring Boot **3.5.6**, JDK 17+, and runs **without a web server** to focus on startup events. A listener is registered before `run()` and observes three milestones: Prepared, Started, and Ready. An `ApplicationRunner` prints one line between Started and Ready.

### Structure

```text
application-prepared-demo/
├── pom.xml
└── src/main/java/demo/PreparedEventDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>application-prepared-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

File `src/main/java/demo/PreparedEventDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PreparedEventDemo {

    @Bean
    ApplicationRunner sampleRunner() {
        return args -> System.out.println("runner: completed");
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(PreparedEventDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
                "demo.mode", "training",
                "logging.level.root", "OFF"));

        // Listener must be registered before application.run().
        application.addListeners(
                (ApplicationListener<ApplicationPreparedEvent>) event -> {
                    var context = event.getApplicationContext();
                    System.out.println("prepared: active=" + context.isActive());
                    System.out.println("prepared: mode=" +
                            context.getEnvironment().getProperty("demo.mode"));
                });

        application.addListeners(
                (ApplicationListener<ApplicationStartedEvent>) event -> {
                    System.out.println("started: active=" +
                            event.getApplicationContext().isActive());
                });

        application.addListeners(
                (ApplicationListener<ApplicationReadyEvent>) event -> {
                    System.out.println("ready: active=" +
                            event.getApplicationContext().isActive());
                });

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("main: active=" + context.isActive());
        }
    }
}
```

Run inside the project directory:

```bash
mvn -q spring-boot:run
```

With Spring Boot 3.5.6 and no configuration-overriding arguments passed, the lines printed by the program itself are:

```text
prepared: active=false
prepared: mode=training
started: active=true
runner: completed
ready: active=true
main: active=true
```

The output above omits ancillary information from Maven or the launch environment. The example disables the banner and reduces Spring Boot logging to make the event milestones easy to see.

**Line-by-line explanation:**

1. When `ApplicationPreparedEvent` is dispatched, the context already exists but has not refreshed yet, so `active=false`. `Environment` already contains default property `demo.mode=training`.
2. After refresh completes, Boot publishes `ApplicationStartedEvent`. The context is now active, yielding `started: active=true`.
3. Boot invokes the `ApplicationRunner` created during refresh. It prints `runner: completed`.
4. After runners finish, Boot publishes `ApplicationReadyEvent`. The listener prints `ready: active=true`.
5. `SpringApplication.run(...)` returns the context, and code in `main` prints `main: active=true`. At the end of the `try` block, the context is closed.

Note: The main file uses `@SpringBootApplication` so Spring Boot finds the configuration and `@Bean ApplicationRunner`. The prepared listener is **not** declared as a `@Bean`; it is attached to `SpringApplication` before running, guaranteeing it is present when the event occurs.

If run with an argument such as `--demo.mode=production`, the property value may be overridden and the `prepared: mode=...` line will differ. This is the intended behavior of the configuration system, not an event ordering bug.

## 6. Reading Properties of ApplicationPreparedEvent

Assuming an `ApplicationPreparedEvent event` has been received, useful accessors are:

| API | Return Type / Meaning | When to Use |
| --- | --- | --- |
| `event.getApplicationContext()` | `ConfigurableApplicationContext` | Inspecting the context and environment |
| `event.getSpringApplication()` | `SpringApplication` | Identifying the application starting up when multiple SpringApplications exist |
| `event.getArgs()` | `String[]` | Knowing which startup arguments were passed |
| `event.getTimestamp()` | `long` | Recording the time the event was created |

Small illustrative snippet, **not a standalone program**:

```java
ApplicationPreparedEvent event = /* event received by listener */;
ConfigurableApplicationContext context = event.getApplicationContext();
String mode = context.getEnvironment().getProperty("app.mode", "default");
int startupArgumentCount = event.getArgs().length;
```

In real code, do not write placeholder lines to create the event: use the `event` parameter of `ApplicationListener` as shown in section 5. Note that `getArgs()` represents arguments passed to `SpringApplication.run`, not the list of all final properties after merging every configuration source.

## 7. Distinguishing ApplicationPreparedEvent from Other Hooks

| Purpose | More Suitable Mechanism | Why |
| --- | --- | --- |
| Read Environment and context state **right before refresh** | **`ApplicationPreparedEvent`** | Exact milestone covered in this topic |
| Modify Environment very early, before context is built | `EnvironmentPostProcessor` / proper Environment config | Works prior to loading bean sources |
| Customize context right after creation, before loading bean sources | `ApplicationContextInitializer` | Dedicated hook for this phase |
| Register/modify bean definitions in the official refresh sequence | `BeanDefinitionRegistryPostProcessor` or `BeanFactoryPostProcessor` | Managed by Spring along the post-processing lifecycle |
| Use fully initialized beans once context refresh completes | `ContextRefreshedEvent`, `ApplicationStartedEvent` | Bean factory has refreshed |
| Run startup work needing injection/service beans | `ApplicationRunner` or `CommandLineRunner` | Invoked after refresh |
| Know when the application is ready to accept traffic | `ApplicationReadyEvent` / readiness state | Proper ready semantics |
| Catch errors occurring while Spring Boot is starting up | `ApplicationFailedEvent` | May contain the exception causing failure |

**Do not use the prepared event to call business services, open connections requiring fully configured beans, query data via repositories, or run a long job.** Those components may not have been created yet; if the listener throws an error, startup can fail.

### ApplicationPreparedEvent Is Not ContextRefreshedEvent

`ApplicationPreparedEvent` belongs to Spring Boot and is published **before** refresh. `ContextRefreshedEvent` belongs to Spring Framework and occurs once refresh is complete. Spring Boot may publish `ApplicationPreparedEvent` even if the subsequent refresh fails and the application **never** reaches `ApplicationStartedEvent` or `ApplicationReadyEvent`.

### Nor Is It ApplicationContextInitializedEvent

`ApplicationContextInitializedEvent` occurs after the context and `ApplicationContextInitializer`s are prepared, **before** application bean definition sources are loaded. `ApplicationPreparedEvent` occurs **after** they are loaded (yet still before refresh). The two events bracket the configuration source loading step.

## 8. Common Mistakes and Important Limitations

### 8.1. Registering the Listener Too Late

If you use `@EventListener` in a bean only created during refresh, it may miss `ApplicationPreparedEvent` because that milestone has already passed. Similarly, calling `addListeners(...)` after `SpringApplication.run(...)` returns is too late for the completed startup run.

**Solution:** register via `SpringApplication.addListeners(...)` before `run(...)`, `SpringApplicationBuilder.listeners(...)`, or `META-INF/spring.factories`.

### 8.2. Inferring That All Beans Are Operational

"Bean definitions loaded" **does not mean** "beans created." `@Bean` methods, additional component scanning, auto-configuration, and singleton creation are mostly processed during refresh. Forcing `getBean(...)` at the prepared milestone can instantiate objects at the wrong time or cause hard-to-diagnose errors.

**Solution:** if you need dependency injection to run business logic, move to `ApplicationRunner` or a post-refresh event.

### 8.3. Processing Too Long or Throwing Exceptions

Startup listeners are dispatched synchronously along the normal `SpringApplication` path, so slow network I/O inside a prepared listener increases startup time. If a listener throws an unhandled exception, `SpringApplication.run(...)` may fail and Boot publishes `ApplicationFailedEvent` during error handling.

**Solution:** keep listeners lightweight with moderate logging/metering; do not perform lengthy business tasks. When catching errors, clearly separate errors that must abort startup from errors that can be logged and continued.

### 8.4. Using Prepared to Signal Readiness

`ApplicationPreparedEvent` does not mean the web server has opened its port, all runners have executed, or the application can safely accept traffic. A monitoring system marking ready upon this event reports readiness at the wrong time.

**Solution:** observe `ApplicationReadyEvent` or readiness probes according to deployment policy.

### 8.5. Multiple ApplicationContexts / SpringApplications

When using a parent-child context hierarchy or multiple `SpringApplication`s, a listener can observe events from more than one context; events can also propagate to an ancestor context via Spring's publishing mechanism. Do not assume there is only one event instance in the entire process.

**Solution:** when needed, identify the source via `event.getApplicationContext()` or `event.getSpringApplication()`, attach a per-startup correlation ID, and filter according to the listener's target.

### 8.6. Confusing with @TransactionalEventListener

The prepared event happens before the application is ready and is usually not bound to an active business transaction. Do not use `@TransactionalEventListener` to wait for a nonexistent startup transaction commit. These are two different event concepts.

## 9. Rules of Application

You can use `ApplicationPreparedEvent` when you need to:

1. Record a bootstrap observation milestone, measuring duration from environment-prepared to pre-refresh.
2. Verify that certain properties/profiles are ready at context preparation time.
3. Detect which application or context is entering the refresh stage in a multi-context environment.
4. Perform very lightweight metadata inspection that does not require initialized beans and does not intervene deeply in the container.

Do not use it when you need to:

1. Execute SQL through an injected repository.
2. Send emails, register consumers, run business jobs, or connect to systems depending on complete beans.
3. Assert that the service is ready to receive traffic.
4. Arbitrarily modify bean definitions, bypassing lifecycle post-processors.

## 10. Self-Check Questions

1. **Does ApplicationPreparedEvent run before or after refresh?** — Before refresh, after loading initial bean definition sources.
2. **Is there an ApplicationContext in the event?** — Yes; `getApplicationContext()` returns `ConfigurableApplicationContext`.
3. **Is the Environment usable yet?** — Yes, to read configuration state.
4. **Should you retrieve every Spring bean via context.getBean() at this point?** — No. The context has not refreshed and many beans have not been created yet.
5. **Why might @Bean/@EventListener miss the prepared event?** — The listener bean may be instantiated after the event was already published.
6. **Where should the listener be registered?** — `SpringApplication.addListeners(...)` before `run(...)` or an appropriate `spring.factories`.
7. **How does it differ from ApplicationStartedEvent?** — `ApplicationStartedEvent` occurs after refresh, before runners.
8. **How does it differ from ApplicationReadyEvent?** — `ApplicationReadyEvent` occurs after runners have executed and the application reaches the ready milestone.
9. **If refresh fails after prepared, is ready guaranteed to appear?** — No; startup may fail and `ApplicationFailedEvent` is published.
10. **Why not use the prepared event as a health-ready signal?** — Because the server and application have not finished starting up.

## References

- [Spring Boot 3.5 — SpringApplication / Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — ApplicationPreparedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html)
- [Spring Boot 3.5 — Customizing the Environment or ApplicationContext](https://docs.spring.io/spring-boot/3.5/how-to/application.html)
- [Spring Boot 3.5 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.5 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
