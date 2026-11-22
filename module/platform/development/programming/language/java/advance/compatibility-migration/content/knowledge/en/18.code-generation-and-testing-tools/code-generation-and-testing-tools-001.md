# Annotation processors and activation mechanism changes across JDK versions

In the **Code Generation and Testing Tools** chapter of **Java Advance Compatibility Migration**, annotation processing is a frequent point of failure when upgrading the JDK: Java source code has not changed, dependencies still exist, and the compiler command may report no error about the annotations themselves, yet **source code previously generated during compilation disappears**.

A typical cause is that the build previously relied inadvertently on **javac automatically scanning the classpath to discover annotation processors**. Starting in **JDK 23**, without explicit annotation processing configuration, javac **no longer enables annotation processing implicitly** by default as before. JDK 21 and 22 already emitted notes warning about relying on implicit processing. Consequently, upgrading the compiler to a newer version can cause a module to lose generated code even while the application uses the exact same annotations.

This lesson covers the annotation processing mechanism, changes across JDK versions, how to configure **javac, Gradle, and Maven**, risks with Lombok/MapStruct/JPA metamodel and testing tools, how to handle annotation processors running on a newer JDK while emitting bytecode for an older target, and a safe migration strategy.

> **Scope:** **compile-time** annotation processing based on JSR 269 and the **javax.annotation.processing** package. This is not runtime reflection reading annotations, not every kind of source generator, and not synonymous with Java agents or custom compiler plugins.

## 1. Distinguishing annotations from annotation processors

An annotation is merely metadata defined in Java. Placing an annotation on a class **does not automatically guarantee** source code will be generated.

Example application-defined annotation:

~~~java
package example.annotation;

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

Consumer source:

~~~java
package example.app;

import example.annotation.GenerateGreeting;

@GenerateGreeting("Hello")
public class Greeter {
}
~~~

Without an enabled processor, the annotation remains valid and the **Greeter** class can still compile, yet a class like **GreeterGenerated** will not appear automatically.

An annotation processor is a **program that runs during compilation**. It can:

- Find supported annotations.
- Inspect program elements through the compiler's model.
- Create Java sources or resources using **Filer**.
- Report diagnostics through **Messager**.
- Work across multiple processing rounds when new sources are created.
- Cause the compiler to compile the generated sources as well.

A processor may generate mapper code, dependency injection wiring, JPA metamodels, builders, or metadata. However, **some tools such as Lombok also rely on deeper compiler internals and integration**; they must not be treated as interacting solely through pure JSR 269 APIs.

### 1.1. Two dependencies that are often separate

| Component | Role | Example |
|---|---|---|
| Annotation API | Lets source code reference the annotation | GenerateGreeting, Mapper, Entity |
| Annotation processor | Runs at compile time, generates code or metadata | GreetingProcessor, MapStruct processor |
| Generated source | Java source created by the processor | GreeterGenerated.java |
| Generated class | Bytecode produced by the compiler from original/generated source | GreeterGenerated.class |
| Runtime library | Library required by the program at runtime | Framework-dependent |
| Test annotation processor | Processor running for test sources | May be separate from main compilation |

With some tools, the annotation API and processor live in **the same JAR**; with others, they live in separate artifacts. Do not infer that adding a dependency to **implementation** or **compileOnly** naturally causes the processor to run on every JDK.

### 1.2. Why can errors surface late?

If main source contains:

~~~java
GreeterGenerated.sayHello();
~~~

when the processor does not run, compilation can fail with **cannot find symbol** immediately.

However, if the processor only generates service metadata or a JPA metamodel consumed by another module, the current module may build cleanly without generating the required artifact. Failures only surface when:

- Another module compiles.
- A framework looks up a generated implementation at runtime.
- Integration tests run.
- Package/CI builds check resources.
- A rarely used feature is invoked.

Therefore, checking only the exit code of one compile command is insufficient to conclude annotation processing works identically to the baseline.

## 2. The JSR 269 mechanism in javac

Standard APIs include classes/interfaces such as:

- **javax.annotation.processing.Processor**
- **javax.annotation.processing.AbstractProcessor**
- **javax.annotation.processing.RoundEnvironment**
- **javax.annotation.processing.ProcessingEnvironment**
- **javax.annotation.processing.Filer**
- **javax.annotation.processing.Messager**
- **javax.lang.model.element.\***
- **javax.lang.model.type.\***
- **javax.lang.model.util.\***

The package name remains **javax.annotation.processing** in the standard JDK API. It does not change to **jakarta.annotation.processing** merely because a project upgrades Spring Boot or Jakarta EE. Renaming JPA's namespace from **javax.persistence** to **jakarta.persistence** is a separate matter.

### 2.1. What steps does the compiler perform?

~~~text
Java source + classpath/module path
                 |
                 v
       javac loads processors
                 |
                 v
       Round 1: read annotations
                 |
                 +--> Processor generates Java source/resource
                 |
                 v
       Round 2: inspect new sources
                 |
                 +--> May generate more sources
                 |
                 v
       Subsequent rounds
                 |
                 v
       Final round / processing over
                 |
                 v
       Compile original and generated sources
                 |
                 v
       .class files + resources
~~~

Processors are invoked in **rounds**. If additional Java source is created in a round, the compiler can run another round so other processors can process the newly generated source.

Do not assume every processor executes exactly once. A processor that keeps state across rounds or writes duplicate files can trigger **FilerException** or produce non-deterministic output.

### 2.2. Processors inspect sources via the language model

A conforming processor typically works with **TypeElement**, **ExecutableElement**, **VariableElement**, and **TypeMirror** rather than loading the class currently being compiled directly via **Class.forName**.

Source under compilation may not yet have bytecode loadable by a class loader. Attempting to use runtime reflection to inspect annotations inside a processor can fail, especially before compilation finishes or when classpath/module paths differ.

### 2.3. Service discovery

A processor JAR may declare:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The file content is the fully qualified name of the processor class:

~~~text
example.processor.GreetingProcessor
~~~

When javac is configured to search for processors on the processor path/classpath without restricting to a specific processor list, it can use the service provider mechanism to discover processors.

However, **JDK 23 does not automatically scan a general classpath to enable annotation processing when no relevant config option is passed**. Having a JAR with a service file sit solely on the dependency classpath is not enough to guarantee the processor executes.

## 3. Key changes across JDK versions

### 3.1. Before JDK 23: implicit annotation processing

On many JDK versions prior to JDK 23, when no explicit annotation processing options were given, javac could automatically find processors on the classpath and execute them.

For example, a legacy project simply added a processor-containing JAR to the classpath:

~~~bash
javac -cp "deps/*" -d out src/example/app/Greeter.java
~~~

If a processor appeared on the classpath with appropriate metadata, older JDKs could run it even though the team **never wrote a separate processor declaration**.

That is an implicit dependency:

~~~text
Processor JAR happens to sit on classpath
                 |
                 v
Older javac auto-discovers it
                 |
                 v
Generated sources appear
~~~

The risk of this default is that dependency JARs may carry unintended processors; changing the dependency graph can silently change which processors execute.

### 3.2. JDK 21 and 22: transition warning notes

JDK 21 began emitting a **note** when implicit annotation processing occurred without explicit annotation-processing configuration. The goal was to warn ahead of time that this default could be disabled in a future release.

Do not "fix" it merely by suppressing the note with lint flags. Hiding the message does not mean the build is explicitly configured and will continue generating code on newer JDKs.

### 3.3. JDK 23: explicit configuration required

Starting in **JDK 23**, without options requesting/configuring annotation processing, javac **does not run processors** by default. To run them, provide an explicit activation mechanism such as:

- **-processor** naming the processor classes to run.
- **--processor-path** or **-processorpath**.
- **--processor-module-path** for modular processors.
- **-proc:full** to request both annotation processing and compilation.
- **-proc:only** to run annotation processing only.

Crucial takeaway: **placing a processor JAR on the ordinary classpath with no other annotation-processing configuration is no longer reliable starting in JDK 23**.

### 3.4. Summary table

| Tool / version | If processor is only on classpath with no APT config | Migration direction |
|---|---|---|
| JDK before 21 | Can be auto-discovered and run by default | Move to explicit declarations |
| JDK 21 | Can run, emitting a note on implicit processing | Do not merely suppress note; declare processor |
| JDK 22 | Implicit processing default in GA release; emits note | Prepare for JDK 23 change |
| JDK 23 and later | Does not auto-enable without APT config | Use explicit processor path/processor list |
| Build tool with own processor config | Depends on javac flags generated by the tool | Check actual compiler command/dependency graph |

**Historical note on JDK 22:** early-access builds experimented with changing the default; for real migration assessment, rely on GA release notes and the exact javac version in use rather than generalizing from an early-access experiment.

### 3.5. This changes javac's default, not removing JSR 269

JDK 23 **does not remove annotation processing**. The Processor API, processing rounds, and code generation tools remain intact. What changed is **the activation condition**.

Do not edit annotations across hundreds of source files when the root cause is simply that the build fails to place the processor on the right path.

## 4. javac options to remember

| Option | Role | Notes |
|---|---|---|
| **-processor** | Specifies FQCNs of processor classes to run | Skips default discovery to pick processors explicitly |
| **--processor-path** | Path holding processors and their dependencies | Also enables processing in javac where applicable |
| **-processorpath** | Equivalent processor-path flag spelling | Common in older build scripts |
| **--processor-module-path** | Searches for processors in modules | Requires modular-packaged/configured processors |
| **-proc:none** | Disables annotation processing | Useful to verify code independently of processors |
| **-proc:only** | Performs annotation processing only | Does not complete normal compilation |
| **-proc:full** | Runs annotation processing then compiles | Explicitly requests processing on newer JDKs |
| **-s directory** | Output directory for generated sources | Separate from class output directory |
| **-d directory** | Output directory for class files | Does not imply generated sources belong here |
| **-Akey=value** | Passes option to annotation processors | Key names are defined by each processor |
| **-XprintRounds** | Logs processing rounds | Useful for diagnostics |
| **-XprintProcessorInfo** | Logs processor/annotation processing info | Useful for diagnostics |

### 4.1. Prefer selecting explicit processors

Illustrative example:

~~~bash
javac ^
  -cp "lib/annotation-api.jar" ^
  -processorpath "lib/greeting-processor.jar" ^
  -processor example.processor.GreetingProcessor ^
  -s generated-src ^
  -d classes ^
  src/example/app/Greeter.java
~~~

The **^** character is the Windows cmd line-continuation character. On macOS/Linux, use **\\** or write on one line; path separators are **;** on Windows and typically **:** on Unix systems.

The example assumes the processor JAR is self-contained or all required processor dependencies are listed on the processor path. Missing processor dependencies can cause **NoClassDefFoundError** or processor loading failures during compilation.

Keep clear separation:

~~~text
Compile classpath:
  annotation-api.jar
  + types referenced by source

Processor path:
  greeting-processor.jar
  + dependencies of the processor itself
~~~

Both paths may share some JARs when needed, yet avoid blindly dumping all compile/runtime dependencies onto the processor path.

### 4.2. -proc:full preserves behavior, yet is not the best design

A transitional workaround:

~~~bash
javac -proc:full -cp "lib/*" -d classes src/example/app/Greeter.java
~~~

This requests annotation processing to work again in a way that can discover processors on the classpath.

However, when the goal is safe, reproducible builds, **scoping processors onto a processor path and/or listing processor names explicitly** is generally better. Using **-proc:full** with a broad classpath can accidentally trigger unwanted processors bundled in dependencies.

### 4.3. When is -proc:only used?

~~~bash
javac -proc:only \
  -processorpath "lib/greeting-processor.jar" \
  -processor example.processor.GreetingProcessor \
  -s generated-src \
  -cp "lib/annotation-api.jar" \
  src/example/app/Greeter.java
~~~

This example targets a Unix shell. It performs **annotation processing only**, rather than compiling complete class files like **-proc:full**.

It can separate a codegen step in specialized workflows, yet requires managing source/generated directories, processor ordering, and a subsequent compile step. Do not switch entire builds to **-proc:only** expecting runnable artifacts directly.

### 4.4. --release does not pick the JDK running the processor

Example:

~~~bash
javac --release 17 \
  -processorpath "lib/processor.jar" \
  -processor example.processor.GreetingProcessor \
  -d classes \
  src/example/app/Greeter.java
~~~

If this command runs using **JDK 23's javac**, the annotation processor executes inside the JDK 23 compiler environment while **--release 17** governs the language/API target and generated class files for the application sources.

This means:

- The processor must be compatible with the JDK running javac.
- Generated Java source must conform to the target release.
- Application runtime dependencies must match the target release.
- If a processor emits bytecode directly rather than only source, control the class-file version and bytecode tools involved.

Do not infer that **--release 17** somehow makes Lombok, MapStruct, or a legacy processor "run on JDK 17".

## 5. Example of building a custom annotation processor

A simple processor makes activation boundaries concrete.

### 5.1. Annotation API

File **example/annotation/GenerateGreeting.java**:

~~~java
package example.annotation;

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

### 5.2. Processor

File **example/processor/GreetingProcessor.java**:

~~~java
package example.processor;

import example.annotation.GenerateGreeting;

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

@SupportedAnnotationTypes("example.annotation.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String packageName =
                processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();

            String generatedName =
                type.getSimpleName() + "Generated";

            String qualifiedName = packageName.isEmpty()
                ? generatedName
                : packageName + "." + generatedName;

            String value =
                type.getAnnotation(GenerateGreeting.class).value();

            try {
                JavaFileObject file =
                    processingEnv.getFiler()
                        .createSourceFile(qualifiedName, type);

                try (Writer out = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        out.write("package " + packageName + ";\\n");
                    }
                    out.write(
                        "public final class " + generatedName + " {\\n"
                    );
                    out.write(
                        "  private " + generatedName + "() {}\\n"
                    );
                    out.write(
                        "  public static String text() { return \\\""
                        + escapeJava(value) + "\\\"; }\\n"
                    );
                    out.write("}\\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate " + qualifiedName + ": " + ex,
                    element
                );
            }
        }
        return true;
    }

    private static String escapeJava(String input) {
        return input
            .replace("\\\\", "\\\\\\\\")
            .replace("\\\"", "\\\\\\\"");
    }
}
~~~

This example demonstrates the JSR 269 API; production generators should use a source-generation library with full escaping handling, especially for newlines/control characters and valid Java syntax. Also avoid creating duplicate files across multiple rounds.

**Key takeaway:** an annotation processor runs during compilation of the consumer's source; it is not a class the application calls in production.

### 5.3. Service registration

To allow automatic discovery on the **processor path**, package the file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Content:

~~~text
example.processor.GreetingProcessor
~~~

If using **-processor example.processor.GreetingProcessor**, the processor class is named explicitly; service discovery is no longer the sole path to finding it.

### 5.4. Consumer source

~~~java
package example.app;

import example.annotation.GenerateGreeting;

@GenerateGreeting("Hello migration")
public class Greeter {
    public static void main(String[] args) {
        System.out.println(GreeterGenerated.text());
    }
}
~~~

When the processor actually runs, it produces **GreeterGenerated.java**. The compiler can then compile that source within the same compilation pass.

When the processor is disabled, **GreeterGenerated** does not exist in a clean build; consumer code referencing it fails with symbol not found.

### 5.5. Why is a clean build necessary?

If the output directory retains **GreeterGenerated.class** from a previous build, compilation or running the app may still appear to succeed even when the processor did not run. This hides errors on developer machines while exposing them on a fresh CI checkout.

Distinguish among:

- **Output generated by the current processor.**
- **Stale files left from an old build.**
- **Intentionally committed generated sources.**
- **Classes coming from another dependency JAR.**

A sound migration verifies the provenance of generated code rather than merely finding a file sitting in a directory.

## 6. Gradle: declaring annotationProcessor explicitly

With Gradle's Java/Java Library plugin, the **annotationProcessor** configuration places processors onto the processor path.

Groovy DSL example:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    // Annotation API referenced in source
    compileOnly 'org.projectlombok:lombok:1.18.34'

    // Processor running at compile time
    annotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

The Lombok version is a **syntax illustration**, not a blanket recommendation for every JDK. When upgrading JDKs, choose a processor version explicitly documented by the vendor to support **the JDK running the compiler**.

### 6.1. implementation differs from annotationProcessor

~~~groovy
dependencies {
    implementation 'example:annotation-api:1.0'

    annotationProcessor 'example:greeting-processor:1.0'
}
~~~

**implementation** supplies dependencies for compiling/running application code in Gradle's model. **annotationProcessor** is where Gradle resolves processors to execute.

Putting only:

~~~groovy
dependencies {
    implementation 'example:greeting-processor:1.0'
}
~~~

is not a reliable way to make Gradle run a processor. Build tools actively separate compile classpaths from processor paths, and relying on implicit discovery also hits javac's default change in JDK 23.

### 6.2. Main and test are two separate compilations

A project may also need annotation processing when compiling **src/test/java**:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'

    testCompileOnly 'org.projectlombok:lombok:1.18.34'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.34'
}
~~~

Configuring only **annotationProcessor** can leave test sources that directly use annotations without a processor during `compileTestJava`, depending on dependencies and setup.

Ask separately:

- Is the processor needed for production source?
- Is the processor needed for test source?
- How does test source use the annotation API?
- Which source set consumes the generated code?

### 6.3. Do not hardcode generated directories and compile twice

Gradle manages annotation-processing generated sources through compile tasks. Manually creating a custom source-generation task and wiring its output into source sets improperly can cause:

- Duplicate classes.
- Wrong compilation ordering.
- Stale generated files.
- Missing declared inputs/outputs breaking incremental builds.
- Non-deterministic build cache outputs.

Prefer Gradle's built-in annotation-processing support. If a custom task is necessary, declare ownership and the task dependency graph explicitly.

### 6.4. Use Java toolchains to know which javac actually runs

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(23)
    }
}
~~~

The toolchain controls the compiler JDK for the corresponding Java task; it does not automatically ensure every plugin/process in the build uses the same JDK. Identify the Gradle daemon, compiler, and test executor JVMs individually when failures happen in a specific stage.

**Do not use sourceCompatibility/targetCompatibility or --release to conclude a processor runs on an older JDK.** They describe target code, not the compiler implementation.

### 6.5. Diagnosing annotation processing in Gradle

When inspecting a real project, you can run:

~~~bash
./gradlew clean compileJava --info
./gradlew compileTestJava --info
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration testAnnotationProcessor
~~~

In this lesson, these commands serve as practical guidance. In a real migration, check that your Gradle wrapper/version supports the target JDK before running them.

Diagnostic compiler flags can be added temporarily:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-XprintRounds',
        '-XprintProcessorInfo'
    ]
}
~~~

Use these arguments selectively; no need to keep overly verbose logs on every CI build if they add noise.

## 7. Maven 3: compiler plugin and annotationProcessorPaths

With Maven 3 and Maven Compiler Plugin 3.x, the standard configuration mechanism is **annotationProcessorPaths**.

Example:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.1</version>
      <configuration>
        <release>21</release>
        <annotationProcessorPaths>
          <path>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct-processor</artifactId>
            <version>1.6.3</version>
          </path>
        </annotationProcessorPaths>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Versions in examples merely illustrate structure. In practice, align versions across the annotation API, processor, Maven Compiler Plugin, JDK, and target framework per vendor documentation.

Typically, the source module still needs the **org.mapstruct:mapstruct** dependency to reference the **@Mapper** annotation. The processor artifact alone does not replace the annotation API.

### 7.1. Specifying annotationProcessors explicitly when needed

~~~xml
<configuration>
  <annotationProcessors>
    <annotationProcessor>
      org.mapstruct.ap.MappingProcessor
    </annotationProcessor>
  </annotationProcessors>
</configuration>
~~~

Specific configuration must match the real processor artifact; if an application uses multiple processors, list every processor that must run or use an explicitly managed processor path.

One processor may depend on another or rely on specific ordering/coordination. Do not omit a processor carelessly just because its annotation does not appear directly in source.

### 7.2. proc=full is a transitional measure

Versions of Maven Compiler Plugin supporting the **proc** setting can pass **-proc:full**:

~~~xml
<configuration>
  <proc>full</proc>
</configuration>
~~~

This can preserve behavior on JDK 23 while a legacy project has not yet separated processors. However, it does not guarantee only trusted processors run.

A more sustainable direction is declaring explicit **annotationProcessorPaths** and/or processor lists, then reviewing transitive processor dependencies.

### 7.3. Note on testCompile

Maven Compiler Plugin also compiles test sources; processor paths and dependencies for tests must be verified separately based on plugin version and module layout. Do not conclude test annotation processing works merely because **mvn compile** passes.

## 8. Maven 4 and Compiler Plugin 4.x

With Maven 4 and Maven Compiler Plugin 4.x, official docs introduce declaring processors using dependencies with appropriate **type** values, such as:

- **processor**
- **classpath-processor**
- **modular-processor**

Structural example:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct</artifactId>
    <version>1.6.3</version>
  </dependency>
  <dependency>
    <groupId>org.mapstruct</groupId>
    <artifactId>mapstruct-processor</artifactId>
    <version>1.6.3</version>
    <type>classpath-processor</type>
  </dependency>
</dependencies>
~~~

Match declarations to the exact plugin and JDK in use. **annotationProcessorPaths** reflects Maven Compiler Plugin 3.x guidance and was superseded by dependency types in 4.x guidance.

Do not copy Maven 4 config into a Maven 3 project assuming processor types work identically. Verify installed versions before migrating.

### 8.1. Why does Maven distinguish classpath processors from modular processors?

Processors packaged and discovered via the module path have different requirements from traditional classpath processor JARs. Choosing the wrong path type can lead to:

- Processors not being found.
- Service provider metadata mismatches.
- Processor dependencies failing to resolve in the module graph.
- Processors lacking access to compiler APIs or required modules.

Use **modular-processor** only when the processor artifact is genuinely packaged to run under modular rules. Do not guess from artifact names.

## 9. When a module has module-info.java

JPMS affects both compile-time dependency declarations and how processors are discovered.

Illustrative application module:

~~~java
module example.app {
    requires example.annotation.api;
}
~~~

Meanwhile, the processor can live on the **processor path** without needing to be declared as a runtime dependency in the application's module-info. If a processor is authored as a named module, it may need **provides javax.annotation.processing.Processor with ...** in its descriptor and be resolved on **--processor-module-path**.

Illustrative processor module:

~~~java
module example.greeting.processor {
    requires java.compiler;
    requires example.annotation.api;

    provides javax.annotation.processing.Processor
        with example.processor.GreetingProcessor;
}
~~~

This is an illustrative model; a real processor must be packaged with suitable dependencies and descriptors. **requires java.compiler** supplies the standard JSR 269 APIs.

### 9.1. JSR 269 APIs are not jdk.compiler internals

**javax.annotation.processing** and most language-model APIs belong to the **java.compiler** module, which is standard API.

Certain advanced tools rely instead on **com.sun.tools.javac.\*** inside **jdk.compiler**'s implementation. That crosses a different boundary:

- Newer JDKs may change internal compiler ASTs.
- Strong encapsulation can block access to implementation internals.
- **--add-exports** and **--add-opens** sometimes appear as workarounds in vendor notes.
- A workaround for one JDK is not guaranteed to work on the next JDK.

Do not reflexively open every **jdk.compiler** package when a processor fails. Identify the processor, its version, and official JDK support level first.

### 9.2. A modular build requires checking both module graphs

Two distinct graphs can exist:

1. The module graph of the **application source** being compiled.
2. The module/path configuration used to **load the processor** and its dependencies.

A valid app module config does not guarantee the processor is located properly. Conversely, a running processor does not guarantee generated source fits the app's module-info.

## 10. Lombok: a special case when upgrading the JDK

Lombok uses annotations like **@Getter**, **@Builder**, and **@RequiredArgsConstructor** to transform code during compilation. Although hooked into annotation processing, Lombok integrates far deeper into compiler internals than ordinary model/Filer processors.

Example:

~~~java
import lombok.Getter;

@Getter
public class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }
}
~~~

When upgrading the JDK, older Lombok versions may:

- Fail to load an internal compiler type.
- Fail because javac AST internals changed.
- Hit access errors into the **jdk.compiler** module.
- Fail to generate getters, builders, or constructors as before.
- Work in the IDE while failing under the CLI compiler.
- Work with an older compiler JDK yet fail on a newer JDK despite keeping **--release** fixed.

### 10.1. Resolution approach

1. Record the compiler JDK, Gradle/Maven, and Lombok versions.
2. Upgrade Lombok to a release officially documented to support the target JDK.
3. Declare Lombok on the appropriate processor path.
4. If test sources use Lombok, configure test annotation processing too.
5. Run a clean rebuild to eliminate old class files/generated outputs.
6. Check IDE plugin/import settings separately if the IDE runs a different compiler.
7. Do not treat **--add-opens** workarounds as a long-term fix.

Gradle example:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:JDK_SUPPORTED_VERSION'
    annotationProcessor 'org.projectlombok:lombok:JDK_SUPPORTED_VERSION'

    testCompileOnly 'org.projectlombok:lombok:JDK_SUPPORTED_VERSION'
    testAnnotationProcessor 'org.projectlombok:lombok:JDK_SUPPORTED_VERSION'
}
~~~

**JDK_SUPPORTED_VERSION** is a placeholder that must be replaced with a real release. Never leave placeholders in a production build.

## 11. MapStruct: generated mappers and processor paths

MapStruct typically involves:

- **mapstruct**: annotation API and any required runtime integration.
- **mapstruct-processor**: component generating implementations at compile time.

Example:

~~~java
import org.mapstruct.Mapper;

@Mapper
public interface CustomerMapper {
    CustomerDto toDto(CustomerEntity entity);
}
~~~

The processor can generate a class such as **CustomerMapperImpl**. If the processor fails to run:

- The source interface still compiles because the annotation API is present.
- Generated implementations are missing in clean builds.
- Compile/test/runtime fail due to missing implementations where the framework expects mappers.
- CI may fail differently from local machines if local retains generated files.

### 11.1. Gradle configuration

~~~groovy
dependencies {
    implementation 'org.mapstruct:mapstruct:SELECTED_VERSION'
    annotationProcessor 'org.mapstruct:mapstruct-processor:SELECTED_VERSION'
}
~~~

The crucial point is placing the processor under **annotationProcessor**, not solely under **implementation**.

### 11.2. Combining Lombok and MapStruct

A module using both Lombok and MapStruct must coordinate how both tools see Lombok-generated/transformed types. Depending on versions, a vendor-recommended integration binding artifact may be needed.

Do not fix issues by shuffling dependency order randomly until compilation succeeds. Identify supported versions of Lombok, MapStruct, and binding artifacts, then declare processor dependencies explicitly.

### 11.3. Generated source and contract

Generated mapper implementations must be treated as build outputs. Do not let committed legacy generated code or stale build directories mask new failures. When checking mapping behavior across releases, compare mapper behavior on sample data rather than just checking that a **MapperImpl** filename exists.

## 12. JPA metamodel, QueryDSL, and framework codegen

Annotation processing can generate types supporting type-safe queries.

JPA Criteria metamodel example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class CustomerEntity {
    @Id
    private Long id;

    private String name;
}
~~~

A JPA metamodel processor can generate classes such as **CustomerEntity_**. Other code may use:

~~~java
root.get(CustomerEntity_.name);
~~~

If the processor does not run, metamodel types are not generated and compilation can fail.

### 12.1. Switching javax to jakarta differs from JDK 23 changes

During Java EE → Jakarta EE migrations, annotation namespaces can switch from:

~~~text
javax.persistence.Entity
~~~

to:

~~~text
jakarta.persistence.Entity
~~~

An older processor supporting only javax annotations may ignore jakarta annotations even while actively running. Distinguish two questions:

1. Is the processor **being activated**?
2. Does the processor **support the current annotation namespace and framework version**?

Adding **-proc:full** does not automatically make an older processor recognize **jakarta.persistence.Entity**.

### 12.2. QueryDSL and other processors

A project may use QueryDSL, AutoValue, Dagger, Immutables, Hibernate Processor, or internal tools. For each tool, document:

- Annotation API artifact.
- Processor artifact.
- Processor class or service registration.
- Java/JDK compatibility.
- Output type and output location.
- Transitive dependencies.
- Test source requirements.
- Runtime library, if any.

Do not apply a blanket assumption that "every processor works like MapStruct"; some generate sources, some generate resources, some emit compile checks, and some hook compiler internals.

## 13. Annotation processors and testing tools

Processors running during **compileJava** and **compileTestJava** (or equivalent tasks) can differ.

### 13.1. Why do tests fail after migration?

Examples:

- Main sources declare the processor, while test sources omit **testAnnotationProcessor**.
- Test fixtures require generated helper classes.
- Test-source processors were disabled on JDK 23 due to implicit setup.
- A test library relies on annotations to generate metadata.
- The test runner uses a different JDK from the compiler.
- Local tests rely on stale generated sources absent in CI.

Pinpoint the exact stage:

~~~text
compileJava
    |
    v
Generated main sources/classes
    |
    v
compileTestJava
    |
    v
Generated test sources/classes
    |
    v
Test execution
~~~

If the failure occurs in **compileTestJava**, do not jump straight to modifying **test runtimeClasspath**. Inspect the test source set's compile classpath and processor path.

### 13.2. Annotation processors are not the JUnit test engine

JUnit Jupiter uses **@Test** to discover and run tests at runtime. Using **@Test** does not mean an application needs a JSR 269 annotation processor for JUnit.

Likewise, Spring annotations such as **@Component** are typically processed by framework/runtime mechanisms; not every annotation triggers compile-time codegen.

Identify which tools truly act as compile-time processors before adding dependencies to the `annotationProcessor` path.

### 13.3. Do not confuse with Kotlin KAPT/KSP

In polyglot projects containing Kotlin:

- **kapt** runs many Java annotation processors against Kotlin via its own mechanism.
- **KSP** is a processor ecosystem distinct from pure Java JSR 269 APIs.
- Kotlin/KSP/KAPT plugins and versions carry separate compatibility matrices.

Adding Java **annotationProcessor** config does not automatically configure Kotlin processors. When Kotlin modules exist, examine each compilation pipeline individually.

## 14. Compiler runtime, target release, and toolchains

A migration typically involves three different numbers:

| Component | Example | Impact |
|---|---|---|
| JDK running javac | 23 | Compiler API, processor runtime, APT default behavior |
| Target release | 17 | Source rules, Java SE APIs, and class-file target |
| Application runtime JDK | 17 or 21 | Execution of generated bytecode/dependencies |

Example:

~~~text
JDK 23 javac
     |
     +--> Processor runs on JDK 23
     |
     +--> --release 17
              |
              v
     Generated source + bytecode target 17
              |
              v
     Application runtime 17
~~~

You cannot run a JDK-17-only processor expecting it to "see JDK 17" simply because the source target is release 17. Processors are loaded by the compiler and must be compatible with the compiler runtime.

### 14.1. Generated source may use overly new APIs

If a processor emits:

~~~java
var text = "hello";
~~~

or calls an API existing only on JDKs newer than the target, the compiler may reject it under the matching **--release** flag. If a processor writes bytecode directly, limits also depend on the bytecode library and class-file version emitted.

A processor capable of running on a newer JDK yet emitting code calling overly new Java APIs **can still break migrations targeting older runtimes**.

### 14.2. Distinguish build-tool JDK from compiler JDK

The Gradle daemon, Maven process, forked javac, Gradle toolchain, and test JVM are not always the same JDK. When debugging annotation processor errors, determine:

- **Which javac version is executing?**
- **Which processor JAR is being loaded?**
- **Which module/classpath holds the processor?**
- **Which release target is configured?**
- **Which JDK compiles and runs the output?**

Do not glance at **java -version** in another terminal and conclude CI uses the matching compiler.

## 15. Supply-chain security: processors are code executed at build time

A major motivation for JDK 23's default change is reducing unintended code execution during builds. Annotation processors are not harmless metadata: they are executable code loaded and invoked by javac inside the build environment.

If an untrusted dependency contains a processor service registration, prior implicit discovery could execute that processor without the developer explicitly opting in.

Potential risks include:

- Reading build environment variables.
- Accessing workspace files.
- Making network requests if the environment permits.
- Generating or altering code incorrectly.
- Slowing builds or introducing flaky failures.
- Varying behavior based on CI environment.
- Relying on unexpected compiler internals or runtime permissions.

Recommended policies include:

1. Declare only vetted processors explicitly.
2. Pin dependency versions and trusted sources.
3. Audit transitive processor dependencies.
4. Keep processor paths separate from runtime dependencies.
5. Run CI with least privilege and protect secrets.
6. Apply dependency verification/SBOMs as appropriate.
7. Avoid scanning broad classpaths with **-proc:full** when specific processors can be named.
8. Monitor changes in processor service metadata.

**A passing compile does not prove a processor JAR is safe.** Supply-chain integrity is independent of generated-code correctness.

## 16. Diagnosing errors when upgrading the JDK

### 16.1. Typical symptoms

| Symptom | Common cause | Where to investigate |
|---|---|---|
| **cannot find symbol** for generated type | Processor did not run or output missing | Processor path, javac options |
| **No implementation was created** | Generated implementation missing | MapStruct/DI processor |
| **cannot find symbol getX()/builder()** | Lombok did not execute | Lombok/JDK support, processor setup |
| JPA metamodel **Entity_** missing | JPA processor inactive or wrong namespace | jakarta/javax, processor version |
| **Processor ... not found** | Processor class absent from chosen path | -processor, processor path, service metadata |
| **NoClassDefFoundError** inside processor | Missing dependency of the processor itself | Processor dependency graph |
| **IllegalAccessError** into **jdk.compiler** internals | Processor uses incompatible internal compiler APIs | Lombok/compiler version |
| **InaccessibleObjectException** | Strong encapsulation blocks reflective access | Stack trace, caller module |
| **NoSuchFieldError** from javac AST | Older processor depends on changed compiler internals | Vendor/JDK support |
| **UnsupportedClassVersionError** | Processor or dependency compiled with newer JDK than compiler JVM | Class-file version, toolchain |
| **FilerException** | Processor tries creating duplicate file | Output ownership, processing rounds |
| Processor runs in IDE yet fails in CI | IDE and CLI compiler/build paths differ | Repro via CLI clean build |
| Generated source exists locally yet missing in CI | Uncleaned old output | Clean build, provenance |
| Compiles yet fails at runtime | Missing generated metadata/resources or mapping bug | Contract/integration tests |

A single error can have multiple causes. **cannot find symbol** alone does not prove JDK 23 is at fault; verify whether the processor ran and produced output.

### 16.2. Triage workflow

1. Capture complete logs of the failing **compile**.
2. Record actual compiler JDK vendor and version.
3. Record Gradle/Maven plugin and processor versions.
4. Check compiler flags for **-processor**, **--processor-path**, **--processor-module-path**, or **-proc:full**.
5. Verify the processor class and transitive dependencies actually appear on that path.
6. When helpful, turn on **-XprintRounds** and **-XprintProcessorInfo**.
7. Inspect generated source directories after a clean build.
8. Check **source/API target** and runtime JDK.
9. If the processor ran without producing output, inspect annotation namespaces, supported source versions, and diagnostics.
10. After fixing, run integration/consumer tests relying on generated artifacts.

Avoid sprinkling **--add-opens** flags before confirming whether the fault lies in processor activation, discovery, or compiler internals.

### 16.3. Distinguishing "processor not found" from "processor matched zero annotations"

Two distinct states:

~~~text
A. javac does not load GreetingProcessor
   -> No processing rounds from that processor

B. javac loaded GreetingProcessor
   -> Yet getElementsAnnotatedWith(...) returns empty
   -> Possibly mismatched annotation or different target/namespace
~~~

If scenario B occurs, re-adding the processor dependency will not fix it. Inspect **SupportedAnnotationTypes**, annotations in source, module layout, and framework versions.

### 16.4. Diagnosing via clean builds

To avoid stale generated files, verify against a clean output directory. In real projects, use your build tool's standard clean/build commands in a controlled environment.

Do not manually delete entire workspaces or human-owned files. Generated directories should belong to the build tool with clear ownership before cleaning.

## 17. Incremental compilation and the build cache

Annotation processors can affect incremental builds:

- **Isolating** processors derive output from individual inputs.
- **Aggregating** processors combine information across multiple inputs.
- Processors that omit proper input tracking can force Gradle to re-run more work.
- Non-deterministic processor outputs (timestamps, randomness, unstable ordering) trigger cache misses or irreproducible builds.
- Build caches can mask missing processor execution in one environment by restoring cached outputs from another.

A migration should verify:

- Clean builds generate expected outputs.
- Incremental builds after editing annotations refresh outputs.
- Removing annotations clears stale outputs.
- Identical inputs/settings yield consistent results locally and in CI.
- No processor writes to directories outside build-tool control.
- Generated files are not unintentionally overwritten by source control or other generators.

Do not "solve" issues by disabling incremental compilation wholesale without evidence; it slows builds while leaving broken processor paths unfixed.

## 18. Migration plan to JDK 23 and later

### Phase A — Inventory

List processors per module:

| Module | Processor | Annotation API | Output | Test source? | JDK support |
|---|---|---|---|---|---|
| api | MapStruct | mapstruct | MapperImpl | Yes/No | Per vendor |
| persistence | Hibernate metamodel | jakarta.persistence | Entity_ | Yes/No | Per vendor |
| domain | Lombok | lombok | Compiler-generated members | Yes/No | Per vendor |
| plugin | Custom processor | annotation-api | Java source/resources | Yes/No | Internal |

Rows above are illustrative rather than asserting what any particular module uses.

### Phase B — Separate dependencies

- Identify annotation APIs required at compile time.
- Identify processor JARs and transitive dependencies.
- Place processors on official processor paths/configurations.
- Stop relying on processors sitting incidentally on implementation/runtime classpaths.
- Pin versions per vendor support policies.
- Record main vs. test compilation needs.

### Phase C — Audit compiler settings

- Actual compiler JDK.
- --release/source/target.
- -processor, --processor-path, --processor-module-path, or -proc.
- Module/classpath layout.
- Maven/Gradle compiler plugin versions.
- CI and IDE settings.

### Phase D — Rebuild and verify generated outputs

- Clean build from baseline artifacts/sources.
- Observe processor rounds if needed.
- Verify generated sources/classes/resources exist.
- Verify generated types compile against target release.
- Run representative consumer/integration tests.
- Confirm test annotation processing where test sources use it.
- Record logs, versions, and checksums/evidence.

### Phase E — Cutover

- Upgrade the compiler JDK to target.
- Keep processor declarations explicit.
- Monitor build failures and runtime behavior.
- Remove temporary workarounds once unnecessary.
- Update templates/build conventions so new modules do not reintroduce implicit discovery.
- Ensure build tool and processor versions stay aligned across environments.

## 19. Recommended test matrix

| Case | Compile JDK | APT config | Expectation |
|---|---|---|---|
| Baseline | JDK 21 | Implicit classpath discovery | May run yet emits note |
| Transition | JDK 21 | Explicit processor path | Stable generated output |
| Target | JDK 23+ | No APT config | Processors do not auto-activate |
| Target | JDK 23+ | Explicit processor path/name | Processor runs if compatible |
| Target | JDK 23+ | -proc:none | No APT output generated |
| Target | JDK 23+ | -proc:only | Processing output only, incomplete compile |
| Target | JDK 23+ | -proc:full | Processing + compile via allowed discovery |
| Cross-target | JDK 23+, --release 17 | Explicit processor config | Generated code conforms to Java 17 |
| Test source | Target JDK | Test processor path | Generated test sources created |
| IDE | IDE compiler | IDE processing enabled | Output matches CLI |
| Clean CI | Target JDK | Pinned versions | No reliance on stale artifacts |

The goal is not running every cell for every module; pick cases matching real processors and support policies.

### 19.1. Acceptance criteria should name concrete artifacts

MapStruct example:

~~~text
Given: CustomerMapper annotated with @Mapper
When: clean compile on target JDK
Then:
  - Selected MapStruct processor was loaded
  - CustomerMapperImpl was generated
  - Generated implementation compiled
  - Mapper behavior test passed
  - No dependency on stale generated files
~~~

JPA metamodel example:

~~~text
Given: CustomerEntity with JPA annotations
When: clean compile on target JDK
Then:
  - Processor recognizes the jakarta/javax namespace in use
  - CustomerEntity_ source/class generated
  - Criteria API consumer compiles
~~~

Lombok example:

~~~text
Given: @Getter / @Builder in source
When: clean compile on target JDK
Then:
  - Lombok version supports the compiler
  - Expected member access in consumer compiles
  - Test source using Lombok also compiles
~~~

These criteria help verify post-migration outcomes; they do not replace application-specific test suites.

## 20. Common mistakes

### 20.1. Adding the dependency only to implementation

Having a dependency on compile/runtime classpath does not ensure the processor executes.

**Solution:** use **annotationProcessor** in Gradle or the appropriate processor path/dependency type for your Maven version.

### 20.2. Merely suppressing the JDK 21 note

Hiding the note does not alter activation rules. JDK 23 can still skip the processor.

**Solution:** configure APT explicitly.

### 20.3. Using -proc:full with a broad classpath and calling it done

It preserves legacy behavior yet may trigger unintended processors.

**Solution:** restrict processor paths and trusted processor lists.

### 20.4. Assuming --release 17 runs processors on JDK 17

Processors run inside the selected compiler environment, not the target runtime.

**Solution:** verify compiler JDK, processor compatibility, and generated-code target separately.

### 20.5. Failing to separate the test processor path

compileJava succeeds while compileTestJava lacks its processor.

**Solution:** configure main and test source sets individually.

### 20.6. Leaving generated files from previous builds

Outputs from earlier compilations can hide that JDK 23 did not invoke the processor.

**Solution:** run clean builds with provenance and test from fresh checkouts.

### 20.7. Confusing JDK 23 changes with javax → jakarta errors

The processor may run yet fail to recognize the newer framework annotation namespace.

**Solution:** check annotation namespaces and vendor processor versions.

### 20.8. Adding --add-opens indiscriminately

A processor missing activation cannot be fixed by opening modules. For Lombok/compiler internals, workarounds can be JDK-specific and fragile.

**Solution:** diagnose the root error and upgrade the processor appropriately.

### 20.9. Changing toolchains without reviewing build plugins

Older Gradle/Maven plugins may lack full support for a newer compiler JDK.

**Solution:** verify the compatibility matrix across compiler plugins, processors, and JDKs.

### 20.10. Mistaking JUnit/Spring annotations for annotation processing

Not every annotation triggers a compile-time processor.

**Solution:** confirm whether a real JSR 269 processor exists before adding dependencies.

### 20.11. Generating sources into human-owned source directories

Mixes generated code with hand-maintained code, creating stale files and complicating rollbacks.

**Solution:** use build-owned generated output directories with explicit ownership and cleaning rules.

### 20.12. Neglecting processor supply-chain controls

Processors execute code during builds with potential access to workspaces and CI secrets.

**Solution:** pin artifacts, verify dependencies, and enable only required processors.

## 21. Checklist before concluding migration succeeds

### Inventory

- [ ] Listed processors by module and source set.
- [ ] Separated annotation APIs from processor artifacts.
- [ ] Verified the actual compiler JDK version in use.
- [ ] Recorded Gradle/Maven Compiler Plugin versions.
- [ ] Identified whether outputs are sources, classes, or resources.
- [ ] Audited internal processors and any using javac internals.

### Configuration

- [ ] Processors declared explicitly on appropriate paths.
- [ ] No reliance on implicit classpath discovery on JDK 23+.
- [ ] Test annotation processing configured where needed.
- [ ] Target release and compiler JDK verified independently.
- [ ] Module path / processor module path aligned if using JPMS.
- [ ] Processor dependencies pinned and sourced under control.
- [ ] JDK internals not opened merely to mask missing activation.

### Verification

- [ ] Clean compiles produce all expected generated files.
- [ ] No dependence on stale outputs from previous builds.
- [ ] Generated sources compile against target release.
- [ ] Representative consumer/integration tests pass.
- [ ] Both main and test source sets verified.
- [ ] CI and IDE configurations are reproducible.
- [ ] Logs/diagnostics confirm which processors actually loaded.
- [ ] No unintended behavioral changes in generated code.
- [ ] Rollback plan or fallback compiler/processor versions available if needed.

### Security and operations

- [ ] Only intentional processors are permitted to execute.
- [ ] Artifacts and transitive dependencies verified.
- [ ] CI secrets and build environment permissions locked down.
- [ ] Temporary workarounds have owners, rationale, and review dates.
- [ ] Build conventions updated so new modules do not repeat the mistake.

## 22. Specifications and reference documentation

Consult resources matching your target JDK and tool versions:

- **JDK 21 Release Notes – implicit annotation processing warning:** https://www.oracle.com/java/technologies/javase/21-relnote-issues.html
- **JDK 23 Release Notes – annotation processing disabled by default (JDK-8321314):** https://www.oracle.com/java/technologies/javase/23all-relnotes.html
- **OpenJDK Quality Outreach – JDK 23 default change:** https://inside.java/2024/06/18/quality-heads-up/
- **javac command documentation:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **Package javax.annotation.processing:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- **Gradle Java Library Plugin – annotationProcessor:** https://docs.gradle.org/current/userguide/java_library_plugin.html
- **Maven Compiler Plugin 3.14.1 – annotationProcessorPaths:** https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/compile-mojo.html
- **Maven Compiler Plugin 4.x – annotation processors:** https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html
- **IntelliJ IDEA annotation processing settings:** https://www.jetbrains.com/help/idea/annotation-processors-support.html

Tool versions and flags continue to evolve. In real migrations, consult release notes for the exact **compiler JDK**, **build tool/compiler plugin**, and **processor library** in use rather than comparing version numbers alone.

---

**Conclusion:** A major breaking point when upgrading the JDK is that **annotation processors previously activated implicitly now require explicit configuration starting in JDK 23**. Identify actually needed processors and dependencies, separate processor paths from general classpaths, check both main and test source sets, ensure processors are compatible with the compiler JDK while generated code matches the target release. Do not solve this by hiding warnings or relying on stale generated files. A reliable build explicitly declares what runs during compilation, which artifacts it produces, and what evidence proves outputs remain valid after migration.