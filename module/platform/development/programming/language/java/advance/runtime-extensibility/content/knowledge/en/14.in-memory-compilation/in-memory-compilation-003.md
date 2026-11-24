# Managing Multiple Output Classes, Nested Classes, and Binary Names in In-Memory Java Compilation

## 1. One Java Source Can Produce Multiple Class Files

The JavaCompiler API (`javax.tools`) supports compiling source code in memory. A compilation unit containing `Outer` can emit `Outer.class`, `Outer$Nested.class`, `Outer$Inner.class`, `Outer$1.class`, and other top-level classes. Therefore, you cannot assume each source returns a single byte array. A proper file manager must handle **every `getJavaFileForOutput` callback** and store each output under the **binary name** supplied by the compiler.

Distinguishing the names:

| Construct | Source/canonical name | Binary name | JAR path |
| --- | --- | --- | --- |
| Top-level | `demo.Outer` | `demo.Outer` | `demo/Outer.class` |
| Static nested | `demo.Outer.Nested` | `demo.Outer$Nested` | `demo/Outer$Nested.class` |
| Non-static inner | `demo.Outer.Inner` | `demo.Outer$Inner` | `demo/Outer$Inner.class` |
| Anonymous class | No canonical name | May be `demo.Outer$1` with javac | `demo/Outer$1.class` |

Do not guess suffixes of local/anonymous classes; the binary name is an output of the compiler, not an application naming policy. `ClassLoader.loadClass` and `Class.forName` accept **binary names**, not canonical names of nested classes.

## 2. File Manager and ClassLoader Architecture

```text
JavaFileObject SOURCE
        |
        v
JavaCompiler.getTask(...).call()
        |
        v
ForwardingJavaFileManager.getJavaFileForOutput
        | per className, Kind.CLASS
        v
Map<String, byte[]> (binaryName -> class bytes)
        |
        v
MemoryClassLoader.findClass(binaryName)
        |
        v
defineClass(binaryName, bytes, 0, bytes.length)
```

The file manager must create a **separate** `ByteArrayOutputStream` for each `className`. When compilation fails, do not publish partial bytecodes. When compilation succeeds, snapshot the entire map and pass it to a new loader. Keep shared APIs in the parent loader so SPI interfaces are not accidentally loaded twice.

## 3. Complete Java 17+ Example

Create the file `MemoryCompilerExample.java`. The example compiles a single source containing a top-level, nested, inner, and anonymous class; stores the binary names; and loads and invokes methods via reflection.

```java
import javax.tools.*;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class MemoryCompilerExample {
    static final class Source extends SimpleJavaFileObject {
        private final String code;
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

    static final class Output extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Output(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }
        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }
        byte[] bytes() {
            return bytes.toByteArray();
        }
    }

    static final class Manager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, Output> outputs = new TreeMap<>();
        Manager(StandardJavaFileManager delegate) {
            super(delegate);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) {
            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IllegalArgumentException("Unexpected kind: " + kind);
            }
            if (outputs.containsKey(className)) {
                throw new IllegalStateException("Duplicate output: " + className);
            }
            Output output = new Output(className, kind);
            outputs.put(className, output);
            return output;
        }
        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new TreeMap<>();
            outputs.forEach((name, output) -> result.put(name, output.bytes()));
            return result;
        }
    }

    static final class Loader extends ClassLoader {
        private final Map<String, byte[]> classes;
        Loader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = Map.copyOf(classes);
        }
        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(binaryName);
            if (bytes == null) throw new ClassNotFoundException(binaryName);
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        String code = """
                package demo;
                public class Outer {
                    public static class Nested {
                        public static String value() { return "nested"; }
                    }
                    public class Inner {
                        public String value() { return "inner"; }
                    }
                    public static String anonymous() {
                        Runnable r = new Runnable() {
                            public void run() {}
                        };
                        r.run();
                        return "anonymous";
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> bytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(diagnostics, null, null);
             Manager manager = new Manager(standard)) {
            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(null, manager, diagnostics,
                            List.of("--release", "17"), null,
                            List.of(new Source("demo.Outer", code))).call());
            if (!ok) {
                diagnostics.getDiagnostics().forEach(System.err::println);
                throw new IllegalStateException("Compilation failed");
            }
            bytes = manager.snapshot();
        }

        System.out.println("Outputs:");
        bytes.keySet().forEach(System.out::println);
        Loader loader = new Loader(
                MemoryCompilerExample.class.getClassLoader(), bytes);
        Class<?> outer = loader.loadClass("demo.Outer");
        Class<?> nested = loader.loadClass("demo.Outer$Nested");
        Class<?> inner = loader.loadClass("demo.Outer$Inner");
        System.out.println("Nested: " +
                nested.getMethod("value").invoke(null));
        System.out.println("Anonymous: " +
                outer.getMethod("anonymous").invoke(null));
        Object outerObject = outer.getConstructor().newInstance();
        Object innerObject = inner.getConstructor(outer)
                .newInstance(outerObject);
        System.out.println("Inner: " +
                inner.getMethod("value").invoke(innerObject));
    }
}
```

Compile and run with JDK 17+ (not a runtime missing `jdk.compiler`):

```bash
javac --release 17 MemoryCompilerExample.java
java MemoryCompilerExample
```

Expected output with JDK 17 `javac`:

```text
Outputs:
demo.Outer
demo.Outer$1
demo.Outer$Inner
demo.Outer$Nested
Nested: nested
Anonymous: anonymous
Inner: inner
```

`TreeMap` gives the printed output list a deterministic order; it is **not** guaranteed by the compiler's callback order. The name `demo.Outer$1` is the result for this source on `javac`, not a name that should be guessed when generating code. The `Outer$Inner` class receives the outer instance as a synthetic constructor parameter, unlike a static nested class.

## 4. Invariants to Maintain When There Are Multiple Output Classes

### One Callback, One Independent Output

Every time the compiler calls `getJavaFileForOutput(location, className, kind, sibling)`, you must return a `JavaFileObject` with an independent stream. If you only store `lastOutput`, earlier bytecode is lost, leading to `NoClassDefFoundError` when the outer class references inner/anonymous classes.

### Binary Name as the Key, Not the Source Filename

The map should take the form `Map<String, byte[]>` with keys like `demo.Outer$Inner`. Do not use the key `Outer.java`, do not replace `$` with `.`, and do not invent `$1` names yourself. `defineClass` must be called with the binary name matching the actual name in the bytecode; if mismatched, the JVM may report `NoClassDefFoundError: wrong name`.

### Publish Only After Success

`CompilationTask.call()` returns a `Boolean`: `false` means compilation failed. Some `.class` files may already have been emitted before the error occurred; this is a partial set and **must not be published**. Collect diagnostics, discard the collector, and let the next compilation run use fresh state.

### Class Identity and Versioning

A runtime class is identified by its binary name together with its defining class loader. Do not call `defineClass` a second time with the same name in the same loader; you will typically get `LinkageError`. To load a new version with the same binary name, use a **new loader** and switch registries/instances in a controlled manner. The parent loader should hold the shared service API so plugin classes can be cast to the SPI interface.

## 5. Compiling Multiple Source Units and Multiple Passes

The input to `JavaCompiler.getTask` can be multiple `JavaFileObject.Kind.SOURCE` instances. One task containing `demo.A` and `demo.B` can produce `demo.A`, `demo.A$Nested`, `demo.B`, plus auxiliary classes. The collector must capture all outputs from the entire task, not filter by the main source name.

For multiple consecutive compilation passes, if a later pass depends on bytecode existing only in memory from an earlier pass, overriding `getJavaFileForOutput` **is not enough**. The compiler needs to locate input classes: the file manager may have to implement `list`, `getJavaFileForInput`, `inferBinaryName`, and related APIs to provide an in-memory classpath/module path. The runtime `MemoryClassLoader` does not automatically make `JavaCompiler` see loaded classes.

With annotation processing, the compiler can also generate new sources and new class outputs. Do not assume the number of outputs is known in advance or limited to classes appearing explicitly in the initial source.

## 6. Packaging and Storing Bytecode

To export a bytecode map into a JAR, convert each binary name to a resource path: replace package `.` with `/`, **keep `$` intact**, and append `.class`. For example:

```text
demo.Outer        -> demo/Outer.class
demo.Outer$Inner  -> demo/Outer$Inner.class
demo.Outer$1      -> demo/Outer$1.class
```

Example snippet inside a method having `classes: Map<String, byte[]>` and `jarPath: Path`:

```java
try (java.util.jar.JarOutputStream output =
        new java.util.jar.JarOutputStream(
                java.nio.file.Files.newOutputStream(jarPath))) {
    for (var entry : classes.entrySet()) {
        String path = entry.getKey().replace('.', '/') + ".class";
        output.putNextEntry(new java.util.jar.JarEntry(path));
        output.write(entry.getValue());
        output.closeEntry();
    }
}
```

If using SPI, the JAR also needs `META-INF/services/<service FQCN>` or proper JPMS module metadata matching the architecture. Storing only `.class` files is insufficient if the plugin needs resource files, a manifest, or descriptors.

## 7. Common Errors and How to Diagnose Them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `ClassNotFoundException` for `demo.Outer.Inner` | Used canonical name | Call `loadClass("demo.Outer$Inner")` |
| `NoClassDefFoundError` for `Outer$1` | Collector did not store anonymous output | Store every output callback |
| `NoClassDefFoundError: wrong name` | Map key differs from binary name in bytecode | Use the exact `className` from the compiler |
| `LinkageError` duplicate definition | Redefining the same class in the same loader | Use a new loader when rebuilding |
| `ClassCastException` to SPI | Plugin loader defined a duplicate API | Share the API via the parent |
| Next compiler pass cannot see old classes | Output manager only, no input support | Add in-memory input lookup |
| Failed yet partial `.class` files exist | Published map before checking `call()` | Publish only when compilation succeeds |
| Memory grows after repeated compilations | Host retains references to old loaders | Manage lifecycles and references |

## 8. Implementation Checklist

- [ ] Verify the system compiler is available; use a suitable JDK.
- [ ] Source URI matches the top-level binary name and `.java` extension.
- [ ] Record every `getJavaFileForOutput` call by `className`, each with its own stream.
- [ ] Do not guess inner/local/anonymous class names.
- [ ] Snapshot outputs only after compilation succeeds.
- [ ] Load all outputs with a consistent loader; keep shared SPIs in the parent.
- [ ] Create a new loader for a new class version when names overlap.
- [ ] If compiling across multiple passes with in-memory dependencies, support class input lookup.
- [ ] When exporting a JAR, preserve `$` in entry names and include resources/SPI metadata.
- [ ] Write tests for outer, nested, inner, anonymous classes, and error diagnostics.
- [ ] Do not treat in-memory compilation as a sandbox: code runs with host JVM privileges.

**Conclusion:** a Java compilation unit can produce multiple `.class` files, so the output unit is not the source file but **a class with a specific binary name**. Storing all bytes from the compiler under the exact names, feeding them into an appropriate class loader, and carefully managing versioning/diagnostics helps avoid missing classes, mismatched names, or definition conflicts.