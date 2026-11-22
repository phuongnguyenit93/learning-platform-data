# Position of Annotation Processing in the Java Compilation Cycle

## 1. Where Does Annotation Processing Sit?

**Annotation processing** is an extension step of the Java compiler where one or more *annotation processors* read the program's declaration model (classes, interfaces, methods, fields, annotations...) and can create additional source files, resource files, or emit diagnostic messages. The standard API is **JSR 269** in the packages `javax.annotation.processing`, `javax.lang.model`, and `javax.tools`. The `javax` prefix here remains the package name in modern Java SE; it is not changed to `jakarta.annotation.processing`.

In a simplified mental model of `javac`, annotation processing takes place **after the compiler has enough information from sources to build the initial element model and before completing type checking, desugaring, and bytecode generation for the entire program**. If a processor generates additional Java sources, the compiler must feed those sources back into the pipeline to be processed and compiled.

~~~text
Initial .java
    |
    v
Read/decode source -> parse syntax -> record declarations and initial symbols
    |
    v
+---------------------------------------------------------+
| ANNOTATION PROCESSING — JSR 269                         |
| Round 1: process elements in input sources              |
|   -> processor may generate additional .java / .class   |
| Round 2, 3, ...: process newly generated files (if any) |
| Final round: signal processingOver = true               |
+---------------------------------------------------------+
    |
    v
Remaining type analysis and semantic checks
    -> control-flow checking, definite assignment
    -> desugaring, preparing lower representation
    -> generate .class bytecode
~~~

The diagram describes the **logical relationship** of the steps, without claiming that `javac` always completes all type attribution after processing or never checks any types before invoking a processor. The compiler may need to resolve/attribute part of the tree to supply the declaration model to the processor; internal processing stages can also vary across JDK versions. The key contract is that the processor receives the *language model* of elements and rounds, can generate additional inputs for the same compilation run, and only then does `javac` finish processing all files to be compiled.

**Point of distinction:** annotation processing is a **compile-time** activity, not the JVM scanning annotations and executing logic after the application has started. An annotation with `RetentionPolicy.RUNTIME` may still be visible via reflection at runtime, yet having or lacking runtime retention **does not determine** whether a processor can handle the annotation during compilation.

## 2. Why Must the Compiler Have This Step?

For example, a class bears `@GenerateGreeting`, while the application uses `GeneratedGreeting` even though that class's source code has not been handwritten. If a processor creates `GeneratedGreeting.java` during compilation, the final program can still be valid:

~~~java
@GenerateGreeting
class Marked {}

// In another Java file:
System.out.println(GeneratedGreeting.message());
~~~

The two illustrative lines above are **not a standalone Java program**. The complete workflow in section 5 will create the class and run.

Without annotation processing (and without a pre-existing `GeneratedGreeting` class on the classpath), the compiler cannot resolve the reference `GeneratedGreeting`. With processing properly configured, the processor generates the source before compilation ends; the new source enters the rounds and gets compiled alongside related sources.

Common uses: generating mapping code, generating metadata, enforcing design rules at compile time, generating service registration code, generating factories/builders, or supporting frameworks. However, the standard mechanism **does not modify methods inside an already-written class by itself**; many libraries that “alter visible syntax” additionally rely on compiler plugins or internal APIs.

## 3. Components of JSR 269 and Their Roles

| Component | Role |
| --- | --- |
| `javax.annotation.processing.Processor` | Interface invoked by the compiler on each round. |
| `AbstractProcessor` | Convenient base class for writing processors. |
| `ProcessingEnvironment` | Provides access to `Filer`, `Messager`, `Elements`, `Types`, and `-A...` options. |
| `RoundEnvironment` | Reports the round's root elements, annotated elements, completion status, and errors. |
| `TypeElement`, `Element`, `TypeMirror` | Compile-time declaration and Java type model; distinct from runtime reflection `Class<?>` objects. |
| `Filer` | Creates sources, classes, or resources; compiler manages output paths and detects duplicate writes. |
| `Messager` | Emits notes, warnings, and errors with element positions for `javac` diagnostics. |
| `@SupportedAnnotationTypes` | Declares annotation names (or patterns) supported by the processor. |
| `@SupportedSourceVersion` | Declares the source language level supported by the processor. |

A processor typically implements:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Read the element model and optionally generate files in the current round.
    return true;
}
~~~

This is a **method excerpt** belonging to a processor class, not a standalone Java file. The `annotations` parameter contains the annotation types requested to be processed in that round; it may be empty, including on the final round. `true` means the processor **claims** the annotations it handles so subsequent processors are not asked about the same annotations under the processor selection mechanism; `false` allows other processors to continue being considered. This boolean is **not a success/failure flag**, nor does it directly decide whether a new round is created. New rounds are tied to new files created by processors.

Processors can be invoked via service provider discovery or explicitly specified on the CLI. They run inside the **build tool's compiler JVM** and have their own classpath/module path for processor dependencies. Code generated by the processor will be **compiled into the target program**; the two environments must be distinguished when declaring dependencies.

## 4. Rounds and Where Sources Are Generated

Consider a compilation with a processor:

1. `javac` reads the initial sources, builds the necessary parts of the language model, and locates matching processors.
2. **Round 1:** the processor receives root elements of the input sources. It can read elements marked with annotations, emit diagnostics, and call `Filer.createSourceFile(...)`.
3. **Round 2:** if the previous round created new Java sources/classes fed into processing by the compiler, the compiler supplies the new root elements. Participating processors may continue to be called. Do not treat this as a brand-new `javac` invocation.
4. **Subsequent rounds:** the cycle repeats while new inputs keep arriving. Processors should avoid continuously generating unnecessary files.
5. **Final round:** `roundEnv.processingOver()` equals `true`. This is the opportunity to finalize work, clean up state, or perform aggregate checks. **Do not rely on generating additional Java sources in the final round for them to be processed in a new round.**
6. After processing finishes with no blocking errors, the compiler proceeds with remaining analysis/compilation steps and generates bytecode for classes requiring `.class` output.

Two easily confused states:

- `processingOver()`: marks the **final round**. It does not mean `process()` was called with the same annotated elements as the first round.
- `errorRaised()`: indicates an error was raised **in a previous round**. It does not mean all errors have finished being checked at the moment of the call, and the processor must still handle the final round safely.

**There is no guarantee every annotation is processed by a processor strictly once in an entire invocation.** The round model can introduce new root elements, other annotations, and a final call with an empty annotation set. Shared state across rounds should be managed carefully; incremental builds also involve independent invocations.

## 5. Complete Example: A Processor Creating a Class Used by the Application

Use **JDK 17 or above**. This example was verified with `javac --release 17`: the processor generates `demo.GeneratedGreeting` in round 1; round 2 receives the generated source; round 3 finishes; class `demo.App` runs and prints `Hello generated!`.

### 5.1. Initial Source Layout

~~~text
project/
  src/
    ap/
      GreetingProcessor.java
    demo/
      GenerateGreeting.java
      Marked.java
      App.java
  build/
    processor-classes/
    classes/
    generated/
~~~

The `build` directories start empty; `javac` will populate classes and generated sources accordingly.

**File `src/demo/GenerateGreeting.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
~~~

`SOURCE` means the annotation serves source code and does not need to appear in the class file at runtime. Processors can still receive it during compilation.

**File `src/ap/GreetingProcessor.java`:**

~~~java
package ap;

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

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean created;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver() || created) {
            return false;
        }

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateGreeting");
        if (annotation == null) {
            return false;
        }

        for (Element element : round.getElementsAnnotatedWith(annotation)) {
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("demo.GeneratedGreeting", element)
                    .openWriter()) {
                writer.write("package demo; public final class GeneratedGreeting { "
                        + "public static String message() { return \"Hello generated!\"; } }");
                created = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString(), element);
            }
        }
        return true;
    }
}
~~~

Explanation:
- `@SupportedAnnotationTypes` declares the processor handles `demo.GenerateGreeting`.
- `getTypeElement` and `getElementsAnnotatedWith` access the **declaration model** supplied by the compiler.
- `createSourceFile("demo.GeneratedGreeting", element)` creates the Java source by fully qualified name, attaching `element` as the related *originating element* to help build tools track dependencies.
- `try-with-resources` closes `Writer` so the compiler receives the completed source. The `created` flag avoids recreating the same file again. In production code, add a strategy for detecting name collisions and handling multiple annotated elements; this lesson intentionally uses one sample element.
- When `Messager` emits `ERROR`, the compiler normally cannot produce output successfully. `return true` still only concerns **claiming the annotation**.

**File `src/demo/Marked.java`:**

~~~java
package demo;

@GenerateGreeting
public class Marked {}
~~~

**File `src/demo/App.java`:**

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
~~~

There is no `GeneratedGreeting.java` in `src/demo` yet; that is the very source to be created in the processing round.

### 5.2. Compiling in Two `javac` Invocations

From the `project` directory, create `build/processor-classes`, `build/classes`, and `build/generated`. In Bash, you can use:

~~~bash
mkdir -p build/processor-classes build/classes build/generated
~~~

In PowerShell, you can use `New-Item -ItemType Directory -Force` for these three paths. Below are two separate invocations so the bootstrap order is explicit.

**Pass 1: compile the annotation and processor first**, so the compiler on the next pass can load `ap.GreetingProcessor`:

~~~bash
javac --release 17 -encoding UTF-8 -d build/processor-classes \
  src/demo/GenerateGreeting.java src/ap/GreetingProcessor.java
~~~

**Pass 2: compile the application with the specific processor enabled**:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp build/processor-classes \
  -processorpath build/processor-classes \
  -processor ap.GreetingProcessor \
  -XprintRounds \
  -s build/generated \
  -d build/classes \
  src/demo/Marked.java src/demo/App.java
~~~

The line-continuation `\` above is for **Bash**; in PowerShell or `cmd.exe`, put each `javac` command on one line or use the line-continuation symbol for your shell.

Meaning of key options:
- `-processor ap.GreetingProcessor`: selects the exact processor to run; no service descriptor is needed for this example.
- `-processorpath build/processor-classes`: where the compiler finds and loads the processor and its dependencies.
- `-cp build/processor-classes`: where application sources locate the `demo.GenerateGreeting` annotation definition.
- `-s build/generated`: destination to save **sources generated by the processor**.
- `-d build/classes`: destination to save **compiled bytecode**.
- `-XprintRounds`: prints round info for observation; this is a `javac` diagnostic option.

Diagnostic output observed with `javac` when running the example:

~~~text
Round 1:
    input files: {demo.Marked, demo.App}
    annotations: [demo.GenerateGreeting]
    last round: false
Round 2:
    input files: {demo.GeneratedGreeting}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Whitespace and layout of `-XprintRounds` may vary across JDKs. What to note is that `demo.GeneratedGreeting` appears in **round 2**, even though it was not among the initial `src/...java` inputs. Round 3 is the final round, not another compilation stage.

Then run:

~~~bash
java -cp build/classes demo.App
~~~

Exact stdout:

~~~text
Hello generated!
~~~

Key artifacts:

~~~text
build/
  generated/
    demo/
      GeneratedGreeting.java
  processor-classes/
    ap/
      GreetingProcessor.class
    demo/
      GenerateGreeting.class
  classes/
    demo/
      App.class
      Marked.class
      GeneratedGreeting.class
~~~

Notice `GenerateGreeting.class` resides in `processor-classes` because it was compiled in pass 1; it does not necessarily reappear under `build/classes` when pass 2 only passes `Marked.java` and `App.java`. When packaging an application, manage annotation API and processor dependencies according to their truly needed scopes. A processor does not have to be on the runtime classpath simply because it ran during the build.

### 5.3. Why Does Compilation Succeed Even Though App Calls a Not-Yet-Existing Class?

At the start of the second invocation, `javac` already knows `App` references `GeneratedGreeting`, yet cannot yet complete all type-linking checks. The processor creates `build/generated/demo/GeneratedGreeting.java` during the first round. The compiler adds this file as a source for the next round and uses its definition to complete compilation. If you remove the processor options, have no other `GeneratedGreeting` source/class, and have a clean `build/classes` directory, the build reports an error like `cannot find symbol`.

Precisely because rounds must coordinate, annotation processing **sits inside the compile pipeline**, rather than being a script step occurring after all `.class` files have been generated.

## 6. How javac Discovers Processors

Besides specifying `-processor` by name, a JAR containing a processor can have the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Containing the fully qualified implementation name, e.g.:

~~~text
ap.GreetingProcessor
~~~

Service provider discovery helps `javac` locate processors on the **processor path**. If packaged inside a Java module configured via the module path, providing processors through `module-info.java` and `--processor-module-path` can also be used. The example in section 5 uses `-processor` because it makes clear which processor runs and reduces reliance on discovery.

**Important change from JDK 23:** `javac` **no longer automatically runs a processor just because it happens to find it on the classpath** if the invocation lacks explicit processing configuration. To actively enable processing, pass `-processor`, `-processorpath`/`--processor-path`, `--processor-module-path`, or an appropriate `-proc:full` or `-proc:only` policy. The older classpath auto-discovery policy could trigger unintended processors; it is best to **explicitly specify required processors and paths**.

Processing modes:

| Option | Meaning |
| --- | --- |
| `-proc:none` | Disables annotation processing; `javac` still compiles ordinary Java sources. |
| `-proc:only` | Runs annotation processing without performing the ordinary bytecode compilation step after processing. Suitable when only processor-generated output is needed. |
| `-proc:full` | Runs annotation processing **and** continues compilation. |
| `-processor a.b.Processor` | Explicitly specifies the processor list; the example in section 5 uses this approach. |
| `-processorpath ...` | Path to load processors; if unconfigured, the tool may search the classpath per JDK version policy. |

`-proc:full` is an explicit choice for tools supporting it; on older JDK updates, exact support depends on version. The example in this lesson uses `-processor`, so it works on JDK 17 and above without relying on default auto-discovery behavior.

The `-Akey=value` option passes custom options to the processor, accessed via `processingEnv.getOptions()`; it does **not** automatically enable or discover processors when the compiler is not configured to execute processors.

## 7. Boundary Between Annotation Processors and Compiler Phases

Standard annotation processors have capabilities defined via the **language model** and **Filer**:

- Read names, modifiers, types, methods, fields, and annotations of declarations.
- Check types via `Types`, look up symbols via `Elements`.
- Emit diagnostics using `Messager`.
- Create sources/classes/resources via `Filer`, for the compiler and build tool to handle.

Standard processors **have no contract to directly modify the AST of an existing class**, are not guaranteed to be invoked at a fixed point inside every internal `javac` analysis step, and do not receive callbacks for each bytecode instruction. Tools wishing to alter ASTs or hook deeply into the compiler can use `com.sun.source.util.Plugin`, `com.sun.source.tree` APIs, `TaskListener`, or `javac` internals, yet those are different mechanisms from pure JSR 269 with their own constraints and stability levels.

Differences from commonly confused mechanisms:

| Mechanism | Timing | Main inputs and outputs |
| --- | --- | --- |
| **Annotation processing (JSR 269)** | During compilation, across processing rounds | Reads declarations/annotations, validates, creates sources/classes/resources. |
| **Lombok and compiler internals** | Integrated into compilation, beyond pure JSR 269 contract | Can intervene in AST/bytecode structure via proprietary mechanisms. |
| **Reflection** | Runtime | Reads metadata of already-loaded classes. |
| **Java agent / instrumentation** | When loading or running classes, depending on mechanism | Transforms bytecode at runtime. |
| **KAPT / KSP** | Kotlin build pipeline | Has dedicated mechanisms to access Kotlin program representations; not equated with javac JSR 269. |
| **Pre-build code generation** | Before compiler invocation, by a separate build task | Creates sources first and feeds them into source sets for compilation. |

## 8. Build Tools and Generated Source Paths

In real projects, Maven or Gradle normally builds compile/processor paths and invokes the compiler on the developer's behalf. The model remains:

~~~text
Resolve dependencies + processors
             |
             v
Compile task invokes javac with processor configuration
             |
             +--> annotation processing rounds
             |      +--> generated sources / resources
             |
             +--> compile original + generated Java sources
             |
             v
Classes output + generated-source output
~~~

**Maven:** versions of the Maven Compiler Plugin support `annotationProcessorPaths` or declaring processor dependencies via the plugin version's corresponding mechanism. Configure processors explicitly, especially when upgrading to JDK 23+. Check your Maven Compiler Plugin version and effective POM before copying configuration; configuration element names vary across plugin generations. Distinguish **compile dependencies** for source code using annotations from **processor dependencies** so the build tool runs the processor.

**Gradle (Java plugin):** annotation processor dependencies are typically declared via the `annotationProcessor` configuration, for instance:

~~~groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:processor:1.0'
}
~~~

This is a **sample snippet** in `build.gradle`, not real dependencies to download directly; replace with artifact coordinates of actual libraries. Gradle configures the annotation processor path for `JavaCompile` tasks and tracks generated sources. Many plugins provide separate compile-only annotation APIs and processor artifacts to avoid placing processors on the runtime classpath.

When encountering a “generated class not found” error, check:
1. Was the processor actually loaded and run (flags and JDK version)?
2. Is the annotation supported by the processor and present in the first round?
3. Did the processor generate the right package/file name; does the generated file have compilation errors?
4. Do the IDE and build tool use the same generated-source directory and compiler invocation?
5. Did incremental compilation/caching omit processor inputs, outputs, or dependencies?

Do not fix this by manually copying generated `.java` files into the main source directory if the processor itself is the source of truth; that easily causes duplicate classes and lets stale outputs mask generation bugs.

## 9. Diagnostics, Errors, and Testing Processors

Useful tools when investigating:

~~~bash
javac -XprintRounds -XprintProcessorInfo ...
~~~

The command above is an **option template**; `...` must be replaced with the full classpath, processor path, processor name, and source file names as in section 5. `-XprintRounds` shows rounds; `-XprintProcessorInfo` displays which processor is asked about/claims which annotations. When checking the pipeline without normal bytecode emission, `-proc:only` can be used. When eliminating processing to determine whether an error comes from this step, use `-proc:none` with sources that do not depend on generated classes.

Common errors:

- **Processor does not run:** not specified, missing service descriptor, missing `-processorpath`, incompatible JDK, or JDK 23+ default rules disabled implicit discovery.
- **`Annotation processor ... not found`:** processor implementation not compiled/packaged, wrong fully qualified name, or processor path missing the required artifact.
- **`FilerException: Attempt to recreate a file`:** processor recreated the same Filer path within one processing run, or collided with an existing source. Use accurate file names and guard generation logic across multiple rounds.
- **`cannot find symbol` for a generated type:** processor failed to generate the file, generated the wrong package, generated source has syntax errors, or the compiler did not pick up source output.
- **`NoClassDefFoundError` when loading processor:** a dependency needed **when running the processor** is missing from the processor path, even though application compile dependencies may be complete.
- **One compilation run works, the next fails:** stale outputs, caching, incremental metadata, or file-generation conditions depending on undeclared inputs.
- **Processor keeps generating sources endlessly:** each round produces a new file, prolonging the cycle; a termination condition must be designed. Do not hardcode logic to a fixed round count.
- **`@SupportedSourceVersion` lower than source level:** a warning may appear; update the actual supported version and check processor compatibility.

A worthwhile test must run on a **clean output directory**, verify the exact `.java` file is generated, compile a class using the generated type, and test negative diagnostics on invalid inputs. Using the real compiler or `JavaCompiler` API tests close to production behavior. For processors supporting incremental builds, also verify that modifying/deleting annotated elements properly removes or updates outputs.

## 10. Typical Misconceptions

1. **“Processors only run after every class has become bytecode.”** False; processors must have the chance to generate sources before compilation finishes so other classes can use them.
2. **“Processors edit original source code directly.”** Standard JSR 269 primarily reads the model and creates new files; AST modification is a different mechanism.
3. **“One invocation = one call to `process()`.”** False; a processor can be invoked across multiple rounds plus a final round.
4. **“`return true` means processing succeeded.”** False; it indicates the annotations have been claimed.
5. **“Annotations must have RUNTIME retention for a processor to see them.”** False; `RetentionPolicy.SOURCE` is also processed when the compiler reads sources.
6. **“`-s` is the directory holding `.class` files.”** False; `-s` is for generated sources, `-d` is for normal class output.
7. **“Just adding a processor JAR to the classpath makes every JDK run it automatically.”** False, especially from JDK 23 onward; configure processing explicitly.
8. **“The processor must be present when running the application.”** Not necessarily; only libraries needed by application bytecode at runtime must be present at runtime.
9. **“Round 2 is another javac invocation.”** False; multiple rounds happen within the same compilation invocation.
10. **“Generated Java does not need compiling.”** False; sources generated by a processor must be analyzed by the compiler and turned into classes if the application uses them.

## 11. Self-Check Questions

**Question 1.** A processor creates `Foo.java` in round 1. Where is `Foo` normally seen next? **In the next round** and compiled by the compiler if processing/compilation continues successfully.

**Question 2.** Why is `processingOver()` `true` in the final round? **The compiler has determined annotation processing is about to end**; the processor should not expect creating sources here to trigger another processing round.

**Question 3.** What is the difference between `-proc:only` and `-proc:full`? **`only` runs only processing; `full` runs processing and normal compilation.**

**Question 4.** A project upgrades from JDK 17 to JDK 23, and a processor stops running even though its JAR is still on the classpath. What do you check first? **Explicit processing configuration** via processor name/path or appropriate mode, along with compile logs and processor dependencies.

**Question 5.** Can using `Class.getAnnotation` at runtime replace generating sources via a processor? **No.** Reflection only accesses metadata of existing classes and does not intervene in `javac`'s compile rounds.

**Question 6.** `GeneratedGreeting.java` is created in `build/generated`; why is there a `GeneratedGreeting.class` in `build/classes`? **Because the compiler compiles the generated source as part of the compilation run**, not because `Filer.createSourceFile` turns the file into bytecode by itself.

### References for Cross-Checking

- [JSR 269 — Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)
- [The javac Command — Annotation Processing](https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html)
- [JDK 23: Changes to Default Annotation Processing Policy](https://inside.java/2024/06/18/quality-heads-up/)

**Key takeaway:** annotation processing is a stage **sitting between initial source modeling and compilation completion**, operating across *rounds*. It can create new sources for the compiler to keep processing in the same invocation; for consistent build behavior, configure processors and output paths explicitly, especially starting with JDK 23.