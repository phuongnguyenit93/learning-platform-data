# Measuring Build Times Before Choosing Optimization Strategies

## 1. The Problem: "Slow Build" Is Not Enough to Know What to Fix

A team working on a Spring Boot application might say "Maven takes over two minutes," "Gradle got faster right after enabling the cache," or "CI runs too long." Those remarks do not show **which part is actually taking time**, whether the runs had **the same conditions**, or whether a change produces a **measurable improvement**.

For example, the first time you run **./gradlew build**, it may have to download the Gradle distribution and dependencies, start the daemon, configure the project, compile, run tests, and package the JAR. The second run may return **UP-TO-DATE** for most tasks. Comparing the durations of those two runs and concluding that a single change in build.gradle made the build ten times faster is wrong if the caching conditions differed.

**Core principle:** before turning on parallel builds, configuration cache, build cache, increasing heap, splitting modules, or skipping tests, measure **the exact same work** under **the exact same conditions**, find the bottleneck, and verify your hypothesis with multiple measurements.

A good measurement must answer:
- **What is being measured?** A clean build, incremental build, no-change build, CI verification, or packaging only?
- **Where is it measured?** A laptop, a CI runner, the same JDK, CPU, RAM, disk, and network, or different ones?
- **How long does it take?** Wall-clock elapsed time, task/goal time, startup, configuration, dependency resolution, tests, or packaging?
- **Does each run perform the exact same work?** Do tests actually run? Do tasks hit the cache? Are dependencies downloaded?
- **Is the conclusion stable?** Are there multiple samples, a median, and a measure of variance?
- **What is changing?** Only one setting at a time, or are you changing the JDK, Spring Boot version, cache, worker count, and test suite all at once?

This lesson belongs to the **Build Optimization** group: the goal is **measure first, analyze second, and optimize last**.

## 2. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **end-to-end** time from Maven plugin goal and Gradle task durations.
2. Design four benchmark scenarios: **fresh environment**, **clean build**, **no-change build**, and **incremental change**.
3. Measure Maven using its **Total time** report, shell/PowerShell stopwatches, and reconcilable logs.
4. Measure Gradle using **--profile**, **Build Scan** (when permitted), task outcomes, and full command timing.
5. Avoid confusing **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**, and **SKIPPED** with actual work performed.
6. Compute the median, spread, and percentage improvement from concrete samples.
7. Select a hypothesis from the data: dependency/network, startup/configuration, Java compilation, annotation processing, tests, packaging, cache, or machine resources.
8. Set up controlled before/after measurements, avoiding false optimizations caused by skipping tests or using two different build scopes.
9. Record a baseline table with enough detail for comparisons on CI and over time.

## 3. What Makes a Timing Metric Meaningful?

### 3.1. Wall-clock elapsed time: the primary metric

Measure the elapsed time from **invoking the command** until the process exits successfully or fails:

~~~text
T_wall = t_finish - t_start
~~~

For example, a single build invocation takes 105 seconds by stopwatch. That number is close to what a developer has to wait when running that exact command, including part of the overhead from JVM startup, the Wrapper script, disk/network I/O, and console log processing.

**Do not substitute CPU time for wall-clock time:** a build can wait on network, I/O, or locks, so CPU time does not reflect user wait time. Conversely, a multi-process build can have **total CPU time greater than wall-clock time** because multiple cores run in parallel.

Note: the duration reported in Maven **Total time** and Gradle **BUILD SUCCESSFUL in ...** is build-tool-reported timing, which may not match an external stopwatch wrapping the entire invocation. An external stopwatch may include Wrapper bootstrap, shell/JVM initialization, and distribution downloads. Use a **consistent clock type** for both baseline and candidate.

### 3.2. Phase-by-phase breakdown helps locate bottlenecks

A typical Java/Spring Boot pipeline includes:

~~~text
Wrapper / Java startup
       |
Build initialization and configuration
       |
Dependency/plugin resolution
       |
Source generation + resource processing
       |
Java/Kotlin compilation
       |
Unit tests / integration tests / quality checks
       |
Spring Boot JAR/WAR packaging
       |
Artifacts, reports, cleanup, and CI post-steps
~~~

In Gradle, `--profile` and Build Scan help break down **startup**, **configuration**, **dependency resolution**, **task execution**, and per-task details. With Maven, the CLI typically prints each lifecycle plugin goal along with **Total time** at the end of the build; getting an accurate per-goal duration breakdown requires appropriate additional profiling/instrumentation or measuring controlled phases separately.

**An important warning:** in builds with parallelism, the sum of task durations **does not necessarily equal** end-to-end time. Two tasks running concurrently for 30 seconds each can consume 60 seconds of total task time while contributing only about 30 seconds to wall time. Do not add up every task duration and call it build time; look at the **critical path** and degree of parallelism.

### 3.3. Which duration is the target metric?

| User concern | Typical command/measurement | Why |
| --- | --- | --- |
| Developer edits one Java line and tests quickly | Maven test or Gradle test, after a small change | High iteration frequency |
| Developer re-runs without changing code | Maven verify, Gradle build (no-change) | Measures caching/up-to-date behavior |
| CI validates a pull request | Maven clean verify or Gradle clean build | Must preserve verification scope |
| CI builds an executable artifact | Maven package/repackage or Gradle bootJar/build | Measures the actual delivery path |
| Fresh CI runner without caches | Fresh checkout + deps/distribution download + build | Measures cold start and network |
| Multi-module build | Selected Maven reactor, Gradle task paths | Separates whole-repo from targeted modules |

If the goal is **reducing CI verify time**, measuring only **bootJar** is insufficient because it may **not run tests**. If the goal is **developer feedback while editing code**, measuring a full-repo clean build may not be representative. Pick the scenario according to the experience you want to improve, not the command that gives the smallest number.

## 4. Four Scenarios That Must Be Measured Separately

### 4.1. Fresh environment: no caches populated yet

A **fresh build** is a build on a new runner/workspace as you define it, which may not yet have downloaded the Gradle distribution, Maven/Gradle plugins, or dependencies, and has no build outputs.

Characteristics:
- Network, repository mirror/proxy, DNS, TLS, and download speed may dominate the duration.
- The Gradle daemon is not yet warmed up, and the JVM has no benefit from previous runs.
- The Maven local repository or Gradle User Home may be empty if the runner is truly fresh.
- This applies to **ephemeral CI agents** or initial setup experience.

**Reliable way to measure:** use a CI runner/container image or a dedicated test environment prepared identically for A/B runs. Do not delete the user's **~/.m2** or **~/.gradle** to simulate a cold run: doing so can slow down other projects, lose caches, and alter conditions unintentionally.

### 4.2. Clean build: deletes outputs, not necessarily dependency caches

~~~bash
./mvnw -B -ntp clean verify
./gradlew --console=plain clean build
~~~

**clean** removes the corresponding build outputs; it **does not mean** deleting the Maven repository in **~/.m2/repository** or the Gradle dependency cache in **~/.gradle/caches**. The Gradle build cache can also restore task outputs after a clean if enabled.

Therefore, label it accurately: **clean output, warmed dependency caches** or **clean output, build-cache enabled**, rather than calling every clean run a cold build.

Use this scenario if you want to measure compile/test/package work from clean outputs, while still recording cache settings and environment.

### 4.3. No-change warm build: exact re-run with no input changes

~~~bash
./mvnw -B -ntp verify
./mvnw -B -ntp verify

./gradlew --console=plain build
./gradlew --console=plain build
~~~

Each command pair represents **two consecutive runs** of one tool (choose Maven or Gradle). Do not edit sources, build scripts, system properties, or the environment between the two runs.

With the Gradle Java plugin, the second run can mark many tasks **UP-TO-DATE** or **FROM-CACHE**. Standard Maven does not have the exact same default task-output caching mechanism as Gradle; some plugins have their own incremental checks, though Maven may still execute goals/tests/packaging. If the project uses the **Maven Build Cache Extension**, that is an optional component and must be recorded separately in the baseline.

**Do not use no-change time to predict real compile time when editing source code.** It is a distinct scenario that must be measured separately.

### 4.4. Incremental build after a small change

For example, modify one method in **src/main/java**, keeping the dependency graph unchanged, then run the usual command:

~~~bash
./mvnw -B -ntp test
./gradlew --console=plain test
~~~

Ideally, test both a **non-public-ABI change** and a **public-ABI change** to see which modules/tasks must recompile. In projects with generated sources/annotation processors, a small edit can widen invalidation scope.

**Procedure:** start from the same commit, apply a deterministic patch, measure the build run, revert the patch, and restore the exact same conditions for the next run. Do not measure the first run of A in a warm workspace and then measure B in a differently modified workspace without resetting. Especially with Gradle incremental compilation/build cache, execution order and output state affect the outcome.

## 5. Establishing a Repeatable Baseline

### 5.1. Minimum record

Before measuring, record:

| Group | What to record |
| --- | --- |
| Source code | Commit hash/branch, uncommitted diff, module scope |
| Build tool | Maven or Gradle, Wrapper version, plugin versions |
| JDK | `java -version` and the JVM actually used by Maven/Gradle |
| Command | Full command including tasks/phases, flags, profiles, test filters |
| Machine | OS, CPU cores, RAM, disk type, CI runner type, container limits |
| Network | Online/offline, repository mirror, whether caches are warm |
| Cache | Gradle build cache/configuration cache, daemon, Maven local repo/extension |
| Scenario | Fresh/clean/no-change/incremental; which warm-up run number |
| Results | Exit status, wall time, report paths, task outcomes, tests summary |
| Runtime environment | CI job identifier, timestamp, machine load, antivirus/background jobs |

A result consisting solely of "98 seconds" without command/commit/cache state is not reliable enough to guide decisions. If A/B runs on runners with different specs or changes the number of test cases, the difference may not come from the optimization.

### 5.2. How many samples are needed?

A single measurement only gives one point-in-time observation. Collect at least **5 valid samples** per option under stable conditions to observe variance; if the expected gain is only a few percent or the environment is noisy, take more samples.

**Warm up** 1–2 runs for warm/daemon benchmarks so the JVM, Gradle daemon, and caches reach the target state; do **not** include those warm-up runs in the measurements if the goal is steady-state performance. Conversely, for fresh CI cold starts, **the very first cold run is the subject of measurement**, and multiple independent fresh environments are needed to estimate the cold-time distribution.

Save **all** samples, not only the fastest one. You can use the **median** as the representative value because it is resilient to an occasional slow outlier; use min/max or p25–p75 to show spread. With only 5 samples, do not present p95/p99 as an accurate SLA forecast.

## 6. Measuring Maven on Linux/macOS

### 6.1. Reading Maven-reported duration

Run an actual build, for example:

~~~bash
./mvnw -B -ntp clean verify
~~~

The flags:
- **-B**: Maven batch mode, suitable for automation and non-interactive logs.
- **-ntp**: disables download/upload transfer progress lines, keeping logs cleaner.
- **clean verify**: deletes outputs and executes the lifecycle through `verify`, including tests and packaging per the POM.

At the end of a successful build, Maven typically prints lines similar to:

~~~text
[INFO] BUILD SUCCESS
[INFO] Total time:  42.817 s
[INFO] Finished at: 2026-11-09T02:00:00Z
~~~

**This is only an illustrative log**, not an actual measurement from a project. Maven's **Total time** is handy for quick observation; to compare total user wait time, add an external stopwatch around the CLI. For multi-module projects, Maven also prints a reactor summary, though the standard summary **does not provide fine-grained profiling for every goal by execution time**.

### 6.2. Using shell time as an external clock

On Linux/macOS:

~~~bash
time -p ./mvnw -B -ntp clean verify
~~~

External output typically looks like:

~~~text
real 43.21
user 66.78
sys 2.91
~~~

These are also **hypothetical illustrative numbers**. **real** is elapsed wall-clock time, **user** is CPU time in user mode, and **sys** is CPU time in kernel mode. On multi-process/multi-threaded runs, **user** can exceed **real**. The **time -p** syntax is supported by many shells/Unix tools; exact output details depend on the shell and OS.

If measuring a warm build, replace **clean verify** with **verify** and document the scenario; do not compare warm results directly against a clean baseline.

### 6.3. Linux script to collect 5 clean-build samples, keeping per-run logs

For **Linux with GNU /usr/bin/time**, create **benchmark-maven.sh** outside or inside the project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

RESULT_DIR="$(cd .. && pwd)/benchmark-results-maven"
mkdir -p "$RESULT_DIR"

for run in 1 2 3 4 5; do
    echo "Maven clean verification: run $run"
    /usr/bin/time -p -o "$RESULT_DIR/run-$run.time"         ./mvnw -B -ntp clean verify         > "$RESULT_DIR/run-$run.log" 2>&1
done

echo "Completed 5 successful Maven runs."
echo "Timing and build logs: $RESULT_DIR"
~~~

How to run:

~~~bash
chmod +x benchmark-maven.sh
./benchmark-maven.sh
~~~

In this script, **set -e** stops the loop if any build fails; that prevents accidentally recording a FAIL run as a "fast" sample. Output logs and time files are placed **outside the project root** to avoid affecting tasks that scan repository inputs. **/usr/bin/time -p -o** here is **GNU time** syntax, not a portable option across all macOS setups. On macOS, you can use shell **time -p** and redirect stderr appropriately.

Note that the script runs **5 clean builds**, during which dependencies and tool distributions may become progressively warmed. If you want to benchmark **steady-state clean with warm deps**, prepare/warm caches beforehand and record that condition. If you want to benchmark **fresh cold**, do not use a loop in the same workspace as five independent cold samples.

**The clean operation deletes build outputs** and can take time/I/O. Only run it in a workspace where you are allowed to clean, never on a production job sharing outputs with another process.

### 6.4. Do not use skipTests to "prove" an optimization

The command:

~~~bash
./mvnw -B -ntp clean verify -DskipTests
~~~

is typically faster because **Surefire does not execute unit tests** (test sources are still compiled by the compiler), but that **changes verification scope** rather than speeding up the same build.

**-Dmaven.test.skip=true** also skips test compilation and execution depending on supporting plugins, making it even further from a baseline with tests. When evaluating a build optimization, **never compare a command with tests against a command skipping tests** and claim the compiler, compilation algorithm, or cache improved. If you have a fast-packaging use case with skip, record a **separate** baseline row and explicitly note its limited scope.

## 7. Measuring Maven on Windows/PowerShell

The Windows Maven Wrapper is typically **mvnw.cmd**. To time the full command and verify its exit code, use PowerShell:

~~~powershell
$clock = [System.Diagnostics.Stopwatch]::StartNew()
& .\mvnw.cmd -B -ntp clean verify
$code = $LASTEXITCODE
$clock.Stop()

Write-Host ("elapsed={0:F3}s; exit={1}" -f $clock.Elapsed.TotalSeconds, $code)
if ($code -ne 0) { exit $code }
~~~

**Stopwatch** uses the .NET timer for elapsed time; no external PowerShell module is needed here. **$LASTEXITCODE** captures the `.cmd` command's exit code. When the code is non-zero, the example exits with that code; do not treat a failed build as a successful benchmark sample.

Measure Gradle similarly by replacing the invocation line with:

~~~powershell
& .\gradlew.bat --console=plain clean build
~~~

The two snippets are **alternatives**; do not run Maven and then Gradle in the same measurement if the goal is to compare the same command. On Windows, filesystem/cache paths, antivirus scanning, and process startup can differ from Linux, so results are not directly comparable when deciding optimizations for a specific platform.

You can use **Measure-Command**, but if you want to check the exit code and capture stdout/stderr and command metadata, the explicit Stopwatch version clearly shows the exact timing boundary.

## 8. Measuring Gradle via CLI and Local Profile

### 8.1. Start from a real command

Example Spring Boot Gradle project:

~~~bash
./gradlew --version
./gradlew --console=plain clean build
./gradlew --console=plain build
~~~

The second command is a **clean build**, and the third is a **no-change/warm build** if no inputs changed. Gradle typically prints a summary:

~~~text
BUILD SUCCESSFUL in 18s
9 actionable tasks: 6 executed, 3 up-to-date
~~~

The lines above are **illustrative only**; actual task counts, duration, and task outcomes depend on the project and Gradle version. Inspect **which tasks actually executed versus UP-TO-DATE/FROM-CACHE** instead of looking at a single number.

**--console=plain** reduces progress UI/ANSI sequences in logs, making them easier to store and read in CI. It is not a flag that speeds up builds by a fixed amount.

### 8.2. Generate a local --profile report without uploading a scan

~~~bash
./gradlew --console=plain build --profile
~~~

Gradle typically generates an HTML report under:

~~~text
build/reports/profile/
    profile-<timestamp>.html
~~~

Here **<timestamp>** is a filename part generated by Gradle, not literal characters to type. In multi-project builds, the report usually lives under **build/reports/profile** of the **root project**. The report displays startup/configuration/task execution by category, though with less detail than a Build Scan.

To measure a clean run with profiling:

~~~bash
./gradlew --console=plain clean build --profile
~~~

**--profile** can add slight overhead from collecting and writing the report. When doing A/B comparisons, use the same option on both sides; when directly measuring user wait time, run normally (without a profiler) and use a separate profiled run for **diagnosis**. Do not mix an A sample with `--profile` and a B sample without `--profile` without noting the difference.

Documentation: https://docs.gradle.org/current/userguide/inspect.html

### 8.3. Reading Gradle's breakdown properly

In the profile, pay attention to:
- **Startup:** JVM/Gradle startup, daemon, init scripts, wrapper distribution if needed.
- **Settings / Configuration:** evaluating `settings.gradle`, `build.gradle`, applying plugins, configuring projects/tasks.
- **Dependency resolution:** downloading/resolving module versions and metadata depending on the build.
- **Task execution:** `compileJava`, `processResources`, `test`, `bootJar`, and other tasks.
- **Task outcomes:** when a task is `UP-TO-DATE` or `FROM-CACHE`, action execution time can differ dramatically from a rebuild.

If configuration takes a large share of time on a **no-change build**, inspect plugins/configuration scripts and consider **configuration cache** after verifying compatibility. If tests take 70% of the time, increasing the compiler worker count may not address the main issue.

### 8.4. Build Scan: richer insight, but shares metadata

If security policy and repository owners permit:

~~~bash
./gradlew --console=plain build --scan
~~~

Build Scan creates a record with performance details, task timeline, environment, dependencies, and build events. The command may prompt for terms acceptance; the scan may be **published to an external service or a Develocity server** depending on configuration.

**Do not enable --scan on sensitive internal projects without permission.** Build Scan can contain build/repo/machine metadata, paths, task names, and other information collected by plugins. If you must keep evidence local only, use **--profile**; if your company has an approved internal Develocity instance, follow the organization's server and data policies.

A Build Scan can help uncover:
- Startup vs configuration vs execution durations.
- Task timeline and critical path.
- Task cache hits and up-to-date behavior.
- Remote/local cache and dependency resolution bottlenecks.
- Plugins or build scripts spending excessive time during configuration.

Source: https://docs.gradle.org/current/userguide/build_scans.html

### 8.5. --dry-run is not for measuring build execution

~~~bash
./gradlew build --dry-run
~~~

This command **previews the task plan** without executing normal task actions. If `--dry-run` finishes very quickly, it does **not** prove the compiler, tests, or Spring Boot packaging have become comparably fast. Even so, the configuration phase may still execute and trigger build-script side effects.

Use `--dry-run` when you want to inspect the task graph or see which tasks remain selected; use a **real build** when measuring build experience.

## 9. Four Gradle Factors That Easily Skew Benchmarks

### 9.1. UP-TO-DATE does not mean the compiler ran faster

If task **:compileJava UP-TO-DATE**, Gradle determined the inputs/outputs match and typically **did not invoke the Java compiler** during that run. That is incremental/up-to-date checking at work, not proof that **javac** itself is faster.

If you want to force all runnable tasks in the graph to execute:

~~~bash
./gradlew --console=plain test --rerun-tasks
~~~

According to Gradle documentation, **--rerun-tasks** bypasses up-to-date checks and the build cache to force task actions to re-run; it resembles **clean test** in forcing re-execution, but **does not delete build outputs** like `clean`. Thus **--rerun-tasks** and **clean** are not completely identical, especially with custom tasks.

### 9.2. Build cache and dependency cache are two distinct mechanisms

- **Dependency cache** stores downloaded artifacts/metadata from repositories.
- **Build cache** stores **outputs of eligible tasks** keyed by matching input fingerprints.
- **UP-TO-DATE** is the result of checking inputs/outputs in the current workspace.
- **Configuration cache** stores the result of the **configuration phase** for compatible builds.

Commands controlling the Gradle build cache:

~~~bash
./gradlew build --build-cache
./gradlew build --no-build-cache
~~~

With build cache enabled, `clean` still deletes **build/**, yet tasks can restore outputs with **FROM-CACHE**. Therefore, benchmarking a **clean build with cache** differs from a clean build with **--no-build-cache**.

**Do not delete ~/.gradle/caches** to benchmark without an isolated workspace/CI setup. Running **--no-build-cache** does not mean the dependency cache is disabled too.

### 9.3. Configuration cache and the Gradle daemon

~~~bash
./gradlew build --configuration-cache
./gradlew build --no-configuration-cache
~~~

Configuration cache reduces configuration work when plugins/scripts/tasks are compatible. It **does not automatically make test methods faster** and does not replace the build cache. The first run that stores the cache and subsequent reuse runs must be measured as **distinct scenarios**; if configuration is invalidated, later runs must reconfigure.

The Gradle daemon avoids JVM startup overhead and makes warm environments faster. **--no-daemon** changes the startup/daemon model and is not a "fairer measurement" choice in every case. If production CI uses the daemon, benchmarks should reflect that policy; if measuring first-run overhead, explicitly record whether a daemon was already running.

### 9.4. Parallel tasks and the critical path

In multi-project builds, Gradle can run some tasks in parallel (when configuration and the task graph allow). Enabling parallelism can increase total task CPU time even as wall-clock time drops. Therefore, before enabling **--parallel**, inspect the critical path and potential RAM/CPU/disk contention.

Only compare options using **the exact same test suite, same source, and same hardware**. If parallelism makes the test suite flaky due to shared databases/ports, saving a few seconds is not worth losing reliability.

## 10. Does Maven Have Caching Like Gradle?

Standard Maven uses a **local repository** to store downloaded dependencies/plugins so later builds avoid re-downloading them. This is **different** from Gradle's task-output caching.

Maven has the **Apache Maven Build Cache Extension**, but it is an **optional extension** that must be installed/configured/evaluated, not a default task-output cache built into every Maven 3 build. Extension documentation states that current releases require **Maven 3.9.0+** and explicit extension registration, with optional remote caching when appropriate.

Do not compare a Maven 3.6 baseline without the extension against Maven 3.9 with the extension and claim "Maven core is X% faster"; you changed the caching mechanism. If evaluating the extension, measure separately:
- Without the extension.
- Extension enabled with a cold cache.
- Extension enabled with a cache hit.
- Fresh CI agent with a shared remote cache.

**Remember to verify outputs and tests:** an incorrect input fingerprint in the cache can reuse an invalid artifact. The Maven Build Cache Extension is opt-in, and project maintainers are responsible for verifying correctness.

Source: https://maven.apache.org/extensions/maven-build-cache-extension/

## 11. Sample Spring Boot Project as a Benchmark Target

A small project helps practice commands and read outcomes without needing a database, Docker, or external services. **It does not represent the scale of an enterprise project**; do not use timings from a tiny example to predict gains in a multi-million-line repository.

Use **Java 17**, Spring Boot **3.5.16**, and either Maven or Gradle. Spring Boot 3.5.16 was released on **2026-06-25** and is the final OSS release of the 3.5 line; this lesson chooses it for a stable example, not as a recommendation for a branch currently receiving OSS fixes. New projects must select a supported version based on security and compatibility requirements.

### 11.1. File layout

~~~text
build-timing-lab/
├── pom.xml or build.gradle (+ settings.gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/... (if Maven)
├── gradlew / gradlew.bat / gradle/wrapper/... (if Gradle)
└── src/
    ├── main/java/com/example/timing/
    │   ├── TimingApplication.java
    │   └── MathOperations.java
    └── test/java/com/example/timing/
        └── MathOperationsTest.java
~~~

Wrappers must be generated with the appropriate tool such as Spring Initializr or the Wrapper plugin; writing a POM/build script does not create the Wrapper automatically.

### 11.2. Self-contained, deterministic Java source

File **src/main/java/com/example/timing/MathOperations.java**:

~~~java
package com.example.timing;

public final class MathOperations {
    private MathOperations() {
    }

    public static int sumFirst(int n) {
        if (n < 0 || n > 1000) {
            throw new IllegalArgumentException("n must be in 0..1000");
        }

        int result = 0;
        for (int value = 1; value <= n; value++) {
            result += value;
        }
        return result;
    }
}
~~~

File **src/main/java/com/example/timing/TimingApplication.java**:

~~~java
package com.example.timing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TimingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimingApplication.class, args);
        System.out.println("sum=" + MathOperations.sumFirst(10));
    }
}
~~~

File **src/test/java/com/example/timing/MathOperationsTest.java**:

~~~java
package com.example.timing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MathOperationsTest {
    @Test
    void sumOfFirstTenNumbers() {
        assertEquals(55, MathOperations.sumFirst(10));
    }
}
~~~

When running the non-web Spring Boot application with the **spring-boot-starter** dependency, the console may include Spring logging lines, while the line printed by this source code after the context starts is:

~~~text
sum=55
~~~

The **sumOfFirstTenNumbers** test verifies 1 + 2 + ... + 10 = 55; when executed properly via JUnit Jupiter, it will PASS. Because the demo has no embedded web server, do not expect HTTP endpoints or a process listening on port 8080.

### 11.3. Complete Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>build-timing-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The Spring Boot starter parent manages dependency versions and Maven plugins. **spring-boot-maven-plugin** is declared so parent-managed repackaging produces an executable JAR during `package`. Do not add **-DskipTests** in baseline measurements if the goal is full verification.

Commands:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
./mvnw -B -ntp verify
java -jar target/build-timing-lab-1.0.0.jar
~~~

Read **Total time** at the end of both builds, then time externally with **time -p**. The second result may differ because the Maven local repository is already warm, but do not claim Maven skips all compilation/tests like Gradle up-to-date checks.

### 11.4. Complete Gradle Groovy DSL

File **settings.gradle**:

~~~groovy
rootProject.name = 'build-timing-lab'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Using the Java plugin and Spring Boot 3.5.16, Gradle Wrapper 8.14 is a valid choice for the example. The dependency-management plugin imports the Spring Boot BOM. If a project does not use that plugin, it must declare the BOM with an appropriate Gradle native platform rather than omitting all versions.

Commands:

~~~bash
./gradlew --version
./gradlew --console=plain clean build
./gradlew --console=plain build
./gradlew --console=plain build --profile
java -jar build/libs/build-timing-lab-1.0.0.jar
~~~

The first **build** run and the repeated **build** run can produce different task outcomes. The **--profile** report is generated under **build/reports/profile** when Gradle supports that option; inspect the HTML report to see how much overhead belongs to startup, configuration, or tasks.

### 11.5. What makes this example useful yet unrepresentative?

**MathOperations** takes almost no effort to compile or test, so most of the time may come from startup/configuration/repository resolution and framework/plugin overhead. If you add 5,000 test cases or annotation processors, the bottleneck may be completely different. When bringing measurements into a real project, still record test count, active profiles, submodule count, and dependency cache state.

## 12. Computing the Median and Percentage Improvement

### 12.1. An illustrative dataset

Suppose you measured **the exact same clean verification workload**, on the same runner/JDK/cache conditions, for five valid runs of each configuration:

| Run | Baseline (seconds) | Candidate (seconds) |
| --- | ---: | ---: |
| 1 | 120 | 94 |
| 2 | 123 | 96 |
| 3 | 118 | 97 |
| 4 | 121 | 95 |
| 5 | 120 | 98 |
| **Median** | **120** | **96** |

The numbers above are **hypothetical data for learning how to process results**, not an actual Maven or Gradle benchmark.

After sorting:

~~~text
Baseline: 118, 120, 120, 121, 123 -> median = 120 s
Candidate: 94, 95, 96, 97, 98   -> median = 96 s
~~~

Percentage reduction in time:

~~~text
Improvement = (T_baseline - T_candidate) / T_baseline * 100%
            = (120 - 96) / 120 * 100%
            = 20%
~~~

That means the candidate saves **24 seconds** on a typical build and **20%** compared to the baseline median. Do **not** report that the build is 24% faster by dividing 24/96; the denominator for "time reduction vs. baseline" is **120**.

If the candidate has a median of **130 seconds** against a baseline of **120 seconds**, plugging into the formula yields a negative value (regression). An improvement smaller than background variance requires more samples and noise investigation before drawing conclusions.

### 12.2. Java 17: program to compute median from measurements

Create a standalone file **BuildTimingStats.java** outside the Spring Boot app or in a separate tools directory:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class BuildTimingStats {
    private BuildTimingStats() {
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Provide one or more durations in seconds");
        }

        double[] durations = Arrays.stream(args)
                .mapToDouble(Double::parseDouble)
                .sorted()
                .toArray();

        for (double duration : durations) {
            if (!Double.isFinite(duration) || duration < 0) {
                throw new IllegalArgumentException(
                        "Durations must be finite and non-negative");
            }
        }

        int n = durations.length;
        double median = n % 2 == 1
                ? durations[n / 2]
                : (durations[n / 2 - 1] + durations[n / 2]) / 2.0;

        System.out.printf(
                Locale.US,
                "n=%d min=%.1f s median=%.1f s max=%.1f s%n",
                n, durations[0], median, durations[n - 1]);
    }
}
~~~

Compile/run with Java 17:

~~~bash
javac --release 17 BuildTimingStats.java
java BuildTimingStats 120 123 118 121 120
java BuildTimingStats 94 96 97 95 98
~~~

Exact stdout of the two **java** commands (excluding `javac`, which produces no stdout on success):

~~~text
n=5 min=118.0 s median=120.0 s max=123.0 s
n=5 min=94.0 s median=96.0 s max=98.0 s
~~~

The code uses **Double.parseDouble**, so inputs must be dot-separated decimals (e.g., **42.5**). It sorts the samples and computes the median; **it does not collect build times itself**, drop outliers arbitrarily, compute confidence intervals, or treat five samples as an accurate p95 measurement.

### 12.3. Why is the median usually useful?

If four builds take 40–42 seconds but one takes 180 seconds due to antivirus or network downloads, the **mean** can be heavily skewed. The **median** gives a better view of the typical experience. However, that 180-second run may be a very real CI occurrence; do not delete it from the dataset—investigate it and describe **tail latency** separately.

Do not let a good median hide:
- Build failures/flaky tests.
- Spikes caused by repository outages.
- Performance regressions on lower-spec runners.
- Higher CPU/RAM cost of a faster configuration.

## 13. An A/B Workflow for Optimization Changes

### Step 1. Define an invariant workload

For example, if you want to speed up CI pull-request verification:

~~~text
Tool: Gradle Wrapper 8.14, JDK 17
Command: ./gradlew --console=plain clean build
Scope: entire project, same test suite
Runner: same machine type, CPU/RAM/container limits
Caches: build cache OFF, configuration cache OFF
Result: only accept BUILD SUCCESSFUL and a valid test report
~~~

Actual commands/flags and conditions must be recorded in the baseline. These are **example parameters**, not a recommendation to disable caching on every CI. If your current CI uses caches, **measure the baseline in the exact actual CI state** and use a separate cache-OFF test when isolating root causes.

### Step 2. Collect the baseline

Run warm-ups when the scenario calls for them, then measure at least five runs; save logs and task outcomes. Record median, min/max, failure count, and reports/profiles.

### Step 3. Analyze the bottleneck

For example, in Gradle `--profile`, you see configuration taking 35 seconds while the test task takes only 10 seconds. The hypothesis may be overly heavy build scripts/plugin configuration; do not optimize JUnit before clarifying that root cause.

With Maven, if the end-of-build log shows 120 seconds total without a detailed breakdown, try **timing phases** and inspecting test reports:
- Run **mvn test** to measure through the `test` phase.
- Run **mvn package** to measure through packaging.
- Review goals, annotation processors, and extra integration tests bound in `verify`.
  
**Be careful:** do not subtract **mvn package − mvn test** and call it exact packaging time when the two commands had different cache states, different test execution, or different profiles. For proper profiling, use appropriate instrumentation or measure under controlled conditions.

### Step 4. Change exactly one variable

For example, enable **configuration cache** alone, or fix one slow Gradle plugin configuration, or split the integration-test suite out of the dev loop (if changing test policy is approved). Do not simultaneously increase RAM, switch JDKs, upgrade Spring Boot, and enable caches, then try to attribute the gain to one factor.

### Step 5. Collect candidate samples

Ensure the same commit/semantically identical source workload, same hardware, and identical conditions differing only in the chosen optimization. For cache benchmarks, define cold cache-fill runs and warm cache-hit runs separately; report both numbers.

### Step 6. Compare medians and verify correctness

A candidate is only valid when:
- The command still verifies the same set of tests/quality checks.
- Test summary, archive, and runtime behavior are no worse than the baseline.
- No flaky tests, race conditions, or unpredictable cache invalidations appear.
- There is a clear, stable difference exceeding noise.

If the app builds a JAR faster by dropping **test** and removing verification from CI releases, that is **reducing work scope**, not improving performance for the same requirement.

### Step 7. Decide to roll out or roll back

Document the change, timing samples, median, risks, and rollback path. If no stable improvement is observed, do **not** ship the change to mainline even if it sounds good in theory.

## 14. Diagnostic Map by Where Time Is Spent

| Observation | Priority hypothesis to test | Investigation path before optimizing |
| --- | --- | --- |
| Fresh build slow, warm build fast | Dependency downloads, wrapper distribution, network | Mirror/repositories, proxy, CI cache policy |
| Every build slow before tasks run | JVM/daemon startup, init/configuration | Gradle `--profile`, startup/configuration breakdown, plugins |
| No source changes, yet Gradle executes many tasks | Unstable inputs/outputs, custom task missing declarations | `UP-TO-DATE` details, task inputs/outputs |
| Gradle `FROM-CACHE` rare despite identical inputs | Cache key differences, env paths, plugin cacheability | Build Scan/caching report, task metadata |
| `compileJava` takes a lot of time | Many sources, annotation processors, invalidation | Task profiling, annotation processor config, ABI changes |
| `processResources` unusually slow | Copying/filtering too many files, bad input globs | Resource includes/excludes, filtering, file count |
| Unit tests dominate wall time | Context initialization, test fixtures, DB/network, sequential runs | Surefire/Gradle reports, test isolation/parallel options |
| JAR/WAR packaging slow | Many/huge dependencies, compression, layers/index | Artifact size, `bootJar`/`repackage`, file I/O |
| Low build CPU but high wall time | I/O, network, locks, or waiting on external services | OS monitoring, network metrics, CI logs |
| Very high build CPU/RAM, machine swapping | Too many workers/forks/daemons, unbalanced heap | Memory, GC, worker counts, container limits |
| Multi-module edit in 1 module rebuilds everything | Task dependencies, inter-module ABI, missing incremental path | Maven reactor selection, Gradle project graph |
| Developer build fast, CI slow | Fresh runners, remote cache misses, security scans, constrained CPU | Compare on same runner, separate build-tool time from CI overhead |

**This is a list of hypotheses**, not conclusions you may draw from a single log line. Data must confirm which phase consumes time and why.

### 14.1. If the bottleneck is dependency download

Consider a repository manager/mirror close to CI, version pinning, cache policies, and reducing dynamic SNAPSHOT resolution. Do not wipe caches on every build out of fear of dependency bugs without evidence. Avoid using **--offline** just to produce pretty numbers if production CI needs to update dependencies/certificate metadata per policy.

### 14.2. If the bottleneck is Gradle configuration

Inspect plugins applied to root/subprojects, eager task configuration, reading files/network during configuration phase, and configuration cache compatibility. **--configuration-cache** can improve the no-change dev loop, but report **first store** and **cache reuse** separately. Do not enable configuration cache and ignore warnings/incompatibilities in production.

### 14.3. If the bottleneck is compilation/code generation

Observe the number of files compiled and annotation processor behavior. Code generators that emit many sources or read broader inputs than needed can defeat incremental builds. In Gradle, configuring task inputs/outputs and cacheability properly can cut repeated work. In Maven, analyze plugins, modules, and compiler options; do not choose **skip compilation** as a functional optimization.

### 14.4. If the bottleneck is tests

Count tests, per-suite execution times, Spring ApplicationContext initializations, database container/external service usage, and test isolation. In Spring Boot, creating many distinct Spring contexts can be expensive; consider reducing unnecessary test configuration variants where appropriate.

If you want to run tests in parallel, evaluate shared data, network ports, transactions, external resources, and flakiness risk. **Dropping tests entirely** shrinks verification scope and cannot be called optimizing the same workload.

### 14.5. If the bottleneck is archive packaging

Inspect the actual artifact type: Maven **spring-boot:repackage**, Gradle **bootJar**, JAR vs WAR, compression, snapshot dependencies, and CI artifact uploads. Scanning, signing, or image upload steps may live **outside the build tool command**; determine whether you are measuring the **build tool** or the **entire CI job** before optimizing.

## 15. Measuring Specific Modules and Commands in Multi-Project Builds

A multi-module Spring Boot repo may have **application**, **common**, **data**, and **integration-tests**. Two distinct needs exist:

- **Full reactor/build**: all modules within CI scope.
- **Targeted developer build**: only the application module and its required dependencies.

### 15.1. Maven reactor

Assuming module **app** exists:

~~~bash
./mvnw -B -ntp clean verify
./mvnw -B -ntp -pl app -am verify
~~~

**-pl app** selects the module, and **-am** builds the reactor projects `app` depends on. This is not an A/B test of the same workload since the module set changes. However, it establishes two **separate benchmark targets**: full-repo CI time and developer feedback time on `app`.

If you want to evaluate parallel reactor policies, you can test Maven **-T** (e.g., **-T 1C**) after identifying bottlenecks and checking plugin thread safety. **-T** is not always faster: CPU/RAM/IO contention and non-thread-safe plugins can cause failures or slowdowns. Benchmark with the exact same reactor, same tests, and same runner.

### 15.2. Gradle multi-project

~~~bash
./gradlew --console=plain build
./gradlew --console=plain :app:build
./gradlew --console=plain :app:bootJar
~~~

Assuming **:app** exists. **:app:build** may pull in tasks from project dependencies; **:app:bootJar** focuses on packaging and does not automatically run **:app:test**. They measure **different scopes**; only compare durations within the same target.

A multi-module build can benefit from **--parallel** when the task graph has enough independent work and the machine has resources; measure CPU/RAM pressure and correctness when enabling it. On a container capped at 2 CPU cores, setting a high worker count can slow the build down.

## 16. What to Investigate When Numbers Vary

### 16.1. One unusually slow build

Causes: newly downloaded files, slow DNS, lagging Maven repository, antivirus scans, fresh Gradle daemon, JIT warm-up, GC pauses, busy disk, contended CI agent, tests waiting on a database, timeouts. Do not delete a sample because it looks "bad"; record the cause if known, and separate "stability" from "median speed."

### 16.2. Branch switches invalidating caches

Changes to `build.gradle`, `settings.gradle`, `pom.xml`, JDK, compiler flags, annotation processor versions, or resource inputs can force many tasks to rebuild. A no-change build after a run on commit A **cannot be compared** directly against the first build on commit B when cache states differ.

### 16.3. Maven total time differs from Gradle

They can differ because:
- Maven ran through **verify**, while Gradle only ran **bootJar**.
- Surefire and Gradle JUnit Platform have different test filters/suites.
- Cache/up-to-date outcomes differ.
- Plugin versions or dependency graphs differ.
- Java toolchain, daemon, and JVM memory differ.
  
To compare build tools, first verify **identical behavior and artifacts**, establish balanced conditions, and repeat multiple times. Do not compare one Maven command against a differently scoped Gradle task and declare one tool "faster."

### 16.4. Total CI time does not equal total build-tool time

A CI job can include checkout, cache restore, JDK setup, unit tests, Docker build, security scans, publish/upload, artifact signing, and notifications. Use CI metrics to measure **job wall time** and each individual step. If Maven Total time is 35 seconds while the CI job takes 7 minutes, analyze the steps **outside Maven** before tuning the Maven compiler.

## 17. A Reusable Measurement Report Template

~~~text
Build Performance Baseline
Project/commit: build-timing-lab / <commit-hash>
Goal: CI verification latency (tests must run)
Tool: Gradle Wrapper 8.14 + Spring Boot Gradle Plugin 3.5.16
JDK: 17
Runner: Linux 4 vCPU, 8 GiB RAM, same runner class
Command: ./gradlew --console=plain clean build
Cache state: dependency cache warm, build cache disabled,
             configuration cache disabled, daemon state controlled
Sample method: 1 warm-up + 5 measured runs
Success criteria: BUILD SUCCESSFUL + required tests passed
Baseline durations (s): 120, 123, 118, 121, 120
Candidate durations (s): 94, 96, 97, 95, 98
Median baseline: 120.0 s
Median candidate: 96.0 s
Difference: -24.0 s / -20.0%
Observed bottleneck: [fill using actual profile]
Single candidate change: [identify one config change]
Correctness validation: [test reports, artifacts, smoke check]
Recommendation: [ship / rerun with more samples / rollback]
~~~

**The numbers, machine specs, and conclusions in the block above are a hypothetical sample report**, not real measurements. When applying this template, replace placeholders with verified data; do not publish a "20% improvement" claim without valid build runs.

**Do not store credentials, access tokens, private repository URLs with sensitive parameters, or unapproved full environment dumps in public logs/scans.**

### Cost/benefit-driven decisions

If CI runs 15 times per day and each run saves 24 seconds, total wall-clock build time saved across those runs is **360 seconds (6 minutes)** per day. With multiple CI jobs running in parallel, that does not automatically equal 6 minutes less wait time for the entire team; factor in runner slots, queueing, and the critical path.

An optimization requiring days of maintenance to shave 1–2 unstable seconds may be lower priority than fixing an anomalous 90-second dependency download step. Beyond speed, weigh resource cost and correctness risk.

## 18. Common Mistakes When Measuring Build Times

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Comparing first dependency download against a warmed second run | Different conditions | Record cold/warm and compare matching states |
| Calling every **clean** a cold build | Clean does not delete Maven/Gradle dependency caches | State output and cache state explicitly |
| Comparing **verify** with tests against **package -DskipTests** | Different test workload | Keep test commands/flags identical |
| Comparing **gradle build** against **gradle bootJar** | Different task graphs | Compare the same task set or report two targets |
| Using **--dry-run** as a compile-time metric | Does not execute task actions | Run a real build |
| Measuring once and concluding | Vulnerable to noise | Multiple samples, median and spread |
| Dropping slow outliers without investigating | Hides tail latency | Keep them and note the cause if known |
| Turning on cache and claiming the compiler got faster | Compilation may not have run | Inspect `UP-TO-DATE`/`FROM-CACHE` |
| Summing Gradle task durations into wall time | Tasks may run in parallel | Use a stopwatch and check the critical path |
| Comparing two different developer laptops | Different CPU/JDK/disk/network | Use the same CI runner or standardized environment |
| Increasing heap/workers without checking RAM | May cause swapping/contention | Measure memory/GC and verify correctness |
| Changing multiple knobs at once | Cannot isolate the cause | One variable per A/B cycle |
| Measuring the build tool and claiming all of CI is faster | Many CI steps sit outside the build tool | Measure the full CI job/critical path |
| Checking only `BUILD SUCCESSFUL` | Tests may be skipped or reports stale | Check actual task outcomes/test reports |
| Using Maven CLI `Total time` for every breakdown | Only shows build total | Use appropriate profiler/instrumentation/phase analysis |

## 19. Pre-Optimization Checklist

- [ ] Defined the exact scenario: fresh, clean, warm no-change, or incremental change.
- [ ] Used the exact same Maven Wrapper/Gradle Wrapper and JDK version for both baseline and candidate.
- [ ] Kept the same commit/build inputs or documented the single change being evaluated.
- [ ] Preserved the same test suite, profiles, quality gates, and packaging tasks.
- [ ] Recorded CPU, RAM, OS, disk, network, runner type, and resource limits.
- [ ] Recorded Maven local repo/Gradle dependency cache, daemon, build cache, and configuration cache states.
- [ ] Used an external stopwatch for wall time; checked Maven **Total time**, Gradle **--profile**, and task outcomes.
- [ ] If using Build Scan, obtained approval under metadata-sharing policy.
- [ ] Collected at least several valid samples; separated warm-up runs from measured samples.
- [ ] Computed median and spread rather than picking only the fastest run.
- [ ] Did not confuse clean builds with cold dependencies or `--rerun-tasks` with a fresh runner.
- [ ] Identified the bottleneck before editing `build.gradle`, `pom.xml`, or CI.
- [ ] Changed one variable with a clear hypothesis; ran A/B tests and checked test reports/artifacts.
- [ ] Checked for regressions, flaky tests, RAM/CPU pressure, and rollback feasibility.
- [ ] Reported wall-time change, confidence, and practical impact on developers/CI.
- [ ] Did not toggle `skipTests`, `-x test`, or disable security checks just to improve numbers.

## 20. Self-Assessment Questions

**Question 1.** Running `mvnw clean verify` twice, the second run is faster. Is that enough evidence that the Maven compiler was optimized?

**Answer:** No. The Maven local repository/plugins may already have been downloaded. You must inspect goal execution, compile logs, test counts, and dependency/cache states. Clean does not delete the dependency cache.

**Question 2.** Gradle reports **:compileJava UP-TO-DATE**. Can we conclude the Java compiler is very fast?

**Answer:** No. Gradle likely skipped the compile action thanks to input/output checks. To measure the compiler itself, use a scenario that actually performs compilation work, or `--rerun-tasks` as designed in your benchmark.

**Question 3.** Is using **./gradlew build --dry-run** valid for timing tests?

**Answer:** No. It computes the task plan without executing test actions. Run a real build/test and inspect test reports/task outcomes.

**Question 4.** Does Maven **-DskipTests** count as speeding up the build at the same quality bar?

**Answer:** No. It shrinks verification scope because Surefire does not run unit tests. Measure a fast-packaging use case separately and keep CI verification complete.

**Question 5.** Why can the sum of task times in a Gradle build exceed stopwatch wall time?

**Answer:** Tasks can run in parallel. Total task duration is the sum of work across tasks; wall time depends on the critical path and actual elapsed time from start to finish.

**Question 6.** What must be kept in mind when enabling `--scan`?

**Answer:** Build Scan typically publishes build metadata to a configured service, which can include project/machine/path details. Policy approval is required. If you only need a local profile, use `--profile`.

**Question 7.** With a baseline median of 120 seconds and a candidate median of 96 seconds, what is the percentage reduction?

**Answer:** (120 − 96) / 120 × 100% = **20%**, saving **24 seconds** on the median build.

**Question 8.** Why shouldn't CI **build** be compared with developer **bootJar**?

**Answer:** `bootJar` may omit tests/quality checks that CI `build` runs. Compare identical workloads or report two independent performance targets.

**Question 9.** Are configuration cache and build cache the same thing?

**Answer:** No. Configuration cache reuses the result of the configuration phase; build cache reuses outputs of tasks with matching cache keys. Dependency cache stores downloaded dependencies/plugins.

**Question 10.** When should an engineering change be adopted?

**Answer:** When a bottleneck is observed via profiles/logs, a hypothesis explains why the change helps, A/B results are stable across multiple samples, correctness is preserved, and the benefit justifies the risk and cost.

## 21. Summary

A Spring Boot build should be optimized iteratively:

~~~text
Define workload / success criteria
                 |
                 v
Record environment + cache state
                 |
                 v
Collect multiple wall-time samples
                 |
                 v
Maven log / Gradle --profile / approved scan
                 |
                 v
Identify bottleneck and critical path
                 |
                 v
Form one optimization hypothesis
                 |
                 v
Change one variable + run A/B measurement
                 |
                 v
Compare median, spread, test correctness
                 |
                 v
Evidence-based rollout or rollback
~~~

**Do not optimize by gut feeling.** One fast no-change build does not prove clean/CI builds are fast; skipping tests does not make the compiler faster; a clean-looking Build Scan does not replace verifying the application. Measuring **the right work**, knowing **why it is slow**, and comparing **before/after under equivalent conditions** is what enables sound investments in caching, dependencies, compilation, tests, packaging, or CI infrastructure.

## 22. Official References

- Gradle — Build Scan and local profile (`--profile`): https://docs.gradle.org/current/userguide/inspect.html
- Gradle — Build Scan Basics, data and publishing conditions: https://docs.gradle.org/current/userguide/build_scans.html
- Gradle — Performance guide: https://docs.gradle.org/current/userguide/performance.html
- Gradle — Command-line options: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Java Testing: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Gradle Profiler (scenarios, warm-up, profiling): https://github.com/gradle/gradle-profiler
- Apache Maven — Maven Getting Started (Total time, first dependency downloads): https://maven.apache.org/guides/getting-started/
- Apache Maven — CLI Options (`-B`, `-ntp`, `-pl`, `-am`, `-T`): https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Build Cache Extension (opt-in): https://maven.apache.org/extensions/maven-build-cache-extension/
- Spring Boot — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5.16 release announcement: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
