# Unrecognized VM Option and Removed GC Options

When upgrading the JDK in **Java Advance Compatibility Migration**, the first error sometimes appears **even before the application runs**. A script that previously started cleanly with JDK 8 may be rejected by the new JDK because of an old JVM parameter, such as a removed GC flag, a logging flag belonging to the pre-Java 9 system, or a vendor-specific option that does not exist in the new runtime.

A common message:

~~~text
Unrecognized VM option 'SomeOldFlag'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred. Program will exit.
~~~

This error belongs to the **JVM initialization phase**. It differs from Java compilation errors, dependency errors, `OutOfMemoryError`, or exceptions occurring while the program is processing requests. To diagnose it accurately, you must find the **actual parameters passed to the right JVM**, determine the status of the parameter on the **target JDK/distribution**, and then remove or replace it by function, rather than guessing a flag with a similar name.

In particular, **"GC was removed" and "option name reports unrecognized" do not always appear together**. For example, the CMS collector was removed from HotSpot in JDK 14 under JEP 363, yet some JDK builds still **accept the old flag and warn that it is ignored**. Conversely, some incremental CMS options were removed in JDK 9, preventing the JVM from starting. Therefore, the statuses `deprecated`, `obsolete`, `removed`, and `unrecognized` must be properly distinguished.

This lesson provides a methodology for investigating startup flags, a classification table of legacy GC flags, how to migrate to `-Xlog`, Gradle/Maven/container configuration examples, verifying the actual collector, and a post-fix testing workflow.

## 1. At Which Stage Does the Error Occur?

The startup process of a Java application can be viewed in simplified form as follows:

~~~text
Shell / container / service manager
        |
        v
Java launcher + environment options
        |
        v
Parse and validate JVM options
        |
        +--> INVALID OPTION
        |      "Unrecognized VM option ..."
        |      JVM startup fails
        |
        v
Initialize JVM, heap and collector
        |
        v
Create class loaders / load main class
        |
        v
Run application initialization
        |
        v
Business requests / background jobs
~~~

When the JVM rejects an option before creating the virtual machine, editing the classpath or changing a method in the source usually **does not resolve the root cause**. You need to look at the **startup command**, not the stack trace of business code.

### 1.1. Comparing startup symptoms

| Symptom | Error category | First investigation direction |
|---|---|---|
| `Unrecognized VM option 'X'` | Flag not recognized by target JVM | Option name, syntax, JDK/version/vendor, and injection source |
| `Unrecognized option: --something` | Unsupported or misspelled launcher option | `java --help`, `java --help-extra`, release |
| `Could not create the Java Virtual Machine` | General initialization failure, possibly due to an option | Read the **preceding error line** |
| `Ignoring option ...; support was removed ...` | Flag accepted but no longer has effect | Remove the flag, confirm the new default |
| `... is deprecated; will use ... instead` | Old flag still temporarily mapped | Migrate to official syntax |
| `Multiple garbage collectors selected` or equivalent conflict | Invalid selection of multiple GCs | Inspect all flags from every source |
| `Error: A JNI error has occurred` | May be a class loading/main startup failure | Read detailed message; do not assume GC |
| `UnsupportedClassVersionError` | Bytecode requires a newer runtime | Runtime JDK and class-file version |
| `OutOfMemoryError: Java heap space` | Heap memory at runtime | Heap sizing, leaks, allocation, and GC logs |
| `InaccessibleObjectException` | Deep reflection blocked by JPMS | `opens`, frameworks, JDK internals |

**An error starting with "Could not create the Java Virtual Machine" is not necessarily due to insufficient heap.** Read the unrecognized/invalid message above it before adjusting `-Xmx`.

## 2. Lifecycle Classification of JVM Options

A flag name may go through different statuses across HotSpot releases:

| Status | Typical meaning | Can it start? | What to do |
|---|---|---|---|
| Supported | JVM understands and applies it per documentation | Usually yes, if value and conditions are valid | Keep if justified with evidence |
| Experimental | Option not yet committed as stable, may require unlocking | Depends on JVM/flags | Check compatibility, avoid using by default without basis |
| Diagnostic | Serves analysis purposes, sometimes requires unlocking | Depends on configuration | Use only when there is an investigation goal |
| Deprecated | Still accepted or functional, but may warn | Usually yes | Plan replacement |
| Obsolete | Flag is still accepted but **ignored**, usually warns | May start | Remove; do not expect an effect |
| Removed | Flag is no longer accepted in the corresponding JVM version | Usually no | Remove or change how the goal is achieved |
| Unrecognized | Current JVM does not understand the name/syntax | No, unless an ignore policy is set | Check typo, version, vendor, and option source |

Statuses are not completely uniform across all vendors/distributions/updates. A flag listed in a JDK 14 guide might not be accepted in a newer JDK release. Therefore, **you must query the specific runtime**, not guess from release years or from flags available on another machine.

### 2.1. Obsolete does not mean the feature still works

A warning such as:

~~~text
OpenJDK 64-Bit Server VM warning:
Ignoring option UseConcMarkSweepGC; support was removed in 14.0
~~~

is shown to illustrate the situation where the flag **no longer has effect**. The application may continue running with another collector. If the team only sees `exit code = 0` and writes "using CMS", that conclusion will be wrong.

Conversely, when a JVM returns `Unrecognized VM option`, it has exited early. There is no reason to wait for the application to handle this error itself.

## 3. Causes Unrelated to GC

Although the lesson focuses on GC flags, the same message can come from:

- Misspelling `-XX:MaxGCPauseMillis=...` or misplacing the `+` sign.
- Passing an option meant for a newer JDK to an older JDK.
- Passing an option from a different JVM, for example a HotSpot setting to an incompatible JVM.
- Using a flag that only exists on a specific OS/architecture or custom build.
- An experimental/diagnostic flag not properly unlocked.
- Invalid `-Xlog` tag/level/decorator syntax or syntax not yet supported by the JDK.
- Old parameters present in `JAVA_TOOL_OPTIONS` or `_JAVA_OPTIONS` unnoticed by the developer.
- IDE, Gradle daemon, Maven, CI, or container injecting flags different from the terminal.
- Passing a system property with the wrong syntax, for example using `-XX:` instead of `-D`.
- Using an old JVM reference document for a different JDK version.

Therefore, the first question when encountering `Unrecognized VM option` is always:

> **Which JVM is receiving which exact option string, from which configuration source?**

Only after that should you examine whether the flag was removed, changed format, or had a deployment mistake.

## 4. Identifying the Java Version Actually Running

In a Unix-like terminal:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
command -v java
~~~

On Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
~~~

If multiple JDKs exist, `java` on `PATH` may not be the JDK configured in the IDE or container. You should use the **absolute path to the Java executable** when creating a reproduction to avoid unseen variation:

~~~bash
/opt/jdk-21/bin/java -version
/opt/jdk-25/bin/java -version
~~~

The paths above are examples. They do not prove that a JDK exists on the current machine.

### 4.1. Application runtime differs from compiler, daemon, and test worker

A Gradle application may use:

- A JDK running the Gradle daemon.
- A JDK selected by the Java toolchain for compilation.
- A JDK selected by the `Test` task.
- A JDK running the application in production.

Maven also has a JVM running Maven core and separate forked JVMs for tests/plugins. Therefore, running `java -version` in the terminal is a **useful signal, but not sufficient**. The option error must be tied to the exact process.

## 5. Checking Syntax, Meaning, and Support for Each Option

Common parameter categories:

| Form | Example | Notes |
|---|---|---|
| Standard launcher | `--class-path`, `--module-path` | Per Java launcher documentation |
| Nonstandard `-X` | `-Xms512m`, `-Xmx2g`, `-Xlog:gc` | Not every version supports the same set |
| HotSpot `-XX` | `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis=200` | Includes boolean flags and valued flags |
| System property | `-Dfile.encoding=UTF-8` | Not a GC flag |
| Java agent | `-javaagent:agent.jar` | Belongs to the agent mechanism |
| Module access | `--add-opens=...` | Resolves opens/reflection issues |
| Native access | `--enable-native-access=...` | Availability/scope depends on JDK |

A boolean flag typically uses `-XX:+FlagName` or `-XX:-FlagName`. A numeric flag uses `-XX:FlagName=value`. However, one should not assume every flag name has both forms or every value is valid.

### 5.1. Self-describing tools of the JVM

On corresponding HotSpot JDKs:

~~~bash
java --help
java --help-extra
java -Xlog:help
java -XX:+PrintFlagsFinal -version
~~~

- `--help` and `--help-extra` introduce launcher options.
- `-Xlog:help` describes tags/levels/decorators on Java 9+.
- `-XX:+PrintFlagsFinal -version` prints effective/available JVM flags for the specific runtime.

The output of `PrintFlagsFinal` is very long; filter it according to your diagnostic goal. On JDKs prior to Java 9, `-Xlog:help` is not an applicable tool.

### 5.2. Testing a minimal option

To verify that the JVM **accepts the syntax** without running the application:

~~~bash
java -XX:+UseG1GC -version
~~~

If this command runs, it only proves the JVM accepts the flag at startup, not that the collector fits the workload. To evaluate behavior, run the application/tests with GC logging and observe under load.

A separate test for logging configuration on JDK 9+:

~~~bash
java -Xlog:gc -version
~~~

Do not bundle all 30 flags immediately to verify one option: finding each error source will be harder.

## 6. Important JDK Milestones for GC Flags

| Milestone | Change | Correct understanding |
|---|---|---|
| JDK 8 | PermGen was replaced by Metaspace (JEP 122) | `PermSize` and `MaxPermSize` no longer bound PermGen |
| JDK 9 | G1 became HotSpot's default GC in common configurations (JEP 248) | Without specifying a GC, the collector may differ from JDK 8 |
| JDK 9 | Unified JVM Logging and unified GC logging (JEP 158/271) | Migrate old GC logging flags to `-Xlog` |
| JDK 9 | Certain GC combinations and Incremental CMS were no longer supported (JEP 214) | Some legacy launch configurations are rejected |
| JDK 14 | CMS collector was removed (JEP 363) | Legacy CMS flags may become obsolete and ignored before being removed from the flag parser |
| JDK 15 | ZGC became a production feature (JEP 377) | Adds a GC option, does not automatically become the default |
| JDK 21 | Generational ZGC was introduced (JEP 439) | Mode and flags must be checked per release |
| JDK 23 | Generational ZGC became the default mode when selecting ZGC (JEP 474) | Old ZGC configuration may change meaning |
| JDK 24 | Non-generational ZGC was removed (JEP 490) | `ZGenerational` is no longer a mode selection to keep |

These are HotSpot/OpenJDK milestones and do not assert that every distributor or platform provides the exact same set of collectors. Draw conclusions only after identifying the **actual runtime JDK** and startup arguments.

## 7. CMS Was Removed: The Most Common Error

CMS (Concurrent Mark Sweep) was a collector used for pause-sensitive workloads in many Java 8 deployments. An old command:

~~~bash
java \
  -XX:+UseConcMarkSweepGC \
  -XX:+CMSParallelRemarkEnabled \
  -XX:+UseParNewGC \
  -jar service.jar
~~~

This configuration should not be carried over unchanged to a modern JDK.

### 7.1. CMS removal in JDK 14

JEP 363 removed the CMS implementation in JDK 14. Some CMS-related flags were placed in **obsolete** status, possibly ignored with a warning; other flags had been removed at earlier milestones or deleted later.

That leads to two different situations:

~~~text
Case A:
  JVM accepts an obsolete flag, prints warning,
  ignores the flag and may start with another collector.

Case B:
  JVM no longer recognizes a removed flag,
  prints "Unrecognized VM option" and exits.
~~~

**Do not infer that JDK 14 always reports the exact same unrecognized string for `UseConcMarkSweepGC`.** How it reacts depends on the flag and release.

### 7.2. What should replace CMS?

There is no "new CMS" flag that preserves identical semantics and tuning knobs.

Directions to consider:

- Try **G1** as default/`-XX:+UseG1GC` if suitable for the workload.
- If strict tail latency is required, evaluate ZGC or another collector **present in the supported runtime**.
- For batch throughput-oriented workloads, evaluate Parallel GC.
- Remove CMS-specific flags that no longer have effect.
- Re-establish heap/GC pause targets by benchmarking on the real application.

Example testing G1 on a suitable JDK:

~~~bash
java \
  -XX:+UseG1GC \
  -Xms512m -Xmx2g \
  "-Xlog:gc*:file=gc.log:time,uptime,level,tags" \
  -jar service.jar
~~~

This is illustrative syntax, not a universal performance recommendation. Collector selection should be based on p95/p99 latency, throughput, CPU/GC overhead, and peak RSS.

### 7.3. Do not port CMS knobs to G1 by renaming them

CMS and G1 have different architectures and heap management policies. Flags concerning CMS remark, initiating occupancy, or fragmentation do not have a one-to-one equivalent in G1.

Keeping `CMSInitiatingOccupancyFraction` just because it "worked well before" makes no sense when CMS is gone. If tuning G1 is needed, start from defaults and options **supported by the target JDK**, then measure in practice. Do not construct a tuning list with similar names without knowing their effects.

## 8. GC Combinations Removed Since JDK 9

JEP 214 removed old GC combinations that had previously been marked deprecated. Migration documentation cites cases such as:

- `DefNew + CMS`.
- `ParNew + SerialOld`.
- Incremental CMS.
- Several CMS foreground/compaction options.

Example of legacy Incremental CMS flag:

~~~bash
java -Xincgc -jar service.jar
~~~

Or:

~~~bash
java -XX:+CMSIncrementalMode -jar service.jar
~~~

These configurations should not be used on Java 9+. Depending on the runtime, they may be rejected immediately at startup. The fix is to **remove configuration flags for the defunct collector**, then select a supported collector and re-verify performance.

Some typical flags removed when handling legacy GC combinations include:

~~~text
-Xincgc
-XX:+CMSIncrementalMode
-XX:+UseCMSCompactAtFullCollection
-XX:CMSFullGCsBeforeCompaction=...
-XX:+UseCMSCollectionPassing
~~~

The list is not exhaustive, and each flag may have a different parser status depending on the JDK. Do not look for a similar flag on G1 merely by guessing names.

## 9. PermGen Flags After Java 8

Two historical options:

~~~text
-XX:PermSize=...
-XX:MaxPermSize=...
~~~

relate to the **Permanent Generation** in older HotSpot JDKs. PermGen was removed in Java 8 (JEP 122), replaced by the Metaspace mechanism.

A familiar message on the corresponding runtime:

~~~text
Java HotSpot(TM) 64-Bit Server VM warning:
Ignoring option MaxPermSize; support was removed in 8.0
~~~

This is **not necessarily a startup error**. However, the flag was ignored, so it should not be kept as part of "valid tuning".

### 9.1. Do not mechanically replace PermGen with Metaspace

There are flags such as:

~~~text
-XX:MetaspaceSize=...
-XX:MaxMetaspaceSize=...
~~~

However, their meaning is not strictly equivalent to PermGen. Metaspace primarily stores class metadata outside the Java heap; `MetaspaceSize` affects GC thresholds/policies for metadata, while `MaxMetaspaceSize` bounds metaspace.

Do not take an old `MaxPermSize=256m` and set `MaxMetaspaceSize=256m` just to preserve the same number. First measure class loading and metadata under workload; setting the cap too low can cause `OutOfMemoryError: Metaspace`.

## 10. Migrating Legacy GC Logging to Unified Logging

Since Java 9, HotSpot uses Unified JVM Logging. Java 8 flags such as:

~~~bash
java \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/var/log/app/gc.log \
  -jar service.jar
~~~

must be **reviewed and converted**. Some flags are still mapped with warnings in newer JDKs, while others have been removed, so do not rely on compatibility aliases.

### 10.1. Reference mapping table

| Legacy logging flag | Intent | Approach on JDK 9+ |
|---|---|---|
| `-XX:+PrintGC` | Basic GC events | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | GC details | `-Xlog:gc*` |
| `-XX:+PrintGCDateStamps` | Wall-clock timestamp | Decorator `time` |
| `-XX:+PrintGCTimeStamps` | Uptime timestamp | Decorator `uptime` |
| `-Xloggc:file` | Write GC log to file | `-Xlog:gc:file=...` or `gc*` |
| `-XX:+PrintHeapAtGC` | Heap info at each GC | `-Xlog:gc+heap=trace` |
| `-XX:+PrintTenuringDistribution` | Object age distribution | `-Xlog:gc+age*=debug` or appropriate trace |
| `-XX:+PrintReferenceGC` | Reference processing | `-Xlog:gc+ref*=debug` |
| `-XX:+PrintGCApplicationStoppedTime` | Application stop time | `-Xlog:safepoint` |
| `-XX:NumberOfGCLogFiles=...` | Number of rotated log files | File output option `filecount=...` |
| `-XX:GCLogFileSize=...` | Size of each file | File output option `filesize=...` |
| `-XX:+UseGCLogFileRotation` | Enable rotation | Configure rotation in `-Xlog` output options |

The table aims to translate the **logging intent**, not claim that log contents across two JDKs can be compared byte-to-byte. Unified Logging changes format, tags, timestamps, and level of detail.

### 10.2. A pragmatic modern configuration

~~~bash
java \
  "-Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar service.jar
~~~

The configuration above:

- Selects logs with GC and corresponding safepoint tags at the default level.
- Writes to a file.
- Adds time/uptime/level/tags decorators.
- Limits the number of files and log size according to framework support.

Directory write permissions and storage capacity must be verified. Overly verbose logging can generate large volumes of data; do not default to trace in long-running production.

### 10.3. View exact syntax on the target JDK

~~~bash
java -Xlog:help
~~~

If a nonexistent tag is passed, the JVM may report an error about logging configuration. That does not mean GC was removed. Change tags/levels/decorators to match the version documentation.

### 10.4. Do not keep two logging systems simultaneously

Combining both `-XX:+PrintGCDetails` and `-Xlog:gc*` can cause warnings or duplicate/overwriting configurations depending on the runtime. Choose one unified configuration matching the target JDK, store it in the authoritative build/deployment source, verify the written log file, and ensure dashboard parsers understand the new format.

## 11. ZGC: Mode Options Changed Across JDK 21–24

ZGC is an example showing that a collector still exists, yet its **mode selection flag** can change.

Milestones:

1. **JDK 21:** Generational ZGC was introduced (JEP 439).
2. **JDK 23:** Generational ZGC became the default mode **when ZGC is selected** (JEP 474).
3. **JDK 24:** Non-generational ZGC was removed (JEP 490); there is no longer a need to maintain the `ZGenerational` mode selection flag.

An old command might contain:

~~~bash
java -XX:+UseZGC -XX:-ZGenerational -jar service.jar
~~~

When upgrading to JDK 24+, **do not keep the option requesting non-generational mode**. If selecting ZGC, you can start from:

~~~bash
java -XX:+UseZGC -jar service.jar
~~~

However, this is not advice to choose ZGC for every application. Heap headroom, CPU, and workload may make G1/Parallel GC more suitable. If the program encounters a `ZGenerational` error, check release docs to distinguish whether the flag was removed, obsolete, or unsupported in the current build.

### 11.1. ZGC's default differs from the whole JVM's default

"Generational ZGC is the default" means **when running ZGC**, generational mode is used in JDKs that switched the default. It **does not mean ZGC becomes the default collector for all Java applications**. On many HotSpot server configurations, G1 remains the default collector when no other GC is selected.

## 12. Do Not Select a Collector with a Conflicting Set of Flags

A common situation when multiple configuration layers assemble JVM arguments:

~~~text
JAVA_TOOL_OPTIONS:
  -XX:+UseG1GC

Container entrypoint:
  -XX:+UseParallelGC

Gradle/Maven or app script:
  -XX:+UseZGC
~~~

If the JVM rejects choices that cannot be used simultaneously, that is a **GC selection conflict** issue, not necessarily that the collector was removed.

Procedure:

1. Collect all launcher arguments from scripts, environment, and process managers.
2. Identify exactly one collector to use or let the JVM choose the default.
3. Remove duplicate/conflicting GC selector flags.
4. Delete leftover CMS-only options.
5. Start up and inspect the actual GC.
6. Run benchmarks before release.

**Do not apply a "last flag wins" rule to all JVM flags.** Some flags can override, whereas conflicting flags can cause the JVM to refuse startup; the behavior depends on the flag/runtime.

## 13. Finding Where Old Flags Are Passed From

This is often the most time-consuming step. A startup option can appear in:

- Shell scripts `start.sh`, `startup.bat`.
- systemd unit files and drop-in overrides.
- Dockerfile `ENTRYPOINT`, `CMD`.
- Kubernetes Deployment/Helm values, ConfigMap, and environment.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `_JAVA_OPTIONS` when supported by the corresponding JVM.
- Gradle `org.gradle.jvmargs`, `Test.jvmArgs`, `JavaExec.jvmArgs`.
- Maven `MAVEN_OPTS`, `.mvn/jvm.config`, Surefire/Failsafe `argLine`.
- IDE run/debug configurations.
- Application server startup scripts or container entrypoint.
- Cron/job scheduler, init scripts, agent/profiler bootstrap.
- JDK argument files `@options.txt`.
- Platform-injected defaults and organization launcher wrappers.

### 13.1. Checking environment sources

Unix-like shell:

~~~bash
printf '%s\n' "$JAVA_TOOL_OPTIONS"
printf '%s\n' "$JDK_JAVA_OPTIONS"
printf '%s\n' "$_JAVA_OPTIONS"
~~~

PowerShell:

~~~powershell
$env:JAVA_TOOL_OPTIONS
$env:JDK_JAVA_OPTIONS
$env:_JAVA_OPTIONS
~~~

**Security note:** environment variables and startup args may contain endpoints, tokens, or secrets. Do not paste them entirely into tickets or public logs; extract only the relevant flags and redact sensitive values.

Not every JDK/runtime/launcher handles these three variables the same way. In particular, `JDK_JAVA_OPTIONS` is a Java launcher mechanism introduced in a newer JDK generation; do not expect it to work on every JDK 8.

### 13.2. Searching in the repository

For example, with ripgrep:

~~~bash
rg -n 'UseConcMarkSweepGC|CMS|PrintGC|Xloggc|PermSize|ZGenerational' .
~~~

For a real repository with many configuration types, you should also search for `-XX:`, `-Xlog`, `JAVA_TOOL_OPTIONS`, and `org.gradle.jvmargs`. Some flags reside only in CI secrets/configs outside the repo, so searching source alone is not enough.

### 13.3. When the process has already started

HotSpot provides several commands:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.version
~~~

Replace `<pid>` with the actual PID. These commands only work when the JVM is running and the tool has attach permissions. **If the process could not start because of an unrecognized flag, there is no process to jcmd**; in that case inspect the launcher, service manager, scripts, and stderr first.

## 14. Gradle: Daemon Errors Differ from Test Worker Errors

An error may occur when the Gradle daemon fails to start or when the `Test` task forks a JVM. Both cases require different configurations.

### 14.1. Gradle daemon

Example old `gradle.properties`:

~~~properties
org.gradle.jvmargs=-Xmx2g -XX:+UseConcMarkSweepGC
~~~

When the Gradle daemon runs on a JDK that does not support CMS, this flag may be ignored with a warning or cause an error depending on the release. Check the daemon's JVM and remove the faulty option from its declaration source.

If no specific GC choice is needed, you can keep a minimal baseline:

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

`-Xmx2g` is just an example; choose according to the memory budget for the daemon/build workload, do not treat this as a default optimal value.

### 14.2. Gradle Test JVM

Test forks can use a different JVM and flags from the daemon. Example in `build.gradle.kts`:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "-XX:+UseG1GC",
        "-Xlog:gc"
    )
}
~~~

This is an option for **JDK 9+** if the test launcher supports it. If the project still runs tests on Java 8, do not use `-Xlog:gc` for Java 8; configure per test runtime or separate jobs.

Do not apply GC flags indiscriminately to every task if some tasks run on a different JDK. And configuring `Test.jvmArgs` does not change the Gradle daemon's JVM flags.

### 14.3. Gradle JavaExec/application plugin

A task running the app:

~~~kotlin
tasks.named<JavaExec>("run") {
    jvmArgs("-XX:+UseG1GC", "-Xlog:gc")
}
~~~

This code assumes the project actually has a `run` task (for example from the Application plugin). In a real project, task names and plugins must be confirmed. Startup scripts generated by the Application plugin may have separate JVM configurations; check the deployment artifact, not just `gradlew run`.

### 14.4. Do not fix daemon errors with test arguments

If the message is in the log "Unable to start the daemon process" or the Gradle daemon's JVM command line, editing `tasks.test.jvmArgs` will not help the daemon start. Conversely, changing `org.gradle.jvmargs` will not necessarily affect test child JVMs.

Errors must be classified by the **actual failing JVM process** before making fixes.

## 15. Maven: MAVEN_OPTS Differs from Surefire/Failsafe argLine

Maven also has multiple JVM layers:

- Maven runtime receives certain arguments from `MAVEN_OPTS` or `.mvn/jvm.config` per configuration.
- The compiler plugin uses the compiler in the runtime or selected toolchain.
- Surefire/Failsafe can fork JVMs to execute tests.
- Application plugin/custom launchers can spawn independent processes.

Example of legacy flags in `.mvn/jvm.config`:

~~~text
-Xmx2g
-XX:+UseConcMarkSweepGC
~~~

If the JDK running Maven no longer supports CMS, modify this file per compatibility policy. Do not only edit POM dependencies.

### 15.1. Surefire argLine

Example POM for tests on a JDK supporting `-Xlog`:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-XX:+UseG1GC -Xlog:gc</argLine>
  </configuration>
</plugin>
~~~

Plugin versions must be managed through the actual POM configuration. If JaCoCo or another plugin appends JVM args via `argLine`, integrate their variable/property mechanisms properly to avoid overwriting agent options or duplicating flags.

A Surefire `argLine` does not configure Maven core or Failsafe/the production application. To investigate errors, identify the command line of the **test fork** and the running plugin.

## 16. IDE and CI: A Configuration Valid on One Machine May Fail on Another

An IDE run configuration may use Java 17 where `-XX:+UseConcMarkSweepGC` is ignored with a warning; CI runs a different JDK and fails hard. Or the IDE does not pass the old flag while CI scripts still do.

To avoid drift:

1. Record the exact JDK of the IDE, Gradle/Maven, test worker, and CI.
2. Choose a clear build tool wrapper and Java toolchain/baseline.
3. Centralize important GC flags in version-controlled configuration.
4. Create environment-specific exceptions only with justification and an owner.
5. Test the production launcher **outside the IDE** with the real runtime image.
6. Do not treat `java -version` in a terminal as proof that CI uses the same JDK.

If tests are run using a separate IDE runner, results may differ from running Gradle/Maven tasks because the classpath, VM args, and test engine differ. For migration, standard build commands in CI should be the final source of confirmation.

## 17. Docker/Kubernetes: Failure Before Health Check

An old Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar

ENTRYPOINT [
  "java",
  "-XX:+UseConcMarkSweepGC",
  "-XX:+PrintGCDateStamps",
  "-jar",
  "/app/app.jar"
]
~~~

This is an example with wrong/no longer appropriate legacy flags. An illustrative post-migration configuration:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar

ENTRYPOINT [
  "java",
  "-XX:+UseG1GC",
  "-Xlog:gc*:stdout:time,uptime,level,tags",
  "-jar",
  "/app/app.jar"
]
~~~

Using a specific base image must follow policy and **pin the digest** in production when reproducibility is needed. In practice you can rely on the default GC and omit `-XX:+UseG1GC` if the default collector has been verified as suitable.

Several notes:

- A Kubernetes Deployment or Helm chart can inject `JAVA_TOOL_OPTIONS` outside the Dockerfile.
- Startup scripts may read both `JAVA_OPTS` and `JAVA_TOOL_OPTIONS`; `JAVA_OPTS` itself is not a variable automatically applied by the standard Java launcher, it takes effect when used by a script.
- A container may have multiple JVM child processes with different flags.
- Writing GC logs to a file requires a writable mount and rotation/retention; stdout may suit Kubernetes logging stacks.
- If the JVM does not start, the readiness probe cannot pass; container restart events do not prove the application served requests.
- If changing `-Xmx` alongside the collector, check cgroup memory headroom for metaspace, thread stacks, and native memory.

## 18. Warning: IgnoreUnrecognizedVMOptions Is Not a Migration Fix

HotSpot may support the flag:

~~~text
-XX:+IgnoreUnrecognizedVMOptions
~~~

It can cause certain unrecognized options to be ignored, depending on the JVM and flag parsing mechanism. However, this is **not a sustainable solution** for migration.

### 18.1. Why should it not be enabled broadly?

- An important flag with a typo may silently have no effect.
- The expected collector is not selected, causing changes in latency/throughput.
- A security/diagnostic flag is ignored, making the operations team think the policy is enabled.
- Old/new environments run with different actual configurations despite identical commands.
- An ignored removed flag does not mean the feature was replaced.
- Certain errors involving values, conflicts, or availability are not necessarily masked by this option.

If it was ever used as a workaround, record an owner and a removal deadline; **list all ignored flags completely and transition to a supported configuration**.

### 18.2. Must fail fast on misconfiguration

For production, a required option not understood by the JVM should usually make the deployment fail clearly, instead of silently running with an unexpected configuration. There should be startup validation on the target JDK and verification of actual flags/collector after launch.

## 19. When a Flag Only Triggers a Warning and the JVM Still Starts

This is easier to miss than a hard failure. For example:

~~~text
warning: Ignoring option MaxPermSize; support was removed ...
~~~

or a warning that an old logging option was mapped to `-Xlog`.

If the JVM still starts:

1. Record the warning and the JDK version.
2. Determine whether the flag is deprecated/obsolete.
3. Check whether runtime behavior still matches expectations.
4. Remove or replace the flag per JDK documentation.
5. Re-run startup with the new configuration.
6. Compare collector, heap sizing, GC logs, and performance.
7. Do not ignore warnings merely because the exit code is 0.

Specifically, **CMS was removed yet CMS flags may be ignored**. In that case the application is running a different collector. Without measuring, you cannot say the migration preserved pause/throughput.

## 20. Checking the Collector and Heap Actually Selected

After removing legacy flags, do not stop at "the JVM starts".

### 20.1. GC startup logging

On Java 9+:

~~~bash
java -Xlog:gc -jar service.jar
~~~

Startup logs typically include a line reporting the collector in use, such as G1. Log structure varies by version.

### 20.2. Printing flags at startup

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Command lines can be intentionally used to filter flags like `UseG1GC`, `UseParallelGC`, `UseZGC`, `MaxHeapSize`, `MaxGCPauseMillis`. The `PrintFlagsFinal` tool only shows how the JVM understands/computes flags for a runtime version; it does not replace a benchmark.

### 20.3. On a running JVM

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Replace `<pid>` with the real PID. Command availability differs by JDK/collector; use `jcmd <pid> help` when needed. For a Java process that died before startup, there is no live PID to inspect.

### 20.4. Mind logging permissions/paths

If `-Xloggc:/var/log/app/gc.log` is replaced with `-Xlog:...file=...` while the application runs as non-root, a GC log write failure may prevent the JVM from initializing as expected. Diagnosis includes filesystem permissions and container log storage; do not conclude the GC flag parser is wrong if the issue is file output.

## 21. A Pipeline to Detect Faulty JVM Flags Before Deployment

A smoke test step can be designed in CI **on the exact JDK runtime image**:

~~~text
1. Build artifact
2. Assemble production VM options
3. Validate startup with target java executable
4. Capture stderr/stdout and version
5. Start application or minimal smoke workload
6. Inspect collector and GC logging
7. Run regression/integration tests
8. Compare SLO and memory
9. Publish only if gates pass
~~~

It is not mandatory to build a new program to parse flags. However, **merely running `java -version` on the runner is not enough** if production options are assembled from Helm values/entrypoint or if CI uses a different JDK from the image.

### 21.1. Startup argument file example

On a Java launcher supporting argument files:

~~~text
# vm-options.txt
-Xms512m
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Run:

~~~bash
java @vm-options.txt -jar service.jar
~~~

Consolidating flags into one file helps diff reviews and avoids copy-paste. However, verify argument file syntax for the exact launcher version, encoding, and how parameters are merged with arguments added by the environment.

A config-generation step can be used to select flag sets by target JDK, but that logic must be version-controlled and tested. Do not hardcode many old flags and merely turn on ignore mode.

## 22. Starting Up Does Not Mean Compatible Performance

After removing CMS flags, the application may run on G1 or another collector with very different behavior:

| Metric | Why measure it |
|---|---|
| p50/p95/p99 latency | GC pauses can affect tail latency |
| Throughput | Collector and CPU overhead may change |
| GC pause count/duration | Compare against targets, not just event counts |
| Heap used/committed/max | Changing collector can alter heap ergonomics |
| RSS/container memory | Native/GC bookkeeping memory may also change |
| CPU throttling | Concurrent GC and thread count are affected by quotas |
| Startup/warm-up | JIT and class loading may differ |
| OOME/OOMKilled | A new collector is not immune to insufficient headroom |

There is no one-to-one mapping from `CMSInitiatingOccupancyFraction` to a G1/ZGC value that guarantees old latency. Benchmark on a representative request mix and memory/CPU limits.

### 22.1. Comparing GC logs by common goals

GC event names, phases, and memory region structures can differ across CMS/G1/ZGC. Do not compare "young GC" counts or total log line counts as an exact equivalent metric.

Instead compare:

- Total work throughput.
- Pause times (distribution and max) in unified units.
- GC CPU/overhead.
- Allocation/live-set/headroom when available.
- p99 application latency.
- Peak RSS and total memory budget.
- Stability over a sufficiently long load test.

## 23. Investigation Example: From JDK 8/CMS to JDK 21

Suppose the old script contains:

~~~bash
java \
  -Xms1g -Xmx4g \
  -XX:+UseConcMarkSweepGC \
  -XX:+CMSIncrementalMode \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -Xloggc:/logs/gc.log \
  -jar billing.jar
~~~

### Step 1: Identify the first error

If the JVM reports `Unrecognized VM option 'CMSIncrementalMode'` or `PrintGCDateStamps`, do not modify application classes. Those flags belong to legacy GC/logging mechanisms.

### Step 2: Remove the entire family of obsolete flags

Do not remove only the single flag mentioned in the first error and stop. There may be many other legacy flags; each time the JVM parses the next flag, it fails again.

### Step 3: Replace the collector selector

Let the JVM use the default or intentionally select G1 after reviewing support and benchmarking. Do not treat G1 starting up as a 1:1 performance replacement for CMS.

### Step 4: Migrate logging

Example:

~~~bash
java \
  -Xms1g -Xmx4g \
  -XX:+UseG1GC \
  "-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar billing.jar
~~~

### Step 5: Verify effectiveness

Confirm the selected GC is G1, the log file is created, the app-running account has write permissions, and heap sizing matches expectations.

### Step 6: Run regression

Run the same business functionality and workload on old/new environments, recording memory, pauses, error rate, and p99 latency. Do not randomly upgrade drivers, ORMs, or change schemas in the same test if the goal is to isolate GC impact.

All commands in examples are only educational material, **not commands executed on the reader's system**.

## 24. Investigation Example: Legacy ZGC on JDK 24

Suppose production is using ZGC with:

~~~text
-XX:+UseZGC
-XX:-ZGenerational
~~~

After upgrading to JDK 24, non-generational ZGC was removed. Do not keep an option requesting a removed mode.

Remediation approach:

1. Check the JDK runtime and release notes.
2. Remove `-XX:-ZGenerational` when upgrading to a release without this mode.
3. Keep `-XX:+UseZGC` **only if there is justification for choosing ZGC**.
4. Run startup validation and GC logs.
5. Benchmark heap headroom, GC CPU, and latency; workloads previously tuned for non-generational may have different trade-offs.
6. Save results and update config docs.

Do not say "Java removed ZGC" — what was removed is the **non-generational mode**, not the entire ZGC collector.

## 25. Investigation Example: Gradle Daemon Fails to Start, Application Has No Error

The log may contain:

~~~text
Unable to start the daemon process.
Unrecognized VM option 'SomeRemovedFlag'
~~~

If the flag is in `org.gradle.jvmargs`, the failing JVM is the **Gradle daemon**. Reasonable steps:

1. Check the Gradle JVM/JDK in terminal/IDE/CI.
2. Check `gradle.properties` at project/user scope and launcher settings.
3. Locate the old flag in `org.gradle.jvmargs`.
4. Remove/replace unsupported flags for the daemon.
5. Restart the build using the right wrapper version.
6. Only then inspect `Test` and `JavaExec` child JVMs.

There is no need to modify `-Xmx` of the application container if only the Gradle daemon fails. And do not mass-delete Gradle caches to solve an option parser error.

## 26. Investigation Example: Production App Fails While Unit Tests Pass

In CI, unit tests may run with default G1, whereas the Kubernetes manifest passes:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:+UseConcMarkSweepGC -XX:+PrintGCDateStamps"
~~~

This is an example of an option source **outside repository build tasks**. The reason unit tests pass is that the test JVM did not receive the same flags; the error only appears when the pod starts.

Fix it in the deployment configuration, run the exact image/entrypoint in staging, and add a startup flag check step to the pipeline. Do not mark migration complete merely because unit tests are green.

## 27. Case Where the Flag Was Not Removed but the Value Is Invalid

Not every parsing error is a removed option. For example:

~~~text
-XX:MaxGCPauseMillis=abc
~~~

The flag may exist, yet `abc` is not a valid value. Or:

~~~text
-Xmx-1g
~~~

is invalid sizing syntax. Some flags require special ranges or dependency conditions.

How to diagnose:

- Verify that the option name exists in the target JVM.
- Check the right boolean/numeric/size format.
- Check the range/units.
- Check unlock requirements if it is experimental/diagnostic.
- Check dependent or conflicting flags.
- Run a reproduction with just one flag, then combine gradually.
- Do not use `IgnoreUnrecognizedVMOptions` to mask invalid values.

If the error says "improperly specified VM option", "outside the allowed range", or similar, preserve the original message in the report; do not lump every error under unrecognized.

## 28. JVM Vendor and Runtime Image Also Matter

Java distributions are not necessarily identical regarding:

- Which GCs are available on an OS/architecture.
- Experimental/diagnostic flags.
- Patches/backports across update trains.
- Minimal runtime images or custom `jlink`.
- GC logging support and build-time features.
- How packaged launchers pass options.

For example, a collector might not be built for a platform, even if the JDK feature number is the same. Verify using vendor documentation and runtime introspection commands; do not assume a JDK has a collector just from reading a general JEP.

When deploying across multiple architectures (Linux x64/ARM64/Windows), verify startup and GC flags on **every declared supported combination**.

## 29. Distinguishing JVM Option Errors from Java Application Option Errors

A command:

~~~bash
java -Xmx1g -jar app.jar --mode=batch
~~~

is normally parsed as:

- `-Xmx1g` is a JVM option before `-jar`.
- `--mode=batch` is an application argument after the JAR name.

However:

~~~bash
java -jar app.jar -XX:+UseG1GC
~~~

usually passes `-XX:+UseG1GC` to the **application** as an argument, not configuring the Java launcher's GC because it follows the JAR. The CLI framework may report "unknown option", easily confused with the JVM's `Unrecognized VM option`.

Therefore, check **argument positions** before and after `-jar`, `--module`, or the main class. With shell wrappers, ensure JVM flags are placed properly on the launcher side.

## 30. Testing Plan and Go/No-Go

A change resolving an option error needs to pass at least appropriate gates:

| Gate | Question | Evidence |
|---|---|---|
| Static audit | Are there removed/obsolete flags in any configuration source? | Inventory of VM options, diff |
| Parse/startup | Does the target JVM accept all flags? | Exit code, stderr, logs |
| Collector selection | Is the right GC or approved default selected? | GC init log, VM.flags |
| Logging | Are GC/safepoint logs written properly? | File/stdout, retention config |
| Memory | Are heap/metaspace/native within budget? | JVM metrics, RSS/container usage |
| Performance | Do p99 latency, throughput, and GC pauses meet SLO? | Load test, GC logs |
| Regression | Do business behavior and negative tests remain correct? | Unit/integration/security tests |
| Reproducibility | Do IDE/CLI/CI/production use controlled config? | Artifact and environment fingerprint |
| Rollback | Can we revert to a stable artifact/config? | Rollout and recovery plan |

Do not automatically accept an ignored option as a safety signal. An application running a different collector than intended can develop regressions under load even when smoke tests pass.

## 31. 12-Step Diagnostic Procedure

### Step 1 — Save the verbatim error and timestamp

Keep stderr/stdout and the first message, avoiding saving only the final line `Could not create the Java Virtual Machine`. Record JDK path/version, OS, container image, and service/job name.

### Step 2 — Identify which process failed

Gradle daemon, Maven, test worker, application server, batch job, or Java agent? The fix paths differ.

### Step 3 — Collect full JVM arguments

Check scripts, environment, IDE, Gradle/Maven, CI, Docker/Kubernetes, argument files, and service managers. Redact secrets in logs.

### Step 4 — Classify each flag

Label supported/deprecated/obsolete/removed/unknown/vendor-specific/invalid value. Do not just remove the first flag in the error.

### Step 5 — Check documentation for the exact JDK

Use `java --help-extra`, `-Xlog:help`, `-XX:+PrintFlagsFinal`, vendor docs, and release notes. For collector changes, inspect relevant JEPs.

### Step 6 — Create a minimal reproduction

Test `java [flag] -version` on the exact target Java executable. Separate option errors from application logic.

### Step 7 — Remove flags that no longer take effect

Do not keep `MaxPermSize`, CMS-only options, or removed modes just because they might still be ignored.

### Step 8 — Replace logging goals with new syntax

Migrate GC logs to `-Xlog`, verifying tags/decorators/rotation/output permissions and log ingestion.

### Step 9 — Select GC intentionally

Use the default or a supported collector based on latency/throughput/memory requirements. Do not copy CMS tuning into G1/ZGC.

### Step 10 — Run the actual real launcher

Use the artifact and container/VM entrypoint like production, not just `java -version` on a laptop.

### Step 11 — Run regression and performance tests

Compare the application on old/new JDKs with equivalent test suites, workloads, and memory/CPU budgets within the supported scope.

### Step 12 — Record evidence and lock down ownership

Save JVM argument diffs, actual GC, JDK build, test reports, metrics, untested areas, and review plans for the next JDK upgrade.

## 32. Sample JVM Options Audit Table

| Existing option | Source | Target JDK | Classification | Decision |
|---|---|---|---|---|
| `-XX:+UseConcMarkSweepGC` | Deployment script | 21 | CMS no longer exists | Remove, check default/G1 |
| `-XX:+CMSIncrementalMode` | Startup args | 21 | Incremental CMS unsupported | Remove |
| `-XX:+PrintGCDateStamps` | Launcher | 21 | Legacy GC logging | Switch to `-Xlog` decorator |
| `-Xloggc:gc.log` | Launcher | 21 | Legacy/deprecated logging form | Switch to `-Xlog` |
| `-XX:MaxPermSize=256m` | Old build config | 21 | Obsolete/ignored | Remove, do not cap mechanically |
| `-XX:-ZGenerational` | ZGC config | 24 | Non-generational mode removed | Remove, run generational ZGC if choosing ZGC |
| `-Xmx2g` | Deployment | 21 | Supported sizing | Keep if memory budget confirms |
| `-XX:+UseG1GC` | Application script | 21 | Supported collector | Keep or use default after testing |

This is an **analysis sample**, not the result from a real service. "Target JDK" is only an example to illustrate identification; before editing, you must still inspect specifically which flags are accepted or ignored by the runtime/vendor.

## 33. Incident Report Template for Prime or Reviewer

~~~yaml
incident:
  category: "JVM_STARTUP_FLAG"
  symptom: "Unrecognized VM option"
  failingProcess: "application container"
  targetJdk:
    version: "record java -version"
    vendorBuild: "record exact build"
  option:
    name: "CMSIncrementalMode"
    source: "deployment JVM arguments"
    original: "-XX:+CMSIncrementalMode"
  change:
    action: "remove legacy CMS option"
    replacementCollector: "G1"
    logging: "-Xlog:gc*"
  validation:
    startup: "NOT_YET_RUN"
    actualCollector: "NOT_YET_VERIFIED"
    regressionTests: "NOT_YET_RUN"
    performanceTest: "NOT_YET_RUN"
  risks:
    - "GC pause profile can differ from CMS"
  owner: "runtime-team"
~~~

Do not replace `NOT_YET_RUN` with PASS before logs/artifacts exist. Attach commits, JDK build, binary/container digest, test reports, workload, and actual SLO figures.

## 34. Misconceptions to Avoid

**"Unrecognized VM option means Java code is wrong."** No. This is usually a launcher/JVM arguments error before the application runs.

**"CMS was removed in JDK 14 so every CMS flag reports unrecognized starting in JDK 14."** No. Some may be obsolete, accepted and ignored; others were removed earlier or later.

**"JVM starts successfully means every flag was applied."** No. Obsolete flags may be ignored with warnings.

**"Just enabling `IgnoreUnrecognizedVMOptions` is enough."** No. It can hide even critical misspelled flags.

**"CMS GC tuning has an equivalent mapping to G1."** No. Algorithms and goals differ.

**"JDK 9 and later still need `PrintGCDateStamps`."** No. Unified Logging uses decorators like `time` and `uptime`.

**"`PrintGCDetails` and `-Xlog:gc*` always produce identical files."** No. Format/tags/levels change.

**"Generational ZGC is default means every application uses ZGC."** No. It only states ZGC's mode when ZGC is selected.

**"ZGC was removed from JDK 24."** No. Non-generational mode was removed, not the entire collector.

**"Running `java -version` in the terminal is enough to verify production."** Not if the app/container/test JVM differs.

**"All startup JVM options must reside in source."** No. They can come from CI, Docker, environment, service managers, IDE, and tool wrappers.

**"Only fixing the first flag that fails is enough."** There may be another chain of incompatible flags.

**"The new JDK still has this flag so every vendor/architecture supports it."** Not necessarily.

**"Changing GC and having functional tests pass means it is done."** Latency, throughput, GC overhead, memory, and OOM risk must be evaluated.

**"Removing `-Xmx`/setting heap right up to the memory limit avoids startup errors."** Unrelated to unrecognized flags and can cause OOMKilled.

## 35. Post-Migration Verification Checklist

- [ ] Identified exact JDK feature/update/vendor/build of the failing process.
- [ ] Recorded full startup message and the first option name.
- [ ] Distinguished Gradle daemon, Maven core, test JVM, and application JVM.
- [ ] Checked `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `_JAVA_OPTIONS`, and launcher script sources where applicable.
- [ ] Audited source/build/CI/container/Helm/systemd/IDE for legacy GC flags.
- [ ] Classified flags as supported, deprecated, obsolete, removed, or invalid.
- [ ] Removed CMS-only/incremental-CMS flags when moving to an unsupported JDK.
- [ ] Removed PermGen flags and did not force metaspace caps based on old values without basis.
- [ ] Updated ZGC mode flags according to the target JDK if using ZGC.
- [ ] Migrated legacy GC logging to `-Xlog` on Java 9+.
- [ ] Checked logging tags/decorators/rotation and output write permissions.
- [ ] Removed duplicate/conflicting flags when assembled from multiple sources.
- [ ] Did not use `IgnoreUnrecognizedVMOptions` as a long-term solution.
- [ ] Ran startup tests with the **exact production JDK and launcher options**.
- [ ] Confirmed effective collector/heap flags from logs/JVM diagnostics.
- [ ] Ran regression tests with the real application artifact.
- [ ] Compared latency, throughput, GC pauses, RSS, and memory budget.
- [ ] Recorded which tests have not run and which environments were not verified.
- [ ] Saved configuration diffs, JDK build, logs, and the go/no-go decision.
- [ ] Assigned an owner and rollback/roll-forward plan in case of regressions.

## 36. Official Reference Documentation

Prioritize documentation for the **exact target JDK** instead of copying flags from guides written years ago:

- **JEP 122 — Remove the Permanent Generation:** https://openjdk.org/jeps/122
- **JEP 158 — Unified JVM Logging:** https://openjdk.org/jeps/158
- **JEP 214 — Remove GC Combinations Deprecated in JDK 8:** https://openjdk.org/jeps/214
- **JEP 248 — Make G1 the Default Garbage Collector:** https://openjdk.org/jeps/248
- **JEP 271 — Unified GC Logging:** https://openjdk.org/jeps/271
- **JEP 363 — Remove the CMS Garbage Collector:** https://openjdk.org/jeps/363
- **JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector:** https://openjdk.org/jeps/377
- **JEP 439 — Generational ZGC:** https://openjdk.org/jeps/439
- **JEP 474 — ZGC: Generational Mode by Default:** https://openjdk.org/jeps/474
- **JEP 490 — ZGC: Remove the Non-Generational Mode:** https://openjdk.org/jeps/490
- **Java 21 launcher options and GC logging mapping:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Oracle JDK 26 migration guide:** https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- **JDK 24 migration changes:** https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html

These links help verify official milestones and syntax. For newer JDKs or a different runtime vendor, check release notes, flags, and collector availability at deployment time.

## Conclusion

**`Unrecognized VM option` is a JVM startup configuration issue, not a bug to fix by modifying Java code.** When upgrading the JDK, legacy GC flags may be removed, become obsolete and be ignored, or remain accepted only as temporary aliases. CMS was removed from JDK 14, several Incremental CMS combinations were removed in JDK 9, and the new GC logging system since Java 9 uses `-Xlog`. With ZGC, mode changes across JDK 21–24 can also cause old flags to lose meaning or stop being supported.

The sustainable solution is to **identify the exact failing JVM, gather all startup options, classify each flag's status for the target JDK, remove or replace by exact function, and then verify the actual collector and logs**. Even after the application starts, regression/performance tests under representative load must still be run to verify performance and memory budget. "No more error messages" is only the first step; a good migration outcome is a traceable configuration, supported by the target JVM, with evidence of safe operation.