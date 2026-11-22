# Tracing Annotation Processing Rounds and Diagnosing Why a Processor Is Not Invoked

**Annotation processing** is the mechanism by which the Java compilation tool invokes *annotation processors* to read the declaration model, check conventions, or generate additional sources/resources. A processor implements the `javax.annotation.processing.Processor` API, typically extending `AbstractProcessor`; the compiler supplies `ProcessingEnvironment` and calls `process(...)` when the processor matches the annotations in a processing round.

When an annotation processor "does not run", there are many different causes: processing is disabled; the processor is not found; service registration is wrong; the annotation is declared in a different namespace; supported annotation types do not match; the processor is discovered yet not selected to run; the processor runs yet finds no matching elements; another processor claimed the annotation; or generated files end up in a different output than expected. Therefore, you must distinguish **discovery → invocation → annotation matching → processing rounds → file generation** before fixing.

From JDK 23 onward, `javac` no longer proactively searches for and runs processors merely because a processor is on the classpath when no explicit annotation-processing configuration is provided. On JDK 21/22, historical default behavior differs. For reproducible builds, **explicitly declare processors and the processor path**, while observing diagnostics and generated files rather than relying on JDK defaults.

## 1. What Are Annotation Processing Rounds?

The compiler works with a set of *root elements* in the first round, typically the top-level declarations of the compilation units being compiled. A processor can read elements carrying supported annotations and use `Filer` to create additional source files. Those new sources can become root elements in the **next round**. At the end of the process, there is a final round letting processors know that no further source-processing rounds will occur.

```text
Source passed to javac
        |
        v
 Round 1: initial roots
   - locate supported annotations
   - invoke selected processor
   - processor may create Generated.java
        |
        v
 Round 2: roots from newly created source
   - inspect newly appearing annotations
   - continue invoking active processor
   - processor may create additional source
        |
       ...
        |
        v
 Final round: processingOver() == true
        |
        v
 Compiler continues compilation steps and generates .class
```

This is a conceptual diagram. The number of rounds depends on whether new files are created, the processors, and the compiler implementation. **Do not assume every run has exactly two or three rounds**; do not use a fixed round count as a condition for build success.

`RoundEnvironment` provides important signals:

| API | Meaning |
| --- | --- |
| `getRootElements()` | Root elements passed to the current round, typically including types created in the previous round |
| `getElementsAnnotatedWith(...)` | Elements within the round's scope carrying the queried annotation |
| `processingOver()` | `true` when this round is the final round; output generated in this round will not be processed in a subsequent round |
| `errorRaised()` | `true` if an error was reported in the **previous** round |

`processingOver()` can be `true` even if `getRootElements()` is empty. Do not attempt to generate new sources in the final round and wait for the compiler to come back and process them. `errorRaised()` is not a total-error counter or an indicator confirming that a processor "has not run".

## 2. Discovery and Invocation Workflow

A processor is invoked only if several steps all match:

1. **Processing is enabled:** `javac` must be in a mode that runs annotation processing.
2. **The compiler finds the processor class:** classpath, processor path, or processor module path is configured properly.
3. **The processor can be discovered:** via `-processor Class.Name`, via proper service loader registration, or via a mechanism provided by the tool.
4. **The processor supports annotations in the round:** the result of `getSupportedAnnotationTypes()`, usually declared by `@SupportedAnnotationTypes`, must match the annotations the tool wants to process; `"*"` denotes a universal processor.
5. **The processor is selected and invoked:** the compiler calls `init` and then `process` according to protocol. An annotation may already have been claimed by another processor, affecting whether subsequent processors are asked to process it.
6. **The processor performs its work properly:** traverses `RoundEnvironment`, generates files or emits diagnostics, avoiding errors/exceptions.
7. **Outputs are used properly:** generated sources/classes/resources reside in the output locations actually used by the compiler or build tool.

Merely seeing a processor class in a JAR **does not prove it was instantiated**. Merely seeing an annotation on source **does not prove a processor will process it**. An annotation can have `RetentionPolicy.SOURCE` and still be processed by an annotation processor at compile time; runtime retention is not a prerequisite.

According to the `Processor` API, the compiler can invoke `process` multiple times **on the same instance**, including rounds where there are no longer annotations to process, if the processor was selected in an earlier round. Do not design global state assuming there is always a new processor object per round.

## 3. `javac` Options You Need to Know

| Option | Purpose |
| --- | --- |
| `-processor demo.MarkProcessor` | Specifies the exact processor to invoke, skipping auto-detecting processor names from service registration |
| `-processorpath path` or `--processor-path path` | Path used to locate processors on the processor classpath |
| `--processor-module-path path` | Module path to locate processors packaged as modules |
| `-proc:none` | Disables annotation processing while still performing compilation |
| `-proc:only` | Runs annotation processing without performing the subsequent normal class-generation step |
| `-proc:full` | Runs annotation processing then full compilation; supported since JDK 21, backported to certain older JDK updates |
| `-XprintRounds` | Prints information about annotation processing rounds |
| `-XprintProcessorInfo` | Prints information about which annotations processors are asked to process |
| `-s path` | Selects the directory to write **generated sources** |
| `-d path` | Selects the directory to write **compiled classes** |
| `-Akey=value` | Passes an option declared as supported by the processor; the compiler does not interpret `key` semantics itself |

`-XprintRounds` and `-XprintProcessorInfo` are **`javac` diagnostic flags**. Content, line count, order, and print location depend on version/compiler; use them to observe in logs, do not turn their text into a mandatory automation contract.

`-processorpath` is where **processor classes are loaded**, not the path for compiling business types. Annotations and dependencies needed by application sources must still be on the corresponding compile classpath or module path. If a processor depends on a helper library at runtime, that helper must also be on the processor path or the processor's class loader configuration.

To check available flags of the JDK in use, run `javac -version`, `javac -help`, and `javac -X`. Do not rely on the same defaults between JDK 17, 21, and 23+.

## 4. JDK 23 Changes the Annotation Processing Default

With `javac` up through JDK 22, if a processor was present under classpath search rules, many legacy builds automatically ran processing **without declaring an explicit annotation-processing option**. JDK 21/22 issued warnings about configurations relying on this default.

**From JDK 23 onward**, without an explicit annotation-processing configuration/request, `javac` **does not run annotation processors by default**. You can specify:

```bash
javac -processor demo.MarkProcessor -processorpath build/processor ...
```

or another mechanism such as configuring an appropriate processor path, `-proc:full`, or `-proc:only` depending on version.

If a build upgrades the JDK and suddenly lacks generated classes such as `MapperImpl` or `QCustomer`, check compile arguments. A processor JAR incidentally present on the classpath previously **is not enough to conclude** it will run automatically on a newer JDK.

`-proc:full` only requests running annotation processing and compiling; it **does not conjure a processor out of thin air**. A discoverable or explicitly specified processor is still needed. For processors you control, `-processor` plus an explicit processor path makes results easier to verify.

Distinguish compiler changes from decisions of Maven Compiler Plugin, Gradle JavaCompile, IDEs, or other tools: they can pass their own options and have incremental compilation mechanisms. Read the task's **actual command/compiler arguments** before concluding "the JDK isn't running the processor".

## 5. Self-Contained Java 17+ Example: Processor Generating Source Across Multiple Rounds

The example below has an `@Mark` annotation, a `MarkProcessor` processor, and an `Example` class depending on a `Generated` class created by the processor. It requires no libraries outside the JDK.

Directory tree:

```text
apt-lab/
  src/
    demo/
      Mark.java
      Example.java
    processor/
      demo/
        MarkProcessor.java
  build/
    processor/       (created beforehand, initially empty)
    classes/         (created beforehand, initially empty)
    generated/       (created beforehand, initially empty)
```

### File 1: src/demo/Mark.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Mark {
}
```

`SOURCE` retention makes the annotation available during source processing without needing it recorded for reading via runtime reflection. Processors do not require annotations with `RUNTIME` retention.

### File 2: src/processor/demo/MarkProcessor.java

```java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Mark")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MarkProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "round: final=" + round.processingOver()
                        + ", roots=" + round.getRootElements().size()
                        + ", errorBefore=" + round.errorRaised()
        );

        if (round.processingOver()) {
            return true;
        }

        Set<? extends Element> matched =
                round.getElementsAnnotatedWith(Mark.class);

        if (!generated && !matched.isEmpty()) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("demo.Generated");

                try (Writer writer = file.openWriter()) {
                    writer.write(
                            "package demo;\n"
                            + "public final class Generated {\n"
                            + "  private Generated() {}\n"
                            + "  public static String text() {\n"
                            + "    return \"generated\";\n"
                            + "  }\n"
                            + "}\n"
                    );
                }

                generated = true;
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "generation failed: " + exception.getMessage()
                );
            }
        }

        return true;
    }
}
```

Points worth observing:

- `@SupportedAnnotationTypes("demo.Mark")` is the fully qualified name of the annotation the processor accepts.
- `@SupportedSourceVersion(RELEASE_17)` declares Java 17 support; the lab compiles with `--release 17` for consistency.
- `getRootElements()` helps identify roots of the current round.
- `getElementsAnnotatedWith(Mark.class)` returns elements carrying `@Mark` within the round's scope; in the round of the newly generated source, that set may be empty.
- `processingOver()` recognizes the final round so no new files are generated when no next round remains.
- The `generated` flag prevents recreating the same fully qualified name across multiple rounds.
- `Filer.createSourceFile("demo.Generated")` creates a new Java file at the source output location; `Writer` must be closed for the content to be processed by the compiler.
- `Messager` emits `NOTE` and `ERROR` for operators to observe via compiler diagnostics. It is better than printing arbitrary logs to stdout.
- `return true` means the processor **claims the annotation types requested for processing**. If a universal processor (`"*"`) returns true, it can prevent other processors from receiving annotations; do not use that behavior unintentionally.

### File 3: src/demo/Example.java

```java
package demo;

@Mark
public class Example {
    public static void main(String[] args) {
        System.out.println(Generated.text());
    }
}
```

`Generated` does not exist before the build. If processing works, the processor generates it and the compiler compiles it alongside the program. If processing is disabled, the compiler typically reports that `Generated` cannot be resolved.

### Running in Two Steps to Avoid Processor Self-Bootstrapping Loops

Run from the `apt-lab` directory. Create three output directories; with Bash:

```bash
mkdir -p build/processor build/classes build/generated
```

With Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/processor,build/classes,build/generated | Out-Null
```

Step A — **compile the annotation type and processor first**, without running annotation processing yet:

```bash
javac --release 17 -encoding UTF-8 -proc:none -d build/processor src/demo/Mark.java src/processor/demo/MarkProcessor.java
```

At this step, output has at minimum:

```text
build/processor/demo/Mark.class
build/processor/demo/MarkProcessor.class
```

Step B — **compile the application and specify the processor explicitly**:

```bash
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.MarkProcessor -XprintRounds -XprintProcessorInfo -s build/generated -d build/classes src/demo/Example.java
```

Notes:

- `-cp build/processor` helps the compiler find the `demo.Mark` annotation used by `Example.java`.
- `-processorpath build/processor` helps the compiler find/load `demo.MarkProcessor` and the processor's `demo.Mark` dependency.
- `-processor demo.MarkProcessor` selects the processor directly, without needing to create `META-INF/services` for the demo.
- `-XprintRounds` and `-XprintProcessorInfo` let you view the number of rounds and which processors were asked to process annotations.
- `-s build/generated` writes generated sources; `-d build/classes` writes class files.
- `--release 17` clarifies the target Java version and maintains compatibility with `RELEASE_17`.

If the build succeeds, source output has:

```text
build/generated/demo/Generated.java
```

Class output has:

```text
build/classes/demo/Example.class
build/classes/demo/Generated.class
```

Run:

```bash
java -cp build/classes demo.Example
```

Exact program stdout:

```text
generated
```

**Do not confuse this stdout with `javac` logs.** Warnings/NOTEs, Round 1/2/final, and processor info may be printed across multiple lines and vary by JDK; do not pin them verbatim. What must be verified is that the compiler returns success, the processor produces appropriate NOTEs and `-XprintProcessorInfo`, generated source/class exist, and running the program prints `generated`.

## 6. Observing the Rounds of the Example

In compilation B, the rounds can be interpreted as follows:

| Round | Key Roots | What Does the Processor Do? |
| --- | --- | --- |
| First round | `demo.Example` | Detects `@Mark`; creates `demo.Generated` |
| Next round | `demo.Generated` | No longer `@Mark` in the new source; because the processor was active, it can still receive another call |
| Final round | Possibly empty | `round.processingOver() == true`; creates no new source |

The compiler is responsible for deciding the actual processing schedule; `-XprintRounds` shows which rounds ran. If a processor generates multiple files in subsequent rounds, the round count can increase. If a processor generates no new files, the process usually ends earlier.

When reading NOTEs from a processor, note that `errorRaised()` only reflects errors reported in the previous round. You cannot conclude the entire build succeeded when a round has no errors yet: the compiler can continue type checking and report errors at a later stage.

**Important:** `getRootElements()` is not a list of every class that already exists on the classpath or in the project; it is the roots of the current round. Processors are not invoked mechanically for every single class. Similarly, `getElementsAnnotatedWith(...)` does not return every annotated element across the entire dependency graph; it is bounded by the API's round/annotation model.

## 7. Situations Where a Processor Truly Is Not Invoked

Several typical cases:

### A. Processing Is Disabled

```bash
javac --release 17 -cp build/processor -proc:none -d build/classes src/demo/Example.java
```

In an empty output, this command does not run `MarkProcessor`, so it does not create `Generated`; `Example` using `Generated` will fail to compile. `-proc:none` is an explicit way to disable processing, often used when compiling the processor itself or when intentionally skipping APT.

### B. JDK 23+ Without Processing Configuration

A command with only `-cp` and without `-processor`, `--processor-path`, `--processor-module-path`, `-proc:only`, or `-proc:full` may **not run APT on JDK 23+**. On JDK 21/22, earlier default behavior differed. Fix with explicit configuration and by inspecting the real compiler task, rather than inferring solely from which JDK version is installed on the machine.

### C. Processor Not on Processor Path

For example, setting `-processor demo.MarkProcessor` yet `-processorpath` does not contain `demo/MarkProcessor.class` or its JAR. The compiler may report `Annotation processor 'demo.MarkProcessor' not found`; you must fix the artifact and search path, not add `import demo.MarkProcessor` to business source.

### D. Processor Present Yet Annotation Does Not Match

`@SupportedAnnotationTypes("demo.Mark")` does not catch another annotation such as `com.other.Mark` despite the same simple name `Mark`. If the processor only supports `demo.Mark` yet source uses `@OtherMark`, the compiler may not select the processor to run because there is no matching annotation.

For a processor meant to check every file even when no annotations exist, you can declare `@SupportedAnnotationTypes("*")` and return `false` if you do not want to claim annotations for other processors. That is a design choice to weigh carefully, not a trick to catch all errors by claiming every annotation.

### E. Incorrect Service Provider Declaration

When not using `-processor` and wanting discovery via the processor classpath, the JAR needs the file:

```text
META-INF/services/javax.annotation.processing.Processor
```

One-line content:

```text
demo.MarkProcessor
```

The path must have exact casing, an accurate fully qualified class name, the file must **reside inside the processor JAR**, and the processor/dependencies must be loadable. The processor class may be present yet the service file missing; if relying solely on auto-discovery, the processor will not run.

For a named module containing a processor, you can declare `provides javax.annotation.processing.Processor with ...;` and use `--processor-module-path` under JPMS rules. Do not assume a classpath service file and a module descriptor are the same discovery mechanism.

### F. Processor Ran Yet "Created Nothing"

A processor can be called with empty `annotations` or empty `round.getElementsAnnotatedWith(...)`, and intentionally generate no files. This differs from the processor not being loaded.

Check `-XprintProcessorInfo`, `-XprintRounds`, and `Messager` diagnostics inside `process`. If logs emitted by `process` exist yet there is no generated source, check file-creation conditions, annotation names, and `Filer`.

### G. Another Processor Claimed the Annotation

If a processor returns `true` to claim an annotation type, subsequent processors in the same round may not be asked to process that annotation. Verify the ordering/selection and claim policy of each processor, especially when a universal processor uses `"*"`.

Do not assume "adding a second processor" will make both receive the same annotation; check which annotations each processor supports and whether it claims annotations.

## 8. Processor Runs Yet Generated Files Cannot Be Found

Learners often check in the wrong place:

| Artifact | Location per Example Command | How to Verify |
| --- | --- | --- |
| Compiled annotation/processor | `build/processor/demo/*.class` | Check class and package path |
| Generated Java source | `build/generated/demo/Generated.java` | Check `-s` |
| Generated class | `build/classes/demo/Generated.class` | Check `-d` |
| Main class | `build/classes/demo/Example.class` | Check compile output |
| Runtime classpath | `build/classes` | Run `java -cp build/classes demo.Example` |

`-s` selects the compiler's source output location; `-d` selects the class output location. Creating sources **does not automatically guarantee** another framework or Gradle task has picked up the right source folder; if the tool uses build caches or incremental compilation, inspect the task's actual output path.

Other mistakes:

- The processor creates a file with `Filer.createResource` (a resource), yet the user looks for `.java`; you must determine the exact API called.
- The processor writes a file with `Files.write` to an arbitrary path: the compiler does not necessarily know it is generated source to feed into rounds.
- The processor creates a file colliding with an already-existing name or creates the same name twice in one run: `FilerException` can occur; create each fully qualified name once.
- File created yet `Writer` was not closed, leaving source incomplete; close resources properly.
- Class generated in source output yet compilation fails afterward: read full diagnostics, do not infer success merely because the Java file exists.
- Processor only runs `-proc:only`: generated Java sources may exist yet **normal compilation after processing does not run**, so do not expect the same class output set as `-proc:full`.

**Remember:** processor discovery, running the processor, creating sources, and creating class files are separate milestones; each milestone needs corresponding evidence.

## 9. Debugging via JavaCompiler API and DiagnosticCollector

When building an IDE/plugin or a tool that invokes the compiler programmatically, do not parse stderr text with fixed regexes. Use `javax.tools.JavaCompiler` and `DiagnosticCollector<JavaFileObject>` to collect diagnostics with kind, source, and location, combined with the `CompilationTask.call()` result.

Illustrative snippet **inside a tool method**, not a standalone program:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("JDK compiler unavailable");
}

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();

StandardJavaFileManager files =
        compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8);

Iterable<? extends JavaFileObject> inputs =
        files.getJavaFileObjectsFromStrings(
                java.util.List.of("src/demo/Example.java"));

JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        files,
        diagnostics,
        java.util.List.of(
                "--release", "17",
                "-cp", "build/processor",
                "-processorpath", "build/processor",
                "-processor", "demo.MarkProcessor",
                "-s", "build/generated",
                "-d", "build/classes",
                "-XprintRounds"
        ),
        null,
        inputs
);

boolean succeeded = Boolean.TRUE.equals(task.call());
files.close();
```

To compile this snippet successfully when placed in a real class, import `javax.tools.JavaCompiler`, `javax.tools.ToolProvider`, `javax.tools.DiagnosticCollector`, `javax.tools.JavaFileObject`, and `javax.tools.StandardJavaFileManager`; the enclosing method must handle `IOException` when calling `close()`. Output directories must exist and the processor must already be built.

`Diagnostics.getDiagnostics()` (with the lowercase `diagnostics` variable name) lets you iterate `Diagnostic` objects. The `Diagnostic.Kind`, `getSource()`, `getLineNumber()`, and `getMessage(Locale)` APIs support structured reporting. However, `getMessage` and `getCode` can still change across compilers; do not treat full text or compiler-specific codes as a fixed error-identification standard.

The API only helps observe errors emitted by the compiler/processor; if the processor was not called yet compilation still succeeds because an old generated class is on the classpath, you also need to inspect clean inputs/outputs and expected processor invocation separately.

## 10. Workflow for Investigating Why a Processor Is Not Invoked

Start from the concrete symptom: missing generated class, missing NOTE, or ignored annotation.

**Step 1 — identify tools and version.** Record `javac -version`, Java toolchain, Maven/Gradle compiler plugin, source/release, and CI worker JDK. JDK 23+ has a changed default processing policy.

**Step 2 — inspect the actual compile command.** Check `-proc:none`, `-proc:only`, `-proc:full`, `-processor`, `-processorpath`, `--processor-module-path`, `-cp`, and `-s`. An IDE can construct a command different from CLI.

**Step 3 — check the processor class.** Determine whether the JAR/class has `demo.MarkProcessor`; does the class have a default public no-argument constructor? Are any processor dependencies missing that cause the class loader to fail?

**Step 4 — check discovery.** If using `-processor`, verify the fully qualified name. If using auto-discovery, check the `META-INF/services/javax.annotation.processing.Processor` file or appropriate module descriptor `provides`.

**Step 5 — observe rounds.** Add `-XprintRounds` and `-XprintProcessorInfo` in a debug environment. If there are no rounds, check processing mode/discovery; if rounds exist yet the processor is absent, check matching/claiming.

**Step 6 — log from inside the processor.** `processingEnv.getMessager().printMessage(NOTE, ...)` in `init` or `process` helps show which lifecycle stage was entered. Do not rely on `System.out.println` and stdout ordering across multiple processors as a stable protocol.

**Step 7 — check annotation matching.** Full name, retention, target, repeated annotations and container annotations, supported types; for annotation processors supporting repeatable annotations, examine both the repeatable annotation and the containing annotation per the API.

**Step 8 — check generated output.** Verify `-s`, `-d`, file names, file open/close, and `FilerException` errors; check whether new generated sources exist when running a clean build.

**Step 9 — check annotation claiming.** A processor returning `true` can claim an annotation type away from later processors. Do not set `"*"` with `return true` if the tool only inspects and does not need exclusive processing.

**Step 10 — distinguish outcomes.** Did the processor run yet create nothing? Was the processor not selected? Did the processor create a file yet compilation failed? Only fix after pinpointing the exact milestone.

## 11. Common Errors and Symptoms

| Symptom | Possible Cause | Appropriate Check |
| --- | --- | --- |
| No generated class after JDK upgrade | JDK 23+ changed APT default | Inspect compiler options; declare processor explicitly |
| `-processor ...` yet compiler reports not found | Processor class or dependency is not on the processor path | Check package, JAR contents, search path |
| Processor present in JAR yet inactive | `-processor` not declared, service file missing, or processing not enabled | Check discovery/processor configuration |
| Rounds exist yet processor absent from log | Wrong annotation name/matching, processor not selected, claimed by another processor | `-XprintProcessorInfo` and `@SupportedAnnotationTypes` |
| NOTE from processor exists yet no generated file | Condition inside `process` not met or `Filer` error | Print annotation/roots size; check `-s`, Messager, exception |
| Runs on first build, processor seems absent on next | Incremental compilation/cache did not actually re-invoke javac/processor | Run a clean build in a test environment |
| `FilerException` due to duplicate file | Created same source name multiple times or collided with existing input | Track per-run generated names; avoid recreating across rounds |
| Unsupported source version warning | `@SupportedSourceVersion` lower than `--release`/`-source` in use | Synchronize source version in processor and task |
| `getElementsAnnotatedWith` empty | Different annotation name, current round roots do not contain matching elements, or annotation claimed | Record full qualified names, roots, rounds |
| `cannot find symbol Generated` | Processor did not generate, generated file not yet compiled, or wrong path/config | Check processor run, `-s`, `-d`, and compiler diagnostics |
| Processor throws exception | Logic error or processor runtime dependency issue | Read stack trace, processor path, and resource lifetime |
| NOTE not seen in CI | Log filtered/hidden by build tool, or processor not invoked | Check compiler task and generated artifacts, enable selective debug |

`-XprintProcessorInfo` only describes processors asked by the compiler to process annotation types; it does not guarantee the processor generated every required file. A file existing in the build directory also does not prove that *the current run* created that file.

## 12. Annotation Processors and Build Tools

### Maven

With Maven Compiler Plugin, processor configuration should reside on the plugin, not rely on the application classpath accidentally containing processors. How options are specified depends on the **plugin version**; modern versions have their own annotation processor path/dependency configuration and `proc` policy. When upgrading to JDK 23+, check the Maven Compiler Plugin version in use and the actual javac/plugin command generated.

Dependencies used at **application compile time** and dependencies used to **load processors** can differ. Do not put processor artifacts into the application's runtime dependencies if only needed during the build; check processor versions and transitive dependencies.

If `-proc:none` is used in the plugin, it disables processing for the task; adding annotations to source will not make the processor run. If `-proc:only` is used, do not expect the same set of class outputs as a normal build.

### Gradle

With the Gradle Java Plugin, processor dependencies are normally declared in the `annotationProcessor` configuration, distinct from `implementation`:

```groovy
dependencies {
    annotationProcessor 'group:processor-artifact:version'
}
```

The line above **illustrates syntax**; group/artifact/version names must be real project dependencies; it is not itself a runnable demo without external libraries.

Gradle passes the processor path to `JavaCompile` based on task configuration. If a processor is in `implementation` without being in `annotationProcessor`, do not conclude the processor is always invoked. Source sets such as `test` need corresponding processor configuration if code generation is needed in tests.

Incremental annotation processing also has constraints on *isolating* or *aggregating* processors depending on Gradle/plugins; processors writing arbitrary files outside `Filer` or reading inputs not tracked by the tool can make incremental builds inaccurate. When debugging, temporarily run a clean build to eliminate cache effects; afterward restore proper incremental mechanisms rather than disabling them permanently over a single error.

## 13. Designing Observable and Safe Processors Across Rounds

A processor can itself make debugging easier:

- Use `Messager` with appropriate `NOTE`/`WARNING`/`ERROR` kind, optionally attaching `Element` so the compiler displays source location.
- When creating files, use `Filer`, close writers/output streams properly, and pass originating elements if helpful for incremental tooling.
- Do not create the same fully qualified type across multiple rounds; processor state can persist throughout compilation.
- Do not rely on round numbers or set iteration order to produce different code generation results.
- Distinguish `processingOver()` and `errorRaised()`; do not create new sources during the final round.
- Handle empty `annotations`, empty `getRootElements()`, and non-matching annotations normally.
- Consider `return true`/`false` according to the annotation-claiming contract; universal validator processors should not accidentally claim all annotations.
- Avoid scanning global mutable state or reading arbitrary environment settings if reproducible builds are desired.
- Add integration tests verifying generated sources/classes and compile status on the target toolchain.
- Avoid making diagnostic text the processor's API; if a machine-readable report is needed, generate a separate tool-controlled schema/artifact.

When a processor has multiple versions or coordinates with other processors, record the processor version and corresponding dependency sources. Seeing processing rounds does not guarantee generated code is semantically correct; generated classes should also be tested.

## 14. Practice Exercises

**Exercise A — observe rounds.** Run the exact section 5 lab with `-XprintRounds`. Point out the first round containing `Example`, the next round containing `Generated`, and the final round marked `processingOver()`. Exact log line counts are not the goal.

**Exercise B — try disabling processing.** Use empty output and replace the Step B option with `-proc:none`, while also removing `-processor` to avoid conflicting configuration. The program will lack `Generated` if no old file supplies that class; explain the compile error.

**Exercise C — wrong supported annotation.** In the processor, change `@SupportedAnnotationTypes("demo.Mark")` to a name absent from inputs, recompile the processor, and run the lab. Observe how matching/selection changes. Restore the name before trying further.

**Exercise D — service discovery.** Remove `-processor` from command B, package the processor with the proper `META-INF/services/javax.annotation.processing.Processor` file, and configure the processor path explicitly. Compare with specifying the processor directly. Do not assume JDK defaults.

**Exercise E — add source created by the processor.** Edit the processor to generate `Generated.java` only when `@Mark` is present; then place `@Mark` on another class. Observe the new generated artifact from the first round, the class being compiled, and application stdout.

**Exercise F — duplicate file.** Intentionally write a processor that creates `demo.Generated` twice in one compilation to observe `FilerException`. Try only on the demo project; then fix by ensuring each name is created at most once.

**Exercise G — CI verification.** Besides checking build success, verify `build/generated/demo/Generated.java` and `build/classes/demo/Generated.class` in clean output. That is easier-to-automate evidence than `Round 1` line counts in stderr.

## 15. Checklist When a Processor Is Not Invoked

1. `javac -version` and the task's actual JDK have been identified.
2. There is an explicit annotation processing config/request, especially with JDK 23+.
3. No accidental `-proc:none`.
4. The processor class and its dependencies can be loaded from the right processor path/module path.
5. Exact `-processor` or proper service registration/module provides exists.
6. `@SupportedAnnotationTypes` matches the fully qualified annotation appearing in code.
7. No other processor claims the annotations this processor needs.
8. `-XprintRounds`/`-XprintProcessorInfo` enabled during diagnostics.
9. `process` or `init` has diagnostics sufficient to prove lifecycle, rather than merely checking class presence.
10. `Filer` creates the right source/resource without creating duplicates.
11. `-s`/`-d` and compiled generated classes are verified in fresh output.
12. The build tool does not skip the compiler task due to cache/incremental logic.
13. Source/annotation version, module path, and compiler plugin match.
14. Build is verified by exit status, generated artifacts, and behavior tests, without depending on log formatting.

## 16. Conclusion and Authoritative References

Annotation processing is a process **with discovery, selection, multiple rounds, and separate outputs**. When a "processor does not run", the best questions to ask are: **is processing enabled; is the processor found; does the annotation match and enter a round; does the processor actually generate files; is that file compiled and used via the right path?**

Use `-processor`/processor path to control dependencies; use `-XprintRounds` and `-XprintProcessorInfo` to observe; use `RoundEnvironment` and `Messager` to understand the current round; use `Filer` per contract to generate files; and verify clean output when investigating.

Authoritative references:

- [JDK 21 javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-XprintRounds`, `-XprintProcessorInfo`, `-proc`.
- [Processor API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html): discovery, annotation claiming, and lifecycle order.
- [RoundEnvironment API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): roots, errorRaised, and processingOver.
- [Filer API JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Filer.html): how to create files and overwrite-prevention limits.
- [Inside Java: JDK 23 annotation processing change](https://inside.java/2024/06/18/quality-heads-up/): default change and `-proc:full`.