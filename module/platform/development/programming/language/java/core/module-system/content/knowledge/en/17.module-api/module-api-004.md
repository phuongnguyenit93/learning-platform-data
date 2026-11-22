# ModuleReference, ModuleReader, and resources

In the Java Module System, the \`java.lang.module\` package provides APIs to locate, describe, and read the contents of a module. Two important types are **ModuleReference** and **ModuleReader**:

- **ModuleReference** represents a reference to a module: it holds the ModuleDescriptor and knows how to open the module's contents.
- **ModuleReader** provides a way to read resources inside the module without loading classes into the JVM.

These APIs are useful when building module inspection tools, analyzing the module path, packaging applications, locating resources, or working with the module resolution process.

## 1. Where the types fit in the Module API

A module can be viewed from three perspectives:

| Type | Role |
|---|---|
| ModuleDescriptor | Describes module metadata: name, version, requires, exports, opens, uses, provides, and packages |
| ModuleReference | Pairs a descriptor with a reference to the module's contents |
| ModuleReader | Reads actual resources from the module's contents |

Typical workflow:

~~~text
ModuleFinder
    |
    | find("module.name")
    v
ModuleReference
    |-- descriptor()  -> ModuleDescriptor
    |-- location()    -> URI or null
    |
    | open()
    v
ModuleReader
    |-- find(name)    -> Optional<URI>
    |-- open(name)    -> Optional<InputStream>
    |-- read(name)    -> Optional<ByteBuffer>
    |-- list()        -> Stream<String>
    |-- release(...)
    |-- close()
~~~

ModuleReference and ModuleReader are not the Module object in the java.lang package. Module is a module already defined at runtime; ModuleReference is a reference used during module lookup and resolution; ModuleReader is an interface for reading the module's contents.

## 2. ModuleReference

ModuleReference is an abstract class in java.lang.module. An instance represents a module that can be found by ModuleFinder.

Key methods:

| Method | Meaning |
|---|---|
| descriptor() | Returns the module's ModuleDescriptor |
| location() | Returns the URI identifying the location of the module's contents, or null if the location is unknown |
| open() | Opens a ModuleReader to read the module's contents; may throw IOException |

ModuleReference does not load classes itself. It provides metadata and an entry point for tools to read module contents.

Example obtaining a reference to the java.base system module:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

ModuleReference reference = ModuleFinder.ofSystem()
        .find("java.base")
        .orElseThrow(() ->
                new IllegalStateException("java.base not found"));

System.out.println(reference.descriptor().name());
System.out.println(reference.location());
~~~

ModuleFinder.ofSystem() finds modules belonging to the current runtime image. For modules located on the module path, you can create a finder using ModuleFinder.of(Path...). Once you have a ModuleReference, you can inspect the descriptor or open a ModuleReader.

Do not assume location() always returns a URI that can be converted directly to a Path. The location may not be provided or may use a URI scheme that the application does not handle as a regular file. If the goal is to read contents, use ModuleReader.

## 3. ModuleReader and how to access resources

ModuleReader is an interface extending Closeable. It provides multiple ways to access the same resource, depending on whether you need a URI, InputStream, or ByteBuffer.

A resource name is a relative name inside the module, using forward slashes to separate packages/directories. For example:

- java/lang/Object.class
- com/example/config.properties
- META-INF/services/com.example.PaymentProvider

Do not add a leading slash to the resource name. Resource names are not absolute paths on the filesystem.

### find(name): finding a resource's URI

find(name) returns Optional<URI>. If the resource is found, the URI describes the resource's location as provided by the ModuleReader implementation.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.net.URI;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<URI> result = reader.find("java/lang/Object.class");

    result.ifPresent(uri ->
            System.out.println("Resource URI: " + uri));
}
~~~

find() is suitable when you need to know whether a resource exists and obtain its URI. This URI is not necessarily a file URI. Do not assume you can use Paths.get(uri) or File to read every returned URI.

### open(name): reading a resource with InputStream

open(name) returns Optional<InputStream>. This is a convenient choice when you need to read data sequentially, such as properties files, JSON, or binary content.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<InputStream> result =
            reader.open("java/lang/Object.class");

    if (result.isPresent()) {
        try (InputStream input = result.get()) {
            byte[] bytes = input.readAllBytes();
            System.out.println("Byte count: " + bytes.length);
        }
    } else {
        System.out.println("Resource not found");
    }
}
~~~

There are two resources to close in the example: ModuleReader and InputStream. Each object is placed in a try-with-resources block to ensure it is closed even if an exception occurs.

### read(name): reading a resource with ByteBuffer

read(name) returns Optional<ByteBuffer>. This approach can be suitable for tools processing binary data or APIs working directly with NIO.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.nio.ByteBuffer;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<ByteBuffer> result =
            reader.read("java/lang/Object.class");

    if (result.isPresent()) {
        ByteBuffer buffer = result.get();

        try {
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            System.out.println("Byte count: " + bytes.length);
        } finally {
            reader.release(buffer);
        }
    }
}
~~~

When read() returns a buffer, call release() on the exact ByteBuffer returned after you are done using it. Specific deallocation depends on the implementation; for some implementations, the buffer may use off-heap memory. Do not replace the original buffer with a duplicate or slice when calling release().

### list(): listing resource names

list() returns a Stream<String> containing the names of resources in the module. This Stream must be closed after use.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.util.stream.Stream;

try (ModuleReader reader = reference.open()) {
    try (Stream<String> names = reader.list()) {
        names.filter(name -> name.endsWith(".properties"))
             .forEach(System.out::println);
    }
}
~~~

Do not assume list() only returns files created by the application itself. Module contents can include classes, metadata, and other resources. Filter by name or extension appropriate to your goal.

## 4. Which reading method to choose?

| Need | API to use |
|---|---|
| Check whether a resource exists and get its URI | find(name) |
| Read sequentially using a stream API | open(name) |
| Process data using NIO ByteBuffer | read(name), then release(buffer) |
| List resources in a module | list() |

If you only need to read content, open() is usually easier to use because InputStream can be closed with try-with-resources. read() is useful when the rest of the program already works with ByteBuffer and can manage the buffer lifecycle properly.

## 5. Lifecycle and error management

ModuleReader represents a session for accessing module contents. After opening a reader, close it when finished:

~~~java
try (ModuleReader reader = reference.open()) {
    // find, open, read, or list resources here
}
~~~

Points to remember:

1. reference.open() and read operations can throw IOException. Handle or declare the exception appropriately.
2. find(), open(), and read() use Optional to represent the case where a resource is not found. Check the Optional before retrieving the value.
3. InputStream obtained from open() must be closed separately.
4. Stream obtained from list() must be closed after traversal.
5. ByteBuffer obtained from read() must be returned to the reader via release() when no longer used.
6. Do not continue using the reader after the reader has been closed.

Using try-with-resources for the reader, stream, and input stream helps prevent resource leaks. For ByteBuffer, use finally to ensure release() is still called if data processing encounters an error.

## 6. Relationship with ModuleFinder and the resolution process

ModuleFinder is responsible for locating ModuleReferences. It can locate modules in the runtime image or from supplied module path locations.

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Set<ModuleReference> references = finder.findAll();

for (ModuleReference reference : references) {
    System.out.println(reference.descriptor().name());
}
~~~

In the example, the mods directory is used as input to ModuleFinder. Each result is a ModuleReference. From a reference, the program can read the descriptor or open a ModuleReader to inspect the contents.

During resolution, Java uses ModuleReferences and ModuleDescriptors to determine which modules need to be present, the requires relationships, and how to construct a Configuration. ModuleReader provides access to module contents for operations that need to read resources. Reading resources with ModuleReader does not mean the module has been defined in a ModuleLayer or that classes of the module have been loaded.

## 7. Distinguishing from ClassLoader and Module

| Component | Responsibility |
|---|---|
| ModuleReference | Reference to a found module, with descriptor and ability to open a reader |
| ModuleReader | Reads resources from module contents |
| Module | Represents a module at runtime |
| ClassLoader | Loads classes and provides resource lookup according to class loader rules |

ModuleReader is a low-level API for working with module contents. If an application only needs to load resources at runtime using normal mechanisms, the resource APIs of ClassLoader or Module may be more appropriate. If you are building tools for analyzing, packaging, or inspecting modules before loading, ModuleReference and ModuleReader are the appropriate APIs.

## 8. Common mistakes

- **Assuming location() is always non-null:** a module's location may be unknown. Use ModuleReader to access contents.
- **Treating URIs as file paths:** a URI may use a scheme other than file. Do not convert URIs to Path by default.
- **Forgetting to close the reader or InputStream:** use try-with-resources.
- **Forgetting to close the Stream from list():** close the stream after traversal.
- **Forgetting to release the ByteBuffer:** call reader.release() with the original buffer after processing.
- **Using resource names like absolute paths:** pass relative names separated by forward slashes with no leading /.
- **Confusing ModuleReference with Module:** reference serves finding and reading modules; Module represents a module already present at runtime.

## 9. Key takeaways

ModuleReference answers the question: “How is this module described and where can its contents be opened?”. ModuleReader answers the question: “Which resources can be found, listed, and read inside the module?”. Combining ModuleFinder, ModuleReference, and ModuleReader allows Java tools to inspect module metadata and contents without loading the module's classes into the application.
