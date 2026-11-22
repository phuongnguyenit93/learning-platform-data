# Using RoundEnvironment to Traverse Elements to Process

## Expected Outcomes

After this lesson, you can:

1. Explain the role of `javax.annotation.processing.RoundEnvironment` in each *round* of Java annotation processing.
2. Distinguish `RoundEnvironment.getRootElements()`, `getElementsAnnotatedWith(...)`, the `annotations` parameter of `Processor.process(...)`, and directly traversing child elements via `Element.getEnclosedElements()`.
3. Check the exact element kind with `ElementKind`, cast safely to `TypeElement` or `ExecutableElement`, and use `Elements`, `Types` when needing to analyze the language model.
4. Build and run a Java 17+ processor that generates a class from a source annotation; observe the next round and final round with `javac`.
5. Properly handle `processingOver()`, `errorRaised()`, claiming annotations, errors from `Filer`, and the case with no matching elements.
6. Avoid common mistakes such as assuming each round contains the entire project, relying only on annotation names, creating duplicate files, inspecting via runtime Reflection instead of the compile-time model, or forgetting compiler/processor paths.

This lesson focuses on how to **traverse and process elements using `RoundEnvironment`** inside an annotation processor. File generation is included as a practical case demonstrating why the compiler must organize multiple rounds.

## 1. Annotation Processing Operates at Compile-Time

An annotation processor is a component participating in the Java compilation process. It can inspect declarations carrying annotations, emit diagnostics, and generate sources or resources through supported APIs. It does not need to launch the application, does not call `main` of the classes being compiled, and does not necessarily use runtime Java Reflection.

Example of an annotated class:

~~~java
@AutoGreeting
public class HelloService {
}
~~~

A processor supporting `@AutoGreeting` can find the declaration element `HelloService` through `RoundEnvironment`, then generate `HelloServiceGreeting.java`. In the next processing round, the compiler examines the newly generated source and may invoke the processor again. After no new source needs processing, the compiler usually performs a final round for the processor to finalize.

Overview diagram:

~~~text
Initial source
  HelloService.java (has @AutoGreeting)
  Main.java
        |
        v
javac initializes processor
        |
        v
Round 1: roundEnv looks up @AutoGreeting
        |
        +--> Processor detects HelloService
        +--> Filer creates HelloServiceGreeting.java
        |
        v
Round 2: compiler puts new source into new round's root set
        |
        +--> Processor may still be called
        +--> If no new @AutoGreeting, match set is empty
        |
        v
Final round: processingOver() == true
        |
        v
javac completes compile (if no errors)
        |
        v
.class of original source and generated source
~~~

The diagram above describes the lesson's example case; if generated source itself contains annotations needing processing, there may be additional rounds. If the processor generates no new source/class, the round sequence is shorter. Log details depend on the compiler and configuration.

### Objects You Will Encounter

| API/Type | Meaning |
| --- | --- |
| `Processor` | Interface of an annotation processor; the key method is `process(...)` |
| `AbstractProcessor` | Convenient base class, providing `processingEnv` and several default methods |
| `ProcessingEnvironment` | Provides `Messager`, `Filer`, `Elements`, `Types`, processor options |
| `RoundEnvironment` | Provides elements relevant to the **current round** and termination/error status |
| `Element` | Model of a Java declaration (type, field, method, parameter, package...) |
| `TypeElement` | Model of a class/interface/enum/record/annotation type declaration |
| `ExecutableElement` | Model of a method or constructor |
| `TypeMirror` | Model of a type in the compiler's type system, not a `Class<?>` object |
| `AnnotationMirror` | Model of an annotation seen by the compiler, useful when annotation classes should not be loaded via Reflection |

Standard annotation processing APIs reside in the `java.compiler` module; commonly used packages are `javax.annotation.processing`, `javax.lang.model.element`, `javax.lang.model.type`, and `javax.lang.model.util`.

## 2. Specific Role of RoundEnvironment

Key signature inside a processor:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Read declarations and process the current round.
    return true;
}
~~~

This is an **illustrative method signature snippet**, not a complete Java class. The complete processor appears in section 5.

The `annotations` and `roundEnv` arguments have **different roles**:

- `annotations`: the set of **annotation types** that the compiler requests the processor to handle in the current invocation. It can be a subset of the annotations the processor declared it supports, and can even be empty.
- `roundEnv`: the query window for **declarations appearing in the round**, round status, and elements annotated with annotations.

Do not write code assuming `annotations.size()` is the number of annotated classes. One annotation type can appear on many declarations. If you want to know how many elements need work, query `roundEnv`.

### 2.1 `getRootElements()`

~~~java
Set<? extends Element> roots = roundEnv.getRootElements();
~~~

Returns the set of **root elements of the current round**. In the first round, roots usually relate to the sources/classes the tool was requested to process. In the next round, roots can come from sources/classes generated by the previous round. A root does not necessarily carry the annotation your processor cares about.

What must not be inferred:

- Roots are not synonymous with the entire project's sources.
- Roots do not necessarily include every field and method as independent elements.
- `getRootElements()` in the next round is not a copy of all roots from the first round.
- `Set` iteration order is not a stable order usable as an output contract.

To analyze members of a root type, you can iterate `root.getEnclosedElements()` or use an appropriate `ElementFilter`. However, when the goal is finding every declaration annotated with a specific annotation **within the round's scope**, `getElementsAnnotatedWith` is usually shorter and more accurate than manually walking the tree.

### 2.2 `getElementsAnnotatedWith(...)`

Common overloads in Java 17:

~~~java
roundEnv.getElementsAnnotatedWith(MyAnnotation.class);
roundEnv.getElementsAnnotatedWith(myAnnotationTypeElement);
~~~

These are **two illustrative calls**, assuming `MyAnnotation` and the variable `myAnnotationTypeElement` already exist in the processor.

- Overload accepting `Class<? extends Annotation>`: convenient when the processor can load the annotation type from the processor classpath.
- Overload accepting `TypeElement`: uses the compiler model; useful when the annotation type should not be loaded directly or you obtain the type via `Elements.getTypeElement(...)`.

The result is a `Set<? extends Element>` consisting of elements carrying the corresponding annotation according to the API's presence rules, within the scope of elements included in the round. An annotation may be considered present directly or through inheritance in valid cases. Scope includes not only root types, but can also include members, constructors, parameters, type parameters, and record components declared inside included types.

**Distinguish annotations on declarations from annotations on type-uses.** `getElementsAnnotatedWith(...)` is not a tool for finding every place an annotation appears on arbitrary type positions in source code.

### 2.3 `getElementsAnnotatedWithAny(...)`

Java 17 has overloads helping retrieve the **union** of elements carrying at least one of multiple annotation types:

~~~java
Set<? extends Element> hits =
        roundEnv.getElementsAnnotatedWithAny(firstType, secondType);
~~~

The snippet above assumes `firstType` and `secondType` are `TypeElement`s representing annotation types. The result is a set of elements, not an ordered list or records separated per annotation. With repeatable annotations (`@Repeatable`), you may need to consider both the base annotation type **and the container annotation type** in supported type declarations and queries, depending on how annotations are represented.

If you want to analyze each annotation separately, call `getElementsAnnotatedWith` for each kind and apply appropriate logic. Do not implicitly assume every repeated annotation occurrence becomes a separate entry in the `Set`.

### 2.4 `processingOver()`

~~~java
if (roundEnv.processingOver()) {
    return true;
}
~~~

The value `true` indicates a round where types generated in this round **will not be fed into a subsequent annotation processing round**. Usually this is the final round. This is a suitable point to finalize certain reporting/aggregation work if state was accumulated across rounds.

**Do not try to generate new Java source in the final round expecting the compiler to process it as a next round.** If the processor needs to create source for the compiler to compile, create it in non-final rounds.

There may still be a need to write certain summary resources in the final round per `Filer`'s contract, yet you must understand timing constraints and not assume new files enter the compilation pipeline.

### 2.5 `errorRaised()`

~~~java
boolean previousRoundHadError = roundEnv.errorRaised();
~~~

It indicates an error was emitted in a **previous round**; it should not be understood as a flag immediately reflecting every error you just emitted within this very call to `process(...)`. Therefore, do not write logic like:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Invalid declaration"
);
// Do not expect roundEnv.errorRaised() to turn true right here.
~~~

This is an illustrative snippet inside `process`, not a standalone program. If you need to know whether your processor emitted an error in the current round, track it with a separate variable, e.g., `boolean hadLocalError` or appropriate state.

### 2.6 Summary Table of APIs

| Method | Question It Answers | Common Misconception |
| --- | --- | --- |
| `getRootElements()` | What are the root declarations of this round? | Assuming it means every class in the project in every round |
| `getElementsAnnotatedWith(A.class)` | Which declarations within the round's scope have `@A`? | Thinking it only finds top-level classes |
| `getElementsAnnotatedWith(TypeElement)` | Find declarations by annotation type represented by the compiler? | Passing a non-annotation type |
| `getElementsAnnotatedWithAny(...)` | Union of declarations carrying at least one sought annotation? | Expecting fixed order or record count matching number of annotation usages |
| `processingOver()` | Are we in the stage with no further round to process newly generated types? | Thinking the final round must still generate more source |
| `errorRaised()` | Did the **previous** round report an error? | Using it as an instant variable to tell whether an error was just reported in the same round |

## 3. Traversing Elements Safely

### 3.1 Checking `ElementKind` Before Casting

`getElementsAnnotatedWith(...)` returns a general `Element`. Annotations may be allowed on types, fields, methods, parameters, or multiple different targets. Before casting to `TypeElement`, check `getKind()`:

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(MyAnnotation.class)) {
    if (!element.getKind().isClass()) {
        processingEnv.getMessager().printMessage(
                javax.tools.Diagnostic.Kind.ERROR,
                "@MyAnnotation chỉ hợp lệ trên class",
                element
        );
        continue;
    }
    TypeElement type = (TypeElement) element;
    // Use type.getSimpleName(), type.getQualifiedName(), ...
}
~~~

The snippet above is a processor snippet, assuming `MyAnnotation` is declared. `ElementKind.isClass()` returns true for kinds describing classes, including certain specific class forms. If the contract permits only regular classes, check `element.getKind() == ElementKind.CLASS`. The `@Target(ElementType.TYPE)` annotation permits multiple type declaration kinds, whereas the processor may need further restriction.

If wanting to process methods:

~~~java
if (element.getKind() == ElementKind.METHOD) {
    ExecutableElement method = (ExecutableElement) element;
    // method.getParameters() returns List<? extends VariableElement>.
}
~~~

This is also a snippet, not an independently compilable class. Branching based on kind prevents `ClassCastException` and helps compiler diagnostics point directly at the source location.

### 3.2 `Element` Differs from Reflection `Class<?>`

In an annotation processor, the type being compiled may **not yet have a class file**. Query using `TypeElement` and `TypeMirror`, rather than trying to use `Class.forName("app.SomeType")` to load the target type.

- `TypeElement.getQualifiedName()`: package-qualified name of the declaration.
- `Element.getSimpleName()`: short name.
- `Element.getEnclosedElements()`: members declared inside the element.
- `ExecutableElement.getParameters()`: parameter declarations of a method/constructor in the compile-time model.
- `Element.asType()`: corresponding type as a `TypeMirror`.
- `Elements` and `Types`: utilities for the compiler model, e.g., checking type assignment or finding the enclosing package.

A design mistake is using `Class<?>` and `getDeclaredMethods()` on uncompiled source; it can accidentally load an old version of the class on the processor classpath, or simply fail to find the class.

### 3.3 Roots, Members, and Annotation Targets

Suppose `@Audit` is allowed on methods in `OrderService`. `OrderService` may appear as a root, while method `submit` is an **enclosed member**. `roundEnv.getElementsAnnotatedWith(Audit.class)` can return the `ExecutableElement` for `submit` even though it is not a top-level root.

If you only iterate `roundEnv.getRootElements()` and check annotations directly on roots, you can miss annotations located on methods/fields. That is why you should pick the query approach based on the goal: to find **annotated elements**, use `getElementsAnnotatedWith`; to inspect the **structure of all members**, use `getEnclosedElements`/`ElementFilter`.

### 3.4 Do Not Rely on Set Iteration Order

`getRootElements()` and `getElementsAnnotatedWith(...)` return `Set`. Do not assume iteration order matches file/source order. If generating deterministic reports, obtain a list, convert to comparable names, and sort:

~~~java
List<Element> elements = new ArrayList<>(
        roundEnv.getElementsAnnotatedWith(MyAnnotation.class)
);
elements.sort(Comparator.comparing(
        e -> e.toString()
));
~~~

This is a snippet; you must import `java.util.List`, `java.util.ArrayList`, `java.util.Comparator` and have `MyAnnotation`. When sorting in a real program, use a semantically accurate stable key (qualified name, signature, model position) rather than treating `toString()` as always a unique identifier for every declaration.

## 4. Preparing a Runnable Project Without an IDE

The goal is creating three parts:

1. Annotation `demo.AutoGreeting` to mark classes.
2. Processor `demo.processor.GreetingProcessor` finding annotated classes via `RoundEnvironment` and generating code.
3. Application sources `sample.HelloService` and `sample.Main` to verify generated code is produced and used in the same `javac` invocation.

Use **JDK 17 or higher**. Verify:

~~~bash
java -version
javac -version
~~~

The example is written for Java 17 and uses `--release 17` when the compiler supports that target. If using a newer JDK, you can still choose `--release 17`. For a reproducible experiment, create a dedicated directory and open a terminal at the root:

~~~text
round-demo/
├── src/
│   ├── demo/
│   │   ├── AutoGreeting.java
│   │   └── processor/
│   │       └── GreetingProcessor.java
│   └── sample/
│       ├── HelloService.java
│       └── Main.java
└── build/
    ├── tools/
    ├── classes/
    └── generated/
~~~

`build/tools` holds the compiled annotation and processor. `build/classes` holds application classes and generated classes. `build/generated` is the source output created by `Filer`.

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force src/demo/processor, src/sample, build/tools, build/classes, build/generated | Out-Null
~~~

**Bash/Zsh (macOS/Linux):**

~~~bash
mkdir -p src/demo/processor src/sample build/tools build/classes build/generated
~~~

Save each Java file as UTF-8 with the **exact package and path**. The following compile commands run from `round-demo`.

## 5. Complete Example: Annotation and Processor

### 5.1 Declaring the Annotation — `src/demo/AutoGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
~~~

`@Target(ElementType.TYPE)` allows attaching to type declarations. In the processor, we further restrict to **class**. `@Retention(SOURCE)` suffices for a compile-time processor: the annotation does not need to exist at runtime for the processor to find it.

Do not confuse annotation processors with runtime reflection. Retention policy `SOURCE` does not prevent javac from seeing annotations on source during the annotation processing phase.

### 5.2 Writing the Processor — `src/demo/processor/GreetingProcessor.java`

~~~java
package demo.processor;

import demo.AutoGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
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

    private final Set<String> generatedNames = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(AutoGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@AutoGreeting chi dung cho class",
                        element
                );
                continue;
            }

            TypeElement owner = (TypeElement) element;

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(owner)
                    .getQualifiedName()
                    .toString();
            String simpleName = owner.getSimpleName() + "Greeting";
            String qualifiedName = pkg.isEmpty()
                    ? simpleName : pkg + "." + simpleName;

            if (!generatedNames.add(qualifiedName)) {
                continue;
            }

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, owner);

                try (Writer writer = file.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n\n");
                    }

                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Hello from "
                            + owner.getSimpleName() + "\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName
                                + ": " + ex.getMessage(),
                        owner
                );
            }
        }

        return true;
    }
}
~~~

This is a standalone processor class, compilable with JDK 17+. The class extends `AbstractProcessor`, has an implicit public no-arg constructor because no explicit constructor is defined; the compiler can instantiate it when specified.

Important lines:

1. `@SupportedAnnotationTypes("demo.AutoGreeting")` publishes the annotation the processor supports. This is the **fully qualified name of the annotation**, not the name of the annotated class.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares the source level the processor supports. If using a compiler with a higher source level, there may be a version warning; in the example we compile with `--release 17`.
3. `roundEnv.processingOver()` avoids creating source when already in the final round.
4. `roundEnv.getElementsAnnotatedWith(AutoGreeting.class)` iterates **exactly the elements annotated in the round**, without manually scanning the whole package.
5. `ElementKind.CLASS` prevents casting from unwanted element kinds.
6. `TypeElement owner` uses the compiler model to retrieve class name and package.
7. `Filer.createSourceFile(qualifiedName, owner)` generates a file at the source output path; `owner` is declared as the originating element so tools/build systems have relevant source info.
8. `generatedNames` guards against repeatedly processing the same name within a single processor run. It **does not replace** conflict checks with existing sources/JARs; `Filer` can still report errors.
9. `Diagnostic.Kind.ERROR` causes errors to be reported by the compiler as diagnostics and normally leads to compilation failure, instead of merely printing to console and letting errors be ignored.
10. `return true` tells the processor to claim the annotation types requested for processing in this call. It does **not** mean every annotation across the entire project has been processed.

**Intentional limitation of the demo:** the generated class name is concatenated from the Java class name and the string `Greeting`; we do not generate Java string literals from arbitrary annotation parameters. For processors generating code from user data, escape/validate characters or use an appropriate code generation API to avoid creating invalid Java source.

### 5.3 Annotated Source — `src/sample/HelloService.java`

~~~java
package sample;

import demo.AutoGreeting;

@AutoGreeting
public class HelloService {
}
~~~

`HelloService` is placed in the `sample` package. If the processor works properly, the created source file will be `sample/HelloServiceGreeting.java`, and the finished class will be `sample.HelloServiceGreeting`.

### 5.4 Application Using the Generated Class — `src/sample/Main.java`

~~~java
package sample;

public final class Main {
    public static void main(String[] args) {
        System.out.println(HelloServiceGreeting.message());
    }
}
~~~

Looking only at the two initial source files in package `sample`, `HelloServiceGreeting` does not yet exist. It is created by the processor during compilation. The example thus proves annotation processing **can create source before the compiler finishes compiling classes that use that source**.

## 6. Compiling and Running the Full Example

### Step 1 — Compile the Annotation and Processor

~~~bash
javac --release 17 -encoding UTF-8 -d build/tools src/demo/AutoGreeting.java src/demo/processor/GreetingProcessor.java
~~~

This command creates at least:

~~~text
build/tools/
└── demo/
    ├── AutoGreeting.class
    └── processor/
        └── GreetingProcessor.class
~~~

At this step, the processor is not yet asked to run: we are **compiling the processor class itself** like normal Java code.

### Step 2 — Have javac Run the Processor with Application Source

~~~bash
javac --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src/sample/HelloService.java src/sample/Main.java
~~~

Meaning of the parts:

| Option | Role |
| --- | --- |
| `--release 17` | Check syntax, platform API, and class-file target of Java 17 |
| `-encoding UTF-8` | Read source files as UTF-8 |
| `-cp build/tools` | Lets application source resolve the `demo.AutoGreeting` annotation |
| `-processorpath build/tools` | Lets javac **load the processor** and its dependencies |
| `-processor demo.processor.GreetingProcessor` | Explicitly selects the processor to run, without needing a service registration file |
| `-s build/generated` | Directory to write **generated source files** created by `Filer` |
| `-d build/classes` | Directory to write class files after compilation |
| `src/sample/HelloService.java`, `src/sample/Main.java` | The two initial source files to compile |

Both `-cp` and `-processorpath` point to `build/tools` **in this simple demo**, yet they have different responsibilities. In real projects, processor dependencies and application compile dependencies should normally be separated.

After a successful command, typical output:

~~~text
build/
├── tools/
│   └── demo/...
├── generated/
│   └── sample/
│       └── HelloServiceGreeting.java
└── classes/
    └── sample/
        ├── HelloService.class
        ├── HelloServiceGreeting.class
        └── Main.class
~~~

The generated source file will have content equivalent to:

~~~java
package sample;

public final class HelloServiceGreeting {
    private HelloServiceGreeting() {}
    public static String message() {
        return "Hello from HelloService";
    }
}
~~~

Because `-s build/generated` is configured, source goes into that directory. Once javac processes the newly generated source and compiles successfully, the corresponding binary resides in `build/classes`.

### Step 3 — Run the Application

~~~bash
java -cp build/classes sample.Main
~~~

Exact stdout of the example:

~~~text
Hello from HelloService
~~~

When running this program, you do not need to put `build/tools` on the runtime classpath: `HelloServiceGreeting.class` contains ordinary code, the annotation has `SOURCE` retention, and the demo does not call into the processor or runtime annotations. **Do not apply this conclusion to every processor/framework**: if generated code or the application depends on other classes at runtime, you still need the corresponding runtime dependencies.

### Step 4 — Observe Round Order

You can add `javac` diagnostic options:

~~~bash
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src/sample/HelloService.java src/sample/Main.java
~~~

**Test on fresh output or clean only the demo generated/output directories before re-running.** The processor uses `Filer` to create files; if you keep old generated source, rebuild behavior and pre-existing file warnings may cause noise. Use fresh `build/generated-second` and `build/classes-second` directories when only wanting to observe:

~~~bash
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated-second -d build/classes-second src/sample/HelloService.java src/sample/Main.java
~~~

Before the second command, create `build/generated-second` and `build/classes-second` just as output directories were created in section 4. Diagnostic information will show rounds, roots, and annotation types; exact formatting, length, element order, and wording can vary by JDK.

In the demo, you expect:

- One round receiving the original source containing `@AutoGreeting`.
- A subsequent round containing the generated type `HelloServiceGreeting`.
- A final round where `processingOver()` is `true`.

Do not expect exact line-by-line output printed by `-XprintRounds`, since that is compiler diagnostic output rather than an application stdout with a stable contract.

## 7. Understanding the Processing Loop via the Run Example

### First Round

The processor is invoked because annotation `demo.AutoGreeting` belongs to supported types. Notable values:

- `roundEnv.processingOver() == false`.
- `roundEnv.getElementsAnnotatedWith(AutoGreeting.class)` contains `HelloService`.
- `getRootElements()` can contain both `HelloService` and `Main` (the initial roots) even though only one of the two is annotated.
- `annotations` is the set of annotation types handed over to process; it is **not** the set of `HelloService` classes.

The processor creates `sample.HelloServiceGreeting` via `Filer`. The new source file does not immediately mutate the root collection contents of the first round.

### Next Round

When javac processes the newly generated source, it can put `HelloServiceGreeting` into the roots of the new round. This class **does not carry `@AutoGreeting`**, so the result of `getElementsAnnotatedWith(AutoGreeting.class)` may be empty. The processor needs to accept that as a valid state.

A very important point: **a processor invoked in one round may continue being invoked in later rounds, including the final round, even when no new annotations for it remain**. Do not write code like “if annotations is empty there is an error”.

### Final Round

In the final call, `processingOver()` is usually true; the demo code immediately returns true without generating new source. `errorRaised()` at this time can indicate whether the previous round reported an error, yet does not mean every element from previous rounds is collected here.

### Storing State Across Rounds

One processor instance is normally reused by the compiler throughout a single annotation processing run; it is not newly instantiated for each round. Therefore, the `generatedNames` field in the demo stores state per **compiler/processor run**, allowing it to avoid generating the same qualified name twice if callbacks encounter repeated data.

Do not rely on that instance field to retain state across **separate builds**. A new `javac` invocation usually creates a new processing environment. Tool incremental builds have their own caching policies, which must not be inferred from an instance variable inside a processor.

## 8. How Does Traversing Roots Differ from Finding Annotations?

Suppose we have source:

~~~java
package sample;

@AutoGreeting
class PackageWorker {
    void run() {}
}

class PlainWorker {
    void stop() {}
}
~~~

This is an illustrative snippet, assuming `AutoGreeting` is imported properly; it is not standalone source for the demo, and do not use it alongside another class of the same name in the package when copying.

- `getRootElements()` returns **root types** the compiler is processing in the round. It can include annotated and non-annotated types.
- `getElementsAnnotatedWith(AutoGreeting.class)` returns declarations carrying `@AutoGreeting` within search scope; `PlainWorker` does not match.
- When needing to find the `run` method inside `PackageWorker` where the method does not carry its own annotation, you must get the `TypeElement` and traverse `getEnclosedElements()`; `getElementsAnnotatedWith(AutoGreeting.class)` does not automatically return every child method.

If an annotation has `@Target(METHOD)`, an annotated method can be returned directly by `getElementsAnnotatedWith` even though it is not in `getRootElements()` as a separate root.

### When Querying Multiple Annotation Types

With a processor supporting `@A` and `@B`, you can:

1. Call `getElementsAnnotatedWith(aType)` and `getElementsAnnotatedWith(bType)` separately to obtain two sets.
2. Use `getElementsAnnotatedWithAny(aType, bType)` to obtain the union of elements.
3. Inspect `AnnotationMirror` or an appropriate method if an element carries multiple annotations and requires different handling.

The `@Repeatable` case is special: the compiler may represent repeated annotations via a container; inspect both the repeatable annotation and container type. Do not assume `getElementsAnnotatedWith(MyRepeatable.class)` in every environment sufficiently describes all repeated states.

## 9. Declaring Supported Annotation Types and Return Value Meaning

The demo's processor uses:

~~~java
@SupportedAnnotationTypes("demo.AutoGreeting")
~~~

This is declarative metadata for tools to decide when the processor matches present annotation types. Note:

- Names must be fully qualified and exact.
- Multiple types can be declared if the processor handles them.
- `@SupportedAnnotationTypes("*")` is how to support all annotation types per the API contract, but should not be used indiscriminately because it can affect other processors.
- A processor supporting `"*"` should usually `return false` if it only observes/validates without wanting to claim all annotation types.

`process(...)` returns:

- **`true`**: the processor claims the annotation types handed to it in the call, causing downstream processors to no longer be asked to process those same types under the claim mechanism.
- **`false`**: does not claim; other processors can still process them.

Do not interpret `true` as “the processor had no errors”, “no more rounds remain”, or “every element in the project has been processed”. It is solely the decision to **claim the annotation types of the current call**.

For a processor dedicated to `demo.AutoGreeting`, `return true` is appropriate when it takes ownership of this annotation. In a system involving multiple cooperating processors, choosing true/false must follow each processor's contract.

## 10. How to Emit Diagnostics at the Exact Location

When users attach annotations to the wrong target or configure invalid code generation, do not just use `System.out.println`. Use `Messager`:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Chi ho tro class thong thuong",
        element
);
~~~

This is a snippet inside the processor, requiring the `element` variable and importing `javax.tools.Diagnostic`. Passing `element` allows the compiler to associate the diagnostic with a declaration; IDEs/build tools can usually display the error location better.

Common levels:

| Diagnostic kind | Purpose |
| --- | --- |
| `ERROR` | Error preventing compilation from being considered successful |
| `WARNING` | Warns about an issue without necessarily blocking compilation |
| `MANDATORY_WARNING` | Warning required to be displayed per tool mechanism |
| `NOTE` | Informational diagnostic message |
| `OTHER` | Message not belonging to the categories above |

If needing a message pointing to a specific annotation, overloads of `Messager.printMessage` can accept `AnnotationMirror` and `AnnotationValue` alongside `Element`. Not every error case can be attached to an exact annotation position; when no position exists, the message may be less specific.

### Practice: Actively Reporting Errors for the Right Element Kind

The demo processor only handles `ElementKind.CLASS`. `@Target(ElementType.TYPE)` also permits several other type declaration kinds. If you attach `@AutoGreeting` to an interface:

~~~java
@AutoGreeting
public interface GreetingContract {
}
~~~

This is a snippet, not a standalone runnable program; place it in a `GreetingContract.java` file with valid package/imports if wanting to test. The annotation is valid under `@Target(TYPE)`, yet the processor will emit `ERROR` because the element kind is not `CLASS`.

This illustrates the difference between **restrictions allowed by annotation targets** and **business constraints validated by the processor itself**.

## 11. Using Filer Properly Across Rounds

`Filer` is the official tool for a processor to create source, class, or resource files. It lets javac know which files were generated during annotation processing. Manually writing files with `Files.writeString` to arbitrary paths can prevent build tools and the compiler from knowing which processing round an artifact belongs to.

In the demo:

~~~java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile(qualifiedName, owner);
~~~

- `qualifiedName` must be a valid type name, e.g., `sample.HelloServiceGreeting`.
- `owner` is the originating element, helping associate the generated file with the required source.
- `createSourceFile` does not mean the compiler has immediately compiled that class in the current round.
- `file.openWriter()` opens a writer to write source. After closing the writer, the compiler can read the file in the next round.
- `-s build/generated` locates generated source output; `-d build/classes` locates binary output.
- `Filer` has a rule against recreating the same pathname/type multiple times within one run. If duplicated, `FilerException`, a subtype of `IOException`, may occur.

### Why Is Duplicate Generation a Common Error?

If a processor sees the same target multiple times due to how rounds are organized, or two different classes both generate the name `sample.Generated`, the second file-creation call will collide. `generatedNames` helps avoid **some duplicate scenarios in this processor**, yet does not handle every conflict with other processors or pre-existing types.

Artifact naming rules must be deterministic, avoid collisions, and be computable from input declarations. If multiple declarations contribute to a single shared registry, you may need to accumulate state and create the file exactly once at an appropriate time; the choice depends on `Filer`'s contract and whether the generated file needs further compiler processing or is only an aggregated resource.

### Do Not Directly Edit Original Source from a Processor

A processor should **read the model and generate new files**, not modify `HelloService.java` itself while the compiler is analyzing it. Modifying original source while the compiler is running creates issues with state synchronization, build reproducibility, and compilation correctness.

## 12. Common Errors and Limitations

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `getElementsAnnotatedWith(...)` is always empty | Annotation not in round, wrong supported type, processor not actually called, or annotation in a position not searched by API | Check annotation name, `-processor`, compiled source, and `-XprintRounds` |
| `annotations` is empty in a round | No new annotation types handed to the processor in that round | Valid state; do not treat as an exception |
| `getRootElements()` does not contain source from previous round | Roots belong to each round, not the entire project | Store needed info if aggregating across rounds |
| `ClassCastException` when casting `Element` to `TypeElement` | Annotation can be attached to method/field/parameter | Check `ElementKind` |
| `ClassNotFoundException` when loading a type being compiled | Used Java Reflection instead of compiler model | Use `TypeElement` and `TypeMirror` |
| Processor not found | Wrong `-processorpath`, processor not built yet, wrong class name, or missing processor dependency | Inspect `build/tools` and name `demo.processor.GreetingProcessor` |
| Annotation not found in app source | Annotation not on compile classpath | Add `build/tools` to `-cp` for the demo |
| `FilerException: Attempt to recreate a file...` | Generated same file/type multiple times or collided with input | Check generated names, state, and responsibility split among processors |
| javac runs yet no generated file appears | Processor did not run, no matching elements, or `-s` points elsewhere | Check `-XprintProcessorInfo`, `-XprintRounds`, source output |
| Processor generates code yet app fails to compile | Generated source has syntax/type error, name collision, or missing dependency | Inspect generated source and first diagnostic |
| Processor sees annotation only in round 1 | Not handling subsequent rounds properly | Understand roots and annotated elements in each round |
| Error after `errorRaised()` returns false | Method reports errors **in the previous round**, not an instantly updated flag | Track newly emitted errors with dedicated state |
| In final round yet still generating source expecting compiler to compile | No subsequent round remains to process generated types | Create source in an appropriate round before `processingOver()==true` |
| Random output order | Iterating a `Set` with no order contract | Sort by stable key before outputting reports |
| Processor “steals” another processor's annotations | `return true`/`"*"` claims too broadly | Declare accurate supported types and choose proper return value |

### Key Point to Remember About `errorRaised()`

If a processor emits `ERROR` in the current round, the compiler usually still finishes the round per tool rules, and then the next round can reflect that error via `errorRaised()`. Do not try to check `roundEnv.errorRaised()` instead of a `hasErrorThisRound` variable in the same `process` invocation.

If your goal is only preventing further file generation once an error occurred, you can keep private state combined with checking `errorRaised()` in subsequent rounds. Do not assume the compiler will continue generating/compiling every file normally after a severe error.

## 13. Inherited Annotations, Nested Types, and Repeatable Annotations

### 13.1 `@Inherited`

With an annotation type having `@Inherited` and allowed on classes, a subclass can be considered to have the annotation via inheritance even if it does not directly write the annotation in source. `getElementsAnnotatedWith(...)` can return declarations based on annotation presence rules.

However, `@Inherited` does not automatically apply similarly to methods, fields, or interfaces in every context. When having to distinguish “written directly” from “considered present via inheritance”, use appropriate annotation/model APIs and understand exact annotation semantics.

### 13.2 Nested Types

A root can contain annotated nested classes. `getElementsAnnotatedWith` can find annotated elements inside enclosed types of the round, not only top-level roots. `TypeElement.getQualifiedName()` for nested types returns a name matching the Java model; do not assume nested names always have a simple top-level form or use `getSimpleName()` as a globally unique identifier.

### 13.3 Record Components and Parameters

In Java 17, the compile-time model supports modern declarations such as records and record components. If an annotation is allowed on the corresponding target, querying annotated elements can return `RecordComponentElement` or `VariableElement` for parameters, instead of `TypeElement`.

When designing a processor supporting multiple targets, use `ElementKind` branching, `instanceof`, or the visitor pattern from `javax.lang.model`; do not force every annotated element to be a class.

### 13.4 Repeating Annotations

When declaring a `@Repeatable(Container.class)` annotation, the compiler may represent multiple occurrences of the same annotation through the container. The processor should declare the necessary supported annotation types and check retrieval APIs according to the repeated-annotation handling policy.

Java 17 has `getElementsAnnotatedWithAny(...)` supporting retrieving the union of annotated elements across multiple annotation types; however, you still need to interpret **annotation values** and containers if business logic depends on repetition counts.

## 14. How Would a Processor Traversing Method Elements Differ?

Example permitting annotations on methods:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
public @interface ValidateCall {
}
~~~

This is an annotation declaration that can be placed in `demo/ValidateCall.java`. A processor supporting `demo.ValidateCall` can traverse:

~~~java
for (Element element :
        roundEnv.getElementsAnnotatedWith(ValidateCall.class)) {
    if (element.getKind() != ElementKind.METHOD) {
        continue;
    }

    ExecutableElement method = (ExecutableElement) element;
    String name = method.getSimpleName().toString();
    int parameterCount = method.getParameters().size();

    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.NOTE,
            name + " has " + parameterCount + " parameter(s)",
            method
    );
}
~~~

This is a **snippet** placed inside `process(...)` with imports for `ExecutableElement`, `Element`, `ElementKind`, `Diagnostic`, and the `ValidateCall` annotation. When a method is annotated, `getElementsAnnotatedWith` takes you directly to the method declaration, without needing to traverse every root and search text containing `@ValidateCall`.

This example also shows why `Element` is a declaration model: we retrieve parameters from `ExecutableElement.getParameters()` without loading the just-compiled class via Reflection.

## 15. How to Test a Processor Within Scope

A processor needs to be tested in at least these scenarios:

1. **One annotated class:** source is generated with the right name, package, and content.
2. **Multiple annotated classes:** each type has its own artifact, independent of iteration order.
3. **No matching annotations:** no exception is thrown; the processor might not be selected in the first round if no matching annotation exists.
4. **Annotation on a target not accepted by the processor:** receives an `ERROR` diagnostic with clear location.
5. **Creating new source across multiple rounds:** generated types are compiled and the processor does not generate duplicates.
6. **Output name collision:** handles diagnostics properly without silently overwriting user files.
7. **Compilation failure:** does not produce a false “success report” when error diagnostics already exist.
8. **Repeated compilation on clean outputs:** results do not depend on stale artifacts.

To isolate variables when testing the demo, keep `build/tools` as the processor output and create a fresh pair of generated/classes outputs for each app compile. When debugging, inspect both stdout/stderr and source files under `-s`, not just the exit code.

### Trying with Two Annotated Classes

Create an additional standalone file **`src/sample/AnotherService.java`**:

~~~java
package sample;

import demo.AutoGreeting;

@AutoGreeting
public class AnotherService {
}
~~~

Compile the app with this extra source, for example:

~~~bash
javac --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated-multi -d build/classes-multi src/sample/HelloService.java src/sample/AnotherService.java src/sample/Main.java
~~~

Beforehand, create two new output directories `build/generated-multi` and `build/classes-multi`. The processor generates two sources:

- `sample.HelloServiceGreeting` with `message()` returning `Hello from HelloService`.
- `sample.AnotherServiceGreeting` with `message()` returning `Hello from AnotherService`.

Because the demo's `Main` only calls `HelloServiceGreeting.message()`, stdout when running:

~~~bash
java -cp build/classes-multi sample.Main
~~~

remains:

~~~text
Hello from HelloService
~~~

This is expected. The separately generated class names prove both annotated elements were processed; an application's output does not necessarily have to print all generated classes.

## 16. Diagnosing When a Processor Does Not Run

### Step 1 — Does the Processor Class Already Exist?

Check the files:

~~~text
build/tools/demo/processor/GreetingProcessor.class
build/tools/demo/AutoGreeting.class
~~~

If missing, recompile step 1. `-processor demo.processor.GreetingProcessor` requires the processor class to be findable by the processor class loader.

### Step 2 — Did the Compiler Actually Specify the Processor?

Use explicit `-processor` as in the lab. In a build-tool project, processors can be registered via a service file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

whose content is the fully qualified name of the processor. However, this example **does not need** a service file because `-processor` is already used. Do not both omit the service file and omit `-processor`, then conclude `RoundEnvironment` is broken.

### Step 3 — Is the Annotation Type Correct?

The demo's `@SupportedAnnotationTypes` uses `demo.AutoGreeting`. In application source it must be that exact annotation, not another annotation with the same short name imported from a different package.

### Step 4 — Are Input Sources Included in the Invocation?

If you only compile `src/sample/Main.java` without supplying or making `HelloService` and the annotation visible, do not expect the processor to always find every class in the project on disk. `RoundEnvironment` only sees elements the compiler actually brings into the invocation's rounds.

### Step 5 — Inspect Round Logs

Add `-XprintRounds -XprintProcessorInfo`, using fresh output paths. If the processor is not called or the annotation is not detected, the log helps narrow down where the problem lies. If the processor runs yet creates no file, check the `processingOver()` branch, the `getElementsAnnotatedWith(...)` set, and diagnostics.

### Step 6 — Distinguish Generated Source and Generated Class

`-s` and `-d` are two different output paths. Seeing `HelloServiceGreeting.java` is not enough to prove the compiler succeeded in creating `HelloServiceGreeting.class`. If generated source has syntax errors or missing dependencies, javac may fail before producing a valid binary.

## 17. Exercises and Verification Answers

### Exercise 1 — Root or Annotated Element?

A round contains two root types `A` and `B`, with only `A` annotated `@AutoGreeting`. How do `getRootElements()` and `getElementsAnnotatedWith(AutoGreeting.class)` differ?

**Answer:** the root set can contain both A and B; the annotated set contains only matching declarations, here A. Do not infer iteration order from `Set`.

### Exercise 2 — Final Round

The processor is in the final round and `roundEnv.processingOver()` is true. Should you call `Filer.createSourceFile` and expect javac to start another round to compile this file?

**Answer:** No. The final round does not guarantee a subsequent round to process new types. Source needing compilation should be generated before the final stage.

### Exercise 3 — Method Annotation

With the `@ValidateCall` annotation attached to a method, why is casting every result of `getElementsAnnotatedWith(ValidateCall.class)` to `TypeElement` wrong?

**Answer:** a method is an `ExecutableElement`; you must check `ElementKind.METHOD` and cast appropriately.

### Exercise 4 — `errorRaised()`

Right after calling `Messager.printMessage(ERROR, ...)` inside `process`, you check `roundEnv.errorRaised()`. Must this method become true immediately at that point?

**Answer:** No. `errorRaised()` describes errors from the **previous round**; to know whether an error was just emitted in the current round, track it with processor state.

### Exercise 5 — Multiple Rounds

Round 1 of the demo creates `HelloServiceGreeting.java`. Why might round 2 have a new root yet `getElementsAnnotatedWith(AutoGreeting.class)` be empty?

**Answer:** the generated type does not carry `@AutoGreeting`, so it can be a root without being a matching annotated element. The processor must accept an empty set.

### Exercise 6 — Classpath and Processorpath

Why does the demo use both `-cp build/tools` and `-processorpath build/tools`?

**Answer:** application source needs to see the annotation type to compile; the compiler needs to find and load the processor class to run it. These are two distinct roles even though the demo shares the directory.

### Exercise 7 — Generated Output

After the compile command, you see `build/generated/sample/HelloServiceGreeting.java` but `build/classes/sample/HelloServiceGreeting.class` is missing. Can you conclude the processor did not run?

**Answer:** No. The generated source proves the processor/Filer performed part of its work. Inspect diagnostics because compilation may have stopped before generating class files.

### Exercise 8 — Claiming Annotations

If a processor supports `demo.AutoGreeting`, finishes iterating, and does `return true`, does this mean all annotations across every module have been completely processed?

**Answer:** No. Returning true only claims the annotation types handed over in the current process invocation; it does not describe the entire project.

## 18. Completion Checklist

- [ ] I understand `RoundEnvironment` provides information per **round**.
- [ ] I distinguish root elements from annotated elements.
- [ ] I know how to use `getElementsAnnotatedWith(Class/TypeElement)`.
- [ ] I do not rely on `Set` iteration order when generating deterministic artifacts.
- [ ] I check `ElementKind` before casting.
- [ ] I use compile-time `Element`/`TypeMirror` instead of Reflection when analyzing uncompiled source.
- [ ] I handle `processingOver()` and understand the previous-round meaning of `errorRaised()`.
- [ ] I do not generate duplicate types/sources with `Filer`.
- [ ] I can explain `return true` and `return false` from `process`.
- [ ] I compiled the annotation/processor, ran `javac -processor`, and inspected generated source.
- [ ] I ran `sample.Main` and received `Hello from HelloService`.
- [ ] I know how to debug with `-XprintRounds` and `-XprintProcessorInfo`.
- [ ] I know how to check annotations, compile classpath, processorpath, `-s`, and `-d` when files are missing.
- [ ] I distinguish the runnable demo from API-explaining snippets.

## References

- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html)
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html)
- [Java SE 17 — javax.annotation.processing package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)

## Remember

**`RoundEnvironment` is a window into each annotation-processing round, not a data store of the entire project.** `getRootElements()` returns the round's roots; `getElementsAnnotatedWith(...)` finds declarations carrying annotations within the round's scope; `processingOver()` and `errorRaised()` help control how the processor reacts to the compilation process. Combining these APIs with `ElementKind`, the compiler model, `Filer`, and properly positioned diagnostics is the foundation for building reliable, reproducible processors supporting multi-round source generation.
