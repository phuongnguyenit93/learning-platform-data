# Reproducing a Java compilation command from build logs and CI environments

## 1. Purpose and significance

When a project **compiles successfully on a local machine yet fails on CI**, the question to answer is not merely “Which command did CI run?” but: **which inputs, options, and environment did the Java compiler receive?** Reproducing a compilation helps distinguish source code bugs, build configuration, JDK, dependencies, annotation processors, and OS differences.

After this lesson, the learner can:

- Trace from a Gradle/Maven invocation in CI to the compilation task and actual Java compiler configuration.
- Gather complete evidence: JDK, working directory, source file list, classpath/module path, output destination, encoding, target release, processors, and relevant environment variables.
- Construct a **semantically equivalent javac command** to the build, or honestly determine when logs are insufficient to construct the exact command.
- Re-run on a developer machine or controlled runner, compare errors, and verify results.

**Distinguish three command layers:**

| Layer | Example | Role |
| --- | --- | --- |
| Pipeline command | ./gradlew build, ./mvnw verify | CI job entry point, may run multiple tasks before/after compilation |
| Build task | Gradle :compileJava, Maven compiler:compile | Selects sources, dependencies, toolchain, processors, and compiler configuration |
| Compiler invocation | javac with -d, --release, -cp, and .java files; or Java Compiler API | Specific compilation action to reproduce |

Do not equate a **build** command with a **javac** command. Gradle or Maven can invoke the compiler inside the same JVM via API, via a worker, or via a forked process. Therefore **not every compilation leaves a verbatim javac shell line in the logs**. When data is missing, state “reconstructed javac command from configuration” rather than claiming it is the exact command line CI actually executed.

## 2. Input model of a compilation run

The result can be viewed as a function of data groups:

~~~text
.class outputs and diagnostics
    = Compiler/JDK + build version/configuration
    + Source files + Java options
    + Classpath / module path / processor path
    + Generated sources + working directory
    + Environment + dependency artifacts
~~~

Important variables to record:

| Group | Data to cross-check | Why it matters |
| --- | --- | --- |
| Compiler | Actual javac path, distribution, and JDK version | Language features, supported APIs, and diagnostics differ |
| Build tool | Gradle/Maven wrapper, compiler plugin, build scripts, profiles | Can alter parameters, select tasks, or select toolchains |
| Source | Exact set of .java files; generator-produced sources; module-info.java | Missing one file or wrong source root can cause cannot find symbol |
| Target | --release or -source/-target; -d; -s | Dictates API, bytecode, and locations of generated classes/sources |
| Dependencies | JARs and directories on -cp/--class-path; --module-path | Declaring dependencies is not synonymous with actual compile classpath |
| Processing | -processorpath/--processor-path, -processor, -A..., -proc:... | Affects code generation and annotation processing round order |
| Environment | OS, architecture, working directory, JAVA_HOME, PATH, locale/encoding, variables read by build | Can switch JDKs, paths, and file resolution behavior |
| CI execution | Commit, container image, runner image, caches, script, and executed tasks | Clarifies whether compilation truly ran or reused existing results |

**Principle:** When comparing two environments, compare **values resolved by the build**, not merely declaration lines in build.gradle or pom.xml. For instance, two configurations both state “Java 21” yet one task uses JDK 21 compiler via toolchain while the other uses a different JDK due to overrides or fork configuration.

## 3. Reading logs and identifying compilation events

### 3.1. Reading from CI along the causal chain

1. Identify commit/SHA, job, failing step, working directory of that step, and its shell command.
2. Identify runtime JDK and compiler JDK; if a toolchain is configured, do not infer compiler solely from java -version.
3. Find the first compile task/goal that actually failed, rather than reading only the final FAILED summary.
4. Locate compiler options, source inputs, classpath, generated sources, and annotation processing info.
5. Keep the **first root-cause diagnostic** with a few lines of context; trailing errors are sometimes mere consequences.
6. Note whether the task was **EXECUTED**, **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**, or skipped (status names vary by tool). If compilation was cached/skipped, that log does not prove the compiler ran.

A shortened example log:

~~~text
> Task :compileJava FAILED
error: package example.generated does not exist
import example.generated.GeneratedConfig;
                        ^
1 error

FAILURE: Build failed with an exception.
Execution failed for task ':compileJava'.
~~~

The task message indicates **where the failure occurred**. It is not enough to conclude which dependency is missing, which toolchain was used, or the exact command line. Inspect where GeneratedConfig is generated from and whether the generator task sits in compileJava's dependency graph.

### 3.2. Gathering info from Gradle

At the project root containing Gradle Wrapper (on Linux/macOS):

~~~bash
./gradlew --version
java -version
javac -version
./gradlew --no-daemon --no-build-cache --rerun-tasks compileJava --info --stacktrace
~~~

- **--version** reports Gradle and the JVM running Gradle; it does **not automatically prove** the compiler task uses that JDK.
- **--info** shows task execution and partial compilation details. For deep investigation **--debug** can be used, yet logs are verbose and may expose paths or sensitive configuration.
- **--rerun-tasks** forces task re-execution, **--no-build-cache** avoids taking outputs from the build cache, and **--no-daemon** helps reduce interference from an old daemon. These are *diagnostic* options, not flags to apply to every CI run.
- If the task invocation uses a different name, use the exact task path CI runs, e.g., **:service:compileJava**; if the project also has test, integrationTest, Kotlin, or other Java modules, running compileJava alone may not reproduce the full pipeline.
- If the task uses the compiler API, Gradle does not necessarily print a copy-pasteable javac command. Inspect resolved configuration instead of extrapolating from a few log lines.

With a Groovy build script, you can **temporarily add to a project copy used for diagnostics** the following snippet to observe JavaCompile inputs right before the task runs:

~~~groovy
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType(JavaCompile).configureEach {
    doFirst {
        println "DIAG task = " + path
        println "DIAG compiler = " + javaCompiler.get().executablePath.asFile
        println "DIAG release = " + options.release.orNull
        println "DIAG encoding = " + options.encoding
        println "DIAG destination = " + destinationDirectory.get().asFile
        println "DIAG source files = " + source.files.sort()
        println "DIAG classpath = " + classpath.files
        println "DIAG extra compiler args = " + options.compilerArgs
    }
}
~~~

This is **task configuration information**, not the complete list of effective parameters received by the Java Compiler API. In particular, default options, source path, module path, and processor path may be organized by Gradle through its own mechanisms. Cross-check plugins, toolchains, the annotationProcessor configuration, and task config if a more exact reproduction is needed. Do not keep diagnostic logging snippets in unintended production changes.

In Gradle Groovy DSL, an example explicitly declaring JDK 21 compiler while targeting Java 17 bytecode/API:

~~~groovy
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
}
~~~

In this example, the **JDK used to compile is 21**, while **--release 17** restricts language/API/bytecode to Java 17. The two values answer two different questions.

### 3.3. Gathering info from Maven

In the directory containing Maven Wrapper:

~~~bash
./mvnw --version
java -version
javac -version
./mvnw -B -ntp -e -X -DskipTests compile
~~~

- **-B** runs batch mode, **-ntp** reduces dependency transfer output, **-e** prints stack traces, and **-X** enables debug.
- Locate the **maven-compiler-plugin:compile** section, source roots, compile classpath, compiler release/options, and fork/toolchain config.
- In many Maven Compiler Plugin versions, compiler command-line info or debug argument files may be emitted on error or with verbose enabled; check the **actual plugin version** and generated files rather than assuming locations are always identical.
- With multi-module Maven, running **compile** at the root can traverse many modules; to reproduce a failure in one specific module, record reactor/project selection and active profiles.

An example Maven configuration:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Release configuration does not replace confirming the **compiler JDK**. If CI runs Maven on one JDK and uses Maven Toolchains or compiler fork with another JDK, both must be identified.

### 3.4. Choosing evidence sources when logs are incomplete

Useful order: **executed task/goal line → verbose/debug logs → resolved task/plugin configuration → resolved file/dependency set → reconstructed command and verification result**.

When logs lack classpath or internal parameters, record “unknown” status and add instrumentation at the task/plugin. Do not fill in JAR paths yourself, guess versions, or swap the task for a similar-looking command.

## 4. Accurately identifying the CI environment

Run the commands below **in the same job/container and as close to the compile step as possible**; this example is for a Linux runner:

~~~bash
pwd
command -v java
command -v javac
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'LANG=%s\n' "$LANG"
./gradlew --version
~~~

If the job uses Maven, replace the last line with **./mvnw --version**. On Windows PowerShell, use:

~~~powershell
Get-Location
Get-Command java,javac | Select-Object Name,Source
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
~~~

**Interpreting evidence accurately:**

- **java -version** reflects the Java launcher found on PATH; **javac -version** reflects the compiler on PATH. A build task may choose a different Java compiler via toolchain.
- **JAVA_HOME** can be empty or differ from the compiler location chosen by PATH/toolchain; cross-check the compiler selected by the task.
- **pwd/Get-Location** helps interpret relative paths in scripts, argfiles, classpaths, and source lists.
- Operating systems change the classpath separator: **:** on Linux/macOS, **;** on Windows; as well as directory separators, quoting rules, and filesystem case sensitivity.
- Repository commit, submodule checkouts, configuration variables, dependency caches, generated files, and downloaded artifacts are all part of the environment; matching only the major JDK version does not guarantee exact reproduction.
- Avoid printing all environment variables or settings files containing tokens. Log only necessary variables and mask secrets.

Example GitHub Actions job for an investigation run on Ubuntu:

~~~yaml
name: reproduce-java-compile
on:
  workflow_dispatch:

jobs:
  compile:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Show environment
        run: |
          pwd
          java -version
          javac -version
          ./gradlew --version
      - name: Re-run Java compilation
        run: ./gradlew --no-daemon --no-build-cache --rerun-tasks compileJava --info --stacktrace
~~~

This workflow illustrates how to collect evidence, **not default to the original CI**. If the original failure occurred inside a dedicated container, in another task, with a different profile variable, or before/after a code generation step, preserve those conditions during reproduction. Switching to a newer runner/JDK can hide the bug instead of reproducing it.

## 5. From discovered configuration to a javac command

### 5.1. Common options mapping

| Build information | Corresponding javac argument | Notes |
| --- | --- | --- |
| Java release | --release 17 | Requires a compiler new enough to support this release |
| Source encoding | -encoding UTF-8 | Determines how characters in .java are read |
| Output directory | -d out | Holds .class files arranged by package/module |
| Classpath dependencies | -cp path1:path2 | Use ; instead of : on Windows |
| Java modules | --module-path modules | Do not equate with -cp; requires module-info and module resolution setup |
| Processor-generated sources | -s generated | Where annotation-processor-generated .java files are placed |
| Processor dependencies | -processorpath processor-jars | Distinct from compile classpath |
| Processor options | -Akey=value | Passed to annotation processors |
| Debug info | -g or -g:none | Affects metadata in class files |
| Parameter names | -parameters | Retains parameter names for reflection |
| Long file/args list | @compile.args | Javac reads arguments from file |

**--release** should generally be preferred when compatibility with an older Java release API is needed: it controls language, bytecode, and public Java platform APIs together. **-source** and **-target** control only syntax and bytecode target respectively; they do not restrict standard APIs used when the compiler runs on a newer JDK. Do not combine **--release** with **-source/-target** in the same invocation.

An illustrative reconstructed command on Linux/macOS once the task has resolved compiler, sources, and dependencies:

~~~bash
/path/to/jdk-21/bin/javac \
  --release 17 \
  -encoding UTF-8 \
  -cp "lib/api.jar:lib/model.jar" \
  -d build/classes/java/main \
  @compile-sources.args
~~~

This is **illustrative syntax**, not runnable standalone without the exact JDK, both JARs, and the declared argfile. Paths must come from the real build and be resolved from the right working directory. If the project uses module path or annotation processors, the corresponding arguments must be added.

### 5.2. @argfile files

With many source files or a very long classpath, arguments can be saved into a UTF-8 file to avoid command-line length limits and keep configuration easy to compare.

Example contents of **compile.args**:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/main/java/example/Main.java
~~~

Execution:

~~~bash
javac @compile.args
~~~

Javac reads arguments in order as if they were on the command line. **Relative paths inside an argfile are resolved from the current working directory**, not automatically from the directory containing the argfile. For paths containing spaces, quote the path per argfile syntax. Do not put source-file wildcards inside an argfile expecting javac to expand them like a shell; list each file individually.

To verify large configurations, save extracted options and source list as an artifact containing only non-sensitive data; also save JAR checksums when needing to distinguish dependencies sharing the same name yet differing in bytes.

## 6. Runnable example: reproducing a compilation with JDK 21

An intentionally Gradle/Maven-independent example to inspect the essence of the javac command. Requirements: **JDK 21**, terminal positioned at project root, and the following file tree:

~~~text
demo/
└── src/
    └── main/
        └── java/
            └── example/
                └── Main.java
~~~

Contents of **src/main/java/example/Main.java**:

~~~java
package example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("CI compile reproducible");
    }
}
~~~

From directory **demo**, Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/main/java/example/Main.java
java -cp out example.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/main/java/example/Main.java
java -cp out example.Main
~~~

Standard output of the **java command**:

~~~text
CI compile reproducible
~~~

A successful **javac** command does not necessarily print anything to stdout. The resulting file is **out/example/Main.class**. Can inspect with:

~~~bash
javap -verbose -classpath out example.Main
~~~

In the output, **major version: 61** indicates Java 17 bytecode. This illustrates that a compiler running on JDK 21 can still emit Java 17 bytecode via **--release 17**; whether a Java 17 JVM can run the program still depends on runtime and actual dependencies.

To use an argfile, replace the options part in the javac command with the contents of **compile.args** from section 5.2, then run **javac @compile.args** from the same demo directory. Compilation results and stdout of this example remain the same.

### 6.1. When dependencies or generated sources are present

If sources import external libraries, the reproduction must supply the exact compile classpath/module path; do not habitually substitute runtimeClasspath for compileClasspath. A **package ... does not exist** error can stem from a missing JAR, a different dependency version, an un-downloaded artifact, a wrong source root, or non-existent generated sources.

If annotation processors are used, identify:

1. Processor name/version and processor dependency JARs.
2. Actual processor path or processor module path.
3. **-A...** options, processing mode, and locations of generated sources/classes.
4. Whether the generator step runs before compilation or belongs to the compiler's own annotation processing round.
5. Whether generated files are pre-existing inputs or outputs of this compilation run.

Copying only .java files from handwritten source directories while skipping generators usually fails to reproduce the same issue. Conversely, copying generated files from another machine can hide task dependency or environment bugs.

## 7. Controlled workflow for reproducing a CI failure

### Step 1 — Pin down evidence of the failure

Record commit, job/step link, OS/image, working directory, pipeline command, failing task/goal, timestamp, and first error message. Ensure logs belong to the **same build attempt**; do not mix logs across retries with different images or commits.

### Step 2 — Separate build tool JVM from compiler JDK

Collect java, javac, wrapper outputs, and toolchain/fork config. If the actual compiler is JDK 17 while release requires 21, a JDK compatibility error is a stronger hypothesis than a source bug.

### Step 3 — Lock down resolved input set

Collect source files, generated sources, compile classpath, module path, processor path, Java options, output destinations, and encoding. For dependencies, use artifact coordinates and hashes if two JARs are suspected to differ.

### Step 4 — Reproduce via the build command itself first

On the right commit and matching environment, re-run the exact task/goal with controlled caching. Try reproducing via the build tool **before** switching directly to javac because the build tool may run generators, dependency transforms, or compiler plugins.

### Step 5 — Construct an equivalent javac command when isolation is needed

Use the corresponding compiler and all verified options/inputs. If failing under the build tool yet standalone javac succeeds, look for what was not reproduced: generated sources, plugin hooks, classpath or module path, annotation processing, working directory, JVM flags, compiler daemon/API, or task ordering.

### Step 6 — Compare results against criteria

Compare exit code, first diagnostic (file/line/symbol), .class output, generated sources, and actual options used. Succeeding when changing one variable does not prove that variable is the sole cause: repeat with the original configuration to observe the error return, if conditions permit.

An example investigation table:

| Component | Failing CI | Repro machine | Assessment |
| --- | --- | --- | --- |
| Source commit | Same SHA | Same SHA | Code difference ruled out |
| Java runtime | 21 | 21 | Same major, still need toolchain check |
| Compiler task | JDK 17 | JDK 21 | Different compiler |
| Requested release | 21 | 21 | JDK 17 does not support compiling release 21 |
| Outcome | Unsupported release | Compile succeeded | Prioritize fixing JDK/toolchain |

This table is a **hypothetical scenario** illustrating methodology, not real logs from a specific project.

## 8. Common errors and analysis methods

| Symptom | Possibilities to check | How to verify |
| --- | --- | --- |
| error: release version 21 not supported | Running javac is not new enough | Check task compiler executable and javac -version |
| error: invalid source release: 21 | Current JDK/compiler plugin is too old | Check toolchain, JavaCompile, Maven compiler config |
| package ... does not exist | Missing JAR, module, generated sources, or compile source root | Print resolved compile classpath, module path, source list |
| cannot find symbol | Missing type/variable/method or mismatched source/generated code versions | Inspect first error and symbol, check processors and dependencies |
| package ... is not visible | Wrong JPMS/module exports/reads configuration | Compare module-info.java, --module-path, --add-modules, exports |
| invalid flag / bad class file | Incompatible compiler option/plugin or JAR | Cross-check command, toolchain, and bytecode version |
| CI green despite local failure | Caches, skipped task, different profile or input source | Disable caches in diagnostic run; confirm compile actually executed |
| CI fails yet standalone javac passes | Reproduction missed a build input/hook | Diff sources, processors, classpath, flags, working directory |

**Do not fix symptoms backward:** a classpath error should not be “fixed” by deleting imports; a JDK error should not be solved by arbitrarily lowering **--release** if the product truly requires new language APIs. Fix the root configuration and re-run along the same CI path.

## 9. Levels of reproduction and conclusion boundaries

Three levels are commonly seen:

- **Pipeline repeatability:** same wrapper command, commit, environment, and pre-compile steps. Most suitable when failures depend on task graphs/plugins.
- **Compiler-input repeatability:** same compiler, sources, flags, classpath/module path, processors, and output directory. Useful for isolating javac bugs, though the hosting compiler runtime may still differ.
- **Byte-for-byte output repeatability:** must also account for processor stability, generated timestamps, build metadata, absolute paths, and auxiliary artifacts. Two successful compilations do not necessarily yield identical bytes.

**Reasonable conclusion criteria:** state clearly which level was achieved, which data was verified by logs/configs, which was merely inferred, and which difference suffices to explain the symptom. If the compiler runs via API, **effectively equivalent** reproduction can be achieved without finding an “original javac line” — that is completely normal.

## 10. Practical checklist before closing a bug

- [ ] Same commit and exact failing CI command/compile task.
- [ ] Compiler JDK/toolchain confirmed separately from the JVM running Gradle/Maven.
- [ ] Source roots, generated sources, and .java list verified.
- [ ] Compile classpath, module path, processor path, and dependency versions resolved.
- [ ] Release/source/target, encoding, output, processor options, and argfile preserved.
- [ ] Working directory, OS/path separator, and relevant environment variables compared.
- [ ] Confirmed task actually compiled rather than restoring from cache or skipping.
- [ ] Reproduced or explicitly noted missing data; diagnostics compared in the same context.
- [ ] No secrets/tokens or sensitive logs included in shared artifacts.
- [ ] Fix verified along the exact build/CI path.

## Reference documentation

- [JDK 21 — official javac documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): options, argfile, classpath/module path, release, and annotation processing.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) and [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): task compilation, JavaCompile, and toolchains.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): compile goal, release, and diagnostic capabilities depending on plugin version.

**Core takeaway:** a reliable reproduction must preserve the **actual compiler, resolved inputs, and execution conditions**, while clearly stating which command is proven by logs and which javac command was reconstructed to test hypotheses.