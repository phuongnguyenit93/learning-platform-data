# Annotation Processing Phase in the Java Compilation Pipeline

Annotation processing is the stage in Java compilation where annotations are processed. During this phase, the compiler can invoke **annotation processors** to read metadata on classes, methods, fields, or packages, validate conventions, and generate additional source code or resources. The generated source files can then be compiled by the compiler within the same build.

Annotation processing is commonly used in libraries and frameworks to reduce boilerplate code, generate implementations automatically, produce metadata, or catch configuration errors at build time. Familiar examples include mapper generators, dependency injection frameworks, serializers, metamodels, and data access code.

Key point: an annotation is only metadata. Having an annotation on an element does not automatically generate code or change behavior. A corresponding annotation processor must be configured and executed by the compiler for that processing to occur.

## 1. Where Does Annotation Processing Fit in the Compilation Pipeline?

A simplified model of compilation with `javac`:

1. **Parse:** reads source code, tokenizes it, and builds the syntax tree.
2. **Enter:** registers class, member, and symbol information so the compiler can resolve references between types.
3. **Annotation processing:** discovers matching processors, invokes them in rounds, and accepts generated source files or resources.
4. **Attribution and type checking:** resolves names and checks types, overloads, generics, and language rules.
5. **Flow analysis:** checks control-flow rules, such as ensuring local variables are assigned before being read.
6. **Lowering/desugaring:** transforms certain high-level language constructs into internal forms suitable for later stages.
7. **Generate:** emits bytecode into `.class` files.

This is a conceptual model to understand the workflow; internal compiler details and phase boundaries may vary across versions or implementations.

```text
Source code + annotations
          |
          v
      Parse / Enter
          |
          v
  Annotation processing
      |           |
      |           +--> Diagnostic: warning / error
      |
      +--> Generate source / resource
                 |
                 v
        Next compiler round
                 |
                 v
       Type checking / Flow analysis
                 |
                 v
          Generate .class
```

Processors run inside the compiler process, typically on the JVM used to run `javac` or the build tool. It is not a step that the application runs on every startup. If an application needs to read annotations at runtime, that is a separate mechanism, usually using reflection with annotations that have `RetentionPolicy.RUNTIME`.

## 2. How Do Annotations and Annotation Processors Differ?

An **annotation** declares metadata:

~~~java
@GenerateGreeting("Java")
public class App {
}
~~~

In this example, `@GenerateGreeting` records a value attached to the `App` class. Annotations can describe intent or supply data to the compiler, frameworks, or processors.

An **annotation processor** is a program that runs at compile time to read that metadata and perform work:

- Check whether an annotation is placed on the proper element.
- Validate types, names, modifiers, or relationships between elements.
- Emit warnings or errors tied to specific source locations.
- Generate additional `.java`, `.class`, or resource files.
- Inspect type structures through the compiler's model APIs.

An annotation may have no processor handling it. In that case, the compiler can still retain the annotation according to its retention policy and compile the class normally, as long as no other language or compiler rule fails the build.

### 2.1. Retention Policy

`@Retention` determines where an annotation is kept:

| Retention | Meaning |
|---|---|
| `SOURCE` | Present only in source code; discarded from the class file after compilation |
| `CLASS` | Stored in the class file, but not returned by standard runtime reflection |
| `RUNTIME` | Stored in the class file and readable via reflection at runtime |

Annotation processors operate during compilation and can read annotations on elements provided by the compiler. If an annotation is only for code generation or build-time checks, `SOURCE` is usually the right choice. If a framework needs to read the annotation via reflection when the application runs, the annotation generally must use `RUNTIME`.

### 2.2. Built-in Compiler-Handled Annotations vs. Annotation Processors

Not every annotation requires a separate processor. For example, `@Override` is understood directly by the compiler to verify that a method validly overrides a supertype method. That is a language/compiler rule, not evidence that an external processor is running.

Conversely, a custom annotation such as `@GenerateGreeting` only produces generated code when its corresponding processor runs and handles it.

## 3. JSR 269 and Standard APIs

Java provides the standard annotation processing API under JSR 269, in the `javax.annotation.processing` package and related model packages.

Key components:

| API | Role |
|---|---|
| `AbstractProcessor` | Common base class for writing processors |
| `Processor` | Interface defining the processor contract |
| `ProcessingEnvironment` | Provides utilities and services during processing |
| `RoundEnvironment` | Provides annotated elements for a given round |
| `Element` | Represents a Java element such as a class, method, field, or package |
| `TypeElement` | Represents a type declaration |
| `Elements` | Looks up and manipulates the declaration model |
| `Types` | Compares and analyzes Java types |
| `Filer` | Creates source files, class files, and resources |
| `Messager` | Reports warning/error diagnostics to the compiler |

Processors typically do not parse source code using string searches or regex. Instead, they use `Element`, `TypeMirror`, `Elements`, and `Types` to work with the language model constructed by the compiler. This understands packages, generic types, modifiers, and inheritance relationships accurately.

### 3.1. Processor Lifecycle

A processor typically follows these steps:

1. The compiler instantiates the processor and provides `ProcessingEnvironment`.
2. The processor declares which annotation types it handles and which source version it supports.
3. The compiler calls `process(...)` in each round.
4. The processor reads elements and annotations from `RoundEnvironment`.
5. The processor may emit warnings/errors or create sources/resources via `Filer`.
6. If new sources are generated, the compiler feeds them into the next round.
7. When no new sources remain, the compiler invokes a final round with `processingOver() == true`.

A processor can be invoked multiple times within the same compilation. Do not assume `process(...)` runs only once.

## 4. Processing Rounds — The Multi-Round Mechanism

Annotation processing uses a round-based model to support code generated by processors.

- **First round:** contains the input source elements of the compilation.
- **Subsequent rounds:** may contain source files generated in the previous round.
- **Final round:** `roundEnv.processingOver()` returns `true`, signaling that no further normal annotation processing rounds will follow.

For example, `App.java` has `@GenerateGreeting`. The processor reads the annotation and creates `AppGreeting.java`. The compiler feeds `AppGreeting.java` into the next round, then type-checks and compiles it along with the related code.

A few important points:

- Sources generated in one round can be processed in a later round.
- Processors can generate additional sources, resources, or class files.
- The final round is suitable for summaries or final checks; do not rely on the final round to generate sources that need to be processed in a subsequent round.
- `roundEnv.errorRaised()` indicates whether an error diagnostic was raised in a previous round.
- Returning `true` from `process(...)` means the processor claims the passed-in annotations; other processors will not receive those claimed annotations in the same round. Returning `false` indicates the processor does not claim them.

Avoid generating the same file name repeatedly across rounds. `Filer` detects duplicate file creation and may throw `FilerException`. Processor design should use stable, unique output names and only generate files when actually needed.

## 5. Writing Your First Annotation Processor

We will create a `@GenerateGreeting` annotation. The processor reads the annotation's value and generates a Java class with a method that returns a greeting.

The example uses Java 17 and standard annotation processing APIs.

### 5.1. Directory Structure

~~~text
project/
  src/
    demo/
      GenerateGreeting.java
      GreetingProcessor.java
      App.java
  processor-out/
  generated-src/
  app-out/
~~~

The three files under `src/demo` are input source files. The `processor-out`, `generated-src`, and `app-out` directories are output directories for the compilation commands.

### 5.2. Declaring the Annotation

Create `src/demo/GenerateGreeting.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

Explanation:

- `@Target(ElementType.TYPE)` allows the annotation to be placed on type declarations such as classes, interfaces, enums, or records.
- `@Retention(RetentionPolicy.SOURCE)` indicates the annotation only needs to exist at compile time.
- `String value()` is the data the processor will read.

### 5.3. Writing the Processor

Create `src/demo/GreetingProcessor.java`:

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
                        "@GenerateGreeting only supports classes",
                        element);
                continue;
            }

            String greeting =
                    element.getAnnotation(GenerateGreeting.class).value();

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element)
                    .getQualifiedName()
                    .toString();

            String generatedName = element.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            String packageLine = packageName.isEmpty()
                    ? ""
                    : "package " + packageName + ";\n";

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);

                try (Writer writer = file.openWriter()) {
                    writer.write(packageLine
                            + "public final class " + generatedName + " {\n"
                            + "    private " + generatedName + "() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"Hello, "
                            + escapeJavaString(greeting)
                            + "!\";\n"
                            + "    }\n"
                            + "}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate source: " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }

    private static String escapeJavaString(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }
}
~~~

Key points to understand:

- `@SupportedAnnotationTypes` declares that the processor handles `demo.GenerateGreeting`.
- `@SupportedSourceVersion` declares the Java level supported by the processor.
- `AbstractProcessor` provides basic utilities and requires implementing `process(...)`.
- `RoundEnvironment` finds elements annotated in the current round.
- `Element` describes a source element; `ElementKind.CLASS` restricts the processor to classes.
- `processingEnv.getElementUtils()` retrieves the class's package to generate code in the same package.
- `Filer.createSourceFile(...)` creates a source file in compiler-managed output.
- `Messager` emits errors associated with an element so IDEs/compilers can point to the exact location.
- `escapeJavaString(...)` escapes backslashes, double quotes, and newlines so the annotation value becomes a valid Java string literal.

In this example, each annotated class produces its own class with the `Greeting` suffix. When building a processor for a real project, validate output names, handle name collisions, and clearly define which element kinds the annotation supports.

### 5.4. Using the Annotation

Create `src/demo/App.java`:

~~~java
package demo;

@GenerateGreeting("Java")
public class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.message());
    }
}
~~~

The source code references `AppGreeting`, even though that class has not been written manually. The processor will generate this class during compilation.

### 5.5. Compiling the Processor and the Application

From the `project` directory, create the output directories. In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force processor-out, generated-src, app-out | Out-Null
~~~

Step 1 — compile the annotation and processor:

~~~text
javac -proc:none -d processor-out src/demo/GenerateGreeting.java src/demo/GreetingProcessor.java
~~~

In this step, `-proc:none` disables annotation processing. We are compiling the processor itself, so there is no need to run processors yet.

Step 2 — compile the application and trigger the processor:

~~~text
javac -cp processor-out -processorpath processor-out -processor demo.GreetingProcessor -s generated-src -d app-out src/demo/App.java
~~~

Meaning of the options:

- `-cp processor-out`: the compiler finds the `GenerateGreeting` annotation in this directory.
- `-processorpath processor-out`: the compiler finds the processor class and its dependencies here.
- `-processor demo.GreetingProcessor`: instructs the compiler to run the processor with this fully qualified name.
- `-s generated-src`: places generated source files into the `generated-src` directory.
- `-d app-out`: places output class files into `app-out`.

After step 2, `generated-src` contains a generated source file similar to:

~~~java
package demo;

public final class AppGreeting {
    private AppGreeting() {}

    public static String message() {
        return "Hello, Java!";
    }
}
~~~

The compiler continues compiling the generated source in subsequent rounds. Therefore, `AppGreeting.class` is also created in `app-out`.

Step 3 — run the application:

~~~text
java -cp app-out demo.App
~~~

Stdout:

~~~text
Hello, Java!
~~~

This example illustrates the full flow: the annotation supplies data, the processor reads it, `Filer` creates the source file, and the compiler compiles that source for the application to use.

## 6. Exploring Key APIs

### 6.1. `Element` and `TypeMirror`

`Element` represents a declaration in the program, such as:

- `PackageElement`: package.
- `TypeElement`: class, interface, enum, or record.
- `ExecutableElement`: method or constructor.
- `VariableElement`: field, parameter, or local variable.
- `TypeParameterElement`: generic type parameter.

`TypeMirror` represents a type. A processor can retrieve return types, parameter types, generic types, and compare types via `Types`.

Avoid using `element.toString()` as a general-purpose way to analyze types. Use `TypeMirror`, `Types`, and `Elements` to inspect types according to the language model.

### 6.2. `Elements` and `Types`

`Elements` supports:

- Looking up packages and types by fully qualified name.
- Getting the package containing an element.
- Reading annotation and member information.
- Getting binary or qualified names of types.

`Types` supports:

- Checking whether two types are compatible or the same type.
- Checking subtypes and assignability.
- Erasing generic types via type erasure.
- Working with declared types, array types, executable types, and type variables.

These APIs help processors enforce type contracts. For example, a processor can verify that an annotated class implements a required interface before generating an adapter.

### 6.3. `Filer`

`Filer` is the standard API for creating outputs during annotation processing:

- `createSourceFile(...)`: creates a `.java` file.
- `createClassFile(...)`: creates a class file.
- `createResource(...)`: creates a resource in a given location and package.

Use `Filer` instead of writing files directly into the project's source directory. The compiler and build tool need to know which files were generated, where outputs live, and how they relate to input sources in order to manage rounds, incremental builds, and diagnostics.

Do not modify input source files from a processor. If you need to generate replacement code, create a new file with a valid, non-conflicting name.

### 6.4. `Messager`

Use `Messager` to report processing results:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.WARNING,
        "This annotation is being used in a deprecated way",
        element);
~~~

Common diagnostic kinds:

- `NOTE`: informational message.
- `WARNING`: warning, typically does not fail compilation.
- `MANDATORY_WARNING`: mandatory warning that must be reported.
- `ERROR`: error that causes compilation to fail.

Attach diagnostics to an element or annotation value whenever possible. IDEs can use that information to navigate the developer directly to the relevant location.

## 7. Processor Discovery and Configuration

There are two common ways for the compiler to know which processors to run.

### 7.1. Explicit Specification with `-processor`

Example:

~~~text
javac -processorpath processor-out -processor demo.GreetingProcessor -d out src/demo/App.java
~~~

`-processor` takes the fully qualified name of the processor. This is explicit and easy to control when testing or diagnosing a specific processor.

### 7.2. Auto-Discovery via Service Provider

A processor library can package the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Its contents list the fully qualified name of each processor, one per line:

~~~text
demo.GreetingProcessor
~~~

When the processor is on the processor path and discovered by the compiler via the service provider mechanism, the compiler can load it automatically without specifying each name with `-processor`.

For processors packaged as named modules, the module descriptor can declare the service provider using `provides javax.annotation.processing.Processor with ...`. Module configuration and the module path must align with how the compiler loads processors.

When reproducible builds are required, configure the processor path and dependencies explicitly. Relying on the general classpath for accidental processor discovery can make builds harder to control and cause differences across local machines, IDEs, and CI.

## 8. `javac` Options Related to Annotation Processing

| Option | Purpose |
|---|---|
| `-processorpath` / `--processor-path` | Specifies where to find annotation processors and their dependencies |
| `-processor` | Specifies the processor names to run |
| `-proc:none` | Disables annotation processing |
| `-proc:only` | Runs only annotation processing, without normal compilation |
| `-s directory` | Specifies where to store generated source files |
| `-d directory` | Specifies where to store class files |
| `-Akey=value` | Passes an option to processors |
| `-XprintRounds` | Prints information about processing rounds |
| `-XprintProcessorInfo` | Prints information about invoked processors and processed annotations |

Example for diagnosing rounds and processors:

~~~text
javac -XprintRounds -XprintProcessorInfo -cp processor-out -processorpath processor-out -processor demo.GreetingProcessor -s generated-src -d app-out src/demo/App.java
~~~

Options starting with `-X` are non-standard/advanced options; check `javac --help` and the documentation of your specific JDK if a compiler does not support an option.

### 8.1. Passing Configuration to a Processor with `-A`

A processor can declare supported options with `@SupportedOptions` or by overriding `getSupportedOptions()`.

Example command:

~~~text
javac -Aconfig=production -processorpath processor-out -processor demo.GreetingProcessor -d out src/demo/App.java
~~~

Inside the processor, read the value with:

~~~java
String config = processingEnv.getOptions().get("config");
~~~

Processor options are compile-time configuration. They do not automatically become system properties in the JVM running the application.

## 9. Annotation Processing in Maven and Gradle

In real projects, the build tool should manage processors as a separate dependency. Separating the annotation/API dependency from the processor dependency avoids pulling compiler plugins into the application's runtime classpath.

### 9.1. Maven

Example Maven Compiler Plugin configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>com.example</groupId>
                <artifactId>greeting-processor</artifactId>
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

If annotations are packaged in a separate artifact, declare the annotation artifact as a compile-time dependency of the application. The processor and dependencies used only during compile-time processing go into `annotationProcessorPaths`.

Run the build:

~~~text
mvn clean compile
~~~

Artifact names, plugin versions, and dependencies in the example are illustrative; replace them with your project's actual coordinates.

### 9.2. Gradle

Gradle Kotlin DSL example:

~~~kotlin
dependencies {
    compileOnly("com.example:greeting-annotations:1.0.0")
    annotationProcessor("com.example:greeting-processor:1.0.0")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

- `compileOnly` provides the annotation API when compiling the application without adding that dependency to runtime.
- `annotationProcessor` places the processor in a dedicated configuration for annotation processing.
- `toolchain` selects the JDK used to build at the specified version.

Run:

~~~text
./gradlew clean compileJava
~~~

On Windows, typically use:

~~~text
gradlew.bat clean compileJava
~~~

Gradle manages generated source directories and annotation processor outputs inside the build directory. Avoid committing auto-generated outputs unless the project specifically requires it.

## 10. Common Errors

### Processor Is Not Invoked

**Symptom:** annotations are present in the source, but no sources or resources are generated.

**Possible causes:**

- The processor is not on the processor path.
- The name in `-processor` is incorrect.
- The service provider file is missing or misnamed.
- The processor does not support the annotation being used.
- The build tool has not configured the annotation processor dependency.
- Annotation processing is disabled via `-proc:none`.

**How to fix:** verify the processor path, fully qualified name, service provider file, and build configuration. Try specifying `-processor` explicitly and use `-XprintRounds -XprintProcessorInfo` to see whether the compiler invokes the processor.

### `cannot find symbol` for a Generated Class

**Symptom:** the application references an auto-generated class, but the compiler reports it cannot be found.

**Possible causes:**

- The processor did not run or did not recognize the annotation.
- The processor generated a package or class name different from what the application references.
- The processor emitted an error before creating the file.
- The source file was written directly outside `Filer`, so the compiler did not include it in a round.
- Output source/class paths or the build cache are out of sync.

**How to fix:** inspect the generated sources from `-s`, processor diagnostics, the fully qualified name of the generated class, and the processor configuration in the build tool. Clear stale build outputs with a clean build if there is evidence of stale output.

### `FilerException: Attempt to recreate a file`

**Cause:** the processor attempted to create the same source or resource multiple times, usually from reprocessing the same element across rounds or multiple processors generating the same name.

**How to fix:** choose unique output names, control round handling, avoid generating files when unnecessary, and define clear ownership of output names across processors.

### `NoClassDefFoundError` When the Compiler Loads the Processor

**Cause:** the processor has a dependency that is missing from the processor path or has an incompatible version.

**How to fix:** add the required dependency to Maven/Gradle's annotation processor configuration or the processor path. The application's runtime classpath does not substitute for the processor path during compilation.

### Processor Reports Unsupported Source Version

**Cause:** the processor declares a source version older than the language version the compiler is using, or the processor has not been updated.

**How to fix:** update the processor and `@SupportedSourceVersion` to match the language level the processor has been tested against. Do not declare a newer source version merely to silence a warning if the processor does not actually support those constructs.

### Build Behaves Differently Between IDE and CI

**Cause:** the IDE and CI use different JDKs, processor paths, `-A` options, dependencies, or incremental build settings.

**How to fix:** centralize processor configuration in the build tool, align JDK/toolchain and dependency versions, and run clean builds in CI.

## 11. Designing a Good Annotation Processor

A reliable processor should follow these practices:

1. **Scope annotations properly:** declare `@SupportedAnnotationTypes` accurately, validate element kinds, and report clear errors.
2. **Do not assume processing order:** multiple processors may run in a round; do not rely on unguaranteed ordering.
3. **Support multiple rounds:** avoid creating duplicate files and handle sources generated in earlier rounds properly.
4. **Use `Filer`:** let the compiler and build tool manage outputs.
5. **Use `Messager`:** report errors attached to elements instead of throwing generic exceptions.
6. **Respect Java types:** use `Elements`, `Types`, `Element`, and `TypeMirror` rather than parsing source code with regex.
7. **Keep outputs deterministic:** identical inputs and options should produce identical outputs; avoid depending on timestamps, local machine paths, or unstable file ordering.
8. **Declare options:** annotate with `@SupportedOptions` and validate input values.
9. **Do not modify original sources:** generate new files with unique names and let the build tool manage them.
10. **Maintain version compatibility:** declare an appropriate source version and test the processor against the target JDK/toolchain.

An annotation processor is executable code that runs during the build, so only add processors from trusted sources. A processor can read source code and perform actions permitted to the account running the build; manage it like a build plugin with code execution privileges.

## 12. When Should You Use Annotation Processing?

Annotation processing is a good fit when the required information is already present in Java's structure and can be validated or turned into code at compile time:

- Generating implementations from interfaces or annotations.
- Creating mappers between data types.
- Generating builders, adapters, or metadata.
- Enforcing architectural or API rules.
- Generating registries, serializers, or schemas.
- Reporting configuration errors before the application runs.

Avoid using a processor merely to replace a short snippet of code without clear benefit. Processors add build complexity and require version management, compiler compatibility, and IDE/CI configuration.

If the requirement is simply to read annotations at runtime, use reflection with an appropriate retention policy. If broad source modifications or complex syntactic transformations are needed, evaluate dedicated compiler tools or plugins instead of forcing annotation processing beyond its intended design.

## 13. Annotation Processing Diagnostic Checklist

- [ ] The annotation declares appropriate `@Target` and `@Retention`.
- [ ] The processor extends `AbstractProcessor` and implements `process(...)`.
- [ ] `@SupportedAnnotationTypes` matches the fully qualified annotation name.
- [ ] `@SupportedSourceVersion` reflects the version supported by the processor.
- [ ] The processor and its dependencies are on the processor path.
- [ ] The annotation API is on the application's compile classpath/module path.
- [ ] The processor is discovered via `-processor` or a valid service provider.
- [ ] `-proc:none` is not accidentally disabling processing.
- [ ] Sources are generated via `Filer`, not written manually into the source tree.
- [ ] `-s` and `-d` point to appropriate output directories.
- [ ] There are no `Messager` errors or duplicate output names.
- [ ] Generated sources are compiled by the compiler in subsequent rounds.
- [ ] Maven/Gradle/IDE/CI use the same processor configuration and JDK.
- [ ] Run a clean build and inspect the generated output.

Annotation processing bridges metadata in source code and automatically generated code right during compilation. When you understand its place in the compilation pipeline, the round mechanism, the `Filer`/`Messager` APIs, and how to configure the processor path, you can build code generators that are controlled, easy to diagnose, and consistently reproducible between developer machines and CI.