# Annotation processing: processing code in the next round and avoiding duplicate file generation

In Java, an annotation processor can generate additional source code using `Filer.createSourceFile(...)`. The newly generated source code **is not treated as a runtime class immediately available within the current callback**: the compiler tool feeds source/class files that have been created and **successfully closed** into the **next annotation processing round** for analysis. Therefore, a processor must understand the multi-round lifecycle (*rounds*) and ensure that each output file/type name is generated **only once in a single compiler run**.

Two goals must be achieved simultaneously:

1. **Identify and process elements from generated code in the next round** when required by business rules; do not attempt to retrieve newly written declarations as if they had already been analyzed in the currently running round.
2. **Avoid creating duplicates of the same file or type name** across multiple rounds, multiple source elements, or multiple processors; handle `FilerException` as a clear diagnostic rather than silently ignoring it.

A typical example: round 1 reads `@Emit` on `Seed` and generates `GeneratedPeer.java`. Because the generated file is also annotated with `@Emit`, the processor sees `GeneratedPeer` in round 2 but **does not proceed to regenerate the same file name**. The final round reports `processingOver() == true`.

## 1. Each compilation has multiple rounds

`javax.annotation.processing.Processor` defines the annotation processing mechanism as a sequence of rounds. For each round, `RoundEnvironment` describes the elements belonging to that round. When a round creates valid source/class files, the generated declarations can become inputs for the subsequent round.

Common model:

```text
Initial source: @Emit class Seed
          |
          v
Round 1: processor sees Seed
          |
          | Filer.createSourceFile("demo.GeneratedPeer", Seed)
          | write content then close Writer
          v
Round 2: javac analyzes GeneratedPeer
          | processor may see @Emit on GeneratedPeer
          | do not create demo.GeneratedPeer a second time
          v
Final round: processingOver() == true
          |
          v
Complete annotation processing and compilation
```

**Key points:**

- The original inputs can be viewed as the result of a **hypothetical round 0**; their elements are processed in the first actual round.
- `Processor.process(...)` may be called multiple times on the **same processor instance** within a single compilation run. Therefore, stateful instance fields can be used to avoid regenerating the same name **within that run**.
- The tool may invoke the processor in subsequent rounds, even when the set of annotations passed into `process` is empty; you should not infer the final round solely from `annotations.isEmpty()`.
- The set of root elements of a round reflects the input elements of that round, including declarations generated in the previous round. Not every type seen previously reappears as a root in every round.
- The generated type name does not necessarily have to be annotated with the same annotation; the processor needs to clearly choose which condition causes generated code to be processed further.

According to the `Filer` contract, source/class files created via the corresponding methods are considered by the tool for the next round **once the `Writer` or `OutputStream` has been closed**. Do not keep a stream open across rounds while expecting the file to be analyzed.

## 2. What signals does RoundEnvironment provide?

Key APIs:

| API | Meaning | Usage |
| --- | --- | --- |
| `getElementsAnnotatedWith(Emit.class)` | Finds elements bearing the annotation within the scope of the round | Precisely select the elements that need to be processed |
| `getRootElements()` | Root elements of the round | Observe types created from the previous round |
| `processingOver()` | Indicates the final round; code generated in this round will not be processed further | Stop generating new code; summarize/emit appropriate diagnostics |
| `errorRaised()` | Indicates whether an error was reported in the **previous round** | Consider skipping additional generation when compilation already has errors |
| `getElementsAnnotatedWith(TypeElement)` | Looks up using the language model without necessarily loading the runtime annotation | Useful when processing annotation declarations via the compiler model |

Example callback structure:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Final round: no next round remains to process new files.
        return true;
    }
    if (roundEnv.errorRaised()) {
        // An error was raised in the immediately preceding round.
        // Decide whether to stop generation or still collect diagnostics.
    }
    // Process elements belonging to the current round.
    return true;
}
```

This is an **illustrative skeleton** that must be placed inside a processor class with the appropriate imports. `errorRaised()` does **not** mean that an error raised directly within the current callback will automatically cause it to change to `true` in the same round.

### When does the final round occur?

After the rounds that process inputs and newly generated files, the tool runs a final round where `processingOver()` returns `true`. At that point, **newly generated types will not be subject to a subsequent processing round**. Do not generate Java source in the final round expecting its annotations to be processed. Certain summarization or reporting tasks may be appropriate here; if an **aggregated resource** such as an index is needed, it must also adhere to the `Filer` contract and build policies.

Do not try to control the number of rounds using a Java loop inside `process()`. The compiler manages rounds; the processor reacts to the events the compiler delivers.

## 3. Filer, FilerException, and the create-once rule

`ProcessingEnvironment.getFiler()` returns a `Filer`, which provides methods to create source, class, and resource files:

```java
JavaFileObject source = processingEnv.getFiler()
        .createSourceFile("demo.GeneratedPeer", originatingElement);

try (Writer writer = source.openWriter()) {
    writer.write("package demo; public class GeneratedPeer {}");
}
```

This is an **illustrative snippet inside a processor**, requiring the appropriate variables/imports and proper name generation. The name format passed to `createSourceFile` is a **fully qualified type name**, not an arbitrary path like `../GeneratedPeer.java`. `Filer` automatically determines the corresponding output directory from the compiler configuration, such as `-s generated`.

### Uniqueness rule scoped to a single processor run

According to the `Filer` API in Java 17:

- A pathname may only be **created once within a single compilation run**; a second creation attempt in the same run throws `FilerException`.
- You cannot create both a source file and a class file for the same type within the same run using incompatible calls.
- The initial input files are considered to have been created in **round 0**; attempting to recreate `Seed.java` from a run that is compiling `Seed.java` may throw `FilerException`.
- If a generated file **from a previous compilation** already exists in the output directory before the first creation in the current run, the API states that the old content may be deleted/replaced. Therefore, do **not** simply use `Files.exists(path)` on disk to decide whether it was "already generated in this run".
- You should not intentionally overwrite files outside the processor's ownership. Two processors competing to generate the same type is a **design conflict** and should not be handled by ignoring the error.

`FilerException` extends `IOException`. When writing with `createSourceFile`, catch the error and report a contextual diagnostic:

```java
try {
    // createSourceFile(...) and write content.
} catch (javax.annotation.processing.FilerException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Trùng tên tệp sinh: " + ex.getMessage());
} catch (java.io.IOException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Không ghi được mã nguồn: " + ex.getMessage());
}
```

This is an **illustrative snippet** that must be placed inside a processor and given actual `try` logic. You should not catch `FilerException` and **treat it as a success** unless you are certain an equivalent element was validly created: the contents might not match, or two processors might be writing incompatibly.

### How do originating elements help?

In the call:

```java
processingEnv.getFiler()
        .createSourceFile("demo.GeneratedPeer", sourceElement);
```

`sourceElement` is the declaration being processed, for example the `TypeElement` for `Seed`. It is the **originating element**, hinting at the causal relationship between the input source and the generated file. Incremental build tools can use this information to determine when to reprocess or delete stale artifacts; not every tool is required to utilize that hint.

**Do not misunderstand:** passing an originating element does **not** allow creating duplicate copies of the same file. The uniqueness of the output name must still be guaranteed.

## 4. Three layers of defense against duplicate generation

A reliable code-generating processor typically combines multiple conditions:

1. **Select the right trigger source.** For example, generate `GeneratedPeer` only when processing `Seed`, rather than generating it for every class annotated with `@Emit`.
2. **Record the fully qualified names requested for creation within the run.** Use `Set<String> generatedNames`, with keys like `"demo.GeneratedPeer"`; do not use only `"GeneratedPeer"` because simple names can collide across multiple packages.
3. **Let Filer perform the final uniqueness verification.** You must still handle `FilerException` because there may be input sources with the same name, other processors, or invalid paths. Your own Set only guards against **duplicate calls within your processor**.

Example principle:

```java
String generatedType = "demo.GeneratedPeer";

if (generatedNames.add(generatedType)) {
    JavaFileObject file = filer.createSourceFile(generatedType, origin);
    // try-with-resources and write the file here.
}
```

This is **illustrative code** requiring `generatedNames`, `filer`, and `origin` to be declared. `Set.add(...)` returns `true` the first time; subsequent rounds return `false` as long as the same processor instance retains state.

**A Set alone cannot solve every problem:**

- It does not automatically coordinate with other processors in the build.
- It lives only for the compilation run and the corresponding classloader/processor instance; the next build starts from scratch.
- If you add the key before creating the file and `Filer` fails, do not mark the task as "succeeded" and stay silent: you must report an error or apply a clear recovery policy.
- If you want to generate **one type per source**, the key must be the output name derived from each element, not a single constant.
- If two different sources happen to produce the same output name, you must define a collision rule rather than silently picking an arbitrary source.

## 5. Standalone Java 17+ example: Round 1 → Round 2 → final round

This example has **three input Java files**, placed in the `demo/` directory, and one source file `demo/GeneratedPeer.java` **automatically generated by the processor**. Do not create the GeneratedPeer file manually beforehand.

### File 1: demo/Emit.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Emit {}
```

The `@Emit` annotation serves as a signal for the processor. `RetentionPolicy.SOURCE` is appropriate because it is only needed at compile time; there is no need to retain the annotation until runtime.

### File 2: demo/RoundProcessor.java

```java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
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

@SupportedAnnotationTypes("demo.Emit")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundProcessor extends AbstractProcessor {
    private final Set<String> written = new HashSet<>();
    private int round;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment env) {
        round++;

        if (env.processingOver()) {
            System.out.println("round=" + round + " processingOver=true");
            return true;
        }

        List<String> found = new ArrayList<>();

        for (Element e : env.getElementsAnnotatedWith(Emit.class)) {
            found.add(e.getSimpleName().toString());

            if (e.getSimpleName().contentEquals("Seed")
                    && written.add("demo.GeneratedPeer")) {
                try {
                    JavaFileObject source = processingEnv.getFiler()
                            .createSourceFile("demo.GeneratedPeer", e);

                    try (Writer out = source.openWriter()) {
                        out.write("package demo;\n"
                                + "@Emit public class GeneratedPeer {\n"
                                + "  public static String message() { return \"generated\"; }\n"
                                + "}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR, ex.toString(), e);
                }
            }
        }

        Collections.sort(found);
        System.out.println("round=" + round
                + " seen=" + String.join(",", found));
        return true;
    }
}
```

Part-by-part explanation:

- `@SupportedAnnotationTypes("demo.Emit")` instructs the processor to recognize the `demo.Emit` annotation; using the fully qualified name avoids package ambiguity.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` specifies the language version supported by the processor. The example compiles with `--release 17` for compatibility.
- `written` is a `HashSet` stored in the **processor instance** across the rounds of the compilation.
- `round` increments each time the processor is called; it is used **solely to illustrate ordering**, and you should not use the round number as a condition for identifying files.
- `if (env.processingOver())` stops code generation in the final round.
- Only `Seed` triggers generation of the type `demo.GeneratedPeer`. When `GeneratedPeer` carrying `@Emit` appears in the next round, it is still observed/logged, but **does not proceed to create the file**.
- `written.add(...)` prevents the processor from asking `Filer` to recreate that exact name in subsequent rounds within the same run.
- `createSourceFile("demo.GeneratedPeer", e)` attaches `Seed` as the originating element.
- `try (Writer out = ...)` **closes the file at the right time** so the tool feeds the generated source into the next round.
- `Diagnostic.Kind.ERROR` ensures code-generation errors are not swallowed; in a real system, you should include the collision reason/file name in the message.

This example intentionally generates only **one file** and checks the source name with `getSimpleName()` for ease of observation. In real-world usage, you must use `TypeElement.getQualifiedName()` or a package model along with the fully qualified name to avoid confusing two classes with the same simple name in different packages.

### File 3: demo/Seed.java

```java
package demo;

@Emit
public class Seed {
    public static void main(String[] args) {
        System.out.println(GeneratedPeer.message());
    }
}
```

Notable point: `Seed` **references `GeneratedPeer` before that code exists in the input source**. Working within the same compilation run, `javac` and the processor can resolve that reference after the `GeneratedPeer.java` source is created and analyzed in the next round.

### Compile and run

From the root directory containing `demo/`:

```bash
javac --release 17 -encoding UTF-8 -d out demo/Emit.java demo/RoundProcessor.java
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor demo.RoundProcessor -s generated -d out demo/Seed.java
java -cp out demo.Seed
```

**For the commands above**, writable output directories `out` and `generated` are needed; `javac` will create the required output directories/packages according to the configuration. If required by the tool or environment, create the root `out` and `generated` directories beforehand.

The first command produces `Emit.class` and `RoundProcessor.class` so the compiler can load the processor. The second command processes `Seed.java` with the processor, generates `generated/demo/GeneratedPeer.java`, and then compiles the applicable sources into class files in `out`. The final command runs `Seed.main`.

In a verified Java 17+ environment, **stdout from the second javac command** is:

```text
round=1 seen=Seed
round=2 seen=GeneratedPeer
round=3 processingOver=true
```

**Stdout from the java command** is:

```text
generated
```

The `round=...` lines come from `System.out.println` inside the processor; they are **not** stdout from the `Seed` runtime program. When compiler logging is enabled or another JDK is used, `javac` may print additional diagnostics; the output above describes a clean run with exactly these three input sources and this single processor.

### Why is generated code processed in round 2?

The generated file contains:

```java
package demo;

@Emit
public class GeneratedPeer {
    public static String message() {
        return "generated";
    }
}
```

This is the **equivalent content** of the string written by the processor, reformatted for readability; **do not create this file manually before the test compilation**.

Round 1 sees `Seed`, then creates and closes the file. Round 2 sees `GeneratedPeer` as a new type annotated with `@Emit`. Calling `getElementsAnnotatedWith(Emit.class)` returns the matching elements of **that round**, without automatically beginning to analyze a copy of `Seed`. The guard mechanism prevents `GeneratedPeer` from triggering duplicate creation of `demo.GeneratedPeer`.

If you omit both the `Seed` name condition and the `written` Set and attempt to create `demo.GeneratedPeer` every time `@Emit` is seen, round 2 will request creating the same pathname again. `Filer` must reject this according to its rules and throw `FilerException`.

## 6. Difference between a “generated file” and a “processed type”

A new source typically goes through these states:

```text
Not yet created
   |
   v
createSourceFile called
   |
   v
Writer open, content is being written
   |
   v
Writer closed successfully
   |
   v
Compiler picks up file to analyze in next round
   |
   v
New Element/TypeMirror may appear
   |
   v
Class file created in the compilation process
```

Several assumptions should be avoided:

- `createSourceFile(...)` **returns a JavaFileObject**, not a `TypeElement` for the new class. Do not cast it or call `Class.forName()` immediately inside the writing callback.
- Do not create a Java source and manually add it to `roundEnv.getRootElements()` in the same round; the root set is provided by the tool.
- Generating a source does not guarantee successful compilation if the source has syntax errors, a mismatched public class name, or unresolved dependencies.
- `processingOver()==true` means **there is no next round to process newly created types**; it does not mean “all build outputs have definitely succeeded”.
- With `-proc:only`, the compiler performs only annotation processing; sources may be generated, but you should not expect the application's runtime class files to be produced as in a normal compilation command.

You also need to distinguish **rounds within the same compilation run** from **different builds**. The `written` Set in the processor helps prevent duplicates within a single run; running `javac` next time creates a new processor instance and a fresh state.

## 7. When multiple sources generate the same file name

In the minimal example, there is only one `Seed`. However, a real processor may encounter:

```java
@GenerateAdapter
class Alpha {}

@GenerateAdapter
class Beta {}
```

This is an **illustrative snippet**; `GenerateAdapter` needs to be declared. If both `Alpha` and `Beta` generate the fixed type `example.Adapter`, a Set only prevents the second call to `Filer`, while leaving one of the two sources **without corresponding generated code**. That is a **naming design conflict**, not a success.

An appropriate policy is typically:

- Generate `example.AlphaAdapter` from `Alpha` and `example.BetaAdapter` from `Beta`, with a stable name based on the fully qualified name.
- If a case occurs where two inputs produce the same name, emit an **ERROR diagnostic** explaining the two involved sources instead of silently ignoring it.
- If the intent is to generate **a shared registry**, collect and merge data according to a consistent contract and choose the right time to generate it **once**, while remembering that elements generated later may change the input set. You must clearly design whether there are one or multiple generation phases; do not arbitrarily wait until the final round to generate a Java source that will need a subsequent round.
- Attach valid originating elements for the sources that directly affect the output to support the build tool's incremental compilation mechanism.

Do not assume that a `Set<Element>` or `HashSet<String>` automatically handles the case where two different processors emit the same output. `Filer` is the component that enforces the final file-writing boundary within a compilation run.

## 8. Common mistakes and how to fix them

### Mistake 1 — Generating the same file in every round

Incorrect pattern:

```java
@Override
public boolean process(Set<? extends TypeElement> anns,
                       RoundEnvironment env) {
    // WRONG: called every round without checking state/inputs.
    filer.createSourceFile("demo.GeneratedPeer");
    return true;
}
```

This **intentionally incorrect** snippet is also missing the `filer` variable, imports, and `IOException` handling. The core problem: the second invocation in the same run can attempt to create the same name again, leading to `FilerException`. You should generate only when there is a valid source and that type has not yet been requested for creation.

### Mistake 2 — Generating Java source in the final round

```java
if (roundEnv.processingOver()) {
    // Wrong if you expect this class to still be processed by the processor in a later round.
    processingEnv.getFiler().createSourceFile("demo.LateClass");
}
```

This is **code illustrating a lifecycle mistake**, and it also omits checked exception handling. The final round does not lead to a subsequent annotation processing round for `LateClass`. If you want the class to be processed further, generate it during an active round, according to your designed policy.

### Mistake 3 — Forgetting to close the Writer

```java
JavaFileObject file = filer.createSourceFile("demo.Thing", origin);
Writer writer = file.openWriter();
writer.write(sourceCode);
// Missing writer.close(): DO NOT do this.
```

This is an **incorrect illustrative snippet**; the variables must be defined in a real processor. Avoid resource leaks or incomplete files by using `try (Writer writer = file.openWriter()) { ... }`. The `Filer` contract ties handing the file off to the next round to closing the stream.

### Mistake 4 — Swallowing FilerException and continuing as if it succeeded

```java
try {
    // Generate file.
} catch (javax.annotation.processing.FilerException ignored) {
    // Wrong: may hide conflicts with inputs or another processor.
}
```

The snippet above **intentionally illustrates an anti-pattern**, not a rule to follow. Use `Messager` to emit a diagnostic and resolve the root cause.

### Mistake 5 — Treating a stale source on disk as a file already created in the current run

A file in `build/generated` may be an artifact from a previous run. According to the `Filer` API, the first creation in the current run may replace it. Conversely, an input currently being read by the compiler is considered to exist from round 0. **The “once per run” rule does not mean “if the file exists on disk, always skip it”.**

### Mistake 6 — Mixing element sets across multiple rounds without control

If the processor needs complete information across multiple rounds, record it by a stable key and update state deliberately. Do not conclude that “`getElementsAnnotatedWith` is empty in this round” means the entire compilation has no annotations. Conversely, do not unconditionally reprocess every element seen in earlier rounds.

### Mistake 7 — Using simple names instead of fully qualified names

`getSimpleName()` returns `User` for both `a.User` and `b.User`. If the processor generates `UserAdapter` into the same target package, a collision can occur. Store the appropriate package/module-qualified name of the output and check for duplicates before calling `Filer`.

### Mistake 8 — Assuming returning true/false controls round generation

`process(...)` returns `true` to **claim the annotation types that the processor has handled**, affecting whether other processors will still be invited to process those annotations. Returning `false` means **do not claim**. This is **not** a switch for “continuing or ending rounds”; new rounds are determined by the tool based on processing and validly generated files.

### Mistake 9 — Assuming generated code is guaranteed to compile

`Filer` writes Java source, but it does not automatically verify the contract of the Java code you generate. Test the output: package declaration, public class name, string escaping, encoding, imports, and dependencies. A closed file can still contain invalid source.

## 9. How to verify the processing rounds with javac

Use the exact same set of three files from section 5 in a clean test directory:

1. Run the compile command for `Emit.java` and `RoundProcessor.java` first so the processor has compiled bytecode.
2. Run the compile command for `Seed.java` with `-processor demo.RoundProcessor`. `-processorpath out` tells the compiler where to load the processor from; `-cp out` lets the application code and compiler resolve the `demo.Emit` type.
3. Inspect the three round log lines; the expected result is: `Seed`, `GeneratedPeer`, then final.
4. Verify that `generated/demo/GeneratedPeer.java` contains only a single corresponding class declaration.
5. Run `java -cp out demo.Seed`; the runtime program prints `generated`.
6. If you want to view round details reported by `javac`, add `-XprintRounds` to the second compile command. This is a debugging option provided by javac, not fixed program stdout.

When testing duplicate cases, do so in a separate build directory and inspect the diagnostics. Do not intentionally introduce a duplicate error into real code and suppress it just to make the compiler keep succeeding.

### Short checklist for a production processor

| Question | What to verify |
| --- | --- |
| Are new rounds handled properly? | `RoundEnvironment` is read on every callback and newly generated source types are picked up in the next round |
| Does generation stop in the final round? | Do not expect sources generated in the final round to be processed further |
| Are outputs closed? | `Writer`/`OutputStream` uses try-with-resources |
| Are stable names generated? | The output's fully qualified name is deterministically derived from the source |
| Is there a guard across rounds? | A Set of created names and appropriate input conditions |
| Are source conflicts detected? | Two sources sharing the same output are not silently ignored |
| Is FilerException handled? | Emit a clear diagnostic; do not swallow the error |
| Are originating elements supplied? | Pass the appropriate originating elements |
| Is incremental build supported? | Check the build tool documentation and the corresponding aggregating/isolating strategy |
| Are generated sources tested? | Compiles cleanly, runs properly, and does not depend on stale files |

## 10. Self-check questions

**Question 1.** A processor writes `@Emit class A` into a new Java source in round 1 and closes the writer. In which round does it typically appear?

**Answer:** In the **next round**, typically round 2, provided the file was validly generated and the tool continues processing.

**Question 2.** Why is a `Set<String> written` used inside the processor still useful even though Filer already enforces a create-once rule?

**Answer:** The Set helps **avoid proactively issuing duplicate creation requests** from the processor itself across multiple rounds. `Filer` remains the final safeguard and can report an error when other conflicts occur.

**Question 3.** When `processingOver()==true`, should you create a source that needs to be processed in a later round?

**Answer:** No. The final round has no subsequent annotation processing round for that source.

**Question 4.** Does the existence of a `GeneratedPeer.java` file from yesterday's build mean the processor is not allowed to generate this file in the current build?

**Answer:** Not necessarily. `Filer` defines uniqueness per **compilation run**, with distinct rules for stale files existing before the first creation and for initial inputs.

**Question 5.** If two source classes share the same simple name `User` in two different packages, is it safe to use `getSimpleName()` as the generation key?

**Answer:** No. Use the fully qualified name and compute the output name deterministically.

**Question 6.** Why must you close the `Writer` from `createSourceFile`?

**Answer:** So that the file finishes writing and the tool can pass it into the next round for processing, per the `Filer` contract.

**Question 7.** Does returning `false` from `process()` instruct javac to create an additional round?

**Answer:** No. `false` means the processor **does not claim** the annotation types it received; it is not a signal to create a round.

**Question 8.** What kind of error should `FilerException` be treated as?

**Answer:** It indicates that the file creation request violated `Filer`'s guarantees (particularly creating a duplicate name/pathname, conflicting with inputs or configuration). You must identify the cause and report a diagnostic; do not assume the desired output already exists accurately.

## Official documentation

- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html).
- [Java SE 17 — FilerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html).
- [Java SE 17 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).

**Remember:** **Create once, close the file, process in the next round.** Fix the output name based on the source, maintain file-creation state within the run, avoid trying to write Java source requiring a subsequent round during the final round, and treat `FilerException` as an error that must be diagnosed. That is the foundation of a reliable code-generating annotation processor.
