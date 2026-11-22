# What is annotation processing and how does it differ from reflection in Java?

**Annotation processing** is a mechanism that allows a tool to participate in the **Java compilation** process, locate annotations in source code, and **validate, report errors/warnings, or generate additional source files and resources**. The standard mechanism is commonly known as **JSR 269 / Pluggable Annotation Processing API**, with APIs in **javax.annotation.processing** and **javax.lang.model**.

**Reflection** is a mechanism for **inspecting types, methods, fields, and annotations of classes in the runtime environment**, through APIs such as **java.lang.Class**, **java.lang.reflect.Method**, and **AnnotatedElement.getAnnotation(...)**.

The core difference does not lie in the **@** syntax, but in **the execution time and the information model that the tool reads**:

- A processor typically runs **while javac is compiling source**; it views program structure through **Element**, **TypeMirror**, and **AnnotationMirror**.
- Reflection is invoked by application code **when the program is running**, after the class has been loaded; it views the runtime model through **Class**, **Method**, **Field**, and annotation objects.
- A processor can process annotations with **RetentionPolicy.SOURCE**, which are not retained in class files for runtime reflection to read. Reflection normally requires annotations with **RetentionPolicy.RUNTIME**.
- A processor can generate new source code for the compiler to continue compiling, but **should not be understood as a tool for arbitrarily modifying original source content or modifying existing bytecode**. Reflection can inspect metadata and perform certain runtime operations permitted by Java, but it **does not automatically generate source or compile source** merely by reading an annotation.

## 1. Why does Java need annotation processing?

An annotation itself is **metadata**. For example:

~~~java
@GenerateNumber(42)
class Demo {}
~~~

An annotation does not by itself cause Java to create additional classes, validate configuration, or print the number 42. There needs to be a **component that reads and interprets** it.

At compile time, an annotation processor can turn this requirement into actions such as:

1. **Source code validation**: ensure only one class is annotated, or that an element has a valid format; use diagnostics to report errors right when running **javac**.
2. **Source code generation**: create auxiliary Java classes from metadata, such as a class containing constants or a mapper. The Java compiler can see and compile the generated source in subsequent processing rounds.
3. **Resource generation**: via **Filer** if the format and output location permit, such as metadata/resource descriptors for the build.
4. **Supporting analysis/build tools**: produce warnings, supplementary information, or check architectural conventions before running the program.

Libraries can use annotation processing to reduce boilerplate code (generated classes), catch errors early, or generate configuration. **Not every annotation in Java has a processor**, and **having an annotation does not mean javac will automatically run the corresponding processor**: the compiler must be configured to discover/load the processor.

## 2. The compile-time model: Processor, Element, TypeMirror

An annotation processor adheres to the contract of the **javax.annotation.processing.Processor** interface, typically implemented by extending **AbstractProcessor**:

~~~java
@SupportedAnnotationTypes("demo.GenerateNumber")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class NumberProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Analyze the elements of the program.
        return true;
    }
}
~~~

The snippet above only illustrates the skeleton; appropriate imports are needed for it to be standalone compilable Java source. The complete example is in the next section.

Key concepts:

| Component | Role |
| --- | --- |
| **Processor** | Contract for a tool participating in annotation processing |
| **AbstractProcessor** | Base class that helps implement Processor and provides the processing environment |
| **@SupportedAnnotationTypes** | Declares the names of annotation types that the processor supports; can be declared using **getSupportedAnnotationTypes()** |
| **@SupportedSourceVersion** | Declares the source language version supported by the processor |
| **ProcessingEnvironment** | Access point for utilities such as **Messager**, **Filer**, **Elements**, **Types**, and options |
| **RoundEnvironment** | Information about the current processing round, annotated elements, and final-round status |
| **Element / TypeElement** | Represents program declarations (class, method, field, package, …) in the compiler's model |
| **TypeMirror** | Represents a **Java type** in the compiler model, distinct from **java.lang.Class** |
| **AnnotationMirror** | Represents an annotation on an element in the compiler model |
| **Messager** | Emits **NOTE**, **WARNING**, and **ERROR** messages through the compiler |
| **Filer** | Creates Java source files, class files, or resources according to annotation processing rules |

**Element is not java.lang.reflect.AnnotatedElement.** The names are similar, but the objects belong to two different models and two different phases. **TypeElement** helps work with class/interface declarations via the compiler, whereas **Class<?>** in reflection represents a class already loaded at runtime.

A processor does not need to execute methods of the processed class, and normally **should not load application classes just to analyze them**. It uses name, type, and annotation information from javac's model.

## 3. Sample annotation processing program in Java 17+

We will create an annotation **@GenerateNumber(42)** with **SOURCE** retention, and a processor that reads the number 42 and generates the file **demo.generated.NumberInfo**. The application class uses the newly generated class right in the same compilation run.

Structure of the three **hand-written** files:

~~~text
project/
├── src/
│   └── demo/
│       ├── GenerateNumber.java
│       └── App.java
└── processor/
    └── demo/
        └── NumberProcessor.java
~~~

After the compilation commands, there will be the directories **processor-out**, **generated-src**, and **out**. You do not need to create the generated files manually.

### Step 1 — Declare the annotation

File **src/demo/GenerateNumber.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateNumber {
    int value();
}
~~~

**@Target(TYPE)** means it can only be used on appropriate type declarations such as classes. **@Retention(SOURCE)** ensures the annotation is present during source processing, but is not retained in the class file for runtime code to read via reflection.

The **value()** element accepts an integer. The syntax **@GenerateNumber(42)** is shorthand for **@GenerateNumber(value = 42)**.

### Step 2 — Write the processor

File **processor/demo/NumberProcessor.java**:

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateNumber")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class NumberProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        Set<? extends Element> annotated =
                roundEnv.getElementsAnnotatedWith(GenerateNumber.class);

        if (annotated.isEmpty()) {
            return true;
        }

        if (annotated.size() != 1) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Exactly one class must use @GenerateNumber");
            return true;
        }

        Element element = annotated.iterator().next();
        int number = element.getAnnotation(GenerateNumber.class).value();

        try {
            JavaFileObject file = processingEnv.getFiler()
                    .createSourceFile(
                            "demo.generated.NumberInfo", element);

            try (Writer writer = file.openWriter()) {
                writer.write("package demo.generated;\n");
                writer.write("public final class NumberInfo {\n");
                writer.write("  private NumberInfo() {}\n");
                writer.write(
                        "  public static final int VALUE = "
                        + number + ";\n");
                writer.write("}\n");
            }

            generated = true;
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Generated NumberInfo from @GenerateNumber",
                    element);

        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate NumberInfo: " + ex.getMessage(),
                    element);
        }

        return true;
    }
}
~~~

**Code explanation:**

1. **@SupportedAnnotationTypes("demo.GenerateNumber")** indicates that the processor supports the annotation type with the fully qualified name **demo.GenerateNumber**.
2. **@SupportedSourceVersion(RELEASE_17)** declares the source version supported by the processor. This declares the processor's capability, not a directive that overrides all javac version options.
3. **roundEnv.getElementsAnnotatedWith(GenerateNumber.class)** retrieves the **Element** instances annotated in the current round. That is the compiler model; there is no need to load App's class.
4. **element.getAnnotation(GenerateNumber.class)** is an API on **javax.lang.model.element.Element**. The syntax looks like reflection, but the **element** object is not a runtime Class/Method/Field. This API provides a way to read annotations in the compiler model; using **AnnotationMirror** is a common choice for general-purpose processors or when manipulating more complex metadata is needed.
5. The example intentionally requires **exactly one** element annotated with GenerateNumber in this compilation; if there are more, Messager emits an **ERROR**, causing compilation to fail.
6. **Filer.createSourceFile(...)** creates a new Java source file with the canonical name **demo.generated.NumberInfo**. Calling **openWriter()** writes its content; the compiler will see the new source in subsequent rounds.
7. The **generated** flag keeps the processor from attempting to recreate the same file across multiple rounds. **Filer** does not allow the same processor to create the same path repeatedly within a single processing run.
8. **return true** signals that this processor has *claimed* the annotation types it supports in the current round; it does **not** mean the program has executed or the newly generated class has been invoked.

**Practical note:** The example uses an integer to generate a Java literal, so no string escaping is needed. If generating code from arbitrary user-supplied String values, you must properly escape according to Java syntax and avoid generating invalid code. In real applications, you need to validate the Element kind thoroughly and handle multiple compilation units properly.

### Step 3 — Write the application class

File **src/demo/App.java**:

~~~java
package demo;

import demo.generated.NumberInfo;

@GenerateNumber(42)
public class App {
    public static void main(String[] args) {
        System.out.println("Generated value=" + NumberInfo.VALUE);
    }
}
~~~

**App** references **NumberInfo** even though the file **NumberInfo.java** does not exist before compiling. This is the goal of the experiment: the processor creates it while javac is processing App.java.

### Step 4 — Compile in two explicit phases

First, from the **project** directory, create the output directories. For example, with **PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force processor-out,generated-src,out | Out-Null
~~~

On bash/macOS/Linux, you can use:

~~~bash
mkdir -p processor-out generated-src out
~~~

Then run the same **javac/java** commands on both environments.

**Phase A: compile the annotation type and the processor itself, temporarily disabling processing while building the processor.**

~~~bash
javac --release 17 -proc:none -d processor-out src/demo/GenerateNumber.java processor/demo/NumberProcessor.java
~~~

This command creates **processor-out/demo/GenerateNumber.class** and **processor-out/demo/NumberProcessor.class**. The processor is not used to generate itself in this step. The **-proc:none** flag disables annotation processing for the current javac invocation.

**Phase B: compile App and instruct javac to invoke the processor.**

~~~bash
javac --release 17 -cp processor-out -processorpath processor-out -processor demo.NumberProcessor -s generated-src -d out src/demo/App.java
~~~

Important flags:

- **-cp processor-out**: places the annotation type **demo.GenerateNumber** on the classpath when compiling App.
- **-processorpath processor-out**: where javac looks for classes needed to load the processor and its dependencies.
- **-processor demo.NumberProcessor**: explicitly requires running the processor with this name; does not rely on the autodiscovery mechanism.
- **-s generated-src**: where generated Java sources are written.
- **-d out**: where compiled class files are written.
- **--release 17**: compiles targeting the Java 17 API and language level matching the example.

After Phase B, the generated source file will be **generated-src/demo/generated/NumberInfo.java**:

~~~java
package demo.generated;
public final class NumberInfo {
  private NumberInfo() {}
  public static final int VALUE = 42;
}
~~~

**javac** also compiles this generated source into a class in **out**. The processing phase may produce a **NOTE** message on javac's diagnostic stream; that is not stdout from the App program.

Run the application:

~~~bash
java -cp out demo.App
~~~

**Stdout of the java command:**

~~~text
Generated value=42
~~~

The application does not need to load the GenerateNumber annotation to print the number 42. The source code created by the processor has been compiled into the **NumberInfo** class, and the program reads the constant from that class. Because the annotation declares **SOURCE** retention, **App.class** does not contain an annotation record accessible via runtime reflection.

**If the processor is disabled in Phase B** without the **demo.generated.NumberInfo** class already on the classpath, javac cannot resolve the import **demo.generated.NumberInfo** in App. This proves that the processor participated in generating new input for the compiler.

## 4. A separate reflection example for comparison

Reflection works with already compiled/loaded classes and annotations retained at runtime. Create another file **src/demo/ReflectionDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeLabel {
    String value();
}

@RuntimeLabel("active")
class ActiveService {
}

class PlainService {
}

public class ReflectionDemo {
    public static void main(String[] args) {
        printLabel(ActiveService.class);
        printLabel(PlainService.class);
    }

    private static void printLabel(Class<?> type) {
        RuntimeLabel label =
                type.getAnnotation(RuntimeLabel.class);

        String value = label == null ? "<none>" : label.value();

        System.out.println(type.getSimpleName() + ": " + value);
    }
}
~~~

This example is independent of the processor in the previous section. Compile and run it directly with javac, **without needing NumberProcessor**:

~~~bash
javac --release 17 -proc:none -d out src/demo/ReflectionDemo.java
java -cp out demo.ReflectionDemo
~~~

**Stdout:**

~~~text
ActiveService: active
PlainService: <none>
~~~

Here:

- **@Retention(RUNTIME)** allows getAnnotation to read RuntimeLabel on **ActiveService**.
- **PlainService** is not annotated, so **getAnnotation(...)** returns null, and the program handles that case safely.
- **Class<?>** represents the loaded type; **getAnnotation(...)** reads the corresponding annotation metadata according to runtime rules.
- No new Java source is generated by these two reflection calls; processing via reflection is logic executed by the running program.

The **RuntimeLabel** annotation in the example can be seen by the compiler at compile time, yet **no processor is registered to process it**. Conversely, **GenerateNumber** using SOURCE retention is sufficient for a processor to read at compile time, while insufficient for runtime reflection.

## 5. Comparison table between annotation processing and reflection

| Criterion | Annotation processing (JSR 269) | Reflection |
| --- | --- | --- |
| **Typical timing** | During javac compilation | When the program runs and classes are loaded |
| **Purpose** | Validate source, produce diagnostics, generate additional source/resources | Inspect metadata/runtime types and execute runtime processing logic |
| **Primary APIs** | **javax.annotation.processing**, **javax.lang.model** | **java.lang.Class**, **java.lang.reflect**, **java.lang.annotation** |
| **Class declaration representation** | **TypeElement** | **Class<?>** |
| **Type representation** | **TypeMirror** | **Class**, **Type**, **AnnotatedType** depending on context |
| **Reading annotations** | **Element.getAnnotation()**, **getAnnotationMirrors()**, **RoundEnvironment** | **AnnotatedElement.getAnnotation()**, **getAnnotationsByType()** |
| **Minimum retention for visibility** | **SOURCE** is sufficient during source processing | **RUNTIME** to use standard Java reflection |
| **Can generate Java source while javac runs?** | Yes, via **Filer** | Not a capability of the reflection API |
| **Can produce compile-time errors?** | Yes, using **Messager** with **ERROR** | Does not participate in prior compilation |
| **Depends on loaded application classes?** | No, operates primarily on the compiler model | Yes, operates on classes/members at runtime |
| **Practical consequence** | Errors are caught early, code is pre-generated | Can make processing decisions based on annotations at runtime |

The table describes **standard usage**. There are still programs that invoke processors via the **JavaCompiler API** or other build tools, and reflection can be used inside build tools. The important distinction is **the compiler model and JSR 269** versus **the runtime object model of reflection**, rather than merely “which tool runs in which process”.

## 6. RetentionPolicy: SOURCE, CLASS, and RUNTIME

**@Retention** determines how long an annotation is retained.

~~~java
@Retention(RetentionPolicy.SOURCE)
@interface CompileOnly {}

@Retention(RetentionPolicy.CLASS)
@interface InClassFile {}

@Retention(RetentionPolicy.RUNTIME)
@interface AtRuntime {}
~~~

Use the exact imports **java.lang.annotation.Retention** and **RetentionPolicy**.

| Retention | Annotation processor during source compilation | Stored in class file | Standard runtime reflection |
| --- | --- | --- | --- |
| **SOURCE** | Visible | No | No |
| **CLASS** | Visible | Yes | No |
| **RUNTIME** | Visible | Yes | Yes |

**CLASS is the default retention** if an annotation type declaration has no **@Retention**.

Key point: **SOURCE is sufficient for annotation processing**, whereas **RUNTIME is required for runtime reflection**. However, declaring RUNTIME **does not automatically invoke reflection**, and declaring SOURCE **does not automatically trigger a processor**. Those are two independent policies: how metadata is retained and how a program/tool consumes that metadata.

Not every annotation processor handles only SOURCE annotations; it can also process CLASS/RUNTIME annotations appearing on source code during the compilation run.

## 7. Annotation processing rounds

Annotation processing typically runs across **multiple rounds**:

1. **Initial round**: the compiler provides the initial input sources; the processor is invoked with **RoundEnvironment**.
2. **The processor inspects and may generate new source/class files** using **Filer**.
3. **Subsequent rounds**: newly generated valid inputs can become subjects for the compiler and processors to continue analyzing.
4. **Final round**: **roundEnv.processingOver()** indicates that processing has ended; you should not attempt to generate additional source expecting it to be processed further after the final round.

The **NumberProcessor** example uses the condition:

~~~java
if (roundEnv.processingOver() || generated) {
    return true;
}
~~~

so it does not recreate **NumberInfo** repeatedly across different rounds. If a processor tries to call **createSourceFile("demo.generated.NumberInfo")** twice for the same path in a single processing run, **Filer** can throw a **FilerException**.

A processor is invoked for the annotation types it has declared support for; **process(...)** receives the set of **TypeElement** representing the annotation types of that round. The **RoundEnvironment** parameter also allows locating annotated elements, for example via **getElementsAnnotatedWith(...)**.

**return true** upon finishing processing means the processor *claims* those annotation types in the invocation, preventing them from continuing to be passed to certain subsequent processors according to the API rules. **return false** does not mean “compilation failed”; it means the processor **does not claim** those annotation types. Compilation errors are reported via **Messager** with kind **ERROR** or arise from source/tool errors.

A processor should not rely on the iteration order of elements found in a **Set**, and should not assume it runs strictly once. With multiple annotation types, multiple classes, and multiple processors, the flow can be more complex than the single-class example.

## 8. Discovering and registering a processor with javac

There are several ways to configure a processor:

**The explicit approach** uses **-processor demo.NumberProcessor** as in the experiment. This is a good choice for illustration because it does not depend on the default processor discovery behavior of individual javac versions.

In library projects, a processor is usually packaged into a separate JAR with a **Service Provider configuration**:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The contents of the service file can be the fully qualified name of the implementation class:

~~~text
demo.NumberProcessor
~~~

When javac is configured to allow processor discovery via the service loader and processor path, the service descriptor helps find providers without listing each class via **-processor**. Newer JDK versions may change the default behavior for running processors automatically; for reproducible builds, you should explicitly configure the processor, processor path, and toolchain.

Build systems such as **Maven** and **Gradle** have their own mechanisms for declaring dependencies and processor paths; you should generally separate dependencies needed to **compile source** from dependencies containing **processors executed during the build phase**. A processor is typically a **build-time dependency** and does not necessarily need to be on the application's runtime classpath.

Do not simply add a processor JAR to general dependencies and assume the processor is guaranteed to run. Verify the options, build configuration, and generated files.

## 9. What can and cannot a processor do?

**Can:**

- Detect annotated classes/methods/fields at compile time.
- Inspect types, signatures, modifiers, and metadata structures using **javax.lang.model**.
- Emit warnings or errors using **Messager**.
- Generate new Java source files and certain build-time resources through **Filer**.
- Coordinate with the compiler so that new source files are examined in processing rounds and compiled.

**Should not be treated as:**

- A mechanism that **runs automatically at program startup**: standard annotation processors operate during the build, not as listeners for every **java** command.
- A way to **automatically alter the bytecode of existing classes** or inject methods into the original class using the standard JSR 269 API. Some external tools may use compiler internals or bytecode weaving, but that is not a capability guaranteed by the standard annotation processing API.
- A duplicate of reflection: a processor is not written to call **Class.forName(...)** in order to analyze every uncompiled source class; the Element/TypeMirror model is designed for this stage.
- A component that automatically understands the business meaning of an annotation. You need a dedicated processor that knows how to interpret the annotation types defined by the library.

Some tools use annotations across multiple stages: a processor generates metadata/code at compile time, and then the library reads part of the metadata at runtime if it is retained. The two mechanisms can complement each other; **they are not mutually exclusive choices**.

## 10. How to choose between processing and reflection in an application

If the goal is to **detect misconfigurations before the build finishes**, process hundreds of classes to create a static registry, or generate data conversion classes from annotations, a processor is a suitable candidate. The benefits are catching issues early and reducing annotation-parsing work at runtime.

If the goal is to **read annotations on an already loaded class**, decide behavior based on metadata at runtime, or scan a set of application classes in the runtime environment, reflection may be more appropriate.

Illustrative examples:

- **Generating mapping code based on model structure:** annotation processing can help create auxiliary classes during the build. At runtime, the application calls the generated classes.
- **Enforcing required @Component on declarations:** a processor can report compile-time errors according to library rules.
- **Reading @Route to build a router at startup:** a framework can use reflection if the annotation is retained at RUNTIME.
- **Generating code based on @Route before running:** a framework can choose a processor and generate static registries/handlers instead of scanning classes at startup.

That a processor outperforms reflection **is not an absolute truth**: you must evaluate build cost, generated code size, configuration flexibility, plugin requirements, and runtime constraints. Reflection is not inherently too slow to use; results depend on workload volume and caching strategy.

## 11. Common mistakes

| Mistake | Cause | Resolution |
| --- | --- | --- |
| Declaring **@GenerateNumber** and expecting NumberInfo to appear automatically | Processor was not run | Ensure javac is configured to load the right processor |
| Adding only the annotation library while forgetting the processor dependency | Annotation types are separate from the processor | Declare both the classpath and processor path appropriately |
| Placing the processor on the classpath without configuring execution | Auto discovery is not guaranteed | Use **-processor** or configure the processor explicitly in the build tool |
| Calling **Class.forName("demo.App")** in a processor to find sources being compiled | App may not yet be compiled into a loadable class | Use **TypeElement**, **Elements**, and **RoundEnvironment** |
| Reading **@Retention(SOURCE)** with runtime reflection | SOURCE is not stored in the class file | Use compile-time processing; or RUNTIME if reflection is genuinely needed |
| Generating the same file across multiple rounds | Filer does not allow creating the same path repeatedly | Track file generation state and manage processing rounds |
| Treating **return true** from process as “execution succeeded” | It indicates claiming annotation types | Use **Messager.ERROR** to report actual errors |
| Assuming a processor modifies the original class using the standard API | JSR 269 primarily analyzes code and creates new files | Generate helper classes or use a tool specifically designed for that |
| Compiling the processor and App in a single pass and expecting javac to automatically run the new processor | The processor must be loaded by javac before processing | Compile the processor first, then compile App with the processor path |
| Dereferencing null from **getAnnotation(...)** at runtime | Not every class carries the annotation | Check for null or use **isAnnotationPresent** |
| Omitting **-s** and not knowing where generated source is placed | The location of generated source depends on javac configuration | Use **-s generated-src** for easy inspection |
| Generating code from arbitrary strings without escaping | Easily produces invalid Java source | Properly escape Java literals and validate input data |

## 12. Self-check exercises

**Exercise 1.** A library needs to report an error right at compile time if a class is annotated with **@GenerateNumber** but has an invalid structure. Should you use reflection or annotation processing? **Annotation processing** is appropriate because it can inspect **Element** and emit **Diagnostic.Kind.ERROR** in javac.

**Exercise 2.** A running program needs to read **@RuntimeLabel("active")** from **ActiveService.class**. Which API should be used? Use **ActiveService.class.getAnnotation(RuntimeLabel.class)** and read the **value()** element after checking for null. The annotation must have **RUNTIME** retention to be queried via standard reflection.

**Exercise 3.** Why can the **@GenerateNumber** annotation with SOURCE retention still be read by NumberProcessor? Because the processor inspects metadata during source compilation via **RoundEnvironment** and the compiler model, before SOURCE-retained annotations are omitted from the class file.

**Exercise 4.** Why must two **javac** commands be run in the example? The first command builds the processor's compiled binaries so the compiler can load and execute it. The second command compiles App with the compiled processor available, thereby generating **NumberInfo**.

**Exercise 5.** When NumberProcessor generates **NumberInfo.java**, do you need to run a separate javac command to compile NumberInfo? **Normally no** in the example: javac processes the generated source in subsequent compilation rounds and produces the corresponding class. You can verify both **generated-src/demo/generated/NumberInfo.java** and **out/demo/generated/NumberInfo.class**.

**Exercise 6.** Is **element.getAnnotation(GenerateNumber.class)** in the processor in the same context as **App.class.getAnnotation(...)**? **No**. The first is a method on **Element** belonging to the compiler model; the second is reflection on a runtime **Class**. They may share a similar method name, but they operate in different phases and on different objects.

**Exercise 7.** If an annotation has **@Retention(RUNTIME)**, is it mandatory to write a processor? **No**. Retention determines metadata storage, not how it is consumed. An application can use reflection alone without running any dedicated processor.

## 13. Official Java documentation

- **Java SE 17 — javax.annotation.processing:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html — interfaces and classes for annotation processing.
- **Java SE 17 — AbstractProcessor:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html — the base class for processors.
- **Java SE 17 — RoundEnvironment:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — annotated elements and processing round information.
- **Java SE 17 — javax.lang.model:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/package-summary.html — compile-time declaration/type model.
- **Java SE 17 — javac options:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html — the **-processor**, **-processorpath**, **-proc**, **-s**, **-d**, and **--release** options.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — APIs for reading annotations via runtime reflection.
- **Java Language Specification §9.6.4.2 — @Retention:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2 — annotation retention levels.

**Conclusion:** Annotation processing is a tool that works with **the source and symbol model during compilation**, capable of **validating and generating code** before the application runs. Reflection works with **loaded types/members at runtime** to **read and interpret metadata**. Choose the mechanism based on timing and purpose; do not assume an annotation has behavior on its own merely because it appears in source.
