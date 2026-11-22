# Checking Logging Dependencies in Java: Facade, Backend, Provider, and Bridge

## 1. Why Check Logging Dependencies?

A Java application may compile successfully, yet at runtime produce **no logs**, write in the wrong format, emit warnings about logger providers, or produce duplicate log entries. A common root cause is **a classpath containing incompatible logging libraries or an incorrect forwarding route**.

For example, business code might contain:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger LOG =
        LoggerFactory.getLogger(PaymentService.class);
```

The snippet above is **an illustration inside the `PaymentService` class**, not a standalone program. It uses the **SLF4J API**; looking at the imports alone cannot tell you whether the runtime is writing via Logback or Log4j 2. The application also needs a **provider/backend** that is properly loaded and has an appropriate configuration.

When checking logging dependencies, the goal is not merely to see a logger library in `pom.xml` or `build.gradle`. You must verify **the entire path**:

```text
Application or library code
          |
          v
Logging API / Facade
  (SLF4J, Log4j 2 API, JUL, Commons Logging...)
          |
          v
Provider / bridge / adapter
          |
          v
Actual backend processing events
  (Logback, Log4j 2 Core, JUL, ...)
          |
          v
Level / filter / appender / formatter
          |
          v
Console, file, collector
```

A build that has the right dependencies *at compile time* but lacks a provider *at runtime* may still emit no logs. Conversely, an application with multiple providers may pick a different backend than intended, causing your configuration to be ignored.

**Desired outcome:** know with certainty which API is used, which provider is active, which backend processes logs, whether any bridges connect other APIs, whether there are any forwarding loops, and whether the runtime configuration is actually loaded.

## 2. Terminology to Distinguish Before Checking

| Term | Responsibility | Examples |
| --- | --- | --- |
| **Logging API** | Set of interfaces/methods for code to emit log calls | `org.slf4j.Logger`, `org.apache.logging.log4j.Logger`, `java.util.logging.Logger` |
| **Facade** | Intermediate API layer decoupling logging calls from a specific backend | SLF4J |
| **Provider/binding** | Component connecting a facade API to the actual processing system | Logback's SLF4J 2 provider; `log4j-slf4j2-impl` |
| **Backend/implementation** | Handles event processing, filtering, appenders, and output destinations | Logback Classic, Log4j 2 Core, JUL |
| **Bridge/adapter** | Routes calls from API A to API B | `jcl-over-slf4j`, `jul-to-slf4j`, `log4j-to-slf4j` |
| **Appender/handler** | Sends events to console, file, network, etc. | `ConsoleAppender`, `FileAppender`, `ConsoleHandler` |
| **Formatter/layout/encoder** | Converts event data into text/JSON/bytes | `PatternLayout`, `PatternLayoutEncoder` |
| **Logging configuration** | Declares log levels, formatters, and destinations | `logback.xml`, `log4j2.xml`, `logging.properties` |

Example structure for **SLF4J → Logback**:

```text
Application
  import org.slf4j.Logger
        |
        v
slf4j-api (facade)
        |
        v
Logback provider (in logback-classic)
        |
        v
logback-classic + logback-core
        |
        v
logback.xml -> ConsoleAppender/FileAppender
```

Example structure for **SLF4J → Log4j 2**:

```text
Application
  import org.slf4j.Logger
        |
        v
slf4j-api
        |
        v
log4j-slf4j2-impl
        |
        v
log4j-api + log4j-core
        |
        v
log4j2.xml -> Appenders
```

And an application **using the Log4j 2 API directly**:

```text
Application -> log4j-api -> log4j-core -> log4j2.xml
```

The last case does not require SLF4J. Adding `log4j-slf4j2-impl` is only necessary when some code or library calls SLF4J and you want those calls routed to Log4j 2.

## 3. Direct Dependencies and Transitive Dependencies

A **direct** dependency is a library you declare in your project. A **transitive** dependency is pulled in by another library through its own dependency relationships.

For example, a `pom.xml` declares:

```xml
<dependency>
    <groupId>ch.qos.logback</groupId>
    <artifactId>logback-classic</artifactId>
    <version>1.5.16</version>
</dependency>
```

When Maven resolves dependencies, `logback-classic` typically pulls in required components such as `logback-core` and a compatible `slf4j-api` version. Another library in the application might simultaneously bring in `slf4j-api`, `log4j-to-slf4j`, `log4j-core`, or another provider. **Do not just read the `<dependency>` lines you wrote yourself and assume you know the entire runtime.**

Distinguish three spaces:

1. **Compile classpath:** requires the APIs/classes for `javac` to compile.
2. **Runtime classpath:** the JARs actually present when the JVM starts and loads providers.
3. **Test classpath:** often contains additional test loggers/providers or configuration files; it may differ from production.

A test that passes while the packaged `jar` or container produces no logs can happen because the runtime lacks the same dependencies, a provider was stripped during packaging, or the configuration/test resources differ.

### "Having the API" Is Not the Same as "Having a Backend"

`slf4j-api` only provides the API and the provider-wiring mechanism, not a logging backend. With SLF4J 2.x, when no suitable provider is found, SLF4J typically logs a warning and falls back to a NOP/no-operation logger: logging calls may be silently discarded. The application can still keep running, making this bug hard to notice if you only test business functionality.

On the other hand, detecting two SLF4J providers at the same time does not mean logs are written through both. The runtime usually picks one provider and warns about multiple providers, but **you should never rely on selection order**. The operational goal is a single, intentional, verified backend route.

## 4. SLF4J Versions: 1.7 Binding Mechanism vs. 2.x Provider Mechanism

This is a very common compatibility issue during framework upgrades:

| API Version | Implementation Mechanism | Signs / Notes |
| --- | --- | --- |
| SLF4J 1.7.x | **Binding** via `StaticLoggerBinder` | Typically looks for `org.slf4j.impl.StaticLoggerBinder`. |
| SLF4J 2.x | **Service provider** based on `SLF4JServiceProvider` | Typically discovers providers via Java's ServiceLoader mechanism. |
| Logback 1.2.x | Typically paired with SLF4J 1.7.x | Not a provider for SLF4J 2.x by default. |
| Logback 1.3/1.4/1.5 (compatible branches) | Uses the SLF4J 2.x mechanism | Choose the version matching your project's Java and framework versions. |
| `log4j-slf4j-impl` | Built for SLF4J 1.7 | Does not replace `log4j-slf4j2-impl` when running SLF4J 2.x. |
| `log4j-slf4j2-impl` | SLF4J 2.x provider/adapter to Log4j 2 | Use with a matching Log4j 2 version. |

Simply seeing "logback" in the name is not enough. For example, a project that upgrades `slf4j-api` to 2.x while keeping a binding built for API 1.7 may cause that binding to be **ignored**. You will commonly see warnings such as "no SLF4J providers were found" or that a binding targeting API 1.7 is being ignored.

Conversely, using an SLF4J 2.x provider in an application still on `slf4j-api` 1.7 cannot be expected to work either.

**Rule:** check **API version + provider/binding mechanism + backend version + JDK requirement** together. A version matrix is only meaningful when verified against actual resolved dependencies—do not guess from JAR filenames alone.

For the Java 17 example later in this guide, we use **Logback Classic 1.5.16** as the SLF4J 2.x provider/backend. This is **a fixed example version set**, not a claim that it is the latest version or the version you must use in production. In real deployments, always check current security advisories and framework/JDK compatibility.

## 5. Maven: Commands to Inspect Logging Dependencies

### 5.1. Viewing the Full Dependency Tree

From the directory containing `pom.xml`:

```bash
mvn dependency:tree
```

Read the path **from the project down to each logging dependency**, not just a flat list of names:

```text
my-service
+- framework-starter
|  +- logging-module
|     +- logback-classic
|     \- slf4j-api
\- some-library
   \- log4j-api
```

The tree above is **a structural illustration**, not actual output from a specific project.

Pay attention to:

- How many backends/providers are present (Logback, Log4j 2 Core/SLF4J provider, JUL provider...)?
- Which `slf4j-api` version was selected after conflict resolution?
- Which library brings in unwanted transitive dependencies?
- Are both an A → B bridge and a B → A bridge present at the same time?
- Are runtime dependencies preserved when packaging the application?

### 5.2. Filtering Notable Libraries

For example:

```bash
mvn dependency:tree -Dincludes=org.slf4j:slf4j-api
mvn dependency:tree -Dincludes=ch.qos.logback:logback-classic
mvn dependency:tree -Dincludes=org.apache.logging.log4j:log4j-core
```

`-Dincludes` limits the displayed portion of the tree, which is useful when a project has hundreds of dependencies. Depending on your Maven version or shell, you may need to wrap the filter string in double quotes.

To inspect backends and adapters more broadly, you can filter by group:

```bash
mvn dependency:tree -Dincludes=org.slf4j
mvn dependency:tree -Dincludes=ch.qos.logback
mvn dependency:tree -Dincludes=org.apache.logging.log4j
```

Note: filtering by group **does not replace** inspecting the full tree, because a bridge may live under a different group (`commons-logging`, legacy `log4j`, `org.slf4j`, etc.). Not every direct Log4j 2 dependency is a backend: `log4j-api` by itself is an API; `log4j-core` is a primary implementation.

### 5.3. Reading Effective Versions and Scopes

Maven applies dependency mediation rules; a different version may be chosen than the one appearing in a deeper branch of the tree. Inspect output for dependencies omitted due to conflicts when needed using the verbose mode supported by your Maven Dependency Plugin, such as:

```bash
mvn dependency:tree -Dverbose
```

The `-Dverbose` output depends on the plugin version; if it lacks the details you need, check `mvn help:effective-pom`, `dependencyManagement` configuration, and the appropriate plugin reports.

Important scopes:

| Maven scope | Common meaning for logging |
| --- | --- |
| `compile` | Present on both compile and runtime classpaths in the standard Maven model. |
| `runtime` | Not needed to compile code calling the API, but required at runtime. |
| `test` | For tests only; should not be expected in the production package. |
| `provided` | Available at compile time, but expected to be supplied by the external runtime environment; easily missing in standalone deployments. |

For example, code with `slf4j-api` in `compile` scope but a provider only in `test` scope will produce logs during unit tests, while the production build may have no provider.

### 5.4. Inspecting Maven's Runtime Classpath

When you suspect a JAR is missing at runtime or when different runners behave differently:

```bash
mvn dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt -DincludeScope=runtime
```

The purpose of this command is to export the Maven dependency classpath for inspection. It is **not** an exact replica of the classpath inside every fat JAR, module path, or container; launchers can alter the set of JARs. Do not treat `build-classpath` output as final proof if production runs via a different launcher.

## 6. Gradle: Check the Right Configuration, Not Just `compileClasspath`

Gradle uses **configurations** such as `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath`. When a backend is missing at runtime, inspect `runtimeClasspath`.

On Linux/macOS:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

On Windows:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

`dependencies` shows the module structure and resolved versions; `dependencyInsight` helps identify **why a particular version was chosen**, the dependency path, and conflict resolution rules. Run these against the appropriate configuration for your application or tests.

In a multi-module project, target the specific module:

```bash
./gradlew :payment-service:dependencies --configuration runtimeClasspath
```

Do not assume every module shares the same runtime classpath just because they share a root build. A library module may only need the logging API, while the runnable application module supplies the provider.

### Choosing One Backend in the Application Module

An illustrative Gradle declaration for SLF4J + Logback:

```groovy
dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.16'
}
```

This is a **`build.gradle` snippet**, not a complete Gradle project. It expresses that code compiles against the API and uses Logback at runtime, though the effective versions still depend on resolution rules, platforms/BOMs, and other dependencies. Always verify `runtimeClasspath` after dependency resolution. In real projects, let the appropriate framework/BOM manage versions consistently whenever possible instead of arbitrarily pinning versions that conflict with the platform.

## 7. Runnable Example with Java 17 and Maven: Proving the Runtime Backend

This exercise intentionally uses **one** backend: SLF4J 2.x + Logback Classic. The Java code inspects the factory loaded at runtime and then emits an event. The output is predictable and does not depend on timestamps.

Requirements: **JDK 17+, Maven**, and access to fetch the declared dependencies.

Create the project:

```text
logging-dependency-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggingDependencyCheck.java
        └── resources/
            └── logback.xml
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-dependency-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Explanation:

- `slf4j-api`: Java code uses a unified API.
- `logback-classic`: backend and SLF4J 2.x provider for the example.
- `logback-core`: pulled in transitively by Logback Classic.
- Maven plugins enable compiling for Java 17, running `main`, and printing the dependency tree.
- Versions are pinned for a reproducible example; **they are not claimed to be the latest or free of current vulnerabilities**.

### 7.2. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

The pattern omits timestamps and thread names for deterministic output. `logback.xml` only takes effect if **Logback is genuinely the active backend**. If the runtime selects Log4j 2 or the NOP provider, this file does not control that backend's output.

### 7.3. `src/main/java/demo/LoggingDependencyCheck.java`

```java
package demo;

import org.slf4j.ILoggerFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingDependencyCheck {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingDependencyCheck.class);

    private LoggingDependencyCheck() {
    }

    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        String actual = factory.getClass().getName();
        String expected = "ch.qos.logback.classic.LoggerContext";

        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Unexpected logging factory: " + actual);
        }

        System.out.println("factory=" + actual);
        LOG.info("event=logging.ready api={} backend={}",
                "slf4j", "logback");
    }
}
```

Run command from the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LoggingDependencyCheck
```

**The two lines explicitly printed by the program when using the sample dependencies and configuration:**

```text
factory=ch.qos.logback.classic.LoggerContext
INFO|LoggingDependencyCheck|event=logging.ready api=slf4j backend=logback
```

Maven or the runtime environment may emit additional notices of their own; the lines above are the expected application output when the configuration is loaded properly.

### 7.4. Why Do Those Two Lines Matter?

1. `LoggerFactory.getILoggerFactory()` returns the factory supplied by the active SLF4J provider. In Logback Classic, the expected implementation name for this example is `ch.qos.logback.classic.LoggerContext`.
2. Comparing the factory name makes the program **fail loudly** if the runtime picks a different provider or the NOP factory; it does not silently assume correctness from a JAR's presence in `pom.xml`.
3. The `LoggingDependencyCheck` logger emits `INFO` and the root logger is configured at `INFO`, so the event is accepted.
4. `%logger{0}` prints the short class name `LoggingDependencyCheck`; `%msg` holds the message after `{}` placeholder substitution.
5. The example proves the actual backend of **the SLF4J path in the Maven-launched process**. It does not by itself prove that a Docker image or fat JAR packaged later will have the same classpath.

### 7.5. Checking the Sample Project's Own Dependency Tree

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.slf4j
mvn dependency:tree -Dincludes=ch.qos.logback
```

The goal is to verify that `slf4j-api`, `logback-classic`, and `logback-core` are in the tree with no unintended providers. The exact tree formatting, conflict lines, and transitive versions printed by the tool can vary with release metadata; do not write tests that assert on the entire raw text tree.

## 8. Matrix of Common Combinations

| Application code calls | Desired backend | Components to understand | Typical config file |
| --- | --- | --- | --- |
| SLF4J 2.x | Logback | `slf4j-api` + compatible `logback-classic` | `logback.xml` |
| SLF4J 2.x | Log4j 2 | `slf4j-api` + `log4j-slf4j2-impl` + compatible `log4j-core` | `log4j2.xml` |
| Log4j 2 API | Log4j 2 | `log4j-api` + `log4j-core` | `log4j2.xml` |
| JUL | JUL | JDK `java.util.logging` API and handlers | `logging.properties` |
| SLF4J 2.x | JUL | Compatible `slf4j-jdk14` provider | JUL configuration |
| Commons Logging | SLF4J + final backend | An explicitly chosen bridge, e.g. `jcl-over-slf4j` | Per final backend |
| JUL | SLF4J + final backend | `jul-to-slf4j` and JUL bridge installed at runtime | Per final backend |

The table describes **required routing directions**, not a recommendation to install all of these libraries into one application. In particular, do not treat the co-presence of `log4j-core` and `logback-classic` on the classpath as definitive proof of two SLF4J providers; check which bridges/providers are present and which one is actually loaded.

### Which Direction Does a Bridge Go?

In dependency names, the order of tokens is easy to confuse:

```text
log4j-to-slf4j
    Log4j 2 API  ---> SLF4J

log4j-slf4j2-impl
    SLF4J 2.x    ---> Log4j 2

jul-to-slf4j
    JUL          ---> SLF4J

slf4j-jdk14
    SLF4J        ---> JUL

jcl-over-slf4j
    Commons Logging ---> SLF4J

slf4j-jcl
    SLF4J        ---> Commons Logging
```

If you combine **two opposing bridges** in a way that forms a cycle, an event can bounce back and forth between APIs/implementations instead of reaching the final backend.

## 9. Detecting and Fixing Logging Forwarding Loops

### 9.1. Log4j 2 API ↔ SLF4J

A serious mistake is having both of these at the same time:

- `log4j-to-slf4j`: Log4j 2 API → SLF4J.
- `log4j-slf4j2-impl`: SLF4J 2 → Log4j 2.

These are **opposite directions**. Do not use them together in a single logging route, as they can create a forwarding loop; versions and implementations may also actively detect or reject the invalid combination.

Choose one architecture:

**Option A — Log4j 2 as the final backend**

```text
SLF4J calls ---> log4j-slf4j2-impl ---> Log4j 2 Core
Log4j 2 API calls --------------------> Log4j 2 Core
```

Exclude `log4j-to-slf4j` from the runtime when using this route.

**Option B — Logback as the final backend**

```text
SLF4J calls ---------------------> Logback Classic
Log4j 2 API calls -> log4j-to-slf4j -> SLF4J -> Logback
```

Do not include `log4j-slf4j2-impl` in the runtime for this route.

The goal is not to delete every dependency with "log4j" in its name. A library may depend only on **`log4j-api`** without pulling in `log4j-core`; inspect the exact paths and intended backend before adding exclusions.

### 9.2. JUL ↔ SLF4J

If an application wants to route **JUL → SLF4J → Logback**, you can use `jul-to-slf4j` and install `SLF4JBridgeHandler` at runtime per your library/framework guidelines.

Do not simultaneously configure **SLF4J → JUL** via `slf4j-jdk14` while installing the opposing **JUL → SLF4J** bridge, as this can create a logging loop once the path is triggered.

A subtle point: merely adding the `jul-to-slf4j` JAR to the dependency tree does not prove JUL events are being bridged. You must verify that **the handler is installed** and check the active JUL configuration. Some frameworks manage this step automatically; do not install it twice or bypass the framework's lifecycle.

### 9.3. Commons Logging ↔ SLF4J

`jcl-over-slf4j` forwards Commons Logging calls to SLF4J. `slf4j-jcl` goes the opposite way. Avoid having both in the same route to prevent loops or class conflicts. For frameworks that have their own Commons Logging mechanism (such as framework-integrated JCL variants), check their documentation and actual dependencies rather than adding a bridge out of habit.

**Verification principle:** draw **one-way arrows from every calling API to the final backend**, then confirm no arrow points backward.

## 10. Multiple SLF4J Providers: Identifying and Resolving

If SLF4J 2.x detects multiple `SLF4JServiceProvider` implementations, startup may warn about multiple providers and list the corresponding classes. An example situation:

```text
slf4j-api
logback-classic
log4j-slf4j2-impl
log4j-core
```

When both Logback and Log4j 2's SLF4J provider are present, the application may pick an unintended provider. It may look as if `logback.xml` is being ignored because the runtime is actually running Log4j 2, or vice versa.

Resolution workflow:

1. Decide the **final backend** first: Logback, Log4j 2, or JUL.
2. Find the parent dependency pulling in the extra provider using Maven `dependency:tree` or Gradle `dependencyInsight`.
3. Remove the extra provider by **adjusting dependencies in the appropriate module**, using exclusions where needed.
4. Keep the provider compatible with your API and JDK versions.
5. Re-check the runtime dependency tree.
6. Run a smoke test to confirm which factory/provider is actually selected.
7. Observe a sample event at the configured output, not just startup messages.

### Maven: Exclusions When a Dependency Pulls an Extra Backend

Suppose `com.example:legacy-library` unexpectedly brings in `logback-classic`, while the application intentionally uses Log4j 2:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

This is an **exclusion template**, not a verified real-world dependency. Replace the library coordinates and version with the actual module in your tree. Maven exclusions apply along a **specific dependency path**: if the extra provider is also pulled in by another branch, handle that branch too. Do not blindly exclude `slf4j-api` if libraries still need it to run.

### Gradle: Excluding by Group and Module

```groovy
dependencies {
    implementation('com.example:legacy-library:1.0.0') {
        exclude group: 'ch.qos.logback', module: 'logback-classic'
    }
}
```

This is an illustrative configuration snippet. In Gradle, an exclusion on one edge does not necessarily remove the module from the entire graph if another edge still requires it. Always re-run `runtimeClasspath` after making changes.

## 11. Detecting the Provider/Binding at Runtime

**The dependency tree only shows resolved artifacts.** Runtime behavior can differ when the application is packaged as a fat JAR, WAR, run inside an application server, under the JPMS module system, or with plugin classloaders.

For SLF4J:

```java
String factoryName =
        org.slf4j.LoggerFactory.getILoggerFactory()
                               .getClass()
                               .getName();
System.out.println(factoryName);
```

This is an **illustrative snippet** for use inside a method when SLF4J is on the classpath. It reveals the active `ILoggerFactory`. For example:

- `ch.qos.logback.classic.LoggerContext`: Logback Classic is providing the factory.
- `org.slf4j.helpers.NOPLoggerFactory`: a NOP/no-operation implementation may be in use.
- Another provider's factory: look up that class/provider and compare it against your intended backend.

**Do not rely on a single class name string alone to guarantee the entire pipeline works.** The right factory can still emit nothing if levels are too high, appenders are unattached, filters drop events, or the collector is not receiving them. Combine a **factory check + sample event + destination check** in your smoke test.

With the Log4j 2 API, you can inspect the `LoggerContext` implementation and active configuration via Log4j Core APIs/diagnostics, but avoid confusing `org.apache.logging.log4j.LogManager` with `org.slf4j.LoggerFactory`: they belong to two different APIs.

### ServiceLoader and JAR Packaging

In SLF4J 2.x, providers use Java's service mechanism, typically declared via the resource:

```text
META-INF/services/org.slf4j.spi.SLF4JServiceProvider
```

When building a fat JAR or shading, if the build drops or overwrites this service file, the runtime may fail to find the provider even though the bytecode classes are present. If you use the Maven Shade Plugin or similar tools, ensure **service descriptors are handled properly** and that only the intended provider remains.

However, do not blindly merge service descriptors to keep *all* logging providers: if multiple providers remain, SLF4J may still warn or pick an unintended one. The goal is **one designed runtime route**, not "the more JARs, the safer."

## 12. Common Scenarios in Frameworks and Deployment Environments

### 12.1. A Framework Starter Already Brings a Backend

Many web/application frameworks include a default logging starter. If you manually add `log4j-core` or `logback-classic` without checking the dependency tree, the application may end up with both the default backend and the new one.

The fix is to identify **which starter brings the backend** and use the framework's official logging-replacement mechanism. Do not strip base libraries with broad exclusions without knowing which modules depend on which API/bridge.

### 12.2. Unit Tests PASS, but Production Logs Nothing

Possible causes:

- The provider is declared in `test` scope and is absent from the runtime artifact.
- The `mvn test` classpath differs from the `java -jar` classpath.
- The runtime container loads a different configuration file.
- Fat JAR packaging stripped the SLF4J service descriptor.
- The framework is actually using a different backend, so your intended config file is ignored.

Inspect the **final runtime artifact** and launch with the same JVM options and environment as deployment—do not stop at the development-time dependency tree.

### 12.3. Multiple Classloaders or JPMS

Application servers, plugin systems, and the JPMS module path can complicate provider loading. One classloader may see the SLF4J API without seeing the provider; another may hold a mismatched provider version. With JPMS, check which modules provide services and ensure the appropriate `ServiceLoader` readability is in place.

When diagnosing, record the exact **JVM, classloader/module path, packaged artifact, and startup command**. Do not assume a Maven command in your workspace behaves identically to an application server running in another environment.

### 12.4. Startup Warnings About Providers or Bindings

Common messages and what they mean:

| Symptom | Common cause | What to check |
| --- | --- | --- |
| "No SLF4J providers were found" | SLF4J 2.x could not find a compatible provider | Runtime classpath, service descriptors, provider/binding version. |
| "Multiple SLF4J providers" | More than one SLF4J 2.x provider is present | Pick a single backend, locate and remove the extra provider. |
| Binding targeting SLF4J 1.7 ignored | 2.x API encountered a legacy binding | Switch to a compatible SLF4J 2.x provider. |
| `ClassNotFoundException`/`NoClassDefFoundError` in logging | Missing dependency, wrong version, or stripped during packaging | Check API/core/provider and the final artifact. |
| `NoSuchMethodError` initializing or calling logger | Version mismatch between API and implementation | Check resolved versions and duplicate JARs. |
| No logs printed, no exception | Logger level OFF/too high, NOP provider, appender/collector not receiving | Factory smoke test, logger levels, and output destination. |
| Duplicate log entries | Appender additivity, misconfigured bridge, or collector re-sending | Count per channel; check logger → appender routing. |

Not every logging warning means "Logback is missing." Read the exact class names, artifacts, versions, bridge directions, and runtime configuration.

## 13. Checklist for Checking Logging Dependencies in a Real Project

Follow these steps in order instead of jumping straight to editing `logback.xml` before confirming the backend:

1. **Identify the APIs in Java code.** Packages `org.slf4j`, `org.apache.logging.log4j`, `java.util.logging`, and `org.apache.commons.logging` show which APIs are called.
2. **Choose the target backend.** For example, SLF4J → Logback or SLF4J → Log4j 2. Draw a one-way route.
3. **Inspect the runtime dependency graph.** Maven `dependency:tree`; Gradle `dependencies --configuration runtimeClasspath`.
4. **Cross-check versions.** SLF4J API 1.7 or 2.x? Is the provider/binding from the same generation? Does the backend support the running JDK/framework?
5. **Count providers, not just JARs.** Is there a NOP, one valid provider, or multiple providers? Which class actually implements `SLF4JServiceProvider`?
6. **Trace bridges by direction.** Are `log4j-to-slf4j` and `log4j-slf4j2-impl` both present? Are JUL and SLF4J bridged in both directions at once?
7. **Verify the runtime artifact.** Does the JAR/WAR/fat JAR contain the provider and service descriptor? Does the container add its own logging JARs?
8. **Verify the runtime backend.** Print the factory/class or use appropriate diagnostics; do not guess from config files.
9. **Check which configuration is loaded.** `logback.xml` controls Logback, `log4j2.xml` controls Log4j 2; a launcher may point to a different path.
10. **Emit a sample event.** Log level, logger name, and event code; confirm exactly one event arrives on the intended channel.
11. **Check the path to the collector.** Are console/files receiving logs? Is the collector reading, parsing, and storing them?
12. **Lock it in with a regression test.** Test startup against the actual artifact's dependencies to catch duplicate providers or backend drift after version upgrades.

For CI, you can use your build tool's dependency analysis alongside a smoke test that verifies the final provider. **Do not rely solely on grepping JAR names**, because an API dependency is not a provider and some classes may reside inside repackaged/shaded artifacts.

## 14. Practice: Deliberate Test Scenarios

### Scenario A — SLF4J API Only

```text
slf4j-api 2.x
no compatible provider
```

Prediction: Java code still compiles; the runtime typically warns that no provider was found and may use a NOP logger. To fix it, **choose an appropriate backend/provider**—do not just add `log4j-api` (the Log4j 2 API) and expect SLF4J to wire into it automatically.

### Scenario B — Two Providers

```text
slf4j-api 2.x
compatible logback-classic
compatible log4j-slf4j2-impl
compatible log4j-core
```

Prediction: the runtime detects multiple providers, may warn, and selects one. The fix is to choose one final route, exclude the other provider, and re-verify with the factory check and a sample log.

### Scenario C — Log4j 2 ↔ SLF4J Loop

```text
log4j-to-slf4j           (Log4j 2 API -> SLF4J)
log4j-slf4j2-impl        (SLF4J 2 -> Log4j 2)
```

This configuration risks creating a loop and must not be kept together. If you choose Logback, keep the Log4j 2 API → SLF4J bridge and Logback as the backend. If you choose Log4j 2, keep SLF4J → Log4j 2 and remove the reverse bridge.

### Scenario D — Right API, Wrong Output

```text
SLF4J -> Logback is correct
but INFO is not visible
```

You can no longer blame dependencies. Continue checking:

- Logger name and effective level.
- Filters, appenders, and additivity.
- Which `logback.xml` was loaded.
- Console/file destinations and permissions.
- Whether the collector is reading the right stream and parsing it properly.
- Log loss from queues, I/O, or shutdown.

**Checking dependencies is the foundational step; it does not replace testing configuration and output data.**

## 15. Preventing Regressions After Dependency Upgrades

- **Centralize version management:** use Maven `dependencyManagement`/BOM or Gradle platforms/version catalogs so modules do not independently pick different SLF4J/Log4j versions.
- **Upgrade the API together with its provider:** when moving from SLF4J 1.7 to 2.x, switch bindings to compatible providers; do not bump only the `slf4j-api` line.
- **Maintain one intentional backend:** manage the final provider in the runnable application module; in reusable libraries, prefer depending only on the API unless there is a specific requirement.
- **Audit transitive dependencies:** especially framework starters and SDKs that may bring in extra logging implementations.
- **Smoke-test the final artifact:** test `java -jar` or the real production launcher, not just Maven exec.
- **Watch startup warnings:** fail builds/tests when known bad bindings/providers appear; do not ignore them just because "the app still runs."
- **Track security advisories:** apply supported patches for backends and bridges. Choose versions based on current security advisories and compatibility, rather than copying a learning example's version forever.
- **Test shutdown and high load:** async backends or collectors can drop records; the right provider does not guarantee durability.
- **Protect sensitive data:** changing backends or formatters can alter how `Throwable`/MDC data is printed; inspect tokens, passwords, and private data across all channels.
- **Document the logging architecture:** describe it with an arrow diagram alongside the key dependency list, owners, config files, and upgrade procedure.

## 16. Self-Check Exercises

### Exercise 1 — Distinguishing API, Provider, and Backend

An application imports `org.slf4j.Logger` and declares `slf4j-api`, but has no compatible implementation. Can it compile? Is it guaranteed to print logs to the console?

**Hint:** The code can compile because the API is present. Without a compatible SLF4J 2.x provider, the runtime may use a NOP/no-operation logger; you cannot assume logs will appear. You must add a proper backend/provider and verify at runtime.

### Exercise 2 — Identifying a Conflict

The final dependency tree contains `slf4j-api 2.x`, `logback-classic`, `log4j-slf4j2-impl`, and `log4j-core`. What steps would you take to fix it?

**Hint:** Choose the desired backend; find the parent dependency pulling in the unwanted provider; exclude the extra module on the appropriate path; re-check `runtimeClasspath`; run a factory smoke test and verify a sample log. Do not try to "raise classpath priority order" as a permanent fix.

### Exercise 3 — Forwarding Loops

Why should `log4j-to-slf4j` and `log4j-slf4j2-impl` not be used together?

**Hint:** The two modules point in opposite directions: Log4j 2 API → SLF4J and SLF4J → Log4j 2. Using both together can create a forwarding loop instead of reaching a final backend. Pick one direction and one implementation.

### Exercise 4 — Tests Pass, Production Is Silent

Project tests log via Logback, yet `java -jar` in a container produces no logs. List at least five things to check.

**Hint:** Test/runtime scopes; dependencies inside the final artifact; fat JAR service descriptors; classloaders; actual active provider; JVM arguments; `logback.xml` configuration; logger levels; appenders; stdout/file collector. Compile/test results do not prove an identical production runtime.

### Exercise 5 — Analyzing Build Commands

How do the purposes of these two commands differ?

```bash
mvn dependency:tree
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
```

**Hint:** Maven prints the project's tree after dependency resolution; Gradle's `dependencyInsight` explains why a specific dependency and its version were selected in a given configuration. To see the full Gradle tree, use `dependencies --configuration runtimeClasspath`.

### Exercise 6 — Checking for Duplicate Logging

An `order.created` event appears twice on the console. Can you conclude this is caused by two SLF4J providers?

**Hint:** Not yet. Multiple providers are usually a provider-selection issue; duplicate logs can also come from appenders attached to both a child logger and root, a misconfigured bridge, two log calls in code, or a collector re-sending events. Check **provider**, then **logger route/appender/additivity**, and then **the collection pipeline**.

### Exercise 7 — Designing a Reusable Java Library

You are writing a Java library consumed by multiple applications, each using a different logging backend. How should the library declare its logging dependencies?

**Hint:** Typically have the library depend on the appropriate **API/facade** without forcing every consumer onto a single backend. The application module is responsible for choosing the actual provider and output configuration. If the library must bridge a legacy system's logging, document the bridge direction clearly and avoid causing conflicts for consumers.

**Conclusion:** A stable logging setup requires **the right API, the right provider/binding, the right backend, the right bridge direction, and the right runtime classpath**. Inspect the dependency tree to see *what is present*, inspect the factory/provider to see *what is active*, and emit a sample event to verify *whether logs actually arrive*.
