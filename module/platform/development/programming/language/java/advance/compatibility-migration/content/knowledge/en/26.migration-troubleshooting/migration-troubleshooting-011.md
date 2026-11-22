# Minimizing Failure Cases and Identifying the First Regression-Causing Change

A Java program running well on an older JDK and then throwing an error after an upgrade **does not mean the new JDK release definitely has a bug**. In a real migration, the team often simultaneously upgrades Maven/Gradle, dependencies, Java agents, container images, database drivers, or edits source code. Without isolating these changes, it is easy to pick the wrong cause and introduce a workaround that masks the symptom instead of fixing the compatibility bug.

There are two important techniques:

- **Minimizing the failure case (*minimal reproducible example*, MRE):** keeping only the minimal code, data, and conditions under which **the same failure still occurs**.
- **Identifying the first regression-causing change (*regression localization*):** finding the boundary between a **known good** state and a **known bad** state, then verifying the causal mechanism of the suspected change.

The goal is to create a failure case others can re-run, prove that a specific change triggered the incorrect result, and turn the finding into a regression test. In Java Advance Compatibility Migration, this is how you distinguish issues caused by the JDK, dependencies, module access, classloaders, serialization, data, or infrastructure configuration.

## 1. First, Define the Failure by Observable Behavior

“Java 21 broke the application” is an insufficient description. A usable report needs to specify:

1. **Input/operation:** which request, method, command, or fixture?
2. **Expected:** what result or invariant must be guaranteed?
3. **Actual:** which exception, response, bytes, or metric is wrong?
4. **Environment:** JDK feature/update/build, vendor, OS, container, JVM flags.
5. **Artifact:** Git SHA, JAR/container digest, dependency versions.
6. **Frequency:** 10/10, 3/50, or only under concurrent load?
7. **Control:** was the run on the old JDK/app version truly equivalent?

For example:

> With artifact checksum H and fixture F, when calling `POST /orders` on JDK 21 build B, the application returns HTTP 500 with `InaccessibleObjectException` in 5/5 attempts. The same artifact, fixture, and equivalent configuration on JDK 17 build A returns HTTP 201 in 5/5 attempts.

This example does not yet blame the JDK; it only describes **what has been verified**.

### 1.1. Failure signature

A *failure signature* is the set of characteristics ensuring that every minimization step still reproduces the same bug.

| Field | Example |
|---|---|
| Trigger | API request X or test Y |
| Expected | HTTP 201; data satisfies invariant |
| Actual | HTTP 500 or wrong output |
| Primary exception | `NoSuchMethodError`, `VerifyError`, `InaccessibleObjectException` |
| Location | Key class/method/stack frame |
| Input | Fixture ID and key bytes |
| Runtime | JDK, JVM flags, agent |
| Frequency | 10/10 or 4/100 |
| Artifact | SHA-256 and Git commit |

When there is no exception, the oracle can be **incorrect arithmetic results**, **skewed timestamps**, **a missing SPI provider**, **GC pauses exceeding threshold**, or **serialized bytes violating the contract**.

### 1.2. Symptom vs. Cause

~~~text
Symptom: HTTP 500
        |
        v
Direct error: ServiceConfigurationError
        |
        v
Missing provider in META-INF/services
        |
        v
Mechanism: Shade task overwrote duplicate-named service file
        |
        v
Triggering change: commit modifying packaging plugin
~~~

HTTP 500 is an external manifestation, not the root cause. Similarly, seeing an error for the first time after upgrading the JDK does not by itself prove the JDK is at fault.

## 2. Capture Evidence Before Changing the Environment

Do not rush to remove flags or upgrade dependencies before capturing a baseline state. If each attempt changes a series of factors simultaneously, investigation data loses comparability.

Create an *evidence bundle*:

~~~text
repro/
  README.md                 Expected/actual and how to run
  environment.txt          JDK/vendor/build, OS, locale/zone
  revision.txt             Git SHA
  artifact.sha256          JAR/container hash
  runtime-options.txt      Redacted JVM flags/agents
  dependency-tree.txt      Runtime dependency resolution
  input.bin                Synthesized fixture bytes
  expected.txt
  actual.txt
  stacktrace.txt
  test-report.xml
~~~

You can collect JDK/toolchain identity with:

~~~bash
java -version
java -XshowSettings:properties -version
mvn -version
# or
gradle --version
~~~

For a running HotSpot process with diagnostic permissions:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
~~~

`12345` is only an illustrative PID. Do not put full command lines, environments, heap dumps, or logs containing secrets/customer data into public issues.

### 2.1. The JDK Running Maven Differs from the Compile/Test JDK

`mvn -version` reports the JVM running Maven, **not necessarily the `javac` used by the Compiler Plugin or the test JVM forked by Surefire**. If toolchains are used, verify the actual compiler, test, and runtime JDKs.

For a compile error, record the compiler vendor/version and `--release`. For a runtime error, record the JDK of the service process/container. For a test error, print `java.version` inside the test JVM to avoid guesswork.

### 2.2. Compare the Same Binary

~~~text
Artifact checksum H
       |
       +-- JDK 17 --> PASS
       |
       +-- JDK 21 --> FAIL
~~~

Using the exact same artifact helps isolate runtime differences. However, the artifact must contain bytecode runnable on both JDKs; running Java 21 class files on JDK 17 will legitimately throw `UnsupportedClassVersionError`, not a mysterious regression.

If the bug is in the compiler/build, instead of the same artifact, compare **the same source and the same dependencies/flags** across each compiler.

## 3. Two Groups of Factors to Minimize

**Program/data group:**

- Number of controllers, services, and methods.
- Request payload, file bytes, SQL rows.
- Dependencies, annotation processors, and plugins.
- Number of threads, retries, schedulers.
- The call path that actually triggers the failure.

**Environment group:**

| Axis | Values to Pin or Test |
|---|---|
| JDK | Feature/update/build/vendor |
| Compiler | `javac`, `--release`, preview flags |
| Build | Maven/Gradle/plugin versions |
| Dependencies | Compile/runtime graph |
| Runtime | JVM options, GC, Java/native agents |
| Packaging | Classpath, module path, shade, nested JAR |
| OS/container | Base image, CPU/RAM, architecture |
| i18n | Locale, charset, timezone, TZDB |
| Data | Schema/version, serialized bytes |
| External services | TLS, database driver, broker |

A useful practice is to **change exactly one axis per experiment**. However, some bugs only appear when multiple factors interact; in those cases, do not force every failure onto a single culprit.

## 4. An MRE Is a Small Yet Faithful Failure Case

A good MRE has:

- Short and clear build/run instructions.
- Shareable input or data fixtures.
- Pinned configuration/JDK/dependencies.
- Expected/actual and PASS/FAIL conditions.
- Minimal unnecessary components.
- Unchanged conditions that cause the bug.

An MRE **does not have to be a single Java file**. A `ServiceLoader` bug may require a shaded JAR; a JNI/JVMTI bug requires a native agent; a concurrency bug requires multiple threads; a database isolation bug may require a small database container.

### 4.1. Avoid Minimization That Destroys the Cause

If the failing source file contains Windows-1252 bytes, opening and saving it as UTF-8 in an editor can make the bug disappear. If packaging drops `META-INF/services`, running tests from `target/classes` instead of the shaded JAR can also make the symptom disappear.

At each code-reduction step, ask: **Does the failure still have the exact same failure signature?** If not, restore the condition you just removed and continue checking.

### 4.2. Iterative Process

~~~text
Large failing application
       |
       v
Write reproduction command + oracle
       |
       v
Remove a group of code/data/config
       |
       v
Re-run in a fixed environment
       |
       +-- Same FAIL: keep the smaller version
       |
       +-- PASS: restore the removed part
       |
       +-- UNKNOWN: retry/investigate test
       |
       v
Continue until reaching a suitable MRE
~~~

Suggested order: reduce input → remove unrelated UI/network → reduce business layers → reduce dependencies → reduce JVM flags/agents → shrink packaging or thread count if the bug still reproduces. This is a guideline, not a mandatory sequence.

## 5. Designing a PASS / FAIL / SKIP / UNKNOWN Oracle

A test used for an MRE or bisection must distinguish:

| Result | Meaning |
|---|---|
| **PASS** | Test ran validly and behavior is correct |
| **FAIL** | Test ran validly and failed with the exact failure signature |
| **SKIP** | Revision/environment cannot be validly tested |
| **UNKNOWN** | Result is not certain enough or is flaky |
| **ERROR** | Harness/infrastructure broke unrelated to the bug |

A Maven build failing because it could not download a dependency is not sufficient to mark the commit being searched as **BAD**. A test added after the good commit that does not exist in older commits is also a **harness problem**, not an application bug.

A good oracle checks the business contract or target exception. An oracle relying solely on a log line can fail when the framework changes wording even though the application still behaves properly.

## 6. Delta Debugging: Systematic Condition Elimination

*Delta debugging* tests subsets of inputs/config to keep a small part that still triggers the failure. Suppose:

~~~text
S = {
  flag A, flag B, flag C,
  dependency X, dependency Y,
  record 1...100
}
~~~

A `ddmin` algorithm splits S into groups, testing each group and its complement. If a subset still FAILs, we continue subdividing that subset; otherwise, we increase the number of groups to search for smaller removals.

Pseudocode:

~~~text
function ddmin(config):
    n = 2

    while size(config) >= 2:
        parts = split(config, n)
        reduced = false

        for part in parts:
            if test(part) == FAIL:
                config = part
                n = max(2, n - 1)
                reduced = true
                break

        if reduced:
            continue

        for part in parts:
            candidate = config - part
            if test(candidate) == FAIL:
                config = candidate
                n = max(2, n - 1)
                reduced = true
                break

        if reduced:
            continue

        if n >= size(config):
            break

        n = min(size(config), n * 2)

    return config
~~~

### 6.1. Important Limitations

A subset may be **invalid**: dependency Y requires API X, a JVM flag only works with another GC, a fixture requires a specific schema revision, or a race condition needs at least two threads. A test that fails to build in this case does not mean PASS or FAIL.

A failure can also result from an interaction:

~~~text
JDK 21 + agent A --> FAIL
JDK 21 without agent --> PASS
JDK 17 + agent A --> PASS
~~~

Neither the JDK nor the agent alone can be removed while keeping the bug. A 1-minimal result does not prove a single cause; it is a small, useful set of conditions for explanation/testing.

## 7. Complete Example: `NoSuchMethodError` Due to an Old Runtime Dependency

Suppose an app is compiled against API v2, but runtime loads API v1. The error occurs when bytecode calls a v2 method that does not exist in v1's class.

### 7.1. API v1

File `src/api-v1/com/example/api/Feature.java`:

~~~java
package com.example.api;

public final class Feature {
    private Feature() {}

    public static String legacyName() {
        return "old";
    }
}
~~~

### 7.2. API v2

File `src/api-v2/com/example/api/Feature.java`:

~~~java
package com.example.api;

public final class Feature {
    private Feature() {}

    public static String legacyName() {
        return "new";
    }

    public static String versionName() {
        return "v2";
    }
}
~~~

### 7.3. Caller

File `src/app/Repro.java`:

~~~java
import com.example.api.Feature;

public final class Repro {
    public static void main(String[] args) {
        System.out.println(Feature.versionName());
    }
}
~~~

### 7.4. Compile with the New Dependency

Example on a Unix shell with a JDK supporting `jar --create`:

~~~bash
mkdir -p build/api-v1 build/api-v2 build/app lib

javac -d build/api-v1 \
  src/api-v1/com/example/api/Feature.java
jar --create --file lib/api-v1.jar -C build/api-v1 .

javac -d build/api-v2 \
  src/api-v2/com/example/api/Feature.java
jar --create --file lib/api-v2.jar -C build/api-v2 .

javac -cp lib/api-v2.jar -d build/app \
  src/app/Repro.java
~~~

### 7.5. Two Runs Differing Only in the Runtime JAR

~~~bash
# GOOD
java -cp "build/app:lib/api-v2.jar" Repro

# BAD
java -cp "build/app:lib/api-v1.jar" Repro
~~~

On Windows, the classpath separator is typically `;`. The GOOD run prints `v2`; the BAD run may throw `NoSuchMethodError`. All source/caller bytecode and the JDK remain identical; only the runtime dependency changed.

What this proves: such a bug **is not necessarily caused by upgrading the JDK**; a dependency mismatch introduced during deployment is enough to cause the failure during the same migration window.

### 7.6. Inspect Bytecode and Signatures

~~~bash
javap -classpath lib/api-v1.jar \
  -public com.example.api.Feature

javap -classpath lib/api-v2.jar \
  -public com.example.api.Feature

javap -classpath build/app -c Repro
~~~

`javap` shows that `Feature.versionName()` exists only in v2 and that the caller has a call site to that method.

In a real application, determine **which class is loaded from which JAR** via classpath/runtime class-loading logs, rather than looking only at the compile dependency tree.

## 8. Example Depending on Default Charset During a JDK Upgrade

Minimal code:

~~~java
import java.nio.charset.Charset;

public final class CharsetRepro {
    public static void main(String[] args) {
        byte[] input = {(byte) 0xE9};
        String value = new String(input);

        System.out.println(Charset.defaultCharset());
        value.codePoints().forEach(cp ->
            System.out.printf("U+%04X%n", cp));
    }
}
~~~

Byte `0xE9` can represent `é` in Windows-1252 or ISO-8859-1, but **is not a valid standalone UTF-8 sequence**. `new String(input)` uses the default charset per the API, so the result differs when the default charset changes.

Starting in **JDK 18**, JEP 400 sets the default charset of Java APIs within the JEP's scope to UTF-8. If the older JDK ran on a system defaulting to Windows-1252 and the newer JDK uses UTF-8, the same bytes can decode differently. If the older JDK already defaulted to UTF-8, this example **will not necessarily reproduce a difference**.

### 8.1. Minimize Properly

1. Preserve the original input bytes; do not copy through an editor that might change encoding.
2. Record `Charset.defaultCharset()` on both JVMs.
3. Remove the database/API layer while keeping `new String(input)`.
4. Print code points and compare.
5. Confirm the true encoding from the data contract.
6. Fix using an explicit `Charset`.

For example, if the source data specifies ISO-8859-1:

~~~java
import java.nio.charset.StandardCharsets;

String decoded =
    new String(input, StandardCharsets.ISO_8859_1);
~~~

The mechanism causing the bug is **assuming the default charset**, while changing the JDK is the trigger. This is the difference between the design root cause and the first change that produced the wrong result.

## 9. Choose Known-Good/Known-Bad Before Binary Search

To find a bug in Git history, you need a PASS commit and a FAIL commit **on the same JDK/environment**. If good ran on Java 17 and bad on Java 21, both source and runtime changed; you cannot infer which commit caused the bug from these two points.

### 9.1. 2×2 Matrix

| | JDK 17 | JDK 21 |
|---|---|---|
| Old App A | PASS | PASS |
| New App B | PASS | FAIL |

This table suggests an **interaction between app B and JDK 21**. If both A and B fail on JDK 21 with the same artifact/conditions, prioritize checking runtime/JVM options/agents. If only B fails on both JDKs, source/dependency changes are more suspect.

### 9.2. Axes That Can Be Bisected

- Git source commits.
- Dependency/plugin versions.
- JDK feature releases or patch builds.
- Container images.
- JVM flags.
- APM/JVMTI agent versions.
- Schema migration revisions.
- Framework configuration.

You do not have to default to `git bisect` as the first step; choose the axis that evidence shows actually changed.

## 10. `git bisect` to Find the First Commit Changing Test Status

Suppose HEAD is confirmed BAD and tag `v2.0.0` is GOOD in an environment with the same JDK/fixture.

~~~bash
git bisect start
git bisect bad HEAD
git bisect good v2.0.0
~~~

Git checks out an intermediate commit. Run the oracle; if PASS:

~~~bash
git bisect good
~~~

If FAIL matching the signature:

~~~bash
git bisect bad
~~~

Repeat until the suspect commit is found, then:

~~~bash
git bisect log
git bisect reset
~~~

**Save or isolate work-in-progress changes before bisecting.** Git will check out different commits; use a separate worktree if needed so you do not affect the current working branch.

### 10.1. Why Is It Fast?

Across roughly 128 commits and a stable oracle, ideal bisection requires about 7 intermediate trials instead of testing nearly 128 commits sequentially. In practice it can take more when merge history is complex, commits fail to build, or tests are flaky.

### 10.2. Automating with `git bisect run`

~~~bash
git bisect start
git bisect bad HEAD
git bisect good v2.0.0
git bisect run ./scripts/bisect-regression.sh
git bisect log
git bisect reset
~~~

Important exit code convention:

| Exit code from script | How `git bisect` interprets it |
|---|---|
| `0` | GOOD |
| `1..127` except `125` | BAD |
| `125` | SKIP, not a valid evaluation |
| `128` and above | Not a normal good/bad result; may abort the process |

A sample script:

~~~sh
#!/bin/sh

# JAVA_HOME, dependency repository, and fixture are fixed.

mvn -q -DskipTests package
build_rc=$?

if [ "$build_rc" -ne 0 ]; then
    exit 125
fi

mvn -q -Dtest=CompatibilityRegressionTest test
test_rc=$?

if [ "$test_rc" -eq 0 ]; then
    exit 0
fi

# Mark BAD only if the test failure matches the target bug.
# If Maven hits an infrastructure error/missing test, classify as SKIP.
exit 1
~~~

This skeleton needs additional logic to distinguish test assertions from infrastructure failures. If `CompatibilityRegressionTest` was only added after the good milestone, running the script on an older commit may report that the test does not exist. In that case, use a harness **outside the worktree being bisected**, or mark untestable revisions appropriately.

### 10.3. First Failing Commit Differs from Root Cause

For example:

~~~text
Commit A: code implicitly uses the default locale
Commit B: add Turkish-language data
Commit C: change the container's default locale
~~~

The test may only start failing at C, yet the design flaw already existed in A. The bisect result states “C is the PASS → FAIL transition point within the tested range,” which is not enough to claim C is the entire cause.

### 10.4. Bisection Is Not Always Monotonic

~~~text
GOOD -> BAD -> GOOD (revert) -> BAD (bug reappears)
~~~

When there are reverts/merges or multiple independent causes, a single-boundary model may not apply. Inspect the commit graph, test neighboring commits, and consider the ancestor range of the release under investigation.

## 11. Narrowing Down the JDK Release/Build

If the same artifact PASSes on JDK 17 yet FAILs on JDK 21, test intermediate JDKs:

~~~text
JDK 17: PASS
JDK 18: ?
JDK 19: ?
JDK 20: ?
JDK 21: FAIL
~~~

If JDK 18 is the first FAIL in the matrix, you can investigate JDK 18 release notes and JEPs, such as default charset under JEP 400. Still, that remains the **earliest tested failing feature release**, not yet a specific OpenJDK source commit.

### 11.1. Check Update Builds and Vendors

~~~text
21.0.2: PASS
21.0.3: PASS
21.0.4: FAIL
21.0.5: FAIL
~~~

A bug may be backported or fixed differently across vendor/update branches. Record the full vendor/build number. Avoid using “Java 21” as the sole label when comparing patch updates.

### 11.2. Conditions That Make Version Bisection Invalid

- Java 21 bytecode cannot run on Java 17.
- JVM flags exist only in the newer version.
- The Java agent does not support the older version.
- The container base image/OS also changed.
- Dependencies require a higher Java version.
- TLS truststore, timezone data, or locale changed independently.

Mark SKIP or redesign the comparison; do not force every startup failure into the same regression.

### 11.3. Identifying the JDK Source Commit Requires Another Step

Testing JDK releases only narrows the version range. Pinpointing an exact OpenJDK commit may require building specific JDK revisions yourself, pinning compiler tools, and running the MRE on each build. This is advanced investigation; application reports should be honest about the level actually determined.

## 12. Purpose-Driven Binary/Classpath and Toolchain Analysis

When encountering `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`, or `UnsupportedClassVersionError`, verify where the class is actually loaded from.

With Maven:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency some-library \
  --configuration runtimeClasspath
~~~

With HotSpot Unified Logging:

~~~bash
java -Xlog:class+load=info \
  -jar app.jar
~~~

Inspect the classloading source/module/class loader, especially when the artifact has been shaded/repackaged.

### 12.1. `javap` Inspects Signatures and Bytecode Level

~~~bash
javap -verbose -classpath target/classes \
  com.example.Service
~~~

Class-file major 61 corresponds to Java 17, and major 65 corresponds to Java 21. For a runtime `NoSuchMethodError`, inspect method descriptors on the running JAR, not just the current source code.

### 12.2. `jdeps` Detects Only Static Relationships

~~~bash
jdeps --summary app.jar
jdeps --jdk-internals app.jar
~~~

`jdeps` is useful for finding dependencies and JDK internals, but is not guaranteed to find classes loaded via reflection, `ServiceLoader`, or string names in configuration. If the bug involves SPI/plugins, keep service metadata in the MRE and run the final artifact.

### 12.3. Compiler and Test JVM Are Two Separate Axes

With Maven Toolchains, the compiler may be JDK 21 with `--release 17` while Surefire forks a 17 JVM. A green build on Maven JVM 21 does not prove Java 17 compatibility. Record the identity of each process and check target bytecode/dependencies.

## 13. JVM Flags, Agents, and Native Crashes

A failure after a JDK upgrade can be caused by a removed `-XX` flag, a Java agent transformer not understanding new class files, changed module access, or an incompatible native JVMTI agent.

For example, startup includes:

~~~text
-Xms2g
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*
--add-opens=java.base/java.lang=ALL-UNNAMED
-javaagent:/opt/agents/apm.jar
-agentpath:/opt/profiler/libprofiler.so
~~~

Minimize by group:

1. App without third-party agents.
2. App with only the APM agent.
3. App with only the native profiler.
4. App with both.
5. Select the exact JDK/build and workload.
6. Then remove unnecessary tuning flags.

If a removed JVM flag causes:

~~~text
Unrecognized VM option ...
Could not create the Java Virtual Machine.
~~~

An MRE sometimes only needs `java <actual flag> -version`. However, do not use a hypothetical flag to claim a bug in the target JDK.

If the JVM crashes natively and produces `hs_err_pid*.log`, inspect the JDK vendor/build, `problematic frame`, native library, agent path, OS/architecture, and stack. Test in an isolated environment instead of repeatedly crashing production.

## 14. When the Bug Is Flaky, a Race Condition, or a Timeout

A single PASS is not enough to mark a state known good if the failure occurs probabilistically:

~~~text
JDK 17: 0/50 failures
JDK 21: 12/50 failures
~~~

This table shows different frequencies; it does not prove the old version **never** fails.

### 14.1. Preserve Concurrency Conditions

Do not accidentally erase the bug by:

- Reducing the thread count to one.
- Adding locks inside the test harness.
- Turning an asynchronous task into a synchronous call.
- Adding heavy logging that alters scheduling.
- Lowering workload below the failure threshold.

An MRE for a race may still require a thread pool and stress loop; record seed, iterations, CPU limit, and relevant flags.

### 14.2. Designing a Retry Policy

When bisecting a flaky failure:

- BAD when the exact failure signature occurs with sufficient evidence.
- GOOD when run a self-defined threshold number of times with no failures.
- UNKNOWN when still uncertain.
- SKIP when the revision cannot be tested.

Do not mark UNKNOWN as GOOD just because the bisect tool needs an immediate answer.

### 14.3. Performance Regressions Require Structured Benchmarks

A single timeout in CI is not enough. You need the same dataset, concurrency, CPU/RAM, warmup, sampling settings, and multiple measurement runs. Inspect p50/p95/p99, throughput, allocation, GC, RSS, and CPU throttling.

If adding JFR/profilers, check the overhead of the observation tool; you can run a comparison **without the agent** before enabling the agent.

## 15. Database, Broker, and Network May Not Be Removable from the MRE

A bug appearing only with PostgreSQL transaction isolation may disappear when swapped for H2. That does not prove the database is unrelated; the fake database may not preserve the same semantics.

An MRE may still use:

- A small database container with schema and a few rows of data.
- A test broker with a specific event format/ordering.
- A test TLS server with a policy/certificate fixture.
- A data file in the exact legacy charset.
- A shaded JAR containing real `META-INF/services`.

### 15.1. Use Synthetic Data While Keeping the Trigger

Do not send production customer data, credentials, keys, or full heap dumps to vendors. If the bug involves a Vietnamese name in decomposed Unicode form, replace it with a synthetic name **having the same code-point properties**, rather than replacing it with ASCII and making the bug vanish.

### 15.2. Rollback May No Longer Be Safe

If the new version has already written a new database/event format, rolling back to the old JAR does not mean rolling back the data. When searching for the first bad commit, still verify whether the old binary can read/write data created by the new version before applying a production rollback.

## 16. Controlled Experiments to Confirm the Cause

After finding the suspect commit/version, design an experiment capable of falsifying the hypothesis.

Example hypothesis:

> Runtime uses an old API JAR that lacks the method called by client bytecode.

Evidence:

1. Keep the same JDK/caller bytecode.
2. Runtime dependency v1 → FAIL.
3. Runtime dependency v2 → PASS.
4. `javap` shows the method exists only in v2.
5. Class-loading logs confirm the source JAR.
6. Fix the dependency graph of the final artifact → PASS.

This is stronger evidence than a single commit hash alone.

### 16.1. A/B/A

In an environment without irreversible data side effects:

~~~text
A: old configuration            PASS
B: change only suspected factor FAIL
A: restore old configuration    PASS
~~~

Repeated results strengthen causality. However, for database migrations/side effects, use an isolated environment and restorable snapshots; do not recklessly perform A/B/A in production.

### 16.2. Distinguish Four Concepts

- **First bad transition:** the first change where the oracle switches PASS → FAIL in the tested range.
- **Trigger:** the condition that exposes the bug.
- **Latent defect:** a faulty assumption that already existed but had not yet been triggered.
- **Root cause/fix:** the mechanism and change that eliminate the defect.

For example, `--add-opens` can mitigate `InaccessibleObjectException`, but if a library relies on encapsulated JDK internals, the sustainable fix may be upgrading the framework/using an official API. A workaround is not by default a long-term solution.

## 17. Turning the MRE into a Regression Test

| Cause | Appropriate Regression Test |
|---|---|
| API runtime mismatch | Binary compatibility/classpath test |
| JPMS reflection | Test on the exact JDK with module access |
| Default-dependent charset | Byte fixture + explicit charset |
| DST/timezone | `Clock.fixed`, `ZoneRules`, fixtures |
| `ServiceLoader` after shade | Black-box test on the final JAR |
| Incompatible Java agent | Integration test with agent/JDK |
| Race condition | Stress/concurrency harness |
| Performance regression | Stable benchmark per SLO |
| Schema migration | Integration test with old/new data |

JUnit 5 example for data with an ISO-8859-1 contract:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class EncodingRegressionTest {
    @Test
    void legacyByteUsesDeclaredCharset() {
        byte[] input = {(byte) 0xE9};

        String decoded = new String(
            input, StandardCharsets.ISO_8859_1);

        assertEquals("é", decoded);
    }
}
~~~

If the actual source is not ISO-8859-1, replace it with the charset specified by the data documentation. The test above does not depend on the default charset, so it is less prone to breaking when the JDK/OS changes.

A **diagnostic MRE** can contain scripts/fixtures/logs to explain the bug; a **regression test** should be short, stable, and verify an invariant. Both can be kept for their respective purposes.

## 18. End-to-End Diagnostic Workflow

### Phase A: Confirm

1. Record expected/actual, failure signature, reproduction count.
2. Collect JDK/build/toolchain/flags/agents, artifact hash.
3. Save the fixture that actually triggers the failure.
4. Identify comparable known good/bad points.

### Phase B: Isolate

1. Same JAR on source/target JDK if possible.
2. Same JDK with different app/dependency versions.
3. Check container/OS/environment differences.
4. Toggle each agent individually in the test environment.
5. Inspect runtime classpath and packaging metadata.

### Phase C: Minimize

1. Reduce input.
2. Remove uninvolved business layers.
3. Keep minimal methods/classes and dependencies.
4. Preserve charset bytes/module layout/concurrency if relevant.
5. Write a reproduction command and oracle.

### Phase D: Locate the Transition Point

1. If source-related: use `git bisect` with a stable test.
2. If JDK-related: test feature/update builds with the same binary.
3. If dependency-related: compare pinned versions.
4. If config/container-related: change one revision at a time.
5. If flaky: repeat, record probability, and preserve UNKNOWN when needed.

### Phase E: Prove and Fix

1. Read the diff of the suspect change.
2. Formulate a testable mechanism hypothesis.
3. Run A/B tests and cross-check logs, `javap`, bytes, profiler.
4. Fix the root cause.
5. Test the fix on source/target JDKs and related business paths.
6. Convert the MRE into a regression test.

### Phase F: Hand Over

Report both good/bad points, inconclusive experiments, how far the cause has been proven, and rollback risks. Do not write “the JDK caused the error” if you only know it is the first version where the bug appeared.

## 19. Report Template for Teams/Vendors

~~~text
Title: [Java migration] <failure signature>

Expected:
Actual:
Reproduction rate:

Application Git SHA:
Artifact checksum:
JDK vendor/feature/update/build:
OS/architecture/container digest:
Maven/Gradle/plugin versions:
JVM flags/agents:
Runtime dependency/classpath/module path:
Locale/charset/zone if relevant:

Fixture:
Build command:
Run command:
Expected output:
Actual output:

Last known good:
Earliest tested bad:
Bisect result:
Skipped/unknown revisions:

Trigger:
Root-cause hypothesis:
Controlled A/B evidence:
Temporary workaround:
Permanent fix:
Regression test:
Supported JDK matrix:
Rollback risks:
~~~

Attach redacted logs or synthetic fixtures; do not attach production secrets, customer data, or native heap/profile dumps not cleared for sharing.

## 20. Common Mistakes

**“The failure appeared after the JDK upgrade, so the JDK is the cause.”** No: source, agents, libraries, or data may have depended on an old behavior.

**“An MRE must have no dependencies.”** Not if the dependency or packaging itself is part of the failure.

**“Removing all JVM flags helps minimize.”** It may also remove a required condition, making the bug vanish without understanding the cause.

**“One PASS is enough to know it is good.”** Not for race/flaky tests.

**“Failing to build at a commit means the commit is bad.”** It may need SKIP or a different harness.

**“`git bisect` gives the root cause.”** It gives the transition point per the oracle/history; controlled experiments are needed to explain why.

**“Upgrade all dependencies to try fixing it.”** This introduces many variables and loses the baseline.

**“`jdeps` doesn't show the class, so it isn't needed.”** Reflection/SPI and config can load classes dynamically.

**“Just test class files; the final artifact isn't needed.”** Wrong for shade, manifest, service metadata, nested JARs, and module path.

**“No exception means no regression.”** Wrong results, charset, DST, or latency can fail silently.

**“Rolling back the source commit is enough.”** Not if the new release already wrote incompatible data/events or created external side effects.

## 21. Checklist

- [ ] Have expected/actual and failure signature.
- [ ] Have clear frequency or reproduction count.
- [ ] Have JDK vendor/update/build of the actual process.
- [ ] Have artifact hash, Git SHA, dependency versions, and JVM flags.
- [ ] Have a byte-accurate fixture cleared for sharing.
- [ ] Have known-good and known-bad under equivalent conditions.
- [ ] Tested the same artifact on multiple JDKs when targets allow.
- [ ] Isolated source/dependency/JDK/container/config.
- [ ] Oracle distinguishes PASS, FAIL, SKIP, UNKNOWN, and ERROR.
- [ ] MRE preserves the exact trigger and failure signature.
- [ ] Considered interdependencies and interactions across factors.
- [ ] Checked the final artifact when packaging/classloaders are involved.
- [ ] Checked `javap`, `jdeps`, or dependency tree when appropriate.
- [ ] Used `git bisect` with a stable oracle, without treating build failures as bad.
- [ ] Narrowed JDK update/build when the error is runtime-specific.
- [ ] Verified the suspect change via A/B.
- [ ] Distinguished trigger, latent defect, first bad, and root cause.
- [ ] Wrote a regression test to prevent recurrence.
- [ ] Ran the fix test on supported JDKs/runtimes.
- [ ] Assessed data/side effects before deciding to roll back.
- [ ] Redacted secrets in reports.

## 22. Technical Documentation

- [Git – git bisect](https://git-scm.com/docs/git-bisect): finding commits, `bisect run`, exit codes, and skip.
- [OpenJDK Bug System](https://bugs.openjdk.org/): looking up and submitting JDK bug reports with an MRE.
- [JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400): example of default charset change.
- [Java javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): method descriptors and bytecode.
- [Java jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): static dependencies and JDK internals.
- [Java jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): JVM diagnostics.
- [Maven Dependency Plugin dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).

When applying these, verify command syntax and the support matrix for the exact JDK, Git, Maven/Gradle, plugin, and OS being run.

## 23. Conclusion

Minimizing a failure case is not the act of deleting code to make it short, but **preserving the exact faulty mechanism in a small, standalone, repeatable test**. Identifying the first regression-causing change requires a reliable known-good/known-bad boundary, control over changing axes, and bisection tailored to source, JDK, dependencies, or configuration.

The first transition point is an investigative lead, **and does not by itself prove the root cause**. After locating it, analyze the mechanism, run A/B control experiments, fix the faulty assumption, test across supported JDKs, and preserve a regression test. This approach helps Java Advance Compatibility Migration avoid intuitive rollbacks or workarounds and reach verifiable technical conclusions.