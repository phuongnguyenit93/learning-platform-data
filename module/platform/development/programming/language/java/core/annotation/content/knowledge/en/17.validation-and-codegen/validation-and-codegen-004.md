# Filer: Generating Source Code, Class Files, and Resources with a Java Annotation Processor

## 1. What Is `Filer` and at What Stage Is It Used?

In Java, **annotation processing** (JSR 269) allows a processor to read the program model at compile time, validate rules, or **generate additional files** from annotations. The standard API responsible for creating files is `javax.annotation.processing.Filer`, provided through `ProcessingEnvironment`:

```java
Filer filer = processingEnv.getFiler();
```

This is code placed inside an annotation processor, such as a class extending `AbstractProcessor`. `Filer` is not an object for writing arbitrarily to any disk directory: it is an interface to the **annotation processing tool** for creating files that the compiler/build can manage.

Three main types of outputs:

1. **Java source file** (`.java`): generates a type declaration, then lets the compiler proceed to compile the new source.
2. **Java class file** (`.class`): directly writes valid bytecode for a type, when the processor actually has the capability to generate bytecode.
3. **Auxiliary resource**: generates metadata, configuration text, identifier lists, or an auxiliary file that the compiler does not treat as a new class/source for automatic annotation processing.

Distinguishing the operations: `Filer` **creates output files**, whereas `RoundEnvironment`/`javax.lang.model` helps **read the model of the input code**. `Messager` is used to report error/warning diagnostics. A practical processor typically coordinates all three APIs.

Example use cases:

- From `@GenerateInfo` on `Widget`, generate `WidgetGenerated.java`.
- From metadata of annotated classes, generate a `META-INF/...` list file in the class output directory.
- From the model of a type, generate a `.class` file using a bytecode generator.
- Attach `originatingElements` so the build tool understands which element the output file originates from.

## 2. Four Main Methods and Return Types

| API | Result | Write or Read | Purpose |
|---|---|---|---|
| `createSourceFile(name, origins...)` | `JavaFileObject` | Write | Create the `.java` source of a type |
| `createClassFile(name, origins...)` | `JavaFileObject` | Write | Create valid `.class` bytecode |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | `FileObject` | Write | Create an auxiliary resource |
| `getResource(location, moduleAndPkg, relativeName)` | `FileObject` | Read | Read an existing resource at a supported location |

The interface is declared in the Java module `java.compiler` (JDK 17). Related types:

```java
import javax.annotation.processing.Filer;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.ProcessingEnvironment;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;
```

`JavaFileObject` can open a character stream with `openWriter()` or a byte stream with `openOutputStream()`. `FileObject` also provides appropriate read/write operations. Each operation is controlled by the compiler's file manager, and you should not guess physical paths when specifying names.

One very important point: **`createSourceFile` and `createClassFile` register the new source/class with the tool**, allowing it to be examined in the **next processing round** after the write stream is closed. **`createResource` does not register the file as a Java source/class to be automatically processed in a subsequent round**, even if the file name looks like `.java` or `.class`.

## 3. Multi-Round Compilation Mechanism and When to Close Files

An annotation processing round (*processing round*) has a set of root elements and annotation types not yet claimed by another processor. A processor can use `Filer` to generate new sources or classes; those files are fed by the tool into processing in the next round.

```text
Round 1 — javac sees @GenerateInfo on Widget
    |
    | Processor reads TypeElement Widget
    | Filer.createSourceFile("demo.WidgetGenerated", Widget)
    | Writer writes content and calls close()
    v
Round 2 — compiler inspects the new WidgetGenerated.java source
    |
    | Processor may be invoked again, even with an empty set of annotations
    v
Final round — roundEnv.processingOver() == true
    |
    v
Annotation processing ends, compiler finalizes output
```

**Closing the `Writer`/`OutputStream` is a meaningful step**, not just for releasing resources. According to the `Filer` contract, a new source/class file is considered for the next round **after its write stream is closed**. Use `try-with-resources` to close it as soon as the content is complete.

```java
JavaFileObject output =
        processingEnv.getFiler().createSourceFile(
                "demo.GeneratedExample", sourceElement);

try (Writer writer = output.openWriter()) {
    writer.write(
        "package demo;\n"
        + "public final class GeneratedExample {}\n");
}
```

This is an **illustrative snippet inside a processor**; `sourceElement` must be a valid `Element`, with `java.io.Writer`/`javax.tools.JavaFileObject` imported and `IOException` handled.

A newly created Java file **does not become a runtime class merely by calling `createSourceFile`**. The compiler still has to compile its contents, so the generated source must be syntactically valid, properly typed, correctly named, and compatible with the source level of the compilation run.

When `roundEnv.processingOver()` is `true`, you should not create additional source/class files expecting another regular processing round for those files. Summary work (diagnostics, reports) needs to be designed appropriately for the final round.

## 4. `createSourceFile`: Generating a Java Source with an Exact Type Name

Signature:

```java
JavaFileObject createSourceFile(
        CharSequence name,
        Element... originatingElements) throws IOException;
```

The `name` parameter is the **canonical, fully qualified name of the primary type** to be declared in the generated source; for example `"demo.WidgetGenerated"`, **not** the path `"src/demo/WidgetGenerated.java"`.

```java
JavaFileObject file =
        filer.createSourceFile("demo.WidgetGenerated", widgetElement);
```

With the `javac -s build/generated` configuration, the tool typically places this file at:

```text
build/generated/demo/WidgetGenerated.java
```

This illustrates a common classpath layout; `Filer` relies on the file manager and the actual output configuration.

The content must declare the matching type:

```java
package demo;

public final class WidgetGenerated {
    private WidgetGenerated() {}

    public static String message() {
        return "generated";
    }
}
```

Principles:

- `createSourceFile` accepts a **type name**, not a filesystem path string.
- The package + type name pair declared in the content must be consistent with `name`.
- If a compilation unit contains multiple top-level types, the file name must correspond to the primary type, especially when there is a public top-level class.
- Content is written via `Writer` or `OutputStream`; close the stream properly so the compiler can continue processing.
- Only create new types; do not attempt to "overwrite" the source class currently being processed with a new source file of the same name.

### What Roles Do `-s` and `-d` Play?

With `javac`, the `-s <dir>` option specifies where to place sources **generated by annotation processors**; `-d <dir>` specifies the output directory for compiled class files and class output resources. The file name in `createSourceFile` remains a type name and does not change with `-s`.

If `-s` is not specified, the tool may use a default location determined by the file manager configuration. To keep build outputs clean and avoid mixing hand-written sources with generated sources, you should configure two separate output directories.

## 5. Complete Java 17+ Example: Creating Both a Source and a Resource in the Same Processor

This example can be run with **JDK 17+**, without requiring Maven, Gradle, or external libraries. A `@GenerateInfo` annotation on class `Widget` will cause the processor to generate:

- `demo.WidgetGenerated.java` in **source output**.
- `demo/Widget.info` in **class output**.

The `Main` program uses the **generated class** and reads the **generated resource** at runtime.

### Initial Source Structure

```text
src/
└── demo/
    ├── GenerateInfo.java
    ├── GenerateInfoProcessor.java
    ├── Widget.java
    └── Main.java
```

### File 1 — `src/demo/GenerateInfo.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateInfo {
}
```

`SOURCE` is sufficient because the processor reads the annotation when compiling the source code. `RUNTIME` is unnecessary unless there is another consumer using reflection after compilation.

### File 2 — `src/demo/GenerateInfoProcessor.java`

```java
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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GenerateInfo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class GenerateInfoProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateInfo.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();
            String name = type.getSimpleName().toString();
            String generatedType = pkg + "." + name + "Generated";

            try {
                JavaFileObject javaFile =
                        processingEnv.getFiler()
                                .createSourceFile(generatedType, type);

                try (Writer writer = javaFile.openWriter()) {
                    writer.write("package " + pkg + ";\n\n"
                            + "public final class " + name
                            + "Generated {\n"
                            + "    private " + name + "Generated() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"generated: " + name
                            + "\";\n"
                            + "    }\n"
                            + "}\n");
                }

                FileObject resource =
                        processingEnv.getFiler().createResource(
                                StandardLocation.CLASS_OUTPUT,
                                pkg,
                                name + ".info",
                                type);

                try (Writer writer = resource.openWriter()) {
                    writer.write(name + "\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate files for " + name
                                + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }
}
```

This is the **complete processor**, not pseudocode:

- `@SupportedAnnotationTypes("demo.GenerateInfo")` registers the annotation type to be processed.
- `roundEnv.getElementsAnnotatedWith(GenerateInfo.class)` finds elements annotated with the annotation in the round.
- `TypeElement` represents the class/interface under inspection; this example creates files for `Widget`.
- `getPackageOf(type)` retrieves the package to construct the name `demo.WidgetGenerated` and place the resource in the right package.
- `createSourceFile(..., type)` and `createResource(..., type)` both accept `type` as the **originating element**.
- Two `try-with-resources` blocks close the Writer before the round ends.
- `IOException` is turned into an `ERROR` diagnostic rather than being silently ignored.
- `return true` declares that the processor claims the assigned annotation types; this boolean does **not** indicate whether the build succeeded or failed.

To keep the example small, the processor only works for classes in a named package with valid Java class names; this article uses only the `demo` package. When building a general-purpose library, you need to handle the unnamed package case, generated name collisions, and multiple annotated classes.

### File 3 — `src/demo/Widget.java`

```java
package demo;

@GenerateInfo
public class Widget {
}
```

### File 4 — `src/demo/Main.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class Main {
    public static void main(String[] args) throws IOException {
        System.out.println(WidgetGenerated.message());

        try (InputStream input =
                Main.class.getResourceAsStream("Widget.info")) {

            if (input == null) {
                throw new IOException("Missing demo/Widget.info");
            }

            String value = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).trim();
            System.out.println("resource: " + value);
        }
    }
}
```

`Main.class.getResourceAsStream("Widget.info")` looks up the resource **relative to `Main`'s `demo` package**, meaning it searches for `demo/Widget.info` on the classpath. Omitting the leading `/` in the name is intentional.

### Build and Run Commands

In the directory containing `src`, create the three output directories first. With Bash (Linux/macOS/Git Bash):

```bash
mkdir -p build/processor build/classes build/generated
```

On Windows PowerShell, you can use:

```powershell
New-Item -ItemType Directory -Force build/processor, build/classes, build/generated | Out-Null
```

Then run the `javac`/`java` commands below in a terminal with JDK 17+ from the same directory:

```bash
javac -d build/processor src/demo/GenerateInfo.java src/demo/GenerateInfoProcessor.java

javac -cp build/processor -processorpath build/processor -processor demo.GenerateInfoProcessor -s build/generated -d build/classes src/demo/Widget.java src/demo/Main.java

java -cp build/classes demo.Main
```

**Stdout of the final `java` command:**

```text
generated: Widget
resource: Widget
```

The compiler may display its own diagnostics/warnings depending on the environment; the two lines above are stdout of the **running application**, not a "mandatory log" from the compiler.

After compilation, the typical output structure is:

```text
build/
├── processor/
│   └── demo/
│       ├── GenerateInfo.class
│       └── GenerateInfoProcessor.class
├── generated/
│   └── demo/
│       └── WidgetGenerated.java
└── classes/
    └── demo/
        ├── Widget.class
        ├── WidgetGenerated.class
        ├── Main.class
        └── Widget.info
```

This is why `Main` can use `WidgetGenerated`: the processor created the source and the compiler processed it in the appropriate rounds of the **same `javac` command**.

If you run the build commands again, you should clean or consistently manage old artifacts and generated outputs. Within **a single annotation processing run**, `createSourceFile` must not be called twice for the same type name; this is different from regenerating output files across **two separate build runs**.

## 6. `createResource`: Generating Auxiliary Files with Relative Names

Java signature:

```java
FileObject createResource(
        JavaFileManager.Location location,
        CharSequence moduleAndPkg,
        CharSequence relativeName,
        Element... originatingElements) throws IOException;
```

Three parameter groups:

- `location`: the logical location, commonly `StandardLocation.CLASS_OUTPUT` or `StandardLocation.SOURCE_OUTPUT`.
- `moduleAndPkg`: the package or module/package (for module environments), for example `"demo"`.
- `relativeName`: the relative name/path within the package, for example `"Widget.info"` or `"META-INF/my-tool/index.txt"` when using the empty package.

Illustrative example:

```java
FileObject out = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo",
        "Widget.info",
        originElement);

try (Writer writer = out.openWriter()) {
    writer.write("Widget\n");
}
```

This is a code snippet inside a processor, requiring the appropriate imports and `originElement` variable.

When `-d build/classes` and the `demo` package are used as in the complete example, the resource file resides correspondingly at `build/classes/demo/Widget.info`. This is where the application at runtime can read it via the classpath if the artifact retains that resource.

Notes:

- `createResource` uses **relative paths**, and does not accept absolute paths like `C:\...` or `/tmp/...`.
- `relativeName` must be non-empty and must not contain `.` or `..` segments; the segment separator in a relative name is `/`.
- If `moduleAndPkg` is the empty string, the relative name is interpreted relative to the root of the location.
- In a JPMS environment, `moduleAndPkg` can carry a `moduleName/package.name` prefix and the tool may need to determine the target module.
- A resource created by `createResource` **is not automatically fed into a new processing round** merely because its name ends with `.java`.
- Do not choose a resource name that collides with the same path as a source/class created through the other methods.

### `CLASS_OUTPUT` and `SOURCE_OUTPUT`

| Location | Common Role | Key Point to Remember |
|---|---|---|
| `StandardLocation.CLASS_OUTPUT` | Resources packaged together with classes/runtime artifacts | Typically points to the `-d` area |
| `StandardLocation.SOURCE_OUTPUT` | Auxiliary resources placed alongside the generated source tree | Typically points to the `-s` area |

These are **logical locations that the file manager must support** for Filer. Check the actual build configuration instead of assuming they always map to the same physical path across all compilers.

For example, a metadata file to be packaged into a JAR may require `CLASS_OUTPUT`; a file intended solely for generating documentation/other sources may suit `SOURCE_OUTPUT`.

## 7. `getResource`: Reading an Existing Resource, Not Generating a New One

Signature:

```java
FileObject getResource(
        JavaFileManager.Location location,
        CharSequence moduleAndPkg,
        CharSequence relativeName) throws IOException;
```

Read an existing auxiliary file using `openReader(...)` or `openInputStream()`:

```java
FileObject resource = processingEnv.getFiler().getResource(
        StandardLocation.CLASS_OUTPUT,
        "demo",
        "previous-report.txt");

try (java.io.Reader reader = resource.openReader(true)) {
    char[] buffer = new char[1024];
    int n;
    while ((n = reader.read(buffer)) >= 0) {
        // Process exactly the n characters just read.
    }
}
```

This is an illustrative snippet inside a processor; the file `demo/previous-report.txt` must exist and the location must be readable. `openReader(true)` uses the encoding-error-ignoring policy per the FileObject API; production code should specify an encoding and handle missing-file cases.

**Do not** treat `getResource` as a way to "immediately read back" a resource already opened for writing via `createResource` in the same run. According to the Filer contract, if the same pathname has already been opened for writing during the processing run, `getResource` may throw `FilerException`. Organize inputs and outputs clearly, or keep data in memory right after generating it instead of creating a file and reading it back.

`getResource` does not accept `originatingElements` because it only reads. If you need to analyze files from dependencies or the classpath, `getResource` may be supported at certain locations depending on the file manager; `CLASS_OUTPUT` and `SOURCE_OUTPUT` are the two guaranteed locations, while other locations require checking the tool's support.

## 8. `createClassFile`: Writing **Bytecode**, Not Java Source

Signature:

```java
JavaFileObject createClassFile(
        CharSequence name,
        Element... originatingElements) throws IOException;
```

`createClassFile` is appropriate when the processor has **valid binary class-file content**, for example from a bytecode generator. Unlike `createSourceFile`, you must not write Java text here:

```java
// ILLUSTRATIVE SNIPPET ONLY — validClassBytes must be validly generated.
JavaFileObject classOut =
        processingEnv.getFiler().createClassFile(
                "demo.GeneratedBytecode", originElement);

try (java.io.OutputStream out = classOut.openOutputStream()) {
    out.write(validClassBytes);
}
```

`validClassBytes` in this snippet is a hypothetical variable containing **the full JVM ClassFile format**, not a string `"public class ..."`. The code above **does not run standalone** because no bytecode generator is provided, which is an appropriate choice when you only need to understand the API.

If you write source text to `createClassFile`, the compiler/JVM will not turn it into a valid `.class` file. To generate Java source, use `createSourceFile` and let `javac` take responsibility for compiling it.

The name `"demo.GeneratedBytecode"` is the **binary name** of the class being written, not the path `"demo/GeneratedBytecode.class"`. The bytecode generator must ensure that the internal classfile name, constant pool structures, method descriptors, and class file version are compatible with the compile/runtime environment.

According to Filer, a created and stream-closed class file is also examined by the tool for **subsequent rounds**. That does not mean the class file is always loaded by the processor's class loader so that it can be used as a runtime Java class inside the processor itself.

### Should You Choose `createSourceFile` or `createClassFile`?

- **Prefer `createSourceFile`** if the goal is to generate Java APIs from annotations: it is readable, easy to debug, and the compiler checks syntax and source-level compatibility.
- Use **`createClassFile`** if you genuinely need to emit binary classes, have a spec-compliant bytecode generator, and know how to verify validity.
- Use **`createResource`** for information that the compiler does not need to treat as a Java type.

A `.class` file created by a processor also cannot be used to arbitrarily modify an input class; Filer enforces the uniqueness of created types/files.

## 9. `originatingElements`: Why Should You Pass Originating Elements?

The file creation methods accept `Element... originatingElements`. These are the elements (class, interface, package, module...) that **triggered the decision to generate the file**.

Example:

```java
TypeElement widget = ...; // Obtained from the annotation processing model.

JavaFileObject generated =
        processingEnv.getFiler().createSourceFile(
                "demo.WidgetGenerated",
                widget);
```

This is an illustrative snippet and is not standalone because `widget` must be retrieved via `RoundEnvironment` or `Elements`.

**Effects:**

- Provides dependency relationships between inputs and outputs that build tools/incremental processing can use.
- Helps some environments decide when to rerun the processor or delete generated files if the source changes.
- Clarifies traceability when a processor generates multiple files.

**Do not misunderstand:**

- `originatingElements` does **not** create the file by itself, adjust its content, or replace `Writer`.
- There is no guarantee that all build tools use that information the same way; tools without incremental support may ignore it.
- Passing an element is not mandatory if there is truly no appropriate origin, but you should pass the true causal sources when available.
- If the output depends on **multiple** source elements, provide the appropriate list instead of passing only a single unrepresentative source.

For example, an index generated from multiple classes can use:

```java
Element[] origins = collectedElements.toArray(Element[]::new);
FileObject index = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/my-tool/index.txt",
        origins);
```

This is an illustrative code snippet assuming `collectedElements` has already been built and `Element`/`FileObject` are imported. Actual incremental behavior still depends on the build environment and the processor type.

## 10. The **Create-Once** Rule and `FilerException`

`Filer` has a very important rule: **within a single annotation processing run, a pathname may be created only once**. In addition, you must not create both a source file and a class file **for the same type name** in that run.

Intentionally wrong example:

```java
Filer filer = processingEnv.getFiler();

filer.createSourceFile("demo.WidgetGenerated");
filer.createSourceFile("demo.WidgetGenerated"); // FilerException
```

This is only an illustrative snippet; in actual use, each output file object must be properly written and closed. The second creation call with the same name within the **same processing run** violates the rule, even if it occurs in a different processing round.

Another error:

```java
filer.createSourceFile("demo.WidgetGenerated");
filer.createClassFile("demo.WidgetGenerated"); // Conflict on the same type
```

The tool also treats the **initial inputs** as having been created in "round 0". Therefore, if `demo.Widget` is an initial source being compiled, the processor cannot use `createSourceFile("demo.Widget")` to replace the content of that same type.

`FilerException` extends `IOException`. You can catch it separately to report the exact cause:

```java
try {
    // Create a new file via Filer.
} catch (javax.annotation.processing.FilerException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "Duplicate generated file: " + ex.getMessage());
} catch (java.io.IOException ex) {
    processingEnv.getMessager().printMessage(
            javax.tools.Diagnostic.Kind.ERROR,
            "I/O error: " + ex.getMessage());
}
```

This example is an illustrative exception-handling skeleton and does not include the specific file-creation call inside the `try` block.

### Distinguishing "Existed from a Previous Build" from "Created in This Run"

Java Filer specifies that if an output pathname already existed before the **first creation** in a processing run, the old contents of that file may be deleted/replaced with the new output. `FilerException` primarily ensures that **the same path is not created again within one processing run**, rather than acting as a permanent overwrite guard for every file already on disk.

Therefore, do not rely on Filer as a tool to preserve hand-written files. Dedicate a separate output directory for generated code, and avoid pointing output at directories containing human-edited sources.

### Avoiding `FilerException` Across Multiple Rounds

- Use a **deterministic and collision-free** naming rule derived from the input, such as `pkg + "." + simpleName + "Generated"`.
- Generate files only when the exact source elements for the round are found; do not call create unconditionally every time `process` runs.
- If the processor creates multiple files from multiple inputs, track already-generated names with a `Set<String>` maintained on the processor instance to avoid recreating them in other rounds.
- When `roundEnv.processingOver()` is `true`, perform finalization work instead of trying to generate new types.
- If two different processors generate the same type name or the same pathname, coordinate naming/ownership. Claiming an annotation type does not by itself resolve output name conflicts.
- When reporting an error, attach the source `Element` via `Messager` so users know which metadata led to the duplicate name.

## 11. Type Names, Resource Names, and Modules Must Be Semantically Correct

The three API families have different naming rules:

| API | Primary Identifier Parameter | Example |
|---|---|---|
| `createSourceFile` | Canonical/FQN name of the primary type or `.package-info` when creating package-info | `"demo.WidgetGenerated"` |
| `createClassFile` | Binary name of the type or `.package-info` for a named package | `"demo.WidgetGenerated"` |
| `createResource` | `location` + `moduleAndPkg` + `relativeName` | `CLASS_OUTPUT`, `"demo"`, `"Widget.info"` |
| `getResource` | The same three location/name parameters | `CLASS_OUTPUT`, `"demo"`, `"Widget.info"` |

For nested types, the **canonical name** and **binary name** can differ (for example `.` versus `$`). You must use the exact name format required by each API, especially when creating class files directly.

### `package-info`

`Filer` can create source for package information using a name such as `"demo.package-info"`. The generated file is `package-info.java` in the corresponding package. `createClassFile` has a case for `package-info.class` of a named package.

Use this only when the task genuinely needs to generate package metadata and does not conflict with a `package-info.java` or `package-info.class` file already created by the compiler/build.

### JPMS and Multiple Modules

In a module environment (Java 9+), the name for creating a source/class can carry a module prefix, such as `"billing.api/demo.WidgetGenerated"` per the API syntax. For resources, `moduleAndPkg` takes the form `"billing.api/demo"` when the tool requires a target module.

If the target module cannot be inferred, is not writable, or the location configuration does not support module prefixes, Filer may throw `FilerException`. In a multi-module project, do not mechanically apply simple classpath examples while ignoring the module path and build configuration.

## 12. Writing with the Proper Encoding, Closing Streams, and Handling Errors

When using `openWriter()`, the charset can be determined by the implementation and compiler options such as `-encoding`. For Java code/metadata containing Vietnamese diacritics, **do not assume every environment writes UTF-8 identically**.

You can specify UTF-8 explicitly via `OutputStreamWriter`:

```java
JavaFileObject javaFile =
        filer.createSourceFile("demo.GeneratedUtf8", origin);

try (java.io.Writer writer = new java.io.OutputStreamWriter(
        javaFile.openOutputStream(),
        java.nio.charset.StandardCharsets.UTF_8)) {

    writer.write("package demo;\n"
            + "public class GeneratedUtf8 {}\n");
}
```

This is an illustrative snippet inside a processor, and `origin` must be a valid `Element`. When using `openWriter()` directly, configure the encoding of `javac`/the build pipeline explicitly. Either way, **close the stream** so the compiler can see the complete file.

Other points to keep in mind:

- Generate Java content that is valid for the source version used by the processor/build.
- For binary class files, write valid bytes matching the JVM version; do not write text via `Writer`.
- Do not open multiple Writer/OutputStream instances for the same file object to write concurrently.
- Do not swallow `IOException`. Report a clear diagnostic or let the tool handle it according to the contract.
- For text resources, align the encoding between both the writer and the reader.
- Do not use a resource file to "sneakily" create a Java source/class expecting the compiler to recognize it automatically; `createResource` does not register such a file for the next round.

## 13. Common Mistakes When Using `Filer`

### 13.1. Generating a Source Without a Subsequent Round Picking Up the File

**Symptom:** The generated source is not compiled as expected.

**Check:** Does the code actually call `createSourceFile`? Is the `Writer` closed? Is the processor generating it during the final round? Are the type/package names correct, and is the source compilable?

Fix this by generating the source in an appropriate round, closing the Writer, and checking compiler diagnostics along with the output path.

### 13.2. Passing a Filesystem Path to `createSourceFile`

Wrong:

```java
filer.createSourceFile("src/demo/WidgetGenerated.java");
```

Correct:

```java
filer.createSourceFile("demo.WidgetGenerated");
```

Both lines are illustrative snippets inside a processor. Filer accepts a **type name**, while the file path is determined by the file manager.

### 13.3. Generating the Same Name Across Multiple Rounds

Wrong:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    filer.createSourceFile("demo.AlwaysGenerated"); // Assumes filer is available, throws IOException
    return true;
}
```

This code is **intentionally wrong/non-standalone**, because `IOException` must be handled and `process` may be invoked repeatedly across multiple rounds. If creating the same name is called a second time, Filer will throw `FilerException`. Only create files when corresponding inputs exist and track already-generated names.

### 13.4. Using `createResource` to "Generate a Java Class"

If you create `WidgetGenerated.java` using `createResource`, the compiler does not automatically register that file to be processed as a new source. Use `createSourceFile` for Java sources.

### 13.5. Writing Java Text to `createClassFile`

`createClassFile` requires **classfile bytes**, not Java source. If the goal is to generate easy-to-debug code, use `createSourceFile`.

### 13.6. Not Passing `originatingElements`

This is **not necessarily a compilation error**, but it makes it difficult for some build tools to track dependencies for incremental compilation. If an output originates from a specific class/element, pass the appropriate source.

### 13.7. Non-Relative Resource Names

Names such as `"../secret.txt"`, `"/absolute.txt"`, or an empty string are invalid for `relativeName`. Use a clear relative name such as `"META-INF/my-tool/index.txt"` with an appropriate package. Avoid colliding with output paths of other tools.

### 13.8. Expecting `getResource` to Read Back a File Just Created in the Same Run

Filer may reject retrieving a resource for a path that has already been opened for writing, even for immediate verification. To validate output, check the data before writing or use a post-build verification step; do not assume `getResource` permits all forms of read-after-write within the same run.

### 13.9. Creating Files Without Handling `IOException`

File access errors, incorrect type names, unwritable modules, or name collisions can cause exceptions. Catch errors purposefully and report them via `Messager`; do not merely log to `System.out` and let the compiler assume everything succeeded.

### 13.10. Confusing `process` Claiming with File-Writing Permission

`return true` in `process` only claims the annotation types assigned in that round; it does not grant permission to bypass Filer rules, prevent file name conflicts, or guarantee that the compiler build succeeds.

## 14. Self-Check Exercises

Suppose the processor encounters:

```java
@GenerateInfo
class Invoice {}
```

Given the rule to generate `InvoiceGenerated.java` and `Invoice.info`, answer the following:

1. To generate `demo.InvoiceGenerated.java`, should you call `createSourceFile("demo.InvoiceGenerated")` or `createResource(..., "InvoiceGenerated.java")`?
2. After the `Writer` of the new source closes, in which round can the compiler examine the file?
3. To generate a resource to be read at runtime via the classpath, is `CLASS_OUTPUT` or `SOURCE_OUTPUT` usually more appropriate?
4. To create `InvoiceGenerated.class` directly without a Java source, what kind of content must `createClassFile` write?
5. Is it allowed to call `createSourceFile("demo.InvoiceGenerated")` twice within the same processing run?
6. If `InvoiceGenerated.java` already exists in the output directory from a previous build, does `FilerException` strictly guarantee that file will not be touched?
7. What does `originatingElements` help the build tool understand?
8. Does `createResource(CLASS_OUTPUT, "demo", "Invoice.info")` automatically register `Invoice.info` as a Java class for the next round?
9. What can happen if you call `getResource` with the exact pathname already opened for writing during the processing run?
10. When checking for invalid errors in annotated source code, should you use `Messager` or the boolean value `return false` to report a compiler error?
11. Is `createSourceFile("demo.Invoice")` valid when `Invoice.java` is an initial input of that same `javac` run?
12. In a multi-module project, can you always skip determining the target module when generating files?

**Answers:**

1. **`createSourceFile`**, because the compiler needs to register and process the new Java source.
2. **The next round**, after the Writer is closed and if the subsequent processing environment is applicable.
3. **`CLASS_OUTPUT`** is usually appropriate so the resource resides in the runtime artifact/classpath.
4. **Valid JVM ClassFile bytecode**, not a Java source string.
5. **No.** Creating the same pathname again in one processing run causes `FilerException`.
6. **No.** A file existing prior to the first creation in the run may be deleted/replaced per the Filer contract.
7. **The origin/dependency relationship** of the generated file, useful for some incremental tools.
8. **No.** A resource is not automatically registered as a new source/class for rounds.
9. A **`FilerException`** may be thrown because Filer restricts reading/writing on the same pathname.
10. **`Messager`**, for example `Diagnostic.Kind.ERROR`; the boolean return value of `process` only relates to claiming annotation types.
11. **No.** Initial inputs are treated as already created in round 0; you cannot recreate a source of the same type.
12. **No.** There are cases where the tool cannot infer the target module or the location does not support the module specification format, leading to `FilerException`.

## 15. Checklist When Writing a File-Generating Annotation Processor

- [ ] Determined whether the output is Java source, classfile bytes, or an auxiliary resource.
- [ ] Used `processingEnv.getFiler()` instead of arbitrarily writing to the source tree via filesystem APIs.
- [ ] For Java source, used `createSourceFile(FQN, origins...)` rather than passing a `.java` path.
- [ ] For class files, used `createClassFile(binaryName, origins...)` and wrote only valid bytecode.
- [ ] For resources, used `createResource(location, moduleAndPkg, relativeName, origins...)`.
- [ ] Selected `SOURCE_OUTPUT`/`CLASS_OUTPUT` appropriately for the purpose; understood `-s` and `-d`.
- [ ] Closed `Writer`/`OutputStream` with `try-with-resources` before the compiler needs to process the file.
- [ ] Avoided recreating the same pathname within one run or creating both a source and a class with the same type name.
- [ ] Avoided colliding with initial inputs already present from round 0; gave generated types distinct names.
- [ ] Passed `originatingElements` corresponding to the real sources when available.
- [ ] Handled `IOException`/`FilerException` and reported diagnostics via `Messager`.
- [ ] Handled multiple rounds, empty annotation sets, and `processingOver()` properly.
- [ ] For Java source, verified package, public class name, source version, and encoding.
- [ ] For resources, used a valid relative name; did not expect resources to trigger a new processing round.
- [ ] When multiple processors/modules exist, checked file-creation permissions, output names, and target modules.
- [ ] Compiled and ran examples to verify both the generated source/class and the resource in the final artifact.

## 16. Official Documentation and Summary

- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): contract for sources/classes/resources, rounds, originating elements, naming rules, and `FilerException`.
- [Java SE 17 — `FilerException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html): invalid file creation scenarios.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): retrieving elements by annotation and identifying the final round.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): accessing `getFiler()` and other processor services.

**Summary:** `Filer` is the official "write gate" of an annotation processor. `createSourceFile` generates Java source for the next round, `createClassFile` emits valid bytecode, `createResource` creates auxiliary files without registering them as sources/classes, and `getResource` reads existing resources. Correct naming, closing streams, originating elements, choosing the output location, and the create-once rule are the decisive factors for a reliable code-generating processor.
