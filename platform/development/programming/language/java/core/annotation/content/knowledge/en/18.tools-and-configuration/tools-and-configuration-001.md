# Registering an annotation processor using META-INF/services/javax.annotation.processing.Processor

An **annotation processor** is a program that runs **during Java compilation**, capable of inspecting metadata, emitting errors/warnings, or generating source code. According to the JSR 269 API, a processor implements `javax.annotation.processing.Processor`; typically you extend `AbstractProcessor` and write `process(...)`.

To have `javac` **automatically discover** the processor in the artifact without having to specify the FQCN with `-processor` each time, you can use the Java **Service Provider Interface (SPI)**. The SPI configuration has a special path, relative to the **root of the processor classpath/JAR**:

```text
META-INF/services/javax.annotation.processing.Processor
```

This text file contains the **fully qualified class name of the implementation**:

```text
tutorial.processing.InspectProcessor
```

The **file** name is the FQCN of the **service interface** `javax.annotation.processing.Processor`; the **file** content is the FQCN of the **provider class** that you write yourself. The two names are different and must not be swapped.

For the processor to be invoked, placing the service file alone is **not enough**: the implementation class must be loadable, the artifact must be on the correct processor search path, and annotation processing must be enabled according to the `javac`/build tool configuration. This article walks through a complete Java 17+ example, verifies actual results, covers JAR packaging, and addresses error handling.

## 1. Where SPI fits in the compilation process

Suppose we have the class:

```java
@Inspect("catalog")
public class Catalog {
}
```

You want the compiler to record classes annotated with `@Inspect`. The three components that do this are:

| Component | Function |
| --- | --- |
| `Inspect` | Defines the annotation type and source metadata |
| `InspectProcessor` | Java code invoked by the compiler to process `@Inspect` |
| `META-INF/services/javax.annotation.processing.Processor` | Declares which implementation can be discovered via SPI |

The compiler follows this flow:

```text
Source code Catalog.java with @Inspect("catalog")
                  |
                  v
       javac with annotation processing enabled
                  |
                  v
  Look up SPI on processor path
  META-INF/services/javax.annotation.processing.Processor
                  |
                  v
  Read provider: tutorial.processing.InspectProcessor
                  |
                  v
  Load + instantiate Processor implementation
                  |
                  v
  Pass RoundEnvironment into process(...)
                  |
                  v
  InspectProcessor emits NOTE or processes metadata
                  |
                  v
  Compiler continues compiling/generating files per selected mode
```

**Key point:** this is a **compiler** plugin, not a callback automatically called by the JVM when the application starts. `@Inspect` does nothing on its own without a processor/consumer.

## 2. Sample project structure

To try this without needing Maven or Gradle, arrange the files as follows:

```text
spi-demo/
├── src/
│   ├── processor/
│   │   └── tutorial/
│   │       ├── annotations/
│   │       │   └── Inspect.java
│   │       └── processing/
│   │           └── InspectProcessor.java
│   └── app/
│       └── tutorial/
│           └── app/
│               └── Catalog.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── javax.annotation.processing.Processor
└── build/  (created by the compile command)
    ├── processor/
    └── app/
```

The package names are concrete examples. You can change them, but you must consistently update `package`, `import`, `@SupportedAnnotationTypes`, and the service file content.

`resources/` is just a source directory containing resources. **The Java compiler does not automatically search for SPI at an arbitrary path in the source tree**. In this example, we will compile the processor into `build/processor`, then copy `META-INF/` to the **root** of `build/processor`.

Correct target structure:

```text
build/processor/
├── tutorial/
│   ├── annotations/
│   │   └── Inspect.class
│   └── processing/
│       └── InspectProcessor.class
└── META-INF/
    └── services/
        └── javax.annotation.processing.Processor
```

If compressed into a JAR, these paths must be **entries inside the JAR**, without an extra `build/processor/` prefix.

## 3. Inspect.java — declaring the annotation read by the processor

File **`src/processor/tutorial/annotations/Inspect.java`**:

```java
package tutorial.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Inspect {
    String value();
}
```

Because of `@Target(TYPE)`, this annotation is placed on type declarations such as `class`. The `String value()` element allows writing the shorthand form `@Inspect("catalog")` instead of `@Inspect(value = "catalog")`.

Because the retention is `SOURCE`, the compiler processes the metadata at compile time without keeping the usage in the class file for Java Reflection to query later. **Processors do not require `RUNTIME` retention**: annotation processors read the source/class model provided by javac.

Most importantly, the processor runs **right when compiling the file with the annotation**. Changing retention to `RUNTIME` does not automatically fix an error where the processor has not been discovered.

## 4. InspectProcessor.java — implementing Processor

File **`src/processor/tutorial/processing/InspectProcessor.java`**:

```java
package tutorial.processing;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import tutorial.annotations.Inspect;

@SupportedAnnotationTypes("tutorial.annotations.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class InspectProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Inspect.class)) {

            Inspect inspect = element.getAnnotation(Inspect.class);

            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "InspectProcessor: " + element.getSimpleName()
                            + " -> " + inspect.value());
        }

        return true;
    }
}
```

`AbstractProcessor` implements the `javax.annotation.processing.Processor` interface and provides a base for processor methods. Therefore, `InspectProcessor` is a valid **service provider** when declared public and instantiable (in this example, the public class has no explicit constructor written, so it has a public no-arg constructor).

Meaning of each component:

- `@SupportedAnnotationTypes("tutorial.annotations.Inspect")` uses the **FQCN of the annotation to process**, **not** the processor name.
- `@SupportedSourceVersion(RELEASE_17)` indicates the source level supported by the processor in the example.
- `RoundEnvironment.getElementsAnnotatedWith(Inspect.class)` retrieves the elements provided by the compiler for the round that have `@Inspect`.
- `element.getAnnotation(Inspect.class)` retrieves easily readable metadata because `Inspect` only contains a `String`.
- `Messager.printMessage(Diagnostic.Kind.NOTE, ...)` emits a **compiler diagnostic**, which usually appears in `javac` output.
- `return true` means the processor **claims the supported annotation types** in that round, not a return code reporting build success or failure.

In processors with complex data such as class literals, enums, nested annotations, or arrays, you should consider `AnnotationMirror`/`AnnotationValue` and `TypeMirror`, avoiding the assumption that every type in the source has already been loaded by the JVM as a `Class<?>`.

**A processor can run multiple rounds.** This example does not generate source files and only emits a note when matching elements exist; do not infer that a processor in every project is called only once.

## 5. Catalog.java — the class inspected by the processor

File **`src/app/tutorial/app/Catalog.java`**:

```java
package tutorial.app;

import tutorial.annotations.Inspect;

@Inspect("catalog")
public class Catalog {
}
```

`Catalog` does not need `main`. When the compiler processes it, `InspectProcessor` emits a message containing `Catalog` and the value `"catalog"`.

You do **not** need to run `java tutorial.app.Catalog`. The processor belongs to build/compile time, not the lifecycle of a `Catalog` object.

## 6. Service file with the right name and content

Create the file at the source path:

`resources/META-INF/services/javax.annotation.processing.Processor`

Exact content of the example:

```text
tutorial.processing.InspectProcessor
```

SPI rules to remember:

1. **The file name is the service interface** `javax.annotation.processing.Processor`, not `InspectProcessor`, `Inspect.java`, or the application package name.
2. **Write one provider FQCN per line**. For the example, the provider is `tutorial.processing.InspectProcessor`.
3. **Do not write filesystem paths** such as `tutorial/processing/InspectProcessor.class` and do not append `.class` or `.java`.
4. **The location must be correct**: `META-INF/services` at the root of an entry on the processor path, for example the root of the classes directory or the root of the JAR.
5. **Should be saved as UTF-8 without BOM**, avoiding stray characters before the class name. SPI service configuration allows ignoring blank lines and comment lines starting with `#`.
6. **Multiple providers:** you can write multiple FQCN lines, but each class must exist, be loadable, implement `Processor`, and be validly instantiable.
7. **Watch the extension:** the file name ends at `.Processor`, and must not accidentally be saved as `.Processor.txt`.

Example content for **two providers only when both classes actually exist**:

```text
tutorial.processing.InspectProcessor
tutorial.processing.AuditProcessor
```

In the actual run in this article, only one provider `InspectProcessor` is used. The `AuditProcessor` line here only illustrates the capability of registering multiple implementations.

### The provider must be loadable

The service file does not contain bytecode. If the SPI file exists but the `InspectProcessor.class` class is not on the processor path, or the provider is not a class implementing `Processor`, a service loading error will occur. For example, the message may contain:

```text
Bad service configuration file, or exception thrown while constructing Processor object
Provider tutorial.processing.InspectProcessor not found
```

This is an **example of a common error format**, without claiming that every JDK prints these two lines verbatim. What needs to be checked is whether the **service file** and the **provider class/dependencies** exist with the right structure on the path the compiler is using.

## 7. Compiling the example in order to avoid premature auto-discovery errors

Position the terminal at the root of the `spi-demo` directory. On Linux/macOS (Bash), create the output directories:

```bash
mkdir -p build/processor build/app
```

**Step 1 — Compile the annotation API and processor implementation:**

```bash
javac --release 17 -d build/processor \
  src/processor/tutorial/annotations/Inspect.java \
  src/processor/tutorial/processing/InspectProcessor.java
```

After this command, `build/processor/tutorial/...` contains `Inspect.class` and `InspectProcessor.class`.

**Step 2 — Copy the service file to the processor output root:**

```bash
cp -R resources/META-INF build/processor/
```

Verify that it exists:

```text
build/processor/META-INF/services/javax.annotation.processing.Processor
```

**Step 3 — Compile Catalog.java, requesting processor discovery:**

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app \
  src/app/tutorial/app/Catalog.java
```

When the processor runs, the compiler prints the diagnostic:

```text
Note: InspectProcessor: Catalog -> catalog
```

This line may appear on `javac`'s stderr, but it is not a compiler error and not runtime output from the `Catalog` program. Across different compilers/IDEs, the diagnostic format or display location may differ.

**Why not copy the SPI file into `build/processor` before step 1?** During processor auto-discovery, the compiler may read the service file **before the implementation class is compiled**. If the file references a provider that does not yet exist, a service configuration error will occur. To avoid a confusing cycle, compile the implementation first, then place the SPI resource and compile the consumer.

### PowerShell on Windows

The equivalent commands can be written **one command per line** (without relying on Bash line-continuation characters):

```powershell
New-Item -ItemType Directory -Force build/processor, build/app | Out-Null
javac --release 17 -d build/processor src/processor/tutorial/annotations/Inspect.java src/processor/tutorial/processing/InspectProcessor.java
Copy-Item -Recurse resources/META-INF build/processor/
javac --release 17 -proc:full -cp build/processor -processorpath build/processor -d build/app src/app/tutorial/app/Catalog.java
```

Even though the shell differs, the paths inside the output/JAR and the service file name remain structurally identical. This example does not require Maven, Gradle, or any external plugins.

**Verified with the JDK:** the processor source compiles successfully with `javac --release 17`. Compiling the consumer using SPI and `-proc:full` invokes the processor and emits the diagnostic `Note: InspectProcessor: Catalog -> catalog`.

## 8. Three types of paths and compiler options

Main command:

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app \
  src/app/tutorial/app/Catalog.java
```

These must be clearly distinguished:

| Parameter | Role |
| --- | --- |
| `--release 17` | Target Java 17 source/API/bytecode |
| `-cp build/processor` | **Compile classpath** so the `Catalog` source can find `tutorial.annotations.Inspect` |
| `-processorpath build/processor` | **Processor path** for javac to find and load the processor + service configuration |
| `-proc:full` | Enables processing and continues compiling class output |
| `-d build/app` | Destination where the application's class files are generated |

In this example, `build/processor` contains both the annotation API and the processor, so the two paths `-cp` and `-processorpath` point to the same directory. That **does not mean the two options are equivalent**.

In real-world projects, the annotation API and the processor implementation can live in **two separate artifacts**: the API on the compile classpath and the implementation along with its dependencies on the annotation processor path. If the processor is on the application classpath but not on the path the compiler uses to find processors, the code may still compile without running the processor.

### Java 23+ and automatic processor execution

Recent JDKs have changed policies around default annotation processing, especially when upgrading from older versions to **JDK 23 and later**. A build that previously relied solely on a processor happening to appear on the classpath should not assume the compiler will always run it automatically.

Explicitly requesting processing with `-proc:full`, or declaring the processor and processor path using your build tool's mechanism, makes intent clear and keeps compilation reproducible. At the same time, keep the processor path minimal and trusted because a processor is **code that can execute during the build**.

## 9. How does SPI discovery differ from -processor and -proc:none?

### 9.1. Using the service file for discovery

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

There is no `-processor` option. Javac can discover the provider from `META-INF/services/javax.annotation.processing.Processor` on the processor path.

### 9.2. Specifying the implementation directly

```bash
javac --release 17 \
  -processor tutorial.processing.InspectProcessor \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

` -processor` passes the FQCN of the processor to run. This approach **does not need to rely on the service file** to find the provider name if the class can be loaded on the corresponding path.

This is a very useful test: if `-processor tutorial.processing.InspectProcessor` works while discovery does not, it is very likely that you should check the **SPI file location/content**, artifact, and processor path first.

### 9.3. Disabling annotation processing

```bash
javac --release 17 -proc:none \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

The processor is not run. `Catalog.java` can still compile into `Catalog.class` if its source/dependencies are valid, but **no note from `InspectProcessor` appears**.

### 9.4. Running the processor without performing normal class compilation

```bash
javac --release 17 -proc:only \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

` -proc:only` is used when you want to process annotations without proceeding through the entire normal class file generation process for the source. It is suitable for certain diagnostic/source-generation steps, but **is not equivalent to a full application build**.

### Comparison table

| Compiler invocation | Is the processor invoked in the example? | Role of the SPI file |
| --- | --- | --- |
| `-proc:full -processorpath ...` | Yes | Compiler finds the provider from SPI |
| `-processor tutorial.processing.InspectProcessor` | Yes | Not needed to specify the processor name |
| `-proc:none` | No | Ignored because processing is disabled |
| `-proc:only -processorpath ...` | Yes | Can be used to discover the processor |

**Actual verification:** all three main paths were run with `javac --release 17`: discovery with `-proc:full` emits the note, `-proc:none` emits no note, and specifying `-processor` emits the note when the implementation class is found. Compilation succeeded in all cases.

## 10. Packaging the processor into a JAR

From the example in section 7, after compiling the processor **and copying `META-INF/services`** into `build/processor`, you can package it:

```bash
jar --create --file build/inspect-processor.jar -C build/processor .
```

Inspect the entries:

```bash
jar --list --file build/inspect-processor.jar
```

You should see at a minimum:

```text
META-INF/services/javax.annotation.processing.Processor
tutorial/processing/InspectProcessor.class
tutorial/annotations/Inspect.class
```

These are **the essential entries that must be present**, not a verbatim copy of the full `jar --list` output. The archive may also contain `META-INF/MANIFEST.MF`, package directories, and other entries.

When using the newly created JAR:

```bash
javac --release 17 -proc:full \
  -cp build/inspect-processor.jar \
  -processorpath build/inspect-processor.jar \
  -d build/app src/app/tutorial/app/Catalog.java
```

In this demo, the JAR contains both the annotation API and the implementation; in production projects, the two can be separated into two artifacts for clearer roles.

**Common mistake:** storing the full `resources/META-INF/services/...` path **inside the JAR** instead of just `META-INF/services/...`. The provider lookup mechanism does not guess an extra `resources` folder. The rule is that **the service file must sit at the archive root** per the SPI specification.

## 11. Registering via a build tool

In Maven/Gradle, copying resources is typically handled by the resource processing mechanism of the plugin/source set. However, you still need to inspect the **output artifact** rather than only looking at the source tree.

The same principles apply:

- The **processor JAR** actually contains `META-INF/services/javax.annotation.processing.Processor`.
- The dependency containing the processor implementation is placed on the **annotation processor path**, not only `runtimeClasspath`.
- The source code being compiled sees the annotation API through the **compile classpath**.
- Annotation processing is enabled/requested in a way compatible with the JDK/plugin.
- If the processor requires supporting libraries, those dependencies must be loadable by the processor class loader.
- The compiler used by the build tool/IDE must be compatible with the processor version.
- When in doubt about the build tool, use the `javac` CLI example to distinguish class/processor errors from build configuration errors.

An IDE may display `@Inspect` and offer code completion properly yet the processor will not run at build time if annotation processing has been disabled. Conversely, annotation processing might run in a separate task without printing output to the terminal you are watching. Do not equate **in-editor source analysis** with **JSR 269 processor execution**.

## 12. Troubleshooting with -XprintRounds and -XprintProcessorInfo

Javac provides additional diagnostic options:

```bash
javac --release 17 -proc:full \
  -XprintRounds -XprintProcessorInfo \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

- `-XprintRounds` lets you view the **processing rounds**.
- `-XprintProcessorInfo` lets you observe which processors are invoked by the compiler along with information about annotation types.
- `Diagnostic.Kind.NOTE` from the processor helps distinguish whether `process` was invoked versus merely producing `Catalog.class`.

Do not rely on `-X...` output as a stable data API across JDKs; those options are for diagnostics. When programming a processor to report real errors, use `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)` or an appropriate overload to attach the error to the source location.

## 13. Ten common configuration mistakes

### 13.1. Wrong SPI file name

**Incorrect:**

```text
META-INF/services/InspectProcessor
META-INF/services/tutorial.processing.InspectProcessor
META-INF/services/javax.annotation.processing.Processor.txt
```

**Correct:**

```text
META-INF/services/javax.annotation.processing.Processor
```

The file name itself is the service interface. Do not name the file after the annotation type or the implementation class.

### 13.2. SPI content is not an FQCN

**Incorrect:**

```text
InspectProcessor
tutorial/processing/InspectProcessor.class
tutorial.processing.InspectProcessor.java
```

**Correct:**

```text
tutorial.processing.InspectProcessor
```

Remember to double-check against the package declaration in `InspectProcessor.java`.

### 13.3. Resource missing from the artifact

You created the file correctly in the source tree but forgot to copy it, or the plugin packaged the file into the wrong folder. Inspect with `jar --list` and look for the exact entry `META-INF/services/javax.annotation.processing.Processor`.

### 13.4. Provider class does not exist yet

The compiler finds the SPI file but cannot find the provider class because it has not been compiled yet, failed to compile, or the JAR did not package the class. Compile the processor first, then copy the resource. Verify the exact entry `tutorial/processing/InspectProcessor.class` in the output/JAR.

### 13.5. Implementation does not implement the right interface or cannot be instantiated

The provider must implement `javax.annotation.processing.Processor` and be loadable/instantiable. A non-public class, missing suitable constructor, abstract class, or missing dependency can cause service loading to fail.

### 13.6. Confusing compile classpath with processor path

`Catalog` sees the annotation API, but the processor implementation is not on `-processorpath`, so there is no provider for the compiler to run. Configure both properly, including any dependencies the provider needs.

### 13.7. Annotation processing is not enabled

` -proc:none` disables processing. When upgrading the JDK or switching build tools, do not assume any processor on the classpath will run automatically. Use `-proc:full` or an appropriate supported processor selection mechanism.

### 13.8. Wrong @SupportedAnnotationTypes

`@SupportedAnnotationTypes("tutorial.annotations.Inspect")` must specify the exact annotation type. Writing `"InspectProcessor"` or a name without a package will not register the intended annotation in this example.

### 13.9. Provider is loaded but no annotated elements exist in the round

The processor may be loaded yet fail to find `@Inspect` on the elements javac passes into the processing round. Check that the right source is being compiled, verify the annotation type/package, `RoundEnvironment`, and processing rounds; note that code may generate additional sources across multiple rounds.

### 13.10. Confusing a retention issue with an SPI issue

`@Retention(SOURCE)` does not prevent a processor from handling an annotation at compile time. Nor does `@Retention(RUNTIME)` cause javac to automatically invoke a processor. Retention governs **how long metadata is retained across phases**, whereas service registration governs **how the processor implementation is discovered**.

## 14. Registering SPI in the Java Module System

The main commands in this article rely on the **classpath and processor path**. If you place the processor in a **named Java module**, the Java Platform Module System (JPMS) also supports declaring the provider in `module-info.java`:

```java
module tutorial.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with tutorial.processing.InspectProcessor;
}
```

The snippet above **illustrates the module service-providing mechanism**, not a complete `module-info.java` for the classpath demo project. If you split the annotation API and processor into separate modules, you will need to design appropriate `requires`/`exports`.

Concepts to distinguish:

- `META-INF/services/javax.annotation.processing.Processor` is the way to register a provider in the **JAR/classpath SPI** ecosystem.
- `provides ... with ...` is the service registration syntax for a named module.
- `--processor-module-path` has a module-path processor lookup mechanism, which differs from `-processorpath`.
- Do not assume a traditional SPI file replaces all `provides` declarations when using named-module resolution.

This lesson uses the common and straightforward approach: **classpath/processor path + META-INF/services**.

## 15. Execution privileges and build security

An annotation processor is **code that executes on the build machine inside the compiler tool process**, not merely harmless metadata. When the compiler discovers a provider from a dependency, it can load and run the processor's code during the build.

Therefore:

1. Use processor artifacts only from trusted sources; control their versions like any other critical build dependency.
2. Do not inadvertently put untrusted JARs on the processor path.
3. Configure the processor path **explicitly and reproducibly** on developer/CI machines.
4. Understand that a processor can read sources, emit diagnostics, create files through `Filer`, and typically runs across multiple rounds.
5. Do not assume `SOURCE` retention restricts a processor's capabilities; retention does not sandbox code.
6. When a processor generates source code, clearly specify the output directory and conditions to avoid generating duplicate files.
7. Use `Messager` and language model APIs to report errors accurately, avoiding arbitrary modifications to user source files.
8. Check the compile task and the JDK used on CI, as upgrading the JDK can change default choices regarding processing.

A syntactically valid SPI configuration does not prove that every processor is safe; the provider code itself and its dependencies must be managed.

## 16. Self-check exercises

### Exercise 1 — File name and content

You write a processor `com.example.tools.CheckProcessor`. What must the SPI file be named and what line must it contain?

**Answer:** file `META-INF/services/javax.annotation.processing.Processor`, content `com.example.tools.CheckProcessor`.

### Exercise 2 — Class is present but SPI is missing

A JAR contains `InspectProcessor.class` but does not contain `META-INF/services/javax.annotation.processing.Processor`. Without `-processor`, will the service discovery approach in this article automatically find the provider name from that class?

**Answer:** no. You must declare the provider properly in the service file, or use `-processor` to specify the implementation.

### Exercise 3 — App compiles but NOTE is missing

`Catalog.class` is created, but the line `Note: InspectProcessor: Catalog -> catalog` is missing. List three causes.

**Hint:** annotation processing is disabled; the JAR is on the compile classpath but not added to the processor path; the SPI resource is incorrect/missing; `@SupportedAnnotationTypes` is declared incorrectly; the processor could not be loaded.

### Exercise 4 — SOURCE retention

Why is `@Inspect` with `SOURCE` retention still visible to the processor at compile time, yet unreadable via Reflection after the build?

**Answer:** an annotation processor processes metadata in the compile-time model; `SOURCE` does not retain the annotation usage to the class file/runtime.

### Exercise 5 — Inspecting the JAR

After packaging the processor JAR, which command do you use to verify that the SPI file is actually at the archive root?

**Answer:** `jar --list --file build/inspect-processor.jar`. Check for the entry `META-INF/services/javax.annotation.processing.Processor`.

### Exercise 6 — Explicit specification

The command with `-processor tutorial.processing.InspectProcessor` runs, but the `-proc:full` command relying on discovery does not. What should you check first?

**Answer:** the service file, provider FQCN content, packaged resources, processor path, and processor selection mode. The implementation already has proof that it runs when specified directly.

### Exercise 7 — Disabling the processor

Add `-proc:none` when compiling the application; will any NOTE generated by the processor still appear?

**Answer:** no. The compiler does not run processors when processing is disabled, even though `Catalog` can still compile if the code is valid.

### Exercise 8 — Multiple providers

An SPI file has two FQCNs, but one provider does not exist. Why is this not a valid way to register a processor “in reserve”?

**Answer:** the service loader may attempt to load every listed provider and fail on the non-existent provider. Declare only implementations that actually exist in the artifact/path.

## 17. Final checklist

1. `InspectProcessor` is a public class implementing `Processor` (directly or via `AbstractProcessor`) and is instantiable.
2. `@SupportedAnnotationTypes` accurately declares the annotation type supported by the processor.
3. The SPI file has the exact name **`META-INF/services/javax.annotation.processing.Processor`**.
4. The line in the SPI file is the **FQCN of the provider class**, not the annotation name, path, or JAR name.
5. The SPI file is copied/packaged at the **root of the output/JAR**, not kept inside a `resources` directory within the archive.
6. The processor class and its dependencies are on the processor path.
7. The application source sees the annotation API via the compile classpath.
8. Annotation processing is enabled by selecting a processor or `-proc:full` where appropriate.
9. The `javac` CLI invokes the processor and emits the expected diagnostic.
10. `-proc:none` disables processing to test and isolate errors.
11. `jar --list` confirms the service file and implementation class inside the artifact.
12. The build tool/IDE/CI uses the right JDK and processor configuration, without relying on automatic classpath assumptions.
13. If using JPMS, handle `module-info.java` and the processor module path separately.
14. The processor artifact is security-controlled because it is code that executes at build time.

**Conclusion:** to register an annotation processor via Java SPI, **place the `META-INF/services/javax.annotation.processing.Processor` file at the root of the processor output/JAR**, write the FQCN of the provider implementing `Processor`, allow the compiler to load the provider on the processor path, and **explicitly enable annotation processing**. `@SupportedAnnotationTypes` controls which annotation types the processor handles; the service file controls **how the processor is found**, while `-processor` allows explicit specification for testing/debugging.
