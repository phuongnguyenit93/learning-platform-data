# Distinguishing Context Close from Calling System.exit in Spring Boot

## 1. The problem: stopping an application differs from terminating the JVM process

In Spring Boot Application Runtime, we often need to stop an application after a batch job, finish a CLI command with a status code, or shut down a web server safely. Three operations look similar yet have **different scopes and contracts**:

- `context.close()` closes an `ApplicationContext`: stops Spring-managed lifecycle components, invokes destruction callbacks, and releases resources of **that context**.
- `SpringApplication.exit(context)` is a Spring Boot helper to **close the context and compute an exit code** from the relevant `ExitCodeGenerator` instances. It **returns an int**, without calling `System.exit` itself.
- `System.exit(code)` requests the **entire JVM** to start shutting down, runs registered shutdown hooks, and terminates the process with the supplied status code. This call **does not return normally**.

This lesson belongs to the **Exit Codes** group. We must distinguish clearly: closing resources at the Spring scope, requesting JVM shutdown at the process scope, and returning a status code to the operating system are **three distinct responsibilities**.

### One-line takeaway

~~~text
context.close()             -> closes a single Spring ApplicationContext
SpringApplication.exit(ctx) -> closes context + computes/returns exit code
System.exit(code)           -> starts shutdown of the ENTIRE JVM with status code
~~~

**Do not infer** that calling `context.close()` means the OS receives a non-zero exit code, or that calling `System.exit(7)` guarantees all Spring resources closed cleanly. When a CLI task needs to return a controlled error code, the official pattern is typically:

~~~java
int code = SpringApplication.exit(context);
System.exit(code);
~~~

This is an **illustrative snippet**, requiring `context` to be a valid `ApplicationContext` and importing `SpringApplication`. Full runnable code is in section 7. When you only want to stop a bean/consumer so it can be restarted later, use a dedicated `Lifecycle` mechanism; `System.exit` is not a pause tool.

## 2. Three scope layers: bean/context, JVM, operating system

~~~text
Host / Kubernetes / shell / CI
       |
       v
    JVM process (single PID)
       |
       +-- Spring ApplicationContext A
       |     +-- singleton beans, SmartLifecycle, DataSource...
       |
       +-- Spring ApplicationContext B (if any)
       |     +-- B's own beans and resources
       |
       +-- Non-Spring threads, native libraries, shutdown hooks...
       |
       v
    JVM shutdown -> process exit status -> shell / orchestrator
~~~

**`contextA.close()` owns closing only A**. It does not automatically close B, nor does it inherently stop all non-daemon threads or native resources created outside A's beans. A program can close context A, continue using context B, and keep functioning normally.

Conversely, **`System.exit(7)` applies to the entire JVM**, not just the current context. It initiates JVM shutdown, so other contexts and libraries in the same process are also affected.

After the process actually exits, the operating system or orchestrator can observe the **exit status**. On many systems, `0` denotes success and a non-zero value represents an unsuccessful outcome or a custom-defined condition. Do not use arbitrary exit code numbers if a scheduler/CI/Kubernetes relies on them to decide retries.

### "Context closed" and "JVM exited" do not have a one-to-one relationship

- A JVM **can keep running** after a context is closed because other threads, other contexts, or remaining `main` code are still active.
- A JVM **can exit naturally** after `main` finishes and no non-daemon threads remain, even if the code never called `System.exit`; registered shutdown hooks can perform cleanup.
- `System.exit` can make the JVM exit even while non-daemon threads are still working, though the JVM still runs shutdown hooks before halting on the standard path.
- `Runtime.halt`, `SIGKILL`, crashes, or power loss offer no guarantee that hooks will run; **never use them as a graceful shutdown mechanism**.

## 3. Exact comparison table

| Question | `context.close()` | `SpringApplication.exit(context)` | `System.exit(code)` |
| --- | --- | --- | --- |
| Belongs to API | Spring Framework | Spring Boot | Java/JVM |
| Scope | One `ApplicationContext` | Specified context and Boot exit-code logic | Entire JVM process |
| Stops `SmartLifecycle` in context? | Yes during normal close | Yes because it closes the context | Via shutdown hook/other logic if registered |
| Calls `@PreDestroy`/`DisposableBean.destroy()`? | Yes for container-owned beans | Yes because it closes the context | Not directly; Boot shutdown hook may close context |
| Destroys singletons/BeanFactory? | Yes | Yes | Not directly; depends on registered hooks |
| Computes error code via `ExitCodeGenerator`? | No | **Yes** | No; uses the caller-supplied `code` |
| Sends exit code to OS itself? | No | **No** | **Yes** when the JVM terminates |
| Return value | `void` | `int` | Does not return normally |
| Affects other contexts in same JVM? | Does not close other contexts | Does not close other contexts | Yes, shuts down the entire process |
| Can statements after the call execute? | Yes | Yes | No on the normal JVM exit path |
| Can the JVM stay alive after the call? | Yes | Yes | No once shutdown completes |
| Used in unit/integration tests? | Suitable when test owns the context | Suitable for carefully testing exit-code logic | Avoid inside the JVM test runner |
| Suitable for batch CLI returning non-zero? | Not enough | Computes code; needs mechanism to pass status to OS | Final step at process entry point |
| Suitable for live production web services? | Only when shutdown is genuinely requested | Rarely needed directly | Should not be called arbitrarily from controllers/services |

**Note on the `System.exit` column:** Spring Boot registers a JVM shutdown hook by default to close contexts created by `SpringApplication`. Thus, under normal configuration, `System.exit` can **indirectly** trigger Spring destruction callbacks. That does not mean `System.exit` calls `@PreDestroy` itself or knows about Spring beans; if the shutdown hook is disabled or unregistered, that assumption no longer holds.

## 4. What does context.close() actually do?

`org.springframework.context.ConfigurableApplicationContext` has a `close()` method. On `AbstractApplicationContext`, a normal close path includes these high-level steps:

~~~text
Code calls context.close()
   |
   +-- Begin closing ApplicationContext
   +-- Publish ContextClosedEvent
   |     +-- Listeners learn shutdown has begun
   |
   +-- LifecycleProcessor.onClose()
   |     +-- Stop running Lifecycle / SmartLifecycle beans
   |     +-- Coordinate phases and stop callbacks
   |
   +-- destroyBeans()
   |     +-- @PreDestroy
   |     +-- DisposableBean.destroy()
   |     +-- @Bean(destroyMethod="close"/"shutdown")
   |
   +-- closeBeanFactory() / complete close
   |
   v
context.isActive() == false (after close completes)
~~~

**`ContextClosedEvent` is published before all destruction callbacks run**. Listeners receiving that event should not assume database pools, executors, or clients are already closed at the exact moment the event fires.

Several principles:

1. `close()` destroys cached singletons owned by the context; prototype resources created and handed off do not automatically receive destroy callbacks simply because the context closes.
2. Spring may invoke `SmartLifecycle.stop(Runnable)` to coordinate graceful stops before destroying beans. The callback should be signaled once stopping actually finishes.
3. Repeated `close()` calls on an already-closed context are designed in Spring Framework to be ignored without destroying the same beans a second time.
4. Closing a **child context** does not close its parent context; ownership of shared resources must be defined properly.
5. After the context closes, do not treat beans with retained external references as still valid resources; they may already be destroyed.
6. `close()` **is not `System.exit`** and does not set a status code for a scheduler or shell.

### Why close does not necessarily make the JVM exit?

A Java process does not terminate merely because a Spring object closed. If **non-daemon threads**, another context, or a loop in `main` remain, the JVM keeps running. If all non-daemon threads have finished, the JVM can exit naturally after completing its shutdown sequence.

Conceptual example:

~~~java
ConfigurableApplicationContext context = launchSpringApp();
context.close();
doOtherWorkOutsideSpring();
~~~

This is **illustrative pseudocode**, not a standalone Java file. `doOtherWorkOutsideSpring()` can still execute if no exception occurs. No `System.exit` is called here.

In test frameworks, this is why you should close **the exact context owned by the test**, yet **never call `System.exit`** from a test to "clean up quickly"; that call terminates the entire test-runner JVM.

## 5. What does System.exit(int) actually do?

Java 17 defines `System.exit(status)` as a convenient call to `Runtime.getRuntime().exit(status)`. It tells the JVM to **start the shutdown sequence**, not merely close a bean or Spring context. On the normal path, this method **never returns**.

~~~text
Thread calls System.exit(7)
   |
   +-- JVM starts shutdown sequence
   +-- Launch registered shutdown hooks
   |     +-- Spring Boot hook: closes context if registered
   |     +-- Other application/library hooks
   |     +-- Order among JVM shutdown hooks is NOT guaranteed
   |
   +-- Wait for shutdown hooks to finish
   +-- JVM halts and process returns requested status
   |
   v
OS / shell receives exit status (e.g. 7)
~~~

**Subtlety:** JVM shutdown hooks are started in an **unspecified** order and may run **concurrently**. Do not write two hooks where one assumes the Spring context has already closed before the other runs. If you need ordered internal resource shutdown, use Spring lifecycle/destroy callbacks within **the same managed close path**.

The Java Javadoc also warns:
- Hooks may run when many services/threads are already shutting down.
- Hooks can deadlock or block, preventing `System.exit` from reaching halt.
- Once the shutdown sequence has begun, registering/removing hooks may throw `IllegalStateException`.
- Calling `System.exit` from inside a running shutdown hook is dangerous and can block indefinitely depending on runtime state.
- Some OSes/containers grant only a finite window for shutdown.
- `SIGKILL`, `Runtime.halt`, or crashes do not guarantee hooks run.

**It is not true that "System.exit is an immediate force kill."** It initiates a shutdown path with hooks. Yet there is **no absolute guarantee of graceful completion** either: hooks can fail, time out under an orchestrator, or out-of-JVM resources may need their own recovery mechanisms.

### What do codes passed to System.exit mean?

~~~java
System.exit(0);   // Caller requests code 0.
System.exit(7);   // Caller requests code 7.
System.exit(42);  // Caller requests code 42.
~~~

The lines above illustrate syntax, not three statements to execute sequentially. The first call puts the program into shutdown and **does not execute subsequent lines** on the normal path.

By common convention, `0` is success and non-zero is failure. However:
- The detailed meaning of `7` or `42` is defined by the application and operations team.
- Some OSes/shells have their own status encoding/representation rules; on Unix many shells display the low 8 bits of the exit status.
- A process killed by a signal, an OOMKilled container, or a failing tool wrapper may be interpreted differently by the orchestrator than a normal `System.exit(code)` call.
- Do not confuse **HTTP status codes** 500/503 with **process exit codes**. They are two protocols at different layers.

## 6. How does SpringApplication.exit() bridge the two worlds?

Spring Boot provides:

~~~java
public static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators);
~~~

This is an illustrative signature of `org.springframework.boot.SpringApplication.exit(...)`. When called with an active context, the API closes the context if possible and returns an **exit code** based on:
- Directly passed `ExitCodeGenerator` instances.
- Beans in the context implementing `ExitCodeGenerator`.
- Generator ordering rules and corresponding error handling.

Per Spring Boot 3.5, if multiple generators exist, the **first non-zero code in sorted order** is selected; order can be controlled via `Ordered` or `@Order` when needed.

### The ExitCodeGenerator interface

~~~java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

This illustrates the signature, not a definition to copy into your project. Spring Boot already provides `org.springframework.boot.ExitCodeGenerator`.

Example returning code 7 and closing the context:

~~~java
int code = SpringApplication.exit(context, () -> 7);
System.out.println("Requested exit code: " + code);
~~~

The snippet above requires a `context` variable and Spring Boot imports. **Execution can continue printing after the call**, because `SpringApplication.exit` **does not call `System.exit`**.

If `main` subsequently finishes and the JVM exits normally **without calling `System.exit(7)` or an equivalent status-forwarding mechanism**, the shell may observe **0**, even though the Java variable `code` is 7.

### Official CLI pattern: compute code then pass to the JVM

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

This is a sample snippet requiring `MyBatchApplication`, imports, and suitable beans/configuration. For a CLI, you can implement `ExitCodeGenerator` as a bean to return a code based on job results.

Another option when an external policy is needed:

~~~java
int code = SpringApplication.exit(context, () -> 7);
System.exit(code);
~~~

**Crucial difference:** `SpringApplication.exit` is responsible for closing the Spring context and determining the code; `System.exit` is responsible for making that code the **process exit status**. If your application lives inside another host (e.g., test runner, desktop app, application server, or plugin), **do not call `System.exit` yourself** just because one Spring module wants to stop.

### ExitCodeGenerator beans and exceptions

Spring Boot allows registering generators from the container:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
~~~

This is an illustrative configuration snippet to place inside a `@Configuration` or `@SpringBootApplication` class with imports. On an intentional exit path, `SpringApplication.exit(context)` can obtain code 42 from this bean.

Additionally:
- Exceptions can implement `ExitCodeGenerator` to express error codes in Boot's startup-failure paths.
- `ExitCodeExceptionMapper` can map exceptions to error codes when Spring Boot handles failures.
- `ExitCodeEvent` can be published when an exit code is determined in the corresponding lifecycle paths.
- A startup exception may occur **before `main` even receives a `context` variable**; at that point you cannot assume a context exists to call `close` yourself in `main`.

**Do not confuse:** Spring Boot's exit-code generation mechanism **does not automatically ensure the OS sees that exact number** if `main` or the host does not pass the code outward appropriately. Organizations should establish a unified exit-code policy for schedulers/CI.

## 7. Complete demo: 4 ways to terminate the same Java 17+ application

The following example uses **Spring Boot 3.5.16**, Java 17+, and creates no web server. It has one Spring-managed singleton resource, an `ApplicationRunner`, and four termination modes:

- `close`: calls only `context.close()`.
- `spring-exit`: calls `SpringApplication.exit(context, () -> 7)` but does **not** call `System.exit`.
- `system-exit`: calls `System.exit(7)` directly and lets **Spring Boot's default shutdown hook** close the context.
- `combined`: calls `SpringApplication.exit(context, () -> 7)` to close and compute the code, then calls `System.exit(code)`.

**Note:** this program intentionally contains `System.exit(7)` strictly for practicing in a **separate** process. Do not invoke this demo by executing `main` directly inside the same JVM of an IDE test runner or a server serving other tasks.

### 7.1. Project structure

~~~text
exit-boundary-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/exitboundary/
                └── ExitBoundaryApplication.java
~~~

### 7.2. Maven pom.xml

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
    <artifactId>exit-boundary-demo</artifactId>
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

`spring-boot-starter` is sufficient for this CLI demo; no `spring-boot-starter-web`, database, or Docker is needed. Use JDK 17+ and a Maven version compatible with the Boot version.

### 7.3. Complete compilable Java

File `src/main/java/com/example/exitboundary/ExitBoundaryApplication.java`:

~~~java
package com.example.exitboundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExitBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitBoundaryApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // Keep Spring Boot's default shutdown hook enabled.
        ConfigurableApplicationContext context = application.run(args);

        String mode = context.getEnvironment()
                .getProperty("demo.mode", "close");

        System.out.println("AFTER_RUN mode=" + mode
                + " active=" + context.isActive());

        switch (mode) {
            case "close" -> {
                context.close();
                System.out.println("AFTER_CONTEXT_CLOSE active="
                        + context.isActive());
            }
            case "spring-exit" -> {
                int code = SpringApplication.exit(context, () -> 7);
                System.out.println("AFTER_SPRING_EXIT code=" + code
                        + " active=" + context.isActive());
            }
            case "system-exit" -> {
                System.out.println("CALL_SYSTEM_EXIT code=7");
                System.out.flush();
                System.exit(7);
            }
            case "combined" -> {
                int code = SpringApplication.exit(context, () -> 7);
                System.out.println("CALL_SYSTEM_EXIT code=" + code);
                System.out.flush();
                System.exit(code);
            }
            default -> {
                context.close();
                throw new IllegalArgumentException(
                        "Unknown demo.mode: " + mode);
            }
        }
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner demoRunner(DemoResource resource) {
        return args -> System.out.println(
                "RUNNER resourceClosed=" + resource.isClosed());
    }

    public static final class DemoResource implements AutoCloseable {
        private boolean closed;

        public DemoResource() {
            System.out.println("RESOURCE_OPEN");
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("RESOURCE_CLOSE");
        }
    }
}
~~~

This is the **complete Java file** along with the `pom.xml` needed to run all four modes. There are no placeholder methods, fake classes, or commands depending on an external server.

**Why does this example hit the mark?**

1. `DemoResource` is a Spring-owned singleton via `@Bean(destroyMethod = "close")`; its constructor prints `RESOURCE_OPEN`.
2. `ApplicationRunner` injects that resource, guaranteeing the bean is created before the runner prints `RUNNER resourceClosed=false`.
3. `SpringApplication.run` finishes successfully before `main` selects the mode. Thus, the exercise **does not try to stop the JVM mid-constructor or mid-startup event**.
4. `--demo.mode=...` is a command-line property placed into `Environment` by Spring Boot by default, so it can be read via `getProperty`.
5. Both `context.close()` and `SpringApplication.exit` make Spring clean up `DemoResource`, but only the second helper returns an `int`.
6. `system-exit` mode relies on **Boot's default JVM shutdown hook**. If the hook is disabled via `setRegisterShutdownHook(false)`, there is no longer any basis to guarantee the resource closes on this branch.
7. `combined` mode closes the Spring context before requesting JVM exit, making Spring-level cleanup order explicit and easy to verify.
8. `DemoResource.close()` is idempotent; if Boot's hook still runs and sees the context already closed, Spring does not destroy the same singleton twice.
9. `System.out.flush()` helps push the message right before `System.exit` to output in the example; it **does not guarantee** all framework logs or out-of-process data are durably persisted.

### 7.4. Compiling the program

In the directory containing `pom.xml`:

~~~bash
mvn package
~~~

You can run:

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=close
~~~

Test with `java -jar` rather than relying solely on `mvn spring-boot:run`, because Maven plugins or IDEs may wrap the process and propagate/interpret exit codes differently from running the JAR directly.

### 7.5. Case A — close context only

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=close
~~~

The lines **printed by the example code** appear in order:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=close active=true
RESOURCE_CLOSE
AFTER_CONTEXT_CLOSE active=false
~~~

These are output markers, excluding Spring Boot's banner and logs. Explanation:
- The context started and the runner executed before `main` reached the `close` statement.
- `DemoResource.close()` was invoked via the destruction callback.
- After close, the context is inactive; however, the `AFTER_CONTEXT_CLOSE` line **still runs**, because `close()` is a normal returning Java method.
- In this non-web demo, once `main` ends and no non-daemon threads remain, the process usually exits **naturally with exit status 0**.
- **No non-zero exit code was requested** even though the context closed.

### 7.6. Case B — SpringApplication.exit computes 7 without calling System.exit

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=spring-exit
~~~

Expected markers:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=spring-exit active=true
RESOURCE_CLOSE
AFTER_SPRING_EXIT code=7 active=false
~~~

Explanation:
- `SpringApplication.exit(context, () -> 7)` retrieves the exit code from the lambda generator.
- The helper closes the context, so `RESOURCE_CLOSE` appears.
- It returns `int 7` to the caller, so the `AFTER_SPRING_EXIT` line **still executes**.
- **If `main` returns normally as in the demo**, the process exit status is usually **0**, not 7. The value `7` here lives only inside Java and was not passed to the JVM.

This is the easiest case to misunderstand: **an exit code variable holding 7 does not make the shell receive 7**.

### 7.7. Case C — System.exit(7) directly

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=system-exit
~~~

Expected markers with **Spring Boot's default shutdown hook enabled**:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=system-exit active=true
CALL_SYSTEM_EXIT code=7
RESOURCE_CLOSE
~~~

Explanation:
- Once `System.exit(7)` executes, `main` never proceeds to any statement after it.
- The JVM starts shutdown and invokes Boot's shutdown hook. The hook closes the context, leading to `RESOURCE_CLOSE`.
- The process requests exit status **7**, unlike closing the context alone.
- There is no `AFTER_SYSTEM_EXIT` line because the call does not return on the normal path.

**Set realistic expectations:** the `RESOURCE_CLOSE` marker comes from Boot's hook under default configuration. If other hooks or asynchronous logging exist, **do not rely on message ordering across different hooks**. The example has only one in-memory Spring resource, so no custom hooks compete to print markers.

### 7.8. Case D — close Spring first, then exit the JVM with the code

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
~~~

Expected markers:

~~~text
RESOURCE_OPEN
RUNNER resourceClosed=false
AFTER_RUN mode=combined active=true
RESOURCE_CLOSE
CALL_SYSTEM_EXIT code=7
~~~

Explanation:
- `SpringApplication.exit` computes 7 and closes the context first, so `RESOURCE_CLOSE` appears first.
- Only afterward does the program print `CALL_SYSTEM_EXIT` and call `System.exit(7)`.
- The process exit status is **7**.
- Boot's shutdown hook may run as the JVM exits, but there is no second effective close on the already-closed context.
- This is the easiest approach to reason about and test when a batch job needs **controlled cleanup + a deterministic status code**.

### 7.9. Demo summary table

| Mode | Context closed? | Code from SpringApplication.exit | Calls System.exit? | Commonly observed process status |
| --- | --- | --- | --- | --- |
| `close` | Yes, explicit | Helper not called | No | 0 if main exits normally |
| `spring-exit` | Yes, via helper | 7 | No | 0 if main exits normally |
| `system-exit` | Via default Boot shutdown hook | Helper not called | `System.exit(7)` | 7 |
| `combined` | Yes, before JVM exit | 7 | `System.exit(7)` | 7 |

This table assumes normal Java 17+ execution, no `SecurityManager` blocking exit, no hanging hooks, and no forced process kill. It describes the **Java process exit status**, not necessarily the exit code returned by a Maven/IDE wrapper.

### 7.10. Checking the process exit code on the OS

**Bash / zsh / POSIX-compatible shells:**

~~~bash
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
echo $?
~~~

The final output line is typically:

~~~text
7
~~~

**Windows PowerShell:**

~~~powershell
java -jar target/exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
$LASTEXITCODE
~~~

Result:

~~~text
7
~~~

**Windows cmd.exe:**

~~~bat
java -jar target\exit-boundary-demo-0.0.1-SNAPSHOT.jar --demo.mode=combined
echo %ERRORLEVEL%
~~~

Result:

~~~text
7
~~~

If you try `spring-exit` mode instead of `combined`, the demo program still prints `AFTER_SPRING_EXIT code=7`, yet when the JVM finishes normally shells typically report **0**. This is the most practical verification of the difference between *a code in a Java variable* and *the status returned by the process*.

**PowerShell note:** `$LASTEXITCODE` holds the code of the last native process. Read it immediately after the Java command, before running another native command that overwrites it.

## 8. Spring Boot JVM shutdown hook: convenient but limited

According to Spring Boot 3.5 documentation, every `SpringApplication` registers a shutdown hook with the JVM by default to ensure the `ApplicationContext` is closed when the JVM enters shutdown on a supported path.

~~~text
System.exit(7)
   |
   v
JVM shutdown
   |
   +-- Spring Boot shutdown hook
   |       |
   |       +-- ApplicationContext.close()
   |               +-- SmartLifecycle.stop(...)
   |               +-- @PreDestroy / destroyMethod
   |
   +-- Other JVM shutdown hooks (unspecified order)
   |
   v
Process terminates with code 7
~~~

Depending on configuration, Boot provides `SpringApplication.setRegisterShutdownHook(boolean)`. If you intentionally disable the hook, **your code must take responsibility for explicit cleanup** before calling `System.exit` or when the JVM exits naturally.

### Why shouldn't hooks perform all business cleanup?

JVM shutdown is a delicate phase:
- Another hook may already be stopping a resource your hook needs.
- Hooks should be short, thread-safe, and avoid unbounded waits.
- They may not run if the process is forcibly killed.
- Network connections or external brokers may no longer respond.
- A hook throwing an exception can terminate only that hook thread; there is no guarantee the system will alter the process code as you wish.

When ordering truly matters, place cleanup inside Spring bean lifecycle mechanisms such as `SmartLifecycle`, `@PreDestroy`, and `destroyMethod`, letting Spring coordinate on context close. Avoid writing multiple independent JVM hooks and relying on their timing to coordinate clients, pools, or consumers.

### What if multiple ApplicationContexts exist?

Spring can register a shutdown hook per managed context. When the JVM exits, each hook/handler can request its corresponding context to close. However, the JVM provides no ordering guarantee among independent hooks. A Spring context **does not automatically close its parent context** on close; if resources are shared across contexts, ownership must be designed explicitly.

This demo has only **one** context to avoid non-deterministic conditions.

## 9. When does the JVM actually exit without calling System.exit?

Java has two common paths into shutdown:

1. **Natural:** all non-daemon threads have finished; the JVM can begin shutdown.
2. **Explicit:** a thread calls `System.exit(status)` / `Runtime.exit(status)`.

Thus, in a simple batch CLI, after `context.close()` and after `main` returns, if no non-daemon threads remain, the JVM terminates. However, a manually created executor, timer, client, or uncleaned application thread can keep the process running indefinitely.

### Context.close is not a way to force unknown threads to stop

Conceptual example:

~~~java
Thread worker = new Thread(() -> runForever());
worker.start();
context.close();
~~~

This is **pseudocode**: `runForever()` and `context` are undefined. If `worker` is non-daemon and is not stopped, the JVM can stay alive after the context closes. You must design cancellation/interruption, `ExecutorService.shutdown()`, and await termination with appropriate timeouts—never use `System.exit(0)` to hide a leak and claim shutdown is clean.

### System.exit does not fix resource ownership bugs either

`System.exit` can make the process disappear while tasks are still uncommitted, messages unacknowledged, or files unflushed. Shutdown hooks are only a best-effort cleanup opportunity; if an important operation must guarantee zero data loss, it needs transactions, idempotency keys, durable queues, checkpoints, and dedicated recovery policies.

**Distinguish two operational requirements:**

- "**No process left running**" → check PID/process exit, timeouts, orchestrator.
- "**All work completed safely**" → check graceful shutdown, in-flight work, transaction completion, and resource cleanup.

These two are related, not synonymous.

## 10. ExitCodeGenerator and establishing an exit-code policy

In a CLI job, the exit code can serve as a public contract:

| Code | Example meaning | What the caller can do |
| ---: | --- | --- |
| 0 | Job succeeded | Record completion |
| 2 | Invalid input | Do not auto-retry; require data fix |
| 3 | Transient dependency error | Retry with backoff and limit |
| 7 | Business failure per demo contract | Record failure, alert |
| 10 | Business condition not met | Handle per job documentation |

This is an **example convention table**, not mandatory Spring Boot or OS standard codes. Each product should maintain one stable code-mapping document and avoid changing meanings once schedulers/CI depend on them.

### Using an ExitCodeGenerator bean

A simple bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

If the context contains this bean and you call `SpringApplication.exit(context)`, Spring Boot can use that generator to compute the code. In real projects, the bean typically reflects job results stored in a state holder or service with a clear lifecycle.

**You do not need `ExitCodeGenerator` if the app only returns 0 or picks a code from a local variable:** you can pass a lambda to `SpringApplication.exit(context, () -> code)` as shown. However, if exit-code logic is shared across components, a generator bean makes the contract more explicit.

### What about multiple generators?

Spring Boot 3.5 specifies that generators are sorted via `Ordered` or `@Order`, and the first non-zero value is used. Therefore:
- Do not rely on arbitrary bean registration order.
- Avoid multiple generators returning different codes without an agreed precedence.
- Test cases with multiple simultaneous errors to know which code gets selected.
- Do not assume "numerically largest wins" or "last wins" is the default rule.

### ExitCodeExceptionMapper and startup failures

When `SpringApplication.run` fails before returning a context to `main`:
- Code in `main` **does not yet have a complete `context` variable** to pass to `SpringApplication.exit(context)`.
- Spring Boot has a startup-failure handling path and can use exceptions implementing `ExitCodeGenerator` or `ExitCodeExceptionMapper` to determine an appropriate code.
- Which cleanup callbacks run depends on which beans/resources were already created and the failure stage.
- Never write `catch (Exception e) { System.exit(0); }`, as it turns a startup failure into a success signal for the scheduler.

An application entry point should handle failures intentionally: log safe context, preserve the root cause, and return an appropriate code; never swallow stack traces and default to "success."

## 11. Production web services: should you call System.exit yourself?

Generally **you should not call `System.exit` from a controller, service, or admin endpoint**. It is a JVM-level API with no way to terminate only "one request" or "one Spring module."

If an HTTP endpoint calls `System.exit(0)`:
- The entire process may enter shutdown while other requests are mid-flight.
- Other non-daemon threads will not keep the process alive long-term once shutdown proceeds.
- The response for the request triggering exit might never finish sending.
- Load balancers/Kubernetes may not have removed the pod from traffic yet.
- With status 0, the scheduler/orchestrator may view the sudden stop as normal, masking an error.

For operating web apps, prefer:
1. The orchestrator sends a stop signal (usually `SIGTERM`) per deployment mechanics.
2. Spring Boot's shutdown hook/handler closes the context on the normal JVM shutdown path.
3. Spring web server graceful shutdown stops accepting new requests and gives in-flight requests a window to complete.
4. Other `SmartLifecycle` beans stop consumers/workers by phase.
5. Resource owners close pools/clients after borrowers stop.
6. If the deadline expires, the orchestrator may force-kill; recovery is needed for uncommitted data.

If you need a "request shutdown" endpoint, design it with authorization, auditing, without calling `System.exit` mid-request thread, and with safe orchestration policy; in most systems it is best left to the deployment platform.

### Graceful shutdown in Spring Boot 3.5

According to Spring Boot 3.5 documentation, graceful shutdown is enabled by default for supported embedded servers and happens **when the ApplicationContext closes**. The timeout per phase is configurable:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

`server.shutdown=graceful` states the intent; the other property sets the wait duration for lifecycle phases. This **is not a guarantee** that every request will finish within 30 seconds; application logic must have its own timeouts/cancellation, and Kubernetes has a matching termination grace period.

Note differences across servers:
- Some servers stop accepting new connections at the network layer.
- Other servers may return HTTP 503 for new requests while gracefully shutting down.
- Once the HTTP server has stopped, the readiness endpoint may **stop responding altogether**.
- Do not use a single HTTP probe result as proof that all destroy callbacks have completed.

## 12. OS signals, kills, and shutdown hooks

### SIGTERM

On Unix/containers, `SIGTERM` normally asks the process to terminate in a way that can execute shutdown hooks if the JVM has a chance to handle it normally. With default Spring Boot, that is a common path leading to context close.

However:
- A process may install custom signal handlers.
- A shell-form Docker entrypoint without `exec` may prevent the signal from reaching the JVM as expected.
- The orchestrator may enforce a deadline and then send `SIGKILL`.
- The resulting exit status when terminated by a signal depends on the shell/runtime/container and is not identical to calling `System.exit(15)`.

### SIGKILL / Runtime.halt

`SIGKILL` and `Runtime.halt` bypass normal shutdown hooks. There is no guarantee that `@PreDestroy`, `SmartLifecycle.stop`, or `DemoResource.close()` will run. Critical data requires an independent recovery protocol.

### Container exit status

Kubernetes exposes the container termination reason and exit code. For example:
- A Java process calling `System.exit(7)` can terminate with exit code 7 and trigger restart decisions per workload policy.
- `OOMKilled` typically carries a dedicated termination reason; the displayed process code may vary by runtime.
- A Pod receiving `SIGTERM` and timing out may end in forced termination rather than a completed graceful close.
- Startup/readiness/liveness probes are distinct signals from process exit codes; **readiness 503 does not equal exit code 503**.

Inspect logs, Kubernetes events, and process status together rather than inferring one value from another.

## 13. Hard problem: shutdown hooks and cleanup order

### 13.1. Two Java shutdown hooks have no guaranteed order

Example:

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("HOOK_A")));

Runtime.getRuntime().addShutdownHook(new Thread(
        () -> System.out.println("HOOK_B")));
~~~

This is a syntax illustration. Never claim `HOOK_A` always appears before `HOOK_B`, because the JVM starts hooks in unspecified order and they can run concurrently.

A Spring Boot hook may be closing the context while a custom hook tries to use a bean from that context. That is a dangerous race. If your logic needs Spring databases/clients, execute it **inside the proper Spring bean lifecycle before destruction**, without relying on the timing of custom JVM hooks.

### 13.2. Calling System.exit from inside a shutdown hook?

Avoid it. While the JVM is already shutting down, calling `Runtime.exit` again can block indefinitely depending on the stage. Never design hook A to call `System.exit` to "force" hook B to finish. If a hanging hook requires forced termination, that belongs to an external process supervisor with a deadline, not overlapping uncontrolled exit calls.

### 13.3. Cleaning up resources before emitting the exit code is clearest

For a CLI/batch where `main` **owns the entire context**, an easy-to-verify flow is:

~~~text
Run batch
  |
  +-- Collect result and desired code
  +-- SpringApplication.exit(context) or context.close()
  |      +-- SmartLifecycle stop
  |      +-- Destroy managed resources
  +-- System.exit(code) at process entry point
  |
  v
Scheduler receives code
~~~

**Do not** call `System.exit` inside an `ApplicationRunner` while startup is still in progress unless you genuinely understand the startup/cleanup events and technical rationale. Normally, let the runner finish so `main` collects the outcome and decides the exit code.

## 14. Practical patterns for batch jobs

### Pattern A — job succeeds and should let the JVM exit naturally

~~~java
try (ConfigurableApplicationContext context =
         SpringApplication.run(MyBatchApplication.class, args)) {
    // Spring runners/jobs already executed inside SpringApplication.run().
}
~~~

This is an illustrative pattern requiring `MyBatchApplication` and imports. `try-with-resources` closes the context; if `main` exits normally and no non-daemon threads remain, the JVM exits with a typical success code of 0.

Use when:
- The job treats normal completion as success.
- No non-zero business code needs to be returned.
- You do not need to force JVM exit and want easily testable code.

### Pattern B — has ExitCodeGenerator and must return code to a scheduler

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Use when:
- A scheduler/CI depends on the process exit code.
- Spring Boot has an `ExitCodeGenerator` bean or explicit generator.
- The code resides at the **process entry point**, not in a library or test running inside another application's JVM.

### Pattern C — exit code computed in main

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyBatchApplication.class, args);

int resultCode = evaluateJobResult();
int exitCode = SpringApplication.exit(
        context, () -> resultCode);
System.exit(exitCode);
~~~

This is **illustrative pseudocode**: `evaluateJobResult()` and `MyBatchApplication` must be defined. Note that variables captured in a lambda must be effectively final in Java. When the code depends on job results, keep an explicit state/result object and avoid reading state from already-destroyed beans after `SpringApplication.exit`.

### Pattern D — host application embedding Spring as a module

~~~java
ConfigurableApplicationContext moduleContext = createModuleContext();
try {
    runModule(moduleContext);
} finally {
    moduleContext.close();
}
continueHostApplication();
~~~

This is pseudocode. In plugins, IDEs, test runners, or desktop apps, a module **must never call `System.exit` itself**, as it kills the entire host. The host code owns terminating the JVM. This is an ownership boundary akin to resource ownership, at the process level.

### Pattern E — multiple sub-jobs

If a single JVM runs multiple jobs in the same process, no sub-job should call `System.exit`. Each job returns a result object to an internal orchestrator; the orchestrator aggregates them and at the **final entry point** decides which contexts to close and the process exit status.

## 15. Common errors and how to fix them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Prints `exitCode=7` but shell reports 0 | Called only `SpringApplication.exit`, not `System.exit` | If process entry point needs the code, call `System.exit(code)` |
| Called `context.close()` but process keeps running | Non-daemon threads or another context still alive | Find thread leaks, close owner-managed resources |
| Calling `System.exit(0)` in runner stops job abruptly | `System.exit` affects the entire JVM | Move exit decision to `main`, run after job completes |
| Resource not `@PreDestroy`ed on `System.exit` | Boot shutdown hook disabled, unregistered, or force-killed | Close explicitly before exit; verify shutdown path |
| Resource closed twice | Multiple owners/hooks cleaning up, non-idempotent | Single clear owner and idempotent close |
| JVM shutdown hangs | Hook deadlock, I/O without timeout, callback never completes | Thread dumps, timeouts, avoid circular dependencies |
| Process killed with no cleanup logs | `SIGKILL`/crash/OOM | Design out-of-JVM recovery/leases |
| Scheduler treats failure as success | Exit code 0 or wrapper masking code | Map codes properly and test actual process status |
| `System.exit` kills entire test suite | Unit test calls process exit in test runner JVM | Separate code-computation logic and use subprocess for `System.exit` tests |
| `ContextClosedEvent` arrives before resources close | Event fires before destruction | Measure destruction callbacks rather than the event alone |
| Exit code from multiple generators unexpected | Generator ordering / first non-zero rule | Use `Ordered`/`@Order`, test precedence |
| Calling exit from controller returns incomplete response | JVM shuts down mid-HTTP request | Let the orchestrator coordinate shutdown |
| Process exit status differs from `echo $?` after Maven | Maven/IDE wrapper returns its own status | Run the JAR with `java -jar` and measure directly |
| In-flight jobs lost on shutdown | Timeout / incomplete stop sequence | Graceful drain, checkpoints/transactions, and retries |
| Closing a child context breaks shared pool | Child closes parent-owned resource | Fix resource ownership; independent parent lifecycle |

### Diagnostic sequence

1. Identify **who invoked** the action: `main`, runner, listener, request handler, container orchestrator, or shutdown hook.
2. Identify the **goal**: stop a bean, close the Spring context, return a code to the OS, or stop the whole process.
3. Safely log milestones: shutdown request, `ContextClosedEvent`, `SmartLifecycle` stop, bean destroy, code returned by `ExitCodeGenerator`.
4. Check `ApplicationContext.isActive()` after explicit close if execution continues.
5. If the process stays alive, inspect non-daemon threads and other contexts; do not look only for a "Spring context closed" log.
6. If the process exited, read the **actual OS/container exit code** instead of a printed Java variable.
7. If no cleanup ran, inspect Boot's shutdown hook, signs of `SIGKILL`/OOM/crash, and termination duration.
8. Cross-check error codes against CI/scheduler contracts; do not change codes to "fix" an error whose root cause is unknown.

## 16. Security, reliability, and testability

### Do not use System.exit as a general exception-handling mechanism

A library method should **throw an exception or return a result**, not terminate the JVM directly. Calling `System.exit` strips the library caller of control over retries, rollbacks, error UI, and cleanup order.

Even in a CLI, the outermost caller should decide the code. For unrecoverable errors, log appropriate context before terminating while avoiding accidental exposure of passwords, tokens, or stack traces containing sensitive data.

### Testing System.exit in a subprocess

Do not invoke `system-exit` mode directly inside the test runner JVM. Tests should:
- Verify code/context state via a separate method that does **not** call `System.exit`.
- When you genuinely need to verify exit status, launch the JAR in a **child process** via `ProcessBuilder` or a suitable process-testing framework.
- Wait for the process with a timeout; consume stdout/stderr to avoid pipe deadlocks.
- Check `exitValue()` or the result of `waitFor()`, not just logs.
- Ensure no orphaned subprocesses are left behind on test failure or timeout.

### Shutdown requires proper ownership

Spring only cleans up context-managed resources and resources with integrated cleanup. Resources created via `new Thread` or external clients without registered cleanup remain the responsibility of their owning code. Do not offload that responsibility onto `System.exit` and assume resource leaks are solved.

### Do not abuse force exit

`Runtime.halt(code)` bypasses normal shutdown hooks and can cause data loss. Only consider it at an emergency orchestration layer once consequences are understood; do not adopt it as an application coding pattern in this lesson.

## 17. Review questions

**Q1:** Does `context.close()` automatically return code 7 to the shell?

**Answer:** No. It closes the context and does not request process exit status 7. If `main` ends normally, the shell typically sees 0.

**Q2:** Does `SpringApplication.exit(context, () -> 7)` terminate the JVM?

**Answer:** No. It computes the code, closes the context if possible, and returns `int 7`. A `System.exit(7)` call or host-level equivalent is needed to pass the code to the OS.

**Q3:** Does `System.exit(7)` invoke `@PreDestroy` directly?

**Answer:** No. However, Spring Boot registers a JVM shutdown hook by default that closes the context, and that close path invokes destroy callbacks on managed singletons. If the hook is disabled or the JVM is forcibly killed, cleanup is not guaranteed.

**Q4:** Why does Spring Boot have a shutdown hook?

**Answer:** So that when the JVM enters normal shutdown, the application context is closed and lifecycle/destruction callbacks get a chance to clean up resources.

**Q5:** Does JVM shutdown hook A always run before hook B in `addShutdownHook` order?

**Answer:** No. Java gives no ordering guarantee, and they may run concurrently. Use Spring lifecycle hooks to control bean shutdown ordering.

**Q6:** Why might `System.exit` not finish quickly?

**Answer:** The JVM waits for shutdown hooks to complete. A deadlocked hook or blocking I/O can stall shutdown until the orchestrator force-kills the process.

**Q7:** When calling close while a custom non-daemon thread is still running, does the process stop immediately?

**Answer:** Not necessarily. Unfinished threads can keep the JVM alive. You must manage cancellation and shutdown of application-owned resources.

**Q8:** Can you call `SpringApplication.exit` to get a code and still run further code in `main`?

**Answer:** Yes. The method returns an `int` as shown in `spring-exit` mode, whereas `System.exit` does not return normally.

**Q9:** An `ExitCodeGenerator` bean returns 42; why might the OS still see 0?

**Answer:** Because Spring only computes the code. Without passing that code to `System.exit` or an equivalent host mechanism, normal termination can yield 0.

**Q10:** Should a Spring Boot controller call `System.exit(0)` to restart its pod?

**Answer:** That is not a safe default design. It kills the entire process, can disrupt other requests, and masks errors with code 0. Use orchestration and controlled shutdown policies instead.

**Q11:** If the JVM receives `SIGKILL`, does Boot's shutdown hook run?

**Answer:** It is not guaranteed and normally does not. You must use transactions/checkpoints/leases/TTLs/recovery for external resources.

**Q12:** In `combined` mode, what is the order of `RESOURCE_CLOSE` and `CALL_SYSTEM_EXIT`?

**Answer:** `RESOURCE_CLOSE` comes first because `SpringApplication.exit` closes the context and returns the code, and only then does `main` call `System.exit`.

**Q13:** If you run the demo in `spring-exit` mode and print code 7, what does `echo $?` in Bash usually show?

**Answer:** 0, because the JVM exited normally without being told to exit with 7. That is the core point of the demo.

**Q14:** Does closing a child context automatically close its parent context?

**Answer:** No. Closing a child does not automatically close its parent. Conversely, `System.exit` applies process-wide and can trigger shutdown on both via registered hooks.

**Q15:** Does `SpringApplication.exit` pick the largest code across all generators?

**Answer:** No. Per Boot 3.5, generators are sorted by order and the first non-zero value is selected.

## 18. Practice exercises

### Exercise A — observe two layers of "closing"

Run `close` and `system-exit` modes. Compare markers, actual exit status, and where cleanup is invoked. Explain why code after `context.close` executes while code after `System.exit` does not.

### Exercise B — exit code does not propagate automatically to the OS

Run `spring-exit` mode. Observe `AFTER_SPRING_EXIT code=7 active=false`. Immediately afterward read `echo $?` or `$LASTEXITCODE`; explain why it is usually 0. Re-run `combined` mode to see code 7 actually propagated outward.

### Exercise C — change the ExitCodeGenerator

Replace the `() -> 7` lambda in the demo with `() -> 12`. Predict the markers and process status in `spring-exit` and `combined` modes, then run to verify. Write a code-12 mapping for a scheduler and explain when to retry.

### Exercise D — ExitCodeGenerator bean

Add an `@Bean ExitCodeGenerator` returning code 5 to the project and call `SpringApplication.exit(context)` without passing a lambda. Observe the returned code; next, try two generators with different `@Order` values to verify the first non-zero rule.

### Exercise E — toggle the shutdown hook

In a test environment only, call `application.setRegisterShutdownHook(false)` before `run`, then run `system-exit` mode. Observe whether the resource destroy marker still appears. Then use `combined` mode to verify explicit `SpringApplication.exit` still closes the context before JVM exit. Never disable the hook in production without an equivalent cleanup mechanism.

### Exercise F — non-Spring thread

Create a non-daemon worker with a clear interrupt/cancellation stop point. Call `context.close` and observe the process staying alive while the worker runs. Then update the code so the worker is managed via `SmartLifecycle` or an `ExecutorService` with proper shutdown/cancellation. Test with timeouts; avoid infinite thread loops.

### Exercise G — web app graceful shutdown

Create an app with `spring-boot-starter-web`, add a time-bounded long-running endpoint, and enable graceful shutdown. Send a stop signal via the OS/orchestrator, and compare graceful drain logs against calling `System.exit` from a request handler. Never put direct exit calls into production endpoints.

### Exercise H — subprocess testing

Use `ProcessBuilder` or a separate script to launch the JAR in `close`, `spring-exit`, `combined`, and `system-exit` modes. Capture stdout/stderr, wait for the process with a timeout, and read the exit code. Write a test matrix comparing all four modes, separating process status from markers printed in Java.

## 19. Official documentation

Cross-check APIs against the exact version of Spring Boot / Spring Framework / Java you run:

- [Spring Boot 3.5 — SpringApplication, Application Exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): default shutdown hook, `ExitCodeGenerator`, `System.exit(SpringApplication.exit(...))` example.
- [Spring Boot 3.5.16 — SpringApplication API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): `exit(ApplicationContext, ExitCodeGenerator...)` and `setRegisterShutdownHook`.
- [Spring Boot 3.5.16 — ExitCodeGenerator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeGenerator.html): `getExitCode()` method.
- [Spring Boot 3.5.16 — ExitCodeExceptionMapper API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeExceptionMapper.html): exception-to-code strategy.
- [Spring Framework 6.2 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `close()` and singleton release responsibility.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): lifecycle phases, embedded server graceful shutdown, and timeouts.
- [Java SE 17 — System.exit(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)): JVM termination with process status.
- [Java SE 17 — Runtime.exit and addShutdownHook](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): unspecified hook ordering, shutdown sequence, deadlock risks.

## 20. Pre-termination checklist

1. Is the goal to **stop one worker**, **close the Spring context**, or **terminate the entire JVM**?
2. Is this code in **`main`/process entry point**, inside a **bean**, or inside a **library/test runner**?
3. Are there **other contexts** or non-daemon threads outside Spring sharing the process?
4. Are resources requiring closure managed by Spring with proper **destruction callbacks**?
5. If a non-zero process code is needed, who **computes the code** and who **passes it to the OS**?
6. Will any `ExitCodeGenerator` beans or exception mappers affect the outcome?
7. Are there multiple JVM shutdown hooks with ordering dependencies between them?
8. Could repeated stop/close calls, force-kills, or shutdown timeouts occur?
9. For web apps, are readiness/drain/graceful shutdown and orchestration timelines aligned?
10. How must the scheduler/CI/Kubernetes handle error codes, and is the real process status tested?
11. If startup fails before obtaining a context, is there a plan for partial resource cleanup and error reporting?
12. Have `System.exit` calls been kept out of beans, request handlers, test runners, and libraries?

### Final takeaway

- `context.close()` **closes the Spring context**; it does not set a JVM exit status or guarantee the whole process exits immediately.
- `SpringApplication.exit(context)` **closes the context and returns an `int` code** from `ExitCodeGenerator`; it **does not call `System.exit`**.
- `System.exit(code)` **requests whole-JVM shutdown**, triggers registered shutdown hooks, and returns the code to the OS upon termination; the method does not return normally.
- Spring Boot registers a shutdown hook by default to close the context on JVM shutdown, though hooks can be disabled or skipped on forced termination.
- JVM shutdown hooks have **no guaranteed order** and can run concurrently; ordered resource cleanup belongs inside Spring's lifecycle.
- The CLI pattern needing both cleanup and a code is **`System.exit(SpringApplication.exit(context))`** or two equivalent statements at the process entry point.
- A Java variable holding exit code 7 **does not mean** the shell receives 7; verify the actual process code.
- Never abuse `System.exit` in web requests, libraries, or tests; use orchestration, graceful shutdown, and proper recovery policies.
