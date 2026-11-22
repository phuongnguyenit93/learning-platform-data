# Choosing How to Diagnose Errors in a Java Toolchain

When a Java build or application fails, diagnostic tools should be chosen based on the symptom and the failing layer. The **java --version** command can confirm the runtime, but it does not explain why Gradle picks a different JDK, why a dependency fails to resolve, why the IDE compiles successfully while CI fails, or why a JVM hangs.

An effective approach is to start with low-impact evidence, identify whether the failure lies in the environment, compiler, build tool, dependency, IDE, CI, or running JVM, and then choose a specialized tool for that layer. Each step should answer a specific question and help decide the next step.

## 1. Diagnosis Is Choosing the Right Layer, Not Running Many Commands

A Java toolchain typically consists of multiple layers:

1. Operating system, architecture, filesystem, and environment variables.
2. Installed JDK: java, javac, javadoc, jcmd, and other tools.
3. Build engine: Gradle or Maven, Wrapper, daemon, and plugins.
4. Compiler/toolchain selected by the build engine.
5. Dependencies, classpath, module path, and annotation processors.
6. IDE, test runner, and run configuration.
7. CI runner, container image, and cache.
8. JVM runtime, garbage collector, threads, memory, and native libraries.

An error can originate in one layer while being reported in another. For example, a “package does not exist” error can be caused by a wrong package in source code, a missing dependency, an incorrect classpath, or a module not exporting the package. Immediately adding a JAR to the classpath can mask the root cause if the application actually runs using JPMS.

Before choosing a command, rewrite the symptom into a verifiable question:

- Is the machine finding the right javac?
- Which JDK is the Gradle daemon running on?
- Which toolchain is the compiler task using?
- Which dependency is resolved, and from which repository?
- Is the JVM runtime the same version as the compiler?
- Does the error occur only in the IDE, only in CI, or in all environments?
- Is the process hanging, running out of memory, or just slow on a single task?

A clear question helps narrow the scope and avoid collecting unnecessary logs.

## 2. Step-by-Step Tool Selection Workflow

Use the following workflow for a new error:

1. **Reproduce:** record the command, working directory, timestamp, exit code, and the first meaningful part of the output.
2. **Determine scope:** is it only one machine, all developers, the IDE, CI, one module, one test, or a runtime process?
3. **Collect baseline:** OS/architecture, java, javac, Gradle/Maven version, JDK path, and toolchain configuration.
4. **Classify the failing layer:** environment, compile, dependency, module, test, IDE, CI, or runtime.
5. **Choose the smallest measurement:** the command needed to confirm or rule out the current hypothesis.
6. **Compare with a working environment:** use the same command, same project revision, and same input data.
7. **Increase detail when needed:** stack trace, --info log, dependency tree, module resolution, or JVM diagnostics.
8. **Form an evidence-based conclusion:** state the confirmed cause, what has been ruled out, and the next fix step.

Do not change the JDK, dependencies, plugins, and build flags simultaneously while diagnosing. If multiple factors change at once, it will be hard to determine which factor made the error disappear.

## 3. Quick Selection Table by Symptom

| Symptom | Question to Answer | Tool to Use First |
|---|---|---|
| java or javac not found | Where is the shell resolving the executable? | Get-Command, where.exe, command -v, PATH, JAVA_HOME |
| java is right but compiler is wrong | Do the runtime and compiler come from the same JDK? | java --version, javac --version, executable paths |
| Build uses the wrong JDK | Is the launcher JVM, daemon JVM, or compiler toolchain different? | gradle --version, javaToolchains, mvn -version, Maven toolchains |
| Syntax or API error during compile | In which file/line does the compiler report the first error? | javac diagnostic, --release, -verbose |
| Class/package not found | Is the dependency on the classpath/module path? | Gradle dependency insight, mvn dependency:tree, jdeps |
| Module fails to resolve | Do the module path and descriptor match? | jar --describe-module, java --show-module-resolution |
| Fails only in IDE | Which SDK, runner, and build model is the IDE using? | Project SDK, Gradle JVM, Maven Runner, IDE build log |
| Fails only in CI | How do the runner, image, JDK, and environment differ from local? | Version report, action log, image digest, CI environment |
| A single test fails | Does the test runner fork a JVM or use different properties? | Run the test individually, test report, test worker JVM args |
| Application hangs | Are threads running, blocked, or deadlocked? | jcmd PID Thread.print |
| High CPU or increased latency | Is CPU, lock, allocation, or I/O the bottleneck? | JFR, JDK Mission Control |
| Growing memory or frequent GC | Is heap, allocation, or native memory growing? | JFR, jcmd PID GC.heap_info, GC log |
| JVM crash | Is it a Java exception or a process crash in the native layer? | hs_err_pid log, OS crash report, core dump |

This table helps choose a starting point. If the result does not answer the question, move to the next layer instead of repeating the same command.

## 4. Verifying the JDK and Shell Environment

This is the first step when the error involves Java version, compiler, or toolchain.

### 4.1. Windows PowerShell

~~~powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac

$env:JAVA_HOME
java --version
javac --version
~~~

Get-Command shows which executable PowerShell will run and can display multiple matches with the same name. where.exe lists matching files in PATH. The where command without .exe in PowerShell is usually an alias for Where-Object, so use where.exe to avoid confusion.

### 4.2. Linux and macOS

~~~bash
command -v java
command -v javac
type -a java
type -a javac

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
java --version
javac --version
~~~

command -v shows which command the shell resolves; type -a can reveal aliases, functions, and multiple executables with the same name.

### 4.3. Checking Runtime Properties

~~~bash
java -XshowSettings:properties -version
~~~

Look for these properties:

- java.version: product version.
- java.runtime.version: full runtime version, usually including the build number.
- java.vendor: vendor string provided by the runtime.
- java.vm.name and java.vm.version: VM identity.
- java.home: actual Java home of the JVM.
- os.name, os.arch: operating system and architecture.
- file.encoding: default charset reported by the JVM.

JAVA_HOME is an environment configuration; java.home is a property of the running JVM. The two paths are usually related, but do not assume they are identical. Similarly, java --version and javac --version must be checked separately because the shell may resolve them from two different directories.

If javac is missing while java is present, the machine may only have a JRE/runtime image installed, or PATH may point to a runtime instead of a JDK. Verify the executable path and check whether JAVA_HOME/bin contains javac.

### 4.4. Environment Variables That Can Alter Results

In addition to JAVA_HOME and PATH, check whether there are variables affecting the launcher or build:

- JDK_JAVA_OPTIONS: appends options to the Java launcher.
- JAVA_TOOL_OPTIONS and _JAVA_OPTIONS: can inject JVM options/agents.
- GRADLE_OPTS and org.gradle.jvmargs: affect the JVM running Gradle.
- MAVEN_OPTS: affects the JVM running Maven.
- MAVEN_ARGS: can pass Maven arguments from the environment.
- CLASSPATH: can affect Java runs that do not use a module path or do not pass an explicit classpath.

Do not post full environment variable values in public issues or logs. Some variables may contain tokens, proxy credentials, internal paths, or JVM agents that should not be exposed. Only record the relevant variable names and values that have been reviewed/redacted for sensitive information.

## 5. Distinguishing the Build-Running JVM from the Compiling JDK

One of the common diagnostic mistakes is seeing that java --version is right and concluding that the entire build uses the right JDK.

### 5.1. Gradle

Start with:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

--version displays the Gradle version, launcher JVM, and daemon JVM. javaToolchains lists the JDKs discovered by Gradle along with their metadata.

Concepts to keep separate:

- **Launcher JVM:** the JVM running the Gradle client.
- **Daemon JVM:** the JVM running the Gradle build daemon.
- **Java compiler toolchain:** the JDK used for compile tasks.
- **Test/runtime launcher:** the JDK used to run tests or JavaExec.

A project can run Gradle on JDK 24 while compiling with JDK 17. This is valid if the build is configured that way. If the error only appears during compilation, check the compiler toolchain instead of only changing JAVA_HOME.

You can inspect logs for a specific task:

~~~bash
./gradlew compileJava --info
~~~

If you suspect a task is using the wrong toolchain, check the java.toolchain configuration, JavaCompile, Test, and JavaExec tasks, and the javaToolchains output.

### 5.2. Maven

~~~bash
mvn -version
mvn -e -DskipTests compile
~~~

mvn -version shows the Maven version and the JVM running Maven. If the project uses Maven Toolchains, the compiler plugin may use a different JDK. Check toolchains.xml, Maven Toolchains Plugin, and toolchain selection logs.

When you need the dependency tree:

~~~bash
mvn dependency:tree
~~~

To filter to a single dependency:

~~~bash
mvn dependency:tree -Dincludes=org.example:library
~~~

mvn -version does not prove that the right compiler toolchain was selected. You need to cross-check Maven's runtime, toolchain configuration, and compiler plugin.

### 5.3. --release Is Not a Way to Select a JDK

For example:

~~~bash
javac --release 17 Main.java
~~~

--release 17 restricts the language rules, class-file target, and Java SE APIs allowed for release 17. It does not select JDK 17 to run the compiler. A newer JDK compiler can still compile with --release 17.

Therefore, when investigating compatibility, check both the actual compiler JDK and the --release/toolchain target.

## 6. When the Error Is in the Compiler or Source Code

Start from the first error in the compiler output. Subsequent errors are sometimes just consequences of the first one.

Re-run the specific compile task to reduce log noise:

Gradle:

~~~bash
./gradlew compileJava --stacktrace
~~~

Maven:

~~~bash
mvn -e -DskipTests compile
~~~

If you need to see how the compiler reads files or locates classes, you can use javac -verbose on a small reproducible compile. Do not manually construct a javac command that differs completely from the build tool and conclude the source has a problem; a manual command may omit annotation processors, compiler arguments, classpath, or generated sources.

Check the following points:

- Do the source level and target release match?
- Are the import/package declarations correct?
- Have generated sources been generated before compilation?
- Are annotation processors declared and resolved at the right version?
- Is the compiler receiving the right classpath/module path?
- Do the IDE and build tool have the same compiler options?

If the error is invalid source release, release version not supported, or a missing API, cross-check the compiler JDK with --release before editing code.

## 7. When the Error Is in a Dependency or Module

Do not add another dependency just to make the error go away. First, identify which dependency is actually resolved.

### 7.1. Gradle Dependency Diagnostics

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

See why a particular version was selected:

~~~bash
./gradlew dependencyInsight --dependency guava --configuration compileClasspath
~~~

Replace guava with the dependency name to investigate. Use the right configuration, such as runtimeClasspath, testCompileClasspath, or a project-specific configuration.

### 7.2. Maven Dependency Diagnostics

~~~bash
mvn dependency:tree
mvn dependency:resolve
~~~

dependency:tree shows the dependency hierarchy after Maven resolves it. dependency:resolve helps confirm whether required dependencies can be downloaded and which versions are selected. If the error only involves one artifact, use -Dincludes=groupId:artifactId with dependency:tree.

### 7.3. Module Path

If the error involves JPMS, choose the tool based on the question:

~~~bash
jar --describe-module --file lib/example.jar
java --module-path lib --describe-module com.example.module
java --show-module-resolution --module-path lib --module com.example.app
jdeps --module-path lib --check com.example.app
~~~

- jar --describe-module: inspect the module descriptor inside a JAR.
- java --describe-module: inspect a module found on the module path.
- --show-module-resolution: see which dependencies are resolved at startup.
- jdeps --check: inspect descriptors and the module dependency graph.

If the module is found but a package is not visible, check exports. If the module cannot read a dependency, check requires. If the error is due to deep reflection, check opens and runtime access permissions. Fix the descriptor or module path properly rather than randomly adding JARs to the classpath.

## 8. When the Error Appears Only in the IDE

An IDE can maintain multiple independent Java configurations:

- Project SDK/JDK.
- Language level of the project or module.
- JDK used for Gradle import/build.
- JRE/JDK used for the Maven runner.
- JDK of the test runner and run configuration.
- Compiler settings, annotation processors, and generated-source directories.

If the command-line build succeeds but the IDE reports errors:

1. Check the Project SDK and module SDK.
2. Check the language level and bytecode target.
3. For Gradle, check the Gradle JVM and Wrapper used by the IDE.
4. For Maven, check the Maven Runner JRE.
5. Check whether the run/test configuration passes custom environment variables or VM options.
6. Refresh/sync the project model after changing build configuration.

If the IDE build succeeds but the Wrapper fails, run the exact Wrapper in a terminal and read the first error. The IDE may be using a different JDK or different caches/generated sources. Do not conclude that the IDE is using the right toolchain just because the editor shows no red underlines.

## 9. When the Error Appears Only in CI or a Container

Compare the actual environment, not just the configuration files.

In CI, record non-sensitive information:

~~~bash
java --version
javac --version
./gradlew --version
mvn -version
~~~

And identify:

- Runner OS, architecture, and image.
- In which step the JDK distribution/version is installed.
- Wrapper version and action/plugin version.
- Container image tag and digest if applicable.
- Working directory, checkout revision, and submodule state.
- Environment variables affecting the build, after redacting credentials.
- Cache key and cache state.
- Dependency repository, proxy, and certificate chain.

If the local build succeeds but CI fails, run the same Wrapper command on the same JDK feature/update version and the same project revision. If it still differs, compare dependency resolution, architecture, filesystem permissions, locale/timezone, and network.

Do not use cache clearing as a first step. First check the cache key and resolution logs. Clearing the cache can destroy evidence and lengthen build times; only do it when there are signs of stale cache or corruption.

## 10. Diagnosing Test and Runtime Exceptions

If compilation succeeds but tests fail, separate the test runner from the compiler:

- Do tests run in a forked JVM?
- Which JDK does the test worker use?
- Do tests receive custom system properties, environment variables, module opens, or agents?
- Does the failure depend on execution order or parallel test execution?
- Are there external resources outside the JVM such as a database, file, port, or service?

Run the failing test individually:

Gradle:

~~~bash
./gradlew test --tests "com.example.MyTest" --info
~~~

Maven Surefire:

~~~bash
mvn -Dtest=MyTest test -e
~~~

For runtime exceptions, preserve the first stack trace, exception cause, and thread name. Determine whether the exception originates in application code, a framework, the JDK, or a native library. Do not skip the first Caused by only to fix the last line.

If the process crashes outside the Java exception flow, look for hs_err_pid*.log, Windows Event Viewer, or an OS core dump. A JVM crash and a Java exception are two different classes of incidents.

## 11. Diagnosing Hung Processes, Deadlocks, or Slow Responses

If the JVM is still running but unresponsive, start with a thread dump:

~~~bash
jcmd -l
jcmd 12345 Thread.print
~~~

Replace 12345 with the actual PID. jcmd -l lists the JVMs visible to the tool. Thread.print prints thread stack traces and can include lock information if the option is supported.

A thread dump is a point-in-time snapshot. If you suspect a deadlock or blocked threads, take two or three dumps a short interval apart, then compare the stack traces:

- Does the stack stay on the same line?
- Are threads BLOCKED, WAITING, or running on CPU?
- Is there a recurring monitor/lock owner?
- Has the thread pool run out of workers?
- Are multiple threads waiting on the same external dependency?

jcmd must run on the same machine as the JVM and under the same effective user/group identity that started the JVM. In containers, PID namespaces can cause the host PID to differ from the PID inside the container. If the process is not visible, check the right container and namespace before concluding that attach is disabled.

## 12. Diagnosing CPU, Latency, and Memory with JFR

When the symptom is high CPU, increased latency, or heavy allocation, JDK Flight Recorder (JFR) usually provides better evidence than a single stack trace.

Start a time-bounded recording:

~~~bash
jcmd 12345 JFR.start name=ToolchainDiag settings=default duration=60s filename=toolchain-diag.jfr
~~~

After the recording completes:

~~~bash
jfr summary toolchain-diag.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample toolchain-diag.jfr
~~~

Use jcmd 12345 help JFR.start to check the options supported by the current JVM. The default template is suitable for basic collection; profile records more data and may introduce higher overhead. Choose short recordings, limit scope, and check disk space.

To view the heap summary:

~~~bash
jcmd 12345 GC.heap_info
~~~

You can correlate with GC logs if the application was started with appropriate logging:

~~~text
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Do not take a heap dump immediately upon seeing memory growth. A heap dump can be large, time-consuming, cause pauses, and contain sensitive data such as tokens, request payloads, or personal information. If truly necessary, confirm the recipient, free disk space, secure storage location, and retention/deletion policy before running GC.heap_dump.

Similarly, GC.class_histogram and other diagnostic commands have their own impact. Use jcmd <pid> help <command> to read the description and impact of the specific command before running it in production.

## 13. Choosing Detail Level and Impact

The most verbose log is not always the best choice.

| Level | Example | When to Use |
|---|---|---|
| 1. Read-only baseline | java --version, javac --version, gradle --version, mvn -version | Always start here |
| 2. Task/build log | Gradle --stacktrace/--info, Maven -e | Need to know where a task or plugin fails |
| 3. Resolution detail | Dependency tree, toolchain listing, module resolution | Version, dependency, compiler, or module errors |
| 4. Process snapshot | jcmd Thread.print, GC.heap_info | Running process is hung, slow, or using abnormal memory |
| 5. Recording/profiling | JFR, JDK Mission Control | Need to analyze CPU, latency, allocation, and GC over time |
| 6. Heap/core dump | GC.heap_dump, OS core dump | Deep investigation once justified with a storage plan |

Increase detail when current evidence is insufficient. If a step has confirmed the cause, stop collecting additional unnecessary data.

### 13.1. Protecting Information in Diagnostic Output

- Gradle --debug produces very large logs and may expose sensitive information.
- Maven -X may print repository configurations, proxies, and internal paths.
- Build Scan may send build data to an external service; use only if permitted by organizational policy.
- JFR, thread dumps, heap dumps, and core dumps can contain application data.
- Do not attach settings.xml, environment dumps, credentials, or full logs to public issues.
- Redact tokens, passwords, URLs with credentials, usernames, and customer data before sharing.

Collect only the data needed for the hypothesis under test and restrict access to diagnostic files.

## 14. Java 17 Example: Generating a Toolchain Identification Report

When comparing two environments, you can run a small program in both environments. This program reports runtime identity, VM, feature version, OS, and encoding. It does not determine which compiler the shell selects; therefore, you must still run javac --version separately.

Create ToolchainReport.java:

~~~java
public final class ToolchainReport {
    private static void print(String key, String value) {
        System.out.println(key + "=" + value);
    }

    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        print("JAVA_VERSION", System.getProperty("java.version"));
        print("JAVA_RUNTIME_VERSION", System.getProperty("java.runtime.version"));
        print("JAVA_VENDOR", System.getProperty("java.vendor"));
        print("JAVA_VM", System.getProperty("java.vm.name"));
        print("JAVA_VM_VERSION", System.getProperty("java.vm.version"));
        print("JAVA_FEATURE", Integer.toString(version.feature()));
        print("OS", System.getProperty("os.name"));
        print("OS_ARCH", System.getProperty("os.arch"));
        print("FILE_ENCODING", System.getProperty("file.encoding"));
    }
}
~~~

Compile and run using the selected JDK 17:

~~~bash
javac --release 17 -d out ToolchainReport.java
java -cp out ToolchainReport
~~~

On Windows with Amazon Corretto 17.0.15+6-LTS, verified output:

~~~text
JAVA_VERSION=17.0.15
JAVA_RUNTIME_VERSION=17.0.15+6-LTS
JAVA_VENDOR=Amazon.com Inc.
JAVA_VM=OpenJDK 64-Bit Server VM
JAVA_VM_VERSION=17.0.15+6-LTS
JAVA_FEATURE=17
OS=Windows 11
OS_ARCH=amd64
FILE_ENCODING=UTF-8
~~~

Compiler version for this run:

~~~text
javac 17.0.15
~~~

When comparing two machines, save the program output together with java --version, javac --version, gradle --version, or mvn -version output. Compare field by field to spot differences in the runtime, compiler, or build engine.

## 15. Common Mistakes When Choosing Diagnostic Tools

| Mistake | Why It Is Ineffective | How to Choose Better |
|---|---|---|
| Running only java --version | Does not show javac, daemon, or compiler toolchain | Check runtime, compiler, and build tool separately |
| Running javac manually to conclude Gradle compiles wrong | Omits Gradle's compiler args, processors, and classpath | Check Gradle's task log and toolchain |
| Seeing mvn -version is right and assuming Maven compiler uses that JDK | Maven Toolchains may select a different JDK | Check toolchains.xml and compiler plugin |
| Running --debug right from the start | Large logs, hard to read, and may leak secrets | Use --stacktrace or --info first |
| Deleting the entire cache to fix dependencies | Can mask resolution errors and destroy evidence | Check dependency tree, cache key, and repository first |
| Taking a heap dump just upon seeing memory growth | Can cause pauses, consume disk, and contain sensitive data | Start with JFR and GC.heap_info |
| Using a single thread dump to conclude a deadlock | One snapshot does not show whether threads are making progress | Compare multiple dumps over time |
| Using --add-opens to fix every module error | Can mask wrong requires or exports | Determine whether the error is readability, export, or reflection |
| Checking only the IDE | The IDE may use a different SDK and runner than the terminal | Compare command-line and IDE build logs |
| Checking only local | CI may differ in OS, architecture, JDK, or network | Collect the same baseline on the runner |
| Posting full logs to a public issue | Can expose tokens, paths, and application data | Filter, redact, and share only relevant excerpts |

## 16. Template for Recording Diagnostic Results

A short structured report helps others reproduce the issue:

~~~text
Problem:
- Symptom and first error message.

Scope:
- Local / IDE / CI / container / production.
- OS and architecture.

Reproduction:
- Git revision.
- Working directory.
- Exact command.
- Exit code.

Toolchain:
- java --version
- javac --version
- Gradle/Maven version
- Launcher JVM / Daemon JVM / Compiler toolchain if relevant.

Evidence:
- Logs or diagnostic commands executed.
- Observed results.
- Confirmed or ruled-out hypotheses.

Conclusion:
- Failing layer and evidence.
- Minimal change required.
- How to verify after fixing.
~~~

Do not include passwords, tokens, secret values, full environment dumps, or heap dumps in this report.

## 17. Checklist for Choosing a Diagnostic Approach

- [ ] Described the symptom as a verifiable question.
- [ ] Recorded the command, working directory, revision, and exit code.
- [ ] Determined whether the failure is local-only, IDE-only, CI-only, or runtime.
- [ ] Checked java and javac separately.
- [ ] Distinguished launcher JVM, daemon JVM, and compiler toolchain.
- [ ] Selected dependency/module diagnostics if the failure is in resolution.
- [ ] Checked IDE runner or CI environment if the failure occurs in only one place.
- [ ] Used thread dumps for hung processes and JFR for time-based issues.
- [ ] Checked impact before running diagnostic commands that may pause or create large files.
- [ ] Redacted sensitive data in logs and dumps.
- [ ] Recorded evidence and post-fix verification steps.
- [ ] Stopped collecting data once the root cause was confirmed.

## 18. Key Takeaways

Choose tools based on the question and the failing layer. Use java/javac to check the JDK, Gradle/Maven to check the build engine and compiler toolchain, dependency trees to check resolution, module diagnostics to check JPMS, IDE/CI logs to find environment differences, and jcmd/JFR to investigate a running JVM.

Start with low-impact measurements, and only increase detail when evidence is insufficient. A good diagnosis must be reproducible, pinpoint the failing layer, and provide a way to verify after fixing.

References:

- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Command-Line Interface and Logging](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Apache Maven — Dependency Plugin Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Command-Line Interface](https://maven.apache.org/ref/current/maven-embedder/cli.html)