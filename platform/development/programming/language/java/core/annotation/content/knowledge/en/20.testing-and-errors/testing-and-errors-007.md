# Diagnosing an Annotation Processor Not Discovered or Not Invoked

When using annotation processing (JSR 269), a common failure is that the Java code still compiles, yet generated files do not appear, or the processor does not print any diagnostics. These two situations are distinct: **the processor has not been discovered/loaded by the compiler** and **the processor has been loaded but does not receive annotations or does not produce output**. The fix depends on identifying the exact stage where it breaks.

## 1. Understanding the Processing Pipeline to Isolate Errors

During a compilation with annotation processing, the typical flow is:

1. `javac` is configured to allow annotation processing; starting from JDK 23, you should not rely on automatic classpath scanning without explicit AP configuration.
2. The compiler determines the **processor path** (or processor module path) and looks for processors via service providers / JPMS or an explicitly specified `-processor` list.
3. The compiler's JVM loads and instantiates the class implementing `javax.annotation.processing.Processor`; for `AbstractProcessor`, the compiler calls `init(ProcessingEnvironment)`.
4. The compiler checks the annotation types supported by the processor via `getSupportedAnnotationTypes()`, then calls `process(...)` in the appropriate rounds.
5. The processor uses `RoundEnvironment` and `Filer` / `Messager` to process elements and may generate source/resource/class files; newly generated sources can trigger subsequent rounds.
6. The compiler completes the final round (`processingOver() == true`) and then compiles the code, unless `-proc:only` is used.

**Processor not found** typically occurs in steps 1–3; **the processor is found but does not run the expected processing code** typically occurs in steps 4–5. **Having no generated files** is not enough to prove that the processor was not invoked: the processor might only perform checks/reporting, find no matching elements, stop at the final round, or fail while creating files.

| Symptom | Primary Hypothesis | How to Confirm |
| --- | --- | --- |
| No processor information in logs | AP is disabled, processor path is missing, or service is not registered | Check `-proc`, `-processorpath`, `-processor`; try `-XprintProcessorInfo` |
| Error `Annotation processor '…' not found` | The class listed in `-processor` is missing from the processor path or cannot be loaded | `jar --list`, fully qualified class name, processor dependencies |
| Error `Bad service configuration file` / `Provider … not found` | The service file contains a wrong name, is missing a class, or cannot be loaded by the classloader | Open `META-INF/services/javax.annotation.processing.Processor` and inspect the JAR |
| Processor appears, but no elements are processed | Supported annotation name is wrong, or the annotation is absent from the compiled sources | `@SupportedAnnotationTypes`, `RoundEnvironment`, `-XprintRounds` |
| Logs show rounds and `process`, but no files are generated | Logic/filter, `Filer`, output location, or stale build | Print diagnostics and check `-s`, generated sources directory |
| Works with `javac`, fails in Maven/Gradle/IDE | Each tool configures the processor path differently | Compare compiler args, JDK toolchain, tasks, and caches |

## 2. Checking the Processor Class and Registration Mechanism

A standard annotation processor typically extends `AbstractProcessor` and must have:

- A public class with an accessible no-argument constructor, compiled to `.class`; use imports from the correct `javax.annotation.processing` package (do not confuse it with `jakarta.annotation`).
- A list of supported annotations via `@SupportedAnnotationTypes("com.example.MyAnnotation")` or by overriding `getSupportedAnnotationTypes()`. Names must be fully qualified; `"*"` means supporting all annotations and is mainly appropriate when truly needed.
- An appropriate source version via `@SupportedSourceVersion(...)` or `getSupportedSourceVersion()`.
- A service provider configuration at the **exact** path `META-INF/services/javax.annotation.processing.Processor` inside the processor JAR; its content consists of fully qualified class names, one processor per line. This is the interface name, not the annotation name.
- When using the JPMS **processor module path**, the processor module must be declared appropriately, for example `provides javax.annotation.processing.Processor with demo.DemoProcessor;` in `module-info.java`, instead of relying solely on the classpath service mechanism.

Distinguishing the paths:

- `-classpath` / `-cp`: required for **application source code** that references classes, such as the `@DemoMark` annotation type.
- `-processorpath` / `--processor-path`: where the compiler **searches for and loads processors along with their dependencies**. If a separate path is declared, simply adding the JAR to the application classpath does not guarantee the processor will be found.
- `--processor-module-path`: path for processors packaged using JPMS; do not use it simultaneously with the classpath as a blind workaround.
- `-processor demo.DemoProcessor`: explicitly invokes the named processor and **skips automatic discovery from the service file**; useful for distinguishing service registration errors from classloading errors.
- `-proc:none`: disables annotation processing; `-proc:only`: runs only the processors without compiling the results; `-proc:full`: performs annotation processing and then compiles.

Starting in **JDK 23**, `javac` no longer automatically runs an annotation processor simply because it happens to find it on the classpath. Explicitly declare the processors allowed to run using `-processor` and the appropriate path; `-proc:full` is a compatible option once the processor path is controlled. In real builds, use an explicit list of processors to avoid accidentally running unintended processors. Verify the actual compiler version with `javac -version` or the build's toolchain logs, rather than only looking at `java -version` in the terminal.

## 3. Minimal Runnable Experiment with Java 17+

The following example creates a source annotation and a processor that only writes diagnostics. It lets you test each step without depending on Lombok, MapStruct, frameworks, or generated files.

Structure:

```text
src/
  processor/demo/DemoMark.java
  processor/demo/DemoProcessor.java
  app/demo/App.java
resources/
  META-INF/services/javax.annotation.processing.Processor
```

File `src/processor/demo/DemoMark.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface DemoMark {}
```

File `src/processor/demo/DemoProcessor.java`:

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.DemoMark")
public final class DemoProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return false;
        }
        for (Element element : roundEnv.getElementsAnnotatedWith(DemoMark.class)) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "DemoProcessor saw " + element.getSimpleName(),
                    element);
        }
        return false;
    }
}
```

File `src/app/demo/App.java`:

```java
package demo;

@DemoMark
public class App {
    public static void main(String[] args) {
        System.out.println("Application runs");
    }
}
```

**Verbatim** content of `resources/META-INF/services/javax.annotation.processing.Processor`:

```text
demo.DemoProcessor
```

From the example root directory, run the following Bash commands (you can create the corresponding directories with PowerShell on Windows):

```bash
mkdir -p build/processor-classes build/classes
javac -d build/processor-classes src/processor/demo/DemoMark.java src/processor/demo/DemoProcessor.java
jar --create --file build/demo-processor.jar -C build/processor-classes . -C resources META-INF
jar --list --file build/demo-processor.jar
javac -cp build/demo-processor.jar -processorpath build/demo-processor.jar -proc:full -XprintRounds -XprintProcessorInfo -d build/classes src/app/demo/App.java
java -cp build/classes:build/demo-processor.jar demo.App
```

**Expected result:** the `jar --list` command outputs `demo/DemoProcessor.class`, `demo/DemoMark.class`, and `META-INF/services/javax.annotation.processing.Processor`. At the `javac` step, the diagnostic contains `DemoProcessor saw App`; `-XprintRounds` shows the processing rounds and `-XprintProcessorInfo` indicates the selected processor. The exact order/format of diagnostics depends on the JDK version; they typically appear on the compiler's stderr, not `java`'s stdout. The application run command prints exactly:

```text
Application runs
```

On Windows, the classpath for the `java` command uses `;` instead of `:`. If you only want to test the processor without generating `App.class`, replace `-proc:full` with `-proc:only` and **do not run** the final `java` command.

**Test to distinguish discovery errors:** keep the same arguments and add `-processor demo.DemoProcessor` to the `javac` command. If this works while automatic service discovery does not, inspect the path/content of the service file inside the JAR or the module path configuration. If neither works, check the processor path, classloading, JDK version, and errors inside the processor. Try with a clean build to avoid confusion with classes generated from a previous run.

## 4. Ordered Diagnostic Procedure

### Step A — Confirm That the Compiler Runs Annotation Processing

Run the build command with compiler arguments displayed. Check for `-proc:none`, options enabling processing, the JDK version, and whether the files containing the annotations are actually being compiled. On JDK 23+, if there is only a regular dependency on the compile classpath, the AP configuration may be insufficient. Test directly with `javac -proc:only -processor ... -processorpath ...` to isolate post-processing compilation.

`-XprintRounds` displays processing rounds, and `-XprintProcessorInfo` displays the queried processors/annotations; seeing no output in an up-to-date project is not necessarily a processor error because the compiler may **not have been invoked** in that build. Use a controlled clean/rebuild and confirm that the task executes.

### Step B — Confirm That the JAR and Service Are Actually Packaged

Inspect the contents of the published JAR or the JAR used by the build:

```bash
jar --list --file path/to/processor.jar
```

Look for the exact `META-INF/services/javax.annotation.processing.Processor`, the processor class, and the appropriate dependencies. Placing the service file in `src/main/java` instead of resources, casing mistakes, writing the short class name instead of the fully qualified name, or excluding resources from the JAR are common causes. For a processor in the same module currently being built, the compiler cannot load a processor that **has not yet been compiled** in that same pass as a prebuilt JAR; compile/publish the processor first or separate it into its own module.

### Step C — Distinguish Load Failures from Annotation Mismatches

Enable `-processor demo.DemoProcessor` to bypass service discovery. If it reports `not found` or `NoClassDefFoundError`, check the class, package, processor dependencies on the processor path, bytecode version compatibility (`UnsupportedClassVersionError`), and JPMS configuration. An `ExceptionInInitializerError` may originate from a static initializer or the processor's constructor; read the full root stack trace.

If the processor was selected but the code inside `process` does not run as expected, check `@SupportedAnnotationTypes`, the annotation type used in the source, and the source set actually being compiled. `@Retention(RetentionPolicy.SOURCE)` is still appropriate for compile-time processing; there is no need to change it to RUNTIME just for the processor to find the annotation. When filtering by package/element kind, emit diagnostics clearly showing the number of matched elements; do not rely on `System.out.println` as the primary diagnostic channel.

### Step D — Distinguish Processor Invocation from Output Creation Failures

A processor runs across multiple rounds. Do not write "first-round-only" logic without understanding sources generated in later rounds; check `roundEnv.processingOver()` and `roundEnv.errorRaised()`. When the processor creates files via `Filer.createSourceFile`, use the exact fully qualified name and guard against duplicate creation: `FilerException: Attempt to recreate a file for type ...` usually indicates the same filename is being created multiple times within a single compilation. If calling `Filer.createResource`, verify the correct `StandardLocation`, package, and relative path name.

Generated source files may reside in the `-s` directory or the generated sources directory configured by the build tool; `-d` is the output for class files. Not finding sources in the class output directory does not mean `Filer` failed to run. With `-proc:only`, source generation can occur while application classes are not yet created; this is intended behavior.

### Step E — Compare the Exact Build Environments

**Gradle (Groovy DSL):** the processor must be declared in the `annotationProcessor` configuration of the compiled source set, rather than only in `implementation`. Example with two existing projects:

```groovy
dependencies {
    implementation project(':annotation-api')
    annotationProcessor project(':demo-processor')
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-XprintRounds', '-XprintProcessorInfo']
}
```

In this example, `annotation-api` contains the annotation types and `demo-processor` contains the processor; the project names are purely illustrative. Run `./gradlew clean compileJava --info` and read the executed task/processor path. For test sources, use `testAnnotationProcessor` when the processor is needed for `compileTestJava`. When using the build cache/incremental compilation, check whether the task actually executed before drawing conclusions about the processor; do not clear the system-wide cache by reflex.

**Maven (Compiler Plugin 3.x):** declare `annotationProcessorPaths` so Maven provides a dedicated path; if you want to pin specific processors, use `annotationProcessors`. Example configuration inside `maven-compiler-plugin` where coordinates should be replaced with real artifacts:

```xml
<configuration>
  <release>17</release>
  <annotationProcessorPaths>
    <path>
      <groupId>com.example</groupId>
      <artifactId>demo-processor</artifactId>
      <version>1.0.0</version>
    </path>
  </annotationProcessorPaths>
  <annotationProcessors>
    <annotationProcessor>demo.DemoProcessor</annotationProcessor>
  </annotationProcessors>
  <compilerArgs>
    <arg>-XprintRounds</arg>
    <arg>-XprintProcessorInfo</arg>
  </compilerArgs>
</configuration>
```

Run `mvn -X clean compile` to view the actual JDK, dependencies, and plugins in use; Maven Compiler Plugin 4.x with Maven 4 also supports declaring `processor` / `classpath-processor` / `modular-processor` dependency types, so cross-check against the exact major version. `annotationProcessorPaths` does not automatically provide the annotation API to the application if the annotation API is absent from compile dependencies.

**IDE:** IntelliJ IDEA/Eclipse may use their own compiler, run builds via Gradle/Maven, or have independent annotation processing configurations. Check that annotation processing is enabled, along with the processor path, generated sources root, and whether the IDE uses the same JDK/build tool as the CLI. If the CLI works while the IDE does not, focus on IDE configuration and delegation before modifying the processor source.

## 5. Misconceptions That Easily Lead to Wrong Fixes

- **"Only `@Retention(RUNTIME)` gets processed."** False: annotation processors work on the source/compile-time model; `SOURCE` is a valid choice.
- **"Having the processor JAR in `implementation` makes it run automatically."** Not necessarily, especially starting in JDK 23 and when Gradle/Maven use a separate processor path.
- **"`-processor` and the service file are always required together."** No: `-processor` specifies the processor explicitly and bypasses discovery. The service file serves automatic processor discovery on the processor classpath.
- **"Not seeing `System.out` means `process` did not run."** Insufficient evidence; use `Messager`, `-XprintRounds`, and `-XprintProcessorInfo`.
- **"`-proc:only` failed because there are no application `.class` files."** That is the annotation-processing-only mode; use `-proc:full` if you want to compile afterward.
- **"A successful build means generated files must exist."** The processor might not match any annotations, might not generate files, or the task might not have re-run.
- **"Just changing `@SupportedAnnotationTypes` to `"*"` is fine."** It can mask an incorrect declaration and cause the processor to receive many unintended annotations; use exact fully qualified names instead.

## 6. Checklist When Receiving a Bug Report

1. Record the **compiler JDK** and the actual compiler arguments; is `-proc:none` present or is AP configuration missing on JDK 23+?
2. Verify that **the compile task ran**; are the sources containing the annotation in that source set?
3. Inspect the **processor path**; check the JAR, classes, dependencies, and service file (or `provides` in JPMS).
4. Run **`-XprintRounds` + `-XprintProcessorInfo`**; try **`-processor fully.qualified.Processor`** to separate discovery failures from loading and matching issues.
5. If the processor did run, log diagnostics using **`Messager`**, and check the annotation name, rounds, `Filer`, and output directory.
6. Cross-check between **the CLI and Gradle/Maven/IDE**, verifying the build cache, test source sets, and compiler/plugin versions.

Record the minimal reproduction command, the full error output, and the before/after differences from the fix. Once the root cause is identified, put an explicit processor configuration into the build so the issue does not recur when upgrading the JDK or switching environments.

## References

- Oracle, `javac` (`-processor`, `-processorpath`, `-proc`, `-XprintRounds`, `-XprintProcessorInfo` options): https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- Inside Java, changes to the default annotation processing policy starting in JDK 23: https://inside.java/2024/06/18/quality-heads-up/
- Apache Maven Compiler Plugin, configuring annotation processors: https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html
