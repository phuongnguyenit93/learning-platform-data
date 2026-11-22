# ModuleFinder and custom module sources

## Objectives

After this lesson, you can:

- Explain the role of **ModuleFinder** in the Java Platform Module System (JPMS).
- Distinguish **ModuleFinder**, **ModuleReference**, and **ModuleReader**.
- Find modules from the module path and runtime image using built-in finders.
- Combine multiple module sources using **ModuleFinder.compose**.
- Create a custom in-memory module source by implementing finder, reference, and reader.
- Feed discovered modules into resolution and create a **ModuleLayer**.

## 1. Why is ModuleFinder needed?

In JPMS, a module is not just a directory containing classes. It has a name, a descriptor, and declared sets of packages, dependencies, and APIs. When the JVM or an application creates a module layer via API, it needs to know:

1. Which modules can be found?
2. What does each module's descriptor describe?
3. Where are the module's bytecode and resources located, and how can they be read?

**ModuleFinder** answers the first question and supplies references to modules. Two further abstractions complete the path to the contents:

- **ModuleReference** represents a discovered module. It holds the **ModuleDescriptor** and an optional module location.
- **ModuleReader** opens and reads entries inside the module, such as .class files and resources.

General flow:

~~~text
Configuration.resolve(...)
          |
          v
     ModuleFinder
       find(name)
       findAll()
          |
          v
    ModuleReference
    descriptor()
    location()
    open()
          |
          v
      ModuleReader
   find / open / read / list
          |
          v
  class bytes and resources
~~~

**ModuleFinder does not compile .java files, does not create class loaders by itself, and does not create module layers.** It is an information source for the resolver to locate modules. Resolving dependencies and defining modules belong to **Configuration** and **ModuleLayer**.

## 2. Three abstractions to distinguish

### 2.1. ModuleFinder — finding modules

**ModuleFinder** is an interface with two main operations:

~~~java
Optional<ModuleReference> find(String name);
Set<ModuleReference> findAll();
~~~

- **find(name)** returns a reference to the module with the corresponding name, or **Optional.empty()** if this source does not contain that module.
- **findAll()** returns the modules provided by the finder.

A finder can represent a module path, runtime image, private repository, memory, database, or another custom source.

### 2.2. ModuleReference — describing a specific module

**ModuleReference** is an abstract class representing a discovered module. It provides:

- **descriptor()** — the **ModuleDescriptor** describing the module name, dependencies, packages, exports, opens, services, and related attributes.
- **location()** — the module location as an optional **URI**. An in-memory or special module source might not have a conventional file location.
- **open()** — opens a **ModuleReader** to access the module's contents.

A ModuleReference is the bridge between a module's metadata and the mechanism for reading that source's contents.

### 2.3. ModuleReader — reading module contents

**ModuleReader** is an interface used to access entries in a module:

| API | Meaning |
|---|---|
| **find(name)** | Finds the URI of an entry if it can be located |
| **open(name)** | Opens an entry as an InputStream |
| **read(name)** | Reads an entry as a ByteBuffer |
| **release(buffer)** | Returns a buffer allocated by read when the implementation needs to free resources |
| **list()** | Lists entry names |
| **close()** | Closes the reader and frees resources |

An entry name is a relative path inside the module, using /, for example **com/acme/app/Main.class** or **config/default.yml**. Do not add a leading /.

**open** and **read** return Optional.empty() when the entry does not exist. Once the reader is closed, the implementation should not continue allowing data reads.

## 3. Using built-in ModuleFinders

In most applications, you do not need to implement a finder yourself. The JDK already provides common factory methods.

### 3.1. Finding modules on the module path

**ModuleFinder.of(Path...)** creates a finder from one or more paths containing modules, such as modular JARs or exploded modules.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

        ModuleReference reference = finder
                .find("com.acme.orders")
                .orElseThrow(() ->
                        new IllegalArgumentException("Module not found"));

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Name: " + descriptor.name());
        System.out.println("Location: " + reference.location().orElse(null));

        descriptor.requires().forEach(requirement ->
                System.out.println("Requires: " + requirement.name()));
    }
}
~~~

The example above only reads metadata. It has not resolved dependencies and has not defined the module in a layer.

### 3.2. Finding modules in the runtime image

**ModuleFinder.ofSystem()** creates a finder for modules belonging to the current JDK runtime image.

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();

systemFinder.find("java.base").ifPresent(reference -> {
    System.out.println(reference.descriptor().name());
});
~~~

This is the way to query system modules via API, instead of guessing the contents of the running JDK.

### 3.3. Combining multiple module sources

**ModuleFinder.compose(...)** combines multiple finders into one finder.

~~~java
ModuleFinder finder = ModuleFinder.compose(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(Path.of("build/modules")),
        ModuleFinder.ofSystem()
);

finder.find("com.acme.orders").ifPresent(reference ->
        System.out.println(reference.descriptor()));
~~~

Finder order matters when the same module name appears in multiple sources: the finder searched earlier can supply the chosen reference for that name. Therefore, organize module sources deliberately and avoid unintended competition between multiple versions of the same name.

Use **compose** when an application has multiple module storage locations but still wants to pass them to the resolver through a single interface.

## 4. How does a custom module source work?

A custom module source is a source of module contents managed by the application itself. For example:

- Modules downloaded from a database or object storage.
- Modules held in memory after decryption.
- Modules supplied by a private plugin repository.
- Modules stored in an archive format that default finders do not support.
- Modules dynamically generated in a test environment.

To integrate this source into JPMS, three parts must be wired together:

1. **Custom ModuleFinder**: maps module names to references.
2. **ModuleReference**: supplies the descriptor and creates the reader.
3. **Custom ModuleReader**: reads bytecode/resources from the actual source.

A custom source must still supply data conforming to the JPMS contract. In particular, the descriptor must accurately reflect the module name, packages, dependencies, and access permissions. A custom module source cannot bypass the module system's resolution rules or encapsulation rules.

## 5. Example: ModuleFinder reading a module from memory

The example below creates a simple in-memory module source. Module contents are stored in a **Map<String, byte[]>**. The finder provides a module named **com.example.memory** and the reader can read the resource **com/example/memory/banner.txt**.

The example focuses on the mechanism of finding and reading modules. This is not yet a complete production module repository; version management, source verification, bytecode loading, and caching must be added according to the real system.

### 5.1. Implementing MemoryModuleFinder

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Stream;

public final class MemoryModuleFinder implements ModuleFinder {

    private final Map<String, ModuleReference> references;

    public MemoryModuleFinder(
            String moduleName,
            Map<String, byte[]> sourceEntries
    ) {
        Objects.requireNonNull(moduleName, "moduleName");
        Objects.requireNonNull(sourceEntries, "sourceEntries");

        Map<String, byte[]> snapshot = new HashMap<>();

        sourceEntries.forEach((name, bytes) -> {
            String validName = validateEntryName(name);
            byte[] copy = Objects.requireNonNull(bytes, "entry bytes").clone();
            snapshot.put(validName, copy);
        });

        Map<String, byte[]> entries = Map.copyOf(snapshot);

        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule(moduleName)
                .packages(Set.of("com.example.memory"))
                .build();

        ModuleReference reference = new ModuleReference(
                descriptor,
                URI.create("memory:///" + moduleName + "/")
        ) {
            @Override
            public ModuleReader open() {
                return new MemoryModuleReader(moduleName, entries);
            }
        };

        this.references = Map.of(moduleName, reference);
    }

    @Override
    public Optional<ModuleReference> find(String name) {
        return Optional.ofNullable(references.get(name));
    }

    @Override
    public Set<ModuleReference> findAll() {
        return Set.copyOf(references.values());
    }

    private static String validateEntryName(String name) {
        Objects.requireNonNull(name, "entry name");

        String[] segments = name.split("/", -1);
        boolean invalidSegment = Arrays.stream(segments)
                .anyMatch(segment ->
                        segment.isEmpty()
                                || segment.equals(".")
                                || segment.equals(".."));

        if (name.isBlank()
                || name.startsWith("/")
                || name.indexOf((char) 92) >= 0
                || invalidSegment) {
            throw new IllegalArgumentException(
                    "Invalid module entry name: " + name
            );
        }

        return name;
    }

    private static final class MemoryModuleReader implements ModuleReader {

        private final String moduleName;
        private final Map<String, byte[]> entries;
        private boolean closed;

        private MemoryModuleReader(
                String moduleName,
                Map<String, byte[]> entries
        ) {
            this.moduleName = moduleName;
            this.entries = entries;
        }

        private void ensureOpen() throws IOException {
            if (closed) {
                throw new IOException("ModuleReader is closed");
            }
        }

        @Override
        public Optional<URI> find(String name) throws IOException {
            ensureOpen();

            if (!entries.containsKey(name)) {
                return Optional.empty();
            }

            return Optional.of(
                    URI.create("memory:///" + moduleName + "/" + name)
            );
        }

        @Override
        public Optional<InputStream> open(String name) throws IOException {
            ensureOpen();

            byte[] bytes = entries.get(name);

            if (bytes == null) {
                return Optional.empty();
            }

            return Optional.of(new ByteArrayInputStream(bytes));
        }

        @Override
        public Optional<ByteBuffer> read(String name) throws IOException {
            ensureOpen();

            byte[] bytes = entries.get(name);

            if (bytes == null) {
                return Optional.empty();
            }

            return Optional.of(
                    ByteBuffer.wrap(bytes).asReadOnlyBuffer()
            );
        }

        @Override
        public void release(ByteBuffer buffer) {
            // ByteBuffer.wrap creates a heap buffer; no native memory needs to be freed.
        }

        @Override
        public Stream<String> list() throws IOException {
            ensureOpen();

            return entries.keySet().stream().sorted();
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
~~~

### 5.2. Creating the finder and reading resources

~~~java
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public class MemoryModuleDemo {

    public static void main(String[] args) throws Exception {
        String resourceName = "com/example/memory/banner.txt";

        Map<String, byte[]> content = Map.of(
                resourceName,
                "Loaded from memory".getBytes(StandardCharsets.UTF_8)
        );

        MemoryModuleFinder finder = new MemoryModuleFinder(
                "com.example.memory",
                content
        );

        ModuleReference reference = finder
                .find("com.example.memory")
                .orElseThrow();

        System.out.println(
                "Module: " + reference.descriptor().name()
        );

        try (ModuleReader reader = reference.open()) {
            System.out.println(
                    "Resource URI: "
                            + reader.find(resourceName).orElseThrow()
            );

            try (InputStream input = reader
                    .open(resourceName)
                    .orElseThrow()) {

                String value = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );

                System.out.println(value);
            }

            System.out.println("Entries:");

            try (var names = reader.list()) {
                names.forEach(System.out::println);
            }
        }
    }
}
~~~

Sample output:

~~~text
Module: com.example.memory
Resource URI: memory:///com.example.memory/com/example/memory/banner.txt
Loaded from memory
Entries:
com/example/memory/banner.txt
~~~

Here, **ModuleFinder** locates the module by name. **ModuleReference** holds the descriptor and creates the reader. The reader returns a URI, stream, or buffer depending on the API called. No JAR file needs to be created on disk.

The URI using the **memory** scheme in the example is an identifier by convention of the custom source. It does not automatically create a URL handler so the application can call URI.toURL().openStream(). When you need to read contents, use the **ModuleReader** contract. A production implementation must clearly specify how URIs are encoded for all valid entry names.

## 6. Passing a custom finder into the resolution process

Having a finder and reference only means the application can describe the module source. To make the module participate in a module layer, you must resolve a configuration and define the layer.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ResolveMemoryModule {

    public static void main(String[] args) {
        String resourceName = "com/example/memory/banner.txt";

        ModuleFinder finder = new MemoryModuleFinder(
                "com.example.memory",
                Map.of(
                        resourceName,
                        "Loaded from memory".getBytes(StandardCharsets.UTF_8)
                )
        );

        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.memory")
                );

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration,
                        List.of(ModuleLayer.boot()),
                        ClassLoader.getSystemClassLoader()
                );

        ModuleLayer layer = controller.layer();

        System.out.println(
                layer.findModule("com.example.memory").isPresent()
        );
    }
}
~~~

The steps have distinct meanings:

1. **Configuration.resolve** locates the root module and required dependencies from the provided finders, while verifying the consistency of the module graph.
2. **ModuleLayer.defineModulesWithOneLoader** defines the modules in the configuration on a shared class loader for the new layer.
3. **controller.layer()** obtains the newly defined layer.

If the module has dependencies, the corresponding finder must supply those dependencies or they must exist in a parent configuration. Otherwise, resolution will fail. A custom finder does not eliminate the requirement to declare **requires** in the descriptor.

This example defines a resource-only module. When you want to load classes from a custom source, the entry map must contain the corresponding .class bytecode and the descriptor must declare the right packages. The layer's class loader will use the module content to locate classes. ModuleReader does not compile classes from source code.

In real applications, only define a layer when there is a clear reason to isolate a group of modules, such as plugins or separate module versions. For typical applications, the module path and boot layer usually suffice.

## 7. The descriptor must match the source contents

The custom source is responsible for providing an accurate descriptor. A descriptor can be constructed using **ModuleDescriptor** builders:

~~~java
ModuleDescriptor descriptor = ModuleDescriptor
        .newModule("com.acme.reporting")
        .requires("java.logging")
        .exports("com.acme.reporting.api")
        .opens("com.acme.reporting.internal")
        .packages(Set.of(
                "com.acme.reporting.api",
                "com.acme.reporting.internal"
        ))
        .build();
~~~

Meaning of the declarations:

- **requires** declares module dependencies.
- **exports** allows other modules to access public types in exported packages under JPMS rules.
- **opens** allows reflective access to packages under package-opening rules.
- **packages** describes the set of packages contained in the module; a custom finder must provide this set matching the actual contents.

**exports** and **opens** have different purposes. Export is the standard compile/runtime API access contract; open serves reflection. Do not use open just because you want a module to be discoverable or readable for resources.

When constructing descriptors dynamically, also describe dependencies, service declarations, main class, and version if the module actually uses those features. The resolver relies on this metadata to validate the module graph.

## 8. Things to watch when writing production finders/readers

### Source consistency

- Every module name must map to the corresponding descriptor.
- **find(name)** and **findAll()** must agree: listed modules must be findable by name.
- Do not let the same module name point to different contents within the same resolution pass.
- Use an immutable snapshot or fixed version throughout the resolve/load lifecycle.

### Entry paths

- Normalize entry names to relative form using /.
- Reject **..**, absolute paths, and forms of path traversal.
- Do not let entry names produce invalid URIs.
- If the source is an archive or remote storage, enforce limits on entry size and count.

### ByteBuffer and resources

- If **read** allocates native/direct memory, the implementation must free it properly in **release**.
- If using a heap buffer as in the example, **release** may not need any deallocation action.
- Streams returned from **open** are the caller's responsibility to close.
- **close** must prevent subsequent read operations and release any underlying source handles/caches/resources.

### Synchronization and lifecycle

A **ModuleReader** is typically used within a read operation with a clear lifecycle. If multiple threads can open readers or read the same module, define a thread-safety policy for the implementation. Do not share a state flag or mutable map without proper synchronization.

### Trust and integrity

If a module comes from a remote repository or database, verify identity/version and bytecode integrity before placing it into a layer. A finder only returns module references; it does not automatically verify signatures, plugin installation permissions, or content provenance.

## 9. Common errors and troubleshooting direction

| Symptom | Cause to check |
|---|---|
| **find(name)** returns empty | Finder does not have a module with that name, or lookup name does not match descriptor |
| Resolve reports missing module | A dependency in **requires** is missing from the finder/parent configuration |
| Resolve fails due to conflict | Descriptor or dependency graph is inconsistent; check duplicate module names, split packages, and constraints |
| Cannot read resource | Wrong entry name, reader does not supply the entry, or reader is already closed |
| Reading resource via class loader fails | Check package encapsulation, **opens**, and resource access method |
| Class is not loaded | Check whether bytecode is in the module source, package mapping, descriptor, and the layer's class loader |
| Reader errors after closing | Caller retained the reader past the end of its lifecycle; open a new reader for new operations |

When debugging, check step by step:

1. Does **finder.find(moduleName)** return a reference?
2. Does **reference.descriptor()** have the right name and dependencies?
3. Does **reference.open().list()** list the needed entry?
4. Can **reader.open(entryName)** read the entry?
5. Does **Configuration.resolve** complete?
6. Does the layer contain the module and provide the corresponding loader?

## 10. Choosing the right approach

| Need | Solution |
|---|---|
| Modules live in modular JARs or exploded modules | **ModuleFinder.of(paths)** |
| Need access to JDK modules | **ModuleFinder.ofSystem()** |
| Modules live in multiple standard directories/repositories | **ModuleFinder.compose(...)** |
| Modules come from memory, database, custom archive, or remote store | Implement **ModuleFinder**, **ModuleReference**, and **ModuleReader** |
| Need to isolate plugins or module groups at runtime | Combine finder with **Configuration.resolve** and **ModuleLayer** |

Only implement a custom source when the data source genuinely differs from the standard module path. A custom finder/reader must handle descriptors, bytecode, resources, URIs, lifecycles, and I/O errors; this is a technical boundary that needs to be managed as part of the module infrastructure.

## Conclusion

**ModuleFinder** answers the question “which modules exist in this source?”. **ModuleReference** describes the module and opens its contents. **ModuleReader** supplies bytecode and resources to the module system. When these three abstractions are implemented according to contract, JPMS can resolve modules from a custom source just as it resolves modules from the standard module path.

Remember to distinguish the three stages: **find modules → resolve module graph → define module layer**. Finding a module does not mean dependencies are resolved or the module is ready to run.
