# Managing Annotation Processors and Choosing -proc:none When Unneeded

When a Java application **compiles source code at runtime** using the JavaCompiler API (JSR 199), compilation can do more than turn `.java` files into bytecode. The compiler can also **invoke annotation processors** per JSR 269 to inspect declarations, generate additional source code, or report errors. This is useful when code genuinely needs MapStruct, Dagger, or a host-controlled processor; however, for user-submitted code or a small Java snippet that does not require code generation, running unintended processors adds side effects, cost, and risk.

Therefore, every dynamic compilation run must have an explicit policy: **when annotation processing is needed, which processors are allowed to run, where processors are loaded from, and when `-proc:none` must be passed**. This is a **compile-time** decision and does not directly affect whether the JVM can read annotations via reflection after the class is loaded.

## 1. What Does an Annotation Processor Do?

An annotation is metadata attached to packages, classes, interfaces, methods, fields, parameters, and other Java elements. Yet merely writing `@SomeAnnotation` **does not make the compiler generate code automatically**. An annotation processor is a Java program implementing **javax.annotation.processing.Processor**, commonly extending `AbstractProcessor`, which `javac` can load and invoke during the annotation processing step.

A processor can:

- read the declaration model of the code being compiled via `javax.lang.model`;
- validate rules and emit `Diagnostic.Kind.ERROR`/`WARNING`/`NOTE` via `Messager`;
- generate Java source, class, or resource files via `Filer`;
- execute across multiple rounds: newly generated source may itself contain annotations and be processed in the next round.

For example, a processor handling `@GenerateMarker` can generate the class `generated.MarkerGenerated`. Afterward, `javac` continues compiling the generated class if running in standard compilation mode.

An annotation with `RetentionPolicy.SOURCE` is still visible to a processor during compilation, even though it does not need to remain for runtime reflection. Conversely, an annotation with `RetentionPolicy.RUNTIME` **does not require an annotation processor**; the program may simply intend to read it via reflection when the class runs.

**Key risk point:** a processor is Java code that can **execute during compilation**. It is not merely passive metadata. A processor can access the filesystem, network, threads, or other resources with the privileges of the compiler process. For an on-demand compile service, the processor allowlist is part of the code-execution authorization policy.

## 2. Three javac Annotation Processing Modes

| Option | Behavior | When Applicable |
| --- | --- | --- |
| **-proc:none** | Standard Java compilation; **runs no annotation processors** | Standalone code, sources not requiring generated code, dynamic inputs without approved processors |
| **-proc:only** | Runs annotation processing **without running the normal class compilation step** afterward | Generating sources or testing processors separately in a pipeline |
| **-proc:full** | Runs annotation processing and then compiles classes | Sources requiring generated code; use when the `javac` version supports this option |

You can omit `-proc` altogether and select processors via `-processor`, `-processorpath`, or `--processor-module-path`. In that case, annotation processing may be enabled according to the rules of the running `javac` version. In systems needing reproducible results, choose **explicitly** instead of relying on whether the compiler automatically discovers processors.

**Do not confuse `-proc:none` with `-implicit:none`.** `-implicit:none` controls whether `javac` emits `.class` files for implicitly found sources; it **does not replace disabling annotation processing**. Likewise, `--release 17` specifies the target language/API/bytecode level and does not automatically disable processors.

### Important Change Since JDK 23

In `javac` versions **up through JDK 22**, when `-proc:none` is absent, the compiler can automatically discover processors on the search path (defaulting to the classpath if no separate processor path is given). This used to trigger unintended execution when a dependency happened to bundle a processor registration file.

**Starting in JDK 23**, annotation processing **is no longer enabled automatically merely because a processor is present on the classpath**. You must configure or request annotation processing explicitly, such as `-processor`, `-processorpath`, `--processor-module-path`, `-proc:only`, or `-proc:full`. This change is a policy of the **running `javac`**, not of the target bytecode version.

For example, a program running **JDK 24** and passing `--release 17` still uses `javac` 24's processor discovery rules; `--release` does not revert annotation-processing defaults to JDK 17.

The `-proc:full` option was backported to some JDK 17 updates (e.g., 17.0.11 and later), though you should not assume all older 17 builds accept it. When targeting multiple JDK 17 builds, explicitly selecting processors with `-processor` and `-processorpath`, or disabling with `-proc:none`, is the clearest approach. Always check `javac -version` and `javac --help` on the actual deployment JDK.

Reference on the change: OpenJDK/Inside Java, “JDK 23: Changes Default Annotation Processing Policy” — https://inside.java/2024/06/18/quality-heads-up/

## 3. Where Are Processors Located?

A very common mistake is mixing **the compiled code's classpath** with **the processor path**:

| Option | Path Used For | Notes |
| --- | --- | --- |
| `-classpath` / `-cp` | Types, annotation APIs, and libraries needed by Java sources to compile | Must not be mixed with the processor path in environments needing isolation |
| `-processorpath` / `--processor-path` | Processor classes/JARs and dependencies required to run processors | Set explicitly when processors are needed; do not allow arbitrary classpath dependencies to be picked up |
| `--processor-module-path` | Module path used to find processors packaged as modules | Use when the processor is an appropriate named module |
| `-processor a.b.FooProcessor` | Comma-separated list of explicitly chosen processor class names | Bypasses default processor discovery |
| `-Akey=value` | Option passed to processors | Processors define the meaning; not a general `javac` flag |
| `-s directory` | Directory where **generated Java sources** are written | Useful for inspecting generated code |
| `-d directory` | Directory where **resulting class files** are written | Should differ across compilation tasks |
| `-XprintRounds`, `-XprintProcessorInfo` | Prints extra round and invoked-processor details (`javac` options) | Useful for diagnosing why a processor did not run |

A processor is registered for automatic `javac` discovery via the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Its contents list processor class names, one per line, for example:

~~~text
demo.MarkerProcessor
~~~

However, if you only allow **one specific processor**, you can pass `-processor demo.MarkerProcessor` and `-processorpath` containing only the approved processor and its dependencies. The runnable example below uses this exact approach and therefore **does not need** a `META-INF/services` file. These are two different processor selection mechanisms, not two files that must both exist together.

In an on-demand compilation application, do not use the host process's `java.class.path` as the processor path by default. The host may carry extra dependencies and processors unintentionally included in it. Build an **allowlist of approved processors/JARs** and use an isolated compilation classpath. Only when the environment is controlled and a processor is required should you grant a path for the compiler to load and execute it.

## 4. When Should You Choose -proc:none?

**Choose `-proc:none` by default** if the task only needs syntax checking, compiling a basic Java class, or compiling externally supplied code with no formal requirement for generated code. This option prevents `javac` from activating annotation processors in that task even if a processor JAR is present on the search path.

Typical scenarios:

- Code snippet compiler for learners: users enter plain Java classes, methods, or expressions.
- Java source validation service before persistence: only compiler diagnostics and bytecode are needed.
- Plugin host compiling Java from uploaded files: no vetted processor list exists yet.
- Compiling classes with annotations used only at runtime, requiring no processor to generate types or config.
- Compiling standalone sources already generated by another step: no need to re-run processors in this compilation.

However, **do not disable processors mechanically** for sources that inherently depend on generated types. For example, projects using MapStruct need generated mapper implementations; Lombok needs processing to support code using generated syntax/methods. With `-proc:none`, the compiler may report `cannot find symbol`, missing implementations, or succeed yet lack expected artifacts. In such cases, either enable the **exact allowlisted processors**, or compile with generated sources/classes prepared by a trusted pipeline.

Seeing an `@` symbol in source **is not enough** to conclude a processor is needed; read the contract of the annotation and required dependencies. For example, `@Override` does not require a user-configured annotation processor.

## 5. Runnable Example: JavaCompiler at Runtime, Enabling and Disabling a Processor

We build a complete Java 17+ program consisting of three files:

~~~text
src/
  demo/
    GenerateMarker.java
    MarkerProcessor.java
    RuntimeCompileDemo.java
~~~

`RuntimeCompileDemo` generates the `generated.Task` source annotated with `@GenerateMarker`, then compiles it **twice** into two separate output directories:

1. **enabled:** selects processor `demo.MarkerProcessor` via `-processor` and sets `-processorpath` explicitly; the processor additionally generates `generated.MarkerGenerated`.
2. **disabled:** passes `-proc:none` and selects no processor; `generated.Task` still compiles because the annotation API is on the classpath, yet `generated.MarkerGenerated` **does not exist**.

Results are verified by checking the actual **class file** existence, not merely processor log messages.

### 5.1. Annotation Definition

**src/demo/GenerateMarker.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMarker {}
~~~

This is simply a marker annotation with no execution logic. `RetentionPolicy.SOURCE` lets the processor observe the annotation in the compilation unit, while the compiler is not required to retain it in the runtime class file.

### 5.2. Annotation Processor Generating a Class

**src/demo/MarkerProcessor.java**

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

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkerProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (generated || round.processingOver()
                || round.getElementsAnnotatedWith(GenerateMarker.class).isEmpty()) {
            return true;
        }
        generated = true;
        try (Writer out = processingEnv.getFiler()
                .createSourceFile("generated.MarkerGenerated").openWriter()) {
            out.write("package generated; public final class MarkerGenerated {}");
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, ex.getMessage());
        }
        return true;
    }
}
~~~

Key components:

- `@SupportedAnnotationTypes` specifies which annotations the processor supports; distinct from importing the annotation inside the processor itself.
- `@SupportedSourceVersion` declares the language level supported by the processor. The example uses `RELEASE_17` and compiles the target with `--release 17`.
- `RoundEnvironment` holds elements carrying annotations in the current round. `processingOver()` identifies the final round.
- `Filer.createSourceFile` creates a new source for the compiler, which is then compiled in standard processing-and-compilation mode.
- The `generated` flag avoids trying to create **the same filename multiple times** across rounds, which would throw `FilerException`.

In this simple example, the processor generates one illustrative class. Real processors must define class naming rules, handling of multiple annotated elements, dependencies, and consistent error reporting; never generate a fixed class name per annotation if collisions are possible.

### 5.3. Host Invoking JavaCompiler with Its Own Processing Policy

**src/demo/RuntimeCompileDemo.java**

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class RuntimeCompileDemo {
    private static void compile(boolean enableProcessor) throws Exception {
        String mode = enableProcessor ? "enabled" : "disabled";
        Path dir = Path.of("build", "dynamic", mode);
        Path source = dir.resolve("src/generated/Task.java");
        Path classes = dir.resolve("classes");
        Path generatedSources = dir.resolve("generated-sources");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);
        Files.createDirectories(generatedSources);
        Files.writeString(source,
                "package generated; import demo.GenerateMarker; " +
                "@GenerateMarker public class Task {}",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }
        String cp = System.getProperty("java.class.path");
        List<String> options = new ArrayList<>(List.of(
                "--release", "17", "-encoding", "UTF-8",
                "-classpath", cp, "-d", classes.toString(),
                "-s", generatedSources.toString()));

        if (enableProcessor) {
            options.addAll(List.of(
                    "-processorpath", cp,
                    "-processor", "demo.MarkerProcessor"));
        } else {
            options.add("-proc:none");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        boolean success;
        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects(source.toFile());
            success = Boolean.TRUE.equals(
                    compiler.getTask(null, files, diagnostics,
                            options, null, units).call());
        }
        if (!success) {
            throw new IllegalStateException(
                    diagnostics.getDiagnostics().toString());
        }
        boolean generated = Files.exists(classes.resolve(
                "generated/MarkerGenerated.class"));
        System.out.println(mode + ": compiled=" + success +
                ", generated=" + generated);
        if (generated != enableProcessor) {
            throw new IllegalStateException(
                    "Unexpected processor behavior");
        }
    }

    public static void main(String[] args) throws Exception {
        compile(true);
        compile(false);
    }
}
~~~

In this program, `javac` runs **inside the application's own JVM** via `javax.tools.JavaCompiler`; it does not use `ProcessBuilder` to spawn an external `javac` process. `getSystemJavaCompiler()` is normally available when running on a full JDK or a runtime image containing the right compiler; if it returns `null`, the application must report that compiler capability is missing. It does not download a JDK automatically.

**JavaCompiler.getTask** accepts options similar to the `javac` CLI. The `enableProcessor` variable is a host decision and must never be taken as an arbitrary option string from untrusted input. When enabled, `-processorpath` and `-processor` are added; when disabled, `-proc:none` is added. The Java input in both modes has the exact same annotation, so the difference in generated classes comes from **the processing policy**, not from changing the source.

To keep the example easy to run, `cp` uses the demo program's own classpath, which contains both the annotation API and the processor. **This is a minimal shortcut for the demo, not how processor privileges should be separated in production.** For a multi-user runtime compiler, separate the processor path from the compiler classpath, restrict approved JARs, and keep output paths isolated per request.

### 5.4. Compiling and Running the Demo Program

Run from the directory containing `src`, with **JDK 17 or later**. On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/classes | Out-Null

javac --release 17 -proc:none -encoding UTF-8 -d out/classes src/demo/GenerateMarker.java src/demo/MarkerProcessor.java src/demo/RuntimeCompileDemo.java

java -cp out/classes demo.RuntimeCompileDemo
~~~

The first `javac` command passes `-proc:none` when **compiling the demo tool classes themselves**, so no processors are discovered and run during the bootstrap compile. Once the program starts, it invokes the compiler sequentially with the `enabled` and then `disabled` policies.

On Linux/macOS, replace the directory creation command with:

~~~bash
mkdir -p out/classes
~~~

The remaining two `javac`/`java` commands stay identical. The code uses `System.getProperty("java.class.path")`, so Java provides the platform-appropriate classpath separator.

**Exact stdout of the program:**

~~~text
enabled: compiled=true, generated=true
disabled: compiled=true, generated=false
~~~

This result was verified with `javac --release 17`, running the program on a newer JDK. `JavaCompiler` generated `generated.Task.class` in **both** directories. Only `enabled` mode produced **generated.MarkerGenerated.class** and its corresponding source file in `generated-sources`.

How to interpret the output:

- `compiled=true` in both runs proves the `@GenerateMarker` annotation does not inherently require a processor for the base source to compile.
- `generated=true` in the first run proves the processor was selected, loaded, and generated source, and the compiler compiled that source.
- `generated=false` in the second run proves `-proc:none` eliminates annotation processing in that compilation task.
- Two separate output directories prevent leftover classes from the previous run from skewing results. When testing real systems, also delete/rotate output namespaces appropriately instead of sharing one code-generation directory across users.

If the annotation API is missing from `-classpath`, the target will not recognize `@GenerateMarker` and compilation will fail **even with processors disabled**. `-proc:none` does not erase annotation classes that the source needs during type checking.

## 6. Selecting Processors via the JavaCompiler API Instead of Auto-Discovery

Selection in the example relies on **`-processor class-name`**. In addition, `JavaCompiler.CompilationTask` provides `setProcessors(Iterable<? extends Processor>)` so the host can supply **processor instances** selected directly.

The idea behind the instance-based branch is:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, files, diagnostics, options, null, units);
task.setProcessors(List.of(new MarkerProcessor()));
boolean ok = Boolean.TRUE.equals(task.call());
~~~

This is an **alternative illustrative snippet** placed in a method where `compiler`, `files`, `diagnostics`, `options`, and `units` are constructed as in the complete example; it is not a standalone program. When using `setProcessors`, do not simultaneously pass `-processor` selecting a different set; pick one controlled selection mechanism. To completely disable annotation processing, pass `-proc:none` and supply no processors.

Supplying instances lets the host manage processor objects explicitly, yet **it is not a sandbox**: processor constructor/`process` code still executes inside the host JVM. For processors loaded from JARs, class loading and instantiation must be managed independently so unapproved dependencies/JARs do not enter the compiler's class loader.

In a real on-demand compilation task, define an input policy such as:

~~~text
CompilationPolicy {
    languageRelease = 17
    annotationProcessing = DISABLED | EXPLICIT
    allowedProcessors = [approved identifiers]
    compilerClasspath = [annotation API and compile dependencies]
    processorPath = [only processor JARs and required dependencies]
    sourceOutput = isolated directory
    classOutput = isolated directory
}
~~~

The block above is a **policy description**, not a runnable Java class. Starting from a fixed policy prevents a request from arbitrarily injecting `-processorpath`, `-proc:full`, `-Xplugin`, or flags that alter the compilation pipeline.

## 7. Trust and Processor Lifecycle in a Runtime Compiler

An annotation processor has the authority to execute code during the compilation task itself. Using `-processorpath` **helps select and organize dependencies**, yet it does not restrict the processor's OS privileges. Placing processors in a separate class loader also only separates namespaces; it does not create a security boundary.

When code or processors are untrusted, decide the following separately:

1. **No generated code required:** pass `-proc:none`; prevent processors from being auto-discovered via bundled JARs.
2. **Supported generated code required:** permit only approved processors via `-processor` or `setProcessors`, with tested artifact sets and versions.
3. **Potential untrusted code execution:** consider running compilation tasks in a **restricted-privilege process/OS container** with CPU, memory, time, filesystem, and network limits. `-proc:none` only disables annotation processing; it **does not turn compilation or bytecode execution into an absolute sandbox**.
4. **Output isolation:** use isolated working directories so processors cannot write into the application's workspace or overwrite another user's artifacts.
5. **Monitoring and errors:** collect Compiler Diagnostics, root exceptions, processor version, source release, duration, and generated files. Avoid leaking sensitive details in logs/errors returned to code submitters.
6. **Reproducibility:** pin `javac` version, `-processor`, processor path, annotation API, and `-A` options; freeze inputs if build reproducibility is required.

Remember that compiled Java source **is not implicitly executed** by the host program when `JavaCompiler` returns. However, processors **already executed** if annotation processing was enabled; and if the host subsequently class-loads/instantiates/invokes generated bytecode, that is a new execution step requiring its own policy.

## 8. Managing Code-Generation Rounds and Filer Errors

A processor can generate source in one round, after which the compiler invokes the processor again in the next round to process the newly generated source. When multiple rounds occur, a processor must avoid rewriting **the same path/file** within the same compilation.

In the example, `MarkerProcessor` uses the `generated` flag to ensure `createSourceFile("generated.MarkerGenerated")` is called only once. When `Filer` encounters an attempt to create a duplicate file in a single compilation, it can throw `FilerException`. If another processor also generates the same class name, the build can fail due to collision; never handle this by silently ignoring the error and picking an arbitrary output.

Helpful practices:

- Derive generated class names from the name/type of the processed element with a collision-avoidance strategy rather than generating one fixed name for every annotation.
- Track processed elements or check rounds as needed; use `round.processingOver()` to detect the final round.
- Report errors through `Messager` with `Element` context so `javac` pinpoints the compilation error.
- Avoid placing arbitrary side-effecting logic in every round, as the number of rounds varies when generated sources introduce new annotations.
- For independent tasks, use isolated output directories and do not retain stale processor/source caches without designing incremental compilation.
- When debugging, try `-XprintRounds` and `-XprintProcessorInfo` on compatible `javac` versions to see which rounds actually invoke the processor.

In the runnable example, verifying the `generated.MarkerGenerated.class` file is even better than reading a processor log line, because it proves the **generate source → compile generated source** pipeline completed end to end.

## 9. When -proc:none Breaks Compilation, How Should You Handle It?

First ask: **does the problem truly require generated output?** If the source only has marker annotations used for tagging or runtime inspection, `-proc:none` remains valid. If the source references a class or method meant to be generated by a processor, disabling processors will cause missing symbols.

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Same source: enabled generates class, disabled does not | Processor genuinely generates that class | Check `-s`, `-d`, and output JAR |
| `-proc:none` reports `cannot find symbol` | Source depends on generated types or classpath lacks annotation API | Identify symbol; distinguish generated source from annotation type |
| Enabled yet processor does not run | Missing `-processor`/`-processorpath`, wrong class name, JDK 23+ disables auto-discovery by default | Log compiler options; inspect processor artifact |
| ServiceLoader-style discovery misses processor | Missing `META-INF/services/javax.annotation.processing.Processor` | Inspect JAR via `jar tf`, verify UTF-8 descriptor contents |
| Processor runs yet generates no code | Annotation mismatches `@SupportedAnnotationTypes`, or no matching elements exist | Use `-XprintRounds`, diagnostics, and annotation tests |
| Source generated yet no `.class` exists | `-proc:only`, compilation failed, or different output path | Check `-proc`, `javac` errors, `-s`, and `-d` |
| `FilerException` from recreated file | Two processors/rounds attempt to create the same source or class name | Fix file-naming strategy; check multi-round handling |
| Generated code disappears after upgrading to JDK 23+ | Build relied on implicit classpath processor scanning | Switch to explicit processor selection |
| Compiler takes too long or task hangs | Processor performs long computation/I/O or blocks on resources | Enforce process resource limits, measure time, and log |

Also check **which JDK runs the processor**. `--release 17` controls the language level of the target source; the processor runs inside the current compiler environment and must be compatible with the JDK executing `JavaCompiler`. Do not assume the processor also runs inside a separate Java 17 JVM merely because the target is 17.

## 10. Checklist for Implementing On-Demand Compilation

Before allowing users or external systems to submit Java source for compilation:

- **Define an explicit policy:** when `DISABLED`, always pass `-proc:none`; when `EXPLICIT`, allow only the exact vetted set of processors.
- **Verify inputs/dependencies:** annotation APIs, sources, and libraries for type checking sit on the expected compiler classpath.
- **Separate the processor path:** never let arbitrary JARs from requests become executed processors. Pin versions and processor allowlists per task type.
- **Verify the JDK:** record the `javac` version and the default behavior difference between JDK 17–22 and 23+; never rely on implicit discovery rules.
- **Separate outputs:** `-d` for classes, `-s` for generated sources, per-task workspaces; verify generated sources/classes actually exist and avoid stale outputs.
- **Collect diagnostics:** do not read only `getTask.call()`'s Boolean; preserve meaningful errors for missing symbols, unsupported sources, unsupported processors, and file generation.
- **Control resources:** processors run Java code inside the compiler; if execution isolation is needed, use proper boundaries, not `-processorpath` alone.
- **Test both branches:** test compilation with and without processors, verifying both outputs and behavior when sources depend on generated code.
- **Never enable all processors indiscriminately:** an annotation processor accidentally bundled in a dependency is no reason to let it run.

## 11. Official References

- Oracle Java SE 17, **The javac Command**, sections on `-proc`, `-processor`, `-processorpath`, and Annotation Processing: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17, **JavaCompiler**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Oracle Java SE 17, **Processor**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Oracle Java SE 17, **CompilationTask**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Inside Java/OpenJDK, **JDK 23: Changes Default Annotation Processing Policy**: https://inside.java/2024/06/18/quality-heads-up/

**Implementation rule:** when a runtime compiler has no explicit requirement to run annotation processors, pass **`-proc:none`**. When generated code is genuinely required, enable **only approved processors**, supply an isolated processor path, test outputs, and treat the compilation task as a code-execution-capable operation.
