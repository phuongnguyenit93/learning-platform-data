# Representing Source Code with SimpleJavaFileObject and Appropriate URIs

In Java, **compiling source code in memory** does not necessarily require creating `.java` files on disk. The `javax.tools.JavaCompiler` API accepts `JavaFileObject` instances representing compilation units. A simple way to create an input is to **extend `SimpleJavaFileObject`, attach a URI representing the proper source name, select `Kind.SOURCE`, and return the Java content via `getCharContent(...)`**.

However, "the content is a `String`" is not enough for the compiler to properly understand a compilation unit. **The URI must match the class/package name and file kind**, because the compiler and file manager may use that name to identify the unit, check compatibility, emit diagnostics, and manage multiple sources.

This lesson explains the API contracts, rules for constructing reliable URIs, a Java 17 example compiling from a `String` and keeping `.class` files in memory as well, along with common pitfalls involving source names, namespaces, diagnostics, class loaders, and resource lifecycles.

## 1. Distinguishing Source Code, JavaFileObject, URI, and Physical Files

A problem typically begins with dynamically generated source code:

```java
String code = """
        package demo.generated;
        public final class Greeter {
            public static String message() {
                return "Hello from memory";
            }
        }
        """;
```

The snippet above is a **Java string**, not a file on the filesystem. To pass it to `JavaCompiler`, you need a **compilation unit** with a name, a kind, and a way to read its content:

```text
Java source code string (String)
          |
          v
SimpleJavaFileObject (Kind.SOURCE)
  - URI: string:///demo/generated/Greeter.java
  - getCharContent(): returns source code
          |
          v
JavaCompiler.getTask(..., compilationUnits)
          |
          v
JavaFileManager receives output bytecode
          |
          v
Class bytes and/or class loaded into ClassLoader
```

There are four concepts:

| Concept | Role | What not to confuse it with |
| --- | --- | --- |
| `String` / `CharSequence` | Unicode Java source code content | Does not contain package/file kind metadata |
| `JavaFileObject` | Abstraction for source, class, or other output kinds | Does not have to point to a file on disk |
| `URI` | Identifier of the input/output object | `string:///...` or `mem:///...` is not a web address or a real file |
| `JavaFileManager` | Provides input/output to the compiler and manages where classes are written | Input from memory does **not automatically** make output go to memory |

`SimpleJavaFileObject` is a base class that helps implement `JavaFileObject` with default behaviors. When you only need to feed source from a string into the compiler, overriding `getCharContent(...)` is usually sufficient. When you need to **capture bytecode without writing to disk**, you must additionally handle output using an appropriate `JavaFileManager`.

## 2. JavaFileObject and SimpleJavaFileObject Contracts

### `JavaFileObject.Kind`

`JavaFileObject.Kind` tells the compiler the kind of unit:

- `SOURCE`: Java source code; default extension `.java`.
- `CLASS`: Java bytecode; extension `.class`.
- `HTML`: HTML documentation.
- `OTHER`: all remaining kinds.

**Sources created from a `String` must declare `Kind.SOURCE`**, not `Kind.CLASS`. Conversely, class bytes produced after compilation must be represented with `Kind.CLASS`. A kind that does not match the content can cause the compiler and file manager to misbehave.

### SimpleJavaFileObject Constructor

```java
protected SimpleJavaFileObject(URI uri, JavaFileObject.Kind kind)
```

The constructor takes a **valid URI** and a `kind`, storing that information for use by methods such as `toUri()`, `getKind()`, and `isNameCompatible(...)`. The URI must have a **non-empty path component**; do not think of the URI as merely an arbitrary label string. The URI should provide a logical path consistent with the package and file name.

### `getCharContent(boolean ignoreEncodingErrors)`

An in-memory SOURCE object typically overrides:

```java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
```

This is a snippet of a subclass having a `sourceCode` field of type `String` or `CharSequence`. The compiler can retrieve the source through this method, so there is no need to create a `FileInputStream`. The `ignoreEncodingErrors` parameter is originally meaningful in implementations that must decode bytes; when the content is already held in a `String`, decoding has already happened earlier. Encoding errors must not be ignored when **reading the initial bytes** from another source.

The default methods of `SimpleJavaFileObject` do not turn it into a general-purpose file I/O object. For example, if you only override `getCharContent`, do not assume `openInputStream`/`openOutputStream` will be supported. If the compiler or another component actually needs a separate byte/reader path, you must implement that contract properly.

### `isNameCompatible(...)`

`JavaFileObject.isNameCompatible(simpleName, kind)` checks whether the source name is compatible with a simple class name and file kind. With the URI:

```text
string:///demo/generated/Greeter.java
```

`isNameCompatible("Greeter", Kind.SOURCE)` returns `true` in practice. A URI ending in a different name or a different extension can cause the check to fail. In addition to simple-name compatibility, the **package name in the source code** also needs to match how the application identifies the compilation unit.

## 3. Appropriate URIs for Java Sources Created in Memory

### The Most Important Rule

For a normal **binary name** of a top-level class, for example `demo.generated.Greeter`, you can construct:

```java
String binaryName = "demo.generated.Greeter";
URI uri = URI.create("string:///" +
        binaryName.replace('.', '/') +
        JavaFileObject.Kind.SOURCE.extension);
```

Result:

```text
string:///demo/generated/Greeter.java
```

The URI path now accurately reflects the components:

- `demo.generated` → `demo/generated/`;
- `Greeter` → top-level type/compilation unit name;
- `.java` → extension of `Kind.SOURCE`;
- `string` → custom scheme expressing application-supplied source data, without asserting the existence of a `.java` file on the filesystem;
- `///` → URI structure with an absolute path, not "three slashes equivalent to an OS path".

For a simple unit, this formula is readable and commonly used with the compiler API. `JavaCompiler` treats the `JavaFileObject` as the source; it does not need to make an HTTP call or access a file named `string:///...`.

### Why Not Use URIs Like These?

| URI/representation | Problem |
| --- | --- |
| `URI.create("Greeter.java")` | Relative URI, missing scheme; not a suitable choice for an object identified by the compiler/file manager |
| `URI.create("string:///Greeter")` | Missing `.java` extension, name is incompatible with `Kind.SOURCE` by convention |
| `URI.create("string:///demo/Other.java")` | Inconsistent with the requested name `Greeter`; easily confusing in diagnostics |
| `URI.create("file:///tmp/Greeter.java")` even when no file exists | Using the `file` scheme easily creates false expectations that a real file exists or triggers filesystem logic in other components |
| `URI.create("string:///demo.generated.Greeter.java")` | Uses package dots instead of converting them into `/` segments; wrong intended namespace |
| `URI.create("string:///demo/Greeter.java")` when the source has package `demo.generated` | URI does not reflect the intended package directory; prone to errors if the compiler/file manager needs to infer the binary name |
| `URI.create("string:///demo/My File.java")` | Unencoded space causes `URI.create` to throw an error; valid names must be validated/encoded |

**Not every URI other than `string:///...` is forbidden by the JDK.** This is a **stable, highly compatible convention** for in-memory sources. You can use `mem`, `memory`, or another custom scheme if your application's file manager/compiler handles it. What matters is that the URI is valid, has a complete path, is consistent with the source name/kind, and is not mistaken for a physical file path.

### Normalization and Name Safety

Do not concatenate raw, free-form user-entered `className` values directly into a URI and pass them to the compiler. First, you must:

1. Determine the class name from application-validated metadata or parse it according to Java rules, rather than just guessing from trailing characters.
2. Validate that the package name and each identifier are valid, without `/`, path-traversal-style `..`, whitespace, or control characters.
3. Enforce a policy on allowed generated classes/namespaces; do not create names that shadow host classes.
4. Use the `URI` API to encode when names genuinely need special characters; avoid hand-building URL strings from untrusted input.

You can start with an ASCII identifier whitelist if your product only permits that style of name; however, do not confuse an ASCII whitelist with the **entire** Java identifier syntax, which allows Unicode.

### Special File Names

Multi-compilation-unit problems also need to handle:

- `package-info.java`: not an ordinary top-level class name;
- `module-info.java`: module descriptor, does not have a class FQCN following the dot-replacement formula;
- multiple top-level types in one file: the **compilation unit name** must match the public top-level type and Java's file-naming rules;
- nested/anonymous classes: a top-level source file can emit multiple `.class` files such as `Outer$Inner.class`; you should not create a "source URI for an inner class" unless it truly is an independent source unit.

Therefore, the formula `binaryName.replace('.', '/') + ".java"` is suitable for **ordinary top-level types**, not a universal solver for every kind of Java source file.

## 4. Standalone Java 17 Example: String → SimpleJavaFileObject → Bytecode in Memory

The following example performs **both parts**:

1. The source resides in a `String`, wrapped in `SourceFile extends SimpleJavaFileObject` with URI `string:///demo/generated/Greeter.java`.
2. The output bytecode is intercepted by `MemoryFileManager` and stored in the `ByteArrayOutputStream` of `ClassFile` with URI `mem:///demo/generated/Greeter.class`.

After compilation, the example uses a dedicated `ClassLoader` to define the class from bytes. No source or bytecode file for `demo.generated.Greeter` is created on disk; only `MemoryCompileDemo.java` and `MemoryCompileDemo.class`, used to run the **demonstration program**, are physical files.

### 4.1. File MemoryCompileDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class MemoryCompileDemo {
    static final class SourceFile extends SimpleJavaFileObject {
        private final String code;

        SourceFile(String binaryName, String code) {
            super(URI.create("string:///" +
                            binaryName.replace('.', '/') +
                            JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        ClassFile(String binaryName) {
            super(URI.create("mem:///" +
                            binaryName.replace('.', '/') +
                            JavaFileObject.Kind.CLASS.extension),
                    JavaFileObject.Kind.CLASS);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] bytecode() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassFile> outputs = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(location, className, kind, sibling);
            }
            ClassFile output = new ClassFile(className);
            outputs.put(className, output);
            return output;
        }

        Map<String, byte[]> classBytes() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            outputs.forEach((name, file) -> result.put(name, file.bytecode()));
            return Map.copyOf(result);
        }
    }

    public static void main(String[] args) throws Exception {
        String name = "demo.generated.Greeter";
        String code = """
                package demo.generated;
                public final class Greeter {
                    public static String message() {
                        return "Hello from memory";
                    }
                }
                """;

        SourceFile source = new SourceFile(name, code);
        System.out.println("sourceUri=" + source.toUri());
        System.out.println("kind=" + source.getKind());
        System.out.println("compatible=" +
                source.isNameCompatible("Greeter", JavaFileObject.Kind.SOURCE));

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiled;

        StandardJavaFileManager standard = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
        try (MemoryFileManager files = new MemoryFileManager(standard)) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(source));
            if (!Boolean.TRUE.equals(task.call())) {
                for (Diagnostic<? extends JavaFileObject> diagnostic
                        : diagnostics.getDiagnostics()) {
                    System.err.println(diagnostic);
                }
                throw new IllegalStateException("Compilation failed");
            }
            compiled = files.classBytes();
        }

        System.out.println("generated=" + compiled.containsKey(name));

        ClassLoader loader = new ClassLoader(MemoryCompileDemo.class.getClassLoader()) {
            @Override
            protected Class<?> findClass(String binaryName)
                    throws ClassNotFoundException {
                byte[] bytes = compiled.get(binaryName);
                if (bytes == null) {
                    throw new ClassNotFoundException(binaryName);
                }
                return defineClass(binaryName, bytes, 0, bytes.length);
            }
        };
        Class<?> greeter = loader.loadClass(name);
        System.out.println("result=" + greeter.getMethod("message").invoke(null));
    }
}
```

**Compile and run:** in the directory containing `MemoryCompileDemo.java`, with JDK 17+:

```bash
javac --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
```

**Verified stdout with `javac --release 17` and `java`:**

```text
sourceUri=string:///demo/generated/Greeter.java
kind=SOURCE
compatible=true
generated=true
result=Hello from memory
```

There is no need to place `demo.generated.Greeter` into a `demo/generated` directory to compile: the compiler reads the source via `getCharContent`. The output manager receives the class name requested by the compiler, creates a `ClassFile`, and collects the bytes. The class loader receives those bytes and defines the class when `loadClass("demo.generated.Greeter")` runs.

### 4.2. Breakdown of Key Points

**A. The source URI logically links the package and compilation unit name**

`SourceFile(name, code)` creates the URI:

```text
string:///demo/generated/Greeter.java
```

`Kind.SOURCE` is metadata; `getCharContent` is the content. The two must go together, especially when the compiler emits diagnostics, locates source files, and matches class names. `Objects.requireNonNull` prevents a `null` source from entering compilation.

**B. Output has a different URI and Kind from the source**

`ClassFile` uses:

```text
mem:///demo/generated/Greeter.class
Kind.CLASS
```

`openOutputStream()` provides a `ByteArrayOutputStream` for the compiler to write bytecode. If you only write `SourceFile` without implementing a file manager, the compiler may write class files to the standard output location, typically on the filesystem. **Source in memory ≠ output in memory.**

**C. JavaFileManager is the compiler's I/O boundary**

`MemoryFileManager` extends `ForwardingJavaFileManager<StandardJavaFileManager>` and overrides `getJavaFileForOutput` to intercept `Kind.CLASS` outputs. It still delegates to the standard file manager for other tasks such as locating classes on the classpath/module path. In the example, the `-proc:none` option disables annotation processing so no generated sources from annotation processors need to be stored separately.

This is a deliberate demonstration: if the compiler were allowed to create `Kind.SOURCE`, resource files, or other module outputs, the current code **forwards** non-`CLASS` kinds to the standard manager. If you want **every kind of output** to stay in RAM for any complex workflow, you must handle those output paths as well rather than assuming overriding one method covers every case.

**D. Do not confuse the running class's package/loader with dynamically generated classes**

`MemoryCompileDemo` runs on the current classpath; `demo.generated.Greeter` is defined in a separate class loader. Class loaders default to **parent-first delegation**: if the parent already has a class with the same binary name, `loadClass` may return the parent's class without calling `findClass`. In the example, the name `demo.generated.Greeter` is chosen uniquely so it does not collide. In a real plugin runtime, you must control namespaces and class-loader policies so dynamic code cannot arbitrarily override host classes.

**E. Close JavaFileManager, do not keep compiler tasks indefinitely**

`try (MemoryFileManager files = ...)` closes the forwarding manager and standard manager after taking a copy of the class bytes. A Java compiler task is a lifecycle-bound operation; do not reuse the same task to compile multiple times. You should create a properly managed task/file manager or context for each compilation and release large references to source/bytecode when no longer needed.

## 5. Compiler API: Feeding Sources from CharSequence into compilationUnits

The key wiring lies in:

```java
JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        files,
        diagnostics,
        List.of("--release", "17", "-proc:none"),
        null,
        List.of(source));
boolean ok = Boolean.TRUE.equals(task.call());
```

This is a snippet taken from the program in section 4; the variables `compiler`, `files`, `diagnostics`, and `source` were already created beforehand.

The parameters of `getTask` in order are:

1. `Writer out` for the compiler to write additional output (here `null`);
2. `JavaFileManager` controlling how the compiler finds inputs and writes outputs;
3. `DiagnosticListener` receiving errors/warnings; `DiagnosticCollector` is a convenient implementation;
4. `options` such as `--release 17` (compile targeting the specified API/language level) and `-proc:none` (do not run annotation processors);
5. `classes` used for annotation processing by class name; these are not the source compilation units, so it is set to `null` in the example;
6. `compilationUnits` is an `Iterable<? extends JavaFileObject>`: here the only source is `List.of(source)`.

The key takeaway: **`JavaCompiler` does not accept a source code `String` directly as a `compilationUnits` parameter**. We use `SimpleJavaFileObject` as the I/O contract bridge.

### Compiling Multiple Classes Together

You can pass multiple source units:

```java
List<JavaFileObject> units = List.of(
    new SourceFile("demo.generated.Greeter", greeterSource),
    new SourceFile("demo.generated.Helper", helperSource)
);
```

This snippet requires two code strings `greeterSource`, `helperSource` and the `SourceFile` class as in the example. If the sources reference each other, passing all compilation units to the same task is one way for the compiler to know about those classes. You should not combine two differently named public top-level classes into one invalid source file. If the code generates nested classes, the compiler may call `getJavaFileForOutput` multiple times to write `Outer.class`, `Outer$Inner.class`, etc.; the file manager needs to store them by the **binary class name** requested by the compiler.

## 6. Diagnostics: Why URIs Matter Beyond Just "Naming"

When compilation fails, `Diagnostic<? extends JavaFileObject>` can provide:

- `getSource()`: the source object that caused the error, from which `toUri()` can be retrieved;
- `getLineNumber()`, `getColumnNumber()`: the location;
- `getKind()`: ERROR, WARNING, NOTE;
- `getMessage(locale)`: the descriptive message.

Illustrative logging snippet (using the existing `DiagnosticCollector<JavaFileObject> diagnostics`):

```java
for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
    String sourceUri = d.getSource() == null
            ? "(unknown)" : d.getSource().toUri().toString();

    System.err.printf("%s %s:%d:%d %s%n",
            d.getKind(), sourceUri,
            d.getLineNumber(), d.getColumnNumber(),
            d.getMessage(Locale.ROOT));
}
```

This snippet is not a standalone program; it requires the imports and variables from section 4. A stable logical URI like `string:///demo/generated/Greeter.java` helps frontends/editors map errors back to the right tab or generated source unit. If all source objects share `string:///Source.java`, multi-file diagnostics may become indistinguishable; if URIs are randomly generated every time for no reason, correlating results and caching become harder.

**A diagnostic's source is not always present** (for instance, certain option/configuration errors), so always check for `null`. Some errors have negative line/column numbers when the position cannot be determined. Do not let logs accidentally contain secret source code or infrastructure details if the source originates from sensitive content.

## 7. Naming Rules: Binary Name, Canonical Name, Source File Name

For the top-level type `demo.generated.Greeter`:

```text
Binary name:       demo.generated.Greeter
Package:           demo.generated
Simple name:       Greeter
Source URI path:   /demo/generated/Greeter.java
Source kind:       SOURCE
Class URI path:    /demo/generated/Greeter.class
Class kind:        CLASS
```

That is the standard mapping. However, concepts must be separated when scaling up:

- The **binary name** of a nested class can contain `$`, for example `demo.generated.Outer$Inner`; the **source file** declaring both can still be `Outer.java`.
- The **canonical name** may use `.` for nested types; do not arbitrarily turn a canonical name into a source file path. Obtain the actual compilation unit/top-level type metadata.
- `package-info.java` and `module-info.java` do not follow the "one source per top-level class" rule.
- For sources without a package (unnamed package), a URI such as `string:///Greeter.java` may suit simple environments, but production plugins/modules should use explicit namespaces to avoid collisions.

In the demo, `MemoryFileManager.getJavaFileForOutput` receives `className` **provided by the compiler**, so it works properly for auxiliary/nested classes emitted by the compiler as well. You should not assume each `SourceFile` produces exactly one `.class`.

### On Non-File URIs: Do Not Convert Them Back into Paths

When `source.toUri()` is `string:///...`, this snippet is invalid as a way to obtain a source file:

```java
// Invalid example: there is no filesystem provider for the "string" scheme.
java.nio.file.Path path = java.nio.file.Path.of(source.toUri());
```

The snippet above is an invalid illustrative example and should not be executed as sample code. `Path.of(URI)` requires a filesystem provider matching the URI; `string` here is a logical identifier, not an assertion that a physical file exists. If you want to save sources for debugging or export, you must perform **explicit** I/O operations according to application policy, rather than assuming a custom URI automatically maps to a file.

## 8. Source in Memory Does Not Mean "Disk-Free" Compilation Completely

A compilation task may still need to reference physical artifacts:

- `javac` locates dependency classes and modules through the standard file manager, classpath/module path;
- Java APIs and libraries may reside in the JDK runtime image, JARs, or external sources;
- annotation processors may generate additional sources/classes/resources and request different output locations;
- if the default file manager receives `CLASS_OUTPUT`, output classes may be written to disk.

**The complete example disabled annotation processing (`-proc:none`)** and intercepted `Kind.CLASS` to clearly demonstrate in-memory output; it does not claim the compiler/JDK reads zero physical resources during dependency resolution.

If you want to compile a multi-module project, run annotation processing, or perform incremental compilation solely from memory, you must build a `JavaFileManager` that additionally manages `list`, `getJavaFileForInput`, `inferBinaryName`, module locations, `getFileForOutput`/`getJavaFileForOutput`, and graph-based caching. Do not assume a single `SourceFile` wrapper suffices to replace an entire build system.

### When Should You Use StandardJavaFileManager?

`StandardJavaFileManager` is well suited for the compiler to fetch external libraries from the classpath/module path and handle standard paths that the application does not override. `ForwardingJavaFileManager` lets you preserve that behavior while replacing only the output writing or dynamic input handling as needed. This is usually far less error-prone than implementing `JavaFileManager` entirely from scratch.

If you need to support dynamically generated sources in a subsequent compilation pass, a registry can store both source code and bytecode and supply corresponding `JavaFileObject` instances by package/binary name. Be sure to manage source versions, cache invalidation, and class loader ownership to avoid picking up stale versions.

## 9. Designing a Maintainable SourceFile

Minimal pattern:

```java
final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') +
                Kind.SOURCE.extension), Kind.SOURCE);
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

This is a snippet requiring `URI` and `SimpleJavaFileObject` imports (and a Java 17+ environment) when placed standalone. It is the core of a text source. In practice, responsibilities should be separated:

1. **Source identity**: package, top-level type, name, version, URI; created consistently and immutably.
2. **Source content**: immutable `String` or `CharSequence` for stable reading by the compiler.
3. **Compilation diagnostics**: map each URI to its input source and errors.
4. **Output bytecode**: mapped by binary class name, kept separate from the input source.
5. **Runtime loading**: class loader with well-defined scope/version and lifecycle.

`SourceFile` should not create class loaders itself, save physical files on its own, or hold JVM-wide caches merely because it has a URI; doing so mixes source-model responsibilities with build/runtime responsibilities.

### Thread Safety

A `SourceFile` holding an immutable `String` is generally easy to share as data. However, **`JavaCompiler.CompilationTask`, `JavaFileManager`, and output storage** are stateful and should not be assumed safe for concurrent use across multiple jobs without control. Each compilation job should have its own source list, diagnostics, and output mapping. If caching is used, publish only completed source/bytecode artifacts with proper concurrency mechanisms.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Compiler says source or class not found despite having a String | Created a String without wrapping it into `compilationUnits` via `JavaFileObject` | Create `SourceFile(URI, Kind.SOURCE)` and pass `List.of(source)` |
| Compiler/diagnostics report strange source names | URI does not match package/top-level class | Build `string:///package/path/Class.java` and validate the name |
| `isNameCompatible` returns false | URI path/extension does not match simple name/kind | Check `.java`, letter casing, and `SOURCE` kind |
| `URI.create` throws `IllegalArgumentException` | Invalid URI containing whitespace/characters needing encoding | Validate identifiers and build proper URIs instead of concatenating arbitrary user input |
| Despite source "in memory", `.class` files still appear on disk | Standard file manager still controls output | Intercept `getJavaFileForOutput` for `Kind.CLASS` and store in `ByteArrayOutputStream` |
| Source has errors but line information is missing | Not using `DiagnosticCollector` or URIs do not distinguish sources | Attach stable URIs, read `Diagnostic`, and map back to the editor |
| Nested class generated, but only outer class bytecode is present | Output manager assumed each source produces one class | Store every `className` requested by the compiler |
| Class loading returns an old implementation | Parent-first loader already holds the same binary name | Use clear namespaces, versioning, and class-loader policies |
| `ToolProvider.getSystemJavaCompiler()` returns null | Runtime does not include the system compiler (e.g., stripped-down runtime image) | Use a JDK/runtime with the required compiler module |
| `task.call()` fails | Invalid source code or missing classpath/module path | Print diagnostics; verify package, options, and dependencies |
| Works in IDE but fails in deployment | Different compilation classpath, module path, or encoding | Configure tool options/file manager explicitly; test in the real runtime |
| Untrusted plugin code poses a security risk | Mistaking custom URIs or class loaders for a sandbox | Do not run untrusted sources in a privileged JVM; isolate with appropriate process/OS policies |

### Three Misconceptions to Avoid

**"Just doing `new SimpleJavaFileObject(...)` lets the compiler read a String."** Incorrect: the base class does not automatically know about your content string. You must override `getCharContent` or an appropriate read method.

**"The URI `string:///...` is a file path that must exist."** Incorrect: it is a logical identifier; it can contain a package path and `.java` extension without any physical file. The file manager/compiler uses the URI according to the `JavaFileObject` contract.

**"In-memory input means all outputs and dependencies are in memory."** Incorrect: output is determined by the file manager, dependencies may require the classpath/module path, and annotation processors may generate many kinds of files. Each I/O path must be designed explicitly.

## 11. Safety and Limits When Compiling Dynamic Code

URI correctness **does not create a security boundary**. The compiler can consume significant CPU/RAM; compiled code, once executed, runs with the privileges of the JVM process. Therefore:

- Do not accept Java source from untrusted parties and load/run it directly in a JVM holding sensitive data. For use cases with untrusted sources, use appropriate process/container/OS permission boundaries and quotas.
- `-proc:none` disables annotation processing in the example, reducing unintended processor execution paths, **without turning javac or a class loader into a sandbox**.
- Restrict the classpath/module path, exposed APIs, and class loader selection; do not treat prefixing a URI with `mem` as a way to isolate code.
- Limit source size, compilation time, and the number of output sources/classes; manage class loader/version lifecycles to prevent metaspace leaks and stale references.
- Do not log full sources or diagnostics containing secrets if inputs contain private data.
- In multi-tenant applications, source/cache identifiers must carry separate tenant/build scopes to avoid picking up source or bytecode from another version.

## 12. Checklist for Applying to a Real Code-Generation System

- [ ] Accurate top-level source identity: package, unit name, source code, version.
- [ ] Valid URI with an appropriate scheme, path in the form `/pkg/path/Class.java`, and `SOURCE` extension.
- [ ] Consistent URI and source content; handle `module-info.java`, `package-info.java`, and nested types separately.
- [ ] `SourceFile` overrides `getCharContent(...)` rather than relying on default unsupported I/O methods.
- [ ] `JavaCompiler.getTask` receives complete compilation units and explicit compiler options.
- [ ] DiagnosticCollector retains URI/line/column to trace back to the source on errors.
- [ ] If RAM-only output is required, the file manager intercepts all output kinds the system can produce, rather than assuming only `SOURCE` from `String`.
- [ ] Bytecode results are mapped by the **class binary name** supplied by the compiler, without assuming one class per source.
- [ ] Class loader uses proper namespace, versioning, and parent delegation; lifecycle and references are managed.
- [ ] Tests cover matching package/class names, multiple sources, nested classes, Unicode, invalid sources, missing compiler, and output manager behavior.
- [ ] Resource limits and isolation policies are enforced if sources are untrusted.

### Official Java 17 References

- [`SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [`JavaFileObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html)
- [`JavaCompiler` and `CompilationTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [`ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html)
- [`DiagnosticCollector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)

**Conclusion:** `SimpleJavaFileObject` is the bridge that turns source code held in a `CharSequence` into a **compilation unit with a valid name, Kind, and URI**. The `string:///package/path/Type.java` convention cleanly identifies the source; `getCharContent` supplies already-decoded characters. To also keep `.class` files in memory, you must add an output-handling file manager and an appropriate class loader — **two responsibilities independent of creating source URIs**.