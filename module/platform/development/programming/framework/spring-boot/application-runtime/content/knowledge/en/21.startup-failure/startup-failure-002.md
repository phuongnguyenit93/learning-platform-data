# Reading the Cause Chain Instead of Only the Top-Level Message on Spring Boot Startup Failure

## 1. Why doesn't the outermost error line usually answer "where to fix"?

In Spring Boot, a failing bean can prevent the application from starting. However, an exception thrown at the failure site often passes through multiple Spring Framework layers: constructor, factory method, dependency injection, bean creation, application context refresh, and finally `SpringApplication.run(...)`. Each layer can **wrap the previous exception in a new exception** to add context.

Consequently, a log like:

~~~text
Application run failed
org.springframework.beans.factory.BeanCreationException:
    Error creating bean with name 'startupGuard'
~~~

only states that **the container could not create a bean**. It does not yet tell you **why the bean could not be created**. The cause you actually need to fix may sit deeper:

~~~text
Caused by: org.springframework.beans.BeanInstantiationException:
    Failed to instantiate [...]
Caused by: java.lang.IllegalArgumentException:
    DEMO_MISSING_SETTING
~~~

The example above **illustrates a wrapper chain**, not mandatory verbatim output for every Spring Boot version. When debugging, read the **entire `getCause()` chain**, the relevant bean/method names, and the stack frames near the origin.

### Three layers of information not to conflate

| Concept | Question it answers | Limitation |
| --- | --- | --- |
| Outermost message (`exception.getMessage()`) | What did the final calling layer observe failing? | May only say "Application run failed" or "Error creating bean" |
| Cause chain (`Throwable.getCause()` and `Caused by:`) | Which exceptions were wrapped across layers? | Not all failure relationships fit into one linear chain |
| Stack trace (`getStackTrace()` / `printStackTrace()`) | Where are the frames and methods where each exception was created/thrown? | Many framework frames; may be abbreviated or under-logged |

**Root cause** in Java terminology usually means the exception at the **end of the `getCause()` chain**. Yet the "deepest exception" is **not always enough to determine the fix**. For example, `ConnectException: Connection refused` at the bottom of the chain only says the connection was refused; you must cross-check host/port configuration, container networking, credentials, service availability, and startup timing to identify the real operational cause.

This article focuses on log-reading methodology, understanding `Throwable`, observing common Spring Boot exceptions, designing logging that preserves the cause chain, and building a Java 17+/Spring Boot lab that reproduces failures in a controlled way.

## 2. Throwable: anatomy of an exception in Java 17+

Every Java exception and error extends `java.lang.Throwable`. A `Throwable` object can contain:

- **Class/type:** e.g., `IllegalArgumentException`, `ConnectException`, or `BeanCreationException`.
- **Message:** a string set by the exception author, sometimes null.
- **Stack trace:** `StackTraceElement` entries around the failure point.
- **Cause:** another `Throwable` explaining why this exception was created.
- **Suppressed exceptions:** secondary errors, typically thrown when closing a resource in `try-with-resources`.

~~~mermaid
flowchart LR
    OUT["BeanCreationException: cannot create bean"] -->|"getCause"| MID["BeanInstantiationException: factory method failed"]
    MID -->|"getCause"| ROOT["IllegalArgumentException: invalid configuration"]
    OUT -.->|"getSuppressed, if any"| SIDE["Secondary error during cleanup"]
~~~

In this model, `OUT` is the outermost exception and `ROOT` is the exception at the end of the `getCause()` path. Secondary errors live on a **separate branch** and should not be merged as another `Caused by` in the chain.

### Essential APIs

| API | Result | When to use |
| --- | --- | --- |
| `getMessage()` | `String`, may be `null` | Read the message of **one** exception |
| `toString()` | Usually includes class name and message | Quick display of the outermost exception kind |
| `getCause()` | `Throwable` or `null` | Traverse the direct cause |
| `getStackTrace()` | `StackTraceElement[]` | Analyze creation/throw locations |
| `printStackTrace()` | Prints exception, causes, and suppressed to a stream | Standalone debugging or when no logger is set up |
| `getSuppressed()` | `Throwable[]` | Find secondary errors raised during resource cleanup |
| `initCause(Throwable)` | Attaches cause in certain valid cases | When an API lacks a cause-accepting constructor; constructors are usually preferred |
| `addSuppressed(Throwable)` | Attaches a secondary error to the primary exception | Library/resource-management; does not replace `initCause` |

**Do not construct a new `RuntimeException` with only a message** when there is an important original exception to preserve. A constructor like `new IllegalStateException("Could not initialize", cause)` keeps the chain; a message-only constructor discards it.

## 3. Reading a stack trace in the right direction

A simple example:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'pricingClient'
    at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory...
Caused by: org.springframework.beans.BeanInstantiationException:
Failed to instantiate [com.example.PricingClient]
    at org.springframework.beans.factory.support.SimpleInstantiationStrategy...
Caused by: java.lang.IllegalArgumentException:
pricing.base-url must not be blank
    at com.example.config.PricingConfiguration.pricingClient(PricingConfiguration.java:42)
    ... 24 common frames omitted
~~~

Recommended reading method:

1. **Identify when it failed:** if the log says `Application run failed`, the error occurred inside `SpringApplication.run`. If logged after `ApplicationReadyEvent`, it may be a runtime error rather than startup.
2. **Note the bean name** in the wrapper exception such as `pricingClient`; that name directs you to the factory method, constructor, or dependency.
3. **Follow every `Caused by:` line** instead of stopping at the first wrapper.
4. **Find the first exception specific enough about the invalid condition:** such as `pricing.base-url must not be blank`, `Port 8080 was already in use`, or `NoSuchBeanDefinitionException`.
5. **Find the first application-owned frame** near the meaningful cause, for example `com.example.config.PricingConfiguration.pricingClient`.
6. **Read the rest for context:** which bean required the failing bean, which profile/properties are active, earlier log errors, and whether there are suppressed/related errors.
7. **Verify with a small controlled change**, without guessing: confirm the bound value, test the port, check dependencies, or rerun in the same environment.

### "... N common frames omitted" does not mean causes are missing

Java's `Throwable.printStackTrace()` may abbreviate stack frames repeated from the enclosing exception to avoid printing duplicate lines. That is normal display formatting; it **does not mean part of the cause was lost**.

If logs are truncated by a log collector, that is a different situation: `Caused by` may genuinely not have been shipped or written. Retrieve the full log during startup, raise the collector's message limit appropriately, or fix the logging configuration.

### Read bottom-up without ignoring top-down context

A practical rule is to read the deepest exception first to learn the specific condition, then walk back up from the bottom:
- Why did that condition happen?
- Which constructor or factory method is it in?
- Which bean depends on that bean?
- Why did Spring need that bean at the current startup phase?

Do not automatically blame or patch the "class at the bottom of the stack" if it is a library or JDBC driver. Application code or configuration passing invalid input to the library may be the real cause.

## 4. Pure Java 17 example: building a clear cause chain

Before reading Spring Boot stack traces, build a plain Java program to see the cause chain clearly.

Create **`ThrowableChainLab.java`**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class ThrowableChainLab {

    public static void main(String[] args) {
        Throwable root = new IllegalArgumentException(
                "SETTING_NOT_NUMERIC");

        Throwable service = new IllegalStateException(
                "SERVICE_INITIALIZATION_FAILED", root);

        RuntimeException outer = new RuntimeException(
                "APP_BOOTSTRAP_FAILED", service);

        // Secondary error, not the cause of outer.
        outer.addSuppressed(new IOException(
                "OPTIONAL_CLOSE_FAILED"));

        printChain(outer);
        System.out.println("SUPPRESSED_COUNT="
                + outer.getSuppressed().length);
        System.out.println("SUPPRESSED_TYPE="
                + outer.getSuppressed()[0].getClass().getSimpleName());
    }

    private static void printChain(Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<>());

        Throwable current = failure;
        Throwable deepest = failure;
        int index = 0;

        while (current != null && seen.add(current)) {
            System.out.println("CAUSE[" + index + "]="
                    + current.getClass().getSimpleName()
                    + ": " + current.getMessage());
            deepest = current;
            current = current.getCause();
            index++;
        }

        System.out.println("ROOT_TYPE="
                + deepest.getClass().getSimpleName());
        System.out.println("ROOT_MESSAGE=" + deepest.getMessage());
    }
}
~~~

Build and run with Java 17+:

~~~bash
javac -encoding UTF-8 ThrowableChainLab.java
java ThrowableChainLab
~~~

Output explicitly printed by the program, in exact order:

~~~text
CAUSE[0]=RuntimeException: APP_BOOTSTRAP_FAILED
CAUSE[1]=IllegalStateException: SERVICE_INITIALIZATION_FAILED
CAUSE[2]=IllegalArgumentException: SETTING_NOT_NUMERIC
ROOT_TYPE=IllegalArgumentException
ROOT_MESSAGE=SETTING_NOT_NUMERIC
SUPPRESSED_COUNT=1
SUPPRESSED_TYPE=IOException
~~~

Here:
- `CAUSE[0]` is the outermost error, describing only that application initialization failed.
- `CAUSE[1]` describes the service-layer error.
- `CAUSE[2]` gives the more specific message about invalid data.
- `SUPPRESSED_COUNT=1` shows that the cleanup error is a **secondary branch**, not a link in the cause chain.

### Why use IdentityHashMap in the loop?

In normal exceptions, `getCause()` reaches `null`. However, `Throwable` can be customized by unusual code; if for any reason the cause graph has a cycle or the same object reappears, a blind `while (cause != null)` loop can run forever. `Collections.newSetFromMap(new IdentityHashMap<>())` tracks **object identity** without relying on `equals`, allowing the diagnostic traversal to stop safely.

This is a defensive practice when writing logging/diagnostic utilities; it does not mean Java routinely produces cyclic cause graphs.

### What happens if you only take the outermost message?

~~~java
System.out.println(outer.getMessage());
~~~

The result is only:

~~~text
APP_BOOTSTRAP_FAILED
~~~

The `SETTING_NOT_NUMERIC` message is lost. To preserve the chain in logs, log the **Throwable object**, not just its text message.

## 5. Preserving causes when throwing exceptions across layers

### How causes get lost

~~~java
try {
    connectToRemoteService();
} catch (IOException e) {
    throw new IllegalStateException("Cannot initialize remote client");
}
~~~

This is a snippet requiring `connectToRemoteService()`. The debugger sees only `IllegalStateException` and cannot tell whether the original `IOException` was a timeout, DNS failure, connection reset, or something else.

### Right way: wrap and pass the cause

~~~java
try {
    connectToRemoteService();
} catch (IOException e) {
    throw new IllegalStateException(
            "Cannot initialize remote client", e);
}
~~~

This preserves `e` under `getCause()`, allowing outer layers to still inspect the underlying I/O error.

### Do not create a cause only to drop the stack in logs

A common logging mistake:

~~~java
logger.error("Startup failure: {}", exception.getMessage());
~~~

This snippet logs only the message and does not automatically print the full stack trace. To have an SLF4J logger print the throwable with its chain:

~~~java
logger.error("Startup failure", exception);
~~~

This snippet requires `logger` to be `org.slf4j.Logger` or compatible, and `exception` to be a `Throwable`. Normally the logging framework prints the stack trace, cause chain, and suppressed exceptions according to its encoder/layout configuration.

**Do not log the same exception at every layer** if it will be rethrown upward and logged repeatedly: that produces hundreds of duplicate lines without adding information. A sound rule is to wrap with context across boundaries and log completely **once at the final handling boundary**, unless specific observability needs dictate otherwise.

### Outermost message may include the cause's message

Some Spring exceptions concatenate nested cause messages into `getMessage()`. This can make the outermost message look longer and more helpful. Still, **do not replace `getCause()` with text parsing**: the message string can omit types, stack frames, suppressed branches, or be formatted differently across versions.

## 6. Cause chains in Spring Framework and Spring Boot

An initialization error often passes through:

~~~mermaid
flowchart TD
  A["SpringApplication.run"] --> B["ApplicationContext.refresh"]
  B --> C["Pre-instantiate singleton beans"]
  C --> D["Create bean via constructor / @Bean"]
  D --> E["Bean method/constructor throws exception"]
  E -. "wraps" .-> F["BeanInstantiationException"]
  F -. "wraps" .-> G["BeanCreationException"]
  G -. "propagates" .-> H["Startup failure handling"]
  H --> I["FailureAnalyzer / log / ApplicationFailedEvent"]
~~~

The diagram **illustrates the case where a bean factory method throws an error**. Not every startup exception produces all three wrapper layers. For example, property binding, web server port, or classpath failures have different cause structures.

### What roles do Spring exceptions play?

| Class/group | Common meaning | Next reading step |
| --- | --- | --- |
| `BeanCreationException` | Container could not create bean | Check bean name, bean definition/resource, and cause |
| `UnsatisfiedDependencyException` | A required injected dependency could not be satisfied | Check which dependency failed, then that dependency's cause |
| `BeanInstantiationException` | Could not instantiate via constructor/factory | Check stack and exception from constructor/factory |
| `NoSuchBeanDefinitionException` | No matching bean found for requirement | Check scan/configuration/conditional beans/profiles |
| `NoUniqueBeanDefinitionException` | Multiple candidate beans, cannot pick one | Check `@Qualifier`, `@Primary`, generics/types |
| `BindException` or validation-related failure | Configuration could not be bound/validated | Check property key, type, value, source, and constraints |
| `PortInUseException`/web server startup error | Cannot bind port | Identify process/port/configuration |
| `ClassNotFoundException`, `NoClassDefFoundError` | Missing or failed to load/initialize class | Check runtime dependencies, shaded JAR, JVM compatibility |
| `ConnectException`, `UnknownHostException` | Cannot connect to or resolve external service | Check endpoint, DNS, network, service uptime, and policy |
| `IllegalArgumentException`, `IllegalStateException` thrown by app | Condition/argument/invariant violated | Read message and first application frame |

**Do not rely solely on the outermost exception name to automatically pick "fix config X".** For example, `UnsatisfiedDependencyException` can be caused by an implementation bean failing during initialization rather than a missing `@Component`.

### Spring NestedRuntimeException has built-in helpers

Some Spring exceptions extend `org.springframework.core.NestedRuntimeException`, which provides:

~~~java
Throwable root = exception.getRootCause();
Throwable mostSpecific = exception.getMostSpecificCause();
~~~

This snippet applies when `exception` has the appropriate type. By API contract:
- `getRootCause()` returns the **innermost cause**, or `null` if there is no cause.
- `getMostSpecificCause()` returns the innermost cause, **or the exception itself** if there is no cause.

Do not call `getRootCause()` and immediately dereference it when it could be null. For an arbitrary `Throwable` (not necessarily a Spring exception), you can safely walk `getCause()` as in the Section 4 example.

### BeanCreationException has "related causes"

`BeanCreationException` provides `getRelatedCauses()`, describing related errors encountered while creating a bean that are **not necessarily direct causes** in the `getCause()` chain. If inspecting the Java object in tooling or a debugger, check this branch too when present. Do not flatten related causes into a linear chain or pick only the last error while ignoring parallel failures.

## 7. Spring Boot FailureAnalyzer: actionable messages do not replace the cause chain

When Spring Boot fails at startup, registered `FailureAnalyzer` implementations have a chance to analyze the exception and display a friendly report, for instance:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
Embedded servlet container failed to start. Port 8080 was already in use.

Action:
Identify and stop the process using port 8080,
or configure the application to listen on another port.
~~~

This is an **illustrative example** from a port-in-use scenario, not a fixed format for every analyzer. Its goal is to pair **Description + Action** for recognized error types.

If the log has `APPLICATION FAILED TO START` with clear guidance, read it first. But if the action is still too generic or does not match reality, continue investigating the exception cause chain and environment. `FailureAnalyzer` is not guaranteed to turn every exception into an exact solution.

### When no matching FailureAnalyzer applies

Boot can log the startup exception normally. If the issue involves auto-configuration/conditional beans, you can enable:

~~~bash
java -jar app.jar --debug
~~~

or DEBUG logging for `ConditionEvaluationReportLoggingListener`. **`--debug` does not mean it always prints the cause chain for every error in the same format**; it additionally outputs the condition evaluation report, helping explain why certain auto-configurations matched or did not match.

Distinguish between:
- **Cause chain:** why an exception was thrown and wrapped.
- **Condition evaluation report:** which configuration conditions matched or did not.
- **Failure analysis:** categorized error explanation and suggested action.
- **Application startup events:** when during startup the failure occurred.

Use them in combination as needed; they are not four different names for the same thing.

### Writing a custom analyzer for recurring errors in an internal framework

Spring Boot supports creating your own `FailureAnalyzer` for a library or application. `AbstractFailureAnalyzer<T>` helps locate an exception of type `T` in the chain and return a `FailureAnalysis(description, action, cause)`.

Register a custom analyzer via:

~~~properties
# src/main/resources/META-INF/spring.factories
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.startup.DemoFailureAnalyzer
~~~

This is **`spring.factories`**, not `application.properties`. Registering via Boot metadata allows the analyzer to be loaded even when the context may not have finished initializing. Avoid expecting a normal bean to be successfully created just to analyze a failure when bean creation itself failed.

The demo below includes an optional implementation.

## 8. Spring Boot 3.5.x / Java 17+ example: deliberately failing and finding the root cause

Goal: reproduce a **bean constructor/factory failure** to watch the exception travel through Spring wrappers and find the **original IllegalArgumentException**.

Uses Spring Boot **3.5.16**, Java **17+**, Maven. Only `spring-boot-starter` is needed; no web server is required.

Structure:

~~~text
startup-cause-demo/
├── pom.xml
└── src/main/java/com/example/startup/
    ├── StartupCauseApplication.java
    └── CauseChainPrinter.java
~~~

### 8.1. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-cause-demo</artifactId>
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

### 8.2. File StartupCauseApplication.java

~~~java
package com.example.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupCauseApplication {

    public static void main(String[] args) {
        try {
            SpringApplication.run(StartupCauseApplication.class, args);
        } catch (RuntimeException failure) {
            // Lab only: Boot may have already logged the error.
            CauseChainPrinter.print(failure);
            throw failure;
        }
    }

    @Bean
    StartupGuard startupGuard(Environment environment) {
        boolean fail = environment.getProperty(
                "demo.fail", Boolean.class, false);

        if (fail) {
            throw new IllegalStateException(
                    "Failed to create StartupGuard",
                    new IllegalArgumentException(
                            "DEMO_MISSING_SETTING"));
        }

        return new StartupGuard("OK");
    }

    @Bean
    CommandLineRunner report(StartupGuard guard) {
        return args -> System.out.println(
                "STARTUP_SUCCESS guard=" + guard.status());
    }

    record StartupGuard(String status) {
    }
}
~~~

**Important points in the code:**

- `@Bean startupGuard(...)` is invoked by Spring while creating singletons needed for startup.
- With `--demo.fail=true`, the method intentionally throws `IllegalStateException` whose cause is `IllegalArgumentException("DEMO_MISSING_SETTING")`.
- Spring may wrap it in `BeanInstantiationException` and `BeanCreationException` when the factory method fails. The exact number of wrappers is a framework detail and should not be assumed fixed.
- In this lab, `main` catches a `RuntimeException` from `SpringApplication.run`, prints the chain, and **rethrows**. Rethrowing is crucial: do not swallow the failure and mislead the OS/CI into thinking startup succeeded.
- `CommandLineRunner` only runs when context creation succeeds; if the bean fails, the runner path does not execute.
- `StartupGuard` is a nested record with valid Java 17 syntax carrying a single status value for verification.

### 8.3. File CauseChainPrinter.java

~~~java
package com.example.startup;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class CauseChainPrinter {
    private CauseChainPrinter() {
    }

    public static void print(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<>());

        Throwable current = failure;
        Throwable deepest = failure;
        int depth = 0;

        while (current != null && visited.add(current)) {
            System.err.println("CAUSE[" + depth + "]="
                    + current.getClass().getName()
                    + ": " + String.valueOf(current.getMessage()));

            deepest = current;
            current = current.getCause();
            depth++;
        }

        if (deepest != null) {
            System.err.println("ROOT_TYPE="
                    + deepest.getClass().getName());
            System.err.println("ROOT_MESSAGE="
                    + String.valueOf(deepest.getMessage()));
        }
    }
}
~~~

`CauseChainPrinter` has no Spring dependency: it takes a `Throwable` and walks from the outermost exception to the innermost. `String.valueOf(...)` prevents a `NullPointerException` if a message is null, but **does not mask secrets**: production logging requires dedicated redaction and data protection policies.

### 8.4. Build and run successfully

~~~bash
mvn -q -DskipTests package
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar
~~~

Line explicitly printed by the runner:

~~~text
STARTUP_SUCCESS guard=OK
~~~

Spring Boot also prints startup logs according to its logging configuration, so do not treat that single line as the entire stdout.

### 8.5. Run the failure branch

~~~bash
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true
~~~

In the diagnostic lines printed by the demo or Boot, look for:

~~~text
ROOT_TYPE=java.lang.IllegalArgumentException
ROOT_MESSAGE=DEMO_MISSING_SETTING
~~~

The lines from `CauseChainPrinter` are a **predictable expected result** because the code explicitly builds the root exception, whereas the count and types of `CAUSE[0]`, `CAUSE[1]`, ... lines can vary depending on how Spring Boot/Spring Framework wraps exceptions. Do not write assertions like "there must be exactly four CAUSE lines" unless that is part of your application's contract.

Boot may also log `Application run failed`, `BeanCreationException`, the bean name, and a stack trace. If `SpringApplication.run` rethrows a different error in special configurations, ensure proper logging/catching; this is a lab for a typical runtime factory method failure, not a template for handling every severe `Error`.

**The line `STARTUP_SUCCESS guard=OK` will not appear in the failure branch**, because the `StartupGuard` bean is rejected before the runner can execute.

The Bash command uses `\` for line continuation; on Windows PowerShell/cmd, use a single-line command or the corresponding shell continuation syntax.

### 8.6. Reading a full startup log

On Linux/Bash:

~~~bash
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true >startup.log 2>&1

# Java may return a non-zero exit code; check immediately after the command.
echo "exit=$?"

# Find key milestones; do not rely on them as the full log.
grep -nE 'Application run failed|Caused by:|CAUSE\[|ROOT_|DEMO_MISSING_SETTING' \
  startup.log
~~~

If running in a script with `set -e`, a `java -jar` returning non-zero can abort the script before `grep` executes. Use `set +e` around the failure-inducing command in the lab, capture the exit status, and re-enable `set -e` if needed.

**Capture both stdout and stderr**, because Boot logging, stack traces, and demo code may write to different streams.

## 9. Using ApplicationFailedEvent when observing startup failures

Spring Boot publishes `ApplicationFailedEvent` when an exception occurs during startup. This event exposes `getException()` to retrieve the `Throwable`, and `getApplicationContext()` may not yet be available on very early errors.

Some application events are published **before the context exists**, so a regular `@Component`/`@Bean` listener is **not guaranteed** to receive every startup failure. Register a listener programmatically **before `run`** if you need to track very early errors:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

// Inside main(), instead of calling static run() directly:
SpringApplication app = new SpringApplication(MyApplication.class);

app.addListeners(
        (ApplicationListener<ApplicationFailedEvent>) event ->
                CauseChainPrinter.print(event.getException()));

app.run(args);
~~~

This is a **snippet** requiring actual `MyApplication` and `CauseChainPrinter` classes. Do not paste it straight into the demo file while keeping the old `SpringApplication.run(...)` call unless you intend to run the app twice.

**Listener limitations:**
- The context may be null or no longer valid, depending on the startup phase.
- Avoid requiring beans, databases, or custom loggers that may not be initialized yet.
- If a failure listener itself throws an exception, it can create extra noise and mask the original root cause.
- The event notifies you of a failure; it is not a callback to "swallow the error and recover" a failed startup.
- If the application uses a context hierarchy, events may propagate to the parent; identify the right event/context when aggregating.

### Choosing between listener, catching in main, and FailureAnalyzer

| Intervention point | Advantage | When to use |
| --- | --- | --- |
| Catch and rethrow in `main` | Easy to demonstrate, no event mechanism needed | Lab/CLI startup, testing cause chains |
| Early `ApplicationFailedEvent` listener | Captures `SpringApplication` failure signals | Startup observability with minimal dependencies |
| `FailureAnalyzer` | Produces clearer Description/Action messages | Libraries/frameworks with recurring error types |
| Logging config | Prints full stack traces and context | Most production applications |
| Integration test | Verifies exception occurrence and root cause | Regression prevention, mandatory configuration |

You do not necessarily need all three callbacks in a small application. Logging a full stack trace from multiple places creates massive duplicate noise.

## 10. Optional extension: FailureAnalyzer for a specific cause

If the `DEMO_MISSING_SETTING` error happens frequently in an internal library, you can add an analyzer:

**File `src/main/java/com/example/startup/DemoFailureAnalyzer.java`:**

~~~java
package com.example.startup;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class DemoFailureAnalyzer
        extends AbstractFailureAnalyzer<IllegalArgumentException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, IllegalArgumentException cause) {

        if (!"DEMO_MISSING_SETTING".equals(cause.getMessage())) {
            return null;
        }

        return new FailureAnalysis(
                "Demo startup guard was rejected by a deliberate flag.",
                "Run without --demo.fail=true or fix the required setting.",
                cause);
    }
}
~~~

**File `src/main/resources/META-INF/spring.factories`:**

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.startup.DemoFailureAnalyzer
~~~

The analyzer receives the root failure passed by Spring and can look up `IllegalArgumentException` in the chain. Matching on the message string is **intentional for this lab**; production code should use a **dedicated exception type** rather than matching on message strings that might change.

After adding the analyzer, rebuild:

~~~bash
mvn -q -DskipTests package
java -jar target/startup-cause-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail=true
~~~

If recognized by Boot, the `APPLICATION FAILED TO START` report can show the cause and action generated by the analyzer. `CauseChainPrinter` in main still prints CAUSE/ROOT lines if the corresponding code runs. **The analyzer does not fix the error or turn startup into a success**; it tells the operator what to do next.

Register analyzers via `META-INF/spring.factories` per Boot documentation; merely adding `@Component` to an analyzer is not an equivalent option for failures when the context has not finished initializing.

## 11. When the deepest cause is not enough: suppressed, related, async, and SQL chains

### 11.1. Suppressed exceptions

In `try-with-resources`, if both the main block and `close()` throw exceptions, the error from `close` is usually stored in `getSuppressed()` of the primary exception:

~~~java
import java.io.Closeable;
import java.io.IOException;

class ResourceDemo {
    void run() {
        Closeable resource = () -> {
            throw new IOException("CLOSE_FAILED");
        };

        try (resource) {
            throw new IOException("READ_FAILED");
        } catch (IOException e) {
            System.out.println(e.getMessage());
            System.out.println(e.getSuppressed()[0].getMessage());
        }
    }
}
~~~

This is a **valid Java 17 class snippet**; calling `new ResourceDemo().run()` prints two lines:

~~~text
READ_FAILED
CLOSE_FAILED
~~~

`CLOSE_FAILED` is a secondary cleanup error, not `getCause()` of `READ_FAILED`. If you only walk the cause chain, you miss this branch.

### 11.2. BeanCreationException related causes

Spring's `BeanCreationException.getRelatedCauses()` can return related errors raised while the container attempted to create a bean. They are **not necessarily** a single `cause->cause` chain. When a bean has complex configuration or lifecycle conditions, inspect them in the logs/debugger if present.

### 11.3. Future, CompletionException, and ExecutionException

Async tasks running in `CompletableFuture` or `Future` can wrap the real error in `CompletionException` or `ExecutionException`. When an `ApplicationRunner`/startup listener waits on `Future.get()`, the outer layer may be `ExecutionException` while the root cause originates on another thread.

Similarly, if a startup callback runs asynchronously **and is not awaited**, the exception may appear **after the app is already ready**, not necessarily causing a startup failure. Check the stack, phase, and async mechanism before assuming every error logged during deployment is a `SpringApplication.run` failure.

### 11.4. Reflection, InvocationTargetException

When invoking a method via reflection, Java may wrap the target exception in `InvocationTargetException`. `getCause()` typically returns the target exception, and `getTargetException()` also returns it per reflection design. Always look at the failing application code frame rather than stopping at "InvocationTargetException".

### 11.5. SQLException.nextException

Some JDBC failures maintain a separate `SQLException.getNextException()` chain alongside `getCause()`. For database startup issues (migrations, pools, schemas), inspect SQL state, vendor code, next exceptions, and database server logs. Do not assume the deepest `getCause()` always holds all SQL diagnostics.

### 11.6. Multiple causes and non-linear graphs

A failure can have **multiple independent causes**: multiple beans failing during init, multiple cleanup failures, or a retry after a previous error. An exception at the end of one chain is only one branch. With multi-source evidence, separate the **primary trigger error**, **secondary cleanup errors**, and **subsequent errors**. Avoid grabbing the last line of a log file and declaring it the root cause of everything.

## 12. Classifying common Spring Boot failure scenarios

### A. Error creating bean with name ...

**Read into deeper layers.** If you see `UnsatisfiedDependencyException`, read the parameter/constructor and the required bean dependency. If followed by `NoSuchBeanDefinitionException`, check component scan, `@Conditional...`, `@Profile`, `@Qualifier`, generic types, and bean registration. If followed by an exception inside a factory method, inspect that exact method and the inputs it received.

Do not fix this by marking every bean `@Lazy` just to "get the app past startup". Lazy initialization can **shift the error to the first request** and cause a production incident later.

### B. Failed to bind properties under ...

Read the key and target type. For example, `app.retry.limit` has a string that cannot parse as `int`. Inspect configuration sources that can override it: CLI, JVM system properties, environment variables, YAML/properties, profile-specific files, and secrets. If there is a validation constraint, read the validation cause. Do not log raw values if they could contain secrets.

### C. Port already in use

The outer exception may be `WebServerException`; Boot's analyzer usually gives a helpful Description/Action. Check which process uses the port, network namespaces/container/host port mappings, and embedded server config. Do not blindly change ports across configs when the root cause is an old unstopped process.

### D. Connection refused / UnknownHost

If the final cause is `java.net.ConnectException`, `UnknownHostException`, or a timeout, find the application class/method calling the remote dependency. Verify host/port, DNS, network policy, certificates/TLS, credentials, and startup deadlines. `Connection refused` means the endpoint refused the connection at that moment, not that the service is permanently down.

### E. BeanInstantiationException: constructor threw exception

Find the application's constructor frame and the exception the constructor actually threw. If the constructor performs long I/O or calls a remote service, consider refactoring initialization and validation appropriately. Do not use try/catch to hide a core failure and pretend the bean is ready to serve.

### F. NoClassDefFoundError

Do not assume it is only a missing dependency. The class may exist yet fail initialization (`ExceptionInInitializerError`), runtime classpath may differ from test/build, versions may mismatch, or packages may have changed across major versions (e.g., `javax.*`/`jakarta.*`). Read the cause of the first error and inspect the dependency tree/JAR.

### G. Circular references

Circular constructor dependencies are detected by the framework during bean creation. The exception chain may name multiple beans in a cycle. Draw the dependency graph and ask why two services need to reference each other directly instead of enabling circular references as a default fix. The solution is usually splitting responsibilities, adding an abstraction, or adjusting dependency flow.

### H. Failure right inside Environment preparation

While config data/property sources are being prepared, `ApplicationContext` is not ready to inject beans. Do not expect a `@Component` handler to always catch this failure. Register an early `ApplicationFailedEvent` listener or rely on startup logs and Boot-registered `FailureAnalyzer`s.

## 13. Practical log-reading workflow

A workflow you can apply when handed a long log file:

1. **Isolate one specific startup attempt:** use PID, timestamps, container ID, and deployment revision. Avoid mixing logs from multiple restarts.
2. **Find the termination marker:** `Application run failed` or `APPLICATION FAILED TO START`; note the time window right before it.
3. **Read the entire exception block**, not just the first line. Record the outermost class and stack.
4. **Follow `Caused by:`** down to the deepest exception in the block; check `Suppressed` and related causes.
5. **Mark the first application frame** near the error; record the bean name, configuration class, and method.
6. **Verify actual configuration sources and dependencies** in the failing environment, rather than guessing profiles from a dev laptop.
7. **Read ConditionEvaluationReport** when the error involves `@Conditional`/auto-configuration; use `--debug` with care.
8. **Verify with a minimal change and restart.** Preserve the root cause message or a failure test to prevent regressions.
9. **Report cause, impact, and evidence**, rather than pasting only a single "BeanCreationException" line.

### Searching with grep without losing context

~~~bash
grep -nE 'APPLICATION FAILED|Application run failed|Caused by:|Suppressed:|BeanCreationException|UnsatisfiedDependencyException' startup.log
~~~

This command finds milestones, but the output consists of **disconnected lines**. Continue reading the original log around those line numbers to see stack frames, application calls, profiles, and omitted messages.

When running in Kubernetes:

~~~bash
kubectl logs POD_NAME -c CONTAINER_NAME --timestamps
kubectl logs POD_NAME -c CONTAINER_NAME --previous --timestamps
~~~

Replace `POD_NAME` and `CONTAINER_NAME` with real values. `--previous` helps when a container just crashed/restarted, but only views the previous instance while the runtime retains its logs; it is not an infinite archive.

In logging pipelines that split events into separate JSON records, ensure multi-line stack traces are collected intact. If a multi-line Java stack trace is split into separate events without a shared correlation ID, search results can mislead readers about cause order.

## 14. Log security and reliability concerns

### Avoid logging secrets

Exception messages can contain:
- JDBC URLs with credentials;
- endpoint query strings or tokens;
- property values from secrets;
- connection strings and filesystem paths;
- user payloads.

Do not print `getMessage()` of arbitrary exceptions on public APIs by default or return full stack traces in HTTP responses. For internal logs, configure appropriate redaction, permissions, and retention. If notifying users, return a standardized message and a correlation ID.

### Do not swallow startup errors to fake success

~~~java
try {
    SpringApplication.run(App.class, args);
} catch (Exception e) {
    System.out.println(e.getMessage());
    // Wrong if exiting with exit code 0
}
~~~

This is an **anti-pattern snippet**, not a complete app. If `main` exits normally after catching the failure, callers may observe a success exit code even though startup actually failed. For CLIs/jobs, propagate the error to the boundary or exit with a non-zero code as appropriate.

### Do not put an entire stack trace into a metric label

The number of classes, methods, messages, and paths is huge; using stack traces as labels causes high-cardinality metrics and wastes resources. Logs and traces hold the details, while metrics use reason codes with controlled cardinality.

### Do not create new exceptions that discard the cause

When adding context:
- Use an exception class whose constructor accepts `Throwable cause`.
- Preserve the original type and message.
- Avoid wrapping in many layers that add no information.
- Never alter the original message to embed passwords.
- If an upper layer already logs completely, lower layers only need to throw the cause with context.

## 15. QA and testing checklist for startup failures

Verify the following scenarios in test/staging:

| Scenario | Verification expectation |
| --- | --- |
| Bean initializes successfully | Runner/ready reached, no startup failure |
| Bean fails configuration | Startup fails, log contains bean name + meaningful cause |
| Multi-layer wrapper | Cause chain preserves original exception |
| Exception without cause | Cause walker avoids NPE and returns the exception itself |
| Cause with null message | Logging does not throw a secondary error |
| Suppressed exception | Not lost by logging only the message |
| Custom FailureAnalyzer | Produces Description/Action on matching error without swallowing exception |
| Very early Environment failure | Does not rely on a bean listener that does not exist yet |
| Logging truncation | Full stack trace captured or truncation point identified |
| Async/runtime error after ready | Not misclassified as a startup failure |
| Production secret data | Does not leak into logs or app responses |
| Exit code | Startup failure reflects failure to deployment/CI |

**Do not equate startup testing solely with `ApplicationContextRunner`.** `ApplicationContextRunner` is great for testing bounded context configurations; by default it does not simulate all of `SpringApplication.run`, the event lifecycle, or JAR entrypoint behavior. To verify fail-fast behavior and exit codes, use integration tests running a real `SpringApplication` or a separate process.

## 16. Review questions

**1. Why is reading only `Application run failed` insufficient?**  
It is a top-level summary message; the real cause may be wrapped several layers deep.

**2. How does `Throwable.getMessage()` differ from `getCause()`?**  
Message is the descriptive string of one exception. Cause is another Throwable explaining the immediate reason and can be traversed further.

**3. What does a `Caused by:` line in a stack trace represent?**  
An exception attached as the cause of the exception being printed.

**4. Is the exception at the bottom of the chain always enough to determine the fix?**  
No. You also need the bean name, application frames, configuration, and environment.

**5. How does `getMostSpecificCause()` in Spring differ from `getRootCause()`?**  
MostSpecific returns the exception itself if there is no cause; rootCause can be null.

**6. What extra information does `BeanCreationException` usually provide?**  
The bean name, bean definition context, and nested exceptions inside.

**7. Does `UnsatisfiedDependencyException` always mean a bean is missing?**  
No. The dependency may exist but fail during creation.

**8. Why must you pass the cause when wrapping an exception?**  
To preserve the cause's type, message, and stack for upper layers.

**9. Are `Suppressed` exceptions part of the `getCause()` chain?**  
Not necessarily. They are secondary error branches, such as failures while closing resources.

**10. When should you use `--debug` in Spring Boot?**  
When you need the condition evaluation report to investigate auto-configuration/conditional beans, not as a sole replacement for stack traces.

**11. Does `FailureAnalyzer` turn a failed startup into a successful one?**  
No. It explains the error and suggested action to the operator.

**12. Why is a `@Component` listener not enough for early bootstrap failures?**  
The context may not have been created yet when very early events fire.

**13. If `main` catches an exception, logs only the message, and returns, what is the risk?**  
It may report a false success / exit code 0 even though the app failed to start.

**14. Why should you read logs from the specific restart attempt?**  
Logs from multiple processes/PIDs can interleave and mix up causes.

**15. Why shouldn't you print the full cause chain in a public HTTP response?**  
Class names, paths, configuration, or secrets could be exposed.

## 17. Official documentation

- [Java SE 17 — Throwable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause`, `getSuppressed`, `getStackTrace`, `printStackTrace`, and how Java prints nested causes.
- [Spring Boot 3.5 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `FailureAnalyzer`, failure reports, `--debug`, and startup conditions.
- [Spring Boot 3.5 — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.5/how-to/application.html): `AbstractFailureAnalyzer`, `FailureAnalysis`, and `spring.factories` registration.
- [Spring Boot 3.5 — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html): `getException()` and the possibly unavailable application context.
- [Spring Boot 3.5 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): Description, Action, and cause.
- [Spring Framework — BeanCreationException API](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/beans/factory/BeanCreationException.html): bean name, related causes, and nested exceptions.
- [Spring Framework — NestedRuntimeException API](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/NestedRuntimeException.html): `getRootCause()`, `getMostSpecificCause()`, and `contains(...)`.

**Conclusion:** when Spring Boot fails to start, do not stop at `BeanCreationException` or the outermost message. Read the **full cause chain**, identify the exception with the specific invalid condition, inspect **application frames and dependent beans**, and verify in the right environment. Tools like `FailureAnalyzer`, `ApplicationFailedEvent`, and condition reports provide valuable perspectives, but they do not replace evidence-based root cause analysis.