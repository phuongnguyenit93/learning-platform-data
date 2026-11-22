# Processing Rounds, Newly Generated Code, and Termination Conditions of Annotation Processing

In Java, **annotation processing** (JSR 269) lets one or more *annotation processors* inspect source declarations, check rules, and **create additional Java source files or class files** while `javac` compiles. A notable characteristic is that the process **does not run strictly once**: the compiler organizes work into **processing rounds**. Code created in the current round can become input for the next round, and the compiler continues until no new sources/classes remain to enter processing and then runs a **final round**.

Understanding processing rounds is key to answering practical questions:

- Why can a processor generate `GeneratedHello.java` and have the program reference that class within **the same `javac` invocation**?
- Why is `process(...)` called multiple times yet must not recreate the same file repeatedly?
- How do `RoundEnvironment.processingOver()` and `errorRaised()` differ?
- When is a processor allowed to generate code, and when should it only summarize results?
- Why do other processors sometimes fail to process a newly generated annotation?
- Do old generated files left in the build directory automatically trigger a new round?

This lesson uses Java 17 and the standard APIs `javax.annotation.processing`, `javax.lang.model`, and `javax.tools`.

## 1. Foundation: One Compile Pass Can Span Multiple Rounds

`javac` initially reads source compilation units, identifies annotation types that processors may support, and selects matching processors from the **processor path** or explicit configuration. Under the JSR 269 model, initial inputs of the compile pass can be viewed as the output of a **conceptual round 0**. Round 0 is only an explanatory model, not a normal `process` invocation.

Example of a processor detecting `@GenerateHello` and creating the `GeneratedHello` class:

```text
Initial input: Main.java (@GenerateHello)
           |
           v
  ROUND 1: process Main
           |
           +-- Filer.createSourceFile("demo.GeneratedHello")
           +-- write and close GeneratedHello.java
           |
           v
  ROUND 2: process newly created GeneratedHello.java
           |  (may have no @GenerateHello in the new file)
           +-- generate no additional Java source/class files
           |
           v
  FINAL ROUND: processingOver() == true
           |   participating processors are called one final time
           +-- summarize / release state; generate no code
           |
           v
  javac finishes checks/compilation and emits .class files
```

This is a **typical processing flow** for an example generating only one file in the first round; the actual number of rounds depends on generated files, processors, configuration, and errors.

A source file created in the current round **does not automatically become a root of that same round**. Once the writer or stream supplied by `Filer` is **closed**, the new source/class file becomes known to the tool for consideration in the **next round**. When multiple processors participate in the current round, do not write code assuming the second processor immediately sees a type the first processor just created; the reliable way is to wait for the compiler to advance to the next round.

### A Processing Round Is Not a “New `javac` Run”

All rounds belong to **the same invocation of the compiler tool**. They share the compiler environment, initialized processor instances, and `Filer` commitments within that invocation. Using multiple rounds does not mean `javac` spawns a new OS process, nor does it mean a build tool starts a new build task.

In standard OpenJDK builds, after annotation processing completes, the compiler continues with analysis and bytecode generation phases. Do not rely on an exact internal phase when designing processor contracts: what you can rely on are **the `ProcessingEnvironment`/`RoundEnvironment` APIs and the rules for files created across rounds**.

## 2. Core API Objects

| API | Role |
| --- | --- |
| `Processor` / `AbstractProcessor` | Processor interface, featuring `init`, `process`, and metadata on supported annotations/source versions |
| `ProcessingEnvironment` | Provides `Filer`, `Messager`, `Elements`, `Types`, compiler options, and source version |
| `RoundEnvironment` | Information **specific to one round**: root elements, annotated elements, `processingOver()`, and `errorRaised()` |
| `Element` / `TypeElement` | Compile-time program structure model: types, methods, fields, packages |
| `Filer` | Creates source/class/resource outputs per compiler protocol |
| `Messager` | Reports `NOTE`, `WARNING`, `ERROR` with element/location where available |
| `SourceVersion` | Declares Java release supported by the processor |
| `JavaFileObject` | Compiler-provided source/class file abstraction, with writer/output stream |

A typical processor:

```java
@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Analyze Elements of the current round.
        return true;
    }
}
```

The snippet above is an **illustrative skeleton**, not a self-compiling file yet: it needs `package`, `imports`, and an appropriate body. The complete example is in section 5.

A processor **does not work like runtime reflection**: it normally reads source structure through `Element` and `TypeMirror`, and should not use `Class.forName` to load application classes currently being compiled. Those classes may not yet have `.class` files or may contain errors.

## 3. Exact Meaning of `RoundEnvironment`

### `getRootElements()`

`roundEnv.getRootElements()` returns the root elements introduced into the **current round**. The first round usually sees top-level declarations in initial source files; subsequent rounds can see top-level declarations from generated source/class files of the prior round.

**Do not** assume a later round's root set contains every source already processed in earlier rounds. If full aggregation of results is required, the processor must maintain valid state across `process` calls or emit artifacts at an appropriate point.

### `getElementsAnnotatedWith(...)`

`roundEnv.getElementsAnnotatedWith(GenerateHello.class)` returns `Element` instances within the current round's scope marked with the relevant annotation, per API rules. This set can be **empty**, even when `process` is still called: for instance, a round with new files containing no annotations supported by the processor.

Do not take an empty annotation set as a reliable signal that “this is the final round”. **The termination signal is `roundEnv.processingOver()`**.

### `processingOver()`

`roundEnv.processingOver()` returns `true` when **types generated in this round will not be passed to a subsequent annotation processing round**. That is the primary flag for identifying the **final round**.

Use the following pattern:

```java
if (roundEnv.processingOver()) {
    // Record final results, generate no additional sources/classes.
    return true;
}
```

This snippet is a **fragment inside `process`**, not a complete file. The final round gives processors an opportunity to complete checks/aggregation; **it is not a round to “generate more code and let the compiler keep processing it”**. Attempting to create sources/classes in the final round does not open another round as desired, and `javac` may warn that files created in the final round will not be processed.

### `errorRaised()`

`roundEnv.errorRaised()` returns **`true` if an error was raised in the previous round**. It does not mean “any warning ever appeared in the whole compilation” and is not a duplicate of `processingOver()`.

Comparison table:

| Condition | Interpretation |
| --- | --- |
| `processingOver() == false` | Still a normal processing round; additional files may be generated per rules |
| `processingOver() == true` | Final round; do not expect a subsequent round to process new files |
| `errorRaised() == true` | An error was raised in the preceding round |
| `errorRaised() == false` | No error by that definition in the preceding round; does not prove the entire compilation definitely succeeded |
| `getElementsAnnotatedWith(...)` empty | No matching elements in the queried scope; **does not mean final round** |

When a processor calls `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ...)`, that is a **diagnostic error** causing compilation to fail per tool rules. A processor should not attempt to keep generating successful output once it knows source data is invalid. If `process` throws an unhandled exception, the tool may halt remaining processors; report errors via `Messager` whenever possible.

## 4. How Do Processors Persist Across Rounds?

Per `javax.annotation.processing.Processor`, the tool instantiates the processor object, calls `init(ProcessingEnvironment)`, queries supported annotation types/options/source version, and calls `process(...)` as appropriate.

**If a processor was invoked in one round, it will continue to be invoked in subsequent rounds, including the final round**, even when no matching annotations remain. No new processor object is created simply because compilation moved from round 1 to round 2.

Therefore, instance state fields can be used, such as:

```java
private boolean generated;
```

This variable helps prevent a processor from recreating **the same file** in every round. However, that state belongs only to **one specific invocation/compiler process** and is not persistent memory across two independent builds. If code creates multiple files, track by **processed file/type names** or a suitable idempotent model instead of an arbitrary single boolean.

### `return true` vs. `return false` in `process`

The return value of `process(Set<? extends TypeElement> annotations, RoundEnvironment roundEnv)` indicates whether the processor **claims the assigned annotation types**:

- `true`: the processor claims the requested annotation set; processors running later in the round are not asked to keep processing the claimed set under discovery rules.
- `false`: unclaimed; allows other processors to still be considered for those annotations.

**It does not mean** `true = file creation succeeded`, `false = file creation failed`, nor does `return false` create a new round on its own. **Only the appearance of newly registered/properly closed files** together with round rules determines the next processing round.

A processor supporting all annotations via `"*"` that always returns `true` can block other processors from receiving needed annotations. If writing a global processor that only validates/observes, typically **`return false`** so you do not monopolize all annotation types.

## 5. Complete Java 17 Example: Processor Generating a Class Used Immediately by the Program

The example has three source files (annotation, processor, app), built in two stages: **compile the processor first**, then **run the processor while compiling the app**. No libraries outside the JDK are needed.

### 5.1. Initial Directory Tree

```text
project/
└── src/
    ├── demo/
    │   ├── GenerateHello.java
    │   └── Main.java
    └── processor/
        └── HelloProcessor.java
```

**File `src/demo/GenerateHello.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {
}
```

`@Retention(RetentionPolicy.SOURCE)` fits annotations used only during source processing. The annotation does not need to exist at runtime for a processor to read it during compilation.

**File `src/processor/HelloProcessor.java`:**

```java
package processor;

import demo.GenerateHello;
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

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateHello.class)) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("demo.GeneratedHello", element);
                try (Writer writer = file.openWriter()) {
                    writer.write(
                            "package demo;\n" +
                            "public final class GeneratedHello {\n" +
                            "  private GeneratedHello() {}\n" +
                            "  public static String message() {\n" +
                            "    return \"Hello from generated code\";\n" +
                            "  }\n" +
                            "}\n");
                }
                generated = true;
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate demo.GeneratedHello: "
                                + exception.getMessage(),
                        element);
            }
        }
        return true;
    }
}
```

Points to note in the processor:

1. `@SupportedAnnotationTypes("demo.GenerateHello")` declares the exact annotation the processor understands. If no matching annotation is present initially, the tool may not invoke this processor.
2. `@SupportedSourceVersion(RELEASE_17)` publishes the processor's supported source version. The processor is compiled with a JDK supporting Java 17.
3. `roundEnv.processingOver()` is checked before any code generation operation. The final round creates no new types.
4. `generated` prevents attempting to create `demo.GeneratedHello` a second time within the same compilation. This example generates **a single class**; multiple input sources require an appropriate naming and tracking policy.
5. `createSourceFile("demo.GeneratedHello", element)` takes a **package-qualified type name**, not a file path, and does not manually prepend `src/` or `build/generated/`. Parameter `element` is the **originating element**, useful for incremental tools.
6. `try (Writer writer = file.openWriter())` ensures the writer closes, allowing the compiler to register the file for processing in the next round.
7. I/O errors are turned into `Diagnostic.Kind.ERROR` instead of being silently ignored.
8. `return true` claims the processed annotation, not controlling round count.

**File `src/demo/Main.java`:**

```java
package demo;

@GenerateHello
public final class Main {
    public static void main(String[] args) {
        System.out.println(GeneratedHello.message());
    }
}
```

Note: **`GeneratedHello` does not exist in the initial source tree yet**. The compiler itself invokes the processor to create this file, then inspects and compiles it before ending the invocation. This is the purpose of illustrating processing rounds.

### 5.2. Step One — Compile the Annotation and Processor

From inside the `project` directory, using JDK 17 or later supporting `--release 17`:

```sh
javac --release 17 -encoding UTF-8 -proc:none -d build/processor src/demo/GenerateHello.java src/processor/HelloProcessor.java
```

Because of `-proc:none`, this bootstrap step **only compiles the processor and annotation**, without running annotation processors in the same invocation. Output:

```text
build/
└── processor/
    ├── demo/GenerateHello.class
    └── processor/HelloProcessor.class
```

A successful compiler run usually prints no messages. The relative path `build/processor` resolves from the command's current working directory.

### 5.3. Step Two — Run the Processor While Compiling `Main`

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.HelloProcessor -s build/generated -d build/classes -XprintRounds -XprintProcessorInfo src/demo/Main.java
```

Explanation of each part:

| Option | Why it is needed |
| --- | --- |
| `-cp build/processor` | Lets `Main.java` see the `demo.GenerateHello` annotation type at compile time |
| `-processorpath build/processor` | Lets the compiler **load the processor** from bootstrap output |
| `-processor processor.HelloProcessor` | Selects the processor **explicitly** by fully-qualified name, needing no service-discovery file |
| `-s build/generated` | Selects the directory for storing **generated source files** from `Filer.createSourceFile` |
| `-d build/classes` | Selects the directory for storing **class files** emitted by the compiler |
| `-XprintRounds` | Displays round information (`javac` diagnostics) |
| `-XprintProcessorInfo` | Displays which processor handles which annotations / is called in rounds |

This is a **concrete command, independent of default processor autodiscovery**. Different JDKs have different automatic processor-execution policies; specifying `-processor` explicitly avoids relying on defaults, especially on newer JDKs.

After successful compilation, key outputs related to the example:

```text
build/
├── processor/
│   ├── demo/GenerateHello.class
│   └── processor/HelloProcessor.class
├── generated/
│   └── demo/GeneratedHello.java
└── classes/
    └── demo/
        ├── GeneratedHello.class
        └── Main.class
```

`GeneratedHello.java` **was created by the processor**; `GeneratedHello.class` was compiled by `javac` from that file during the same step-two invocation. `build/processor` holds the build-time classpath, not the runtime classpath required by the sample application.

### 5.4. Step Three — Run the Application

```sh
java -cp build/classes demo.Main
```

**Exact stdout:**

```text
Hello from generated code
```

The program uses neither reflection nor manual class loading. `Main` calls the static method of the processor-generated class directly. The JVM only needs the classes in `build/classes` to run this example; `SOURCE` retention on `@GenerateHello` does not require the annotation class at runtime.

### 5.5. Step Four — Observe the Number of Rounds

The `-XprintRounds` option typically reveals three rounds involved in the example:

| Round | Primary roots | Matching annotations | `processingOver()` |
| --- | --- | --- | --- |
| 1 | `demo.Main` | `demo.GenerateHello` | `false` |
| 2 | `demo.GeneratedHello` | No `GenerateHello` in new class | `false` |
| 3 (final) | Empty root set | None | `true` |

This is an **explanatory table of expected behavior** and does not claim logs match the table verbatim in line order, bracketing, or every detail across all JDKs. In this example, only one new source file is emitted in round 1; round 2 has no new files; then the final round runs.

Notably, `HelloProcessor` **is still invoked in round 2 and the final round** after being invoked in round 1, even though `roundEnv.getElementsAnnotatedWith(GenerateHello.class)` is empty in those rounds. That explains why branching on `processingOver` and managing generated state is necessary.

## 6. When Does a New File Trigger a Next Round?

Not every file-write operation in a processor has the same effect.

| API / action | Effect on annotation processing |
| --- | --- |
| `Filer.createSourceFile("demo.X")` and close writer | Source is **registered** for processing consideration in the next round |
| `Filer.createClassFile("demo.X")` and close stream | New class file is considered by the tool in the next round per `Filer` contract |
| `Filer.createResource(...)` | Creates auxiliary resource; **not** registered as source/class to trigger a new annotation round |
| Write file via `Files.write(...)` outside `Filer` | Compiler is not guaranteed to recognize or feed the file into a new round |
| Emit only diagnostics/console logs | Creates no new types; does not create a round on its own |
| Old code remaining in `build/generated` from prior build | Not automatically a newly generated file of this invocation, unless compiler/tool is configured to read it or processor generates it properly |

Per `Filer`, a new file created in one round is considered in the **subsequent round after closing its `Writer`/`OutputStream`**. Creating a resource solely to store ordinary metadata does **not** add another round, even if the resource name resembles `.java` or `.class`.

The event of **a new source/class file being created** matters more than whether the processor code invokes `process`, `getElementsAnnotatedWith`, or `return false`.

### Why Use `Filer` Instead of Creating Files Manually?

`Filer` manages logical output locations, type names, collision prevention, originating element relationships, and notifying the compiler that files were created. Writing files arbitrarily via `java.nio.file.Files` can leave the compiler unaware of new sources, causing app code referencing `GeneratedHello` to fail with `cannot find symbol` even though the file is on disk.

For **generated source** outputs, use `Filer.createSourceFile`; if output is an auxiliary file serving an annotation processor, use `createResource` with an appropriate location.

## 7. Termination Conditions: “No More Files Generated” and the Final Round

In the standard model:

1. The compiler starts with inputs fed to processing and runs matching processors.
2. If processors create additional **source/class files** through `Filer`, the new files are examined in the **next round** after closing the output streams.
3. If even more source/class files appear, corresponding rounds continue.
4. When a round **creates no new source/class files to process**, the compiler executes a **final round**.
5. In the final round, participating processors can summarize/verify, yet cannot expect newly created files to be processed by another round.
6. After annotation processing, if compilation was not aborted and processing-only mode is not active, the compiler finishes generating class files for valid sources.

**Do not use the number “round 3” as a universal stop marker.** A processor creating source A containing an annotation that causes another processor to create source B, which in turn generates source C, will have more rounds. If file-creation logic continues without a stopping condition, builds can run very long or fail with errors; the processor itself must ensure code generation reaches a sensible **fixed point**.

The reliable termination signal while a processor runs is **`roundEnv.processingOver()`**, not “`process` was called twice”, “annotations are empty”, or “nothing new in logs”.

### Processor Pattern with Final-Round Handling

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Summarize collected state; generate no sources/classes.
        return false;
    }
    // Iterate over elements of the current round.
    return false;
}
```

This is merely an **illustrative method fragment** inside an `AbstractProcessor`, not a complete source file. `return false` here is a choice about **claiming annotations**, unrelated to whether the round is final.

### When Errors Occur

If a processor or the compiler reports an error in a round, `errorRaised()` may be `true` in the subsequent round; the compiler may end generating further rounds early and transition to a final notification round depending on error state. Processors must prioritize **emitting accurate diagnostics**, rather than pushing forward through the pipeline assuming the build still succeeds.

Do not treat `processingOver() == true` as proof that compilation **succeeded**: a final round can also happen after errors occurred.

## 8. `FilerException` and the Duplicate File Creation Problem

A crucial rule: **within one annotation processing invocation, the same pathname/type must not be created via `Filer` multiple times**. For example, if a processor attempts again to run:

```java
processingEnv.getFiler().createSourceFile("demo.GeneratedHello");
```

in round 2 for the same type already created in round 1, `Filer` usually throws **`FilerException`**. Per the API, both source and class files with the same type name or colliding with initial input types can also be rejected.

### Distinguish Two Cases

- **Recreating in the same invocation:** Risks `FilerException` even when called in a different round. The `generated` flag in section 5 guards precisely this single-type generation case.
- **Output file left from an earlier invocation:** `Filer` may manage/truncate output on first creation in a new invocation per its rules; do not conclude every existing file on disk automatically causes `FilerException`. However, stale files no longer matching inputs can cause stale code if the build tool does not clean/declare sources properly.

**Do not “fix” `FilerException` by deleting files while the processor is running.** Fix the naming algorithm, avoid generating twice, use originating elements, and let the build tool manage outputs. If multiple annotated elements all try generating the same `demo.GeneratedHello` name, design a way to aggregate **once** or generate a unique name per element.

### Note on Types/Paths

`createSourceFile` takes a Java package-qualified type name, such as `demo.GeneratedHello`, **not** `"build/generated/demo/GeneratedHello.java"`. The output directory comes from `javac -s` or compiler configuration; it is not part of the type name. Using a wrong file path can trigger `FilerException` or generate code in the wrong package.

## 9. Choosing How to Run and Observe Annotation Processors

| `javac` option | Effect |
| --- | --- |
| `-processor processor.HelloProcessor` | Selects specified processor by package-qualified name |
| `-processorpath path` / `--processor-path path` | Where to find/load processor classes and required dependencies |
| `-classpath path` / `-cp path` | Where source finds dependent classes/annotations; not synonymous with `-processorpath` |
| `-s dir` | Destination for generated **source files** |
| `-d dir` | Destination for generated/final **class files** |
| `-proc:only` | Runs annotation processing **without compiling final application classes** |
| `-proc:none` | Disables annotation processing |
| `-XprintRounds` | Diagnostics for processing rounds |
| `-XprintProcessorInfo` | Diagnostics showing which processors participate |
| `-Akey=value` | Supplies custom options to processors supporting the key |
| `--processor-module-path path` | Where to find processors packaged as modules per module mechanism |

### `-proc:only` to Inspect Generated Source

Once the processor is bootstrapped in step 5.2, run:

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.HelloProcessor -s build/generated-only -d build/classes-only -proc:only -XprintRounds src/demo/Main.java
```

The compiler runs annotation processing and writes generated sources, yet **does not emit application class files** via normal compilation. This is a way to inspect `GeneratedHello.java` before deciding to compile separately or run normal mode.

Do not rely on `build/classes-only/demo/Main.class` being created by `-proc:only`, because this mode's goal is **processing only**. Depending on configuration, processors proactively emitting class files via `Filer.createClassFile` may produce separate outputs; distinguish that from final application compilation.

### Discovering Processors via Service Providers

Besides explicit `-processor`, tools can discover processors via the service provider mechanism. Traditional classpath processor JARs usually contain:

```text
META-INF/services/javax.annotation.processing.Processor
```

Example content:

```text
processor.HelloProcessor
```

The two lines above are **a resource name and service file content**, not shell commands. The processor must have a public no-arg constructor and be loadable from the processor path. For processors in named modules, module descriptors/`provides` and `--processor-module-path` have separate rules.

To **avoid depending on default changes across JDK versions**, the primary example uses explicit `-processor processor.HelloProcessor`. If compilation does not invoke the processor, check whether `-proc:none` is enabled, whether processor path configuration is valid, whether compiler/tool autodiscovery is active, and whether annotations supported by the processor are actually present.

## 10. Running Multiple Processors: What Is and Is Not Guaranteed?

Suppose:

- `ProcessorA` reads `@Model`, generates `model.GeneratedDescriptor`.
- `ProcessorB` reads `@Descriptor`, generates `consumer.GeneratedClient`.

If `GeneratedDescriptor` carries `@Descriptor`, normally `ProcessorB` sees the new annotation in the **next round** after A's source is created/closed. Do not expect B to see an `Element` that does not exist yet in the current round merely because A just called `createSourceFile`.

Principles making processors more compatible:

1. **Order independence:** Avoid relying on the order in which the tool invokes processors within one round, unless a specific build-system contract exists.
2. **Consistency:** Processing identical inputs yields identical outputs; avoid randomness, current timestamps, or unstable set iteration orders.
3. **No overlapping outputs:** Every generated type has clear ownership and naming rules.
4. **Do not rely on another processor generating files immediately in the same round:** Generated-code dependencies should be resolved via the next round or a dedicated design contract.
5. **Handle empty annotations:** `annotations` or `getElementsAnnotatedWith(...)` can be empty even when `process` is called.
6. **Do not retain `Element`s indefinitely:** Elements/TypeMirrors belong to the invocation's processing environment; caching references across compiler invocations is invalid.
7. **Claim appropriate scope:** `return true`/`false` affects processor discovery of annotation types, not creating/stopping rounds.
8. **Termination condition:** Generated code must converge to a state where no further types need creation.

JSR 269 recommends the properties **orthogonality, consistency, commutativity, independence** so processors run together without order-dependent outputs or hard-to-reproduce side effects.

## 11. Incremental Builds and Stale Generated Code

Annotation processing rounds operate **within one compilation invocation**; incremental build is a **build tool** feature tracking changes across invocations. The two concepts are related yet not synonymous.

If a `@GenerateHello` source is deleted, the build tool must know whether `GeneratedHello.java/.class` is still needed or should be removed from artifacts. A processor cannot rely solely on `generated = true` (an object field in the current invocation) to manage files persisting across multiple builds.

Design suggestions:

- Pass `originatingElements` to `Filer.createSourceFile` so build tools know which elements produced the generated file; these are **hints**, not guarantees that every tool implements incremental builds identically.
- Avoid gratuitously reading arbitrary files outside the processing environment, and avoid writing outputs to arbitrary directories not managed by the build tool.
- Define stable naming and ordering, especially for aggregating processors creating one file from multiple elements.
- Never manually edit generated sources. The source of truth is the input annotations/sources plus the processor.
- Configure a dedicated generated-source directory, avoiding mixing with human-edited source trees.
- If suspecting stale classes, use the project's clean build to re-verify — clean only **owned build output directories**.

Use two types of tests: **clean builds** to confirm code generation logic works properly and **incremental rebuilds** to verify stale files are handled sensibly. Round outcomes in a single invocation do not guarantee incremental correctness.

## 12. Common Errors and How to Fix Them

| Symptom | Common cause | Investigation direction |
| --- | --- | --- |
| `cannot find symbol: GeneratedHello` | Processor did not run, does not support annotation, failed to emit/close file, or generated source has errors | Check `-processor`, `-processorpath`, `-s`, output, and `-XprintRounds` logs |
| `Annotation processor ... not found` | Processor class not on processor path or wrong name/configuration | Compile processor first, use fully-qualified class name |
| `Attempt to recreate a file for type ...` | Same type recreated via `Filer` | Track generated type names, avoid duplicate creation across rounds |
| `processingOver()` is true yet still trying to generate code | Algorithm did not converge before final round | Only summarize in final round; generate code in earlier rounds |
| `getElementsAnnotatedWith(...)` empty in round 2 | New type lacks annotations supported by processor | Do not equate empty set with final round |
| Generated `.java` exists yet `.class` is missing | Used `-proc:only`, generated source has errors, or compilation failed | Check mode, diagnostics, class output `-d` |
| Directory `-s` is empty | Processor only validates without generating source, or emits class/resource instead of source | Check `Filer` calls and output kinds |
| Error in earlier round yet `process` still called once more | Processor lifecycle includes final callback | Use `errorRaised()` to know prior round had errors; create no new outputs |
| Clean build succeeds, incremental build fails | Stale generated files, undeclared processor dependencies, or unstable naming | Check originating elements, task inputs/outputs, clean/rebuild |
| Two processors generate the same type | Output ownership conflict | Separate naming or coordinate the responsible class |
| New source generated in final round is not processed | Final round opens no further round | Generate types before final round; only summarize at end of rounds |

### Step-by-Step Investigation Sequence

1. **Inspect exact command:** `javac -version` and all `-processor`/`-processorpath`/`-cp`/`-s`/`-d`/`-proc:...` flags.
2. **Inspect inputs:** Does the annotation type have proper retention, package/name, and target elements? Is the annotated code included in source/compiler inputs?
3. **Enable round logs:** Use `-XprintRounds` and `-XprintProcessorInfo` in a debug environment.
4. **Confirm new file:** Does the generated source have the right package/type name? Was the writer closed? Is output under `-s`?
5. **Identify next round:** Do newly generated source/class files appear as roots? If not, verify `Filer` usage and stream closing.
6. **Inspect final round:** Does the processor have a `processingOver` branch avoiding final output creation? Were there errors from an earlier round?
7. **Use diagnostics, not guesses:** `Messager` emits positioned errors/warnings better than `System.out.println`.
8. **Verify final artifacts:** Run the normally compiled program; do not mistake a prior compile's stale outputs for new compile success.
9. **Test cooperating processors together:** Do initialization and annotation claiming interfere with each other?
10. **Compare clean vs. incremental builds:** Ensure generated files are neither missing nor duplicated.

## 13. Misconceptions to Avoid

**“One annotation means the processor calls `process` only once.”** False. Once participating, a processor can be invoked across multiple rounds, including the final round.

**“`annotations.isEmpty()` means we are done.”** False. A processor may be called in a round with new root types carrying no matching annotations. Use `processingOver()`.

**“`return true` stops annotation processing.”** False. It claims annotation types; it is not a round-stopping switch.

**“`Filer.createResource` makes a new source appear in the next round if named `.java`.”** False. Resources are not registered for processing as source files.

**“After creating a file, closing the Writer is unnecessary.”** False. The API registers new files for the next round after the output stream closes; use try-with-resources.

**“A file generated in round 1 is read immediately by all processors in round 1.”** False. It is examined in the **subsequent round** per file-creation rules.

**“Reaching the final round means compilation succeeded.”** False. Compilation can fail from diagnostic errors or errors in generated sources; the final callback is not a success callback.

**“Processors are re-instantiated every round, so state fields are useless.”** False. One processor object spans rounds within the same invocation; instance state must be managed carefully.

**“`FilerException` is always caused by files from a previous build.”** False. Attempting to create the same pathname/type twice **within the same invocation** is an explicit cause; `Filer` rules for pre-existing output files differ from recreation within one run.

**“Using `-s` means `.class` files already exist.”** False. `-s` specifies generated source output; `-d` specifies class output, while `-proc:only` skips final application compilation.

**“The termination condition is a fixed number of rounds.”** False. Round count depends on new files actually created by processors and error states; never hard-code round indices to emit code.

## 14. Checklist for Designing a Safe Processor

- [ ] Accurately declared `@SupportedAnnotationTypes` and `@SupportedSourceVersion`?
- [ ] Processor has a public no-arg constructor and is loadable from processor path/module path?
- [ ] Understood `getRootElements()` returns roots only of the **current round**?
- [ ] Distinguished `processingOver()` from an empty annotation set?
- [ ] Handled/noted `errorRaised()` properly as **an error in the previous round**?
- [ ] Code generated via `Filer.createSourceFile`/`createClassFile` with writer/stream closed?
- [ ] Never recreates the same source/class output multiple times in one invocation?
- [ ] Avoids attempting to generate new code in the final round?
- [ ] `return true`/`false` chosen per annotation claiming policy, not used as a stop condition?
- [ ] `-s` and `-d` outputs separated, without mixing generated sources with handwritten sources?
- [ ] Tried `-XprintRounds`, `-XprintProcessorInfo`, and `-proc:only` when debugging?
- [ ] Tested outcomes on both clean builds and incremental rebuilds when using build tools?

**Key takeaway:** Annotation processing operates in multiple rounds within **a single compilation**. **Source/class files generated via `Filer` after closing their output streams** become inputs for the next round; once no files remain to process, the tool runs a **final round** with `processingOver() == true`. Processors must generate code before the final round, avoid duplicate creation, and treat `return true` strictly as **claiming annotations**, not “ending the build”.

## Official References

- Java SE 17 `Processor` — processing rounds, final round, lifecycle, and `process` semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Java SE 17 `RoundEnvironment` — `processingOver()`, `errorRaised()`, roots, and annotated elements: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Java SE 17 `Filer` — generated source/class files, closing writers, resource files, and `FilerException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html
- Oracle JDK 17, *The javac Command* — annotation processing rounds, `-processor`, `-s`, `-d`, `-XprintRounds`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- JSR 269 — Pluggable Annotation Processing API: https://jcp.org/en/jsr/detail?id=269
