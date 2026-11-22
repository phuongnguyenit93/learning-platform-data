# Avoiding duplicate file creation, handling FilerException, and recording originating elements in Java annotation processors

## 1. Nature of the problem

When building an annotation processor under JSR 269, we can generate Java sources, class files, or resources while `javac` compiles. The object managing these outputs is `javax.annotation.processing.Filer`, accessed via `processingEnv.getFiler()`. Creating a file is not merely writing text to disk: the compiler needs to know about the new file, the identity of the new type, the processing round receiving new input sources, and the relationship to original declarations.

The most important rule: **within a single invocation of annotation processing, each output pathname/type can only be created once**. If the same generated type or path is requested to be created again within the same invocation, Filer may throw `FilerException`.

Common error example:

~~~text
error: Expected duplicate: Attempt to recreate a file for type demo.generated.SharedHello
1 error
~~~

Two situations must be separated:
- **Duplicate within the current invocation:** two annotated elements, multiple rounds, or two processors each request creating the same name; this is the typical cause of FilerException.
- **Generated file already exists from a previous build:** Filer can replace the contents of the old file when creating it for the first time in a new invocation. An old file on disk **does not automatically imply** FilerException, unless it is fed in as a compilation input or another conflict occurs.

The Java compiler treats sources/classes that are **initial inputs** as already created in “round 0”, so processors must not duplicate types corresponding to initial inputs. Filer may also report invalid names or an undetermined target module; do not diagnose every FilerException as “called twice” before reading the message.

## 2. Contract of Filer APIs

| API | Purpose | Notes |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | Creates Java source for a principal top-level type or package-info | Qualified type name; can be fed into the next processing round after the writer is closed |
| `createClassFile(name, origins...)` | Creates a JVM class file | Uses binary name; do not create both source and class for the same type in one invocation |
| `createResource(location, pkg, relativeName, origins...)` | Creates a resource in an output location | Resources also follow the no-duplicate-pathname rule and do not automatically become Java source for processing |
| `getResource(location, pkg, relativeName)` | Reads an existing resource | Not a “check and reserve” operation; do not use to bypass file creation contracts |

A good call:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.AlphaHello",
        alphaTypeElement);
~~~

This is an excerpt **inside a processor**, where `alphaTypeElement` is the actual `TypeElement` of `demo.Alpha`. The second parameter is the **originating element**, helping tooling know which source led to the output.

Using `Writer` and closing reliably:

~~~java
try (Writer writer = processingEnv.getFiler()
        .createSourceFile(fullName, sourceType)
        .openWriter()) {
    writer.write(javaSource);
}
~~~

This snippet illustrates part of a method, assuming appropriate variables and imports. `Filer` manages the new file; closing `Writer` or `OutputStream` informs the compiler that contents are complete to schedule the next round. Do not use `Files.writeString(...)` to create generated Java sources directly and expect the compiler to process them with the same metadata.

## 3. Common sources of duplicate creation

### Two inputs sharing the same output name

If source has both `Alpha` and `Beta` marked with the annotation and code runs:

~~~java
for (Element e : round.getElementsAnnotatedWith(annotation)) {
    processingEnv.getFiler()
            .createSourceFile("demo.generated.SharedHello", e);
}
~~~

then the first iteration may succeed, while the second iteration recreates the exact same name. Placing `createSourceFile` **inside a loop** is valid only when **each iteration has a distinct name**. If the output is an aggregated file, compute all data first and call Filer **once**.

### Duplicates across processing rounds

A processor can run across multiple rounds in one invocation. A source created in round 1 can be supplied as a root of round 2. If the processor calls to recreate the same name, it is still the same invocation: Filer rejects it.

### Two processors owning the same type

Processors A and B both create `demo.Generated`. Each processor may keep its own `Set<String>` and think nothing collides, yet **the compiler's shared Filer** detects the conflict. An ownership rule is required: only one processor creates each output; do not rely on processor registration order.

### Colliding with initial sources

If `demo.Generated.java` is already passed directly as an input to `javac` and a processor also creates `demo.Generated`, that is a round-0 collision. This error often happens when the generated-source directory of a previous build was mistakenly added to the main source set.

### Collisions due to name simplification

If `sales.User` and `hr.User` both generate `demo.generated.UserAdapter`, the simple name `User` is not sufficiently unique. Output names must reflect the necessary package and enclosing type; they can be generated in the original package or follow a stable qualified-name conversion convention. Do not use timestamps, random numbers, or iteration order to dodge the error.

### Resource or class/source duplicates

`createResource` also prohibits opening and creating the same pathname multiple times in one invocation. `createSourceFile` and `createClassFile` for the same type can also conflict even though the output destinations are different file kinds. Do not treat resource files as a “backdoor” to emit a Java type multiple times.

## 4. Safe design strategies

A processor should follow this sequence:

1. **Identify each input uniquely:** full package/module/type name; avoid taking only the simple name in large projects.
2. **Deterministic input → output mapping:** the same logical source must yield the same output name and valid content.
3. **Choose a generation model:** one output per element (*isolating*) or one aggregated output from multiple elements (*aggregating*).
4. **Check for conflicts before opening a writer:** store the list of planned outputs or a `Set<String>` reserved for the current processor.
5. **Create only once within the same invocation**, even across multiple rounds; do not attempt to create Java sources in the final round.
6. **Pass appropriate originating elements** to `createSourceFile`, `createClassFile`, or `createResource`.
7. **Close streams** and emit `Diagnostic.Kind.ERROR` if conflicts or I/O failures occur.
8. **Do not retry the same name after FilerException**; fix generation logic or ownership.
9. **Do not modify source/generated files via direct filesystem operations** to bypass Filer.
10. **Test clean + incremental** and test editing/deleting inputs to detect stale outputs.

A `Set<String>` prevents duplicate creation by **that processor itself**. It does not replace Filer, does not control other processors, and does not resolve module errors or invalid names.

## 5. Runnable Java 17 example: generating one file per source class

The practice lab uses:
- Annotation `demo.GenerateHello`.
- Processor `ap.HelloProcessor`.
- Two classes `demo.Alpha` and `demo.Beta`.
- `demo.App` using generated types `demo.generated.AlphaHello` and `demo.generated.BetaHello`.

Source structure:

~~~text
project/
  api/demo/GenerateHello.java
  processor/ap/HelloProcessor.java
  src/demo/Alpha.java
  src/demo/Beta.java
  src/demo/App.java
~~~

### 5.1. File api/demo/GenerateHello.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {}
~~~

`RetentionPolicy.SOURCE` does not prevent processors from observing the annotation at compile time; it only indicates the annotation does not need to be retained in the class file for runtime use.

### 5.2. File processor/ap/HelloProcessor.java

~~~java
package ap;

import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    private final Set<String> reservedNames = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) return true;

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateHello");
        if (annotation == null) return false;

        for (Element e : round.getElementsAnnotatedWith(annotation)) {
            if (!(e instanceof TypeElement type)) continue;

            String shortName = type.getSimpleName() + "Hello";
            String fullName = "demo.generated." + shortName;

            if (!reservedNames.add(fullName)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Duplicate generated type: " + fullName, e);
                continue;
            }

            try (Writer out = processingEnv.getFiler()
                    .createSourceFile(fullName, type).openWriter()) {
                out.write("package demo.generated; public final class " + shortName
                        + " { public static String text() { return \""
                        + type.getSimpleName() + "\"; } }");
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Filer name conflict: " + ex.getMessage(), e);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot write generated source: " + ex, e);
            }
        }
        return true;
    }
}
~~~

Points to understand:
- `reservedNames` holds the names that **this processor instance has already planned to create** in the current invocation.
- `fullName` has package `demo.generated` and a deterministic class name. The sample limits itself to top-level classes `Alpha`, `Beta` in package `demo` with distinct simple names. In production with multiple packages/nested types, change this rule to avoid collisions.
- `createSourceFile(fullName, type)` passes the exact originating element.
- `try-with-resources` closes the writer; no need to manually manipulate the generated directory.
- `catch (FilerException)` precedes `catch (IOException)` because FilerException extends IOException.
- `Messager.printMessage(..., e)` locates diagnostics at the **source element**, a distinct role from Filer's originating element.
- `return true` means **claiming the annotation**, not synonymous with processing success. Error diagnostics still cause compilation to fail.
- Source string literal concatenation here is tested with the two names `Alpha`/`Beta`; with arbitrary input data, generators must escape Java string literals and validate identifiers.

### 5.3. File src/demo/Alpha.java

~~~java
package demo;

@GenerateHello
public final class Alpha {}
~~~

### 5.4. File src/demo/Beta.java

~~~java
package demo;

@GenerateHello
public final class Beta {}
~~~

### 5.5. File src/demo/App.java

~~~java
package demo;

import demo.generated.AlphaHello;
import demo.generated.BetaHello;

public final class App {
    public static void main(String[] args) {
        System.out.println(AlphaHello.text() + "/" + BetaHello.text());
    }
}
~~~

The two generated classes do not yet exist in handwritten source, yet will be processed by the compiler in the same invocation with the processor.

## 6. Compiling and observing rounds

Using JDK 17 or higher, run in directory `project` under Bash:

~~~bash
mkdir -p api-classes processor-classes classes generated

javac --release 17 -encoding UTF-8 \
  -d api-classes api/demo/GenerateHello.java

javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/HelloProcessor.java

javac --release 17 -encoding UTF-8 \
  -cp api-classes \
  -processorpath processor-classes \
  -processor ap.HelloProcessor \
  -XprintRounds -s generated -d classes \
  src/demo/Alpha.java src/demo/Beta.java src/demo/App.java

java -cp classes demo.App
~~~

In PowerShell/cmd, each `javac` command can be placed on a single line instead of using Bash's `\` line continuation. The example was tested with `javac 24.0.2 --release 17`, yielding compile **exit code 0**. Main rounds:

~~~text
Round 1:
    input files: {demo.Alpha, demo.Beta, demo.App}
    annotations: [demo.GenerateHello]
    last round: false
Round 2:
    input files: {demo.generated.AlphaHello, demo.generated.BetaHello}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Indentation and order of info may vary by compiler. Round 2 sees sources generated in round 1 after writers close. The final round has `processingOver()` equal to `true` and is not an opportunity to create a source expecting a subsequent round.

**Exact stdout:**

~~~text
Alpha/Beta
~~~

Important outputs:

~~~text
generated/demo/generated/AlphaHello.java
generated/demo/generated/BetaHello.java
classes/demo/Alpha.class
classes/demo/Beta.class
classes/demo/App.class
classes/demo/generated/AlphaHello.class
classes/demo/generated/BetaHello.class
~~~

Here `-s generated` is **source** output and `-d classes` is **bytecode** output. The annotation API is only needed on the compile classpath for `@GenerateHello` sources; due to SOURCE retention and the app not using the annotation at runtime, the sample app runs with `-cp classes`.

## 7. Negative experiment: creating a duplicate name

Also create file `processor/ap/BadProcessor.java`, written intentionally **wrong** to observe FilerException:

~~~java
package ap;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class BadProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver() || annotations.isEmpty()) return true;

        for (var ignored : round.getRootElements()) {
            try (Writer out = processingEnv.getFiler()
                    .createSourceFile("demo.generated.SharedHello").openWriter()) {
                out.write("package demo.generated; public class SharedHello {}");
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Expected duplicate: " + ex.getMessage());
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString());
            }
        }
        return true;
    }
}
~~~

It requests creating `demo.generated.SharedHello` multiple times within one round. Compile only `Alpha` and `Beta` in the negative test; `App` depends on other generated names that BadProcessor does not create.

~~~bash
mkdir -p bad-classes bad-generated

javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/BadProcessor.java

javac --release 17 -encoding UTF-8 \
  -cp api-classes \
  -processorpath processor-classes \
  -processor ap.BadProcessor \
  -s bad-generated -d bad-classes \
  src/demo/Alpha.java src/demo/Beta.java
~~~

In the test on JDK 24 using `--release 17`, the confirmed diagnostic:

~~~text
error: Expected duplicate: Attempt to recreate a file for type demo.generated.SharedHello
1 error
~~~

The build returns **exit code 1**. Even though `SharedHello.java` may have been written by the first creation, outputs from a failed compile run must not be treated as valid artifacts to ship in the product.

If you truly want **one aggregated class**, collect data from annotated elements and call `createSourceFile` once with appropriate originating elements. If you want **one class per source**, assign distinct names such as `AlphaHello` and `BetaHello`.

## 8. What is recording originating elements?

Filer's file-creation methods take parameter `Element... originatingElements`. These are **the source declarations causing the output to be created**; for example:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.AlphaHello",
        alphaTypeElement);
~~~

This information is a **hint for build infrastructure**. A build tool supporting incremental annotation processing can link generated outputs to the sources that created them. When sources change or are deleted, the build tool knows the recompilation scope and which outputs to clean.

Do not confuse:
- **Originating element:** relevant `TypeElement`, `PackageElement`, or `ModuleElement`; used for dependency tracking.
- **Diagnostic element:** element passed to `Messager.printMessage(..., element)`, used to display errors at the right location.
- **`@Generated` annotation:** metadata that a generator may actively write into source; **not automatically inserted** by passing an originating element.
- **File name:** a qualified name string that Filer uses to identify the output; does not replace originating elements.

Example of an aggregated output depending on two types:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.Registry",
        alphaTypeElement,
        betaTypeElement);
~~~

The snippet above only illustrates the API signature inside a processor, not a standalone program. It indicates both inputs contribute to creating the output. **Do not declare a false origin** just to make a build run faster.

Omitting originating elements does not necessarily cause a compiler error, yet may force incremental builds to rebuild a wider scope or lack information determining output–input relationships. On non-incremental systems, this hint may go unused.

## 9. Isolating and aggregating: applying accurately with Gradle

Gradle supports incremental annotation processing for processors adhering to dedicated contracts. Two common types:

| Type | How output is computed | Example |
| --- | --- | --- |
| **Isolating** | Each output depends on one appropriate element | `Alpha` → `AlphaHello`; `Beta` → `BetaHello` |
| **Aggregating** | Output depends on a set of multiple elements | Aggregating multiple `@Service` elements into one `ServiceRegistry` |

For an isolating processor, Gradle requires each output generated via Filer **to have exactly one originating element** and the processor to obey other incremental rules. Passing 0 or multiple elements may force Gradle to recompile more broadly. For aggregating, an output can depend on multiple declarations; you cannot assign an arbitrary single origin and claim the output is isolating.

The processor JAR can register the incremental category in:

~~~text
META-INF/gradle/incremental.annotation.processors
~~~

Example content:

~~~text
ap.HelloProcessor,isolating
~~~

**Register this only if the actual implementation satisfies the isolating rules of the Gradle version in use.** The sample restricts inputs to `demo.Alpha`, `demo.Beta`; if applying to multiple packages/nested types, first fix the naming policy so every valid source has its own output and does not inspect other types in a way that violates isolating.

Incremental contracts also involve how the processor accesses elements, creates outputs, unstable data, and dependency metadata. Do not use metadata to trick the build: it can produce stale artifacts while clean builds still work.

## 10. Error handling in processors: catch accurately and report sufficient context

`FilerException` **extends `IOException`**, so it must be caught separately first:

~~~java
try (Writer out = processingEnv.getFiler()
        .createSourceFile(fullName, origin).openWriter()) {
    out.write(generatedSource);
} catch (FilerException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Conflicting output " + fullName + ": " + ex.getMessage(),
            origin);
} catch (IOException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "I/O generating " + fullName + ": " + ex.getMessage(),
            origin);
}
~~~

This is a **processor fragment**, assuming `fullName`, `origin`, and `generatedSource` already exist. Errors in `openWriter`, `write`, or `close` all require investigation. Messages should include the output name and origin, not merely a meaningless stack trace.

Do not:
- Catch `FilerException`, ignore it, and pretend generation succeeded.
- Delete the file and retry the same name within the same invocation.
- Assign random output names to dodge collisions.
- Overwrite generated Java sources using `java.nio.file.Files` bypassing Filer.
- Downgrade mandatory conflicts to warnings if missing classes will break the build.
- Lump every exception into “duplicate” when the actual cause is permissions, modules, or I/O errors.

**Emitting `Diagnostic.Kind.ERROR`** is the appropriate choice when a required output fails to be created properly. Errors positioned at the source element help users know which declaration caused the conflict. For conflicts between processors, also inspect processor paths/service descriptors and ownership of generated names.

## 11. Multi-round lifecycle and processor state

A processor can receive multiple `process` invocations across rounds within the **same invocation**. Distinguish:
- `RoundEnvironment.processingOver() == false`: still in processing; generated sources with closed writers can trigger subsequent rounds.
- `processingOver() == true`: final round; **do not rely on creating sources here** for the compiler to run an extra round.
- `RoundEnvironment.errorRaised()`: an error was raised in the previous round; processors can use it to adjust handling, not as the sole indicator determining failure.
- `return true` of `process`: processor claims those annotation types in that round; **not** a boolean reporting all files were created successfully.

`Set<String> reservedNames` in the example processor persists across rounds of **a single compilation**. Do not arbitrarily hold lists of “already created” files in static caches across builds: compiler daemons, incremental builds, and JDK toolchains can cause stale state reuse.

Avoid recursive generation without termination conditions. If generated source also carries annotations the processor handles, the next round may create additional sources and prolong processing unnecessarily. Naming rules and generation state must be designed to always terminate.

## 12. Generating a shared registry properly

If the goal is a single `Registry` file from multiple annotated classes, choose the **aggregating** model:

1. Collect info on annotated types and corresponding originating elements.
2. Sort names in a deterministic order for reproducible outputs.
3. Choose a point when sufficient data is collected and processing is **not yet in the final round**.
4. **Call Filer exactly once** for `Registry`, passing the genuinely relevant origins.
5. Close the writer and let the compiler pick up the generated file.
6. Register aggregating metadata with the build tool when the implementation satisfies the contract.

Pseudocode illustrating the collection part, not a complete standalone runnable source:

~~~java
Map<String, TypeElement> contributors = new TreeMap<>();
for (Element e : round.getElementsAnnotatedWith(serviceAnnotation)) {
    if (e instanceof TypeElement type) {
        contributors.put(type.getQualifiedName().toString(), type);
    }
}

// After having sufficient inputs and before the final round:
// Element[] origins = contributors.values().toArray(new Element[0]);
// JavaFileObject file = filer.createSourceFile("demo.generated.Registry", origins);
// try (Writer out = file.openWriter()) { ... }
~~~

If another processor can generate additional annotated types in later rounds, design the “sufficient inputs collected” moment carefully. Do not recreate `Registry` in every round; Filer will reject it. For complex pipelines, splitting per-type generation and aggregation into separate tasks can be easier to maintain.

Similarly, a service descriptor `META-INF/services/...` is **one resource**. Do not create that resource once per annotated class; aggregate provider names and write one file in deterministic order.

## 13. Stale outputs and incremental builds

A good verification cycle includes:

| Scenario | What to verify |
| --- | --- |
| Clean compile | Each output is created once, with right name and right contents |
| Rebuild without editing inputs | No FilerException from round logic, no wrong old files published |
| Edit `Alpha.java` | Related outputs updated properly; independent of element order |
| Delete `Alpha.java` | Output `AlphaHello` cleaned properly by build tool when incremental support operates |
| Add `Gamma.java` | New output exists without colliding with existing generated names |
| Two types with same simple name | Naming policy distinguishes fully, or reports duplicate clearly |
| Two processors create same name | Build fails with message identifying who owns the output |
| Generated source has syntax error | Compiler reports error, does not publish incomplete or stale artifacts |

**Note:** an old generated file still lingering after a failed compile does not prove the current invocation succeeded. Inspect the exit code and clean builds, rather than just glancing at a file in the output directory.

If generated source is **mistakenly added to the initial Java input set** while the processor still generates it, the failure differs from files merely remaining on disk from an old build. Fix the source set/compile task so the build tool manages outputs; do not commit generated copies into main source directories where the processor also duplicates them.

## 14. Java modules and output names

In a JPMS environment, Filer may need to determine the **target module** of generated sources. Some module-aware configurations allow names prefixed with the module:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.module/demo.generated.AlphaHello",
        sourceType);
~~~

This is a **snippet for module-aware environments**, valid only if the target module actually exists and the compiler supports writing output for that module. Do not copy verbatim into ordinary classpath applications lacking this module.

`FilerException` can report an unknown module or an unwritable target module even before any filename duplication happens. Check module path, module descriptor, `-s`, `-d`, and module names; a `Set<String>` cannot fix those errors.

The **processor loading** path (e.g., `--processor-module-path`) is not synonymous with the module of the **generated class**. Distinguish the processor module, application module, and Filer target module.

## 15. Maven, Gradle, and output ownership

### Maven

Maven Compiler Plugin typically manages generated Java sources in directories such as `target/generated-sources/annotations`. Exact paths depend on plugins and specific configuration. Scenarios to check:
- Are multiple compiler executions creating the same output name?
- Are generated sources included as initial sources in the same invocation causing a round-0 collision?
- Are processor artifacts or plugin versions declared redundantly?
- Are source and output directories shared across modules?

Use `mvn clean compile` to verify a clean baseline, then fix plugin/source path configurations according to the build mechanism instead of deleting files mid-processing. For code generators needing incremental tracking, inspect plugin/compiler support and origins data.

### Gradle

Example Groovy DSL snippet:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'example:annotation-api:1.0'
    annotationProcessor 'example:processor:1.0'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

The `example:...` coordinates are **illustrative**, not confirmed existing artifacts. `annotationProcessor` configures the dependency path to run processors; `compileOnly` is suitable when the annotation API is only needed at compile time. Generated sources must be managed by the JavaCompile task.

Run `./gradlew clean compileJava` (Windows: `gradlew.bat clean compileJava`) to establish a baseline, then test incremental builds after editing/deleting sources. If only clean builds work while incremental builds fail, focus on checking origins, isolating/aggregating metadata, and output ownership; do not mark a processor isolating when generated data depends on multiple unrelated elements.

## 16. Ordered FilerException diagnostic workflow

1. Read the **full message**: type/file name, module, location, specific cause.
2. Record the compiler JDK and **actual list of processors** loaded in the invocation.
3. Check flags `-processorpath`, `--processor-module-path`, `-s`, `-d`, source paths, and modules.
4. Enable `-XprintRounds` / `-XprintProcessorInfo` to see round order and invoked processors.
5. Log the **output name before each Filer call**, alongside originating type and round, to pinpoint the second call.
6. Verify whether conflict stems from the **same loop, prior round, another processor, or round-0 input**.
7. Inspect naming scheme: packages, nested classes, modules, and collisions from simple names.
8. Distinguish `FilerException` from other `IOException`s; check module targets, permissions, and path validity.
9. Confirm writers are closed and processing does not emit sources in the final round.
10. Check originating elements and incremental rules of the build tool.
11. Run a clean build to separate logic bugs from stale outputs; then test incremental.
12. Fix the root cause and rerun end-to-end, without suppressing or retrying conflicts.

## 17. Self-check questions

**1.** In the same round, two annotated classes both call `createSourceFile("demo.Generated")`. What happens on the second call?  
**Answer:** `FilerException` may occur because the same output was already created in the invocation.

**2.** A generated file from the previous build exists on disk. Will a new build recreating that name definitely error?  
**Answer:** No. Distinguish old files on disk, round-0 inputs, and duplicate creation within the new invocation.

**3.** Why use `createSourceFile(fullName, type)` instead of only `createSourceFile(fullName)`?  
**Answer:** To pass the originating element so tooling links the output to the source that caused it.

**4.** Can a registry file depending on 20 source types be marked isolating with one arbitrary origin?  
**Answer:** No. It is an aggregating case and must declare tracking matching the true relationship.

**5.** Can `IOException` be caught before `FilerException`?  
**Answer:** No. `FilerException` is a subclass of `IOException`; catching the subclass after the superclass is unreachable.

**6.** A processor has a `Set<String>` yet still hits a duplicate; what should be checked?  
**Answer:** Another processor, round-0 source inputs, resource/source/class collisions, module/path validity.

**7.** Does `createResource` allow writing a service descriptor repeatedly multiple times?  
**Answer:** Do not assume so; Filer tracks resource pathnames within an invocation.

**8.** Are `@Generated` and an originating element the same thing?  
**Answer:** No. The annotation can be written inside generated source; an originating element is a metadata hint passed to Filer.

**9.** Should sources be created in the final round expecting a subsequent round?  
**Answer:** No. `processingOver()==true` indicates processing is about to finish.

**10.** If an error states the target module is unwritable, does it definitely mean two duplicate creation calls occurred?  
**Answer:** No. Check the compiler's module/output configuration.

## 18. Authoritative references

- [Java SE 17 Filer API: creation rules, originating elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [Java SE 17 FilerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html)
- [Java SE 17 RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Gradle Java plugin: incremental annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Oracle javac command (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Conclusion:** A reliable processor must control **output names**, **creation timing**, and **output origins**. Use Filer to generate files, check duplicates inside the processor, respect FilerException across processors/rounds, pass accurate originating elements, and test clean/incremental builds. Avoid swallowing errors or manually editing generated files just to make one compile pass.
