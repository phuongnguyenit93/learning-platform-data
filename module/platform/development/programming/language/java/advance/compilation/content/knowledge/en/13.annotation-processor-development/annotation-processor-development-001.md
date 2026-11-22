# Structure of AbstractProcessor and ProcessingEnvironment in Java Annotation Processing

## 1. Purpose and Nature

**Annotation processing** is a mechanism allowing the Java compiler to invoke a program to process annotations and type/declaration information at compile time. A processor can validate code conventions, emit diagnostics, and generate additional sources, classes, or resources. It is not a callback triggered when the application runs.

The two most important APIs when building a standard Java processor:

- **javax.annotation.processing.AbstractProcessor**: the base class implementing the Processor interface, supporting declaration of annotation types/options/source version and providing init/process extension points.
- **javax.annotation.processing.ProcessingEnvironment**: the environment provided by the compiler when initializing the processor, containing tools to write outputs, report errors, read the language model, and read build options.

This lesson focuses directly on **the structure of AbstractProcessor and the role of ProcessingEnvironment**, with Java 17+, a runnable example, the two-stage compilation order, multiple processing rounds, common errors, and guidelines for evolving into a processor used in real projects.

After this lesson, you should be able to explain: why super.init must be called, the meaning of the boolean returned from process, the difference between Element and TypeMirror, the roles of Filer/Messager/Elements/Types, the reason for using -processorpath, and why generated source can be compiled in the same invocation.

## 2. Processing Flow Diagram

~~~text
.java source files + annotations
                |
                v
            javac
                |
                v
     Find / load Processor
                |
                v
    init(ProcessingEnvironment)
                |
                v
      Processing round 1
    process(annotations, roundEnv)
        |           |
        |           +----> Messager: NOTE/WARNING/ERROR
        +----------------> Filer: create new source
                |
                v
      Processing round 2
   Newly generated files join input
                |
                v
     ... possibly more rounds ...
                |
                v
     Final round processingOver=true
                |
                v
   Complete compilation and output .class
~~~

The diagram is conceptual; it is not intended to fully describe javac's internal implementation order. The compiler will not always have exactly three rounds. A generated source does not necessarily contain new annotations; even so, it can still appear in the input of the next round.

**Distinction from Reflection:** Reflection typically inspects classes loaded at runtime; annotation processors primarily use javax.lang.model to inspect declarations/types **before .class files even need to exist**. Do not try to load source classes with Class.forName to analyze annotations in a normal processor.

## 3. What Is AbstractProcessor?

Processor is the standard interface declaring operations a compiler can ask a processor to perform. AbstractProcessor provides a more convenient implementation approach than implementing the entire interface directly.

Java 17 skeleton:

~~~java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.processor.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public synchronized void init(ProcessingEnvironment env) {
        super.init(env);
        // Store services needed from env.
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        // Process annotations and elements in the round.
        return true;
    }
}
~~~

**This is only an illustrative skeleton:** it does not yet have a complete package/annotation/app source. A complete runnable project appears in sections 7–9.

### Important Methods

| Component | Meaning |
| --- | --- |
| init(ProcessingEnvironment) | Called by the compiler to supply the environment before processing |
| process(Set<? extends TypeElement>, RoundEnvironment) | Processes the annotation types and elements assigned in the round |
| getSupportedAnnotationTypes() | Declares the names of annotations the processor can handle |
| getSupportedSourceVersion() | Declares the source language level supported by the processor |
| getSupportedOptions() | Declares the names of -A options |
| getCompletions(...) | API suggesting completions for annotation values, usually does not need overriding |
| protected processingEnv | Environment field of AbstractProcessor after init |

AbstractProcessor is capable of reading configuration annotations such as SupportedAnnotationTypes, SupportedSourceVersion, and SupportedOptions to return the corresponding information. Failing to declare supported annotations or an appropriate source version can cause warnings and prevent the processor from being invoked as desired.

**super.init(env) is very important.** If overriding init and forgetting to call super.init, AbstractProcessor's processingEnv field and several default mechanisms may not be validly initialized. Do not use processingEnv in a constructor or static initializer before the compiler calls init.

### Boolean Returned from process

- **true**: the processor declares it has handled/claimed the handed annotation types; subsequent processors will normally not be handed those same types again.
- **false**: not claimed; the compiler can give other processors a chance to process the corresponding types.

**true does not mean “build succeeded”.** A processor can still report ERROR via Messager and then return true. This is a decision about annotation distribution among processors, not javac's exit code.

The learning example exclusively owns @GenerateGreeting, so it returns true. When multiple processors need to read an annotation, claiming must be designed according to a coordination contract.

## 4. ProcessingEnvironment: Set of Compiler-Provided Services

ProcessingEnvironment is not an object manually created by the author with new. The compiler provides it via init. APIs worth remembering:

| Method | Returns | Used For |
| --- | --- | --- |
| getFiler() | Filer | Creating .java, .class, or resource outputs managed by the compiler |
| getMessager() | Messager | Printing NOTE/WARNING/ERROR diagnostics attached to source elements |
| getElementUtils() | Elements | Finding and inspecting class/package/method/field declarations |
| getTypeUtils() | Types | Analyzing TypeMirror, assignability, subtype, erasure |
| getOptions() | Map<String,String> | Reading -Akey=value configuration for the processor |
| getSourceVersion() | SourceVersion | Knowing the source version of the processing environment |
| getLocale() | Locale | Locale used for constructing diagnostics |

~~~text
                  ProcessingEnvironment
                          |
          +---------------+---------------+
          |               |               |
        Filer          Messager          Elements
       output        diagnostics     declarations
          |               |               |
     .java/.class       errors          TypeElement
                          |
                       Types
                     TypeMirror
~~~

**Do not mix roles:**

- **Filer** writes outputs according to compiler rules. Do not replace it with FileWriter arbitrarily overwriting original source.
- **Messager** is the standard channel for javac/IDEs to receive messages with severity and location. Do not use System.out to simulate compile errors.
- **Elements** queries about *declarations*: a class's package, qualified name, type members.
- **Types** queries about *types*: which type is assignable to which type, subtypes, erasure, etc.

### How Do Element and TypeMirror Differ?

Element represents a **declaration/program element**; TypeElement represents a type declaration (class/interface...). TypeMirror represents a **type** in the compiler's type system model, for example List<String>, a primitive type, or a generic type variable.

In a processor, do not compare getSimpleName() as strings and conclude two TypeElements represent the same type; two packages can have classes with the same name. If type relationships need analysis, use the corresponding Types API.

Illustrative snippet, not standalone:

~~~java
TypeElement runnableType =
        processingEnv.getElementUtils().getTypeElement("java.lang.Runnable");
boolean matches = processingEnv.getTypeUtils().isAssignable(
        candidate.asType(),
        runnableType.asType());
~~~

candidate must be a TypeElement obtained from the processing environment. Depending on logic, Types.isSubtype or other APIs may be more suitable; do not use Reflection on uncompiled source types.

## 5. Lifecycle: init, process, and RoundEnvironment

**init** is normally called once per processor instance before processing rounds begin. **process** may be called multiple times within the same compilation run.

RoundEnvironment provides:

- **getElementsAnnotatedWith(AnnotationClass.class)**: elements annotated with the specified annotation in the round.
- **getElementsAnnotatedWith(TypeElement)**: variant using the compile-time model instead of Class<?>.
- **getRootElements()**: root elements provided for the round.
- **processingOver()**: indicates the final round.
- **errorRaised()**: indicates whether an error was reported in a previous round per API contract.

For example:

~~~text
Round 1:
    Order.java is annotated with @GenerateGreeting
    Processor generates OrderGreeting.java

Round 2:
    OrderGreeting.java becomes new source
    No new @GenerateGreeting

Round 3:
    Final round, processingOver() == true
~~~

The final round usually has an empty annotation set. Do not assume process runs only once or that every round has new elements. A good processor does not create duplicate files just because process is called again.

**FilerException:** recreating the same output file in one processing invocation, overwriting an input file, or collisions among multiple processors can lead to FilerException. Use unique output names, control the round creating files, and report errors instead of catching and silencing them.

## 6. Java 17 Practice Project

Create the **processor-lab** directory:

~~~text
processor-lab/
├── src-processor/
│   └── demo/
│       └── processor/
│           ├── GenerateGreeting.java
│           └── GreetingProcessor.java
├── src-app/
│   └── demo/
│       └── app/
│           ├── Order.java
│           └── Main.java
└── build/
    ├── processor/
    ├── classes/
    └── generated/
~~~

Output paths will be created before compiling. Separate src-processor and src-app to clearly see the **two stages**: first creating the processor .class; next using that processor when compiling the app. No Maven/Gradle or external libraries needed.

### 6.1. src-processor/demo/processor/GenerateGreeting.java

~~~java
package demo.processor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
}
~~~

@Target(TYPE) allows attaching the annotation to type declarations. The demo processor accepts ElementKind.CLASS; if attached to an interface or enum, it actively emits ERROR. RetentionPolicy.SOURCE is sufficient for a processor reading annotations in source; there is no need to retain this metadata at runtime.

Annotation processors **do not force every annotation to have SOURCE retention**. Retention describes where the annotation is kept, while selecting/running processors depends on the compiler and annotation processing configuration.

### 6.2. src-processor/demo/processor/GreetingProcessor.java

~~~java
package demo.processor;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Filer;
import javax.annotation.processing.Messager;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.PackageElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.Elements;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.processor.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private Filer filer;
    private Messager messager;
    private Elements elements;

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        filer = environment.getFiler();
        messager = environment.getMessager();
        elements = environment.getElementUtils();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnvironment) {
        if (roundEnvironment.processingOver()) {
            return true;
        }

        for (Element element : roundEnvironment
                .getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "Only classes are supported", element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            PackageElement packageElement = elements.getPackageOf(type);
            String packageName = packageElement.isUnnamed() ? ""
                    : packageElement.getQualifiedName().toString();
            String simpleName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty() ? simpleName
                    : packageName + "." + simpleName;

            try {
                JavaFileObject file = filer.createSourceFile(qualifiedName, type);
                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n\n");
                    }
                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Generated for "
                            + type.getSimpleName() + "\";\n");
                    writer.write("    }\n}\n");
                }
                messager.printMessage(Diagnostic.Kind.NOTE,
                        "Generated " + qualifiedName, type);
            } catch (IOException ex) {
                messager.printMessage(Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": " + ex.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

**Code explanation:**

1. SupportedAnnotationTypes specifies the qualified name of the annotation that the processor accepts.
2. SupportedSourceVersion declares the Java 17 language level the processor was designed to support.
3. init calls super.init before retrieving Filer, Messager, and Elements.
4. process skips file generation when processingOver() is true.
5. getElementsAnnotatedWith retrieves sources in the round carrying @GenerateGreeting.
6. The processor checks that element has ElementKind.CLASS before casting to TypeElement.
7. Elements.getPackageOf retrieves the package. The qualified name of the output is the class name + Greeting in the corresponding package.
8. Filer.createSourceFile creates the new source, writer writes the Java code, and closes via try-with-resources.
9. Messager NOTE indicates the output was created; IOException errors are converted into ERROR diagnostics.
10. return true means claiming this annotation type, not guaranteeing the entire build succeeded.

**Demo limitations:** the annotated type only needs to be a class; the code does not handle every collision case with nested classes, multiple classes with the same simple name, or pre-existing generated types. This is an area to expand if used in production. Valid class names from getSimpleName() keep the sample source from having to escape arbitrary input data; if your output concatenates string data from annotation values, safely escape Java string literals.

The javax.annotation.processing and javax.lang.model APIs in JDK 17 belong to the **java.compiler** module; there is no need to install external dependencies just because the package name has a javax prefix.

### 6.3. src-app/demo/app/Order.java

~~~java
package demo.app;

import demo.processor.GenerateGreeting;

@GenerateGreeting
public final class Order {
}
~~~

Order is marked @GenerateGreeting. The processor will generate **demo.app.OrderGreeting**, in the same package as Order.

### 6.4. src-app/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(OrderGreeting.message());
    }
}
~~~

In the source project, **there is no initial OrderGreeting.java**. javac will see the generated source in the next annotation processing round and compile it; therefore the OrderGreeting reference in Main becomes valid within the same compilation invocation.

## 7. Compile Processor First, Compile App Later

Use **JDK 17 or newer** and open a terminal at the processor-lab root.

~~~sh
javac -version
java -version
~~~

Create output directories, choosing a command matching your shell:

~~~bash
# Bash on macOS/Linux
mkdir -p build/processor build/classes build/generated
~~~

~~~powershell
# PowerShell on Windows
New-Item -ItemType Directory -Path build/processor,build/classes,build/generated -Force | Out-Null
~~~

### Stage A — Compile the Processor

~~~sh
javac --release 17 -d build/processor src-processor/demo/processor/GenerateGreeting.java src-processor/demo/processor/GreetingProcessor.java
~~~

The .class files will appear in build/processor/demo/processor. The processor needs to be compiled first so the compiler can load the implementation in the next stage. Do not use java to run GreetingProcessor like an application with main.

### Stage B — Instruct javac to Run the Processor

~~~sh
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src-app/demo/app/Order.java src-app/demo/app/Main.java
~~~

| Option | Role |
| --- | --- |
| --release 17 | Compile at Java 17 language level |
| -cp build/processor | Where app source looks up the GenerateGreeting.class annotation |
| -processorpath build/processor | Where javac loads the processor implementation |
| -processor demo.processor.GreetingProcessor | Select the exact processor without relying on auto-discovery |
| -s build/generated | Where to write generated **.java source** |
| -d build/classes | Where to write .class files for app and generated types |

In the demo, the annotation API and implementation reside together in build/processor so both -cp and -processorpath point to one place. In production projects, the annotation API artifact is usually separated from the processor implementation artifact; the two paths serve different purposes.

After the command, javac may print a NOTE like:

~~~text
src-app/demo/app/Order.java:...: Note: Generated demo.app.OrderGreeting
~~~

This is a **javac diagnostic**, not application stdout. Line numbers/carets may vary by JDK.

View the generated source:

~~~text
build/generated/demo/app/OrderGreeting.java
~~~

Content:

~~~java
package demo.app;

public final class OrderGreeting {
    private OrderGreeting() {}
    public static String message() {
        return "Generated for Order";
    }
}
~~~

And generated bytecode is at build/classes/demo/app/OrderGreeting.class alongside Order.class and Main.class.

### Stage C — Run the App

~~~sh
java -cp build/classes demo.app.Main
~~~

**Exact stdout:**

~~~text
Generated for Order
~~~

This project does not need build/processor on the runtime classpath: the annotation has SOURCE retention, and generated output does not call processor code at runtime. In other projects, runtime dependencies must still be provided if executing code actually references them.

## 8. Observing Rounds When Debugging

Javac supports a diagnostic option:

~~~sh
javac -XprintRounds --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src-app/demo/app/Order.java src-app/demo/app/Main.java
~~~

When re-running from scratch, use **fresh output paths or clean the exact example output directories** to avoid confusing old generated files. Do not delete files belonging to other workspaces.

An illustrative log output:

~~~text
Round 1:
    input files: {demo.app.Order, demo.app.Main}
    annotations: [demo.processor.GenerateGreeting]
    last round: false
Round 2:
    input files: {demo.app.OrderGreeting}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

This is an **illustrative sample**, without guaranteeing exact output order/formatting across every JDK. Points to observe: Order carries the annotation in the first round; OrderGreeting is generated and becomes new input; the final round has processingOver()==true.

Javac also has -XprintProcessorInfo to find out which processors ran and which annotations were handed over. -X options are diagnostic; when using another JDK, consult javac -help-extra.

**Do not call createSourceFile in the final round:** files generated in the final round cannot participate in a normal new annotation processing round the way you might expect. The demo generates only when processingOver() is false.

## 9. Filer: Generating Files and Avoiding Duplicates

Filer manages outputs generated by the processor. Commonly used methods:

| Method | Used to Create |
| --- | --- |
| createSourceFile(qualifiedName, originatingElements...) | New .java file |
| createClassFile(binaryName, originatingElements...) | .class file directly generated by a generator |
| createResource(location, packageName, relativeName, originatingElements...) | Resource file at an API-supported location |

Typical operation structure:

~~~java
JavaFileObject file = filer.createSourceFile(qualifiedName, originatingType);
try (Writer writer = file.openWriter()) {
    writer.write("public final class Sample {}");
}
~~~

This snippet only illustrates the API; it is not a standalone program to run with java. originatingType is the source element corresponding to the generated file, helping the compiler/build tool understand input–output relationships. This is useful information for some incremental compilation systems, **without by itself guaranteeing** the processor is incremental-safe.

### Why Not Use FileWriter to Write Directly into src-app?

- The compiler does not necessarily see manually written files as valid annotation processing outputs in the next round.
- Overwriting user source is a hard-to-control side effect.
- Path issues arise easily when switching IDEs, Maven/Gradle, or Windows/Linux.
- It is difficult to use build caches/incremental tooling properly.

Filer enforces output rules, tracks created files, and has mechanisms to prevent duplicate file identities within a single invocation. Closing Writer ensures the compiler receives a complete file.

### FilerException and Output Collision

FilerException is an IOException that can appear when:

- Two annotated elements both generate the exact same qualified source name.
- A processor attempts to recreate a file already created in the current invocation.
- Source generated by a processor collides with source already present as input.
- Multiple processors generate the same output.

How to fix: define stable naming rules, check supported scopes of annotations, handle nested classes and name collisions, and generate each output once. Do not catch the error and pretend the build succeeded, because client code could be missing generated types or load stale artifacts.

## 10. Messager: Sending Standard Diagnostics

Messager helps the compiler/IDE attach messages to source code:

~~~java
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "Only classes are supported",
        element);
~~~

Some Diagnostic.Kind values:

- **NOTE**: processing status information.
- **WARNING**: warning.
- **MANDATORY_WARNING**: mandatory warning per compiler contract.
- **ERROR**: compilation error.

With overloads accepting Element, the message is attached to the source declaration. There are overloads accepting AnnotationMirror/AnnotationValue to pinpoint an invalid annotation or value.

**System.out is not a substitute for Messager.** If an annotation has missing configuration or a type fails requirements, report a helpful ERROR stating the reason and how to fix it. Merely logging stack traces or throwing undirected exceptions makes it hard for users to find errors.

In the example, an interface annotated with @GenerateGreeting is a syntactically valid annotation target (@Target(TYPE)) yet **invalid under the processor's policy**. The processor will report Only classes are supported. This is a processor validation error, not an annotation definition error.

## 11. Elements, Types, and Checking Source at Compile Time

### Elements and TypeElement

In the demo:

~~~java
PackageElement packageElement = elements.getPackageOf(type);
String packageName = packageElement.isUnnamed() ? ""
        : packageElement.getQualifiedName().toString();
~~~

The Elements API provides package information more accurately than manually splitting .java file path strings. With nested classes or generics, do not rely solely on simple names to infer package/binary names.

### Types and TypeMirror

If the processor must only accept classes implementing Runnable, production code can retrieve the TypeElement corresponding to java.lang.Runnable and check with Types.isAssignable. This is a check on the compile-time type model; comparing short name strings is insufficient because two types can share the same simple name.

Non-standalone snippet:

~~~java
TypeElement runnableType =
        processingEnv.getElementUtils().getTypeElement("java.lang.Runnable");
boolean valid = processingEnv.getTypeUtils().isAssignable(
        candidate.asType(),
        runnableType.asType());
~~~

candidate must be an obtained TypeElement. Depending on the case, null checks, subtypes, generic bounds, or erasure may need checking so the rule truly matches business requirements. Using the right type-model API is better than Reflection when source does not yet have bytecode.

### Options from the Compiler

Externally you can pass:

~~~sh
javac -Agreeting.mode=short ...
~~~

In an extended processor, declare @SupportedOptions("greeting.mode") or override getSupportedOptions. Read:

~~~java
String mode = processingEnv.getOptions()
        .getOrDefault("greeting.mode", "default");
~~~

This snippet is **illustrative for extensions**; the runnable GreetingProcessor of this lesson does not support greeting.mode, so adding this option **does not automatically change output**. Do not confuse an illustrative snippet with an implemented feature.

Options are input data and need validation. When generating Java source from user-entered configuration text, escape strings per Java syntax; do not directly concatenate untrusted text into string literals or source code.

## 12. -processor, Discovery, and Packaging

The demo uses:

~~~text
-processorpath build/processor
-processor demo.processor.GreetingProcessor
~~~

This forces javac to select a specific processor, making it easy to reproduce. If the implementation is missing from the processor path, a processor not found error may occur.

Another mechanism is **service registration**. A classpath-style processor JAR can contain:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Content:

~~~text
demo.processor.GreetingProcessor
~~~

When the toolchain allows discovery, the compiler can find processors declared in service metadata. However, **you should not rely on a processor always running automatically just because its JAR is on the classpath**: discovery defaults and annotation processing policies change across JDK versions and build tools. The lesson's command explicitly selects the processor for verifiability.

If packaging the processor as a named Java module, the service provider can be published via module-info.java with provides javax.annotation.processing.Processor with ... following JPMS rules. This is another packaging approach; the demo project uses a simple classpath.

In Maven/Gradle projects, processor and annotation API dependencies can be separated and declared in configurations dedicated to annotation processing. The compiler process **executes with the build process's privileges**, so only run processors from trusted sources and control their versions.

## 13. Common Errors

| Symptom | Possible Cause | Fix Step |
| --- | --- | --- |
| Annotation processor not found | Stage A not compiled yet, wrong class name or -processorpath | Check build/processor and qualified class name |
| package demo.processor does not exist | App compile missing annotation API | Check -cp build/processor or annotation dependency |
| cannot find symbol OrderGreeting | Processor did not run or did not generate file | Check -processor, build/generated, javac diagnostics |
| FilerException: Attempt to recreate a file | Generated duplicate qualified name in compile invocation | Identify collision, create once |
| Only classes are supported | Annotation placed on a kind unsupported by processor | Change target or intentionally extend rule |
| Warning about supported source version | JDK/source level higher than declared by processor | Check @SupportedSourceVersion and --release |
| Generated .java exists but .class does not | Source compilation failed or -proc:only is used | Check errors and -proc flag |
| Processor does not appear to run | Discovery disabled or processor not selected | Explicitly select using -processor |
| Running produces old results | Stale generated/class output | Clean **exact demo outputs** and rebuild |

### -proc:only and -proc:none

- **-proc:only** requests running annotation processing while skipping full compilation into .class files. Used to inspect generators, not a build command to run a complete app.
- **-proc:none** disables annotation processing. With this project, unless OrderGreeting is provided another way, Main will fail to compile due to missing generated type.

The main commands in section 7 do not use these two flags. When moving to a new JDK, check annotation processing configuration explicitly because compiler/toolchain defaults can change.

## 14. Designing Processors for Real Projects

An easy-to-control structure:

~~~text
GreetingProcessor extends AbstractProcessor
    |
    +-- init(ProcessingEnvironment)
    |     +-- obtain Filer / Messager / Elements / Types
    |     +-- validate supported options
    |
    +-- process(annotations, round)
          +-- read annotated elements
          +-- validate kind, type, annotation values
          +-- build intermediate model
          +-- determine unique output name
          +-- generate source via Filer
          +-- report errors/warnings via Messager
~~~

Important rules:

1. **Validate before generating:** ensure kind, type constraints, and options are valid before writing partial source.
2. **Deterministic output:** identical inputs/options should produce identical code; do not inject timestamps/randomness into source without reason.
3. **Stable output names:** handle nested types, packages, collisions with existing source, and multiple annotated elements.
4. **Originating elements:** pass the exact source element to Filer to help compilers/build tooling understand dependencies; that alone is not enough to make a processor incremental-safe.
5. **Do not depend on Set order:** with multiple elements, sort by qualified name if generated source order matters.
6. **Do not retain Element/TypeMirror from old compile invocations:** the compiler model has its own lifecycle; avoid static caches causing stale data.
7. **Do not modify user-written source:** the standard JSR 269 API primarily supports reading the model and generating new output. AST mutation is a compiler-specific mechanism, not guaranteed by AbstractProcessor.
8. **Protect the build:** a processor is code running at build time; do not arbitrarily load unknown processors or grant sensitive privileges.

### Testing a Processor

At minimum, verify:

- With valid Order.java, demo.app.OrderGreeting.java is generated properly.
- Generated source is compiled by javac into .class in the same build.
- Running Main prints exactly Generated for Order.
- Annotating an unsupported type produces ERROR at the right location.
- Duplicate output names do not silently swallow errors.
- When the annotation is absent, no unnecessary source is generated.
- When changing input, a fresh build uses the newly generated code rather than stale artifacts.

You can use the JavaCompiler API from javax.tools, temporary test directories, or annotation processor testing libraries to verify output files and diagnostics, not just inspect NOTE messages.

## 15. Practice Exercises

**Exercise 1 — Identify Services.** If you want to create source, report a compile error, retrieve a class's package, and check type relationships, which of Filer/Messager/Elements/Types do you choose for each? Why is Reflection unsuitable when analyzing source?

**Exercise 2 — Observe Rounds.** Use -XprintRounds. Explain why OrderGreeting is processed by the compiler in the next round even though it does not have @GenerateGreeting, and why process can be called with an empty annotation set.

**Exercise 3 — Change Source Class.** Rename Order to Invoice, update Main to call InvoiceGreeting.message(). Compile cleanly. Expected stdout:

~~~text
Generated for Invoice
~~~

Explain how Elements.getPackageOf and TypeElement.getSimpleName lead to the generated class name.

**Exercise 4 — Validate Annotation.** Attach @GenerateGreeting to an interface to see the NOTE/ERROR decided by the processor. Change back to class and compile successfully.

**Exercise 5 — Test Filer Collision.** Choose a scenario where two sources cause the generator to target the same qualifiedName. Why does Filer refuse to recreate it? Propose a naming rule to avoid collisions.

**Exercise 6 — Separate Dependencies.** Suppose the annotation API is packaged into annotation-api.jar and the processor implementation into processor.jar. Point out the roles of the compile classpath and processor path in stage B.

**Exercise 7 — Service Registration.** State the META-INF/services path and the qualified name line used when auto-discovery is enabled. Explain why explicit -processor does not need to rely on discovery.

**Exercise 8 — Options.** Add SupportedOptions("greeting.mode"), read getOptions(), validate values, and produce different output when mode=short. Remember to escape output text and write tests for invalid values.

## 16. Knowledge Checklist

- Understand that annotation processors run at compile time, not runtime Reflection.
- AbstractProcessor is the base class of Processor and provides processingEnv.
- init is called before process and requires super.init.
- ProcessingEnvironment provides Filer, Messager, Elements, Types, Options, SourceVersion, and Locale.
- Element/TypeElement is a declaration; TypeMirror is a type; do not confuse the two models.
- process can run multiple rounds; the boolean return indicates claiming annotations.
- RoundEnvironment provides elements, root elements, and processingOver.
- Filer creates output once per qualified name; close Writer and handle FilerException appropriately.
- Messager helps print standard diagnostics instead of relying on System.out.
- Processor classes must be compiled first so javac can load them via -processorpath.
- -cp, -processorpath, -processor, -s, and -d serve different roles.
- You can inspect generated source and run generated bytecode, but must distinguish compiler output from program stdout.
- Auto-discovery/service metadata does not replace explicit processor configuration in every toolchain.
- Production design must account for output collisions, incremental behavior, diagnostics, and testing.

### Standard References for Deeper Reading

- Java SE 17 API: **javax.annotation.processing.AbstractProcessor**, **Processor**, **ProcessingEnvironment**, **RoundEnvironment**, **Filer**, **Messager**.
- Java SE 17 API: **javax.lang.model.element**, **javax.lang.model.type**, **javax.lang.model.util**.
- Official **javac** documentation: -processor, -processorpath, -proc:only, -s, -XprintRounds, and related compiler options.
- **JSR 269**: Pluggable Annotation Processing API.

**Remember:** AbstractProcessor defines the processor skeleton and callbacks; ProcessingEnvironment provides services for interacting with the compiler; RoundEnvironment provides data for each round. When combining these three components properly with Filer, Messager, and the Elements/Types model, you can generate new code in a controlled manner right inside the Java compilation process.
