# processingOver(), errorRaised(), and the Final Processing Round in Java Annotation Processing

## 1. Context: Annotation Processors Are Invoked Across Multiple Rounds

In the **Java Annotation Processing API** (JSR 269), an annotation processor is not necessarily invoked only once per `javac` command. The compiler may invoke the `Processor.process(...)` method across **multiple processing rounds**, especially when the processor generates additional Java or class files. The relevant APIs are available in the standard **`java.compiler`** module, **`javax.annotation.processing`** package of Java SE, with no third-party libraries required.

Common `process` signature when extending `AbstractProcessor`:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Read elements in the current round and optionally generate files.
    return true;
}
```

Where:

- `annotations`: the set of **annotation types** requested by the tool for the processor to handle in the current invocation; this set may be **empty**, especially in the final round.
- `roundEnv`: the **`RoundEnvironment`** object describing a round. It indicates whether the round is the final round, whether an error was raised in the previous round, and the source/class elements relevant to this round.
- The boolean return value of `process`: `true` **claims** the assigned annotation types; `false` leaves them unclaimed so other processors can handle them. **This is not a "more rounds remaining" or "compilation succeeded" flag.**

A typical workflow:

```text
javac command with initial source files
    |
    v
Round 1: process roots from input
    |  Processor may use Filer to generate new source files
    v
Round 2: process roots generated from the previous round
    |  No new files need further processing
    v
Final round: processingOver() == true
    |  Cleanup/aggregation; do not expect a new processing round
    v
Annotation processing completes
```

The number of rounds usually depends on newly generated files, activated processors, errors, and tool behavior. **Do not hard-code** "there are always three rounds" or "round 2 is always the final round".

## 2. Two Key Methods of RoundEnvironment

`RoundEnvironment` provides two boolean methods that are frequently confused:

| Method | Actual question answered | When is it typically true? | What must NOT be inferred |
| --- | --- | --- | --- |
| `processingOver()` | Will types generated in **this round** still be passed to a subsequent annotation processing round? | In the final processing round | Does not imply an error occurred or compilation succeeded |
| `errorRaised()` | Was an error reported in the **previous processing round**? | The round following a round that had an error diagnostic | Does not immediately reflect an error just reported in the current round itself |

According to the Java SE 17 documentation:

- `processingOver()` **returns `true` if the types generated in the current round will no longer be processed in a subsequent annotation processing round**.
- `errorRaised()` **returns `true` if an error was raised in the previous processing round**, and `false` otherwise.

Both are **per-round** states, not properties of individual annotations, individual files, or an automatic counter. There is no requirement that `processingOver() == true` implies `errorRaised() == true`. A normal successful run has a final round with `processingOver() == true` and `errorRaised() == false`.

### 2.1. Reading State with the Right API

```java
if (roundEnv.processingOver()) {
    // Final round: handle completion appropriately.
    return true;
}

if (roundEnv.errorRaised()) {
    // An error diagnostic was reported from the previous round.
    // Depending on business logic, avoid further output generation operations.
}
```

The snippet above is only a logic pattern inside `process`, not a standalone Java program. **There is no need to check `errorRaised()` to determine the final round**; use `processingOver()` for that purpose.

### 2.2. errorRaised Is Not an Error Check for the Current Round

Suppose a processor calls:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Cấu hình không hợp lệ");
```

This call **reports an error diagnostic**. However, the `RoundEnvironment` object for the **currently running round** does not immediately change `errorRaised()` to `true` as a result. Java specifies `errorRaised()` as a flag indicating the error status of the **previous round**.

Therefore, the correct interpretation is:

```text
Round N:
  errorRaised() = false
  Processor reports Diagnostic.Kind.ERROR
  Processors in round N may still continue to be invoked

Next round:
  errorRaised() = true
  This round may be the final round
```

If the processor itself has already identified an invalid configuration in the current round, **record the error in the processor's own state when needed** or stop the parts of work that are no longer appropriate; do not wait for `roundEnv.errorRaised()` to change its value within that same round.

## 3. The Final Processing Round: processingOver() == true

The **final round (last/final round)** is still a `process` invocation under the annotation processing contract. If a processor was asked to process in an earlier round, it will continue to be invoked in subsequent rounds, **including the final round**, even when no annotation types are assigned to it.

A typical pattern:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Finalize statistics or clean up state.
        return true;
    }

    // Process elements of a normal round.
    return true;
}
```

**Reasonable tasks in the final round:**

- Summarize the count of elements processed in previous rounds.
- Inspect the internal state of the processor and report results.
- Emit final error/warning diagnostics when needed.
- Release temporary data in the processor.
- Finalize aggregated data according to the designed output contract, such as auxiliary resources, with a clear understanding of Filer and the build environment.

**Things to avoid in the final round:**

- Generating **new source/class files expecting them to be processed by an annotation processor in a subsequent round**. `processingOver() == true` explicitly states that **there is no subsequent round to process types generated in this round**.
- Using the final round to generate a source type that needs to trigger generation of further source types.
- Assuming the `annotations` set or `getRootElements()` always contains data in the final round.
- Starting a file-generation chain that cannot yet be completed.
- Assuming that calling `process` in the final round is an error or that the processor is given a new instance.

**Filer note:** `Filer` is the API for generating source, class, and resource files. Source/class files generated and whose streams are closed during a normal round are examined in the next round. In the final round, **do not generate source/class files expecting further processing**; some tools such as `javac` may warn that files generated in the final round will not be subject to annotation processing. If the design requires creating an **aggregated resource**, choose an appropriate final timing, handle I/O errors, and ensure it does not depend on a new processing round.

### 3.1. The Final Round Does Not Mean "Error-Free"

Two states may occur:

```text
FINAL: processingOver=true, errorRaised=false  // Normal completion
FINAL: processingOver=true, errorRaised=true   // Error reported in a previous round
```

If `errorRaised()` is `true` in the final round, the processor should consider **not publishing an aggregated artifact deemed valid**, because an earlier step has already reported an error. However, it can still print statistics for diagnostic purposes; the handling policy depends on the processor's purpose.

If `errorRaised()` is `false` in the final round, **it should also not be inferred as independent proof that all subsequent compilation/packaging steps succeeded**. The flag reflects errors from the previous round in annotation processing, not the exit code of the entire build pipeline.

## 4. Rounds That Typically Occur When Using Filer

When a processor calls:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("generated.Example");
```

and closes the `Writer`/output stream used to write the file, the annotation processing tool can pass the newly created type into the **next processing round**. New rounds are not caused by the processor calling `process` recursively; they are managed by compiler orchestration.

What typically happens:

1. **Initial round**: the roots corresponding to the input source files are examined; the processor sees the annotations that need handling.
2. **Generated round**: source/class files generated by the previous round become eligible roots, and the processor can process annotations present on those files.
3. **Final round**: no new types remain to be processed; `processingOver()` becomes `true`.

A useful detail in `RoundEnvironment` is `getRootElements()`: it returns the **root elements corresponding to the output of the previous round**. For the first round, the initial inputs are treated as the output of a hypothetical "round 0". Roots do not necessarily consist only of classes; depending on the inputs, they may also include packages or modules.

**Do not infer the number of rounds solely from the number of annotations:** a processor can handle multiple annotations within the same round. Conversely, a single annotation type may appear across multiple rounds if new types are generated.

### 4.1. The Processor Is Re-invoked, Not Re-instantiated Each Round

The tool typically instantiates a processor (public no-arg constructor), calls `init`, and then invokes `process` for the relevant rounds on the **same processor object** for that compilation run. This allows keeping counters or aggregated data in instance fields:

```java
private int normalRounds;
private boolean generated;
```

These fields represent **state for a single processing run of the processor** and must not be understood as persistent storage across multiple `javac` invocations. A compiler may run inside an IDE or build daemon in its own way; do not rely on static state or global state as a contract across multiple builds.

## 5. Complete Java 17+ Example: Two Normal Rounds and a Final Round

The following example consists of **three Java files** with no external library dependencies. An annotation processor generates an additional file `GeneratedGreeting.java` in the first round, causing the compiler to run one more normal processing round before invoking the final round.

Use JDK 17 or later with `--release 17` so that the example has consistent Java 17 source semantics even if the machine is running a newer JDK.

### 5.1. The DemoTag.java File

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface DemoTag {}
```

`DemoTag` does not require `RUNTIME` retention: an annotation processor **reads structure during compilation**, not via runtime reflection. Because `@Retention` is not declared, the annotation's default retention policy is `CLASS`; this does not prevent the processor from finding the annotation in source code.

### 5.2. The Demo.java File

```java
@DemoTag
class Demo {}
```

`Demo` is the initial type annotated with `DemoTag`, giving the processor an annotation type to handle.

### 5.3. The RoundLifecycleProcessor.java File

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("DemoTag")
@SupportedOptions("fail")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundLifecycleProcessor extends AbstractProcessor {
    private int normalRounds;
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            System.out.println("FINAL processingOver=" + roundEnv.processingOver()
                    + " errorRaised=" + roundEnv.errorRaised());
            return true;
        }

        normalRounds++;
        Set<? extends Element> targets =
                roundEnv.getElementsAnnotatedWith(DemoTag.class);
        System.out.println("ROUND " + normalRounds
                + " processingOver=" + roundEnv.processingOver()
                + " errorRaised=" + roundEnv.errorRaised()
                + " targets=" + targets.size());

        if ("true".equals(processingEnv.getOptions().get("fail"))) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "simulated error");
            return true;
        }

        if (!generated) {
            generated = true;
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("GeneratedGreeting").openWriter()) {
                writer.write("@DemoTag class GeneratedGreeting {}\n");
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, e.getMessage());
            }
        }
        return true;
    }
}
```

**Key points in the processor:**

- `@SupportedAnnotationTypes("DemoTag")` declares the annotation type supported by the processor. Using a name in the default package is only for demonstration purposes; real projects should use an explicit package.
- `@SupportedSourceVersion(RELEASE_17)` declares the language version supported by the processor; depending on the build environment, another appropriate version can be chosen.
- `@SupportedOptions("fail")` declares the `-Afail=true` option to demonstrate a controlled error scenario in section 6.
- The final round is detected **before** incrementing the counter or calling `Filer`; the `processingOver()` branch only summarizes.
- In a normal round, `getElementsAnnotatedWith(DemoTag.class)` retrieves the roots/elements annotated with `@DemoTag` within the scope of the current round.
- `generated` prevents the processor from re-creating the same `GeneratedGreeting` file in a later round; if the same pathname is created again, `Filer` may throw a `FilerException`.
- The source-writing line uses `\n` in the Java string to produce a single newline character in the generated file, rather than the two characters `\` and `n`.
- `return true` **claims the annotation type**, rather than stopping the annotation processing pipeline.

### 5.4. Commands to Compile and Run the Processor

Create the three files in the **same empty directory**. Open a terminal in that directory. For example, in a shell that supports `mkdir -p`:

```bash
mkdir -p build generated

javac --release 17 -d build DemoTag.java RoundLifecycleProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor RoundLifecycleProcessor \
  -d build -s generated Demo.java
```

In PowerShell, you can create the directories with `New-Item -ItemType Directory -Force build, generated` and then write the `javac` command on a single line; the line-continuation character `\` in the `bash` block is **not** PowerShell's line-continuation syntax.

Meaning of the flags:

| Flag | Purpose |
| --- | --- |
| `--release 17` | Compile targeting Java 17 APIs and semantics |
| `-d build` | Write `.class` files to the `build` directory |
| `-cp build` | Make the compiled `DemoTag.class` visible to the compiler |
| `-processorpath build` | Specify where to load `RoundLifecycleProcessor.class` along with its required dependencies |
| `-processor RoundLifecycleProcessor` | Instruct the compiler to run the specific processor without relying on service discovery |
| `-s generated` | Write source files generated by the annotation processor to the `generated` directory |

With the files above, when invoking `javac` on `Demo.java`, the processor prints to stdout:

```text
ROUND 1 processingOver=false errorRaised=false targets=1
ROUND 2 processingOver=false errorRaised=false targets=1
FINAL processingOver=true errorRaised=false
```

This output was verified on JDK 21 using `--release 17`. This is **stdout printed by the processor**, not the result of running a class with `main`.

Explanation:

1. Round 1 receives `Demo` annotated with `@DemoTag`, so `targets=1`. The processor generates the new file `GeneratedGreeting.java`.
2. Round 2 receives the generated `GeneratedGreeting` type which also has `@DemoTag`, so `targets=1` again. Since `generated=true`, no further new files are generated.
3. The final round is invoked with `processingOver=true`. There were no error diagnostics from the previous round, so `errorRaised=false`.

After the build, the `GeneratedGreeting.java` file appears in `generated`. `javac` also compiles the newly generated type as part of the tool workflow, but **the number of rounds belongs to annotation processing** and should not be confused with the number of linking/packaging steps.

### 5.5. Trying -XprintRounds

You can add the `-XprintRounds` option to the second `javac` command so that the compiler prints additional information about each round. The lines printed by `javac` will appear **in addition to stdout from `System.out.println` inside the processor**; exact ordering/details depend on the tool version.

`-XprintRounds` is very useful for diagnostics because it displays the inputs, annotation sets, and round states. It is a **javac option**, not a method on `RoundEnvironment`.

## 6. Error Example: errorRaised() Appears in the Next Round

The processor in section 5 declared `@SupportedOptions("fail")`. To simulate an error, run the build command for `Demo.java` with the option:

```bash
javac --release 17 -cp build -processorpath build \
  -processor RoundLifecycleProcessor -Afail=true \
  -d build -s generated Demo.java
```

This compilation **is expected to fail**, because the processor calls `Messager.printMessage(Diagnostic.Kind.ERROR, "simulated error")`.

The **stdout lines from the processor** in this test case:

```text
ROUND 1 processingOver=false errorRaised=false targets=1
FINAL processingOver=true errorRaised=true
```

The `javac` tool also prints the error diagnostic (for example `error: simulated error`) to the diagnostic stream; display position, error count, and formatting may vary by environment. **The exit code is non-zero** because an error diagnostic was raised.

Accurate interpretation:

- When entering round 1, **there was no error from a previous round**, so `errorRaised=false`.
- The processor itself reports **an ERROR in round 1**. The value of `roundEnv.errorRaised()` in round 1 does not change immediately.
- The next round is the final round, with `processingOver=true` and `errorRaised=true`, indicating an error in the previous round.
- The error scenario intentionally **does not generate `GeneratedGreeting`**, so there is no second normal round to process new source files.

Do not define `errorRaised()` as "the current round has an error" or "the entire javac command is guaranteed to fail at the moment of the query". Similarly, `processingOver()` is true in the final round even when **no errors occurred at all**.

## 7. Relationship Between errorRaised(), Messager, and Continued Processing

### 7.1. Errors via Messager Differ from Unhandled Exceptions

In an annotation processor, the standard way to report a controlled error is:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR, "Giá trị annotation không hợp lệ");
```

The compiler collects diagnostic errors; **the current round may continue running to completion**, and `errorRaised()` in the next round reflects that an error occurred in the previous round.

Conversely, **throwing an uncaught exception** from a processor is not the standard mechanism for reporting validation errors: the tool may stop invoking other processors or terminate annotation processing abnormally. For user-fixable errors such as a missing annotation value or misconfiguration, use `Messager` with a specific `Element` location whenever possible, instead of throwing an unhandled exception.

### 7.2. warning Is Not errorRaised

`Diagnostic.Kind.WARNING` or `MANDATORY_WARNING` is not `ERROR`. Do not assume that a warning causes `errorRaised=true`. However, the compiler may be configured with options such as `-Werror` to treat warnings as conditions that cause compilation to fail; the exact impact on error state depends on the tool and configuration. Therefore, avoid designing logic based on assumptions about `errorRaised()` when mixing multiple warning policies.

### 7.3. Why Not Check for Errors Only in the Final Round?

Suppose a processor encounters an invalid annotation in a normal round yet still attempts to generate a Java file based on the invalid configuration. The generated file may propagate errors further or produce meaningless output.

The safe approach is to **validate before generating** in every round and maintain an internal flag if needed. `errorRaised()` only lets you observe diagnostics from the previous round; **it does not replace validation by the processor within the current round itself**.

## 8. Processor Design Pattern to Avoid Errors in the Final Round

A real-world processor typically needs to manage three kinds of state:

- **Per-round input:** the annotated `Element` instances and current roots; these should be retrieved from the `RoundEnvironment` of that exact round.
- **Accumulated state:** information that needs to be aggregated across multiple rounds; use instance fields scoped to a single processing run.
- **Final state:** `processingOver()`, `errorRaised()`, and custom error flags to decide on data aggregation/output.

Java pseudocode example:

```java
// Sketch code; the referenced types and methods must be defined.
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        if (!roundEnv.errorRaised() && !hasOwnErrors) {
            finishSummary(); // Do not generate additional sources requiring a new round.
        }
        return true;
    }

    for (Element element : roundEnv.getElementsAnnotatedWith(MyTag.class)) {
        if (!isValid(element)) {
            hasOwnErrors = true;
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Invalid annotation", element);
            continue;
        }
        collect(element);
    }

    generateNewSourcesIfNeeded(); // Normal rounds only.
    return true;
}
```

`hasOwnErrors`, `MyTag`, `finishSummary`, `collect`, `isValid`, and `generateNewSourcesIfNeeded` are **illustrative names**, not a standalone Java class. This pattern emphasizes **branching for the final round right at the start** and separating validation from the file-generation step.

### 8.1. Considerations When Aggregating Information Across Multiple Rounds

- The same type name may appear because of sources generated in different rounds; use an appropriate key and avoid unintended duplicate counting.
- Do not assume the element order from a `Set` is deterministic; if used to generate a resource, sort explicitly when needed.
- A generated file may carry annotations supported by this same processor; avoid endlessly generating a new type in every round and causing an unnecessarily long processing chain.
- Do not attempt to re-create a source/class with the same pathname within a single processing run; `Filer` enforces rules against duplicate writes and may throw `FilerException`.
- When reporting an error, do not produce an artifact deemed valid if the source data is invalid.
- When integrating with a build system, distinguish compiler annotation processing from post-build app/test tasks; `processingOver()` is not a "product deployed" signal.

## 9. Common Mistakes

**1. Confusing processingOver() with "the processor has already finished running".** This is the flag for the final round currently being invoked; the processor still has an opportunity to execute finalization logic in that `process` call.

**2. Confusing errorRaised() with an error raised in the current round itself.** According to the Javadoc, this indicates an error from the previous round. Immediately after calling `Messager.ERROR`, do not expect the flag to change right away.

**3. Treating processingOver=true as synonymous with an error.** The final round occurs even during a normal build with no errors.

**4. Treating errorRaised=false as synonymous with the entire build pipeline succeeding.** The flag only describes errors from the previous annotation processing round and does not cover all stages of compilation, testing, linking, or deployment.

**5. Checking only annotations.isEmpty() to determine the final round.** The annotation set can be empty during a `process` call, but only `processingOver()` is the reliable signal for the final round.

**6. Generating new source files in the final round and expecting them to be processed.** There is no subsequent round to process types created in the final round. Generate new source/class files at the proper time during normal rounds.

**7. Using return true to prevent subsequent rounds.** `return true` claims the annotation types; it does not cancel remaining rounds. A processor that has already been invoked may continue receiving the final round.

**8. Failing to guard against duplicate source file generation.** Each file path may only be created once per annotation processing run under the Filer contract; maintain appropriate state to avoid FilerException.

**9. Assuming subsequent rounds always have data.** `getRootElements()` and the annotation set can be empty. Final-round code must handle the case where there are no roots.

**10. Assuming there will always be exactly two normal rounds.** The number of rounds depends on file generation, inputs, and the tool; this example has two normal rounds because it intentionally generates a new source file in the first round.

**11. Manually creating a new processor instance in each round.** The tool typically keeps the same processor object across rounds; do not assume instance state is lost between `process` calls.

**12. Using uncaught exceptions to report user errors.** Prefer Messager diagnostics with a source location; unhandled exceptions may cause abnormal termination of processing.

## 10. Checklist for Debugging an Annotation Processor

1. Identify the compiler and source level (for example, `javac --release 17`).
2. Verify that the processor is actually enabled (`-processor` or appropriate service discovery) and that `@SupportedAnnotationTypes` specifies the correct annotation types.
3. Add logging showing `processingOver()`, `errorRaised()`, the number of roots, and the number of annotated elements found **per round**.
4. Enable `-XprintRounds` when using `javac` to inspect round ordering and root types.
5. When files are generated, check the file name, when the stream is closed, the `-s` directory, and whether the next round receives the newly generated type.
6. If the compiler reports `FilerException`, look for where the processor re-creates the same pathname across rounds.
7. If there is no data in the final round, review the earlier accumulation logic; do not treat empty annotations as an error.
8. If `errorRaised=true`, look for a `Diagnostic.Kind.ERROR` from the previous round (possibly from another processor); do not attribute every error solely to the current processor.
9. Verify that the processor does not generate files requiring further processing during the final round.
10. Do not conclude that the entire build succeeded based solely on `errorRaised=false` in the final `process` call.

## 11. Practice Exercises

1. **No file generation:** In `RoundLifecycleProcessor`, temporarily remove the `createSourceFile` branch, then rerun `javac`. Predict the number of normal rounds and when `processingOver=true` occurs.
2. **Generate an additional layer:** Modify the processor to generate another new type annotated with `@DemoTag` in the second normal round, while controlling it with a counter so it does not generate indefinitely. Observe the number of rounds with `-XprintRounds`.
3. **Report an error:** Run with `-Afail=true`. Explain why the round 1 line still prints `errorRaised=false`, while the final round prints `true`.
4. **Simulate a warning:** Change `Diagnostic.Kind.ERROR` to `WARNING` in test mode. Compare the `errorRaised` result without and with the compiler's `-Werror` mechanism enabled. Note any tool-specific differences.
5. **Remove the processingOver check:** Observe the design flaw when the processor continues calling Filer even in the final round. Then restore the `processingOver()` guard.
6. **Claim annotations:** Change `return true` to `false` and explain its effect on other processors, without confusing it with the number of rounds.
7. **Aggregate data:** Add a `Set<String>` to store the names of `TypeElement` instances seen during normal rounds; print the sorted list in the final round. Ensure entries are not double-counted when similar roots appear.

## 12. Official References

- [RoundEnvironment — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): specification of `processingOver()`, `errorRaised()`, `getRootElements()`, and `getElementsAnnotatedWith()`.
- [Processor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): sequence of rounds, invocation of processors in the final round, and rules for claiming annotation types.
- [Filer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): how files generated in the current round become inputs for the next round, file name management, and duplicate errors.
- [Messager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): how a processor reports warning/error diagnostics.

**Key takeaway:** `processingOver()` answers **"is this the final round, with no subsequent processing round for generated types?"**; `errorRaised()` answers **"was an error reported in the previous round?"**. When writing a processor, check for the final round early, generate sources during normal rounds, report errors with `Messager`, and avoid using these two flags in place of business state or the final outcome of the entire build.
