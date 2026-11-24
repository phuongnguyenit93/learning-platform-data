# Tuning the Gradle Daemon, JVM Memory, and Parallelism

In Java/Spring Boot projects, when `./gradlew build` is slow, tasks fail with `OutOfMemoryError`, the machine constantly swaps, or CI is killed by the OS for running out of RAM, the three groups of settings to understand are the **Gradle Daemon**, the **memory of the JVMs participating in the build**, and the **level of parallelism**.

These are **three distinct configuration axes**:

- The **Gradle Daemon** is a long-lived JVM process running Gradle that can be reused across multiple builds. The Daemon reduces startup overhead and keeps certain state and caches in memory.
- **`org.gradle.jvmargs`** sets JVM arguments for the **Gradle build/daemon process**, such as `-Xmx` (heap limit). It does **not** automatically change the heap of every child JVM, tests, `bootRun`, or the production application.
- **`org.gradle.parallel` / `--parallel`** and **`org.gradle.workers.max` / `--max-workers`** control concurrent execution of work inside a build. Running more work concurrently can be faster on machines with enough CPU and RAM, but can also raise total memory consumption, cause I/O contention, or destabilize builds.

**The goal is to optimize build duration within resource limits**, not to turn every knob up to maximum. A sensible configuration for a 4 GB RAM machine can be completely wrong for a 16 GB RAM CI runner or a developer workstation running Docker, databases, and an IDE simultaneously.

This lesson uses Gradle Wrapper commands (`./gradlew`, Windows: `.\gradlew.bat`), Java 17, and Spring Boot as examples. The `-Xmx` values and worker counts are **illustrative values for experimentation**, not blanket recommendations for every machine. Base your choices on available resources and measured data.

## 1. Which JVMs/Processes Does Gradle Run On?

This is where many optimizations go wrong.

When running:

~~~bash
./gradlew :app:bootJar
~~~

several processes may be involved:

~~~text
Terminal
   |
   v
Gradle Client JVM
   |
   | connects to compatible Daemon
   v
Gradle Daemon JVM -------------------------+
   |                                      |
   +-- configure projects, plugins, tasks |
   +-- process task graph                 |
   +-- may fork worker processes ---------+
   +-- may fork JVM to run Tests
   +-- may fork Java compiler (if configured)
   +-- may fork JVM for bootRun
   |
   v
JAR/WAR output (if running bootJar/bootWar)

After build, deploy:
java -jar app.jar
   |
   v
Application JVM running independently of Gradle
~~~

This is a high-level diagram. Individual plugins may choose process, thread, or classloader isolation differently—not every task spawns its own JVM.

### Processes to distinguish

| Component | Who starts it? | Typical memory tuning | Directly affects production JVM? |
| --- | --- | --- | --- |
| Gradle Client | `gradlew` script / IDE | `JAVA_OPTS`, `GRADLE_OPTS` within client scope | No |
| Gradle Daemon/build JVM | Gradle when executing a build | `org.gradle.jvmargs` | No |
| Gradle Test worker JVM | `Test`-type tasks | `maxHeapSize`, `jvmArgs`, `maxParallelForks` | No |
| Java compiler fork (if used) | `JavaCompile`/toolchain or plugin | Compiler fork options, corresponding process JVM memory | No |
| Kotlin compiler daemon (if using Kotlin) | Kotlin Gradle plugin | Separate Kotlin daemon JVM configuration | Not automatically |
| Spring Boot `bootRun` JVM | `BootRun`/`JavaExec` task | `jvmArgs`, `maxHeapSize` if supported by API | Only the JVM launched by that task |
| App run with `java -jar` | JVM in the deployment environment | `java -Xmx... -jar ...`, env vars/JVM/container config | Yes |

**Example:** If a build fails in `:app:test` because the test JVM ran out of heap, raising `org.gradle.jvmargs` from 1 GB to 4 GB may **not fix the actual problem**. Inspect the **test JVM** heap limit and number of parallel test forks. Conversely, if the Gradle Daemon throws `Java heap space` while configuring a large build, tuning Daemon memory is the relevant lever.

## 2. What Is the Gradle Daemon and Where Does It Speed Things Up?

The **Gradle Daemon** is a JVM process that persists across Gradle invocations, reading settings/build scripts, resolving dependencies, and orchestrating and executing build work. Modern Gradle releases **enable the Daemon by default**.

Compared to starting a fresh JVM every time, the Daemon can:

1. Avoid part of the JVM startup cost on consecutive build commands.
2. Benefit from warmed-up JVM JIT compilation.
3. Keep build state, plugin classes, and caches in memory.
4. Reuse file-system watching information on supported operating systems.
5. Lower latency on consecutive `compileJava`, `test`, and `bootJar` runs for repeated workloads.

Speedups are not a fixed percentage: the first build typically resolves/downloads dependencies and initializes caches; later runs can also be faster due to **UP-TO-DATE**, build cache, or configuration cache—not the Daemon alone.

### Toggle per invocation

~~~bash
./gradlew help --daemon
./gradlew help --no-daemon
~~~

`--daemon` requests using a Daemon; `--no-daemon` requests not reusing a long-lived Daemon for this invocation. **Important note:** if the client's JVM arguments do not satisfy the build's requirements, Gradle may still spawn a **single-use Daemon** (a JVM used for one build and then stopped) even with `--no-daemon`. Thus `--no-daemon` does not always mean "only one JVM process."

Disable the Daemon for all builds of a project (only with good reason):

~~~properties
# gradle.properties
org.gradle.daemon=false
~~~

When fast iterative builds are needed on developer workstations or persistent CI agents, keeping the Daemon enabled makes sense. Do not disable it merely because you see a `GradleDaemon` process in Task Manager.

### Inspecting and stopping Daemons

~~~bash
./gradlew --status
./gradlew --stop
~~~

- `--status` lists Daemons associated with the **current Gradle version**, with PID/state info; it is not an inventory of every Java process on the machine.
- `--stop` stops Daemons managed by **that same Gradle version**, helpful for diagnosing a stuck daemon or restarting after changing configuration. It does **not** delete source code, build caches, or `build/`.
- Do not run `--stop` before every build if you want Daemon reuse; doing so discards warm-up benefits.

Changing `org.gradle.jvmargs` or the Daemon JDK can cause Gradle to **spawn a new Daemon** instead of reusing the old one. Multiple Daemons with different versions/JDKs/JVM args can coexist and consume RAM; check them before diagnosing a memory leak.

### Daemon logs and troubleshooting

In Gradle User Home, the directory is usually:

~~~text
~/.gradle/daemon/<gradle-version>/
    daemon-<pid>.out.log
    registry.bin
~~~

On Windows, Gradle User Home defaults to `%USERPROFILE%\.gradle` (unless overridden via `GRADLE_USER_HOME`). Daemon logs help inspect GC errors, daemon crashes, JVM start parameters, or why Gradle failed to connect. When connection errors occur, read the console message and log file rather than immediately raising heap.

**Reuse compatibility:** Gradle looks for a Daemon matching the Gradle version, Java runtime, JVM startup arguments, and certain immutable environment properties. Changing `-Xmx` creates a new set of requirements; Gradle cannot resize max heap on an already-running JVM.

## 3. Files and Environment Variables Controlling Gradle

Common configuration points:

| Where configured | Scope | Example |
| --- | --- | --- |
| `<root>/gradle.properties` | Builds using this project root | `org.gradle.jvmargs=-Xmx1g` |
| `<GRADLE_USER_HOME>/gradle.properties` | Per-user / CI-agent settings | Machine-specific resource limits |
| Command-line options | Current invocation | `--parallel --max-workers=2` |
| `JAVA_HOME` / PATH / IDE JVM | JVM launching the Gradle client, default when unspecified | JDK runtime |
| `org.gradle.java.home` | JDK/JVM used to run the Gradle build process via Gradle settings | Explicit JDK path |
| Daemon JVM criteria (when used) | Rules selecting the Daemon JVM on supported Gradle versions | `gradle/gradle-daemon-jvm.properties` |
| Java toolchain in `build.gradle` | Java compiler/test/tool invocations per plugin/toolchain support | Java 17 compile |
| Task-specific JVM properties | Forked JVMs for `test`/`bootRun`/workers | `maxHeapSize`, `jvmArgs` |

**Do not mix up `-P...` with JVM args.** `-PbuildType=...` sets a project property; `-D...` sets a system property; `--max-workers` is a Gradle CLI option. Each affects a different layer.

Gradle has a defined precedence order across command-line system properties, user-home properties, and root properties, and settings/plugin logic may also adjust values. To avoid team conflicts, pick one clear version-controlled default and override per invocation when benchmarking. Never scatter one `-Xmx` in a local profile, another in CI env vars, and a third in the root file without knowing which takes effect.

### Special case: `JAVA_OPTS` and `GRADLE_OPTS`

Two variables frequently misunderstood:

- `JAVA_OPTS` generally configures the **Gradle Client JVM**, not the Daemon JVM executing the build when a Daemon is used.
- `GRADLE_OPTS` also typically goes to the **Gradle Client JVM**; it can pass Gradle configuration system properties (such as `-Dorg.gradle.jvmargs=...`) that alter Daemon requirements.
- **The cleanest way to set the Gradle build process heap is `org.gradle.jvmargs`.**

Thus, setting `JAVA_OPTS=-Xmx4g` and seeing the Daemon use a different heap is not necessarily a bug. The client simply forwards the request and streams output, while the Daemon has its own JVM arguments.

### Gradle Daemon JVM vs. Java toolchain

Example `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

This requests a Java 17-compatible compiler/tooling for the project. It **does not mean** "the Gradle Daemon always runs on JDK 17." The Daemon JVM may come from the environment, `org.gradle.java.home`, or Daemon JVM criteria depending on Gradle version.

In Gradle versions supporting **Daemon JVM criteria**, the `updateDaemonJvm` task can generate `gradle/gradle-daemon-jvm.properties` declaring the required Daemon Java version/vendor. This mechanism can take precedence over `JAVA_HOME` and `org.gradle.java.home`. Use it only when your project/Gradle version supports it, and check the environment's JDK provisioning/download policies.

**Do not swap JDKs randomly when you only meant to raise heap.** The Java toolchain, Daemon JVM, test JVM, and production JVM can intentionally differ.

## 4. Tuning JVM Memory with `org.gradle.jvmargs`

A `gradle.properties` file in the root project might contain:

~~~properties
# Illustrative configuration; measure against actual available RAM.
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
~~~

Breakdown:

- **`-Xmx1g`** sets the **maximum Java heap limit of the Daemon** around 1 GiB. It does not immediately commit all of that memory to the Java heap.
- **`-XX:MaxMetaspaceSize=384m`** caps Metaspace used for class metadata; this is not Java heap. Setting it too low can trigger `OutOfMemoryError: Metaspace` in builds with many plugins/classloaders.
- **`-Dfile.encoding=UTF-8`** sets the JVM's default encoding property at startup; Java 17/platforms and plugins behave accordingly, though this does not remove the need to declare charsets explicitly when reading/writing sources or resources.
- **`-Xms`** (if specified) sets initial heap; avoid forcing `-Xms` equal to `-Xmx` by default on memory-constrained machines since it holds memory unnecessarily.
- `-XX:+HeapDumpOnOutOfMemoryError` can help investigate heap crashes, though heap dumps can be huge and **contain sensitive data**; manage storage paths and permissions carefully.

**Heap is not a JVM's total RAM.** Alongside Java heap sit Metaspace, thread stacks, code cache, direct/native buffers, JIT, and other overhead. A Daemon with `-Xmx1g` can consume **more than 1 GiB** of total resident memory. Adding test/`bootRun`/worker JVMs increases total build memory further.

### When should you increase `-Xmx`?

Consider raising it when backed by evidence:

- The Gradle Daemon genuinely fails with `java.lang.OutOfMemoryError: Java heap space`.
- A build with many subprojects/plugins has configuration state too large for the current heap.
- High/frequent GC overhead and profiling show heap pressure in the Daemon.
- An in-process task requires more memory than the current Daemon heap allows.

**Do not raise Daemon heap to cure every error:**

| OOM location | Right place to tune |
| --- | --- |
| Gradle Daemon: `Java heap space` | `org.gradle.jvmargs`, build logic, and plugin behavior |
| Daemon: `Metaspace` | Metaspace in daemon JVM args; check for classloader churn |
| Test worker JVM | `tasks.withType(Test).configureEach { maxHeapSize=... }` |
| `bootRun` JVM | `tasks.named('bootRun') { jvmArgs ... }` |
| Production JVM running `java -jar` | Java runtime/container configuration, **not** the Gradle Daemon |
| OS/container OOM killer | Total RAM across **all** processes, worker count, and container limits |
| Gradle process crash in native allocation | Native memory, JDK, thread count, workers/processes |

A build may report "Daemon disappeared unexpectedly" when the OS kills the process for exceeding RAM; in that case there is no basis to assume raising `-Xmx` helps. Raising heap too high can cause the container to **be killed sooner** due to higher total resident memory.

### When should you decrease `-Xmx`?

Lower it when the machine has limited RAM, CI runs multiple Gradle builds concurrently, or the build genuinely does not need a high heap ceiling. The target is **sufficient**, not **as large as possible**. Too little heap causes frequent GC and slowdowns; too much heap increases RAM pressure, swapping, or starves child JVMs. Base the choice on measurements.

### Configuring the test JVM

In `build.gradle` of a module with tests:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 1
}
~~~

`Test` is a Gradle task that spawns forked JVMs to run tests. `maxHeapSize` tunes **each test worker's heap**, while `maxParallelForks` caps how many test JVMs run concurrently for that task. This is separate from `org.gradle.jvmargs`.

To speed up tests, you can try:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 2
}
~~~

However, **two test forks** can simultaneously consume nearly double the **allowed heap**, plus JVM overhead. If tests share a database, fixed server port, shared temp directory, or unisolated static state, parallel forks can cause flaky tests. Test parallelism tuning must therefore go hand in hand with test isolation checks.

### Dedicated configuration for `bootRun`

In a Spring Boot `build.gradle` with the Boot plugin:

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    jvmArgs '-Xmx512m'
}
~~~

`bootRun` runs the application JVM for development; `jvmArgs` applies to that JVM. When later deploying `java -jar` in production, `bootRun` **is no longer involved**, so JVM arguments must be configured independently for the production runtime:

~~~bash
java -Xmx512m -jar build/libs/application.jar
~~~

`application.jar` is a placeholder; replace it with the actual executable JAR filename. Never set `-Xmx` in Gradle and assume production inherits that limit.

## 5. Tuning Parallelism

Gradle has several layers of parallelism. To optimize properly, distinguish them:

| Level | Option | Scope |
| --- | --- | --- |
| Parallel project execution | `--parallel` or `org.gradle.parallel=true` | Allows tasks from independent projects to run concurrently when Gradle permits |
| Worker limit | `--max-workers=N` or `org.gradle.workers.max=N` | Caps concurrent worker capacity within one Gradle build |
| Test processes | `Test.maxParallelForks` | Number of forked test JVMs per `Test` task |
| Tool-specific workers | Java/Kotlin compilers, annotation processors, plugin Worker API | May manage their own forks and memory |
| Configuration Cache | `--configuration-cache` | Caches configuration and can change parallel task scheduling by Gradle version |
| Multiple Gradle commands/CI jobs | CI executor/concurrency | **Outside** a single Gradle invocation's worker limit |

### `--parallel` does not mean "every task runs at once"

Without configuration cache, `--parallel` focuses on **parallel execution across projects** in a multi-project build. Tasks still obey `dependsOn`, input/output wiring, constraints, and resource locks. Example:

~~~text
:alpha:compileJava  ──┐
                       ├──> :app:compileJava ──> :app:bootJar
:beta:compileJava   ──┘
~~~

Independent `:alpha` and `:beta` can compile concurrently when worker slots are available; `:app:compileJava` needs outputs from both and cannot run until those required inputs are ready.

In a single-project build with a mostly linear task graph, enabling `--parallel` may **provide no meaningful gain**. Scheduling overhead or CPU/disk contention can even make it slower.

**Version note:** Modern Gradle versions using **Configuration Cache** can enable intra-project task parallelism when tasks are properly isolated/serialized. In those modes, `--parallel` is no longer the sole concurrency switch. When teaching or benchmarking, record **both Gradle version and configuration-cache mode**; avoid blanket claims across all versions.

### `org.gradle.workers.max` and `--max-workers`

Try in root `gradle.properties`:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Or enable for a single invocation:

~~~bash
./gradlew :app:bootJar --parallel --max-workers=2
~~~

`--max-workers=2` caps Gradle's worker capacity for the current invocation. It does not guarantee **strictly two OS processes** exist: the Daemon, client, compiler/test forks, and external tools have their own lifecycles; workers are Gradle's scheduling slots, not a system-wide process cap.

`N` is typically chosen based on **available CPU cores, RAM, and task characteristics**. Do not pick `--max-workers=32` inside a 2-vCPU container just because the host machine has 32 cores. Inside containers, quotas/cgroups and memory limits matter far more than host hardware specs.

### When parallelism backfires

- Only 2 GB of RAM available while launching multiple test JVMs, compilers, and the Daemon.
- Multiple tasks reading/writing to a slow disk, causing I/O contention.
- Tasks have hidden shared outputs, writing to the same undeclared file/cache.
- Test suites share fixed ports, database schemas, or temp directories.
- Annotation processors or code generators are not safe for concurrent execution.
- The CI runner simultaneously runs memory-heavy Docker containers alongside the build.

When troubleshooting elusive failures, try **`--no-parallel --max-workers=1`** and lower test forks to isolate the issue. However, with configuration cache in newer Gradle versions, `--no-parallel` does not necessarily disable all parallel task execution; race conditions ultimately require fixing dependencies/inputs/outputs or guarding shared resources rather than relying purely on forcing serial runs.

## 6. Hands-On Exercise: Measuring Daemon, Heap, and Two Worker Slots

This Spring Boot example has three subprojects:

- `:alpha` — Java library returning the word `FAST`.
- `:beta` — Java library returning the word `BUILD`.
- `:app` — Spring Boot command-line app using both modules to build an executable JAR.

The two library modules are **independent**, giving Gradle an opportunity to build them concurrently when project parallelism is enabled. The app depends on both, so Gradle still preserves build ordering.

### 6.1. Layout

~~~text
daemon-parallel-demo/
├── settings.gradle
├── gradle.properties
├── alpha/
│   ├── build.gradle
│   └── src/main/java/com/example/alpha/AlphaWord.java
├── beta/
│   ├── build.gradle
│   └── src/main/java/com/example/beta/BetaWord.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/DaemonParallelApplication.java
~~~

Wrapper files (`gradlew`, `gradlew.bat`, `gradle/wrapper/...`) are generated or added separately if not already present; they do not go inside the three subprojects.

### 6.2. Root `settings.gradle`

~~~groovy
rootProject.name = 'daemon-parallel-demo'
include 'alpha', 'beta', 'app'
~~~

`include` declares the subprojects participating in the build. Dependencies among them are declared in `app/build.gradle`. A root `build.gradle` is **not required** in this example.

### 6.3. Root `gradle.properties`

~~~properties
# Experimental values, NOT an optimal configuration for every machine.
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Why `2`? To let the two library modules run concurrently while keeping resource demands modest for the demo. On tightly RAM/CPU-constrained CI, `workers.max=1` may fit better; on beefier machines, higher values can be tested. After editing this file, re-run your command so Gradle selects a compatible Daemon if JVM arguments changed.

### 6.4. `alpha/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### 6.5. `alpha/src/main/java/com/example/alpha/AlphaWord.java`

~~~java
package com.example.alpha;

public final class AlphaWord {
    private AlphaWord() {
    }

    public static String value() {
        return "FAST";
    }
}
~~~

### 6.6. `beta/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### 6.7. `beta/src/main/java/com/example/beta/BetaWord.java`

~~~java
package com.example.beta;

public final class BetaWord {
    private BetaWord() {
    }

    public static String value() {
        return "BUILD";
    }
}
~~~

The Java library files need no Spring annotations. `java-library` exposes outputs/variants consumed via project dependencies, and neither library depends on the other.

### 6.8. `app/build.gradle`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':alpha')
    implementation project(':beta')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.app.DaemonParallelApplication'
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('daemon-parallel-demo.jar')
}
~~~

**Explanation:**

1. The Boot plugin is applied only to **app**, since `alpha` and `beta` are plain Java libraries.
2. `implementation project(':alpha')` and `implementation project(':beta')` let Gradle wire classpaths/producer tasks automatically without copying JARs manually.
3. When running `:app:bootJar`, Gradle knows it needs outputs from `alpha` and `beta`; parallelism is not allowed to violate dependency order.
4. `spring-boot-starter` suffices for a command-line Spring Boot app without starting an HTTP server.
5. `archiveFileName` produces a deterministic artifact path for easy smoke testing.

### 6.9. `app/src/main/java/com/example/app/DaemonParallelApplication.java`

~~~java
package com.example.app;

import com.example.alpha.AlphaWord;
import com.example.beta.BetaWord;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DaemonParallelApplication {

    public static void main(String[] args) {
        SpringApplication.run(DaemonParallelApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult() {
        return args -> System.out.println(
                "BUILD_RESULT=" + AlphaWord.value() + "-" + BetaWord.value());
    }
}
~~~

This Java class uses classes from both subprojects; without project dependencies, compiling `:app` would fail on unresolved imports. That provides a simple check that the build graph and runtime classpath are wired accurately.

### 6.10. Running and verifying output

Assuming a compatible Gradle Wrapper version (e.g., Gradle 8.7), from the build root on Linux/macOS:

~~~bash
./gradlew projects
./gradlew :app:bootJar --parallel --max-workers=2
~~~

The first command confirms `:alpha`, `:beta`, and `:app` belong to the build. The second builds the executable JAR with up to two worker slots. The configured output file is:

~~~text
app/build/libs/daemon-parallel-demo.jar
~~~

Run the packaged artifact:

~~~bash
java -jar app/build/libs/daemon-parallel-demo.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

The trailing backslashes are **Linux/macOS shell** line-continuation syntax; on Windows PowerShell write the `java -jar` command on a single line. Upon successful build and startup, the line printed by the application is:

~~~text
BUILD_RESULT=FAST-BUILD
~~~

Startup logs depend on the environment; the line above is the marker printed by `CommandLineRunner`.

There is no need to run `:alpha:jar` or `:beta:jar` manually before `:app:bootJar`; Gradle project dependencies create the required task dependencies.

### 6.11. Comparing parallel and sequential runs

Run a control comparison to observe the difference:

~~~bash
./gradlew :app:bootJar --no-parallel --max-workers=1 --info
./gradlew :app:bootJar --parallel --max-workers=2 --info
~~~

**Do not draw speed conclusions from two runs over already `UP-TO-DATE` outputs.** The first run may download dependencies while the second only checks inputs; any timing difference there does not measure parallelism itself. To inspect task scheduling more clearly, you can use `--dry-run`:

~~~bash
./gradlew :app:bootJar --parallel --max-workers=2 --dry-run
~~~

`--dry-run` does not execute actions or produce artifacts; it only previews the selected graph. To measure real performance, use the same workload, same cache state/inputs, repeated runs, and the valid benchmarking method in Section 9.

To test without editing build scripts repeatedly, `--no-parallel` and `--max-workers=1` are CLI flags that override root `gradle.properties` for that invocation.

## 7. Deliberately Configuring `test`/`bootRun`

The example in Section 6 has no unit test sources, so `test` may report `NO-SOURCE`. In a real Spring Boot project with test suites, you can add this **separate snippet** to `app/build.gradle`:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 1
}
~~~

Once test isolation is solid and RAM allows, try `maxParallelForks=2` and measure both duration and memory. Do not add test forks blindly just because `org.gradle.workers.max` is large; each test JVM has overhead, and integration tests launching embedded servers or databases consume much more RAM than plain unit tests.

To size the `bootRun` application JVM independently:

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    jvmArgs '-Xmx512m'
}
~~~

This is an **optional snippet** in `app/build.gradle`; it is not needed to build `bootJar`. Then run:

~~~bash
./gradlew :app:bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

The app still prints `BUILD_RESULT=FAST-BUILD`, while the heap limit of the JVM launched by `bootRun` is configured independently. Root `org.gradle.jvmargs` still governs only the build/daemon JVM.

## 8. Budgeting RAM for the Entire Build, Not Just `-Xmx`

Suppose a CI runner is allocated 4 GiB of RAM and the project uses:

~~~text
Daemon -Xmx1g
2 test JVMs, each -Xmx512m
1 compiler process that may fork when configured
Kotlin daemon or annotation processor (if any)
Native/metaspace/threads/code cache/direct buffers across all JVMs
Gradle client, OS, container agent, and auxiliary services
~~~

The combined **maximum allowed heap** of the Daemon and two test JVMs already totals roughly **2 GiB**, while **total resident memory can be substantially higher** due to overhead and other processes. You cannot assume "4 GiB leaves 2 GiB free" without measuring.

A practical budgeting approach:

1. Record the actual RAM limit of the host/container—never use total host RAM if the build runs under a cgroup limit.
2. List processes that may run concurrently: Daemon, test forks, compilers/workers, Kotlin daemon, Docker/databases.
3. Reserve headroom for metaspace, native memory, thread stacks, OS, and CI agents.
4. Pick worker slots and fork counts so **peak memory** stays comfortably within budget.
5. Increase parallelism in small increments while watching peak RSS, GC activity, and build duration.

### Two common cases

**CPU idle, plenty of RAM, multiple independent subprojects:** try `--parallel` and raise `--max-workers` from 1 → 2 → 4, measuring whether the critical path shrinks.

**CPU at 100%, low RAM, heavy swapping/GC:** reduce workers or test forks before raising heap further. If a specific JVM genuinely hits heap OOM, raise heap only for that JVM after freeing headroom elsewhere.

### When CI runs multiple jobs concurrently

`org.gradle.workers.max=4` applies **within a single Gradle invocation**. If CI runs three build jobs simultaneously on one runner, each build's limit does not automatically cap all three to 4 workers total. Manage **CI concurrency**, memory limits, and Gradle worker settings together.

Similarly, a laptop running `./gradlew build` in two terminals concurrently may have one or multiple Daemon/build JVMs depending on compatibility and busy state. Use `./gradlew --status` and OS tools to inspect actual processes.

## 9. Benchmarking Optimizations Fairly

Speedups cannot be judged by "this run felt faster than the last one" if the workload changed. Follow a simple discipline:

### Step 1 — Pick the right workload

- `./gradlew help`: measures configuration/startup overhead, not compilation/tests/packaging.
- `./gradlew :app:compileJava`: isolates app compilation and producer tasks.
- `./gradlew :app:test`: focuses on test JVMs and parallel forks.
- `./gradlew :app:bootJar`: measures packaging and runtime dependency assembly.
- `./gradlew build`: full build pipeline with the real task graph.

Never compare `help` under config A against `bootJar` under config B.

### Step 2 — Control variables

For every test pair:

- Use the same Gradle Wrapper, Java version, source revision, dependency versions, and machine/runner.
- Record Daemon warm/cold state, number of running JVMs, and available CPU/RAM.
- Document whether build cache, configuration cache, and incremental build are enabled.
- Do not let the first run download dependencies while the second skips downloads, then credit `--parallel`.
- Change **one group of variables at a time**: Daemon on/off, `-Xmx`, `max-workers`, or test forks.
- Repeat multiple times, exclude or report warm-up separately, and use the **median** rather than cherry-picking one lucky run.

### Step 3 — Use Gradle reports/logs

~~~bash
./gradlew :app:bootJar --profile
./gradlew :app:bootJar --info
./gradlew :app:bootJar --stacktrace
~~~

- `--profile` creates an HTML performance profile in `build/reports/profile/` (exact path per Gradle/build layout); inspect configuration time, tasks, and top cost centers.
- `--info` shows why tasks ran or reported `UP-TO-DATE`; logs are verbose, so avoid turning it on by default in every CI job.
- `--stacktrace` helps debug exceptions; it is **not** a performance metric.
- Gradle offers **Build Scan/Develocity** for detailed bottleneck analysis, though `--scan` can upload build/environment data to an external service; follow organization security policy before running it.

In Gradle 9.x, **Configuration Cache** can introduce stronger parallel task scheduling; when comparing versions, document the exact cache settings used. Do not claim `--no-parallel` forces strictly sequential task execution if the active version/mode does not guarantee it.

### Step 4 — Inspect memory on the exact process

Using JDK tools:

~~~bash
jps -lv
~~~

Locate `GradleDaemon`, test workers, Kotlin daemon, or other Java processes. PIDs and process counts vary at runtime. Inspect JVM flags for a **specific PID**:

~~~bash
jcmd <PID> VM.flags
~~~

`<PID>` is a placeholder to replace with the actual PID—do not type angle brackets `<...>` in the shell. If permissions or JVM versions mismatch, `jcmd` may error. On Windows use Task Manager/Process Explorer; on Linux/macOS use `top`/`ps` to check resident memory. Always read `max heap` directly from the target JVM rather than guessing.

Heap dumps/JFR/JVM diagnostics can contain stacks, paths, and sensitive data; never publish them without authorization.

### Step 5 — Record measurements

A decision table template:

| Run | Daemon | `-Xmx` | Workers | Test forks | Workload | Median time | Peak RAM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | On | 512m | 1 | 1 | `:app:build` | Measured value | Measured value |
| B | On | 1g | 1 | 1 | `:app:build` | Measured value | Measured value |
| C | On | 1g | 2 | 1 | `:app:build` | Measured value | Measured value |
| D | On | 1g | 2 | 2 | `:app:build` | Measured value | Measured value |

This is an **experiment template**, not real benchmark numbers. Pick a configuration only after populating real measurements under identical workloads/cache states and verifying tests did not become flaky.

## 10. Relationship to Other Optimization Mechanisms

Daemon, heap, and parallelism do not replace Gradle's **work-avoidance** optimizations:

| Mechanism | What does it optimize? | Relation to the three setting groups? |
| --- | --- | --- |
| **Up-to-date checks** | Skips tasks when inputs/outputs are unchanged | Reduces work scheduled across workers |
| **Incremental compilation** | Compiles only affected classes | Reduces CPU/heap load |
| **Build Cache** | Reuses task outputs by input fingerprints | Reduces the number of executed tasks |
| **Configuration Cache** | Reuses configuration state and task graph | Cuts configuration time and can alter parallel task execution |
| **Configuration avoidance** | Avoids creating/configuring unneeded tasks | Cuts configuration cost and heap usage |
| **Parallel project execution** | Runs independent work concurrently | Improves throughput at higher RAM/CPU cost |
| **Gradle Daemon** | Reuses build JVM and in-memory state | Reduces startup/warm-up overhead |

Standalone test commands:

~~~bash
./gradlew :app:bootJar --build-cache
./gradlew :app:bootJar --configuration-cache
~~~

Do not enable every option across production builds if plugins are incompatible yet, since configuration-cache errors may require refactoring build logic or task actions. Across newer Gradle releases, defaults and behavior may evolve; check documentation for your **project's exact wrapper version**.

**On parallelism under configuration cache:** modern Gradle can run tasks in parallel even within the same project when configuration cache guarantees state isolation; in that case `--parallel` alone is not the full picture of concurrency. Proper task input/output modeling and shared-state coordination matter more than flipping a single flag.

## 11. Common Failures: Causes and Resolutions

| Symptom | Likely explanation | Next step |
| --- | --- | --- |
| `Gradle Daemon disappeared unexpectedly` | Daemon crashed, OS/cgroup OOM kill, Java crash, or environment failure | Check Daemon log, OS/container OOM events, heap/native memory |
| `OutOfMemoryError: Java heap space` in Daemon | Build process heap too small or build logic/plugins retain too many objects | Tune `org.gradle.jvmargs` after confirming PID; profile build logic |
| `OutOfMemoryError: Metaspace` | Class metadata exceeds Metaspace limit | Check plugin/classloader churn and Metaspace limit |
| `OutOfMemoryError` in test worker | Test JVM lacks heap or too many parallel forks | Tune `Test.maxHeapSize`, `maxParallelForks`, and test allocations |
| `bootRun` runs out of RAM | App JVM forked by `bootRun` has its own limit | Tune `BootRun.jvmArgs`, inspect app allocations |
| Production `java -jar` OOM | Production/container JVM memory limit | Tune runtime memory, not just `gradle.properties` |
| `Cannot allocate memory` / OS kill | Combined heap + native memory + too many workers/processes | Reduce concurrency; build a memory budget |
| Multiple Daemons running | Different Gradle/JDK/JVM args, busy daemon, or IDE/tooling requests | Run `--status`, inspect JDK/Gradle versions and JVM args |
| `--no-daemon` still spawns a JVM once | Gradle needs JVM settings differing from client | Read single-use Daemon notice; do not confuse with persistent Daemon |
| Build time unchanged with `--parallel` | Linear task graph, few independent subprojects, CPU/IO saturated | Inspect critical path and `--profile`; check benchmark validity |
| Parallel runs cause random test failures | Unisolated tests, shared outputs, or fixed ports | Fix isolation/dependencies; cap forks while diagnosing |
| `--max-workers=8` slows CI down | Too many workers contending for CPU/RAM/disk | Lower to 2/4/1 based on measurements |
| Memory config changed, old JVM still used | Reusing Daemon with old settings or inspecting wrong process | Check compatibility/PID; use `--stop` to diagnose |
| `JAVA_OPTS=-Xmx4g` yet Gradle ignores 4 GiB | `JAVA_OPTS` usually targets the client JVM | Set `org.gradle.jvmargs` for the Daemon |
| Java 17 toolchain yet Daemon uses different JDK | Toolchain and Daemon JVM are resolved independently | Check Gradle JVM criteria/`JAVA_HOME`/`org.gradle.java.home` |
| Profile looks fast due to `UP-TO-DATE` tasks | Heavy task execution did not actually run | Standardize cache state and repeat benchmark |
| `--scan` blocked by company policy | Tool can transmit build metadata externally | Use `--profile` or organization-approved tools |

### Common analytical mistake: "More heap always makes builds faster"

Not always true. If the Daemon previously suffered excessive GC due to insufficient heap, a reasonable increase helps. On RAM-starved machines, however, raising heap triggers OS swapping and slows every process down. And if the bottleneck is dependency downloads, compiler CPU, or test databases, Daemon heap fixes none of those root causes.

### Another mistake: "8 cores means `workers.max=8` is always best"

No. For RAM- or I/O-bound tasks, 8 concurrent workers can **reduce** throughput. If tests fork multiple JVMs running full web servers, RAM ceilings and shared resources can matter far more than core count. Start conservatively, measure, then scale up.

## 12. Context-Based Starting Configurations

The examples below are **starting points to test**, not pre-benchmarked optimal choices:

### Study machine or modest-RAM laptop

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx768m -XX:MaxMetaspaceSize=384m
org.gradle.parallel=false
org.gradle.workers.max=1
~~~

Helpful for prioritizing stability when many other apps consume RAM. If a large build hits real heap pressure, adjust upward. `parallel=false` does not cap test forks if test tasks configure them separately.

### Multi-module developer workstation with adequate resources

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=512m
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

A straightforward starting point for parallel project builds; verify cores and RAM are utilized well before raising worker count.

### Memory-constrained CI runner

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Though identical on paper to the developer setup, CI must also account for concurrent jobs, test forks, Docker services, and cgroup memory limits. A 2-vCPU / 4-GiB-RAM runner may require `workers.max=1` and fewer test forks. **Never** size settings purely from total host RAM.

### Should short-lived CI disable the Daemon?

There is no single flag that fits every case. On very short-lived containers/agents, the Daemon is not reused across builds, reducing cross-run warm-up benefits. However, Gradle may still spawn a single-use JVM to satisfy build requirements, and Daemon mode can still aid work within a single build. Test on vs. off on your actual runner type instead of extrapolating from a developer laptop.

## 13. Checklist Before Finalizing Build Tuning

1. **Pin Gradle Wrapper version** and compatible JDK. Never compare commands across two Gradle versions without noting it.
2. **Locate where failures/slowness actually live**: configuration, compilation, tests, packaging, daemon startup, downloads, or environment.
3. **Identify the exact JVM/process** before editing heap: Daemon vs. test worker vs. `bootRun` vs. production.
4. **Start with a realistic memory budget** for your cgroup/CI runner, leaving native/OS headroom.
5. **Keep the Daemon enabled** for reuse unless clear evidence/measurements justify turning it off.
6. **Pick a modest worker count** and enable parallel execution only when meaningful independent work exists.
7. **Tune test forks separately** and verify isolation before raising parallelism.
8. **Keep dependency/task graphs accurate** with declared inputs/outputs rather than relying on accidental ordering.
9. **Measure one change at a time on an invariant workload**, separating cold/warm caches, repeating runs, and checking peak RAM.
10. **Protect sensitive data** in heap dumps, logs, and Build Scans; never expose internal build metadata publicly.
11. **Verify the Spring Boot artifact runs** via `java -jar` after builds; speeding up a build that emits a broken archive is not a valid optimization.
12. **Document verified settings**, machine/runner specs, and rationale so teammates do not have to rediscover them from scratch.

## 14. Self-Check Questions

**Question 1.** Does `org.gradle.jvmargs=-Xmx2g` give `java -jar app.jar` in production a 2 GiB heap?

**Answer:** No. That property controls the Gradle build/Daemon JVM. Production runtimes take their own JVM arguments from the launch command, container, or environment.

**Question 2.** Is `JAVA_OPTS=-Xmx4g` enough to make the Gradle Daemon use 4 GiB?

**Answer:** No in standard Daemon mode. `JAVA_OPTS` targets the client JVM; set `org.gradle.jvmargs` for the build/Daemon JVM.

**Question 3.** Why does `--no-daemon` sometimes still create a Daemon-like process?

**Answer:** When client JVM settings do not meet the build's requirements, Gradle may start a **single-use Daemon** that stops after the build instead of reusing a persistent Daemon.

**Question 4.** Is a build with `--parallel --max-workers=8` always faster than `--max-workers=2`?

**Answer:** No. It depends on independent tasks, CPU, RAM, I/O, locks/shared resources, and test fork counts. Measure on the real workload.

**Question 5.** Why does `org.gradle.parallel=true` help in a multi-project build yet often not in a single-project build?

**Answer:** Parallel project execution runs tasks from **independent projects** simultaneously, whereas a single-project build may lack those independent branches. Newer configuration-cache modes have different intra-project parallel semantics, so check your exact Gradle version/mode.

**Question 6.** Tests hit `OutOfMemoryError` while the Daemon still has ample heap; what should you adjust first?

**Answer:** Identify the failing test JVM, tune `Test.maxHeapSize` or reduce `maxParallelForks`, and check for leaks and total RAM. Do not blindly raise Daemon heap.

**Question 7.** Does `org.gradle.workers.max=2` limit the total number of JVMs on the machine to 2?

**Answer:** No. It limits worker scheduling capacity inside one Gradle build; client, daemon, forked processes, and other builds/CI jobs can still coexist.

**Question 8.** Why does changing `-Xmx` spawn a new Daemon?

**Answer:** A JVM cannot resize max heap after startup; a running Daemon with old JVM arguments is incompatible with the new requirements, so Gradle starts a matching Daemon.

**Question 9.** What metrics are needed to conclude that increasing workers actually helped?

**Answer:** Median build duration on identical tasks/workloads, peak RSS/container memory, CPU saturation, I/O contention, GC activity, and test stability—with unrelated cache/download differences eliminated.

**Question 10.** A test suite turns flaky only when parallel execution is enabled; should you disable parallelism forever?

**Answer:** You can disable it temporarily for stability, but you should fix shared filesystems, fixed ports, shared databases/test data, and task dependencies. Parallelism merely exposed a pre-existing race condition.

## 15. Official References

- Gradle — [Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): Client/Daemon JVMs, reuse, `--status`, `--stop`, single-use Daemon, and JVM criteria.
- Gradle — [Configuring Gradle](https://docs.gradle.org/current/userguide/config_gradle.html): `org.gradle.jvmargs`, `JAVA_OPTS`, and JVM heap examples.
- Gradle — [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.parallel`, `org.gradle.workers.max`, `org.gradle.java.home`, and properties.
- Gradle — [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--parallel`, `--max-workers`, `--profile`, and Daemon flags.
- Gradle — [Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html): workers/parallelism, bottlenecks, and profiling.
- Gradle — [Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test.maxHeapSize`, `maxParallelForks`, and test worker JVMs.
- Gradle — [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration caching and parallel task execution in cached mode.
- Gradle — [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): module independence and task/dependency graphs.
- Spring Boot — [Gradle Plugin: Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar` and artifact packaging.
- Spring Boot — [Gradle Plugin: Running](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` and JVM/application arguments.

**Remember:** the Gradle Daemon avoids repeated build JVM startup, `org.gradle.jvmargs` sizes **the build JVM specifically**, and `--parallel`/`--max-workers` regulate **concurrent work**. Effective optimization means **measuring the right process, leaving enough headroom, scaling concurrency carefully, and verifying both the build and the executable Spring Boot archive**, rather than blindly cranking every number higher.
