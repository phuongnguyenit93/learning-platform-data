# Lifecycle of `init`, `process`, and Processing Rounds in Java Annotation Processing

Annotation processing is a mechanism in which an **annotation processor** is invoked by `javac` at compile time to **read the program model**, analyze annotations, report errors/warnings, or **generate additional sources, classes, or resources**. A processor is not a listener called when the application runs; it operates at the compilation phase and has its own lifecycle.

The three most important points:

1. **`init(ProcessingEnvironment)`** prepares the processor and is typically called once per processor instance in a processing run.
2. **`process(Set<? extends TypeElement>, RoundEnvironment)`** is called in **processing rounds** to receive the assigned annotation types and the round's set of input elements.
3. **A new round occurs when new sources/classes are generated for the compiler to process**; after normal rounds, there is a **final round** (`processingOver() == true`), which is not an invitation to generate additional sources for the next round.

This model belongs to the standard `javax.annotation.processing` API and works with JDK 17+.

## 1. Objects Participating in an Annotation Processing Run

| Component | Responsibility |
| --- | --- |
| `javax.annotation.processing.Processor` | The contract that an annotation processor must implement, including `init`, `process`, and querying annotations/source version/options/completions. |
| `AbstractProcessor` | A utility class that partially implements `Processor`, providing `processingEnv`, `getSupportedAnnotationTypes()`, and default methods. |
| `ProcessingEnvironment` | Utilities provided by the compiler to the processor: `Messager`, `Filer`, `Elements`, `Types`, options, source version, etc. |
| `RoundEnvironment` | Information **specific to the current round**: root elements, annotated elements, `processingOver()`, `errorRaised()`. |
| `TypeElement` | Models a Java type declaration; in `process`, the `annotations` set contains **the annotation types** assigned to the processor. |
| `Filer` | Creates source files, class files, or resources according to the processor API rules. |
| `Messager` | Emits diagnostics (NOTE, WARNING, ERROR) at compile time. |

A processor typically extends `AbstractProcessor`, declaring the annotations it supports and the desired Java version:

```java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedAnnotationTypes("com.example.MyMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class MyProcessor extends AbstractProcessor {
    // init(...) and process(...) are implemented here.
}
```

This is only an **illustrative skeleton**; to become a concrete compilable class, it must implement `process(...)`. The annotation named `SupportedAnnotationTypes` specifies **the canonical name of the annotation**, rather than automatically creating a `MyMarker` type in the project.

## 2. Processor Discovery Step: Must Be Loaded by the Compiler

`javac` needs to know which processor to invoke. Common ways:

- **Explicit specification** using `javac -processor com.example.MyProcessor ...`.
- **Service discovery**: package the processor into a JAR containing the `META-INF/services/javax.annotation.processing.Processor` file listing the processor class name, then place the JAR on the appropriate processor search path.
- Build tools such as Maven or Gradle configure the annotation processor path and invocation accordingly.

The processor must **be compiled and loadable before it processes application code**. You should not assume `javac` will compile a processor from source and automatically discover/run that processor in the same pass if it has not been loaded yet. In the example at the end of this article, we compile the processor first, then run `javac` a second time with `-processor` to avoid relying on automatic discovery.

`-classpath` is used to locate classes when compiling application code; `-processorpath` can be used to specify the processor search path (if not specified, processor lookup depends on `javac` option mechanisms). For projects with a module path and processor modules, there are separate options; the module path for the application should not be confused with the processor path.

A processor receives a **code model** (`Element`, `TypeMirror`) through the compiler, not runtime objects constructed with `new` or annotation proxies from `Class.getAnnotation(...)`.

## 3. `init(ProcessingEnvironment)`: One-Time Initialization

Once the compiler has created a processor instance, it calls:

```java
@Override
public synchronized void init(ProcessingEnvironment env) {
    super.init(env);
    // Prepare state, read options, check configuration.
}
```

In `AbstractProcessor`, `super.init(env)` assigns `processingEnv`, checks initialization constraints, and allows other methods to access the environment. Call `super.init(env)` when overriding. You should not call `init` manually from application code.

Some useful APIs after `init`:

```java
processingEnv.getMessager();       // Report errors/warnings/notes to the compiler
processingEnv.getFiler();          // Create sources/classes/resources
processingEnv.getElementUtils();   // Inspect Element declarations
processingEnv.getTypeUtils();      // Analyze TypeMirror
processingEnv.getOptions();        // -A... options provided by the compiler
```

`init` is suitable for **one-time tasks**: reading `-A` configuration, creating maps/sets to hold processed state, and preparing helpers. There is no need to access source code using runtime Reflection.

Lifecycle distinction:

- A **processor instance** receives `init` once in a compiler processing run, and may subsequently receive **multiple `process` calls**.
- A new `javac` invocation is a new compilation run and may create a **new instance**; instance variables are not guaranteed to preserve state across build commands.
- Do not store `ProcessingEnvironment` in a `static` variable shared across multiple compiler tasks. This environment belongs to a single compilation run.

## 4. `process(...)`: Receiving Annotations and Elements of the Current Round

Standard signature:

```java
@Override
public boolean process(
        java.util.Set<? extends javax.lang.model.element.TypeElement> annotations,
        javax.annotation.processing.RoundEnvironment roundEnv
) {
    return true;
}
```

The first parameter, `annotations`, is the set of **annotation types assigned to the processor by the environment in this round**, not the set of all annotated classes, nor a list of **runtime values**. To find specific declarations:

```java
for (javax.lang.model.element.TypeElement annotationType : annotations) {
    for (javax.lang.model.element.Element element :
            roundEnv.getElementsAnnotatedWith(annotationType)) {
        // Read the element and metadata using javax.lang.model.
    }
}
```

Core methods on `RoundEnvironment`:

| API | Meaning |
| --- | --- |
| `getRootElements()` | The set of root elements of the **current round**; the first round typically consists of input top-level types/sources, while subsequent rounds may include new declarations created by generators. |
| `getElementsAnnotatedWith(TypeElement)` | Finds elements annotated with the passed type in the current round's model. |
| `getElementsAnnotatedWith(Class<? extends Annotation>)` | A way to query by annotation class when the processor can load this annotation type; using `TypeElement` generally helps limit runtime classloader dependencies. |
| `processingOver()` | Whether this is the **final round**. |
| `errorRaised()` | Whether an `ERROR` diagnostic was raised **in the previous round**. |

**Timing note:** `errorRaised()` does not necessarily report an error just sent via `Messager.printMessage(ERROR, ...)` **within the current `process` call**. It should be understood as the error status from the previous round according to the `RoundEnvironment` contract.

With multiple annotation types, a processor may be asked to handle certain types in this round while others are assigned to another processor. You should not assume `annotations` is the complete set of all annotations appearing across the entire program.

## 5. The `boolean` Return Value of `process`: Claiming Annotations

The return value of `process` signifies **claiming** (*taking responsibility for processing*) the assigned annotation types:

- `return true;`: the processor **claims** the annotation types it received in this round. Within the same round, subsequent processors will typically **not be asked to process those same claimed annotation types**.
- `return false;`: the processor **does not claim** them; other processors may still be assigned the corresponding annotation types.

This value does **not** mean "compilation succeeded / failed". To report an error that can halt compilation, use `Messager` with `Diagnostic.Kind.ERROR`:

```java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Cấu hình annotation không hợp lệ"
);
```

A processor returning `true` can still emit an ERROR diagnostic; a processor returning `false` does not mean the compiler must stop. Nor is `process` an operation that returns generated data: new sources/classes appear because `Filer` is called, not because of `return true`.

**Choose to claim intentionally.** If a processor is the sole primary handler responsible for an annotation, `true` is usually appropriate. If multiple processors need to read the same type of metadata together, you should consider coordination and claiming choices; do not use the wildcard `"*"` indiscriminately and claim annotation types that do not belong to your processor's responsibility.

## 6. Processing Rounds: Why Are There Multiple Rounds?

A single compilation run can consist of multiple **rounds**. The compiler processes existing sources/classes, invokes processors, and then feeds **newly generated** files into the next round. This approach allows a second generator to see types emitted by a first generator.

Common diagram:

```text
Compiler loads processor
        |
        v
      init()
        |
        v
Round 1: initial sources → process(..., roundEnv1)
        |       Filer creates GeneratedA.java
        v
Round 2: GeneratedA.java → process(..., roundEnv2)
        |       Filer creates GeneratedB.java
        v
Round 3: GeneratedB.java → process(..., roundEnv3)
        |       no new Java/class files
        v
Final round: processingOver() == true
        |
        v
Compiler completes the remaining compilation steps
```

Not every compiler invocation always has exactly three normal rounds or a predetermined fixed count. The number of rounds depends on generated files, errors, participating processors, and processing rules.

Each `process` call has a **new `RoundEnvironment`**. `getRootElements()` in the next round is not always "all roots of the project"; the new roots may be the newly generated sources/classes just created by generators. To keep a list of items examined in previous rounds, the processor must **store state itself** in the instance (for example, `Set<String>`).

A processing run ends with a round where `processingOver() == true`, even though in practice the compiler may encounter errors. When processing is over, the compiler does not start a new annotation processing round to process types that `process` attempted to generate during the final round.

## 7. The Final Round: `processingOver()` and `errorRaised()`

Common pattern:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Finish up, write summary diagnostics, or clean up temporary state.
        return true;
    }

    // In normal rounds only: read elements and generate sources if needed.
    return true;
}
```

This is an **illustrative snippet**; `Set` and `TypeElement` need to be imported, and it must be placed inside a processor class.

The final round is useful for writing a **summary**, emitting warnings about incomplete data, or executing end-of-run logic. However, if additional sources/classes are created in the final round, there will be **no subsequent annotation processing round for that new file**; attempting to create files at this stage may cause warnings/errors or result in output not being processed as expected. Therefore, generate sources during normal rounds.

`roundEnv.errorRaised()` indicates that an error was raised in the **previous round**. If the program has a summary step or a final metadata generation decision, you can check this flag to avoid outputting a "success" report when errors have already occurred.

Using `processingOver()` explicitly is better than inferring the final round by checking `annotations.isEmpty()` or `roundEnv.getRootElements().isEmpty()`. A normal round might have no annotation types assigned to a **specific processor** even though compilation is still continuing; in contrast, the final round is an official state reported by the API.

## 8. Runnable Java 17+ Example: A Processor Going Through Three Rounds

We will build a small example without external libraries. The processor detects `@DemoTag` on a class and creates **`GeneratedGreeting.java`** with the same annotation, giving the compiler an additional normal round to process the new source before the final round.

Create four files **in the same directory** with the exact names below.

### File 1: `DemoTag.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface DemoTag {
}
```

The `DemoTag` annotation uses `SOURCE` retention because the processor reads the **source model at compile time**, without needing to retain the marker until runtime. It applies to type declarations (`TYPE`).

### File 2: `RoundProbeProcessor.java`

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("DemoTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class RoundProbeProcessor extends AbstractProcessor {
    private int roundCount = 0;
    private boolean generated = false;

    @Override
    public synchronized void init(ProcessingEnvironment env) {
        super.init(env);
        System.out.println("init");
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        int hits = 0;
        for (TypeElement annotationType : annotations) {
            hits += roundEnv.getElementsAnnotatedWith(annotationType).size();
        }

        roundCount++;
        System.out.println("round=" + roundCount
                + ", over=" + roundEnv.processingOver()
                + ", hits=" + hits);

        if (!roundEnv.processingOver() && !generated) {
            generated = true;
            try {
                JavaFileObject source =
                        processingEnv.getFiler().createSourceFile("GeneratedGreeting");

                try (Writer writer = source.openWriter()) {
                    writer.write(
                            "@DemoTag\n"
                          + "public final class GeneratedGreeting {\n"
                          + "    public static String message() {\n"
                          + "        return \"generated\";\n"
                          + "    }\n"
                          + "}\n"
                    );
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString());
            }
        }
        return true;
    }
}
```

Instance state explanation:

- `init()` prints an `init` line when the processor is initialized for the compiler task.
- `roundCount` increments on each `process` call.
- `hits` counts the elements annotated with annotation types belonging to the `annotations` set assigned to the processor in **this round**.
- `generated` guards against writing **the same file** again across rounds. Without this flag, calling `createSourceFile("GeneratedGreeting")` a second time could cause a `FilerException`, because Filer does not allow the same processor run to recreate an already created file.
- `!roundEnv.processingOver()` prevents file creation in the **final round**.
- `return true` indicates that the processor claims `DemoTag`, not a success indicator for writing the file.

In this illustrative example, logging uses `System.out.println` to make the lifecycle order easy to follow; in a real processor, use `Messager` for compiler-meaningful messages (NOTE/WARNING/ERROR), and limit arbitrary log output if the build needs clean output.

### File 3: `Example.java`

```java
@DemoTag
public class Example {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
```

`Example.java` intentionally calls a class **that does not yet exist in the initial sources**. `GeneratedGreeting` is created by the processor in round 1, after which the compiler can include it in the processing and compilation steps so that `Example` can reference it.

### Compile and Run

Run these commands in order inside the directory containing the three `.java` files just created:

```bash
mkdir out
javac -encoding UTF-8 DemoTag.java RoundProbeProcessor.java
javac -encoding UTF-8 -cp . -processorpath . -processor RoundProbeProcessor -d out Example.java
java -cp out Example
```

**Typical output of the second `javac` command** (messages printed by the processor to `stdout`):

```text
init
round=1, over=false, hits=1
round=2, over=false, hits=1
round=3, over=true, hits=0
```

The command running the application prints:

```text
generated
```

Why are there three `process` calls?

1. **Round 1:** the compiler sees `Example` with `@DemoTag`; the processor is called with `hits=1` and then uses `Filer` to create `GeneratedGreeting.java`, which is also marked with `@DemoTag`.
2. **Round 2:** the compiler processes the newly generated source, so the processor again receives `@DemoTag` on `GeneratedGreeting`, `hits=1`. Because `generated == true`, the processor does not create any more new files.
3. **Round 3:** there are no more new sources/classes to process in a subsequent round, so the compiler invokes the **final round** with `processingOver() == true`. `hits=0` and the processor does not create new files.

In this example there are no errors, so `errorRaised()` will be `false` in the rounds being examined. There is no need to rely on it to control the number of rounds.

`javac` may emit additional information depending on options and the build environment; the log output listed above consists of **the lines printed by the example itself**, excluding messages from wrappers or IDEs. Running `java -cp out Example` still works because the `Example` and `GeneratedGreeting` classes are created in the `out` directory; the `DemoTag` annotation has `SOURCE` retention so it does not need to be loaded for runtime Reflection to read.

**Note:** The processor is declared to support the name `"DemoTag"` because the example uses the default package for ease of working in a single directory. For real projects, you should place classes in an explicit package and specify the fully qualified annotation name, for example `@SupportedAnnotationTypes("com.example.annotations.DemoTag")`, and then configure the appropriate processor path.

## 9. Preserving State Across Rounds and Avoiding Duplicate Generation

A common mistake is treating each `process` call as a completely new program. In reality, the same processor instance is called across the rounds of the same annotation processing run, so instance fields help store state:

```java
private final Set<String> processedTypes = new HashSet<>();
```

Inside `process`, you can store the qualified name `TypeElement.getQualifiedName().toString()` for processed types. When encountering a previously seen type again, skip it if the workflow does not require reprocessing.

**Illustrative** example (requires importing `Set`, `HashSet`, `Element`, `TypeElement` and placing inside a processor):

```java
for (Element element : roundEnv.getElementsAnnotatedWith(annotationType)) {
    if (element instanceof TypeElement type) {
        String name = type.getQualifiedName().toString();
        if (processedTypes.add(name)) {
            // Generate a single output for this type if needed.
        }
    }
}
```

For a generator, choose **stable output names** and clearly determine that each output is created once. `Filer` tracks files created within a processing run; if `createSourceFile` is called twice with the same name, `FilerException` is normal expected behavior that needs to be handled, not a strange IDE bug.

Avoid storing full `Element` objects across multiple rounds when long-term persistence is needed; when only an identifier is needed, you can store the **qualified name** and look it up again using `Elements` when appropriate. An `Element` belongs to the compiler model of the current run, not a persistent domain object across multiple builds.

## 10. Distinguishing `Filer`, `Messager`, and `System.out`

During processing, a processor typically performs three tasks:

1. **Inspect** annotated declarations using `Element`/`TypeMirror`.
2. **Report diagnostic results** using `Messager`.
3. **Generate** new files using `Filer` (when actually needed).

Example of reporting an error attached to an element's location:

```java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Chỉ được dùng annotation trên class hợp lệ",
        element
);
```

`element` here is an `Element` variable retrieved from `RoundEnvironment`, and the snippet must be placed in an appropriate processing method. Reporting `ERROR` can cause the build to fail; **returning `false` does not replace sending a diagnostic**.

`Messager` enables IDEs and the compiler to display errors/warnings attached to the corresponding source locations. `System.out` merely outputs plain text from the processor process without diagnostic structure like the compiler API; it is fine for illustrating the lifecycle, but when developing libraries you should prefer `Messager`.

`Filer` is not an API for arbitrarily modifying user sources. It supports **creating** new files in compiler-managed locations; overwriting previous outputs within the same processing run or replacing code currently being compiled easily causes conflicts.

## 11. Lifecycle and Error Handling Rules

A well-built processor needs to distinguish three error levels:

| Level | Example | How to Handle |
| --- | --- | --- |
| Invalid annotation | Missing business-required attributes, wrong target | `Messager.printMessage(ERROR, ...)` attached to the element. |
| File generation error | `FilerException`, unable to write source, duplicate name | Emit a diagnostic with specific information; do not silently swallow the error. |
| Error from generated code | The `.java` file is created but fails to compile | Fix the generator logic, type/package/import names; track the round where the error occurred. |

`RoundEnvironment.errorRaised()` **does not replace** `try/catch` error handling when creating files. It only indicates that an error occurred in the previous round. Even when no error was seen from the previous round, the current Filer operation can still fail.

If a processor emits an ERROR in a normal round, the compiler may continue some necessary work to summarize and then report build failure. **Do not** infer from `processingOver()==true` that the build certainly succeeded. A final round can still occur even if previous rounds had errors.

For a generator emitting multiple interdependent files, design the output so that:
- A newly generated file does not need to feed back into **the current round itself**; it is typically processed in the next round.
- It does not infinitely loop generating more files from inputs generated by itself.
- It does not depend on the iteration order of `Set<? extends TypeElement>` or `getRootElements()`, because no source traversal order is guaranteed.
- Once an error has been reported, it does not announce that all sources were generated successfully.

## 12. Interaction Between Multiple Processors

In a single compilation run, multiple processors can participate together. The compiler is responsible for orchestrating the rounds and deciding which matching annotation types to assign to each processor:

```text
Round 1: @InputModel in source code
    ├─ Processor A reads the model, generates GeneratedDto.java
    └─ Processor B processes other assigned annotations
Round 2: GeneratedDto.java has @DtoMarker
    └─ Processor C processes @DtoMarker (if discovered/selected)
Final round
    └─ No more new rounds to process sources created here
```

Points to note:

- `return true` affects **whether subsequent processors can still be assigned the same annotation types in that round**.
- A processor that only supports a specific annotation type should not assume it will be called in every round with all roots, especially when no matching annotation is present or the processor is not selected.
- `@SupportedAnnotationTypes("*")` declares the ability to receive all annotation types, which may cause the processor to be considered in many situations. If a processor is only meant to validate `@DtoMarker`, declare the exact supported annotation instead of `"*"`.
- The output of processor A can become input for B/C in the next round if it contains the corresponding annotation types.

Specifying a particular processor with `-processor X` in examples makes the output easy to follow; real projects with multiple processors may produce logs in different orders. Do not rely on a fixed round count in general tests when multiple generators collaborate, unless you control the entire fixture.

## 13. Java Version Support and Processor Options

`@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares the language level supported by the processor. For projects using a newer Java version, you may need to update the declared version or override `getSupportedSourceVersion()` accordingly. You should not assume a processor targeting Java 17 can handle future syntax without changes.

To receive options from `javac`, declare them with `@SupportedOptions(...)` or override the corresponding API; when running the compiler, pass `-Akey=value`. Inside `init`, access them with:

```java
String mode = processingEnv.getOptions().get("mode");
```

This is a snippet used inside a processor after the environment has been initialized. Do not use system properties or read files arbitrarily when the compiler already provides clearly managed options.

With service discovery, the processor must be packaged and have the correct canonical name; when using modules, check the service provider declaration mechanism and `--processor-module-path`. Build layout, classloaders, and processor selection are **dependent on the compilation environment**, whereas the `init`/`process`/`RoundEnvironment` contract belongs to the Java API.

## 14. Common Misconceptions

| Misconception | Correct Explanation |
| --- | --- |
| `init` is called before every round | **No**: `init` prepares the processor instance before the `process` calls of the processing run. |
| `process` is called only once | **No**: it can be called across multiple rounds; the final round can also call `process`. |
| `annotations` are runtime annotation objects | **No**: it is a set of `TypeElement` representing the **annotation types** assigned to the processor. |
| `process(...)` returning `true` means the build succeeded | **No**: that claims the annotation types; report errors using `Messager`. |
| Generated sources are reprocessed by the processor immediately in the same round | Usually **no**: the compiler passes new files to the next round. |
| `getRootElements()` always contains all initial sources | **No**: it reflects the roots of the current round, which may be newly generated sources. |
| `annotations.isEmpty()` means `processingOver()` | **No**: use the official `roundEnv.processingOver()` flag. |
| You can generate more Java sources in the final round to open another round | **No**: the final round does not open another annotation processing round. |
| Calling `createSourceFile` with the same name across two rounds safely overwrites | **No**: `Filer` refuses to recreate an output with the same name within a single run. |
| Simply `return false` when there is an invalid configuration | **No**: you must emit `ERROR` if you want the compiler to report an error. |
| `errorRaised()` immediately reports any error just emitted in this round | **No**: it reflects errors from the previous processing round. |
| `SOURCE` annotations cannot be read by an annotation processor | **False**: annotation processing happens at compile time; `SOURCE` markers are a normal case. |

## 15. Knowledge Self-Check

Suppose a processor handles the `@Model` annotation; on each processing pass it generates a new Java file with `@Model` in the first two rounds, and then generates no more. There are no compilation errors.

1. How many times is `init()` called for the same processor instance? **Once**.
2. How many times can `process()` be called? **Multiple times**: the rounds with new sources plus one final round according to the processing mechanism.
3. When do you officially know you are in the final round? **`roundEnv.processingOver()` is `true`**.
4. Is `roundEnv.getRootElements()` the list of all classes in the project? **No**; only the roots relevant to **the current round**.
5. Does `return true` mean "no errors"? **No**; it claims the assigned annotation types.
6. When is a `.java` class created with `Filer` in round 1 typically processed? **In the next round**, not as an immediate recursive call inside the current `process`.
7. How do you avoid recreating the same file in every round? **Store instance state**, such as a set of generated output names or a `generated` flag.
8. What if you need to report an invalid annotation configuration? **`Messager.printMessage(ERROR, ...)`**, optionally passing an `Element` so the compiler points to the exact declaration.
9. Should you call `init(processingEnv)` manually from application code? **No**; the compiler orchestrates the lifecycle.
10. Should you assume every processor is called for the same number of rounds and with the same set of annotation types? **No**; processor selection, claiming, and new outputs affect the schedule.

To grasp the essence, think of `init` as **preparing the processing session**, `process` as **the work of one round**, `Filer` as the way to **create input data for subsequent rounds**, and `processingOver` as **the completion signal**. A proper processor should read elements selectively, generate output at most once per target, and report errors via the compiler API.

## References

- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): contract for initialization, claiming, processing rounds, and supported annotation types.
- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): utilities and `init` behavior.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `processingOver`, `errorRaised`, root elements, and finding elements by annotation.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): rules for creating new files between rounds.
