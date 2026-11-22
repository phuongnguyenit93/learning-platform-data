# Log4j Bridge — Connecting Facades and Backends in Java

## 1. The Problem That Log4j Bridge Solves

A Java application rarely has only a single logging API. Code written by your development team may call the **Log4j API**; third-party libraries may call the **SLF4J API**; JDK libraries or legacy modules may use **java.util.logging (JUL)**; other dependencies may call **Apache Commons Logging (JCL)** or the **Log4j 1.x** API. If each source chooses a different output mechanism, events will scatter across different consoles, files, backends, or formats, making searching, alerting, and investigation difficult.

A **logging bridge** is a component that forwards logging calls from a **source API** to a **target API**. Bridges allow an application to keep the source code of legacy libraries untouched while routing their events into a single unified processing system.

For example, when **Log4j Core** is chosen as the backend:

~~~text
App code using Log4j API -------------+
                                      |
Library using SLF4J --[SLF4J bridge]--+---> Log4j API ---> Log4j Core
                                      |                        |
Module using JUL ------[JUL bridge]---+                        +--> LoggerConfig
                                      |                        +--> Filter
Library using JCL -----[JCL bridge]---+                        +--> Appender
                                                               |
                                                               v
                                                       stdout / file / collector
~~~

**Key takeaway:** A bridge has a **direction**. Routing SLF4J into Log4j Core is one direction; routing Log4j API to SLF4J/Logback is the opposite direction. Installing both directions at once can create a loop and break logging.

After this lesson, you will be able to:

- Distinguish between a logging facade, API, backend, binding/provider, bridge, and Appender.
- Identify the direction of **log4j-slf4j2-impl**, **log4j-slf4j-impl**, **log4j-to-slf4j**, **log4j-jul**, and **log4j-to-jul** artifacts.
- Understand how to bridge JUL, JCL, JPL, and Log4j 1.x sources.
- Choose dependencies based on the final backend, not by guessing from artifact names containing "Log4j".
- Configure bridges from SLF4J 2 and JUL to Log4j Core with Maven, compile a Java 17 target program, and verify stdout.
- Analyze risks of bridge loops, conflicting providers, duplicate logs, missing logs, level mismatches, lost context, and performance impact.

**Scope:** This lesson belongs to the *Facade and Backend* section of *Java Core Logging*. The focus is on the path of logging events and API connection architecture, not on writing an Appender or a new logging framework.

## 2. Distinguishing the Layers of a Logging System

| Concept | Function | Example |
| --- | --- | --- |
| **Logging API** | Contract for Java code to emit logging requests | Log4j API, SLF4J, JUL, JCL |
| **Facade** | Stable API so calling code is not tightly coupled to a backend | SLF4J is commonly called a facade |
| **Implementation/backend** | Applies configuration, processes, and outputs events | Log4j Core, Logback, JUL |
| **Bridge/adapter** | Forwards events/calls from one API to another | SLF4J → Log4j API, JUL → Log4j API |
| **Binding/provider** | Runtime implementation selected for an API, which may be a bridge | log4j-slf4j2-impl provides an SLF4J 2 provider |
| **Appender/Handler** | Delivers events to an output destination | Log4j Console Appender, JUL FileHandler |
| **Layout/encoder** | Converts events into text/JSON/bytes | PatternLayout, JSON Template Layout |

**A bridge does not itself become a full backend with Appenders.** For example, **log4j-slf4j2-impl** is responsible for receiving calls from the SLF4J 2 API and forwarding them to the Log4j API. Meanwhile, **log4j-core** is the implementation that reads the Log4j2 configuration and writes via Appenders.

This can be viewed in two stages:

~~~text
Compile-time API                 Runtime bridge/provider       Backend
---------------------------------------------------------------------------
Log4j API ---------------------------------------------------> Log4j Core
SLF4J API ----------------------> log4j-slf4j2-impl ----------> Log4j Core
JUL API ------------------------> log4j-jul ------------------> Log4j Core
~~~

This is the model when the final destination is Log4j Core. If the final destination is replaced with Logback, the bridge must be reversed by design.

### 2.1. Why Doesn't Library Code Need to Be Modified?

Example of a compiled library using SLF4J:

~~~java
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("library.orders");
logger.info("event=order.created id={}", "ORD-42");
~~~

This is a code snippet inside a method and requires the SLF4J dependency; it has no main method so it does not run standalone. When a suitable SLF4J provider pointing to the Log4j API is present at runtime, the library still calls **org.slf4j.Logger** as before, but the event is processed by Log4j Core.

**A bridge is different from source migration.** If you replace every org.slf4j.Logger with org.apache.logging.log4j.Logger, that is migrating the API in source code. A bridge keeps the source API intact and changes the execution path behind it, which is especially useful for external dependencies.

### 2.2. Is It Better to Install as Many Bridges as Possible?

No. Only add bridges for APIs that actually appear and need to be routed to the chosen backend. Adding an unused bridge increases complexity; adding a reverse-direction bridge can create a loop.

How to decide:
1. Identify the **source API** of each module/library.
2. Choose **one target backend** for the application.
3. Draw an arrow from each API to the backend.
4. Verify that no arrow points back toward a source API.

## 3. Log4j 2 Bridge Matrix

| Source API | Target API/Backend | Artifact | Important Notes |
| --- | --- | --- | --- |
| Log4j API | Log4j Core | **log4j-api + log4j-core** | Native processing path, no bridge needed |
| SLF4J **2.x** | Log4j API | **log4j-slf4j2-impl** | SLF4J 2 provider |
| SLF4J **1.7.x** | Log4j API | **log4j-slf4j-impl** | Do not swap with the SLF4J 2 version |
| JUL | Log4j API | **log4j-jul** | Replace LogManager early or use Log4jBridgeHandler |
| JCL | Log4j API | **log4j-jcl** / compatible JCL mechanism | Check JCL version and classpath |
| Log4j 1.x API | Log4j 2 API | **log4j-1.2-api** | Compatibility bridge for migration, has limitations |
| JPL / System.Logger | Log4j API | **log4j-jpl** | Different from JUL; depends on LoggerFinder mechanism |
| Log4j API | SLF4J API | **log4j-to-slf4j** | REVERSE DIRECTION of log4j-slf4j2-impl |
| Log4j API | JUL | **log4j-to-jul** | REVERSE DIRECTION of log4j-jul |

Two particularly easy-to-confuse pairs of names:

**log4j-slf4j2-impl**: receives SLF4J 2 and routes **into Log4j API**.  
**log4j-to-slf4j**: receives Log4j API and routes **to SLF4J API**.

**log4j-jul**: routes JUL **into Log4j API**.  
**log4j-to-jul**: routes Log4j API **to JUL**.

**Do not guess direction from the JAR filename.** Check the artifact's role in the matrix and trace the actual event path before declaring dependencies.

## 4. Direction A: Multiple APIs → Log4j Core

Suppose the application chooses Log4j Core as the central backend:

~~~text
App code (Log4j API) -----------------+
                                      |
Library A (SLF4J 2) ---> provider ----+---> Log4j API ---> Log4j Core
                                      |                         |
Library B (JUL) --------> bridge -----+                         +--> Console
                                      |                         +--> RollingFile
Library C (JCL) --------> bridge -----+                         +--> Collector
~~~

In this setup:
- Code using Log4j API needs **log4j-api**.
- The application needs **log4j-core** and an appropriate LoggerConfig/Appender configuration.
- Libraries using SLF4J 2 need the **log4j-slf4j2-impl** provider.
- If JUL needs to be consolidated, use **log4j-jul** and choose an appropriate startup mechanism.
- For JCL/Log4j 1.x, install compatibility bridges only when truly needed.

The benefit is that multiple log sources can share the same **level policy**, **format**, **routing**, **retention**, and **collector** through a central backend. However, a bridge does not guarantee every record is persisted: Filters, Appenders, async queues, and storage sinks can still drop or discard events.

### 4.1. SLF4J 2 → Log4j2

Logical dependencies:

~~~text
slf4j-api 2.x              API for code/libraries calling SLF4J
log4j-slf4j2-impl          SLF4J 2 -> Log4j API provider
log4j-api                  target API
log4j-core                 backend/implementation
~~~

When code using SLF4J calls:

~~~java
org.slf4j.Logger slf4j =
        org.slf4j.LoggerFactory.getLogger("billing.service");
slf4j.info("event=payment.retry attempt={}", 2);
~~~

the event can be received by Log4j Core just like events from the Log4j API, with Logger name, level, message, and associated data transferred according to the bridge contract.

### 4.2. SLF4J 1.7 Differs from SLF4J 2.x

SLF4J 2.x uses a different provider mechanism than SLF4J 1.7.x. Therefore:

- **SLF4J 1.7.x or older:** **log4j-slf4j-impl**.
- **SLF4J 2.x:** **log4j-slf4j2-impl**.

Do not swap the two artifacts just because both contain "slf4j". If the classpath contains multiple versions of **slf4j-api**, resolve the dependency conflict; do not judge solely from the version declared directly in pom.xml while ignoring transitive dependencies.

### 4.3. Only One Compatible SLF4J Provider

Do not include both **logback-classic** and **log4j-slf4j2-impl** as a "backup". Both can provide a logging implementation/provider for SLF4J. A runtime needs a single unambiguous choice; multiple providers can cause warnings and unexpected behavior.

To inspect the dependency tree:

~~~bash
mvn dependency:tree
~~~

Run this command in a Maven project with a pom.xml. Verify which provider is selected **at runtime**, especially when a framework or starter pulls in dependencies transitively.

## 5. Direction B: Log4j API → SLF4J/Logback

If the application has chosen **Logback** as its backend, but a library uses the Log4j API, the appropriate path can be:

~~~text
Library (Log4j API)
        |
        v
    log4j-to-slf4j
        |
        v
      SLF4J API
        |
        v
     Logback backend
~~~

**log4j-to-slf4j** goes from Log4j API to SLF4J. In this setup, **do not install log4j-slf4j2-impl** to route SLF4J back into Log4j API.

Similarly, if the target backend is JUL while code uses the Log4j API, the **log4j-to-jul** module goes in the direction Log4j API → JUL. It does **not** route JUL into Log4j Core.

### 5.1. An Application Does Not Necessarily Have to Rewrite All Source Code

Bridges exist so libraries can continue using the API they chose. If the development team wants to change the Logging API in source code, it can migrate in a planned way; however, **changing the backend** and **changing the API** are two separate tasks. Changing the backend does not necessarily require editing thousands of `LOG.info` calls in business code.

## 6. No Bridge Loops Allowed

The most serious mistake:

~~~text
SLF4J API
   |
   | log4j-slf4j2-impl
   v
Log4j API
   |
   | log4j-to-slf4j
   v
SLF4J API
   |
   +--------> back to start
~~~

**Never install log4j-slf4j2-impl and log4j-to-slf4j together.** Two opposing bridges can lead to logging loops, provider conflicts, initialization failures, or broken logging. For SLF4J 1.x, likewise never combine **log4j-slf4j-impl** with **log4j-to-slf4j**.

Other architectural warnings:

- Installing an SLF4J provider targeting Log4j alongside a provider targeting Logback makes backend selection ambiguous.
- Using JUL → SLF4J → Log4j API may be valid in direction, but it is longer than JUL → Log4j API directly.
- Installing multiple JUL Handlers that each forward the same event to one backend can duplicate logs.
- Attaching the same Console Appender to both a child LoggerConfig and Root with unintended additivity can duplicate records, even when bridges are configured properly.
- An event passing through multiple conversion layers may undergo semantic changes in context or level; verify rather than assuming exact equivalence.

**Rule:** Each source API needs only one intentional path to the final backend. Any path that loops back to its source or provides two routes to the same destination must be evaluated before deployment.

## 7. JUL → Log4j2: Specifics of Java Util Logging

A library emitting logs with:

~~~java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("legacy.payment");
jul.info("event=legacy.ready");
~~~

is using **JUL**, the logging API built into the JDK. Adding **log4j-core** to the classpath **does not automatically redirect** JUL to Log4j2. The **log4j-jul** module supports two key approaches.

### 7.1. Replacing the JUL LogManager at JVM Startup

Set the JVM system property:

~~~text
java.util.logging.manager=org.apache.logging.log4j.jul.LogManager
~~~

Example flag syntax:

~~~bash
java -Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager -cp "..." Main
~~~

This command is illustrative only: the classpath and `Main` class must be replaced with the actual application; the full runnable command is in section 10.

**Set the property before JUL is initialized.** Because the JUL LogManager lives in the JVM's shared logging infrastructure, a library may call JUL during bootstrap, before `main()`. Calling **System.setProperty** too late does not guarantee replacing an already-initialized manager.

Replacing the LogManager can be more efficient than a Handler bridge because JUL logging calls are routed into the Log4j API without running through the entire standard JUL pipeline first.

**Limitation:** Log4j documentation notes that JUL **Handlers** are not supported in the same way under this LogManager replacement mechanism; applications relying on custom JUL Handlers must evaluate compatibility. Do not arbitrarily set this property in an application server where multiple applications share the JUL infrastructure.

### 7.2. Using Log4jBridgeHandler

If the environment already initializes JUL before the application can set the system property, **org.apache.logging.log4j.jul.Log4jBridgeHandler** is another option. It is a JUL Handler responsible for forwarding `LogRecord` instances to Log4j.

~~~text
JUL Logger
    |
    v
JUL Handler: Log4jBridgeHandler
    |
    v
Log4j API --> Log4j Core --> Appender
~~~

Example in a JUL **logging.properties** file:

~~~properties
handlers = org.apache.logging.log4j.jul.Log4jBridgeHandler
~~~

This is only a **configuration snippet**; ensure the Handler is loaded from log4j-jul, the Log4j Core backend is active, and JUL levels are set appropriately. Log4j also supports installing the Handler programmatically via **Log4jBridgeHandler.install()**.

**Risk:** If an old JUL `ConsoleHandler` remains active alongside the bridge Handler, a single record may be written to both destinations. Because records pass through the JUL pipeline before reaching Log4j, a Handler bridge can have higher overhead than replacing the LogManager. Log4j provides the **propagateLevels** option to reduce processing of events disabled by backend configuration, but level mapping must be tested.

### 7.3. Which Approach Should You Choose?

| Condition | Recommended Direction |
| --- | --- |
| Full control over JVM startup, want direct integration | LogManager replacement in log4j-jul |
| JUL is already initialized early, cannot replace manager | Log4jBridgeHandler |
| Need to preserve multiple custom JUL Handlers | Test the Handler bridge path and lifecycle |
| No JUL sources need consolidation | No need to install log4j-jul |
| System requires durable audit logging | Design dedicated delivery/retention, not just a bridge |

**Note:** Spring Boot or containers may already integrate bridges, so verify the actual configuration before adding more.

## 8. JCL, JPL, and Log4j 1.x

### 8.1. JCL / Apache Commons Logging

JCL uses the **org.apache.commons.logging** API. In an architecture using Log4j2 as the backend, **log4j-jcl** is an option to route JCL to the Log4j API when compatible with the Commons Logging version and classloader in use.

Some applications take the path JCL → SLF4J → Log4j2; this path can be valid if all arrows point in one direction, though you must understand there are more translation layers. Do not install multiple JCL implementations simultaneously without determining class-loading/provider order.

### 8.2. JPL / System.Logger

**System.Logger** (Java Platform Logging) is distinct from **java.util.logging.Logger**, even though both are JDK-bundled APIs. Log4j provides **log4j-jpl** to integrate `System.Logger` with the Log4j API. Check **System.LoggerFinder**, when the provider is selected, and runtime compatibility; do not assume **log4j-jul** automatically bridges all JPL calls in every environment.

### 8.3. Log4j 1.x API

Legacy code may use:

~~~java
import org.apache.log4j.Logger;
~~~

The Log4j 2 API uses a different package:

~~~java
import org.apache.logging.log4j.Logger;
~~~

**log4j-1.2-api** is a compatibility layer that allows many Log4j 1.x API calls to enter the Log4j2 system during migration. However, **this does not mean every Log4j 1.x appender, configuration, and extension will be reproduced 100%**. Consult the migration guide and run integration tests.

Do not treat the compatibility module as a reason to keep outdated legacy implementations indefinitely. Review dependencies, security policies, and a source migration roadmap when appropriate.

## 9. Version and Dependency Management

A system using Log4j Core typically needs Log4j artifacts with synchronized versions. **log4j-bom** is the standard way to manage unified versions for **log4j-api**, **log4j-core**, **log4j-slf4j2-impl**, **log4j-jul**, and other modules.

**Library responsibility:** A shared Java library should normally depend only on a logging API; the consuming application decides the implementation. Bundling Logback/Log4j Core or a provider inside a library makes other applications prone to conflicts.

**Application responsibility:** Choose the final backend, declare the required runtime providers/bridges, configure LoggerConfigs/Appenders, and test.

Use Maven to inspect the graph:

~~~bash
mvn dependency:tree
~~~

Look for both direct and transitive artifacts:
- `slf4j-api`, `logback-classic`;
- `log4j-api`, `log4j-core`;
- `log4j-slf4j2-impl`, `log4j-slf4j-impl`, `log4j-to-slf4j`;
- `log4j-jul`, `log4j-to-jul`, `jul-to-slf4j`;
- `log4j-jcl`, `jcl-over-slf4j`;
- `log4j-1.2-api` and any remaining legacy implementations.

If you find two opposing bridges or two SLF4J providers, exclude the unwanted choice. **The goal is not the classpath with the fewest JARs**, but ensuring each API has a single, clear path to the chosen backend.

## 10. Standalone Runnable Example: Java 17 + Maven, Three APIs Routing to Log4j2

This demo uses **Log4j 2.26.1**, **SLF4J 2.0.17**, and Maven compiler target **Java 17**. These versions are pinned so the example is reproducible, not as a claim that every project must use these exact versions. Before using in production, update to current versions and security advisories.

Goals:
1. Emit an event via **Log4j API**.
2. Emit an event via **SLF4J 2 API**.
3. Emit an event via **JUL**.
4. Have all three printed by Log4j Core using the **same PatternLayout**.
5. Print the JUL LogManager class name to confirm the bridge initialized in time.

### 10.1. Project Structure

~~~text
log4j-bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── bridge/
        │           └── BridgeDemo.java
        └── resources/
            └── log4j2.xml
~~~

### 10.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId><artifactId>log4j-bridge-demo</artifactId><version>1.0</version>
  <properties><maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencyManagement><dependencies><dependency>
    <groupId>org.apache.logging.log4j</groupId><artifactId>log4j-bom</artifactId>
    <version>2.26.1</version><type>pom</type><scope>import</scope>
  </dependency></dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-api</artifactId></dependency>
    <dependency><groupId>org.slf4j</groupId><artifactId>slf4j-api</artifactId><version>2.0.17</version></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-core</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-slf4j2-impl</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-jul</artifactId><scope>runtime</scope></dependency>
  </dependencies>
  <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId><version>3.14.0</version>
    <configuration><release>17</release></configuration>
  </plugin></plugins></build>
</project>
~~~

**Why split scopes like this?** Source code directly uses Log4j API and SLF4J API, so they are present at compile time. **log4j-core**, **log4j-slf4j2-impl**, and **log4j-jul** serve the runtime in this demo. The BOM ensures all Log4j modules share a consistent version.

Do not add **log4j-to-slf4j** to this pom.xml: it would create a reverse loop from Log4j API back to SLF4J.

### 10.3. src/main/resources/log4j2.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%level|%logger|%msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="demo.bridge" level="INFO" additivity="false">
      <AppenderRef ref="CONSOLE"/>
    </Logger>
    <Root level="ERROR"><AppenderRef ref="CONSOLE"/></Root>
  </Loggers>
</Configuration>
~~~

Loggers under **demo.bridge** are configured at INFO and use a Console Appender writing to stdout. **additivity=false** prevents the same event from also being forwarded to the Root Appender. Root ERROR serves as the baseline configuration for other Loggers.

**Bridges only decide the event path.** PatternLayout, level, Filter, and Appender are managed by Log4j Core.

### 10.4. src/main/java/demo/bridge/BridgeDemo.java

~~~java
package demo.bridge;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.slf4j.LoggerFactory;

public final class BridgeDemo {
    private static final Logger LOG4J = LogManager.getLogger("demo.bridge.app");
    private static final org.slf4j.Logger SLF4J =
            LoggerFactory.getLogger("demo.bridge.lib");
    private static final java.util.logging.Logger JUL =
            java.util.logging.Logger.getLogger("demo.bridge.jul");

    public static void main(String[] args) {
        LOG4J.info("source=log4j event=ready");
        SLF4J.info("source=slf4j event=order.created id={}", "ORD-42");
        JUL.info("source=jul event=legacy.ready");
        System.out.println("jul-manager="
                + java.util.logging.LogManager.getLogManager().getClass().getName());
    }
}
~~~

The program uses exactly three APIs and contains no custom bridge code. Dependencies and the JVM property control the routing. The final line confirms that the JUL LogManager is indeed the class provided by `log4j-jul`.

### 10.5. Build the Project and Run a Separate JVM

From the directory containing `pom.xml`, run:

~~~bash
mvn -q -B package dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Then **run java directly in a new JVM**, with the JUL system property set **before JUL initializes**.

On **Linux/macOS**:

~~~bash
java -Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager \
  -cp "target/classes:$(cat classpath.txt)" demo.bridge.BridgeDemo
~~~

On **Windows PowerShell**:

~~~powershell
$deps = (Get-Content .\classpath.txt -Raw).Trim()
java '-Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager' -cp "target\classes;$deps" demo.bridge.BridgeDemo
~~~

**Distinguishing classpath separators:** Unix typically uses **:**, while Windows uses **;**. In a Maven environment with many plugins, do not assume running **exec:java** inside Maven's own JVM will always be early enough to replace the JUL LogManager; the command above spawns a separate JVM and sets the property at startup.

### 10.6. Verified stdout

The program was **compiled targeting Java 17 and executed** with the dependencies/versions listed above. Below is its stdout:

~~~text
INFO|demo.bridge.app|source=log4j event=ready
INFO|demo.bridge.lib|source=slf4j event=order.created id=ORD-42
INFO|demo.bridge.jul|source=jul event=legacy.ready
jul-manager=org.apache.logging.log4j.jul.LogManager
~~~

**Line 1:** Log4j API goes directly to Log4j Core.  
**Line 2:** SLF4J 2 API goes through `log4j-slf4j2-impl`, with the `{}` placeholder replaced by `ORD-42`.  
**Line 3:** JUL is routed by `log4j-jul` into the Log4j API because the manager was replaced at JVM startup.  
**Line 4:** Confirms the JUL LogManager is `org.apache.logging.log4j.jul.LogManager`.

All log lines share the **same format**, without extra output from the default JUL `ConsoleHandler` and without duplicating through the Root Appender. Thus they demonstrate a verifiable centralized pipeline.

### 10.7. What If You Remove a Bridge?

| Change | Expected Behavior to Verify |
| --- | --- |
| Remove `log4j-slf4j2-impl` | SLF4J lacks the expected provider or picks another provider |
| Remove `log4j-jul` or the JVM property | JUL falls back to another LogManager/Handler and may print a different format |
| Remove `log4j-core` | Configured Log4j Core backend/Appenders are no longer present |
| Add `log4j-to-slf4j` | Routing-direction conflict with SLF4J → Log4j API |
| Change `LoggerConfig` level to `WARN` | Demo `INFO` events may be filtered out by Log4j Core |
| Set `additivity=true` | Events may also be forwarded to the Root Appender and duplicated |

Do not intentionally introduce a bridge loop into production to "experiment"; check the dependency graph and pick one direction upfront.

## 11. Level Mapping, Context, and Data Across Bridges

Bridges forward events, but APIs do not share an identical set of concepts.

### 11.1. Level Mapping

| Purpose | SLF4J | Log4j2 | JUL |
| --- | --- | --- | --- |
| Very detailed | TRACE | TRACE | FINEST/FINER depending on bridge |
| Diagnostic | DEBUG | DEBUG | FINE |
| Informational | INFO | INFO | INFO |
| Warning | WARN | WARN | WARNING |
| Error | ERROR | ERROR | SEVERE |

This is a reference guide, **not an absolute mapping across all versions**. Log4j2 has `FATAL`; JUL has `CONFIG` and multiple `FINE` levels. The actual adapter may have specific conversion rules.

A JUL **FINE** record can be filtered by the JUL Logger/Handler **before** reaching Log4j Core, even if the target `LoggerConfig` enables `DEBUG`. With a Handler bridge, check both the JUL level and the Log4j2 level. Avoid blindly raising everything to `ALL` before knowing where events are being dropped.

### 11.2. MDC and ThreadContext

SLF4J uses **MDC**; Log4j2 has **ThreadContext**. A compatible provider/bridge can pass context into Log4j Core, but do not assume every data type or context is preserved 100% across every bridge chain.

When you need `requestId`/`traceId`:
- Check the output after Layout/Encoder, not just whether `MDC.put` ran.
- Use `try/finally` scoping or closeable context APIs.
- Propagate context explicitly across `ExecutorService`, `CompletableFuture`, and async processing.
- Do not leak a `ThreadLocal` from one request to another when thread pools reuse threads.
- Do not write passwords, tokens, cookies, or private data into MDC/ThreadContext.

### 11.3. Marker, Throwable, and Caller Location

A logging API may support `Marker`, structured `Message`, key-value pairs, or `Throwable` differently from the target API. A bridge can map them, but it does not guarantee identical metadata preservation.

Test the following:
1. Do the `Throwable` and its root cause reach the Appender?
2. Is the stack trace formatted properly?
3. Is a `Marker` needed for filtering preserved and displayed?
4. Does caller class/method/source location still point to business code, or has it become the adapter class?
5. When running async, at what point is the event's context captured?

If downstream systems rely on structured data, use a stable schema and proper encoder; do not just parse message text and assume the bridge forwarded every field.

## 12. Operational Considerations

### 12.1. Performance

Bridges can add overhead for event translation, level/metadata mapping, and formatting. With JUL `BridgeHandler`, events pass through JUL before entering Log4j Core, incurring extra cost compared to `LogManager` replacement.

Measure performance under realistic workloads: throughput, CPU, latency, allocations, and slow-sink scenarios. Async configurations can reduce request-thread impact, but still carry risks of queue saturation, blocking/dropping, and record loss on abrupt JVM shutdown.

### 12.2. Duplicate Logs

Two common causes:
- **Two routing paths** from one source: JUL `ConsoleHandler` active alongside `BridgeHandler`, or two providers/backends configured ambiguously.
- **Additivity/Appender** in Log4j Core: a child `LoggerConfig` and `Root` both write the same event to a shared destination.

The fix is not deleting every Handler or setting `additivity=false` on every Logger. Map out the exact routes, identify the required destinations, and verify the final record count.

### 12.3. Security and Sensitive Data

Bridges do not automatically sanitize every message. If a library logs tokens, passwords, cookies, private keys, credentials, or full sensitive payloads, consolidating into a central backend can spread that data further.

Minimize data **at the source**, use proper escaping/JSON encoders, and configure access controls, retention, and redaction at the appropriate layers. Logging at `DEBUG` is not inherently safe either, since `DEBUG` may be enabled during investigations.

### 12.4. Library Logging API vs. Application Implementation

Shared Java libraries should normally depend only on a **logging API**; choosing the final backend belongs to the application. A library should not force a specific provider onto the application's runtime, as it may conflict with frameworks or other applications.

The final application must control the dependency graph, pick one backend, install bridges for APIs that actually exist, and test before deploying.

## 13. Common Troubleshooting Scenarios

| Symptom | What to Check | How to Fix |
| --- | --- | --- |
| SLF4J does not output via Log4j Core | Is the SLF4J 2 provider present? | Use the matching `log4j-slf4j2-impl` |
| Multiple SLF4J providers at runtime | Are both `logback-classic` and Log4j provider present? | Choose one provider/backend |
| Errors mentioning `log4j-to-slf4j` | Is a reverse-direction bridge also installed? | Remove the SLF4J ↔ Log4j loop |
| JUL still prints to JDK stderr | Was `java.util.logging.manager` set early enough? | Set at JVM startup or use Handler bridge |
| JUL `FINE` does not appear | Levels in both JUL and Log4j2 | Inspect both filtering layers |
| One event is printed twice | Old JUL Handler or Log4j additivity | Remove redundant routing path |
| Layouts differ across APIs | Log sources hitting two different backends | Verify provider and pipeline |
| `requestId` lost across threads | Context propagation | Propagate/snapshot context and clean up scope |
| `Marker`/`Throwable` missing in output | Adapter/Encoder/PatternLayout | Test semantics of each field |
| Sudden log volume spike after bridging | Newly consolidated sources or duplicate emission | Tune levels, routing, retention |
| File Appender fails to write | Write permissions/path/queue/backpressure | Check the sink, not just the bridge |
| Source importing Log4j 1.x fails on Log4j2 | Missing compatibility module or incompatible API | Evaluate `log4j-1.2-api` and migration |

**Investigation order:** Source API → bridge/provider → Log4j API → LoggerConfig/Filter → Appender/Layout → output. If you cannot prove which step is active, do not guess based only on a missing console line.

## 14. Safe Deployment Checklist

Before rolling out a bridge configuration to a real application, check:

- **One final backend** has been chosen and clearly configured.
- **Source APIs** have been inventoried from source code and the dependency tree.
- Every bridge points in the **right direction**, with no loops.
- SLF4J version and provider artifact are **compatible**.
- Log4j2 modules use **synchronized versions** (via BOM where appropriate).
- JUL `LogManager` replacement, if chosen, is configured **before JUL initializes**.
- JUL Handler bridge, if chosen, does not leave redundant Handlers causing duplicates.
- Log events from each API reach the same backend with the **right level, Logger name, and layout**.
- `Marker`, context, `Throwable`, and location have been tested if the application relies on them.
- Async/backpressure, write permissions, shutdown, error handling, and retention are properly planned.
- No secrets or log injection appear in the output.
- You can roll back or remove the bridge if integration fails.

**Do not guess expected log counts from an abstract configuration.** Emit test events with distinct keys/Logger names, observe the actual output, and verify whether records are dropped or duplicated.

## 15. Practice Exercises

**Exercise 1 — Choose the right bridge direction:** A library uses SLF4J 2, and the application wants Log4j Core. Which artifact do you choose?  
Hint: **log4j-slf4j2-impl**, not `log4j-to-slf4j`.

**Exercise 2 — Choose Logback as backend:** The application uses SLF4J/Logback, and a library uses the Log4j API. Draw the path and choose the artifact for the Log4j API.  
Hint: **Log4j API → log4j-to-slf4j → SLF4J → Logback**.

**Exercise 3 — JUL startup issue:** In an application server, JUL is already initialized before the application deploys. You cannot replace the manager. Is there a way to route JUL into Log4j Core?  
Hint: **Log4jBridgeHandler**, then check old Handlers and overhead.

**Exercise 4 — Check levels:** In the demo, change `LoggerConfig` `demo.bridge` to **WARN**. Predict why `INFO` records no longer appear via Log4j Core even though the source APIs still call `info()`.

**Exercise 5 — Duplicates:** Add a JUL `ConsoleHandler` alongside the JUL bridge, or set `additivity=true` in the Log4j Core example. Observe why a single event can produce multiple lines. Do not do this in production.

**Exercise 6 — Diagnose a dependency graph:** A `pom.xml` contains `log4j-slf4j2-impl`, `log4j-to-slf4j`, and `logback-classic`. The intended final backend is Log4j Core. Identify the dependencies to remove and explain why.

**Exercise 7 — Structured logging:** Attach `requestId` via MDC in a module using SLF4J, then display it using a Log4j2 Layout. Verify scoping and ensure no context leaks when the thread pool reuses threads.

**Exercise 8 — Legacy migration:** A module imports `org.apache.log4j.Logger`. Explore `log4j-1.2-api` and list legacy usages that need extra testing: custom appenders, configuration, caller location, MDC/filters.

## 16. Self-Assessment Questions

**1. What is a bridge?**  
A component that forwards calls/events from one logging API to another API so they use the chosen backend.

**2. Can `log4j-slf4j2-impl` and `log4j-to-slf4j` be installed together?**  
No. They go in opposite directions and create a dangerous routing loop.

**3. How does `log4j-jul` differ from `log4j-to-jul`?**  
**log4j-jul** is for JUL → Log4j API; **log4j-to-jul** is for Log4j API → JUL.

**4. Does SLF4J 1.7 use the same provider as SLF4J 2?**  
It should not. SLF4J 1.7 uses **log4j-slf4j-impl**; SLF4J 2 uses **log4j-slf4j2-impl**.

**5. Does installing `log4j-core` automatically collect all JUL events?**  
No. You need a JUL integration mechanism, such as `log4j-jul` and the appropriate startup property or Handler bridge.

**6. Why must JUL `LogManager` replacement happen very early?**  
Because JUL may already initialize its global manager before `main()`; late configuration is not guaranteed to take effect.

**7. Does a bridge guarantee identical JSON fields, `Throwable`s, and caller locations?**  
No. You must verify semantic translation and the actual encoder behavior.

**8. Should you add every bridge to every project to avoid losing logs?**  
No. Only add the bridges you need, map the direction correctly, and check for duplicates and loops.

**9. If all APIs are already routed to Log4j Core and logs are still missing, what should you check?**  
Logger name, `LoggerConfig`, level, `Filter`, `AppenderRef`, `additivity`, `Layout`, sink, and collector.

**10. Does a bridge replace security and audit policies?**  
No. A bridge is routing infrastructure; it does not by itself guarantee redaction, durability, retention, or access control.

## 17. Official References

- Apache Log4j — Installation: https://logging.apache.org/log4j/2.x/manual/installation.html
- Apache Log4j — Components: https://logging.apache.org/log4j/2.x/components.html
- Apache Log4j — JUL-to-Log4j bridge: https://logging.apache.org/log4j/2.x/log4j-jul.html
- Apache Log4j — Log4j-to-JUL bridge: https://logging.apache.org/log4j/2.x/log4j-to-jul.html
- Apache Log4j — Migrating from Logback: https://logging.apache.org/log4j/2.x/migrate-from-logback.html
- Apache Log4j — Migrating from SLF4J: https://logging.apache.org/log4j/2.x/migrate-from-slf4j.html

These guides apply to **Log4j 2.x**. When using other versions, frameworks, or containers, cross-check the provider mechanism, dependencies, and integration guides for that runtime.

## 18. Key Takeaways

**A bridge only forwards log sources from one API to another in a single direction**; the backend decides level, Filter, Appender, and output. When **Log4j Core** is chosen as the target: Log4j API goes directly, SLF4J 2 typically goes through **log4j-slf4j2-impl**, JUL goes through **log4j-jul**, and legacy APIs use appropriate adapters if actually present in the application.

A proper routing path must have **no loops, no duplicates, and be verifiable with sample log events from each API**. In the Java 17+ example we ran, Log4j API, SLF4J, and JUL all output in one format through Log4j Core, while the JUL `LogManager` was confirmed to be the `log4j-jul` implementation. This is the practical standard for evaluating a bridge configuration, rather than relying only on the list of installed JARs.
