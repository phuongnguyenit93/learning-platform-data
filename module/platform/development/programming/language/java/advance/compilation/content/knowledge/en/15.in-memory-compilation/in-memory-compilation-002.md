# Representing a String Source Using SimpleJavaFileObject

In Java, you can compile a piece of source code **residing in a `String`** without creating a `.java` file on disk. The `javax.tools.JavaCompiler` API accepts a collection of `JavaFileObject` instances rather than only file path names. To pass a `String` into the compiler's input, the common approach is to subclass **`SimpleJavaFileObject`**, create a URI representing the source name, and override **`getCharContent(boolean)`** to return the Java code content.

This approach is very useful for code editors, online exercises, code generators, compiler tests, template systems, and source analysis tools. However, an important boundary must be understood: **source in memory does not mean the output class file is also in memory**. If you still use the default `StandardJavaFileManager` and configure `-d out`, the class file is written to disk. To keep bytecode in RAM as well, you must add a `JavaFileManager` that handles output.

This lesson focuses on **representing a `.java` source unit from a string** and passing it into `JavaCompiler`, while also providing an advanced example for fully in-memory compilation. The standalone programs run with **Java 17+** and have been verified using JDK 24 with the `--release 17` option.

## 1. APIs involved in the process

| Component | Role | Notes |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Retrieves the Java compiler provided by the current JDK | Returns `null` when no suitable compiler is present in the runtime |
| `JavaCompiler` | Creates compilation tasks | An interface of the Java Compiler API, not the `javac` shell command |
| `JavaFileObject` | Abstracts source, class, or file types for the compiler | Has `Kind.SOURCE`, `Kind.CLASS`, and other kinds |
| `SimpleJavaFileObject` | Base class helping define a custom JavaFileObject | Must override read/write methods according to purpose |
| `URI` | Logical identifier for a source unit | Does not require the URI to point to a real file if the object can supply content |
| `getCharContent(boolean)` | Provides source code characters | Important read path for sources from a String |
| `StandardJavaFileManager` | Standard file manager of the compiler | Suitable for using classpath, module path, and disk output |
| `DiagnosticCollector` | Collects structured errors/warnings/notes | Used to inspect source, line, column, severity |
| `JavaCompiler.CompilationTask` | Represents a single compilation pass | `call()` returns success/failure result |

A source code string is **not** a direct parameter of `compiler.getTask(...)`. You must wrap the content in one or more `JavaFileObject` instances so the compiler knows: “what is the name of this Java source unit, what kind is it, and where to read the characters from”.

### Overall Pipeline

```text
String containing Java code
       |
       v
StringSource extends SimpleJavaFileObject
   - URI: string:///demo/Hello.java
   - Kind.SOURCE
   - getCharContent() -> String
       |
       v
JavaCompiler.getTask(...)
       |
       +---- DiagnosticCollector: errors / warnings / positions
       |
       +---- StandardJavaFileManager: classpath, output
       |
       v
CompilationTask.call()
       |
       +---- false: compilation error
       |
       +---- true: compilation succeeded
                 |
                 +---- (default or -d) .class on disk
                 |
                 +---- (custom FileManager) bytecode in RAM
```

The compiler can read multiple source units in the same task: `List.of(sourceA, sourceB)`. In this lesson, each example starts with one logical source file to clearly see the relationship between class name and URI, before expanding.

## 2. Minimal structure of StringSource

Core template:

```java
import java.net.URI;
import java.util.Objects;
import javax.tools.SimpleJavaFileObject;

public final class StringSource extends SimpleJavaFileObject {
    private final String content;

    public StringSource(String binaryName, String content) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') +
                Kind.SOURCE.extension), Kind.SOURCE);
        this.content = Objects.requireNonNull(content);
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return content;
    }
}
```

The class above **does not contain `main`**; it is a component to be used with `JavaCompiler`. It can be saved as `StringSource.java` and compiled alongside the using program, or defined as a nested class in the complete example later.

Explanation of each part:

1. `extends SimpleJavaFileObject`: you do not implement every method of `JavaFileObject` yourself; the base class already provides the foundation.
2. `URI.create("string:///...")`: creates a **logical identifier**, not a request to read from the network or access the filesystem.
3. `binaryName.replace('.', '/')`: converts `demo.Hello` into the logical path `demo/Hello`.
4. `Kind.SOURCE.extension`: equivalent to the `.java` string, avoiding hardcoding the file extension.
5. `Kind.SOURCE`: indicates the proper input object kind; if `Kind.CLASS` is mistakenly used, the compiler will not treat this as normal Java source code.
6. `getCharContent(...)`: provides the `String` content to the compiler. There is no call to `Files.readString` or opening a `.java` file.
7. `Objects.requireNonNull(content)`: clarifies that the source content must have a value; receiving an empty string is a different case that the compiler will diagnose based on context.

The `ignoreEncodingErrors` parameter exists in the interface because some file managers reading from byte streams need to handle decoding errors. In this example, the source is already Java characters in a `String`, so **no byte decoding is needed**, and leaving the parameter unused is intentional.

### Why is the URI string:///demo/Hello.java?

Suppose the binary name of the class is `demo.Hello`:

```text
binaryName                       demo.Hello
binaryName.replace('.', '/')     demo/Hello
Kind.SOURCE.extension            .java
URI                              string:///demo/Hello.java
```

The `///` prefix is commonly used so the URI has an absolute path. The `string` scheme is a **custom convention of the example**, not an HTTP protocol, does not make the compiler automatically fetch data from a website, and does not create a file at `/demo/Hello.java`.

The important point is that the URI gives the compiler a **valid, stable, distinguishable** identifier among sources. With code snippets from users, you should not concatenate untrusted names directly into the URI without validating the class name and characters needing escaping. This example assumes `binaryName` is already a valid Java binary name.

## 3. Source code and URI must describe the same compilation unit

Suppose the source contains:

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from String");
    }
}
```

The binary name of the public class is `demo.Hello`. When creating `StringSource`, we use:

```java
new StringSource("demo.Hello", text)
```

Normally the `public` class name must match the source unit name `Hello.java`; package `demo` resides in the Java code snippet and corresponds to the logical path `demo/Hello.java`.

Common mistakes:

- Using `new StringSource("Hello", text)` while the source declares `package demo;`; the URI naming does not reflect the package, which can cause errors in tools that need to infer the binary name.
- Using URI `string:///demo/Other.java` for a file containing `public class Hello`; the compiler may report that the public class name does not match.
- Putting a string containing **multiple public top-level classes** into a single source unit; Java file naming rules still need to be respected.
- Creating two `JavaFileObject` instances with the same URI/name for two different sources in one task; the compiler may encounter compilation unit conflicts.

One source file can contain additional **non-public** top-level classes per Java rules. When a problem requires multiple public classes belonging to multiple files, create **multiple StringSource instances** with the corresponding binary names.

## 4. Runnable example: String → compiler → class file → run class

Create the file **`StringSourceDemo.java`** with the complete content below. This example chooses *in-memory input* but **class file output in a temporary directory** so the pipeline is easy to observe.

```java
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class StringSourceDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String text) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.source = Objects.requireNonNull(text);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run this example with a JDK.");
        }

        String text = """
                package demo;
                public class Hello {
                    public static void main(String[] args) {
                        System.out.println("Hello from String");
                    }
                }
                """;

        Path classes = Files.createTempDirectory("string-classes-");
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Boolean ok = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-d", classes.toString()),
                    null,
                    List.of(new Source("demo.Hello", text))
            ).call();

            System.out.println("compiled=" + Boolean.TRUE.equals(ok));

            if (!Boolean.TRUE.equals(ok)) {
                for (Diagnostic<? extends JavaFileObject> item
                        : diagnostics.getDiagnostics()) {
                    System.err.println(item.getKind() + ": " +
                            item.getMessage(Locale.ROOT));
                }
                return;
            }
        }

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {classes.toUri().toURL()})) {
            Class<?> type = Class.forName("demo.Hello", true, loader);
            type.getMethod("main", String[].class)
                    .invoke(null, (Object) new String[0]);
        }
    }
}
```

Use a terminal in the directory containing `StringSourceDemo.java`, with JDK 17+:

```bash
javac --release 17 StringSourceDemo.java
java StringSourceDemo
```

Stdout **verified using JDK 24 with `--release 17`**:

```text
compiled=true
Hello from String
```

Actual sequence:

1. `javac --release 17 StringSourceDemo.java` compiles the **host program** that provides the Java Compiler API, not `demo.Hello`. This is the preparation step to run the example.
2. `java StringSourceDemo` runs the host.
3. The host gets the compiler from `ToolProvider`; creates a `Source` object with URI `string:///demo/Hello.java` and a String containing the code of `demo.Hello`.
4. `compiler.getTask(...).call()` compiles the source returned by `getCharContent`. `--release 17` restricts the language/API/class target version of this compilation pass.
5. `-d classes.toString()` places `demo/Hello.class` into the temporary directory.
6. `URLClassLoader` loads the generated class from that directory; reflection invokes `main` of `demo.Hello`.
7. Class `demo.Hello` prints `Hello from String`.

**Distinguish the two compiler passes:** the shell compiler creates `StringSourceDemo.class`; then the JavaCompiler API inside the host program creates `demo/Hello.class`. Simply copying the `demo.Hello` source snippet without using the API does not illustrate the actual problem.

### Why use (Object) new String[0]?

The call:

```java
type.getMethod("main", String[].class)
    .invoke(null, (Object) new String[0]);
```

`Method.invoke` takes `Object... args`. Casting `(Object)` ensures the `String[]` array is passed as **a single argument** to `main(String[] args)`, instead of risking confusion with reflection's varargs syntax. Because `main` is static, the receiver passed to `invoke` is `null`.

In production systems, loading/running dynamically compiled code carries more risk than the compilation part: **do not run untrusted Java code inside the same JVM and expect the class loader to guarantee a safe sandbox**. `ClassLoader` is a class-loading mechanism, not a strong enough security boundary for code from untrusted users.

### Are temporary files deleted?

The example uses `Files.createTempDirectory(...)` and does not delete the directory in the demo to stay focused on the workflow. In real deployments, you need a lifecycle management policy and safe deletion of temporary class files once the associated classloaders are no longer in use, subject to operating system and runtime capabilities. Do not delete a directory without being certain it is a directory created by the application itself.

## 5. Generating diagnostics with file, line, and column even though the source is a String

An important benefit of `JavaFileObject` is that the compiler can generate errors/warnings **attached to a logical URI** even when the source does not exist on disk. Use `DiagnosticCollector<JavaFileObject>` to collect structured diagnostics.

Create the file **`StringSourceErrorDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class StringSourceErrorDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String binaryName, String content) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') +
                    Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler javac = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        String broken = """
                package demo;
                public class Broken {
                    int number = "not an int";
                }
                """;

        try (StandardJavaFileManager files =
                javac.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            boolean passed = javac.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("demo.Broken", broken))
            ).call();

            System.out.println("compiled=" + passed);
        }

        for (Diagnostic<? extends JavaFileObject> issue
                : diagnostics.getDiagnostics()) {
            if (issue.getKind() == Diagnostic.Kind.ERROR) {
                System.out.println("kind=" + issue.getKind());
                System.out.println("source=" + issue.getSource().toUri());
                System.out.println("line=" + issue.getLineNumber());
                System.out.println("column=" + issue.getColumnNumber());
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 StringSourceErrorDemo.java
java StringSourceErrorDemo
```

Stdout of the example **verified on JDK 24**:

```text
compiled=false
kind=ERROR
source=string:///demo/Broken.java
line=3
column=18
```

The output shows:

- There is no real `demo/Broken.java` file; the URI `string:///demo/Broken.java` was supplied by the `Source` constructor itself.
- The compiler found the error of assigning a `String` literal to a field of type `int`.
- `Diagnostic.Kind.ERROR` identifies the error level from the Java compiler itself; the programmer does not need to parse stderr strings.
- `getSource().toUri()` links the diagnostic with the **logical source unit**.
- `getLineNumber()` and `getColumnNumber()` return the position in the source for that specific error. For diagnostics not attached to a position, the API may return `Diagnostic.NOPOS` (value `-1`).
- Because the example intentionally contains a source error, `CompilationTask.call()` returns `false`, but the **host program** still completes normally, so the `java StringSourceErrorDemo` command may have exit code 0. Do not confuse the host's exit code with the dynamic compilation result printed in `compiled=false`.

**Position 3:18 belongs to the exact given source snippet and tested compiler**, not a guarantee that every error/every JDK always reports column 18. Other warnings may have an unspecified source or position.

### Need to display compiler messages to the user?

You can use:

```java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : diagnostics.getDiagnostics()) {
    System.err.println(
        diagnostic.getKind() + " at " +
        diagnostic.getLineNumber() + ":" +
        diagnostic.getColumnNumber() + " - " +
        diagnostic.getMessage(Locale.ROOT));
}
```

This is an **illustrative code snippet**, assuming the `diagnostics` variable was already created in a complete program. Only use line/column numbers when different from `Diagnostic.NOPOS`. When building a multi-tab editor, map the source URI to the corresponding tab so the user can jump to the error position.

## 6. Source from String and class output do not necessarily both reside in RAM

The chapter name “in-memory compilation” sometimes leads learners to think creating a `SimpleJavaFileObject` is all that is needed. In reality, there are two I/O directions:

```text
INPUT                               OUTPUT
String containing Java code         class bytes
   |                                   |
   v                                   v
JavaFileObject.Kind.SOURCE       JavaFileObject.Kind.CLASS
   |                                   |
getCharContent()                  openOutputStream()
   |                                   |
   +----------- JavaCompiler ----------+
                       |
                       +-- StandardJavaFileManager -> filesystem
                       |
                       +-- custom JavaFileManager -> ByteArrayOutputStream
```

In `StringSourceDemo`, the source comes from a `String`, but the output goes through `StandardJavaFileManager` with `-d`, creating `.class` on disk. To make **the compiler write no bytecode to disk at all**, we must intercept output via `JavaFileManager.getJavaFileForOutput(...)`.

That is a logical technical extension of the lesson, **not a mandatory requirement of the source SimpleJavaFileObject**. Managing in-memory class output is a separate responsibility, so do not try to put `openOutputStream` onto the same `Kind.SOURCE` object expecting the compiler to write class bytes into that source object.

## 7. Advanced example: both source and bytecode in memory

Create the file **`FullyMemoryDemo.java`**. The example consists of four components:

1. `Source`: as before, holds the String and has `Kind.SOURCE`.
2. `Output`: a `SimpleJavaFileObject` with `Kind.CLASS`, writing data to a `ByteArrayOutputStream`.
3. `MemoryFiles`: wraps `StandardJavaFileManager`, intercepting class output from the compiler to store in a Map.
4. `ClassLoader`: loads the newly generated `byte[]` bytecode and invokes a sample method.

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
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

public class FullyMemoryDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String name, String content) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class Output extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        Output(String name, Kind kind) {
            super(URI.create("mem:///" + name.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] content() {
            return bytes.toByteArray();
        }
    }

    static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        final Map<String, Output> classes = new HashMap<>();

        MemoryFiles(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className, JavaFileObject.Kind kind,
                FileObject sibling) throws java.io.IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            Output output = new Output(className, kind);
            classes.put(className, output);
            return output;
        }
    }

    public static void main(String[] args) throws Exception {
        String source = """
                package demo;
                public class InMemory {
                    public static int sum(int x, int y) {
                        return x + y;
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> issues = new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                    issues, Locale.ROOT, StandardCharsets.UTF_8);
             MemoryFiles memory = new MemoryFiles(standard)) {
            boolean ok = compiler.getTask(
                    null,
                    memory,
                    issues,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new Source("demo.InMemory", source))
            ).call();

            System.out.println("compiled=" + ok);
            if (!ok) {
                return;
            }

            ClassLoader loader =
                    new ClassLoader(FullyMemoryDemo.class.getClassLoader()) {
                        @Override
                        protected Class<?> findClass(String name)
                                throws ClassNotFoundException {
                            Output output = memory.classes.get(name);
                            if (output == null) {
                                throw new ClassNotFoundException(name);
                            }
                            byte[] bytes = output.content();
                            return defineClass(name, bytes, 0, bytes.length);
                        }
                    };

            Class<?> type = loader.loadClass("demo.InMemory");
            Object result = type.getMethod(
                    "sum", int.class, int.class).invoke(null, 7, 8);
            System.out.println("result=" + result);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 FullyMemoryDemo.java
java FullyMemoryDemo
```

Stdout **verified on JDK 24**:

```text
compiled=true
result=15
```

There is no `-d` in the **dynamic compilation call inside the application**; the compiler calls `MemoryFiles.getJavaFileForOutput` and receives an `Output` object. When writing the class file, the compiler uses `openOutputStream`, so the bytecode is kept in `ByteArrayOutputStream` instead of creating `demo/InMemory.class` from the dynamic compilation pass.

**Scope of the claim “fully in memory”:** this refers to the **`demo.InMemory` source and the bytecode of the dynamic compilation pass**. The `FullyMemoryDemo.java` file and the class file of the **host program** are still produced by the external `javac FullyMemoryDemo.java` command. The standard file manager can still read libraries/JDK/classpath; this is not a mechanism that blocks all I/O across the entire JVM.

### Why is a Map by binary name needed?

When the compiler generates multiple classes (such as inner classes or classes from multiple sources), each output has **its own binary name**. `Map<String, Output>` holds the corresponding bytecode so the class loader can look it up by name. Keeping only one shared `ByteArrayOutputStream` for all outputs can cause multiple class files to overwrite/corrupt each other's data.

In production, you may also need to handle resources generated by annotation processors, concurrency, package resolution, and module names. The example above demonstrates the **capture class output** principle, and does not automatically become a compiler server supporting every kind of build.

### Is the example's class loader a sandbox?

**No.** `ClassLoader.defineClass` is a mechanism for defining classes inside the JVM, not restricting all actions that can be performed by the loaded code. If the source comes from untrusted users, you need **process/container/VM isolation**, resource limits, and permissions according to an appropriate security model. Do not use a custom class loader as the sole security boundary.

## 8. Why not use Files.readString or getJavaFileObjectsFromStrings?

The two approaches have different goals:

```java
String sourceText = "public class A {}";
```

`sourceText` is **Java code content**. However, the API:

```java
fileManager.getJavaFileObjectsFromStrings(
    java.util.List.of("A.java"));
```

accepts **file names/paths** under the standard file manager's contract, not raw Java code content from a string. If you pass `"public class A {}"` into that list, the tool may treat it as a **strange path name**, not a source unit.

Using `StandardJavaFileManager` to read files already on disk is completely appropriate when the goal is to compile files. Using `SimpleJavaFileObject + getCharContent` is suitable when **the source only resides in a String** or is synthesized in RAM.

As for `Files.readString(path)`, it is an API for reading from a real file; using it before creating `StringSource` still works, but **brings no benefit if the source is already in memory**. Choose the method based on the actual data source.

## 9. Multiple StringSources in one CompilationTask

Suppose there are two source units:

```java
String utilCode = """
        package demo;
        public class Util {
            public static int doubleOf(int n) {
                return n * 2;
            }
        }
        """;

String mainCode = """
        package demo;
        public class UseUtil {
            public static void main(String[] args) {
                System.out.println(Util.doubleOf(5));
            }
        }
        """;
```

These are **two illustrative String declaration snippets** inside a Java 17+ method, not a standalone program. Once you have the `Source` class from above, you can pass:

```java
List.of(
    new Source("demo.Util", utilCode),
    new Source("demo.UseUtil", mainCode)
)
```

into the `compilationUnits` parameter of `compiler.getTask(...)`. The compiler knows both source units within the same task and can resolve the reference to `Util` from `UseUtil` without needing to create two `.java` files beforehand.

If the classes are written to disk with `-d out` and run with `java -cp out demo.UseUtil`, stdout will be:

```text
10
```

**Important:** the multi-source example above consists of code snippets to **insert into an appropriate JavaCompiler API host**; it is not a standalone shell command. Do not confuse having a valid `List.of(...)` with a complete program containing `main`.

### Each source must have its own URI

Even though both classes share the `demo` package, the two URIs are still:

```text
string:///demo/Util.java
string:///demo/UseUtil.java
```

Do not assign a shared `string:///demo/Source.java` to both and expect the compiler to infer everything from the content. The URI describes the **source unit**, not just the package.

## 10. DiagnosticCollector, Charset, and error positions

Because `getCharContent` returns an already-decoded `CharSequence`, the `Charset` parameter of `getStandardFileManager(...)` **does not automatically re-encode `Source`'s source String**. It remains useful for real files read by the standard manager and related file operations.

Example:

```java
compiler.getStandardFileManager(
    diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
```

- `Locale.ROOT` helps select diagnostic output in a locale-neutral format when the API supports it.
- `StandardCharsets.UTF_8` specifies the charset used by the standard file manager; it does not “convert every String to UTF-8” because a String inside the JVM is already in character form.
- `DiagnosticCollector` collects the list of diagnostics, supporting `ERROR/WARNING/NOTE` levels, URI, line, column, diagnostic code, and message.

You can inspect further:

```java
long line = issue.getLineNumber();
long column = issue.getColumnNumber();
String code = issue.getCode();
String message = issue.getMessage(Locale.ROOT);
```

This is an illustrative snippet inside a loop with a variable `issue` of type `Diagnostic<? extends JavaFileObject>`. Internal diagnostic codes and message text may vary across JDKs/vendors; rely on `Kind`, source URI, position, and testing policy instead of trying to hard-code an English sentence.

A diagnostic not attached to a specific source may have `getSource() == null`, so **check for null before calling `toUri()`** in general programs. The `StringSourceErrorDemo` lesson has a corresponding source, so `getSource()` is non-null in the verified case.

## 11. JavaCompiler.CompilationTask: which parameters are easily confused?

Common signature:

```java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
```

The signature above is rewritten to explain the API; no need to copy it into source.

Practical meaning:

1. `out` is where some additional compiler tool output is written; pass `null` in demos to use the default.
2. `fileManager` coordinates input/output lookup paths; it can be the standard manager or your `ForwardingJavaFileManager`.
3. `diagnosticListener` receives structured diagnostics; `DiagnosticCollector` is a convenient implementation.
4. `options` is the list of individual compiler arguments, for example `List.of("--release", "17", "-d", classes.toString())`.
5. `classes` is used for class names to be processed under relevant modes; demos compiling source units directly should pass `null`.
6. `compilationUnits` is the `JavaFileObject` collection containing the source units.

**Do not mix up the order of `options` and `compilationUnits`.** Strings like `"--release"`, `"17"` are *compiler options*, whereas content like `"public class..."` must reside in `Source.getCharContent`.

### Each task should have a clear purpose and lifecycle

`CompilationTask.call()` should only be called once per task. If you want to compile new code, create a new task and supply appropriate source units/diagnostics again; do not keep one task and call `call()` repeatedly like a service endpoint. Reusing a compiler instance or file manager must follow the API documentation; do not infer general thread safety from a single-threaded example.

Managing `StandardJavaFileManager` with try-with-resources as in the examples helps release resources. With a custom forwarding manager, closing both the wrapper and delegate must be handled explicitly; the `FullyMemoryDemo` example closes two resources in order, suitable for the tested experiment.

## 12. Classpath, annotation processors, and modules still matter

Sources from `String` **do not bypass the type resolution system**. If the code contains `import com.example.Service;`, the compiler still needs to find the library providing that class.

Example compiler options for external libraries:

```java
List.of(
    "--release", "17",
    "-classpath", "libs/example.jar",
    "-d", output.toString()
)
```

This is an illustrative options list; a real JAR file is needed if you want to compile dependent code. The compiler does not automatically access the Internet or download dependencies when it sees `import`.

Several notes:

- If compiling code belonging to a **named module**, consider `module-info.java`, `--module-path`, and the module model, not just replacing the classpath.
- Annotation processing can be enabled, disabled, or configured depending on the toolchain. If you only need to check source without running external processors, use `-proc:none` when appropriate for the JDK.
- If intending to run processors, configure `-processor`, `-processorpath`, or the corresponding processor module path, along with processor dependencies.
- Do not treat the `string` URI scheme as a module path or filesystem path; it is only the identifier of the input JavaFileObject.
- Class output in memory does not mean dependent classes are also in memory: the compiler may still read the classpath/module path from disk or the runtime image.

In large systems, the distinction between **class name**, **source URI**, **runtime class loader**, and **module name** can cause hard-to-debug errors; log the exact layer of information rather than only saving the source string.

## 13. Common errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `getSystemJavaCompiler()` returns `null` | Application runs in an environment without a system Java compiler | Run with a JDK having the `jdk.compiler` module, check runtime image |
| Source unit not found | Passing String directly instead of `JavaFileObject` or invalid URI/Kind | Ensure `Kind.SOURCE` and `getCharContent` |
| `public class Hello` reports file mismatch | URI/name incompatible with the public class name | Use logical name `demo.Hello` -> `string:///demo/Hello.java` |
| Source has `package demo` but references fail to resolve | Binary name/URI mismatch or missing source/dependency | Verify URI and compilation units list |
| `compiled=false` yet host exit code is still 0 | Task returned failure, host did not call `System.exit` | Read Boolean result and diagnostics |
| Null `getSource()` causes `NullPointerException` | Diagnostic has no specific source | Check for null before `toUri()` |
| `.class` not found in expected directory | Wrong output path, custom manager holding bytecode, or `-proc:only` | Verify `-d`, file manager, task mode |
| Compilation succeeds but classloader cannot find class | Class output is not at the corresponding URL/classloader | Check package/class path and loader |
| Class compiles but fails to run due to dependency error | Runtime lacks required classes or modules | Check the separate runtime classpath/module path |
| Bytecode from multiple classes gets overwritten | Using a single buffer instead of a map by binary name | Use one output object per class |
| Encoding error despite source being a String | Code creating the String was wrong or dependent file uses another charset | Check how the String was created and file manager |
| Repeated compilations cause RAM leaks | Retaining bytecode, source, diagnostics, class loader too long | Set limits/lifecycles and release references |

**Do not fix the wrong kind of error:** a wrong URI is not a classloader issue if `javac` has not compiled successfully yet; conversely, successful compilation followed by `ClassNotFoundException` during dynamic loading is a runtime loader/output issue, not `getCharContent`.

## 14. Performance, limits, and security

Compiling code from memory can reduce the need to create temporary `.java` files, but **is not guaranteed to be faster in every case**. `JavaCompiler` still has to parse/type-check/emit bytecode, may access the JDK and libraries, generate diagnostics, and consume CPU/RAM. Reusing compiler structures must adhere to resource and lifecycle contracts.

Points to actively control:

- **Limit source size:** avoid accepting unbounded strings that exhaust the heap.
- **Limit CPU/memory time:** an input can cause the compiler/processor to consume heavy resources; the API does not provide a sandbox on its own.
- **Avoid running untrusted code in the same process:** custom classloaders and `-proc:none` do not replace system isolation.
- **Do not load arbitrary processors from untrusted sources:** annotation processors can be executable code inside the compiler process; manage the processor path.
- **Manage diagnostics:** do not inadvertently return internal logs or sensitive paths.
- **ClassLoader lifecycle:** loaded bytecode can persist as long as references to the classloader, class, or objects exist; clearing the map does not mean immediately freeing all runtime classes.
- **Temporary resources:** if using an output directory, track and delete only directories you created, avoiding affecting out-of-scope data.

An “online Java runner” system must have an appropriate isolation architecture. This lesson **only teaches how to represent sources and invoke the compiler**, and does not provide security guarantees for executing user code.

## 15. Practice exercises

### Exercise 1 — Identifying JavaFileObject

A `Source` class holds a `String` of Java code and wants the compiler to read that code. What constructor and overrides are needed?

**Answer:** Create a `SimpleJavaFileObject` with the source unit's logical URI and `Kind.SOURCE`; override `getCharContent(boolean)` returning a `CharSequence` containing the code. `openOutputStream` is not automatically needed on the source object.

### Exercise 2 — Source name and package

The source contains `package shop; public class Product {}`. Which binary name does the URI correspond to?

**Answer:** `shop.Product` and a logical URI like `string:///shop/Product.java`. Do not use `shop/Other.java` for public class Product.

### Exercise 3 — Which line is the error on?

Why can `DiagnosticCollector` print `string:///demo/Broken.java` even though this file does not exist on the filesystem?

**Answer:** Because `JavaFileObject.toUri()` is provided by the source object; the compiler associates the diagnostic with that very JavaFileObject. `getCharContent` provides the actual characters, without needing a physical file.

### Exercise 4 — Compilation succeeded but no destination file

A dynamic compilation pass uses custom `MemoryFiles` and a bytecode map. Not seeing `demo/InMemory.class` on disk—did the compiler fail?

**Answer:** No. `CompilationTask.call()` can return `true`; the bytecode was written to `Output`'s `ByteArrayOutputStream`, not the filesystem.

### Exercise 5 — Misusing the semantics of getJavaFileObjectsFromStrings

A learner writes `fileManager.getJavaFileObjectsFromStrings(List.of("public class A {}"))`. Why does this miss the goal?

**Answer:** The standard file manager's method accepts **file names**, not source code strings. You need to create `StringSource("A", "public class A {}")` and pass it into compilation units.

### Exercise 6 — Why does compiled=false not cause the host to fail?

The host prints `compiled=false` yet the `java StringSourceErrorDemo` command returns exit code 0. Is that unusual?

**Answer:** No. The compiler task and host application are two result layers. If the host needs to report a build failure to the shell/CI, determine the host's exit code explicitly.

### Exercise 7 — Diagnostic without a source

If a diagnostic has `getSource() == null`, what happens when calling `issue.getSource().toUri()`?

**Answer:** `NullPointerException`. Only read the URI when a source is present; use `Diagnostic.NOPOS` to recognize cases without line/column.

### Exercise 8 — Keeping code completely in RAM

Is overriding only `Source.getCharContent` enough to keep bytecode in RAM?

**Answer:** No. You must provide a file manager capable of creating `Kind.CLASS` output objects whose `openOutputStream()` writes into a buffer, then manage class bytes and the loader if execution is needed.

### Exercise 9 — Is running external code safe?

Does compiling a String source and loading it with `ClassLoader.defineClass` guarantee preventing the code from reading files or making network connections?

**Answer:** No. ClassLoader is not a full security sandbox. You need an isolated environment and an appropriate resource management policy for untrusted sources.

## 16. Checklist when writing a real StringSource

- [ ] `getSystemJavaCompiler()` is not `null`.
- [ ] `StringSource` has a valid, unique URI and `Kind.SOURCE`.
- [ ] The URI reflects the binary name/package of the top-level public type.
- [ ] `getCharContent(boolean)` returns the properly constructed Java code.
- [ ] Each source unit in the task has its own identifier.
- [ ] `getTask(...)` receives the parameters in the right order and the `compilationUnits` collection.
- [ ] Options have each argument properly structured, e.g. `"--release", "17"`.
- [ ] A `DiagnosticCollector` is present to handle errors/warnings and source positions.
- [ ] Read Boolean/`Boolean.TRUE.equals` of `call()` before loading classes.
- [ ] Distinguish the standard file manager and a custom manager for in-memory bytecode.
- [ ] Close the file manager and classloader when appropriate.
- [ ] If using a custom classloader, distinguish runtime classpath and compiler classpath.
- [ ] Do not assume the host exit code matches the dynamic compilation result.
- [ ] Do not execute untrusted code inside the host JVM without isolation measures.

## 17. Conclusion and official documentation

**`SimpleJavaFileObject` is the bridge between a character string inside the JVM and an abstract input that `JavaCompiler` can compile.** The three core elements are **the URI identifying the source unit**, **`Kind.SOURCE`**, and **`getCharContent(boolean)`** returning the String content. From there, `JavaCompiler.getTask(...)` performs type checking and emits class files; `DiagnosticCollector` allows linking errors/warnings with the URI and source position even without a real file.

If you want all **output bytecode to reside in RAM**, you must also extend the output `JavaFileManager`/`SimpleJavaFileObject`, not only modify the source object. Loading/running classes must be handled separately and is not a security mechanism for untrusted code.

References:

1. [Java SE 17 — SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): constructor `(URI, Kind)` and methods to override.
2. [Java SE 17 — JavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html): `Kind.SOURCE`, `Kind.CLASS`, and source/class interface.
3. [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, standard file manager, and compilation units.
4. [Java SE 17 — ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): retrieving the system Java compiler.
5. [Java SE 17 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): collecting structured diagnostics.
6. [Java SE 17 — ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): wrapping and customizing the compiler's file lookup/write mechanisms.

When debugging a String source compilation problem, check in this order: **source name and URI → `getCharContent` → compilation units/options → diagnostics → file manager/output → class loader**. Dividing the layers clearly helps find the real bug instead of confusing source code, bytecode, and runtime.