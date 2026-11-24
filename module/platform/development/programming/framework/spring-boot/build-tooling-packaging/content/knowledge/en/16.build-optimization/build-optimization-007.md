# Running Maven in Parallel and Evaluating Non-Thread-Safe Plugins

## 1. Why Can Parallel Maven Builds Be Faster Yet Risky?

When a Spring Boot project is split into multiple Maven modules, `mvn clean verify` by default traverses the **reactor build** while respecting inter-module dependency order. When **independent** modules exist, Maven 3 can build them **concurrently** using the `-T` (*thread count*) option. This cuts wait time in multi-module projects, but is safe only if **plugin goals, tests, file outputs, and external services** can execute concurrently.

Key takeaway:

> `mvn -T 2 clean verify` lets Maven use **two worker threads to process ready modules**, which does not mean every module or every test method runs concurrently.

This distinction matters. Maven honors dependency relationships in the reactor, yet **side effects outside the dependency graph**—writing to a shared file, binding the same TCP port, or mutating a shared database—can still cause race conditions even when each module compiles cleanly.

This lesson explains how to choose `-T`, interpret Maven's feedback about plugin goals **not marked thread-safe**, audit common side effects, and measure real gains on a runnable Java 17 Maven/Spring Boot project.

### Expected outcomes

After studying this lesson, you will be able to:

- Use `mvn -T 2`, `mvn -T 1C`, and `mvn -T 1.5C` accurately.
- Explain the reactor **dependency DAG**, when two modules can build in parallel, and the **critical path** limit.
- Distinguish **Maven reactor parallelism** from **JUnit 5 test parallelism**, **Surefire forks**, and running multiple CI jobs.
- Read warnings about goals missing the `threadSafe` marker and locate the **exact plugin, version, and goal** executing.
- Evaluate plugin safety from **code, descriptor, and side effects**, rather than blindly trusting a thread-safe label.
- Run a serial baseline and controlled parallel builds, comparing reports and performance.
- Keep build outputs, test ports, databases, and external services **isolated across modules**.

## 2. What Does Maven `-T` Actually Parallelize?

### 2.1. Command-line syntax

At the root of a Maven reactor, on Linux/macOS:

```bash
# Baseline: reactor parallelism disabled
./mvnw clean verify

# Up to 2 Maven worker threads in the reactor:
./mvnw -T 2 clean verify

# Roughly 1 worker thread per CPU core detected by Maven:
./mvnw -T 1C clean verify

# Roughly 1.5 worker threads per CPU core detected by Maven:
./mvnw -T 1.5C clean verify

# 4 worker threads (not 4 threads per module):
./mvnw -T 4 clean package
```

If the project has no Maven Wrapper and Maven is installed locally, replace `./mvnw` with `mvn`. On Windows PowerShell use `.\mvnw.cmd`, for example:

```powershell
.\mvnw.cmd -T 2 clean verify
.\mvnw.cmd -T 1C clean verify
```

| Option | Meaning | Notes |
|---|---|---|
| Without `-T` | Maven reactor builds projects sequentially in normal mode | Useful baseline for debugging |
| `-T 2` | Fixed worker thread count of 2 | Easy to bound resource usage in CI |
| `-T 4` | Fixed worker thread count of 4 | Reasonable with enough independent modules and CPU/RAM |
| `-T 1C` | Multiplier of 1 thread per CPU core | Thread count depends on cores detected by Maven |
| `-T 1.5C` | Multiplier of 1.5 threads per CPU core | Can oversubscribe CPU; must benchmark |
| `-pl :service-app -am` | Selects the app module **and required upstream dependencies** | Combines with `-T` |
| `-fae` | *Fail at end*: continues building unaffected modules before failing | Does not make a broken build pass |
| `-ff` | *Fail fast*: reactor policy to stop quickly on failure | Does not guarantee already-running workers stop instantaneously |

`C` here is a **cores multiplier**, not "compiler threads" or a Docker/CI CPU quota. Inside containers, the core count seen by Maven/JVM may differ from allocated CPU resources; always measure in the target environment.

### 2.2. The Maven reactor is a dependency graph

Consider this layout:

```text
                     parent (pom)
                         |
              +----------+----------+
              |                     |
          format-lib             math-lib
              |                     |
              +----------+----------+
                         |
                     service-app
                         |
                 executable Boot JAR
```

- `format-lib` and `math-lib` **do not depend on each other**, so they become eligible to build concurrently once the root parent is processed.
- `service-app` depends on both, so Maven **cannot complete the app build until both required library modules finish**.
- If you only have a linear chain A → B → C → D, raising `-T 8` cannot create eight parallel tasks because the graph lacks independent branches.
- When many modules depend only on the parent, the reactor can exploit concurrency much better.

Relationships governing reactor ordering include **project dependencies**, **plugins built inside the reactor**, **plugin dependencies**, **build extensions**, **parent POMs**, and, when unconstrained, `<modules>` order. Entries declared only in `dependencyManagement`/`pluginManagement` **do not create reactor edges**. Maven prioritizes dependency graph correctness and will not bypass dependencies because of `-T`.

### 2.3. What is NOT automatically parallelized?

`-T` does **not** make Maven parallelize everything inside a single module. These mechanisms have their own controls:

- The compiler has its own policies; `-T` does not mean `javac` compiles individual source files across threads.
- Surefire/Failsafe control **forked JVMs** and test framework execution.
- JUnit Jupiter has its own **parallel execution** configuration.
- Spring Boot Maven Plugin `repackage` creates the executable JAR within the **app module's** lifecycle.
- CI can run multiple Maven processes across separate jobs; that is **job/process parallelism**, distinct from `-T` inside one Maven reactor.

With `-T 4` across multiple modules that contain tests, **Surefire executions in different modules can run simultaneously** even while test methods inside each module remain sequential. That is a frequent source of port, database, shared-file, and container-runtime contention.

## 3. What Does "Thread-Safe Plugin" Mean in Maven?

A Maven plugin contains one or more **Mojos** (*Maven plain Old Java Objects*). Each Mojo is a **goal**, such as `compiler:compile`, `surefire:test`, or `spring-boot:repackage`. A single plugin can have goals with different behavior, so **never label an entire plugin safe by name alone** without checking the specific goal invoked.

Since Maven 3, a plugin goal can declare `threadSafe` metadata (e.g., `@Mojo(..., threadSafe = true)` in plugin source). Maven inspects the plugin descriptor to identify goals whose authors **marked them as supporting parallel builds**.

### 3.1. What the warning actually says

When running in parallel, Maven may print a warning with this meaning:

```text
Your build is requesting parallel execution, but this project contains
plugin(s) that have goals not marked as thread-safe...
```

This is a **paraphrase of the message**; exact wording, plugin lists, and formatting depend on Maven version. The warning fires because one or more goals in the execution plan **lack the `threadSafe` marker**—not because Maven proved a race condition occurred.

**Distinguish three states:**

| State | What you can conclude | What you cannot conclude |
|---|---|---|
| Goal marked `threadSafe=true` | Author declared the goal supports Maven reactor parallel execution | Every custom config, script, database, or test sharing resources is automatically safe |
| Goal lacks marker or `threadSafe=false` | Maven has reason to warn and the goal needs evaluation | The goal will definitely fail in every project |
| One `-T` run succeeded | No failure was observed in that run | The build is free of races, flaky tests, or non-reproducible artifacts |

A plugin may be marked thread-safe yet **project configuration** makes every module write to `target/shared-report.json` under the root. Or plugin code might use mutable static fields, shared singletons, or non-thread-safe libraries. A positive marker is an encouraging sign, **not a substitute for auditing real side effects**.

### 3.2. Evaluating at the goal and version level

First identify the **exact plugin goals invoked** in phases such as `generate-sources`, `compile`, `test`, `package`, and `verify`. Check:

- `pom.xml`, parent POMs, and active Maven profiles.
- `help:effective-pom` for configuration after inheritance and profiles.
- Maven build logs showing plugin coordinates, versions, and goals per module.
- Official documentation for that goal (many goal docs list thread-safety under **Attributes**).
- The plugin descriptor `META-INF/maven/plugin.xml` inside the plugin JAR (for thorough verification).
- Source code, issue trackers, or release notes when warnings or races remain unclear.

Example commands:

```bash
# Effective build configuration:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Describe a goal, plugin, and parameters:
./mvnw help:describe \
  -Dplugin=org.apache.maven.plugins:maven-jar-plugin \
  -Dgoal=jar -Ddetail

# Inspect a specific Boot plugin goal (do not assume all goals share metadata):
./mvnw help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin \
  -Dgoal=repackage -Ddetail
```

On Windows, replace `./mvnw` with `.\mvnw.cmd`; you can write the command on one line. `help:describe` is a **helper/aggregator goal** that may not itself be marked thread-safe; run diagnostic goals like this **without `-T`**. If `help` output does not state thread-safety clearly, check the goal docs and plugin descriptor for that exact version rather than guessing from silence.

Example inspecting the descriptor with JDK `jar` (requires the plugin JAR at the resolved path):

```bash
# Example JAR path after Maven has downloaded plugin 3.5.16:
jar tf "$HOME/.m2/repository/org/springframework/boot/spring-boot-maven-plugin/3.5.16/spring-boot-maven-plugin-3.5.16.jar"
```

A valid Maven plugin artifact contains `META-INF/maven/plugin.xml`. Extract it to a separate directory and check `<goal>repackage</goal>` alongside `<threadSafe>...` **inside the same `<mojo>` element**, rather than grepping the whole file and reading a flag from a different goal. `~/.m2` is the **common default** and may differ if `settings.xml` or `-Dmaven.repo.local` overrides the local repository.

### 3.3. Checklist for auditing whether a plugin is truly safe

Check **metadata, implementation, and environment**:

1. **Mutable static state**: does the plugin hold unsynchronized static maps, lists, or caches?
2. **Singleton/service components**: do objects shared across worker threads contain mutable state?
3. **Thread-unsafe libraries**: does the plugin call formatters, archivers, or helpers that maintain unprotected shared state?
4. **Output paths**: does each module write to its own `${project.build.directory}` or do all modules write to one file at root?
5. **Temp files**: are temp filenames unique per module and goal invocation?
6. **Global resources**: TCP ports, H2 file databases, Docker container names, Git index, lockfiles, local repository metadata, or private caches?
7. **Forked processes**: can the goal spawn subprocesses, scripts, or external tools concurrently?
8. **Lifecycle side effects**: does it modify parent POMs, generated sources of another module, version files, or shared resources?
9. **Reproducibility**: do outputs depend on scheduling order, system clock, random seeds, or filesystem iteration order?
10. **Error handling**: if multiple modules fail simultaneously, does the plugin leave partial outputs or locks that break the next build?

**Key distinction:** Maven core coordinates reactor concurrency, yet **cannot automatically protect files, sockets, or databases outside the dependency graph**.

## 4. Risk Scenarios: Shared Files, Shared Ports, and Shared Resources

### 4.1. Two modules writing to one file outside per-module build directories

Suppose a custom `generate-report` plugin in both `format-lib` and `math-lib` is configured to write:

```text
multi-module/
├── format-lib/target/       (own output)
├── math-lib/target/         (own output)
└── target/
    └── all-reports.json     (both modules write here)
```

If each execution overwrites `root/target/all-reports.json`, under `-T 2` the two modules can:

- Clobber each other's data with concurrent writes.
- Trigger `FileSystemException`/file locks on Windows.
- Read a partially written file produced by the other module.
- Produce non-reproducible output depending on which module finishes first.

**Better design:**

- Have each module write to `${project.build.directory}/reports/report.json`.
- Add a **dedicated aggregation step** after modules finish rather than having modules race to update one combined file.
- If a plugin forces a shared path, run that phase/job **serially** or implement explicit locking and verify it under load.
- Avoid fixed filenames in shared `/tmp` across projects/jobs; namespace by module and CI run.

**Illustrative** plugin configuration (not a real plugin to copy and run directly):

```xml
<configuration>
    <!-- Choose a separate output path per Maven project -->
    <outputFile>${project.build.directory}/reports/report.json</outputFile>
</configuration>
```

Because `project.build.directory` defaults to each module's `target`, this is safer than `${maven.multiModuleProjectDirectory}/target/report.json` shared by all modules. Even so, verify actual behavior in case a module overrides `build.directory` or the plugin ignores `outputFile`.

### 4.2. Two integration test suites binding the same TCP port

Suppose two modules both launch test servers on port `18080`. When `-T 2` overlaps their test runs, one may fail with:

```text
java.net.BindException: Address already in use
```

This is a **possible failure example**, not guaranteed output on every Maven run. When tests use Spring Boot's embedded web server, configure:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExampleIntegrationTest {
    // Test against the dynamically assigned port.
}
```

This is an **illustrative class snippet**, without test methods and not a standalone runnable file. Inject the actual assigned port when making HTTP requests instead of hardcoding `18080`. For servers outside Spring Test, ask the OS for **port 0** and read back the bound port.

Similar hazards apply to fixed-port Kafka/Testcontainers brokers, shared database schemas, SQLite/H2 files, and un-namespaced Redis keys. Never paper over races merely by raising timeouts.

### 4.3. Shared databases or test data

Two modules can collide when they:

- Drop tables or run migrations against a shared integration database.
- Reset `users` rows while the other module is asserting on them.
- Create Kafka topics or Docker containers with the same fixed name.
- Share credentials and rate-limited external APIs.

Solution: use **per-module/per-run** test databases, schemas, or containers, namespaced test data, proper transaction rollback, and unique temp names. If test infrastructure cannot be isolated, run that test stage **serially**.

### 4.4. Multiple Maven processes in the same workspace

Unlike a single `mvn -T 2` invocation, CI might launch **two separate Maven commands** on the same checkout. Two independent processes introduce extra hazards:

- One can run `clean` and delete the other's `target`.
- Both can install/deploy artifacts with the same GAV but different bytes.
- They can collide on temp files, generated sources, or local repository metadata during publishing.
- They can contend for ports, databases, and Docker.

`threadSafe = true` on a Maven Mojo **never** guarantees safety across **multiple Maven processes** sharing a workspace. Give each CI job its own workspace; if sharing a local Maven repository, verify cache concurrency behavior and avoid concurrent writes of mutable/SNAPSHOT artifacts.

## 5. Parallel Maven Reactor vs. Parallel Surefire/JUnit Tests

This is a very common source of confusion.

| Mechanism | Controlled by | Parallel unit | Typical risk |
|---|---|---|---|
| **Maven reactor parallelism** | `mvn -T 2 ...` | **Independent modules** | Concurrent plugin executions, inter-module port/file/DB collisions |
| **Surefire forked JVMs** | `forkCount`, `reuseForks` | Test JVM processes within a module | High RAM usage, shared resources across forks |
| **JUnit Jupiter parallel execution** | `junit.jupiter.execution.parallel.enabled=true` and modes | Test classes/methods inside JUnit engine | Shared test fixtures, static state, ordering assumptions |
| **TestNG/JUnit4 provider parallel** | Provider-specific Surefire configuration | Test classes/methods per framework | Thread-safety/shared state in tests |
| **CI pipeline parallel jobs** | GitHub Actions/Jenkins/GitLab/... config | Independent CI jobs/processes | Workspaces, ports, artifact repos, rate limits |

If you combine `-T 4` with multiple Surefire forks inside each module, active JVMs can multiply rapidly; **never assume CPU/RAM usage corresponds to just four threads**. Bound total pipeline concurrency using a realistic concurrency matrix.

### 5.1. Surefire/JUnit Jupiter does not parallelize tests automatically

With compatible Surefire/JUnit 5 versions, test methods **do not automatically run in parallel** just because Maven uses `-T`. To enable parallelism **inside** JUnit Jupiter, configure JUnit Platform in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

This is a **separate choice**, not a default setting to turn on everywhere. When enabled, test classes and methods must be thread-safe with no unprotected shared mutable state. JUnit 5 configuration is handled by the test engine; Surefire's `parallel` option has **provider- and framework-specific semantics**. Do not copy settings written for the JUnit 4.7 provider onto JUnit Jupiter assuming they are equivalent.

### 5.2. When should you parallelize the reactor but not tests?

Suppose a project has many independent libraries while each module's integration tests use shared fixtures: it can benefit from `-T 2`, **provided test resources are isolated across modules**. If test resources are not yet isolated, keep `verify` serial until test infrastructure is fixed. Never pass `-DskipTests` to declare a "green parallel build" and pretend quality was verified.

## 6. Hands-On Maven Reactor + Spring Boot Java 17 Project

We build **four Maven projects**: a root parent, two independent JAR libraries, and a Spring Boot app depending on both. This lesson provides runnable code and unit tests to compare **serial vs. parallel** outcomes.

Use **Java 17+**, a compatible Maven 3.9.x or project-configured Maven Wrapper, and Spring Boot **3.5.16** as the pinned example version. Do not claim the example version is the newest Spring Boot release. The first build may download plugins/dependencies; warm the cache before timing runs.

### 6.1. Directory layout

```text
parallel-build-lab/
├── pom.xml
├── mvnw                          (if Maven Wrapper is present)
├── mvnw.cmd                      (if Maven Wrapper is present)
├── .mvn/wrapper/...              (if Maven Wrapper is present)
├── format-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/format/GreetingFormatter.java
│   └── src/test/java/com/example/format/GreetingFormatterTest.java
├── math-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/math/SumCalculator.java
│   └── src/test/java/com/example/math/SumCalculatorTest.java
└── service-app/
    ├── pom.xml
    └── src/main/java/com/example/app/ParallelLabApplication.java
```

Wrappers do not appear automatically just by creating POMs. If no wrapper exists, use your installed `mvn`. The project consists of exactly three modules declared under the root POM; no Gradle switch or extra automation scripts are required.

### 6.2. Root POM: aggregator + parent

Create `pom.xml` at the root:

```xml
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
    <artifactId>parallel-build-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>format-lib</module>
        <module>math-lib</module>
        <module>service-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Root has `<packaging>pom</packaging>`, acting as aggregator/parent rather than producing an executable JAR. It inherits `spring-boot-starter-parent` for dependency and plugin management; the root **does not declare the Spring Boot Maven Plugin under `<build><plugins>`**. Putting the Boot plugin into the root where children inherit it could apply `repackage` to libraries that have no `main` class. Only the app declares that plugin in Section 6.5.

### 6.3. `format-lib`: POM + Java class + unit test

Create `format-lib/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>format-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`format-lib/src/main/java/com/example/format/GreetingFormatter.java`:

```java
package com.example.format;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`format-lib/src/test/java/com/example/format/GreetingFormatterTest.java`:

```java
package com.example.format;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {
    @Test
    void formatsGreeting() {
        assertEquals("Hello, Java!", GreetingFormatter.greet("Java"));
    }
}
```

This is a standard Java module with **one JUnit Jupiter unit test**, no `main` class, and no Boot packaging plugin. `junit-jupiter` gets its version from the Spring Boot Parent; `test` scope excludes it from the final library JAR.

### 6.4. `math-lib`: independent of `format-lib`

Create `math-lib/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>math-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`math-lib/src/main/java/com/example/math/SumCalculator.java`:

```java
package com.example.math;

public final class SumCalculator {
    private SumCalculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

`math-lib/src/test/java/com/example/math/SumCalculatorTest.java`:

```java
package com.example.math;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SumCalculatorTest {
    @Test
    void addsTwoIntegers() {
        assertEquals(42, SumCalculator.add(20, 22));
    }
}
```

This module **does not import from `format-lib`**, allowing Maven to process both library projects concurrently when `-T` is used and a worker is free. `Math.addExact` is standard in Java 17; for inputs 20 and 22, the exact result is 42.

### 6.5. `service-app`: depends on both modules

Create `service-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>format-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>math-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
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
```

`${project.version}` interpolates to `1.0.0` within the module POM. `spring-boot-starter` supplies the Spring Boot runtime; omitting `spring-boot-starter-web` keeps the demo a console application.

With `spring-boot-starter-parent`, declaring `spring-boot-maven-plugin` in the app activates the parent-managed `repackage` execution. Do not declare this plugin in the libraries. `spring-boot:run` is a development command, not a goal automatically bound to `mvn verify`.

`service-app/src/main/java/com/example/app/ParallelLabApplication.java`:

```java
package com.example.app;

import com.example.format.GreetingFormatter;
import com.example.math.SumCalculator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ParallelLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelLabApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult() {
        return args -> {
            System.out.println(GreetingFormatter.greet("Java"));
            System.out.println("answer=" + SumCalculator.add(20, 22));
        };
    }
}
```

The application calls both independent library JARs. Only **service-app** has `main` and the Boot plugin, so `repackage` runs strictly on the right module.

### 6.6. Running the baseline and parallel builds

From the root `parallel-build-lab`:

```bash
# Serial baseline, building all modules and tests:
./mvnw clean verify

# Re-run the same reactor with 2 workers:
./mvnw -T 2 clean verify

# Build only the app and the projects it depends on:
./mvnw -T 2 -pl :service-app -am clean verify

# Run the packaged application:
java -jar service-app/target/service-app-1.0.0.jar
```

Replace `./mvnw` with `mvn` if the project lacks a Maven Wrapper; PowerShell uses `.\mvnw.cmd`. Run the specific command suited to each check rather than repeating all three builds just to produce an artifact. On success, the **two lines printed by the application** are literally:

```text
Hello, Java!
answer=42
```

Console output may also include Spring Boot banners/startup logs depending on environment. Do not claim **all stdout** consists solely of those two lines.

### 6.7. Interpreting Maven output

With a properly configured reactor, Maven prints project logs and a `Reactor Summary` like:

```text
parallel-build-lab ................. SUCCESS
format-lib ......................... SUCCESS
math-lib ........................... SUCCESS
service-app ........................ SUCCESS
BUILD SUCCESS
```

This is an **illustrative summary of expected states**, not verbatim output (timings, padding, and Maven log lines vary). With `-T 2`, logs from `format-lib` and `math-lib` may **interleave** because different workers build them concurrently. `Reactor Summary` may still print in a stable reactor order; do not use log ordering as proof of dependency scheduling.

**Key observation:** while `format-lib` and `math-lib` build concurrently without shared side effects, `service-app` only runs once both library dependencies are ready. This is concurrency at the **module level**; it does not guarantee a 2x speedup.

### 6.8. Inspecting actual artifacts after the build

```bash
# Standard library JARs:
jar tf format-lib/target/format-lib-1.0.0.jar
jar tf math-lib/target/math-lib-1.0.0.jar

# Spring Boot executable JAR:
jar tf service-app/target/service-app-1.0.0.jar
```

In the Boot executable archive, look for entries:

```text
BOOT-INF/classes/com/example/app/ParallelLabApplication.class
BOOT-INF/lib/format-lib-1.0.0.jar
BOOT-INF/lib/math-lib-1.0.0.jar
```

In library JARs, classes sit at package root, such as `com/example/format/GreetingFormatter.class` or `com/example/math/SumCalculator.class`. The difference confirms the reactor packaged each module per its own type; `-T` never alters a library module into a Boot JAR.

## 7. When Maven Warns That a Goal Is Not Thread-Safe

Suppose a real project uses an older or custom plugin bound to `generate-resources`. When running:

```bash
./mvnw -T 2 clean verify
```

and seeing a warning that a plugin is not marked thread-safe, follow an **evidence-based workflow**:

1. **Record exact plugin coordinates**: `groupId:artifactId:version` of the warned plugin and the goal in the execution plan.
2. **Locate the module and phase** where the goal executes (from logs or effective POM).
3. **Read the goal docs/plugin descriptor** for that exact version, not a different version.
4. **Search for side effects**: root-level files, shared databases, fixed ports, Docker image tags, temp directories.
5. **Check release notes**: did a newer version fix thread-safety or archive/cache bugs?
6. **Compare against a serial build** with identical JDK, dependency versions, Maven settings, and active profiles.
7. **Test modest parallelism** such as `-T 2` first rather than jumping straight to `-T 2C` in CI.
8. **Inspect artifacts and reports**, not only `BUILD SUCCESS`.
9. **Keep risky stages serial** if safety cannot be proven.
10. **Open a plugin issue** or fix custom Mojos when a race reproduces; do not assume it is a Maven core bug.

### Choosing the right remedy

| Finding | Preferred resolution |
|---|---|
| Older goal has a newer thread-safe version | Upgrade plugin with testing; pin version in `pluginManagement` |
| Goal lacks `threadSafe`, yet logic is read-only with no shared side effects | Audit implementation, test parallel runs repeatedly, request upstream marker if valid |
| Goal writes the same file across all modules | Move output to each module's `${project.build.directory}` or add a post-reactor aggregation step |
| Goal calls an API/service that rejects concurrency | Run that part serially, throttle requests, or isolate resources |
| Goal uses a shared test database | Isolate schemas/containers/data, or serialize integration tests |
| Goal packages/mutates another module's archive | Fix module boundaries; each goal should touch only its own module's artifacts |
| Custom plugin has unclear thread safety | Audit static/singleton state, locking strategy, and dependencies |
| Cannot prove safety before release | Use **serial `mvn clean verify`** on the release path |

**Important:** never pass `-Dmaven.test.skip=true` or `-DskipTests` just to avoid test-related warnings and declare parallelism safe. Those flags alter what is verified and can mask critical bugs.

### Is there a one-line Maven flag to "disable parallelism just for goal X"?

Maven 3 has no universal CLI flag like `-T 4 --sequential-plugin=X` that automatically serializes selected goals mid-reactor. When a goal is unsafe:

- Fix the plugin/configuration or upgrade its version.
- Move the work into a **separate coordinated step**, such as aggregating after modules write independent outputs.
- Use profiles appropriately to run safe phases quickly, then invoke risky goals/phases in a **dedicated serial step**.
- If you cannot decouple it cleanly yet, keep the entire build serial until fixed.

Never assume Maven automatically locks every goal lacking a `threadSafe` marker. The warning is a signal to audit, not a guarantee that Maven serializes those goals.

## 8. Benchmarking Properly Instead of Chasing "Feels Faster"

Not every build speeds up when adding threads. Performance depends on:

- Number of independent modules and proportion of work on the **critical path**.
- CPU/RAM/IO, disk throughput, artifact repository network latency, and container quotas.
- Compiler/test JVM startup and memory footprint.
- Maven daemon/JDK warm-up, dependency caching, and plugin resolution.
- Plugin synchronization or shared resources causing lock contention.
- Whether builds execute identical tests/Failsafe suites, quality checks, codegen, and image builds.

### 8.1. Basic benchmark

On Linux/macOS, warm the dependency cache first (downloading dependencies on the first run is not a fair comparison), then run multiple iterations with the **exact same goals**:

```bash
# Warm-up build, excluded from primary metrics:
./mvnw clean verify

# Serial benchmark:
time ./mvnw clean verify

# 2-worker benchmark:
time ./mvnw -T 2 clean verify

# CPU-scaled benchmark:
time ./mvnw -T 1C clean verify
```

PowerShell:

```powershell
Measure-Command { .\mvnw.cmd clean verify }
Measure-Command { .\mvnw.cmd -T 2 clean verify }
Measure-Command { .\mvnw.cmd -T 1C clean verify }
```

`Measure-Command` records execution duration, yet **never look at Duration alone**: inspect logs, exit status, test counts, and generated artifacts. Runs must share the same JDK/Maven versions, flags, profiles, network/cache state, `clean verify` target, and CPU allocation. Run several iterations per configuration, alternate order or take the median to reduce warm-up and noise bias.

**Evaluation formula:**

```text
speedup = serial time / parallel time

speedup > 1: parallel run is faster
speedup = 1: roughly equal speed
speedup < 1: parallel run is slower
```

Illustrative example: serial `120 s`, parallel `90 s` ⇒ speedup `120/90 ≈ 1.33`; these are hypothetical figures to illustrate the math, **not a guarantee of Maven performance**.

### 8.2. Why can `-T 1C` sometimes perform worse than `-T 2`?

- CI exposes many logical cores with limited RAM; each module runs tests/forked JVMs.
- Parallel builds increase CPU, garbage collection, and filesystem pressure.
- Reactor libraries form a long dependency chain, leaving extra workers idle.
- Plugins or external services bottleneck; adding threads worsens lock/connection contention.
- Multiple test containers starting simultaneously overload the Docker daemon or registry.

**Choose concurrency via measurements and stability**, not the maximum thread count hardware allows. In many pipelines, `-T 2` or `-T 1C` is worth testing; for small builds, serial can win.

## 9. Verifying Results Beyond `BUILD SUCCESS`

A successful parallel build must pass both **functional correctness** and **artifact correctness**:

| Target | How to verify |
|---|---|
| Reactor modules | `Reactor Summary` lists every expected module with no unintended `SKIPPED` |
| Unit tests | Pass/fail/skipped counts from `target/surefire-reports` in **every module** |
| Integration tests | Failsafe `verify` and `target/failsafe-reports` if ITs are configured |
| Generated sources | Files live inside their owning module, not deleted/overwritten by another module |
| Executable JAR | `jar tf` verifies `BOOT-INF/classes`, `BOOT-INF/lib`, and valid manifest |
| Runtime smoke test | `java -jar service-app/target/service-app-1.0.0.jar` runs cleanly |
| Reproducibility | Checksums/archive comparisons match the project's reproducible-build policy |
| Shared resources | No port collisions, cross-test DB pollution, or file races |
| Warning logs | No ignored plugin warnings or intermittent test failures |

### Testing a comparative pipeline

Suppose the CI goal is building the entire reactor:

```bash
# 1. Confirm serial baseline:
./mvnw clean verify

# 2. Run controlled parallel build:
./mvnw -T 2 clean verify

# 3. Smoke-test application artifact:
java -jar service-app/target/service-app-1.0.0.jar
```

Compare reports afterward. In real projects, repeat parallel runs to flush out flaky behavior; if intermittent errors appear, collect logs and reports **before deleting `target/`**. Never approve a release based on a single parallel pass if serial and parallel produce differing dependencies or artifacts.

### Reading interleaved logs

In a parallel reactor build, logs from modules A and B interleave. To diagnose failures:

- Search for the plugin goal/module prefix, `Reactor Summary`, and the first project-related error.
- Group logs by job/module if CI supports it, or re-run the **failing module in serial mode** to reduce noise.
- Use `-pl :module-name -am` if the module needs reactor dependencies.
- Use `-X` for deep Maven internals when needed, noting debug logs may contain local paths, settings, and internal URLs; sanitize before sharing publicly.
- Do not read console line order as an exact worker execution timeline.

## 10. Integrating with the Spring Boot Maven Plugin

In multi-module Spring Boot builds, **library modules** should use plain JAR packaging, while **application modules** declare the Spring Boot Maven Plugin to `repackage` the executable JAR.

This reduces risks:

- Libraries are not forced to locate `main()` or emit executable archives.
- The app has one clear packaging step after Maven builds its dependent modules.
- Multiple apps/libraries do not mutate a shared artifact at root `target`.
- Build profiles and policies stay clearly scoped per module.

**Do not assume every goal of the Spring Boot Maven Plugin has identical thread safety.** `repackage`, `run`, `build-image`, and `process-aot` differ in lifecycle, I/O, and side effects; check your exact **version/goal** and project usage.

### `spring-boot:run` is not a `-T` build benchmark

`spring-boot:run` launches the application for development and can keep the process running until stopped. It is **not** a goal to include in `mvn -T ... verify` for throughput benchmarking. For build benchmarking, use `clean test`, `clean package`, or `clean verify` with identical policies in both serial and parallel runs.

`spring-boot:repackage` builds the executable JAR/WAR from the archive produced by `package`. If another custom plugin mutates the same `target/app.jar` in the same phase without explicit ordering, that is a plugin coordination bug regardless of `-T`. Define explicit executions and let each module own its own outputs.

### Docker/`build-image` and external resources

If CI runs `spring-boot:build-image` across multiple apps concurrently, they may:

- Share the Docker/Podman daemon and buildpack cache.
- Overwrite image tags if group/artifact/version naming collides.
- Contend on disk, network, and image layer caches.
- Hit shared credentials, environment limits, or registry rate limits.

These side effects require dedicated CI policy. Never infer from `@threadSafe` on a goal that the Docker daemon or registry is safely isolated.

## 11. Guidelines for Adopting `-T` in a Real Project

Follow an **incremental** rollout path:

### Phase 1 — Establish a clean baseline

Run serial `mvn clean verify` with consistent Java/Maven/settings. Ensure zero test failures, clean dependency resolution, and a working executable artifact. Record post-warmup build duration.

### Phase 2 — Pilot modest parallelism

Run `mvn -T 2 clean verify`. Inspect plugin warnings, Surefire/Failsafe reports, and actual artifacts. If non-thread-safe warnings appear, resolve or audit them before raising thread counts.

### Phase 3 — Classify unsafe spots

List goals lacking `threadSafe`; audit static/singleton state, output paths, temp directories, test ports, and external dependencies. Categorize each risk as fixable via **module-specific outputs**, **resource isolation**, **plugin upgrade**, or **serialization**.

### Phase 4 — Benchmark and choose CI settings

Compare serial vs. `-T 2` and `-T 1C` on real CI hardware. Prefer settings that are **stable**, flake-free, and fast—never pick the highest thread count solely from one fast run.

### Phase 5 — Protect the release path

Ensure release jobs run all required tests/quality gates with no skip flags masking issues. If plugins are unproven or test environments lack isolation, **keep release builds serial** or split safe and risky stages explicitly with verification.

## 12. Common Failures and Remedies

| Symptom | Likely cause to check | Remedy |
|---|---|---|
| Maven warns plugin not marked thread-safe | Goal lacks `threadSafe` metadata | Identify plugin/version/goal, check descriptor/docs, audit side effects |
| `-T 8` is no faster than `-T 2` | Narrow module graph or saturated resources | Analyze critical path, CPU/RAM/IO, benchmark |
| Parallel build fails while serial passes | Plugin race, test port, shared file/DB, or unmodeled ordering | Collect logs/reports, isolate resources, re-test systematically |
| `Address already in use` | Modules share a fixed test port | Use dynamic ports or serialize that test stage |
| Generated file missing or truncated | Multiple modules write to shared root output | Write to each module's `${project.build.directory}` and aggregate later |
| `FileSystemException`/file lock on Windows | Concurrent writes to shared files/caches | Separate output paths, lower concurrency, isolate workspaces |
| `OutOfMemoryError` under `-T 1C` | Too many Maven workers and forked test JVMs | Reduce `-T`/`forkCount`, increase RAM per measurements |
| Boot JAR missing a module library | Missing project dependency in POM or wrong packaging | Check reactor deps, `dependency:tree`, `BOOT-INF/lib` |
| `NoClassDefFoundError` only in parallel artifact | Stale/corrupt artifact or dependency/packaging bug | Clean rebuild serial and parallel, diff archives, find root cause |
| Test counts differ between builds | Test discovery/filter/skip/cache issue or race | Compare per-module `surefire-reports`; look beyond `BUILD SUCCESS` |
| Different plugin versions across modules | Inconsistent parent/`pluginManagement`/profiles | Pin versions and inspect effective POM per module |
| Scrambled Maven logs | Workers interleaving stdout | Read `Reactor Summary`, per-module reports, and grouped CI logs |
| `spring-boot:run` never exits | Dev app running as a long-lived server | Do not benchmark long-lived goals; use `package`/`verify` |
| Image builds time out or collide on tags | Shared Docker/buildpack cache and tags | Isolate per app/run and serialize where needed |
| Multiple CI Maven jobs in same directory | Processes delete/overwrite each other's `target` | Give each CI job its own checkout/workspace |
| Plugin marked `threadSafe` still races | Marker does not guarantee test config or external services are safe | Audit side effects and file an issue with a minimal reproducer |

## 13. Final Checklist

- [ ] Confirmed the project is a **multi-module reactor** with independent modules.
- [ ] Understood `-T 2` and `-T 1C` cap **worker threads**, not forcing every test method to run concurrently.
- [ ] Understood dependent modules wait for upstream projects in the graph.
- [ ] Know how to run `help:effective-pom` and `help:describe` **without `-T`** when auditing plugins.
- [ ] Identified exact goals/versions and `threadSafe` metadata instead of judging by plugin name alone.
- [ ] Audited files, temp dirs, ports, databases, Docker, and caches for cross-module sharing.
- [ ] Scoped outputs to each module's `${project.build.directory}` or a post-reactor aggregation stage.
- [ ] Distinguished Maven `-T` from Surefire `forkCount` and JUnit 5 parallel execution.
- [ ] Verified a serial baseline before raising worker threads.
- [ ] Inspected all warnings and test reports instead of trusting a single `BUILD SUCCESS`.
- [ ] Verified the Boot executable JAR and library JARs inside `BOOT-INF/lib`.
- [ ] Benchmarked multiple runs with identical phases, test policies, and hardware.
- [ ] Kept releases serial if plugins/tests are not proven safe in parallel.
- [ ] Never used skip flags or `ignoreFailures` to trade correctness for green builds.

**Conclusion:** Maven `-T` speeds up builds at the **Maven reactor module level**. Maven preserves dependency order but cannot automatically fix non-thread-safe plugin goals, shared output paths, or resource-contending tests. The sound workflow is **verify graph → inspect plugin goal metadata → audit side effects → pilot `-T 2` → compare reports/artifacts → benchmark → adopt a safe CI policy**.

### Official References

- [Apache Maven — Parallel Builds in Maven 3](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Plugin API — plugin descriptor and threadSafe](https://maven.apache.org/ref/3.9.16/maven-plugin-api/plugin.html)
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire — surefire:test parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Spring Boot 3.5 — Running Your Application with Maven](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
