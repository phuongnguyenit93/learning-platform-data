# Relationship Between DevTools Restart, Shutdown Hooks, and Resource Cleanup in Spring Boot

## 1. The Problem: Code Edited, DevTools Restarts, Yet Old Resources Remain

When developing a Spring Boot application, **spring-boot-devtools** can automatically restart the application after classes on the classpath are compiled and changed. This makes the edit cycle faster than restarting the entire JVM. However, restarts can introduce subtle bugs:

- After multiple code edits, the number of background threads keeps growing.
- TCP ports or file handles from the previous context are not released.
- An old scheduled task and a new task run simultaneously.
- The connection pool was re-initialized, yet old connections remain open.
- `ThreadLocal`s, listeners, or caches hold objects loaded by the old classloader.
- DevTools fails to restart properly after code disables the shutdown hook.
- The first restart works fine, yet the third reports "port already in use".

To solve these issues, you must understand the relationship between **DevTools restart**, **`ApplicationContext.close()`**, the **SpringApplication shutdown hook**, **bean destruction callbacks**, and the **JVM/classloader lifecycle**.

~~~text
JVM keeps running
   |
   +-- DevTools base ClassLoader      (stable libraries)
   |
   +-- RestartClassLoader #1         (application classes pass #1)
   |        |
   |        +-- ApplicationContext #1
   |        +-- Bean resources #1
   |        +-- HTTP server / scheduler / listeners
   |
   +-- Classpath changed -> restart requested
   |        |
   |        +-- Close ApplicationContext #1
   |        |       +-- ContextClosedEvent
   |        |       +-- SmartLifecycle.stop(...)
   |        |       +-- @PreDestroy / destroy callbacks
   |        |
   |        +-- Drop references to RestartClassLoader #1
   |
   +-- RestartClassLoader #2
            |
            +-- ApplicationContext #2
            +-- Bean resources #2
            +-- New server / scheduler
   |
   +-- JVM continues running, PID usually unchanged
~~~

**Operational rule of this lesson:** DevTools can swap the `ApplicationContext` and restart classloader, yet **it cannot automatically close resources created by the application outside Spring's lifecycle**. If a thread, socket, timer, or static cache retains a reference to the old classloader, the JVM can still keep most old objects in memory.

This lesson uses **Java 17+, Spring Boot 3.3.13, Maven, and `spring-boot-devtools`**. The accompanying example runs in a development environment; never use DevTools in production.

## 2. What Is a DevTools Restart Really?

Per Spring Boot 3.3 documentation, the **automatic restart** mechanism uses two classloaders:

1. **Base classloader:** contains stable dependency JARs, typically third-party libraries. It is retained across restart cycles.
2. **Restart classloader:** contains classes of the project under active development, typically read from mutable classpath directories like **`target/classes`**. On restart, DevTools discards this classloader and creates a new instance.

Retaining the base classloader usually makes restarts faster than cold starts: already-loaded library classes do not have to initialize from scratch.

### 2.1. Restart Differs from Reload

| Concept | Impact |
| --- | --- |
| **DevTools restart** | Closes the old application context, rebuilds the context and restart classloader |
| **LiveReload** | Signals the browser to refresh when matching resources change; does not mean JVM/context restart |
| **IDE hot code replace** | Replaces certain running bytecodes if supported by debugger/JVM; does not necessarily create a new context |
| **JVM process restart** | Old process terminates, a new process is spawned by the OS with a new PID |
| **Kubernetes rollout** | Replaces instances/containers; operates outside the JVM |
| **`ApplicationContext.refresh()`** | Refreshes a context per its contract; not automatically equivalent to a DevTools restart |

**Do not confuse DevTools restart with "re-running main in a new JVM".** DevTools re-runs application bootstrapping inside the current JVM via a new classloader. Certain components and state residing in the base classloader can survive across multiple restarts.

### 2.2. When Does DevTools Auto-Restart?

DevTools watches **resources on the classpath**. Editing a **`.java` file in the source directory** will not trigger a restart if the IDE has not compiled and copied the new class to the output directory.

Common ways this happens:

- Eclipse can compile on save.
- IntelliJ IDEA requires **Build Project** or properly configured auto-build.
- Maven **`mvn compile`** or Gradle builds write new classes to the output path.
- A trigger file can be used to control restart timing.

Static resources and templates can be handled by DevTools via **LiveReload** without a full application restart, depending on configuration.

### 2.3. Restart Does Not Mean Every Edit Starts a New Cycle

Do not assume every Save closes the context. An edit that does not change classpath output, or matches paths excluded from restart, may only trigger a reload or no restart at all.

To verify a genuine restart occurred, inspect the **context instance** and a **resource ID** generated when a new bean is created—not how many times the user pressed Ctrl+S.

## 3. What Is a Shutdown Hook in Spring Boot?

By default, **`SpringApplication`** registers a shutdown hook with the JVM so the `ApplicationContext` is closed when the process goes through a normal shutdown path.

Related API:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

// Default is true. Do not disable when relying on DevTools restart.
application.setRegisterShutdownHook(true);
application.run(args);
~~~

This is a **snippet**; it requires defining `MyApplication` and corresponding imports. SpringApplication 3.3 docs state **`setRegisterShutdownHook(...)` defaults to `true`** to support closing the context on JVM shutdown.

Spring Boot 3.3 DevTools explicitly states that **restart relies on the application context shutdown hook** to close the old context. If you use:

~~~java
application.setRegisterShutdownHook(false);
~~~

DevTools **will not work properly** per official documentation. Disabling this mechanism merely to make console output look cleaner or to manage server stopping manually is not recommended.

### 3.1. Distinguishing Three Easily Confused Actions

| Action | Description | Important Detail |
| --- | --- | --- |
| **Registering the shutdown hook** | `SpringApplication` sets up context closure on JVM shutdown | DevTools needs this mechanism enabled |
| **Closing `ApplicationContext`** | Spring invokes stop/destroy lifecycles on managed beans | Happens during DevTools restart without JVM exit |
| **JVM running `Runtime` shutdown hooks** | The JVM begins an actual process shutdown | Does not happen by default on every DevTools restart |

A **DevTools restart is not a JVM shutdown**. When the old application context closes, Spring callbacks like **`@PreDestroy`** run. However, **do not assume the JVM executes threads registered by the app via `Runtime.addShutdownHook(...)` after every reload**.

This is the core boundary of this lesson: **Spring bean destruction callbacks** are tied to context closure; **`Runtime.addShutdownHook`** is tied to JVM termination.

### 3.2. Why the Phrase "Shutdown Hook" in DevTools Causes Confusion

DevTools docs say: restart requires the **application context's shutdown hook** to close the context. That refers to the integration between DevTools and `SpringApplication`'s context-closing mechanism. It does not mean DevTools simulates **`System.exit()`** or sends `SIGTERM` whenever the classpath changes.

If your logs show:

~~~text
CONTEXT_CLOSING ...
RESOURCE_DESTROY ...
NEW_CONTEXT_STARTED ...
~~~

that is evidence the context closed and was recreated. It **does not prove the whole JVM ran its shutdown sequence** or that all custom JVM hooks ran.

### 3.3. When Should You Call context.close() Manually?

In a CLI program or integration test that must terminate deliberately, **`context.close()`** directly asks Spring to close the current context's lifecycle.

In a web app using DevTools, **never add `context.close()` right after `SpringApplication.run(...)`**: the app would immediately close the server when `main` returns instead of waiting for DevTools/watchers and developer requests.

For long-running applications, let `SpringApplication`/DevTools coordinate the context; close manually only as a designed, controlled lifecycle operation.

## 4. What Gets Cleaned Up When Closing ApplicationContext?

Spring manages lifecycles for properly registered beans. During a normal context close, participating mechanisms include:

- **`ContextClosedEvent`:** event signaling the context is closing.
- **`SmartLifecycle.stop(...)`** and ordered stop phases.
- **`@PreDestroy`:** destruction callback on the corresponding managed bean.
- **`DisposableBean.destroy()`:** Spring's destruction interface.
- **`@Bean(destroyMethod = "close")`** or another destroy method.
- **`AutoCloseable` / `Closeable`** where bean definition inference applies.
- **Embedded WebServer stop:** releases the port and request infrastructure as supported by the server.
- **Executor/scheduler bean shutdown:** depending on the bean, config, and task-awaiting policy.

For most standard beans, Spring invokes destruction callbacks when **`ApplicationContext.close()`** occurs. Yet there is **no guarantee all custom resources outside the context will close**, and crashes/hard kills do not guarantee callbacks run.

### 4.1. ContextClosedEvent Is Not @PreDestroy

| Mechanism | Role | Limitation |
| --- | --- | --- |
| **`ContextClosedEvent`** | Notifies listeners that the context is closing | Not a good place to block indefinitely |
| **`SmartLifecycle.stop(callback)`** | Stops active lifecycle components; supports phases and callbacks | Must invoke completion callback; avoid deadlocks |
| **`@PreDestroy`** | Releases resources owned by the bean | Runs only if bean is managed and context reaches destruction |
| **`DisposableBean.destroy`** | Spring-specific destruction contract | Increases coupling to Spring |
| **`@Bean destroyMethod`** | Declares close method for third-party beans | Requires matching signature and ownership |
| **`Runtime.addShutdownHook`** | Callback on JVM shutdown | Not a per-DevTools-restart callback |

During normal context closure, **`ContextClosedEvent`** is published and lifecycle components stop before general destruction. Never write code relying on strict ordering across arbitrary custom beans, especially with async listeners, differing phases, or bootstrap errors.

### 4.2. Spring Cleans Up Only Resources It Knows About

Bad example:

~~~java
@Component
class WorkerStarter {

    @PostConstruct
    void begin() {
        Thread thread = new Thread(() -> loopForever());
        thread.start();
    }
}
~~~

This is an **anti-pattern snippet**, assuming a `loopForever()` method. Spring knows the **`WorkerStarter`** bean, yet **does not know** how to cancel a manually spawned `Thread`. Without a stop flag, interrupt/join, or shutdown policy, the old thread can keep running after a DevTools restart.

If an old thread retains the context classloader or a reference to an application bean, it can pin classes/objects of the old restart classloader in memory and cause a **classloader leak**.

### 4.3. Registering Resources Outside Spring Leaves Cleanup Without an Owner

Examples requiring explicit management:

- **`ExecutorService`** created via `Executors.newFixedThreadPool` or `newSingleThreadScheduledExecutor`.
- Manually created **`Timer` / `TimerTask`**.
- **`ServerSocket` / `Socket` / `FileChannel` / `WatchService`**.
- **`JDBC Connection`** opened and held directly outside a pool.
- Third-party **HTTP client/connection manager** with a `close`/`shutdown` API.
- **MBean registered manually** with the platform `MBeanServer`.
- **Listeners/callbacks** registered in a non-Spring registry.
- **Global static caches**, `ThreadLocal`s, or callbacks in singleton libraries holding application classes.

If a resource is created inside a bean, ensure **that bean also closes the resource** when destroyed. For library-created resources, use an adapter bean and `destroyMethod`.

## 5. Why Do Resource Leaks Surface Easily with DevTools?

In a brand-new JVM launch, some leaks go unnoticed because when the process dies, the OS reclaims file descriptors and TCP sockets, and JVM memory vanishes.

However, DevTools keeps the JVM alive across multiple restart cycles:

~~~text
Start #1:
  classloader 1 -> executor 1 -> 2 threads

Restart #1, missing cleanup:
  classloader 1 -> executor 1 -> 2 threads STILL RUNNING
  classloader 2 -> executor 2 -> 2 threads

Restart #2, missing cleanup:
  classloader 1 -> executor 1 -> 2 threads
  classloader 2 -> executor 2 -> 2 threads
  classloader 3 -> executor 3 -> 2 threads

Result:
  multiple tasks running concurrently, heap retains old classloaders,
  resources and logs multiply.
~~~

If beans shut down cleanly, the old executor stops and the old classloader is no longer referenced by those activities. GC reclaiming the classloader is **possible once no strong references remain**, though not guaranteed instantaneously after each DevTools restart.

### 5.1. Restart Classloader and Base Classloader Complicate Leaks

DevTools typically places application classes in the **restart classloader** and library JARs in the **base classloader**. A singleton or static cache inside a base-classloader library can retain references to objects from the restart classloader.

Example of a library registering callbacks without unregistering:

~~~text
BaseClassLoader
   |
   +-- GlobalRegistry static Map
           |
           +-- callback from RestartClassLoader #1
           +-- callback from RestartClassLoader #2
           +-- callback from RestartClassLoader #3
~~~

Because the base classloader stays alive, that map can pin multiple old application classloaders. In this case, merely creating new Spring beans does not remove the previous context's callbacks without explicit unregistration.

**Solution:** when `@PostConstruct` registers with a registry, `@PreDestroy` must unregister the exact instance/token; or use an `AutoCloseable` resource wrapper.

### 5.2. Thread Context ClassLoader Can Also Pin References

A thread spawned from application code inherits the current thread's **`Thread.contextClassLoader`**. If the thread stays alive after restart, it can keep a reference to the old restart classloader even when no longer directly invoking application methods.

**Do not try fixing leaks simply by calling `thread.setContextClassLoader(null)`.** That may drop one reference path, yet it does not close sockets, stop work, or unregister callbacks. Stop resources through proper lifecycle management.

### 5.3. Static Fields Do Not Necessarily "Live Forever" After DevTools Restart

Static state of a class **loaded in the restart classloader** is scoped to that classloader, so creating a new classloader produces a fresh static copy.

Conversely, static state of a class **residing in the base classloader** can persist across multiple restarts.

Therefore, do not assume every static counter keeps incrementing across restarts, or that every static cache resets. Behavior depends on **which loader loaded the class and which references remain**.

## 6. Runnable Spring Boot 3.3 Example: Observing OPEN / CLOSE / OPEN

The Java 17+ project below creates:

1. A Spring MVC/Tomcat web app to keep the process alive.
2. A **`ManagedPollingResource`** bean creating a local scheduled executor.
3. **`@PostConstruct`** opening the resource.
4. **`@EventListener(ContextClosedEvent.class)`** logging when the context closes.
5. **`@PreDestroy`** shutting down the executor with a bounded wait and interruption handling.
6. **`ApplicationRunner`** printing the resource ID, PID, and classloader.
7. A development endpoint **`GET /debug/resource`** to inspect the current context instance.

When you edit a class and build, DevTools restarts the context. A **new resource ID** appears; the old resource logs `CLOSE` during shutdown. The **PID** normally stays the same because the JVM did not restart.

### 6.1. Maven Structure

~~~text
devtools-lifecycle-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/devtools/DevtoolsLifecycleDemo.java
  src/test/java/com/example/devtools/ManagedResourceTest.java
~~~

**Prerequisites:** JDK 17+, Maven, and an IDE or terminal able to compile onto the classpath while the app is running.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>devtools-lifecycle-demo</artifactId>
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
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Note that DevTools is a development-time dependency.** Maven marks it optional so it is not propagated transitively to consuming modules. The Spring Boot Maven plugin excludes DevTools from repackaged executable archives by default. Never force-enable DevTools for production by altering packaging exclusions.

### 6.3. application.properties

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s

spring.devtools.restart.enabled=true
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

Meaning:

- **`spring.devtools.restart.enabled=true`:** enables restart functionality when DevTools runs in an eligible development environment.
- **`server.shutdown=graceful`:** on context closure, Tomcat grants in-flight HTTP requests a grace window and rejects new requests per Boot 3.3 mechanics.
- **`spring.lifecycle.timeout-per-shutdown-phase=10s`:** timeout limit per `SmartLifecycle` phase.
- **`log-condition-evaluation-delta=false`:** reduces condition-diff logs on restart; does not alter cleanup logic.

Graceful web shutdown only handles the embedded web server; the **background executor in the example still requires its own shutdown policy**.

### 6.4. Complete Java Application

Create **`src/main/java/com/example/devtools/DevtoolsLifecycleDemo.java`**:

~~~java
package com.example.devtools;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DevtoolsLifecycleDemo {

    public static void main(String[] args) {
        // Keep the default shutdown hook: DO NOT call
        // application.setRegisterShutdownHook(false).
        SpringApplication.run(DevtoolsLifecycleDemo.class, args);
    }

    @Bean
    ApplicationRunner startupLog(ManagedPollingResource resource) {
        return args -> System.out.println(
                "RUNNER id=" + resource.id()
                + " pid=" + ProcessHandle.current().pid()
                + " loader="
                + DevtoolsLifecycleDemo.class.getClassLoader()
                        .getClass().getName());
    }
}

@Component
class ManagedPollingResource {

    private final String id =
            UUID.randomUUID().toString().substring(0, 8);

    private final AtomicBoolean closed = new AtomicBoolean();
    private ScheduledExecutorService executor;

    @PostConstruct
    void start() {
        executor = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(
                    task, "demo-poll-" + id);
            thread.setDaemon(true);
            return thread;
        });

        System.out.println("OPEN id=" + id);

        executor.scheduleWithFixedDelay(
                () -> System.out.println("TICK id=" + id),
                0, 3, TimeUnit.SECONDS);
    }

    @EventListener(ContextClosedEvent.class)
    void onClosing() {
        System.out.println("CONTEXT_CLOSING id=" + id);
    }

    @PreDestroy
    void cleanup() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        System.out.println("CLOSE id=" + id);

        ScheduledExecutorService current = executor;
        if (current == null) {
            return;
        }

        current.shutdown();

        try {
            if (!current.awaitTermination(2, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    String id() {
        return id;
    }

    boolean isClosed() {
        return closed.get();
    }
}

@RestController
class ResourceDebugController {

    private final ManagedPollingResource resource;

    ResourceDebugController(ManagedPollingResource resource) {
        this.resource = resource;
    }

    @GetMapping("/debug/resource")
    Map<String, String> info() {
        return Map.of(
                "resourceId", resource.id(),
                "pid", Long.toString(ProcessHandle.current().pid()),
                "closed", Boolean.toString(resource.isClosed()),
                "classLoader",
                DevtoolsLifecycleDemo.class.getClassLoader()
                        .getClass().getName());
    }
}
~~~

**Why is this code valid?**

- **`DevtoolsLifecycleDemo`** is a public top-level class matching the filename; the remaining classes are package-private in the same package.
- **`@SpringBootApplication`** and component scanning discover **`@Component`** and **`@RestController`**.
- **`@PostConstruct`/`@PreDestroy`** use **`jakarta.annotation`** compatible with Spring Boot 3.x.
- **`ManagedPollingResource`** owns the executor as a bean resource, so when the bean is destroyed it can close it.
- **`AtomicBoolean`** makes cleanup **idempotent** if invoked multiple times in a test scenario.
- **`shutdown()`** stops accepting new tasks; **`awaitTermination(2s)`** waits with a bound; **`shutdownNow()`** requests cancellation/interruption on timeout.
- The worker thread is marked daemon in the demo, which is not a fix for resource leaks; threads must still be stopped when the context closes.
- **`ApplicationRunner`** runs after refresh; the PID printed via `ProcessHandle.current().pid()` helps compare across restarts.
- The **`/debug/resource`** endpoint is a learning tool—**do not expose runtime or classloader details in production**.

### 6.5. What Not to Infer from the Demo

There is no guarantee that **`TICK`** appears after every `RUNNER` line, because the scheduler runs on a separate thread and logs may interleave. There is no arithmetic pattern to object IDs; each is randomly generated when a new bean is created.

After a successful DevTools restart, typical output looks like:

~~~text
OPEN id=<old-id>
RUNNER id=<old-id> pid=<same-pid> loader=<restart-loader>
TICK id=<old-id>

... classpath changes ...

CONTEXT_CLOSING id=<old-id>
CLOSE id=<old-id>
OPEN id=<new-id>
RUNNER id=<new-id> pid=<same-pid> loader=<restart-loader>
TICK id=<new-id>
~~~

**This is an illustrative log format, not immutable literal stdout.** The ID, PID, classloader name, and `TICK` timing depend on the environment. What matters is that **the old ID logs `CLOSE` during/before replacement by the new ID**, and **no `TICK` from the old resource appears after cleanup finishes**.

### 6.6. Building and Running in Development Mode

From the project directory:

~~~bash
java -version
mvn spring-boot:run
~~~

**`mvn spring-boot:run`** runs against the development classpath, where DevTools can watch classes in the output directory. When using Maven/Gradle build plugins, keep **forking** enabled so DevTools gets an isolated application classloader per Boot 3.3 docs.

In another terminal:

~~~bash
curl http://localhost:8080/debug/resource
~~~

Illustrative response example:

~~~json
{
  "resourceId": "7d5e28f0",
  "pid": "12345",
  "closed": "false",
  "classLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader"
}
~~~

**Do not assert literally** on `resourceId`, PID, or classloader name. Check your own running instance: if `classLoader` is not similar to the restart loader, DevTools may not be active under the current launch setup.

### 6.7. Triggering a Real DevTools Restart

In your IDE, edit a Java line without breaking compilation, save, and run **Build Project** if the IDE does not auto-compile classpath output. From a terminal, after editing source you can run in a separate terminal:

~~~bash
mvn compile
~~~

DevTools watches the classpath directory. Once the compiler updates `.class` in **`target/classes`**, DevTools detects it and restarts. Not every Save triggers a restart if code has not been compiled.

Call again:

~~~bash
curl http://localhost:8080/debug/resource
~~~

Verify:

- The new **`resourceId`** differs from the previous value (UUID, almost certainly).
- **`pid`** normally stays the same during a DevTools restart.
- The console shows **`CONTEXT_CLOSING`/`CLOSE`** for the old ID and **`OPEN`/`RUNNER`** for the new ID.
- Only one stream of `TICK` lines from the current ID appears after the restart completes.
- If editing a class causes the IDE to kill/relaunch the process, the PID changes: that is a **process restart**, not an internal DevTools restart.

**Do not use `java -jar target/...jar` to test default DevTools restart.** Spring Boot 3.3 normally disables DevTools when running a fully packaged application; DevTools is also excluded from repackaged JARs by default.

### 6.8. Stopping the App in the IDE or with Ctrl+C

When the process terminates via a normal shutdown path, Spring gets a chance to close the context and run **`@PreDestroy`** on beans. If the IDE uses hard terminate or the JVM is forcibly killed, cleanup callbacks are not guaranteed.

A DevTools restart while the JVM stays alive is **not** the same action as Ctrl+C / `SIGTERM` terminating the entire process. Check the logs and PID to confirm which operation actually occurred.

## 7. JUnit 5: Testing Bean Destruction Without Pretending to Simulate DevTools

You can verify that context closure invokes **`@PreDestroy`** using a small Spring context, without enabling DevTools or starting a real server.

Create **`src/test/java/com/example/devtools/ManagedResourceTest.java`**:

~~~java
package com.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagedResourceTest {

    @Test
    void closingContextCleansUpManagedExecutor() {
        ManagedPollingResource resource;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(ManagedPollingResource.class);
            context.refresh();

            resource = context.getBean(ManagedPollingResource.class);
            assertFalse(resource.isClosed());
        }

        // try-with-resources already called context.close().
        assertTrue(resource.isClosed());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This test verifies that **the bean is Spring-managed**, initialized, and that closing the context triggers the destruction callback setting **`closed=true`**.

**Test scope:** it does not create a DevTools restart classloader or simulate classpath changes. Pure Spring lifecycle tests ensure the resource's cleanup contract works **independently** of how DevTools orchestrates restarts.

### 7.1. What Test Proves DevTools Actually Closes Old Resources?

A dev-environment integration/smoke test should:

1. Start the app with **`mvn spring-boot:run`** with DevTools active.
2. Record an initial resource ID and PID.
3. Edit and compile an application class to trigger a restart.
4. Observe **`CONTEXT_CLOSING`** and **`CLOSE`** for the old resource ID.
5. Observe **`OPEN`** and **`RUNNER`** for the new resource ID.
6. Wait across two or three poller intervals to detect any leaked `TICK`s from the old ID.
7. Verify thread/port/handle counts do not grow across restart cycles.
8. Repeat across several cycles to catch cumulative leaks rather than just one restart.

Do not rely solely on **`@SpringBootTest contextLoads`**: it does not exercise IDE DevTools restarts and can pass even when dev/production lifecycles diverge.

### 7.2. Do Not Write Tests Relying on Exact Stdout Timing

Because the poller runs asynchronously, a `TICK` line may appear before or after `RUNNER`. Tests should assert **the old resource stopped after close**, not strict ordering across multi-threaded logs.

To test termination, use a **`CountDownLatch`** or executor state assertions with a short deadline, rather than just **`Thread.sleep(1000)`** hoping tasks stop on their own.

## 8. Proper Lifecycle for Each Resource Type

### 8.1. Manually Created ExecutorService

If a bean owns an `ExecutorService`, shut it down explicitly on destruction:

~~~java
@Component
class WorkerOwner {

    private final ExecutorService workers =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void stop() {
        workers.shutdown();

        try {
            if (!workers.awaitTermination(3, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        } catch (InterruptedException ex) {
            workers.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

This snippet requires imports and task submission code. **`shutdownNow()` only requests interruption**—it does not guarantee every task honors interrupts or stops immediately. Ensure tasks have timeouts and clean exit logic.

Better when possible: use Spring-managed executors/schedulers configured with destroy/lifecycle policies so the framework coordinates shutdown.

### 8.2. @Scheduled and Spring-Managed TaskScheduler

With **`@EnableScheduling`** and a `TaskScheduler` bean in the context, Spring manages the scheduler lifecycle. When the context closes, the scheduler stops according to its bean configuration.

However, **an active `@Scheduled` job is not automatically allowed to finish indefinitely** across a DevTools restart. If the job writes to a database, sends messages, or calls external APIs, clarify:

- Can the job safely be interrupted?
- Must it commit before a new instance starts?
- Could two contexts overlap while handing off?
- Are idempotency and transaction boundaries in place?
- Are timeouts and post-restart retries handled if critical?

Never treat DevTools restart as a durable job scheduler or an exactly-once execution guarantee.

### 8.3. TCP Sockets and File Handles

A resource like **`ServerSocket`** or **`FileChannel`** can be closed with **`close()`**. If created as a Spring-owned bean, declare its destruction method:

~~~java
@Configuration(proxyBeanMethods = false)
class SocketConfiguration {

    @Bean(destroyMethod = "close")
    ServerSocket localSocket() throws IOException {
        return new ServerSocket(0);
    }
}
~~~

This snippet requires imports and a valid configuration setup; port 0 requests an OS-assigned ephemeral port. This illustrates bean ownership only, without an accept loop or complete protocol server.

When the context closes, Spring calls `close` on the socket bean. If that same socket were created via **`new` inside a static initializer** without lifecycle management, Spring would not know to close it.

### 8.4. Database Connection Pools

Spring Boot's auto-configured **`DataSource`/HikariCP** is registered as a bean with corresponding pool shutdown lifecycle. When DevTools restarts the old context, the managed pool closes cleanly before the new pool is created.

If the app manually instantiates another `HikariDataSource` outside the bean container and never calls `close`, it can leak connections and worker threads across restarts. Do not blame DevTools or Hibernate for missing bean ownership.

Distinguish between:

- **A managed `DataSource` bean**: Spring manages destruction.
- **Connections borrowed from the pool**: code must close connection handles after each operation/transaction.
- **Manually created custom connection pools**: the owner must hook `close` into the lifecycle.

### 8.5. Messaging Consumers and Observers

Kafka/RabbitMQ/JMS consumers create threads, listeners, and connections. When inside Spring-managed listener containers, the framework provides lifecycle stop/close. If you register listeners manually in an external/global registry, the bean must **unregister** on close.

Do not let the new context start consuming concurrently while the old context has not finished stopping if business rules forbid overlap. During testing, use event IDs and client instance IDs to catch duplicate processing.

### 8.6. File WatchService, Timer, ThreadLocal, and Callbacks

The following are especially easy to forget:

- **`WatchService`** has a `close` API.
- **`Timer`** has a `cancel` API.
- **`ThreadLocal`** values on reused threads must be cleared via `remove()`.
- Manually registered **MBeans** must be unregistered.
- **Global event bus callbacks** must remove listeners.
- **Static caches** holding application classes must invalidate/unregister.
- **Third-party schedulers** must be shut down/disposed per library contract.

**Ownership principle:** whichever component creates or registers a resource must know exactly when and via which API to release it.

## 9. Why Runtime.addShutdownHook Does Not Replace @PreDestroy

A common anti-pattern:

~~~java
@PostConstruct
void registerJvmHook() {
    Runtime.getRuntime().addShutdownHook(
            new Thread(() -> cleanupExternalResource()));
}
~~~

This is an illustrative snippet assuming `cleanupExternalResource()`. Problems:

- The hook binds to **JVM shutdown**, not DevTools restarts.
- Each newly created bean after a restart registers yet another hook.
- The runtime holds references to the `Thread`/callback, which can pin the old application classloader.
- Multiple hooks may try closing the same resource in the wrong order or fail.
- If the JVM receives `SIGKILL`, hooks do not run at all.

**Prefer `@PreDestroy` or bean `destroyMethod`** for context-scoped resources. If a library mandates registering a JVM hook, understand unregistration or manage the hook at a JVM-lifetime layer, keeping in mind `Runtime.removeShutdownHook` limitations once JVM shutdown has begun.

### 9.1. The Spring Shutdown Hook Must Still Be Registered

Do not misread the section above as "disable all shutdown hooks". The **default `SpringApplication` shutdown hook must be kept** for DevTools restart to work properly per Boot 3.3 docs.

Separate the two rules:

- **Keep** the shutdown hook managed by `SpringApplication` (do not call `setRegisterShutdownHook(false)`).
- **Do not abuse** `Runtime.addShutdownHook` for resources scoped to an `ApplicationContext` that DevTools may restart.

### 9.2. What If a Library Registers Its Own JVM Hook?

Some libraries register global hooks to close resources. If the library is loaded by the base classloader and its hook/registry persists across restarts, check whether it exposes a shutdown/reset API or can integrate with a Spring-managed bean.

If no clean cleanup hook exists, consider disabling DevTools restart in dev environments using that library or configuring classloader rules, while **never assuming changing classloaders fixes a resource leak by itself**.

## 10. SmartLifecycle When Ordered Shutdown Is Needed

A bean owning a background consumer can implement **`SmartLifecycle`** instead of only `@PreDestroy` when it needs to:

- Auto-start after context refresh.
- Stop in phase order before or after other components.
- Accept a completion callback for asynchronous stopping.
- Coordinate dependencies with HTTP servers, executors, or connection pools.

Conceptual pattern:

~~~java
@Component
class MyConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start consumer
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
            // stop accepting new work; drain bounded tasks
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This is a **snippet without a real consumer implementation**, requiring `SmartLifecycle` and `Component` imports. The key requirement is that **`stop(Runnable callback)`** must invoke `callback.run()` once stopping finishes, even on error, so the lifecycle processor knows the phase can proceed.

A production implementation needs a thread-safe state machine, timeouts, idempotent `stop`, and failure handling. **Never block indefinitely in `stop(...)` or wait on the very thread running `stop`**, as that can hang a DevTools restart.

### 10.1. What Does Phase Mean?

Per Spring Framework, `SmartLifecycle` beans have a **phase** determining start/stop ordering. In general:

- Higher phases **start later and stop earlier** than lower phases.
- Lower phases **start earlier and stop later**.
- Dependencies can adjust actual ordering.

For Boot web servers, graceful shutdown occurs in an early phase of the stop lifecycle. If an HTTP request needs a background executor or datasource, do not configure that component to stop too early and break in-flight request completion.

### 10.2. @PreDestroy Remains Useful After SmartLifecycle.stop

If `SmartLifecycle.stop` handles **stopping new intake and draining**, `@PreDestroy` can serve as the **final resource-closing layer**. Both callbacks should be idempotent, avoid throwing unchecked exceptions, and never assume `stop` always precedes `destroy` in abnormal failure scenarios.

Spring Framework notes that certain failure paths may invoke `destroy` without a preceding `stop`. Destruction logic must therefore be safe on its own.

## 11. Graceful Shutdown and DevTools Restart

For web applications, you can enable:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

When the context closes via normal lifecycle paths, Boot lets the embedded server wait for in-flight requests and reject new ones within the timeout. This applies to contexts replaced by DevTools if the server shuts down through the normal lifecycle path.

However:

- DevTools restart **is not** a rolling deployment.
- Requests in an IDE may still be interrupted on restart; this is not a zero-downtime guarantee.
- WebSocket/SSE streams or long requests may exceed the timeout.
- Executors/background tasks have their own shutdown policies.
- When an IDE performs a hard terminate, graceful shutdown hooks may not run.

In Boot 3.3, **`server.shutdown=graceful`** must be enabled explicitly if desired (Boot 3.3 defaults to immediate). Do not confuse this with newer Spring Boot versions that have different defaults.

### 11.1. Why Should Background Executors Shut Down with a Bound?

If `@PreDestroy` calls `executor.awaitTermination` indefinitely, every DevTools restart can hang. Always set a deadline and cancellation fallback. If a task holds a lock that the destruction callback waits on, a deadlock can happen.

With DevTools, this bug surfaces easily because developers restart constantly. A resource owner should stop accepting work, wait a bounded duration, request cancellation, and log if clean termination fails.

### 11.2. What If a Long Job Must Finish Before Restarting?

DevTools is a development tool; if work must never be lost, use a durable job system or checkpointing. Do not raise the grace period to minutes relying on it for data integrity.

You can temporarily disable restart while debugging long jobs or use a trigger file so restarts only happen when ready, though **neither replaces retry/idempotency** in production.

## 12. Disabling Restart Properly to Isolate Bugs

If you suspect a classloader or cleanup bug, test a run **without DevTools restart** and compare.

Disable via config:

~~~properties
spring.devtools.restart.enabled=false
~~~

Per Boot 3.3 docs, this normally **stops watching for file changes**, though part of the restart infrastructure/classloader may still initialize.

To **disable restart support completely**, set the **system property before calling `SpringApplication.run(...)`**:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

This snippet requires a matching `MyApplication` class. Or configure the JVM at launch:

~~~bash
java -Dspring.devtools.restart.enabled=false -cp ... com.example.MyApplication
~~~

This line illustrates the JVM flag; **`...`** must be replaced with your real development classpath, not run verbatim. With the Maven plugin, configure JVM arguments appropriately rather than assuming flags after the run goal are JVM options.

**Never disable the `SpringApplication` shutdown hook to "turn off DevTools".** Those are two separate mechanisms; disabling the hook breaks context cleanup during restarts.

### 12.1. Trigger Files Make Restarts Less Surprising

If the IDE compiles continuously, you can use:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Create **`src/main/resources/.reloadtrigger`** and update it after classes change to trigger a restart check.

A trigger file helps when you want to edit multiple classes before restarting. However, it **cannot fix uncleaned resources**. Even with manual restarts, the old context must still close all resources.

### 12.2. Excluding Resources That Do Not Need Restart

By default DevTools does not trigger full restarts for certain static resources/templates. You can configure **`spring.devtools.restart.additional-exclude`** to append exclusion patterns while keeping defaults.

Never exclude an important application classes directory merely to avoid a cleanup bug; that hides the bug instead of fixing the lifecycle.

## 13. Classloader Issues and Diagnosis

Some errors appear only when the restart loader swaps:

- **`ClassCastException`** when a class of the same name is loaded by two different loaders.
- Deserializing objects with `ObjectInputStream` without using the right context classloader.
- Reflection caches retaining `Class<?>` from an old restart loader.
- `ThreadContextClassLoader` causing service loaders to pick the wrong class.
- Multi-module projects splitting loaders awkwardly.
- Static registries in library JARs holding callbacks from an application loader.

When DevTools restart fails while a full JVM launch succeeds, disable restart to confirm the difference. If caused by classloader partitioning, Spring Boot supports **`META-INF/spring-devtools.properties`** with **`restart.include`** and **`restart.exclude`** to adjust which loader handles which classpath segments.

Illustrative example of a configuration file:

~~~properties
restart.include.project-shared=/project-shared-[^/]+[.]jar
restart.exclude.legacy-module=/legacy-module-[^/]+/
~~~

**These regexes are examples**—adapt them to your real classpath. This is not a normal Java application property placed in `application.properties`. Keys in `META-INF/spring-devtools.properties` must be unique, and matching runs against classpath entries.

**Separate two failure categories**:

1. **Classloader partition issue**: fix include/exclude rules or library handling.
2. **Resource lifecycle leak**: close resources and unregister callbacks; changing loaders will not automatically release a socket or thread.

### 13.1. Standard ObjectInputStream Can Fail

Spring Boot docs note that deserializing objects via standard `ObjectInputStream` sometimes fails with the restart classloader. If Java serialization is genuinely required, **`ConfigurableObjectInputStream`** with the right context classloader may be needed.

Avoid configuring serializers/deserializers by arbitrary class names; prefer data formats independent of Java classloaders and re-test across restarts.

### 13.2. Why Can a Class Name Look "Identical" Yet Casting Fails?

In the JVM, a class's identity comprises **fully qualified name plus defining `ClassLoader`**. Two classes with the same name loaded by different loaders are not the same runtime class. Leaks or registries mixing objects from old and new contexts can trigger confusing **`ClassCastException`** errors.

Log the `classLoader` identity of the actual involved objects, not just class names. Never expose classloader details on production HTTP endpoints.

## 14. Debugging Retained Resources After Multiple Restarts

### 14.1. Watching Logs Across Each Context Cycle

Print minimal markers such as:

~~~text
OPEN resource-id=...
CONTEXT_CLOSING resource-id=...
CLOSE resource-id=...
OPEN resource-id=...
~~~

Compare by resource ID rather than timestamp alone. If a new `OPEN` appears without a prior `CLOSE`, inspect bean ownership/lifecycle and whether DevTools actually closed the old context.

Do not conclude there is no leak solely because `CLOSE` was logged: a method might print `CLOSE` without actually stopping threads or closing sockets. Check actual resource state.

### 14.2. Inspecting Threads

In a running dev JVM, capture a thread dump with JDK tooling:

~~~bash
jcmd <pid> Thread.print
~~~

**`<pid>` is a placeholder**—replace it with the real process ID. Look for threads named **`demo-poll-...`**; once a DevTools restart completes and cleanup runs properly, threads from the old instance should no longer exist.

You can also use **`jstack`** on supported JDKs or JDK Flight Recorder (JFR) to analyze thread churn, allocations, and retained references.

### 14.3. Inspecting Ports and File Handles

Symptoms:

- First restart succeeds, then **`BindException: Address already in use`**.
- Files cannot be renamed/deleted on Windows.
- Old watchers continue receiving events.
- Pool connections remain open even after the app runs a new context.

Check resource/port owners and close logs. Do not blindly kill another process to "free the port"; verify the exact process/PID and resource first.

### 14.4. Heap/Classloader Diagnostics

For a dev app whose heap grows across restarts:

1. Capture a heap dump in a permitted environment, avoiding sensitive data.
2. Compare the number of retained **`RestartClassLoader`** instances.
3. Follow GC roots to find `Thread`s, static `Map`s, listener registries, or shutdown hooks.
4. Identify which object in the base classloader pins old application objects.
5. Fix the owner to unregister/close, then re-test across multiple cycles.

**Finding one remaining `RestartClassLoader` after a GC snapshot is not guaranteed proof of a leak**: it may still hold valid references during handoff. Trace the retaining path and check whether old objects stay pinned after restart settles.

## 15. Common Design Mistakes

### 15.1. Disabling SpringApplication's Hook

**Wrong:** calling **`setRegisterShutdownHook(false)`** in an app using DevTools restart. Spring Boot docs warn restart will not work properly. Keep the default `true`.

### 15.2. Using Runtime.addShutdownHook to Close Context Resources

Wrong scope. JVM hooks do not run on every DevTools restart. Use `@PreDestroy`/`SmartLifecycle`/`destroyMethod`.

### 15.3. Spawning a Thread in @PostConstruct Without Stopping It

Each restart spawns another worker; old threads pin old classloaders. Have an executor owner and clear stop policy.

### 15.4. Letting a Global Registry Hold Old Context Listeners

Unregister on destruction. Do not merely null out a bean field while the registry still holds the callback.

### 15.5. Waiting Indefinitely for Tasks During Destruction

Can hang DevTools restarts. Use bounded waits, interruption, and retries/checkpoints when needed.

### 15.6. Assuming JVM Shutdown Hooks Run on Every Restart

False. Restart does not mean JVM exit; Spring context closure and `Runtime` hooks are distinct lifecycles.

### 15.7. Assuming Static Caches Always Reset

No. Classes in the base loader retain static state; classes in the restart loader get fresh static copies. Check the actual loader.

### 15.8. Thinking Daemon Threads Cannot Leak

Daemon status only affects JVM liveness; it does not close resources or drop references. Daemon threads can still survive across many context restarts.

### 15.9. Disabling DevTools in application.properties and Assuming the Classloader Vanished

The property in `application.properties` normally only stops file watching/restart behavior; to disable completely, set the system property before `run` or remove the dependency.

### 15.10. Testing with an Executable JAR and Claiming DevTools Is Broken

DevTools automatically disables itself in fully packaged apps and is excluded from repackaged JARs by default. Use the dev classpath or Maven/Gradle boot run.

### 15.11. Relying on @PreDestroy During SIGKILL

`SIGKILL`/crashes never guarantee Java cleanup. Critical workloads require independent persistence and recovery.

### 15.12. Equating Graceful HTTP Shutdown with All Async Jobs Finishing

No. `WebServer` and `TaskExecutor`/consumers have separate shutdown policies; coordinate them if they depend on each other.

### 15.13. Confusing File Save with a Classpath Change

DevTools watches classpath output, not arbitrary source Save actions. Check IDE compile/build.

### 15.14. Failing to Test Multiple Restart Cycles

A single restart may hide leaks. Repeat several times while watching threads, heap, sockets, and callback counts.

### 15.15. Registering Two Cleanup Paths Without Checking Idempotency

If a resource has both `@PreDestroy` and an external shutdown callback, it can be closed twice or race. Make `close` idempotent and define clear ownership.

## 16. Pre-Flight Checklist for Using DevTools Restart

- [ ] DevTools is only on the development classpath; remote DevTools is never enabled in production.
- [ ] Keep the default `SpringApplication` shutdown hook; never call `setRegisterShutdownHook(false)`.
- [ ] Understand that DevTools restart **does not terminate the JVM**.
- [ ] Distinguish Spring context destruction from `Runtime` shutdown hooks.
- [ ] Resources opened in `@PostConstruct` have cleanup in `@PreDestroy` or `destroyMethod`.
- [ ] Manually created executors have shutdown, bounded await, and interruption policies.
- [ ] `@Scheduled` tasks/consumers have stop strategies and avoid overlap when needed.
- [ ] Static/global registries unregister old context callbacks.
- [ ] `ThreadLocal`s and thread context classloaders do not retain stale references unnecessarily.
- [ ] Sockets/file channels/watch services have an owner that closes them properly.
- [ ] Spring-managed or custom connection pools are closed.
- [ ] `SmartLifecycle.stop(callback)` always invokes the callback upon completion.
- [ ] Cleanup never blocks indefinitely and has timeout handling.
- [ ] Startup failure paths also clean up partially allocated resources.
- [ ] Logs include `OPEN`, `CONTEXT_CLOSING`, and `CLOSE` with resource IDs.
- [ ] Test `context.close` separately with JUnit.
- [ ] Test real DevTools restarts in IDE/Maven with compiled classpath output.
- [ ] Test multiple consecutive restarts and verify threads/ports/heap do not grow abnormally.
- [ ] For classloader issues, test disabling restart cleanly, then inspect include/exclude rules.
- [ ] Never rely on `SIGKILL`/IDE hard-stop to evaluate `@PreDestroy`.
- [ ] Never use DevTools as a deployment mechanism or zero-downtime guarantee.

## 17. Self-Check Questions

**Question 1.** Does a DevTools restart create a new JVM process?

**Answer:** Normally no. DevTools swaps the restart classloader and context inside the current JVM; it is not a full process restart.

**Question 2.** What does the base classloader hold?

**Answer:** Usually unchanging dependency JARs. It persists across restarts and can hold static caches/registries longer than the application context.

**Question 3.** Why does `setRegisterShutdownHook(false)` cause problems?

**Answer:** Spring Boot docs note DevTools needs the application context shutdown hook to close the context on restart; disabling it prevents restart from working properly.

**Question 4.** Does every DevTools restart invoke all `Runtime.addShutdownHook` callbacks?

**Answer:** Do not assume so. Runtime hooks belong to JVM shutdown; DevTools restart closes and replaces the application context, not the JVM process.

**Question 5.** When is `@PreDestroy` invoked?

**Answer:** When Spring destroys a managed bean during normal context closure, including the old context during a proper DevTools restart.

**Question 6.** Can an old daemon `Thread` still alive after restart cause a leak?

**Answer:** Yes. Daemon status only avoids keeping the JVM alive, yet the thread can still pin classloaders, references, sockets, or other resources.

**Question 7.** Why can a static map in a library JAR pin an old classloader?

**Answer:** The library typically resides in the base classloader surviving restarts; the map can hold callbacks/objects loaded by the old restart classloader.

**Question 8.** How do you know a restart actually occurred rather than just LiveReload?

**Answer:** Inspect context/resource IDs, lifecycle logs, and the restart classloader—not just browser reloads or file Saves.

**Question 9.** Should you close the context immediately after `SpringApplication.run` in a web app?

**Answer:** No, because that shuts down the server right after startup. Close explicitly only in CLI apps/tests meant to exit.

**Question 10.** Does `@SpringBootTest contextLoads` prove DevTools classloader restarts do not leak?

**Answer:** No. That test does not run DevTools restarts. You need a smoke test via IDE/Maven dev classpath across multiple restarts.

**Question 11.** Does setting `server.shutdown=graceful` automatically wait for all background tasks?

**Answer:** No. It focuses on the web server; executors/schedulers need their own shutdown policies.

**Question 12.** If a bean allocates a resource and `@PostConstruct` fails halfway, is `@PreDestroy` guaranteed to run?

**Answer:** Do not rely on it for resources that did not finish lifecycle registration. Use `try/catch` and close partial allocations if init fails.

**Question 13.** Should you disable DevTools by turning off the Spring shutdown hook?

**Answer:** No. Use `spring.devtools.restart.enabled=false` in the proper scope or remove the dependency; keep the `SpringApplication` hook for context lifecycles.

**Question 14.** When seeing two streams of `TICK` logs from two resource IDs after restart, what should you check first?

**Answer:** Check whether `@PreDestroy` ran for the old ID, whether the executor shut down, and whether any thread or global registry still holds the old reference.

## 18. Summary

**A DevTools restart swaps the `ApplicationContext` and restart classloader within the same JVM—it is not a full JVM shutdown.** Spring Boot 3.3 DevTools depends on the application context shutdown hook: disabling it via **`SpringApplication.setRegisterShutdownHook(false)`** breaks proper restart behavior.

To clean up resources, **bind resource ownership to Spring-managed beans** and use **`@PreDestroy`**, **`destroyMethod`**, or **`SmartLifecycle`** when ordered stopping is needed. Manually registered **`Runtime.addShutdownHook`** callbacks do not substitute for destruction callbacks when DevTools restarts the context.

A healthy DevTools restart shows **the old context `CLOSE` and the new context `OPEN`**, with no lingering background threads, sockets, or listeners from the old context still active. Never rely on automatic GC or daemon flags to free resources; verify with logs, thread dumps, port/handle counts, and multiple real restart cycles.

## 19. Official References

- Spring Boot 3.3 — Developer Tools, Automatic Restart, Shutdown Hook, Restart vs. Reload, Classloaders: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — SpringApplication, Application Exit and Shutdown Hooks: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — SpringApplication.setRegisterShutdownHook API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — Bean Lifecycle, @PreDestroy, DisposableBean, SmartLifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html