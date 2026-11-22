# Distinguishing Annotation Processing from Reflection and AST Transformation in Java

When encountering an annotation such as `@Override`, `@Deprecated`, `@Entity`, or `@GenerateBuilder`, learners often mistakenly assume that the annotation itself “runs on its own” and modifies Java code. In reality, **an annotation is metadata**; behavior depends on **the tool reading the metadata**, **when it is read**, and **which APIs are permitted to act**. Three mechanisms must be distinguished:

1. **Annotation processing (JSR 269)**: a tool activated by the compiler during compilation, reading declaration/type models, verifying rules, and typically **generating new Java files, class files, or resources**.
2. **Reflection**: a running program using APIs such as `Class.getAnnotation(...)` or `getDeclaredMethods()` to **inspect class structure and annotations retained at runtime**, optionally invoking methods within granted access permissions.
3. **AST transformation (Abstract Syntax Tree transformation)**: intervening in **internal syntax trees or compiler phases** to alter program structure, such as adding fields, constructors, or methods into the type currently being compiled. This is **not** a standard mutation capability of JSR 269.

This lesson sits in the context of **Java compilation**: you need to know when the compiler observes annotations, what tools can do, how to organize builds, and why ordinary annotation processors are not synonymous with direct AST modification mechanisms.

## 1. Quick Comparison Table

| Criterion | Annotation processing (JSR 269) | Reflection | AST transformation |
| --- | --- | --- | --- |
| Primary timing | During **build/compile** via `javac` or a compatible compiler | When **program runs**; can also be used by other tools on loaded classes | Inside parser/compiler pipeline or a source analysis/transformation tool |
| Observed subject | `Element`, `TypeMirror`, `RoundEnvironment`, and annotations on the language model | `Class`, `Method`, `Field`, `Constructor`, and runtime annotations | Syntax tree nodes, position info, expression/statement structure |
| Typical APIs | `javax.annotation.processing`, `javax.lang.model`, `Filer`, `Messager` | `java.lang.reflect`, `java.lang.annotation` | Tree/compiler/plugin APIs or tool-specific AST libraries |
| Common results | Generate sources/resources; validate and emit diagnostics; emit new classes | Read metadata, find members, invoke methods reflectively | Edit/replace nodes, insert declarations, rewrite code, or alter compiler steps |
| Directly edits original class body? | **No**, not provided by standard JSR 269 APIs | **No**, reflection does not rewrite compiled class definitions | **Possible**, depending on framework/compiler and support limits |
| Required annotation retention | Can read annotations at compile time including `SOURCE` | Must be `RUNTIME` to be seen via standard reflection | Depends on stage and AST reading mechanism, not necessarily runtime retention |
| Portability | Relatively good if using only standard JSR 269 APIs | Standard Java reflection API | Often compiler/version-dependent if manipulating internal trees |
| Examples | Dagger, AutoService, MapStruct (code generation model), custom processors | Frameworks scanning `@Controller`, reading `@Test` at runtime | Certain techniques in Lombok, javac compiler plugins, or source transformers |

**Note:** a library's name does not replace inspecting how it works. A framework may combine annotation processors, reflection, code generation, and bytecode instrumentation. The `@` syntax itself does not dictate timing or processing method.

## 2. Annotations Specify Data; Tools Decide Behavior

Consider:

~~~java
@Deprecated
public void oldMethod() {
}
~~~

`@Deprecated` is metadata. Compilers and IDEs may warn when the deprecated method is used; the annotation does not execute an instruction modifying objects at runtime by itself. Similarly, an application annotation such as `@GenerateGreeting` produces artifacts only when a processor is **configured and executed** to interpret that annotation.

An annotation type is declared like a special interface:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

This snippet illustrates only an annotation declaration. It has no processor yet and no `main` yet.

- `@Target(TYPE)` restricts where it can be used syntactically/by declaration kind (class, interface, enum, annotation type, record depending on rules).
- `@Retention(SOURCE)` specifies the annotation need not be recorded in `.class` files. Compilers/processors **can still read it while processing sources**.
- Having a processor understand `@GenerateGreeting` is logic programmed in the processor, **not** an inherent capability created by `@Retention` or `@Target`.

Annotations can take parameters: `public @interface Table { String name(); }` and be used as `@Table(name = "orders")`. This is metadata that processors or reflection can read when retention matches; it does not automatically generate SQL or add fields.

## 3. Three Retention Levels: SOURCE, CLASS, RUNTIME

| RetentionPolicy | Present in source? | Written to class file? | Readable by standard runtime reflection? |
| --- | --- | --- | --- |
| `SOURCE` | Yes | Not kept as runtime/class metadata | No |
| `CLASS` | Yes | Yes, typically as non-runtime-visible annotation metadata | No |
| `RUNTIME` | Yes | Yes, runtime-visible metadata | Yes |

If `@Retention` is omitted, the default is **`CLASS`**. Specify `@Retention(RUNTIME)` when a runtime tool needs to read the annotation, not to “enable” annotation processing. A JSR 269 processor can handle annotations declared as `SOURCE`, `CLASS`, or `RUNTIME` whenever the annotation appears in the compilation model it processes.

Practical examples:

- **SOURCE** fits metadata used only for compile-time checks or code generation.
- **CLASS** fits tools reading bytecode/class metadata without needing ordinary runtime reflection.
- **RUNTIME** fits frameworks using reflection to find annotations while the application runs.

Do not confuse `Class.getAnnotations()` not seeing a `CLASS` annotation with that annotation never having existed. It can be present in the class file as a runtime-invisible annotation attribute yet not be returned by reflection.

`@Inherited`, if used, affects only certain annotation queries on **classes** along superclass relationships; it does not make annotations auto-generate code and is not a way to apply inherited annotations to methods, fields, or interfaces.

## 4. Annotation Processing: The JSR 269 Mechanism When javac Runs

Java provides the standard API in `javax.annotation.processing`. A processor typically extends `AbstractProcessor` and implements:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
)
~~~

This is an **illustrative method signature**, not a standalone Java file. Key abstractions:

- **`Processor`/`AbstractProcessor`**: contract for implementing annotation processing.
- **`@SupportedAnnotationTypes`**: declares which annotation type names the processor supports (or the processor can override `getSupportedAnnotationTypes()`).
- **`@SupportedSourceVersion`**: declares the source language level the processor supports.
- **`RoundEnvironment`**: info about root elements, annotated elements, and processing round status.
- **`Element`/`TypeElement`**: models **declarations** such as packages, types, methods, fields, and parameters.
- **`TypeMirror`**: models **types** of elements/expressions within the corresponding API, distinct from `java.lang.Class` objects loaded by the JVM.
- **`ProcessingEnvironment`**: provides `Elements`, `Types`, `Filer`, `Messager`, and options.
- **`Filer`**: creates **new** sources, classes, or resources generated by the processor.
- **`Messager`**: reports `NOTE`, `WARNING`, or `ERROR` to the compiler on the appropriate element.

A processor runs **during the compilation process** with code-execution permissions in the build environment. It can inspect source structure and types known to the compiler without requiring a runtime instance of the class being compiled.

### The Concept of Rounds

A common flow:

~~~text
javac reads input sources
        |
        v
Round 1: processor sees @GenerateGreeting on App
        |
        +--> Filer creates AppGreeting.java
        |
        v
Round 2: compiler/processor sees the generated source
        |
        +--> other processors can process new annotations
        |
        v
Final round: processingOver() = true
        |
        v
javac completes type checking and emits matching .class files
~~~

This is a **mental model** diagram: actual sequence and round count depend on generated content, processors, and compiler. A processor should not redefine the same file across multiple rounds; `Filer` may report an error if recreating the same path within one processing run.

**Important limitation:** With the standard JSR 269 API, a processor has no command to “open the original class and add fields/methods to its AST”. It can **generate a new class, report errors, or emit metadata/resources**. Tools that modify declarations currently being compiled require other mechanisms/compiler extensions.

## 5. Runnable Java 17 Example: Processor Generating New Source Code

This example compiles with JDK 17+ (using `SourceVersion.RELEASE_17`) without dependencies outside the JDK. We will create a `@GenerateGreeting` annotation, a processor, and an application using the newly generated class.

Create the file tree at the project root:

~~~text
annotation-lab/
└── src/
    ├── annotation/demo/GenerateGreeting.java
    ├── processor/demo/GreetingProcessor.java
    └── app/demo/App.java
~~~

### 5.1. Define the SOURCE Annotation

**File `src/annotation/demo/GenerateGreeting.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

Here, SOURCE retention is sufficient for the compiler/processor in the experiment. This annotation does not exist in `App.class` runtime metadata.

### 5.2. Write a Standard JSR 269 Processor

**File `src/processor/demo/GreetingProcessor.java`:**

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
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting requires a class",
                        element
                );
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element).getQualifiedName().toString();
            String generatedName =
                    element.getSimpleName().toString() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try {
                JavaFileObject file =
                        processingEnv.getFiler()
                                .createSourceFile(qualifiedName, element);
                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write("public final class " + generatedName + " {\n");
                    writer.write("  private " + generatedName + "() {}\n");
                    writer.write(
                            "  public static String message() {\n"
                            + "    return \"Generated for "
                            + element.getSimpleName() + "\";\n"
                            + "  }\n"
                    );
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": "
                                + ex.getMessage(),
                        element
                );
            }
        }

        return true;
    }
}
~~~

Technical points:

- `getElementsAnnotatedWith(GenerateGreeting.class)` finds declarations marked with the annotation.
- `ElementKind.CLASS` ensures the lab only supports classes; the annotation type has `@Target(TYPE)` permitting other type forms, which the processor **intentionally rejects** in this example.
- `getPackageOf(...)` retrieves the declaration's package.
- `Filer.createSourceFile(...)` creates **a new source file**, without modifying `App.java`.
- `Messager` emits a positioned compiler error if file generation fails.
- `return true` tells the compiler the processor **claims** the annotation types passed for that round; it does not mean “AST edited successfully”.
- The processor generates source named `AppGreeting` when processing class `App`. In real systems, add handling for special names, duplicates, escaping, and multi-package tests before releasing a shared processor. This is a deliberately simple class-naming lab.

### 5.3. Application Using the Generated Code

**File `src/app/demo/App.java`:**

~~~java
package demo;

@GenerateGreeting
public final class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.message());
        System.out.println(
                App.class.isAnnotationPresent(GenerateGreeting.class)
        );
    }
}
~~~

`AppGreeting` **does not exist yet** before the processor runs. If you compile `App.java` without running the processor, calling `AppGreeting.message()` causes a symbol-not-found error. When the processor generates source during a round, the compiler can compile the generated source in the same `javac` invocation.

### 5.4. Compile and Run on Linux/macOS (Bash)

From the `annotation-lab` root:

~~~bash
mkdir -p build/processor build/app build/generated
javac -encoding UTF-8 -d build/processor \
  src/annotation/demo/GenerateGreeting.java \
  src/processor/demo/GreetingProcessor.java
jar --create --file build/greeting-processor.jar -C build/processor .
javac -encoding UTF-8 \
  -cp build/greeting-processor.jar \
  -processorpath build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -s build/generated -d build/app \
  src/app/demo/App.java
java -cp "build/app:build/greeting-processor.jar" demo.App
~~~

**Exact stdout** of the application:

~~~text
Generated for App
false
~~~

The generated file resides at `build/generated/demo/AppGreeting.java`, and `javac` creates `build/app/demo/AppGreeting.class` alongside `App.class`. You can open the generated file to inspect its contents or run `javap -classpath build/app demo.AppGreeting`.

Because `@GenerateGreeting` has SOURCE retention, runtime reflection inside `App` returns `false`. The fact that the processor ran and generated code does **not** promote retention to RUNTIME.

### 5.5. Corresponding Commands on Windows PowerShell

Create the files in the exact layout above, then run in the `annotation-lab` root:

~~~powershell
New-Item -ItemType Directory -Force "build\processor", "build\app", "build\generated" | Out-Null
javac -encoding UTF-8 -d "build\processor" "src\annotation\demo\GenerateGreeting.java" "src\processor\demo\GreetingProcessor.java"
jar --create --file "build\greeting-processor.jar" -C "build\processor" .
javac -encoding UTF-8 -cp "build\greeting-processor.jar" -processorpath "build\greeting-processor.jar" -processor demo.GreetingProcessor -s "build\generated" -d "build\app" "src\app\demo\App.java"
java -cp "build\app;build\greeting-processor.jar" demo.App
~~~

Stdout:

~~~text
Generated for App
false
~~~

Windows uses `;` to join runtime classpath entries. In the lab, the processor was **explicitly specified** via `-processor demo.GreetingProcessor`; thus there is no need to create `META-INF/services` for autodiscovery.

### 5.6. Distinguishing the Paths and Options

| Option | Role in lab |
| --- | --- |
| `-d build/processor` | Root of `.class` files for the annotation and processor when building the JAR |
| `-processorpath build/greeting-processor.jar` | Where `javac` finds and loads the processor to execute during the build |
| `-processor demo.GreetingProcessor` | Requests running a specific processor without relying on autodiscovery |
| `-cp build/greeting-processor.jar` | Makes the `demo.GenerateGreeting` type known to the application compiler |
| `-s build/generated` | Directory storing `.java` files generated by the processor |
| `-d build/app` | Directory storing final class files of the application and generated classes |
| `java -cp ... demo.App` | Runtime classpath and fully-qualified name of the main class |

**Processor path and compile classpath are two separate concerns.** A processor may need to be on the processor path to execute, while annotations/APIs imported by application code must appear on the compile classpath. In projects using build tools, configuring dependencies separately for annotation processing is usually safer than putting every processor into runtime dependencies.

## 6. Reflection: Reading Annotations While the Program Runs

Reflection does not require `Filer`, `RoundEnvironment`, or a compiler round. It operates on classes already loaded by the JVM and metadata available at runtime.

**Standalone file `ReflectionDemo.java`:**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public final class ReflectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Label {
        String value();
    }

    @Label("runtime")
    static final class Task {
    }

    public static void main(String[] args) {
        Label label = Task.class.getAnnotation(Label.class);
        System.out.println(label.value());
        System.out.println(Task.class.isAnnotationPresent(Label.class));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 ReflectionDemo.java
java ReflectionDemo
~~~

**Exact stdout:**

~~~text
runtime
true
~~~

Because `@Label` has `RUNTIME` retention, `Class.getAnnotation(Label.class)` returns annotation info. Reflection is reading metadata from `Task.class`; **it does not generate `TaskGenerated.java`, alter ASTs, or inject methods into `Task`**.

### Common Reflection APIs

- `Class.getDeclaredAnnotations()` returns directly declared annotations per API rules, differing from queries considering `@Inherited`.
- `Class.getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` list compiled members of the class.
- `Method.invoke(receiver, args...)` reflectively invokes a method when access permissions and runtime conditions allow.
- `Class.forName("some.Type")` loads/locates a class by name per API behavior; it does **not** launch an annotation processor to generate new source.

Reflection can detect annotations so a framework can make decisions, such as registering endpoints, creating objects, or mapping data. Yet that logic is **programmed by the framework**, not produced by the annotation itself.

### The Same Annotation Can Be Used at Both Times

A `@Retention(RUNTIME)` annotation can be checked by a processor at compile time **and** read via reflection at runtime, if both tools exist and are configured. The two mechanisms are not mutually exclusive. The difference lies in **timing, data model, and effect**, not merely the annotation name.

## 7. AST Transformation: Altering Code Structure Instead of Generating a New Class

An **AST** is the tree representation of source code after parsing. Example:

~~~java
public final class Person {
    private final String name;
}
~~~

A very simplified AST can be illustrated as:

~~~text
ClassDecl Person
  Modifier public final
  FieldDecl name
    Modifier private final
    Type String
~~~

An **AST transformation** tool can insert a constructor, getter, or method into the `Person` class tree before the relevant compiler phases finish:

~~~text
ClassDecl Person
  FieldDecl name
  ConstructorDecl Person(String name)   <-- inserted by transformer
  MethodDecl getName(): String          <-- inserted by transformer
~~~

This is **a diagram**, not output from a standard AST API usable across all compilers. The key point is that the **original** class after transformation gains extra members when bytecode is emitted, even though the source file does not contain those members textually.

### Why Can Standard JSR 269 Not Edit the Original AST?

`javax.lang.model.element.TypeElement` represents **declarations/types** for observation and analysis, rather than an AST node with an `addMethod(...)` method. `Filer` provides a mechanism for creating **new files** and is not a tool for editing an existing input source file. JSR 269 does not promise permission to edit internal compiler parser/attribution structures.

A processor can:
- Read the `Person` declaration and annotated fields.
- Generate `PersonBuilder.java` or `PersonMapper.java`.
- Emit a compile error if `Person` lacks a required condition.
- Generate resource metadata for runtime code to use.

It **cannot rely purely on standard JSR 269 APIs** to add a `getName()` method directly into the `Person` type being compiled.

### Compiler Tree APIs and Extensions

The JDK provides APIs such as `com.sun.source.tree` and `com.sun.source.util.Trees` to inspect source syntax trees when supplied by the compiler. **Reading** trees through published APIs does not equate to having a standard API to **arbitrarily mutate** compiler nodes and guarantee valid bytecode.

Tools wanting to mutate internal `javac` trees sometimes use `com.sun.tools.javac.*`, specialized plugins, internal hooks, or custom transformers. These details can change across JDKs, compilers, IDEs, and module boundaries. A system relying on internal APIs may require module-access flags or frequent updates when switching JDKs.

Therefore, separate three ideas:

1. **AST observation** (compiler tree inspection) for analysis or diagnostics.
2. **Generating separate sources** with JSR 269 (`Filer`): standard mechanism, easier to deploy across compilers.
3. **Modifying the AST being compiled**: deep intervention in the compiler pipeline, with support level and portability varying by tool.

## 8. Why Does Lombok Easily Cause Confusion?

Lombok annotations such as `@Getter`, `@Setter`, or `@Builder` often make developers see a class as if methods/constructors were added without writing them in source. Lombok integrates with compilers and IDEs to achieve that effect; in many `javac` environments, annotation processing is a **trigger point**, yet structural transformation uses **mechanisms/compiler internals beyond JSR 269's standard file-generation capabilities**.

Do not reason “Lombok uses an annotation processor, so any processor can mutate the original class via `TypeElement`”. A pure JSR 269 processor like the `GreetingProcessor` example only creates `AppGreeting.java`; Lombok aims to alter how the compiler understands the original class. These are two **different** models.

Design consequences:

- Processors generating separate classes produce `.java` files to inspect; codegen is explicit, though callers may need to reference helper classes.
- AST transformers provide a terser source experience yet depend deeply on the compiler/IDE.
- When upgrading JDKs, errors from AST transformers can differ from those of pure JSR 269 processors.
- IDE integration needs to understand generated sources or the corresponding AST plugin. An IDE reporting missing getters while command-line compilation succeeds is a sign to check IDE/plugin/config, not a reason to assume Java runtime reflection will “create getters” at runtime.

## 9. Annotation Processors Are Not Bytecode Transformers

There is another group of techniques: **transforming bytecode after classes are compiled**, or instrumentation when classes load.

| Mechanism | Input | Output/effect |
| --- | --- | --- |
| JSR 269 | Source/element model during compile | **New** source/class/resource files, diagnostics |
| AST transform | Syntax tree/compiler model | **Modified** tree or source prior to emitting bytecode |
| Bytecode transform | `.class` file/bytecode | **Rewritten** or transformed bytecode before execution |
| Runtime reflection | Loaded classes and metadata | Runtime inspection/invocation/access without modifying bytecode itself |

Bytecode manipulation libraries can use ASM or other mechanisms to edit instructions, fields, methods, or attributes in bytecode. Java agents can instrument classes during loading, subject to their own rules on timing and permitted changes. **Reflection is not equivalent to instrumentation**, and annotation processors are not Java agents by default.

Conceptual pipeline order:

~~~text
.java
  |
  +--> Parser / compiler AST
  |          |
  |          +--> JSR 269 processor: inspects model, generates new files
  |          |
  |          +--> compiler extension: may manipulate AST
  |
  v
.class
  |
  +--> bytecode transformer / agent (if any)
  |
  v
JVM loads/links/executes class
  |
  +--> runtime reflection: reads existing metadata and members
~~~

This diagram is a way to **distinguish functions**, not a guarantee of the exact order among all `javac` phases or all transformers; some frameworks combine multiple techniques.

## 10. Filer, Generated Sources, and Compiler Rounds: Rules to Remember

### Do Not Overwrite Input Source Code

A processor should generate **new files with clearly defined fully-qualified names and packages**. `Filer` manages files created within the processing environment; attempting to create duplicate paths in one processing run or collide with an input file can lead to `FilerException`/diagnostics. Do not try to open a `Writer` for a `TypeElement` and overwrite `App.java`: no such standard JSR 269 API exists.

### A Processor Can Serve Purely Validation Duties

Not every processor emits files. A processor checking that annotations sit on valid declaration kinds, database column names are valid, or API constraints are honored can call:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Unsupported annotation usage",
        element
);
~~~

This is a **snippet inside the body of `Processor.process`**, not standalone runnable code; variable `element` is an `Element` held by the processor. The compiler reports a positioned error when possible, failing the build. Neither reflection nor AST mutation is required to verify metadata at compile time.

### Rounds, Annotation Types, and Claiming

A processor can receive annotation types to examine in each round, generate sources causing another round, and be invoked in the final round with `processingOver() = true`. A processor should handle the final round, idempotency, and invalid inputs deliberately. `process(...)` returning `true` means claiming the annotation types it handles; it does **not** mean “more data generated” or “compilation succeeded”.

In the `GreetingProcessor` example, only `App` carries `@GenerateGreeting`; the newly generated class does not carry the annotation, so it does not trigger an infinite generation loop.

### Build Outputs Must Be Reproducible

When a processor creates filenames depending on timestamps, randomness, unstable element iteration order, or build-machine state, outputs can differ between two builds of identical source. For reliable builds:
- Base outputs on declaration inputs supplied by the compiler.
- Sort elements when ordering affects file contents.
- Use stable paths/encodings and avoid unnecessary dependence on the working directory.
- Avoid emitting unrelated extra files.
- Test the processor in incremental and clean builds per the build tool in use.

A processor is **code running inside the build**, so an untrusted processor library can execute actions against the build environment. Choose dependencies and versions carefully; do not treat annotation processors as harmless static metadata.

## 11. Configuring Processors: Explicit Discovery and Build Tools

Example used:

~~~bash
javac -cp build/greeting-processor.jar \
  -processorpath build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -s build/generated -d build/app \
  src/app/demo/App.java
~~~

Modes worth knowing:

- `-processor fully.qualified.Processor`: selects processors by name; convenient for labs and builds with explicit requirements.
- `-processorpath path`: where the compiler searches for processors to run. If unconfigured, different `javac` versions/configurations have different default processor lookup rules; do not rely on implicit discovery for reproducible builds.
- `META-INF/services/javax.annotation.processing.Processor`: `ServiceLoader` mechanism to advertise processors for discovery in environments allowing it. The file lists fully-qualified processor names, e.g., `demo.GreetingProcessor`.
- `-s dir`: where the compiler writes generated sources; helpful for debugging.
- `-proc:only`: runs only processing without generating class files as in ordinary compilation. Do not use it if your goal is immediately running the application without a subsequent compile.
- `-proc:none`: disables annotation processing, useful when diagnosing differences between plain sources and the codegen step.
- `-Akey=value`: passes processor-supported options; processors read them via `ProcessingEnvironment.getOptions()`.

JDK releases can change discovery defaults for security/build clarity; therefore a lab using **explicit** `-processor` gives more predictable results. In real applications, Maven/Gradle and IDEs should have annotation processor configurations aligned with CI builds.

**Note:** If processing is turned off in the lab, `App.java` referencing `AppGreeting` will fail to compile unless pre-generated classes/sources already exist. Clean generated outputs from prior runs before verifying so stale classes do not create the illusion that the processor is still running.

## 12. Reflection and Access Checks Do Not Grant Type-Modification Rights

Reflection is commonly used to read runtime annotations, list fields/methods, and access/invoke members subject to Java access checks, module boundaries, and runtime policies. However, that does not mean:

- You can call `Class.addMethod(...)`; **no such standard reflection API exists**.
- `Method.invoke(...)` adds a method to a class. It only invokes a method **that already exists**.
- A `@Retention(RUNTIME)` annotation generates behavior on its own. Runtime code must actually read and process it.
- `setAccessible(true)` bypasses all Java module restrictions. On Java 9+, strong encapsulation can block deep reflection if a package is not properly opened.

A framework using reflection may build proxy objects or synthesize another class via bytecode generation. In that case, **proxy/bytecode generation** is an additional mechanism, not reflection mutating the original class itself.

## 13. Scenarios for Choosing the Right Mechanism

### Generating Mappers/Builders from Schemas at Compile Time

Wanting to generate `UserMapperImpl` from annotations and interface declarations without modifying the original interface: a **JSR 269 processor** usually fits. Produces clear source, checks type errors during the build, and avoids runtime reflection per request.

### Validating Annotation Rules

Wanting to emit errors if `@Route` is placed on a non-public class or a method has invalid parameters: **annotation processors** and `Messager` fit well. No runtime execution is needed to catch statically checkable mistakes.

### Frameworks Discovering Endpoints at Application Startup

Wanting to find methods with `@Route` and register handlers at runtime: use **RUNTIME annotations + reflection/scanning**, or pre-generated codegen metadata/indexes to reduce runtime scanning. Annotation retention and lookup mechanisms must align with the design.

### Automatically Adding Getters to the Original Class Itself

Wanting to turn `class User { private String name; }` into a class possessing `getName()` without declaring the method in source: **pure JSR 269 does not provide this operation**. Other options are needed, such as editing sources/templates, generating subclasses/helpers, compiler AST extensions, or tools like Lombok with dedicated integration.

### Tools Modifying Bytecode Instructions

Wanting to add logging into compiled methods or instrument at class loading: look at **bytecode transformers/Java agents**. This is neither an annotation processor nor reflection in the standard sense, even if the tool decides what to transform based on annotations.

## 14. Common Errors and Misconceptions

| Symptom or claim | Cause / distinction to make |
| --- | --- |
| `cannot find symbol: AppGreeting` | Processor did not run, failed, generated under a different package/name, or generated sources were not compiled |
| SOURCE annotation does not appear in reflection | **Expected**, because SOURCE retention drops annotation metadata from class files |
| `getAnnotation(...)` returns `null` | No matching runtime annotation; check `@Retention(RUNTIME)`, actual declaration, `@Inherited`, and declared/inherited queries |
| Processor loaded yet generated nothing | No matching annotated elements, wrong annotation type name, or processor/round returned unexpectedly |
| `FilerException` due to duplicate file | A file was created twice in the same processing environment or collided with input; check rounds and output names |
| IDE does not recognize generated classes | Annotation processing disabled/misconfigured or generated sources missing from IDE model |
| Runs yet shows stale generated code | Old artifacts not cleaned; build tool incremental cache did not update properly |
| Processor “did not add getter to original class” | JSR 269 does not grant AST transformation rights for that |
| Lombok breaks on JDK upgrade | Likely due to differing compiler/IDE integration dependencies; check supported versions, do not assume reflection |
| Annotation present at runtime yet has no effect | No framework/code reads the metadata and executes behavior |
| Reflection cannot access member | Java accessibility and module encapsulation restrict reading/invocation |
| `AppGreeting.java` exists yet `AppGreeting.class` is missing | Only `-proc:only` processing ran or generated sources have not been compiled yet |

### Short Investigation Checklist

1. Does the annotation type have the right package, `@Target`, and appropriate retention?
2. Which JDK is running the compiler? Was the annotation processor selected via `-processor` or valid discovery?
3. Is the processor on the processor path, and is the annotation type on the compile classpath?
4. Did `-s` output any files? Did `Filer` report duplicates or IO errors?
5. Were generated sources compiled by the compiler, and does the runtime classpath contain the necessary outputs?
6. If runtime reflection is required, is the annotation truly `RUNTIME` and is the query checking the right `Class`/`Method`/`Field`?
7. If wanting to modify methods/fields of an existing class, are you mistakenly trying to use JSR 269 for the job of an AST transformer or bytecode tool?
8. If plugins/compiler internals are involved, are the current JDK and IDE supported by that tool?

## 15. Self-Check Exercises with Answers

**Exercise 1.** `@Check` has `RetentionPolicy.SOURCE`. Can a `javac` processor read that annotation? Can runtime reflection read it?

**Answer:** A processor can read it in the compilation model. Standard runtime reflection does not see SOURCE annotations on compiled classes.

**Exercise 2.** A processor calls `Filer.createSourceFile("demo.UserBuilder")`. Did it add a method directly to `demo.User`?

**Answer:** No. It created a source file for another type (`demo.UserBuilder`). Directly altering the contents of the original class requires mechanisms beyond standard `Filer` capabilities.

**Exercise 3.** `@Label` has `RetentionPolicy.RUNTIME` and `getAnnotation(Label.class)` returns the annotation properly. Does this prove `javac` ran a processor to generate code?

**Answer:** No. Reflection reads runtime metadata; an annotation's presence does not prove any processor ran.

**Exercise 4.** A tool inserts a getter into the AST currently being processed by `javac`. Can we say that tool uses only standard `javax.lang.model.element.TypeElement` and `Filer`?

**Answer:** No. Standard JSR 269 provides a declaration model and file-generation mechanism, not an API to mutate the original class's AST. The tool may use extensions/compiler internals.

**Exercise 5.** Why does `App.class.isAnnotationPresent(GenerateGreeting.class)` print `false` in the lab even though `AppGreeting.class` exists?

**Answer:** `@GenerateGreeting` has SOURCE retention so it is not retained for reflection to see. The generated class is a product of build-time processing; the two are independent.

**Exercise 6.** `-processorpath` points to the right processor JAR, yet the compiler cannot find `@GenerateGreeting` when compiling `App.java`. What needs checking?

**Answer:** The compile classpath or module path containing the annotation type imported by source, package/name, and presence of the corresponding class/source file. Processor path does not substitute for compile classpath for application types.

**Exercise 7.** Why should compiler AST internals not be used merely to generate a helper class?

**Answer:** When JSR 269 and `Filer` already suffice, using the standard API is usually easier to reproduce and less compiler-dependent. Internal AST mutation increases compatibility costs across JDKs, IDEs, and module boundaries.

## Key Takeaways

- **Annotations do not run on their own**; behavior comes from tools reading annotations.
- **JSR 269** is **compile-time** processing, inspecting `Element`/`TypeMirror`, emitting diagnostics, and generating new files via `Filer`; it is not standardized for mutating the AST of original classes.
- **Reflection** is **runtime** querying/invocation on loaded classes; reading annotations requires **RUNTIME retention** and runtime code actually processing the metadata.
- **AST transformation** can alter the structure of classes being compiled, yet is a separate mechanism and usually compiler/tool-dependent; some systems like Lombok combine annotation processing with compiler-specific integration.
- **Bytecode transformation** acts on classes post-compilation or at load time, distinct from reflection or JSR 269.
- For reliable builds, define processor path, compile classpath, generated source path, compiler rounds, and retention appropriately for your goal. Choose tools by **the effect needed**, not simply because they all share `@Annotation` syntax.
