# Choosing a Facade — Designing the Right Logging API for a Java Project

## 1. What Is a Logging Facade?

In Java, a **logging facade** is an **intermediate API layer** that application or library code calls to emit logs, while the actual processing and output of log records are delegated to a specific **logging backend/provider**.

The goal of a facade is to decouple business code from the underlying logging system. A developer writes:

~~~java
LOG.info("event=order.created orderId={}", orderId);
~~~

With **SLF4J**, this call goes through the SLF4J API. The backend behind it can be **Logback**, **Log4j 2** via the corresponding provider, or another implementation chosen for the application. Switching to a different backend generally does not require changing every `LOG.info` call in the source code.

Three concepts need to be distinguished:

| Concept | Responsibility | Examples |
| --- | --- | --- |
| **Facade / logging API** | Defines the methods that source code calls: logging by level, passing parameters, Throwable | SLF4J API, Log4j 2 API; JUL is also a logging API but is tied to the JDK |
| **Provider / binding / adapter** | Connects the facade to the logging execution system | Logback's SLF4J provider; log4j-slf4j2-impl |
| **Backend** | Determines levels, appenders, filters, formatting, and output destinations | Logback Classic, Log4j 2 Core, JUL via an appropriate adapter |

**SLF4J is not a log file by itself, nor does it provide a complete file-writing/rotation mechanism.** In modern versions, if only the API is present without a matching provider, the application may emit a warning and log calls will not be output as expected.

### Basic Architecture

~~~text
Application / Library
        |
        v
  org.slf4j.Logger
        |
        v
   SLF4J 2.x API
        |
        v
   Selected provider
        |
        v
  Backend (Logback / Log4j 2 / ...)
        |
        v
  Appender + Encoder / Formatter
        |
        v
  Console / File / Logging platform
~~~

Do not confuse a **facade** with a **bridge**: a facade is the API called directly by your code; a bridge is a component that forwards logs emitted through **another API** to the chosen system. For example, a legacy library using JUL may need a bridge if the entire application wants to centralize events into SLF4J.

## 2. Why Choose a Facade from the Start?

A project may begin with a few log statements and later grow into multiple modules, numerous libraries, and different runtime environments. If every class calls a backend API directly, switching backends or unifying configuration later becomes costly.

Consider two ways of depending on logging:

**Depending on a facade:**

~~~java
// Snippet inside a class, requiring the SLF4J API.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

**Depending directly on the Logback backend:**

~~~java
// Illustrative snippet, only appropriate when the Logback API is genuinely needed.
ch.qos.logback.classic.Logger logger =
        (ch.qos.logback.classic.Logger)
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

The second snippet depends on a specific implementation and can throw a **ClassCastException** if the application selects a different provider. Avoid this kind of cast in normal business code.

Choosing an appropriate facade helps:

1. **Keep business code stable** when the backend or operational policies change.
2. **Allow reusable libraries to avoid imposing an output destination** on the consuming application.
3. **Centralize configuration** of log levels, appenders, encoders, retention, and access control at the deployment layer.
4. **Reduce conflicts** when multiple modules or dependencies attempt to manage logging.
5. **Simplify testing** of output strategies suited for CLIs, web services, containers, or tests.

However, a facade does not automatically make logging faster, safer, or more complete. Performance, context, filtering, and durability ultimately depend on the backend, configuration, and log ingestion infrastructure.

## 3. Facade and API Options Worth Knowing

### 3.1. SLF4J — Usually the Sensible Default for New Java Projects

**Simple Logging Facade for Java (SLF4J)** provides the **org.slf4j.Logger** and **LoggerFactory** APIs so applications can log without referencing a specific backend's implementation classes.

Strengths:

- Broad Java ecosystem with support across many frameworks and libraries.
- **trace/debug/info/warn/error** methods, parameterized logging with **{}**, and Throwable support.
- Easy for each application to choose its own backend while libraries depend only on the API.
- Provides **MDC** and context propagation capabilities when supported by the provider.
- Can integrate other logging APIs via adapters/bridges when the project genuinely needs them.

Limitations:

- Requires selecting a **provider compatible** with both the SLF4J API version and the actual backend.
- Some backend-specific APIs or features are not fully exposed through the facade.
- Switching backends may require changing **configuration files**, patterns, encoders, appenders, and operational features even though the Logger calls remain unchanged.
- A facade cannot eliminate the cost of evaluating Java arguments before the logger method is invoked.

**Practical recommendation:** For a typical multi-module Java application without special constraints, **SLF4J 2.x is usually a good starting point for the API**, with an appropriate backend chosen afterward. This is a guideline based on common needs, not a mandatory rule for every system.

### 3.2. java.util.logging (JUL) — Built into the JDK

JUL is built into Java and uses **java.util.logging.Logger** with levels such as **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**.

Advantages:

- No extra dependencies required for basic logging.
- Suitable for small applications, JDK-only tools, or projects already standardized on JUL.
- Includes its own Handler, Formatter, Filter, LogManager, and configuration mechanism.

Limitations:

- Its API and configuration model differ from the SLF4J/Logback/Log4j 2 ecosystem.
- Features like structured fields or MDC are not as uniform as with the SLF4J facade API and modern backends.
- If the system uses SLF4J as its unified direction, you may need a JUL → SLF4J bridge to centralize logs from JUL-based components.

**There is no Level.DEBUG or Level.ERROR in JUL**; FINE and SEVERE are the closest equivalents in purpose, though they do not match every behavior of SLF4J's DEBUG/ERROR.

### 3.3. Log4j 2 API — When the Project Adopts the Log4j 2 Ecosystem

**org.apache.logging.log4j.Logger** is the Log4j 2 API. You can write code against this API and pair it with a corresponding implementation such as **Log4j 2 Core**. The Log4j 2 ecosystem offers extensive configuration and extension capabilities of its own.

Consider it when:

- The existing project is already standardized on the Log4j 2 API.
- You need API features or observability architecture tightly coupled to Log4j 2.
- Existing operational standards or dependency policies already mandate this stack.

**Do not assume the Log4j 2 API is SLF4J.** Adapters exist to connect the two ecosystems, but you must choose the right direction, matching versions, and avoid bridge loops.

### 3.4. Commons Logging (JCL) — Common in Legacy Projects

**Apache Commons Logging (JCL)** is a logging API found in many traditional Java libraries. When maintaining legacy systems, you may encounter **org.apache.commons.logging.Log**.

There is no need to introduce JCL into a new project just to write logs. If a legacy dependency uses it, you can keep it as-is and use the framework's compatibility solution. Evaluate how logging is already integrated in the system before adding adapters yourself.

**Note:** Many frameworks have their own logging integration mechanisms. If the project uses Spring Boot or a pre-configured platform, follow the framework's dependency/configuration mechanism rather than forcing every library into a custom setup.

## 4. Comparison Table

| Criterion | SLF4J API | JUL | Log4j 2 API |
| --- | --- | --- | --- |
| Built into the JDK? | No | Yes | No |
| Decouples code from a specific backend? | Yes, primary goal | Not under the same multi-backend facade model | Provides API/implementation separation within the Log4j 2 ecosystem |
| Common level names | TRACE, DEBUG, INFO, WARN, ERROR | FINEST/FINER/FINE, CONFIG, INFO, WARNING, SEVERE | TRACE, DEBUG, INFO, WARN, ERROR, and additional API-specific levels |
| Library dependency | Usually only slf4j-api | No dependency outside the JDK | log4j-api |
| Output destination | Configured by provider/backend | JUL Handler | Corresponding implementation/backend |
| MDC/context | MDC API, depends on provider and propagation | No direct equivalent MDC API | ThreadContext/corresponding API |
| Best suited for | Java apps/libraries wanting backend flexibility | Pure-JDK tools, JUL-standardized stacks | Projects already committed to the Log4j 2 API/stack |
| Pitfalls to avoid | Missing/duplicate provider, version mismatch, bridge loops | Expecting LOG_LEVEL=DEBUG to work automatically, assuming Level.DEBUG exists | Wrong adapter direction, mixing multiple backends |

**A criterion more important than the library name:** does the facade fit your current architecture, library contracts, active versions, and operational practices? Do not choose based solely on an isolated benchmark that does not reflect your system's configuration and workload.

## 5. Decision Process for Choosing a Facade

You can work through the following questions in order.

### Step 1: Are You Writing an Application or a Reusable Library?

- An **application** is responsible for choosing the backend, configuring levels, appenders, retention, and integrating with the log collection system.
- A **library** should emit logs through an appropriate API and **must not impose a backend**, because the consuming application needs process-wide control over logging.

If you are writing a shared library without an existing mandatory standard, **depending only on slf4j-api** is usually appropriate. Do not add logback-classic or log4j-core as a required runtime dependency of a library just so the library can log.

### Step 2: What Logging Stack Does the Project Already Have?

Inspect existing logging dependencies, frameworks, and configurations. If the application is already standardized on SLF4J/Logback, calling the SLF4J Logger in new code is usually simplest. If a project is pure JUL and only needs built-in features, migrating everything to another stack may not be worth the cost.

Do not adopt a new facade without checking what APIs existing modules already use; doing so can increase the number of bridges, backend conflicts, and maintenance overhead.

### Step 3: Are There Any Special Deployment Requirements?

Certain requirements may influence backend/configuration choices without necessarily forcing a facade change:

- Structured JSON output with a clear schema and request/trace ID correlation.
- Console logging for containers, file rotation, and asynchronous appenders.
- Runtime level changes and filtering by package or component.
- Latency, throughput, and I/O pressure control.
- Security, masking, retention, and auditing.

For instance, **wanting JSON output is not a sufficient reason to drop SLF4J**; choosing an appropriate backend and JSON encoder can solve that. Conversely, if you need backend-specific APIs in source code, you must either accept that coupling or design your own abstraction.

### Step 4: Choose One Primary Provider/Backend

With SLF4J 2.x, your options include:

- **Logback Classic:** a common backend supporting appenders, encoders, filters, and configuration via logback.xml.
- **Log4j 2 via the corresponding provider:** useful if your infrastructure is already standardized on Log4j 2.
- **slf4j-simple:** a lightweight backend for demos and simple tools; not a replacement for full production logging needs.
- **slf4j-jdk14:** connects SLF4J to JUL in systems that must use JUL as the backend.

**Do not attach multiple SLF4J providers at the same time** expecting all of them to write logs: the runtime may pick one provider and ignore the others with a warning. One primary backend and a clear routing architecture are usually easiest to operate.

### Step 5: Check How Libraries Use Other APIs

An application may use SLF4J in new code while legacy dependencies use JUL, JCL, or the Log4j 2 API. When consolidating output, choose the **bridge in the right direction**, inspect the dependency tree, and avoid creating loops.

### Step 6: Verify by Running the System

- Are INFO/WARN/ERROR logs reaching the expected destination?
- Is DEBUG hidden at the INFO threshold and visible at the DEBUG threshold?
- Do Throwables include stack traces when needed?
- Is there exactly one log record per event?
- Does MDC/trace context propagate properly across async tasks?
- Is sensitive information excluded or masked?

**Choosing a facade is an architectural decision, but it must be validated by running the actual system.**

## 6. Complete Example: Choosing SLF4J, Implemented with Logback

The goal is to demonstrate that the code uses only the **SLF4J API**, while the backend and output format are determined in **logback.xml**.

Requirements: **JDK 17+**, Maven 3.x, and the ability to download dependencies (the first run requires repository access unless already cached).

### 6.1. Project Structure

~~~text
facade-choice-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── FacadeChoiceDemo.java
        └── resources/
            └── logback.xml
~~~

### 6.2. Create pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>facade-choice-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FacadeChoiceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**This example uses specific versions** and does not claim they are the latest releases. In a real project, verify compatibility and security patches according to your project's dependency management; do not add a second provider.

### 6.3. Create src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

This configuration sets:

- **Root INFO**: INFO, WARN, and ERROR are accepted under normal level rules; DEBUG is filtered out.
- **ConsoleAppender**: sends events to **System.out** by default in Logback's ConsoleAppender.
- **Pattern**: prints the log level, a separator, and the message; omits the timestamp so output is easy to compare.
- **UTF-8**: handles Unicode when supported by the terminal/collector.
- The appender is attached only at the root logger, avoiding duplicate appender configuration on child loggers.

### 6.4. Create src/main/java/demo/FacadeChoiceDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FacadeChoiceDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(FacadeChoiceDemo.class);

    public static void main(String[] args) {
        String orderId = "ORD-7";

        LOG.debug("event=order.validation orderId={} passed=true", orderId);
        LOG.info("event=order.received orderId={}", orderId);
        LOG.warn("event=order.retry orderId={} attempt={}", orderId, 2);
        LOG.error("event=order.failed orderId={} code={}",
                orderId, "REMOTE_TIMEOUT");
    }
}
~~~

This code **imports only org.slf4j.Logger and LoggerFactory**, not Logback's Logger class. Therefore, the facade remains SLF4J; Logback is present only in dependencies and configuration.

### 6.5. Compile and Run

In the **facade-choice-demo** directory:

~~~bash
mvn -q compile exec:java
~~~

With the files and configuration above, the **stdout emitted by the program** (excluding Maven or runtime environment output) is:

~~~text
INFO | event=order.received orderId=ORD-7
WARN | event=order.retry orderId=ORD-7 attempt=2
ERROR | event=order.failed orderId=ORD-7 code=REMOTE_TIMEOUT
~~~

The DEBUG line is not printed because the root level is INFO. SLF4J's **{}** placeholders are replaced by arguments, whereas **%level | %msg%n** is Logback's pattern syntax; these are **two separate formatting layers**.

### 6.6. Try Enabling DEBUG Without Modifying Java Code

Change `logback.xml`:

~~~xml
<root level="DEBUG">
    <appender-ref ref="STDOUT"/>
</root>
~~~

Run the application again. **The application's stdout** now includes the first line:

~~~text
DEBUG | event=order.validation orderId=ORD-7 passed=true
INFO | event=order.received orderId=ORD-7
WARN | event=order.retry orderId=ORD-7 attempt=2
ERROR | event=order.failed orderId=ORD-7 code=REMOTE_TIMEOUT
~~~

The change is entirely in backend configuration, **with no changes needed to facade calls in the source code**.

## 7. Switching Backends: Keeping the SLF4J API While Replacing Logback

Suppose you only want simple logging in a quick test tool. You can replace the **logback-classic** backend dependency with an SLF4J 2.x–compatible **slf4j-simple**, while keeping the SLF4J API.

In `pom.xml`, keep the `slf4j-api` dependency and replace the **entire logback-classic dependency** with:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

The Java file **FacadeChoiceDemo.java** does not need any edits. Keep in mind:

- **slf4j-simple** has its own configuration and formatting mechanism; **logback.xml is no longer read by this backend**.
- The default output of slf4j-simple **differs from the Logback format in Section 6** and is typically written to **stderr**, so you cannot assume the same three stdout lines for the new backend.
- To adjust levels and formatting, consult slf4j-simple's configuration rather than keeping Logback's configuration.
- You must **remove the Logback provider from the runtime classpath**; adding slf4j-simple while keeping logback-classic creates a multiple-provider situation.
- Switching backends does not automatically preserve features such as async appenders, file rotation, or JSON encoders. Those capabilities must be re-verified.

This illustrates both the benefit and the boundary of a facade: **logging call sites stay the same, while deployment and configuration still must be adapted appropriately**.

## 8. Applications vs. Libraries: Different Dependency Decisions

### 8.1. Applications Choose Their Own Backend

For a web, worker, or CLI application that logs at runtime, the typical dependency chain is:

~~~text
application code
    -> slf4j-api
    -> one SLF4J provider
    -> corresponding backend
~~~

For example, Logback Classic is chosen as the primary provider/backend. The application decides where logs go, which levels are recorded, how retention works, and how `requestId`/`traceId` are attached to events.

### 8.2. Libraries Depend Only on the Facade

For a library reused across multiple applications, the main dependency should be the API, for example:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.17</version>
</dependency>
~~~

A library should not declare **logback-classic** or **slf4j-simple** as a required runtime dependency just because it calls a logger; doing so can force a backend onto the consumer's application. In the library's own tests, you can include a simple provider in `test` scope if you need to assert log output.

A library should also avoid:

- Calling `LoggerContext.reset()` and altering application-wide logging.
- Attaching appenders directly to the root logger.
- Changing logging levels or formats for packages outside the library.
- Logging sensitive data or forcing the application to create log files at a fixed path.

**Ownership of overall logging configuration belongs to the application or orchestrating framework**, not to individual libraries.

### 8.3. Managing Versions

In **SLF4J 2.x**, provider discovery is based on **ServiceLoader**. This is a major change from the legacy static binding mechanism of SLF4J 1.7.x.

Therefore:

- Do not assume **bindings for SLF4J 1.7** are automatically compatible with **SLF4J 2.x**.
- The versions of `slf4j-api`, the provider, and the backend must be compatible with one another.
- When an older library pulls in a different API/provider version, inspect the **dependency tree**, apply dependency management, and exclude conflicting dependencies.
- Do not try to fix "no logs appearing" by randomly adding multiple bindings/providers.

Having only the API without a compatible provider can prevent events from being logged as expected. Having multiple providers causes the runtime to pick one and emit a warning; do not treat that as a way to log simultaneously to multiple backends.

## 9. Bridges and Adapters: Choosing the Right Direction

When existing libraries use another logging API, an application can consolidate logs by routing events into the primary stack. Some common routes:

~~~text
Code using JUL
       |
       v
jul-to-slf4j  (requires installing the appropriate bridge)
       |
       v
   SLF4J API
       |
       v
  Logback provider / backend
~~~

~~~text
Code using SLF4J 2.x
       |
       v
log4j-slf4j2-impl
       |
       v
Log4j 2 backend
~~~

~~~text
Code using Log4j 2 API
       |
       v
log4j-to-slf4j
       |
       v
SLF4J provider (e.g., Logback)
~~~

**Several critical notes:**

| Component | Primary Routing Direction | Notes |
| --- | --- | --- |
| jul-to-slf4j | JUL → SLF4J | Requires installing/configuring the bridge properly; having the JAR alone may not forward all logs |
| slf4j-jdk14 | SLF4J → JUL | An SLF4J provider backed by JUL, not a reverse bridge |
| log4j-to-slf4j | Log4j 2 API → SLF4J | Used when Log4j 2 API calls should be routed to SLF4J |
| log4j-slf4j2-impl | SLF4J 2.x → Log4j 2 | The opposite route, used when Log4j 2 is the backend |
| jcl-over-slf4j | JCL API → SLF4J | Can serve libraries using Commons Logging; check dependencies and how the framework handles JCL |

**Never install two opposing directions at the same time so that they point into each other.** In particular, combining **log4j-to-slf4j** with **log4j-slf4j2-impl** in the same setup creates an invalid forwarding loop. Likewise, **jul-to-slf4j** paired with an SLF4J → JUL provider such as **slf4j-jdk14** is a dangerous combination that routes records in both directions.

Bridges must be installed at the application layer that controls logging. A JUL → SLF4J setup also requires attention to JUL's own thresholds: events filtered out by JUL before reaching the bridge will not appear in the new backend. Do not assume that adding a dependency alone forwards every level.

## 10. How Does a Facade Differ from an Adapter, Wrapper, and Backend?

Some systems add a custom **wrapper** written by the project to standardize event codes, required fields, sensitive-data masking, and context propagation. In that case, you might have:

~~~text
Business code -> ProjectLogger -> SLF4J -> Logback
~~~

This wrapper does not necessarily replace SLF4J; it can serve as an additional layer enforcing internal conventions. However, an overly thick wrapper can obscure the facade's ability to pass Throwables, placeholders, markers, or use a fluent API.

Four concepts should be kept distinct:

1. **Facade/API:** the logging contract at the source-code level.
2. **Provider/binding:** the component connecting the facade to the chosen implementation.
3. **Backend:** event processing and output policies.
4. **Bridge:** forwards events from another logging API into the primary stack.

Each component does not have to live in a separate JAR; packaging depends on the library. What matters is understanding the **dependency direction** and **where configuration lives**.

## 11. Using a Facade Properly in Business Code

### 11.1. Obtain Loggers by Class Name

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
~~~

This is a **snippet inside the PaymentService class**, not a standalone program. Obtaining a logger per class produces clear logger names and allows setting thresholds by package.

Do not create a new logger named after a `requestId` or `orderId` for each operation. Such IDs belong as **context/fields** in events, not in the logger name hierarchy.

### 11.2. Placeholders and Argument Evaluation Cost

In SLF4J:

~~~java
LOG.debug("event=discount.checked orderId={} matched={}",
        orderId, matched);
~~~

Use **{}** so the backend can format the message with the arguments. However, Java evaluates arguments before calling the logger:

~~~java
LOG.debug("payload={}", expensiveSerialize(payload));
~~~

Even when DEBUG is disabled, **expensiveSerialize(payload)** still executes. For costly computations:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

These are **illustrative snippets**: they assume surrounding variables and methods in the enclosing class. Newer SLF4J versions also offer a fluent API for logging, but check the version and supplier usage supported by your project; do not assume every expression passed to a logger is evaluated lazily.

**Never embed required business logic inside a debug message call.** When the log level changes, logic tied to logging might not execute.

### 11.3. Logging Throwables with Context

~~~java
try {
    callRemoteService();
} catch (java.io.IOException ex) {
    LOG.error("event=remote.call.failed requestId={}",
            requestId, ex);
}
~~~

This is an **illustrative snippet** inside a class with `LOG`, `requestId`, and `callRemoteService()`. Passing the **Throwable** allows the backend to record the stack trace and cause chain; the encoder decides the actual representation.

Do not log only `ex.getMessage()` and lose the error context, and do not log the same exception at every layer if that only produces duplicate stack traces.

### 11.4. MDC and Trace Context

SLF4J provides the MDC API to carry key-value pairs for event correlation, such as `requestId`:

~~~java
// Illustrative snippet inside a method that has LOG.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

The backend must configure an encoder/pattern to include MDC fields in the output—for example, Logback uses **%X{requestId}**. **MDC does not automatically propagate across all thread pools, CompletableFutures, or reactive tasks**; proper propagation mechanisms and cleanup when work finishes are required.

Never put passwords, tokens, session cookies, or sensitive personal data into MDC.

## 12. What Changes When Switching Backends

Even when SLF4J-based code stays unchanged, switching backends can still alter:

| Area | Examples to Verify |
| --- | --- |
| Level configuration | Are package names, root logger, and filters still equivalent? |
| Destination | Do ConsoleAppender, FileAppender, or another backend actually write to the right place? |
| Formatter/encoder | Are patterns, JSON, timestamps, timezones, and escaping as expected? |
| Throwable | Are stack traces and cause chains still output completely? |
| MDC/context | Are correlation fields carried through to the encoder and collector? |
| Async logging | When queues overflow or the process shuts down, what are the drop/flush policies? |
| File rotation | Are file size, count, retention, and paths still valid? |
| Security | Have masking, file permissions, or retention periods changed? |
| Performance | Formatting overhead, I/O, buffering, and resource pressure under real load |

No facade guarantees 100% identical runtime behavior across backends. **A facade primarily stabilizes the interface for calling code**, rather than standardizing every implementation detail.

## 13. Considerations for Frameworks and Existing Projects

### 13.1. Spring Boot Applications

Spring Boot has its own logging management and default dependencies depending on starters, versions, and project configuration. If SLF4J + Logback is already the primary stack, **do not add another backend** just to use a Logger.

Inspect the dependency tree and configure **logging.level...**, backend configuration files, or environment variables according to the Spring Boot version in use. Do not assume a JUL `logging.properties` file will directly control all logs going through Logback.

### 13.2. Pure-JDK Applications or Small CLI Tools

If it is a simple utility with no framework and minimizing dependencies is a high priority, **JUL may be enough**. Adding SLF4J + a backend makes sense when you want a unified API across multiple modules, but it is not mandatory for every Java program.

### 13.3. Libraries Embedded in Multiple Applications

Choose an API that fits your target ecosystem; **SLF4J** is a very common choice. Avoid forcing consumers to use `logback.xml` or a specific provider; instead, document logger names, levels, and key events so applications can decide how to output them.

### 13.4. Projects Already Standardized on the Log4j 2 API

You can continue using the Log4j 2 API if the entire organization or system already uses it consistently and there is no reason to migrate. If you want new code to use SLF4J, choose the appropriate **SLF4J → Log4j 2 provider** and avoid accidentally installing a bidirectional bridge. Rewriting all source code just to unify Logger names is rarely better than configuring clear routing.

## 14. Security When Choosing a Facade and Backend

**Using a facade does not make a log record secure by default.** Regardless of the API, protect:

- **Secrets:** passwords, access tokens, API keys, private keys, session cookies.
- **Personal or payment data:** log only the minimum allowed by policy.
- **Untrusted input:** may contain newlines, control characters, or log-forging strings; use an encoder with proper escaping.
- **Throwables/stack traces:** may expose paths, arguments, or internal data; enforce access control and masking.
- **Files and centralized systems:** read permissions, retention, collection, and downstream data handling.

Do not log full HTTP bodies, authorization headers, or `object.toString()` just because DEBUG is enabled. Structured logging and MDC make searching easier, which also increases the need for strong data protection.

## 15. Performance and Reliability

A `LOG.info` call does not guarantee that a log record has been durably persisted. The provider or backend may filter, buffer, drop, or fail when sending it. Therefore:

- **Measure under realistic load:** especially when DEBUG is enabled, many stack traces are logged, or JSON is emitted.
- **Use appropriate levels:** INFO for milestones, DEBUG for investigation, WARN/ERROR for significant anomalies.
- **Avoid logging inside high-throughput loops** unless there is clear diagnostic value.
- **Use metrics for rates/counts and tracing for distributed flows**, rather than emitting a log line for every measurement.
- **Do not treat logs as guaranteed storage for critical transactions/audits** if the system requires a dedicated durable storage contract.
- **Consider shutdown/flush behavior** for appenders if the backend requires it, while recognizing that local flushing still does not guarantee a remote collector has persisted the data.

Performance is usually determined far more by the **backend and configuration** than by the facade name alone. Do not choose based solely on a microbenchmark that does not represent production traffic.

## 16. Diagnosing Provider Conflicts and Missing Logs

A practical checklist:

1. **Identify the actual Logger API**: is the code importing `org.slf4j.Logger`, `java.util.logging.Logger`, or `org.apache.logging.log4j.Logger`?
2. **Inspect the classpath and dependency tree**: how many SLF4J providers are present? Are both `logback-classic` and `slf4j-simple` included?
3. **Check version generations**: does `slf4j-api` 2.x have a ServiceLoader-compatible provider?
4. **Verify adapter direction**: Log4j 2 API → SLF4J or SLF4J → Log4j 2?
5. **Check for bridge loops**: `log4j-to-slf4j` alongside `log4j-slf4j2-impl`, or JUL → SLF4J paired with SLF4J → JUL?
6. **Check log levels**: what is the effective level of the specific logger and any appender filters?
7. **Check the output destination**: stdout, stderr, file, or collector; are you looking at the wrong stream or path?
8. **Check which config file is loaded**: `logback.xml`, `log4j2.xml`, `logging.properties`, or a framework-specific file?
9. **Verify message and Throwable formatting**: placeholders, encoder, stack trace, timezone, and charset?
10. **Check for delayed/dropped collection**: sampling, buffering, network loss, or storage limits?

In Maven, you can inspect dependencies with:

~~~bash
mvn dependency:tree
~~~

This is a Maven diagnostic command, not a logging API. Check both direct and transitive dependencies; sometimes a starter already brings in a backend that the application does not need to add again.

**Seeing no logs does not mean the code did not run**; you must inspect the configuration and event routing path.

## 17. Common Mistakes When Choosing a Facade

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using a backend Logger class in every service | Hard to switch backends, prone to cast errors | Use an appropriate facade API in business code |
| Library adds `logback-classic` as a required dependency | Forces a backend onto applications | Library depends only on the API; application chooses the provider |
| Adding only `slf4j-api` with no runtime provider | Logs do not appear as expected | Add one compatible provider |
| Having two SLF4J providers on the classpath | Warnings, unintended backend selected | Inspect dependency tree and exclude conflicts |
| Using a 1.7 binding with SLF4J 2.x API | Provider is not selected properly | Align version generations |
| Installing bidirectional Log4j 2 bridges simultaneously | Risk of forwarding loops | Choose one direction matching the architecture |
| Installing `jul-to-slf4j` and `slf4j-jdk14` in a circle | Wrong routing/loops | Do not configure opposing directions together |
| Switching from Logback to Simple while expecting `logback.xml` to work | Configuration is ignored | Use the new backend's config file/properties |
| Assuming a facade guarantees logs are persisted | Records may be lost due to filters/I/O | Verify appenders, collectors, and retention |
| Mechanically using `{}` with JUL | Messages are not formatted as expected | Distinguish each API's placeholder syntax |
| Expensive string concatenation before debug | Wastes CPU even when DEBUG is off | Use parameterized logging and appropriate guards |
| Logging tokens or raw payloads | Data exposure | Log minimal fields, mask data, and enforce access control |

## 18. Practice Exercises and Self-Check Questions

**Exercise 1 — Reusable Payment Library.** A library is embedded in three applications: App A uses Logback, App B uses Log4j 2, and App C has not chosen a backend yet. Should the library add `logback-classic` itself?

**Answer:** Usually no. The library can choose the SLF4J API and emit events with appropriate logger names and levels. Each application decides its own provider/backend and output configuration.

**Exercise 2 — Facade Without a Provider.** Code compiles because `slf4j-api` is present, but no INFO logs appear at runtime. What is the first thing to check?

**Answer:** Check whether a compatible SLF4J provider exists and whether there are version/classpath conflicts, then check logger levels, appenders, and output destinations.

**Exercise 3 — Switching Backends.** An application replaces `logback-classic` with `slf4j-simple` while still using `org.slf4j.Logger`. Do `LOG.info` calls in Java need to change?

**Answer:** Usually no, as long as the SLF4J API remains compatible. However, you must update/verify the backend configuration, formatting, and output destination, and remove the old provider from the runtime classpath.

**Exercise 4 — Log4j 2 Bridge.** A library uses the Log4j 2 API, and the application uses SLF4J + Logback. Which routing direction should you look for?

**Answer:** Look for a **Log4j 2 API → SLF4J** adapter such as `log4j-to-slf4j`, and avoid adding the reverse SLF4J → Log4j 2 provider in the same routing path.

**Exercise 5 — Pure JUL.** A small tool uses only the JDK and has no framework. Is it mandatory to add SLF4J?

**Answer:** No. JUL can cover basic logging needs. The decision depends on deployment requirements, multi-module consistency needs, and dependency management preferences.

**Exercise 6 — Expensive Arguments.** Does `LOG.debug("payload={}", costlySerialize(payload))` avoid calling `costlySerialize` when DEBUG is disabled?

**Answer:** No. Java evaluates arguments before the method call. If the computation is expensive, use an `isDebugEnabled` guard or a valid lazy-logging mechanism supported by the API/version in use.

**Exercise 7 — Security.** If DEBUG is disabled in production, is it safe to pass an access token into `LOG.debug`?

**Answer:** No. Levels can be changed dynamically or logs may be collected in another environment. Never log secrets at any level.

**Exercise 8 — Separating Responsibilities.** Who decides file rotation: the facade or the backend?

**Answer:** The backend, appender, and operational configuration. The facade only provides the API for log-emitting code; it does not define rotation policies itself.

## 19. Summary and Selection Rules

**Choosing a facade means choosing the API your source code will depend on long-term; choosing a backend means choosing how logging is executed and operated.**

For a **modern Java application without existing constraints**, a sensible choice is usually **SLF4J API + one provider/backend** suited to your framework and infrastructure (such as Logback). For a **reusable library**, prefer depending only on the facade and never imposing a backend. For a **small Java tool**, built-in JUL from the JDK may be sufficient. For a **system already standardized on the Log4j 2 API**, you can keep the current choice if it meets your requirements.

Whatever you choose, uphold four principles: **a clear routing architecture, compatible versions, configuration at the responsible layer, and runtime verification of levels/destinations/Throwables/security**. That is the foundation for useful logs without locking business code into an unnecessary implementation.
