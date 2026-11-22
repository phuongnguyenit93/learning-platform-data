# Annotation Processing Phase in javac

Annotation Processing is the phase of processing annotations at compile time. The **javac** compiler can load annotation processors to read information about packages, classes, methods, fields, and annotations in the source code, and then validate rules or generate additional source code, class files, and resources.

This phase is widely used in Java libraries and frameworks. For example: Lombok supports code generation for certain Java constructs; MapStruct generates mappers; Dagger generates code for dependency injection; other processors can create metadata, registries, adapters, or enforce API conventions.

Annotation processing takes place at build time, before the application runs. It is not a runtime reflection mechanism. Processors run within the compilation process and work with the program model provided by the compiler.

## 1. Where does Annotation Processing fit in the compilation process?

A compilation run can be conceptualized as the following main steps:

1. **Reading and parsing:** javac reads the source files, parses packages, imports, type declarations, and Java syntax.
2. **Establishing the declaration model:** the compiler determines the root elements and type information needed so that processors can query them.
3. **Annotation processing:** javac locates configured processors, identifies matching annotations, and invokes processors in rounds.
4. **Type analysis and checking:** the compiler checks types, access rights, overloading, generics, and language rules across the final set of sources.
5. **Bytecode generation:** unless running in annotation-processing-only mode, javac generates `.class` files for both the original source code and the generated source code.

This is a conceptual model for understanding the role of the processing phase. The internal details of javac can be more complex, especially when multiple modules are involved or when annotation processors generate additional sources.

Processors do not typically operate directly on compiled bytecode. They read the language model through APIs such as Element, TypeMirror, Elements, and Types, and then generate sources or resources through Filer.

## 2. Processing rounds

Annotation processing operates in rounds. A round receives the initial set of sources or the sources generated from the previous round.

General workflow:

~~~text
Initial Java sources
       |
       v
Round 1: find annotations and invoke processors
       |
       +---- processor generates no new sources
       |             |
       |             v
       |       Final round (processingOver)
       |
       +---- processor generates new sources
                     |
                     v
              javac reads new sources
                     |
                     v
              Round 2, Round 3, ...
                     |
                     v
              No more new sources
                     |
                     v
                Final round
                     |
                     v
          Analyze and generate class files
~~~

In each round:

- RoundEnvironment provides the root elements and the elements carrying annotations to be processed.
- A processor can read declaration structures, check conditions, and generate new sources.
- Newly generated Java sources are fed into subsequent rounds for the compiler to continue processing.
- A processor that has been invoked during a compilation run may continue to be invoked in subsequent rounds, including the final round.
- When roundEnv.processingOver() returns true, the processor knows there will be no more normal processing rounds to follow.

The final round is an opportunity to finalize aggregate work based on previous rounds. You should not create additional source files in the final round because there is no subsequent round for the compiler to process those sources.

A processor typically checks processingOver() at the beginning of the process method to avoid repeating file generation in the final round.

## 3. Processor API and the role of components

The main APIs reside in two packages:

- javax.annotation.processing: processor interface, processing environment, rounds, Filer, and Messager.
- javax.lang.model: model representing elements, types, packages, modules, and type-querying utilities.

Common components:

| API | Role |
|---|---|
| Processor | Contract that an annotation processor must implement |
| AbstractProcessor | Base class that reduces boilerplate code to implement |
| ProcessingEnvironment | Provides Filer, Messager, Elements, Types, and options |
| RoundEnvironment | Provides elements and state of the current round |
| Element | Represents a declaration such as a class, method, field, or package |
| TypeElement | Represents a type declaration such as a class or interface |
| ExecutableElement | Represents a method or constructor |
| VariableElement | Represents a field, parameter, or local variable in the model |
| TypeMirror | Represents a Java type in the compiler model |
| Elements | Utilities for querying declarations and packages |
| Types | Utilities for comparing, checking, and operating on types |
| Filer | Creates source files, class files, and resources |
| Messager | Sends NOTE, WARNING, or ERROR messages to compiler output |

### AbstractProcessor

Most real-world processors extend AbstractProcessor rather than implementing Processor from scratch.

Commonly declared via annotations:

- @SupportedAnnotationTypes: the annotations that the processor handles.
- @SupportedSourceVersion: the Java language version that the processor supports.
- @SupportedOptions: custom options that the processor accepts via javac -A.

A processor can also override the corresponding methods if dynamic configuration is needed.

### process

The core method:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
)
~~~

- annotations is the set of annotation interfaces requested to be processed in the current round.
- roundEnv provides the annotated elements, root elements, and round state.
- The return value indicates whether the processor claims the passed-in annotation interfaces.

If it returns true, the processor declares that it has processed the annotation interfaces in the passed-in set, and subsequent processors will not receive those claimed annotations in that round. If it returns false, the processor does not claim them, giving other processors a chance to process them.

A general-purpose processor supporting `"*"` annotations should be careful with its return value. If it does not intend to block other processors, return false.

## 4. How javac locates and loads processors

A processor is Java code compiled into class files and typically packaged in a JAR. It runs in the compiler's execution environment, so it is necessary to distinguish:

- **Compile classpath:** where javac looks for classes referenced by the source code being compiled.
- **Processor path:** where javac looks for annotation processor classes and dependencies that the processor needs at runtime.
- **Processor module path:** where javac looks for processors packaged as modules.

Important options:

| Option | Meaning |
|---|---|
| -processorpath or --processor-path | Path containing processors and processor dependencies |
| --processor-module-path | Module path for processors |
| -processor | Specifies the class names of processors to run |
| -proc:none | Disables annotation processing |
| -proc:only | Runs only annotation processing, skipping the subsequent class compilation step |
| -proc:full | Performs annotation processing and compilation |
| -Akey=value | Passes a custom option to processors |

Example of specifying a processor explicitly:

~~~bash
javac \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/app/demo/app/App.java
~~~

If a processor depends on annotation types or libraries that the application source code also needs, place the corresponding dependencies on the compile classpath. The processor path and compile classpath serve different purposes, even though some projects may use the same directory for both.

### Automatic discovery via Service Provider

A processor can be discovered automatically using the Java Service Provider mechanism. Inside the processor JAR, create the file:

META-INF/services/javax.annotation.processing.Processor

The file content is the fully qualified name of each processor, one per line:

~~~text
demo.processor.GenerateGreetingProcessor
~~~

When javac is configured to run annotation processing and finds a JAR containing this service descriptor on the processor path, the compiler can discover the processor without listing its class name in -processor.

If only the processor class is present without a service descriptor and without specifying -processor, javac may not find the processor when relying on automatic discovery.

### Changes starting in JDK 23

Starting in JDK 23, javac no longer runs all processors found on the classpath by default simply because they are present there. Annotation processing must be requested explicitly, such as with -processor, --processor-path, --processor-module-path, -proc:full, or -proc:only.

In JDK 17, javac had the legacy default behavior: when a processor was found on the classpath, the compiler could run annotation processing without explicit configuration like the above. Therefore, legacy builds might work on JDK 17 but stop generating code after upgrading the JDK if they relied on implicit discovery.

For stable builds across versions, explicitly configure the processor path and processor class/service in your build tool or javac command. Do not rely on a dependency happening to appear on the compile classpath.

## 5. Generating output with Filer

Processors should not write files directly into the src directory or perform arbitrary filesystem operations. The Filer API allows the compiler to manage files created during annotation processing.

Commonly used methods:

- createSourceFile(...): creates a Java source file.
- createClassFile(...): creates a class file.
- createResource(...): creates a resource in a location such as SOURCE_OUTPUT or CLASS_OUTPUT.

Output paths can be configured using javac options:

| Option | Output |
|---|---|
| -s directory | Directory containing source files generated by processors |
| -d directory | Directory containing class files |
| -Akey=value | Option value that processors read via ProcessingEnvironment.getOptions() |

Example:

~~~bash
javac \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/app/demo/app/App.java
~~~

In this example, sources generated by the processor go into build/generated-sources; compiled classes go into build/classes.

If a processor generates resources, specify the appropriate location and package path when calling Filer.createResource. The build tool also needs to know where resources are generated so it can include them in the output or packaged artifact.

Filer tracks files created within a compilation run. Do not recreate the same file name across multiple rounds; doing so can result in a FilerException because the file already exists.

## 6. Reporting messages with Messager

Processors should report errors attached to specific elements rather than throwing generic exceptions or merely printing to the console.

Example:

~~~java
processingEnv.getMessager().printMessage(
    Diagnostic.Kind.ERROR,
    "Tên khai báo không hợp lệ",
    element
);
~~~

Main message kinds:

- NOTE: informational messages for developers.
- WARNING: warnings, which do not necessarily cause compilation to fail.
- MANDATORY_WARNING: warnings required to be displayed by compiler rules.
- ERROR: errors that cause compilation to fail.

Messages can be attached to an Element, an AnnotationMirror, or a specific member so that IDEs and the compiler can pinpoint the location in source code.

Do not use System.out.println as the primary messaging channel. Messager integrates with compiler diagnostics, supports error localization, and informs the build tool whether compilation has errors.

## 7. Reading custom processor options

Options starting with -A are passed by javac to processors. Example:

~~~bash
javac \
    -Aapp.generatedPackage=demo.generated \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/app/demo/app/App.java
~~~

In the processor, read the value using:

~~~java
String generatedPackage =
        processingEnv.getOptions().get("app.generatedPackage");
~~~

To advertise supported options, you can use:

~~~java
@SupportedOptions("app.generatedPackage")
~~~

If a required option is missing or its value is invalid, the processor should report an error using Messager. Do not silently fall back to a different value if that could produce incorrect or inconsistent source code.

Multiple options can be declared in the annotation:

~~~java
@SupportedOptions({
    "app.generatedPackage",
    "app.generatedClassName"
})
~~~

Keep option names namespaced, such as app. or the project name, to reduce the chance of colliding with options from other processors.

## 8. Complete example: generating source code with an annotation processor

This example uses Java 17+ and javac. An annotation @GenerateGreeting marks a class. The processor reads that class and generates an additional class with a message() method.

Project structure:

~~~text
annotation-demo/
├── src/
│   ├── processor/
│   │   └── demo/
│   │       ├── GenerateGreeting.java
│   │       └── processor/
│   │           └── GenerateGreetingProcessor.java
│   └── app/
│       └── demo/
│           └── app/
│               └── App.java
└── build/
~~~

### Step 1: define the annotation

Create src/processor/demo/GenerateGreeting.java:

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

RetentionPolicy.SOURCE means the annotation only needs to be present in the source code at compile time; it is not retained in the class file for the application to read via reflection at runtime.

ElementType.TYPE restricts this annotation to type declarations such as classes, interfaces, enums, or records. The processor in this example only accepts regular classes.

### Step 2: write the processor

Create src/processor/demo/processor/GenerateGreetingProcessor.java:

~~~java
package demo.processor;

import demo.GenerateGreeting;

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
public final class GenerateGreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting chỉ áp dụng cho class",
                        element);
                continue;
            }

            TypeElement typeElement = (TypeElement) element;
            String generatedName =
                    typeElement.getSimpleName() + "Generated";
            String qualifiedName =
                    "demo.generated." + generatedName;

            try {
                JavaFileObject sourceFile =
                        processingEnv.getFiler()
                                .createSourceFile(qualifiedName, element);

                try (Writer writer = sourceFile.openWriter()) {
                    writer.write(
                            "package demo.generated;\n\n"
                            + "public final class " + generatedName + " {\n"
                            + "    private " + generatedName + "() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"Generated by annotation processing\";\n"
                            + "    }\n"
                            + "}\n");
                }

                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        "Generated " + qualifiedName,
                        element);

            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": "
                                + e.getMessage(),
                        element);
            }
        }

        return true;
    }
}
~~~

This processor:

1. Declares the annotation it supports.
2. Declares source version level 17.
3. Retrieves elements annotated with @GenerateGreeting.
4. Verifies that the element is a class.
5. Uses Filer.createSourceFile to generate a new class.
6. Uses Messager to report the result to the compiler.
7. Returns true to claim the annotation processed by the processor.

The processor does not use reflection to analyze the class being compiled. It uses Element and TypeElement provided by the compiler, which is suitable for source code that does not yet have bytecode.

### Step 3: write an application using the annotation

Create src/app/demo/app/App.java:

~~~java
package demo.app;

import demo.GenerateGreeting;

@GenerateGreeting
public class App {

    public static void main(String[] args) {
        System.out.println(
                demo.generated.AppGenerated.message());
    }
}
~~~

The AppGenerated class does not exist in the initial sources. It will be generated by the processor during compilation.

### Step 4: compile the annotation and processor

Create the output directory:

~~~bash
mkdir -p build/processor-classes
~~~

Compile the annotation along with the processor:

~~~bash
javac --release 17 \
    -d build/processor-classes \
    src/processor/demo/GenerateGreeting.java \
    src/processor/demo/processor/GenerateGreetingProcessor.java
~~~

After this step, the build/processor-classes directory contains:

~~~text
build/processor-classes/
└── demo/
    ├── GenerateGreeting.class
    └── processor/
        └── GenerateGreetingProcessor.class
~~~

### Step 5: run annotation processing when compiling the application

Create the output directories:

~~~bash
mkdir -p build/classes build/generated-sources
~~~

Compile the application and specify the processor explicitly:

~~~bash
javac --release 17 \
    -cp build/processor-classes \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/app/demo/app/App.java
~~~

Explanation:

- -cp build/processor-classes: helps the compiler find the demo.GenerateGreeting annotation used by App.
- -processorpath build/processor-classes: helps javac load the processor and its dependencies when running the processor.
- -processor demo.processor.GenerateGreetingProcessor: specifies the processor to run.
- -s build/generated-sources: where generated sources are written.
- -d build/classes: where compiled bytecode is written.

Because the processor is specified explicitly, this command does not rely on implicit discovery from the compile classpath and aligns with the default behavior change starting in JDK 23.

### Step 6: inspect the output

After compiling, the main files look like this:

~~~text
build/
├── processor-classes/
│   └── demo/
│       ├── GenerateGreeting.class
│       └── processor/
│           └── GenerateGreetingProcessor.class
├── generated-sources/
│   └── demo/
│       └── generated/
│           └── AppGenerated.java
└── classes/
    ├── demo/
    │   ├── app/
    │   │   └── App.class
    │   └── generated/
    │       └── AppGenerated.class
~~~

AppGenerated.java is generated in the first round. Javac reads the new source in the next round, then compiles it into AppGenerated.class.

Run the application:

~~~bash
java -cp build/classes demo.app.App
~~~

Output:

~~~text
Generated by annotation processing
~~~

The application only needs the class output; the annotation has SOURCE retention and the processor is only needed at compile time. Therefore, there is no need to include build/processor-classes on the runtime classpath in this example.

## 9. javac annotation processing modes

Commonly used modes:

~~~bash
javac -proc:none -d build/classes src/demo/App.java
~~~

Disables annotation processing. Source code is still compiled normally, but processors are not invoked.

~~~bash
javac -proc:only \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/demo/App.java
~~~

Runs only annotation processing. This mode is useful when you want to inspect generated sources separately without performing the final class compilation step of full mode.

~~~bash
javac -proc:full \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/demo/App.java
~~~

Performs annotation processing and compilation. When processors are explicitly configured, javac may enable processing by default; -proc:full helps express that intent clearly in scripts.

The default mode varies by JDK version. Starting in JDK 23, if there is no explicit annotation processing configuration, javac does not automatically run processors simply because they are on the classpath. When a build needs code generation, configure the processor path or processor class and verify behavior on the target JDK.

## 10. Integrating processors into build tools

In real-world projects, developers should not be expected to remember long javac commands. Build tools have dedicated mechanisms to separate compile dependencies from processors.

### Gradle

With the Java plugin, annotation processor dependencies are declared separately:

~~~groovy
dependencies {
    compileOnly "com.example:my-annotations:1.0"
    annotationProcessor "com.example:my-processor:1.0"
}
~~~

- compileOnly provides annotation types during compilation if the application needs to import them.
- annotationProcessor provides the processor and dependencies required for the processor to run at compile time.

If the annotation and processor are in the same artifact, you may need to declare dependencies appropriately according to how the library is packaged. Avoid placing processors on the application's runtime classpath if the application does not need them at runtime.

### Maven

With the Maven Compiler Plugin, processors can be configured in annotationProcessorPaths or according to the processor configuration of the plugin version in use. The exact configuration depends on the plugin version and how the project manages dependencies.

When upgrading the JDK or plugin version, check the Maven logs to confirm that the processor is actually loaded and generated sources appear in the expected output directory.

### Incremental builds and determinism

Processors should produce deterministic output from their inputs. The same source code, annotations, and options should produce the same result. Avoid depending on the current time, unstable iteration order, developer machine contents, or unnecessary network access.

Build tools can optimize incremental compilation based on the relationship between sources, processors, and generated outputs. Non-deterministic processors or writing files outside the build scope can make build results difficult to reproduce.

## 11. Common errors

**Processor does not run**

Check the processor path, -processor, service descriptor, and JDK version. On JDK 23+, do not rely on the processor happening to be on the compile classpath.

**Annotation type not found**

Application source code needs the annotation on the compile classpath. The processor path only serves to load the processor; it does not replace the compile classpath.

**Processor runs but does not see the annotation**

Check @SupportedAnnotationTypes, the fully qualified package name, retention, target, and the annotated element. Also check which round the annotation appears in.

**Generated class not found**

Verify that the processor actually calls Filer.createSourceFile, that the compiler runs a subsequent round, and that the generated source compiles successfully. Check -s and -d to confirm the right output directories.

**FilerException: Attempt to recreate a file**

The processor may be creating the same file name multiple times. Check the round, file name, and logic for preventing duplicate generation. Do not write the same generated type in every round.

**Source version errors**

@SupportedSourceVersion must match the source version supported by the processor. If using newer language APIs, update the source version or explicitly handle support limits.

**Generated source has syntax errors**

Use Messager to report input errors early, check escaping when generating Java literals, and inspect files in -s to find the cause. Do not concatenate package names or identifiers from unvalidated data.

**Annotation processing slows down the build**

Avoid scanning the entire classpath or filesystem unnecessarily. Only process annotations that the processor supports, avoid repeating work across rounds, and limit the data that needs to be read.

**Two processors handle the same annotation**

Understand the claiming rule. A processor returning true claims the passed-in annotations; subsequent processors may not receive those annotations in that round. If processors need to cooperate, clearly design which annotations are claimed and which processor is responsible.

## 12. Security and design principles

An annotation processor is code that executes at build time. A third-party processor can read files that the build user has permission to access, invoke other processes, or access the network if the environment allows it. Therefore:

- Only use processors from trusted sources and pin dependency versions.
- Separate runtime dependencies from compile-only dependencies.
- Do not pass secrets into processor options or the command line unnecessarily.
- Do not write tokens, credentials, or sensitive content into generated sources or diagnostics.
- Do not let processors directly modify the source tree or files outside the output directory.
- Use Filer and Messager to integrate with the compiler.
- Validate identifiers, package names, and values placed into generated code.
- Avoid depending on file ordering, time, or build machine environment.
- Keep processors small, easy to test, and clear in input error reporting.

If a processor generates code based on information outside the source code, make that data a managed and tracked input in the build. This helps keep builds reproducible and safer to cache.

## 13. Checklist when implementing an annotation processor

1. Identify which annotations are supported and which elements are valid.
2. Choose the source version and declare @SupportedSourceVersion.
3. Write the processor based on AbstractProcessor.
4. Use RoundEnvironment to retrieve elements to process.
5. Use Elements and Types to inspect declarations and types.
6. Use Filer to create sources, classes, or resources.
7. Use Messager to report errors and warnings on the exact element.
8. Define options with @SupportedOptions and read them via getOptions().
9. Configure the processor path or processor module path explicitly.
10. Verify discovery on JDK 23+.
11. Separate generated sources (-s) and class output (-d).
12. Test cases for missing annotations, wrong targets, multiple elements, multiple rounds, and duplicate generated names.
13. Verify incremental builds, clean builds, and CI results.

The annotation processing phase extends the compiler by enabling compile-time validation and code generation based on program structure. By understanding processing rounds, processor discovery, the compiler model, and Filer, you can build safe code-generation tools that integrate well with javac and produce reproducible builds.
