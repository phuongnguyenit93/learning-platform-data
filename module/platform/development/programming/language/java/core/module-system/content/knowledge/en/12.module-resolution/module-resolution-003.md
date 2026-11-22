# ModuleReference and ModuleReader in the Java Platform Module System (JPMS)

## 1. Objectives and Position in Module Resolution

In JPMS (Java 9 and later), a module is more than just a name and directives in `module-info.java`. The system also needs to **locate the module implementation**, **read its descriptor**, **resolve dependency relationships**, and sometimes **directly access contents** inside the module. Two APIs in the `java.lang.module` package serve this purpose:

- `ModuleReference`: represents an **observable/discoverable** module from a `ModuleFinder`, along with the module's descriptor and location information (if available).
- `ModuleReader`: an interface for reading the resources of the module represented by a `ModuleReference`; for example, listing resource names, opening an `InputStream`, or obtaining a `ByteBuffer` containing the contents.

These two types are very useful when writing module analysis tools, packaging tools, content validators, custom module loaders, or module discovery code. They do not replace the resolution step, do not create a `ModuleLayer` by themselves, and do not load classes into the JVM.

## 2. Position of the APIs in the Processing Flow

```text
Module path / system module set
             │
             ▼
       ModuleFinder
       find / findAll
             │
             ▼
      ModuleReference ── descriptor() ──► ModuleDescriptor
             │                              name, requires, exports, ...
             │
             ├── open() ──► ModuleReader ──► resources (.class, configs, ...)
             │
             ▼
Configuration.resolve(...) ──► Configuration ──► ResolvedModule
                                                  │
                                                  └── reference()
             │
             ▼
        ModuleLayer + ClassLoader (at the layer creation step)
```

Points to distinguish:

| Type | Primary Role | Not Equivalent To |
|---|---|---|
| `ModuleFinder` | Finds observable modules by name | The list of resolved modules |
| `ModuleReference` | References a module artifact and its descriptor | `java.lang.Module` belonging to a layer |
| `ModuleDescriptor` | Describes declarations: name, `requires`, `exports`, `opens`, `uses`, `provides`, version... | The file contents of the module |
| `Configuration` / `ResolvedModule` | Result of resolving modules and readability relationships | ClassLoader or already-loaded bytecode |
| `ModuleReader` | Accesses resources inside a module | `ClassLoader`, `Class.forName`, or access permissions via `exports` |
| `java.lang.Module` | Runtime module object belonging to a `ModuleLayer` | `ModuleReference` from a finder |

A module found by `ModuleFinder` **is not necessarily selected** into the current `Configuration`. Conversely, from a `ResolvedModule` in a configuration, you can retrieve its `ModuleReference` via `reference()`.

## 3. Understanding and Using ModuleReference

`ModuleReference` is an abstract class in `java.lang.module`. Common public operations:

| Method | Result and Interpretation |
|---|---|
| `descriptor()` | Returns `ModuleDescriptor`, providing the module's name and declared characteristics |
| `location()` | Returns `Optional<URI>` indicating the module's location if published by the provider |
| `open()` | Opens a `ModuleReader` to access contents; may throw `IOException` |

### 3.1. Obtaining a Reference via ModuleFinder

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class FindSystemModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.ofSystem();

        ModuleReference ref = finder.find("java.base")
                .orElseThrow(() -> new IllegalArgumentException(
                        "Module java.base not found"));

        System.out.println("Name: " + ref.descriptor().name());
        System.out.println("Requires: " + ref.descriptor().requires());
        System.out.println("URI: " + ref.location()
                .map(Object::toString)
                .orElse("(no URI)"));
    }
}
```

`ModuleFinder.ofSystem()` accesses the system module set in the runtime image. To locate modules from one or more paths on the module path, use:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
ModuleReference ref = finder.find("com.example.report")
        .orElseThrow(() -> new IllegalArgumentException(
                "com.example.report not found on module path"));

System.out.println(ref.descriptor());
```

The second example assumes the `mods` directory contains the corresponding module and that it is compiled/packaged in the proper format. Finding a reference does not mean the module has been resolved or is ready for `Class.forName`.

### 3.2. A Module's Location Is Not Necessarily a File Path

`location()` returns `Optional<URI>`, not `Path`. The URI may use the `jrt:` scheme for a module in the runtime image, `file:` for a location on the filesystem, or have no value. Therefore:

- Always handle the `Optional.empty()` case.
- Do not assume every URI can be converted with `Path.of(uri)` or read with `Files.readAllBytes(...)`.
- When you need to access contents in a storage-independent way, prefer `reference.open()` and then use `ModuleReader`.

## 4. Understanding and Using ModuleReader

`ModuleReader` is an interface extending `Closeable`. A reader reads resources of **one** specific module whose reference opened it.

| Method | Purpose |
|---|---|
| `find(String name)` | Returns `Optional<URI>` for the resource with the given relative name in the module, if found |
| `open(String name)` | Returns `Optional<InputStream>` to read the resource content |
| `read(String name)` | Returns `Optional<ByteBuffer>` containing the resource data |
| `release(ByteBuffer bb)` | Releases a buffer allocated by the reader via `read` when no longer needed |
| `list()` | Returns a `Stream<String>` containing resource names in the module |
| `close()` | Closes the reader and associated resources |

Resource names use `/` as the separator and are interpreted **relative to the module root**, for example:

- `java/lang/String.class`
- `com/example/report/ReportService.class`
- `config/app.properties`
- `META-INF/services/com.example.spi.Service`

A resource name is not a module name, not a binary class name, and not an absolute file path. For example, `java.lang.String` is a class name, whereas `java/lang/String.class` is the corresponding resource name.

### 4.1. Complete Example: Reading the java.base Module

The following program runs directly on JDK 11+ without needing a custom module. It obtains a reference from the boot layer's configuration, lists some resources, and tries two ways of reading a class file.

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.lang.module.ResolvedModule;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.Optional;
import java.util.stream.Stream;

public class ModuleContentDemo {
    public static void main(String[] args) throws IOException {
        ResolvedModule resolved = ModuleLayer.boot()
                .configuration()
                .findModule("java.base")
                .orElseThrow();

        ModuleReference ref = resolved.reference();

        System.out.println("Module: " + ref.descriptor().name());
        System.out.println("Location: " + ref.location()
                .map(URI::toString)
                .orElse("(no URI published)"));

        String resource = "java/lang/String.class";

        try (ModuleReader reader = ref.open()) {
            // List some resources in the java.lang package
            try (Stream<String> names = reader.list()) {
                names.filter(name -> name.startsWith("java/lang/"))
                        .limit(5)
                        .forEach(System.out::println);
            }

            // Option 1: read via InputStream, then close the stream
            try (InputStream input = reader.open(resource).orElseThrow()) {
                byte[] prefix = input.readNBytes(4);
                for (byte value : prefix) {
                    System.out.printf("%02X ", value & 0xFF);
                }
                System.out.println();
            }

            // Option 2: read via ByteBuffer, then properly release the buffer
            Optional<ByteBuffer> maybeBuffer = reader.read(resource);
            if (maybeBuffer.isPresent()) {
                ByteBuffer buffer = maybeBuffer.get();
                try {
                    System.out.println("Remaining bytes: "
                            + buffer.remaining());
                } finally {
                    reader.release(buffer);
                }
            }

            // Get the resource URI, if supported by the implementation
            System.out.println("Resource URI: "
                    + reader.find(resource)
                            .map(URI::toString)
                            .orElse("(not found)"));
        }
    }
}
```

Save as `ModuleContentDemo.java` and run:

```bash
javac ModuleContentDemo.java
java ModuleContentDemo
```

The first four bytes of a valid class file are `CA FE BA BE`. The order and number of printed resource names depend on the implementation and runtime contents; do not build logic that relies on the order of `list()`.

### 4.2. open() and read(): Which One to Choose?

- Use `open(name)` when you want to process data as a stream or pass it to an API that accepts `InputStream`. Always close the returned stream.
- Use `read(name)` when you need to operate on a `ByteBuffer`, such as reading headers or analyzing bytecode. Always call `release(buffer)` in a `finally` block for the buffer returned by the reader.
- Use `find(name)` when you only need the URI of a resource. The URI may be a provider-specific URI; do not assume the resource is an ordinary file.
- Use `list()` to discover resources. Because the stream may have associated resources, close the stream in a `try-with-resources` block; close the reader after finishing consuming the stream.

Calling `release` is not equivalent to `close`: it is for a buffer allocated by `read`, whereas `close` closes the entire reader. Do not use a buffer after it has been released.

## 5. Direct Connection to the Module Resolution Process

Suppose an application module `com.example.report` is already on the module path. We can go from the resolution process to a reference to that module:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder before = ModuleFinder.of(Path.of("mods"));
ModuleFinder after = ModuleFinder.of();

Configuration config = ModuleLayer.boot()
        .configuration()
        .resolve(before, after, Set.of("com.example.report"));

ModuleReference ref = config
        .findModule("com.example.report")
        .orElseThrow()
        .reference();

System.out.println("Resolved module: " + ref.descriptor().name());
```

In this example:

1. `before` provides observable modules from `mods`; `after` is an empty supplementary finder.
2. `resolve(...)` selects the modules needed to satisfy dependency relationships from the root `com.example.report` and creates a new `Configuration`.
3. `findModule(...)` on `Configuration` returns a `ResolvedModule`; `reference()` leads to the selected `ModuleReference`.
4. If you want to access files inside that module, call `ref.open()` to get a reader.
5. If you want to **execute classes** belonging to that module, you still need to build a `ModuleLayer` with an appropriate module definition/class loader mechanism. Having only `Configuration` or `ModuleReader` is not enough.

Distinguishing these two ways of looking up a module is important: `finder.find(name)` returns an observable module from a source; `configuration.findModule(name)` returns a module **selected in the resolution result**.

## 6. Practical Use Cases

### 6.1. Module Inventory Tools

Use `ModuleFinder.ofSystem().findAll()` or `ModuleFinder.of(path).findAll()` to list references and inspect `descriptor()`. You can aggregate module names, `requires`, `exports`, `opens`, and declared services without loading classes.

### 6.2. Packaging Verification Tools

Open a `ModuleReader` to check for expected configuration resources or classes:

```java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;

static boolean hasResource(ModuleReference ref, String name)
        throws IOException {
    try (ModuleReader reader = ref.open()) {
        return reader.find(name).isPresent();
    }
}
```

The return value only reflects whether the resource was found by the reader. It does not confirm that the class can be initialized, that the module is required by another module, or that a service provider can run successfully.

### 6.3. Bytecode Analysis

A tool can read `*.class` via `open` or `read` and pass the bytes to a class-file analysis library. `ModuleReader` supplies raw bytes; interpreting the constant pool, methods, and annotations is the responsibility of the analysis library.

### 6.4. Exploring Resources of an Unresolved Module

You can obtain a `ModuleReference` directly from a finder and open its reader even before adding the module to a configuration. This is suitable for module structure inspection tools. However, being able to read resources does not guarantee that all dependencies of that module are valid.

## 7. Resource Management, Errors, and Limitations

| Situation | How to Handle |
|---|---|
| `finder.find(name)` returns empty | Check the module name and module path; do not call `get()` without checking |
| `configuration.findModule(name)` returns empty | The module is not in the configuration under inspection; distinguish this from finder results |
| `reader.open/read/find(name)` returns empty | The resource does not exist under the given name or the provider cannot locate it |
| `ModuleReference.open()` or reader operations throw `IOException` | Handle the I/O exception according to context; close the reader with `try-with-resources` |
| `reader.list()` returns a stream | Consume it while the reader is still open; close the stream before closing the reader |
| `reader.read(name)` succeeds | Call `reader.release(buffer)` in a `finally` block when done |
| `location()` is empty or has a non-`file:` URI | Do not infer a real filesystem path; use the reader to access contents |
| Dependency resolution errors such as module not found or invalid graph | Handle during the resolution step; `ModuleReader` does not resolve dependencies |
| Module has unexported packages | Reading bytes with a reader does not grant Java code access to those packages |

In addition:

- A reader must not be shared or used concurrently arbitrarily; respect the contract and limitations of the specific provider.
- Do not hold onto an `InputStream` or `ByteBuffer` from a reader longer than its required lifetime.
- Do not assume the order of `list()`, OS-dependent path naming, or the ability to turn a URI into a `Path`.
- When working with externally supplied module paths, treat bytecode/resource data as untrusted input.
- Using `ModuleReader` to inspect contents does not bypass `requires`, `exports`, and `opens` rules when Java actually links classes or uses reflection.

## 8. Frequently Asked Questions

**How does ModuleReference differ from java.lang.Module?**

`ModuleReference` represents a module located by a finder and provides a way to read its contents. `java.lang.Module` represents a module at runtime, attached to a module layer. You cannot call `reference.open()` and treat that as having created a runtime module.

**Can you get a ModuleReference from a resolved module?**

Yes. Obtain the `ResolvedModule` from `Configuration.findModule(name)`, then call `reference()`. For example, with the boot layer: `ModuleLayer.boot().configuration().findModule("java.base").orElseThrow().reference()`.

**Does ModuleReader load classes like a ClassLoader?**

No. `open` and `read` provide resource data, which may be `.class` bytecode, but they do not perform class definition, linking, initialization, or cross-module access control.

**Why not use Files or JarFile to read a module?**

That approach can work for a specific packaging format. `ModuleReader` provides a uniform interface for modules in the runtime image and modules supplied by other providers, making tools less coupled to storage formats.

**When should you read ModuleDescriptor without opening a ModuleReader?**

When you only need metadata such as the name, required dependencies, exported/opened packages, and used/provided services. Only open a reader when you actually need the resource list or resource contents.

## 9. Key Takeaways

`ModuleFinder` **locates** modules; `ModuleReference` **represents** a found module instance and gives access to `ModuleDescriptor`; resolution produces a `Configuration` containing `ResolvedModule` entries; `ModuleReader` **reads the referenced resources**; and `ModuleLayer` and class loaders are the components that bring modules into the runtime environment. Distinguishing these roles helps you use JPMS at the right layer of responsibility and avoid confusing finding a module, resolving dependencies, reading bytecode, and executing classes.
