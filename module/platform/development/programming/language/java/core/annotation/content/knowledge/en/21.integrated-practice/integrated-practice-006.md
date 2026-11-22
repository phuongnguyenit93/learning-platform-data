# Generating an Index Class from Annotated Elements Using an Annotation Processor

This integrated practice builds a **Java annotation processor (JSR 269)** to find classes annotated with `@Indexed` during compilation, and then **automatically generate a Java class containing the list of class names**. After compilation, the application calls the generated class like ordinary Java source code, instead of having to write the list manually or use runtime classpath scanning.

For example, given three classes:

```java
@Indexed class Alpha {}
@Indexed class Beta {}
class Gamma {}
```

The desired result is an automatically generated source class:

```java
package demo.generated;

public final class IndexedTypes {
    private IndexedTypes() {}
    public static java.util.List<String> names() {
        return java.util.List.of(
            "demo.app.Alpha",
            "demo.app.Beta"
        );
    }
}
```

`IndexedTypes.names()` must contain **exactly two elements**, in a deterministic order, **without `Gamma`**. This is a **static index generated at compile time**, not a Registry that self-registers during class loading and not a Java Reflection mechanism that scans the entire classpath at runtime.

This lesson illustrates the full cycle of **defining an annotation → implementing a processor → finding `Element` instances with the annotation → using `Filer` to create a `.java` file → the compiler compiling the generated file → verifying the result**. The main code uses Java 17+, requiring only the JDK, with no dependencies on Maven, Gradle, Spring, or external libraries.

## 1. Problem and Architecture

In many applications, it is necessary to collect a list of types marked by an annotation in order to:

- Have a catalog of components/modules declared in source.
- Generate metadata for routing, plugins, serialization, or documentation.
- Avoid maintaining a list of class names by hand, where entries are easily missed.
- Avoid having to scan the classpath using Reflection at application startup.
- Emit a compile-time error if the annotation is placed on an unsupported element.

The solution uses two main parts:

1. **`@Indexed`**: an annotation that marks a type to be included in the index.
2. **`IndexProcessor`**: a compiler plugin invoked by javac that finds elements annotated with `@Indexed` and then generates the class **`demo.generated.IndexedTypes`**.

Diagram:

```text
Alpha.java          Beta.java           Gamma.java
   @Indexed            @Indexed           (not annotated)
      |                    |                     |
      +--------------------+---------------------+
                           |
                 javac + IndexProcessor
                           |
            RoundEnvironment.getElementsAnnotatedWith
                           |
                     Alpha, Beta
                           |
                TypeElement.getQualifiedName
                           |
                TreeMap for stable sorting
                           |
                 Filer.createSourceFile
                           |
        build/generated/demo/generated/IndexedTypes.java
                           |
                javac continues compiling
                           |
           build/classes/demo/generated/IndexedTypes.class
                           |
                     demo.app.App
                           |
              IndexedTypes.names()
                 [Alpha, Beta]
```

**Intentional limitation:** this practice demonstrates **ordinary top-level classes**, not every Java `Element` kind. The `@Target(TYPE)` annotation syntactically allows interfaces/enums/records as well, but the processor will only accept `ElementKind.CLASS`; other kinds are reported as errors if annotated. The final section explains how to extend this for methods, fields, nested classes, multiple modules, and multiple processing rounds.

## 2. Directory Structure to Create

Place the files:

```text
index-demo/
├── src/
│   └── demo/
│       ├── marker/
│       │   └── Indexed.java
│       ├── processor/
│       │   └── IndexProcessor.java
│       └── app/
│           ├── Alpha.java
│           ├── Beta.java
│           ├── Gamma.java
│           └── App.java
└── build/
    ├── processor/  (javac generates the processor and annotation classes)
    ├── generated/  (Filer generates the IndexedTypes.java source)
    └── classes/    (javac generates the application classes and IndexedTypes.class)
```

The `build/...` paths are outputs and will be created during the compile step. In the demo, we place the annotation and processor in separate packages, but compile them into the same initial classes directory to minimize configuration.

`demo.generated.IndexedTypes` **does not exist in the initial source yet**. Do not manually create a file with this name in `src`: the goal is for the processor to generate the file via `Filer`, and creating a duplicate file can cause a `FilerException`.

## 3. Indexed.java — Annotation to Mark Classes

File **`src/demo/marker/Indexed.java`**:

```java
package demo.marker;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Indexed {
}
```

Explanation:

- `@interface Indexed` defines an annotation with no data elements; only whether it is **present or not** is needed.
- `@Target(TYPE)` allows use on type declarations. In the processor, we will filter for ordinary classes only.
- `@Retention(SOURCE)` is sufficient because the processor reads the annotation **during javac compilation**. There is no need to retain this marker for runtime Reflection to read.
- `Indexed` is declared `public` in the `demo.marker` package so application code can `import demo.marker.Indexed`.

When used:

```java
@Indexed
public class Alpha {
}
```

the compiler can provide the `TypeElement` object for `Alpha` to the processor when processing the source. The annotation does not create the index by itself, does not register the class by itself, and does not run code inside `Alpha` by itself.

### SOURCE or RUNTIME?

If the sole goal is to **generate a list at compile time**, `SOURCE` keeps the design simple and does not force the application to retain the marker in class files. If another system **needs to read that annotation itself via Reflection at runtime**, `RUNTIME` can be chosen. These are two different needs:

| Need | Mechanism | Sufficient Retention |
| --- | --- | --- |
| Processor finds classes at compile time | Java annotation processing / `RoundEnvironment` | `SOURCE` |
| App calls `Class.getAnnotation(Indexed.class)` at runtime | Java Reflection | `RUNTIME` |
| App uses the list of names from the generated index class | `IndexedTypes.names()` | Marker does not need to exist at runtime |

The generated index class contains **class name strings**. That content can exist at runtime even when the source annotation `@Indexed` is no longer present in the `.class` file.

## 4. IndexProcessor.java — Finding and Filtering Annotated Elements

Complete file **`src/demo/processor/IndexProcessor.java`**:

```java
package demo.processor;

import demo.marker.Indexed;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Map;
import java.util.TreeMap;
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

@SupportedAnnotationTypes("demo.marker.Indexed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class IndexProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            java.util.Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        Map<String, Element> found = new TreeMap<>();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Indexed.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Indexed can only mark ordinary classes in this demo",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            found.put(type.getQualifiedName().toString(), type);
        }

        if (found.isEmpty()) {
            return true;
        }

        try {
            JavaFileObject file = processingEnv.getFiler().createSourceFile(
                    "demo.generated.IndexedTypes",
                    found.values().toArray(new Element[0]));

            try (Writer out = file.openWriter()) {
                out.write("package demo.generated;\n\n");
                out.write("public final class IndexedTypes {\n");
                out.write("    private IndexedTypes() {}\n");
                out.write("    public static java.util.List<String> names() {\n");
                out.write("        return java.util.List.of(\n");

                var names = new ArrayList<>(found.keySet());
                for (int i = 0; i < names.size(); i++) {
                    out.write("            \"" + names.get(i) + "\"");
                    out.write(i + 1 == names.size() ? "\n" : ",\n");
                }

                out.write("        );\n");
                out.write("    }\n");
                out.write("}\n");
            }

            generated = true;
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Could not create demo.generated.IndexedTypes: "
                            + ex.getMessage());
        }

        return true;
    }
}
```

This is a **runnable** annotation processor for the exercise with top-level classes. It creates a standard Java source file through the `Filer` API, without writing directly to the original source directory and without opening a relative path with `new FileWriter(...)`.

### 4.1. Processor Configuration

```java
@SupportedAnnotationTypes("demo.marker.Indexed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
```

These two meta-annotations declare the annotation type supported by the processor and the source level. `@SupportedAnnotationTypes` requires the **fully qualified name of the annotation type**, not the name of `IndexProcessor` or the source file name.

`IndexProcessor` extends `AbstractProcessor`, thereby providing `processingEnv`, `Messager`, `Filer`, and language model utilities. It runs when **javac selects the processor**, not when the application calls `main`.

### 4.2. Finding Elements with RoundEnvironment

```java
roundEnv.getElementsAnnotatedWith(Indexed.class)
```

returns the `Element` instances that the compiler determines are annotated with `@Indexed` in the current round. An `Element` is a **declaration model inside the compiler**, not an instance of an application class or a runtime `Class<?>`.

In the example, `Alpha` and `Beta` are `TypeElement` instances because they are type declarations. `Gamma` has no annotation, so it is not returned.

The call above is used **inside the processor**, where `Indexed.class` is the class of the annotation type that the compiled processor references. That does not mean the `Alpha` and `Beta` classes have been loaded by the JVM running the processor.

### 4.3. Filtering ElementKind

```java
if (element.getKind() != ElementKind.CLASS) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "@Indexed can only mark ordinary classes in this demo",
            element);
    continue;
}
```

`@Target(TYPE)` allows the annotation to be written on multiple kinds of type declarations. However, the goal of **the demo** is to index ordinary classes. The processor proactively reports an error for other `ElementKind` values.

`Diagnostic.Kind.ERROR` prevents javac from treating the build as a valid compilation in this situation. Application code should fix the annotation usage or intentionally extend the processor logic; it should not be silently ignored if it is a contract violation.

### 4.4. Getting the Type Name from TypeElement

```java
TypeElement type = (TypeElement) element;
String qualifiedName = type.getQualifiedName().toString();
```

For the top-level class `Alpha` in the `demo.app` package, the retrieved name is `demo.app.Alpha`. This is the **qualified name/canonical-like source name** of the type, not a file path or a slash-separated package path.

Do not use:

```java
Class.forName("demo.app.Alpha")
```

inside the processor to look up classes being compiled. They may not have `.class` files yet, and the runtime loader should not be required to create instances just to know source metadata. `TypeElement` solves the compile-time problem properly.

**Nested classes limitation:** `getQualifiedName()` can return a source-style name such as `demo.app.Outer.Inner`, whereas `Outer.Inner.class.getName()` uses a **binary name** with `\$` (for example, `demo.app.Outer$Inner`). This lesson uses top-level classes; if you want an index of names that can be passed directly to `Class.forName`, for nested types you should look into `Elements.getBinaryName(TypeElement)` and test separately. Do not conflate all Java name forms.

### 4.5. Why Use TreeMap?

```java
Map<String, Element> found = new TreeMap<>();
found.put(type.getQualifiedName().toString(), type);
```

A `TreeMap` sorts keys in lexicographical order while also preventing duplicates of the **same name**. This yields **stable** output instead of depending on the order in which the compiler happens to traverse `Element` instances.

The `names` list is created from `found.keySet()`, so for two classes named `demo.app.Alpha` and `demo.app.Beta`, the index has `Alpha` before `Beta`.

Stable ordering makes tests reproducible, makes diffs of the generated file easy to read, and avoids causing the build system to detect spurious changes simply because the annotation processor ran in a different traversal order.

### 4.6. Creating Files with Filer

```java
JavaFileObject file = processingEnv.getFiler().createSourceFile(
        "demo.generated.IndexedTypes",
        found.values().toArray(new Element[0]));
```

`createSourceFile` takes the **fully qualified name of the class to be generated**. Javac determines the output path according to `-s` or the build configuration; directory paths should not be hardcoded inside the processor.

The trailing `Element` list specifies **originating elements**: metadata linking the generated file to the input declarations that contributed to producing it. This is useful for certain dependency-tracking/incremental compilation mechanisms; it does not mean the compiler is required to merge all dependencies identically across every build tool.

The syntax:

```java
try (Writer out = file.openWriter()) {
    // Write valid Java source code to the JavaFileObject.
}
```

uses try-with-resources to close the writer immediately upon completion. If it is not closed, the compiler might not receive the complete source file in time.

### 4.7. Generating the Index Class

The processor writes:

```java
out.write("package demo.generated;\n\n");
out.write("public final class IndexedTypes {\n");
out.write("    private IndexedTypes() {}\n");
out.write("    public static java.util.List<String> names() {\n");
out.write("        return java.util.List.of(\n");
```

and then writes each class name into a string literal. Afterward, it closes `List.of(...)`, the method, and the class.

The generated class:

- `final`: not intended to be subclassed by the application.
- `private` constructor: contains only a static API, so there is no need to create instances.
- `names()` returns an immutable `List<String>` via `List.of`.
- The method's data is a **compile-time index**, not the result of automatically scanning the classpath at runtime.

Because the code generates class names as strings, it **does not instantiate `Alpha` or `Beta`**; even when the code contains the line `"demo.app.Alpha"`, it is not equivalent to calling `new Alpha()`.

**Safety when generating source:** the example takes names directly from `TypeElement` determined by the compiler, within the scope of top-level types. If you extend the generator to insert user-supplied annotation data into string literals, you must **escape quotes, backslashes, and control characters** and validate values before concatenating them into the source to avoid generating syntactically invalid Java files.

### 4.8. Avoiding Creating the Same File Twice

```java
private boolean generated;
```

and:

```java
if (roundEnv.processingOver() || generated) {
    return true;
}
```

prevent the processor from calling `Filer.createSourceFile("demo.generated.IndexedTypes")` again in subsequent rounds. JSR 269 can run **multiple processing rounds**, especially when additional source files have just been generated.

Under the `Filer` contract, attempting to recreate the same file name within one processing run can throw a `FilerException`. Therefore, avoid rewriting the file or trying to reopen it in a later round.

**Limitation to be aware of:** the demo intentionally creates the index **in the first round that has annotated classes** and stops regenerating afterward. If another processor **generates additional `@Indexed` classes in a later round**, the demo's index **will not automatically append them**. For projects that need to collect all generated items across multiple rounds, design a dedicated **aggregating processor** strategy, separate the aggregation step, or use a controlled multi-stage pipeline. Do not simply remove the `generated` flag to "let it run again", because you will encounter a duplicate file creation error.

### 4.9. Handling File-Writing Errors

```java
} catch (IOException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Could not create demo.generated.IndexedTypes: "
                    + ex.getMessage());
}
```

Errors such as duplicate files, an unwritable output path, or I/O failures must become a **compiler diagnostic** rather than being silently ignored. The build must fail when a required generator cannot produce valid source.

`process(...)` returns `true` here to **claim the processed annotation type** in the round. This value is not a `boolean` indicating "the index class was successfully created"; the compiler uses it for processor coordination rules.

## 5. Annotated and Unannotated Classes

File **`src/demo/app/Alpha.java`**:

```java
package demo.app;

import demo.marker.Indexed;

@Indexed
public class Alpha {
}
```

File **`src/demo/app/Beta.java`**:

```java
package demo.app;

import demo.marker.Indexed;

@Indexed
public class Beta {
}
```

File **`src/demo/app/Gamma.java`**:

```java
package demo.app;

public class Gamma {
}
```

These are three separate files, each containing a public class of the same name. `Alpha` and `Beta` are selected by `IndexProcessor`, while `Gamma` is not added to `found`.

If you remove `@Indexed` from `Beta`, the index generated in **a clean build** will contain only `Alpha`. If you add `@Indexed` to `Gamma` and run a clean build, it will be included in the list in name order from `TreeMap`.

**Recommendation:** perform a clean build when testing changes to the set of annotated classes. Because generated files are build artifacts, old output should not be treated as a reliable data source for a new compilation if the task/build tool does not delete or properly manage it.

## 6. App.java — Using the Generated Class

File **`src/demo/app/App.java`**:

```java
package demo.app;

import demo.generated.IndexedTypes;

public class App {
    public static void main(String[] args) {
        System.out.println("Index entries=" + IndexedTypes.names().size());

        for (String name : IndexedTypes.names()) {
            System.out.println(name);
        }

        System.out.println("contains Alpha="
                + IndexedTypes.names().contains(Alpha.class.getName()));

        System.out.println("contains Gamma="
                + IndexedTypes.names().contains(Gamma.class.getName()));
    }
}
```

`App` imports `demo.generated.IndexedTypes` even though the `IndexedTypes.java` file **does not exist before the compiler runs**. Javac can pick up sources created by the annotation processor in the appropriate processing round and continue compiling them; that is why **there is no need to copy the generated file manually** for the application to use it.

`IndexedTypes.names()` returns the list of strings:

```text
demo.app.Alpha
demo.app.Beta
```

`Alpha.class.getName()` is `demo.app.Alpha` and `Gamma.class.getName()` is `demo.app.Gamma` for the top-level classes in the example. App verifies that the index contains the annotated class and does not contain the unannotated class.

The application **does not need to scan the classpath**, **does not read `@Indexed` via Reflection**, and **does not instantiate the indexed classes itself**.

## 7. Compiling the Entire Demo with javac

Run the commands in the root `index-demo` directory. Use JDK 17 or later.

### Step 1 — Create the Output Directories

On Linux/macOS or a Bash shell:

```bash
mkdir -p build/processor build/generated build/classes
```

On PowerShell:

```powershell
New-Item -ItemType Directory -Force build/processor, build/generated, build/classes | Out-Null
```

### Step 2 — Compile the Annotation API and Processor

```bash
javac --release 17 -d build/processor \
  src/demo/marker/Indexed.java \
  src/demo/processor/IndexProcessor.java
```

Afterward, you have:

```text
build/processor/demo/marker/Indexed.class
build/processor/demo/processor/IndexProcessor.class
```

At this stage, the processor is only **compiled** and has not yet run on the application classes. We have not yet required service discovery or a `META-INF/services` file.

### Step 3 — Compile the Application and Run the Processor

```bash
javac --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.IndexProcessor \
  -s build/generated \
  -d build/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Gamma.java \
  src/demo/app/App.java
```

Meaning:

| Option | Role |
| --- | --- |
| `-cp build/processor` | Allows app sources to import `demo.marker.Indexed` |
| `-processorpath build/processor` | Where javac loads `IndexProcessor` and required dependencies |
| `-processor demo.processor.IndexProcessor` | Specifies the **explicit processor**; no SPI file is needed for the example |
| `-s build/generated` | Directory for storing `.java` files created by `Filer.createSourceFile` |
| `-d build/classes` | Directory for storing `.class` files of the application **and generated sources** |
| `--release 17` | Target Java 17 API/language syntax/bytecode |

**Key point:** do not add `src/demo/generated/IndexedTypes.java` to the javac command because that file does not exist in the original source. `IndexProcessor` creates it using `Filer`, and javac picks it up and compiles it as part of the process.

The Bash snippets use the `\` character at the end of lines for line continuation. In PowerShell, use a single long line or backtick line continuation:

```powershell
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.IndexProcessor -s build/generated -d build/classes src/demo/app/Alpha.java src/demo/app/Beta.java src/demo/app/Gamma.java src/demo/app/App.java
```

### Step 4 — Run the Program

```bash
java -cp build/classes demo.app.App
```

The **exact** stdout of the program:

```text
Index entries=2
demo.app.Alpha
demo.app.Beta
contains Alpha=true
contains Gamma=false
```

**Empirical verification:** the entire processor and application were compiled with `javac --release 17`; `App` ran successfully and output the exact five lines above. The test files were created in a temporary directory for testing purposes without modifying the project source.

## 8. Inspecting the Generated Source Directly

After running the second compile step, view:

```bash
cat build/generated/demo/generated/IndexedTypes.java
```

On PowerShell:

```powershell
Get-Content build/generated/demo/generated/IndexedTypes.java
```

Expected full content:

```java
package demo.generated;

public final class IndexedTypes {
    private IndexedTypes() {}
    public static java.util.List<String> names() {
        return java.util.List.of(
            "demo.app.Alpha",
            "demo.app.Beta"
        );
    }
}
```

This is not a snippet you wrote beforehand in the source directory. It is the output that `IndexProcessor` generated through `Filer`.

After compilation finishes, there will also be:

```text
build/classes/demo/generated/IndexedTypes.class
```

If the generated source exists but the generated class does not, check whether javac stopped due to a compilation error, whether `-proc:only` is being used, whether a different `-d` was specified, or whether you are checking the wrong directory.

### Why Generate Source Instead of Writing Bytecode Directly?

`Filer.createSourceFile` is an easy-to-learn choice because:

- The generated Java source can be read and inspected like a normal file.
- Javac continues to type-check and syntax-check the generated source.
- There is no need to know how to encode the class file/constant pool manually.
- Build tools can track generated files and originating elements when supported.
- Debugging is simple: compare the `.java` file in `build/generated` against the expected output.

`Filer.createClassFile` can be used in scenarios that require generating bytecode directly, but that requires knowledge of the class file format and is unnecessary for this practice exercise.

## 9. Testing the Index Instead of Only Looking at Stdout

A simple verification approach is to turn the expected class names into a list and compare directly:

```java
java.util.List<String> expected = java.util.List.of(
        "demo.app.Alpha", "demo.app.Beta");

java.util.List<String> actual = demo.generated.IndexedTypes.names();

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Index mismatch: expected=" + expected + ", actual=" + actual);
}
```

This is a **snippet to place inside a test method or inside `main`**, not an independent standalone file. `List.equals` checks **the count, each value, and the order**, so it detects missing elements, extra elements, and wrong order alike.

The following cases should be tested:

| Case | Input source | Expectation on a clean build |
| --- | --- | --- |
| Two classes with `@Indexed` | `Alpha`, `Beta` | `[demo.app.Alpha, demo.app.Beta]` |
| One class without `@Indexed` | `Gamma` | No `Gamma` in the index |
| Only one annotated class | Only `Alpha` | Single-element index |
| Reverse order of files passed to javac | `Beta.java` then `Alpha.java` | Still `Alpha` before `Beta` due to `TreeMap` |
| Applying `@Indexed` to an interface | `interface Service` | Compilation reports an error due to the demo's policy |
| Applying `@Indexed` to a method | `void run()` | Javac rejects it due to `@Target(TYPE)` |
| Second build without cleaning | Old output may remain | Do not treat old output as accurate when changing the source set |
| No classes annotated | Empty set | The demo **does not generate `IndexedTypes`**; if App still imports it, compilation will fail |

**Why is the "no classes" case worth noting?** In the processor there is `if (found.isEmpty()) return true;`, meaning no index file is generated. This design fits a minimal example, but an application that always imports `IndexedTypes` will fail to compile when there are zero entries at all. If the requirement is that the index must always exist even when empty, you need to change the generator contract: you can specify that the index is always generated from an empty set in an appropriate round, and thoroughly test multiple processing rounds to avoid duplicate generation.

## 10. Distinguishing an Annotation Processor from Runtime Reflection

The following two ideas are **not equivalent**.

**In a compile-time processor:**

```java
for (Element e : roundEnv.getElementsAnnotatedWith(Indexed.class)) {
    // Read the source/compiler model.
}
```

**In runtime Reflection:**

```java
boolean present = Alpha.class.isAnnotationPresent(Indexed.class);
```

With `@Retention(SOURCE)` in the main example, a runtime Reflection query on `Alpha.class` does not see the `@Indexed` usage. However, the `IndexedTypes` index still exists because it was generated during the build.

Characteristics to understand:

- **Annotation processing:** the compiler knows which sources/elements are being processed; it can generate new sources using `Filer`.
- **Runtime Reflection:** an API that reads runtime-visible metadata of already-loaded classes; it does not automatically scan every class on the classpath.
- **Generated index:** a generated Java class containing a **list finalized at build time**, used just like ordinary Java code.

If the runtime needs to retrieve the list via `IndexedTypes.names()`, the application no longer needs to see the annotation marker on the class file. This difference typically gives startup more stable data than runtime scanning, but in return **the build must run the processor properly whenever the source set changes**.

## 11. Adding the Processor to Maven, Gradle, or an IDE

This lesson runs with the CLI and an **explicit `-processor`** so it does not depend on automatic discovery configuration. When moving to a build tool:

1. Place the **annotation API** on the compile classpath of the application module.
2. Place the **processor implementation** along with its dependencies on the appropriate annotation processor path.
3. Ensure the build **enables annotation processing** and selects the processor; you can use the service file `META-INF/services/javax.annotation.processing.Processor` for automatic provider discovery.
4. Put generated sources in an output directory managed by the build tool, and avoid accidentally committing temporary files if the project does not have a policy of committing generated code.
5. Ensure downstream compile tasks see both the sources and classes created by the processor.
6. Verify incremental builds: an index pattern that **aggregates multiple annotated classes into a single file** usually needs to be recognized by the build tool as **aggregating**.

If using SPI discovery instead of `-processor`, the service file has the **exact** path:

```text
META-INF/services/javax.annotation.processing.Processor
```

Contents for this example:

```text
demo.processor.IndexProcessor
```

The file must reside at the root of the classes/JAR on the processor path. Avoid the mistake of placing the service file into the output **before the processor implementation is compiled**, causing the compiler to try loading a provider that does not exist yet.

**Modern JDK note:** newer JDKs have changed how annotation processing is enabled by default. **Explicitly** configuring processor selection and the processor path makes builds more reproducible. Do not simply drop a JAR into dependencies and assume the processor will run across all JDKs/IDEs.

## 12. Limitations of the Sample Generator and How to Extend It

### 12.1. Multiple Rounds, Multiple Processors

`RoundEnvironment` can change across rounds. Sources generated by one processor may be fed by javac into the next round. The processor in this lesson chooses the strategy of **generating once in the first round that has annotated classes**:

```java
if (roundEnv.processingOver() || generated) {
    return true;
}
```

This approach avoids duplicate creation, but it is **not a complete multi-round aggregation solution**. Another processor that generates `@Indexed class NewComponent` in a later round will not be added to the demo's `IndexedTypes` file.

If all elements from multiple rounds are required, design an accumulation and aggregation pipeline with an appropriate endpoint, which may require separating the final index generation step into a distinct compilation task. Do not wait until `processingOver()` and arbitrarily call `createSourceFile` for sources that need to be compiled in the same compilation: that is the final round, which can lead to warnings/errors or sources not being processed as expected.

### 12.2. Multiple Modules and Sources in Dependency JARs

`roundEnv.getElementsAnnotatedWith(...)` does not mean the processor automatically scans every class across all application dependencies. It reflects the elements provided by the compiler during that specific processing run.

If you want the index to include classes from previously built modules/JARs, you need a cross-module metadata merging strategy—for example, having each module generate a separate index/resource and then running an aggregation step later. You should not assume that a single javac pass on the current module will automatically discover every annotated class from external libraries.

### 12.3. Nested Classes and Binary Names

The example uses `TypeElement.getQualifiedName()` and stores names like `demo.app.Alpha`. For a nested class, the qualified name may be `demo.app.Outer.Inner`, whereas `Class.getName()` uses `Outer$Inner`.

If the goal is a name suitable for `Class.forName`, consider:

```java
String binaryName = processingEnv.getElementUtils()
        .getBinaryName(type)
        .toString();
```

You need to test nested classes, member classes, and other supported locations. You must also decide whether private, abstract, local, or anonymous classes are allowed according to the tool's contract.

### 12.4. Wanting to Index Methods or Fields

This lesson only accepts `ElementKind.CLASS`, although another problem might need to index:

- `ExecutableElement` for methods/constructors.
- `VariableElement` for fields, enum constants, or parameters.
- `TypeElement` for classes/interfaces/enums/records.

To do so, `@Target` must allow the corresponding targets (such as `METHOD`, `FIELD`), and the processor must generate a structure that sufficiently identifies the location: **owning class, member name, signature, and overload characteristics**. Storing only a method name like `"run"` will not be enough to distinguish overloads.

### 12.5. Wanting to Generate a Factory Instead of a String List

In the demo, the index contains `List<String>`, so it only has **class name metadata**. If instantiation is needed, determine:

- Which constructor or factory method is allowed to be called.
- Whether the class is public/accessible.
- Whether the classes share a common interface/base type.
- What dependency injection/arguments are required.
- Whether there are side effects or costs upon initialization.

Do not arbitrarily emit `new SomeClass()` solely based on the presence of `@Indexed`. An annotation only marks intent; instantiability and runtime safety are separate requirements.

## 13. Common Errors and How to Troubleshoot

**Error: Cannot find `demo.generated.IndexedTypes` when compiling.** Check whether javac actually ran `-processor demo.processor.IndexProcessor`, whether the annotation API is on the compile classpath, whether the processor class is on the processor path, whether there is at least one `@Indexed` class, and whether the generated source appears under `-s build/generated`.

**Error: `FilerException: Attempt to recreate a file for type ...`.** The processor may have called `createSourceFile` twice for the same qualified name within a single compilation, or there may be a duplicate source/file. Maintain an appropriate `generated` state and do not manually place generated files into the source inputs without a plan to manage name collisions.

**Error: Compilation fails when `@Indexed` is placed on an interface.** `@Target(TYPE)` allows this placement at the annotation level, but the processor intentionally supports only `ElementKind.CLASS`. Extend the processor if you genuinely want to index interfaces instead of ignoring the error.

**Error: Class name has the wrong package.** Do not assemble package names with arbitrary string concatenation; obtain the name from `TypeElement` and verify the kind of name to store (qualified name or binary name).

**Error: List order changes between two builds.** Do not rely on the iteration order of a `Set` from the processor or the order of files received by javac. This lesson uses `TreeMap` to sort by qualified name before generating source.

**Error: Compilation succeeds but the index is not updated after removing an annotation.** Check whether the incremental build re-ran the processor and replaced old artifacts. With a generated aggregator, try a clean build before blaming `getElementsAnnotatedWith`.

**Error: Processor runs but no class is generated.** Inspect `found.isEmpty()`, `processingOver()`, the `generated` flag, and `Messager` diagnostics. If there are no annotated classes, the demo intentionally does not create the file.

**Error: Generated file exists but Java cannot compile it.** Open the file in `build/generated` and read the javac diagnostics. The generator must emit valid Java code, escape user-supplied strings, and output brackets and commas in the right places.

**Error: Compiling with `-proc:none`.** This flag disables annotation processing; `IndexedTypes` is not generated. When debugging, try explicit `-processor` as shown in the example command.

**Error: Reading `@Indexed` with Reflection returns `null`.** The annotation has `SOURCE` retention, so this is the expected behavior. Use the generated index instead, or change retention according to your specific Reflection needs.

## 14. Practice Exercises with Guided Solutions

### Exercise 1 — Changing the List

Remove `@Indexed` from `Beta`, clean the output, and recompile. Predict `IndexedTypes.names()`.

**Answer:** only `[demo.app.Alpha]` remains; `Gamma` still has no marker, so it is not indexed.

### Exercise 2 — Checking the Order

Reverse the order of source files in the javac command: place `Beta.java` before `Alpha.java`. Does the list change?

**Answer:** not under the current design. `TreeMap` sorts by qualified name; `demo.app.Alpha` comes before `demo.app.Beta`.

### Exercise 3 — Detecting the Wrong Element Kind

Annotate `@Indexed` on:

```java
@Indexed
interface Plugin {
}
```

Should the code be added to the index?

**Answer:** no. The processor emits `Diagnostic.Kind.ERROR` because the element kind is `INTERFACE`, which differs from `ElementKind.CLASS` allowed by the demo.

### Exercise 4 — Inspecting the Generated Source

Why is `IndexedTypes.java` located in `build/generated/demo/generated/` instead of `src/demo/generated/`?

**Answer:** `Filer.createSourceFile` uses the qualified name and compiler-controlled output, specifically `-s build/generated`. Generated source is an artifact of the compilation process, not a file the user must create manually.

### Exercise 5 — Filer and Rounds

Why should you not call `createSourceFile("demo.generated.IndexedTypes")` in every round?

**Answer:** `Filer` does not allow recreating the same file within a single compilation; it can throw a `FilerException`. You need a single-generation strategy and a clear design for elements discovered across multiple rounds.

### Exercise 6 — SOURCE Retention

`@Indexed` has `SOURCE` retention. Why can `App` still query the list of annotated classes?

**Answer:** `App` calls **the `IndexedTypes` index class generated and compiled by the compiler**, not Reflection to retrieve the annotation. The list data was finalized in the generated source.

### Exercise 7 — Extending to Nested Type Names

Suppose `@Indexed` is placed on `Outer.Inner`. Why do you need to think about `getQualifiedName` and `getBinaryName` if you want to use `Class.forName`?

**Answer:** the source name and binary name of a nested class can differ (`Outer.Inner` versus `Outer$Inner`). The name stored in the index must match the consuming API.

### Exercise 8 — Designing an Index for Methods

If multiple overloaded methods are annotated with a new annotation, is storing only `getSimpleName()` of `ExecutableElement` sufficient?

**Answer:** no. You also need the owning class and appropriate parameter/return type signatures to distinguish overloads and identify the method accurately.

## 15. Exercise Completion Checklist

1. Does the `@Indexed` annotation have `@Target` and `@Retention` suited to the compile-time goal?
2. Is the processor compiled first and properly selected by javac via `-processor` or service discovery?
3. Does `@SupportedAnnotationTypes` use the exact name `demo.marker.Indexed`?
4. Does `RoundEnvironment` find the exact annotated elements during the compilation pass?
5. Have you selected and checked the supported `ElementKind`?
6. Did you obtain the name from `TypeElement` instead of trying to use runtime class loading?
7. Is there a stable sorting/deduplication rule so that output does not depend on traversal order?
8. Is `Filer.createSourceFile` called exactly once for a qualified generated class?
9. Is the Writer closed with try-with-resources?
10. Does `-s` point to the generated sources directory and `-d` point to the compiled classes directory?
11. Can the generated `IndexedTypes.java` file be viewed and compiled?
12. Does App use the list without needing to scan the runtime classpath?
13. Have tests verified that `Alpha` and `Beta` are present and `Gamma` is absent?
14. Have you tested annotation changes with a clean build?
15. Have you distinguished the single-round demo limitation from multi-round/multi-module aggregating problems?
16. If the build fails, do you read the diagnostics instead of hiding errors or overwriting the generated file?

**Conclusion:** an annotation processor uses `RoundEnvironment` to find annotated `Element` instances, `TypeElement` to obtain type names, and `Filer.createSourceFile` to create **a compilable Java index class**. The demo generates `demo.generated.IndexedTypes` from two `@Indexed` classes, ensures stable ordering, and lets the application read the list via `IndexedTypes.names()` without runtime Reflection. This serves as a foundation for developing compile-time registration, source generation, and static metadata indexing tools, provided it is intentionally extended for multiple rounds, other element kinds, and real-world build configurations.
