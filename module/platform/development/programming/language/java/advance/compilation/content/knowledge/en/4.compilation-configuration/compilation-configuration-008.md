# Recording Actual Configuration to Reproduce a Java Compilation

## 1. Why “Built with Java 17” Is Not Enough

A compilation can succeed on machine A yet fail on machine B even though both have the same source in one repository. The cause often lies in **actual compiler configuration**: the selected JDK build, target release, source path, classpath, annotation processors, encoding, environment variables, or leftover `.class` files from a prior build.

Saying “using Java 17” is also ambiguous: Java 17 could mean the JDK running `javac`, the language level of `--source 17`, the class file format of `--target 17`, or the Java SE language/API set of `--release 17`. These pieces of information are not equivalent.

**Recording actual configuration** means saving verifiably which compiler ran, which arguments and inputs it received, in what environment, and what results it produced. Keeping only a script or a screenshot of the line “BUILD SUCCESSFUL” is not enough: a script can resolve dependencies that change over time, an IDE/build tool can pick a different toolchain, or a task might not actually run due to caching.

After this lesson, you will know:

1. The minimum elements to record in order to reproduce `javac` on Java 17+.
2. How to accurately collect sources, options, dependencies, environment, and outputs.
3. How to practice a compilation with a record clear enough to replay.
4. Why reproducing results/diagnostics and producing byte-for-byte identical artifacts are two different goals.
5. How to investigate hidden inputs in Gradle/Maven/IDE and annotation processing.

## 2. You Must Define the Reproduction Goal First

| Goal | What Must Be Proven | Required Evidence |
| --- | --- | --- |
| **Replay compiler invocation** | Re-run the same compiler with the same source set and configuration | Exact JDK, working directory, options, source, classpath, processors, environment |
| **Replay error or behavior** | Re-compiling reproduces the error or the program exhibits the same behavior | Above data, exit code, diagnostics, runtime/test script and results |
| **Replay artifact byte-for-byte** | `.class` or JAR file has exact identical content | Lock all inputs affecting output, clean build, compare SHA-256 of each artifact |

Two class files with different hashes can still have equivalent semantics, e.g., differing in debug metadata or how the compiler emitted bytecode. Nor do two class files with the same hash guarantee the program runs if the runtime classpath is missing a library. Therefore, you must state the goal of the comparison explicitly.

## 3. What Information Layers Make Up Actual Configuration?

### 3.1. Compiler and Toolchain Identity

Always record the `javac` **executable path**, full version, and JDK distribution; when investigating compiler-specific differences, include build/vendor as well if available. Record how the toolchain was selected from `PATH`, `JAVA_HOME`, Gradle toolchain, Maven toolchains, IDE, or container. Record OS/architecture when they affect native components, paths, filesystem behavior, or code generation steps.

```bash
javac -version
java -version
```

`javac -version` and `java -version` are outputs from **two executables resolved** in the shell session. Do not assume they definitely belong to the same JDK. Locate them on Linux/macOS:

```bash
command -v javac
command -v java
```

In Windows PowerShell:

```powershell
(Get-Command javac).Source
(Get-Command java).Source
```

If the result points to a wrapper or symlink, trace further to the actual JDK behind the wrapper when exact replay is needed. You can save the JDK's `release` file information or CI/toolchain metadata to identify the build.

### 3.2. All javac Options Resolved to Actual Values

| Group | Example | Effect That Must Be Recorded |
| --- | --- | --- |
| Language rules, API, class target | `--release`, `--source`, `--target`, `--enable-preview` | Which Java syntax and APIs are accepted, class file version |
| How source is read | `-encoding UTF-8` | Decoding source file bytes |
| Files compiled | Names of `.java` files, `@argfile`, implicitly located sources | Which declarations participate in the compilation |
| Type and module lookup | `-cp`, `--source-path`, `--module-path`, `--module-source-path`, `--system`, and module flags | Which dependencies the compiler can see |
| Output destinations | `-d`, `-s`, `-h` | Where classes, generated sources, and native headers are written |
| Annotation processing | `-proc:*`, `-processor`, `--processor-path`, `--processor-module-path`, `-A...` | Which processors run, with what parameters and dependencies |
| Metadata | `-g`, `-g:none`, `-g:lines,vars,source`, `-parameters` | Attributes inside class files |
| Diagnostics | `-Xlint`, `-Werror`, `-implicit` | Warnings, build failure conditions, and class files for implicit sources |
| Other JVM/compiler | `-J...`, non-standard options when used | Runtime/compiler-specific behavior |

**Record the actual arguments, not just the arguments visible on one command line.** An `@argfile` can hold additional flags. `JDK_JAVAC_OPTIONS` can inject arguments into the `javac` call. An IDE or build plugin can also add options different from the configuration file written by the developer.

When Java 17 compatibility is needed from a newer compiler, `--release 17` is the clear way to request the language level, class file format, and Java SE APIs of that release, within what the current JDK supports. `--release` must not be combined with `--source` or `--target`. Pinning the platform API does not pin third-party libraries: you must still record resolved dependency versions.

### 3.3. Actual Source Inputs

You must record the list of `.java` files, their contents at the time the compiler reads them, and the list of source files generated before/during compilation. A Git commit is a useful landmark yet does not cover uncommitted files, generated sources, or files outside the repository.

For each important file, compute SHA-256. For example, Linux has `sha256sum`:

```bash
sha256sum src/demo/Main.java src/demo/Message.java
```

On Windows PowerShell:

```powershell
Get-FileHash src/demo/Main.java -Algorithm SHA256
Get-FileHash src/demo/Message.java -Algorithm SHA256
```

Save the **actual hashes obtained**; do not treat a file name as proof that content is unchanged. When there are many sources, generate a manifest with consistent relative paths and hashes for each file. If a generator reads templates, schemas, resources, or timestamps, record those inputs too when they affect generated code.

### 3.4. Classpath, Module Path, and Binary Dependencies

Record the exact **order and content** of entries in `-cp`/`--class-path`, resolved JAR/class directory paths, modules on `--module-path`, and related options like `--add-reads`, `--add-exports`, or `--patch-module` if used.

A name `lib/common.jar` is not enough: two files with the same name can carry different bytes. Record resolved dependency coordinates, versions, and SHA-256 of each JAR. For class directories, record the manifest/hashes of the class files or corresponding packaged artifact. Classpath is ordered: if multiple locations provide the same class name, order can affect which type the compiler finds.

Note on operating systems: the separator for multiple classpath entries is `;` on Windows and `:` on Linux/macOS. A script copying a classpath string verbatim between two platforms may not be equivalent.

### 3.5. Environment and Hidden Inputs

Information to examine:

- **Working directory** at the exact time the compiler runs. Relative paths on the command line and inside `@argfile` are resolved from the working directory.
- `JAVA_HOME`, `PATH`, `CLASSPATH`, `JDK_JAVAC_OPTIONS`; JVM/launcher options and variables like `JAVA_TOOL_OPTIONS` if actually applicable.
- Default encoding when `-encoding` is not used; locale can affect diagnostic messages; filesystem traits can affect paths/symlinks/case.
- Versions and configuration of processors, compiler plugins, build tools, daemons, task caches, and CI.
- External files or data read by generators or processors; timestamps/randomness if they affect output.

There is no need to dump every environment variable indiscriminately. You need **enough variables that can affect this compilation**, stored in an appropriate place; do not expose passwords, tokens, or sensitive content just for debugging.

### 3.6. Invocation Results

Save the **exit code**, stdout/stderr, diagnostics, output paths, and artifact listing and hashes. When needing to reproduce warnings, record both `-Xlint`/`-Werror` and the JDK version; phrasing, locations, and formatting of compiler messages can change between versions or locales.

Important: `-d out` does not mean cleaning `out` before compiling. An error can leave old `.class` files or partial output behind. To prove an artifact was produced by *this run*, build in a clean output directory or record before/after states very clearly.

## 4. Runnable Example: Locking Down a Java 17 Compilation

Use two source files in a project without `module-info.java` and without external dependencies:

```text
replay-demo/
├── config/
│   └── javac.args
└── src/
    └── demo/
        ├── Message.java
        └── Main.java
```

File `src/demo/Message.java`:

```java
package demo;

public final class Message {
    private Message() {
    }

    public static String hello(String name) {
        return "Hello, " + name + "!";
    }
}
```

File `src/demo/Main.java`:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.hello("Linh"));
    }
}
```

File `config/javac.args` contains **the exact lines** below:

```text
--release
17
-encoding
UTF-8
-proc:none
-g:lines,vars,source
-parameters
-d
build/classes
src/demo/Message.java
src/demo/Main.java
```

Inside `replay-demo`, run:

```bash
javac @config/javac.args
java -cp build/classes demo.Main
```

Deterministic output of the program:

```text
Hello, Linh!
```

`javac` normally prints nothing when compilation succeeds. Expected output:

```text
build/classes/
└── demo/
    ├── Main.class
    └── Message.class
```

Configuration explanation:

1. `--release 17` selects the Java SE 17 language level, class file format, and APIs.
2. `-encoding UTF-8` defines source encoding.
3. `-proc:none` disables annotation processing to reduce hidden inputs for the practice exercise; real projects needing processors must enable them and record full processor configuration.
4. `-g:lines,vars,source` requests the corresponding debug information types. `-parameters` saves parameter names for reflection.
5. `-d build/classes` selects where class files are generated. Modern JDKs create necessary output directories if they do not yet exist.
6. Both source files are specified explicitly so there is no reliance on implicit source-file lookup behavior.
7. `build/classes` is the classpath root when running `demo.Main`; do not run `java -cp build/classes Main` because the class is in package `demo`.

File `config/javac.args` is located via the path written after `@`, yet **the paths inside that file are resolved relative to the working directory when `javac` runs**, not from the `config` directory. Thus changing the working directory without updating paths can make replay fail.

## 5. Collecting the Actual Record for the Example

From `replay-demo`, capture context and input hashes before compiling. Example on Linux with `sha256sum`:

```bash
pwd
command -v javac
command -v java
javac -version
java -version
sha256sum config/javac.args src/demo/Main.java src/demo/Message.java
javac @config/javac.args
sha256sum build/classes/demo/Main.class build/classes/demo/Message.class
java -cp build/classes demo.Main
```

On Windows PowerShell:

```powershell
(Get-Location).Path
(Get-Command javac).Source
(Get-Command java).Source
javac -version
java -version
Get-FileHash config/javac.args -Algorithm SHA256
Get-FileHash src/demo/Main.java -Algorithm SHA256
Get-FileHash src/demo/Message.java -Algorithm SHA256
javac '@config/javac.args'
Get-FileHash build/classes/demo/Main.class -Algorithm SHA256
Get-FileHash build/classes/demo/Message.class -Algorithm SHA256
java -cp build/classes demo.Main
```

These commands demonstrate **data collection** and do not automatically store a durable record; capture actual output into build logs/artifacts. If `javac` fails, record the exit code and diagnostics; stop using the output directory as a fresh build result, because old classes may remain in the directory.

A structured record should save:

| Field | What Must Be Filled From the Run |
| --- | --- |
| Goal | Replay compiler invocation, error/behavior, or byte-for-byte artifact |
| Toolchain | `javac` path and identity, JDK vendor/version/build |
| Runtime | `java` path and version used during testing |
| CWD | Absolute path to the `replay-demo` directory |
| Invocation | `javac @config/javac.args` along with the full content and hash of the argfile |
| Compiler options | `--release 17`, `-encoding UTF-8`, `-proc:none`, `-g:lines,vars,source`, `-parameters`, `-d build/classes` |
| Inputs | Both `src/demo/*.java` files with SHA-256, source revision |
| Dependencies | Java SE API belonging to release 17; no external non-platform JARs in the example |
| Processors | Disabled via `-proc:none` |
| Environment | CWD, OS, `PATH`, `JAVA_HOME`, `JDK_JAVAC_OPTIONS` and related variables |
| Output state | Whether `build/classes` was cleaned before compilation |
| Result | Exit code, stdout/stderr, hashes of `Main.class`/`Message.class` |
| Runtime check | `java -cp build/classes demo.Main` prints `Hello, Linh!` |

When needing to re-check months later, store the record and checksums together with source revisions/artifacts in an immutable location. Record timestamps aid traceability yet do not replace checksums.

## 6. Differences Between Intended Configuration and Actually Applied Configuration

Distinguish three layers:

```text
Declared configuration (build.gradle / pom.xml / IDE settings)
    ↓ resolution: toolchain, dependency, source sets, plugins, environment
Compiler configuration used by the task (options, sources, classpath, processors)
    ↓ javac invocation/API call or cached compile task
Actual results (exit code, diagnostics, .class, generated files)
```

A build file might state “Java 17” while Gradle runs on JDK 21 and selects a JDK 21 compiler with `--release 17`. That **can be completely valid**, yet saying “JDK 17 compiler” in that case is wrong. Maven/IDEs also have mechanisms to select a compiler different from the IDE's or application's runtime. To replay, record the **resolved** toolchain version, not just the desired value.

Gradle Groovy example (this is **build configuration**, not runnable Java code):

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.add('-parameters')
}
```

This example shows the compiler JDK is selected via toolchain 21, while output targets Java 17. It **does not** automatically pin the resolved JDK patch/vendor build, dependency JARs, annotation processors, or generated sources. When using Gradle/Maven, also record wrapper/plugin versions, executed tasks, lockfiles or dependency verification, effective compile options, and artifact cache information.

**Not every build tool executes an external `javac` executable.** The compiler may be invoked via the Java Compiler API or through a daemon. Do not invent a shell command and call it an “exact invocation” if the tool actually uses an API; record arguments/options, compile tool instance, and inputs in the way the build system provides. If a task receives output from a cache, save the cache key/provenance; do not say the compiler just ran merely because the task reported success.

## 7. Annotation Processing: A Subtle Source of Variance

Annotation processors are Java programs running inside the compiler environment. They can generate sources, classes, resources, and diagnostics based on annotations, processor settings, classpath, timestamps, templates, or external files. Record:

- Processor classes/versions and hashes of JARs containing processors and their dependencies.
- `-processor`, `-proc:none`/`-proc:only`/`-proc:full`, `--processor-path`, `--processor-module-path`, `-Akey=value` per actual configuration.
- Generated source/class/resource directories and inputs read by processors.
- Java runtime running the processors and environment variables that can have an effect.

Do not assume a processor definitely ran merely because code has annotations. Default processor discovery behavior can vary by JDK/version or build tool. Set explicit configuration and verify logs when needed. `javac` has diagnostic options like `-XprintRounds` and `-XprintProcessorInfo` to observe annotation processing activity on a specific toolchain.

If you want to reproduce a compilation involving code generation, do not set `-proc:none` just to “make the build run easily”: that changes the problem. That option fits only the processor-free example above.

## 8. Environment Inputs That Are Easily Overlooked

**`JDK_JAVAC_OPTIONS`:** can be prepended to the compiler arguments list; merely copying `javac @config/javac.args` does not guarantee receiving the exact same options on another machine. Record its value or ensure it is controlled.

**`CLASSPATH`:** if no classpath is passed via CLI, `javac` can use this environment variable, or the current directory if it is unset. When compiling a regular classpath application without setting a source path, the compiler can also search for sources on the user classpath.

**`-d` does not automatically add the output directory to the compile classpath of a non-modular project.** If already-compiled files reside in `build/classes` and a new compilation needs them, pass `-cp build/classes` explicitly, rather than assuming `-d build/classes` has that effect.

**Relative paths and operating systems:** changing CWD, filesystem case-sensitivity differences, or classpath separators can make a command no longer equivalent.

**Generated inputs and dynamic dependencies:** a generator embedding timestamps/randomness into source or dependencies with SNAPSHOT/dynamic versions can produce different outputs even when configuration files share the same names. To replay, save actual bytes or use immutable resolution mechanisms.

**Log security:** compiler records can contain internal paths, tokens in processor options, or environment values. Store sensitive information in a properly protected system; publicly shared logs should contain only safely sanitized data and clearly state what was redacted when replay requires corresponding access.

## 9. Clean Rebuilds and Artifact Comparison

If you need to prove two compilations produce byte-for-byte identical class files, you must also control pre-run output state before each compilation. For the example, run two independent builds into clean output directories; hash newly generated class files and match them by relative path.

If hashes differ, use:

```bash
javap -v -classpath build/classes demo.Main
```

`javap -v` displays class file details, constant pool, methods, and attributes. It helps find differences in debug/parameter metadata and bytecode yet does not replace compiler/toolchain records. **A hash change is not necessarily a semantic bug; nor does a successful compilation guarantee all artifacts are byte-for-byte identical across different compilers.**

With JARs there is also packaging, entry ordering, timestamps, manifests, and signing data. Reproducing `.class` files and reproducing a JAR are two related yet distinct requirements. Do not conclude a JAR is reproducible merely because its class files match identically.

If a build fails, the output directory can contain classes from an earlier run or files created before the error occurred. Check the **exit code** and logs; do not run an old output file and claim the compiler just created it successfully.

## 10. Replaying a Specific Error: Controlled Investigation

Suppose CI reports `cannot find symbol` while a laptop build succeeds. A good investigation process:

1. Obtain CI logs along with compiler path/version, release, options, CWD, source list, dependency graph, processor configuration, and exit code.
2. Pin the commit plus any uncommitted changes, generated sources, JAR hashes, and relevant environment.
3. Reconstruct compilation in a clean output directory with matching toolchain and options; use an argfile to avoid errors from overly long command lines.
4. If the error does not appear, compare **actual inputs** before editing source: differences in release, classpath order, JARs, source files, processors, environment, or cache.
5. Vary one factor at a time to find the root cause. When the error reproduces, save a minimal reproducer and the locked record.

For example, CI uses `--release 17` while a local machine uses a JDK 21 compiler without pinning release. Code calling a Java SE API newer than 17 can compile locally yet be rejected on CI. The cause is at the API/release level, not necessarily different source files.

Another case: both use `--release 17`, yet a dependency JAR changed or classpath ordering differs. Inspect resolved dependency lists and hashes instead of looking solely at compiler version.

## 11. Common Wrong Conclusions

| Unfounded Conclusion | Correct Verification |
| --- | --- |
| “Both use Java 17, so the configs are identical.” | Compare JDK vendor/build, `--release`/`--source`/`--target`, and all options |
| “Having `pom.xml` or `build.gradle` is enough.” | Check effective task/compiler options, toolchain, resolved deps, generated sources |
| “Keeping the Git commit preserves all source inputs.” | Check uncommitted files, generated sources, out-of-repo sources, and hashes |
| “`@args` stores the whole configuration.” | Save argfile content, CWD, and `JDK_JAVAC_OPTIONS`/wrapper options |
| “JAR name and version suffice to prove identical dependencies.” | Compare JAR byte hashes and ordered classpath/module path |
| “`javac -d out` is a clean build.” | Record or control pre-compile output state |
| “Seeing `Main.class` after a failed compile means compilation succeeded.” | Check exit code, logs, and artifacts freshly created from clean output |
| “Two class files with different hashes mean Java runs differently.” | Inspect metadata and bytecode with `javap -v` and run functional tests |
| “Gradle task succeeded means `javac` ran.” | Inspect task execution/cache evidence and compiler invocation |
| “`--release 17` pins all libraries automatically.” | Separately pin JARs/third-party dependencies and processor paths |

## 12. Checklist for Handing Over a Compile Record

- [ ] Identify the replay requirement: command, diagnostics/behavior, or byte-for-byte artifacts.
- [ ] Record the `javac` path, JDK vendor/version/build, and runtime used for testing.
- [ ] Record CWD, OS, how the toolchain was resolved, and affecting environment variables.
- [ ] Save all actual compiler arguments; keep exact content/hash of `@argfile` if used.
- [ ] Explicitly record release/encoding/preview/debug/parameter/warning/processor options.
- [ ] List and hash each actual source file; pin commit, uncommitted changes, and generated sources.
- [ ] List resolved binary dependencies, ordered classpath/module path, and checksums.
- [ ] Record annotation processors, processor dependencies/options, and generated outputs if any.
- [ ] Record pre-compile output state, exit code, stdout/stderr, and post-compile output manifest/hashes.
- [ ] For behavior replay, save the `java` command, runtime classpath, and output/test logs.
- [ ] Store the record alongside artifacts in an access-controlled location; do not publish secrets.
- [ ] Re-run in an independent environment and compare against the defined reproduction level.

## 13. Self-Check Exercises and Answers

**Exercise 1.** Two machines both use JDK 21; machine A runs `javac --release 17`, machine B has no release option. Do they have the same compile configuration?

**Answer:** No. Machine A is constrained to Java SE 17, whereas machine B can use newer syntax/APIs per JDK 21 defaults. Both the compiler JDK and release target must be recorded.

**Exercise 2.** Running `javac @config/javac.args` from a different directory fails with file not found for `src/demo/Main.java`. Why?

**Answer:** File paths written inside the argfile are resolved relative to the working directory of the `javac` invocation, not from `config`.

**Exercise 3.** Two `Main.class` files have different SHA-256 hashes, yet both programs print `Hello, Linh!`. What does this prove?

**Answer:** The class files are not byte-for-byte identical; it does not yet prove different semantics. You need to inspect compiler, flags, debug metadata, processors, and `javap -v` to explain why.

**Exercise 4.** A CI log shows `BUILD SUCCESSFUL` yet no compile task ran due to a cache hit. Can this be called “an actual compiler invocation”?

**Answer:** No. You must record the cache/artifact provenance and task execution evidence. If you need to replay compilation, run the actual compiler again with matching inputs.

**Exercise 5.** After a failed compilation, `demo/Main.class` still exists in `build/classes`. What is missing to claim the class was generated by this run?

**Answer:** Evidence of clean output before compilation, exit code, diagnostics, and artifact manifest/hashes after a controlled build.

## 14. References

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — `--release`, `-encoding`, `-d`, `-g`, `-parameters`, processors, classpath, and argument files.
- **dev.java — Javac, the Compiler:** https://dev.java/learn/jvm/tools/core/javac/ — compiler overview, implicit source files, `JDK_JAVAC_OPTIONS`.
- **Java SE 21 Language Specification:** https://docs.oracle.com/javase/specs/jls/se21/html/ — language semantics, compile-time errors.
- **Java SE 21 Virtual Machine Specification:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — class file format and JVM constraints.
- **Gradle Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html — selecting the actual JDK for compile tasks.

**Practical message:** a valuable reproduction record must answer *which compiler ran, which input bytes and options it received, in what environment, and what output it produced*. Only once that data is locked down do differences between builds have a solid basis for investigation.