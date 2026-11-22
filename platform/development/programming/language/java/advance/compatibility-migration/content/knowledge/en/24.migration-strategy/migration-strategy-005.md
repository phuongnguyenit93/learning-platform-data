# Using adapters or separate implementation branches when supporting multiple JDKs

In a **Java Advance Compatibility Migration** project, the biggest challenge sometimes lies not in the code needing edits, but in **not being able to upgrade every consumer onto the same JDK simultaneously**. One batch job still runs Java 8; a new service has moved to Java 21; an internal library serves both; a partner application follows an upgrade schedule outside the development team's control. Replacing the entire source with newer APIs can cause older apps to stop compiling or fail when the JVM loads classes.

A frequently useful solution is creating a **shared contract** and isolating JDK-dependent parts behind **adapters** or **separate implementations**. One implementation path uses APIs compatible with the older JDK, while another leverages modern Java. For minor differences, a **multi-release JAR** can work; for broad divergence in frameworks and dependencies, multiple artifacts or independent release branches may be necessary.

The goal is not maintaining the legacy JDK indefinitely. This is a controlled transition strategy: supporting existing consumers, allowing newer applications to evolve, preserving data correctness, and planning the end of legacy support.

This lesson explains how to choose a pattern, design adapters at the source/binary/API levels, build Java 8 and Java 21 examples, configure Maven/Gradle, ServiceLoader, JPMS, and MR-JARs, control the dependency graph, test across multiple JVMs, and handle rollout, rollback, security backports, and sunsetting.

## 1. Define exact compatibility requirements

### 1.1. Which layers does "supporting multiple JDKs" cover?

| Layer | Question | Common failure |
|---|---|---|
| Source | Can older consumers still compile against the API? | Altered method signature or newer syntax used |
| Binary | Do previously compiled classes still link cleanly? | `NoSuchMethodError` or `NoClassDefFoundError` |
| Class-file | Can the JVM read the `.class` major version? | `UnsupportedClassVersionError` |
| Java platform API | Does the Java SE method exist on older JDKs? | Using `java.net.http` on Java 8 |
| Dependencies | Do transitive JARs require a newer Java version? | Major-65 library inside a Java 8 app |
| Behavior | Do results, concurrency, and timeouts keep the contract? | New adapter overloads a database |
| Data/protocol | Can older versions read data written by newer versions? | Unknown enums, JSON/schema incompatibility |
| Deployment | Do runtime images, native libraries, agents, and flags fit? | Wrong OS/architecture, agent crash |
| Vendor support | Are frameworks and JDKs in the support matrix? | EOL framework line |

An API adapter can hide Java API changes yet will not automatically resolve all other layers. State explicit requirements before choosing a pattern.

### 1.2. Build JDK differs from runtime JDK

A module compiled using JDK 21 can still emit Java 8 bytecode via `javac --release 8`. Still, if any dependency was compiled for Java 21, a Java 8 runtime cannot load it.

Intentional configuration example:

```text
Shared API:
  compiler: JDK 21
  --release: 8
  runtime floor: Java 8

Legacy adapter:
  compiler: JDK 21
  --release: 8
  runtime floor: Java 8

Modern adapter:
  compiler: JDK 21
  --release: 21
  runtime floor: Java 21
```

Java 8 class-file major version is **52**, Java 17 is **61**, and Java 21 is **65**. A Java 8 runtime rejects major 65 classes. Running tests on Java 21 does not replace executing the legacy variant on an actual Java 8 runtime.

### 1.3. Identify the consumer base and support window

Record:

- Which services/applications remain on each JDK.
- Their respective frameworks and build tools.
- Upgrade deadlines or support terms.
- Public APIs and protocols they consume.
- Deployed artifacts/versions.
- Who owns backports and security fixes.

If zero JDK 8 consumers remain, creating a new JDK 8 implementation only creates unnecessary maintenance obligations.

## 2. Choose the right level of separation

| Strategy | When to use | Advantages | Trade-offs |
|---|---|---|---|
| Single implementation targeting lower JDK | Newer APIs are not truly needed | Easy to maintain | Cannot directly exploit newer APIs |
| Adapter + implementation JARs | Shared API, distinct runtime implementations | Clear boundaries and independent tests | Extra artifacts/wiring |
| Adapter via `ServiceLoader` | Pluggable runtime implementations desired | Consumer has no compile dependency on implementation | Risk of bundling missing or duplicate providers |
| Multi-release JAR | Small differences under one public API | Single JAR; JVM selects release-specific classes | Complex builds, inspection, and shading |
| Two artifact lines | Major framework/dependency divergence | Explicit consumer selection | Larger release matrix |
| Two Git release branches | Widely diverging roadmaps/support contracts | Independent backports and release schedules | Divergence and high upkeep cost |
| Reflection/MethodHandles at one boundary | One small new API without splitting JARs | Fewer artifacts | Runtime failures, weaker type safety |
| Release modern variant only | Legacy consumers already sunset | Simplest model | Drops compatibility with older JDKs |

Do not start with two Git branches when the sole difference is one class calling a newer API. Conversely, do not force an MR-JAR to bridge two completely different framework lines.

## 3. Basic adapter architecture

### 3.1. Diagram

```text
                         +------------------+
                         |  Business Logic  |
                         |  shared JDK API  |
                         +---------+--------+
                                   |
                                   v
                          +----------------+
                          | TaskExecutor   |
                          | interface      |
                          | target Java 8  |
                          +--------+-------+
                             /           \
                            /             \
             +-------------+--+      +-----+------------+
             | JDK 8 adapter |      | JDK 21 adapter   |
             | platform pool |      | virtual threads  |
             +----------------+      +------------------+
                      |                       |
                      v                       v
                Java 8 app               Java 21 app
```

The shared API depends solely on types present in the lowest runtime. Adapters encapsulate JDK-specific code without exposing implementation types in the public interface.

### 3.2. Shared interface usable on Java 8

```java
package com.example.tasks.api;

import java.util.concurrent.Callable;
import java.util.concurrent.Future;

public interface TaskExecutor extends AutoCloseable {
    <T> Future<T> submit(Callable<T> task);

    @Override
    void close();
}
```

`Callable`, `Future`, and `AutoCloseable` all exist in Java 8. This interface makes no mention of `Thread.Builder` or `Executors.newVirtualThreadPerTaskExecutor()`.

An **unsuitable** pattern while Java 8 support is still needed:

```java
// Wrong: public contract references an API present only in newer Java.
public interface TaskExecutor {
    Thread.Builder.OfVirtual newVirtualTask();
}
```

You cannot preserve compatibility merely by "not calling that method" on Java 8. Referencing that type in the API signature already breaks the baseline.

### 3.3. Contracts must specify behavior too

Beyond signatures, define:

```text
submit(task):
  - task is non-null
  - Future returns the task's result/exception
  - caller can cancel or wait with timeout
  - no specific scheduling order is guaranteed

close():
  - initiates shutdown
  - accepts no new tasks
  - does not automatically wait for all tasks to complete

operational:
  - bound downstream resources independently of the thread model
  - do not lose tasks during shutdown
```

If the legacy adapter uses 8 threads while the modern adapter spawns many virtual threads, runtime behavior and downstream pressure can differ despite an identical interface.

## 4. Java 8 implementation

### 4.1. Using a traditional ExecutorService

```java
package com.example.tasks.jdk8;

import com.example.tasks.api.TaskExecutor;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Jdk8TaskExecutor implements TaskExecutor {
    private final ExecutorService delegate;

    public Jdk8TaskExecutor(int threads) {
        if (threads <= 0) {
            throw new IllegalArgumentException(
                "threads must be positive");
        }
        this.delegate = Executors.newFixedThreadPool(threads);
    }

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        Objects.requireNonNull(task, "task");
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
    }
}
```

This code relies only on features available in Java 8. It needs no knowledge of how the modern adapter works.

### 4.2. Limitations of fixed thread pools

`Executors.newFixedThreadPool` bounds worker threads yet allows large wait queues. In production systems, consider:

- Queue capacity and rejection policies.
- Backpressure when producers outpace consumers.
- Task timeouts and cancellation.
- Metrics for active threads, queue depth, and wait times.
- Graceful shutdown and handling unfinished tasks.

If the business contract requires backpressure, design explicit abstractions or policies rather than treating a default thread pool as sufficient.

### 4.3. Test on a real Java 8 runtime

Compiling targeting Java 8 does not prove runtime behavior. Configure a job to:

```text
Build shared API with --release 8
Build legacy adapter with --release 8
Assemble full legacy dependency graph
Run contract + integration tests on Java 8 JVM
```

Tests must run against the final artifact and real runtime dependency versions, not merely compile test sources on a newer JDK.

## 5. Java 21 implementation

### 5.1. Using virtual threads

Java 21 provides `Executors.newVirtualThreadPerTaskExecutor()`:

```java
package com.example.tasks.jdk21;

import com.example.tasks.api.TaskExecutor;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Jdk21TaskExecutor implements TaskExecutor {
    private final ExecutorService delegate =
        Executors.newVirtualThreadPerTaskExecutor();

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        Objects.requireNonNull(task, "task");
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
    }
}
```

This implementation compiles targeting Java 21. The shared interface remains Java 8, keeping application code coupled to the abstraction rather than thread creation mechanics.

### 5.2. Virtual threads do not mean unlimited resources

Virtual threads help I/O-blocking workloads, yet they do not add CPU cores, database connections, or API quotas.

For example, a semaphore/bulkhead outside the adapter may still be required:

```text
Incoming jobs: 10,000
Virtual threads: many
Database pool: 20 connections
=> concurrent DB call limits must still be managed
```

If an earlier Java 8 deployment incidentally capped concurrency via 8 threads, switching to virtual-thread-per-task can overwhelm downstream systems. Define capacity limits, timeouts, and rate limits explicitly in contracts or operations.

### 5.3. When Java 17 is also a target

If Java 17 consumers need the modern API without finalized virtual threads, you can:

- Run the legacy implementation on Java 17.
- Add a dedicated Java 17 implementation when concrete benefits exist.
- Keep the Java 21 adapter for Java 21 and later.
- Raise the overall support floor once consumers are ready.

There is no need for a separate adapter per JDK release. Create variants only when real capabilities and needs justify them.

## 6. Selecting an implementation at build or deploy time

### 6.1. Explicit dependency injection

A legacy app can instantiate:

```java
TaskExecutor executor = new Jdk8TaskExecutor(8);
```

A Java 21 app:

```java
TaskExecutor executor = new Jdk21TaskExecutor();
```

These belong to **separate** application configurations or bootstrap modules; never place modern code inside a source unit compiled with `--release 8`.

Advantage: zero runtime guessing or reflection, making the active artifact obvious. Trade-off: requires separate wiring configuration.

### 6.2. Framework DI

With Spring, CDI, or another DI container, common options include:

- Each application profile pulls in only one provider artifact.
- Bean configuration binds to the published runtime/deployment.
- The application module determines interface bindings.
- Feature flags select a feature only when both implementations are built compatibly.
- Startup tests assert "exactly one bean/provider".

A newer framework version requiring Java 17 cannot be forced to run on Java 8 merely by wrapping beans inside an adapter. Frameworks and transitive libraries still govern the JDK floor.

### 6.3. Never implicitly select based on the build tool's JDK

If CI runs Maven or Gradle on JDK 21 to build a Java 8 artifact, a rule saying "if build JDK >= 21 pick the modern adapter" selects the **wrong** variant.

Selection must follow the release target/consumer contract, never whichever JDK happens to sit on a developer's PATH.

## 7. ServiceLoader and SPI

### 7.1. When to use ServiceLoader

`java.util.ServiceLoader` has existed since early Java and works well when the app compiles only against the shared interface while the runtime supplies the implementation.

For classpath providers, a Java 8-compatible JAR typically declares the resource:

```text
META-INF/services/com.example.tasks.api.TaskExecutor
```

The resource contents list the fully qualified class name of a provider offering a public no-arg constructor.

### 7.2. Legacy provider fitting SPI

Because `Jdk8TaskExecutor` above only has a constructor taking `threads`, create a wrapper:

```java
package com.example.tasks.jdk8;

import com.example.tasks.api.TaskExecutor;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;

public final class Jdk8TaskExecutorProvider
        implements TaskExecutor {

    private final Jdk8TaskExecutor delegate =
        new Jdk8TaskExecutor(8);

    public Jdk8TaskExecutorProvider() {
    }

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
```

Service descriptor in the legacy JAR:

```text
com.example.tasks.jdk8.Jdk8TaskExecutorProvider
```

The modern JAR can register a modern provider against the same interface.

### 7.3. Loader running on Java 8

```java
package com.example.tasks.api;

import java.util.Iterator;
import java.util.ServiceLoader;

public final class TaskExecutors {
    private TaskExecutors() {
    }

    public static TaskExecutor loadExactlyOne() {
        Iterator<TaskExecutor> providers =
            ServiceLoader.load(TaskExecutor.class).iterator();

        if (!providers.hasNext()) {
            throw new IllegalStateException(
                "No TaskExecutor provider available");
        }

        TaskExecutor executor = providers.next();

        if (providers.hasNext()) {
            throw new IllegalStateException(
                "Multiple TaskExecutor providers found");
        }

        return executor;
    }
}
```

At runtime, ship **only one matching provider**:

```text
Java 8 distribution:
  task-api.jar
  task-adapter-jdk8.jar

Java 21 distribution:
  task-api.jar
  task-adapter-jdk21.jar
```

`ServiceLoader` does not automatically pick the JDK-compatible implementation by class-file version. Bundling both JARs can leave two providers visible or fail trying to load an incompatible modern provider on an older JDK.

### 7.4. Take care when building fat JARs

Shading can:

- Drop `META-INF/services`.
- Merge both provider descriptors into a single file.
- Relocate implementation classes without updating descriptors.
- Bundle a modern JAR into a legacy package.

Always run SPI tests against **the final packaged artifact**, not solely the IDE classpath.

## 8. Maven multi-module design

### 8.1. Structure

```text
multi-jdk-library/
  pom.xml
  task-api/
    pom.xml
  task-adapter-jdk8/
    pom.xml
  task-adapter-jdk21/
    pom.xml
  app-legacy/
    pom.xml
  app-modern/
    pom.xml
```

Dependency relationships:

```text
task-api
  |
  +-- task-adapter-jdk8 ----> app-legacy
  |
  +-- task-adapter-jdk21 ---> app-modern
```

The parent POM manages plugin versions, dependency versions, and baselines; child modules specify their individual compile releases.

### 8.2. Shared API and legacy adapter

Example in the corresponding two POMs:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

Pin `maven-compiler-plugin` and run it with a toolchain/compiler supporting `--release`. Java 8 compilers lack `--release`; a common pattern compiles with JDK 21 targeting release 8, then executes runtime tests on actual Java 8.

### 8.3. Modern adapter

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This implementation depends on `task-api` plus Java-21-capable dependencies. Never place the modern adapter into the legacy app's dependency graph.

### 8.4. Legacy application dependencies example

```xml
<dependencies>
    <dependency>
        <groupId>com.example.tasks</groupId>
        <artifactId>task-api</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>com.example.tasks</groupId>
        <artifactId>task-adapter-jdk8</artifactId>
        <version>1.0.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

This example assumes SPI usage where only the API is needed at compile time. If bootstrap code instantiates `Jdk8TaskExecutor` directly, the implementation dependency must sit in compile scope.

### 8.5. Do not confuse a passing Maven reactor with compatibility

A green reactor build proves only that each module compiled under its configured settings. It does not prove:

- The legacy graph excludes Java 21 JARs.
- Application runtime loads the intended provider.
- The app runs on Java 8.
- Frameworks, JDBC drivers, and agents do not demand a higher JDK.

Verify `dependency:tree`, effective POMs, and runtime tests per distribution.

### 8.6. Explicit profiles outperform build-JDK activation

When using Maven profiles, invoke explicit profile flags:

```text
-Plegacy-distribution
-Pmodern-distribution
```

Never let a profile auto-enable the modern adapter merely because Maven runs on JDK 21 when building artifacts for Java 8 users.

## 9. Gradle multi-project design

### 9.1. Declaring projects

```groovy
rootProject.name = 'multi-jdk-library'

include 'task-api'
include 'task-adapter-jdk8'
include 'task-adapter-jdk21'
include 'app-legacy'
include 'app-modern'
```

### 9.2. Shared API targeting Java 8

`task-api/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
```

The JDK 21 compiler emits Java 8 class-file versions while restricting Java SE APIs used in source accordingly.

### 9.3. Modern adapter targeting Java 21

`task-adapter-jdk21/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}

dependencies {
    implementation project(':task-api')
}
```

The legacy adapter sets `options.release = 8` and depends on `:task-api`.

### 9.4. Apps choosing runtime dependencies

`app-legacy/build.gradle`:

```groovy
dependencies {
    implementation project(':task-api')
    runtimeOnly project(':task-adapter-jdk8')
}
```

`app-modern/build.gradle`:

```groovy
dependencies {
    implementation project(':task-api')
    runtimeOnly project(':task-adapter-jdk21')
}
```

This fits applications using `ServiceLoader`. If calling the implementation class directly, declare it on the compile classpath appropriately.

### 9.5. Convention plugins and centralized configuration

In large monorepos, rather than scattering `options.release` everywhere, enforce policies via convention plugins:

```text
shared API modules  -> release 8
legacy adapters     -> release 8
modern adapters     -> release 21
legacy apps         -> release 8
modern apps         -> release 21
```

Still permit explicit documented overrides. Building a module with JDK 21 does not automatically authorize emitting Java 21 bytecode.

### 9.6. Variant metadata

Gradle Module Metadata can express target JVMs and resolve variants via attributes. However, Maven consumers do not automatically understand that metadata; therefore, libraries serving mixed build tools are often simpler to maintain with distinct artifact coordinates and explicit support matrices.

Never assume variant resolution guarantees every JAR inside a fat distribution has compatible major versions.

## 10. Multi-release JAR: one artifact holding JDK-specific implementations

### 10.1. Layout

Java supports multi-release JARs from Java 9 onward. One JAR holds base classes alongside release-specific overrides:

```text
task-library.jar
  META-INF/MANIFEST.MF
  com/example/tasks/TaskEngine.class
  com/example/tasks/EngineImpl.class
  META-INF/versions/21/com/example/tasks/EngineImpl.class
```

The manifest must declare:

```text
Multi-Release: true
```

On Java 8, the JVM loads base classes. On Java 21, MR-JAR-aware classloading selects the versioned class under `META-INF/versions/21`.

### 10.2. Advantages

- Single coordinates/artifact to distribute.
- Base API preserves the older runtime floor.
- Newer JDKs pick optimized implementations without consumer dependency edits.
- Effective when differences sit inside a few internal classes rather than an entire framework.

### 10.3. Limitations

An MR-JAR **does not**:

- Select distinct Maven/Gradle dependencies at runtime automatically.
- Make a Java 21 JAR runnable on Java 8.
- Resolve native ABI, OS/architecture, or application-server differences.
- Allow diverging public APIs between variants cleanly.
- Guarantee every shading, bytecode-scanning, obfuscation, or classpath tool handles versioned entries.

If the modern adapter pulls in a suite of libraries that dropped Java 8, shipping two separate artifacts is usually cleaner.

### 10.4. Build rules

- Compile base classes for the lowest runtime floor.
- Compile versioned classes matching each `versions/N` folder target.
- Keep public API compatibility between base and versioned classes.
- Ensure valid manifest entries and JAR layout.
- Confirm a Java 8 runtime loads base classes cleanly.
- Confirm a Java 21 runtime actually selects the newer variant.
- Verify the dependency closure remains valid per runtime.
- Configure CI class-major scanners to understand MR-JARs.

A naive scanner checking "every `.class` in the ZIP <= major 52" rejects valid Java 21 MR-JAR entries. Conversely, inspecting only root classes can miss badly compiled versioned classes.

### 10.5. Testing MR-JARs

```text
Java 8:
  uses base implementation
  no reference to Java 21 API
  behavior contract passes

Java 17:
  uses base or highest eligible <= 17 variant
  behavior contract passes

Java 21:
  uses Java 21 versioned implementation
  behavior contract passes
```

Run `jar --list`, `javap`, and `jdeps --multi-release` where helpful, yet base conclusions on **the published JAR running on real target JVMs**.

## 11. When to maintain two artifact lines

### 11.1. Major dependency divergence

Suppose:

```text
shared-api:
  Java 8 baseline

legacy-adapter:
  Java 8
  older HTTP library
  framework line A

modern-adapter:
  Java 21
  java.net.http
  framework line B
```

If framework line B demands Java 17/21, pulling it onto a legacy app's classpath cannot be hidden by an adapter. Each distribution needs its own dependency closure.

### 11.2. Explicit release coordinates

Example:

```text
com.example:task-api:1.4.0
com.example:task-adapter-jdk8:1.4.0
com.example:task-adapter-jdk21:1.4.0
```

Sharing a version family simplifies tracking without proving compatibility automatically. If publishing versions independently, maintain an explicit matrix of compatible API/adapter pairs.

### 11.3. Separate artifactId vs. classifier

| Approach | Strength | Risk |
|---|---|---|
| Separate artifactId | Clear graph, independent transitive dependencies | More coordinates to publish |
| Separate classifier | Single artifact family | Classifier dependency metadata harder to manage |
| Gradle variants | Attribute-based resolution in supported setups | Maven/older consumers may not understand |
| MR-JAR | Single file | Complex build/runtime verification |

When two implementations carry distinct transitive dependencies, separate `artifactId`s are generally easier to audit.

### 11.4. Document minimum JDKs clearly

Example template:

```text
task-adapter-jdk8:
  minimum Java: 8
  tested Java: 8, 17, 21 (record only after testing)

task-adapter-jdk21:
  minimum Java: 21
  tested Java: 21, 25 (record only after testing)
```

Artifact names never substitute for documented runtime support. Never label future JDK releases as "supported" without test evidence.

## 12. When are two Git branches needed?

### 12.1. Splitting implementations does not mandate splitting repositories

If two adapters differ by only a handful of classes, keeping them in one repository/main branch keeps code reviews, API contracts, and security fixes consistent.

Separate release branches fit when:

- Major framework lines diverge deeply.
- Public APIs or build tooling split sharply.
- Legacy consumers require multi-year maintenance without new features.
- Release/operations teams have distinct owners and SLAs.
- Changes cannot cleanly share modules/source sets.

### 12.2. Branch model

```text
main
  -> Java 21 modern development

release/java8
  -> critical fixes + security backports

release/java17 (if needed)
  -> maintenance for Java 17 consumers
```

Never spin up a branch per JDK major without active consumers or business requirements.

### 12.3. Backport intent rather than blind cherry-picks

Suppose modern uses the Java 21 HTTP Client while legacy uses `HttpURLConnection`. A bug fix for retry/timeout policy must port **business semantics** across different APIs:

```text
Modern fix:
  use HTTP client timeout API

Legacy fix:
  configure connect/read timeouts on HttpURLConnection

Shared contract:
  request fails after documented deadline
```

Do not try to force identical source code when runtime APIs differ.

### 12.4. Every branch needs exit criteria

A branch policy should specify:

- Branch owner.
- Minimum JDK and framework line.
- Consumer list.
- Eligible security fixes.
- Critical bug-fix criteria.
- Maintenance end date.
- CI matrix and artifact release flow.
- Consumer migration steps onto the modern line.
- Exit criteria and archival rules.

Without these, a "transitional branch" tends to linger indefinitely without adequate maintenance staffing.

## 13. Feature detection instead of guessing versions

### 13.1. Why version checks mislead

Writing in Java 8 source:

```java
if (javaVersion >= 21) {
    // call Java 21 API directly
}
```

does not make the code Java 8-compatible: the compiler still compiles calls missing on Java 8, and JVM class loading/verification may resolve those newer types.

Running on a particular JDK version also does not guarantee frameworks, plugins, or custom runtime images expose the expected capability.

### 13.2. Reflection suits only narrow boundaries

You can probe for a method using Java 8 reflection:

```java
import java.lang.reflect.Method;
import java.util.concurrent.Executors;

public final class RuntimeCapabilities {
    private RuntimeCapabilities() {
    }

    public static boolean hasVirtualThreadExecutor() {
        try {
            Method method = Executors.class.getMethod(
                "newVirtualThreadPerTaskExecutor");
            return method != null;
        } catch (NoSuchMethodException ex) {
            return false;
        }
    }
}
```

This merely detects capability; it does not prove suitability for workload or policy. When invoking newer APIs via reflection, handle invocation exceptions and resource cleanup while keeping Java 21 types out of public signatures.

### 13.3. Never swallow Throwable and silently fall back

If `Class.forName` loads a modern provider, failures may stem from:

- Missing implementation JAR.
- JVM too old for bytecode version.
- Missing transitive dependency.
- Blocked JPMS module access.
- Error in static initializer or constructor.
- Misconfigured provider.

Catching `Throwable` and falling back silently can mask critical production breakages. Distinguish "feature absent" from "broken deployment" and log sufficient sanitized diagnostics.

### 13.4. Runtime.version does not exist on Java 8

`Runtime.version()` arrived in Java 9. Shared Java 8 source must not call it directly. Where version inspection is genuinely necessary, use compatible APIs and test format parsing; however, build/deploy-time artifact selection is usually cleaner.

## 14. JPMS, module descriptors, and classloading

### 14.1. JPMS APIs on newer runtimes

A named module can declare:

```java
module com.example.tasks.api {
    exports com.example.tasks.api;
    uses com.example.tasks.api.TaskExecutor;
}
```

Provider module:

```java
module com.example.tasks.jdk21 {
    requires com.example.tasks.api;

    provides com.example.tasks.api.TaskExecutor
        with com.example.tasks.jdk21.Jdk21TaskExecutor;
}
```

This illustrates JPMS service declarations. However, `module-info.java` cannot compile with Java 8 targets; when the shared API targets Java 8, plan intentionally around classpath SPI, versioned MR-JAR descriptors, or module-aware artifacts.

### 14.2. Classpath SPI differs from module-path SPI

On the classpath, providers register via `META-INF/services/...`. On the module path, `module-info.java` uses `provides`/`uses`. Never assume migrating packaging from classpath to module path leaves service discovery behavior identical.

### 14.3. Split packages and duplicate classes

If legacy and modern providers reuse identical packages/class names and appear on the module path together, module/package conflicts arise. If a plugin bundles its own copy of the shared API under a separate classloader, provider instances may fail casting to the host's interface despite identical class names.

Separate packages cleanly:

```text
com.example.tasks.api
com.example.tasks.jdk8
com.example.tasks.jdk21
```

Place shared APIs in the proper parent classloader/module layer and avoid bundling duplicate copies inside plugins.

## 15. Dependency closure determines the minimum JDK

### 15.1. A major-52 implementation can still depend on major 61

```text
legacy-adapter.jar  major 52
        |
        +--> metrics-library.jar major 61
```

Java 8 fails loading Java 17 dependency classes even if the adapter itself targets release 8.

Inspect:

- Direct dependencies.
- Transitive dependencies.
- Fat/nested JARs.
- Java agents.
- Annotation processors and separate test dependencies.
- Native library requirements.
- Framework/ORM/HTTP/serialization baselines.

### 15.2. BOMs and dependency locking do not rewrite bytecode

Gradle version catalogs, BOMs/platforms, lockfiles, and Maven `dependencyManagement` organize versions. None make a Java 21 JAR run on Java 8.

When a modern adapter pulls a Java-21-only dependency, exclude it from legacy deployment graphs. Updating a shared BOM requires validating legacy branches too, not solely modern targets.

### 15.3. Inspect actual artifacts

```shell
javap -verbose -classpath task-api.jar \
    com.example.tasks.api.TaskExecutor
```

Checking one class as major 52 is encouraging yet insufficient. Scan every class in JARs and nested dependencies; for MR-JARs, inspect `META-INF/versions/N` aware of version folders.

Then execute tests on the minimum supported JVM to expose incompatible Java APIs, modules, reflection, and runtime behavior.

## 16. Second example: HTTP adapter

### 16.1. Splitting the HTTP client API

Java 8 lacks `java.net.http.HttpClient`, whereas Java 11+ includes it. A shared interface uses only Java 8 types:

```java
package com.example.http.api;

import java.io.IOException;

public interface TextFetcher {
    String fetch(String url) throws IOException;
}
```

One implementation uses `HttpURLConnection`; the modern one uses `java.net.http.HttpClient`.

### 16.2. Legacy implementation

```java
package com.example.http.jdk8;

import com.example.http.api.TextFetcher;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class Jdk8Fetcher implements TextFetcher {
    @Override
    public String fetch(String address) throws IOException {
        HttpURLConnection c =
            (HttpURLConnection) new URL(address).openConnection();

        c.setConnectTimeout(5000);
        c.setReadTimeout(5000);

        try {
            if (c.getResponseCode() != 200) {
                throw new IOException(
                    "Unexpected HTTP response: " +
                    c.getResponseCode());
            }

            StringBuilder result = new StringBuilder();

            try (BufferedReader reader =
                     new BufferedReader(
                         new InputStreamReader(
                             c.getInputStream(),
                             StandardCharsets.UTF_8))) {

                String line;
                while ((line = reader.readLine()) != null) {
                    result.append(line).append('\n');
                }
            }

            return result.toString();
        } finally {
            c.disconnect();
        }
    }
}
```

This snippet illustrates JDK boundaries rather than a production-hardened HTTP client: real services must manage redirects, response size limits, charsets, proxies, TLS, SSRF defenses, and status policies. User-supplied URLs need allowlisting and internal network restrictions.

### 16.3. Modern implementation

```java
package com.example.http.jdk21;

import com.example.http.api.TextFetcher;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class Jdk21Fetcher implements TextFetcher {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Override
    public String fetch(String address) throws IOException {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(address))
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        try {
            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            if (response.statusCode() != 200) {
                throw new IOException(
                    "Unexpected HTTP response: " +
                    response.statusCode());
            }

            return response.body();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException(
                "Interrupted during HTTP request", ex);
        }
    }
}
```

`java.net.http` arrived in Java 11; placing this implementation in a Java 21 module reflects a release choice here rather than the API requiring Java 21.

### 16.4. Contract tests across both HTTP adapters

Compare:

- HTTP status handling (200, 201, 204, 4xx/5xx).
- Redirect policies.
- Timeouts and retries.
- Charsets and newlines.
- Proxy handling.
- TLS truststores and hostname verification.
- Error messages and exception contracts.
- Resource cleanup.
- Response-size bounds.
- Cancellation and thread interruption.

Testing only "fetching a single happy-path page" allows behavioral differences to surface after deployment.

## 17. Testing API, binary, and behavioral compatibility

### 17.1. Shared contract tests

A shared helper can run against both implementation modules:

```java
import com.example.tasks.api.TaskExecutor;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class TaskExecutorContract {
    public static void verify(TaskExecutor executor)
            throws Exception {

        try {
            Future<Integer> result =
                executor.submit(() -> 6 * 7);

            int actual = result.get(5, TimeUnit.SECONDS);

            if (actual != 42) {
                throw new AssertionError(
                    "Expected 42 but got " + actual);
            }
        } finally {
            executor.close();
        }
    }
}
```

Production test suites should also cover exception propagation, cancellation, timeouts, shutdown, and concurrency behavior.

### 17.2. Source compatibility does not imply binary compatibility

Changing a public method:

```java
// V1
byte[] encode(String text);

// V2
java.nio.ByteBuffer encode(CharSequence text);
```

breaks beyond JDK targets: it alters the method descriptor. Consumers already compiled against V1 can throw `NoSuchMethodError` against V2 at runtime even when both use Java 8 bytecode.

When guaranteeing binary compatibility, retain the prior method or release a breaking API version with clear migration guidance. A JDK adapter cannot heal a deleted public API.

### 17.3. Never execute tests solely on the newer JVM

Misleading test coverage example:

```text
shared API target 8
legacy adapter target 8
all tests executed on Java 21
=> Java 8 compatibility not proven
```

To verify legacy support, run the app or contract suite on an actual Java 8 runtime with the actual legacy dependency closure.

### 17.4. Binary comparison tools

Tools like `japicmp`, `Revapi`, or an organization-standard API compatibility checker help detect public API/binary changes, yet must still be paired with runtime integration and data protocol tests.

## 18. CI and release matrix

### 18.1. Suggested matrix

| Component | Compiler JDK | Target release | Test JVM |
|---|---:|---:|---|
| Shared API | 21 | 8 | 8, 21 |
| Legacy adapter | 21 | 8 | 8 |
| Modern adapter | 21 | 21 | 21 |
| Legacy app | Per config | 8 | 8 |
| Modern app | Per config | 21 | 21 |
| Legacy release bundle | Per target | 8 closure | Java 8 production-like |
| Modern release bundle | Per target | 21 closure | Java 21 production-like |

Include only JDK releases and OS/architectures the product genuinely supports. If Java 11 or 17 is also supported, add explicit rows with owners and dedicated test workloads.

### 18.2. Reference pipeline

```text
Checkout immutable commit
        |
        v
Pin Maven/Gradle + compiler JDK
        |
        v
Build shared API
        |
        +--> Build legacy adapter
        |         |
        |         v
        |    Resolve legacy dependencies
        |         |
        |         v
        |    Package legacy application
        |         |
        |         v
        |    Bytecode scan + Java 8 tests
        |
        +--> Build modern adapter
                  |
                  v
             Resolve modern dependencies
                  |
                  v
             Package modern application
                  |
                  v
             Bytecode scan + Java 21 tests
        |
        v
Review API/binary compatibility
        |
        v
Integration / protocol / security tests
        |
        v
Immutable artifacts + SBOM + provenance
```

### 18.3. Inspect compiled artifacts

Check class-file major versions of **every class the JVM can load**, not just main classes. For JARs carrying `META-INF/versions`, scanners must be MR-JAR-aware. For executable fat JARs containing nested dependencies, inspect inner JARs as well.

Never check only the compile/test classpath if runtime deployment constructs a different classpath.

### 18.4. Verify packaging and providers

Confirm:

- Legacy distribution contains only the legacy provider.
- Modern distribution contains only the modern provider.
- `ServiceLoader` finds exactly one provider.
- JPMS services resolve cleanly when using module path.
- No duplicate common API classes span classloaders.
- Startup and uncommon runtime code paths both run cleanly.

## 19. Rolling deployment and data compatibility

### 19.1. JDK adapters do not ensure protocol compatibility

Two services on different JDKs often communicate via JSON, Avro, Protobuf, or shared databases. If the modern service emits an enum value unknown to legacy consumers, failures occur even when both run matching JVM adapters.

Manage data compatibility separately from bytecode compatibility.

### 19.2. Expand then contract

Sample plan:

```text
1. Update legacy consumers to tolerate new schemas or unknown values.
2. Deploy modern producers without emitting modern-only data yet.
3. Enable feature flags incrementally under monitoring.
4. Track schema errors, unknown enums, retries, and dead letters.
5. Once zero legacy consumers remain, drop legacy fallbacks.
```

If legacy consumers cannot be updated, modern producers may need to continue emitting legacy-compatible formats throughout the support window.

### 19.3. Rollback plans must include data state

Rolling a Java 21 app back to Java 8 does not undo database migrations or emitted messages. Determine:

- Can older versions read newly written data?
- Should dual-readers or versioned DTOs remain active?
- Can state downgrade safely without data loss?
- How much message backlog/replay remains?
- When can legacy writers safely retire?

Never promise "rollback is just redeploying the JAR" if the upgrade modified persisted schemas or external contracts.

## 20. Observability and performance per variant

### 20.1. Semantically equivalent metrics

Legacy adapters might expose active thread counts/queue depths; modern adapters may monitor concurrent tasks, virtual-thread metrics, and downstream pool saturation. Never compare raw "thread count" metrics across variants as if both use the same concurrency model.

Contract-level metrics should cover:

- Throughput and latency percentiles.
- Task queue/wait duration or active task count.
- Success, error, and cancellation rates.
- Timeout rates.
- Downstream calls and connection-pool utilization.
- Memory/CPU usage and GC behavior.
- Graceful shutdown duration.

### 20.2. APM agents also need support matrices

Bytecode-instrumenting agents support specific JDK/class-file versions. If the modern adapter runs Java 21 under an outdated APM agent, startup may crash or tracing may silently drop.

Test on deployment artifacts carrying production-matching agents and flags. Never count "app boots with agent disabled" as compatibility proof.

### 20.3. Canary and feature rollouts

When a modern adapter changes threading or HTTP mechanics, canary it against a narrow traffic slice first; monitor latency, downstream errors, and resource consumption. Keep matching artifact lockfiles and schema compatibility ready for rollback.

## 21. Security and supply chain across variants

### 21.1. Two dependency graphs, two risk profiles

The legacy variant may rely on older library lines than the modern variant. Each graph requires:

- Dependency inventory/SBOM.
- Security vulnerability scanning.
- License reviews.
- Artifact integrity checks.
- Runtime JDK security update policies.
- Assigned remediation ownership.
- Time-boxed risk exceptions when upgrades are blocked.

Never equate an immutable lockfile with security. Locks merely make changes deliberate.

### 21.2. Immutable artifacts

Publish artifacts with distinct versions and checksums. Never overwrite existing coordinates with new bytes; build caches and repository proxies can serve mismatched contents under identical versions.

### 21.3. Reassess legacy support horizons

If Java 8/legacy frameworks exit vendor support or accumulate unfixable CVEs, continuing to maintain an adapter may become unacceptable. At that point, schedule consumer migrations, apply time-bounded isolation/mitigations, and set a clear sunset milestone.

## 22. Troubleshooting

### 22.1. `UnsupportedClassVersionError` on Java 8

**Cause:** a modern adapter or transitive major-65 JAR leaked into the legacy graph.

**Resolution:** identify the offending JAR, check class majors, dependency trees, runtime classpath, and packaging. Select the legacy artifact; do not merely flip `--release 8` on the app module.

### 22.2. `NoSuchMethodError` despite both targeting Java 8

**Cause:** binary API mismatch in a shared library or dependency.

**Resolution:** compare compiled vs. runtime API versions; run binary compatibility checks, preserve prior signatures, or publish an explicit breaking release.

### 22.3. `ServiceConfigurationError`

**Cause:** missing provider class, missing no-arg constructor, wrong SPI descriptor, or incomplete module-path/service declaration.

**Resolution:** inspect the final artifact, read `META-INF/services`, and verify class/module names plus runtime dependencies.

### 22.4. Duplicate providers found

**Cause:** both legacy and modern JARs were bundled together.

**Resolution:** include only one provider per distribution, or enforce a tested explicit selection policy.

### 22.5. MR-JAR fails to load the newer class

**Cause:** missing `Multi-Release: true`, misplaced `META-INF/versions/21` entries, or non-MR-aware classloaders/tooling.

**Resolution:** verify manifest, archive layout, and test execution of the final JAR on the target JVM.

### 22.6. MR-JAR rejected by scanner

**Cause:** scanner enforces one maximum class-file major without understanding versioned folders.

**Resolution:** configure MR-aware validation per base and versioned entry sets.

### 22.7. New adapter breaks HTTP/DB behavior

**Cause:** changed behavioral semantics such as redirects, timeouts, TLS, concurrency, or connection pooling.

**Resolution:** expand contract/integration tests, bound downstream resources, and canary with metrics; never equate interface compilation with compatibility.

### 22.8. Java 8 app passes in IDE yet fails in production

**Cause:** IDE runs a newer JDK while production executes Java 8 with different dependencies/agents.

**Resolution:** run CI on the lowest supported JDK in production-like containers/VMs, checking actual Java launchers and artifacts.

### 22.9. Maven profile picks the wrong adapter

**Cause:** profile activates based on Maven's runtime JDK rather than deployment target.

**Resolution:** use explicit release profiles/coordinates and inspect distribution contents.

### 22.10. Stagnant legacy branch misses security patches

**Cause:** missing ownership, backport workflow, and sunset date.

**Resolution:** restore maintenance governance or retire support on a communicated schedule; never assume untouched legacy branches stay safe.

## 23. Step-by-step migration workflow

### Step 1: Build an inventory

Document current JDKs, target JDKs, consumers/versions, frameworks, APIs, protocols, native dependencies, and support deadlines.

### Step 2: Define adapter boundaries

Confine JDK-specific APIs strictly inside implementation modules. Compile and run the shared API against the lowest supported JDK floor.

### Step 3: Write contract tests first

Lock down behavior expectations for inputs/outputs, exceptions, timeouts, cancellations, data semantics, and resource lifecycles.

### Step 4: Extract the existing implementation

Move existing code into the legacy adapter without altering semantics; validate on the older JVM first.

### Step 5: Add the modern implementation

Adopt newer JDK capabilities where clear value exists. Never duplicate JDK-independent business logic.

### Step 6: Formalize provider selection

Choose DI, SPI, distinct artifact coordinates, or MR-JARs. Guarantee each distribution resolves predictably.

### Step 7: Block newer dependencies from legacy graphs

Inspect class-file majors and JDK baselines across all transitive dependencies, plugins, and agents.

### Step 8: Build the CI matrix

Compile, test, and package both variants. Run legacy suites on Java 8 and modern suites on Java 21, adding OS/architecture coverage as needed.

### Step 9: Canary and rollback

Monitor runtime performance/behavior, retain prior immutable artifacts, and verify bidirectional data/protocol compatibility wherever rolling upgrades occur.

### Step 10: Sunset

Confirm every consumer has upgraded, end backports per policy, and retire end-of-life adapters and branches.

## 24. Practice exercises

### Exercise 1: Defining boundaries

A Java 8 library exposes a public API returning `java.net.http.HttpResponse` after a team upgrades to JDK 21. Explain why preserving that signature while swapping implementations still breaks Java 8, then design a shared DTO or interface using Java 8 types.

### Exercise 2: Two task execution implementations

Build `task-api`, `task-adapter-jdk8`, and `task-adapter-jdk21` following the example. Compile with JDK 21 using `--release 8` and `--release 21` respectively. Execute contract tests on actual Java 8 and Java 21 runtimes.

### Exercise 3: ServiceLoader

Package the legacy provider, then attempt bundling the modern provider into the same distribution. Observe `loadExactlyOne()`, and propose CI artifact checks preventing duplicate providers.

### Exercise 4: Multi-release JAR

Design an MR-JAR with a Java 8 base and Java 21 override. Specify compiler targets, manifest headers, archive layout, API contracts, tests on Java 8/17/21, and criteria for splitting into two separate artifacts instead.

### Exercise 5: Release branches

A partner needs 12 more months on Java 8 while internal services move to Java 21. Propose support horizons, backport rules, dependency security workflows, release metadata, and sunset criteria.

### Exercise 6: Binary mismatch

A consumer compiles against `MessageCodec.encode(String): byte[]`, while a newer library changes the method to `encode(CharSequence): ByteBuffer`. Identify the source/binary break, explain why a JDK adapter alone does not fix it, and outline an API migration plan.

## 25. Pre-release checklist

### Architecture

- [ ] Documented consumer inventory and minimum supported JDKs.
- [ ] Shared API avoids types/syntax exclusive to newer JDKs.
- [ ] Shared contract tests run against every adapter.
- [ ] Implementation modules isolate only genuine differences.
- [ ] Explicit choice made among adapters, MR-JARs, artifact lines, and branches.
- [ ] Owner and sunset schedule assigned for legacy support.

### Build

- [ ] Maven/Gradle versions and JDK toolchains pinned.
- [ ] `--release` set accurately for API and each implementation.
- [ ] Legacy dependency closure free of newer bytecode or APIs.
- [ ] BOMs, version catalogs, and lockfiles managed per variant.
- [ ] Service descriptors and JPMS declarations validated.
- [ ] Both providers never bundled unintentionally together.
- [ ] Fat/nested JARs and MR-JAR layouts verified on final artifacts.

### Runtime and protocol

- [ ] Legacy artifact tested on the real minimum JDK.
- [ ] Modern artifact tested on the real target JDK.
- [ ] Binary compatibility tested when un-recompiled consumers must be supported.
- [ ] Concurrency, errors, timeouts, and shutdown preserve contracts.
- [ ] Java agents, native libraries, and framework integrations tested.
- [ ] Data and protocols tested with mismatched producer/consumer versions.
- [ ] Rollback verified without unsafe database/schema assumptions.

### Release

- [ ] Artifacts published with immutable versions and checksums.
- [ ] Separate SBOM/security reviews completed for legacy/modern variants.
- [ ] Release notes explicitly distinguish minimum vs. tested JDKs.
- [ ] Canary plan, monitoring, rollback procedure, and runbooks ready.
- [ ] Backport and legacy-retirement processes defined.

## Conclusion

When supporting multiple JDKs, the sustainable strategy is rarely scattering `if (javaVersion >= ...)` throughout codebases. Keep a **shared contract compatible with the lowest JDK floor**, isolate API and runtime differences behind adapters, and ship the matching implementation to each consumer. For small internal variations under one public API, multi-release JARs fit neatly; when frameworks, dependencies, or release lifecycles diverge deeply, pick separate artifact lines or release branches.

Migration quality hinges on the complete **dependency closure**, **real runtime testing**, **source/binary/data compatibility**, and **an explicit sunset plan**, rather than compilation success alone. A disciplined roadmap combining clear adapters, controlled releases, CI matrices, and rollback readiness lets older and newer Java applications coexist smoothly during transition without forcing every system to upgrade at once.
