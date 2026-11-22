# Tracking Annotation Processing Rounds with `-XprintRounds` and `-XprintProcessorInfo`

In Java, an annotation processor runs **at compile time**, can be invoked across multiple *processing rounds*, and can generate new sources/classes for the compiler to process in the next round. When a build produces missing or duplicate files, a processor is not invoked, or logs differ from expectations, two diagnostic options of `javac` are particularly useful:

- **`-XprintRounds`**: prints information about annotation processing rounds, including the initial round and subsequent rounds.
- **`-XprintProcessorInfo`**: prints information about **which annotation types a processor is asked to process**.

These are two **`javac` compiler options**, not Java annotations, not application-defined options, and not a runtime API. They help observe compiler behavior **without modifying the processor code just to add `System.out.println` statements**. They do not replace error handling, testing, or emitting diagnostics via `Messager`.

## 1. Why Do You Need to See Each Processing Round?

An annotation processing run is not required to consist of only a single call to `process(...)`. If a processor creates a new source file, the compiler can read that file in the **next round**. Each round has its own inputs, its own set of annotations, and its own completion status.

A typical sequence:

```text
javac receives Source.java
        |
        v
Round 1: processes Source.java
        |     Processor generates GeneratedA.java
        v
Round 2: processes GeneratedA.java
        |     No additional Java source/class generated
        v
Final round: processingOver() == true
        |
        v
Annotation processing ends
```

When `-XprintRounds` is enabled, developers can answer the following questions:

1. Does the compiler actually start annotation processing?
2. How many rounds have occurred?
3. In each round, which input sources/types does the compiler record?
4. Which annotations are present in the round?
5. Which round is the final round (*last round*)?
6. Is a generated source passed to the next round?

When **both** options are enabled, you can also view information about which annotations a processor is assigned to process and, depending on the JDK version, information related to the processor **claiming** annotations.

Note: the lines displayed by `-XprintRounds` are **compiler logs**, not application data printed when running with the `java` command.

## 2. How Are the Two Options Similar and Different?

| Option | Primary Observation | Useful Questions |
| --- | --- | --- |
| `-XprintRounds` | Annotation processing rounds: input files, annotations, last-round status. | “Why are there three rounds? Does the generated source appear in round two?” |
| `-XprintProcessorInfo` | Which processor is asked to process which annotation types. | “Was the processor selected/invoked for `@TraceTag`?” |
| Using **both** | View by **round** and by **processor**. | “In round two, which markers does the compiler see and which processor does it assign them to?” |

The syntax consists of **two independent tokens**, with exact spelling and capitalization:

```bash
javac -XprintRounds -XprintProcessorInfo ...
```

Do not write `@XprintRounds`, `--XprintRounds`, `-XprintRound`, or pass them as program options via `java`.

These two options belong to the `-X` group of **`javac`**. You can check the options supported by the JDK in use with:

```bash
javac -X
```

The `-X` list can differ across JDKs. For the diagnostic results to be meaningful, verify that you are running the **exact `javac` of the build toolchain**, not just the `java` used when running the application.

## 3. How to Read Information from `-XprintRounds`

An **illustrative log excerpt following the familiar OpenJDK `javac` format**:

```text
Round 1:
    input files: {Input}
    annotations: [TraceTag]
    last round: false
Round 2:
    input files: {GeneratedInput}
    annotations: [TraceTag]
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
```

The lines above depict a case where a processor generates `GeneratedInput.java` in round one. **This is an example illustrating the information, not a byte-for-byte guarantee across all JDK builds**: delimiters, ordering, type names, formatting, or the presence of additional lines may vary depending on the version and context.

Key fields:

- **`Round N`**: the sequence number of the annotation processing round within the current compilation run.
- **`input files`**: the input roots/types reported by the compiler for that round; not synonymous with all source files in the repository.
- **`annotations`**: the **annotation types** present in the inputs detected in the round; not a list of annotation element values or runtime objects.
- **`last round: false`**: a normal processing round. The processor can analyze and generate new sources/classes.
- **`last round: true`**: the final round to conclude processing. Semantically corresponds to `RoundEnvironment.processingOver()`.

**The number of rounds is not a constant.** A processor that only analyzes without generating files may result in just one normal round plus the final round. If multiple processors continue generating files in subsequent rounds, the number of normal rounds can increase. When build errors occur, the progression may also differ from an error-free example.

Do not assume that seeing `last round: true` means compilation **succeeded**: processing can end after the compiler/processor has produced errors.

## 4. How to Read `-XprintProcessorInfo`

This option answers “**which processor is asked to process which annotation types?**”, does not answer “which files did the processor create?”, and does not prove that the processor processed the logic correctly.

A common form of `javac` output, used as an **illustration**:

```text
Processor TraceProcessor matches [TraceTag] and returns true.
```

Meaning of the components:

- `TraceProcessor`: the specific processor that the compiler selected/invoked.
- `matches [TraceTag]`: the annotation type that the compiler assigned to the processor at that step.
- `returns true`: when this format is printed, indicates the return value of `process` in the reported processing call. **`true` means the processor claims the assigned annotation types, not that the build succeeded.**

Information to understand accurately:

1. `@SupportedAnnotationTypes(...)` only **declares** the scope that the processor supports; that does not mean the processor will be called for every annotation in the project.
2. The set of assigned annotations depends on **the current round, processor selection, and claims by earlier processors**.
3. If `process(...)` returns `false`, the processor does not claim the assigned annotations, so they can still be processed by another processor.
4. If there are no matching annotations, the processor is not found, or annotation processing is disabled, the corresponding line may not appear.
5. Seeing a processor printed in the log does not guarantee that it called `Filer`, created sources, or reported errors in the right place.

**Do not use `-XprintProcessorInfo` as an execution-time profiler or complexity counter.** It is a processor selection/assignment diagnostic. To know exactly which files a processor generates, inspect the output directory, diagnostics, or appropriate instrumentation.

## 5. Complete Java 17+ Example: Enabling Both Options

This example has **three Java files created by the learner**. The processor will automatically generate a **fourth Java file** during compilation, allowing us to clearly see multiple rounds. No Maven, Gradle, or libraries outside the JDK are needed.

Goal:

- A class `Input` with `@TraceTag`.
- `TraceProcessor`, explicitly specified via `-processor`, receives `@TraceTag`.
- In the first round, the processor creates `GeneratedInput.java`, which also carries `@TraceTag`.
- In the next round, the compiler processes the new source, but the processor **does not create any additional files**.
- Finally, there is a final round, where the processor generates no sources.

### File 1 — `TraceTag.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface TraceTag {
}
```

The annotation has `SOURCE` retention because the processor needs the metadata during **compilation**, without needing to query it at runtime.

### File 2 — `TraceProcessor.java`

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("TraceTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TraceProcessor extends AbstractProcessor {
    private boolean generated = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (Element element : round.getElementsAnnotatedWith(TraceTag.class)) {
            if (element.getKind() != ElementKind.CLASS || generated) {
                continue;
            }

            generated = true;
            try {
                JavaFileObject output = processingEnv.getFiler()
                        .createSourceFile("GeneratedInput", element);

                try (Writer writer = output.openWriter()) {
                    writer.write(
                            "@TraceTag\n"
                            + "public final class GeneratedInput {\n"
                            + "}\n"
                    );
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate source: " + ex.getMessage(),
                        element
                );
            }
        }

        return true;
    }
}
```

Explanation of key details:

- `@SupportedAnnotationTypes("TraceTag")` matches the annotation's name in the **default package**, solely so the example is easy to run. In real projects, use an explicit package and the **fully qualified** annotation name.
- `@SupportedSourceVersion(RELEASE_17)` declares the source level supported by the processor; it can be updated appropriately when upgrading the toolchain.
- `round.getElementsAnnotatedWith(TraceTag.class)` finds elements carrying `@TraceTag` in the current round. The processor can reference `TraceTag.class` because the annotation type is compiled and present on the processor path.
- `generated` is instance state that prevents creating `GeneratedInput` a second time. `Filer` does not allow creating duplicate copies of the same source in a single processing run.
- `createSourceFile("GeneratedInput", element)` informs Filer of the originating element. The generated source becomes input for the next round, not a new element inserted directly into the `RoundEnvironment` of the current `process` call.
- `processingOver()` is checked before generating files: the final round does not open another annotation processing round to process newly generated files.
- `return true` is a **claim** on the assigned annotations, not a success code for the file write operation.
- When an I/O error occurs, the processor reports an `ERROR` diagnostic instead of swallowing the exception. The compiler can halt the build according to its error-handling flow.

The processor **does not call `System.out.println`**. As a result, the lines displayed by the two `-X` flags will be easily recognized as **javac diagnostics** rather than output printed by the application itself.

### File 3 — `Input.java`

```java
@TraceTag
public class Input {
}
```

This class serves only as input so that the processor can find the marker. No `main` method is needed because the example tests **compile time**, not running an application.

### Commands to Run on Linux/macOS or Bash

Open a terminal in the directory containing the three files just created. To run again from scratch, use a new/empty output directory.

```bash
mkdir -p build generated

javac -encoding UTF-8 -proc:none -d build TraceTag.java TraceProcessor.java

javac -encoding UTF-8 \
    -cp build \
    -processorpath build \
    -processor TraceProcessor \
    -proc:only \
    -s generated \
    -XprintRounds \
    -XprintProcessorInfo \
    Input.java
```

If you are using **PowerShell**, you can create the directories with:

```powershell
New-Item -ItemType Directory -Force build, generated | Out-Null
```

And write the second `javac` command on **one line** to avoid relying on Bash line-continuation characters:

```powershell
javac -encoding UTF-8 -cp build -processorpath build -processor TraceProcessor -proc:only -s generated -XprintRounds -XprintProcessorInfo Input.java
```

The first compilation command uses `-proc:none` to **compile `TraceTag` and `TraceProcessor` into `.class` files first**, without running annotation processors in this step. Only the second command explicitly runs the processor. This two-step approach eliminates the confusion of “why does `javac` have to invoke the processor before it even exists?”.

Meaning of the options in the second command:

| Option | Purpose |
| --- | --- |
| `-cp build` | Allows the compiler to see the compiled annotation type and supporting classes. |
| `-processorpath build` | Specifies the path to locate annotation processor classes. |
| `-processor TraceProcessor` | Selects the exact processor to run, without relying on service discovery. |
| `-proc:only` | Runs annotation processing, **without proceeding to compile application classes**. |
| `-s generated` | Selects the directory to store `.java` files emitted by the processor. |
| `-XprintRounds` | Prints information for each round. |
| `-XprintProcessorInfo` | Prints processor selection/assignment information. |
| `Input.java` | The initial source containing `@TraceTag`. |

After the second command, the `generated` directory typically contains:

```text
generated/
└── GeneratedInput.java
```

Because `-proc:only` is used, do not expect this command to produce `Input.class` or `GeneratedInput.class`. If you want to proceed with compilation as a normal application, replace `-proc:only` with an appropriate processing **and** compilation mode (for example, specifying the processor explicitly and omitting `-proc:only`).

## 6. Reading the Example Output Round by Round

With JDK 17 following `javac` conventions, the log may show **three rounds** in roughly the following form (format illustration only; do not treat it as exact, immutable stdout):

```text
Round 1:
    input files: {Input}
    annotations: [TraceTag]
    last round: false
Processor TraceProcessor matches [TraceTag] and returns true.
Round 2:
    input files: {GeneratedInput}
    annotations: [TraceTag]
    last round: false
Processor TraceProcessor matches [TraceTag] and returns true.
Round 3:
    input files: {}
    annotations: []
    last round: true
```

Do not turn the spaces, line ordering, or exact `Set` representation spelling above into rigid snapshot tests across multiple JDKs. **Verify meaningful invariants**:

1. **Round 1** sees `Input` carrying `@TraceTag`, and the processor is assigned that annotation type.
2. The processor creates `GeneratedInput.java` once.
3. **Round 2** sees `GeneratedInput` with `@TraceTag`, which indicates that the newly generated file has become an input for the next round.
4. In round two, no new source is created because the `generated` variable has already become `true`.
5. The **final round** has `last round: true`. This signals the end of the annotation processing lifecycle; it must not be interpreted as a round that can arbitrarily generate more sources and expect a next round.

In addition to the lines emitted by the two options, `javac` may display extra warnings/errors if there are issues with the compiler, source code, or environment. If `-Xlint` or other options are used, the line count and ordering may also change.

To compare differences, run the same command enabling only one flag at a time:

```bash
javac -encoding UTF-8 -cp build -processorpath build \
  -processor TraceProcessor -proc:only -s generated -XprintRounds Input.java
```

**Remember to delete or change the output directory** `generated` if you want to verify file generation cleanly. `Filer` calls can overwrite a file from a previous compiler invocation depending on output location rules, but within a single processing run **the same file still cannot be created repeatedly**. To avoid stale sources affecting diagnostics, always inspect the output directory and compiler inputs.

Comparing the value of the two flags: `-XprintRounds` shows **the data journey across rounds**, while `-XprintProcessorInfo` shows **the assignment of annotations to processors**. When you need to reproduce a bug, enable both and preserve the log along with the JDK version, command line, and error messages.

## 7. Distinguishing from `-Xprint`, `-proc:only`, and `-proc:none`

The names look quite similar, but their functions differ:

| Option | Meaning |
| --- | --- |
| `-XprintRounds` | Prints information about annotation processing rounds. |
| `-XprintProcessorInfo` | Prints information about which annotations a processor is asked to process. |
| `-Xprint` | Prints a textual representation of types via the tool, **without performing normal annotation processing/compilation**; this is not a flag to enable round tracing. |
| `-proc:only` | Annotation processing only, without performing the subsequent compilation step; very convenient when verifying a processor. |
| `-proc:none` | Disables annotation processing for that invocation. |
| `-processor` | Specifies which processor classes to run. |
| `-processorpath` | Specifies where to locate processors when using classpath-style processor loading. |

A command such as:

```bash
javac -proc:none -XprintRounds Input.java
```

cannot be used to prove that a processor is active, because `-proc:none` **disables** annotation processing. Do not conclude “the trace flag is broken” when the invocation itself disabled the feature being observed.

Conversely:

```bash
javac -processor TraceProcessor \
  -cp build -processorpath build \
  -proc:only -XprintRounds -XprintProcessorInfo Input.java
```

explicitly enables processing and provides suitable input, so there is a basis for displaying logs. If the processor is configured invalidly, the compiler may report an error before reaching any round.

`-XprintRounds` and `-XprintProcessorInfo` only apply to **`javac`**; the command `java -XprintRounds Input` does not run annotation processors and is not an equivalent syntax.

## 8. Correlating Logs with `RoundEnvironment`

The two `-X` flags provide a view **from outside the processor**. When you need to determine file-generation conditions or complex internal state, you can combine them with the standard API:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment round) {
    boolean finalRound = round.processingOver();
    boolean priorError = round.errorRaised();

    // ... process according to the processor's needs ...
    return true;
}
```

This is an illustrative snippet meant to be placed inside a processor class, not a standalone program. The corresponding APIs:

| Data in Log | Related API/Model |
| --- | --- |
| `last round: true` | `RoundEnvironment.processingOver()` |
| `input files: {...}` | The round's root set: `RoundEnvironment.getRootElements()` (not a guarantee of identical printed strings). |
| `annotations: [...]` | Annotations appearing in the round, along with the matching/assignment of annotation types to the processor. |
| Processor receives annotation types | The `Set<? extends TypeElement> annotations` parameter in `process(...)`, following the processor selection rules of the tool. |
| Processor `returns true` | The return value of `process`: **claim**, not the exit code of `javac`. |

`RoundEnvironment.errorRaised()` indicates that an `ERROR` occurred in the **previous round**; it should not be used as an immediate indicator for the round currently being processed. `getRootElements()` returns the roots of the corresponding round; it must not be treated as a snapshot of every class in the entire project.

If you want to know **exactly why** the generator creates a file in a particular round, you can add `Messager`:

```java
processingEnv.getMessager().printMessage(
    javax.tools.Diagnostic.Kind.NOTE,
    "Generating source from @TraceTag"
);
```

This snippet illustrates code inside a processor. `Messager` is appropriate for compiler-attached messages; a processor's `System.out` logs and `-X` option logs should only be used for diagnostics when needed, not as an application contract.

## 9. Common Observations When Enabling Both Flags

### Seeing Only Round 1 and the Final Round

The processor may **not have generated new sources/classes**, or there are no files left to process next. That alone does not indicate the processor is wrong: a processor that only validates annotations typically does not need to create files.

If source generation was expected, check the conditions for calling `Filer`, `ERROR` messages, output names, the `-s` directory, and whether the processor was assigned the expected annotations.

### Seeing Many Consecutive Rounds

If a new source file appears in every round, check whether the processor is **generating output repeatedly without a termination condition**. A common bug is generating `Generated1`, then encountering `Generated1` and generating `Generated2`, and then continuing to generate `Generated3` endlessly.

Ways to control this:
- Maintain a set of already-processed names **inside the processor instance** for a compiler invocation.
- Do not regenerate the same file across multiple rounds.
- Do not create additional output if the generated source is already the desired final result.
- Let the trace pinpoint which new source triggered the next round.

### Round 1 Appears, but `-XprintProcessorInfo` Does Not Show the Expected Processor

Possibilities to check:

1. **Discovery/path**: is the processor compiled, present on the processor path, and using the correct class name?
2. **Processor selection**: is `-processor` specified? If so, is the list correct? If relying on service discovery, is the `META-INF/services/javax.annotation.processing.Processor` file valid?
3. **Supported annotations**: does `@SupportedAnnotationTypes` specify the correct fully qualified name and the right annotation types to process?
4. **Claim**: an earlier processor may have already claimed that annotation in the same round.
5. **Source level**: is `@SupportedSourceVersion` compatible with the version of the source code/toolchain?
6. **Input and target**: is the input actually annotated at a location permitted by `@Target`?
7. **Invocation mode**: is processing disabled by `-proc:none` or by the build configuration?

Do not try to debug inside `process(...)` before knowing whether the compiler actually **selected and invoked** the processor.

### `-XprintProcessorInfo` Appears, but No Files Are Generated

This also does not prove that the compiler is malfunctioning. The invoked processor might only perform validation, its file-generation conditions might not be met, or it might have emitted an error. The `matches` indication is not a count of generated files.

### Logs Differ Between CLI and IDE/Build Plugins

Maven/Gradle/IDEs may:

- Use a different JDK or compiler than the terminal.
- Separate the processor path/classpath according to their own configuration.
- Run incremental compilation, resulting in a different number of roots/rounds.
- Filter, aggregate, or change where compiler output is displayed.
- Use a compiler implementation that is not completely identical to CLI `javac`.

To isolate the issue, prioritize running a direct `javac` command with minimal input and processor, enable both options, save all compiler messages, and only then bring the equivalent configuration back to the build tool.

## 10. Working with Maven, Gradle, and CI

The options belong to the **compiler**, not the JVM. When configuring a build tool, you must pass them to the actual **`javac` invocation** that the tool uses. The mechanism for passing options can vary across plugin/build-tool versions, so you should not treat a configuration snippet for a specific version as universal Java syntax.

Useful principles:

1. Identify the JDK toolchain and `javac` version that the build uses.
2. Identify the processor path / processor module path, not just runtime dependencies.
3. Pass `-XprintRounds` and `-XprintProcessorInfo` into **compiler arguments** (where the plugin allows), rather than putting them in `JAVA_TOOL_OPTIONS` as if they were JVM options.
4. Test with a clean build when investigating round counts to avoid interference from stale/incremental outputs.
5. Attach tracing to diagnostic debug/CI sessions instead of forcing every normal build to print overly verbose logs.
6. If comparing across JDKs, prioritize logical events (processor selected, generated source present, final round reached) rather than full-text snapshots.

For example, in a shell, if you want to keep both stdout and stderr for analysis:

```bash
javac -cp build -processorpath build -processor TraceProcessor \
  -proc:only -s generated -XprintRounds -XprintProcessorInfo \
  Input.java > processing.log 2>&1
```

`2>&1` is a common shell redirection syntax, not a `javac` flag. After running, check the compiler's **exit code** and read the log; having round logs does not guarantee that the command exited with code `0`.

If you need to trace exact per-round data in a way more stable than the `-X` log format, you can implement checks using `RoundEnvironment` and record structured values controlled by the processor itself. However, tests must also avoid depending on a fixed round count when multiple processors participate in the build.

## 11. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| These two flags must be placed after the `java` keyword | They are **`javac`** options, not the command to run an application. |
| `-XprintRounds` prints annotation element values | It prints **processing round information**, not the values of individual `@Annotation(...)` instances. |
| `-XprintProcessorInfo` prints every processor on the classpath | It focuses on processors **asked to process annotations**; unselected processors do not necessarily appear. |
| Seeing `returns true` means compilation succeeded | Here `true` means **claiming** the annotations; build success requires checking errors and the exit code. |
| Seeing `last round: true` means all class compilation steps are complete | The final processing round does not mean compilation is complete; `-proc:only` even skips the subsequent compilation step. |
| You must add `@Retention(RUNTIME)` to read an annotation in a processor | `SOURCE` is sufficient for annotation processing during compilation. |
| `-proc:none -XprintRounds` should still print rounds | `-proc:none` **disables** annotation processing, so there is no round flow to trace. |
| `-Xprint` is simply a shorthand for `-XprintRounds` | **No**: the two options serve completely different purposes. |
| Seeing generated files means the processor was invoked in all rounds | A processor may be invoked differently depending on selection/claim state and inputs. |
| Round logs have identical text across all JDKs | Formatting and specific details may vary; check semantics instead of raw-string equality. |
| Seeing one `process` call means `init` is also called every round | `init` initializes the processor before processing; `process` can be called across multiple rounds. |
| Multiple processors always have the exact same ordering and annotation sets across every build | They depend on selection, claims, the toolchain, and sources generated across rounds. |
| `-XprintProcessorInfo` is enough to confirm correct output | It only shows which annotations were assigned to a processor, not whether generated files have the right contents. |

## 12. Self-Check Exercises

Suppose the compiler reports:

```text
Round 1: Input / @TraceTag / last=false
Round 2: GeneratedInput / @TraceTag / last=false
Round 3: {} / [] / last=true
```

This is **a shorthand notation for reasoning**, not the verbatim `javac` format.

1. Why is there a second round? **Because there is a new input** (`GeneratedInput`) created by the processor in the first round.
2. Which flag lets you see the sequence of three rounds? **`-XprintRounds`**.
3. Which flag indicates which annotation types a processor was assigned? **`-XprintProcessorInfo`**.
4. Which method does `last=true` correspond to? **`RoundEnvironment.processingOver()`**.
5. What does `returns true` from `process` mean? **The processor claims the assigned annotation types**; it does not prove that the logic succeeded.
6. Must a processor that only inspects sources and creates no new files necessarily have three rounds like the example? **No**.
7. Does `-proc:only` emit `Input.class` like a full build? **No**.
8. If you want to debug “processor not appearing in the log”, what should you check first? **Processor path, processor name, supported annotation types, processing mode, and input**.
9. If `@TraceTag` has `RetentionPolicy.SOURCE`, can the processor read it? **Yes**, because this happens at compile time.
10. If after the log is produced the compiler reports an ERROR, can the build be considered successful? **No**; you must check the diagnostics and exit code.
11. Why should you not snapshot the entire `-XprintRounds` output as a cross-JDK test? **Because the text is an implementation diagnostic, not a stable data protocol**.
12. In what situation are both flags needed? **When you want to know both which files/annotations entered which round and whether the processor was assigned to process those annotations**.

## 13. References

- [Oracle Java SE 17 — The `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html), the Extra Options (`-XprintRounds`, `-XprintProcessorInfo`) and Annotation Processing sections.
- [Oracle Java SE 21 — The `javac` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), along with options for comparing against newer JDK toolchains.
- [Java SE 17 — `javax.annotation.processing.Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html), rules for assigning annotation types to a processor, claiming, and processing rounds.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html), especially `processingOver()`, `getRootElements()`, and `errorRaised()`.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html), creating new sources for the compiler to process in subsequent rounds.
