# Generating sources and resources with Filer in Java Annotation Processing

When building an annotation processor using the **JSR 269** API (package `javax.annotation.processing`), a common requirement is reading annotated declarations and generating **Java source files** or **resources** for the compiler and application to use. The standard API for that is **`Filer`**, obtained via `ProcessingEnvironment.getFiler()`.

For example, a class `@GenerateCompanion Hello` is recognized by the processor, which generates `HelloCompanion.java`, while also generating `META-INF/lesson/generated.txt` listing the name of the newly created class. `javac` can then compile the new source code in the next processing round. The resource goes into the output for the application to read at runtime, without needing hardcoded strings in source code.

Crucially: `Filer` **creates new files whose names are managed by the compiler**; it is not an API for directly modifying the abstract syntax tree (AST) of a class currently being compiled, nor is it a way to overwrite input sources.

## 1. Where does Filer sit in the compilation process?

A standard processor receives a `ProcessingEnvironment` object when initialized. From that environment, it can use:

| API | Purpose |
| --- | --- |
| `processingEnv.getFiler()` | Create new sources, class files, or resources |
| `processingEnv.getMessager()` | Emit `NOTE`, `WARNING`, `ERROR` to the compiler |
| `processingEnv.getElementUtils()` | Read packages, declaration names, and the `Element` model |
| `processingEnv.getTypeUtils()` | Analyze/compare `TypeMirror` |
| `RoundEnvironment` | Inspect annotated elements and processing round state |

Conceptual diagram:

~~~text
App.java (@GenerateCompanion)
             |
             v
      javac: parse/enter
             |
             v
  JSR 269 annotation processor
      |                 |
      | Filer           | Filer
      v                 v
HelloCompanion.java   META-INF/lesson/generated.txt
      |                 |
      v                 v
next round of javac   CLASS_OUTPUT/resource
      |
      v
HelloCompanion.class
      |
      v
Run App -> call generated method and read resource
~~~

The diagram simplifies internal `javac` phases. What must be remembered is that **generated source** can become input to the next compilation round/phase; whereas **resources** are typically packaged alongside class/JAR outputs for the application to use.

### How is Filer different from File/Files?

`java.io.File` and `java.nio.file.Files` are general I/O APIs: they can write to any path the process has permission for. `Filer` adds the **annotation processing contract**: managing file names, output locations, detecting duplicate creation attempts, and informing the compiler about newly generated files.

Inside a processor, prefer `Filer` for build product files. If you manually write `.java` via `Files.writeString(...)` into an arbitrary directory, the compiler **is not automatically obligated to discover and compile** that file in the same processing run.

## 2. The four main operations of Filer

The `javax.annotation.processing.Filer` interface provides four groups of operations:

| Method | Result | Important arguments |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | `JavaFileObject` containing source of a new type | Canonical fully qualified name of the type, e.g., `demo.HelloCompanion` |
| `createClassFile(name, origins...)` | `JavaFileObject` containing class file data | Binary name, **valid** bytecode contents |
| `createResource(location, pkg, relativeName, origins...)` | `FileObject` for a new resource | Output location, package (can be empty), relative path |
| `getResource(location, pkg, relativeName)` | `FileObject` for reading an existing resource in an appropriate location | Does not create a new file; has rules restricting reading files created by the same processor |

Use **`createSourceFile`** when you want the compiler itself to process the generated Java source. `createClassFile` is intended for tools that actually generate valid class file bytecode, such as a code generator producing bytecode via a specialized library; writing Java text into `createClassFile` will not produce valid bytecode.

`createResource` is not limited to `.properties` files. It can create `.txt` files, metadata, indexes, or other resources. In this lesson, we choose a clear `META-INF/...` path.

### `originatingElements`

The trailing parameters of `createSourceFile`, `createClassFile`, and `createResource` are `Element... originatingElements`. Pass the source declaration that caused the processor to generate the product, for example class `Hello` bearing `@GenerateCompanion`. This **describes the source → output relationship**, which is useful for incremental build tools or diagnostics.

It **does not** modify the file scope/path, does not determine whether the compiler will succeed in compiling, and does not replace processing-round management logic. Accurate incremental support still depends on the build tool and processor behavior.

## 3. Source output, class output, and resource locations

A common mistake is confusing output locations.

| Tool/concept | Role |
| --- | --- |
| `-s build/generated` of `javac` | Where `.java` files generated by annotation processors are saved |
| `-d build/classes` | Where compiled `.class` files and `CLASS_OUTPUT` resources are stored |
| `StandardLocation.SOURCE_OUTPUT` | Output location for generated sources and resources created in source output |
| `StandardLocation.CLASS_OUTPUT` | Class output location; resources created here can be packaged into a JAR with classes |
| `StandardLocation.CLASS_PATH` | Location for reading/finding classes or resources on the classpath; **not the default output root for creating resources** |
| `-processorpath ...` | Where `javac` looks for processors to execute |
| `-cp ...` | Where `javac` looks for types needed by application code during compilation |

With `createSourceFile("demo.HelloCompanion", ...)` and `-s build/generated`, the compiler creates the corresponding path:

~~~text
build/generated/demo/HelloCompanion.java
~~~

With:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/lesson/generated.txt",
        origin
);
~~~

the resource resides correspondingly at:

~~~text
build/classes/META-INF/lesson/generated.txt
~~~

The `createResource` snippet is **illustrative inside a processor**, assuming variables `filer` and `origin` exist. The `relativeName` string is a relative name using `/` per `Filer` semantics, not a Windows absolute path. Do not use names with parent traversal such as `../outside.txt` or paths starting with `/` to try escaping the output root.

**Deciding where to place resources matters**: `CLASS_OUTPUT` is usually suitable for resources that should appear on the runtime classpath; `SOURCE_OUTPUT` is suitable for resources tied to the generated sources directory. Do not expect the runtime to automatically find a resource sitting only in `build/generated` when only `build/classes` is added to the classpath.

## 4. Complete Java 17 example: generating a class and a resource

The following example uses only JDK 17+, with no Maven/Gradle or external libraries needed. We create annotation `@GenerateCompanion`, processor `CompanionProcessor`, and application `Hello`. The processor generates **`demo.app.HelloCompanion`** with method `message()`, and writes the generated class path into a resource.

Lay out the files as follows:

~~~text
filer-lab/
└── src/
    ├── api/demo/api/GenerateCompanion.java
    ├── processor/demo/processor/CompanionProcessor.java
    └── app/demo/app/Hello.java
~~~

Three separate source roots allow compiling the processor first, then using the processor when compiling the application.

### 4.1. Define the annotation

**File `src/api/demo/api/GenerateCompanion.java`:**

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateCompanion {
}
~~~

- `TYPE` allows placing the annotation on type declarations per Java rules.
- `SOURCE` is sufficient for the processor to see the annotation during compilation; when the application runs, the annotation **does not need** to appear in `Hello.class`.
- This annotation **does not generate files by itself**; a designated processor must read it.

### 4.2. Processor using createSourceFile and createResource

**File `src/processor/demo/processor/CompanionProcessor.java`:**

~~~java
package demo.processor;

import demo.api.GenerateCompanion;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
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
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.api.GenerateCompanion")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CompanionProcessor extends AbstractProcessor {
    private boolean resourceCreated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        List<String> generatedNames = new ArrayList<>();
        List<Element> origins = new ArrayList<>();

        for (Element element
                : roundEnv.getElementsAnnotatedWith(GenerateCompanion.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateCompanion requires a class",
                        element
                );
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(element)
                    .getQualifiedName()
                    .toString();
            String generated = element.getSimpleName() + "Companion";
            String qualified = pkg.isEmpty()
                    ? generated : pkg + "." + generated;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualified, element);
                try (Writer writer = source.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n");
                    }
                    writer.write("public final class " + generated + " {\n");
                    writer.write("  private " + generated + "() {}\n");
                    writer.write(
                            "  public static String message() {\n"
                            + "    return \"Generated for "
                            + element.getSimpleName()
                            + "\";\n"
                            + "  }\n"
                    );
                    writer.write("}\n");
                }
                generatedNames.add(qualified);
                origins.add(element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualified + ": "
                                + ex.getMessage(),
                        element
                );
            }
        }

        if (!generatedNames.isEmpty() && !resourceCreated) {
            try {
                FileObject resource = processingEnv.getFiler()
                        .createResource(
                                StandardLocation.CLASS_OUTPUT,
                                "",
                                "META-INF/lesson/generated.txt",
                                origins.toArray(new Element[0])
                        );
                try (Writer writer = resource.openWriter()) {
                    for (String name : generatedNames) {
                        writer.write(name + "\n");
                    }
                }
                resourceCreated = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot write generated index: "
                                + ex.getMessage()
                );
            }
        }

        return true;
    }
}
~~~

Part-by-part explanation:

1. `@SupportedAnnotationTypes` declares the fully qualified name of the annotation the processor accepts.
2. `@SupportedSourceVersion(RELEASE_17)` declares the source level the processor supports; the build commands below use `--release 17` for consistent configuration.
3. `roundEnv.getElementsAnnotatedWith(GenerateCompanion.class)` finds declarations marked with the annotation in the current round.
4. The processor generates only for `ElementKind.CLASS`. This is a lab-specific policy; `@Target(TYPE)` can also apply to other declaration kinds, yet the processor emits an error if encountering them.
5. `getPackageOf(element)` determines the package. The output name is constructed from the original class name plus `Companion`.
6. `createSourceFile(qualified, element)` creates the new source, with `element` as the originating element.
7. `source.openWriter()` writes the Java text, and `try-with-resources` closes the writer. The compiler can only process the output reliably after the file is closed.
8. `createResource(CLASS_OUTPUT, "", "META-INF/lesson/generated.txt", ...)` creates the resource in class output, not source output.
9. `resourceCreated` prevents attempting to write the same resource across multiple rounds. It is a simple flag sufficient for the lab; production processors handling data discovered in late rounds need a different aggregation strategy.
10. `return true` means the processor **claims** the annotation types being processed per the API contract. It does not mean every I/O operation succeeded.

**Intentional limitation of the lab:** the processor generates the resource index based on annotated classes discovered in the first round that produces output. For a single class `Hello`, the output is complete and deterministic. If you need to aggregate all classes generated by multiple other processors in subsequent rounds, design an **aggregating processor** with a strategy to collect elements and write the resource once at a valid time; do not recreate the same file on every round.

### 4.3. Application using the generated class and resource

**File `src/app/demo/app/Hello.java`:**

~~~java
package demo.app;

import demo.api.GenerateCompanion;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

@GenerateCompanion
public final class Hello {
    public static void main(String[] args) throws Exception {
        System.out.println(HelloCompanion.message());

        try (InputStream stream = Hello.class.getClassLoader()
                .getResourceAsStream("META-INF/lesson/generated.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing generated resource");
            }
            String index = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
            System.out.print(index);
        }
    }
}
~~~

`HelloCompanion` **does not exist in the input source**; compilation succeeds when the processor generates `HelloCompanion.java` and the compiler then compiles it. The resource is read from the runtime classpath via `ClassLoader.getResourceAsStream`.

`readAllBytes()` has existed since Java 9; the lab targets Java 17 so there are no API compatibility issues. The resource contains a trailing newline so the program uses `print` to avoid adding an extra blank line.

### 4.4. Two-stage compilation on Linux/macOS (Bash)

From the root directory `filer-lab`:

~~~bash
mkdir -p build/processor build/classes build/generated

javac --release 17 -encoding UTF-8 \
  -d build/processor \
  src/api/demo/api/GenerateCompanion.java \
  src/processor/demo/processor/CompanionProcessor.java

jar --create --file build/companion-processor.jar \
  -C build/processor .

javac --release 17 -encoding UTF-8 \
  -cp build/companion-processor.jar \
  -processorpath build/companion-processor.jar \
  -processor demo.processor.CompanionProcessor \
  -s build/generated \
  -d build/classes \
  src/app/demo/app/Hello.java

java -cp build/classes demo.app.Hello
~~~

**Exact stdout of the application:**

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

Successful `javac` and `jar` runs normally print no explanatory output lines. In the experiment, the important output structure is:

~~~text
build/
├── companion-processor.jar
├── processor/
│   └── demo/
│       ├── api/GenerateCompanion.class
│       └── processor/CompanionProcessor.class
├── generated/
│   └── demo/app/HelloCompanion.java
└── classes/
    ├── demo/app/Hello.class
    ├── demo/app/HelloCompanion.class
    └── META-INF/lesson/generated.txt
~~~

**Why does compilation succeed even though `Hello.java` calls a class that does not exist yet?** In the first round, the processor recognizes `@GenerateCompanion` and creates source `HelloCompanion.java`. The compiler continues processing the new source before finishing the compilation pass. `Hello.class` can reference `HelloCompanion.class` like a normal type.

If the processor is disabled on a **clean** build, the compiler does not generate the companion and reports `cannot find symbol` at the usage site of `HelloCompanion`.

### 4.5. Windows PowerShell

Also from root `filer-lab`, after creating the three Java files as above:

~~~powershell
New-Item -ItemType Directory -Force "build\processor", "build\classes", "build\generated" | Out-Null

javac --release 17 -encoding UTF-8 -d "build\processor" "src\api\demo\api\GenerateCompanion.java" "src\processor\demo\processor\CompanionProcessor.java"

jar --create --file "build\companion-processor.jar" -C "build\processor" .

javac --release 17 -encoding UTF-8 -cp "build\companion-processor.jar" -processorpath "build\companion-processor.jar" -processor demo.processor.CompanionProcessor -s "build\generated" -d "build\classes" "src\app\demo\app\Hello.java"

java -cp "build\classes" demo.app.Hello
~~~

Stdout matches the Bash version:

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

For simplicity, we use only **one** runtime classpath entry `build/classes`, so no entry separator `;` (Windows) or `:` (Linux/macOS) is needed. If multiple entries are needed later, use the appropriate separator for the operating system.

### 4.6. Packaging generated sources and resources into a JAR

After compiling the application, run:

~~~bash
jar --create --file build/app.jar -C build/classes .
jar --list --file build/app.jar
java -cp build/app.jar demo.app.Hello
~~~

The JAR listing must contain at least:

~~~text
demo/app/Hello.class
demo/app/HelloCompanion.class
META-INF/lesson/generated.txt
~~~

The lines above are the **entries to verify**, not the entire stdout of `jar --list` (a JAR also has a manifest and directories). When running `java -cp build/app.jar demo.app.Hello`, stdout remains:

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

Because `@GenerateCompanion` is a SOURCE-retention annotation, this application does not need to load the annotation type or the processor at runtime; the application JAR already contains `Hello`, the generated class, and the required resource.

## 5. Filer.createSourceFile: choosing the right name, right content

The `name` argument of `createSourceFile` is a **type name** following proper Java syntax, not an arbitrary file path. Example:

~~~java
JavaFileObject output = processingEnv.getFiler()
        .createSourceFile("com.acme.generated.UserMapper", origin);
~~~

This snippet is **code inside a processor**. If `-s target/generated-sources`, the corresponding file is:

~~~text
target/generated-sources/com/acme/generated/UserMapper.java
~~~

Principles to follow:

- Compute the fully qualified name from package + simple name of the target type. Do not manually concatenate OS path separators in the argument.
- Emit a package declaration matching the requested name: `package com.acme.generated;` for class `UserMapper`.
- For a public generated class, the file name and class name must follow Java rules.
- Ensure the generated source is valid Java. To emit Java strings from annotation data, properly **escape** `"`, `\`, newlines, and control characters; do not concatenate untrusted data into string literals without processing.
- Close `Writer` or `OutputStream` before expecting the compiler to compile the new source.
- Use originating elements so build tools gain source-to-product relationships.
- Do not create the same qualified name multiple times in a single processing run.

In this lab, a simple class name like `Hello` is a valid Java identifier, so emitting the string `Generated for Hello` is safe. General-purpose processors generating code from user-input-style annotation values must use reliable escaping/code-generation tools or perform strict data validation.

## 6. Filer.createResource: package, relativeName, and output location

Signature to remember:

~~~java
FileObject createResource(
    JavaFileManager.Location location,
    CharSequence pkg,
    CharSequence relativeName,
    Element... originatingElements
) throws IOException;
~~~

This is a **simplified API signature for explanation**, not a method to copy verbatim into a learner's class.

Components:

- **`location`**: a supported output location, typically `StandardLocation.CLASS_OUTPUT` or `SOURCE_OUTPUT`.
- **`pkg`**: package name used to structure the resource by package layout; use `""` if the resource resides at the root of the location.
- **`relativeName`**: relative resource name inside the package/location, using `/` between segments.
- **`originatingElements`**: original declarations that caused the resource to be generated, useful for build tools.
- **`FileObject`**: permits `openWriter()`, `openOutputStream()`; **do not arbitrarily open two different streams to write to the same file**.

Example A, shared resource at the class output root:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/acme/index.txt",
        origin
);
~~~

Path under `-d build/classes`:

~~~text
build/classes/META-INF/acme/index.txt
~~~

Example B, resource corresponding to package `com.acme`:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "com.acme",
        "config/defaults.properties",
        origin
);
~~~

Path under class output:

~~~text
build/classes/com/acme/config/defaults.properties
~~~

Snippets A/B are **processor fragments**, assuming `filer`, `origin`, and `StandardLocation` import exist. Do not treat `pkg` as an arbitrary file path: use a Java package name, do not pass `com/acme` into this parameter.

### Writing UTF-8 and binary resources

`openWriter()` uses the character encoding provided by the JavaFileManager/compiler environment. For absolute encoding control on resources exchanged across multiple systems, you can write UTF-8 bytes via `openOutputStream()`:

~~~java
byte[] bytes = "status=generated\n"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
try (java.io.OutputStream out = resource.openOutputStream()) {
    out.write(bytes);
}
~~~

The fragment above requires variable `resource` to be a newly created `FileObject`, not a standalone program. For JSON, protobuf, or binary payloads, choose a clear convention for encoding/serialization. When creating a new file, the content and location of the resource must be consistent with how the application locates it via `ClassLoader.getResource(...)`.

### Reading an existing resource

`Filer.getResource(...)` is used to obtain a `FileObject` for an existing resource in a compiler-supported location. Distinguish it from `createResource(...)`; the API is designed for the compiler to manage newly created files, **not** for a processor to arbitrarily write and re-read the same file like an overwritable cache. Some locations and files created within the same run have restricted access, so avoid “create → reopen to edit” or “recreate if content differs” workflows.

## 7. Rounds, duplicate files, and FilerException

Annotation processing can have multiple rounds, especially when a processor creates new `.java` files. Each round uses `RoundEnvironment` to report the current root/annotated elements and status. Code typically contains:

~~~java
if (roundEnv.processingOver()) {
    return true;
}
~~~

The lines above avoid generating new files in the final round in the example. When a processor creates a Java file in one round, the compiler can inspect that file in the subsequent round. A pure resource does not by itself cause the compiler to discover a new type.

### Filer checks against creating the same path multiple times

An **intentionally incorrect** example inside a processor:

~~~java
filer.createSourceFile("demo.Generated");
filer.createSourceFile("demo.Generated"); // Error recreating the same file.
~~~

Typically the second call throws `FilerException` (a subclass of `IOException`), because a file with that name has already been created in the same processing run. Do not fix it by catching and ignoring the exception unconditionally: understand **why** the processor tried to create it twice.

Common situations:

- Two annotated types have the same simple name in the same package and the generator algorithm produces a shared output name.
- One processor creates the same file across two processing rounds.
- Two processors both try to generate a class/resource with the same name and location.
- A processor tries to overwrite a source file that is an original input.
- Incremental builds leave old output behind causing behavior to differ across build tools, or the generator has unstable logic.

**Correct rule:** determine each unique output name, decide which processor owns it, and create it once in a single compiler processing run. If multiple annotated elements contribute to one resource index, collect the information and **write one aggregated resource once**.

### Processor state and multi-round handling

A processor instance can retain state across rounds within a single run. In the lab, `resourceCreated` prevents recreating `META-INF/lesson/generated.txt`. Do not assume **every** instance, build daemon, or compilation invocation reuses the exact same state across builds.

Two common patterns exist:

- **Isolating output**: each annotated element generates a separate file such as `HelloCompanion.java`. The origin should be that element.
- **Aggregating output**: multiple annotated elements contribute to a single index file. The write timing and origins must be designed so the output does not lose data arriving in late rounds.

The terms isolating/aggregating are commonly used by build tools to classify processors for incremental compilation. They are not two methods of `Filer`. To support incremental builds, comply with the specific contracts of Gradle/Maven/IDEs and test modifying/deleting inputs; passing `originatingElements` alone is not enough.

## 8. Is generated source compiled automatically?

Within a single `javac` run with annotation processing, source created by `Filer.createSourceFile` can be fed by the compiler into subsequent processing rounds and compiled, like `HelloCompanion.java` in the example.

However, remember three points:

1. **`-proc:only`** only runs annotation processing without performing normal class compilation; generated source exists, but `HelloCompanion.class` will not necessarily exist.
2. **`-proc:none`** disables annotation processing. On a clean build, `Hello.java` referencing the ungenerated class can report `cannot find symbol`.
3. **Depending on the build tool**, generated sources may be processed in a subsequent compiler task rather than directly within the same `javac` invocation. Observe the actual command and output directories to determine the pipeline.

Example checking compilation with an explicit processor:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp build/companion-processor.jar \
  -processorpath build/companion-processor.jar \
  -processor demo.processor.CompanionProcessor \
  -s build/generated -d build/classes \
  src/app/demo/app/Hello.java
~~~

This is similar to the command in Section 4, assuming the processor has been packaged into a JAR and output directories exist. If the command succeeds, inspect both the generated source **and** the generated class; merely having a `.java` file is not enough to prove the application can run.

## 9. Processor path, annotation API, and discovery

In the lab, the processor JAR contains both the annotation type and the processor class. We clearly separate:

- **`-processorpath build/companion-processor.jar`** tells the compiler where to find the **processor executable**.
- **`-cp build/companion-processor.jar`** tells the compiler where to find the type `demo.api.GenerateCompanion` imported by `Hello.java`.
- **`-processor demo.processor.CompanionProcessor`** invokes the processor **by name**, without relying on compiler auto-discovery.

If `-cp` is omitted in a setup where the annotation is not on the search path, `Hello.java` cannot find `GenerateCompanion` even though the processor path may contain that class. Conversely, merely having the annotation on the compile classpath does not guarantee the processor is activated during the build.

### Service registration for processors

The following file can be packaged into the processor JAR:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Its content is the fully qualified name of the processor:

~~~text
demo.processor.CompanionProcessor
~~~

When discovery is enabled and the processor is placed on the processor search path, `javac` can use `META-INF/services` to discover the processor. However, default behavior for processor auto-discovery can vary by JDK version, configuration, and build tool. For the lab, we choose **explicit `-processor`** to eliminate this factor.

If using Maven/Gradle, configure annotation processor dependencies separately (if the build plugin supports it) instead of putting every processor onto the runtime classpath. Processors execute **code at build-time** and can access the build process's filesystem/environment; control trusted dependency sources.

## 10. Difference between createSourceFile and AST transformation

A JSR 269 processor views types through `TypeElement` and the `javax.lang.model` model. It can read annotations, methods, fields, and type signatures, yet the standard API **does not provide `TypeElement.addMethod(...)`** to directly alter the `Hello` class.

Result of the lab:

~~~text
Input: Hello.java
           |
           +--> Class Hello still contains main() as in source
           |
           +--> Filer creates new type HelloCompanion
                   |
                   +--> static message()
~~~

If the requirement is “add a getter to class Hello itself even though the source lacks a getter”, `Filer.createSourceFile("demo.app.HelloCompanion", ...)` **does not** perform that operation. A different strategy is needed: generating a subclass/helper, generating the entire source via a template, using compiler-specific AST extensions, or bytecode transformation. Those mechanisms carry their own contracts and compatibility risks and do not belong to standard `Filer` AST modification rights.

Similarly, `createClassFile(...)` creates **a new class file**; it is not a convenient way to “patch” the bytecode of an existing input class in the same compilation. Bytecode transformation systems have different APIs and lifecycles.

## 11. Emitting diagnostics when file generation fails

In the lab, an I/O error generating source is reported with:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Cannot generate " + qualified + ": " + ex.getMessage(),
        element
);
~~~

This is **code inside the `process` method**, with corresponding variables. Attaching `element` helps the compiler point to the related declaration location. `Diagnostic.Kind.ERROR` typically causes compilation to fail; it is appropriate when the generated type or resource is required for the application to compile/run properly.

Diagnostic classification:

| Kind | When to use |
| --- | --- |
| `NOTE` | Information for debugging/tracing if needed |
| `WARNING` | Notable situation not yet requiring halting the build |
| `MANDATORY_WARNING` | Warning the tool must display per contract |
| `ERROR` | Wrong annotation input, required output cannot be created, or correct result cannot be guaranteed |

Do not lose the cause when reporting errors; include the generated type/path name and I/O message so users know which output failed. However, avoid exposing secrets of the build environment in diagnostics.

### How should a processor react when errors occur?

- If an annotation is placed on the wrong declaration kind: report the error immediately at the element without creating invalid output.
- If an output name collides: report a meaningful error instead of swallowing `FilerException`.
- If source generation fails midway: close the stream via `try-with-resources` and report an error.
- If a generator dependency is missing: fix the processor path/compile path rather than trying to call runtime reflection to “self-heal”.
- If the build already has an error in the current round: you can inspect `roundEnv.errorRaised()` and limit generating unreliable outputs, depending on processor policy.

## 12. Designing a resource index usable at runtime

Suppose a processor needs to generate a file listing components, routes, mappers, or service implementations. A common pattern is:

~~~text
META-INF/my-framework/components.idx
  demo.app.HelloCompanion
  demo.app.OtherCompanion
~~~

This is a **resource index illustration**, not the actual content of the single-class lab in Section 4. The advantage is that the runtime can read a metadata file instead of scanning every class via reflection.

To keep a resource index durable:

1. Clearly define the format (UTF-8, newlines, comments, escaping).
2. Determine whether there is one index per module/JAR or multiple same-named files needing merging.
3. When multiple elements contribute, choose an aggregation strategy that does not miss late rounds.
4. Avoid duplicate lines and optionally sort names for reproducible builds.
5. Emit into `CLASS_OUTPUT` so it is packaged with runtime artifacts when the build pipeline supports it.
6. If building a **fat/uber JAR**, check whether the packaging tool merges same-named resources or keeps only one file.
7. When the runtime uses `ClassLoader.getResource(...)`, it retrieves only one matching URL; if metadata from multiple JARs is needed, use `getResources(...)` and merge in a controlled manner.

**Do not confuse this with `META-INF/services/<service-interface>`.** That is the standard metadata format for `ServiceLoader` to find providers. If writing `META-INF/services`, you must comply with the format, service name, and constructor/provider/module conditions per the `ServiceLoader` mechanism; merely creating an arbitrary file inside `META-INF` does not cause the JVM to automatically register a service.

## 13. Filer in incremental builds and testing

In a real build, generated sources and resources are **products** of a set of inputs. If original sources change or class names are deleted, the build tool needs to determine which outputs to regenerate or delete. Because the lab uses manual steps, cleaning outputs can affect results:

~~~bash
# On Linux/macOS: clean only the lab's build directory
rm -rf build
~~~

The command above **is only manual guidance** and should not be run if you are in the wrong directory or have important data in `build`. On Windows, you can use the build tool's clean task or delete only the exact output directory of the lab; do not delete arbitrary directories.

### Testing the processor

Cases to test:

- Valid inputs generate the right qualified name, package, method, and resource.
- Invalid input types (e.g., annotation placed on an interface when policy only accepts classes) emit `ERROR`.
- Two inputs producing the same output name are detected and reported clearly.
- The same processor across multiple rounds does not generate duplicates.
- Generated Java output compiles at the target source level.
- Resources actually reside on the runtime classpath/JAR, readable with the right encoding and path.
- Incremental builds editing/deleting an annotated type produce corresponding results; do not let stale generated classes/resources cause false success.
- Building with different Java compilers/JDKs that the processor declares support for.

If testing codegen by checking `String.contains("Generated for Hello")`, that is only a text check. Reliable tests must also **compile the generated source** and, when appropriate, execute its behavior on the target runtime.

## 14. Common errors when using Filer

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `cannot find symbol: HelloCompanion` | Processor did not run, did not generate file, source output not compiled, or stale classes | Verify `-processor`, processor path, `-s`, `-d`, and diagnostics |
| `FilerException: Attempt to recreate a file ...` | Attempted to create the same path multiple times in one processing run or duplicate input | Check rounds, output names, processor coordination; create only once |
| `HelloCompanion.java` exists but `.class` is missing | Used `-proc:only`, compilation stopped halfway, or build has not compiled generated sources | Run the proper compile phase and inspect compiler errors |
| Resource exists in `build/generated` yet runtime cannot see it | Placed in wrong location or resource not copied to runtime classpath | Use `CLASS_OUTPUT` if resource is for runtime; check JAR |
| `getResourceAsStream(...) == null` | Wrong path, resource not packaged, different classloader | Inspect JAR via `jar --list`, verify classpath/loader |
| Generated class package name is incorrect | `createSourceFile` name does not match package declaration | Use qualified name and emit matching package |
| Processor is not discovered | Missing `-processor`, wrong service file, or processor path | Specify processor explicitly in build |
| Processor runs but finds no annotated elements | Wrong annotation name/import, input not in compilation, wrong target | Inspect `RoundEnvironment` and log via `Messager` |
| Generated source contains invalid Java string | Failed to escape annotation values when generating code | Use proper serializer/escaping; compile generated source |
| Rebuilding yields wrong/missing index data | Aggregating logic missed late rounds, stale output | Design single aggregation write, test clean/incremental |
| UTF-8 resource has garbled accents | Inconsistent writer/reader encoding | Write UTF-8 bytes or explicitly configure compiler encoding |
| Old compiler warns about processor source version | `@SupportedSourceVersion` does not match running source level | Use supported processor version, configure source/target accordingly |

When investigating, start from **what is on disk**: inspect generated source files, generated `.class` files, and resources before looking for runtime bugs. Avoid tweaking the runtime classpath if sources were not generated at compile time.

## 15. Self-check exercises with answers

**Exercise 1.** With `-s build/generated`, the processor calls `createSourceFile("com.demo.MapperImpl", origin)`. Where is the file typically generated?

**Answer:** `build/generated/com/demo/MapperImpl.java`, with package declaration `package com.demo;` in the source.

**Exercise 2.** The processor needs to create a file `META-INF/config/index.txt` for the application to read after JAR packaging. Which location should be used?

**Answer:** Usually `StandardLocation.CLASS_OUTPUT` with an empty package and relative name `META-INF/config/index.txt`; verify the packaging pipeline copies resources into the JAR.

**Exercise 3.** The processor calls `createSourceFile("demo.Generated")` in round 1 and round 2 of the same compilation. Is this valid?

**Answer:** No. Filer manages output names within a processing run; attempting to recreate the same file typically leads to `FilerException`.

**Exercise 4.** `@GenerateCompanion` has SOURCE retention. Can the processor read it? Does runtime reflection see it on `Hello.class`?

**Answer:** The processor can read it from the compilation model. Ordinary runtime reflection does not see SOURCE-retention annotations in class files.

**Exercise 5.** Does `createClassFile(...)` allow writing source text `public class Demo {}` and automatically turning it into bytecode?

**Answer:** No. That method is for generating valid class files; to generate source text for the compiler to compile, use `createSourceFile(...)`.

**Exercise 6.** Why does `Hello.java` still report it cannot recognize `demo.api.GenerateCompanion` even though the processor JAR is already on `-processorpath`?

**Answer:** The processor path is for loading processors; the annotation type imported by source still needs to appear on the compilation type search path, such as the appropriate compile classpath.

**Exercise 7.** Does `originatingElements` automatically guarantee incremental builds delete all old generated files when inputs are deleted?

**Answer:** No. It provides source-to-output relationships, while incremental/cache/cleanup logic is carried out jointly by the build tool and processor.

**Exercise 8.** When two JARs contribute metadata with the same resource name, does `ClassLoader.getResource(...)` merge the contents of both?

**Answer:** No. `getResource` returns one matching resource; if multiple resources need to be found, use `getResources` and apply explicit merging logic.

## Key takeaways

- **`Filer` is the output API for annotation processors**: creates sources, class files, and resources in the build; does not modify the AST of the original class.
- **`createSourceFile`** accepts a qualified type name; the compiler can compile the new source in the next round.
- **`createResource`** accepts location, package, and relative name; `CLASS_OUTPUT` is suitable for many resources needed in the runtime JAR.
- **`-s` and `-d` differ**: `-s` for generated sources, `-d` for class files and `CLASS_OUTPUT` resources.
- **Close Writer/OutputStream** after writing; never create the same path multiple times; report `FilerException` and IO errors via `Messager`.
- **Rounds and originating elements** matter for codegen, especially when generating aggregated resources and incremental builds.
- **Processor path and compile classpath have distinct roles**; configure the processor explicitly and verify generated `.java`, `.class`, and resources in the artifact.
