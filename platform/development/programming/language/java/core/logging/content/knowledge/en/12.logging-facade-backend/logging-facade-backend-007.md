# JCL Bridge in Java Logging: From Apache Commons Logging to SLF4J and Log4j 2

A **JCL bridge** is a mechanism that routes logging calls written against **Apache Commons Logging (JCL)** to a logging API or backend chosen by the application, typically SLF4J/Logback or Log4j 2. It allows legacy Java libraries to continue using `org.apache.commons.logging.Log` while the entire application follows a unified logging policy.

This topic belongs to **Facade and backend**. To use a JCL bridge correctly, you need to answer four questions: **which API does the source code call, which classes actually provide JCL, in which direction does the bridge forward events, and which backend writes the final output?** Getting any single step wrong can lead to missing logs, duplicate logs, classloader errors, or forwarding loops.

## 1. What is Apache Commons Logging (JCL)?

JCL is a long-standing logging abstraction from Apache. It provides the `Log` interface and the `LogFactory` factory in the `org.apache.commons.logging` package. Instead of depending directly on Logback or Log4j Core, a library calls a relatively stable API:

```java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

public final class LegacyOrderClient {
    private static final Log LOG =
            LogFactory.getLog(LegacyOrderClient.class);

    public void submit(String orderId) {
        LOG.info("event=order_submit orderId=" + orderId);
    }
}
```

This is **an illustrative class** without a `main` method, and it requires a library providing the JCL API to compile. `LogFactory.getLog(LegacyOrderClient.class)` retrieves a logger whose category corresponds to the class. Familiar JCL methods include `trace`, `debug`, `info`, `warn`, `error`, `fatal`, and their overloads accepting a `Throwable`.

**Difference from SLF4J:** JCL's `Log.info(Object)` does not natively provide `{}` parameterized overloads like SLF4J does. If source code is already written against JCL, adding an SLF4J backend does not change the syntax of those JCL calls. A bridge solves **the event routing path**, not the API that the source code compiles against.

JCL originally used factory/discovery mechanisms and classloaders to select an implementation. This allowed frameworks or host applications to plug in a different logging implementation, though it sometimes made troubleshooting difficult when multiple JARs provided `org.apache.commons.logging` classes or when different classloaders loaded them differently.

## 2. How do API, bridge, and backend differ?

```text
Library code
  |
  | org.apache.commons.logging.Log.info(...)
  v
JCL API / implementation selected by classloader
  |
  | one-way bridge
  v
SLF4J API or Log4j 2 API
  |
  | provider / implementation
  v
Logback, Log4j Core, JUL...
  |
  | level/filter -> formatter/encoder -> appender/handler
  v
Console / file / collector
```

| Concept | Examples | Responsibility |
| --- | --- | --- |
| **Facade/API** | JCL, SLF4J, Log4j 2 API | Provides methods for source code to emit logs |
| **JCL bridge/adapter** | `jcl-over-slf4j`, `log4j-jcl` | Forwards JCL calls to the target API |
| **SLF4J provider** | `logback-classic`, `slf4j-simple`, `log4j-slf4j2-impl` | Implements the SLF4J API at runtime |
| **Logging backend** | Logback, Log4j Core, JUL | Manages levels, layouts, context, and log routing |
| **Output destination** | ConsoleAppender, RollingFileAppender, ConsoleHandler | Writes events to console/file/collector |

**A bridge is not an appender.** Adding `jcl-over-slf4j` does not automatically create log files; to get logs, you still need a properly selected provider/backend, an enabled log level, an active appender/handler, and a collection system reading from the right destination.

A large application may have multiple **source APIs**, but it should have a single **primary target backend** or an intentional routing design, rather than letting random adapters form a cycle.

## 3. Table of JCL bridges and forwarding directions

| Artifact / mechanism | Direction and meaning | When to evaluate? |
| --- | --- | --- |
| `org.slf4j:jcl-over-slf4j` | **JCL API → SLF4J API** | A library still uses JCL, but the application already uses SLF4J |
| `org.apache.logging.log4j:log4j-jcl` | **JCL → Log4j 2 API** | Some applications use Commons Logging 1.2 or older and want Log4j 2 Core |
| `org.springframework:spring-jcl` | Spring's JCL implementation; selects **Log4j 2 API, SLF4J, or JUL** based on the classpath | Spring Framework / Spring Boot infrastructure |
| `commons-logging:commons-logging` 1.3.x+ | Official JCL with built-in adapters, **including Log4j API** | An additional Log4j bridge is not always needed |
| `org.slf4j:slf4j-jcl` | **SLF4J → JCL** (reverse direction), geared toward legacy integration | When the environment mandates JCL; requires checking version/binding |

**Do not install all artifacts in the table.** `commons-logging`, `jcl-over-slf4j`, and `spring-jcl` can provide classes in the same `org.apache.commons.logging` package. Having multiple implementations with the same class names makes the outcome classloader-dependent and can cause warnings or confusing behavior. Choose **one JCL implementation intentionally**.

One important change to know: **starting from Apache Commons Logging 1.3.0**, official JCL supports the Log4j API in its built-in adapters. Therefore, with JCL **1.3+**, check the actual discovery/backend behavior before adding `log4j-jcl`. With **JCL 1.2 and older**, `log4j-jcl` is the bridge documented by Log4j for routing logs to Log4j 2.

## 4. Common scenario: JCL → SLF4J → Logback

Suppose a legacy library uses JCL, while the new application chooses SLF4J as its facade and Logback as its backend:

```text
Legacy library
    |
    | org.apache.commons.logging.LogFactory.getLog(...)
    v
jcl-over-slf4j
    |
    v
SLF4J API
    |
    | Logback as provider
    v
Logback
    |
    +-- ConsoleAppender
    +-- RollingFileAppender
```

`jcl-over-slf4j` is designed as a **drop-in replacement compatible with JCL's public API**. Legacy code can still import `org.apache.commons.logging.Log` and `LogFactory`, while the implementation forwards events to SLF4J.

Typically you need:

1. `jcl-over-slf4j` to intercept JCL calls.
2. `slf4j-api` for the target API.
3. **An appropriate SLF4J provider**, such as `logback-classic`.
4. Backend configuration for levels, formatter/layout, and appenders.

If a legacy library's dependencies pull `commons-logging:commons-logging` into the runtime classpath, check whether you need to **exclude that JAR** to avoid two implementations both providing `LogFactory`. Do not exclude dependencies blindly: in a Spring project, `spring-jcl` may be the JCL implementation chosen by the framework.

If only `jcl-over-slf4j` and `slf4j-api` are present **without a matching provider**, the application may emit an SLF4J warning and fall back to a no-op (NOP) logger. In that case, the API works at the method-call level, but events never reach any destination. Do not confuse this situation with a Java error where `LogFactory` cannot be found.

## 5. Standalone runnable example: Java 17 + Maven + jcl-over-slf4j

This example demonstrates **two different facades routing to the same provider**. The project uses JDK 17, Maven, SLF4J's JCL bridge, and `slf4j-simple` 2.x for easy observation. This is a learning choice; production applications can use Logback or another organization-approved provider.

Structure:

```text
jcl-bridge-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/JclBridgeDemo.java
    └── resources/simplelogger.properties
```

### 5.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jcl-bridge-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <slf4j.version>2.0.17</slf4j.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>${slf4j.version}</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>jcl-over-slf4j</artifactId>
            <version>${slf4j.version}</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>${slf4j.version}</version>
            <scope>runtime</scope>
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
                    <mainClass>com.example.logging.JclBridgeDemo</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Note:** The actual XML must have `<version>${slf4j.version}</version>` — without a backslash before the `$` character. All three SLF4J modules are pinned to the same version to minimize conflicts. This is a **specific example version**, not a claim of being the latest release.

### 5.2. `JclBridgeDemo.java`

```java
package com.example.logging;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class JclBridgeDemo {
    private static final Log JCL =
            LogFactory.getLog(JclBridgeDemo.class);

    private static final Logger SLF4J =
            LoggerFactory.getLogger(JclBridgeDemo.class);

    private JclBridgeDemo() {
    }

    public static void main(String[] args) {
        System.out.println("loggerName=" + SLF4J.getName());

        JCL.info("event=jcl_accepted requestId=req-17");
        SLF4J.warn("event=slf4j_retry attempt={}", 2);

        System.out.println("finished=true");
    }
}
```

**Explanation:** `JCL` has type `org.apache.commons.logging.Log`, while `SLF4J` is `org.slf4j.Logger`. Both retrieve a logger for the same class, with category name `com.example.logging.JclBridgeDemo`. The code does not call two APIs for **the same event**; it creates two separate events to prove that both reach a single provider.

### 5.3. `simplelogger.properties`

Create `src/main/resources/simplelogger.properties`:

```properties
org.slf4j.simpleLogger.defaultLogLevel=info
org.slf4j.simpleLogger.showDateTime=false
org.slf4j.simpleLogger.showThreadName=false
org.slf4j.simpleLogger.showLogName=true
org.slf4j.simpleLogger.showShortLogName=false
org.slf4j.simpleLogger.logFile=System.err
```

These keys are specific to the `slf4j-simple` provider. If you swap the backend for Logback or Log4j Core, you must replace the target configuration accordingly; the bridge itself does not use this backend configuration file.

### 5.4. Compile and run

Inside the `jcl-bridge-demo/` directory:

```bash
mvn -q compile exec:java
```

**Stdout printed directly by the application code** in exact order:

```text
loggerName=com.example.logging.JclBridgeDemo
finished=true
```

**Two application log lines emitted by SimpleLogger to stderr** according to the configured pattern:

```text
INFO com.example.logging.JclBridgeDemo - event=jcl_accepted requestId=req-17
WARN com.example.logging.JclBridgeDemo - event=slf4j_retry attempt=2
```

Maven/plugins may emit additional build output in other environments. The terminal may display stdout and stderr together, but **interleaving order between the two streams is not guaranteed**. What needs to be verified is that both the JCL message and the SLF4J message are written through **the same provider and the same format**.

To see the role of the bridge, if you remove `jcl-over-slf4j` without any other JCL API present, the Java source will no longer compile due to missing `org.apache.commons.logging`. If you remove only `slf4j-simple` with no other provider present, SLF4J may warn about a missing provider; in that case, the log calls may not appear on stderr as expected.

## 6. Scenario: JCL → Log4j 2 Core

If the final destination is Log4j Core rather than Logback, pay attention to the JCL version and implementation.

### Commons Logging 1.2 or older

Apache Log4j provides the `log4j-jcl` bridge:

```text
commons-logging 1.2 (JCL)
            |
            | log4j-jcl
            v
       Log4j 2 API
            |
            v
       Log4j 2 Core
            |
            v
      Appender
```

A Maven dependency snippet for an application using the Log4j BOM:

```xml
<dependency>
    <groupId>org.apache.logging.log4j</groupId>
    <artifactId>log4j-jcl</artifactId>
    <scope>runtime</scope>
</dependency>
```

This is only a **dependency fragment**, not a complete POM. You still need an appropriate JCL, Log4j API/Core, and appender configuration. If the artifact has no explicit version, the POM must manage its version through a compatible BOM or parent.

### Commons Logging 1.3+

Apache Commons Logging **1.3.0 and later** directly supports the Log4j API in its adapters. A project with a newer JCL version may not need a separate `log4j-jcl`. Determine which implementation the JCL factory is selecting and test the actual output.

**Do not misunderstand:** JCL supporting the Log4j API does not mean the application automatically has Log4j Core/config. The final backend must still exist to process events, and JCL implementation selection is affected by the classpath/classloader.

If the application already uses SLF4J and Logback as its primary backend, you should not add Log4j Core just because one library uses JCL. Routing **JCL → SLF4J → Logback** is usually cleaner in that situation.

## 7. `spring-jcl`: Spring already provides a compatible JCL API

Spring Framework includes the **`spring-jcl`** module for logging within the framework and related extensions. The module provides the API in the `org.apache.commons.logging` package and has a mechanism to select the logging API present on the classpath: Log4j 2, SLF4J, or fallback JUL, depending on the Spring version and environment.

```text
Spring Framework
      |
      | org.apache.commons.logging.Log
      v
  spring-jcl
      |
      +--> Log4j 2 API --> Log4j Core
      |
      +--> SLF4J API --> Logback/other provider
      |
      +--> JUL if no compatible API is selected
```

The branches above are **alternatives**, not three simultaneous outputs for each event. In a standard Spring Boot setup, the logging starter already prepares the backend/provider for the application. Therefore:

- **Do not automatically add `jcl-over-slf4j` just because Spring code uses Commons Logging.**
- If you see both `spring-jcl` and `commons-logging`, check classpath warnings and decide which one should provide JCL.
- For new application code, Spring recommends using SLF4J, Log4j API, or JUL directly by convention; it does not force you to choose JCL.
- If you genuinely replace `spring-jcl` with another implementation, do so intentionally, and inspect the dependency tree and application logs after the change.

**Example of the wrong approach:** adding `commons-logging`, `spring-jcl`, and `jcl-over-slf4j` at the same time to "cover every framework". These artifacts can provide overlapping classes in the same package, leading to warnings or a different provider being used than the author intended. Keep **one valid JCL source** in the corresponding classloader.

## 8. Do not confuse `jcl-over-slf4j` with `slf4j-jcl`

The two names look very similar, but they go in **opposite directions**:

```text
jcl-over-slf4j:
    JCL API ----------> SLF4J API ----------> backend

slf4j-jcl:
    SLF4J API --------> JCL API ------------> implementation
```

`slf4j-jcl` appears in legacy integration scenarios where the environment requires JCL as the central logging hub. For SLF4J 2.x projects, you must re-verify **version-compatible provider/binding** support; do not assume a binding built for SLF4J 1.7 works with 2.x.

**Never combine both directions in the same runtime:**

```text
JCL --> jcl-over-slf4j --> SLF4J
 ^                            |
 |                            v
 +---------- slf4j-jcl --------+
```

When calls loop continuously, the application can hit a **`StackOverflowError`** or fail to initialize logging properly. The SLF4J documentation explicitly warns against this case. The fix is to **remove the reverse-direction bridge**, not to add appenders, raise log levels, or catch the loop exception.

The same principle applies to other bridge pairs such as SLF4J ↔ Log4j 2 or JUL ↔ SLF4J: avoid creating cycles in the logging graph.

## 9. Using Maven to inspect dependency conflicts

In real-world projects, JCL bridge issues are usually **runtime classpath issues**, not a bug in a single `LogFactory.getLog` line. You can inspect them with:

```bash
mvn dependency:tree
```

Look for the following artifacts in the output:

```text
commons-logging:commons-logging
org.springframework:spring-jcl
org.slf4j:jcl-over-slf4j
org.slf4j:slf4j-jcl
org.slf4j:slf4j-api
org.slf4j:slf4j-simple
ch.qos.logback:logback-classic
org.apache.logging.log4j:log4j-jcl
org.apache.logging.log4j:log4j-core
org.apache.logging.log4j:log4j-slf4j2-impl
org.apache.logging.log4j:log4j-to-slf4j
```

This is a **checklist, not a list of things that must all be installed**. Check both direct and transitive dependencies (from HTTP clients, Spring starters, legacy libraries). For code running inside an application server or a custom classloader, Maven's dependency tree may not fully reflect the actual runtime classpath.

If a dependency pulls in an unwanted legacy `commons-logging` into a project using `jcl-over-slf4j`, you can exclude it via Maven exclusions on the dependency that brought it in:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>some-legacy-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

This is an **illustrative fragment**; `com.example:some-legacy-library:1.0.0` is not a verified existing dependency. Verify the classpath after excluding and test thoroughly, as some libraries/frameworks have specific requirements regarding JCL.

### Identifying where the `LogFactory` class is loaded from

To investigate the JCL class source at runtime (for classes already present in the program), you can print the code protection source:

```java
// Fragment inside a program that already has a JCL dependency.
var source = org.apache.commons.logging.LogFactory.class
        .getProtectionDomain()
        .getCodeSource();
System.out.println("jclLocation="
        + (source == null ? "unavailable" : source.getLocation()));
```

The snippet above is not a standalone program. `getCodeSource()` may return `null` in some environments; printing JAR paths for internal investigation should not be enabled by default in production logs because it can expose deployment structure.

## 10. Common errors and troubleshooting

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Cannot compile `org.apache.commons.logging.Log` | Missing JCL API on the compile classpath | Add a **single** JCL API/implementation matching your architecture |
| JCL runs, but no logs appear | Wrong bridge, missing SLF4J provider, or disabled by level/filter | Trace from JCL factory to backend and appender |
| SLF4J warns about missing provider | `jcl-over-slf4j` forwards logs to SLF4J, but runtime has no valid provider | Add a provider compatible with the SLF4J version in use |
| SLF4J warns about multiple providers | Logback, SimpleLogger, and other providers are competing | Keep only the provider for the chosen backend |
| `StackOverflowError` as soon as logging occurs | JCL → SLF4J → JCL bridges form a cycle | Remove one bridge direction |
| Spring warns about Commons Logging discovery | `spring-jcl` coexists with `commons-logging` | Inspect the dependency tree and actual class source |
| JCL logs go to JUL instead of Logback | JCL/`spring-jcl` picked another path from the classpath | Check the JCL implementation and backend provider |
| The same event appears twice | Duplicate additivity/appenders or code logging twice | Audit the event emission path and logger hierarchy config |
| `DEBUG` logs are missing | Logger or backend is set to `INFO` | Check effective log levels and filters/appenders |
| Missing stack traces | `Throwable` not passed, or formatter does not render exceptions | Call the overload accepting `Throwable` and check the layout |
| Logs missing request ID | Bridges do not create MDC or propagate context across threads | Configure MDC and context propagation explicitly |
| Log file is not written | Wrong backend selected, appender not attached, or write permission error | Check backend/appender, filesystem, and collector |

When diagnosing an event that does not appear, trace end-to-end:

```text
Is JCL LogFactory loaded?
  |
  +--> Which JCL implementation is being used?
         |
         +--> Forwarding to SLF4J, Log4j, or JUL?
                |
                +--> Is the right backend/provider running?
                       |
                       +--> Do levels and filters let it through?
                              |
                              +--> Is the appender/handler writing to the right destination?
                                     |
                                     +--> Can the collector read it?
```

Do not assume the problem is a missing bridge just because `LogFactory.getLog` succeeds without producing output. The logger may be emitting events while a backend filter or output destination is failing.

## 11. Exceptions, levels, request context, and performance across a bridge

### Exceptions

JCL typically provides the `error(Object, Throwable)` overload, which passes exceptions into the pipeline:

```java
// Fragment: org.apache.commons.logging.Log LOG
// and Throwable cause are already available in the catch block.
LOG.error("event=payment_failed requestId=req-17", cause);
```

A proper bridge forwards the `Throwable` to the target API/backend; how stack traces, `Caused by`, and frames are rendered depends on the encoder/layout. Do not log only `cause.getMessage()` if you need to investigate the error path.

### Levels

JCL has `FATAL`, whereas SLF4J has no direct equivalent level (primarily `TRACE` through `ERROR`). Bridges therefore map non-equivalent levels according to implementation-specific rules. When searching for a record, check the level at both **the source logger API and the target backend**, rather than expecting every level name to be preserved verbatim.

### Messages

JCL accepts `Object` as a message; SLF4J supports `{}` placeholders via SLF4J overloads. Do not write `LOG.info("id={}", id)` on an `org.apache.commons.logging.Log` variable as if it were SLF4J: that does not match the standard JCL API.

For expensive computations used only for logging, you can check `LOG.isDebugEnabled()` before building a long message. Avoid heavy computation or calling methods with side effects solely to construct debug data.

### Request ID and security

A bridge does not automatically generate `requestId`, `traceId`, MDC/ThreadContext, or propagate context across executors/async boundaries. If you need those fields, configure observability and propagation explicitly. Never put tokens, passwords, session cookies, or unnecessary personal data into logs; if user-supplied data contains CR/LF characters, escape it or use an appropriate structured encoder.

### Overhead

A bridge adds a translation layer, though formatting, I/O, queues, and event volume are usually larger factors. Avoid unnecessary adapter chains, competing backend configurations, and logging huge payloads. For production, verify log-drop behavior when queues fill up and backend shutdown lifecycles.

## 12. Checklist for choosing a JCL bridge for your project

1. **Identify the source API**: is any code or library importing `org.apache.commons.logging.Log`?
2. **Identify the JCL implementation**: is `commons-logging`, `spring-jcl`, or `jcl-over-slf4j` actually being loaded?
3. **Choose the target backend**: Logback, Log4j Core, or JUL; which destination is responsible for storing events?
4. **Draw a one-way path**: JCL → SLF4J → Logback or JCL → Log4j API → Core; no backward arrows.
5. **Check versions**: Commons Logging 1.3+ differs from 1.2; SLF4J 2.x uses the new provider mechanism—do not assume 1.7 bindings still apply.
6. **Eliminate duplicate classes**: avoid having `spring-jcl`, `commons-logging`, and `jcl-over-slf4j` supply classes uncontrollably at the same time.
7. **Verify the provider/backend**: having a bridge does not mean a console/file appender is properly configured.
8. **Test both APIs**: emit one JCL event and one primary facade event; verify one expected record/event at the destination with no duplicates.
9. **Verify exceptions and levels**: are throwables and `DEBUG`, `INFO`, `WARN`, `ERROR` levels handled properly?
10. **Keep operations secure**: no leaked secrets, correlation IDs present, proper retention, sufficient permissions, and collector-compatible formatting.

**Remember:** `jcl-over-slf4j` routes **JCL → SLF4J**; `log4j-jcl` supports **JCL → Log4j 2** scenarios; `spring-jcl` is the implementation suited for the Spring ecosystem; `slf4j-jcl` goes the other way, **SLF4J → JCL**. A stable logging setup requires **a clear API, one intentional JCL implementation, a properly directed bridge, and a configured/verified final backend**.

## Official Documentation

- Apache Commons Logging User Guide: https://commons.apache.org/proper/commons-logging/guide.html
- SLF4J Bridging legacy APIs: https://www.slf4j.org/legacy.html
- SLF4J diagnostic messages: https://www.slf4j.org/codes.html
- Apache Log4j 2 installation & bridge: https://logging.apache.org/log4j/2.x/manual/installation.html
- Spring Framework logging & spring-jcl: https://docs.spring.io/spring-framework/reference/core/spring-jcl.html
