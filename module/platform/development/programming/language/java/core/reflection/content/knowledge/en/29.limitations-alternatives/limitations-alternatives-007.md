# Distinguishing Runtime Reflection from Compile-Time Annotation Processing

**Java Reflection** and **Annotation Processing** both help a program or tool work with information about types and annotations. However, they operate at **two different phases**, with different APIs, access rights, and outputs:

- **Runtime Reflection:** the program is already compiled and running; it reads metadata about `Class`, methods, constructors, fields, or annotations visible at runtime, and can then instantiate objects or invoke methods according to access permissions. Typical APIs: `Class<?>`, `java.lang.reflect.*`.
- **Compile-time Annotation Processing:** the compiler runs processors over the source/type element model (`Element`, `TypeMirror`), inspects annotations, and **generates source code/resources or emits diagnostics** before the application runs. Typical APIs: `javax.annotation.processing.*`, `javax.lang.model.*`, `Filer`, and `Messager`.

Using an annotation for compile-time processing **does not imply** the application can read that annotation via Reflection; that depends on `@Retention`. Conversely, reading an annotation with `RUNTIME` retention at runtime does not cause an annotation processor to run automatically.

## 1. Placing Both Mechanisms on the Same Timeline

~~~text
.java source files
     |
     v
javac / build
     |
     +-- Annotation processor (0..n rounds)
     |      +-- reads Element, AnnotationMirror, TypeMirror
     |      +-- validates structure / reports compiler diagnostics
     |      +-- Filer generates .java or resources
     |                |
     |                +-- javac continues processing new sources in the next round
     |
     v
.class / JAR bytecode
     |
     v
JVM loads classes and executes the application
     |
     +-- Runtime Reflection
            +-- reads Class / Method / Field / Constructor metadata
            +-- reads annotations retained until runtime
            +-- instantiates objects / invokes methods when permitted
~~~

An annotation processor generates code from inputs available at compile time, whereas Reflection works with types/classes already loaded into the JVM. This does not mean every processor runs in a single round: `javac` can organize **multiple processing rounds** when processors generate additional source files. Runtime Reflection is not another compiler "processing round".

The two activities can **complement** each other: an annotation processor generates code so the application does not need heavy scanning or reflection at runtime; or a processor generates metadata for runtime code to load and use later. Nevertheless, they cannot automatically replace each other in every situation.

## 2. Comparing Against Practical Design Questions

| Criterion | Runtime Reflection | Compile-time Annotation Processing |
|---|---|---|
| Timing | After classes have been loaded in the JVM | While `javac`/build tool processes sources |
| Primary input | `Class` and reflection members on existing types | `Element`/`TypeMirror`, annotations, and compiler model |
| What is visible | Metadata retained in class files and exposed by runtime APIs | Source/element structure provided by the compiler, including `SOURCE` annotations |
| Must load/run app classes? | Usually has `Class<?>`; some Reflection operations can trigger code | Does not need to instantiate application instances to inspect elements |
| Ability to invoke business logic | Possible via `Constructor.newInstance`, `Method.invoke` | No concept of "running instances of classes being compiled" |
| Generating build files | Not a core function of Reflection | Has `Filer` to generate source/class/resources per compiler rules |
| Reporting build errors | Not directly; errors usually appear only at runtime | Has `Messager` to report `ERROR`, warnings, and source locations |
| Runtime dependencies | Depends on metadata/runtime APIs used | Processor code does not necessarily ship in the runtime artifact |
| Main limitations | Access control/JPMS, dynamic names/signatures, runtime cost, retention | Knows only compile-time info; processor config and generated sources must be valid |
| Use cases | Plugin loaders, runtime DI, serializers, command dispatchers | Generators, type-safe adapters, compile-time API validation, metadata indexes |

**A common wrong choice:** using `Class.forName` and runtime Reflection to detect misconfigurations that the compiler already had enough information to catch. If a tool can check a contract from source, annotation processing can move errors to build time. However, if extensions are selected only when the application runs (for example plugin classes added later), a compile-time processor cannot foresee all runtime plugins.

## 3. Annotation Retention Decides Whether Reflection Sees It

Annotations in Java have `@Retention` from `java.lang.annotation.RetentionPolicy`:

| Retention | Compiler/processor at compile time | Class file after compilation | Reflection read via `getAnnotation` |
|---|---|---|---|
| `SOURCE` | Readable in appropriate processing rounds | Normally not written into the class file | **No** |
| `CLASS` | Readable via the compiler model | Retained in the class file | **No**, under standard Reflection |
| `RUNTIME` | Readable via the compiler model | Retained in the class file | **Yes**, on the matching element |

`RetentionPolicy.CLASS` is the default value if an annotation omits `@Retention`. This does not mean `CLASS` will appear in `Class.getAnnotation(...)` results.

An example annotation used only at compile time:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface AutoGreeting {}
~~~

An example annotation needing lookup at runtime:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RuntimeLabel {
    String value();
}
~~~

Both snippets above are **illustrative fragments**; the full version with imports is in Section 5. Choosing retention should be based on need:

- `SOURCE`: rules meant solely for source-time processors; does not add annotation metadata to compiled class files.
- `CLASS`: metadata kept in class files for bytecode analysis tools; not a standard Reflection API target.
- `RUNTIME`: running code needs to read `Class`/`Method`/`Field` annotations via Reflection.

**Do not raise all annotations to `RUNTIME` just because a tool uses annotation processing.** A processor can work with `SOURCE` annotations, and runtime does not need to see them.

`@Target` restricts where an annotation may be applied (for example `TYPE`, `METHOD`, `FIELD`); it is independent of `@Retention`. A `RUNTIME`-retained annotation placed on a method still must be read from the corresponding `Method`; do not assume `SomeClass.class.getAnnotation(...)` will automatically scan all method annotations.

## 4. Different APIs and Programming Models

### 4.1. Reflection Side

Common calls:

~~~java
Class<?> type = Demo.class;
Method[] methods = type.getDeclaredMethods();
RuntimeLabel label = type.getAnnotation(RuntimeLabel.class);
~~~

This is an **illustrative fragment**, assumed to sit inside a program with `Demo` and `RuntimeLabel` from Section 5 along with `import java.lang.reflect.Method;`.

`Class<?>` describes a type at runtime. `getDeclaredMethods()` returns directly declared methods, with no guaranteed order and excluding inherited methods. `getAnnotation(RuntimeLabel.class)` looks up a `RuntimeLabel` annotation visible to Reflection on the `Class` object.

If you need to invoke behavior:

~~~java
Constructor<?> constructor = type.getConstructor();
Object instance = constructor.newInstance();
Method method = type.getMethod("run");
method.invoke(instance);
~~~

This is an **API illustrative fragment**, not runnable against `Demo` in Section 5 because `Demo` does not declare `run()`. Finding a member **does not guarantee** it can be invoked: Java/JPMS access rights, receiver, and parameter signatures must still be valid. `Method.invoke` can wrap exceptions thrown by the target method in `InvocationTargetException`. `Class.forName(...)` can load and initialize a class when using the single-parameter overload; runtime Reflection operations do not always merely read metadata.

### 4.2. Annotation Processor Side

An `AbstractProcessor`-style processor receives:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv)
~~~

Typical APIs:

- `RoundEnvironment.getElementsAnnotatedWith(...)`: finds annotated elements in the current round.
- `Element`: represents a declaration, such as a class/method/field; `TypeElement` represents a type declaration.
- `TypeMirror`: describes a type in the compiler model, not equivalent to obtaining `Class<?>` at runtime.
- `ProcessingEnvironment.getElementUtils()` and `getTypeUtils()`: look up elements/types and type relationships.
- `Filer.createSourceFile(...)`: creates a new Java source output file for the compiler to process.
- `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`: emits diagnostics, which can fail the build.
- `RoundEnvironment.processingOver()`: signals the final round, when no normal processing rounds remain to generate additional sources.

A processor can inspect names, modifiers, types, annotations, and sources parsed by the compiler without instantiating classes under inspection. **Do not use `Class.forName` to read source classes currently being compiled as a substitute for `Element`**: those classes might not exist as bytecode yet, or stale bytecode on the classpath could produce wrong results.

## 5. Java 17 Example: Processor Generates Code, Reflection Reads Runtime Annotation

The example has **four files in the same directory**, with no package declaration to keep standalone testing simple. In production code, use explicit packages and fully qualified annotation names for `@SupportedAnnotationTypes`.

Goals:

1. `@AutoGreeting` has `SOURCE` retention. The processor sees it at compile time and generates `GreetingGenerated.java`.
2. `@RuntimeLabel("active")` has `RUNTIME` retention. The application uses Reflection to read the string `active`.
3. Application code calls `GreetingGenerated.message()` like **an ordinary Java method**, without needing `Method.invoke`. This demonstrates one benefit of code generation: the method is known and type-checked at build time.

### 5.1. File `AutoGreeting.java`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface AutoGreeting {}
~~~

### 5.2. File `RuntimeLabel.java`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RuntimeLabel {
    String value();
}
~~~

### 5.3. File `GreetingProcessor.java`

~~~java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("AutoGreeting")
public class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.RELEASE_17;
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (generated || roundEnv.processingOver()
                || roundEnv.getElementsAnnotatedWith(AutoGreeting.class).isEmpty()) {
            return false;
        }

        generated = true;
        try {
            JavaFileObject file =
                    processingEnv.getFiler().createSourceFile("GreetingGenerated");
            try (Writer writer = file.openWriter()) {
                writer.write(
                        "public final class GreetingGenerated {\n"
                        + "  public static String message() {\n"
                        + "    return \"Generated at compile time\";\n"
                        + "  }\n"
                        + "}\n");
            }
        } catch (IOException e) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Cannot generate source: " + e);
        }
        return true;
    }
}
~~~

Details to understand:

- `@SupportedAnnotationTypes("AutoGreeting")` tells the processor which annotation types it handles. The name in the example is in the **unnamed package**; real code uses a qualified name, such as `"com.example.AutoGreeting"`.
- `process(...)` is invoked by the compiler across **processing rounds**. The `generated` field prevents attempting to regenerate the same file when a subsequent round runs.
- `Filer.createSourceFile("GreetingGenerated")` declares a new Java file under the generated-sources directory managed by the compiler. The new file is examined/compiled by the compiler as processing continues.
- `process(...)` returns `true` when the processor **claims** the annotation types it handles, preventing other processors from receiving claimed annotation types in the same dispatch mechanism; returning `true` does not mean the compiler stops all rounds.
- `Messager` emits a diagnostic at `ERROR` level when source generation fails; the compiler/build can halt with an error status.
- A processor is a **compiled program loaded for the compiler to run**. It is not merely an annotation placed in source code.

This is a single-source-class demo. A real generator must handle output names per element, collisions, incremental builds, idempotency, package naming, and cases with multiple annotated types; avoid using a single shared flag to generate one file for all types if the feature requires one file per type.

### 5.4. File `Demo.java`

~~~java
@AutoGreeting
@RuntimeLabel("active")
public class Demo {
    public static void main(String[] args) {
        RuntimeLabel runtime = Demo.class.getAnnotation(RuntimeLabel.class);
        AutoGreeting sourceOnly = Demo.class.getAnnotation(AutoGreeting.class);

        System.out.println("runtime label = " + runtime.value());
        System.out.println("SOURCE annotation visible = " + (sourceOnly != null));
        System.out.println("generated method = " + GreetingGenerated.message());
    }
}
~~~

The expression `Demo.class.getAnnotation(AutoGreeting.class)` **compiles validly** because the `AutoGreeting` annotation type is on the classpath. However, this annotation has `SOURCE` retention, so that annotation metadata does not exist in `Demo.class` and Reflection returns `null`. Conversely, `RuntimeLabel` has `RUNTIME` retention, so `getAnnotation(...)` reads `"active"`.

### 5.5. Step-by-Step Compilation and Execution

Run from the directory containing all four files. The commands below work with Java 17+ `javac`/`java`; trailing `\` is only a shell convention in multiline examples, so executable commands are written **one command per line**:

~~~bash
mkdir build
mkdir generated
javac --release 17 -encoding UTF-8 -d build AutoGreeting.java RuntimeLabel.java GreetingProcessor.java
javac --release 17 -encoding UTF-8 -cp build -processorpath build -processor GreetingProcessor -s generated -d build Demo.java
java -cp build Demo
~~~

**Windows note:** Creating directories with `mkdir` in PowerShell or CMD works when the directories do not yet exist. If retrying where `build`/`generated` already exist, create a fresh example folder or delete the demo's own outputs so you do not accidentally reuse `GreetingGenerated.class` from an earlier run.

Explaining the two `javac` commands:

1. The first command compiles the annotation types and the processor. The compiler needs to find the **compiled** `GreetingProcessor` class in the next step.
2. The second command uses `-cp build` so `Demo` finds the required annotations and classes; `-processorpath build` so the compiler loads the processor; `-processor GreetingProcessor` activates the specified processor; `-s generated` selects where **generated source** is saved; `-d build` selects where **compiled classes** are saved.
3. The processor receives `@AutoGreeting` on `Demo`, generates source for `GreetingGenerated`, and the compiler compiles the generated class. `Demo` calls this class like an ordinary type-checked dependency.
4. Finally, the `java` command runs the program and invokes runtime Reflection.

**Verified stdout with `javac --release 17`:**

~~~text
runtime label = active
SOURCE annotation visible = false
generated method = Generated at compile time
~~~

After compilation, you may see typical output files:

~~~text
build/
  AutoGreeting.class
  RuntimeLabel.class
  GreetingProcessor.class
  Demo.class
  GreetingGenerated.class
generated/
  GreetingGenerated.java
~~~

This is an **illustrative file tree**, not showing all possible metadata. Both `AutoGreeting` and `RuntimeLabel` classes exist as annotation types, but the **`@AutoGreeting` annotation placed on `Demo`** is absent from `Demo.class` bytecode because of `SOURCE` retention. Do not confuse "the class defining the annotation was compiled" with "the annotation marker attached to an element was retained".

**A meaningful experiment:** In a clean build directory, omit `-processor GreetingProcessor` or omit the processor path when compiling `Demo.java`; the compiler will not generate `GreetingGenerated`, and calling the generated class will lead to a cannot-find-symbol error. Create a clean build before testing so stale outputs do not mask the issue. Automatic processor discovery also depends on JDK/build-tool version configuration and service registration; this example explicitly specifies `-processor` so it does not depend on auto-discovery.

## 6. Annotation Processor Lifecycle and Source-Time Limits

Several easily overlooked differences:

**Multiple rounds.** A processor generating a Java file in an earlier round can cause the compiler to run an additional round to process new declarations. Do not try to create the same file name via `Filer` across multiple rounds: doing so can cause `FilerException`. Generator designs should tie outputs to source elements and determine unique names.

**Not a runtime classloader.** Compiler models `TypeElement` and `TypeMirror` do not necessarily correspond to a `Class<?>` loadable in the JVM running the processor. Do not call `newInstance` on a class being compiled to "test" an annotation. If you need to inspect methods/fields by signature, use `Elements`/`Types` utilities from the compiler.

**Do not edit user-written source.** A processor should generate **new files** via `Filer` or emit errors/warnings, rather than overwriting sources being compiled. Under standard Java JSR 269, processors are not arbitrary syntax-rewriting tools for existing classes or bytecode. Some libraries use compiler internals/AST rewriting, bytecode instrumentation, or custom compiler plugins; do not treat those as default `AbstractProcessor` capabilities.

**Not all sources are guaranteed present in every round.** Processors must tolerate the round cycle; if depending on another processor's output, manage ordering and availability rather than assuming every generated class exists in the very first round.

**Processors are build-time executable code.** A processor dependency is executed by the compiler in the build environment; control dependency provenance, build-environment file/network access permissions, and reproducibility just like build plugins. Input annotation metadata may be untrusted; do not treat a processor as a complete security filter for runtime data.

## 7. Limits of Runtime Reflection

Reflection operates only within classes/modules visible to the runtime and members accessible to the API. It cannot:

- Recover `SOURCE` annotations stripped from class files after compilation.
- Replace the compiler to catch syntax/type errors before the program is compiled.
- Access private members across JPMS by default merely by calling `getDeclaredFields()`.
- Retroactively generate `GreetingGenerated.java` in past processing rounds. You can write code that generates source at runtime, yet that is a different pipeline, not annotation processing of the completed build.
- Fully enforce business rules solely from field/type/annotation names. Runtime annotations can carry metadata, but validation requires an active API/engine to execute it.

`setAccessible(true)` can be denied when another module's package is not appropriately `opens`; `IllegalAccessException` or `InaccessibleObjectException` may appear on individual call paths. Designing tools around public APIs is usually more durable than relying on deep reflection.

**On performance:** Reflection incurs lookup/dispatch overhead and limits compile-time type checking; annotation processors can generate explicit code to reduce runtime introspection, at the cost of a more complex build pipeline. Do not assume generated code is always faster than every Reflection path: measure real workloads, considering metadata caching and initialization cost.

**On deployment:** In environments restricting dynamic class metadata, AOT/native image, or runtimes with special packaging policies, compile-time code generation can be advantageous. Yet concrete support depends on the runtime/toolchain and metadata configuration, with no absolute rule for every Java project.

## 8. Choosing a Tool by Requirement

| Requirement | Reasonable starting choice | Why |
|---|---|---|
| Catch mistyped annotation usage at build time | Annotation processor | Has compiler model and `Messager.ERROR` |
| Generate fixed adapters/mappers from source types | Annotation processor | Generated code is type-checked by the compiler and callable directly |
| Build docs/indexes from annotations in source | Annotation processor | Extracts metadata during compilation and generates resources |
| Discover new plugins appearing after app startup | Reflection or runtime contract/plugin discovery | Compiler cannot know all runtime types ahead of time |
| Read annotations used to drive runtime behavior | Reflection + `RUNTIME` retention | Annotations are present in runtime metadata |
| Invoke methods by names from runtime configuration | Reflection or controlled runtime dispatch | Names are decided after compilation |
| Reduce startup scanning when type lists are known upfront | Compile-time index / code generation | Shifts discovery to build time |
| Need a shared contract for plugins with fixed structure | Interface / factory / `ServiceLoader` before deep Reflection | Clear API, preserves type checking and access control |

**A third option is often better:** If you already know the interface or service contract, plain Java, interfaces, factories, or `ServiceLoader` can be simpler than either a generator system or complex dynamic invocation. There is no need to apply annotation processing when checks are already guaranteed by the language/type system.

A practical framework may choose a **hybrid**:

1. An annotation processor generates registries/adapters for types visible at build time.
2. A runtime registry instantiates objects via constructors/factories and calls statically typed methods.
3. Reflection handles only dynamic types outside the build-time list if the use case truly requires it.
4. Both paths must enforce module access, API contracts, data validation, and error handling.

## 9. Common Errors and How to Verify

| Symptom | Possible cause | How to verify |
|---|---|---|
| `getAnnotation(MyAnnotation.class)` returns `null` | `SOURCE`/`CLASS` annotation, wrong element, annotation absent | Check `@Retention`/`@Target` and the queried element |
| Processor does not run | Missing `-processor`, unregistered service, wrong processor path, unconfigured build tool | Perform clean compile; check `-processorpath` and processor discovery |
| `cannot find symbol GreetingGenerated` | Generated source was not created/compiled, or wrong classpath | Check `-s`, `-d` directories and compiler diagnostics |
| `FilerException: Attempt to recreate a file` | Generating the same name multiple times across rounds or processors | Manage output names and track generated elements |
| Runtime throws `ClassNotFoundException` | Class is not on the classpath/module path visible to the loader | Check packaging and runtime class loader |
| Runtime throws `InaccessibleObjectException` | Deep reflection blocked by JPMS | Design via public APIs or intentionally granted `opens` policy |
| "Annotation is readable" yet logic does not run | Reflection only reads metadata; it does not auto-execute handlers/validators | Invoke the proper engine or explicit call |
| Generated class appears even after disabling processor | Stale class file from an earlier build | Perform a clean build output to verify |

### Self-Practice

1. Change `@Retention(RetentionPolicy.SOURCE)` on `AutoGreeting` to `CLASS`, then to `RUNTIME`. Before each run, perform a clean recompile; compare `Demo.class.getAnnotation(AutoGreeting.class)`.
2. Remove `@RuntimeLabel("active")` from `Demo` and confirm `getAnnotation(RuntimeLabel.class)` returns `null`. Update the program to check for `null` before calling `value()`; explain the NPE if unchecked.
3. Omit `-processor GreetingProcessor` in the second compile on a clean build. What error does the compiler report and why?
4. Modify the processor to generate a method returning a different string and rebuild. Which step must be rebuilt before the runtime output changes?
5. Change `@SupportedAnnotationTypes("AutoGreeting")` to a non-matching name. What happens to `GreetingGenerated`? Why?
6. Design a `@MinLength(3)` annotation for method parameters or fields: state cases suited for compile-time checking and cases requiring runtime data validation. Do not assume an annotation creates validation on its own.
7. When a plugin is loaded from a new JAR after the application was built, choose among Reflection, code generation, or interface/`ServiceLoader`. Explain which facts are absent at compile time.
8. In a JPMS application, why does a processor successfully reading the source model not prove the runtime can invoke that type's private constructor?

**Key takeaway:** Annotation processing is **compiler work** over the source/type model to check and generate code; Reflection is **JVM work at runtime** over class/member metadata and access rights. `RetentionPolicy.SOURCE` serves compile-time processing; `RetentionPolicy.RUNTIME` lets Reflection read the corresponding annotation. Choose the mechanism based on **when you have enough information**, the kind of output needed, checking requirements, and maintenance cost.

### Official Java 17 Documentation

- [Annotation Processing: `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html)
- [`RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [`Filer` for generating sources and resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [`RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [`Class.getAnnotation` / `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [`javac` options including `-processor` and `-processorpath`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)