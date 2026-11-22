# JavaFileObject Model and URI of a Source Unit in In-Memory Compilation

In the Java Compiler API, source code does not have to reside in a `.java` file on disk. The compiler can read a `String` through an object implementing `JavaFileObject`. That object has a **URI as its logical identity**, a **Kind to indicate the file type**, and methods providing content. This is the foundation of embedded compilers in IDEs, REPLs, code generation tools, or source-checking services.

This lesson belongs to the **In-Memory Compilation** topic of Java Advance – compilation. The focus is distinguishing a class's binary name, a compilation unit's URI, source text content, the lookup/write mechanism of JavaFileManager, and bytecode output. Examples use APIs available in Java 17, run with `javac --release 17`; differences from newer JDKs are noted separately.

## 1. JavaFileObject is a Java file model, not synonymous with a real file

`javax.tools.JavaFileObject` extends `javax.tools.FileObject`. They represent objects that compiler tools can read from or write to, whether the actual data resides in RAM, the filesystem, a JAR, or another storage source.

Key components:

| API | Role |
|---|---|
| `toUri()` | Returns the URI identifying the file object |
| `getName()` | Display name for users, diagnostics, or tools |
| `getKind()` | Classifies the unit as SOURCE, CLASS, HTML, OTHER |
| `getCharContent(boolean)` | Reads the character content of the file object |
| `openReader(boolean)` | Opens a Reader if the implementation supports it |
| `openInputStream()` | Opens a byte input stream when supported |
| `openOutputStream()` | Opens a byte output stream, commonly used for class output |
| `openWriter()` | Writes characters when the file object supports it |
| `isNameCompatible(simpleName, kind)` | Matches the simple name and Kind |
| `getLastModified()`, `delete()` | Auxiliary metadata/operations depending on the implementation |

`JavaFileObject.Kind` consists of `SOURCE` (extension `.java`), `CLASS` (`.class`), `HTML` (`.html`), and `OTHER` (no default extension).

A file object for Java source contains **text characters** and uses `Kind.SOURCE`. A file object for output bytecode contains **binary bytes** and uses `Kind.CLASS`. Do not read `.class` by arbitrarily decoding it into a String; nor attach Kind.CLASS to a source simply because the compiler is about to generate a class from that source.

### 1.1. Compilation unit is not synonymous with a single class output

A source `JavaFileObject` represents **a compilation unit**. One Java file can contain one public top-level class, package-private types, and nested classes. Therefore, a single source can generate **multiple** `.class` files:

~~~java
package demo;

public class Hello {
    static class Nested {}
}

class Helper {}
~~~

With a source like the above, the compiler can generate `demo/Hello.class`, `demo/Hello$Nested.class`, and `demo/Helper.class`. The in-memory output file manager must store each class separately. Do not assume one source always corresponds to exactly one class.

## 2. Source URI: logical identity instead of physical path

URI stands for Uniform Resource Identifier. The `FileObject.toUri()` API does not require using the `file:` scheme. Illustrative examples:

~~~text
file:///home/reader/project/src/demo/Hello.java
string:///demo/Hello.java
mem:///demo/Hello.class
jar:file:///opt/libs/example.jar!/demo/Hello.class
~~~

Where:

- `file:` can represent a real file on the filesystem.
- `jar:` can represent an entry inside a JAR.
- `string:` is a **custom scheme** to identify a source stored in a String.
- `mem:` is a **custom scheme** for output residing in RAM.

There is no standard network protocol or filesystem automatically handling `string:` and `mem:` in the examples. A URI is a **name**, while the content is provided by the JavaFileObject implementation. When writing `string:///demo/Hello.java`, no real `Hello.java` file automatically appears on disk.

### 2.1. Why is string:/// commonly used?

~~~java
URI uri = URI.create("string:///demo/Hello.java");
~~~

This URI has scheme `string`, path `/demo/Hello.java`, and no authority. Use a path resembling the package structure so the file object and the compiler share a consistent convention. Do not convert a `string:` URI to a `Path` and assume `Files.readString` will work; there is no corresponding default filesystem provider.

### 2.2. Class name, file name, and URI are three concepts

With the source:

~~~java
package demo;
public class Hello {}
~~~

| Concept | Value |
|---|---|
| Binary name | `demo.Hello` |
| Simple class name | `Hello` |
| Source URI in the example | `string:///demo/Hello.java` |
| Bytecode URI in the example | `mem:///demo/Hello.class` |

A URI can be constructed from the binary name:

~~~java
String binaryName = "demo.Hello";
URI sourceUri = URI.create(
    "string:///" + binaryName.replace('.', '/')
    + JavaFileObject.Kind.SOURCE.extension
);
~~~

The output has URI `string:///demo/Hello.java`. The example assumes the binary name is a valid Java name. In an application accepting external data, you must **validate the class/package name** before concatenating the URI string and encode URI characters if needed. The binary name differs from the name displayed by an editor, and differs from the actual source content.

### 2.3. Meaning of isNameCompatible

`SimpleJavaFileObject.isNameCompatible` checks whether the Kind and URI path are compatible with the requested simple name. If the URI ends with `/Hello.java` and Kind is SOURCE:

~~~java
source.isNameCompatible("Hello", JavaFileObject.Kind.SOURCE); // true
source.isNameCompatible("Other", JavaFileObject.Kind.SOURCE); // false
~~~

This is an illustrative snippet with an already-created `source` variable. Naming conventions are especially important for a **public top-level class**: a source declaring `public class Hello` but given a logical name `Wrong.java` may be rejected by the compiler, similar to standard Java file naming rules.

## 3. Creating a JavaFileObject from a String using SimpleJavaFileObject

`javax.tools.SimpleJavaFileObject` is designed to be subclassed. Primary constructor:

~~~java
protected SimpleJavaFileObject(URI uri, JavaFileObject.Kind kind)
~~~

Example of a read-only source object:

~~~java
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

final class StringSource extends SimpleJavaFileObject {
    private final String content;

    StringSource(String binaryName, String content) {
        super(URI.create("string:///"
                + binaryName.replace('.', '/')
                + JavaFileObject.Kind.SOURCE.extension),
              JavaFileObject.Kind.SOURCE);
        this.content = content;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return content;
    }
}
~~~

This is a **component class**, not yet a standalone program. The complete program with main is in section 7.

Key points:

1. `super(uri, SOURCE)` provides the identity and type of the source unit.
2. `getCharContent` returns the source text already stored in the String.
3. The compiler can parse the source even without a physical file.
4. By default, `SimpleJavaFileObject.getCharContent` throws `UnsupportedOperationException`; if not overridden, the virtual source cannot provide content this way.
5. The `ignoreEncodingErrors` parameter relates to reading/decoding bytes; with a String already containing characters, the implementation above does not need to decode bytes and returns content directly.

An in-RAM source does not automatically make all outputs reside in RAM too. If using the default file manager, the compiler can still write bytecode to disk. You must configure **both the source input path and the result output path**.

## 4. How do JavaCompiler and JavaFileManager coordinate?

Main components of the `javax.tools` package:

- `ToolProvider.getSystemJavaCompiler()`: retrieves the JDK environment's Java compiler; may return null if the runtime does not provide a compiler.
- `JavaCompiler.getTask(...)`: creates a compilation task, accepting options, file manager, diagnostics, classes/processors, and the list of compilation units.
- `JavaCompiler.CompilationTask.call()`: performs compilation, typically returning a Boolean.
- `StandardJavaFileManager`: the standard file manager handling files, classpath, module path, and standard locations.
- `ForwardingJavaFileManager`: wraps another manager and overrides only the operations that need customization.
- `DiagnosticCollector<JavaFileObject>`: collects errors/warnings with source information, location, and severity.
- `JavaFileObject`: the compiler-level input/output unit.

Basic flow:

~~~text
String containing source
        |
        v
StringSource: Kind.SOURCE, URI string:///demo/Hello.java
        |
        v
JavaCompiler.getTask(..., sources)
        |
        v
parse -> resolve -> type check -> generate
        |
        v
JavaFileManager.getJavaFileForOutput(...)
        |
        v
BytecodeOutput: Kind.CLASS, URI mem:///demo/Hello.class
        |
        v
byte[] in RAM -> ClassLoader -> execute
~~~

When you only want the source in RAM but output on disk, you can use StandardJavaFileManager with `-d out`. When you want **both source and class output in RAM**, the file manager needs to return an object that receives bytes when the compiler requests output.

### 4.1. getJavaFileForOutput

Important signature:

~~~java
JavaFileObject getJavaFileForOutput(
    JavaFileManager.Location location,
    String className,
    JavaFileObject.Kind kind,
    FileObject sibling
) throws IOException;
~~~

- `location`: logical location, such as CLASS_OUTPUT during a class-emitting task.
- `className`: binary name of the class the compiler is generating.
- `kind`: typically CLASS when generating `.class`.
- `sibling`: hint about the origin/related object; not assumed to be a real file path.

The file manager can return a JavaFileObject whose `openOutputStream()` writes to a ByteArrayOutputStream. If there are multiple class outputs, each class must have its own buffer. `ForwardingJavaFileManager` allows standard operations that are not overridden to continue being handled by the standard manager.

## 5. Compiling in RAM vs. loading classes in RAM

**Compile-time:** JavaCompiler locates sources, symbols, and dependencies through JavaFileObject and JavaFileManager. It generates bytecode.

**Runtime:** JVM/ClassLoader locates or defines classes from appropriate bytecode. ClassLoader does not itself participate in compiling sources inside JavaCompiler.

In the example in section 7, the output map stores `String binaryName -> BytecodeOutput`. A custom ClassLoader retrieves byte[] from the map and calls `defineClass`. This proves that both source and dynamically generated bytecode can reside in RAM, but **ClassLoader is not a security sandbox** and does not replace the compiler classpath.

If after compiling class A, you create a **second compiler task** to compile B depending on A, having only the byte map from the first task is not enough. The file manager needs to help the compiler find class A (or you output it to a standard location). With multiple interdependent sources, compiling **in the same task** is usually simpler.

## 6. SourceObject and ClassOutputObject have different access capabilities

A source object typically only needs to provide:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return content;
}
~~~

A class output object typically provides:

~~~java
@Override
public OutputStream openOutputStream() {
    return output;
}
~~~

`output` is the object's own ByteArrayOutputStream. Do not use `getCharContent` to read a class file into a String because bytecode is binary data.

A URI like `mem:///demo/Hello.class` does not mean `new URL(...).openStream()` can automatically read bytes from the map. A **specific file manager/class loader** capable of reading the data is required. The URI by itself only identifies the object.

## 7. Complete Java 17 Program: String source to bytecode in RAM

Create the file **InMemoryCompilationDemo.java** with the exact name and no package declaration. The code below is a complete program, compiled and run with `javac --release 17` on JDK 24.0.2.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryCompilationDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String content;

        StringSource(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class BytecodeOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        BytecodeOutput(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] bytes() {
            return output.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        StringSource source = new StringSource(
                "demo.Hello",
                "package demo; public class Hello { "
                + "public static String message() { return \"Xin chào\"; } }");

        Map<String, BytecodeOutput> outputClasses = new HashMap<>();
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                    compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
             JavaFileManager files =
                    new ForwardingJavaFileManager<StandardJavaFileManager>(
                            standard) {
                        @Override
                        public JavaFileObject getJavaFileForOutput(
                                Location location, String className,
                                JavaFileObject.Kind kind, FileObject sibling) {
                            BytecodeOutput output =
                                    new BytecodeOutput(className, kind);
                            outputClasses.put(className, output);
                            return output;
                        }
                    }) {

            Boolean succeeded = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-encoding", "UTF-8"),
                    null, List.of(source)).call();

            System.out.println("sourceURI=" + source.toUri());
            System.out.println("kind=" + source.getKind());
            System.out.println("compatible=" + source.isNameCompatible(
                    "Hello", JavaFileObject.Kind.SOURCE));
            System.out.println("compiled=" + succeeded);

            if (!Boolean.TRUE.equals(succeeded)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.out.println(
                        d.getKind() + " " + d.getMessage(Locale.ROOT));
                }
                return;
            }
        }

        ClassLoader loader = new ClassLoader(
                InMemoryCompilationDemo.class.getClassLoader()) {
            @Override
            protected Class<?> findClass(String name)
                    throws ClassNotFoundException {
                BytecodeOutput output = outputClasses.get(name);
                if (output == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = output.bytes();
                return defineClass(name, bytes, 0, bytes.length);
            }
        };

        Class<?> generated = Class.forName("demo.Hello", true, loader);
        System.out.println(
            "classURI=" + outputClasses.get("demo.Hello").toUri());
        System.out.println(
            "message=" + generated.getMethod("message").invoke(null));
        System.out.println("classCount=" + outputClasses.size());
    }
}
~~~

Compile the orchestrator program and run:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryCompilationDemo.java
java InMemoryCompilationDemo
~~~

**Verified exact stdout:**

~~~text
sourceURI=string:///demo/Hello.java
kind=SOURCE
compatible=true
compiled=true
classURI=mem:///demo/Hello.class
message=Xin chào
classCount=1
~~~

### 7.1. Explanation of each result

- `sourceURI`: the source JavaFileObject has a logical URI, with no physical `demo/Hello.java` file.
- `kind=SOURCE`: the compiler recognizes the object as source.
- `compatible=true`: the name Hello and Kind.SOURCE match the URI path.
- `compiled=true`: the JavaCompiler task completed successfully.
- `classURI`: BytecodeOutput for the class has a virtual mem URI.
- `message=Xin chào`: the class loader defined the class from byte[] stored in RAM and the method was invoked successfully.
- `classCount=1`: this specific compilation unit produced only one class.

The outermost javac command creates **InMemoryCompilationDemo.class** on disk, whereas the inner task creates **demo.Hello** in RAM. These two compilation layers must not be confused. When running the inner task, we do not invoke the javac shell command again; JavaCompiler runs inside the orchestrator tool's JVM process.

### 7.2. How to try modifying the source content

Change the source string so the message method returns `"Hello RAM"`, recompile and rerun the orchestrator program. The URI can remain the same because the binary name is still demo.Hello; the content provided by StringSource has changed. If a real application needs to version multiple edits, you should store a revision along with the URI so diagnostics map to the right source version.

If a source contains multiple classes or nested classes, outputClasses can contain multiple entries. Do not try to write all classes into the same ByteArrayOutputStream.

## 8. DiagnosticCollector uses URI to attach errors to virtual sources

Create **DiagnosticDemo.java**:

~~~java
import java.net.URI;
import java.util.List;
import javax.tools.*;

public class DiagnosticDemo {
    static class Source extends SimpleJavaFileObject {
        Source() {
            super(URI.create("string:///demo/Broken.java"), Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return "package demo;\n"
                + "public class Broken {\n"
                + " int n = \"bad\";\n"
                + "}\n";
        }
    }

    public static void main(String[] args) {
        JavaCompiler javac = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> report =
                new DiagnosticCollector<>();

        boolean ok = javac.getTask(
                null, null, report,
                List.of("--release", "17"),
                null, List.of(new Source())).call();

        System.out.println("success=" + ok);
        for (Diagnostic<? extends JavaFileObject> d
                : report.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                System.out.println("uri=" + d.getSource().toUri());
                System.out.println("line=" + d.getLineNumber());
                System.out.println("column=" + d.getColumnNumber());
                System.out.println("kind=" + d.getKind());
            }
        }
    }
}
~~~

Compile and run:

~~~sh
javac --release 17 -encoding UTF-8 DiagnosticDemo.java
java DiagnosticDemo
~~~

**Verified exact stdout:**

~~~text
success=false
uri=string:///demo/Broken.java
line=3
column=10
kind=ERROR
~~~

There is no Broken.java file on disk: the compiler receives source text from getCharContent and the diagnostic returns the URI we specified.

In general code, check `d.getSource() != null` before retrieving the URI; global diagnostics may have no source or position, and line/column may hold `Diagnostic.NOPOS`. Line/column values correspond to the **exact version of text the compiler read**. When an editor modifies source continuously, you need to associate the URI with a revision to avoid highlighting the wrong place.

DiagnosticDemo uses the default file manager because it illustrates a **failed compilation** pass. To ensure successful passes do not create class files on disk, a custom file manager like InMemoryCompilationDemo is needed.

## 9. Compiling multiple JavaFileObjects in the same task

`JavaCompiler.getTask` accepts an Iterable of `JavaFileObject`. One task can contain multiple compilation units and allows the compiler to resolve cross-references.

Example placed in a program that already defines StringSource:

~~~java
JavaFileObject library = new StringSource(
    "demo.Library",
    "package demo; public class Library { "
    + "public static int answer() { return 42; } }"
);

JavaFileObject main = new StringSource(
    "demo.Main",
    "package demo; public class Main { "
    + "public static void main(String[] args) { "
    + "System.out.println(Library.answer()); } }"
);

List<JavaFileObject> units = List.of(library, main);
~~~

Pass `units` to getTask instead of `List.of(source)`. The snippet above does not run on its own because it still needs a compiler task, file manager, and imports; it is an extension for the complete program.

Benefit: the compiler sees both Library and Main together, without needing to immediately build a mechanism to read class bytes from a previous task. For a separate subsequent task, if you want to use in-memory class bytes as a dependency, you must implement a file manager to return those class files when the compiler looks them up.

### 9.1. Methods to consider for an advanced file manager

In a multi-pass compilation system, besides getJavaFileForOutput, you may need:

- `getJavaFileForInput`: returns class/source input by location, binary name, and Kind.
- `list`: lets the compiler list file objects in a package by Kind.
- `inferBinaryName`: converts a file object managed by the manager into the proper binary name.
- `hasLocation` and location configuration: ensures the compiler knows where to look.
- `getFileForOutput`: handles resources that are not just classes, potentially generated by annotation processors.
- Managing source/class output for multiple tasks, module path, and classpath as required.

Overriding only getJavaFileForOutput does **not** create a complete in-memory classpath. The design must rely on the JavaFileManager contract, rather than assuming the compiler automatically sees every bytecode map.

## 10. Valid URI, yet the compiler can still report errors

A valid URI **does not guarantee valid code**. The compiler still enforces the Java Language Specification:

- The package and public class must be consistent with the source unit.
- Types, variable/method names, access modifiers, and generics must be valid.
- If the source imports external libraries, the compiler must be able to find dependencies via classpath/module path.
- If multiple sources share the same binary name, a duplicate class error may occur.
- If the output object does not support the write operation the compiler uses, the task may fail with an I/O error.

Example: StringSource has URI string:///demo/Hello.java and code `package demo; public class Hello...` is consistent. However, content `package other; public class Hello...` will not match expectations from the URI and lookup if the file manager system organizes sources by demo.Hello. Design binary name, source package, and URI under one convention, instead of only trying to make the URI parseable.

### 10.1. Are duplicate URI names allowed?

Within the same set of compilation units, choose distinct URIs for distinct sources. Duplicate URIs can make source identification, caching, or diagnostics ambiguous. For an editor with multiple files sharing the name Hello.java in different packages, the URI needs to reflect the package path or another valid identifier.

### 10.2. When names come from users

Do not concatenate arbitrary data directly into URI paths. Validate Java identifiers and package components, avoid traversal or characters that alter URI structure; use appropriate URI constructors/escaping if needed. The display name for the editor may differ from the binary name the compiler uses.

## 11. Java versions: which APIs exist since JDK 17?

The core interfaces and classes `JavaCompiler`, `JavaFileObject`, `SimpleJavaFileObject`, `StandardJavaFileManager`, `ForwardingJavaFileManager`, and `ToolProvider` are supported in Java 17. The main example uses these APIs, so Java 23 is not required.

**Since JDK 23**, `SimpleJavaFileObject.forSource(URI, String)` helps create a source object directly without writing a subclass:

~~~java
JavaFileObject source = SimpleJavaFileObject.forSource(
    URI.create("string:///demo/Hello.java"),
    "package demo; public class Hello {}"
);
~~~

The snippet above is only for **JDK 23 and above**. Do not write it into a project required to compile with `--release 17`, because Java 17 does not have this factory method yet.

In InMemoryCompilationDemo, the options passed to the **inner task** are:

~~~java
List.of("--release", "17", "-encoding", "UTF-8")
~~~

This flag instructs JavaCompiler to target Java 17; it does not automatically change the runtime version running the orchestrator tool. If the compiler JDK does not support that release, the task will fail. To check, inspect `javac -version`, `java -version`, and the tool's actual options.

## 12. Common errors and how to fix them

| Symptom | Common Cause | How to Verify/Fix |
|---|---|---|
| getSystemJavaCompiler returns null | The runtime does not provide a compiler | Run with a JDK having jdk.compiler or a suitable toolchain |
| UnsupportedOperationException when reading source | SimpleJavaFileObject has not overridden getCharContent | Provide getCharContent or a suitable text-reading method |
| public class must be in Hello.java | URI/name does not match the simple name | Use a URI ending with /Hello.java with SOURCE |
| package does not exist | Missing source or dependency needed for compilation | Pass all required units, configure classpath/module path |
| Bytecode appears on disk | Output is still written by the standard manager | Intercept getJavaFileForOutput and return BytecodeOutput |
| Compiled successfully but cannot load class | The runtime loader lacks bytes for the right binary name | Keep a map of all outputs, check the loader |
| Second task does not see classes from the first task | The RAM map has not been exposed as compiler input | Add list/getJavaFileForInput/inferBinaryName or compile in the same task |
| Only one output despite source having nested classes | The file manager overwrites the same buffer | Create a separate BytecodeOutput per className |
| Diagnostic URI does not have the right source | Duplicate identity or wrong text/revision map | Associate the URI with the right source unit and revision |
| string: URI cannot be read with Files | This is a logical scheme, not a filesystem path | Read from JavaFileObject/custom file manager |
| Mistaking ClassLoader for a sandbox | Defined classes still run inside the JVM | Do not execute untrusted code in a privileged process |
| Byte/loader cache increases RAM usage | Keeping maps and references too long | Define lifecycles, clear caches, and set quotas |

## 13. Secure design for embedded compilers

If building a service that accepts source from an editor or external requests, distinguish **compilation** and **execution**.

1. Limit the number of sources, source size, and CPU/RAM usage.
2. Validate binary names and URIs; avoid confusing user inputs with arbitrary filenames.
3. Lock down the list of trusted compiler options and dependencies.
4. Consider annotation processors: they are **code running during the build**, not just metadata.
5. Do not put secrets into diagnostic logs or untrusted sources.
6. Do not invoke user-compiled code inside the same JVM that has system access without proper sandboxing/process isolation.
7. Manage the lifecycles of JavaFileManager, ClassLoader, and the bytecode cache.
8. Associate diagnostics with the exact source URI, line/column, and revision.
9. Run tests on the actual target JDK and classpath/module path.
10. Separate the runtime loader from the compile-time file manager and verify dependencies on both sides.

A custom ClassLoader is **not** a security boundary; it helps define and find classes, but code can still use APIs with the JVM process's permissions. In applications with untrusted code, isolate processes/containers, permissions, and resources appropriately.

## 14. Practice exercises

**Exercise 1:** From binary name `edu.lesson.Parser`, construct the SOURCE and CLASS URIs. Suggested answer: `string:///edu/lesson/Parser.java` and `mem:///edu/lesson/Parser.class`.

**Exercise 2:** With URI `string:///demo/Hello.java`, test isNameCompatible with Hello/SOURCE, Other/SOURCE, and Hello/CLASS. Explain the results based on path and Kind.

**Exercise 3:** Given a StringSource containing two top-level classes and a nested class. Predict the number of class outputs, then observe the BytecodeOutput map. Why can one source generate multiple classes?

**Exercise 4:** Add a demo.Library source and a demo.Main source referencing Library, pass both into one getTask. Compare with passing only Main without the dependency.

**Exercise 5:** Change the content of DiagnosticDemo to an error on another line, check Diagnostic.getSource().toUri(), line, and column. Why can the error still be attached to the source even without a real file?

**Exercise 6:** Compare source URI and class URI in the stdout of InMemoryCompilationDemo. Why does the mem: scheme not allow Class.forName to automatically find the class if a ClassLoader is missing?

**Exercise 7:** Evaluate switching from compiling in one task to multiple tasks; list which JavaFileManager APIs need to be added to reuse RAM class outputs.

**Exercise 8:** When a project needs Java 17, explain why using a SimpleJavaFileObject subclass can run, whereas SimpleJavaFileObject.forSource is only suitable when targeting JDK 23+.

## 15. End-of-lesson checklist

- [ ] Distinguish binary name, URI, Kind, and source text.
- [ ] SOURCE object has a valid URI, Kind.SOURCE, and a way to read characters.
- [ ] Public class, package, and URI are set consistently.
- [ ] Compiler task receives the needed JavaFileObjects and sufficient dependencies.
- [ ] Class output is written by the file manager to the right place: RAM or filesystem.
- [ ] CLASS bytecode is bytes, not a String.
- [ ] Multiple class outputs are kept separate, including nested/helper classes.
- [ ] DiagnosticCollector maps URI and position back to the right source.
- [ ] ClassLoader sees bytecode and runtime dependencies.
- [ ] Java/API version matches the --release level.
- [ ] Resource limits are in place and ClassLoader is not treated as a security sandbox.

**Conclusion:** JavaFileObject is a **compiler-level logical file object**; URI is the object's identity, not a guarantee of a file on disk. When a Kind.SOURCE provides text via getCharContent and JavaFileManager handles output, the compiler can compile a Java string into Kind.CLASS entries in RAM. The boundary between identity, content, lookup, output, and class loading is the key to implementing correct and scalable in-memory compilation tools.

## 16. Official documentation

- Java SE 17, JavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html
- Java SE 17, SimpleJavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- Java SE 17, JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17, JavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html
- Java SE 17, ForwardingJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html
- Java SE 24, SimpleJavaFileObject and factory forSource: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- JSR 199 — Java Compiler API: https://jcp.org/en/jsr/detail?id=199
