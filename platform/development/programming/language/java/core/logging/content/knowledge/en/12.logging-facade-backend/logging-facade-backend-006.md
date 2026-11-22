# JUL bridge: routing java.util.logging to SLF4J and a backend

**JUL bridge** is a mechanism that routes events emitted by **Java Util Logging** (`java.util.logging`, abbreviated **JUL**) into the **SLF4J facade**, so they are processed by the backend chosen by the application, such as **Logback** or **Log4j 2**. The commonly used mechanism is the `org.slf4j:jul-to-slf4j` library and the **`org.slf4j.bridge.SLF4JBridgeHandler`** class.

The idea: a legacy library still calls `java.util.logging.Logger`; the application does not need to modify that library's code, yet it can consolidate its log records into a single shared logging pipeline.

~~~text
Legacy library calls JUL                 Application code calls SLF4J
java.util.logging.Logger                 org.slf4j.Logger
          |                                     |
       JUL Logger                               |
   (level and filter)                           |
          |                                     |
          v                                     |
 JUL Handler: SLF4JBridgeHandler                |
          |                                     |
          +------------- SLF4J API <------------+
                              |
                     SLF4J provider
                              |
                  Logback / Log4j 2 / ...
                              |
                     Appender and filter
                              |
                   stdout / file / collector
~~~

**Remember the forwarding direction:** `jul-to-slf4j` is **JUL → SLF4J**, not SLF4J → JUL. The final output still depends on an actual **SLF4J provider/backend** present at runtime and that backend's configuration.

## 1. The problem the JUL bridge solves

In a large Java application, libraries may use multiple logging APIs:

| Code component | Common API | Operational issue |
| --- | --- | --- |
| A long-standing Java library | `java.util.logging.Logger` | May print via JUL ConsoleHandler with its own format and level |
| Application code | `org.slf4j.Logger` | Routed to Logback according to shared configuration |
| Another library | Log4j 2 API or Commons Logging | May use yet another logging path |
| Chosen backend | Logback or Log4j 2 | Only receives all sources that have been wired into the right path |

If JUL and SLF4J run separately, operators may encounter two timestamp/pattern styles, two log-level thresholds, two output destinations, or JUL stderr ending up outside files managed by Logback. When a JUL bridge is added in the right direction, many JUL records can be formatted and routed alongside other SLF4J logs.

Common benefits:

1. **Centralized output configuration:** appenders, patterns/encoders, file rolling, and collectors are managed in the shared backend.
2. **Easier event correlation:** a logger name and event message from a JUL library can be emitted alongside application logs.
3. **Reduced parallel configuration:** avoids maintaining separate console/file handlers for JUL and appenders for Logback.
4. **No changes to source library code:** the library keeps using JUL, while the bridge handles forwarding at runtime.

**Limitations:** the bridge does not automatically turn every record into structured JSON, does not automatically generate `requestId`/`traceId`, does not guarantee zero log loss, and does not replace protecting sensitive data at the source.

## 2. Distinguishing bridge, facade, provider, and backend

| Component | Illustrative artifact/class | Role |
| --- | --- | --- |
| **JUL source** | `java.util.logging.Logger` | Emits `LogRecord` from a library or application |
| **JUL → SLF4J bridge** | `jul-to-slf4j`, `SLF4JBridgeHandler` | Forwards JUL records into SLF4J |
| **SLF4J facade** | `slf4j-api` | Common `Logger`, `LoggerFactory` interface |
| **SLF4J 2.x provider** | Inside `logback-classic` or `log4j-slf4j2-impl` | Discovered by SLF4J to select the runtime implementation |
| **Backend** | Logback, Log4j 2, or JUL | Filters, formats, and writes records |
| **Output destination** | ConsoleAppender, FileAppender, collector | Receives processed logs |

**Do not confuse `jul-to-slf4j` with an SLF4J provider.** If only `jul-to-slf4j` and `slf4j-api` are present without a provider, JUL events may be forwarded to SLF4J and then fall into the **NOP logger**: no expected output is produced.

Conversely, having `logback-classic` without installing the bridge means Logback still receives regular SLF4J calls, but does not automatically guarantee that `java.util.logging.Logger` calls will go to Logback.

### SLF4J mechanism by version

- SLF4J **1.7.x** uses `StaticLoggerBinder`-style bindings; choose a binding artifact compatible with that version.
- SLF4J **2.x** uses `SLF4JServiceProvider` via `ServiceLoader`; it requires a provider of the matching major version.
- `jul-to-slf4j` is a **bridge on the JUL source side**, not a legacy binding or a modern provider. Even when using the bridge, the application still needs to choose the right backend for its facade version.

A system running SLF4J 2.x with only a legacy 1.7 binding may still report a missing provider; adding the JUL bridge **does not fix** that mismatch.

## 3. How does SLF4JBridgeHandler actually work?

`SLF4JBridgeHandler` is a **JUL Handler**. Once attached to the JUL system, it receives `LogRecord`s that have passed JUL-side checks and forwards the corresponding event to SLF4J.

Detailed flow:

~~~text
julLogger.info(...) / julLogger.warning(...)
                  |
                  v
            JUL Logger
     logger level + logger filter
                  |
                  v
           JUL LogRecord
                  |
      handlers attached to logger
                  |
       parent handlers if enabled
                  |
                  v
        SLF4JBridgeHandler
           (JUL Handler)
                  |
           map JUL level
                  |
                  v
       LoggerFactory / SLF4J Logger
                  |
      SLF4J provider and backend
                  |
       backend level/filter/appender
                  |
                  v
                Output
~~~

Two thresholds worth distinguishing:

- **Whether JUL accepts the event:** if `java.util.logging.Logger` drops `FINE` at an `INFO` threshold, no `LogRecord` reaches the bridge; a `DEBUG` backend cannot recover an event already dropped by JUL.
- **Whether the backend emits the bridged event:** when JUL accepts `FINE` and the bridge maps it to `DEBUG`, Logback can still drop `DEBUG` if the Logback logger's effective level is `INFO`.

The bridge does not magically disable JUL filtering. When `DEBUG` logs from a JUL library are missing, **check both the JUL level and the backend level**, rather than checking only `logback.xml`.

### JUL logger name and log context

The bridge typically uses the logger name attached to the `LogRecord` to select the corresponding logger on the SLF4J side. For example, a record with logger name `com.vendor.client.HttpTransport` can reach the logger of the same name in the backend and follow that namespace's configuration.

However, **this does not mean all JUL metadata automatically becomes structured fields** in every backend. `Throwable`/message information can be forwarded, but parameter formatting, resource bundles, caller data, and structured fields must be verified against the specific version and backend. If you need JSON or `traceId`, configure the encoder/context in the downstream pipeline.

## 4. Installing the bridge: three distinct tasks

To use `jul-to-slf4j` with Logback:

1. **Add `jul-to-slf4j` to runtime dependencies** alongside `slf4j-api` and a compatible Logback provider/backend.
2. **Install `SLF4JBridgeHandler` into JUL**, typically on the root JUL logger, early enough during startup.
3. **Manage existing JUL handlers** so the same record is not both forwarded through the bridge and written directly by an old `ConsoleHandler`/`FileHandler`.

Commonly used APIs:

~~~java
// Startup configuration snippet: not a standalone program.
import org.slf4j.bridge.SLF4JBridgeHandler;

SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
~~~

What they do:

- `removeHandlersForRootLogger()` removes **handlers currently attached directly to the root JUL logger**, helping avoid both printing via JUL's root `ConsoleHandler` and forwarding records through the bridge.
- `install()` **attaches a bridge handler instance to the root JUL logger**. To verify, use `SLF4JBridgeHandler.isInstalled()`.
- This action **mutates global logging across the same JVM**. Only perform it when the application owns JUL initialization; do not arbitrarily strip root handlers managed by an application server, framework, or other critical library.
- Install the bridge **once** at startup, not from every class or every request. Repeated installation can leave multiple bridge handlers receiving the same event, producing duplicate logs.
- Removing **root** JUL handlers does not automatically remove handlers attached to child JUL loggers. If a child logger still has a `FileHandler` or `ConsoleHandler`, records can still take two paths. Check the actual configuration.

**If a framework has already installed the JUL bridge**, do not call these methods again just to "be sure." Identify who owns the application's logging setup.

### Install early to capture early events

The bridge starts receiving JUL records emitted after it is attached. Messages emitted before `install()` **are not replayed**. Libraries may log very early in static initializers or during bootstrapping; when those records matter, integrate the bridge during the framework/container logging initialization phase.

## 5. How are log levels mapped?

JUL and SLF4J use different level names. A common mapping with `SLF4JBridgeHandler` is:

| JUL Level | Typical corresponding SLF4J level | Purpose |
| --- | --- | --- |
| `SEVERE` | ERROR | Severe error |
| `WARNING` | WARN | Warning |
| `INFO` | INFO | Informational event |
| `CONFIG` | DEBUG | Configuration detail |
| `FINE` | DEBUG | Diagnostics |
| `FINER` / `FINEST` | TRACE | Very detailed diagnostics |

`ALL` and `OFF` are normally used as **JUL filtering thresholds**, not business log levels to emit directly. If custom JUL levels exist, check the mapping rules of the bridge version in use.

Note the **two-step filtering**:

| JUL Logger level | Record | Backend Logback level | Result |
| --- | --- | --- | --- |
| INFO | FINE | DEBUG | No log: JUL drops FINE before the bridge |
| FINE | FINE | INFO | FINE is bridged to DEBUG, then dropped by the backend |
| FINE | FINE | DEBUG | Can emit DEBUG if appender/filter permits |
| INFO | WARNING | INFO | Can emit WARN if bridge path and appender are configured |
| OFF | INFO | TRACE | No log: JUL disables logging at the source |

When analyzing results, you must also account for JUL `Filter`s, parent handlers, appender filters, and output destinations. Two level columns alone do not describe every condition in a real application.

## 6. Maven + Java 17+ example: JUL and SLF4J both routed through Logback

The following example uses one Java program and three dependencies:

- **SLF4J API 2.0.17:** logging facade.
- **jul-to-slf4j 2.0.17:** JUL Handler bridge.
- **Logback 1.5.18:** SLF4J provider/backend.

This is an **illustrative version set that has been compiled and run**, not a claim about the latest versions. Production projects should manage dependencies according to compatible versions and their own update policies.

### 6.1. Project structure

~~~text
jul-bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/JulBridgeDemo.java
        └── resources/logback.xml
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jul-bridge-demo</artifactId>
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
      <groupId>org.slf4j</groupId>
      <artifactId>jul-to-slf4j</artifactId>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

If a project already pulls `slf4j-api` transitively via `logback-classic`, Maven can resolve it indirectly; this example declares it explicitly so learners see that **facade / bridge / provider** are separate responsibilities.

### 6.3. JulBridgeDemo.java

Create `src/main/java/demo/JulBridgeDemo.java`:

~~~java
package demo;

import java.util.logging.Level;
import java.util.logging.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.bridge.SLF4JBridgeHandler;

public final class JulBridgeDemo {
    private static final Logger JUL =
            Logger.getLogger("demo.legacy.PaymentClient");
    private static final org.slf4j.Logger SLF4J =
            LoggerFactory.getLogger(JulBridgeDemo.class);

    public static void main(String[] args) {
        SLF4JBridgeHandler.removeHandlersForRootLogger();
        SLF4JBridgeHandler.install();

        JUL.setLevel(Level.FINE);

        JUL.info("event=legacy_ready");
        JUL.warning("event=legacy_retry attempt=2");
        JUL.fine("event=legacy_diagnostic");
        SLF4J.info("event=modern_ready");

        System.out.println("bridgeInstalled="
                + SLF4JBridgeHandler.isInstalled());
    }
}
~~~

Key points:

- `JUL` is a `java.util.logging.Logger`; `SLF4J` is an `org.slf4j.Logger`. Both classes share the `Logger` name but belong to **different APIs**.
- `removeHandlersForRootLogger()` removes the JUL root handler in the example to prevent printing JUL records through the old path.
- `install()` attaches the bridge to the JUL root; child JUL loggers such as `demo.legacy.PaymentClient` normally propagate records up to root unless parent handlers have been disabled.
- `JUL.setLevel(Level.FINE)` allows `FINE` to pass the **JUL level check**. Without this line, default JUL configuration can drop `FINE` before it reaches the bridge.
- `SLF4J.info(...)` goes directly to the facade without passing through the JUL bridge.
- `isInstalled()` checks whether the bridge handler is attached to the JUL root.
- In a multi-class application, bridge installation logic belongs in **startup/configuration**, not inside individual business classes.

Because this is a short-lived program, it does not demonstrate cleanup. If you build an application or plugin that manages its own logger lifecycle, look into `SLF4JBridgeHandler.uninstall()`; do not uninstall a bridge that is still used by a framework or other components.

### 6.4. logback.xml

Create `src/main/resources/logback.xml`:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder><pattern>%level | %logger | %msg%n</pattern></encoder>
  </appender>

  <logger name="demo.legacy" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Here the `demo.legacy` logger namespace allows `DEBUG`, while root stays at `INFO`. Logback's `ConsoleAppender` receives both bridged JUL records and direct SLF4J records using **the exact same pattern**.

### 6.5. Compile, run, and output

From the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JulBridgeDemo
~~~

**Exact output** of the program with the files above:

~~~text
INFO | demo.legacy.PaymentClient | event=legacy_ready
WARN | demo.legacy.PaymentClient | event=legacy_retry attempt=2
DEBUG | demo.legacy.PaymentClient | event=legacy_diagnostic
INFO | demo.JulBridgeDemo | event=modern_ready
bridgeInstalled=true
~~~

Explanation of the output:

1. JUL `INFO` is mapped to SLF4J/Logback `INFO`.
2. JUL `WARNING` is mapped to `WARN`.
3. JUL `FINE` is mapped to `DEBUG`; this record is emitted because the JUL logger accepts `FINE` **and** the Logback logger `demo.legacy` allows `DEBUG`.
4. The direct SLF4J log `modern_ready` goes through the same appender, formatted identically to the JUL records.
5. The line `bridgeInstalled=true` is printed by `System.out.println` and is **not a log event going through SLF4J**.

In this example, JUL messages are fixed strings. When using JUL `{0}` placeholders or resource bundles, verify how your bridge/backend version formats parameters. **Do not assume** JUL `{0}` templates behave identically to SLF4J's `{}` syntax.

## 7. JUL bridge with Gradle

To express the same dependency selection in Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'org.slf4j:jul-to-slf4j:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.JulBridgeDemo'
}
~~~

**Important note:** `JulBridgeDemo.java` directly imports `org.slf4j.bridge.SLF4JBridgeHandler`, so **the Java example above requires `jul-to-slf4j` on the compile classpath**. If you want to copy that example as-is into Gradle, use the following instead of `runtimeOnly 'org.slf4j:jul-to-slf4j:2.0.17'` above:

~~~groovy
implementation 'org.slf4j:jul-to-slf4j:2.0.17'
~~~

This is an important dependency rule: **use `implementation` when your code directly imports the bridge**, whereas `runtimeOnly` can be appropriate if a framework/bootstrap already loads the bridge indirectly and application code does not depend on the bridge class at compile time.

When using the project's Gradle Wrapper:

~~~bash
./gradlew run
~~~

The `logback.xml` file still goes in `src/main/resources`. If a framework already provides a logging starter and bridge, do not add duplicate dependencies before inspecting the runtime dependency graph.

## 8. The most common mistake: bridge installed, but JUL FINE still missing

Suppose you configured:

~~~xml
<logger name="com.vendor" level="DEBUG"/>
~~~

in Logback. Yet a JUL library under `com.vendor` calls `julLogger.fine(...)` and nothing appears.

**The cause may lie in JUL:** the JUL logger's effective level is `INFO`. The `FINE` record is blocked **before** it ever reaches the bridge. Changing the Logback logger to `TRACE` will not help because the bridge never sees the record.

There are three ways to handle this:

1. **Configure the JUL level** with enough detail for the source namespace, for example `java.util.logging.Logger.getLogger("com.vendor").setLevel(Level.FINE)`. If child library loggers have no explicit level, they can inherit `FINE`.
2. **Use JUL `logging.properties`** or an appropriate configuration mechanism to set levels for the JUL loggers you want forwarded.
3. **With Logback**, consider `LevelChangePropagator` to synchronize appropriate Logback levels to JUL and reduce unnecessary forwarding overhead.

Avoid solving this by setting **the entire JVM** to `ALL` and letting Logback filter a massive volume of logs under high load: JUL would still construct `LogRecord`s and invoke the bridge for records ultimately discarded by the backend.

### Logback's LevelChangePropagator

Logback provides `ch.qos.logback.classic.jul.LevelChangePropagator`, a context listener that helps propagate certain Logback level changes to JUL:

~~~xml
<configuration>
  <contextListener class="ch.qos.logback.classic.jul.LevelChangePropagator">
    <resetJUL>true</resetJUL>
  </contextListener>

  <!-- Appenders, loggers, and root are declared as in a normal Logback configuration -->
</configuration>
~~~

This is an **illustrative configuration snippet**, not a standalone `logback.xml` file. When using it, understand its impact on **JUL loggers across the entire JVM** and enable it only if the application allows Logback to control JUL levels.

**`LevelChangePropagator` does not install `SLF4JBridgeHandler` automatically.** It handles **level threshold synchronization**, whereas the bridge handler handles **forwarding `LogRecord`s**. Those are two distinct roles. Initialization order, already-existing loggers, and framework-managed configuration must all be checked during integration.

## 9. Performance risks when forwarding JUL to SLF4J

The bridge introduces intermediate overhead: creating/receiving a JUL `LogRecord`, extracting required data, mapping the level, and invoking the SLF4J `Logger`.

Best case: JUL already filters out unneeded verbose events or levels are properly synchronized. Worst case: many JUL `FINEST`/`FINER` events are accepted by JUL and only then dropped by Logback `INFO`; the events are never emitted, yet the system has already paid the cost.

Things to check:

- **Hot path:** if a library generates tens of thousands of verbose records per second, the bridge can become a noticeable share of overhead.
- **Synchronized levels:** JUL and Logback should agree on detail levels based on real diagnostic needs.
- **Message parameters:** message construction and formatting can add extra cost, especially with heavy objects.
- **Stack traces:** exceptions and caller/location data can be expensive if enabled unnecessarily.
- **Backend appenders:** file I/O, async queues, network calls, and JSON encoders also contribute latency; do not blame all latency on the bridge.

Use load tests or profiling if the system has significant log volume; do not extrapolate performance from a few console lines in a small example.

## 10. Avoiding a JUL ↔ SLF4J loop

This is the most dangerous design mistake when picking dependencies by name without checking **forwarding direction**.

### Correct direction when Logback is the backend

~~~text
JUL --jul-to-slf4j--> SLF4J --Logback provider--> Logback
~~~

This is a one-way path. Logback is the final backend and does not push records back to JUL.

### Reverse direction: slf4j-jdk14

`org.slf4j:slf4j-jdk14` is a **provider that forwards SLF4J → JUL**. It is useful when an application intentionally chooses JUL as its backend, **not as a replacement JUL bridge**.

If an application simultaneously installs `jul-to-slf4j` (for JUL → SLF4J) and selects `slf4j-jdk14` as the provider (SLF4J → JUL), it can form:

~~~text
JUL --> SLF4J --> JUL --> SLF4J --> ...
~~~

This loop can cause severe logging recursion, even `StackOverflowError` or complete loss of observability. **Do not attempt to test a loop configuration on a real system.**

| Desired final backend | Provider on the SLF4J side | Should you install JUL → SLF4J? |
| --- | --- | --- |
| Logback | `logback-classic` matching SLF4J API | Yes, if you need to route JUL into Logback |
| Log4j 2 | `log4j-slf4j2-impl` for SLF4J 2.x | Yes, provided no reverse path is created |
| JUL | `slf4j-jdk14` matching SLF4J API | **Do not** install the JUL → SLF4J bridge on the same path |
| SLF4J Simple | `slf4j-simple` | Only if you need JUL through Simple and understand its limits |

A similar loop can occur if you use both **`log4j-to-slf4j`** (Log4j 2 API → SLF4J) and **`log4j-slf4j2-impl`** (SLF4J → Log4j 2) at the same time. That is not the JUL bridge, but the lesson is the same: **draw the arrows clearly before adding a bridge**.

### The bridge does not choose the provider

`jul-to-slf4j` does not select Logback on its own. If runtime accidentally loads `slf4j-simple` instead of Logback, the bridge can route JUL into `SimpleLogger`. If runtime has no provider, it can fall back to NOP. Always verify the actual runtime backend/provider.

## 11. Avoiding duplicate logs: root handlers and child-logger handlers

If the JUL root still has a `ConsoleHandler` and you only call `SLF4JBridgeHandler.install()`, a single JUL record can be:

1. Printed directly to stderr by JUL's `ConsoleHandler`.
2. Forwarded by the bridge into SLF4J and printed to console by Logback.

One event produces **two differently formatted lines**. This is not because the application called the logger twice; the pipeline itself has two handlers.

The common fix is to remove root handlers before installing the bridge:

~~~java
SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
~~~

Keep these considerations in mind:

- Handlers **attached to child loggers** can still remain active; `removeHandlersForRootLogger()` does not clean up the entire JUL tree.
- A container or framework may need its own root handler; removing it indiscriminately can drop logs managed by the framework.
- Logback can also cause duplicates when the same appender is attached to both a child logger and root with default additivity. If duplicate JUL handlers are gone yet output still repeats, check the backend next.
- Installing the bridge repeatedly at multiple startup points can attach extra bridge handlers. Ensure lifecycle is coordinated by **one owner**.

To verify, emit a JUL `WARNING` with a test ID and check that it appears the **exact expected number of times** at each destination, with no leftover records from the old JUL path if the architecture requires full consolidation.

## 12. What the JUL bridge cannot do on its own

| Misconception | Reality |
| --- | --- |
| Adding the `jul-to-slf4j` JAR immediately sends all JUL logs to Logback | You usually must **install the bridge handler** and handle existing JUL handlers |
| The bridge provides its own backend | You still need a compatible **SLF4J provider** |
| Root Logback DEBUG always makes JUL FINE appear | JUL FINE may already be blocked by the JUL level before reaching the bridge |
| JUL `{0}` and SLF4J `{}` always format identically | The two APIs have different template mechanisms; check specific bridge/backend behavior |
| Every `LogRecord` automatically becomes full structured JSON | Depends on encoder/backend, context, and metadata forwarding |
| The bridge automatically adds `traceId` | Requires an appropriate context/tracing setup |
| `System.out.println` also goes through the bridge | No: direct stdout is not a JUL `LogRecord` |
| JUL events emitted before `install()` are replayed | No: the bridge does not replay history |
| A backend warning is always a JUL bug | You must identify whether it comes from the JUL source, SLF4J provider, appender, or collector |
| The bridge guarantees durable log storage | No: durability still depends on appenders, queues, files/network, and the pipeline |

An important debugging note: **preserving the logger name** through the bridge does not mean runtime automatically knows `requestId`. If a legacy library lacks correlation IDs, correlate via external context or application-controlled code; do not generate dynamic logger names as a substitute for IDs.

## 13. Diagnosing when the JUL bridge does not work

Proceed in order instead of adding dependencies at random:

1. **Identify the source:** is the call actually `java.util.logging.Logger` or another API? Check imports and logger names.
2. **Identify the destination:** does the application want JUL → SLF4J → Logback/Log4j 2 or another route?
3. **Check runtime dependencies:** you must have `jul-to-slf4j`, `slf4j-api`, **exactly one compatible provider**, and its accompanying backend.
4. **Verify the bridge is installed:** use `SLF4JBridgeHandler.isInstalled()`; having the JAR does not mean `install()` was called.
5. **Check JUL level and filter:** does `Logger.isLoggable(Level.FINE)` allow the record you want to observe?
6. **Check parent handlers:** does the record reach the root bridge? If a child logger calls `setUseParentHandlers(false)` and has no bridge handler on that branch, the record may never enter the bridge.
7. **Check Logback/Log4j 2 level and appender:** does the backend logger accept the corresponding `INFO`/`DEBUG` level? Are any filters/thresholds blocking it?
8. **Check for duplicate logs:** root JUL handlers, child JUL handlers, repeated bridge installs, and backend additivity.
9. **Check for loops:** is `slf4j-jdk14` or a reverse bridge installed?
10. **Check actual output:** are logs going to stderr/stdout, a file, container logs, or a different collector than expected?

### Maven and Gradle commands to inspect dependencies

~~~bash
mvn dependency:tree
~~~

If the project uses the Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jul-to-slf4j --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
~~~

Pay attention to the **runtime classpath** of the deployed artifact. A dependency present on the test classpath is not guaranteed to be inside the running JAR or container.

If SLF4J 2.x warns about missing or multiple providers, fix the provider configuration first. **The JUL bridge is not a substitute for resolving SLF4J provider errors.**

### Common troubleshooting table

| Symptom | Possible cause | Suggested fix |
| --- | --- | --- |
| JUL still prints in the old format | Bridge not installed or old root JUL handler still present | Install bridge properly at startup; check handlers |
| JUL INFO prints twice | Both JUL `ConsoleHandler` and `SLF4JBridgeHandler` receive the record | Manage root/child handlers and backend appenders |
| JUL FINE is silent while SLF4J DEBUG prints | JUL logger is at `INFO` | Lower the JUL level or use `LevelChangePropagator` appropriately |
| JUL FINE reaches the bridge but does not print | Backend is at `INFO` or blocked by an appender filter | Check effective backend level and appender |
| All logs disappear after installing the bridge | SLF4J has no provider, uses NOP provider, or has the wrong backend | Verify `ILoggerFactory` and runtime dependencies |
| Log recursion or `StackOverflowError` | JUL → SLF4J and SLF4J → JUL are both active | Remove one direction of the reverse bridge/provider |
| Library's JUL logs do not enter the bridge | Child logger disables parent handlers or attaches its own handler | Inspect logger hierarchy and `LogRecord` path |
| Earliest startup logs bypass the bridge | Bridge was installed after the library emitted logs | Integrate during early bootstrap |
| Works in IDE but fails in container | Different runtime dependencies, config, or output targets | Check classpath and logs of the deployed process |
| Application slows down even though backend drops DEBUG | JUL still constructs records before backend drops them | Synchronize/tune JUL levels, reduce unnecessary logging |
| Maven has the bridge, but imports fail to compile | Bridge is only in `runtime` scope | Put the bridge on the compile classpath when code imports it directly |

## 14. When should you NOT enable the JUL bridge?

The JUL bridge is not always the right choice:

- The application only uses JUL, has no SLF4J backend, and JUL `ConsoleHandler`/`FileHandler` already meet requirements.
- A framework or application server intentionally manages JUL handlers; replacing root handlers could affect other apps or components in the same JVM.
- The application uses `slf4j-jdk14` to route SLF4J to JUL as the backend; adding the reverse direction is dangerous.
- Most verbose JUL logs do not need forwarding, and forwarding overhead is too high; separate JUL configuration or controlled level synchronization may be better.
- Source logs must remain on a separate path due to operational, security, or retention policies already designed into the system.

Determine your **intended final backend**, map out the path of each logging API, and only then choose a bridge.

## 15. Practice exercise

Suppose a library emits:

~~~java
// Illustrative snippet inside a class with a JUL logger.
julLogger.fine("event=remote_call_retry attempt=2");
julLogger.warning("event=remote_call_slow durationMs=900");
~~~

The application uses Logback as its backend, with root level `INFO`, and `com.vendor` in Logback set to `DEBUG`. The library's JUL logger inherits `INFO`.

**Questions:**

1. If the bridge's `install()` was called properly, will the `fine` event appear as `DEBUG`? Why or why not?
2. What level in SLF4J will JUL `WARNING` map to?
3. If the JUL logger is set to `FINE` but the corresponding Logback logger remains `INFO`, will the `FINE` event be printed?
4. If both the old JUL `ConsoleHandler` and the bridge handler are attached to root, what is the risk?
5. If the SLF4J provider is `slf4j-jdk14`, is adding `jul-to-slf4j` dangerous?
6. Does `LevelChangePropagator` replace `SLF4JBridgeHandler.install()`?

**Answers:**

1. **No.** JUL drops `FINE` at the `INFO` threshold before the bridge ever receives the `LogRecord`.
2. **WARN**, assuming the JUL record reaches the bridge and the backend accepts it.
3. **It will not print through the default appender at the `INFO` threshold:** the bridge converts `FINE` to `DEBUG`, but Logback filters out `DEBUG`.
4. It can **print duplicates**, once through the old JUL handler and once through the SLF4J backend.
5. **Yes**, because it creates a JUL → SLF4J → JUL path that can recurse.
6. **No.** `LevelChangePropagator` helps with levels; `SLF4JBridgeHandler` is what forwards records.

## 16. Safe integration checklist

- [ ] Draw a clear one-way path: **JUL → SLF4J → final backend**.
- [ ] Choose **one SLF4J provider** compatible with the API.
- [ ] Add `jul-to-slf4j` to the right classpath; code importing `SLF4JBridgeHandler` must compile.
- [ ] Install the bridge once, early enough; avoid conflicting with framework configuration.
- [ ] Remove root JUL handlers only when you truly own the configuration and have assessed the impact.
- [ ] Check levels/filters on **both JUL and the backend**.
- [ ] Verify `FINE`/`DEBUG`, `WARNING`/`WARN`, and an `INFO` message reach the right destination.
- [ ] Confirm there is no `slf4j-jdk14` → JUL → SLF4J loop.
- [ ] Test with a record containing a synthetic ID to detect duplicate logs.
- [ ] Evaluate overhead if JUL produces high volumes of verbose records; manage levels deliberately.
- [ ] Check log data security, exceptions, and log access permissions on the backend.
- [ ] After making changes, verify the runtime artifact/container rather than checking only build files.

**Key takeaway:** The JUL bridge solves **forwarding events from JUL into SLF4J**, not replacing the provider or backend. For logs to appear properly, you need a **JUL level permissive enough for records to pass**, an **installed bridge handler**, a **compatible SLF4J provider**, and a **backend appender that permits writing**. In particular, avoid **JUL ↔ SLF4J loops** and handle legacy JUL handlers that can cause duplicate logs.
