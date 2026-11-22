# What Is Annotation Processing and When Should You Generate Code?

## 1. Concept: Annotations Do Not Perform Work on Their Own

An annotation in Java is **metadata attached to a declaration or type-use site**, such as `@Override`, `@Deprecated`, `@Entity`, `@Builder`, or a project-defined annotation. Writing an annotation itself **does not automatically generate methods, modify classes, or execute business logic**. Another mechanism must **read** the annotation and decide what to do.

**Annotation processing** is the mechanism for processing annotations at compile time using the standard **JSR 269** API (Java Annotation Processing API) in the `java.compiler` module, primarily in these packages:

- `javax.annotation.processing`: `Processor`, `AbstractProcessor`, `ProcessingEnvironment`, `RoundEnvironment`, `Filer`, `Messager`.
- `javax.lang.model` and its subpackages: models of program elements/signatures, such as `Element`, `TypeElement`, `ExecutableElement`, `TypeMirror`, `Elements`, `Types`.
- `javax.tools`: compiler-managed file objects such as `JavaFileObject`, along with diagnostic kinds `Diagnostic.Kind`.

When `javac` is configured to run annotation processors, the compiler reads the source files, builds the element model, and lets processors observe the corresponding annotations. A processor can:

1. **Check rules at compile time**, emitting useful errors/warnings (for instance, detecting invalid configuration).
2. **Generate Java sources**, class files, or auxiliary resources needed by the build.
3. **Generate metadata** for another system to read, such as a registry of registered types.
4. **Do nothing** if annotations do not belong to types supported by the processor or there are no inputs requiring processing.

Example: a project has `@AutoGreeting` on `OrderService`; a processor can generate the class `OrderServiceGreeting` containing a static API. The new class is compiled in the same pass so user code can invoke it directly.

**Important distinction:** JSR 269-style annotation processing runs at **compile time**, unlike an application using reflection at runtime to read annotations with `RetentionPolicy.RUNTIME`. It also differs from bytecode instrumentation, compiler plugins manipulating internal ASTs, or runtime proxies. The standard `Filer` API is for **creating new files**, not a contract for mutating the AST of a class currently being compiled.

## 2. Where Are Annotations Visible?

Java annotations are declared via `@interface` and commonly carry two important meta-annotations:

- `@Target`: where the annotation may be attached (`TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `RECORD_COMPONENT`, ...).
- `@Retention`: how long the annotation is retained.

| Retention | Meaning | Can an annotation processor use it? |
| --- | --- | --- |
| `SOURCE` | Annotation belongs to source; typically not written into class files after compilation | **Yes**, when the processor runs on source containing the annotation |
| `CLASS` | Information may be written into class files; not required to be present in runtime reflection | **Yes**, when the input model supplies that annotation |
| `RUNTIME` | Accessible via runtime reflection | **Yes** at compile time, and runtime code can read it when needed |

**There is no need to set `RUNTIME` just so a processor can see an annotation**. For example, markers intended solely for code generation commonly choose `SOURCE` to avoid carrying unnecessary metadata into runtime.

A `SOURCE` annotation in an already-compiled `.class` file is usually no longer present; if a processor only receives information via binaries without corresponding source, it cannot assume `SOURCE` annotations are still there. When inspecting `SOURCE` annotations of a dependency is required, ensure the source is actually included in compilation and processed by the processor.

**Type-use annotations** (`ElementType.TYPE_USE`) have their own representation via `TypeMirror` / `AnnotatedConstruct`. Do not assume every annotation in source automatically appears in `RoundEnvironment.getElementsAnnotatedWith(...)` the same way as a class annotation. A processor analyzing type-use annotations needs to work with the appropriate type model.

## 3. Compilation Timeline and Processing Rounds

Conceptually, a `javac` invocation with annotation processing configured proceeds as follows:

```text
Input .java files and dependencies
         |
         v
javac reads sources, builds Element / Type model
         |
         v
Round 1: invokes processors for matching annotations
         |  \
         |   \-- Filer creates new sources/resources
         v
Round 2: compiler adds new sources into processing set
         |
         v
Further rounds if new sources continue being generated
         |
         v
Final round: processingOver() == true
         |
         v
Compiles original sources and generated sources
         |
         v
.class, generated source, diagnostics
```

The diagram expresses the **logical** mechanism and does not attempt to describe every internal phase of a specific `javac` build. Specifically:

1. In a round, a processor is queried for **the annotation types** it declares support for.
2. The processor receives `RoundEnvironment` to obtain the corresponding elements. Not every round is guaranteed to have annotations to process.
3. If new source files are created, the processor and compiler can proceed to the next round to process the new declarations.
4. A processor invoked in one round will continue to be invoked in subsequent rounds, including the final round; when `processingOver()` is true, do not create new sources expecting another round to process them.
5. When `-proc:only` is not used, the compiler proceeds to generate class files for both the original sources and generated sources, provided no errors prevent compilation.

Do not assume “a new processor instance is created for each round”: a processor instance is initialized and can participate in multiple rounds within **a single compilation**, so write code carefully to avoid writing the same file twice.

## 4. When Should You Generate Code and When Should You Not?

### 4.1. Scenarios Where Code Generation Adds Value

| Need | Why code generation helps | Example problem types |
| --- | --- | --- |
| Repetitive code with stable patterns | Reduces boilerplate while keeping explicit source/classes | Builders, factories, typed adapters |
| Mappings determinable from static types | Validates structure and emits direct calls | DTO mappers, serializers/deserializers |
| Integrations needing a type registry | Generates registries or metadata right at compile time | Service indexes, DI component registries |
| Configuration errors best caught early | Compiler can report mistakes right at the source element | Required fields, conflicting annotation configs |
| Avoiding runtime reflection on hot paths | Generates direct-call code or precomputed metadata | Certain mappers/DI frameworks |
| Creating strongly typed APIs from schemas | Authors get type checking and IDE completion | Typed clients, enum-like schema bindings |

Code generation makes the most sense when **inputs are structured**, generation rules are **deterministic**, outputs are **easy to inspect and stable**, and the cost of maintaining the generator is smaller than writing repetitive code by hand.

### 4.2. Scenarios Where You Should Not Generate Code

- Only a few simple lines of logic with no meaningful repetition.
- Requirements change **based on runtime data**, dynamic configuration, or user input after deployment.
- Generation logic is harder to debug than handwritten code; developers cannot inspect generated sources or have no way to test them.
- The generator must read the Internet, current time, random variables, or external systems during every build without pinning inputs, making builds non-reproducible.
- Wanting to **modify method bodies of existing classes** via the standard API; JSR 269/`Filer` is not an AST-rewriting tool. Consider alternative designs or specialized tools when genuinely needed.
- Encountering generated file/name collisions, infinite cyclic generation dependencies, or requiring a processor to rely on the invocation order of another processor.
- Increasing compile times, complicating IDE/CI setup, or causing API explosion with disproportionate benefit.

**Distinguish validation from generation:** many annotation processors only validate and report errors via `Messager`; they create no files at all. Generate code only when there is a concrete artifact users will consume.

## 5. Complete Example: An Annotation Generating a Java Class Usable in the Same Compile Pass

The following example uses **JDK 17 or later**, running in an ordinary project without `module-info.java`. Filenames, package names, and commands are consistent and require no libraries outside the JDK.

Structure:

```text
annotation-demo/
├── processor-src/
│   └── processor/
│       └── GreetingProcessor.java
└── src/
    └── demo/
        ├── AutoGreeting.java
        ├── OrderService.java
        └── Main.java
```

### 5.1. Define the Annotation

File **`src/demo/AutoGreeting.java`**:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
```

`@Target(TYPE)` allows the annotation on classes/interfaces/enums...; the processor below accepts only **classes** and reports an error for other declaration kinds. `RetentionPolicy.SOURCE` suffices because the annotation is used only during compilation.

### 5.2. Declare Usage of the Annotation

File **`src/demo/OrderService.java`**:

```java
package demo;

@AutoGreeting
public final class OrderService {
}
```

There is no handwritten `OrderServiceGreeting.java` file in the source tree; the processor will create it.

### 5.3. Main Calls a Class That Does Not Exist Before Compilation

File **`src/demo/Main.java`**:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(OrderServiceGreeting.message());
    }
}
```

If **the processor is not run**, the compiler will not find `OrderServiceGreeting` and will report an error. When the processor is configured properly, the class is generated and the compiler can resolve the name within that same compilation pass.

### 5.4. Write the Processor Using the Standard API

File **`processor-src/processor/GreetingProcessor.java`**:

```java
package processor;

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

@SupportedAnnotationTypes("demo.AutoGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element
                    : roundEnv.getElementsAnnotatedWith(annotation)) {

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@AutoGreeting requires a class",
                            element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String packageName = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simpleName = type.getSimpleName() + "Greeting";
                String fullName = packageName + "." + simpleName;

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(fullName, type);

                    try (Writer writer = file.openWriter()) {
                        writer.write("package " + packageName + ";\n");
                        writer.write("public final class " + simpleName + " {\n");
                        writer.write("  private " + simpleName + "() {}\n");
                        writer.write("  public static String message() {\n");
                        writer.write("    return \"Hello from processor\";\n");
                        writer.write("  }\n");
                        writer.write("}\n");
                    }
                } catch (IOException e) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Cannot generate " + fullName + ": " + e,
                            element);
                }
            }
        }
        return true;
    }
}
```

**Why does the code use these APIs?**

- `@SupportedAnnotationTypes("demo.AutoGreeting")` declares the annotation type that the processor can handle.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` publishes the maximum source level supported by this example processor version; it is not a flag controlling `javac`'s target. Use `--release 17` in commands to keep the exercise consistent.
- `annotations` receives `TypeElement` instances representing the annotation types the framework asks to process in the round. Using `getElementsAnnotatedWith(TypeElement)` avoids needing to load the annotation class via reflection in the processor's classloader.
- `ElementKind.CLASS` verifies the exact declaration kind before creating the class; `TypeElement` represents a type declaration in the compiler model.
- `Elements.getPackageOf(type)` reads the package; `Filer.createSourceFile(fullName, type)` asks the compiler to manage **a new source file** and records the originating element to assist build tools.
- `Messager.printMessage(ERROR, ..., element)` emits a diagnostic bound to the element, easy to locate in IDEs/CI. Do not use `System.out.println` as an error-reporting mechanism.
- `process(...)` returning `true` means the processor **claims** the requested annotation types, so subsequent processors will not continue processing them under standard claiming semantics. This is an intentional decision, not “all files generated successfully” as a function return status.
- `processingOver()` detects the final round; the processor does not attempt to generate more code in this round.

**Example limitation:** the processor builds class names from simple names. This works for top-level classes like `demo.OrderService`; for nested classes, multiple declarations sharing a simple name, multiple processors, or complex naming rules, design stable generated names and avoid collisions. The example is not meant to handle every Java construct.

## 6. Compile the Processor First, Then Use It in javac

The processor must be **compiled before `javac` runs it**. If the processor and application code sit in the same source group while the processor does not yet exist as class files, do not expect the compiler to “compile the processor and execute it simultaneously” in that pass.

From inside the `annotation-demo` directory, create three output directories:

```bash
# Linux/macOS
mkdir -p build/processor build/generated build/classes
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force build/processor,build/generated,build/classes | Out-Null
```

### 6.1. Step A: Compile the Processor Separately

```bash
javac --release 17 -d build/processor processor-src/processor/GreetingProcessor.java
```

Because the processor references only standard JDK APIs, this step does not depend on the `demo.AutoGreeting` annotation. Generated artifact:

```text
build/processor/processor/GreetingProcessor.class
```

### 6.2. Step B: Compile the Application and Run the Processor

Use the command below for Linux/macOS **and** Windows PowerShell (paths contain no spaces in the example):

```bash
javac --release 17 \
  -processorpath build/processor \
  -processor processor.GreetingProcessor \
  -s build/generated \
  -d build/classes \
  src/demo/AutoGreeting.java \
  src/demo/OrderService.java \
  src/demo/Main.java
```

Trailing `\` characters are POSIX shell line-continuation syntax, **not** Windows PowerShell syntax. In PowerShell, use the single-line equivalent:

```powershell
javac --release 17 -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

When processing `@AutoGreeting`, the processor creates the file:

```text
build/generated/demo/OrderServiceGreeting.java
```

Contents of the generated file:

```java
package demo;

public final class OrderServiceGreeting {
  private OrderServiceGreeting() {}
  public static String message() {
    return "Hello from processor";
  }
}
```

The compiler continues compiling both the original source code **and** the newly generated source so `OrderServiceGreeting` can be used from `Main`. Main class outputs:

```text
build/classes/
└── demo/
    ├── AutoGreeting.class
    ├── Main.class
    ├── OrderService.class
    └── OrderServiceGreeting.class
```

### 6.3. Run the Program

```bash
java -cp build/classes demo.Main
```

Exact expected stdout on JDK 17+:

```text
Hello from processor
```

**Distinction to keep clear:** `-s` specifies where to write **generated sources**, whereas `-d` specifies where to write **class files**. Generated sources can be compiled by the compiler within the same compilation unit, yet `.java` files remain separate artifacts to read/inspect. If any build command fails, do not use old class files to conclude the processor ran successfully.

## 7. Specifying Processors, Discovery, and Default Changes Across JDKs

There are two common ways to locate processors:

1. **Explicitly list processor names** with `-processor processor.GreetingProcessor` and place its classes on `-processorpath` (as in the exercise).
2. **Service discovery** via `META-INF/services/javax.annotation.processing.Processor` in a processor-path JAR/directory; contents list `Processor` implementation names, one fully-qualified name per line. Build tools typically place processor JARs on a separate processor path.

The second approach is useful for reusable packaged processor libraries, but JDK version changes must be understood:

- **JDK 21:** `javac` may automatically discover processors on the classpath using legacy behavior if not explicitly configured; it warns/notifies about relying on implicit discovery in certain situations.
- **JDK 23 and later:** by default, **annotation processing does not automatically run merely because a processor happens to be on the classpath**. To run it, explicitly configure the processor/discovery path or request processing, e.g., `-processor`, `--processor-path`, `--processor-module-path`, `-proc:full`.
- **`-proc:none`:** disables annotation processing.
- **`-proc:only`:** runs only annotation processing without performing the ordinary class-file compilation stage for sources.
- **`-proc:full`:** requests both annotation processing and compilation; on compilers supporting this flag, this is the explicit configuration.

**For builds with codegen, configure processors explicitly**, without relying on default discovery that varies across JDK versions. The example command uses both `-processorpath` and `-processor`, directly stating which processor must run. When running older JDKs, verify support for `-proc` values per version and update release; for example, source code choosing Java 17 does not mean every JDK 17 build provides all newer compiler flags.

## 8. Processing Rounds: Why Can Newly Generated Source Be Recognized by the Compiler?

In the example:

- **First round:** the compiler reads `OrderService` carrying `@AutoGreeting` and invokes `GreetingProcessor`.
- The processor writes `OrderServiceGreeting.java` via `Filer`.
- **Next round:** the generated file becomes input source for the following round. Because the generated class does not carry `@AutoGreeting`, the processor does not need to generate further source.
- **Final round:** `processingOver()` is true; the processor returns without writing additional files.
- The compiler generates class files from original sources and generated sources, provided there are no errors.

You can observe this using `javac` flags:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

These flags print diagnostics about rounds and invoked processors, though exact log text/format depends on compiler version. Do not try to force log lines to match a fixed output to verify correctness of the exercise. Check generated files together with final execution results.

Do not generate code in the final round expecting the compiler to open another round. Avoid workflows where processor A must create a file first so processor B can run **within the same round in an invariant order**; the standard API encourages processors to operate independently, deterministically, and without relying on implicit execution order.

## 9. Filer, Messager, Elements, and Types: Core Tools

| API | Role | When to use |
| --- | --- | --- |
| `RoundEnvironment` | Identify annotations/elements being processed, final round status | Every `process` call |
| `Element`, `TypeElement` | Model class, interface, method, and field declarations | Static source analysis |
| `TypeMirror` | Model types in the compile-time Java language model | Checking types, generics, subtypes |
| `Elements` (`processingEnv.getElementUtils()`) | Search and read names, packages, annotations, members | Codegen based on declaration structure |
| `Types` (`processingEnv.getTypeUtils()`) | Check assignability, subtyping, erasure, type transformations | Validation for typed mappers, adapters |
| `Filer` | Create source/class/resource outputs | When artifacts must be generated |
| `Messager` | Report NOTE/WARNING/ERROR with associated locations | Validation and diagnostics |
| `ProcessingEnvironment.getOptions()` | Read `-Akey=value` options specific to processors | Declaratively configuring generators |

For example, a processor checking whether a method has a valid return type should use `TypeMirror` and `Types`, **not** `Class.forName(...)` to attempt loading the class being compiled. Source classes may not yet exist in the processor runtime; ClassLoaders and the compile-time model are two different worlds.

Be careful when generating Java source strings: data from annotations can contain quotes, newlines, backslashes, or invalid identifiers. The example in this lesson generates only **a fixed string constant**, avoiding the need to escape inputs. Real generators must escape literals according to Java grammar, validate identifiers, control package names, and handle encoding properly.

### Filer Is Not an API for Editing Existing Source

`Filer.createSourceFile(...)` creates a new file with a fully-qualified name. Within a single compilation run, attempting to create **the same name twice** leads to `FilerException`; colliding with an existing input source file is also an error. Filer accepts originating elements so build systems know which inputs produced an output; this assists incremental compilation but does not automatically make every processor incremental.

Do not overwrite user sources, directly mutate classes being processed, or write to arbitrary paths instead of using `Filer` during builds: such approaches break file ownership boundaries, break IDEs, and make builds hard to reproduce.

## 10. Separating Processor Path from Application Classpath

An annotation processor **runs inside the compiler's execution environment**, even though it reads a model of the program being compiled. This clarifies two distinct dependency sets:

- **Application compile classpath:** dependencies that application source code is allowed to reference during compilation.
- **Processor path:** JARs/classes of the processor and dependencies required **for the processor itself to execute**.

In the example, `-processorpath build/processor` holds `GreetingProcessor`'s implementation; `src/demo/AutoGreeting.java` is supplied as source so the compiler sees the annotation. The processor does not need to reference the annotation class directly, so there is no need to add an annotation JAR to the processor path.

If your processor itself imports a specific annotation class instead of using `TypeElement`, the processor will need that annotation class on the processor classpath when **compiling and loading the processor**. If the processor uses a template library or parser, those required dependencies must also be placed on the processor path.

Do not unnecessarily place all application libraries onto the processor path. Because processors are **programs executing during the build**, a processor from an untrusted dependency can read files, environment variables, and produce outputs; pin versions, verify provenance, enable only approved processors, and do not expose unrestricted secrets to compile jobs.

For JPMS, `--processor-module-path` is used to locate processors packaged as modules; do not mechanically swap it with the application's `--module-path`. Consult the appropriate `javac` documentation for the module layout in use.

## 11. Build Tools and IDEs: Making Codegen Reliable

### 11.1. In Gradle

When using the Gradle Java plugin, dependencies for compile-time APIs and processors are usually declared separately. Symbolic example (replace artifact coordinates with real dependencies chosen by the project):

```groovy
dependencies {
    compileOnly 'example:annotations:1.0'
    annotationProcessor 'example:generator:1.0'
}
```

This is an **illustrative Gradle DSL snippet, not a project with real existing dependencies**. `compileOnly` fits when the annotation API is only needed at compile time; `annotationProcessor` places the processor on the processor path managed by Gradle. Some frameworks need the annotation API at runtime, in which case dependency scope must change accordingly. Configure `testAnnotationProcessor` or other source sets when test code also uses annotation processors.

Gradle can manage generated sources and incremental compilation, yet does not guarantee every processor supports incremental execution. In serious builds, use dependency locking/verification, verify toolchains, options, and generated output directories instead of relying on generated files left over from a previous build.

### 11.2. In Maven

The Maven Compiler Plugin provides configurations for annotation processors and processor paths/processor dependencies; exact syntax depends on **Maven/JDK/plugin versions**. Read the documentation for the plugin in use rather than assuming an old configuration works on JDK 23+. Points to specify:

- Which processors are allowed to run and their actual versions/JARs.
- Source/target or `release` used by the compiler.
- Generated sources directory, compile classpath, and processor dependency isolation.
- Whether processing runs during test compilation.

For critical codegen, pin Maven Wrapper/plugin versions and build on a JDK with explicit processing configuration.

### 11.3. IDEs and CI

IDEs recognize generated classes only when annotation processing is properly configured and the generated source directory is marked correctly by the IDE. When encountering “builds on command line but red in IDE”, check processor enablement, compiler JDK, processor path, output directory, and required IDE plugins.

**Do not blindly commit generated sources.** If generated code is an artifact reproducible from sources and a pinned generator, usually manage it in build outputs rather than editing manually. Some projects have reasons to store generated sources for code review or SDK publishing; in that case state a clear policy and verify outputs do not drift.

## 12. Quality of Generated Code and Reproducibility

If a processor generates code, treat the output as real code that requires testing:

1. **Deterministic:** identical inputs/versions/options must yield identical meaningful output. Sort elements in a stable order if output order affects artifacts.
2. **Do not read hidden undeclared data:** avoid current timestamps, random IDs, machine paths, and network calls in generated outputs.
3. **Stable file/class names:** avoid collisions when multiple elements share simple names, nested types exist, or multiple processors emit artifacts.
4. **Never write duplicate files:** create each name only once per run; handle final rounds and duplicates gracefully.
5. **Clear provenance:** pass originating elements to `Filer` when appropriate and keep the generated source directory easy to inspect.
6. **Good diagnostics:** report errors on misconfigured elements explaining how to fix them; do not swallow `IOException` or turn failures into false success.
7. **Never emit invalid source:** escape values and validate identifiers/packages/types; test with a real compiler.
8. **Managed APIs:** changing generated names/classes can break consumers; coordinate processor and annotation API versioning.
9. **Avoid cyclic dependencies:** a processor should not require its own output to start; avoid designs causing unbounded multi-round generation.
10. **Compile/test generated code:** have unit tests for the processor, negative tests for invalid configs, and integration tests proving clients can call the generated API.

A good generator should have **a small, clear, predictable contract**. If a minor rule change causes an explosion in generated classes or cryptic diagnostics, build costs may outweigh benefits.

## 13. Typical Errors and How to Investigate

| Symptom | Common cause | Check |
| --- | --- | --- |
| `cannot find symbol: OrderServiceGreeting` | Processor did not run, was not discovered, or failed to emit file | `-processor` / `-processorpath`, `-proc`, generated source directory, diagnostics |
| `Annotation processor ... not found` | Processor class not compiled, typo in name, missing dependency, or processor path | Check `build/processor`/JAR and fully-qualified processor name |
| `FilerException: Attempt to recreate a file` | Processor or another processor tried to create duplicate source/class in the same run | Generated names, rounds, output ownership, duplicate inputs |
| Code generated yet IDE does not resolve | IDE has annotation processing disabled or generated source root not recognized | IDE settings and generated paths |
| Works on JDK 21 yet processor does not run on JDK 23 | Relied on legacy implicit discovery defaults | Explicit processing configuration |
| Processor has lower `@SupportedSourceVersion` than source | Processor's declared source version does not match compilation | Update processor and source-version policy |
| Generated class missing method/differs from expectation | Stale generator version, annotation value, or build cache | Dependency version/hashes, clean build, generated source |
| `NoClassDefFoundError` inside processor | Processor's own dependency missing on processor path | Separate processor path from application dependencies |
| Generated Java has syntax errors | Improper string/identifier escaping, missing imports, class name collision | Open `-s` output, inspect diagnostics and generated source |
| Build spans excessive rounds | Processor keeps generating more source endlessly, mutual dependencies | `-XprintRounds`, file-creation conditions, final-round guard |

**Do not read logs from a single line.** Combine annotation sources, actual compiler command, processor path, list of generated files, and diagnostics. `-XprintRounds` / `-XprintProcessorInfo` help verify whether the processor ran and which annotation types it received.

## 14. When Only Compile-Time Checks Are Needed, File Generation Is Unnecessary

A processor can emit an error when detecting misconfiguration:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "A required annotation value is missing",
        element);
```

This is an **illustrative snippet inside the `process` method** where variable `element` is already available; it is not a standalone Java program. When using `Diagnostic.Kind.ERROR`, the compiler can report compilation failure even when the processor creates no sources. Tools such as DTO/API convention checkers, special naming rules, or annotation combination validators can achieve their goal through validation alone.

A useful design principle:

- If you want **early error reporting** → prefer validation.
- If you want **repetitive, rule-based static APIs/metadata** → consider code generation.
- If behavior genuinely must **vary at runtime** → consider runtime config, reflection, service loading, or another appropriate mechanism.
- If the goal is **modifying AST/bytecode of existing classes** → JSR 269 provides no standard contract for that; use specialized approaches and understand compiler dependencies.

## 15. Control Experiment: Enabling and Disabling the Processor

After compiling `GreetingProcessor`, test with **new/clean outputs**:

### 15.1. Explicitly Enable the Processor

```bash
javac --release 17 -processorpath build/processor -processor processor.GreetingProcessor -s build/generated -d build/classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

Result: the processor creates `OrderServiceGreeting.java`, the compiler creates classes, and `demo.Main` prints `Hello from processor` when run.

### 15.2. Disable the Processor

```bash
javac --release 17 -proc:none -d build/without-processor src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

If `build/without-processor` holds no old classes and the compile classpath has no `OrderServiceGreeting` elsewhere, this command **fails** because `Main` references a class that was never generated. This experiment confirms the processor itself is the source creating that API.

### 15.3. Run Annotation Processing Only

```bash
javac --release 17 -proc:only -processorpath build/processor -processor processor.GreetingProcessor -s build/only-generated -d build/only-classes src/demo/AutoGreeting.java src/demo/OrderService.java src/demo/Main.java
```

With `-proc:only`, inspect generated sources and diagnostics; do not expect this step to produce complete class files for running `demo.Main`. To run the application, a compilation phase generating the corresponding `.class` files must run. Do not assume generated files automatically become runtime classes.

**Keep the environment clean** when comparing. If the output directory holds `OrderServiceGreeting.class` from an earlier compile, a processor-disabled test can be masked. In real projects, use clean builds or isolated output directories and explicit classpaths.

## 16. Self-Check Questions

**Question 1.** Does `@Retention(SOURCE)` prevent an annotation processor from reading the annotation?

**Answer:** No. Processors can read annotations on sources during compile time. `SOURCE` retention merely means the annotation is not runtime metadata after compilation.

**Question 2.** If we want a processor to create `OrderServiceGreeting.java`, which standard API handles creating the file?

**Answer:** `ProcessingEnvironment.getFiler().createSourceFile(...)`. Pass originating elements when appropriate and avoid creating duplicate names within the same compilation.

**Question 3.** Why must `GreetingProcessor.java` be compiled before running it in the example?

**Answer:** `javac` needs to load a `Processor` implementation already compiled into classes (or a processor JAR) placed on the proper processor path. Uncompiled processor source does not automatically become an executable processor during the same application compilation pass.

**Question 4.** Does `process(...)` returning `true` mean “all codegen files succeeded”?

**Answer:** No. `true` means the processor claims the annotation types assigned to it in the round; generation success/failure must be reflected via outputs and diagnostics.

**Question 5.** Why should a processor not call `Class.forName("demo.OrderService")` to inspect methods of a class being compiled?

**Answer:** The class being compiled may not exist in the processor's runtime yet. Use the `Element` / `TypeMirror` model via `Elements` and `Types`.

**Question 6.** A build runs annotation processing on JDK 21 with no explicit configuration. On JDK 23, generated classes disappear. What is the likely cause?

**Answer:** Since JDK 23, processors are no longer automatically run merely because they are found on the classpath. Configure the processor/discovery path or `-proc:full` explicitly, and verify JDK and build tool settings.

**Question 7.** A processor only needs to check an annotation value and report an error if invalid. Must it generate Java source?

**Answer:** No. Emitting diagnostics via `Messager` is enough; code generation is appropriate only when a concrete artifact is needed.

**Question 8.** Should class names be generated using the simple name of every nested type without considering owner/package?

**Answer:** No. Multiple types can share a simple name and cause collisions. Generators need complete, stable naming rules and collision checks.

## 17. Official References

- **Oracle JDK 21 `javac` — Annotation Processing:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — round mechanisms, `-processor`, `-processorpath`, `-proc`, `-s`, `-XprintRounds`.
- **JDK 23 Release Notes:** https://www.oracle.com/java/technologies/javase/23all-relnotes.html — annotation processing default change; requires explicit configuration.
- **Java SE 21 `Processor` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html — lifecycle, `process`, and claiming semantics.
- **Java SE 21 `RoundEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — rounds, `getElementsAnnotatedWith`, and `processingOver`.
- **Java SE 21 `Filer` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Filer.html — creating source/class/resource files and file constraints.
- **Java SE 21 `ProcessingEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html — access to `Elements`, `Types`, `Filer`, and `Messager`.

**Conclusion:** annotation processing is a compile-time step using a program model to **validate rules or generate new code/resources**. Generate code when output follows clear rules, adds type-safe value, and is reproducible; use validation when only error reporting is needed, and choose runtime mechanisms when requirements are genuinely dynamic. Explicit processor configuration, managing generated sources, and testing generated code are decisive factors for a reliable solution.
