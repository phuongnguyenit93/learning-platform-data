# Limitations of the Standard API: Generating Files vs. Modifying the Syntax Tree with Custom Tools

## 1. What Can and Cannot an Annotation Processor Do?

When placing an annotation on a Java class, many people expect the compiler to automatically add fields, getters, constructors, or modify methods of that class itself. It is necessary to distinguish **two completely different groups of capabilities**:

1. **Standard annotation processing (JSR 269):** analyzes declaration structures, checks rules, reports errors/warnings, and **generates new files** (Java source, class files, or resources) through `Filer`.
2. **Syntax tree/compiler AST transformation:** intervenes in the structure of an existing compilation unit, such as **inserting a new method into a class being compiled**. JSR 269 and `Filer` **do not provide a standard, guaranteed API to do this**; it requires specialized mechanisms, rewrite tools, or other APIs/compiler internals.

Example:

~~~java
@GenerateGreeting
class Client {}
~~~

A standard processor can **create an additional** `ClientGreeting` class:

~~~java
final class ClientGreeting {
    static String text() {
        return "Hello, Client!";
    }
}
~~~

However, using `Filer` alone, it cannot directly add the `text()` method into **`Client`**, making `new Client().text()` a valid call on the source class itself. That is the difference between **generating a new compilation unit** and **modifying an existing compilation unit**.

### Compilation Flow Diagram

~~~text
Initial source files: Client.java, Main.java, annotation type
         |
         v
javac analyzes source / type / symbol
         |
         +--> javax.lang.model (Element, TypeMirror, AnnotationMirror)
         |         reads declarations and annotations
         |
         +--> Processor / RoundEnvironment
         |       +-- Messager: reports errors / warnings / notes
         |       +-- Filer: generates NEW FILE
         |               ClientGreeting.java
         |
         +--> Next round can process the new source
         |
         v
Compiles .class for running / packaging

To directly modify the AST of Client:
  requires a compiler-specific mechanism or custom source rewriter,
  NOT a standard operation of Filer.
~~~

An annotation processor runs **at compile time**, not when the application is running. Annotations with `SOURCE` retention are still completely useful for triggering a processor.

## 2. Standard APIs of Annotation Processing

JSR 269 is provided in the JDK's `java.compiler` module. Typical components:

| Component | Primary Responsibility | Not Guaranteed |
|---|---|---|
| `Processor` / `AbstractProcessor` | Receives processing rounds and supported annotations | Adding methods to a source class |
| `RoundEnvironment` | Finds elements in a round, checks `processingOver()` | Directly modifying the AST |
| `Element`, `TypeElement`, `ExecutableElement` | Describes classes/methods/fields/parameters | Standard setters to transform declarations |
| `TypeMirror`, `Types` | Analyzes and compares types | Rewriting syntax |
| `AnnotationMirror`, `AnnotationValue` | Reads metadata inside the compiler, including `SOURCE` annotations | Executing business behavior of the annotation |
| `Elements`, `ElementFilter` | Looks up types, filters fields/methods and structures | Changing bytecode of an existing class |
| `Messager` | Reports `ERROR`, `WARNING`, `NOTE` at declaration locations | Creating or updating files |
| `Filer` | Generates **new** source/class/resource files in tool-managed output | Entering a source class and altering the syntax tree |

A processor can be defined with:

~~~java
@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        // Read declarations, report diagnostics, generate files.
        return true;
    }
}
~~~

This is only an **illustrative skeleton**, without imports or a complete body yet. Section 5 will provide a complete version that compiles and runs on Java 17+.

## 3. What Types of Files Does `Filer` Generate?

The processor obtains `Filer` from the compilation environment:

~~~java
Filer filer = processingEnv.getFiler();
~~~

Main APIs:

| Method | Meaning |
|---|---|
| `createSourceFile("demo.Generated", origins...)` | Creates a **new Java source**, returning a `JavaFileObject` to write content to |
| `createClassFile("demo.Generated", origins...)` | Creates a **new class file**, where the processor writes valid bytecode itself |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | Creates a new resource, such as a registry, service descriptor, or metadata |
| `getResource(location, moduleAndPkg, relativeName)` | Accesses an existing resource for reading |

**`createSourceFile` does not write getters automatically:** it only creates a new destination file. The processor needs to write the **entire source code** of the new type to the `Writer`.

~~~java
JavaFileObject output = processingEnv.getFiler()
        .createSourceFile("demo.ClientGreeting", sourceElement);
try (Writer writer = output.openWriter()) {
    writer.write("package demo;\n"
            + "public final class ClientGreeting {}\n");
}
~~~

This is an **API snippet inside a processor**, not a standalone Java file: it requires `processingEnv`, `sourceElement`, and imports/exception handling.

Essential points to understand:

- The name `demo.ClientGreeting` is mapped by the compiler/tool to a source output path such as `generated/demo/ClientGreeting.java`. Do not pass an arbitrary path to a user source file in order to “modify” it.
- `originatingElements` indicates the source declarations that produced the output; this is a useful hint to build tools regarding dependencies/incremental processing, and does not guarantee incremental builds will automatically be correct in every environment.
- You **must close** the `Writer` or `OutputStream`. Source and class files created through Filer are only recognized by the tool for processing in the next round after the stream is closed.
- `createClassFile` requires **real class bytecode**, not a Java source code string with a renamed `.class` extension.
- `createResource` creates a resource. **A resource is not automatically registered as a source/class input for the next round**, even if you give the resource a name that looks like a Java file.

### An Important Nuance Regarding Existing Output

“Filer creates new files” means creating them according to the **output model managed by the compilation tool**, not asserting that the pathname on disk has never existed before. Within **a single invocation**:

- A pathname may only be created **once**; creating it a second time will cause a `FilerException`.
- The initial input files are considered to have already appeared in the first round, so you cannot create source/class files corresponding to them to modify them.
- If the pathname of a generated output **from a previous invocation** already exists on disk, the tool may rewrite that output on the new build according to Filer's contract.
- A processor **must not intentionally overwrite files that are not generated artifacts**, and in particular must not treat Filer as permission to arbitrarily modify user files.

This is why `Filer` **cannot replace a source editor**. Nor should you do so by writing directly to `src/main/java` from a processor.

## 4. Annotation Processing Rounds

Annotation processing typically has **multiple rounds**, rather than a `process()` method running only once:

~~~text
Round 1: compiler sees @GenerateGreeting on Client
         -> processor generates ClientGreeting.java, closes Writer
Round 2: compiler picks up newly generated source
         -> if there are other annotations, corresponding processors may run
Final round:
         -> round.processingOver() == true
         -> no subsequent processing round for new output
~~~

This diagram shows a typical case, not the exact schedule for every compiler implementation.

`RoundEnvironment` provides:

- `getElementsAnnotatedWith(TypeElement)`: the elements carrying a specific annotation in the current round.
- `getRootElements()`: the root elements provided by the compiler in that round.
- `processingOver()`: indicates that the processing rounds are over.

Because a processor may be invoked multiple times, **avoid recreating the same class source in different rounds**. The Filer contract treats recreating the same pathname within a single invocation as an error.

Depending on the goal, a processor can return `true` to claim the supported annotation types or `false` to let other processors inspect them as well. The return value **does not determine AST modification**.

## 5. Java 17+ Practice: Generating `ClientGreeting` from an Annotation

This hands-on exercise has **four source files**. We place the processor in the *default package* to keep the CLI commands short, while the business classes are placed in the `demo` package.

Initially:

~~~text
project/
├── GreetingProcessor.java
└── src/
    └── demo/
        ├── GenerateGreeting.java
        ├── Client.java
        └── Main.java
~~~

### 5.1. `GreetingProcessor.java`

~~~java
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
public class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) return true;

        TypeElement marker = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateGreeting");
        if (marker == null) return false;

        for (Element element : round.getElementsAnnotatedWith(marker)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Only classes are supported",
                        element);
                continue;
            }

            String simple = element.getSimpleName().toString();
            String generated = simple + "Greeting";
            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile("demo." + generated, element);
                try (Writer writer = source.openWriter()) {
                    writer.write("package demo;\n"
                            + "public final class " + generated + " {\n"
                            + "  private " + generated + "() {}\n"
                            + "  public static String text() {\n"
                            + "    return \"Hello, " + simple + "!\";\n"
                            + "  }\n"
                            + "}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.getMessage(), element);
            }
        }
        return true;
    }
}
~~~

Explanation:

1. `@SupportedAnnotationTypes("demo.GenerateGreeting")` specifies the annotation that the processor handles.
2. `getTypeElement(...)` retrieves the symbol of the annotation type via the compiler model.
3. `round.getElementsAnnotatedWith(marker)` finds the annotated declarations.
4. `ElementKind.CLASS` restricts the demo to classes; even though the `@Target(TYPE)` annotation could also be attached to other types, the demo intentionally rejects them.
5. `element.getSimpleName()` of `Client` is `Client`; the generated name is `ClientGreeting`.
6. `createSourceFile("demo.ClientGreeting", element)` **creates a new class**, without altering `Client`.
7. `try-with-resources` closes the writer so the tool can process the source.
8. `IOException`/`FilerException` errors are reported via `Messager` so the build receives the information.

**Intentional limitations:** the demo hard-codes the `demo` package and is designed for simple top-level classes. A production processor needs to handle packages via `Elements.getPackageOf`, nested types, name collisions, modules, validation, escaping, and various compiler configurations.

### 5.2. `src/demo/GenerateGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {}
~~~

`SOURCE` is sufficient for an annotation processor because it inspects metadata **at compile time**. `RUNTIME` is not needed solely for code generation.

### 5.3. `src/demo/Client.java`

~~~java
package demo;

@GenerateGreeting
public class Client {}
~~~

The `Client` class does not have a `text()` method, and the processor does not modify `Client.java`. Placing the annotation does not make `new Client().text()` a valid call.

### 5.4. `src/demo/Main.java`

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(ClientGreeting.text());
    }
}
~~~

`Main` calls the **separately generated** class. The compiler picks up the output through the processing rounds and can resolve the name `ClientGreeting` when compiling the application.

### 5.5. Commands to Run

In the `project` directory, on Bash:

~~~bash
mkdir -p processor-classes generated classes

javac --release 17 -d processor-classes GreetingProcessor.java

javac --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor GreetingProcessor \
  -s generated \
  -d classes \
  src/demo/GenerateGreeting.java \
  src/demo/Client.java \
  src/demo/Main.java

java -cp classes demo.Main
~~~

In PowerShell/CMD, run the second `javac` command on **one line** or use line continuation according to that shell's syntax; the trailing `\` character above is for Bash.

**Verified stdout:**

~~~text
Hello, Client!
~~~

Generated file:

~~~text
generated/demo/ClientGreeting.java
~~~

Generated source content:

~~~java
package demo;
public final class ClientGreeting {
  private ClientGreeting() {}
  public static String text() {
    return "Hello, Client!";
  }
}
~~~

You can additionally check `classes/demo/ClientGreeting.class` after compilation. This example was run successfully with `javac --release 17`, the processor generated the expected file, and `java -cp classes demo.Main` printed the exact line above.

**Note on `-proc:only`:** If you add `-proc:only` to `javac`, the compiler only runs annotation processors and does not complete the normal class-generation step for the application; you cannot assume `java demo.Main` will run immediately afterward without another compilation.

## 6. `FilerException` Is Not a Signal to “Overwrite an Old Class”

Within a single invocation, this snippet is **intentionally wrong**:

~~~java
filer.createSourceFile("demo.ClientGreeting", sourceElement);
// Processor creates the same name again within the invocation:
filer.createSourceFile("demo.ClientGreeting", sourceElement);
~~~

The second call violates the contract and can throw `FilerException`. Similarly, attempting to create `demo.Client` when `demo.Client` is already a source input cannot be used to “inject methods” into the existing class.

Other causes:

- Two processors both try to create the same fully qualified name.
- A processor creates both a source file and a class file for the same type.
- The generated name is invalid or an output module cannot be selected.
- A resource pathname is recreated within a single invocation.

The solution is to **design stable, non-conflicting generated names** and create each file once; do not retry overwriting the file or silently ignore errors.

### Generating a Separate Resource

Snippet inside a processor:

~~~java
import javax.tools.FileObject;
import javax.tools.StandardLocation;
import java.io.Writer;

FileObject file = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/example/registry.txt",
        sourceElement);
try (Writer writer = file.openWriter()) {
    writer.write("demo.Client\n");
}
~~~

The snippet above is not a standalone program (it requires the `processingEnv` environment and exception handling). The resource output has a relative path managed by the tool. If multiple elements need to contribute content to the **same registry**, collect the data and write the file **once**, rather than repeatedly opening the same pathname.

### Generating a Class File Directly

`createClassFile("demo.Generated", ...)` requires the processor to write **`.class` data in valid JVM format**; you cannot write Java source text into this file. When custom bytecode techniques are not yet needed, `createSourceFile` is an easier-to-test choice and allows javac to check syntax, generic types, and language rules.

## 7. `Element` Is Not a Syntax Tree with Setters

A processor can read:

~~~java
for (Element e : round.getElementsAnnotatedWith(marker)) {
    System.out.println(e.getKind());
    System.out.println(e.getSimpleName());
    System.out.println(e.getEnclosedElements());
}
~~~

However, JSR 269 does not provide methods such as:

~~~java
// INTENTIONAL PSEUDOCODE, NOT A JAVA API:
e.addMethod("getId", ...);
e.removeField("password");
e.replaceMethodBody(...);
~~~

`Element` is a model of **declarations**, whereas `TypeMirror` describes **Java types**. `getEnclosedElements()` provides a list of declarations, not a list where you can insert a method and have the compiler automatically synchronize all symbol tables, type attribution, and bytecode.

A processor can **create a new class that interacts with the old class**, but that does not mean the old class is modified.

## 8. Compiler Tree API: Reading the AST vs. Modifying the AST

The JDK provides the Compiler Tree API in the `jdk.compiler` module:

- `com.sun.source.tree.Tree` along with `ClassTree`, `MethodTree`, `VariableTree`, `AnnotationTree`...
- `com.sun.source.util.Trees` to associate an `Element` with its source tree when available.
- `TreePath`, `TreePathScanner`, `TreeScanner` to traverse the tree.
- `SourcePositions` to find syntactic positions within a compilation unit.

Example of **reading** the tree in a processor executed by javac:

~~~java
import com.sun.source.tree.Tree;
import com.sun.source.util.Trees;

// Inside AbstractProcessor, with a valid Element element:
Trees trees = Trees.instance(processingEnv);
Tree tree = trees.getTree(element);
if (tree != null) {
    System.out.println(tree.getKind());
}
~~~

The snippet must be placed in an appropriate processor and does not compile standalone. For an element without a corresponding source tree, `getTree(...)` may return `null`; this depends on whether the compiler/tool supports `Trees`.

**Boundary to remember:** The public Compiler Tree API provides interfaces for **querying and traversing the AST**, but has no guaranteed general-purpose AST rewrite mechanism like `addMethod(ClassTree, ...)`. Having access to the source tree does not grant the ability to modify nodes with a standard setter that causes javac to adopt the changes.

## 9. Compiler-Specific Tools, Plugins, and Internal AST Manipulation

Some libraries/tools can add code as if it were inside the already-written class. However, it is important to distinguish the approaches:

| Approach | Effect | Trade-offs |
|---|---|---|
| **JSR 269 + Filer** | Generates **new** source/class/resource files | Does not directly mutate an existing class |
| **Javac plugin via `com.sun.source.util.Plugin`** | Integrates with the compiler, registers `TaskListener`, and observes phases | The public plugin API does not include a general-purpose AST editor |
| **Javac internals** | Manipulates objects such as `com.sun.tools.javac.tree.JCTree`, `TreeMaker`, symbols | Depends on compiler implementation, JDK version, module access, IDE |
| **Source-to-source rewriting** | Uses a parser/refactoring engine to produce a new version of the source before compilation | Requires managing source ownership, formatting, imports, and synchronization |
| **Bytecode transformation** | Modifies/generates `.class` code in another pipeline | Does not give the Java source the method itself at compile time; requires classpath synchronization |
| **Runtime proxy/instrumentation** | Creates wrappers/proxies or alters behavior at runtime | Not equivalent to modifying declarations in the source |

For example, getter-supporting annotations such as Lombok may rely on compiler-specific integration. **Do not infer from the presence of getters that `Filer` has an API to add methods to a source class.**

Similarly, structured source-generation libraries (such as JavaPoet) make **the job of writing new sources** easier, yet the result still needs to be saved as a generated source; that library alone does not turn JSR 269 into an AST-modification mechanism.

### When Are Non-Standard Tools Actually Needed?

If the requirement is that **`new Client().getName()` must compile even though the source class does not declare a getter**, a simple generated companion will not suffice. You must change the application contract or implement a compiler-specific source/AST transformation, addressing specific technical questions:

- Does it need to support javac, the Eclipse compiler, IDE indexing, and annotation processing in CI?
- Does it rely on internal APIs encapsulated in the `jdk.compiler` module?
- Which compiler phase handles the transformation? How will symbol/type attribution be updated?
- Do newer JDK versions change internal tree classes or the order of compiler phases?
- Are there sufficient regression tests for compilation, IDE, runtime, and incremental builds?

You cannot assume that an arbitrary combination of `--add-exports` or `--add-opens` will resolve all risks; module settings and compiler internals can vary across tools.

## 10. Alternative Designs That Avoid Modifying the Source Class

### Generating a Companion/Helper

~~~java
@GenerateGreeting
class Client {}
// Generates the ClientGreeting class in a new file.
~~~

Callers use `ClientGreeting.text()` or appropriate helpers. This is the approach demonstrated by the example in Section 5.

### Generating an Adapter or Implementation

Given an existing interface:

~~~java
interface Mapper<T> {
    String encode(T value);
}

class Client {
    String id;
}
~~~

The processor can generate `ClientMapper implements Mapper<Client>`. In practice, this is often sufficient for serializers, mappers, RPC clients, or dependency injection bindings.

### Generating a Separate Factory/Builder

The processor creates `ClientFactory` or `ClientBuilder` based on existing constructors/setters/accessibility. It **does not add constructors inside Client**: the factory returns an instance via already valid existing APIs.

### Generating a Subclass

If the source type can be inherited (is not `final`) and has an appropriate constructor/visibility, a generator can create a subclass with new methods. However, **the static type of the superclass does not automatically gain the subclass's methods**; a subclass cannot override final/private methods and cannot alter Java's inheritance constraints.

### Generating Code in a Separate Output Directory

Generated sources should reside in a separate build output (`generated/`, `build/generated/...`, or similar) recognized by the IDE/build system. Avoid mixing processor-owned files with developer-edited sources; this supports clean builds, avoids merge conflicts, and makes error tracing easier.

## 11. Testing, Warnings, and Incremental Builds

### Minimal Processor Testing

A reliable test should prove:

1. The compiler recognizes the correct annotation type and processor.
2. The generated file appears at the correct output path.
3. The generated source content is valid for the Java source version.
4. The generated class can be picked up by the compiler and referenced from other code.
5. When an annotation is misplaced, the processor emits a clear diagnostic.
6. With multiple inputs, generated type names do not collide.
7. The final round does not create files infinitely.
8. Incremental/clean builds do not allow stale outputs to cause false results.

The `-processor GreetingProcessor` option in the example **explicitly enables the processor**; therefore, it does not need to rely on the toolchain's default service discovery mechanism. In large projects, processors are usually packaged into a JAR and configured accordingly in Maven/Gradle/IDE.

### Using `Messager` to Report Errors

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Only classes are supported",
        element);
~~~

The processor should validate types, names, visibility, and required preconditions **before creating files**, rather than attempting to modify the user's source code. Clear diagnostics give build errors a location and a way to fix them.

### Incremental Build Considerations

`originatingElements` helps the build environment infer dependencies from generated outputs back to inputs. However, incremental effectiveness also depends on processor conventions, the tool, and the output kind (isolating/aggregating). Do not claim that every processor using `originatingElements` will always be incremental-safe.

When a generator creates **a shared registry** from multiple classes, it differs from the case where **each input generates a separate class**. You must aggregate the data, create the output only once per invocation, and define appropriate dependency semantics.

### Toolchain Security and Trust

An annotation processor is code that **executes during the build phase** and can run logic beyond simple annotation reading. Only enable trusted processors and restrict dependencies/processor paths in the pipeline. Do not equate “the source only has annotations” with the processor having no side effects.

## 12. Common Mistakes

**“A processor can only see annotations with `@Retention(RUNTIME)`.”** False. Processors operate at compile time; `SOURCE` retention is usually sufficient. `RUNTIME` is only needed if the application also has to inspect metadata via reflection at runtime.

**“`Filer.createSourceFile` can overwrite `Client.java` to insert getters.”** Violates the contract. Initial inputs cannot be recreated via Filer as a new type within the same invocation; the tool has no standard API to modify input ASTs.

**“`Element.getEnclosedElements()` returns a mutable list, so you just need to add an `ExecutableElement`.”** There is no such guarantee; compiler symbols/types are not restructured via arbitrary mutation of a collection.

**“Having `Trees.getTree(...)` means there is an official AST editor.”** False. The public Compiler Tree API is primarily for observing/traversing; mutating internal compiler nodes is a separate matter.

**“A processor only runs once.”** False. There are multiple rounds. Each generated pathname may only be created once per invocation; you must guard against `FilerException`.

**“`createClassFile` accepts Java source text.”** False. That API writes a binary class file; to have javac compile new source code, use `createSourceFile`.

**“An official javac plugin means there is a public method to add fields to the AST.”** False. The plugin API provides init/task event mechanisms; internal modification requires specialized tools/approaches and carries compatibility risks.

**“A runtime proxy makes the IDE see getters that do not exist in the source.”** Not automatically. The compile-time symbol model and runtime dynamic proxies are two different things.

## 13. Checklist Before Choosing a Technology

- [ ] Is the requirement to **generate new types/resources** or to **modify existing declarations**?
- [ ] Can a generated companion, adapter, mapper, factory, or builder be designed instead of mutating the AST?
- [ ] If using JSR 269, does the processor properly specify `@SupportedAnnotationTypes` and `ElementKind`?
- [ ] Has `Filer` created valid/unique output names, passed `originatingElements`, and closed the writer?
- [ ] Have multiple rounds, `processingOver()`, and `FilerException` scenarios been handled?
- [ ] Is the generated source placed in the output directory and recognized by javac and the IDE?
- [ ] Are `-s`, `-d`, `-processorpath`, and `-proc:only` properly distinguished?
- [ ] If using `Trees`, is it only reading/traversing, or is AST modification truly needed?
- [ ] If compiler-specific internals are needed, have the JDK version, compiler plugin, module access, IDE, and regression tests been thoroughly evaluated?
- [ ] Do you build/test against the target Java version and verify the generated source/runtime output?

## 14. Official Documentation

- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): contract for generating sources/classes/resources, originating elements, rounds, and duplicate files.
- [Java SE 17 — `FilerException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html): reasons why the tool refuses to create a file.
- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): processors and processing rounds.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): root elements, annotation lookup, and the final round.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getFiler()`, `getMessager()`, `getElementUtils()`.
- [Java SE 17 — `Trees`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html): mapping symbols to source trees.
- [Java SE 17 — `com.sun.source.tree`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html): source AST interfaces.
- [Java SE 17 — `javac Plugin`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Plugin.html): javac plugin integration capabilities.

**Key takeaway:** The standard annotation processing API **reads and checks declarations, reports diagnostics, and generates new files**. `Filer` does not directly modify existing classes/ASTs. If a problem requires adding methods directly to the original class when the source does not contain those methods, you must change the API design or deliberately choose a source/compiler/bytecode transformation tool outside JSR 269 with its own risk and compatibility trade-offs.
