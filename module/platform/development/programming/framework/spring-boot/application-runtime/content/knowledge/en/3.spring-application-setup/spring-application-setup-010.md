# Configuring the Shutdown Hook and ApplicationContextFactory in SpringApplication

**Topic:** Spring Boot Application Runtime → SpringApplication Setup. This lesson focuses on two application-level configuration points: how Spring Boot registers the mechanism to close `ApplicationContext` when the JVM exits, and how to choose the strategy for creating `ApplicationContext` at startup. The examples below use **Java 17+ and Spring Boot 3.3.x**; when using another version, verify the API and shutdown defaults against that version's documentation.

## 1. Learning Objectives

After this lesson, you should be able to:

1. State clearly where `SpringApplication` creates, configures, refreshes, and closes `ApplicationContext` in the lifecycle.
2. Explain `setRegisterShutdownHook(true/false)`, its default value, and when you must call `close()` manually.
3. Distinguish between a **JVM shutdown hook** and **web server graceful shutdown**, bean destruction callbacks, and OS process termination.
4. Explain `ApplicationContextFactory`, `WebApplicationType`, and the three common context types: servlet, reactive, and non-web.
5. Configure a factory via `setApplicationContextFactory(...)`, verify the actual context class created, and recognize mismatches that cause startup failures.
6. Test application shutdown scenarios and record evidence from logs, HTTP responses, and resource-cleanup callbacks.

These options serve **two different moments**:

| Configuration | When Does It Happen? | What Does It Control? | Typical Value |
|---|---|---|---|
| `setApplicationContextFactory(...)` | Before refreshing the context during startup | Which `ConfigurableApplicationContext` object is created | Keep the default factory unless there is a special requirement |
| `setRegisterShutdownHook(true/false)` | While the application registers its lifecycle with the JVM | Whether to register a hook to close the context on JVM shutdown | Keep `true` if the JVM owns the application lifecycle |
| `server.shutdown` | When closing a web app's context | Whether the web server stops gracefully or immediately | Choose per Boot version and operational requirements |
| `@PreDestroy` / `DisposableBean` | When Spring destroys beans while closing the context | How resources managed by beans are cleaned up | Implement short, reliable cleanup callbacks |

Do not use one setting to do another's job: selecting the right context **does not** determine how the JVM shuts down; a shutdown hook **cannot** fix beans that fail to close their resources.

## 2. Lifecycle and Placement of the Two Configuration Points

~~~text
main(String[] args)
    |
    v
new SpringApplication(Source.class)
    |  setApplicationContextFactory(factory)
    |  setRegisterShutdownHook(true/false)
    v
SpringApplication.run(args)
    |
    +-- infer or receive WebApplicationType (SERVLET / REACTIVE / NONE)
    +-- prepare Environment and configuration sources
    +-- invoke factory to create an UNREFRESHED ConfigurableApplicationContext
    +-- configure context, register bean sources, refresh context
    +-- start embedded web server if it is a web application
    +-- run ApplicationRunner / CommandLineRunner
    +-- publish ApplicationReadyEvent upon successful startup
    |
    v
Application active: receive HTTP requests / process jobs
    |
    +-- normal JVM shutdown, if hook registered --------+
    +-- or application calls context.close() -----------+
                                                        |
                                                        v
                                               ApplicationContext.close()
                                                        |
                                  +---------------------+-------------------+
                                  |                                         |
                        ContextClosedEvent                         stop SmartLifecycle,
                        and listeners                              destroy singleton beans
                                                                          |
                                                                    @PreDestroy,
                                                                    DisposableBean,
                                                                    destroy method
~~~

This is a conceptual diagram; real execution has many additional startup and shutdown events. `ApplicationContextFactory` creates a context that is **not yet fully configured/refreshed**. `SpringApplication` proceeds to prepare the environment, bean sources, refresh, and integration mechanisms. The factory must not call `refresh()` itself or close the context it just created.

When `close()` begins, Spring publishes `ContextClosedEvent`, stops lifecycle components, and runs eligible destroy callbacks. Ordering across callbacks of multiple beans, log threads, or asynchronous operations may vary; avoid building business logic that depends on an arbitrary log order.

## 3. Default Values and What Is Actually Guaranteed

Per the Spring Boot 3.3 API, `SpringApplication#setRegisterShutdownHook(boolean)` defaults to `true`. Therefore, a typical Boot application already registers a hook requesting context closure on JVM shutdown. When the JVM receives a termination signal handled normally, the hook helps Spring execute resource-cleanup callbacks.

However, **the hook is not an insurance policy for every kind of process termination**. `SIGKILL` (such as `kill -9` on Linux), forced termination preventing the JVM from running its shutdown sequence, hardware failures, or certain crashes do not guarantee the hook runs. `System.exit(...)` triggers the JVM shutdown sequence; `Runtime.halt(...)` bypasses shutdown hooks. How an IDE, container, or operating system delivers signals also affects whether the hook gets a chance to run.

Regarding context type, Boot normally infers it from the classpath and `WebApplicationType`:

| WebApplicationType | Default Context in Boot 3.3 | Typical Use Case |
|---|---|---|
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Spring MVC with an embedded servlet server |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | WebFlux reactive server |
| `NONE` | `AnnotationConfigApplicationContext` | CLI, batch worker, tasks without a web server |

When **both Spring MVC and WebFlux are on the classpath**, Boot typically selects the servlet type. You can explicitly call `setWebApplicationType(WebApplicationType.NONE)` for a CLI program, but do not confuse that with replacing the factory. `WebApplicationType` states which model the application belongs to; the factory decides which **concrete context instance** compatible with that model gets created.

## 4. Runnable Sample Application: Observing Context and Shutdown

### 4.1. Creating the Project

Create a Maven project named `lifecycle-lab` on Spring Initializr, with group `com.example`, package `com.example.lifecyclelab`, Java 17, Spring Boot 3.3.x, and the **Spring Web** dependency. Initializr generates the Maven Wrapper; keep the `pom.xml` and starter versions generated by Initializr. No external Tomcat installation is needed.

Create these files:

~~~text
lifecycle-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/lifecyclelab/
    LifecycleLabApplication.java
    ProbeController.java
  src/main/resources/
    application.properties
~~~

### 4.2. Main Class: Configuring Both Shutdown Hook and Factory

File `src/main/java/com/example/lifecyclelab/LifecycleLabApplication.java`:

~~~java
package com.example.lifecyclelab;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.AnnotationConfigServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                LifecycleLabApplication.class);

        // Already true by default; set explicitly for easier observation.
        app.setRegisterShutdownHook(true);

        // Lab uses Spring MVC: select a compatible servlet context.
        app.setApplicationContextFactory(
                ApplicationContextFactory.ofContextClass(
                        AnnotationConfigServletWebServerApplicationContext.class));

        ConfigurableApplicationContext context = app.run(args);
        System.out.println("LAB_CONTEXT_TYPE="
                + context.getClass().getSimpleName());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_APPLICATION_READY");
    }

    @EventListener(ContextClosedEvent.class)
    public void onClosed() {
        System.out.println("LAB_CONTEXT_CLOSED");
    }

    @Bean
    CleanupProbe cleanupProbe() {
        return new CleanupProbe();
    }

    public static final class CleanupProbe {
        @PreDestroy
        public void cleanup() {
            System.out.println("LAB_PRE_DESTROY");
        }
    }
}
~~~

**Line-by-line key explanations:**

- `new SpringApplication(LifecycleLabApplication.class)` lets you call setters before `run(...)`; the shorthand `SpringApplication.run(Source.class, args)` does not give you an application instance to customize directly.
- `setRegisterShutdownHook(true)` demonstrates explicit configuration. In typical environments this line can be omitted because `true` is the default.
- `ApplicationContextFactory.ofContextClass(...)` creates a factory from an instantiable context class; here, the servlet class is compatible with the Spring Web dependency.
- `app.run(args)` creates/refreshes the context and runs the application. Do not call `context.close()` immediately after `run` in a web server meant to keep serving.
- `ApplicationReadyEvent` and `ContextClosedEvent` emit markers when the application is ready or starts closing; `@PreDestroy` is the resource-cleanup callback of the `CleanupProbe` singleton bean.
- `LAB_CONTEXT_TYPE` is printed **after `run` returns**, so the `LAB_APPLICATION_READY` marker may appear before the context type line; this is expected behavior.

To avoid putting non-ASCII characters into Java source code in environments without unified encoding, log strings and comments in the example use ASCII only; explanations and output notes are written in English.

### 4.3. Endpoint for Evidence That the Application Is Serving

File `src/main/java/com/example/lifecyclelab/ProbeController.java`:

~~~java
package com.example.lifecyclelab;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    @GetMapping("/probe")
    public Map<String, String> probe() {
        return Map.of("status", "running");
    }
}
~~~

When the context is a servlet web context and the embedded server is listening on its port, the `GET /probe` endpoint returns JSON with one key.

### 4.4. Web Shutdown Configuration

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=lifecycle-lab
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

We write `server.shutdown=graceful` explicitly so learners can see the setting. In Spring Boot 3.3, you must set `server.shutdown=graceful` to enable graceful shutdown for supported embedded web servers; the default value does not enable this mode automatically. `spring.lifecycle.timeout-per-shutdown-phase` sets the maximum duration for **one** lifecycle shutdown phase, not a guarantee that the entire process will exit in exactly 20 seconds. This value does not determine whether the JVM registers a shutdown hook.

### 4.5. Running and Comparing Markers

In the `lifecycle-lab` directory, Linux/macOS:

~~~bash
java -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/probe
~~~

If using Windows PowerShell where `curl` is aliased, run `curl.exe -i http://localhost:8080/probe`. With the project running properly, HTTP returns status 200 and a body equivalent to:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"status":"running"}
~~~

In the application console, look for two markers:

~~~text
LAB_APPLICATION_READY
LAB_CONTEXT_TYPE=AnnotationConfigServletWebServerApplicationContext
~~~

Tomcat log lines, timestamps, and PIDs vary by environment. The presence of both markers along with a valid HTTP response proves the factory created a compatible context and startup completed.

Next, press **Ctrl+C** in the terminal running the application (or send a valid termination signal to the JVM process). When the shutdown mechanism has a chance to run, you normally see:

~~~text
LAB_CONTEXT_CLOSED
LAB_PRE_DESTROY
~~~

Server graceful shutdown logs may appear interleaved. When running via the Maven plugin, signals/terminals/IDEs may affect both Maven and the child JVM; to observe more cleanly, run the JAR file as in the next step. **Do not** treat missing markers after a forced process kill as evidence that `@PreDestroy` is broken.

## 5. Running the JAR and Self-Testing Context Closure via Signal

Stop the previous Maven session to free the port, then build:

~~~bash
./mvnw clean package
java -jar target/lifecycle-lab-0.0.1-SNAPSHOT.jar
~~~

On Windows: `./mvnw.cmd clean package`, then run the same `java -jar` command. The example JAR name applies when the project version is `0.0.1-SNAPSHOT`; if configured with another version, use the exact JAR name generated under `target/`.

On Linux/macOS, you can launch the process from a shell and capture logs (do not use this pattern to simulate `SIGKILL`):

~~~bash
java -jar target/lifecycle-lab-0.0.1-SNAPSHOT.jar > app.log 2>&1 &
app_pid=$!
curl -i http://localhost:8080/probe
kill -TERM "$app_pid"
wait "$app_pid"
~~~

If `curl` runs before the application is ready, wait for the `LAB_APPLICATION_READY` log and retry; that is a startup timing issue, not a shutdown hook failure. With `kill -TERM`, the shell may report a non-zero exit status when a process stops due to a signal; inspect the logs to draw conclusions about callbacks. Never kill an unrelated PID or run this against a service serving real users.

After shutdown, verify `app.log` contains `LAB_CONTEXT_CLOSED` and `LAB_PRE_DESTROY`. Once the process has actually stopped and no other server listens on port 8080, requests to `/probe` can no longer connect.

**Distinguishing four pieces of evidence:**

| Observation | What Can Be Concluded | What Cannot Be Concluded Yet |
|---|---|---|
| `LAB_CONTEXT_TYPE=...Servlet...` | The factory returned a servlet context on that run | Any given business HTTP endpoint is correct |
| `LAB_APPLICATION_READY` | Startup reached the ready event milestone | All future requests will succeed |
| `LAB_CONTEXT_CLOSED` | The context entered the closing phase and published the event | All external resources have already been released |
| `LAB_PRE_DESTROY` | Spring invoked the bean's destroy callback | The hook can run even when the process is killed with `SIGKILL` |
| Port 8080 stops accepting connections | No listener remains on that port (assuming other services ruled out) | All background jobs and data were committed |

## 6. When to Disable the Shutdown Hook and Manage close() Yourself

API:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setRegisterShutdownHook(false);
~~~

Setting `false` prevents the application from automatically registering `SpringApplication`'s context-closing hook with the JVM. It does **not** call `close()` automatically, does not make `@PreDestroy` run when `main()` returns, and does not stop the web server from listening on its port. When the hook is disabled, **another lifecycle owner must close the context**.

Appropriate cases include an application embedded inside a host with its own lifecycle, a CLI/batch program requiring deterministic resource scoping, or a test harness that explicitly creates and closes contexts. There is usually no need to disable it in a standalone deployed Spring Boot web service.

### Non-Web Example That Self-Closes After Completing Work

The example below is a **main class for a separate CLI project**; do not place it alongside another `@SpringBootApplication` inside the same component-scan scope. You can use a project with just the basic Spring Boot starter dependency.

File `src/main/java/com/example/clilab/CliLabApplication.java`:

~~~java
package com.example.clilab;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

@SpringBootApplication
public class CliLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(CliLabApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setRegisterShutdownHook(false);
        app.setApplicationContextFactory(
                ApplicationContextFactory.ofContextClass(
                        AnnotationConfigApplicationContext.class));

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("LAB_CLI_WORK_COMPLETE");
        }
        System.out.println("LAB_CLI_CONTEXT_CLOSED");
    }

    @Bean
    Cleanup cleanup() {
        return new Cleanup();
    }

    public static final class Cleanup {
        @PreDestroy
        public void destroy() {
            System.out.println("LAB_CLI_PRE_DESTROY");
        }
    }
}
~~~

Expected meaningful output:

~~~text
LAB_CLI_WORK_COMPLETE
LAB_CLI_PRE_DESTROY
LAB_CLI_CONTEXT_CLOSED
~~~

`LAB_CLI_PRE_DESTROY` appears upon exiting the `try-with-resources` block because `ConfigurableApplicationContext` supports `close()`. In this example, the callback is **triggered by an explicit close**, not by a shutdown hook. Do not wrap `run()` of a web server in `try-with-resources` when you want the application to keep serving after `main()` returns, because it will close the context immediately.

Another option is holding a `ConfigurableApplicationContext` reference and calling `context.close()` inside `finally`. If you need to return an exit code for a CLI, you can use `SpringApplication.exit(context)` according to the appropriate API; understand that closing the Spring context and exiting the JVM process are two related but distinct actions.

## 7. ApplicationContextFactory: Selecting the Right Context Type

`ApplicationContextFactory` is a strategy interface accepting `WebApplicationType` and returning a `ConfigurableApplicationContext`. Boot provides:

- `ApplicationContextFactory.DEFAULT`: chooses the implementation matching servlet, reactive, or none.
- `ApplicationContextFactory.ofContextClass(ContextClass.class)`: uses a specific context class.
- `ApplicationContextFactory.of(ContextType::new)`: creates a context via a `Supplier`.
- Custom factory: creates a context conditionally by `WebApplicationType`; usually should delegate to `DEFAULT` for non-special cases.

### 7.1. When Customization Is Unnecessary

For most applications, the following is enough:

~~~java
SpringApplication.run(LifecycleLabApplication.class, args);
~~~

Classpath and configuration select the context. Merely wanting to **observe** the context type is rarely a good reason to replace the factory; you can capture the context returned by `run()` and print its class name. Customize only when you need a specialized context implementation, to integrate with a host system, or to test context creation behavior.

### 7.2. Explicitly Choosing a Servlet Context

The example in section 4 uses:

~~~java
app.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigServletWebServerApplicationContext.class));
~~~

This class belongs to Spring Boot 3.3's `org.springframework.boot.web.servlet.context` package. If a project uses Spring MVC yet forces a plain `AnnotationConfigApplicationContext`, the web server lifecycle may be incompatible or fail at runtime. Do not simply swap the class name expecting Spring to convert every web bean to non-web automatically.

### 7.3. Logging When the Factory Is Called While Keeping Default Behavior

You can replace the factory configuration line in section 4 with **one** delegating factory as follows:

~~~java
app.setApplicationContextFactory(webType -> {
    ConfigurableApplicationContext context =
            ApplicationContextFactory.DEFAULT.create(webType);
    System.out.println("LAB_FACTORY_CALLED webType=" + webType
            + " context=" + context.getClass().getSimpleName());
    return context;
});
~~~

This experiment uses `DEFAULT` to create the right context, then logs its actual class; it does not refresh the context manually. Some environments need a custom `Environment`; `ApplicationContextFactory` also has default methods related to environment type and creation. When replacing the factory completely, ensure environment/context compatibility; merely demonstrating context creation is not enough to prove a production custom factory is sound.

### 7.4. Factory Switching by WebApplicationType

If you genuinely need a per-application-type policy, you can build a branching factory that defaults to delegating to Spring Boot:

~~~java
app.setApplicationContextFactory(type -> {
    if (type == WebApplicationType.NONE) {
        return new AnnotationConfigApplicationContext();
    }
    return ApplicationContextFactory.DEFAULT.create(type);
});
~~~

This is a **snippet placed inside a main class that already imports `WebApplicationType`, `AnnotationConfigApplicationContext`, and `ApplicationContextFactory`**; it is not a standalone Java file. The example itself preserves servlet/reactive semantics for web types. If you need to support multiple distinct context and environment types, design a full implementation and test across all supported `WebApplicationType` values.

### 7.5. A Factory Does Not Replace Choosing the Web Mode

The two lines below are different:

~~~java
app.setWebApplicationType(WebApplicationType.NONE);
// Choose the application mode that does not start a web server.

app.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigApplicationContext.class));
// Choose the specific context implementation.
~~~

Using both for a CLI makes sense. If you only set `NONE` and keep the default factory, Boot automatically creates the matching non-web context anyway. If you only force a plain context while letting Boot infer `SERVLET`, the configuration easily becomes inconsistent. For web applications, keeping the default factory is the simplest and lowest-risk choice unless customization is required for a clear reason.

## 8. Shutdown Hook and Graceful Shutdown: Two Layers of Responsibility

Model:

~~~text
JVM receives a normal termination signal
    |
    +-- shutdown hook registered by SpringApplication (default)
            |
            +-- close ApplicationContext
                    |
                    +-- publish ContextClosedEvent
                    +-- stop SmartLifecycle and embedded web server
                    |      +-- graceful: process in-flight requests
                    |          within the configured time
                    +-- destroy eligible beans
                           +-- @PreDestroy / DisposableBean / destroyMethod
~~~

**The hook** is the mechanism wiring JVM shutdown to closing the context. **Graceful shutdown** is the server-stopping policy while the context is closing; its goal is giving in-flight requests time to finish and stopping new requests according to the server's mechanism. **Bean cleanup** is where the application releases resources such as threads, sockets, connection pools, file handles, or flushes buffers if managed by beans.

In Spring Boot 3.3, enable graceful shutdown for supported embedded web servers with:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

If using Boot 3.3 or another line, check the exact version's documentation for defaults. Under load testing, actual request duration, server behavior, phases, and how clients hold connections can vary. `@PreDestroy` should clean up resources within bounded time; a hanging callback can delay shutdown or prevent it from finishing as expected.

**Commonly confused scenario:** switching to `server.shutdown=graceful` while disabling the hook and never calling `close()`. In that case, the JVM may exit without letting the Spring lifecycle run; the graceful option alone cannot guarantee a graceful stop. Conversely, keeping the default hook while adding your own `Runtime.getRuntime().addShutdownHook(...)` just to call `context.close()` again is usually redundant and obscures lifecycle ownership.

## 9. Hands-On Comparison of Three Scenarios

### Scenario A — Default Hook, Active Web App

1. Run the JAR from section 4 with `setRegisterShutdownHook(true)`.
2. Call `GET /probe`; record HTTP status, body, and startup markers.
3. Send a valid, non-forced termination signal.
4. Look for `LAB_CONTEXT_CLOSED` and `LAB_PRE_DESTROY`; then verify the process stopped serving.

**Valid conclusion:** the JVM had an opportunity to run the hook; the context entered the closing phase and the bean received its destroy callback. Do not infer user data is safe if the application lacks proper commit/flush mechanisms.

### Scenario B — Hook Disabled with Explicit Close in CLI

1. Run the CLI project from section 6.
2. Observe `LAB_CLI_WORK_COMPLETE`.
3. Observe `LAB_CLI_PRE_DESTROY` upon exiting `try` and `LAB_CLI_CONTEXT_CLOSED` afterward.

**Valid conclusion:** Spring callbacks ran due to intentional `close()`. Compare against Scenario A to distinguish **what triggered closure** from **the closure action itself**.

### Scenario C — Explicit or Delegating Factory

1. Run the Spring MVC app with `ofContextClass(AnnotationConfigServletWebServerApplicationContext.class)`.
2. Record `LAB_CONTEXT_TYPE` and check `GET /probe`.
3. Switch to the `DEFAULT.create(webType)` delegating factory from section 7.3, rebuild, and re-run on the same port after the old process stops.
4. Compare context class and HTTP results between both runs.

**Valid conclusion:** the factory can change how the context is created yet must remain compatible with the web mode; given the same classpath and default behavior, both approaches produce an equivalent servlet context and endpoint. If a refresh error occurs or the server fails to bind the port, inspect the web mode/context class and root exception instead of deleting shutdown callbacks.

## 10. Signal-Based Troubleshooting Guide

| Symptom | Cause to Check | Right-Scoped Fix |
|---|---|---|
| `LAB_PRE_DESTROY` missing when stopped with `kill -9` | JVM was forcefully terminated; hook had no chance to run | Retry with `SIGTERM`/Ctrl+C as appropriate; inspect the environment's stop mechanism |
| `setRegisterShutdownHook(false)` yet expecting callbacks on JVM exit | No application-managed mechanism closes the context | Call `context.close()` / try-with-resources in the true lifecycle owner, or keep the hook |
| App starts yet no HTTP listener appears | `WebApplicationType.NONE`, incompatible custom context, or startup error | Check web type, factory class, root exception, and actual port |
| Servlet MVC using `AnnotationConfigApplicationContext` | Factory forced a non-web context in an app needing web lifecycle | Use the default factory or a compatible servlet web server context |
| Factory calls `refresh()` itself and SpringApplication refreshes again | Violated the contract to return an unrefreshed context | Factory only creates the context; SpringApplication handles configuration/refresh |
| Context closes yet beans still keep external threads alive | Missing proper shutdown callback or app-managed threads | Add bounded-timeout cleanup and define clear ownership |
| `ContextClosedEvent` fires yet requests wait too long | Slow requests, stuck resources, graceful shutdown timeout/lifecycle phase | Check request durations, per-phase timeouts, and server logs |
| Maven command stops yet logs lack markers | Wrapper/IDE/signal may stop the child JVM differently | Run the JAR directly, send the signal to the exact JVM PID, and verify |
| App exits immediately when `main` finishes | Non-web app has no remaining non-daemon threads or code closed it | Confirm whether it is CLI or web, check web mode and `try` scope |

**Technical details easy to overlook:**

- For `@PreDestroy` on Spring Boot 3.x, import `jakarta.annotation.PreDestroy` (do not mistakenly use the `javax.annotation` namespace from older stacks).
- Spring manages destroy callbacks for eligible beans, especially singletons; Spring does not manage the full destruction lifecycle for prototype beans the way it does for singletons.
- `ContextClosedEvent` marks the start of closure; it alone does not guarantee all beans have already released resources.
- Registering multiple independent shutdown hooks can cause hooks to run concurrently; do not design ordering dependencies across library hooks.
- A custom factory written by the application must return an appropriate, unrefreshed context; do not create two contexts and return only one, as the abandoned context may leak resources.
- Do not expose traces containing secret configuration or leave a public shutdown endpoint open in production. When using an orchestrator, configure the deployment environment's grace period long enough for the JVM to complete shutdown.

## 11. Self-Check Questions with Answers

**1. If you remove `setRegisterShutdownHook(true)` from the web example, does Spring Boot 3.3 still register the hook?** Yes, because `true` is `SpringApplication`'s default.

**2. Does changing to `setRegisterShutdownHook(false)` make beans get destroyed right when `main()` finishes?** No. Running callbacks requires a valid `ApplicationContext` closure mechanism; `main()` returning is not equivalent to `context.close()`.

**3. Seeing `LAB_CONTEXT_CLOSED` before `LAB_PRE_DESTROY` appears—is that enough to conclude all resources are released?** No. The context-closed event and destroy callbacks are separate milestones in the shutdown sequence.

**4. Why shouldn't `ofContextClass(AnnotationConfigApplicationContext.class)` be forced on a servlet MVC application?** Because that implementation lacks an embedded servlet web server lifecycle like `AnnotationConfigServletWebServerApplicationContext`, so it may be incompatible with how Boot starts a web app.

**5. Should a factory call `context.refresh()` before returning the context?** No. `SpringApplication` is responsible for configuring/refreshing after the factory instantiates it.

**6. Does disabling the hook and setting `server.shutdown=graceful` guarantee a graceful JVM shutdown?** No. Graceful server shutdown only runs when the context-closing flow is triggered; either the hook or an explicit close is required.

**7. Why can `SIGTERM` reveal `@PreDestroy`, whereas `SIGKILL` cannot be used to test it?** Because `SIGTERM` normally gives the JVM a chance to run its shutdown sequence, while `SIGKILL` terminates the process immediately.

**8. When should you keep the default factory instead of forcing a context class?** Whenever the classpath and `WebApplicationType` already represent the application accurately and you have no real need for custom lifecycle/context behavior. The default factory minimizes the risk of picking the wrong context type.

## 12. Lesson Completion Checklist

- [ ] Create a Java 17, Spring Boot 3.3.x project with Spring Web and run it successfully.
- [ ] Record `LAB_APPLICATION_READY` and the actual servlet context class after `run`.
- [ ] Verify `GET /probe` returns HTTP 200 and matching JSON.
- [ ] Terminate the JVM cleanly and record `LAB_CONTEXT_CLOSED` and `LAB_PRE_DESTROY`.
- [ ] Distinguish among the JVM hook, context closure, bean destruction, and graceful server shutdown.
- [ ] Run the `setRegisterShutdownHook(false)` CLI example and prove explicit `close()` triggers destruction.
- [ ] Explain the three web types and their default contexts, plus the effect of `setApplicationContextFactory(...)`.
- [ ] Compare results between `ofContextClass(...)` and a `DEFAULT`-delegating factory.
- [ ] Describe the root cause of a context/web-type mismatch error and a scenario where shutdown does not run.
- [ ] Explain clearly that shutdown mechanisms do not guarantee cleanup under forced termination.

## 13. Official Reference Documentation

- Spring Boot 3.3 — SpringApplication and Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — SpringApplication API (`setRegisterShutdownHook`, `setApplicationContextFactory`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — ApplicationContextFactory API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationContextFactory.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework — Bean lifecycle and destroy callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html

When moving to Spring Boot 4.x, re-verify packages, dependencies, and settings against the 4.x documentation in use; the principle **factory creates context, SpringApplication manages startup, shutdown hook/explicit close triggers teardown** remains the core axis for analysis.