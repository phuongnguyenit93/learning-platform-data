# Server Lifecycle in ApplicationContext and Resource Cleanup

In Spring Boot web applications, the embedded HTTP server and business components do not operate independently: the **Spring ApplicationContext** coordinates initialization, request serving, shutdown, and resource cleanup. When terminating properly, the application stops accepting new requests, gives in-flight requests a chance to finish, stops background workers, closes pools and clients, and releases ports, threads, and operating system resources. Misunderstanding this lifecycle can leave the JVM hanging after HTTP stops responding, or cause the JVM to exit too early and interrupt active requests or transactions.

This lesson uses **Spring Boot 3.x, Java 17+**, with **Spring MVC + embedded Tomcat** as the primary example. The context lifecycle principles also apply to WebFlux and other servers, though connection acceptance/rejection behavior during shutdown may differ.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **JVM/process**, **ApplicationContext**, **WebServer**, singleton beans, and external resources.
2. Explain the sequence **SpringApplication.run → ApplicationContext.refresh → WebServer startup → runners → ApplicationReadyEvent**.
3. Choose the right lifecycle hook: **@PostConstruct**, **ApplicationRunner**, **SmartLifecycle**, **ContextClosedEvent**, **@PreDestroy**, or destroy methods.
4. Describe context closing, stop-order management, and resource cleanup by owner/dependency.
5. Configure **server.shutdown=graceful**, distinguish **liveness/readiness**, and verify in-flight requests during deployment/shutdown.
6. Analyze thread leaks, shutdown timeouts, unexecuted cleanup, and forced termination scenarios.

Prerequisites include Java/annotations, HTTP, IoC/DI, the concept of server ports, and how to run a Spring Boot application. The focus is on web runtime behavior rather than database design or specific orchestration platforms.

## 2. Resource Ownership Diagram

~~~text
Process/JVM
  |
  +-- SpringApplication: boots the application
         |
         +-- ApplicationContext: beans + lifecycle + events
                |
                +-- WebServer: Tomcat / Jetty / Reactor Netty / ...
                |      |
                |      +-- connectors, sockets, threads, HTTP requests
                |
                +-- Controller -> Service -> repository/client beans
                |
                +-- DataSource, ExecutorService, schedulers, consumers...
                       |
                       +-- whichever bean creates a resource must close it properly
~~~

| Component | Responsibility | What Not to Confuse |
| --- | --- | --- |
| **JVM / process** | Executes bytecode, threads, heap; receives OS signals | A running JVM does not prove the HTTP server is healthy; forced kill does not guarantee cleanup runs. |
| **SpringApplication** | Prepares Environment, creates context, coordinates startup/events | Not an HTTP server; it initializes and orchestrates components. |
| **ApplicationContext** | Registers/creates beans, injection, refresh, events, lifecycle, destroy | A context can exist without a web server, e.g., non-web apps or unit tests. |
| **ServletWebServerApplicationContext** | Web context for Servlet and embedded server | Distinct from a plain ApplicationContext; not a controller. |
| **ReactiveWebServerApplicationContext** | Web context for reactive WebServer | Request pipeline and execution differ from Servlet; close principles remain similar. |
| **WebServer** | Opens port, accepts requests, manages connectors/event loops/thread pools | The server does not automatically close every executor/client created by the application. |
| **Singleton bean** | Services, controllers, workers, clients, pools managed by Spring | Destroy hooks run when the context destroys beans; not for objects instantiated directly with new outside Spring. |
| **Resources outside Spring** | Files, manually created threads, sockets, native handles | GC does not replace timely closing; clear ownership is required. |

Spring Boot uses **ServletWebServerFactory** or **ReactiveWebServerFactory** depending on application type and dependencies to create the WebServer. In a Spring MVC app with **spring-boot-starter-web**, Tomcat is typically the default embedded server. In WebFlux, **Reactor Netty** is typically used with the reactive starter. **Deploying a WAR to an external Tomcat** is a special case: the external container also participates in coordinating the lifecycle, so do not assume Spring Boot always owns an embedded Tomcat.

## 3. How Is the Server Created and Started Inside ApplicationContext?

### 3.1. Startup Stages

~~~text
main()
  -> SpringApplication.run(...)
  -> prepare Environment, profiles, configuration
  -> infer WebApplicationType (SERVLET / REACTIVE / NONE)
  -> create matching ApplicationContext
  -> load bean definitions, process auto-configuration
  -> context.refresh()
       -> create/inject/initialize beans
       -> web context creates WebServer
       -> lifecycle processor starts appropriate lifecycle beans
       -> WebServer starts and binds port
  -> ApplicationStartedEvent
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
~~~

This is a **conceptual diagram**, not an exact call stack for every internal Spring step. Steps during refresh can interleave; exact ordering among all beans cannot be inferred from the diagram alone. **WebApplicationType.NONE** creates no HTTP server, while **SERVLET** and **REACTIVE** use matching contexts and server factories.

In a Servlet web context, Spring Boot prepares the server through web context mechanisms during refresh and then uses lifecycle components to coordinate start/stop. Normally you **do not call Tomcat.start()** in main and do not call stop() directly on the server from a controller. Keeping server infrastructure inside the context lifecycle allows Spring to coordinate other beans during startup and shutdown.

### 3.2. Bean Initialization Does Not Mean the App Is Ready

**@PostConstruct** or a bean's init method executes during bean initialization. They should be lightweight and focused on preparing the bean's own state. If a `@PostConstruct` waits minutes for an external API or loops forever, refresh can hang; errors inside it can cause startup to fail.

**ApplicationRunner** and **CommandLineRunner** run after context refresh and before **ApplicationReadyEvent**. They are better suited for work that must finish before announcing readiness, such as validating startup conditions. However, **the HTTP port may already be bound before runners finish**. Without a router honoring readiness, clients could still hit that port directly. Never treat "port open" as sufficient proof of full service readiness.

### 3.3. Events and Readiness Milestones

| Event / State | Accurate Interpretation |
| --- | --- |
| **ApplicationStartingEvent** | SpringApplication just started; context is not created yet. |
| **ApplicationEnvironmentPreparedEvent** | Environment has been prepared, before context creation. |
| **ApplicationContextInitializedEvent** | Context created and initializers ran, before loading bean definitions. |
| **ApplicationPreparedEvent** | Bean definitions loaded, right before refresh. |
| **ContextRefreshedEvent** | Context finished refreshing. |
| **WebServerInitializedEvent** | WebServer initialized; has variants ServletWebServerInitializedEvent and ReactiveWebServerInitializedEvent. |
| **ApplicationStartedEvent** | Context refreshed, before runners. |
| **AvailabilityChangeEvent: LivenessState.CORRECT** | Spring Boot considers the application live after the started milestone. |
| **ApplicationReadyEvent** | Runners finished executing. |
| **AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC** | Application announces it is ready to accept traffic. |
| **ApplicationFailedEvent** | An exception occurred during startup; cleanup hooks are not guaranteed to run identically to a normal shutdown path. |

**ContextRefreshedEvent** and **WebServerInitializedEvent** appear before **ApplicationStartedEvent** in a typical startup; do not depend on a rigid relative ordering between those two events across all context types. Bean listeners using **@EventListener** cannot catch events published before the bean/context exists; listeners needed at very early stages must be registered with SpringApplication before calling run.

Regular event listeners execute synchronously on the publisher thread. Do not put long work, blocking I/O, or infinite loops in a listener just to track state.

## 4. Request Lifecycle Is Not the Server Lifecycle

For Spring MVC:

~~~text
HTTP client
   -> Tomcat connector + Servlet thread
   -> Filter chain
   -> DispatcherServlet
   -> Controller -> Service -> external dependencies
   -> serialize data into response
   -> return response, release request-scoped resources
~~~

Completing a single request **does not mean** controllers, singleton services, HTTP clients, or DataSources should be closed. They normally serve many requests throughout the context's lifetime. Calling **executor.shutdown()** after every request will break subsequent requests; conversely, opening files or sockets per request without closing them leaks resources regardless of having `@PreDestroy` at application shutdown.

In WebFlux, requests typically flow through **WebFilter** and **DispatcherHandler**, and Reactor Netty may run on event loops. Never call blocking APIs casually on the event loop. Regardless of execution model, the context still must stop the WebServer along with beans and resources before the process exits.

**Scope rule:** short-lived resources should use **try-with-resources/finally** in their exact scope. Application-lived resources should be owned by beans with cleanup hooks or managed by framework components. Avoid storing clients or connection pools in static fields without a close policy.

## 5. What Actually Happens When Closing the Context?

### 5.1. Where Can Shutdown Originate?

- **SIGTERM** from the OS, Docker, or orchestrator: usually triggers JVM shutdown hooks, which close the context.
- **Ctrl+C** in a terminal: can trigger JVM shutdown handling depending on the environment and runner.
- **ConfigurableApplicationContext.close()**: explicit API to close the context and release beans/resources it manages.
- **SpringApplication.exit(context)**: closes the context and computes an exit code for the process; does not automatically call System.exit in every program.
- **External servlet container undeploy/stop**: part of the lifecycle is coordinated by the external container.

Spring Boot normally registers a JVM shutdown hook to close the context when the JVM exits gracefully. **There is no guarantee that @PreDestroy or stop callbacks run on kill -9/SIGKILL, JVM crashes, Runtime.halt(), power loss, or forced OS termination.** Some IDE Stop buttons or Windows process-termination tools may bypass graceful shutdown.

### 5.2. Normal Close Sequence

~~~text
Application shutdown requested
         |
         v
ApplicationContext.close()
         |
         +-- ContextClosedEvent
         |
         +-- LifecycleProcessor stops Lifecycle/SmartLifecycle beans
         |      |
         |      +-- graceful WebServer restricts new requests
         |      +-- gives in-flight requests time to complete
         |      +-- stops lifecycle components by phase/dependency
         |
         +-- destroy singleton beans
         |      |
         |      +-- @PreDestroy
         |      +-- DisposableBean / destroyMethod
         |      +-- close executors, pools, sockets, files, clients...
         |
         +-- finish closing context/server infrastructure
         v
JVM exits once no non-daemon threads keep the process alive
~~~

This is the **conceptual order of a normal context close**: some server components also have internal stop/destroy steps. On a failed refresh or hot refresh, the framework may invoke destroy without full stop notifications, so **never assert that SmartLifecycle.stop() always runs before @PreDestroy on every path**.

**ContextClosedEvent** announces that closing has started, not that all resources have already closed. **ContextStoppedEvent** corresponds to context **stop()**, a different concept from **close()**. A closed context is no longer an active context capable of serving traffic; restarting the application requires creating a new context or following a separate startup process.

### 5.3. Why Might the Server Stop Yet the JVM Still Refuse to Exit?

Stopping the HTTP port only releases one group of resources. A **ScheduledExecutorService**, manually created thread, Kafka consumer, or HTTP client with background threads can still keep the JVM alive. Conversely, **SIGKILL** lets the OS reclaim memory and sockets without giving application transactions, jobs, or logs a chance to flush or commit. Therefore, design both **cleanup** and **recovery/idempotency** for critical work.

When using **parent/child ApplicationContexts**, closing a child context does not automatically close all parent contexts; resources must be released by the context that owns them. Dependencies matter too: if a bean needs a client during stop, that client should not be closed before the bean stops cleanly.

## 6. Which Hook Fits Which Responsibility?

| API | When It Executes | Why Choose It |
| --- | --- | --- |
| **@PostConstruct** | After injection, during bean initialization | Short state preparation/validation. |
| **ApplicationRunner** / **CommandLineRunner** | After refresh, before ready | Work that must finish before SpringApplication is ready. |
| **@EventListener(ApplicationReadyEvent.class)** | When application is ready | Observe/mark ready milestone; avoid blocking inside listener. |
| **SmartLifecycle.start()** | When lifecycle processor starts components | Start consumers or workers needing coordinated start/stop. |
| **SmartLifecycle.stop(Runnable)** | When lifecycle processor requests stop | Stop intake, wait for drain, invoke callback once stopped. |
| **@EventListener(ContextClosedEvent.class)** | Context begins closing | Announce closing state, stop intake early, or observe. |
| **@PreDestroy** | When singleton bean is destroyed | Close bean-owned resources within a bounded duration. |
| **DisposableBean.destroy()** | When Spring-managed bean is destroyed | Requires Spring destroy interface; increases framework coupling. |
| **@Bean(destroyMethod = "close")** | Bean created by factory method is destroyed | Close library clients with close/shutdown without modifying the original class. |

In **Spring Boot 3.x**, import lifecycle annotations from **jakarta.annotation.PostConstruct** and **jakarta.annotation.PreDestroy**. Examples using the legacy **javax.annotation** namespace may not work as expected.

**Scope warning:** Spring manages destruction for singleton beans, but **prototype beans** are not tracked by the container for full cleanup after handing instances to callers. Objects created manually with **new** outside the container also never have `@PreDestroy` called by Spring. If a library bean already has Spring auto-configured auto-close, do not close the same resource in multiple places.

### 6.1. SmartLifecycle and Phase Ordering

**SmartLifecycle** provides **start()**, **stop()**, **stop(Runnable)**, **isRunning()**, **isAutoStartup()**, and **getPhase()**. Under normal phase rules: smaller phases **start first**, larger phases **stop first**; the lifecycle processor also considers bean dependencies. When stopping asynchronously, implementations must call **callback.run()** after actual shutdown completes, otherwise the lifecycle processor may have to wait for timeout.

Example of a simulated consumer—a complete Java class to place in the practice project's package:

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class ConsumerLifecycle implements SmartLifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("consumer started");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                System.out.println("consumer stopped");
            }
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This demo class only flips a flag, so invoking the callback immediately is fine. A real consumer must **stop accepting new messages/jobs, wait for in-flight jobs to complete or hand off safely**, and only then invoke the callback. Never invoke the callback to signal "shutdown started" while the worker is still processing data. If `stop()` runs on a thread and waits for that very same thread to terminate, a deadlock can occur.

**@PreDestroy** is usually meant for final resource disposal; **SmartLifecycle.stop(...)** is for ordered, time-bounded stop orchestration. Both can be combined if the close operation is idempotent. Do not hardcode Spring Boot infrastructure bean phase numbers based solely on a casual observation in one version.

## 7. WebServer Graceful Shutdown

### 7.1. Configuration

Place in **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: lifecycle-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

In **Spring Boot 3.3**, **server.shutdown=graceful** enables graceful shutdown. Declaring it explicitly keeps the exercise reproducible even if newer Spring Boot versions change defaults. **spring.lifecycle.timeout-per-shutdown-phase** sets the wait timeout **per lifecycle phase**, not an absolute total cap for the entire shutdown and all destroy callbacks. Avoid assuming "20s guarantees the process exits within 20s."

Graceful shutdown runs during context close at the appropriate stop phase, giving in-flight requests a chance to finish while restricting new requests. Spring Boot 3.3 supports it on Tomcat, Jetty, Reactor Netty, and Undertow. How new requests are rejected depends on the server: several servers stop accepting new connections at the network layer, while Undertow may return **503 Service Unavailable**. Keep-alive connections and proxies can alter what clients observe.

A 60-second request is not guaranteed to complete within a 20-second grace period. For **WebSockets, SSE, streaming, large uploads, long transactions, or job queues**, plan explicit draining, retries, timeouts, and recovery. Graceful HTTP server shutdown does not replace data-safety mechanisms in message consumers.

### 7.2. Readiness During Startup and Shutdown

Spring Boot uses **ApplicationAvailability** with two state types:

- **LivenessState.CORRECT/BROKEN:** whether the application is healthy at the runtime survival level.
- **ReadinessState.ACCEPTING_TRAFFIC/REFUSING_TRAFFIC:** whether the instance should receive additional traffic.

During startup, the context may have refreshed and the server may be technically ready while **readiness remains REFUSING_TRAFFIC** until runners complete. During graceful shutdown, readiness switches to refusing new traffic. With Spring Boot Actuator and health probes configured as above, the common endpoints are:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

**Readiness is only useful if the load balancer/orchestrator actually respects it.** A client hitting the port directly can bypass the readiness contract. Readiness does not necessarily include every external dependency: add appropriate indicators/health groups if business requirements truly need to verify them. Avoid putting flaky dependencies into liveness, which triggers cascading restart loops.

### 7.3. Relationship Between Graceful Shutdown and Rollouts

~~~text
Version replacement requested
  -> old instance readiness refuses traffic
  -> load balancer stops routing new requests (propagation takes time)
  -> graceful web server gives active requests bounded time to complete
  -> workers/consumers stop intake and drain
  -> beans are destroyed and pools/clients closed
  -> process exits or is terminated by orchestrator on deadline
  -> new instance serves traffic per readiness
~~~

In real systems, there can be overlap between old and new instances as well as timeouts from orchestrators, proxies, clients, and message brokers. Choose timeouts realistically according to actual latency; the HTTP server's own deadline does not control all those external deadlines.

## 8. Runnable Hands-On Exercise: Observing Milestones and Resource Cleanup

Generate a project from **https://start.spring.io** with Gradle, **Spring Boot 3.x**, **Java 17+**, group **com.example**, artifact **lifecycle-demo**, package **com.example.lifecycledemo**, and dependencies **Spring Web**, **Spring Boot Actuator**, **Spring Boot Starter Test**. Use the generated Gradle wrapper. If using a newer version than Boot 3.x, check the corresponding packages/APIs and defaults.

### 8.1. Main and ApplicationContext

**src/main/java/com/example/lifecycledemo/LifecycleDemoApplication.java**

~~~java
package com.example.lifecycledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }
}
~~~

Place main in the parent package so the `@Component`/`@RestController` classes below are found by component scanning. **SpringApplication.run(...)** builds the web context and server; do not create Tomcat manually.

### 8.2. Controller with Fast and Slow Requests

**src/main/java/com/example/lifecycledemo/WorkController.java**

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.TimeUnit;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    public record Ping(String message) { }

    @GetMapping("/demo/ping")
    public Ping ping() {
        return new Ping("pong");
    }

    @GetMapping("/demo/slow")
    public String slow(@RequestParam(defaultValue = "6") int seconds)
            throws InterruptedException {
        int boundedSeconds = Math.max(0, Math.min(seconds, 10));
        TimeUnit.SECONDS.sleep(boundedSeconds);
        return "finished";
    }
}
~~~

Here **sleep** simply simulates an in-flight Servlet request to test shutdown, capped at 10 seconds. Do not use sleep for real business logic or load control. The response body of **GET /demo/ping** when running with Jackson in Spring Web is:

~~~json
{"message":"pong"}
~~~

The response body of **GET /demo/slow?seconds=6** when completing normally is:

~~~text
finished
~~~

### 8.3. Observing Events

**src/main/java/com/example/lifecycledemo/RuntimeEvents.java**

~~~java
package com.example.lifecycledemo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.ServletWebServerInitializedEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RuntimeEvents {
    @EventListener
    public void serverInitialized(ServletWebServerInitializedEvent event) {
        System.out.println("HTTP port: " + event.getWebServer().getPort());
    }

    @EventListener
    public void applicationReady(ApplicationReadyEvent event) {
        System.out.println("ApplicationReadyEvent");
    }

    @EventListener
    public void contextClosed(ContextClosedEvent event) {
        System.out.println("ContextClosedEvent");
    }
}
~~~

**ServletWebServerInitializedEvent** provides the **actual** port after the server initializes. When `server.port=0` is configured, the OS picks a random port; do not assume 8080. **ContextClosedEvent** arrives when closing starts, not necessarily when all resources have already closed. Use logs to observe milestone meanings rather than strictly asserting exact cross-thread line ordering.

### 8.4. Real Resource Owned by a Bean

**src/main/java/com/example/lifecycledemo/MaintenanceTask.java**

~~~java
package com.example.lifecycledemo;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceTask {
    private final ScheduledExecutorService executor =
            Executors.newSingleThreadScheduledExecutor();

    @PostConstruct
    public void start() {
        executor.scheduleAtFixedRate(
                () -> System.out.println("maintenance tick"),
                0, 30, TimeUnit.SECONDS);
    }

    @PreDestroy
    public void close() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    System.err.println("maintenance task did not terminate");
                }
            }
        } catch (InterruptedException exception) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        System.out.println("maintenance cleanup attempted");
    }
}
~~~

This bean **creates its own ScheduledExecutorService**, so it is responsible for stopping new task intake and shutting down the thread when the context destroys the bean. **shutdown()** requests an orderly stop; **awaitTermination** waits up to the deadline; **shutdownNow()** interrupts running tasks, though it cannot guarantee stopping uncooperative tasks. In production, tasks must honor interruption and include recovery policies if data has not been committed.

If a resource is created and owned by framework auto-configuration (such as many DataSources/connection pools), verify the existing destroy mechanism before adding manual cleanup; closing twice or closing too early can break other beans.

### 8.5. Running and Testing Shutdown

On Linux/macOS, at the project root:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~text
gradlew.bat bootRun
~~~

Open another terminal:

~~~bash
curl -s http://localhost:8080/demo/ping
curl -s "http://localhost:8080/demo/slow?seconds=6"
~~~

In the second step, to verify graceful shutdown while a slow request is still running:

1. Package with **./gradlew bootJar**, and run the executable JAR via **java -jar build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar** (adjust the name if your actual version differs).
2. Run **curl -s "http://localhost:8080/demo/slow?seconds=6"** in a separate terminal.
3. While the request is running, send **SIGTERM** to the JVM process PID using **kill -TERM PID** on Linux/macOS, or use **docker stop** if running via Docker. Avoid using SIGKILL.
4. With a 20s grace period, the 6s request typically completes and returns **finished** if the environment does not cut the connection; new requests started during shutdown may be rejected.
5. Observe **ContextClosedEvent**, cleanup logs from **@PreDestroy**, the process, and the port after stopping.

Results depend on the server, proxy, OS signals, and exact timing when the request was accepted. An IDE Stop button or forced termination command may not deliver SIGTERM as needed for this test. **Do not run kill -9** to test graceful shutdown.

### 8.6. Small Test Verifying Destroy Callbacks

This test only proves the bean lifecycle mechanism when closing a context; it does not start Tomcat.

**src/test/java/com/example/lifecycledemo/ContextCloseTest.java**

~~~java
package com.example.lifecycledemo;

import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextCloseTest {
    static class Probe {
        boolean closed;

        @PreDestroy
        void cleanup() {
            closed = true;
        }
    }

    @Test
    void closingContextInvokesPreDestroy() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();
        context.registerBean(Probe.class);
        try {
            context.refresh();
            Probe probe = context.getBean(Probe.class);
            assertFalse(probe.closed);

            context.close();
            assertTrue(probe.closed);
        } finally {
            context.close();
        }
    }
}
~~~

Run **./gradlew test**. The test uses **AnnotationConfigApplicationContext** rather than a web context, confirming that a Spring-managed bean has its `@PreDestroy` callback executed after close. **close() can be called repeatedly without destroying the same context multiple times**, though production code should still manage ownership carefully. This test does not prove HTTP requests are drained; use the SIGTERM experiment in the previous section to observe real server behavior.

## 9. Resource Cleanup Checklist

| Resource | Problem If Cleanup Is Forgotten | How to Handle |
| --- | --- | --- |
| **Embedded WebServer** | Port/connector/threads remain alive | Let Spring web context coordinate; configure shutdown and verify in practice. |
| **Custom ExecutorService/ScheduledExecutorService** | Threads do not exit, jobs keep running | shutdown, awaitTermination with deadline, handle interrupt, shutdownNow if needed. |
| **Database connection pool** | Connections/sockets not returned | Use bean/pool with clear owner; prefer framework-configured mechanisms. |
| **Pooled HTTP client** | Holds connections, timers, threads | Create reusable bean; call the library's close on context destroy if app-owned. |
| **Message listener/consumer** | Consumes messages during shutdown, loses acks/offsets | Stop intake, drain/commit or allow safe retry; prevent double-processing via idempotency. |
| **Scheduled tasks, background workers** | Jobs run after dependencies have closed | Use proper lifecycle stop, bounded deadlines, close executors. |
| **Per-request files/sockets/streams** | Handle leaks, unflushed data | try-with-resources/finally right when scope ends. |
| **WebSocket, SSE, long polling** | Long-lived connections block shutdown | Send close notice, bound duration, reconnect/resume if needed. |
| **ThreadLocal** | State leaks across requests on thread pools | Clean up in finally of request/task; do not wait for @PreDestroy. |

**Owner rule:** only close resources owned by the bean/application. A controller should not close a shared DataSource or shared HTTP client at the end of each request. Before adding `@PreDestroy`, check whether Spring auto-configuration already manages and closes that resource.

## 10. Common Issues and How to Diagnose Them

### 10.1. HTTP Stopped Yet JVM Stays Alive

**Symptom:** port no longer listening, logs show context closing, process remains alive. **Suspects:** non-daemon threads, custom executors, schedulers, workers ignoring interrupt, uncompleted stop callbacks. **Check:** take a thread dump with **jcmd PID Thread.print** or **jstack PID** while the JVM is still accessible; find thread names and owner stacks. **Fix:** shut down via proper APIs, apply timeouts/interrupts, and never wait on the same thread executing stop.

### 10.2. Shutdown Takes Longer Than Configured Timeout

**Cause:** timeout-per-shutdown-phase applies per phase; multiple phases or blocking destroy hooks/client closes may exist. **Check:** measure callback durations, phase logs, queued/active tasks, and external client timeouts. **Fix:** enforce clear deadlines, stop intake early, avoid infinite blocking callbacks; increase timeouts only after understanding the cause.

### 10.3. Restarts Return 502/503 or Connection Reset

**Cause:** load balancer still sends new requests while instance stops, slow readiness propagation, grace period shorter than requests, proxy closes connections before server. **Fix:** test rolling shutdown under load, measure p95/p99 and gateway timeouts, tune draining and client/consumer retries/idempotency. Server graceful shutdown is only one piece of safe rollouts.

### 10.4. @PreDestroy Is Never Called

**Check:** objects created with new, prototype scope, wrong annotation namespace, context never closed, SIGKILL/crash, or early startup failure. **Fix:** place resources in properly scoped managed beans, declare valid hooks, and design recovery so you do not depend solely on cleanup.

### 10.5. Startup Reports Port Error or Not Ready

**Check:** actual **server.port** value, process occupying the port, dependencies/server factory, WebApplicationType, bean creation or runner errors. **Application started** is not synonymous with **ready**; read the stack trace root cause and lifecycle milestone before guessing HTTP mapping errors.

### 10.6. Calling close() Too Early or Multiple Owners Closing

**Symptom:** controller fails after the first request, consumer loses connection before stopping, executor rejects tasks. **Fix:** clarify resource owners, never close shared pools per request, make close operations idempotent, and order lifecycle by dependencies. If cleanup throws an exception, log details and proceed to close independent resources safely instead of aborting all cleanup.

### 10.7. ContextClosedEvent Mistaken for "Everything Is Released"

This is only the **opening event of context closing**. To verify resources have truly been reclaimed, measure callbacks, executor/pool states, thread counts, ports, and process exit. Avoid signaling "safe to remove resources" based solely on ContextClosedEvent while other beans are still cleaning up.

## 11. Knowledge Self-Check

**1. Can an ApplicationContext exist without a WebServer?** Yes. An ApplicationContext can serve non-web applications or unit tests. A WebServer only belongs to an appropriate web context/app type.

**2. Why does WebServerInitializedEvent differ from ApplicationReadyEvent?** Server initialization does not mean runners have finished or readiness permits traffic. Ready is the application milestone after runners.

**3. How does context close differ from stop?** Stop coordinates Lifecycle components; close ends the context lifecycle, destroys singletons, and releases resources—it must not be treated as a pause that can restart the old context.

**4. Why does SmartLifecycle need a callback?** It allows the shutdown phase to wait until asynchronous stop tasks genuinely finish. Invoking the callback before draining finishes creates a false completion signal.

**5. Why doesn't @PreDestroy protect data on kill -9?** SIGKILL prevents the JVM from running hooks; critical data requires transactions, retries, checkpoints/idempotency, or out-of-process recovery.

**6. Is a 20s grace period enough for every request?** No. It is a per-phase wait timeout; long requests, streams, proxies, and orchestrators have separate deadlines. Measure against your real system.

**7. Should a controller close a DataSource?** No. A DataSource is typically a shared resource managed by beans/the framework; close it by owner on shutdown, not per request.

**8. Why can a manually created thread hang the JVM after the HTTP port closes?** That thread is an independent resource; server shutdown does not know how to stop it without an owner and cleanup callback.

## 12. Completion Checklist

- [ ] Explain the relationship **JVM → SpringApplication → web ApplicationContext → WebServer → request**.
- [ ] Run the demo and receive exact **{"message":"pong"}** when calling /demo/ping.
- [ ] Point out **WebServerInitializedEvent**, **ApplicationStartedEvent**, **ApplicationReadyEvent**, and the meaning of readiness.
- [ ] Package the JAR and test SIGTERM while /demo/slow is processing; observe in-flight and new requests.
- [ ] Verify **ContextClosedEvent**, **@PreDestroy**, and that the executor does not keep the JVM alive after shutdown.
- [ ] Run the context-close test and explain why that test does not verify Tomcat graceful shutdown.
- [ ] Identify owner, timeout, and recovery path for at least one real resource in your application.

### Official Documentation

- [Spring Boot 3.3: Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html) — server capabilities and per-phase timeouts.
- [Spring Boot 3.3: SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) — startup events and availability states.
- [Spring Framework: Lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html) — bean destruction and SmartLifecycle.
- [Spring Framework: ConfigurableApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html) — close and shutdown hooks.

The server lifecycle is part of the **ApplicationContext** lifecycle, while request completion is an even narrower scope. The server may stop accepting new traffic while the context is still draining and destroying beans; the JVM only exits cleanly once resources owned by the application and framework have been released or terminated within appropriate deadlines.