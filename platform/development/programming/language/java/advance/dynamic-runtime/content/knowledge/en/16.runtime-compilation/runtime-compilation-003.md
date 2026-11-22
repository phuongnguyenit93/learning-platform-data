# 16.3. Representing Source Code with JavaFileObject and SimpleJavaFileObject

> **Context:** Knowledge lesson under **16. Runtime Compilation** of the **Java Advance – dynamic-runtime** module. The focus is on the mechanism for representing a Java source unit as a `javax.tools.JavaFileObject`, and how to extend `SimpleJavaFileObject` to provide source code from a **`String`/memory** to the standard compiler API (JSR 199) in Java 21. The lesson also explains distinguishing `SOURCE` inputs from `CLASS` outputs, file managers, compilation results, diagnostics, class loading, and practical limitations. All examples run using the JDK without external bytecode libraries.

## 1. Learning Outcomes and Prerequisites

After this lesson, you should be able to:

1. Distinguish `FileObject`, `JavaFileObject`, `SimpleJavaFileObject`, `JavaFileManager`, `StandardJavaFileManager`, and `JavaCompiler.CompilationTask`.
2. Know how `Kind.SOURCE` differs from `Kind.CLASS`, when to use `getCharContent`, `openReader`, `openInputStream`, `openOutputStream`, and which default methods of `SimpleJavaFileObject` throw `UnsupportedOperationException`.
3. Build a `StringSource` properly using `URI.create("string:///.../Name.java")`, map a **binary class name** to a package path, and preserve `Kind.SOURCE`.
4. Pass one or more `JavaFileObject` instances into `JavaCompiler.getTask(... compilationUnits)`, use `ToolProvider.getSystemJavaCompiler()`, handle the case when the compiler is unavailable, close the file manager, and read the result of `call()`.
5. Compile source located in memory while writing `.class` files to a temporary directory; distinguish the **input source location** from the **output bytecode location**.
6. Compile **both source and class output in memory** using `ForwardingJavaFileManager` and a `CLASS`-kind `SimpleJavaFileObject`, then load the generated class via a `ClassLoader`.
7. Compile multiple source units in a single task and collect `DiagnosticCollector` entries to tie error lines back to the source object's URI.
8. Recognize limitations: do not equate a `JavaFileObject` with a file on disk, do not open a `string:` URL scheme over the network, and do not assume the compiler API is a sandbox for untrusted code.
9. Independently run five standalone Java 21 programs and understand the meaning and limitations of each stdout line.

**Prerequisites:** classes/packages and `.java` files; `String`, `URI`, `Reader`, `OutputStream`; `ClassLoader` and Reflection; `try-with-resources`; `javac` fundamentals. This lesson uses APIs in the `java.compiler` module and the standard compiler implementation included in the JDK (`jdk.compiler`).

## 2. Why doesn't the compiler only accept file paths?

A compiler typically reads source code from `src/com/example/Hello.java` and writes bytecode to `out/com/example/Hello.class`. However, plugin systems, templating, expression engines, or code generation may produce Java code directly in RAM, from a database, or from another source. To avoid tightly coupling every compiler to `Path`/`File`, the `javax.tools` API provides the **file object abstraction**.

```text
Java character source
  |
  +--- real file ------------ StandardJavaFileManager -----------+
  |                                                              |
  +--- String in RAM -------- StringSource extends               |
                             SimpleJavaFileObject                |
                                          |                      |
                                          v                      v
                                   JavaFileObject SOURCE (compilationUnits)
                                          |
                                          v
                      JavaCompiler.getTask(...).call()
                                          |
                            Compiler requests FileManager to output result
                                          |
                          +---------------+----------------+
                          |                                |
               .class on disk                  BytecodeOutput CLASS in RAM
            StandardJavaFileManager              ForwardingJavaFileManager
                          |                                |
                     URLClassLoader                  ClassLoader#defineClass
```

A **`JavaFileObject`** carries the information "this is Java source at this URI, with this content" or "this is class output at this URI, with a stream to write bytes". That does not mean it **is** an operating system file. A `URI` such as `string:///...` or `mem:///...` is only used to identify the object; the JVM does not automatically open network connections or disk files from those example schemes.

### 2.1. Two-way data flow

- **Input:** the compiler reads `JavaFileObject.Kind.SOURCE` through character content (`getCharContent`, `openReader`, or the corresponding read API).
- **Output:** the file manager provides `JavaFileObject.Kind.CLASS` for the compiler to write bytecode. In memory examples, the output object must implement `openOutputStream`.
- **Diagnostic:** the compiler reports errors, warnings, and source locations via `DiagnosticListener`/`DiagnosticCollector`; `Diagnostic.getSource()` can point directly to the input `JavaFileObject`.
- **Load/execute:** is a **separate** step after compilation. `JavaCompiler` does not automatically run `main` or invoke newly generated static methods.

This very separation makes the API useful for dynamic compilation, while also requiring strict management of class loading and execution permissions.

## 3. Distinguishing interfaces and classes in javax.tools

| API | Role | Key data |
| --- | --- | --- |
| `FileObject` | File abstraction for tools in general, not only Java | `toUri()`, `getName()`, `getCharContent`, streams, timestamp, delete |
| `JavaFileObject` | `FileObject` with Java source/class semantics | `getKind()`, `isNameCompatible()`, `getNestingKind()`, `getAccessLevel()` |
| `SimpleJavaFileObject` | Base class for writing custom `JavaFileObject` with less boilerplate | Constructor `(URI,Kind)`; defaults for name, kind, reader, streams |
| `JavaCompiler` | Programmatic compiler | `getTask(...)`, `getStandardFileManager(...)` |
| `JavaCompiler.CompilationTask` | A compilation task | `call()` returns success/failure |
| `DiagnosticCollector<JavaFileObject>` | Collects diagnostics from the compiler | `getDiagnostics()` and `Diagnostic` location |
| `JavaFileManager` | Resolves classpath/modules and chooses where to store outputs | `getJavaFileForOutput`, `getJavaFileForInput`, `list`... |
| `StandardJavaFileManager` | File manager working with filesystem/JAR/Path | Methods to obtain `JavaFileObject` from `Path`/`File` |
| `ForwardingJavaFileManager` | Wrapper class forwarding to another manager | Selective overrides, e.g., intercepting `CLASS` output |

`JavaFileObject` is an **interface**; `SimpleJavaFileObject` is only one of its implementations. When real files already exist, `StandardJavaFileManager.getJavaFileObjectsFromPaths(Collection<Path>)` is usually more appropriate than writing a custom subclass. When the source is a string in memory, `SimpleJavaFileObject` is a concise choice because it already implements most of the base details.

### 3.1. Separation of roles

Do not use a `JavaFileObject.Kind.SOURCE` to hold `.class` bytecode; do not use `CLASS` and only override `getCharContent` to pretend it is source. Kinds represent the **data type**, while the stream methods provide **how the data moves**.

A compiler is not meant to bypass the `JavaFileManager` contract. When you want to change how class outputs are created, the standard approach is to **customize the file manager**, not try to guess where the compiler will write bytes based on the source URI.

## 4. JavaFileObject.Kind: SOURCE, CLASS, HTML, OTHER

`JavaFileObject.Kind` is an enum indicating the kind of file object:

| Kind | Extension | Meaning and example |
| --- | --- | --- |
| `SOURCE` | `.java` | Compilation unit: `com/acme/Widget.java` |
| `CLASS` | `.class` | Bytecode output/input: `com/acme/Widget.class` |
| `HTML` | `.html` | HTML document that Java tools can process |
| `OTHER` | empty string | Other files, such as metadata or tool-specific resources |

`Kind.SOURCE.extension` is `".java"`; `Kind.CLASS.extension` is `".class"`. Use the enum's extension to reduce hard-coding. `isNameCompatible(simpleName,kind)` checks compatibility between a **simple name** and the kind/path of the file object; it does not validate the syntax of the source text inside.

### 4.1. Constructor and fields

`SimpleJavaFileObject` provides a **protected** constructor:

```java
// Example only, inside a subclass of SimpleJavaFileObject.
super(URI.create("string:///com/acme/Widget.java"), Kind.SOURCE);
```

The superclass stores `protected final URI uri` and `protected final Kind kind`. `toUri()` returns the identifier; `getKind()` returns the kind. `getName()` is used for a human-friendly name and diagnostic locations; the specific value of the name may be the URI path, depending on the implementation and contract, and is **not** the binary class name.

`getNestingKind()` and `getAccessLevel()` in the base implementation return `null` because they are only **hints**. If you already know the exact information, you can override them responsibly; do not infer that `null` means the class is definitely top-level or package-private.

### 4.2. Default methods that often cause surprises

According to the Java SE 21 Javadoc:

- `SimpleJavaFileObject.getCharContent(boolean)` throws `UnsupportedOperationException` by default.
- `openInputStream()` and `openOutputStream()` also throw `UnsupportedOperationException` by default.
- `openReader(boolean)` wraps the result of `getCharContent(...)` in a `Reader`; if you override `getCharContent` to return a `String`, `openReader` will work.
- `openWriter()` wraps `openOutputStream()`; it only works if the output stream is supported.
- `getLastModified()` returns `0L` by default; `delete()` does not delete and returns `false` by default.
- `isNameCompatible(simpleName, kind)` checks by default whether the URI path matches `simpleName + kind.extension` or ends with `"/" + simpleName + kind.extension`, **and the kind must also match**.

Do not catch these exceptions and silently turn them into an empty string: you will hide implementation bugs and cause the compiler to receive empty source.

## 5. Designing StringSource: from binary name to URI

A basic Java 21-compatible implementation:

```java
// Class excerpt; standalone program version in Lab 1.
static final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///" + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

Suppose `binaryName="demo.Hello"`, the URI becomes `string:///demo/Hello.java`. The compiler treats this as Java source belonging to package `demo` with a public top-level class `Hello`. No real file at `/demo/Hello.java` on the OS is needed.

**Three parts must be consistent:**

1. **Identifier name:** `binaryName` is the fully qualified dot-separated name, e.g., `com.acme.Hello`.
2. **URI path:** replace `.` in the package with `/` and append `Kind.SOURCE.extension`, yielding `string:///com/acme/Hello.java`.
3. **Source declaration:** inside `code`, there must be `package com.acme;` and a corresponding public top-level type named `Hello`. The compiler uses the file/compilation unit name to check the public top-level type name when required.

If you specify `"demo.Hello"` while the code is `public class Other`, the compiler may report that `Other` must be declared in a file named `Other.java`. The URI is used for diagnostics and name-compatibility checks; **it does not automatically rename the class in the source code**.

### 5.1. Choosing a safe URI

- Use an absolute URI with an explicit scheme such as `string:///...`, a standard path, and the proper extension; a relative `"Hello.java"` is not a stable pattern for a virtual source.
- Do not concatenate class names from arbitrary input and then call `URI.create`. Validate the binary name/package, reject path traversal, URI reserved characters, and unexpected input; if character encoding is needed, use the multi-argument `URI` constructor.
- Nested classes do not need a separate source file for `Outer$Inner` if they reside in `Outer.java`; an input compilation unit normally carries the **top-level type name**.
- `package-info.java` and `module-info.java` are special compilation units. Do not blindly apply the rule "every source has a binary public class name".
- `getName()` is a human-readable name, `toUri()` is an identifier; do not equate them with `Class.getName()` or use them to establish classloader identity.

### 5.2. Right Kind but missing content

A subclass that only calls `super(uri, Kind.SOURCE)` is **not enough** to represent a String source: the compiler may request to read characters, and by default `getCharContent` throws `UnsupportedOperationException`. This is the core override of the entire lesson.

## 6. Lab 1 — In-RAM source JavaFileObject

Save the file **`SourceObjectBasicsLab.java`**:

```java
import java.io.Reader;
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

public class SourceObjectBasicsLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String source;

        StringSource(String binaryName, String source) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        String source = "package demo; public class Hello {}";
        JavaFileObject file = new StringSource("demo.Hello", source);

        System.out.println("kind=" + file.getKind());
        System.out.println("uri=" + file.toUri());
        System.out.println("name=" + file.getName());
        System.out.println("compatibleHello=" +
                file.isNameCompatible("Hello", JavaFileObject.Kind.SOURCE));
        System.out.println("compatibleWrongName=" +
                file.isNameCompatible("Other", JavaFileObject.Kind.SOURCE));
        System.out.println("compatibleWrongKind=" +
                file.isNameCompatible("Hello", JavaFileObject.Kind.CLASS));
        System.out.println("sameSource=" +
                source.contentEquals(file.getCharContent(false)));
        try (Reader r = file.openReader(false)) {
            System.out.println("firstCharacter=" + (char) r.read());
        }
        System.out.println("timestamp=" + file.getLastModified());

        try {
            file.openInputStream();
            System.out.println("input=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("input=UnsupportedOperationException");
        }

        try {
            file.openOutputStream();
            System.out.println("output=unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("output=UnsupportedOperationException");
        }
    }
}
```

**Commands (JDK 21 or newer JDK supporting `--release 21`):**

```sh
javac --release 21 -Xlint:all SourceObjectBasicsLab.java
java SourceObjectBasicsLab
```

**Verified stdout on the JDK used to run the lab:**

```text
kind=SOURCE
uri=string:///demo/Hello.java
name=/demo/Hello.java
compatibleHello=true
compatibleWrongName=false
compatibleWrongKind=false
sameSource=true
firstCharacter=p
timestamp=0
input=UnsupportedOperationException
output=UnsupportedOperationException
```

### 6.1. Reading the output

- `getKind()` gives `SOURCE` because the constructor received `Kind.SOURCE`.
- `toUri()` preserves the `string` scheme and the path from the binary name. The `getName()` line is the readable name in the tested implementation; the Javadoc does not require every `JavaFileObject` to return **the exact same friendly name format**.
- `isNameCompatible("Hello",SOURCE)` is true because the path ends with `/Hello.java` and the kind matches. `Other` is the wrong name, `CLASS` is the wrong kind.
- `getCharContent(false)` returns the source `String` in a bytecode-independent way, while `openReader(false)` reads the first character `p` of `package`.
- `timestamp=0` is the base class default value, not the time you instantiated `StringSource`.
- `openInputStream`/`openOutputStream` are not overridden, so both calls are rejected. This is not a compiler bug: the class is designed to allow reading source only as characters.

## 7. Pre-existing strings and encoding issues

`getCharContent(boolean ignoreEncodingErrors)` works with a **`CharSequence` already decoded into Java characters**. If the source is already a valid `String`, `getCharContent` itself does not have to run a byte-stream decoder, so the `ignoreEncodingErrors` parameter usually does not affect the content:

```java
// Illustrative getter in StringSource:
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return code;
}
```

However, if you write a `JavaFileObject` that reads from a **`byte[]`**, compressed file, or network stream, encoding becomes a real responsibility. In that case, you must honor the `ignoreEncodingErrors` contract along with the charset and diagnostics/replacement policy. Do not equate "no encoding errors in an existing `String`" with "all byte inputs can ignore encoding".

### 7.1. When to use openReader and openInputStream?

- For `Kind.SOURCE` of `StringSource`, `getCharContent` is the simplest path. `openReader` inherits an implementation that already wraps the `CharSequence`, so no separate override is needed.
- If the backend is a file/byte array, you can override `openInputStream` or `openReader` according to the contract and the behavior of the corresponding compiler/file manager.
- For `Kind.CLASS`, bytecode is **binary** data, so memory output examples override `openOutputStream` for the compiler to write bytes; you must not use a Java `String` to hold binary bytes because it can corrupt the data.
- `StandardJavaFileManager` is responsible for encoding when working with source files on disk; `getStandardFileManager(..., charset)` lets you choose the appropriate charset. Do not needlessly convert an already-valid Java source `String` into bytes and decode it again.

### 7.2. Can the content be mutable?

Keep `code` as `private final String`. A custom `CharSequence` could be mutable; if the source changes between compiler reads, diagnostic line/positions and parse results can become inconsistent. For a memory-based compilation unit, a good practice is to **create an immutable `String` snapshot** per task.

## 8. Connecting JavaFileObject to JavaCompiler.getTask

`ToolProvider.getSystemJavaCompiler()` returns the built-in compiler when the JDK runtime includes the `jdk.compiler` implementation; it may return **`null`** in a stripped-down image that does not contain the compiler. Always check before using the API.

Main API shape:

```java
// Illustrative signature with detailed generic type names omitted:
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits);
```

Each parameter:

| Parameter | Function |
| --- | --- |
| `out` | `Writer` for non-diagnostic output or tool output; `null` uses the default |
| `fileManager` | Resolves classpath/module path and creates outputs; `null` makes the compiler use the standard manager |
| `diagnosticListener` | Receives errors/warnings; use `DiagnosticCollector<JavaFileObject>` |
| `options` | `javac`-like options, e.g., `--release`, `-d`, `-proc:none` |
| `classes` | Class names for annotation processing in supported cases; **not the list of compilation units** |
| `compilationUnits` | `Iterable` containing the source `JavaFileObject` instances to compile |

**Key call:** `Boolean ok = compiler.getTask(...).call()` executes the work. Creating the task object or creating the `JavaFileObject` does not run the compiler yet. A `CompilationTask` is not designed to have `call()` invoked multiple times; to compile another request, create a new task.

### 8.1. Syntax for a single compilation from memory source

```java
// Illustrative snippet: compiler, fileManager, diagnostics, source, and outDir are already available.
boolean ok = compiler.getTask(
        null,
        fileManager,
        diagnostics,
        List.of("--release", "21", "-proc:none", "-d", outDir.toString()),
        null,
        List.of(source)
).call();
```

`"--release", "21"` requests compilation targeting Java 21. `"-proc:none"` disables annotation processing in the labs to reduce side effects and keep output deterministic. `"-d"` specifies the **class files output directory**, without turning the input source URI into a real file.

Some compiler errors may be `Diagnostic.Kind.ERROR`; `call()` returns `false` when compilation fails. Do not assume that `getTask` not throwing an exception means compilation succeeded.

## 9. Lab 2 — source code in String, class output to a temporary directory

Create a standalone file **`CompileToDirectoryLab.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileToDirectoryLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        JavaFileObject unit = new StringSource("demo.Calculator",
                "package demo; public class Calculator { " +
                "public static int add(int a, int b) { return a + b; } }");

        Path out = Files.createTempDirectory("java-compiler-lab-");
        try {
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            boolean ok;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(diagnostics, null, null)) {
                ok = compiler.getTask(null, manager, diagnostics,
                        List.of("--release", "21", "-proc:none", "-d", out.toString()),
                        null, List.of(unit)).call();
            }

            System.out.println("compiled=" + ok);
            System.out.println("errorCount=" +
                    diagnostics.getDiagnostics().stream()
                            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count());
            System.out.println("classFile=" +
                    Files.isRegularFile(out.resolve("demo/Calculator.class")));

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {out.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> calc = Class.forName("demo.Calculator", true, loader);
                Object result = calc.getMethod("add", int.class, int.class)
                        .invoke(null, 4, 9);
                System.out.println("add=" + result);
            }
        } finally {
            try (var walk = Files.walk(out)) {
                for (Path path : walk.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(path);
                }
            }
        }
    }
}
```

Commands:

```sh
javac --release 21 -Xlint:all CompileToDirectoryLab.java
java CompileToDirectoryLab
```

**Stdout:**

```text
compiled=true
errorCount=0
classFile=true
add=13
```

### 9.1. Why isn't this "fully in-memory compilation" yet?

- `unit` is `Kind.SOURCE` with data taken from a `String`; there is no `demo/Calculator.java` on disk.
- The compiler still has **`StandardJavaFileManager`** and the `-d` option. Therefore, the output `demo/Calculator.class` is written to a **real temporary directory**.
- `URLClassLoader` is created separately from `out` and loads the class by the binary name `demo.Calculator`; Reflection calls `add(4,9)` and gets 13.
- `try-with-resources` closes the file manager and `URLClassLoader`. `finally` cleans up the temporary directory, leaving no lab files scattered around.
- Real-world options and classpaths can affect the ability to compile dependencies outside the JDK; this lesson uses self-contained source so the output stays deterministic.

### 9.2. How to distinguish the source path from the class output path

Two forms of identification:

```text
Input  JavaFileObject.toUri() : string:///demo/Calculator.java
Output filesystem class path  : <temporary-directory>/demo/Calculator.class
Runtime binary name           : demo.Calculator
```

The name `demo.Calculator` is a **binary name**, not a URI. `Class.forName("demo.Calculator", ...)` requires the loader to find the exact bytes of the class output. You cannot call `Class.forName("string:///demo/Calculator.java")` because that is a source URI, not a class name.

## 10. Compiling multiple JavaFileObject instances in one task

`compilationUnits` is an `Iterable<? extends JavaFileObject>`, not limited to a single file. For multiple source units that depend on each other, providing them in **one task** allows the compiler to resolve type references through the same compilation context.

Example:

```text
JavaFileObject SOURCE "plug.Service"
  package plug; public interface Service { int eval(int x); }

JavaFileObject SOURCE "plug.ServiceImpl"
  package plug; public class ServiceImpl implements Service { ... }

JavaCompiler.getTask(... List.of(serviceUnit, implUnit)).call()
   |
   +--> plug/Service.class
   +--> plug/ServiceImpl.class
```

Compilation units supplied together can find one another; you do not need to pre-generate `Service.class` yourself. However, if class A was already compiled in **a previous task** into a custom memory store, a subsequent task that wants to use it as a dependency will need a **file manager that can locate the previous output** — which is a different problem from `compilationUnits` in the same task.

### 10.1. Packaging source data properly

When creating sources from multiple `String` values, distinguish:

- **Sources list**: `List<JavaFileObject>` built by you, each item having an appropriate URI and `Kind.SOURCE`.
- **Options list**: `List<String>`, with each flag and value occupying its own position.
- **`classes` list** in `getTask`: usually pass `null` for straightforward compilation; do not put source class names here in place of `compilationUnits`.
- **Classpath/module path**: provide in options or configure the file manager if the source references libraries. Do not misuse the host `ClassLoader` to replace all compiler classpath configuration.

## 11. Lab 3 — two JavaFileObject sources in a single compilation

Create **`MultipleSourcesLab.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class MultipleSourcesLab {
    static final class Source extends SimpleJavaFileObject {
        final String code;

        Source(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        List<JavaFileObject> units = List.of(
                new Source("plug.Service",
                        "package plug; public interface Service { int eval(int x); }"),
                new Source("plug.ServiceImpl",
                        "package plug; public class ServiceImpl implements Service { " +
                        "public int eval(int x) { return x + 5; } }")
        );

        Path dir = Files.createTempDirectory("multiple-units-");
        try {
            boolean success;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(null, null, null)) {
                success = compiler.getTask(null, manager, null,
                        List.of("--release", "21", "-proc:none", "-d", dir.toString()),
                        null, units).call();
            }

            System.out.println("sourceUnits=" + units.size());
            System.out.println("compiled=" + success);
            System.out.println("bothClasses=" +
                    (Files.exists(dir.resolve("plug/Service.class"))
                    && Files.exists(dir.resolve("plug/ServiceImpl.class"))));

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {dir.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
                Class<?> api = Class.forName("plug.Service", true, loader);
                Class<?> impl = Class.forName("plug.ServiceImpl", true, loader);
                Object object = impl.getConstructor().newInstance();
                System.out.println("implementsService=" + api.isInstance(object));
                System.out.println("eval=" +
                        impl.getMethod("eval", int.class).invoke(object, 7));
            }
        } finally {
            try (var paths = Files.walk(dir)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(p);
                }
            }
        }
    }
}
```

```sh
javac --release 21 -Xlint:all MultipleSourcesLab.java
java MultipleSourcesLab
```

**Stdout:**

```text
sourceUnits=2
compiled=true
bothClasses=true
implementsService=true
eval=12
```

### 11.1. Analysis

- `units` is a list of **two** `JavaFileObject` instances both with `SOURCE` and URIs corresponding to each class.
- The compiler generates two class files, even though **no source files were saved to disk**.
- `Class.forName` loads both the interface `plug.Service` and the implementation `plug.ServiceImpl` through the same loader, so `api.isInstance(object)` is true.
- `eval(7)` invokes the actual method of the newly compiled class, returning 12. No hand-written code parses the source into bytecode, because `JavaCompiler` handled parsing/type checking/code generation.
- In a real system, if multiple plugins/class loaders have the same type name, runtime type identity still depends on the defining class loader; `JavaFileObject.toUri()` itself does not control the runtime loader.

## 12. When you want the output bytecode in memory as well

If you only override `getCharContent`, the **input** is in memory, but the **output** is still decided by the file manager. To avoid creating `.class` files, you need a **custom `JavaFileManager`**.

Common design:

```text
                           compiler
                        JavaCompiler.getTask
                           |         |
                           |         +--> getJavaFileForOutput(CLASS_OUTPUT, name, CLASS)
                           |                                      |
 Input StringSource        |                              MemoryManager wrapper
 getCharContent(...)       |                                      |
                           |                              BytecodeOutput CLASS
                           |                              openOutputStream()
                           |                                      |
                           +--------------------------------------+
                                                                  |
                                                        ByteArrayOutputStream
                                                                  |
                                                   Map<binaryName, byte[]>
                                                                  |
                                                  custom ClassLoader#defineClass
```

`ForwardingJavaFileManager<StandardJavaFileManager>` is a utility class: it **delegates** most operations for finding JDK classes/dependencies to the standard manager, while you only override `getJavaFileForOutput(...)` to capture class outputs.

### 12.1. Three specialized components

**1. StringSource (input):** extends `SimpleJavaFileObject` with kind `SOURCE` and provides `getCharContent`.

**2. BytecodeOutput (output):** extends `SimpleJavaFileObject` with kind `CLASS` and overrides `openOutputStream`. The compiler writes **classfile bytes**, without needing to convert them through `String`.

**3. MemoryManager (output routing):** extends `ForwardingJavaFileManager`, overrides `getJavaFileForOutput(location,binaryName,kind,sibling)`. The compiler can generate **multiple class files** from a single source unit, such as nested classes, anonymous classes, and synthetic members. Do not reuse a single `ByteArrayOutputStream` across all outputs if you want to keep distinct class bytes.

### 12.2. Output URI differs from source URI

For example, `binaryName="live.Multiply$Part"` and kind `CLASS`:

```text
Source:        string:///live/Multiply.java
Main output:   mem:///live/Multiply.class
Nested output: mem:///live/Multiply$Part.class
Runtime names: live.Multiply, live.Multiply$Part
```

The JDK compiler calls the file manager with the **binary name of the output**. You are responsible for storing each output under that name in a map. The `mem:` URI is an identifier; `ClassLoader#defineClass` using the bytes does not require a URL protocol handler for `mem:`.

### 12.3. Limitations of the demo memory manager

A manager that only overrides `getJavaFileForOutput` is sufficient for a simple compile task that **already has all compilation units** and only needs to capture outputs. If a subsequent compile task needs to read generated classes from a previous task, you may also need to override `getJavaFileForInput`, `list`, `inferBinaryName`, and appropriate location operations so the compiler can see the bytes existing in memory. Do not assume that "outputs are in a map" means the compiler will automatically look them up when resolving dependencies.

This lesson also does not implement support for annotation-generated sources, module-specific output locations, or generated resources. Those rules require extending the file manager contract according to the use case.

## 13. Lab 4 — compiling source and CLASS output completely in RAM

Create a standalone file **`CompileInMemoryLab.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileInMemoryLab {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static final class BytecodeOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        BytecodeOutput(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] toByteArray() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, BytecodeOutput> classes = new HashMap<>();

        MemoryManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String binaryName,
                JavaFileObject.Kind kind, FileObject sibling) {
            BytecodeOutput output = new BytecodeOutput(binaryName, kind);
            classes.put(binaryName, output);
            return output;
        }
    }

    static final class ByteLoader extends ClassLoader {
        private final Map<String, byte[]> code;

        ByteLoader(Map<String, byte[]> code) {
            super(ClassLoader.getPlatformClassLoader());
            this.code = Map.copyOf(code);
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = code.get(name);
            if (bytes == null) throw new ClassNotFoundException(name);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        String source = """
                package live;
                public class Multiply {
                    public static int run(int x, int y) { return Part.product(x, y); }
                    private static class Part {
                        static int product(int a, int b) { return a * b; }
                    }
                }
                """;
        Map<String, byte[]> bytes = new HashMap<>();
        boolean ok;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(null, null, null);
                MemoryManager manager = new MemoryManager(standard)) {
            ok = compiler.getTask(null, manager, null,
                    List.of("--release", "21", "-proc:none"), null,
                    List.of(new StringSource("live.Multiply", source))).call();

            manager.classes.forEach((name, file) ->
                    bytes.put(name, file.toByteArray()));
        }

        System.out.println("compiled=" + ok);
        System.out.println("generatedClasses=" + bytes.size());
        System.out.println("allHaveBytes=" +
                bytes.values().stream().allMatch(b -> b.length > 4));

        ByteLoader loader = new ByteLoader(bytes);
        Class<?> main = Class.forName("live.Multiply", true, loader);
        Object result = main.getMethod("run", int.class, int.class)
                .invoke(null, 3, 7);
        System.out.println("product=" + result);
        System.out.println("customLoader=" + (main.getClassLoader() == loader));
    }
}
```

```sh
javac --release 21 -Xlint:all CompileInMemoryLab.java
java CompileInMemoryLab
```

**Stdout:**

```text
compiled=true
generatedClasses=2
allHaveBytes=true
product=21
customLoader=true
```

### 13.1. Why does one source produce two class files?

The source `live.Multiply` contains a nested class `Part`. The compiler generates **`live.Multiply.class`** and **`live.Multiply$Part.class`**; the output count is 2. Because the file manager keeps a map by binary name, both are stored separately. If you only kept `Multiply.class`, the program could fail with `NoClassDefFoundError` when the `run` method needs to use the nested `Part`.

### 13.2. Compiler vs. ClassLoader

- `compiler.getTask(...).call()` produces bytes and passes them through the file manager; it does not load the class into a runtime `Class<?>`.
- `ByteLoader.findClass` looks up bytes by binary name and calls `defineClass`. That is the step that creates runtime class identity for the new code.
- `ByteLoader` sets its parent to the platform loader so the example is isolated from unrelated app classes; the types in the source only use the JDK. For real plugins with shared interfaces/SDKs, you must choose the parent and delegation policy intentionally.
- `customLoader=true` confirms the main class was defined by the loader we created, not by the application class loader that compiled `CompileInMemoryLab`.
- Output `allHaveBytes=true` is only a sanity check; if you want to validate a class file, you can check the magic bytes `0xCAFEBABE` or test loading it with a `ClassLoader`, though that **does not** prove the source code is safe to run.

### 13.3. What not to copy verbatim into production

In the example, `MemoryManager` uses a simple `HashMap` for a single sequential task and returns the output bytes once the task completes. In an application with multiple compilation tasks/threads, manage per-task ownership, class loader lifecycles, memory pressure, and closing streams. The `JavaFileManager` contract does not require an instance to be completely thread-safe, though it must support concurrent operations on *distinct file objects* that it supplies.

In addition, when compiling **code supplied by untrusted users**, you must isolate it at an appropriate **process/container/OS boundary**, enforce quotas/timeouts/resource limits, and set an annotation processor policy. A custom classloader is not a complete security sandbox.

## 14. DiagnosticCollector keeps errors attached to the source object

`JavaCompiler.getTask` can accept a `DiagnosticCollector<JavaFileObject>` as a listener. When the source has errors, the compiler emits `Diagnostic` objects containing:

| Property | Meaning |
| --- | --- |
| `getKind()` | `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`... |
| `getSource()` | `JavaFileObject` attached to the diagnostic, may be `null` if not attached to a specific source |
| `getLineNumber()` | Line in source, or `Diagnostic.NOPOS` |
| `getColumnNumber()` | Column in source, or `NOPOS` |
| `getStartPosition()/getEndPosition()` | Character positions if available |
| `getCode()` | Implementation-supplied diagnostic code |
| `getMessage(locale)` | Human-readable description, which may vary by locale/JDK |

The source URI is very useful in an editor or code playground website: users can tell which "virtual file" an error belongs to, even with no file on disk. Remember, however, that `URI` is only an identifier, **not a path that automatically grants permission to read a real file**.

### 14.1. Do not use message text for assertions

The wording of compiler errors may be localized or change across JDK versions. When writing stable tests, check `kind`, `source`, `line`, or `Diagnostic.getCode()` when appropriate, while also noting that diagnostic codes are not a universal language contract across all compilers. In the next example, the program prints **kind, URI, line** instead of printing the entire message.

## 15. Lab 5 — syntax-invalid source and diagnostics with locations

Create the file **`DiagnosticsLab.java`**:

```java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticsLab {
    static final class Source extends SimpleJavaFileObject {
        final String code;

        Source(String name, String code) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }
        JavaFileObject bad = new Source("demo.Broken",
                "package demo;\npublic class Broken {\n    int x = ;\n}\n");
        DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
        Path out = Files.createTempDirectory("diagnostics-");
        try {
            boolean success;
            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(collector, null, null)) {
                success = compiler.getTask(null, manager, collector,
                        List.of("--release", "21", "-proc:none", "-d", out.toString()),
                        null, List.of(bad)).call();
            }

            Diagnostic<? extends JavaFileObject> firstError =
                    collector.getDiagnostics().stream()
                            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                            .findFirst().orElseThrow();

            System.out.println("compiled=" + success);
            System.out.println("kind=" + firstError.getKind());
            System.out.println("source=" + firstError.getSource().toUri());
            System.out.println("line=" + firstError.getLineNumber());
            System.out.println("errorsPresent=" +
                    collector.getDiagnostics().stream()
                            .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR));
        } finally {
            try (var paths = Files.walk(out)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.delete(p);
                }
            }
        }
    }
}
```

```sh
javac --release 21 -Xlint:all DiagnosticsLab.java
java DiagnosticsLab
```

**Verified stdout:**

```text
compiled=false
kind=ERROR
source=string:///demo/Broken.java
line=3
errorsPresent=true
```

### 15.1. Explaining the error data

- `DiagnosticsLab.java` **compiles successfully**; the error is inside the `String` simulating the `demo.Broken` source, which is only compiled by the second compiler **at runtime**.
- `int x = ;` is on **line 3** of the virtual source, which is invalid Java syntax, so the inner compilation returns `false`.
- `Diagnostic.getSource().toUri()` returns `string:///demo/Broken.java`, matching the original source URI. No real file is needed to identify the source and line number.
- Do not report `compiled=false` as meaning `DiagnosticsLab` itself failed to run; it ran and captured the error of the secondary compilation as designed.
- If a diagnostic is not attached to a source, `getSource()` may be null; production code must check before calling `toUri()`. If no position is available, `Diagnostic.NOPOS` is not a crash error.

## 16. Comparing three strategies for storing source and class output

| Need | Input JavaFileObject | FileManager | Class output | How to run |
| --- | --- | --- | --- | --- |
| Typical CLI compiler | `.java` on filesystem | Standard manager | `.class` on disk | `java -cp...` |
| Generate Java source at runtime, save output to file | `SimpleJavaFileObject(SOURCE)` from String | Standard manager + `-d` | `.class` on disk | `URLClassLoader` |
| Fully in-memory compiler | `SimpleJavaFileObject(SOURCE)` from String | Custom forwarding manager | `ByteArrayOutputStream` by binaryName | Custom `ClassLoader#defineClass` |
| IDE/editor with virtual sources | A set of `JavaFileObject`s for multiple buffers | Custom/forwarding manager | Application-dependent | May only compile/check, not execute |
| Annotation processing/code generator | `SOURCE` and generated `SOURCE`/`CLASS` objects | FileManager supporting locations and outputs | Multiple class/resource outputs | Pipeline-dependent |

Two criteria must be decided independently: **where does the source live?** and **where will the compiler write the output?** A program calling `new StringSource(...)` cannot automatically claim "no disk usage" without checking the file manager.

### 16.1. StandardJavaFileManager and paths

For real source files:

```java
// Illustration: compiler and java.nio.file.Path sourcePath already exist.
try (StandardJavaFileManager standard =
        compiler.getStandardFileManager(null, null, null)) {
    Iterable<? extends JavaFileObject> units =
            standard.getJavaFileObjectsFromPaths(java.util.List.of(sourcePath));
    boolean ok = compiler.getTask(
            null, standard, null, java.util.List.of("-proc:none"),
            null, units).call();
}
```

This is the approach when the source is already on disk. You should not read the entire file into a `String` and create a virtual source just to duplicate what the standard manager already does, unless you genuinely need to modify the content in memory before compiling.

### 16.2. One source unit can generate multiple class files

Java source containing nested/local/anonymous classes can generate **multiple `Kind.CLASS` outputs**. The file manager must handle each `binaryName`, not just the output file whose name matches the top-level class. Lab 4 demonstrates one source producing two `.class` files.

If a processor generates additional source units, `Kind.SOURCE` outputs can be produced during compilation, and the file manager must support the corresponding mechanism. Do not treat a single `Map<String,byte[]>` holding only classes as the sole store for all types of generated files.

## 17. Choosing the right contracts for name, URI, and class identity

### 17.1. Source file name, binary name, and runtime name are three layers

```text
Java source declaration:
    package app.rules;
    public class RuleEngine { ... }

source JavaFileObject.toUri():
    string:///app/rules/RuleEngine.java

class output:
    mem:///app/rules/RuleEngine.class

runtime binary name:
    app.rules.RuleEngine

actual runtime Class<?>:
    (binary name, defining ClassLoader, runtime module context)
```

A URI does not contain the defining loader. A Java class can be defined by different loaders even if the output binary name is the same. An in-memory compiler can produce valid bytes, but you still must ensure valid classloader/linkage/shared API identity when passing objects to the rest of the system.

### 17.2. Do not use getName to look up a runtime class

`file.getName()` is not an API that returns `"app.rules.RuleEngine"`, nor does it replace `Class.getName()`. Similarly, `FileObject.toUri()` does not replace `ClassLoader.loadClass("app.rules.RuleEngine")`. Store the **binaryName** separately in metadata if needed after compilation.

### 17.3. When the source is module-info or package-info

`module-info.java` declares a module, not a public class `module-info`; `package-info.java` holds package metadata. Choosing the URI and compilation unit `Kind` must respect these special names, module-specific compiler options, and corresponding file manager locations. Do not take the name `module-info` and pretend it is an ordinary binary class name.

### 17.4. If compiling multiple times, manage dependencies in the right place

A `Map<String,byte[]>` containing class outputs from a previous run can be used by a **custom runtime `ClassLoader`**, but the compiler in the next run will not automatically see that map. For the compiler to resolve a previously compiled type, you can:

- Supply the source unit again in the same task.
- Save the class files to a directory/JAR and pass it on the compiler classpath/module path.
- Extend the custom `JavaFileManager` to report the class file via `getJavaFileForInput/list/inferBinaryName`, along with location and URI rules.

Choose an approach with an explicit contract, rather than relying on "the class was already loaded by a custom `ClassLoader`, so `JavaCompiler` will surely find it too".

## 18. Reliability, JDK versions, and safety

### 18.1. Only use APIs available in Java 21

Starting in Java 23, some JDK versions have a new convenience factory on `SimpleJavaFileObject` for creating a source from a `String`. **Do not use APIs added after Java 21** in code supporting Java 21. Here we use the long-supported `protected` constructor `SimpleJavaFileObject(URI,Kind)` and override `getCharContent`. Verify the API version instead of copying a snippet from JDK 25/26 docs and attaching `--release 21` without compiling.

`javac --release 21` checks the source, available APIs, and target bytecode for Java 21; running the program in a JDK that supports the class file version is a separate step. In this lab, the programs can run on JDK 21+ with a full built-in compiler.

### 18.2. ToolProvider can return null

A `jlink` JRE/JDK runtime image may not include the `jdk.compiler` module. `ToolProvider.getSystemJavaCompiler()==null` means there is no system compiler provider; the solution is to run on a full JDK or provide a valid compiler via the tool SPI, rather than dereferencing null and blaming the source object.

### 18.3. Do not compile and execute untrusted code in the same process

**Important:** `javax.tools.JavaCompiler` is a compilation tool, **not a sandbox**. Even when the source is held in a `String` and the output is a byte array:

- Annotation processors can execute code during compilation if enabled.
- Compiled code, when loaded/initialized/invoked, has the permissions of the process/class loader/module context, and can perform I/O, spawn threads, open network connections, or consume resources if the runtime allows it.
- `ClassLoader#defineClass` **does not** by itself limit CPU, RAM, filesystem, or network access.
- Oversized inputs, many compilation units, or complex generated code can consume significant memory/CPU.

The labs use `-proc:none` to avoid running annotation processors. For untrusted source code, you need **process/container/OS-level isolation**, permission/resource/timeout limits, a safe output directory, and no automatic invocation of code after compilation. Without isolation, only compile trusted/controlled sources.

### 18.4. Lifecycle of compiler and class loader

Use `try-with-resources` for `StandardJavaFileManager`, `ForwardingJavaFileManager`, `URLClassLoader`, and streams. The Compiler/FileManager may cache JAR/file handles; do not hold references indefinitely. Each task can produce multiple class output objects, so set policies limiting the number of classes/bytes/versions. A classloader is not guaranteed to unload if objects, static fields, threads, or caches still hold references to the classes/loader.

## 19. Common errors and how to investigate them

| Symptom | Common cause | Check/fix |
| --- | --- | --- |
| `UnsupportedOperationException` when the compiler reads source | Subclass of `SimpleJavaFileObject` does not override `getCharContent`, or provides the wrong read API | Return a real `CharSequence` for `Kind.SOURCE`. |
| `IllegalArgumentException` when creating `URI` | URI/path contains reserved characters/invalid scheme | Validate binary name, create an absolute URI, percent-encode by component. |
| `isNameCompatible=false` | URI path does not end with `Name.java` or `Kind` is wrong | Print `toUri()`, `getKind()`; use `Kind.SOURCE.extension`. |
| "public class X should be in X.java" | Source URI/file name does not match public top-level type name | Align `binaryName`, source package, and top-level class. |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime lacks the compiler module/provider | Run on a JDK with `jdk.compiler`, check the module image. |
| `task.call() == false` | Source syntax, types, classpath/options error | Collect `DiagnosticCollector` and display source URI/line. |
| No `.class` in RAM | Only created `StringSource`, still using standard file manager | Override `getJavaFileForOutput`, provide `Kind.CLASS` output. |
| `openOutputStream` is unsupported | `BytecodeOutput` does not override the stream | Use `ByteArrayOutputStream` and return the stream to the compiler. |
| Only one class when source contains nested types | File manager overwrites the same stream/output key | Store outputs separately by binary name + kind/location when needed. |
| `ClassNotFoundException` after compile | Loader cannot see the output binary name | Check the map/`-d` path, loader parent, output location. |
| `NoClassDefFoundError` when invoking | Missing dependency/nested class output or classloader identity conflict | Store all generated classes and supply appropriate shared deps. |
| `ClassCastException` between plugin types | Same class name but two different defining loaders | Share interface contracts through a common loader. |
| Virtual source compilation error without knowing location | Omitted diagnostic listener or wrong source URI | Use `DiagnosticCollector`, `getSource/toUri`, line/column. |
| Second compiler task cannot find output of previous task | Memory output map is not integrated into classpath/file manager | Override input/list methods or materialize classes in a controlled way. |
| Running code consumes too much CPU/RAM | Dynamic source assumed safe because it is "in memory" | Process isolation, quotas, timeouts, input validation. |
| Resources/JARs locked | File manager, output streams, or `URLClassLoader` not closed | Use `try-with-resources` and clean up resources after the task finishes. |

### 19.1. Layered debugging order

```text
[1] Is the source code String complete with the right package/public class name?
       |
[2] Is JavaFileObject.getKind() == SOURCE?
       |
[3] Is toUri() absolute and does its path end with .java? Is isNameCompatible true?
       |
[4] Does getCharContent() return the content?
       |
[5] Is compiler != null? Are options/classpath/module path correct?
       |
[6] Did getTask(..., compilationUnits).call() succeed?
       |
[7] Does DiagnosticCollector have any ERROR, and which source URI and line?
       |
[8] Does FileManager output CLASS to disk or memory? Does it include all nested classes?
       |
[9] Does ClassLoader load the right binaryName and dependencies?
       |
[10] Is the runtime invocation using the right type/permissions and safe?
```

Do not skip step 6 and blame the `ClassLoader`, and do not take a class loading exception to immediately assume the source compiler failed. Each phase has its own contract.

## 20. Practice exercises and guided answers

**Exercise 1 — Distinguishing Kind.** Create two `SimpleJavaFileObject` instances with the same binary name `demo.Hello` but `Kind.SOURCE` and `Kind.CLASS`. Predict the URI extensions if the constructor appends `kind.extension` and the results of `isNameCompatible("Hello", SOURCE/CLASS)`. Explain why `CLASS` bytes should not be returned via `getCharContent`.

**Exercise 2 — Source name mismatch.** Change the `StringSource` name from `demo.Hello` to `demo.Other` while still declaring `public class Hello`. Compile and inspect `DiagnosticCollector`. Fix it by aligning the binary name with the public top-level type; do not alter `getKind` to hide the error.

**Exercise 3 — Reading from Reader.** Use `SourceObjectBasicsLab` to count source characters via `openReader(false)`. Compare `length` with `getCharContent(false).length()`, using `try-with-resources`.

**Exercise 4 — Missing system compiler.** Describe how to handle `ToolProvider.getSystemJavaCompiler()==null`; do not propose an unconditional `Runtime.exec("javac")` fallback on arbitrary hosts because path, version, permissions, and security must be controlled.

**Exercise 5 — Compiler options.** In Lab 2, remove `-d` and replace it by configuring `StandardLocation.CLASS_OUTPUT` on the standard manager. Check whether the output location is correct. Keep `--release 21` and `-proc:none` for predictable output.

**Exercise 6 — Multiple source units.** In `MultipleSourcesLab`, add `plug.AnotherImpl` implementing `Service`; pass three `JavaFileObject`s, expecting three `.class` files. Verify before loading that all output class paths exist.

**Exercise 7 — One source, multiple class outputs.** In Lab 4, add a nested `static class Helper`. Predict `generatedClasses` increases, and the map must contain `live.Multiply$Helper` and `live.Multiply$Part`. Update QA criteria instead of hard-coding "one `SOURCE` equals one `CLASS`".

**Exercise 8 — Bytecode storage.** In `CompileInMemoryLab`, verify each byte array starts with at least the 4 bytes `CA FE BA BE`. Do not interpret having magic bytes as sufficient proof that the class is valid/safe.

**Exercise 9 — Diagnostics and line mapping.** Change the broken source to span multiple lines, then print `getLineNumber()`/`getColumnNumber()`. If a diagnostic has no source or `NOPOS`, how should a helper display it?

**Exercise 10 — Recompile dependencies.** Run a task compiling `plug.Service` in memory and then another task compiling `plug.ServiceImpl` referencing only the interface whose bytes already exist. Explain why merely keeping bytecode in a map is not enough, and choose between providing the source in the same task, materializing class output, or implementing `JavaFileManager.getJavaFileForInput`/`list`.

**Exercise 11 — Unicode source.** Create a `StringSource` containing a Vietnamese string literal or non-ASCII characters and call `getCharContent(false)`. Explain why when the source is already a Java `String`, byte decoding has already occurred beforehand; when reading external bytes in, the charset policy matters again.

**Exercise 12 — Security review.** A website accepts Java source from strangers, compiles it, and loads it via a custom classloader inside the web server. Identify at least three risks and an appropriate isolation architecture. Explain how `-proc:none` helps restrict processor execution but does not turn the output bytecode into safe code.

### 20.1. Completion checklist

- [ ] Distinguish `SOURCE`, `CLASS`, and the input/output data flow.
- [ ] Write a proper `SimpleJavaFileObject` subclass with `Kind.SOURCE` and `getCharContent`.
- [ ] Understand that the URI `string:///.../Name.java` is an identifier, not a real file.
- [ ] Align `binaryName`, source package/public class, and output class name.
- [ ] Pass multiple `JavaFileObject`s via `compilationUnits`.
- [ ] Use `JavaCompiler.getTask`, `StandardJavaFileManager`, `DiagnosticCollector`, and close resources.
- [ ] Write a `Kind.CLASS` output object with `openOutputStream` and `ForwardingJavaFileManager` to keep bytecode in memory.
- [ ] Load classes by binary name, ensuring nested outputs/dependencies are present.
- [ ] Separate errors across source syntax, name, compiler availability, file manager, and class loader.
- [ ] Run and understand the stdout of all five labs; do not treat the compiler API as a security sandbox.

## 21. Official Java 21 Documentation

- [Java SE 21 — JavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind`, `isNameCompatible`, nesting/access hints, and source/class file contracts.
- [Java SE 21 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): protected constructor, `getCharContent`, `openReader`, stream defaults, `toUri`.
- [Java SE 21 — FileObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/FileObject.html): URI, name, character/byte access, timestamps, delete.
- [Java SE 21 — JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, standard manager, compiler services, and SPI.
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler()`.
- [Java SE 21 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): mapping between `Path/File` and `JavaFileObject`.
- [Java SE 21 — JavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileManager.html): file locations, binary names, and output factories.
- [Java SE 21 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): wrapper with selective overrides.
- [Java SE 21 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) and [Diagnostic](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html): diagnostics with source, line, and kind.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, parent delegation, and runtime class identity.
- [JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release`, `-d`, `-proc:none`, and compiler options.

**Conclusion:** `JavaFileObject` is the interface of a **source/class file in the compiler toolchain**, not necessarily a file on disk. `SimpleJavaFileObject` lets you implement a virtual source with **URI + Kind.SOURCE + getCharContent()**; `JavaCompiler` compiles it alongside other sources; `JavaFileManager` chooses where to write `Kind.CLASS`; and **ClassLoader** is what decides how to load the compiled code. Keeping these four responsibilities separate lets you build a clear runtime compiler with useful diagnostics and without confusing source data with execution privileges.
