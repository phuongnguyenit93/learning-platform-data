# ConfigurableApplicationContext.close and SpringApplicationShutdownHook

A Spring Boot application needs not only to **start properly** but also to **stop properly**. When terminating, the container must notify running components to stop accepting new work, allow eligible tasks time to complete, invoke bean destruction callbacks, and release connections/resources. Two names frequently appear when reading the source code:

- **`ConfigurableApplicationContext.close()`**: an **explicit** call to close an active Spring `ApplicationContext`.
- **`SpringApplicationShutdownHook`**: the internal mechanism that **Spring Boot** uses to register with **JVM shutdown** and close registered application contexts when the process reaches the shutdown step.

These two mechanisms are related, yet **they are not the same thing**. `close()` does not need to wait for the JVM to exit; the JVM shutdown hook is not a command an application should call every time it closes a context. Distinguishing them prevents hard-to-diagnose issues: "closed the context yet the Java process is still running", "why was `@PreDestroy` called when pressing Ctrl+C?", "why did I add a shutdown hook and callbacks ran out of order?", or "does `SpringApplication.exit` automatically terminate the JVM?".

This lesson uses **Spring Boot 3.3.x / Spring Framework 6.1 / Java 17+**, focusing on **application shutdown** without going deep into the full startup process. It includes a runnable Gradle/Java example, two observation modes for **manual close** and **JVM shutdown**, ways to use shutdown handlers, event ordering, graceful HTTP shutdown, testing, and error handling.

## 1. Four Concepts Often Confused Together

| Concept | Level | Purpose |
| --- | --- | --- |
| `ConfigurableApplicationContext.close()` | Spring Framework container | Closes a context, stops lifecycle beans, destroys singletons managed by the context |
| `SpringApplicationShutdownHook` | Spring Boot internal | Coordinates closing registered contexts during JVM shutdown |
| `Runtime.getRuntime().addShutdownHook(...)` | Java/JVM | Registers a thread to run during normal JVM shutdown |
| `System.exit(status)` | Java/JVM | Requests the **JVM process** to exit with an exit status; triggers the shutdown sequence |

Example:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Closes the context without directly asking the JVM to terminate:
context.close();
~~~

The snippet above is an illustration inside a method with `MyApplication` and corresponding imports. **`context.close()` does not call `System.exit(...)`**. If the process still has non-daemon threads or resources outside the context, the JVM can remain alive. If no non-daemon threads remain, the JVM can terminate after `main` returns.

Conversely, if you use:

~~~java
System.exit(0);
~~~

The JVM begins shutdown; if Spring Boot registered the shutdown hook by default, the hook can call `close()` on active contexts. **`System.exit` is not an API to close Spring beans directly**: it is a request to terminate the JVM, and Spring cleanup happens via the hook.

## 2. Overview Map: Two Paths Leading to Context Closure

~~~text
                      RUNNING SPRING APPLICATION
                                   |
                     +-------------+-------------+
                     |                           |
                     v                           v
      Application code calls close()     JVM begins shutdown
                     |                 (System.exit, SIGTERM,
                     |                  appropriate Ctrl+C, ...)
                     |                           |
                     |                           v
                     |              SpringApplicationShutdownHook
                     |               iterates registered contexts
                     |                           |
                     +------------+--------------+
                                  |
                                  v
                  ConfigurableApplicationContext.close()
                                  |
                                  v
                        AbstractApplicationContext
                           executes doClose()
                                  |
                    +-------------+-------------+
                    |             |             |
                    v             v             v
              ContextClosed   Lifecycle      destroy
                  Event     Processor.stop   singletons
                    |             |             |
                    +-------------+-------------+
                                  |
                                  v
                           context inactive
                                  |
                +-----------------+--------------------+
                |                                      |
                v                                      v
      If only close() was called:             If JVM shutdown:
      Java code can keep running              JVM continues exiting;
                                               Boot shutdown handlers
                                               may be called after
                                               contexts close
~~~

The diagram merges both paths into **a single context-closing mechanism** for clarity; the exact detailed order is **`ContextClosedEvent` → `LifecycleProcessor.onClose()` → destroy singletons → close bean factory** in the normal `AbstractApplicationContext` close path. Failed callbacks or custom contexts can make real-world observations more complex.

Sentence to remember:

> **The hook is the trigger that initiates context closure when the JVM is about to exit; `close()` is the operation that closes the context.** Do not treat these two names as two completely independent options with unrelated effects.

## 3. What Does `ConfigurableApplicationContext.close()` Do?

`ConfigurableApplicationContext` is the interface for configurable contexts, extending `ApplicationContext` capabilities and supporting closure. `SpringApplication.run(...)` returns a `ConfigurableApplicationContext` on the successful startup path.

A familiar example:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

try {
    // Use beans, perform work.
} finally {
    context.close();
}
~~~

For CLI applications or components that manage their own lifecycle, the `try/finally` pattern releases the context when the task finishes or fails. `try-with-resources` can also be used because `ConfigurableApplicationContext` is `AutoCloseable`:

~~~java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    // Use context within this scope.
}
// context.close() has been called upon exiting the block.
~~~

**Do not wrap a long-running web server in `try-with-resources`** if `main` immediately exits the block: the context will close right away and the server will stop. For long-running web apps, normally let Spring Boot/the JVM shutdown hook coordinate when a stop signal arrives.

### Closing Order of `AbstractApplicationContext`

In Spring Framework 6.1, the normal path can be understood as follows:

~~~text
context.close()
   |
   +-- Mark/coordinate the closing process
   |
   +-- publishEvent(new ContextClosedEvent(context))
   |
   +-- lifecycleProcessor.onClose()
   |      Stop running Lifecycle / SmartLifecycle beans
   |      By phase and dependency relationships
   |
   +-- destroyBeans()
   |      @PreDestroy, DisposableBean.destroy(),
   |      destroyMethod on eligible singletons
   |
   +-- closeBeanFactory()
   |
   +-- Remaining context close steps
   |
   v
context.isActive() == false
~~~

**`ContextClosedEvent` occurs before lifecycle beans finish stopping and before standard destroy callbacks.** Listeners receiving that event should not assume "all connections are already closed". It is **a signal that context closure has begun**, not an event guaranteeing that all cleanup has finished.

The corresponding steps live in `org.springframework.context.support.AbstractApplicationContext`; context subclasses may add custom handling. If an exception occurs in a callback, Spring logs it and continues appropriate steps, but **do not rely on recovering from severe errors** such as `OutOfMemoryError` or a forced process kill.

### `close()` Does Not Destroy Every Java Object

Spring only knows about beans and resources managed by the context through scope/lifecycle contracts. Objects created with `new` outside the context, an `ExecutorService` not registered as a bean, manually spawned background threads, or library resources without lifecycle integration **are not automatically destroyed just by calling `close()`**.

Incorrect example:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
context.close();
// executor is not managed by Spring -> may still keep non-daemon threads alive.
~~~

The snippet above is a fragment requiring imports for `ExecutorService` and `Executors` along with a valid `context` variable. You must call `executor.shutdown()` or design a bean with an appropriate destroy method.

## 4. What Is `SpringApplicationShutdownHook`?

In Spring Boot 3.3, `org.springframework.boot.SpringApplicationShutdownHook` is **an internal implementation class in the `org.springframework.boot` package**, not a public extension point that business code should instantiate or call directly.

The `SpringApplication` 3.3.13 source code holds a shared shutdown hook to manage registered contexts. By configuration contract, **`SpringApplication.setRegisterShutdownHook(true)` is the default**. When running:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.run(args);
~~~

Spring Boot registers the created context with the shutdown hook mechanism unless this feature is disabled. When the JVM begins its normal shutdown process, the hook closes active registered contexts.

Conceptually:

~~~text
SpringApplication.run(...)
   |
   +-- registerShutdownHook = true (default)
   |
   +-- create ApplicationContext
   |
   +-- register context with SpringApplicationShutdownHook
   |
   +-- refresh and continue startup
   |
   v
ApplicationContext active
   |
   ... application runtime ...
   |
   v
JVM shutdown
   |
   +-- Boot shutdown hook thread runs
   |
   +-- close() managed contexts that are not yet closed
   |
   +-- wait for contexts to become inactive when needed
   |
   +-- run registered SpringApplicationShutdownHandlers
   v
JVM continues terminating
~~~

In the 3.3 implementation, the hook also tracks contexts that have published `ContextClosedEvent` so that concurrently closing contexts are not overlooked. This is an **implementation detail for understanding the code**, not an API for applications to manipulate the internal context list directly.

**Do not confuse `SpringApplicationShutdownHook` with `ConfigurableApplicationContext.registerShutdownHook()`.** The latter is a **Spring Framework** API that can register a dedicated JVM hook for a single context. Spring Boot coordinates shutdown at the `SpringApplication` level; in a typical Boot application you do not need to call `context.registerShutdownHook()` as well.

## 5. A Hook Exists by Default; When Should You Configure It?

Spring Boot allows:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setRegisterShutdownHook(false);
ConfigurableApplicationContext context = application.run(args);
~~~

This is a fragment inside a method with an appropriate `MyApplication` class. When hook registration is disabled, **the application must explicitly manage closing the context** along every termination path it owns. Do not set `false` merely to "speed up shutdown"; doing so can prevent `@PreDestroy` and lifecycle callbacks from being invoked when the JVM exits.

Equivalent external configuration:

~~~properties
spring.main.register-shutdown-hook=false
~~~

This option can be used in architectures that **embed Spring Boot inside a host with its own lifecycle management**, certain specialized test programs, or situations requiring shutdown coordination with external software. In most Spring Boot applications running as standalone processes, **keep the default `true`**.

### Easily Confused Cases

- Calling `context.close()` manually **does not require** disabling the shutdown hook. Once the context is closed, the hook tracks its state so it does not need to destroy beans a second time on the normal path.
- Disabling the hook **does not prevent** calling `context.close()`: you can still close the context explicitly.
- Disabling the hook **does not make the JVM stay alive longer** if no non-daemon threads remain. Active threads and JVM lifetime are separate concerns.
- If an application has multiple `ApplicationContext` instances, understand who creates, registers, and closes each context; do not assume closing one context automatically closes all independent contexts.
- `spring.main.register-shutdown-hook` is a `SpringApplication` setting, not a global flag affecting every hook registered by Java or other libraries.

## 6. What Happens During JVM Shutdown?

The JVM begins shutdown in several common scenarios:

- `System.exit(status)`.
- A normal stop signal is sent, such as `SIGTERM` on Unix/Linux, and the JVM is able to run shutdown hooks.
- Pressing `Ctrl+C` while the process runs in the foreground in an appropriate terminal.
- The JVM shuts down automatically when **no non-daemon threads remain** (when a console application finishes).

When the JVM enters the shutdown sequence, hooks registered via `Runtime.addShutdownHook(Thread)` are executed. Spring Boot registers its hook to request context closure. However, not every termination method runs hooks:

| Termination method | Normally runs JVM shutdown hooks? | Key notes |
| --- | --- | --- |
| `context.close()` | **Does not start JVM shutdown itself** | JVM can continue running after context closes |
| `System.exit(0)` | Yes, on the normal shutdown path | Runs hooks then terminates the JVM |
| `SIGTERM`/`kill -TERM` | Usually yes on HotSpot/OpenJDK | Depends on OS and how the process receives signals |
| Foreground `Ctrl+C` | Usually yes | IDEs/terminals may stop processes differently |
| `kill -9`/`SIGKILL` | **No** | OS forcibly terminates the process |
| `Runtime.getRuntime().halt(...)` | **No** | Bypasses shutdown hooks; use with extreme caution |
| Power loss, forced container kill | Not guaranteed | May not execute any Java callbacks at all |

**Operational note:** "running hooks" does not mean all cleanup work is **guaranteed to finish**. Container orchestration enforces a termination deadline; if exceeded, the process may be killed. Normal shutdown still requires timeouts, bounded blocking, idempotence, and crash recovery.

### Do Not Manually Call `Thread.run()` on a Hook

A JVM shutdown hook is a thread invoked by the JVM at shutdown time. You should not keep a reference and call `run()` manually to "simulate JVM shutdown"; that only executes the `Runnable` on the current thread without reproducing the JVM shutdown contract or state.

To explicitly close the context in code, call **`context.close()`**.

## 7. Ordering of `ContextClosedEvent`, `SmartLifecycle`, and Destroy Callbacks

These three mechanisms often appear together in the same shutdown log:

### `ContextClosedEvent`

Published **when the context begins closing**, before the lifecycle stop phase in a normal `AbstractApplicationContext`.

~~~java
@EventListener
public void onClose(ContextClosedEvent event) {
    System.out.println("EVENT ContextClosedEvent");
}
~~~

This is an example method in a Spring bean, requiring `@EventListener` and `ContextClosedEvent` imports.

### `LifecycleProcessor.onClose()`

Spring stops running `Lifecycle`/`SmartLifecycle` beans through `LifecycleProcessor`. With `SmartLifecycle`, the `stop(Runnable callback)` method allows signaling when stopping has actually finished.

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

This is a fragment in a class implementing `SmartLifecycle`. For **asynchronous** stopping, invoke the callback only after in-flight work has finished per contract. Forgetting the callback can cause the coordinator to wait until the phase timeout expires.

Stop order normally proceeds from **higher phase to lower phase** (opposite of start from low to high), while also accounting for dependencies. Do not assign `phase` levels arbitrarily: if a consumer uses a connection, you normally want the consumer to stop accepting work before closing the connection it needs.

### `@PreDestroy`, `DisposableBean.destroy()`, Destroy Method

After the normal lifecycle stop step, the context destroys its managed singletons:

~~~java
@PreDestroy
public void preDestroy() {
    System.out.println("DESTROY @PreDestroy");
}
~~~

Or configured via:

~~~java
@Bean(destroyMethod = "cleanup")
ExternalResource resource() {
    return new ExternalResource();
}
~~~

These snippets are fragments requiring appropriate classes and imports; the full example is in section 9. **Stop is not the same as destroy**: a bean can stop running before it is destroyed, and a destroy callback is not the ideal place for an unbounded wait loop.

### Sequence to Remember

~~~text
close() begins
   -> ContextClosedEvent
   -> LifecycleProcessor.onClose()
        -> SmartLifecycle.stop(callback)
   -> destroyBeans()
        -> @PreDestroy
        -> DisposableBean.destroy() if present
        -> configured destroy method
   -> close BeanFactory/context
   -> isActive() == false
~~~

For a bean using multiple destruction mechanisms, Spring defines the order among them. The sequence above illustrates the normal path and does not imply every bean has all three callbacks.

## 8. How Does `SpringApplicationShutdownHandlers` Differ from `SpringApplicationShutdownHook`?

`SpringApplicationShutdownHook` is an **internal coordinator class**, whereas `SpringApplicationShutdownHandlers` is a **public interface** for Spring Boot users to register actions to run during JVM shutdown:

~~~java
SpringApplication.getShutdownHandlers().add(() -> {
    System.out.println("BOOT shutdown handler");
});
~~~

In Spring Boot 3.3, handlers registered via `SpringApplication.getShutdownHandlers()`:

- Run **at JVM shutdown**, **not immediately after a `context.close()` call** while the JVM keeps running.
- Are coordinated **sequentially** by Boot rather than letting independent JVM hooks run in an unspecified order.
- By API contract, are invoked **after registered `ApplicationContext` instances have been closed and are no longer active**.
- Are suitable for work **after the Spring context has closed**, and unsuitable if the action still needs to inject or look up active beans.

A practical scenario: writing a final marker to a logging mechanism independent of Spring beans to record that the JVM passed the context-closing step. However, the callback must not depend on a `DataSource` or logger bean that has already been destroyed.

To unregister:

~~~java
Runnable action = () -> System.out.println("late cleanup");
SpringApplication.getShutdownHandlers().add(action);

// Elsewhere, before JVM shutdown:
SpringApplication.getShutdownHandlers().remove(action);
~~~

Both snippets **illustrate the same `Runnable` instance**. You must use the exact same object to remove it; do not expect two lambdas with identical bodies to share the same identity.

### Distinguishing the Two Callback Types

| Action | `ContextClosedEvent` listener | `SpringApplicationShutdownHandlers` |
| --- | --- | --- |
| Triggered when code calls `context.close()` | Yes | Not just from close |
| Triggered on JVM shutdown when hook closes context | Yes | Yes, if hook is registered and runs |
| Timing relative to bean destruction | **Before** stop/destroy | **After** registered contexts close |
| Should it call active Spring beans? | With care: shutdown has begun | **Do not assume beans still exist** |
| Must the listener be a Spring-managed bean? | Typically can be a bean | Not required |
| Suitable for | Stopping new work, marking close start | Small final context-independent tasks |

**Do not rely on ordering among arbitrary `Runtime.addShutdownHook(...)` hooks.** The JVM may run different hooks **concurrently**, with no guaranteed order. If you truly need "after the Spring context closes", use the `SpringApplicationShutdownHandlers` contract rather than an arbitrary JVM hook.

## 9. Runnable Example: Comparing `close()` and JVM Shutdown

We will create a **Spring Boot CLI without starting a web server** so stdout is easy to observe. The demo includes:

- A `SmartLifecycle` bean printing `start`/`stop` milestones.
- An `ApplicationRunner` confirming the app finished startup.
- A `ContextClosedEvent` listener printing when context closure starts.
- A `DemoResource` bean with `@PreDestroy` and `destroyMethod`.
- A `SpringApplicationShutdownHandlers` entry printing `context.isActive()` **at JVM shutdown**.
- Two modes: `--demo.mode=manual` and `--demo.mode=exit`.

In production applications, **do not call `System.exit` directly from an HTTP controller**. The `exit` branch in this demo runs only when you explicitly request it in a local test run.

### 9.1. Project Structure

~~~text
shutdown-hook-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/shutdown/
    └── ShutdownDemoApplication.java
~~~

### 9.2. `settings.gradle`

~~~groovy
rootProject.name = 'shutdown-hook-demo'
~~~

### 9.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    // BOM resolves versions of Spring Boot/Jakarta modules.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

The Spring Boot plugin is paired with **Gradle's native BOM**, since `spring-boot-starter` has no explicit version. JDK 17 or higher and a Gradle version compatible with Spring Boot 3.3 are required.

### 9.4. `ShutdownDemoApplication.java`

~~~java
package com.example.shutdown;

import java.util.Arrays;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Do not disable registerShutdownHook (default is true).
        ConfigurableApplicationContext context = application.run(args);

        SpringApplication.getShutdownHandlers().add(() ->
                System.out.println("BOOT_HANDLER active=" + context.isActive()));

        System.out.println("MAIN active=" + context.isActive());

        boolean exitMode = Arrays.asList(args).contains("--demo.mode=exit");
        if (exitMode) {
            System.out.println("MAIN request System.exit");
            System.exit(0);
        }

        System.out.println("MAIN explicit close");
        context.close();
        System.out.println("MAIN after close active=" + context.isActive());
    }

    @Bean
    SmartLifecycle demoWorker() {
        return new DemoWorker();
    }

    @Bean(destroyMethod = "cleanup")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("RUNNER");
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("EVENT ContextClosedEvent");
    }

    static final class DemoWorker implements SmartLifecycle {
        private volatile boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("WORKER start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("WORKER stop");
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
    }

    static final class DemoResource {
        @PreDestroy
        public void beforeDestroy() {
            System.out.println("RESOURCE @PreDestroy");
        }

        public void cleanup() {
            System.out.println("RESOURCE cleanup");
        }
    }
}
~~~

In the demo, `DemoWorker` auto-starts at the end of context refresh because it implements `SmartLifecycle` with `isAutoStartup() == true`. `ApplicationRunner` runs after refresh. `DemoResource` performs no background work; it exists to observe the destroy phase.

The program has only one context, one worker, and one resource so the output stays deterministic. In real applications with multiple `SmartLifecycle` beans, `stop` milestones can be split across phases and dependencies.

### 9.5. Running in Manual Close Mode

If you have the Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--demo.mode=manual"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=manual"
~~~

Or with an installed Gradle (when no wrapper exists):

~~~bash
gradle bootRun --args="--demo.mode=manual"
~~~

Lines **printed by the program's `System.out.println`** on the successful run path, in order:

~~~text
WORKER start
RUNNER
MAIN active=true
MAIN explicit close
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
MAIN after close active=false
BOOT_HANDLER active=false
~~~

Additional Spring Boot logs and Gradle output may appear. The `BOOT_HANDLER active=false` line happens **at JVM shutdown after `main` ends**, not because `context.close()` directly invoked the handler.

Key takeaways:

1. `context.close()` is called from `main`.
2. The listener receives `ContextClosedEvent` before the worker stops.
3. The worker stops before the resource destruction phase.
4. `@PreDestroy` runs before the configured `cleanup` destroy method.
5. After `close()`, `context.isActive()` is `false`.
6. **Even though the context is already closed**, a handler registered with Spring Boot can still be invoked later when the JVM proceeds to shutdown.

### 9.6. Running in JVM Shutdown Mode

Run again in **a fresh JVM**:

~~~bash
./gradlew bootRun --args="--demo.mode=exit"
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=exit"
~~~

Lines printed by the demo code on the normal path:

~~~text
WORKER start
RUNNER
MAIN active=true
MAIN request System.exit
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
BOOT_HANDLER active=false
~~~

**There is no `MAIN after close active=false` line** in this branch because `System.exit(0)` tells the JVM to terminate instead of returning to execute lines at the end of `main`. The JVM invokes the Spring Boot shutdown hook; the hook requests context closure, and then the handler runs.

Both runs show **the exact same Spring cleanup sequence**, triggered by different initiators:

- Manual branch: code calls `context.close()`.
- Exit branch: JVM shutdown triggers `SpringApplicationShutdownHook`, which calls `close()`.

**Never use `System.exit` inside a test runner, shared IDE process, or production server just to "check logs":** it terminates the entire JVM and can affect every other application or process inside it. The demo should only be run as a standalone executable.

### 9.7. Running via JAR

Build:

~~~bash
./gradlew clean bootJar
~~~

After a successful build, the JAR name for the project above is typically:

~~~text
build/libs/shutdown-hook-demo-1.0.0.jar
~~~

Run:

~~~bash
java -jar build/libs/shutdown-hook-demo-1.0.0.jar --demo.mode=manual
java -jar build/libs/shutdown-hook-demo-1.0.0.jar --demo.mode=exit
~~~

These two commands create **two separate JVM runs**, not invocations in the same process. Check the actual JAR name if you changed the artifact configuration.

## 10. Using `SpringApplication.exit(context)` Properly

Spring Boot provides the API:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

Core semantics:

- Triggers **context closure** along with Spring Boot's exit-code resolution logic.
- Can aggregate values from eligible `ExitCodeGenerator` beans.
- **Returns an `int`**, without guaranteeing JVM termination just because the method returned.

If a CLI application wants to exit the process with a specific status code:

~~~java
int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

This is a **replacement fragment** for manual close in `main`; it should not be redundantly chained with `context.close()` or called repeatedly to "close more thoroughly".

A bean can implement `ExitCodeGenerator`:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

This is a fragment inside a Spring configuration class requiring `org.springframework.boot.ExitCodeGenerator`. The value `7` is just an example. When code calls `SpringApplication.exit(context)`, Spring Boot can use these generators to determine the exit code. **Calling `context.close()` directly does not compute or forward that exit code to the OS.**

Distinction:

| Option | Closes context? | Guarantees immediate JVM exit? | Return value |
| --- | --- | --- | --- |
| `context.close()` | Yes | No | `void` |
| `SpringApplication.exit(context)` | Yes | Not automatically | `int` |
| `System.exit(code)` | Indirectly via hook if registered and active | Requests JVM exit | Exit status sent to OS |
| `Runtime.halt(code)` | **Not guaranteed / skips hooks** | Forced stop | Exit status sent to OS |

For **web applications serving real traffic**, use process/container lifecycle and graceful shutdown to stop. Do not expose a public HTTP endpoint just to call `System.exit`.

## 11. `ContextClosedEvent` Means "Closing Started", Not "Closing Finished"

If code contains:

~~~java
@EventListener
public void onClose(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
~~~

the listener may run while other beans **are still running**. Therefore, avoid:

- Calling another bean's API assuming it will stay alive throughout a long task.
- Starting new I/O or new transactions while the context is closing.
- Waiting indefinitely inside an event listener.
- Calling `context.close()` recursively.
- Treating the close event as "all requests have been drained".

If the goal is to **stop consumers, schedulers, or new work intake**, use `SmartLifecycle` with phases and `stop(Runnable)`, or a well-designed and tested shutdown callback. If you need to **release sockets/files**, `@PreDestroy`/destroy methods are appropriate. If you need **code to run after all contexts have closed at JVM shutdown**, look at `SpringApplicationShutdownHandlers` and ensure the code does not depend on Spring beans.

### Why Is the `stop(Runnable)` Callback Important?

If a bean needs to stop asynchronously:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingJobs();
    executor.execute(() -> {
        try {
            waitForInFlightJobs();
        } finally {
            callback.run();
        }
    });
}
~~~

This is **illustrative code** in a `SmartLifecycle` bean assuming `executor` and the helper methods already exist. The callback must be called once stopping completes; avoid calling it too early or forgetting to call it. Production code must also handle the possibility that `executor.execute` rejects tasks during shutdown.

The purpose is to let the lifecycle processor know when it may proceed to stop subsequent phases.

## 12. Graceful Shutdown of the Spring Boot Web Server

Closing the context of an HTTP server does not mean **every in-flight request is terminated immediately**; Spring Boot provides graceful shutdown to stop accepting new requests and give current requests a chance to complete within a time window.

For **Spring Boot 3.3**, typical configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Explanation:

- `server.shutdown=graceful` enables graceful shutdown mode for the corresponding embedded web server.
- `spring.lifecycle.timeout-per-shutdown-phase=20s` sets the wait limit per phase when stopping `SmartLifecycle` beans; it does not mean "the JVM is guaranteed to stop in exactly 20 seconds".
- In Spring Boot 3.3, graceful shutdown is supported on **Tomcat, Jetty, Reactor Netty, and Undertow**, with server-specific ways of refusing new requests.
- It executes during **context closure**, in an early phase of stopping `SmartLifecycle` beans.
- If orchestration sends `SIGKILL` before the grace window expires, Spring cannot finish all callbacks.

**Version note:** other Spring Boot versions may have different graceful shutdown defaults. For this 3.3 module, configure it explicitly if graceful behavior is desired; do not extrapolate defaults from newer versions.

### Readiness Differs from Closed Sockets

When graceful shutdown begins, Spring Boot can transition readiness to `ReadinessState.REFUSING_TRAFFIC`. However, HTTP probes may not observe this immediately due to kubelet/readiness intervals and endpoint propagation. The internal state transition, the web server rejecting new requests, and the load balancer stopping traffic are **distinct milestones**.

With Kubernetes, coordinate:

- `terminationGracePeriodSeconds` large enough for configured drain/stop.
- Readiness probes and when the Pod is removed from Service endpoints.
- `preStop` when delaying/coordinating to allow traffic drain is genuinely needed.
- Stop time for queue consumers, connection pools, and workers.
- In-flight older requests and timeout policies.

A single `@PreDestroy` callback cannot guarantee graceful shutdown while requests or tasks are still running.

## 13. Does Disabling the Boot Hook Mean No Shutdown Hooks Remain?

**No.** Considering only `SpringApplication.setRegisterShutdownHook(false)`: you are asking `SpringApplication` not to use its own hook mechanism to register new contexts. However:

- The JVM may still have other hooks registered by libraries or application code.
- An independent context might still call Spring Framework's `registerShutdownHook()`.
- Resources not managed by Spring have their own shutdown mechanisms.
- `System.exit` still requests JVM shutdown regardless of Spring Boot's flag.

Therefore, in a JVM with multiple hooks, seeing one callback line execute cannot serve as proof that the Boot hook was registered.

### Should You Register Both Types of Hooks Yourself?

Normally **no**:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);
context.registerShutdownHook();
~~~

This **snippet shows an action typically unnecessary in Boot**, not a recommendation. Spring Boot already has a default mechanism to close the context on JVM shutdown. Registering an additional framework hook can cause multiple hooks to target the same context, complicating reasoning about shutdown order even though Spring's implementation guards against duplicate bean destruction.

If you are writing a plain Spring Framework application **without `SpringApplication`**, `context.registerShutdownHook()` may be the right choice. Always choose based on **who owns the context lifecycle**.

## 14. Multiple Contexts in One JVM

A process can create multiple `ApplicationContext` instances, such as running two separate business modules or using parent/child contexts. In that case:

- `SpringApplicationShutdownHook` can manage contexts registered through their respective Boot runs.
- `contextA.close()` targets only `contextA` by contract; do not assume an independent `contextB` also closes.
- Parent/child contexts have their own lifecycle relationships and event propagation; read the API of the context type in use rather than assuming "closing one closes all".
- Contexts not registered through Boot's path need their own ownership and closing mechanism.
- `SpringApplicationShutdownHandlers` run **after registered contexts** become inactive at JVM shutdown; do not access their beans inside the handler.

Thus, with multiple contexts or multiple libraries registering JVM hooks, **do not design business logic around an implicit global ordering**. Identify which context owns which resource and place stop/destroy logic in the owning context.

## 15. Why Did `close()` Run Yet the JVM Stayed Alive?

This is a common operational bug in CLIs, batch processors, or apps that spawn background threads manually.

Check in order:

1. Has `context.isActive()` transitioned to `false`?
2. Was any **non-daemon** `ExecutorService` or `Thread` created outside the container?
3. Is an SDK or library keeping connection/worker threads alive?
4. Have `SmartLifecycle` beans stopped; did `stop(Runnable)` invoke its callback?
5. Did `@PreDestroy`/destroy methods finish or block indefinitely?
6. If using virtual threads, are non-daemon carrier/keep-alive threads or other components affecting JVM lifetime?
7. Is another JVM shutdown hook blocking indefinitely once shutdown has started?

Buggy example:

~~~java
ExecutorService externalPool = Executors.newSingleThreadExecutor();
externalPool.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        // No realistic termination condition.
    }
});

context.close();
// externalPool is not part of the Spring bean lifecycle.
// The JVM may stay alive because of the worker thread.
~~~

This is an **intentionally bad example** requiring corresponding imports and a valid `context`; do not run it verbatim since the tight loop can consume CPU. The fix is to design jobs with cancellation support, shut down the executor, and await termination with a timeout—rather than using `System.exit(0)` to mask thread-management bugs.

If `context.close()` **has not returned**, look for blocking stop/destroy callbacks, especially `SmartLifecycle.stop(Runnable)`, and inspect thread dumps, logs, and timeouts. If `close()` **has returned** yet the JVM remains alive, check non-daemon threads outside the context first.

## 16. Why Was `@PreDestroy` Not Called When Killed?

Several possibilities:

- The process received `SIGKILL`/`kill -9` or was forcibly terminated by the container, so the JVM **did not run shutdown hooks**.
- `SpringApplication.setRegisterShutdownHook(false)` was used without an alternative closing mechanism.
- The object was instantiated with `new` outside Spring, not as a container-managed singleton bean.
- The bean has `prototype` scope: Spring normally **does not automatically manage destruction callbacks for individual prototype instances**.
- The context was not fully initialized or startup failed before the bean was created.
- Cleanup code hung/errored or the JVM hit the orchestrator's shutdown timeout.
- You confused context closure managed by a test framework with an actual process kill.

Do not solve every case by adding more `Runtime.addShutdownHook(...)` calls. Determine whether a **normal shutdown** was received, who owns the resource, and whether the callback sits on the right lifecycle hook.

## 17. Writing Safe Shutdown Code

Principles to follow:

**Idempotent:** repeated stop/destroy calls must not cause dangerous side effects. Spring's context `close()` guards its state, but custom-written resources still need safe logic.

**Bounded:** enforce timeouts when waiting on in-flight requests, messages, or transactions. A handler hanging indefinitely can cause the orchestrator to kill the process after the grace period.

**Do not depend on destroyed beans:** Spring shutdown handlers run after contexts close; use self-contained data or independent logging, and avoid calling beans whose lifecycle has ended.

**Do not start new tasks:** while the context is closing, avoid spawning new requests or jobs that cannot complete.

**Observable:** clearly log shutdown signal receipt, start/stop of work intake, stop completed, destroy completed, and application exited. Do not log sensitive data.

**Do not assume JVM hook order:** independent hooks may run concurrently. When strict ordering is required, use lifecycle phases or a handler API with an appropriate contract.

**Protect external resources:** critical data must be designed with transactions, ack/retry/idempotency rather than relying solely on hooks always running.

## 18. Testing Shutdown with a Standalone JVM

### Testing Manual Close

Run the demo with `--demo.mode=manual` and verify the milestones:

~~~text
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
MAIN after close active=false
BOOT_HANDLER active=false
~~~

These are **the trailing lines** of the demo. `BOOT_HANDLER` appears only when the JVM actually shuts down afterward. If another non-daemon thread remains in the JVM, the handler may appear later.

### Testing System.exit

Run a fresh JVM with `--demo.mode=exit` and compare:

~~~text
MAIN request System.exit
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
BOOT_HANDLER active=false
~~~

Note: this test **intentionally terminates the JVM**; do not run it inside the project's JUnit test runner or a process hosting other services.

### Testing SIGTERM in a Production-Like Environment

With Unix/Linux and a long-running web application:

~~~bash
java -jar my-service.jar --server.shutdown=graceful &
pid=$!

# Once the app is confirmed ready via probe:
kill -TERM "$pid"
wait "$pid"
~~~

This is an **illustrative script**, not a complete readiness-checking solution. In real testing, wait for health/readiness using a bounded condition rather than guessing with a fixed `sleep`. `SIGTERM` normally triggers JVM shutdown hooks on OpenJDK, though behavior also depends on OS/runtime/container.

### Testing Forced Failures

Never use `kill -9` as a routine test on live systems holding critical data. In an isolated environment with dummy data, you can verify that `SIGKILL` does not guarantee callbacks execute, validating recovery from message queues and transactional storage.

### Automated Testing

For bean lifecycles, you can write a `@SpringBootTest` and verify callbacks using a custom test context. However, **do not call `System.exit` inside the JUnit/Gradle test worker JVM**: it can kill the entire test runner process. To properly test JVM hooks, use an **isolated subprocess** and a test harness waiting on stdout/exit code with a clear timeout.

## 19. Quick Comparison of Shutdown APIs

| API or mechanism | When to use | What not to assume |
| --- | --- | --- |
| `context.close()` | CLI/batch managing its own context, integration tests owning context | Not equivalent to `System.exit` |
| `try-with-resources` with context | Running tasks in a bounded scope | Do not wrap a long-running web server only to close immediately |
| `SpringApplication.exit(context)` | Need to close context and compute exit code | Does not send exit code to OS by itself |
| `System.exit(code)` | Intentionally terminating a standalone JVM | Do not use to stop an individual bean/request |
| Default Spring Boot shutdown hook | Normal JVM shutdown for Boot-managed applications | Does not handle `SIGKILL` |
| `context.registerShutdownHook()` | Plain Spring Framework or manually managed context outside Boot | No need to register unconditionally in Boot |
| `SpringApplication.getShutdownHandlers()` | Sequential actions after contexts close on JVM shutdown | Does not run merely from calling `close()` |
| `SmartLifecycle.stop(Runnable)` | Stopping consumers/workers, ordered by phase | Not the final bean destruction callback |
| `@PreDestroy` / destroy method | Releasing bean resources | Not guaranteed to be called on forced kill |
| `server.shutdown=graceful` | Giving the web server a chance to drain requests | Does not guarantee infrastructure stops traffic instantaneously |

## 20. Self-Check Questions

1. **Does `ConfigurableApplicationContext.close()` call `System.exit()`?** No.
2. **Is `SpringApplicationShutdownHook` a public extension API to instantiate directly or an internal component?** It is an internal Spring Boot mechanism.
3. **Does Spring Boot 3.3 register a JVM shutdown hook for the context by default?** Yes; `setRegisterShutdownHook(true)` is the default.
4. **If you want to close the context immediately when a CLI job finishes, what do you use?** `context.close()` or `try-with-resources` matching ownership scope.
5. **If you want to close the context and compute an exit code, what do you use?** `SpringApplication.exit(context)`.
6. **Does `SpringApplication.exit(context)` terminate the JVM by itself?** No; to send the exit status to the OS you can call `System.exit(code)` afterward.
7. **When the JVM receives `SIGKILL`, are shutdown hooks guaranteed to run?** No.
8. **Does `ContextClosedEvent` occur before or after `SmartLifecycle.stop`?** Before, in the normal `AbstractApplicationContext.doClose()` path.
9. **Is a bean's `@PreDestroy` usually called before or after the lifecycle stop phase?** After, in the normal context closing path.
10. **When do `SpringApplicationShutdownHandlers` run?** At JVM shutdown, after registered contexts are closed and no longer active.
11. **`context.close()` was called yet the JVM stayed alive; what should you check?** Non-daemon threads, external executors, and resources outside the context.
12. **Should you manually call `context.registerShutdownHook()` in every Boot app?** No; Boot provides a default hook.
13. **What is the HTTP graceful shutdown setting in Boot 3.3?** `server.shutdown=graceful`, coordinated with timeouts and orchestration.
14. **Does `spring.lifecycle.timeout-per-shutdown-phase=20s` mean the entire JVM dies in exactly 20 seconds?** No; it is the timeout per stop phase.
15. **Is a custom JVM hook guaranteed to run after the Spring Boot hook?** No; independent JVM shutdown hooks have no guaranteed order.
16. **If you need to clean up a resource after `close()` in the same JVM, must you wait for a Boot handler?** No. You can execute code after `close()` returns or design an appropriate callback; Boot handlers are tied to JVM shutdown.
17. **If a `SmartLifecycle` bean stops asynchronously, what must you remember?** Call `callback.run()` when stopping actually finishes.
18. **Why shouldn't you rely solely on hooks to protect critical data?** Because forced kills, power loss, or timeouts can prevent callbacks; durable storage/message broker mechanisms are required.

**Summary:** In Spring Boot 3.3, **`ConfigurableApplicationContext.close()` is the operation that closes a context**, while **`SpringApplicationShutdownHook` integrates that closure into the JVM shutdown lifecycle**. On the normal path, the context publishes `ContextClosedEvent`, stops `Lifecycle` beans via `LifecycleProcessor`, destroys singletons, and becomes inactive. `SpringApplicationShutdownHandlers` is a separate API for actions **after registered contexts have closed during JVM shutdown**, not a callback invoked on every manual context close. To operate safely, keep the default hook unless a host manages lifecycle separately, use `SmartLifecycle` for ordered stops, `@PreDestroy` for cleanup, graceful shutdown for HTTP servers, and always test both normal shutdown and forced-kill scenarios.

### References

- Spring Boot 3.3.13 — `SpringApplication` API (includes `setRegisterShutdownHook`, `getShutdownHandlers`, `run`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `SpringApplication` reference, **Application Exit**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplicationShutdownHandlers` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationShutdownHandlers.html
- Spring Boot 3.3.13 — `SpringApplication` source code (hook registration, context refresh): https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Boot 3.3.13 — `SpringApplicationShutdownHook` source code: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplicationShutdownHook.java
- Spring Framework 6.1 — `AbstractApplicationContext` API (`close`/`doClose`/`registerShutdownHook`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.3 — **Graceful Shutdown**: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — **Actuator health groups / readiness probes**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — **Gradle Plugin / Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
