# Generating Deterministic Output and Coordinating Multiple Annotation Processors in Java

## 1. The Problem: Identical Input Must Produce Identical Output

With annotation processing (JSR 269), `javac` can load multiple processors to validate declarations, emit diagnostics, and generate Java code or resources. If two builds use the same source code, annotations, configuration, JDK, and dependencies, yet a processor generates two files with different contents **for no business reason**, the system becomes very difficult to test and cache effectively.

For example, a processor scans classes annotated with `@ServiceEntry` and generates a list:

~~~text
demo.AlphaService
demo.ZebraService
~~~

If another build arbitrarily reverses the order of the two lines, even though the input has not changed, the file contents still differ. Snapshot tests report changes; hash-based caches may be invalidated; and diffs make it harder for reviewers to spot real modifications.

**Deterministic output (deterministic generation)** means that given the same set of inputs and normalization rules, the processor produces the same file names, bytes, record order, and source code structure.

**Coordinating multiple processors** means that a compilation session can include multiple processors with different responsibilities without depending on arbitrary execution order, missing sources generated in later rounds, or contending to write the same file.

These two goals are closely related: a processor that generates deterministic output must control **data ordering**, **write timing**, and **output ownership**.

## 2. Three Levels of Determinism to Distinguish

### 2.1. Deterministic Generated File Content

Given the same annotated elements and declared configurations, a processor must generate the exact same text. Common sources of non-determinism include:

- Iterating over a `HashMap`, `HashSet`, or `Element` set without a guaranteed order.
- Inserting timestamps, `UUID.randomUUID()`, random numbers, or `System.identityHashCode` into the file.
- Using absolute paths, usernames, or build machine environment values when those values are not business inputs.
- Leaving encoding or newlines machine-dependent, or using `Locale.getDefault()` for machine-readable content.
- Writing annotation elements in an incidental order returned by Reflection or the model API.
- Using an object's `toString()` as a canonical format even though it has no stability contract.

The solution is to transform inputs into **normalized values**, sort by a meaningful key, use an explicit charset and line ending, and avoid adding information that changes between builds unless it is truly necessary.

### 2.2. Deterministic Generated File Names and Paths

A processor must derive the output name from a stable key, such as the qualified type name: `demo.Alpha` generates `demo.AlphaGenerated`. Do not use iteration order as a suffix like `Generated1`, `Generated2` if that order is not normalized.

Names must avoid collisions: two different inputs must not both request `Filer.createSourceFile("demo.SameName")`. For an aggregated resource, designate a **single** processor as the owner of `META-INF/demo/index.txt`.

### 2.3. Reproducible Entire Artifact

Having deterministic bytes in generated files **does not by itself prove** that the entire build or JAR is reproducible. `.class` files, stored files, archive entry timestamps/order, classpath, compiler flags, and dependency versions also affect the final artifact. Separate verification is required if the goal is two byte-for-byte identical JARs.

## 3. Relevant Java APIs

Most annotation processors extend `javax.annotation.processing.AbstractProcessor`, whose root contract is `javax.annotation.processing.Processor`.

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Analyze the model and generate output.
    return true;
}
~~~

This is only a **fragment**; it requires a processor class and appropriate imports.

| API | Role |
| --- | --- |
| `Processor` | Contract for `init`, supported annotation types/options/source, `process`, and claiming |
| `AbstractProcessor` | Base class that pre-implements part of the contract and holds `processingEnv` |
| `ProcessingEnvironment` | Compiler services such as `getFiler()`, `getMessager()`, `getElementUtils()`, and `getTypeUtils()` |
| `RoundEnvironment` | Root elements, annotation occurrences, and state of each processing round |
| `Filer` | Creates source/class/resource files within the compiler-managed output area |
| `Messager` | Emits `Diagnostic.Kind.ERROR`, `WARNING`, and `NOTE` messages with location information |
| `TypeElement` / `Element` | Java declaration model, not runtime `Class<?>` |
| `TypeMirror` / `Types` | Type representation and compile-time type relationship checks |

In Java 17, these APIs belong to the `java.compiler` module, with the standard package name **`javax.annotation.processing`**, which did not change to `jakarta.annotation.processing`.

`@SupportedAnnotationTypes` specifies the annotation types that the processor handles; `@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares support for the Java 17 language version. Those two annotations **do not activate the processor on their own**: the compiler still needs to load it via `-processor`, service registration, or build tool configuration.

### Claiming Is Not Success Control

Returning `true` from `process(...)` means the processor **claims** the assigned annotation types in that round; returning `false` means not claiming them, giving other processors a chance to process them. Do not use `return false` to report business errors. Use `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)` instead.

If two processors handle **the same annotation type**, having one processor claim it can prevent the other processor from receiving that annotation under the same dispatch mechanism. The design must be intentional; do not rely on the assumption that two given processors will be invoked in a desired order.

## 4. Canonicalizing Ordering, Characters, and Names

### 4.1. Sorting Before Writing

`RoundEnvironment.getElementsAnnotatedWith(...)` returns a set of elements, not a list with an output order tailored for you.

Illustrative snippet **inside a processor**:

~~~java
List<String> names = new ArrayList<>();

for (Element element : roundEnv.getElementsAnnotatedWith(MyMarker.class)) {
    if (element instanceof TypeElement type) {
        names.add(type.getQualifiedName().toString());
    }
}

names.sort(Comparator.naturalOrder());

for (String name : names) {
    writer.write(name);
    writer.write(10); // LF
}
~~~

This fragment requires `MyMarker`, `writer`, and the corresponding imports. `TypeElement.getQualifiedName()` is better than `getSimpleName()` when you need to distinguish classes with the same simple name across different packages. If the business logic only needs a set of unique names, `TreeSet<String>` can combine **sorting and deduplication**. However, if duplicates carry business meaning, do not use a Set just to remove them.

### 4.2. Fixed Byte Formatting

Explicitly use `StandardCharsets.UTF_8` and LF newlines:

~~~java
try (Writer writer = new OutputStreamWriter(
        file.openOutputStream(), StandardCharsets.UTF_8)) {
    writer.write("alpha");
    writer.write(10); // LF character
    writer.write("zebra");
    writer.write(10);
}
~~~

This is a fragment assuming a `FileObject file`. Writing `10` via `Writer.write(int)` is a clear way to demonstrate LF newline output. Do not use `System.lineSeparator()` if the format requires LF across all machines.

If generating Java string literals from arbitrary annotation values, you must properly **escape** `"`, backslashes, control characters, and relevant Unicode cases; do not concatenate user strings directly into source code and expect it to always be valid Java.

### 4.3. One Output Has Only One Owner

`Filer` is not a shared mutable file system where the last processor is allowed to overwrite a file. If two processors both try to create `META-INF/demo/index.txt`, a `FilerException` or an error diagnostic may occur. The solution is to assign a single **aggregator processor** to write that file; producers either contribute metadata through the compiler model or each producer writes its own resource under its own namespace.

## 5. Coordinating via Processing Rounds, Not Execution Order

The JSR 269 model allows source files generated by a processor in one round to be picked up by the compiler in the **next round**.

~~~text
First round:
    @Seed on Alpha and Zebra
             |
             v
    ProducerProcessor generates AlphaGenerated and ZebraGenerated
             |
             v
Next round:
    @GeneratedItem on the new classes
             |
             v
    IndexProcessor collects qualified names
             |
             v
Final round:
    IndexProcessor writes the sorted resource without generating additional Java source
             |
             v
Application reads index.txt at runtime
~~~

This is a coordination protocol with **clear boundaries between rounds**. There is no need to assume processor B runs immediately after A within the same round. B reads the annotated elements from the compiler's `RoundEnvironment` instead of opening a file that A might still be writing.

When output needs to be aggregated across **multiple rounds**, the aggregator should accumulate state over the processor's lifecycle and finalize at the appropriate stage. The **final round** (`processingOver() == true`) is suitable for finalizing a **resource** that does not require further compiler processing, but **it is not the time to generate new Java sources and expect the compiler to run another round**.

## 6. Java 17 Demo: Two Processors Cooperating to Generate a Deterministic Resource

This complete example consists of five initial files, uses JDK 17+, and requires no third-party libraries.

~~~text
src/
  demo/
    Seed.java
    GeneratedItem.java
    ProducerProcessor.java
    IndexProcessor.java
    Demo.java
~~~

Goal: `ProducerProcessor` generates source files for two input classes; `IndexProcessor` receives the new classes in the next round and creates the file `META-INF/demo/index.txt`. The file is sorted by qualified name, independent of declaration order in the source.

### 6.1. `src/demo/Seed.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Seed {
}
~~~

`@Seed` is recognized by processor A at compile time. `SOURCE` is sufficient; the runtime does not need to read this annotation.

### 6.2. `src/demo/GeneratedItem.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GeneratedItem {
}
~~~

Intermediate annotation allowing B to detect Java sources generated by A. This is a **signal between two processors via the compiler's source model**, not a runtime event.

### 6.3. `src/demo/ProducerProcessor.java`

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
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

@SupportedAnnotationTypes("demo.Seed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ProducerProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        List<TypeElement> inputs = new ArrayList<>();

        for (Element element : roundEnv.getElementsAnnotatedWith(Seed.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind()
                            != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Seed requires a top-level class",
                        element);
                continue;
            }
            inputs.add((TypeElement) element);
        }

        inputs.sort(Comparator.comparing(
                type -> type.getQualifiedName().toString()));

        for (TypeElement type : inputs) {
            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();

            if (pkg.isEmpty()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Seed requires a named package",
                        type);
                continue;
            }

            String simple = type.getSimpleName().toString();
            String generated = simple + "Generated";
            String name = pkg + "." + generated;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(name, type);

                try (Writer writer = new OutputStreamWriter(
                        source.openOutputStream(), StandardCharsets.UTF_8)) {
                    writer.write("package " + pkg + ";");
                    writer.write(10);
                    writer.write("@demo.GeneratedItem");
                    writer.write(10);
                    writer.write("public final class " + generated + " {");
                    writer.write(10);
                    writer.write("    private " + generated + "() {}");
                    writer.write(10);
                    writer.write("}");
                    writer.write(10);
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + name + ": " + error.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

Mechanism:

1. `@SupportedAnnotationTypes("demo.Seed")` ensures A only processes its assigned metadata type.
2. The processor checks for a **top-level class** before constructing the name to avoid nested type cases not supported by the demo's simple rule.
3. The list of `TypeElement` instances is sorted by qualified name.
4. `getElementUtils().getPackageOf(type)` retrieves the package from the compile-time Java model.
5. `Filer.createSourceFile(name, type)` creates a single source file by qualified name; `type` is the *originating element* providing provenance for the toolchain.
6. The generated source code carries the `@demo.GeneratedItem` annotation so B can pick it up in the next round.
7. The writer is closed via try-with-resources and uses fixed UTF-8 and LF.
8. File creation errors are reported via `Messager`, without attempting retries or overwrites.

In this demo, the inputs are the classes `Alpha` and `Zebra`, so the two generated names are `demo.AlphaGenerated` and `demo.ZebraGenerated`. If the class `AlphaGenerated` already exists from another source or another processor owns the same name, creating the new file will cause a conflict; that is an error that must be fixed in the naming policy.

### 6.4. `src/demo/IndexProcessor.java`

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GeneratedItem")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class IndexProcessor extends AbstractProcessor {
    private final SortedSet<String> names = new TreeSet<>();
    private boolean written;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver()) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(GeneratedItem.class)) {
                if (element.getKind() == ElementKind.CLASS) {
                    TypeElement type = (TypeElement) element;
                    names.add(type.getQualifiedName().toString());
                }
            }
            return true;
        }

        if (!written && !roundEnv.errorRaised()) {
            written = true;
            try {
                FileObject file = processingEnv.getFiler().createResource(
                        StandardLocation.CLASS_OUTPUT,
                        "",
                        "META-INF/demo/index.txt");

                try (Writer writer = new OutputStreamWriter(
                        file.openOutputStream(), StandardCharsets.UTF_8)) {
                    for (String name : names) {
                        writer.write(name);
                        writer.write(10);
                    }
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate index: " + error.getMessage());
            }
        }

        return true;
    }
}
~~~

`IndexProcessor` performs **aggregating**:

- Supports only `@GeneratedItem`, so it does not compete with A to claim `@Seed`.
- Accumulates names across **multiple rounds** in a `TreeSet` to maintain ordering and avoid adding the same qualified name multiple times.
- Creates the **resource** only when `processingOver()`; resources do not require further compilation by the Java compiler.
- `written` prevents the write logic from being invoked twice if the implementation is later extended.
- `errorRaised()` is used as a policy to skip the index in the final round when compilation has already produced an earlier error diagnostic.
- B does **not** look for the files A just generated by reading the build directory. Instead, it uses source annotations via `RoundEnvironment`.

Note: using `TreeSet` here is correct because the index stores **unique class names**. If the business requirements need to store multiple distinct records with the same name, a key and conflict resolution mechanism must be defined rather than silently deduplicating them.

### 6.5. `src/demo/Demo.java`

~~~java
package demo;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

@Seed
class Zebra {
}

@Seed
class Alpha {
}

public class Demo {
    public static void main(String[] args) throws Exception {
        String resource = "META-INF/demo/index.txt";

        try (InputStream in =
                Demo.class.getClassLoader().getResourceAsStream(resource)) {
            if (in == null) {
                throw new IllegalStateException("Missing " + resource);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        }
    }
}
~~~

Notice that `Zebra` appears **before** `Alpha` in the file. This serves as a visual check that the final output does not depend on source order.

### 6.6. Compiling with `javac` and Running with `java`

Open a terminal in the **parent directory of `src`**. Example command to create directories with Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/classes, build/generated | Out-Null
~~~

**Step 1: Compile the two annotation types and the two processors.**

~~~bash
javac -encoding UTF-8 -d build/processor src/demo/Seed.java src/demo/GeneratedItem.java src/demo/ProducerProcessor.java src/demo/IndexProcessor.java
~~~

**Step 2: Compile the program and activate both processors.**

~~~bash
javac -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.ProducerProcessor,demo.IndexProcessor -s build/generated -d build/classes src/demo/Demo.java
~~~

Important options:

- `-cp build/processor`: makes `Seed` and `GeneratedItem` visible to both application sources and generated sources.
- `-processorpath build/processor`: allows the compiler to locate the classes of the two processors.
- `-processor demo.ProducerProcessor,demo.IndexProcessor`: explicitly activates the processors without relying on auto-discovery.
- `-s build/generated`: directory for generated Java source files.
- `-d build/classes`: directory for class and resource output.

**Expected output of a clean build:**

~~~text
build/generated/demo/AlphaGenerated.java
build/generated/demo/ZebraGenerated.java

build/classes/demo/Demo.class
build/classes/demo/AlphaGenerated.class
build/classes/demo/ZebraGenerated.class
build/classes/META-INF/demo/index.txt
~~~

The resource `build/classes/META-INF/demo/index.txt` contains two UTF-8 lines terminated by LF:

~~~text
demo.AlphaGenerated
demo.ZebraGenerated
~~~

**Step 3: Run the program.**

~~~bash
java -cp build/classes demo.Demo
~~~

**Exact stdout:**

~~~text
demo.AlphaGenerated
demo.ZebraGenerated
~~~

Any messages from `javac` or the build tool, if present, belong to the compilation phase and are not part of the stdout of the `java` command above.

### 6.7. Why Doesn't This Example Require a Fixed Execution Order for the Processors?

In the first round, A sees `@Seed` and generates two new sources annotated with `@GeneratedItem`. When the compiler picks up those sources in the next round, B sees `@GeneratedItem` and adds the qualified names to its set. When the final round arrives, B writes a sorted index. There is no need to rely on execution order within the **same round** as a data-passing protocol.

This approach is completely different from having A write a temporary file and B hastily open that file within the same round: the latter behavior easily depends on flush state and is not a portable coordination model recommended by JSR 269.

## 7. Ownership and Types of Conflicts

**Two processors generate the same file name.** `Filer` does not provide a “last writer wins” mechanism. A `FilerException`, which is an `IOException`, may occur. Output ownership must be assigned right from the design phase.

**A processor recreates a file in a later round.** If every invocation of `process` calls `createSourceFile("demo.AlphaGenerated")`, a duplicate name error will occur. Only generate a file when an appropriate input is present, and create each path exactly once.

**Two processors both claim the same annotation type.** If both handle `@Seed` and the first processor returns `true`, the other processor may not receive `@Seed` in the same round. You need to change the assignment model or adjust claiming intentionally.

**The aggregator only inspects the first round.** If B writes the index before generated sources exist in subsequent rounds, the index may be empty or missing entries. Accumulate across rounds.

**The aggregator generates Java source in the final round.** The compiler makes no commitment to run another normal round to process the newly generated source. The final round is better suited for resource outputs that do not require compilation.

**Processor B scans the entire classpath and treats it as the whole project.** `RoundEnvironment.getRootElements()` only contains the roots relevant to the round; it is not an enumeration of every class in dependency JARs.

## 8. Deterministic Is Different from Incremental

A processor can produce **deterministic** files during a clean build yet still behave **incorrectly** when an incremental compile deletes a source file.

For example, in the demo, if `Alpha` is deleted, a new clean build should produce an index containing only `demo.ZebraGenerated`. However, if the build tool does not rerun processor B or does not remove the old artifact, the index file can become **stale**.

Common concepts:

- **Isolating generator:** one output clearly originates from a single input, for example `AlphaGenerated.java` from `Alpha`. Passing the `originating element` to `Filer.createSourceFile` helps the toolchain track the relationship.
- **Aggregating generator:** one output depends on multiple inputs, for example an index containing all generated classes. Modifying or deleting a single class requires re-aggregating the entire index.

These are terms from toolchains that support incremental annotation processing, **not two separate interfaces in JSR 269**. Each build tool has additional requirements and metadata; the demo does not guarantee support for incremental builds in all environments.

When deploying to production, consult the documentation of Gradle, the Maven Compiler Plugin, or the build tool in use to declare dependencies properly, declare incrementality if supported, and test **adding, updating, and deleting inputs**.

## 9. Deterministic Output Testing Plan

A useful test suite includes:

1. **Two clean builds:** delete the entire output directory, compile with the same JDK/options/dependencies, and compare the bytes or SHA-256 hash of `index.txt`.
2. **Reverse input order:** swap the positions of `Alpha` and `Zebra` in the source file. The index must still be ordered `demo.AlphaGenerated` followed by `demo.ZebraGenerated`.
3. **Add input:** add `@Seed class Beta {}`. A clean build must contain three lines for Alpha, Beta, and Zebra in alphabetical order.
4. **Delete input:** remove `Beta` and run a clean build again; the index must return to two lines. For incremental builds, verify that the old artifact is also removed properly.
5. **Name conflict:** pre-create a class named `AlphaGenerated` in package `demo`. Compilation must report a clear error rather than silently overwriting.
6. **Different machines:** use the same configuration on a different OS or locale; verify UTF-8 encoding, LF newlines, and that no machine paths are written into the file.
7. **Two processors:** add a third processor to the build to test claiming state, ownership, or generated annotations without relying on the `-processor` declaration order.

If timestamps or UUIDs remain in the generated source, its hash will change on every build. Information that is truly a build input must be separated from unnecessary data.

## 10. Common Pitfalls

**Mistake 1:** Assuming a collection or `getElementsAnnotatedWith` always iterates in source order. **Fix:** normalize and sort by qualified name.

**Mistake 2:** Using `System.currentTimeMillis()` as the generated file version. **Fix:** use a configured version value, not the system clock, when determinism is the goal.

**Mistake 3:** Using the OS default charset and newline for machine-readable formats. **Fix:** use UTF-8 and LF consistently according to a unified schema.

**Mistake 4:** Allowing two processors to create the same file. **Fix:** assign a single owner or separate the output paths.

**Mistake 5:** Having processor B wait for processor A by polling the filesystem. **Fix:** use intermediate sources/annotations across compiler rounds, or split into separate build tasks with explicit dependencies.

**Mistake 6:** Treating `getRootElements()` as the entire project. **Fix:** understand the scope of a single round properly.

**Mistake 7:** Writing the aggregated resource too early. **Fix:** accumulate across rounds and finalize once all data is collected.

**Mistake 8:** Generating new Java source files when `processingOver()` is true and expecting the compiler to compile them further. **Fix:** generate Java sources during normal rounds.

**Mistake 9:** Thinking `process() == false` reports an error. **Fix:** use `Messager` with `Diagnostic.Kind.ERROR`.

**Mistake 10:** Attempting to overwrite after a `FilerException`. **Fix:** resolve name/path collisions and generation conditions instead of retrying in a last-writer-wins fashion.

**Mistake 11:** Thinking a processor being on the runtime classpath means the compiler will run it automatically. **Fix:** verify the processor path and activation/registration.

**Mistake 12:** Equating deterministic output with incremental correctness or JAR reproducibility. **Fix:** test these properties separately.

## 11. Self-Practice

**Question 1.** Why is `TreeSet<String>` appropriate for the qualified class names collected by processor B?  
**Answer:** Because the index needs unique names and a deterministic order. If duplicates carry business meaning, a different structure must be used.

**Question 2.** If A generates a source annotated with `@GeneratedItem`, where should B read it?  
**Answer:** Through `RoundEnvironment` in the next processing round, without having to manually open an intermediate file being written.

**Question 3.** Can two processors both calling `Filer.createResource` for `META-INF/demo/index.txt` overwrite each other?  
**Answer:** There is no last-writer-wins contract; a single owner or a different aggregation mechanism is required.

**Question 4.** Does returning `true` from `process(...)` prove that the output is correct and compilation succeeded?  
**Answer:** No. It claims the annotation types; it is not a certificate of zero errors.

**Question 5.** Is an identical index across two clean builds enough to prove the entire JAR is completely reproducible?  
**Answer:** No. You also need to account for class files, archive metadata, compiler flags, dependencies, timestamps, and every step of the build.

**Question 6.** Why does B wait until `processingOver()` to create the resource?  
**Answer:** So that data generated in later rounds is also accumulated, avoiding omissions. Resources do not need further compilation, making them suitable to finalize in the final round.

**Hands-on Exercise:** Run the complete demo. Add `@Seed class Beta {}` to `Demo.java`, perform a clean build, and predict the three alphabetical output lines. Next, reverse the order of class declarations without changing their names; the index must remain unchanged. Afterward, remove `Beta` and verify a clean build, then try creating a class named `AlphaGenerated` to observe the name conflict error. Explain each case in terms of **ordering**, **ownership**, **rounds**, and **incremental dependency**.

## 12. Official Documentation

- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): lifecycle, declaring supported annotations, claiming.
- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): base processor class.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): data for each round and `processingOver()`.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `Filer`, `Messager`, `Elements`, and `Types` services.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): file creation and rules to avoid duplicate creation.
- [Java SE 17 — `Messager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): compiler diagnostics.
- [Java SE 17 — `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-encoding`, `-s`, `-d`.

**Key takeaway:** Generating deterministic output requires **sorting, normalizing data and bytes, and establishing clear output ownership**. When multiple processors cooperate, use **compiler processing rounds**, separate annotation responsibilities, and aggregate data at the right time rather than relying on execution order or overwriting files.
