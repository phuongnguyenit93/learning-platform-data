# Separating Processor Path, Processor Module Path, and Application Classpath When Compiling Java

## 1. Why Are Three Different Paths Needed?

A project using **annotation processing (JSR 269)** has at least two very different roles: the Java code being compiled and **the processor program** that `javac` loads to analyze annotations, validate declarations, or generate additional code. If all dependencies are placed onto a single classpath, the project may still work in some configurations yet easily encounter problems:

- The compiler cannot find annotation classes in the source (`package ... does not exist`).
- The compiler finds the annotation yet does not load or run the processor, causing generated types not to exist (`cannot find symbol`).
- The processor JAR is present yet lacks **the processor's own** dependencies when loading (`NoClassDefFoundError`, `ServiceConfigurationError`).
- The processor accidentally appears on the application's runtime classpath, increasing size and adding unnecessary dependencies.
- Upgrading to JDK 23+ causes relying on **accidental processor auto-discovery on the classpath** to no longer work by default.
- Mixing `--processor-module-path` and `-processorpath` in the same invocation causes an error right at compiler options.

Three main concepts:

| Path | Who Consumes It? | What Does It Contain? | `javac` Option |
| --- | --- | --- | --- |
| **Application compile classpath** | The compiler when resolving types used by **application sources** | Annotation APIs, libraries/compiled classes needed by sources | `-cp`, `-classpath`, `--class-path` |
| **Processor path** | The compiler when **locating and loading classpath-style processors** | Processor implementations, dependencies of the processor | `-processorpath`, `--processor-path` |
| **Processor module path** | The compiler when **locating and loading processors that are named modules** | Modules providing `Processor`, module dependencies | `--processor-module-path` |

**Core point:** processor path and processor module path are **two different ways to deploy processors**, not two mandatory parts that must always be used together. In a single `javac` command, choose the appropriate processor path. The application classpath (or application module path) is an **independent** configuration for the code being compiled.

Do not confuse `--processor-module-path` with `--module-path`: the former is where **processor modules** are loaded; the latter is where **modules of the program being built** are resolved. Both contain the word *module*, yet serve two different dependency graphs.

## 2. Diagram of Dependency Layers at Compile Time

~~~text
                             JAVAC
                       (compiler process)
                               |
             +-----------------+-----------------+
             |                                   |
             v                                   v
   Resolve the program               Load and run Processor
  (app/annotation API)                (JSR 269, per round)
             |                                   |
   -classpath / --module-path         -processorpath
             |                         OR
             |                         --processor-module-path
             |                                   |
             +----------+------------------------+
                        |
                        v
              Generated Java source
                        |
                        v
          Compile input + generated sources
                        |
                        v
                    .class files
~~~

A practical dependency classification:

- **Annotation API artifact:** provides `@Generate`, `@Mapper`, or marker annotations; application sources must see those types when compiling. If the annotation only has `RetentionPolicy.SOURCE` and is no longer referenced by bytecode/runtime, this artifact can be a compile-time-only dependency.
- **Processor implementation artifact:** provides classes implementing `javax.annotation.processing.Processor`; the compiler must load it during the build. Normally the application **does not need** the processor implementation at runtime.
- **Processor's own dependencies:** JARs/modules that processor classes call while running inside the compiler. They must be on the **processor loading path**, not merely on the application classpath.
- **Application libraries:** types that sources call in the program; placed on the compile classpath/module path and, if bytecode needs them at execution time, the runtime classpath/module path.

Some projects intentionally package the annotation API and the processor in **the same JAR**. This is a permitted packaging choice, yet be aware that adding that JAR as a compile dependency can pull the processor implementation into an unnecessary scope. Splitting into two artifacts usually helps control roles and limit dependencies better.

## 3. Processor Discovery Mechanisms: `-processor`, Service Providers, and JDK 23+

There are two main ways for `javac` to know which processor to run:

1. **Explicitly naming the processor class**, for example `-processor ap.GenerateProcessor`, and providing where to load it (`-processorpath processor.jar` for a processor on the classpath).
2. **Service-provider discovery**, with a `META-INF/services/javax.annotation.processing.Processor` file in a classpath-style JAR, or `provides javax.annotation.processing.Processor with ...` in the module descriptor of a named-module processor.

Since **JDK 23**, by default `javac` does not run annotation processors merely because a processor happens to appear on the classpath. This is an important change in discovery behavior. Configure annotation processing **explicitly**, such as via `-processor`, `-processorpath`, `--processor-module-path`, or `-proc:full` if supported by the compiler. On earlier JDK releases, auto-discovery on the classpath could make builds "just work" yet was environment-dependent and less safe.

The modes:

| Option | Meaning |
| --- | --- |
| `-proc:none` | Do not run annotation processing. |
| `-proc:only` | Run processing without performing normal bytecode compilation afterward. |
| `-proc:full` | Run processing and continue compiling. |
| `-processor a.b.X` | Explicitly specify the processor class; does not require a service file when loaded via classpath with the proper processor path. |
| `-XprintRounds` | Print processing rounds for diagnostics. |
| `-XprintProcessorInfo` | Print information about processors invoked and annotations claimed. |

**Do not equate `-processorpath` with "enabling a specific annotation".** This option only specifies **where to look for processors**; which processor is selected is still determined by `-processor`, service registration, and the compiler's discovery rules. If specifying `-processor` manually, know precisely which processors need to run so you do not accidentally omit other necessary processors.

## 4. Complete Example: Separating Annotation API, Processor, and Application

The example uses Java 17+ (verified with `javac --release 17`). An annotation `@Generate` marks class `App`; the processor generates `demo.Generated`; the application calls `Generated.say()` even though this source was not written by hand.

Initial structure:

~~~text
project/
  api/
    demo/Generate.java
  processor/
    ap/GenerateProcessor.java
    META-INF/services/javax.annotation.processing.Processor
  app/
    demo/App.java
  processor-module/
    module-info.java
    ap/GenerateProcessor.java
~~~

The `processor-module/` directory serves **the modular variant in section 7**; it is not needed for the processor-path run in section 5. The two `GenerateProcessor.java` sources have identical content in the example, yet they are packaged separately under two strategies—**do not use both at the same time**.

### 4.1. File `api/demo/Generate.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Generate {}
~~~

An annotation with `SOURCE` retention is still visible to processors during compilation. `RUNTIME` retention is not required for the compiler to process annotations. Annotating a class also does not generate code by itself: a processor must run and create the source file.

### 4.2. File `processor/ap/GenerateProcessor.java`

~~~java
package ap;

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

@SupportedAnnotationTypes("demo.Generate")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GenerateProcessor extends AbstractProcessor {
    private boolean made;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment env) {
        if (env.processingOver() || made) {
            return true;
        }

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.Generate");
        if (annotation == null) {
            return false;
        }

        for (Element element : env.getElementsAnnotatedWith(annotation)) {
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("demo.Generated", element)
                    .openWriter()) {
                writer.write("package demo; public final class Generated { "
                        + "public static String say() { return \"generated\"; }}");
                made = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString(), element);
            }
        }
        return true;
    }
}
~~~

**Notably:** the processor does not directly import `demo.Generate`; it declares the annotation name as a string and uses the `TypeElement` model. Therefore, you can **compile the processor independently** of `annotations.jar` in this example. If the processor actually imports `demo.Generate` or calls a helper class belonging to the API artifact, that dependency may need to be on the **classpath when compiling the processor** as well as on the **processor path when running the processor**.

Components:
- `@SupportedAnnotationTypes` selects annotations that the processor understands.
- `RoundEnvironment` provides the corresponding elements in each round.
- `Filer.createSourceFile` creates Java source; `javac` compiles that source in subsequent steps.
- `made` prevents duplicate creation of `demo.Generated`; this simple code assumes one annotated element. Production code must handle multiple elements, file name conflicts, and incremental builds properly.
- `Messager` emits an error when file operations fail.

`javax.annotation.processing` is a standard Java SE package even on modern JDKs. Do not switch to `jakarta.annotation.processing` merely because some Java EE/Jakarta EE APIs use `jakarta.*` names.

### 4.3. File `app/demo/App.java`

~~~java
package demo;

@Generate
public class App {
    public static void main(String[] args) {
        System.out.println(Generated.say());
    }
}
~~~

There is no `Generated.java` file written by the developer. A compile command that neither runs the processor nor provides the generated class will report `cannot find symbol` at `Generated.say()`, even though the annotation API was resolved.

### 4.4. Service Descriptor for a Processor on the Classpath

The text file **`processor/META-INF/services/javax.annotation.processing.Processor`** contains only the implementation class name:

~~~text
ap.GenerateProcessor
~~~

This line tells the service-provider discovery mechanism which class provides the `Processor` service. If using `-processor ap.GenerateProcessor` directly, the service descriptor **is not mandatory** for the example, yet when packaging a JAR for build tools or discovery, valid registration is required.

## 5. Running a JAR Processor with `-processorpath`

In the `project/` directory, create the output directories (Bash):

~~~bash
mkdir -p api-classes processor-classes app-classes generated
~~~

### 5.1. Compile and Package the Annotation API

~~~bash
javac --release 17 -encoding UTF-8 \
  -d api-classes api/demo/Generate.java

jar --create --file annotations.jar -C api-classes .
~~~

The `annotations.jar` JAR must contain the entry `demo/Generate.class`; it is the artifact for **application sources to resolve the annotation**.

### 5.2. Compile and Package the Processor

~~~bash
javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/GenerateProcessor.java

jar --create --file processor.jar \
  -C processor-classes . \
  -C processor META-INF/services/javax.annotation.processing.Processor
~~~

After packaging, `processor.jar` contains:
- `ap/GenerateProcessor.class`
- `META-INF/services/javax.annotation.processing.Processor`

**There is no need** to add `processor.jar` to the application classpath of `App.java` just to run the processor. It needs to be passed via the **processor path**, and the application source only needs `annotations.jar` to resolve `@Generate`.

### 5.3. Application Compile Command Separating Both Paths

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -processor ap.GenerateProcessor \
  -XprintRounds \
  -s generated \
  -d app-classes \
  app/demo/App.java
~~~

The two most important arguments:

- **`-cp annotations.jar`**: `javac` reads the `demo.Generate` type used by the application source; this is the **application's** compile classpath.
- **`-processorpath processor.jar`**: `javac` locates and loads `ap.GenerateProcessor`; this is the **compiler plugin/processor's** classpath, independent of the application classpath.

`-processor ap.GenerateProcessor` makes processor selection explicit. `-s generated` specifies the path for generated Java sources; `-d app-classes` is the output for class files. On Windows PowerShell/cmd, put each invocation on **one line** or adjust line-continuation syntax appropriately: the `\` character in the example is for Bash.

Key round output from testing with `javac` (indentation in logs may vary by JDK):

~~~text
Round 1:
    input files: {demo.App}
    annotations: [demo.Generate]
    last round: false
Round 2:
    input files: {demo.Generated}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Round 1 processes the input source; round 2 receives the `demo.Generated` file created by the processor; round 3 is the final round. There are not three `javac` calls here: **all three rounds happen within the same application compile invocation**.

Run:

~~~bash
java -cp app-classes demo.App
~~~

Exact stdout:

~~~text
generated
~~~

`annotations.jar` does not have to be present on the **runtime classpath of this example**: the `@Generate` annotation has `SOURCE` retention and the application does not need to access the annotation class at runtime. This is a characteristic of **this specific example**, not a rule that all annotation APIs can be excluded from runtime. If an annotation has `RUNTIME` retention and a framework uses reflection, or runtime code uses the annotation API, provide the appropriate artifact.

Corresponding outputs:

~~~text
annotations.jar       # contains demo/Generate.class
processor.jar         # contains ap/GenerateProcessor.class + service descriptor
generated/
  demo/Generated.java
app-classes/
  demo/App.class
  demo/Generated.class
~~~

### 5.4. What If the Processor Is Not Explicitly Named?

Because `processor.jar` already has a service descriptor, you can also use:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -s generated -d app-classes app/demo/App.java
~~~

With `javac 24.0.2`, explicit processor path configuration enables service-provider discovery; the example compiles successfully. Do not rely on the processor being loaded **merely because the JAR is present somewhere on the application classpath**, especially from JDK 23 onward.

## 6. If the Processor Path Has Dependencies, Where Do They Go?

Suppose `ap.GenerateProcessor` calls a helper library `com.acme.codegen.WriterHelper` inside `codegen-helper.jar`. That library must be readable while **the processor is running inside the compiler**.

In the classpath-style processor case on Bash/macOS/Linux:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath "processor.jar:codegen-helper.jar" \
  -processor ap.GenerateProcessor \
  -d app-classes app/demo/App.java
~~~

On Windows, use `-processorpath "processor.jar;codegen-helper.jar"`.

`codegen-helper.jar` here is an **illustrative name**, not an existing artifact in the section 5 example. The command will only run when the library actually exists and the processor needing it is compiled accordingly.

If a dependency is missing when loading or during processor execution, you may encounter:

~~~text
java.lang.NoClassDefFoundError: com/acme/codegen/WriterHelper
~~~

or a service loading/processor initialization error, depending on where it occurs. Adding `codegen-helper.jar` to the **application classpath** is not guaranteed to fix a missing dependency **on the processor path** if `javac` is using a separate processor loader. Conversely, libraries that application sources import must be on the application compile path; adding them only to the processor path is not enough either.

**Separating dependencies is a logical and build-tool boundary**, not an absolute security sandbox. Annotation processors execute Java code during compilation and can access files, the environment, and resources that the compiler process has permissions for. Only run processors from trusted sources, lock versions, and review the dependency supply chain.

## 7. Processor as a Named Module: Using `--processor-module-path`

When packaging a processor as a **JPMS named module**, use a Java module descriptor with a `provides` service instead of a classpath-style service file.

Create **`processor-module/module-info.java`**:

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
            with ap.GenerateProcessor;
}
~~~

Create **`processor-module/ap/GenerateProcessor.java`** with **identical content** to `processor/ap/GenerateProcessor.java` in section 4.2. You do not need to copy the `META-INF/services` service descriptor into the module JAR for this modular example: the provider is declared in `module-info.java`.

Explanation:
- `requires java.compiler`: the processor uses the Java Compiler API (JSR 269).
- `provides ... with ap.GenerateProcessor`: registers the `Processor` implementation for the compiler to discover from the processor module path.
- You do not have to export package `ap` just so application code can import the processor class; **application source does not need to reference the implementation**. Java module service loading has its own mechanism for providers.
- Module `demo.processor` is a module of the **compile-time tool**, not a required module of the application.

### 7.1. Build the Processor Module

~~~bash
mkdir -p processor-module-classes generated-mod app-classes-mod

javac --release 17 -encoding UTF-8 \
  -d processor-module-classes \
  processor-module/module-info.java \
  processor-module/ap/GenerateProcessor.java

jar --create --file processor-mod.jar -C processor-module-classes .
~~~

Verify with:

~~~bash
jar --describe-module --file processor-mod.jar
~~~

The output must show module `demo.processor`, dependency `java.compiler`, and provider `ap.GenerateProcessor`. Line formatting/version output may vary across JDK releases.

### 7.2. Use Processor Module Path While App Still Uses Classpath

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  --processor-module-path processor-mod.jar \
  -XprintRounds \
  -s generated-mod \
  -d app-classes-mod \
  app/demo/App.java
~~~

There is no `-processorpath` in this command. The compiler discovers the processor via the **module service descriptor** and processes annotations in the application source. `App.java` and `annotations.jar` in this example still follow the classpath/unnamed-module model: **a processor using the module path does not force the entire application to become a named module as well**.

Verified with `javac 24.0.2`: generates `generated-mod/demo/Generated.java`, prints three processing rounds as in section 5, and run:

~~~bash
java -cp app-classes-mod demo.App
~~~

Stdout:

~~~text
generated
~~~

If the processor module needs its own dependent modules, those dependencies must be resolved in the **processor module layer** according to JPMS. Do not simply append JARs to the application classpath and expect the processor module to read them automatically. For dependencies packaged as automatic modules, you must consider module names, readability, and compatibility when modularizing.

### 7.3. Can Both `-processorpath` and `--processor-module-path` Be Enabled?

**No.** When trying in the same invocation:

~~~bash
javac --release 17 \
  -cp annotations.jar \
  -processorpath processor.jar \
  --processor-module-path processor-mod.jar \
  -d app-classes app/demo/App.java
~~~

`javac 24.0.2` reports:

~~~text
error: illegal combination of -processorpath and --processor-module-path
~~~

Do not try to solve this by passing both paths to "look for processors in both places". Choose **one processor-loading strategy** per compile invocation. If an application needs multiple processors with different packaging styles, reorganize packaging/configuration at the build tool level and ensure the compiler can load them via a supported mechanism, instead of passing two mutually exclusive flags.

## 8. Distinguishing Application Module Path and Processor Module Path

A modularized application may have:

~~~java
module demo.app {
    requires demo.annotations;
}
~~~

This is **an example `module-info.java` for another JPMS application**; `demo.annotations` must actually be a module readable by the application, with an exported package. It **does not belong to the runnable files in section 4**, where `annotations.jar` is just a regular JAR on `-cp`.

With JPMS, there can be **four** axes to identify:

| Axis | Contains | Goal |
| --- | --- | --- |
| `--class-path` | Libraries/classes used by source in the unnamed module | Resolve application symbols |
| `--module-path` | Named/automatic modules of the program | Resolve and check application readability/exports |
| `--processor-path` | Processor JAR + classpath dependencies | Load classpath-based processors |
| `--processor-module-path` | Processor module + module dependencies | Load modular processors |

In one invocation, you can use **application module path** together with **processor module path** if the project is modularized and the processor is modular. These two options are not mutually exclusive because they serve different roles. Mutual exclusion is between **processor path** and **processor module path**.

For a JPMS project, an annotation's package may exist yet not be accessible if the application's module descriptor lacks `requires` or the library module does not `exports` the package. That is a **module readability/exports** problem, distinct from "processor was not loaded".

## 9. Negative Experiments: Knowing Which Path You Are Missing

### 9.1. Having Only Annotation API Without Running Processor

Example using `-proc:none`:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -proc:none -d app-classes app/demo/App.java
~~~

The command intentionally **fails** when output is clean and `demo.Generated` does not exist yet:

~~~text
error: cannot find symbol
        System.out.println(Generated.say());
                           ^
  symbol:   variable Generated
  location: class App
~~~

`@Generate` was resolved because `annotations.jar` is on the application classpath. The error occurred on the **generated type** because processing was disabled.

### 9.2. Missing Annotation API on Compile Classpath

If you only pass `-processorpath processor.jar` without placing `annotations.jar` on the app compile path, `@Generate` in source can fail with:

~~~text
error: cannot find symbol
@Generate
 ^
  symbol: class Generate
~~~

The processor seeing it via the processor path **does not mean application source also sees annotation types**. Similarly, if the annotation belongs to another package, the import may report `package ... does not exist`.

### 9.3. Processor Present Yet Not Selected/Run

If the processor JAR is on the app classpath without explicit processing configuration, behavior depends on compiler/JDK and flags. With JDK 23+, do not expect implicit processing; the compiler may skip running the processor, leaving the generated class missing. The right approach: provide the proper processor path/module path and enable discovery or specify the processor.

### 9.4. Missing Processor Dependency

When `javac` reports an error while loading a processor (`NoClassDefFoundError` / provider initialization), inspect the **processor dependency graph**. Do not fix it by adding all dependencies to the application runtime path: that is a different set.

### 9.5. Processor Generates Source Yet App Still Fails to Compile

Check whether the generated source in `-s` has the right package/type, whether the processor threw an error, whether the round picked up the new source, and whether the generated source has compile errors. Do not assume every `cannot find symbol` is due to a missing path; the processor might have generated the wrong name or failed to satisfy generation conditions.

## 10. Build Tools: Configuring Dependencies by Role

In real projects, developers typically do not type `javac` manually each time; Maven and Gradle construct compiler arguments. How dependencies are declared must maintain the same functional boundaries as manual commands.

### 10.1. Gradle Java Plugin

Groovy DSL example (`build.gradle`):

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'com.example:annotations-api:1.0.0'
    annotationProcessor 'com.example:generate-processor:1.0.0'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

This is an **illustrative configuration**: `com.example:annotations-api:1.0.0` and `com.example:generate-processor:1.0.0` are not artifacts claimed to exist. Replace them with actual library coordinates.

- `compileOnly`: provides the annotation API for source compilation; does not automatically add to the runtime classpath. Only appropriate when the application truly **does not need** that dependency at runtime.
- `annotationProcessor`: dependency intended for the processor path of the `JavaCompile` task; not equivalent to `implementation`.
- `implementation`: used for libraries that application source needs at both compile time and runtime.
- `runtimeOnly`: does not expose classes for source imports at compile time.

If Java test sources also use an annotation processor, pay attention to `testAnnotationProcessor` and test dependencies/source sets. With Kotlin/KAPT/KSP, processors must be configured through the corresponding plugin; do not conflate those processing systems with pure Java JSR 269.

When using a processor that is a **JPMS named module**, check the Gradle JavaCompile/Gradle plugin version and how it constructs `--processor-module-path`. `annotationProcessor` is a Gradle **dependency configuration**, while `--processor-module-path` is a **`javac` option**; you cannot assume by default that every Gradle version will automatically infer a modular processor-loading strategy from a dependency containing `module-info.class`.

### 10.2. Maven Compiler Plugin

With Maven Compiler Plugin versions that support `annotationProcessorPaths`, you can separate the annotation API dependency from the processor artifact:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>annotations-api</artifactId>
        <version>1.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example</groupId>
                        <artifactId>generate-processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is a **POM snippet** to place inside a complete `<project>`, not a standalone runnable POM; dependency coordinates are illustrative only. `provided` in Maven still puts the dependency onto the **compile classpath**, yet assumes the environment supplies the dependency if needed at runtime; for a `SOURCE` annotation not used at runtime, this can be a suitable option. If the annotation has a runtime role, the scope must be reconsidered.

How processor path or processor module path is configured in Maven **depends on the Maven Compiler Plugin version** and dependency type configuration. The common 3.x plugin uses `annotationProcessorPaths`; newer plugin versions add dedicated dependency mechanisms (processor/classpath-processor/modular-processor). Consult the documentation **for the exact version** and the effective POM rather than assuming an old configuration automatically handles modular processors properly on every JDK.

### 10.3. General Rules for Build Tools

1. **Annotation API** on the compile classpath or application module path if sources import the annotation.
2. **Processor implementation** on the processor path or processor module path; avoid including it in runtime artifacts if unnecessary.
3. **Processor dependencies** on the appropriate classpath/module path serving the processor loader.
4. **Generated sources** are tracked by the compile task, placed in a separate output directory, and never edited manually.
5. **JDK 23+** has a new processor discovery policy: verify compiler arguments instead of relying on the classpath accidentally containing a processor.
6. **Gradle/Maven compiler versions and JDK toolchains** must be compatible with the processor-loading style in use.

## 11. Inspecting Paths with JDK Tools

### Listing Artifact Contents

~~~bash
jar tf annotations.jar
jar tf processor.jar
jar tf processor-mod.jar
~~~

Results to distinguish:
- `annotations.jar` contains `demo/Generate.class`.
- `processor.jar` contains `ap/GenerateProcessor.class` and the service descriptor in `META-INF/services`.
- `processor-mod.jar` contains `module-info.class` and `ap/GenerateProcessor.class`; the module descriptor is where `provides` is declared.

### Verifying a Modular Processor

~~~bash
jar --describe-module --file processor-mod.jar
~~~

Verify the module name, `requires java.compiler`, and `provides javax.annotation.processing.Processor with ap.GenerateProcessor`.

### Checking Whether the Processor Was Actually Invoked

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp annotations.jar \
  -processorpath processor.jar \
  -processor ap.GenerateProcessor \
  -XprintRounds -XprintProcessorInfo \
  -s generated -d app-classes app/demo/App.java
~~~

If the first round lacks the expected annotation, check the annotation name, `@SupportedAnnotationTypes`, and input sources. If the processor does not appear, check the loader path and service/processor name. If source is generated yet compilation fails, read diagnostics from the generated Java file; changing paths cannot substitute for fixing content errors.

### Checking Which Flags javac Supports

~~~bash
javac --help
javac -version
~~~

Especially when working with Java 17, 21, 23+, check the actual compiler invocation, not just the `java -version` value printed from another terminal.

## 12. Misconceptions to Avoid

**Misconception 1: "The processor JAR must always be on the application classpath."** False. Processors have their own loading path; the app only needs APIs used by source or runtime.

**Misconception 2: "I added annotations.jar to -processorpath so @Generate must be resolved."** Incorrect if source needs this type yet the compile classpath/module path does not contain it. The two loaders serve two tasks.

**Misconception 3: "Using processor path and processor module path simultaneously increases the chance of finding processors."** On standard `javac`, this is an illegal combination.

**Misconception 4: "If the processor is a named module, the application must also have module-info.java."** False. The example in section 7 shows that processor module path and app classpath can coexist.

**Misconception 5: "All JDKs automatically scan processors on the application classpath."** No. JDK 23+ changes the default; explicit configuration is safer and more reproducible.

**Misconception 6: "A processor dependency can be replaced with runtimeOnly."** False. Application `runtimeOnly` does not provide dependencies to the JVM running the processor inside the compiler when a separate processor path is configured.

**Misconception 7: "Once the compiler creates sources, the application can automatically run even if compilation has errors."** False. Generated sources still need to be parsed and compiled, with the right classpath/module graph and no semantic errors.

**Misconception 8: "Only one --module-path is needed for everything."** False. Application modules and processor modules have different roles; the processor module path is not the application module path.

**Misconception 9: "Separating the processor path is a security sandbox."** False. It helps control dependencies/discovery, not isolate permissions of processor code running inside the compiler.

**Misconception 10: "Not seeing the generated class means the processor was not loaded."** Not necessarily. The processor may have been invoked yet failed to match the annotation, generated the wrong package, emitted an error, or had its output excluded from the compile task.

## 13. Quick Diagnostic Workflow

When reporting `package ... does not exist`, `cannot find symbol`, `Processor ... not found`, or `NoClassDefFoundError` in a build with annotation processing, follow this order:

1. **Identify the failing object**: source annotation type, processor implementation, processor dependency, or generated class?
2. **Read the compiler invocation**: record the exact `-cp`, `--module-path`, `-processorpath`, `--processor-module-path`, `-processor`, `-proc:...`, and `javac` version.
3. **Inspect the actual JAR/module**: `jar tf`, `jar --describe-module`, packages, and class names.
4. **Check discovery**: service descriptor for processor JAR or `provides` in the module descriptor; with JDK 23+, do not rely on implicit classpath discovery.
5. **Enable `-XprintRounds`**: see whether the annotation is processed and whether the generated class appears in the next round.
6. **Check processor dependencies**: if it crashes while loading the processor, fix the processor path/module path, do not blindly modify the application path.
7. **Check generated source/output**: `-s` for sources, `-d` for `.class`; do not confuse the two paths.
8. **Clean the build and retry**: avoid old `.class` or generated sources hiding the root cause.
9. **Pin configuration in Maven/Gradle**: ensure IDE and CI use the same dependency graph, toolchain, and processor mode.

Classification examples:

| Symptom | Check First |
| --- | --- |
| `@Generate` not visible | `annotations.jar` on the app compile classpath/module path |
| `ap.GenerateProcessor` not found | Whether the processor implementation JAR/module is properly on the processor path/module path |
| `NoClassDefFoundError` from processor code | Processor loader dependency missing or unreadable |
| `Generated` does not exist | Whether the processor ran, matched the annotation, and generated source properly |
| `illegal combination of -processorpath and --processor-module-path` | Drop one of the two strategies and configure consistently |
| Build runs on JDK 17 yet fails on JDK 23+ | Check implicit processor discovery and explicit processing flags |
| Compilation passes yet runtime lacks application helper | Check runtime classpath/module path; do not use processor path to "fix" runtime |

## 14. Self-Check Questions

**Question 1.** Source `App.java` imports `demo.Generate`, the processor JAR is on `-processorpath`, yet `annotations.jar` is not on `-cp`. Why does it fail?  
**Answer:** The **application's** compile classpath cannot see the annotation API. Processor path does not replace symbol resolution for application sources.

**Question 2.** Processor `ap.GenerateProcessor` calls a separate helper library in `helper.jar`. Where should `helper.jar` be added when the processor is loaded from `-processorpath`?  
**Answer:** You need to ensure it is on the processor path together with the processor, such as `-processorpath "processor.jar:helper.jar"` on Unix or `"processor.jar;helper.jar"` on Windows.

**Question 3.** Can you compile a non-modularized app while using a modular processor via `--processor-module-path`?  
**Answer:** Yes. The example in section 7 uses `-cp annotations.jar` and `--processor-module-path processor-mod.jar` in the same invocation.

**Question 4.** By which mechanism does a named-module processor register its implementation?  
**Answer:** `provides javax.annotation.processing.Processor with ap.GenerateProcessor;` in `module-info.java`, together with the corresponding `requires java.compiler` dependency.

**Question 5.** Is using `-processorpath` and `--processor-module-path` simultaneously valid?  
**Answer:** No; `javac` rejects this combination.

**Question 6.** Why might Java 23+ fail to generate classes even though the processor JAR is in the application classpath?  
**Answer:** You should not rely on implicit auto-discovery. Processor execution must be configured explicitly according to the JDK and build tool.

**Question 7.** Does giving `@Generate` `SOURCE` retention prevent the processor from receiving the annotation during compilation?  
**Answer:** No. The compiler sees annotations in source code during processing rounds.

**Question 8.** Since a processor is a compile-time dependency, does it need to be placed on the application's runtime classpath?  
**Answer:** Usually no. Only include on the runtime classpath libraries that bytecode/runtime logic actually needs.

**Question 9.** Is it true that every `cannot find symbol` in a project using processors is caused by a missing processor path?  
**Answer:** No. The annotation API may be missing, the processor may not match, the generated class may have the wrong name, or source/generated source may have an independent Java error.

## 15. Standard References

- [Java 17 javac command — annotation processing and paths](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Java 24 javac command — processor options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [JSR 269 — Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)
- [Java Platform Module System — `provides` and `requires`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Gradle Java Plugin: dependencies for annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven Compiler Plugin documentation](https://maven.apache.org/plugins/maven-compiler-plugin/)

**Conclusion:** Separate **dependencies that application sources need to resolve** from **dependencies needed for the compiler to load processors**. Use `-cp`/application module path for application code; choose either `-processorpath` or `--processor-module-path` for processors; configure discovery explicitly, especially from JDK 23 onward. Finally, inspect generated files, compiler rounds, and runtime dependencies separately.