# Spring Boot Application Shutdown Paths: close, JVM Shutdown Hook, OS Signals, and Failures

## 1. Four Concepts to Distinguish

When we say Spring Boot "stops", we may be referring to different things:

- **Closing the ApplicationContext**: Spring stops lifecycle beans and invokes destroy callbacks of container-managed beans.
- **JVM shutdown**: The Java Runtime runs registered shutdown hooks and then terminates the virtual machine.
- **Operating system signals**: The OS, terminal, or container asks the JVM to terminate, which may trigger shutdown hooks.
- **Abnormal termination**: Process crash, SIGKILL, Runtime.halt, or power loss; callbacks cannot be relied upon to guarantee cleanup.

The most important rule: **ApplicationContext.close() is not System.exit()**. The former closes the Spring container; the latter requests the entire JVM to terminate. Conversely, **System.exit() is not SIGKILL**, because System.exit still triggers the shutdown sequence and shutdown hooks.

A web application can stay alive after main() returns because the embedded server still has non-daemon threads. A batch application can explicitly close its context, yet the JVM may not exit if other threads exist outside the container.

## 2. Table of Shutdown Paths

| Path | Initiator | Immediate JVM shutdown? | Spring Cleanup |
| --- | --- | --- | --- |
| context.close() | Code or test | No | Closes the context directly |
| SpringApplication.exit(context) | Application code | No | Closes context if possible, returns exit code |
| System.exit(code) | Code | Yes | Boot JVM hook closes context if still registered |
| JVM runs out of non-daemon threads | JVM | Yes | Runs shutdown hooks |
| SIGTERM | OS/Docker/Kubernetes | Usually yes | JVM hook gets a chance to close context |
| SIGINT/Ctrl+C | Terminal/OS | Usually yes | Depends on environment and signal forwarding |
| SIGKILL/kill -9 | OS | Forced | No callback guarantee |
| Runtime.halt(code) | Java code | Forced, skips hooks | No callback guarantee |
| Startup exception | SpringApplication.run | Not equivalent to JVM shutdown | Boot handles startup failure and attempts cleanup |
| Runtime exception after Ready | Request/worker | Not by default | Context may continue running |

Do not infer from this table that signals and lifecycles always behave identically across Linux, Windows, IDEs, shell wrappers, and containers. Always verify on the real environment.

## 3. Direct Closure via ApplicationContext.close()

ConfigurableApplicationContext provides the close() API:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);
context.close();
~~~

This is an illustrative snippet requiring an actual MyApplication class. Simplified normal close sequence:

~~~text
ApplicationContext.close()
   ContextClosedEvent
   LifecycleProcessor.onClose()
     SmartLifecycle stop
     Stop order: higher phase before lower phase
   Destroy managed singleton beans
     @PreDestroy
     DisposableBean.destroy()
     Bean destroyMethod
   ApplicationContext closed
close() returns
~~~

**ContextClosedEvent** is published when the context begins its normal close path; it **does not mean all resources have finished stopping**. Spring subsequently coordinates lifecycle stop and bean destruction.

Notes:

1. **close() does not automatically call System.exit**. The JVM still depends on non-daemon threads, other contexts, and the host runtime.
2. If the embedded web server is owned by Spring, close stops the server; whether in-flight requests are drained depends on the graceful shutdown configuration.
3. Resources outside Spring-managed beans must be closed by their own owners.
4. Emails already sent, outbound HTTP calls, published messages, or committed data are not automatically rolled back when the context closes.
5. Bean cleanup should tolerate repeated stop calls and states where a resource is already closed or not yet fully initialized.

In CLI/batch applications, use try-with-resources:

~~~java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    executeJob(context);
}
~~~

This is an illustration with an application-defined executeJob. If run returns the context successfully, Java automatically closes it upon exiting the try block. If **SpringApplication.run throws an exception before returning the context**, the try block does not yet own the resource, and Spring Boot must handle failure cleanup of the context being created.

## 4. SpringApplication.exit Is Not the Same as System.exit

Spring Boot API:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

SpringApplication.exit collects exit codes from **ExitCodeGenerator** instances and closes the context if possible. It returns an **int**, but **does not necessarily terminate the JVM**.

Example of explicitly stopping a CLI application with a non-zero exit code:

~~~java
int exitCode = SpringApplication.exit(context, () -> 42);
System.exit(exitCode);
~~~

The lambda here is an ExitCodeGenerator passed directly. By convention, 0 indicates success, and a non-zero code signals an error.

The differences:

- **SpringApplication.exit**: handles the Spring side and returns the exit code.
- **System.exit**: starts the JVM shutdown sequence, runs remaining registered shutdown hooks, and terminates the JVM.
- **System.exit(0)** does not automatically compute an exit code from ExitCodeGenerator beans; to obtain the logical code from Spring, use the result of SpringApplication.exit.
- **ExitCodeExceptionMapper** and exceptions implementing ExitCodeGenerator can participate in the startup failure handling path; this is not an explicit shutdown call made by code after the app is ready.

For a web service, you generally **should not call System.exit from a controller** just because a single request failed. It affects the entire JVM and all remaining requests. For CLI/batch applications, an exit code is a useful contract so schedulers, CI, and shells know the outcome.

## 5. Spring Boot's Default JVM Shutdown Hook

As of Spring Boot 3.3, SpringApplication registers a JVM shutdown hook by default to close the ApplicationContext when the JVM shuts down in an orderly manner:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);
application.setRegisterShutdownHook(true);
application.run(args);
~~~

This is an illustrative example; the default value of setRegisterShutdownHook is **true**. If configured to false, the owning code must ensure the context is closed via an appropriate path.

**Do not confuse these three mechanisms:**

| Mechanism | Belongs to | When it occurs |
| --- | --- | --- |
| JVM shutdown hook | Java Runtime | When the JVM begins shutdown |
| ContextClosedEvent | Spring ApplicationContext | When the context is being closed |
| @PreDestroy/DisposableBean | Spring BeanFactory | When a managed bean is destroyed |

A normal path might look like this:

~~~text
OS SIGTERM
JVM shutdown sequence
Spring Boot shutdown hook
ApplicationContext.close()
ContextClosedEvent
SmartLifecycle stop
@PreDestroy and destroy callbacks
JVM exits
~~~

If code calls context.close() directly, ContextClosedEvent can occur **without the JVM shutdown hook having been triggered yet**.

### Do Not Depend on Ordering Between JVM Hooks

According to the Java Runtime API, the JVM starts shutdown hooks in an **unspecified order**; they may run concurrently. Therefore:

- Custom hook A is not guaranteed to run before Boot hook B.
- Do not call a Spring Repository in a custom hook assuming the context is still active.
- Hooks must be thread-safe, fast, and have appropriate timeouts.
- Do not call **System.exit() from inside a shutdown hook**, because calling exit during shutdown can block and prevent shutdown from completing.
- When resource stop ordering is required, use **SmartLifecycle.getPhase()** and bean dependencies inside the Spring context.

## 6. Standalone Java Program to Verify the Shutdown Hook

Create the file **HookBasics.java**:

~~~java
public class HookBasics {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("JVM_HOOK")));

        System.out.println("MAIN_BEGIN");

        if (args.length > 0 && args[0].equals("exit")) {
            System.exit(0);
        }

        System.out.println("MAIN_END");
    }
}
~~~

Run with Java 17+:

~~~bash
javac HookBasics.java
java HookBasics
~~~

The printed messages:

~~~text
MAIN_BEGIN
MAIN_END
JVM_HOOK
~~~

When main finishes and no non-daemon threads remain, the JVM shuts down automatically, so the hook is invoked.

Run the System.exit branch:

~~~bash
java HookBasics exit
~~~

Messages:

~~~text
MAIN_BEGIN
JVM_HOOK
~~~

MAIN_END does not appear because System.exit starts shutdown before reaching that line. There is only one hook in the example, so there is no ordering issue among multiple hooks. This program has no Spring context and does not cover @PreDestroy.

## 7. Operating System Signals

### SIGTERM

On Linux/Unix with a standard JVM, SIGTERM normally causes the Java Runtime to start the shutdown sequence. If the Boot hook is still registered and the JVM has enough time, the context is closed:

~~~bash
kill -TERM JAVA_PID
~~~

Use only the actual PID of the **Java process**. If running through Gradle, an IDE, or a shell wrapper, the PID you see in the terminal may belong to the wrapper rather than the JVM. Never send arbitrary signals to production processes.

### SIGINT/Ctrl+C

Ctrl+C typically sends SIGINT in a terminal. On Unix with a standard JVM, SIGINT can trigger JVM shutdown. Windows, IDEs, and containers have their own mechanisms; a Stop button in an IDE might terminate the process immediately instead of simulating SIGTERM.

### SIGKILL

~~~bash
kill -KILL JAVA_PID
~~~

SIGKILL is a forced termination; the JVM has no chance to complete hooks along the normal path. **There is no guarantee that ContextClosedEvent, stop, @PreDestroy, or finally will execute**.

### Runtime.halt

~~~java
Runtime.getRuntime().halt(1);
~~~

This is a dangerous API example; do not run it in practice exercises. Runtime.halt terminates the JVM immediately and **does not start the shutdown sequence**. It differs from System.exit.

Host crashes, OOM kills, power outages, native errors, and node evictions can also skip cleanup. Therefore, critical resources require transactions, idempotency, checkpoints, and restart recovery rather than relying on shutdown hooks as the sole line of defense.

## 8. Server Graceful Shutdown in Spring Boot 3.3

**Version distinction:** in **Spring Boot 3.3**, graceful shutdown is supported but must be explicitly enabled:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot 3.4+ documentation describes a different default, so do not use newer-version defaults to assert behavior for Boot 3.3.

Spring Boot 3.3 supports graceful shutdown with the embedded web servers **Tomcat, Jetty, Reactor Netty, and Undertow**. When the context closes, the server stops accepting new requests according to its mechanism and gives in-flight requests extra time to complete.

- Tomcat/Jetty/Reactor Netty can stop accepting new requests at the network layer.
- Undertow may still accept new connections but respond with HTTP 503.
- Persistent connections, proxies, HTTP protocol, and timing affect the outcome.
- **spring.lifecycle.timeout-per-shutdown-phase** is the wait budget **per shutdown phase**, not a total JVM limit that is always exactly 20 seconds.

**Readiness is not the same as graceful shutdown.** Readiness probes help the orchestrator stop routing new traffic. Web graceful shutdown helps the embedded server drain in-flight requests. HTTP readiness **does not automatically pause Kafka/RabbitMQ consumers or schedulers**; those components need their own stop/pause/ack lifecycles.

## 9. SmartLifecycle and Destroy Callbacks

Spring-managed resources can use:

- **@PreDestroy** from jakarta.annotation in Spring Boot 3.
- **DisposableBean.destroy()**.
- **@Bean(destroyMethod="close")** or a suitably inferred destroy method.
- **SmartLifecycle.stop(Runnable)** for continuously running components that may need to wait for an asynchronous stop.
- **ContextClosedEvent** for lightweight logging/metrics when closing begins.

During a normal close, Spring performs lifecycle stops and then destroys managed singleton beans. With SmartLifecycle, shutdown proceeds from **higher phase to lower phase**, allowing consumers to stop pulling new work before underlying resources shut down. If stopping asynchronously, the callback must be invoked after actual completion:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Do not invoke the callback immediately after merely submitting an async stop command. If the callback is never invoked, the lifecycle processor may wait until the phase timeout expires.

If a bean defines all three destroy mechanisms on different methods, the typical order is **@PreDestroy, DisposableBean.destroy(), custom destroyMethod**. However, do not close the same connection in three different places without a clear reason; avoid double close, races, and ambiguous resource ownership.

**Errors in factory methods:** if a client/socket is created and then an exception is thrown before Spring receives the bean, @PreDestroy is not guaranteed to be called. Partially opened resources must be closed immediately in catch/finally at the creation site while preserving the original exception for diagnosis.

## 10. Spring Boot 3.3/Java 17 Example: Four Shutdown Paths

This project demonstrates the following modes:

- **close**: main directly closes the context.
- **exit**: SpringApplication.exit followed by System.exit.
- **signal**: embedded Tomcat continues running until the OS sends SIGTERM.
- **fail**: runner throws an exception during startup, and ApplicationFailedEvent observes the error.

### 10.1. Project Structure

~~~text
shutdown-paths-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          ShutdownPathsDemo.java
      resources/
        application.properties
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'shutdown-paths-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Requires JDK 17+, a compatible Gradle version, and dependencies available via repository/cache.

File **src/main/resources/application.properties**:

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
spring.main.log-startup-info=false
~~~

### 10.2. Java Source

File **src/main/java/example/ShutdownPathsDemo.java**:

~~~java
package example;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ShutdownPathsDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ShutdownPathsDemo.class);

        app.addListeners(
                (ApplicationListener<ApplicationFailedEvent>) event ->
                        System.out.println("APPLICATION_FAILED"));

        ConfigurableApplicationContext context = app.run(args);
        String mode = context.getEnvironment()
                .getProperty("demo.mode", "signal");

        switch (mode) {
            case "close" -> {
                System.out.println("CALL_CLOSE");
                context.close();
                System.out.println("CLOSE_RETURNED");
            }
            case "exit" -> {
                System.out.println("CALL_EXIT");
                int code = SpringApplication.exit(context, () -> 0);
                System.out.println("EXIT_CODE=" + code);
                System.exit(code);
            }
            case "signal" -> System.out.println("WAIT_SIGNAL");
            default -> {
                context.close();
                throw new IllegalArgumentException(
                        "Unknown mode: " + mode);
            }
        }
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> {
            System.out.println("RUNNER");
            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("Demo startup failure");
            }
        };
    }
}

@Component
class ManagedWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("WORKER_START");
    }

    @Override
    public void stop() {
        if (running) {
            running = false;
            System.out.println("WORKER_STOP");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    @PreDestroy
    public void destroy() {
        System.out.println("WORKER_PRE_DESTROY");
    }
}

@Component
class CloseEvents {

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("APPLICATION_READY");
    }

    @EventListener
    public void closed(ContextClosedEvent event) {
        System.out.println("CONTEXT_CLOSED");
    }
}

@RestController
class SlowController {
    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        Thread.sleep(4_000);
        return "DONE";
    }
}
~~~

**Verification:** only ShutdownPathsDemo is a public class; the remaining classes are package-private in the same package. SmartLifecycle is fully implemented; @PreDestroy uses Jakarta. ApplicationFailedEvent is registered before run to receive startup failures even if the context is incomplete. SlowController only simulates an in-flight HTTP request and is not a production pattern.

## 11. Running and Comparing Results

### 11.1. The close() Path

~~~bash
./gradlew bootRun --args="--demo.mode=close"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=close"
~~~

Lines printed by the demo code in order:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
CALL_CLOSE
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
CLOSE_RETURNED
~~~

Spring Boot/Tomcat/Gradle also produce their own logs. In a normal close, ContextClosedEvent arrives before lifecycle stop, followed by bean destruction, and then close returns.

### 11.2. The SpringApplication.exit + System.exit Path

~~~bash
./gradlew bootRun --args="--demo.mode=exit"
~~~

Lines printed by the code:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
CALL_EXIT
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
EXIT_CODE=0
~~~

Then System.exit(0) puts the JVM into shutdown. The context is already closed, so duplicate destroy callbacks are not expected. If the generator is changed to 42, the OS process may return code 42 and Gradle may treat bootRun as failed.

### 11.3. The SIGTERM Path

To get the real Java PID, package and run directly:

~~~bash
./gradlew bootJar
java -jar build/libs/shutdown-paths-demo-1.0.0.jar --demo.mode=signal
~~~

Lines before the signal:

~~~text
WORKER_START
RUNNER
APPLICATION_READY
WAIT_SIGNAL
~~~

From another Linux/macOS terminal, identify the real Java PID and send:

~~~bash
kill -TERM JAVA_PID
~~~

If the JVM handles SIGTERM and the Spring hook runs, cleanup lines typically appear:

~~~text
CONTEXT_CLOSED
WORKER_STOP
WORKER_PRE_DESTROY
~~~

There is no guarantee that stdout of the entire process contains only these lines; web server logs, signal forwarding, and flush behavior depend on the runtime. When testing on Windows, Ctrl+C can be used; it is not identical to how an IDE stops a process.

### 11.4. Testing Graceful HTTP Drain

In signal mode, in terminal A:

~~~bash
curl -i http://localhost:8080/slow
~~~

While the server has received the request and is still waiting for about four seconds, send SIGTERM from another terminal. With graceful enabled and a 20-second phase timeout, the accepted request **has a chance to complete**. New requests may be rejected. The outcome depends on signal timing, networking, keep-alive, and the client; returning 200 on every single run is not guaranteed.

### 11.5. The Startup Failure Path

~~~bash
./gradlew bootRun --args="--demo.fail"
~~~

Lines before the error typically include:

~~~text
WORKER_START
RUNNER
APPLICATION_FAILED
~~~

The runner throws IllegalStateException before SpringApplication.run returns. There is no APPLICATION_READY as in the successful startup branch; main also does not print CALL_CLOSE/CALL_EXIT/WAIT_SIGNAL. Boot handles the error and attempts to clean up the context if present. **The order of all callbacks in the failure branch should not be treated as fixed stdout**, especially when the context fails very early.

## 12. Startup Failures Differ from Runtime Failures

**Startup failure** can happen during bean initialization, context refresh, port binding, SmartLifecycle.start, or runners. Spring Boot provides **ApplicationFailedEvent**, FailureAnalyzer, and best-effort cleanup. The context of ApplicationFailedEvent may be null if the failure happens before the context is created. Do not assume every @PreDestroy is invoked during a refresh that fails partway through.

**Runtime failure** after Ready can be an exception in an HTTP controller, @Async task, scheduled method, or message listener. These errors **usually do not automatically shut down the entire SpringApplication**. Each infrastructure component has its own retries, error handlers, circuit breakers, and handling policies. ApplicationFailedEvent is not a generic event for all business errors after Ready.

If a runtime error truly renders the service unable to serve, you must design a policy: update readiness, stop accepting new work, wait/drain tasks, request an orchestrator restart, or exit the JVM with a non-zero code. Do not just print a stack trace and expect the system to automatically know this is a fatal error.

**Partially created resources:** if a constructor/factory method opens a socket and fails before the bean completes, cleanup must be performed immediately in a local try/finally/catch. Spring cannot automatically know every external resource that code is holding. Do not use @PreDestroy as a substitute for transactions and idempotency.

## 13. Kubernetes/Docker and Shutdown Budgets

A typical path:

~~~text
Pod termination requested
preStop hook if present
SIGTERM to Java process
JVM shutdown hooks
Spring Boot context.close()
Web graceful drain
SmartLifecycle stop
Bean destroy callbacks
Process exits
If grace period expires: SIGKILL
~~~

This diagram is conceptual; the exact sequence of routing updates, preStop, and signals also depends on the platform.

**Checklist:**

1. The signal must reach the exact **Java PID**, especially if the entrypoint has a shell wrapper. Use exec java or proper init/signal forwarding.
2. **terminationGracePeriodSeconds** must be sufficient for preStop, web drain, worker shutdown, and cleanup.
3. **spring.lifecycle.timeout-per-shutdown-phase** is per phase, not the total time allowed by the OS.
4. With Boot 3.3, **server.shutdown=graceful** must be enabled.
5. Readiness probes help limit new traffic, but routing updates have propagation delay.
6. Kafka/RabbitMQ consumers must stop polling and ack/nack/requeue or handle in-flight messages according to their own semantics.
7. Background executors/tasks must have ownership and cancellation/timeouts.
8. SIGKILL when the deadline expires can cut across transactions and I/O; retries/idempotency/checkpoints are required.
9. The final exit code may be affected by shell wrappers or orchestrators; do not assert that every SIGTERM yields a fixed number.

## 14. Common Mistakes

**1.** Calling context.close() and assuming the JVM always exits immediately. **Wrong:** the JVM may still have non-daemon threads.

**2.** Calling SpringApplication.exit and forgetting to use the exit code when a CLI needs to return status. **Wrong:** the method only returns an int.

**3.** Thinking System.exit skips JVM hooks. **Wrong:** it is Runtime.halt that skips the shutdown sequence.

**4.** Thinking SIGKILL runs @PreDestroy. **Wrong:** there is no guarantee of cleanup running.

**5.** Adding a custom JVM hook and relying on registration order relative to the Boot hook. **Wrong:** hooks can run concurrently.

**6.** Thinking ContextClosedEvent means all beans have been destroyed. **Wrong:** it is published before the normal stop/destroy phase.

**7.** Not enabling graceful web shutdown in Boot 3.3 while expecting in-flight draining. **Required:** server.shutdown=graceful.

**8.** Setting timeout-per-shutdown-phase=20s and concluding every JVM stops in exactly 20 seconds. **Wrong:** multiple phases and OS grace periods still apply.

**9.** Having @PreDestroy call a remote API without a timeout. **Consequence:** hangs shutdown or gets killed by the OS before finishing.

**10.** Believing HTTP graceful shutdown automatically pauses schedulers, Kafka, or RabbitMQ. **Wrong:** each workstream needs its own stop policy.

**11.** Closing the same resource in a JVM hook, a ContextClosedEvent listener, and @PreDestroy. **Consequence:** double-close and race conditions.

**12.** Treating a request exception after Ready as an ApplicationFailedEvent. **Wrong:** startup events differ from runtime errors.

**13.** Setting custom setRegisterShutdownHook(false) but forgetting to close the context manually. **Consequence:** missing cleanup on JVM shutdown.

**14.** Catching a runner's RuntimeException and only logging it even when a mandatory startup condition failed. **Consequence:** the service may report ready erroneously.

**15.** Failing to handle restarts/crashes idempotently. **Consequence:** incomplete side effects may be duplicated or lost on forced shutdown.

## 15. Self-Check Questions

**Question 1:** Is context.close() equivalent to System.exit(0) by default?  
**Answer:** No. It only closes the Spring context.

**Question 2:** What does SpringApplication.exit(context) return?  
**Answer:** An int exit code; it also closes the context if possible.

**Question 3:** Does Boot 3.3 register a JVM shutdown hook automatically?  
**Answer:** Yes, setRegisterShutdownHook defaults to true.

**Question 4:** Do two custom JVM shutdown hooks run in the order they were registered?  
**Answer:** There is no guarantee; they may run concurrently.

**Question 5:** How do SIGTERM and SIGKILL differ?  
**Answer:** SIGTERM normally triggers JVM shutdown hooks; SIGKILL forces termination.

**Question 6:** What is needed to drain requests in Spring Boot 3.3?  
**Answer:** Enable server.shutdown=graceful and choose an appropriate shutdown timeout.

**Question 7:** Is ContextClosedEvent published before or after @PreDestroy normally?  
**Answer:** Before bean destruction in a normal close.

**Question 8:** When must SmartLifecycle's stop(Runnable) invoke the callback?  
**Answer:** When stopping has actually completed.

**Question 9:** If ApplicationRunner throws an exception, does ApplicationReadyEvent appear as in the success path?  
**Answer:** No.

**Question 10:** Does an HTTP request throwing an exception automatically shut down the JVM?  
**Answer:** Usually not.

**Question 11:** Are shutdown hooks guaranteed to run when the host loses power?  
**Answer:** No.

**Question 12:** A container has terminationGracePeriodSeconds configured but still receives kill -9; why?  
**Answer:** The deadline may have expired or the runtime/orchestrator forced termination; cleanup had not finished.

**Conclusion:** To stop Spring Boot properly, clearly distinguish **closing the context**, **JVM shutdown**, and **forced termination**. **context.close** closes managed resources; **SpringApplication.exit** returns an exit code; **System.exit/SIGTERM** normally route the JVM through shutdown hooks; **SIGKILL/halt/crash** bypass reliable cleanup. On **Spring Boot 3.3**, enable **server.shutdown=graceful** and configure enough time for SmartLifecycle, HTTP drain, and resource cleanup. Always design for idempotency and recovery because shutdown callbacks cannot be assumed to run in every scenario.

### References

- [Spring Boot 3.3 — Application Exit, Startup Failure, and Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Framework — Lifecycle/Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Java SE 21 — Runtime Shutdown Hooks](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html)
