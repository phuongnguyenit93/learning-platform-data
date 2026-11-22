# Dependency Conflicts in Java Logging: SLF4J, Logback, Log4j2, and JUL

A Java application may run normally in the IDE, yet upon packaging or deployment it can produce `multiple SLF4J providers` warnings, lose logs, print duplicate logs, ignore `logback.xml`, or fail with `NoClassDefFoundError`. The root cause usually lies in the **dependency graph and runtime classpath**: multiple libraries bringing in a logging implementation, an API version incompatible with the provider, a bridge routing logs in the wrong direction, or a configuration written for a backend that is not actually active.

**Logging dependency conflicts** are not just about “having two versions of the same JAR.” They can involve **multiple competing providers**, **a missing provider**, **a generation mismatch between API and implementation**, **a bridge loop**, or **two independent pipelines writing simultaneously**. To fix them properly, you must trace the path of log events and choose **one primary logging destination** by design, rather than adding JARs until the warning disappears.

In this article, `SLF4J` is a commonly used facade, `Logback` and `Log4j2 Core` are backends, and `java.util.logging` (**JUL**) is the logging system built into the JDK. Versions and runtime messages may vary across releases; always verify against the actual dependency tree and runtime.

## 1. Understand the Three Layers: API, Backend, Bridge

```text
Application or library code
  |
  +-- SLF4J API ------------> SLF4J provider ------> Backend
  |                                |                     |
  |                                +-- Logback Classic   +--> Console/File
  |                                +-- Log4j2 provider   +--> Console/File
  |                                +-- slf4j-simple      +--> Simple output
  |
  +-- Log4j2 API -----------> Log4j2 Core or adapter
  |
  +-- JUL API --------------> JUL Handler or bridge
```

The **API/facade** is where code calls `info/debug/error`. The **provider/backend** decides configuration and emits log records. A **bridge/adapter** forwards calls from one API to another to unify the pipeline. A bridge always has a **specific direction**; installing both directions creates a loop.

| Artifact | Common Role | Notes |
| --- | --- | --- |
| `org.slf4j:slf4j-api` | SLF4J facade API. | Does not write to files or the console on its own without a provider. |
| `ch.qos.logback:logback-classic` | SLF4J provider with the Logback backend. | Pulls in `logback-core` and required dependencies. |
| `org.slf4j:slf4j-simple` | Simple logging provider. | Good for small demos, but competes with Logback if both are present. |
| `org.slf4j:slf4j-nop` | Provider that intentionally discards logs. | Unsuitable if the application requires operational logs. |
| `org.apache.logging.log4j:log4j-api` | Log4j2 API. | Not synonymous with Log4j2 Core. |
| `org.apache.logging.log4j:log4j-core` | Log4j2 backend and appenders. | Needs a version compatible with `log4j-api`. |
| `org.apache.logging.log4j:log4j-slf4j2-impl` | Direction **SLF4J 2.x → Log4j2**. | Choose when Log4j2 is the backend for SLF4J 2.x. |
| `org.apache.logging.log4j:log4j-slf4j-impl` | Direction **SLF4J 1.7.x → Log4j2** on the compatibility branch. | Do not use in place of an SLF4J 2.x provider. |
| `org.apache.logging.log4j:log4j-to-slf4j` | Direction **Log4j2 API → SLF4J**. | Do not install together with an SLF4J → Log4j2 adapter. |
| `org.slf4j:jul-to-slf4j` | Bridge **JUL → SLF4J**. | Requires installing the handler/configuring the bridge, not just adding the dependency. |
| `org.slf4j:slf4j-jdk14` | Provider **SLF4J → JUL**. | Do not use simultaneously with the JUL → SLF4J bridge if it creates a loop. |

The final destination can be Logback, Log4j2, or JUL. **Do not choose a backend just by looking at the imports of a single class**: an external dependency might use the Log4j API while the application uses SLF4J and a one-way bridge to combine them.

## 2. The Most Common Error: Multiple SLF4J Providers on the Classpath

Suppose a project includes both `logback-classic` and `slf4j-simple`. Both provide an implementation for the SLF4J facade. At startup, SLF4J may emit a warning that **multiple providers** are present and pick one of the visible providers via runtime discovery. **Do not rely on arbitrary classpath ordering to decide the backend.**

A typical broken dependency tree:

```text
application
+-- ch.qos.logback:logback-classic
|   +-- ch.qos.logback:logback-core
|   \-- org.slf4j:slf4j-api
\-- org.slf4j:slf4j-simple          <-- adds a competing provider
```

As a result, `logback.xml` may have no effect because the other provider was chosen, leading to unexpected log formats, different log levels, and confusing runtime messages.

### How to Fix

1. **Choose the primary backend** for the application, for example Logback.
2. **Keep exactly one matching SLF4J provider** at runtime, for example `logback-classic`.
3. Exclude `slf4j-simple`, `slf4j-nop`, `slf4j-reload4j`, or other Log4j2 providers if they are not part of the design.
4. Check both **direct and transitive dependencies**, especially artifacts pulled in by starters/frameworks and SDKs.
5. Re-run on the **final packaged classpath**, not only the unit test classpath.

**Distinguish API from provider:** multiple dependencies referencing `slf4j-api` does not mean there are multiple providers. Maven/Gradle normally resolves those to a single artifact version on the classpath; the real issue lies in the providers or in an incompatible resolved version.

## 3. SLF4J 1.7 and 2.x: Do Not Mix Bindings with Providers

The two generations of SLF4J use different implementation discovery mechanisms:

| API Generation | Backend Discovery Mechanism | Required Artifact |
| --- | --- | --- |
| SLF4J 1.7.x and earlier | Looks for **`StaticLoggerBinder`** (binding). | Binding targeting SLF4J 1.7.x. |
| SLF4J 2.0.x | Uses `ServiceLoader` to find **`SLF4JServiceProvider`**. | Provider compatible with SLF4J 2.0.x. |

Therefore, if the runtime uses `slf4j-api:2.0.x` but only has an old binding for 1.7, SLF4J 2 may **ignore the old binding**, report a missing provider, and fall back to a no-op (`NOP`) implementation for SLF4J calls. Conversely, the 1.7 API does not understand the 2.x provider mechanism.

Cases to distinguish:

- **API 2.0.x + compatible 2.0.x provider:** valid architecture; still ensure there is no competing provider.
- **API 2.0.x + only 1.7.x binding:** cannot resolve an SLF4J 2.x provider.
- **API 1.7.x + only 2.0.x provider:** does not satisfy SLF4J 1.7's binding mechanism.
- **API 2.0.x + some libraries compiled against an older SLF4J API:** not automatically an error; the client-facing API maintains broad compatibility, though the runtime provider must still match.
- **Multiple versions of `slf4j-api` declared:** the build tool will pick one according to resolution rules; check the **effective runtime version** instead of guessing from `pom.xml`.

Messages may include phrases such as “No SLF4J providers were found”, “Class path contains multiple SLF4J providers”, or warnings about bindings targeting 1.7. **Exact wording can vary by version**; use the warning text as a clue, then inspect the dependency tree.

### Versioning Principles

`org.slf4j` artifacts such as `slf4j-api` and `slf4j-simple` must match within the same version branch; with SLF4J 2.0.x, the provider must target 2.0.x, not a 1.7.x binding. Logback and Log4j2 providers have their own versioning schemes, so **do not compare Logback's 1.5 with SLF4J's 2.0 expecting the numbers to be equal**; consult the backend's compatibility matrix.

In multi-module projects, apply dependency management or a version catalog/BOM where appropriate to keep versions consistent. Do not downgrade `slf4j-api` just to “hide” a warning if the rest of the application uses SLF4J 2.x features.

## 4. Dangerous Loop: Bidirectional Bridges

An error more serious than a multiple-provider warning is creating a **logging forwarding loop**:

```text
SLF4J API
  | log4j-slf4j2-impl
  v
Log4j2 API
  | log4j-to-slf4j
  v
SLF4J API
  | ...
  +----> loop
```

**Never deploy** `log4j-slf4j2-impl` together with `log4j-to-slf4j`. Likewise, `log4j-slf4j-impl` must not be combined with this reverse-direction bridge. Log4j2 may detect the invalid configuration and throw an error rather than actually looping infinitely; regardless of the exact symptom, a bidirectional loop design must be eliminated.

### Choose One of the Two Destinations

| Desired Backend | Valid Forwarding Direction | What to Exclude |
| --- | --- | --- |
| **Logback** handling logs called via Log4j2 API | `Log4j2 API → log4j-to-slf4j → SLF4J → Logback` | Do not add `log4j-slf4j2-impl`. |
| **Log4j2 Core** handling logs called via SLF4J 2.x | `SLF4J → log4j-slf4j2-impl → Log4j2 Core` | Do not add `log4j-to-slf4j`; do not add a competing Logback provider. |
| **JUL** as backend | `SLF4J → slf4j-jdk14 → JUL` | Do not simultaneously attach JUL → SLF4J creating a loop. |
| **Logback** as backend with libraries calling JUL | `JUL → jul-to-slf4j → SLF4J → Logback` | Do not add `slf4j-jdk14` in the reverse direction; activate the JUL bridge properly. |

A bridge is not a generic “log upgrade” plugin. It translates an API in a **fixed direction** and can affect formatting overhead, level mapping, or contextual information. Integrating JUL with `jul-to-slf4j` requires installing `SLF4JBridgeHandler` or an equivalent integration; **the dependency alone does not replace JUL's handlers**.

Other bridge pairs also require checking direction: `jcl-over-slf4j` routes Commons Logging → SLF4J, whereas `slf4j-jcl` routes SLF4J → Commons Logging. Never place both directions together in a way that turns a call into a loop.

## 5. Distinguishing Backend Conflicts from Configuration-Based Duplicate Logs

Not every occurrence of two identical log lines is caused by “multiple providers.”

**Scenario A – Two competing providers:** Logback and `slf4j-simple` are both on the runtime classpath. SLF4J may warn about provider selection. The fix is to clean up dependencies.

**Scenario B – Only one Logback provider, yet logs are printed twice:** the same appender is attached to both a child logger and the root logger while `additivity=true`. The fix is to adjust appender/additivity configuration, not to change the backend.

**Scenario C – A library calls JUL while the application uses Logback:** JUL events may still go to `ConsoleHandler` while SLF4J events go to Logback, producing two differently formatted output streams. Decide whether to bridge JUL → SLF4J or keep the JUL pipeline independent; simply adding the Logback dependency does not route JUL calls into it.

**Scenario D – Both Log4j API and SLF4J API are present at runtime:** this is not a conflict by itself. It is valid if a single one-way bridge routes both APIs to a unified backend. Check which provider and adapter are actually active.

In short, **counting JARs with “logging” in their names is not enough to diagnose an error**. You must inspect each artifact's role and the event's path from API to sink.

## 6. Symptoms to Recognize

| Runtime/Build Symptom | Suspected Cause | What to Check |
| --- | --- | --- |
| **multiple SLF4J providers** warning | Two or more SLF4J 2.x providers are present. | `logback-classic`, `slf4j-simple`, `slf4j-reload4j`, `log4j-slf4j2-impl`. |
| **multiple SLF4J bindings** warning in legacy apps | Multiple `StaticLoggerBinder` bindings from the 1.7 ecosystem. | `slf4j-api` version, legacy bindings. |
| **no SLF4J providers** warning | Missing provider, API-only dependency, or legacy binding ignored. | Runtime artifacts, scope, service descriptor packaging. |
| Logs missing or not emitted despite calls | NOP provider, wrong level/filter, or another backend's config. | Actual provider, loaded config, effective level. |
| `logback.xml` has no effect | Runtime selected a different backend or framework loaded another config. | Provider + config files on the classpath. |
| `log4j2.xml` has no effect | Log4j Core not selected, missing artifact, or config not loaded. | API/Core, adapter, provider, resources. |
| `NoClassDefFoundError` / `NoSuchMethodError` | Runtime classpath diverges from compile classpath, mismatched API/impl versions, missing JAR. | Which JAR provides the class, dependency graph, packaging. |
| `ClassCastException` casting the backend | Code assumes SLF4J logger factory belongs to Logback while runtime uses another backend. | Decouple facade from backend-specific APIs. |
| Bridge/loop error between Log4j2 and SLF4J | Both opposing adapters were included. | `log4j-slf4j2-impl` and `log4j-to-slf4j`. |
| Single event emitted multiple times | Appender additivity, multiple pipelines/handlers, or duplicate collection config. | Loggers/appenders/collectors, not just dependencies. |
| Works in IDE but fails when packaged | Test scope, provided/runtime scope, assembly/shading, or Spring Boot repackaging differences. | Final classpath of the JAR/container. |

**Diagnose from the actual error, not by guessing from a single message.** `NoClassDefFoundError` can also come from non-logging libraries; read the full class name and stack trace.

## 7. Inspecting the Dependency Tree with Maven

Assuming you run the Maven project in the directory containing `pom.xml`:

```bash
mvn dependency:tree
```

Look for coordinates starting with:

```text
org.slf4j:slf4j-api
org.slf4j:slf4j-simple
org.slf4j:slf4j-nop
org.slf4j:slf4j-jdk14
ch.qos.logback:logback-classic
ch.qos.logback:logback-core
org.apache.logging.log4j:log4j-api
org.apache.logging.log4j:log4j-core
org.apache.logging.log4j:log4j-slf4j2-impl
org.apache.logging.log4j:log4j-slf4j-impl
org.apache.logging.log4j:log4j-to-slf4j
org.slf4j:jul-to-slf4j
```

In the dependency tree, inspect **which transitive path pulled in** a provider or bridge. Maven resolves version conflicts via dependency mediation (typically favoring the nearest path and declaration order on ties), so you cannot read a version inside a transitive dependency and assume it is the runtime version.

### Reading Dependencies from a Runtime Perspective

Distinguish between scopes:

- `compile`: dependency is normally on both the compile and runtime classpaths.
- `runtime`: needed at runtime, though not necessarily required to compile business code.
- `test`: only on the test classpath; passing unit tests does not prove the application is packaged correctly.
- `provided`: relies on the runtime/container to supply the library; if that assumption is wrong, the deployed JAR will miss required classes.
- `optional` and dependency exclusions: affect which transitive artifacts reach the consuming project.

You can run `mvn help:effective-pom` to see versions applied by parent POMs, BOMs, or `dependencyManagement`. Always re-check `mvn dependency:tree` after configuration changes instead of reading only a few lines of `pom.xml`. When running a fat JAR, container, or launcher with a classpath different from Maven's, inspect the final runtime environment.

### Fixing with Targeted Exclusions

If a transitive dependency pulls in an unwanted provider, exclude the **provider artifact on the edge that brings it in** while keeping the appropriate API. Maven syntax:

```xml
<!-- Example inside a Spring Boot project that already manages versions. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

This is an **illustrative configuration snippet inside a Spring Boot POM**, not a standalone `pom.xml`. Excluding `spring-boot-starter-logging` is typically done when switching a Spring Boot application to another backend starter **and after adding the appropriate replacement backend**. Do not copy this exclusion into a project that uses default Logback, as doing so can remove the provider altogether.

**Do not exclude `slf4j-api` just because you see many lines referencing the API.** The problem usually lies in the provider or bridge, not in multiple libraries using the facade. Maven exclusions apply per dependency branch, so if the same artifact is pulled in via another branch, inspect the final tree.

## 8. Inspecting `runtimeClasspath` with Gradle

For Gradle projects, typical commands are:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency logback-classic --configuration runtimeClasspath
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat` if the project includes the Windows Gradle Wrapper. These commands are **instructions for an existing Gradle project with a build script**, not part of the Maven demo below.

`dependencyInsight` shows why a version was chosen; unlike Maven, Gradle's default conflict resolution favors the higher version unless constraints, platforms, forced rules, or custom configurations dictate otherwise. Therefore, two projects with the same declared dependencies can have **different runtime outcomes** if their build tools or version rules differ.

Example of excluding a transitive provider in Gradle Kotlin DSL when the parent dependency actually pulls in that artifact:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-logging"
        )
    }
    // Requires a suitable replacement backend dependency managed by the project.
}
```

The snippet above is **illustrative** for a project with Spring Boot version management; without versions, a BOM, or build plugins, it cannot be copied into an empty project and run as-is. Avoid global `configurations.all { exclude(...) }` rules without understanding their impact, as they can easily strip dependencies needed by other features.

## 9. Java 17 Practice: One SLF4J API, One Logback Provider

The walkthrough below demonstrates a **conflict-free** setup. The code uses only the SLF4J API, and the runtime has **a single provider: Logback Classic**. The program prints the implementation class name of `ILoggerFactory` to prove which provider was selected, while logging events in a fixed format.

The example uses **JDK 17 + Maven**. The versions `slf4j-api 2.0.17` and `logback-classic 1.5.18` are **pinned versions for this lesson**, not necessarily the latest releases. Real-world projects should use supported, security-patched versions and verify the compatibility matrix.

### 9.1. Project Structure

```text
logging-dependency-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LoggingDependencyDemo.java
        └── resources/
            └── logback.xml
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-dependency-demo</artifactId>
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
                    <mainClass>demo.LoggingDependencyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` pulls in `logback-core`; `slf4j-api` is declared directly so the lesson makes the API usage explicit. In applications that manage dependencies via a BOM, you do not necessarily specify a version on each dependency, but **the runtime should have only one SLF4J provider** for consistent behavior.

### 9.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

The pattern omits timestamps, thread names, MDC, and ANSI colors to keep output deterministic. In production, include fields needed for investigation and control sensitive data.

### 9.4. src/main/java/demo/LoggingDependencyDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingDependencyDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingDependencyDemo.class);

    public static void main(String[] args) {
        System.out.println(
                "factory=" +
                LoggerFactory.getILoggerFactory().getClass().getName()
        );

        LOG.debug("event=diagnostic.hidden");
        LOG.info("event=service.ready requestId={}", "req-17");
        LOG.warn("event=dependency.check outcome={}", "clean");
    }
}
```

### 9.5. Compile and Run

Open a terminal in the directory containing `pom.xml`; Maven may need network access to download dependencies on the first run:

```bash
mvn -q compile exec:java
```

**Standard output from the program**, excluding any separate output that Maven or the environment might print:

```text
factory=ch.qos.logback.classic.LoggerContext
INFO | demo.LoggingDependencyDemo | event=service.ready requestId=req-17
WARN | demo.LoggingDependencyDemo | event=dependency.check outcome=clean
```

Explanation:

1. `LoggerFactory.getILoggerFactory()` returns the Logback Classic provider's implementation: `ch.qos.logback.classic.LoggerContext`.
2. `LOG` belongs to the `demo.LoggingDependencyDemo` namespace and inherits the `INFO` level from root.
3. `DEBUG` is filtered out at the `INFO` threshold; the two `INFO`/`WARN` events are accepted by the `STDOUT` appender.
4. `{}` is SLF4J's parameter placeholder syntax, unlike JUL's `{0}`; Logback formats the message through the facade.
5. `logback.xml` in `src/main/resources` is placed on the classpath when Maven runs; with only one provider present, the backend configuration is picked up consistently.

### 9.6. Simulating a Mistake: Adding a Second Provider

If you **add** the following dependency to the demo's `pom.xml` (only in a test environment—never deploy this configuration):

```xml
<!-- ONLY TO ILLUSTRATE A PROVIDER CONFLICT, NOT A VALID CONFIGURATION. -->
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.17</version>
</dependency>
```

The runtime now contains both `logback-classic` and `slf4j-simple`. SLF4J may report **multiple providers**, and which backend gets selected should not be left to classpath ordering. Once you finish testing, **remove the `slf4j-simple` dependency** to return to a single provider. Do not force `slf4j.provider` as a way to mask an uncleaned dependency graph.

## 10. Runtime Classpath, Fat JARs, and Frameworks

### Multi-Module Projects

A library project should **depend on the API**, and typically should not force consumers to use a specific backend. If a library pulls `slf4j-simple` or Logback into a product's runtime, the main application may receive an unwanted extra provider. For libraries using SLF4J, declare `slf4j-api` with an appropriate scope and let the **final application** choose the backend.

However, some framework application starters intentionally ship a default backend because they target applications rather than standalone libraries. When switching backends, use the exclusion/starter mechanism supported by the framework instead of deleting every dependency with “logging” in its name.

### Spring Boot

In many traditional Spring Boot setups, `spring-boot-starter-logging` provides Logback by default. When switching to Log4j2 as the backend, applications typically switch to `spring-boot-starter-log4j2` and exclude the default logging starter on the necessary dependency branches. Specific Boot versions may change dependency details; **check the documentation and dependency tree for the exact version in use**.

Do not let both the Logback provider and the Log4j2 SLF4J provider occupy the runtime simply because two starters were pulled in from different modules. Also, `logback-spring.xml` is a configuration mechanism within the Spring Boot ecosystem; plain Java applications do not understand all of its extensions.

### Fat JARs, Shaded JARs, and Class Loaders

A “clean” Maven dependency tree does not guarantee a clean deployable artifact:

- Shading can **overwrite or accidentally drop** `META-INF/services/org.slf4j.spi.SLF4JServiceProvider`, causing the provider not to be found.
- Assembly or manual packaging can include **multiple JAR versions** or providers not visible in the expected build dependency tree.
- An application server may supply a logging library in a parent class loader, creating differences between local runs and runtime.
- `provided`/`test` scopes can leave the final runtime missing an implementation.
- Plugins, agents, or SDKs may use isolated logging; understand class loader isolation before assuming “multiple JARs” means a conflict.

Inspect the **classpath and contents of the exact deployed artifact**, not just the dependency declaration files. If using containers, inspect both the image and any platform-provided library layers.

## 11. Workflow for Resolving a Logging Dependency Incident

Work in order from root cause to resolution:

1. **Collect symptoms:** capture the full SLF4J/Log4j warning, exception stack trace, environment, and launch command. Do not screenshot just the last line.
2. **Identify the API used by logging code:** SLF4J, Log4j2 API, JUL, Apache Commons Logging, or another API.
3. **Choose one primary backend:** Logback, Log4j2 Core, or JUL. Map a one-way path for every other API.
4. **List actual providers and bridges:** inspect the dependency tree and runtime JARs; distinguish APIs from implementations.
5. **Check versions:** SLF4J 1.7 binding vs. 2.0 provider, Log4j API/Core, Logback compatibility, and Java baseline.
6. **Find the conflicting transitive branch:** run Maven/Gradle dependency reports or `dependencyInsight`; confirm which artifact pulls in the extra provider.
7. **Apply targeted exclusions:** remove the unwanted provider/adapter at the branch that introduces it while keeping the required API. Use a BOM/`dependencyManagement` to align versions.
8. **Remove reverse bridges:** especially `log4j-slf4j2-impl` with `log4j-to-slf4j`, or `slf4j-jdk14` with `jul-to-slf4j` when they form a loop.
9. **Verify the loaded configuration:** `logback.xml`, `log4j2.xml`, `logging.properties`, and framework-specific mechanisms; do not tweak config files while the backend is still wrong.
10. **Re-run on the final runtime:** unit tests, integration tests, fat JAR/container; verify startup, `INFO`, `DEBUG`, and exceptions with causes/stack traces.
11. **Confirm no duplicate or missing logs:** check stdout/files/collectors and appender additivity, not just that the warning disappeared.
12. **Lock in dependency hygiene:** add CI checks/dependency management rules so conflicting providers/bridges do not reappear after updates.

### Before–After Decision Example

**Before:** a project uses Logback, and a new library pulls in `slf4j-simple`; startup warns about multiple providers, and `logback.xml` is ignored in some environments.

**After:** keep `slf4j-api` and `logback-classic`, exclude `slf4j-simple` on the transitive branch, re-check the dependency tree, run on the final JAR, and verify the Logback factory is selected; test log levels and output. Do not rewrite the codebase to JUL just to dodge a classpath conflict.

## 12. Common Bad Fixes and Why They Are Dangerous

| Quick Fix | Consequence | Proper Approach |
| --- | --- | --- |
| Adding `slf4j-simple` when Logback is already present | Two providers exist; runtime selection is inconsistent. | Keep only the provider the application intentionally chose. |
| Upgrading `slf4j-api` to 2.x while keeping a 1.7 binding | No compatible provider; may fall back to NOP. | Upgrade/select a matching 2.x provider and check release notes. |
| Installing `log4j-to-slf4j` alongside `log4j-slf4j2-impl` | Bridge loop. | Choose a single API → backend direction. |
| Removing all SLF4J dependencies | Code/libraries calling SLF4J fail with missing classes instead of resolving the conflict. | Keep the facade API; fix the provider/bridge. |
| Raising log level to ERROR to force logs to appear | Masks symptoms and loses INFO/DEBUG needed for investigation. | Identify which backend and config are actually active. |
| Leaving SLF4J NOP in production to silence warnings | Loses critical operational logs. | Configure a real provider suited to requirements. |
| Skipping checks on the runtime artifact | Works locally, fails in CI/containers. | Inspect the fat JAR/image/classpath and actual startup. |
| Excluding providers globally without understanding branches | May strip the backend from another app in a multi-module build. | Exclude at the specific transitive edge and verify each module. |
| Editing only `logback.xml` when runtime uses Log4j2 | Configuration continues to have no effect. | Choose the backend first, then use its matching config. |
| Assuming duplicate logs = definitely multiple providers | Misses additivity or duplicate log collection. | Check sinks, handlers/appenders, and collectors. |
| Ignoring warnings because “the app still runs” | May be using NOP or an unintended backend. | Verify the logger factory and output after deployment. |

## 13. Pre-Merge Checklist for Logging Dependencies

- [ ] Every logging API routes to the **chosen backend** via a clear path with no bidirectional loops.
- [ ] The runtime has **one compatible SLF4J 2.x provider** (if using SLF4J 2.x), or the corresponding binding for legacy setups.
- [ ] Versions of `slf4j-api`, backend, bridges, and Java baseline are compatible; no mixing of 1.7 bindings with 2.x providers.
- [ ] The Maven/Gradle dependency graph has no extra providers from transitive dependencies, starters, or test scope.
- [ ] Logback/JUL/Log4j2 is reading the intended configuration file; no unwanted provider/binding warnings remain.
- [ ] The final runtime (fat JAR, container, app server) includes the right implementation and service descriptors.
- [ ] `DEBUG`/`INFO`/`WARN`/`ERROR` events have appropriate levels without unexpected drops or duplicates.
- [ ] Exceptions are passed as `Throwable`, and stack traces/causes are not stripped by the pipeline.
- [ ] Logs do not contain unnecessary tokens, passwords, session cookies, or personal payloads; retention and access controls are in place.
- [ ] CI includes dependency version/tree checks and a startup test to catch returning conflicts.

## 14. Official Documentation to Consult When Upgrading

- [SLF4J FAQ – providers, versions, and compatibility](https://slf4j.org/faq.html).
- [SLF4J Manual – facade/provider model](https://slf4j.org/manual.html).
- [SLF4J Error Codes – missing or multiple provider warnings](https://www.slf4j.org/codes.html).
- [Apache Log4j 2 Components – bidirectional bridges and artifacts](https://logging.apache.org/log4j/2.x/components.html).

**Conclusion:** When you encounter a logging conflict, do not start by tweaking messages or raising log levels. **Trace the path API → provider/bridge → backend → appender/handler**, inspect the dependency tree and runtime classpath, keep exactly one provider for SLF4J, remove reverse adapters, and verify actual output. That approach prevents lost logs, loops, duplicate logs, and hard-to-reproduce deployment failures.