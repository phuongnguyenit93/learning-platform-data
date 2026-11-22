# Processors and Plugins Are Executable Code in the Compilation Environment

## 1. Why Is This a Build Security Concern?

When running **javac**, we often assume the compiler only reads Java source code, checks types, and generates `.class` files. However, certain components loaded into the compilation process are **actual Java code that gets executed**, not merely data to be parsed:

- **Annotation processor** uses the `javax.annotation.processing` API (JSR 269) to process program elements and annotations across compilation rounds. A processor can generate source code/resources, emit diagnostics, and call other Java APIs.
- **javac plugin** implements `com.sun.source.util.Plugin`, can be activated via `-Xplugin`, and typically registers a `TaskListener` to observe compilation stages.
- **Plugins/tasks of Gradle, Maven, and other build tools** also execute code during preparation/compilation, yet reside in the build tool's own mechanism; they are neither annotation processors nor javac plugins.

From a security perspective, a JAR named "processor," "compiler plugin," "codegen," or "linter" is still third-party code. If executed, that code can exercise the privileges of the process running the build: reading files the build account can access, reading environment variables, writing files, spawning other processes, or making network connections if allowed by the OS/environment. **Annotations or option names do not create a sandbox.**

This is especially critical on developer machines and CI runners, where repository access keys, deploy tokens, registry credentials, environment variables holding secrets, or write access to release artifacts may exist. An ordinary runtime dependency placed on the classpath **is not automatically executed** just because it is found; the risk arises when the build actually loads and invokes an extension, or when a task/build script itself actively executes code.

**Lesson objective:** accurately identify when processors/plugins run, distinguish each activation path, test with observable evidence, and apply the principle of least privilege to compilation. This topic falls under the **safety and limits** of Java compilation; it is not intended to turn writing processors/plugins into a control-bypass mechanism.

## 2. Distinguishing Loading and Activation Paths

| Component | Execution entry point | Typical selection or configuration | Scope of impact |
| --- | --- | --- | --- |
| Annotation processor | `Processor.init(...)`, `process(...)` | `-processor`, `-processorpath` / `--processor-path`, `--processor-module-path`, `-proc` option | Processes the source model, generates sources/resources, emits diagnostics; still Java code holding the process's OS privileges |
| javac plugin | `Plugin.init(JavacTask, String...)` | `-Xplugin:Name`, Java ServiceLoader of `com.sun.source.util.Plugin` | Observes/intervenes in the compiler pipeline via the plugin API |
| Build plugin/task | Plugin application, task configuration/execution, lifecycle hooks | Gradle `plugins`, Maven plugin execution, custom build script | Can run before, after, or around the compiler; build runner privileges |
| Annotation declared in source | Metadata `@Something` | Java source | By itself does **not** run a processor; execution depends on compiler/build configuration |
| JAR on compile classpath | Type/symbol definitions for the compiler | `-classpath`, `--class-path` | Does not imply every class in the JAR executes; however, check processor discovery and the corresponding build tool |

For example, an annotation processor can receive `RoundEnvironment`, traverse `TypeElement`s, and use `Filer` to write new Java classes. Beyond its legitimate function, a malicious/rogue processor can still execute code when invoked by the compiler. Similarly, a javac plugin is selected by its `getName()` and service configuration, after which the compiler calls `init(...)`.

**Conceptual sequence** of a compilation pass with a processor:

~~~text
Build command or IDE
    │
    ├─ Prepare JDK, source, classpath, processor path, and options
    │
    ├─ javac starts compilation
    │    ├─ Select/load processor if annotation processing is enabled
    │    ├─ Invoke processor across one or more processing rounds
    │    ├─ Receive generated sources/resources
    │    └─ Analyze types and generate bytecode per -proc policy
    │
    └─ Return exit status, diagnostics, and artifacts
~~~

Exact ordering between compiler phases and hooks can depend on the compiler/toolchain. `javac` plugins have their own lifecycle; build plugins can even run **before invoking javac**. Thus, `-proc:none` is only a switch for annotation processing in javac and **does not disable** all compiler plugins, build tool plugins, or custom commands in the build.

## 3. How Are Annotation Processors Discovered and Executed?

### 3.1. Standard JSR 269 Mechanism

An annotation processor implements `javax.annotation.processing.Processor` or extends `AbstractProcessor`. The compiler instantiates it, calls `init`, and then calls `process` across rounds. The processor can:

1. Read the source/type/annotation model via `Elements`, `Types`, and `RoundEnvironment`.
2. Emit `Diagnostic.Kind.NOTE`, `WARNING`, or `ERROR` via `Messager`.
3. Generate sources or resources via `Filer`. Newly generated sources can participate in the next round.
4. Execute any Java code permitted by the process and OS/container policies, including I/O unrelated to code generation.

A processor can be selected explicitly via **`-processor fqcn`**, or discovered by the compiler via service provider configuration, usually the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The service file contains the fully qualified name of the processor class, one provider per line. Processor classes must reside where the compiler searches for processors, such as **`-processorpath`** (a dedicated classpath for processors) or **`--processor-module-path`** with appropriate module configuration. Declaring an annotation in source **does not by itself specify a trustworthy processor**.

### 3.2. Default Differences Across JDK Versions

This is a common pitfall when upgrading JDKs:

- On JDK 21–22, some `javac` invocations can find and run processors from the classpath even if the user has not explicitly configured processing; javac in those versions emits a warning about implicit discovery.
- **Starting in JDK 23**, without explicit processing configuration, annotation processing **does not run** by default. To process annotations, you must provide appropriate options such as `-processor`, `-processorpath`, `--processor-module-path`, `-proc:only`, or `-proc:full`. Do not assume "upgrading the JDK" will keep running implicit code generation as before.
- **`-proc:none`**: compiles while disabling annotation processing.
- **`-proc:only`**: runs only annotation processing, without performing full class generation as in a regular compile.
- **`-proc:full`**: runs annotation processing and then compiles. This option is available in newer JDKs and has been backported into some JDK 17/11 updates; for a specific JDK 17 build, verify the update version before relying on it by default.

To avoid depending on implicit behavior across JDKs, **explicitly specify which processors are allowed to run** and separate the **processor path** from dependencies used to compile application code. How processing is enabled does not by itself prove a JAR is trustworthy; you must still verify artifact provenance.

References: [OpenJDK — JDK 23 policy change](https://inside.java/2024/06/18/quality-heads-up/), [Oracle — JDK 23 release notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html).

## 4. Runnable Example: A Processor Generating a Class During Compilation

This example uses only public JDK APIs, with no Maven/Gradle or external libraries needed. The processor prints a diagnostic and generates `demo.Generated`; the application depends on the generated class. Thus, we can observe **the difference between the compiler running with and without the processor**.

File layout:

~~~text
processor-demo/
├── processor/
│   └── demo/
│       └── ProbeProcessor.java
├── app/
│   └── demo/
│       └── App.java
└── build/
    ├── processor/          # compiler output of the processor
    ├── generated/          # source generated by the processor
    ├── classes/            # application bytecode
    └── no-processor/       # output for the negative test
~~~

### 4.1. Processor Code

**processor/demo/ProbeProcessor.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ProbeProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (generated || round.processingOver()) {
            return false;
        }

        generated = true;
        processingEnv.getMessager().printMessage(
            Diagnostic.Kind.NOTE, "PROBE_PROCESSOR_EXECUTED");

        try {
            JavaFileObject output = processingEnv.getFiler()
                    .createSourceFile("demo.Generated");
            try (Writer writer = output.openWriter()) {
                writer.write(
                    "package demo; public final class Generated { " +
                    "public static String value() { return \"ok\"; } }");
            }
        } catch (IOException e) {
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR, e.getMessage());
        }
        return false;
    }
}
~~~

**Part-by-part explanation:**

- `@SupportedAnnotationTypes("*")` allows this educational example to be invoked even though the source declares no custom annotation. In real projects, restrict the annotation names to process rather than `*` to avoid redundant work and unintended interactions.
- `@SupportedSourceVersion(RELEASE_17)` declares the Java source level supported by the processor. The processor is called by the compiler when processing configuration allows; this annotation does not trigger processing by itself.
- The `generated` flag prevents the processor from trying to create the same file in subsequent rounds. `round.processingOver()` avoids generating additional sources in the final round.
- `Filer.createSourceFile` asks the compiler to manage the generated file; if the name has already been created in the same processing run, a `FilerException` can occur.
- The `NOTE` line shows evidence that **process() was actually invoked**. If source creation fails, the processor reports `ERROR`, causing the positive case to fail.

### 4.2. Code Using the Generated Class

**app/demo/App.java**:

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println(Generated.value());
    }
}
~~~

This file **cannot compile by itself** if `Generated` does not appear in source/classpath. That is an intentional control case, helping verify that the processor ran and supplied the new class.

### 4.3. Compiling the Processor and Running Two Control Cases

Run the following commands inside the **processor-demo/** directory. On Linux/macOS you can create the directories with:

~~~bash
mkdir -p build/processor build/generated build/classes build/no-processor
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path build/processor,build/generated,build/classes,build/no-processor | Out-Null
~~~

Compile **the processor itself** first:

~~~text
javac --release 17 -encoding UTF-8 -d build/processor processor/demo/ProbeProcessor.java
~~~

**Negative case — disabling annotation processing:**

~~~text
javac --release 17 -proc:none -d build/no-processor app/demo/App.java
~~~

Expected: javac returns a **non-zero** exit code because `Generated` is not found. A common diagnostic is `cannot find symbol`. This is a processing-configuration test case, **not** proof that the command disables all external code in a build.

**Positive case — explicitly specifying processor and processor path:**

~~~text
javac --release 17 -processorpath build/processor -processor demo.ProbeProcessor -s build/generated -d build/classes app/demo/App.java
~~~

Expected:

- javac exit code equals **0**.
- Compiler prints a diagnostic like `Note: PROBE_PROCESSOR_EXECUTED`.
- A generated source file exists at **build/generated/demo/Generated.java** and application/generated class bytecode exists at **build/classes/demo/**.

Run the application (this is an additional runtime step, not a substitute for compilation checks):

~~~text
java -cp build/classes demo.App
~~~

Exact stdout:

~~~text
ok
~~~

**Verification:** the example suite above was run with OpenJDK 24.0.2: the `-proc:none` case returned exit code **1** (because `Generated` did not exist), and the processor-enabled case printed the `PROBE_PROCESSOR_EXECUTED` diagnostic and the program printed `ok`.

To re-run independently, use a **fresh output directory or clean old outputs**. If you accidentally put `build/classes` from the positive run onto the negative run's classpath, the previously compiled `Generated` class can make the negative case falsely succeed. On Windows PowerShell 5.1, `Set-Content -Encoding UTF8` adds a BOM to some files; for Java 17 source, save as UTF-8 **without BOM** using an editor or appropriate API if you encounter invalid BOM character diagnostics.

## 5. Runnable Example: A javac Plugin Initialized During Compilation

The **javac plugin** mechanism differs from annotation processors. A plugin implements `com.sun.source.util.Plugin` in the `jdk.compiler` module, and the compiler recognizes it by the name returned from `getName()`. Plugins are loaded via Java's **ServiceLoader**, using the service file `META-INF/services/com.sun.source.util.Plugin`. Typically a plugin registers a `TaskListener`; the example below simply emits a signal in `init` to demonstrate that plugin code ran.

Create the additional files:

~~~text
processor-demo/
├── plugin/demo/AuditPlugin.java
├── app/demo/Standalone.java
└── build/plugin/META-INF/services/com.sun.source.util.Plugin
~~~

**plugin/demo/AuditPlugin.java**:

~~~java
package demo;

import com.sun.source.util.JavacTask;
import com.sun.source.util.Plugin;

public final class AuditPlugin implements Plugin {
    @Override
    public String getName() {
        return "AuditProbe";
    }

    @Override
    public void init(JavacTask task, String... args) {
        System.err.println("AUDIT_PLUGIN_STARTED");
    }
}
~~~

**app/demo/Standalone.java**:

~~~java
package demo;

public final class Standalone {}
~~~

**build/plugin/META-INF/services/com.sun.source.util.Plugin** must contain exactly one line:

~~~text
demo.AuditPlugin
~~~

First create the directories **build/plugin** and **build/plugin-classes**, and place the service file at the exact path. Then run:

~~~text
javac -encoding UTF-8 -d build/plugin plugin/demo/AuditPlugin.java
jar --create --file build/audit-plugin.jar -C build/plugin .
javac -processorpath build/audit-plugin.jar -Xplugin:AuditProbe -d build/plugin-classes app/demo/Standalone.java
~~~

The last line activates the plugin named **AuditProbe** while still compiling the `Standalone` class. When the plugin is found and loaded successfully, stderr contains:

~~~text
AUDIT_PLUGIN_STARTED
~~~

**Verification:** this command ran successfully on OpenJDK 24.0.2. `-Xplugin:AuditProbe` is **javac**'s plugin-selection option; it is not an annotation processor and is not disabled merely by `-proc:none`. In this example, `-processorpath` is used as the extension search path for the plugin's ServiceLoader mechanism as well; if the path/JAR/service file is wrong, the compiler cannot load the plugin.

**API-level distinction:** the processor example above specifies `--release 17` because it uses standard Java 17 APIs. `com.sun.source.util.Plugin` is a JDK compiler API and should not be treated as a universal Java SE application library across all compilers. When developing a real plugin, build and test against the target **javac** version, especially if using AST internals or unstable `com.sun.tools.javac.*` APIs.

Reference: [Plugin API — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/Plugin.html).

## 6. Why Can Processors/Plugins Create Supply Chain Risks?

Consider a CI system fetching a new processor JAR from an artifact repository. CI runs `javac` with that JAR on the processor path. As soon as it is loaded and activated, the processor **is already executable code in the build context**, so it can do much more than generate code. Risk categories:

| Risk category | Example possible impact | Ways to reduce attack surface |
| --- | --- | --- |
| Reading sensitive info | Build process can read environment variables, config files containing tokens | Do not supply secrets to the compile step unnecessarily; minimal file access rights |
| Writing files and altering artifacts | Processor generates extra sources/resources or modifies files the process has write access to | Run in a temporary working directory, restrict write permissions, diff/inspect artifacts |
| Network connections | Extension code sends data out if the runner has network egress | Restrict egress via the execution environment, proxy, or firewall per policy |
| Executing other commands | Processor/plugin uses Java process APIs to run external tools | Isolate runners, reduce OS privileges, do not mount sensitive sockets/credentials |
| Non-reproducible builds | Output depends on clock, network, local machine, or undeclared inputs | Pin versions, check inputs/outputs, run in an isolated environment |
| Swapped dependency/processor | Artifact has the same name but altered contents | Pin versions and checksums/signatures, use trusted registries, review updates |
| Resource exhaustion | Processor loops long, creates mass files, consumes large RAM | Enforce CPU/RAM/time and disk limits in containers/CI |

Crucially, **actual permissions and limits come from the execution environment**, not from annotation metadata. JPMS manages module readability and exports, yet **is not an OS sandbox** for processors. Classpath/module path rules also do not replace network or filesystem controls. Running a processor in a separate JVM can help isolate faults, but if that separate JVM still holds the same privileges and secrets, process separation alone does not create a complete security boundary.

In some build tools, the compiler or processor runs inside a worker process/daemon; in other setups, the task may run inside the build process or via a fork. Do not assert that every processor always runs in a fixed PID. The principle remains identifying the **process that actually loads the extension**, its user/permissions, and the resources it can access.

## 7. Safe Configuration Checklist in Projects

### 7.1. Controlling Which Extensions Run

- Configure a separate **processor path**; avoid letting an unrelated artifact silently participate in processor discovery.
- Use **`-processor`** with a list of fully qualified names when you want to specify exactly which processors may be invoked.
- If annotation processing is not needed, set **`-proc:none`** on the corresponding **javac** step; still audit javac plugins and other build tasks.
- Inspect **`-Xplugin`**, `META-INF/services/com.sun.source.util.Plugin`, and JAR paths when evaluating compiler plugins.
- In Gradle/Maven, inspect dependencies used for processors, compiler plugins, buildscript/plugin classpaths, and code-generation tasks. These paths have different permissions/lifecycles; disabling one path does not disable all of them.

**Gradle — illustrative configuration** for an approved processor:

~~~groovy
dependencies {
    annotationProcessor("org.example:approved-processor:1.2.3")
}
~~~

This is a **Gradle syntax** example, not real artifact coordinates to download. It must be replaced with a verified dependency; merely declaring it under `annotationProcessor` does not guarantee the processor is safe. When processing needs to be disabled on a specific compile task, configure the corresponding compiler args and verify the actual command line passed to javac.

### 7.2. Locking Dependency Sources and Reproducibility

- Use dependency locking/version pinning and checksum/signature verification mechanisms if supported by the build tool.
- Review processor/plugin updates just like executable code updates, not just project source code reviews.
- Use only verified artifact registries and publisher accounts; never run a newly downloaded arbitrary JAR just because the name matches.
- In CI, pin the JDK toolchain, record compiler version, processor/plugin versions, and options; inspect generated sources/resources when they are critical artifacts.
- When an update alters generated files, read the diff and investigate changes that do not correspond to functional requirements.

### 7.3. Designing Least-Privilege Runners

A good CI environment for compilation typically features: ephemeral workspace, unprivileged user, filesystem writable only where necessary, CPU/RAM/time limits, controlled network egress, and **no release keys granted** to untrusted source compilation steps. Deployment secrets should only be provided to an authorized deploy step; do not share them broadly with the build process for configuration convenience.

Containers can help, yet are not automatically safe if mounting sensitive paths, running privileged/root, exposing the Docker socket, or enabling unrestricted networking. Build runner restrictions must take effect at the OS/container/CI layer and be tested in practice. **Reading code or running compilation from an untrusted pull request** must be treated as executing untrusted code if the build invokes processors/plugins.

### 7.4. Recording Traces and Distinguishing Error Causes

It is useful to record: the javac command (secrets redacted), Java version, classpath/processor path, selected processor/plugin names, valid diagnostic markers, and generated artifacts. A NOTE message only proves a piece of code ran; **it does not prove the processor performed no other actions**.

Do not print secret values or entire environment variables directly to logs. Processor names and paths can contain internal metadata; redact logs according to project policy before publishing.

## 8. Boundary Testing: A Matrix Runnable in CI

After preparing the two-part example above, run each case in a **clean output directory** and compare against expectations:

| ID | Setup | Expected | Evidence |
| --- | --- | --- | --- |
| C01 | Compile `App.java` with `-proc:none`, no `Generated` on classpath/sourcepath | REJECT | non-zero javac; error for missing `Generated` |
| C02 | Correct `-processorpath` and `-processor demo.ProbeProcessor` | ACCEPT | javac 0; marker `PROBE_PROCESSOR_EXECUTED`; source/class generated |
| C03 | Compile `Standalone.java` without `-Xplugin` | ACCEPT | javac 0; no plugin marker from the example |
| C04 | `-Xplugin:AuditProbe` and valid JAR/service descriptor | ACCEPT | javac 0; stderr contains `AUDIT_PLUGIN_STARTED` |
| C05 | Configure `-Xplugin:WrongName` with no plugin of that name | REJECT config | javac rejects the request for missing plugin |
| C06 | Omit processor path while specifying a processor not on classpath | REJECT config | javac cannot find processor |
| C07 | Put old `Generated.class` onto C01's classpath | Counter-example only | C01 can compile even when processor does not run; shows lack of isolation in testing is flawed |

Cases C05/C06 are **compiler infrastructure configuration tests**, not "wrong-type" Java source tests. Do not group them into the same statistics as Java semantic negative cases without classification. Case C07 should only be run in an intentional test environment to demonstrate **false positives**, then remove the stale class path.

An automated runner should:

1. Prepare fixtures and successfully compile the example's own processor/plugin before testing the application.
2. Clean/create fresh output for each run; place only explicitly identified JARs on the classpath/processor path.
3. Run javac and capture the exit code **right on that run**, diagnostics, markers, and artifact list; distinguish compiler errors from process-launch failures.
4. For ACCEPT, require exit code **0** and markers/artifacts when required by the case contract. For REJECT, require non-zero and the exact failure cause. Do not treat arbitrary exceptions or timeouts as a "negative pass."
5. Try inverting expectations or removing verification markers; the runner must report FAIL. This tests that the oracle can detect failures rather than merely printing "PASS" on exit code.
6. When comparing messages, avoid depending on verbatim full stderr: locale and JDK versions may vary. Pin the compiler version if checking specific diagnostic codes.

## 9. Common Misconceptions

**"Annotations are just metadata, so an annotation processor cannot cause side effects either."** Incorrect. Annotations in source are metadata, whereas a processor is a Java class executed by the compiler when selected/loaded.

**"Enabling `--release 17` means my build cannot run other code."** Incorrect. `--release` constrains the language/API of the **compiled target code**; it is not a sandbox mechanism for compiler processors/plugins.

**"Disabling annotation processing disables all build extensions."** Incorrect. `-proc:none` only affects annotation processing in javac; `-Xplugin`, Java agents, compiler wrappers, Gradle/Maven plugins, or custom tasks belong to different mechanisms.

**"Separating processor path from classpath guarantees total safety."** Incorrect. Path separation helps control extension loading sources and avoid unintended discovery; processors allowed to run still possess the process/runner privileges.

**"JDK 23 never runs processors anymore."** Incorrect. JDK 23 changed the **default when not explicitly configured**; users can still enable processing via valid options.

**"No generated file means no processor ran."** Incorrect. A processor may only inspect code and emit diagnostics, or run without generating files. Measure according to the specific processor/test contract.

**"Having `.class` files guarantees the recent compilation succeeded."** Incorrect if artifacts from a prior run remain. Use clean output and check the current run's exit code.

**"All compilers have the exact same plugin API and diagnostics."** Incorrect. `com.sun.source.util.Plugin` is provided by the JDK's `jdk.compiler`; other compilers may offer different extension mechanisms. Error messages, codes, and diagnostic ordering can also differ.

## 10. Reinforcement Exercises

**Exercise A — identifying allowed processor execution:** reproduce the example in section 4 in a temporary workspace. Run C01 and C02 in turn; explain why the same `App.java` produces different outcomes. Specify the processor name, the directory holding the processor binary, and the generated file.

**Exercise B — distinguishing plugins from processors:** implement section 5 and observe `AUDIT_PLUGIN_STARTED` in C04. Additionally run `javac -proc:none -processorpath build/audit-plugin.jar -Xplugin:AuditProbe -d build/plugin-classes app/demo/Standalone.java` in clean output and explain why the plugin still activates even though annotation processing is disabled.

**Exercise C — controlling the build environment:** take a small project with a real processor. List each extension loading path (annotation processor, javac plugin, Gradle/Maven plugin), artifact sources, filesystem permissions, network accessibility, and secrets. Design a least-privilege CI setup and specify which parts are required to function. Do not intentionally attempt to read secrets or exfiltrate data.

**Completion criteria:**

- Identify at least three categories of executable code during compile/build and their entry points.
- Accurately explain `-processor`, `-processorpath`, `-proc:none`, `-proc:full`, and `-Xplugin`, including the default change in JDK 23.
- Run the enabled/disabled annotation processing pair and observe differing diagnostics and bytecode.
- Run the javac plugin example producing a marker upon initialization.
- Distinguish compile-time execution from runtime application code, and javac switches from Gradle/Maven configuration.
- State actual privilege boundaries, identify risks from untrusted artifacts, and propose at least three practical controls: explicit extension selection, artifact locking/verification, and least-privilege CI.

**Core message:** a dependency used as a compiler extension must be treated as **code allowed to execute**, not merely a data-type library. Compiling untrusted sources alongside untrusted processors/plugins in a highly privileged environment can turn a build step into an attack surface. Declare extensions explicitly, observe through testing, and isolate privileges at the execution environment level.