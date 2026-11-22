# Annotation processors and compiler arguments

In Java, an **annotation processor** is a program that runs during compilation to analyze annotations, enforce rules, or generate additional sources/resources. Tools that generate mappers, metadata, adapters, or boilerplate code commonly rely on this mechanism.

In the Java Platform Module System (JPMS), you must clearly distinguish **the module path of the application being compiled** from **the path used to locate annotation processors**. A JAR containing a processor is not necessarily a runtime dependency of the application. Placing it in the right location, declaring how the processor is discovered, and passing accurate compiler arguments determine whether the processor runs.

This topic belongs to the *Build tools* group: focusing on `javac`, Maven, Gradle, how processors are packaged, and diagnosing build errors when migrating projects to named modules.

## 1. At which stage does an annotation processor run?

A typical compilation flow can be pictured as:

    Java source with annotations
             |
             v
    javac analyzes sources + module graph
             |
             v
    Annotation processing rounds
      - find supported annotations
      - read source structure via Element/TypeMirror
      - generate extra sources or resources via Filer
             |
             v
    javac compiles original sources and generated sources
             |
             v
    .class in output directory/JAR

The standard API belongs to the `java.compiler` module, specifically:

- `javax.annotation.processing.Processor`: the processor contract.
- `javax.annotation.processing.AbstractProcessor`: a convenient base class.
- `javax.annotation.processing.RoundEnvironment`: information about a processing round.
- `javax.annotation.processing.ProcessingEnvironment`: access to `Messager`, `Filer`, `Elements`, `Types`, `Options`.
- `javax.lang.model.element.Element` and `TypeElement`: compile-time representations of Java program structure.
- `javax.lang.model.type.TypeMirror`: representation of types in the Java language model.

Annotation processing is not runtime reflection and does not require running the application to generate code. The processor runs inside the compilation environment and can create new files before `javac` finishes compiling.

## 2. Annotations vs. processors

An annotation is metadata placed on source code or declarations:

    package com.example.app;

    import java.lang.annotation.ElementType;
    import java.lang.annotation.Retention;
    import java.lang.annotation.RetentionPolicy;
    import java.lang.annotation.Target;

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.SOURCE)
    public @interface GenerateGreeting {
    }

Class using the annotation:

    package com.example.app;

    @GenerateGreeting
    public class OrderService {
    }

`@Retention(SOURCE)` is appropriate when the annotation is needed only for compile-time processing; the annotation does not need to be retained at runtime. The processor reads the source model and can generate additional classes.

One processor can support multiple annotations. Keep responsibilities separate:

- The annotation type declares data or markers in source code.
- The processor reads and handles annotations across compilation rounds.
- The compiler manages the processing lifecycle, outputs, and compilation of generated code.
- The build tool decides where the processor resides and which arguments are passed to the compiler.

Merely creating an annotation type does not cause any code to be generated automatically. A processor must be registered and annotation processing must be enabled.

## 3. Writing a minimal processor

The example below creates the class `com.example.app.generated.GreetingGenerated` when encountering `@GenerateGreeting`.

    package com.example.processor;

    import java.io.IOException;
    import java.io.Writer;
    import java.util.Set;

    import javax.annotation.processing.AbstractProcessor;
    import javax.annotation.processing.RoundEnvironment;
    import javax.annotation.processing.SupportedAnnotationTypes;
    import javax.lang.model.SourceVersion;
    import javax.lang.model.element.Element;
    import javax.lang.model.element.TypeElement;
    import javax.tools.Diagnostic;
    import javax.tools.JavaFileObject;

    @SupportedAnnotationTypes("com.example.app.GenerateGreeting")
    public final class GreetingProcessor extends AbstractProcessor {
        @Override
        public SourceVersion getSupportedSourceVersion() {
            return SourceVersion.latestSupported();
        }

        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment roundEnv) {

            if (roundEnv.processingOver() || annotations.isEmpty()) {
                return false;
            }

            for (TypeElement annotation : annotations) {
                for (Element ignored :
                        roundEnv.getElementsAnnotatedWith(annotation)) {
                    String name =
                            "com.example.app.generated.GreetingGenerated";

                    try {
                        JavaFileObject source =
                                processingEnv.getFiler()
                                        .createSourceFile(name);

                        try (Writer out = source.openWriter()) {
                            out.write(
                                "package com.example.app.generated;\n" +
                                "public final class GreetingGenerated {\n" +
                                "  public static String message() {\n" +
                                "    return \"Hello from processor\";\n" +
                                "  }\n" +
                                "}\n"
                            );
                        }
                    } catch (IOException e) {
                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.ERROR, e.toString());
                    }
                    return true;
                }
            }
            return false;
        }
    }

This is a minimal example for a single annotated class. Real-world processors must handle **multiple elements**, avoid creating the same file more than once, and provide appropriate originating elements when generating files to support incremental builds.

If `Filer.createSourceFile(...)` is called multiple times for the same filename in a single compilation, the compiler may report `FilerException`. A processor should not recreate files already generated in an earlier round.

## 4. Annotation processing runs in multiple rounds

A single compiler execution of processors may consist of multiple *rounds*.

In the first round, processors receive the annotations present in the source files. When a processor creates new sources, the compiler parses the new sources and can open another round. A final round signals that processing is finishing via `roundEnv.processingOver()`.

This matters when designing a generator:

- Do not assume all needed classes appear in the very first round.
- Do not regenerate a class with the same name across multiple rounds.
- Use `RoundEnvironment.getElementsAnnotatedWith(...)` to retrieve valid elements.
- Distinguish a processor **claiming** an annotation from blocking all other processors: the boolean return value of `process` indicates whether the annotations are claimed.
- Report errors through `Messager` rather than merely printing to standard output.

To observe rounds, use:

    javac -XprintRounds -XprintProcessorInfo ...

The `-X` flags mainly serve compiler diagnostics. They should not be treated as options for configuring processor business logic.

## 5. Two paths to locate processors: processor path and processor module path

JPMS clarifies two ways for the compiler to locate processors:

| Option | Used for | Common processor registration |
|---|---|---|
| `--processor-path path` or `-processorpath path` | Processor JARs loaded via a dedicated compiler classpath | `META-INF/services/javax.annotation.processing.Processor` |
| `--processor-module-path path` | Processors distributed as modules | `provides javax.annotation.processing.Processor with ...` in the descriptor |
| `--module-path path` | Dependencies/modules of **the sources being compiled** | `requires` in the source module |
| `--class-path path` or `-cp` | Classpath dependencies of the sources being compiled | Regular classes/JARs; does not act as the processor path once a separate processor path is configured |

**Core point:** `--module-path` and `--processor-module-path` serve two different purposes. Putting a processor JAR on the application module path does not mean the compiler is guaranteed to run that processor.

Similarly, dependencies needed to compile annotation types must be visible to source compilation; the JAR executing the processor must be located by the compiler via the processor path or processor module path. The two dependency sets can overlap, but they are not the same.

## 6. Declaring a classpath-style processor JAR

If a processor is packaged in a traditional JAR, it can be registered via a service configuration file:

    META-INF/services/javax.annotation.processing.Processor

Contents:

    com.example.processor.GreetingProcessor

If there are multiple processors, list the fully qualified name of each processor on its own line.

Example compiling sources with a separate processor JAR:

    javac --processor-path libs/greeting-processor.jar
          -processor com.example.processor.GreetingProcessor
          -s build/generated
          -d build/classes
          src/com/example/app/*.java

The line breaks are for readability only; when running in a shell, place the command on one line or use the appropriate line-continuation character.

`-processor` explicitly specifies the processor to run, bypassing default processor discovery. If a valid `META-INF/services` file exists and the processor path is configured, `-processor` does not necessarily need to be specified; the tool can discover the processor via service configuration.

With a classpath JAR, the processor typically requires a **public no-argument constructor** so the compiler's ServiceLoader can instantiate it.

## 7. Declaring a processor as a named module

For a named module `com.example.processor`, the descriptor can be:

    module com.example.processor {
        requires java.compiler;

        provides javax.annotation.processing.Processor
            with com.example.processor.GreetingProcessor;
    }

Meaning:

- `requires java.compiler`: the processor uses the `javax.annotation.processing` and `javax.lang.model` APIs.
- `provides ... with ...`: registers the implementation of the `Processor` service.
- `GreetingProcessor` is the provider class in the module; for example, extending `AbstractProcessor`.

If the processor uses third-party libraries, supply those dependencies in the processor module path environment so the processor's module graph resolves.

Example compiler invocation for a named-module processor:

    javac --module-path libs
          --processor-module-path processor-mods
          --module-source-path src
          -d out
          -m com.example.app

In this command:

- `libs` holds the modules the application needs to compile sources.
- `processor-mods` holds the processor module and any dependencies needed by the processor.
- `src` is the module source layout.
- `-m com.example.app` specifies the source module to compile.

Do not confuse `provides javax.annotation.processing.Processor` in a **processor module** with `uses` or `provides` of business services that the application uses at runtime. A processor is a **compile-time** tool.

## 8. Important compiler arguments

| Argument | Purpose |
|---|---|
| `-processor p1,p2` | Runs the named list of processors instead of default discovery |
| `--processor-path path` | Specifies the classpath for processors |
| `--processor-module-path path` | Specifies the module path for processors |
| `-proc:none` | Disables annotation processing |
| `-proc:only` | Runs only annotation processing without the subsequent compilation step |
| `-proc:full` | Runs annotation processing and then proceeds with compilation |
| `-Akey=value` | Passes an option specifically to processors |
| `-s directory` | Output directory for Java sources generated by processors |
| `-d directory` | Output directory for class files generated by the compiler |
| `-XprintRounds` | Prints information about annotation processing rounds |
| `-XprintProcessorInfo` | Prints information about invoked processors and processed annotations |
| `--module-path path` | Dependency modules for source compilation |
| `--module-source-path path` | Layout of multiple source modules |
| `--release version` | Compiles against the API and class-file target of the specified Java version |

Options `-A` and `-processor` serve processors; `--module-path` and `--release` serve compilation as a whole. Grouping arguments correctly avoids passing an option meant for the application JVM instead of the compiler/JVM executing annotation processing.

## 9. JDK 23 and later: annotation processing is no longer implicitly enabled

An important change starting in **JDK 23** is that `javac` no longer automatically searches for and runs processors on the classpath when the compile command has no explicit annotation processing configuration.

Previously, a JAR accidentally containing a processor service file on the classpath could cause the processor to run even if the build did not intentionally enable it. With JDK 23 and later, configure it explicitly, for example in one of these ways:

    javac -proc:full ...

    javac --processor-path processor-libs ...

    javac --processor-module-path processor-mods ...

    javac -processor com.example.processor.GreetingProcessor ...

`-proc:full` requests both processing and compilation. Some older JDK lines supported only `-proc:none` or `-proc:only`; `-proc:full` support was added in specific updates.

For long-lived builds, it is best to **explicitly declare the trusted set of processors** and the processor path/module path rather than relying on implicit classpath scanning. This makes builds more reproducible and avoids running unintended processors.

When upgrading the JDK and generated classes suddenly disappear, first check whether annotation processing is still enabled rather than checking only whether application dependencies changed.

## 10. Passing -A parameters to processors

Processors can define custom options. For example, to configure a prefix for generated classes:

    javac --processor-path libs/greeting-processor.jar
          -Acodegen.prefix=Demo
          -d out
          src/com/example/app/*.java

Inside the processor:

    String prefix = processingEnv
            .getOptions()
            .getOrDefault("codegen.prefix", "Default");

Supported options should be declared:

    @SupportedOptions("codegen.prefix")
    public final class GreetingProcessor
            extends AbstractProcessor {
        // ...
    }

When `@SupportedAnnotationTypes` and `@SupportedOptions` are used, the names must match the actual annotations or options.

`-Acodegen.prefix=Demo` is forwarded by `javac` to the processor. It is not equivalent to:

    -Dcodegen.prefix=Demo

`-D` is a JVM system property when passed to the appropriate JVM; `-A` is the option interface of annotation processors.

## 11. Distinguishing arguments for javac vs. arguments for the compiler JVM

Not every module-related flag is passed at the same layer.

- `javac`'s `--module-path` specifies modules for the compiler to **compile sources**.
- `--processor-module-path` specifies modules for the compiler to **locate processors**.
- `-A...` configures processors.
- `-J...` passes an option to **the JVM running the javac tool** when invoking the `javac` command-line launcher.

This distinction is especially important if a legacy processor relies on internal APIs of `jdk.compiler`, such as packages starting with `com.sun.tools.javac`. Those APIs are not stable public compiler APIs.

If a tool truly must access an internal package from the compiler's unnamed module, a workaround might require a JVM flag like:

    -J--add-exports=jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED

This is only an example of **granting access to the JVM executing javac**, not a way to automatically open permissions for every compilation target module. For a processor in a named module, the target module must be identified accurately and may require different configuration.

Prefer updating processors to use standard `javax.annotation.processing` and `javax.lang.model`; do not depend long-term on internal `com.sun.tools.javac` APIs because they can change between JDK releases.

## 12. Which module do generated sources belong to?

When `javac` is compiling named module `com.example.app`, sources created by a processor for that module are processed by the compiler as part of that module's source compilation according to the output layout.

For example, the processor generates:

    package com.example.app.generated;

    public final class GreetingGenerated {
        public static String message() {
            return "Hello from processor";
        }
    }

If the generated class is used only **inside** `com.example.app`, package `com.example.app.generated` does not need to be exported.

If another module needs to call public APIs of the generated package directly, module `com.example.app` must export that package:

    module com.example.app {
        exports com.example.app.generated;
    }

Generating classes does not automatically add `exports`, `requires`, or `opens` to the module descriptor.

If the processor generates sources that depend on another library, `javac` needs to see that dependency on the source compilation's module path/classpath. Dependencies of the processor itself do not automatically become dependencies readable by the application module.

## 13. Generated sources and output files

Directories should be kept clearly separated:

    project/
      src/
      build/
        generated/
        classes/
      processor-libs/

- `src`: project-managed sources.
- `build/generated`: sources generated by annotation processing.
- `build/classes`: `.class` files after compilation.
- `processor-libs`: processor JARs and processor dependencies.

You can use:

    -s build/generated
    -d build/classes

Normally, developer-managed source files should not be overwritten by generated outputs. The build tool should configure the generated directory inside the build output tree, cleared by clean tasks, and distinct from the main source root.

If an IDE does not see generated classes during development, check whether annotation processing is enabled in the project and whether the IDE marks the generated source directory properly. `javac` succeeding does not guarantee every IDE immediately updates its generated source configuration.

## 14. Maven Compiler Plugin configuration

In Maven projects, processors are usually placed in dedicated `maven-compiler-plugin` configuration rather than declared only as runtime dependencies.

Example with a classpath-style processor JAR using `annotationProcessorPaths`:

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <annotationProcessorPaths>
          <path>
            <groupId>com.example</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>

The example above illustrates only the relevant configuration section; the project still needs a plugin version and appropriate JDK settings.

When explicit processor selection is required, the plugin can accept processor class names (depending on version). Do not assume merely adding a `greeting-processor` dependency in `dependencies` is enough, especially on JDK 23 and later.

For **modular annotation processors**, configuration depends on the Maven Compiler Plugin version. Some newer versions support dependency types or dedicated configuration for processors on the module path; choose the right type for the processor artifact. Do not put both `--processor-module-path` and `--processor-path` into the same configuration just because it is unclear which type the JAR belongs to.

When upgrading Maven/JDK and generated sources disappear, inspect the actual compiler command log and passed processor options rather than checking only whether the POM lists the processor artifact.

## 15. Gradle configuration

With the Gradle Java plugin, there is a dedicated dependency configuration for annotation processors:

    plugins {
        id 'java'
    }

    dependencies {
        implementation 'com.example:annotations-api:1.0.0'
        annotationProcessor 'com.example:greeting-processor:1.0.0'
    }

`implementation` supplies dependencies to application sources. `annotationProcessor` supplies the processor to the Java compilation task. Both may be necessary if sources use annotation types from one library while the processor is a separate artifact.

In test source sets, you may need:

    dependencies {
        testImplementation 'com.example:annotations-api:1.0.0'
        testAnnotationProcessor 'com.example:greeting-processor:1.0.0'
    }

If the project uses JPMS, module-path inference can be enabled for the Java plugin:

    java {
        modularity.inferModulePath = true
    }

However, module-path inference for the application does not automatically ensure every processor is configured on the processor module path. Check the Gradle version, plugins, and how the processor artifact is packaged.

When needing to pass `-A` to specific `JavaCompile` tasks:

    tasks.withType(JavaCompile).configureEach {
        options.compilerArgs += [
            '-Acodegen.prefix=Demo'
        ]
    }

Pass only arguments supported by the processor. Putting the processor JAR in `runtimeOnly` is not the normal way to trigger annotation processing during the compile task.

## 16. Unit tests and testAnnotationProcessor

Many projects use annotation processing not only in `src/main/java` but also in test fixtures and `src/test/java`. Since main compilation and test compilation are typically separate tasks, processor configurations can also be separate.

For example:

- Main sources use `annotationProcessor`.
- Test sources use `testAnnotationProcessor`.
- Generated sources for main and test typically go into separate output directories.
- A processor may need different module access permissions when compiling tests.
- The test JVM does not run annotation processors itself: processing normally happens when compiling test sources.

A useful verification test compiles a sample annotated source and asserts that the generated class appears in the output. Do not verify only that the processor JAR resolved as a dependency; verify that the processor was actually invoked.

## 17. Diagnosing a processor that does not run

When generated classes are missing, walk through in order:

1. **Check the JDK:** which JDK is used? On JDK 23+, is annotation processing explicitly enabled?
2. **Check the artifact:** is the processor JAR downloaded and on the processor path/module path?
3. **Check packaging style:** does the JAR use `META-INF/services` or is it a named module with `provides`?
4. **Check annotation types:** does `@SupportedAnnotationTypes` match the fully qualified annotation name?
5. **Check sources:** does the annotation actually appear on an element being compiled?
6. **Check rounds:** use `-XprintRounds` and `-XprintProcessorInfo` to see whether the processor was invoked.
7. **Check outputs:** which directory are generated sources written to, and are generated classes compiled and packaged?
8. **Check Filer errors:** is the processor creating duplicate files in a single compilation?
9. **Check module graphs:** are processor dependencies and application dependencies on their respective right paths?

Common messages:

| Symptom | Diagnostic direction |
|---|---|
| `Annotation processor ... not found` | Wrong class name in `-processor`, or JAR missing from processor path/module path |
| Generated class does not exist | Processing not enabled, annotation mismatch, or processor did not create the file |
| `FilerException: Attempt to recreate a file` | Processor created the same source/resource name twice in one compilation |
| `NoClassDefFoundError` inside processor | Processor's own dependency missing from processor path/module path |
| `package ... is not visible` | Source module lacks readability or the module owning the package does not export it |
| `IllegalAccessError` when processor uses internal APIs | JDK strong encapsulation or incompatible processor version |
| Builds in IDE yet fails in CI | JDK/toolchain/arguments/processor path mismatch between IDE and CI |

These errors belong to different layers. A generated class missing because the processor never ran will not be fixed by randomly adding `--add-opens` to source modules.

## 18. Common misconceptions

- **Assuming annotations and processors are the same thing.** Annotations declare metadata, while processors are compile-time programs that read those annotations.
- **Assuming a processor JAR on the runtime classpath is enough.** Processors must be present in the compilation environment and enabled.
- **Assuming `--module-path` is also `--processor-module-path`.** One path is for modules being compiled, the other is for processor modules.
- **Assuming `-proc:only` produces complete class files like normal compilation.** It runs only annotation processing without continuing to full compilation.
- **Assuming generated sources are automatically exported from a named module.** Generated packages remain governed by the module descriptor.
- **Assuming JDK 23+ still scans processors implicitly on the classpath like older releases.** Explicit processing configuration is required.
- **Assuming `-Akey=value` is a JVM system property.** `-A` supplies options to annotation processors.
- **Assuming `-J` and `--module-path` affect the same layer.** `-J` passes options to the JVM running the compiler tool.
- **Assuming a Maven/Gradle runtime dependency is enough for a processor to run.** Use configurations or plugin setups dedicated to processors.
- **Assuming a processor is always a named module.** Classpath processor JARs with `META-INF/services` remain a valid mechanism.

## Key takeaways

- Standard annotation processing APIs belong to the `java.compiler` module.
- A processor can be registered via `META-INF/services/javax.annotation.processing.Processor` or `provides javax.annotation.processing.Processor with ...` in a named processor module.
- `--processor-path` and `--processor-module-path` locate processors; `--module-path` is for source compilation modules.
- `-processor` selects processors explicitly; `-Akey=value` passes configuration; `-s` and `-d` control outputs.
- Starting with JDK 23, enable or configure annotation processing explicitly; `-proc:full` is one way to request processing followed by compilation.
- Maven and Gradle should separate processor dependencies from application runtime dependencies.
- When debugging, inspect processing rounds and outputs before tweaking module access flags.

A stable JPMS build distinguishes three layers: **source module graph**, **processor discovery**, and **JVM/compiler options**. When the processor path, service registration, and compiler arguments are set correctly, annotation processors operate consistently even when an application is split into multiple named modules.