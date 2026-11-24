# Reading Resources with InputStream and the Limits of Resource.getFile in a JAR

A Spring Boot application often ships with non-Java resources: email templates, sample JSON files, SQL scripts, public certificates, images, fonts, PDF documents, CSV lookup tables, or seed data. When running from an IDE, resources in `src/main/resources` are usually copied to a directory on disk so you can read them with `File` or `Path`. However, once packaged into an **executable JAR**, resources can reside **inside an archive**, no longer existing as standalone files on the operating system's filesystem.

This is the root cause of a very common Spring Boot error:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json] cannot be resolved to absolute
file path because it does not reside in the file system
~~~

The error typically occurs when code calls `Resource.getFile()` or derives a `Path` from the URL of a resource inside a JAR. It does not mean the resource does not exist. It can still be read normally using `Resource.getInputStream()`.

**Core principle:** for resources packaged on the classpath, think in terms of **byte streams or the resource abstraction**, and do not assume a resource has a physical file path. Only use `File` or `Path` when the target genuinely resides on the filesystem, or when you intentionally copy the content to a temporary file for an API that strictly requires a file.

This lesson covers Spring's resource model, why `getFile()` works in an IDE but fails when running a JAR, how to read text/binary data with `InputStream`, integrating `@Value` and `ResourceLoader`, using resources outside the JAR, along with testing and troubleshooting examples.

## 1. What Are Resources in a Spring Boot Application?

A typical Maven or Gradle project has the structure:

~~~text
my-spring-boot-app/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       └── CatalogService.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── data/
│   │       │   ├── catalog.json
│   │       │   └── cities.csv
│   │       ├── templates/
│   │       │   └── welcome.txt
│   │       └── images/
│   │           └── logo.png
│   └── test/
│       └── resources/
│           └── data/
│               └── catalog-test.json
└── build.gradle
~~~

During the build process, the contents of `src/main/resources` are placed on the **runtime classpath**. Resources are accessed by paths **relative to the classpath root**, without the `src/main/resources` prefix.

Examples:

| File in project | Runtime resource location |
| --- | --- |
| `src/main/resources/data/catalog.json` | `classpath:data/catalog.json` |
| `src/main/resources/data/cities.csv` | `classpath:data/cities.csv` |
| `src/main/resources/templates/welcome.txt` | `classpath:templates/welcome.txt` |
| `src/main/resources/images/logo.png` | `classpath:images/logo.png` |

If you write `classpath:src/main/resources/data/catalog.json`, the application will typically fail to find the resource because `src/main/resources` is not part of the resource name on the classpath.

### 1.1. Classpath and filesystem are not the same

A filesystem path, for example:

~~~text
/opt/app/config/catalog.json
C:\applications\demo\catalog.json
~~~

points to a physical file on the operating system. Java can open it using `Path`, `Files.newInputStream(...)`, or `FileInputStream` if permissions allow.

By contrast, `classpath:data/catalog.json` is a **logical resource name** searched by a class loader. That resource may reside:

- In the project's build output directory when run from an IDE.
- Inside a standard JAR.
- Inside `BOOT-INF/classes` of a Spring Boot executable JAR.
- Inside a dependency JAR, possibly a nested JAR.
- In another class loader or packaging environment supported by Spring.

Therefore, a logical resource name does not equate to a stable physical path.

### 1.2. Reading resources differs from reading dynamic configuration

A default template bundled with the application fits well in `src/main/resources`. However, files that operators need to update after deployment should generally live outside the JAR and be referenced via a property or filesystem path.

If you edit a file inside `src/main/resources` on a development machine and redeploy the application, the new content is packaged into the artifact. In production, you should not assume you can modify resources directly inside an executable JAR like standalone files.

## 2. The Spring Resource Abstraction

Spring defines the `org.springframework.core.io.Resource` interface. It provides uniform access to various kinds of resources without forcing callers to know the concrete storage location.

Common methods:

| Method | Meaning | Things to note |
| --- | --- | --- |
| `getInputStream()` | Opens a stream to read the resource's bytes | Suitable for classpath/JAR; caller must close the stream |
| `exists()` | Checks whether the resource exists per implementation | Does not mean the resource is a physical file |
| `isReadable()` | Checks readability per resource implementation | Does not replace handling `IOException` |
| `getFilename()` | Gets the trailing filename of the resource | May be null, not a physical path |
| `getDescription()` | Describes the resource for logs/errors | Does not contain file content |
| `getURL()` | Returns a URL representing the resource location | URL may use the `jar:` protocol or another scheme |
| `getURI()` | Returns the resource's URI | Not guaranteed to be convertible to a `Path` |
| `getFile()` | Requests a `java.io.File` from the resource | May fail if the resource is inside an archive |
| `contentLength()` | Determines content length | Some implementations may need to read the stream to compute it |
| `lastModified()` | Gets modification time if available | Not every implementation provides meaningful information |

`Resource` is an abstraction over many different locations. Choose the API based on **what you need to do**: to read bytes, use a stream; to edit a file on disk, work with an actual filesystem path; do not force every Resource into a File.

### 2.1. Important implementations

| Implementation | Use case | `getFile()` |
| --- | --- | --- |
| `ClassPathResource` | Resource on the classpath | May succeed when in a directory; usually fails inside a JAR |
| `FileSystemResource` | File on the filesystem | Suitable for an actual `File`/`Path` |
| `PathResource` | Resource represented by an NIO `Path` | Suitable for a filesystem path |
| `UrlResource` | Resource with a URL like `file:`, `jar:`, `https:` | Depends on protocol; `jar:` is not automatically a file |
| `ByteArrayResource` | Byte content already in memory | Not a physical file |
| `InputStreamResource` | Wraps an already-opened stream | Usually single-read; do not treat as a re-openable resource |

A `ClassPathResource` may support `getFile()` when running from a directory, but that is **a capability of its current location**, not a contract guaranteeing classpath resources always have a physical file.

## 3. Why Does Resource.getFile() Often Fail in an Executable JAR?

Consider the following code:

~~~java
import java.io.File;
import java.io.IOException;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class CatalogLoader {

    public String loadCatalogPath() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");
        File file = resource.getFile(); // May fail in a packaged JAR.
        return file.getAbsolutePath();
    }
}
~~~

When running from an IDE, the resource may be copied to a directory like:

~~~text
build/resources/main/data/catalog.json
~~~

Here the class loader finds the resource under a URL with filesystem semantics, so `getFile()` can return a `File`.

When packaging the Spring Boot application into an executable JAR:

~~~text
app.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   └── data/
    │       └── catalog.json
    └── lib/
        ├── spring-boot-....jar
        └── some-library.jar
~~~

The `catalog.json` resource is **an entry inside an archive**. The operating system does not provide a standalone file at `/somewhere/catalog.json` merely because an entry exists in the JAR.

Spring Boot also uses a dedicated class loading mechanism for executable JARs and nested dependency JARs. The URL locating the entry may represent a location within an archive rather than a `file:` URL pointing to a regular file.

~~~mermaid
flowchart TD
    A["ClassPathResource: data/catalog.json"] --> B{"Runtime location"}
    B -->|IDE / exploded classes| C["Directory on filesystem"]
    B -->|Executable JAR| D["Entry in BOOT-INF/classes"]
    B -->|Dependency JAR| E["Entry in a library JAR"]
    C --> F["getFile() may succeed"]
    D --> G["getFile() has no physical file"]
    E --> G
    C --> H["getInputStream()"]
    D --> H
    E --> H
    H --> I["Read bytes via stream"]
~~~

Thus, the very same line of code can run smoothly in the IDE and then break when deployed via `java -jar app.jar`.

### 3.1. Resource existing does not mean getFile() will succeed

Example:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

boolean exists = resource.exists(); // Can be true in an executable JAR.

// Do not infer:
File file = resource.getFile();      // Can still throw IOException.
~~~

`exists()` answers "was the resource found?". `getFile()` answers "can this resource be represented as a filesystem file?". These are two different questions.

### 3.2. How does the error usually manifest?

You may see an exception such as:

~~~text
java.io.FileNotFoundException:
class path resource [data/catalog.json] cannot be resolved to absolute
file path because it does not reside in the file system
~~~

Sometimes code does not call `getFile()` directly but fails at:

~~~java
Path path = resource.getFile().toPath();

String content = Files.readString(resource.getFile().toPath());

FileInputStream stream = new FileInputStream(resource.getFile());
~~~

The fix is not to swap `getFile().toPath()` for some URI-conversion variant; check whether the final operation truly requires a physical file or only wants to read the content.

## 4. The Right Way: Read Resources with Resource.getInputStream()

For packaged resources, `Resource.getInputStream()` is the standard, reliable API for reading content.

Simple example:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class CatalogReader {

    public String readCatalog() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            byte[] bytes = input.readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }
}
~~~

The code needs no filesystem path. The stream is opened by the class loader and `Resource` implementation from the actual location, whether directory or JAR entry.

### 4.1. Why is try-with-resources important?

`getInputStream()` returns a stream that must be closed. `try-with-resources` guarantees `close()` is invoked even if reading encounters an error:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Read content.
}
~~~

Omitting stream closure can hold onto native resources, file descriptors, connections, or handles depending on the implementation. Under repeated requests, stream leaks can lead to resource exhaustion and hard-to-diagnose failures.

Do not hold an opened `InputStream` in a singleton field across the application's lifetime without a clear reason and lifecycle management. Normally, hold the `Resource` and open a stream per operation.

### 4.2. Example with an injected Resource

Instead of instantiating `ClassPathResource` inside each method, you can inject the resource with Spring:

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTemplateService {

    private final Resource template;

    public WelcomeTemplateService(
            @Value("classpath:templates/welcome.txt") Resource template) {
        this.template = template;
    }

    public String loadTemplate() throws IOException {
        try (InputStream input = template.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

File:

~~~text
src/main/resources/templates/welcome.txt
~~~

Example content:

~~~text
Hello, this is a Spring Boot application!
~~~

`@Value` on the constructor parameter tells Spring the resource location. The service holds only the `Resource`, not an opened stream.

When `loadTemplate()` is called, the method opens a fresh stream. This works for `ClassPathResource` and many re-openable resources; do not assume every `Resource` implementation supports reopening, especially `InputStreamResource`.

## 5. Reading Text: Specify the Charset Explicitly

`InputStream` is a **byte** stream; it does not know whether text is UTF-8, UTF-16, or another encoding. When reading text, you must choose the charset.

### 5.1. Reading small text content completely

For small templates or lightweight JSON configuration files:

~~~java
public String readUtf8(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
    }
}
~~~

`readAllBytes()` is available in Java 9 and later; Spring Boot 3.3 runs on Java versions meeting its minimum requirement, so this API is available.

Note: `readAllBytes()` loads the entire content into RAM. It is suitable for small bundled resources of controlled size. Do not use it for very large files or user-supplied data without size limits.

### 5.2. Using InputStreamReader and BufferedReader

If you want to process line by line:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public void printLines(Resource resource) throws IOException {
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8
            )
    )) {
        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println(line);
        }
    }
}
~~~

`BufferedReader` provides buffered text reading, and `readLine()` splits lines according to reader semantics. Suitable for line-oriented CSVs, text config files, or data lists.

Note: the snippet above only illustrates line-by-line reading. For real-world CSVs containing quoted fields, commas, or embedded newlines inside fields, do not parse manually with `String.split(",")`; use a CSV library with a format-compliant parser.

### 5.3. Keep raw bytes or convert to String?

| Data type | Recommended reading approach |
| --- | --- |
| Small UTF-8 text | `readAllBytes()` then `new String(..., UTF_8)` |
| Large text processed line by line | `InputStreamReader` + `BufferedReader` |
| JSON | Pass `InputStream` to Jackson/ObjectMapper |
| XML | Pass stream to a securely configured XML parser |
| CSV | Pass reader to a CSV library |
| PNG/JPEG/PDF | Process bytes or stream; do not blindly convert to String |
| ZIP or archive | Use the appropriate stream/archive API |

Do not assume arbitrary bytes can be converted into a UTF-8 String without losing information. For binary files, use streams or byte buffers.

## 6. JSON Example: Passing InputStream Directly to Jackson

Suppose an application has sample data in `src/main/resources/data/catalog.json`:

~~~json
{
  "catalogName": "spring-fundamentals",
  "items": [
    { "id": "book-1", "title": "Introduction" },
    { "id": "book-2", "title": "Resources" }
  ]
}
~~~

Java record:

~~~java
public record Catalog(
        String catalogName,
        List<Item> items
) {
    public record Item(String id, String title) {}
}
~~~

Service using Jackson `ObjectMapper`:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ObjectMapper objectMapper;

    public CatalogService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Catalog readBundledCatalog() throws IOException {
        Resource resource = new ClassPathResource("data/catalog.json");

        try (InputStream input = resource.getInputStream()) {
            return objectMapper.readValue(input, Catalog.class);
        }
    }
}
~~~

`ObjectMapper` can read directly from a stream, eliminating the need for an intermediate `String`, `File`, or `Path`. In an application with appropriate Spring Boot JSON auto-configuration, `ObjectMapper` is typically registered as an injectable bean; otherwise, declare a concrete bean.

### 6.1. Might the parser close the stream?

Some libraries have options to manage the input source themselves. Even if a parser closes the stream in certain modes, let `try-with-resources` express resource ownership clearly. When a method owns the stream it opened, it must close the stream when done.

If passing a stream into an asynchronous API that reads after the method returns, closing early via `try-with-resources` will fail. In that case, the owner of the async operation must manage the stream's lifetime per the API contract.

## 7. Reading Binary Data with InputStream

For PDFs, images, or binary files, avoid decoding into text. You can copy content to an `OutputStream`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public void copyResource(Resource resource, OutputStream output)
        throws IOException {

    try (InputStream input = resource.getInputStream()) {
        input.transferTo(output);
    }
}
~~~

`InputStream.transferTo(...)` (since Java 9) transfers bytes from input to output. The method above **closes only the InputStream it opened**, not the caller-supplied `OutputStream`. The caller owns the output stream and decides when to close it.

This pattern fits well when an application sends a bundled document to storage, writes data to an HTTP response, or passes a file through a stream-accepting API.

### 7.1. When to use streaming instead of readAllBytes?

Suppose a PDF file is 200 MB. Calling `readAllBytes()` requires keeping the full 200 MB (and potentially intermediate copies) in memory before processing.

By using streams and copying via buffers, the application can process data incrementally. `transferTo` avoids writing manual copy loops and prevents holding the whole resource in RAM.

For APIs that require a byte array, enforce a size limit on the resource before reading it all. Do not treat `contentLength()` as the sole security guard; a dynamic resource may have an unknown or changing length.

### 7.2. Use a manual buffer if needed

~~~java
public void copyBuffered(Resource resource, OutputStream output)
        throws IOException {

    try (InputStream input = resource.getInputStream()) {
        byte[] buffer = new byte[8192];
        int count;

        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
        }
    }
}
~~~

This has the same streaming semantics while letting you insert logic to enforce byte limits, compute checksums, or measure transfer progress.

Do not flush `output` manually after every small chunk unless specifically needed, as doing so can hurt performance.

## 8. @Value and ResourceLoader: Two Ways to Obtain a Resource

`ClassPathResource` is a direct choice when the resource name is fixed. When the location needs to come from configuration or support multiple resource types, `ResourceLoader` and injection can be a better fit.

### 8.1. Injecting Resource directly with @Value

~~~java
@Component
public class ReportTemplateRepository {

    private final Resource template;

    public ReportTemplateRepository(
            @Value("classpath:templates/report.html") Resource template) {
        this.template = template;
    }

    public String readTemplate() throws IOException {
        try (InputStream input = template.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Spring supports converting a resource location into a `Resource` at the injection point.

If operators need to override the path, move the location into a property instead of hard-coding it:

~~~properties
app.report.template-location=classpath:templates/report.html
~~~

~~~java
@Component
public class ConfigurableTemplateRepository {

    private final Resource resource;

    public ConfigurableTemplateRepository(
            @Value("${app.report.template-location}") Resource resource) {
        this.resource = resource;
    }

    public String read() throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

When the property is set to `file:/opt/app/config/report.html`, Spring can inject a filesystem resource instead of a classpath one.

### 8.2. Using ResourceLoader

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class ResourceReadingService {

    private final ResourceLoader resourceLoader;

    public ResourceReadingService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public byte[] readClasspathFile(String path) throws IOException {
        Resource resource =
                resourceLoader.getResource("classpath:" + path);

        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

This example illustrates the API. With user-supplied input, **do not concatenate arbitrary paths directly** without validation. Users might attempt to select unauthorized resources. Allow only predefined resource names or carefully normalize and restrict paths.

### 8.3. What if a location has no prefix?

`ResourceLoader.getResource(location)` supports prefixes like `classpath:` and URL protocols like `file:`. How an unprefixed location is interpreted depends on the specific resource loader implementation and context.

To keep code clear and less environment-dependent, use explicit prefixes:

- `classpath:data/catalog.json` for packaged resources.
- `file:/opt/app/data/catalog.json` for files outside the JAR.
- Do not arbitrarily allow external URLs without proper security policies and timeouts.

## 9. ClassPathResource and ClassLoader.getResourceAsStream()

Beyond the Spring Resource abstraction, Java provides built-in mechanisms to read resources via class loaders.

### 9.1. ClassPathResource

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

try (InputStream input = resource.getInputStream()) {
    // Read data.
}
~~~

The path in this example is resolved from the classpath root.

### 9.2. ClassLoader.getResourceAsStream

~~~java
ClassLoader classLoader = Thread.currentThread()
        .getContextClassLoader();

try (InputStream input =
             classLoader.getResourceAsStream("data/catalog.json")) {
    if (input == null) {
        throw new IOException("Resource not found: data/catalog.json");
    }

    // Read data from input.
}
~~~

`ClassLoader.getResourceAsStream(...)` returns `null` if the resource is not found. Never call `input.read()` immediately without handling the null case.

### 9.3. Class.getResourceAsStream and the leading slash

~~~java
try (InputStream rootResource =
             DemoApplication.class.getResourceAsStream(
                     "/data/catalog.json"
             )) {
    // Leading /: search from the classpath root.
}
~~~

With `Class.getResourceAsStream`:

- `"/data/catalog.json"` starts from the classpath root.
- `"data/catalog.json"` without a leading slash is resolved relative to the class's package.

With `ClassLoader.getResourceAsStream`, the path is always a resource name from the classpath root, **without a leading slash**.

| API | Example from classpath root |
| --- | --- |
| `new ClassPathResource(...)` | `"data/catalog.json"` |
| `ClassLoader.getResourceAsStream(...)` | `"data/catalog.json"` |
| `DemoApplication.class.getResourceAsStream(...)` | `"/data/catalog.json"` |

The leading slash can be a subtle source of bugs when switching between APIs. When already using Spring, `ClassPathResource` or `ResourceLoader` typically conveys intent more clearly.

## 10. getURL() and getURI() Do Not Replace getInputStream()

Some developers fix `getFile()` errors by calling `resource.getURL()` and then converting the URL to a `Path`:

~~~java
URL url = resource.getURL();

// Unsafe for resources inside a JAR:
Path path = Paths.get(url.toURI());
~~~

When the URL points to a regular file, this conversion may work. But when the resource sits inside a JAR, the URL may have a special scheme representing an archive entry, and `Path.of(uri)` or `Paths.get(uri)` does not know how to treat it like a regular file.

Conceptual location examples:

~~~text
file:/opt/app/classes/data/catalog.json
jar:file:/opt/app/lib/config.jar!/data/catalog.json
jar:nested:/opt/app/app.jar/!BOOT-INF/lib/library.jar!/data/catalog.json
~~~

Actual URLs depend on version, loader, and packaging. Do not parse URL strings like these by splitting on `!` or attempting to concatenate them into filesystem paths.

### 10.1. URL is a locator, not a File

`URL` and `URI` describe how to locate a resource; `File` and `Path` represent an object on a filesystem. The two overlap for `file:` URLs, but not every URL converts into a file.

When the task is reading content, open a stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Read bytes.
}
~~~

If a library accepts a `URL` and properly supports reading `jar:` URLs, you may pass the URL directly. Check the library's contract first; do not assume it can handle nested JARs provided by the Spring Boot loader.

### 10.2. Do not use ZipFile just to access a resource

Another approach people try is opening the executable JAR with `ZipFile` or `JarFile` to look up entries. This couples code to packaging structure, the `BOOT-INF/classes` layout, and nested JAR mechanics.

If the class loader already knows how to read the resource, let `ClassPathResource.getInputStream()` or class loader APIs do it. Only use archive APIs when the business requirement truly involves inspecting or manipulating archive contents as a ZIP/JAR file.

## 11. When an External Library Only Accepts File or Path

Not every API accepts an `InputStream`. A legacy library might require:

~~~java
legacyParser.parse(File file);
~~~

If the resource is inside a JAR, you cannot convert `ClassPathResource` directly into a `File`. In that situation, there are two options:

1. First look for an overload accepting `InputStream`, `Reader`, `byte[]`, or `URL` supported by the library.
2. If the API cannot be changed, **copy the resource to an actual temporary file**, then pass the `File` or `Path` to the library.

### 11.1. Copy to a temp file using Files.copy

~~~java
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.core.io.Resource;

public class LegacyParserAdapter {

    private final LegacyParser legacyParser;

    public LegacyParserAdapter(LegacyParser legacyParser) {
        this.legacyParser = legacyParser;
    }

    public void parseBundledResource(Resource resource) throws IOException {
        Path temporaryFile =
                Files.createTempFile("spring-resource-", ".bin");

        try {
            try (InputStream input = resource.getInputStream()) {
                Files.copy(
                        input,
                        temporaryFile,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }

            File file = temporaryFile.toFile();
            legacyParser.parse(file);
        } finally {
            Files.deleteIfExists(temporaryFile);
        }
    }
}
~~~

In this example, `LegacyParser` represents a hypothetical library. Replace it with your actual API. The key point is that the resource is copied to a **physical file** before being passed into the API.

### 11.2. When is it safe to delete the temporary file?

The example above deletes the file in `finally` **after `parse(file)` completes**. This is only valid if the library finishes reading the file synchronously inside the method.

If the library stores the path and processes it asynchronously, deleting immediately will cause the background task to miss the file. In that case, manage the temp file according to the task's lifecycle: delete it only after the task genuinely completes, fails, or is canceled.

### 11.3. Temp files need appropriate suffixes and permissions

Some libraries select a parser based on the file extension, such as `.json`, `.pdf`, or `.ttf`. Create the temp file with an appropriate suffix instead of always using `.bin`.

Considerations:

- Temporary disk space and write permissions inside containers.
- Sensitive information that may reside in the temporary file.
- Deleting the file on success, failure, and application interruption.
- Avoiding fixed file names that could collide across requests.
- Never letting clients directly control the temporary file path.
- Some operating systems prevent deleting files still held open by a process.

If an API can accept a stream, that approach is usually simpler and avoids the extra risks of temporary files.

### 11.4. Should you always copy to cache the resource?

Not necessarily. If you need to read a small file many times, you can parse it once during bean initialization and keep an **immutable** result in memory. If you need to stream large data, open a stream per operation. Only create a temporary file when an API or use case truly requires a filesystem path.

## 12. Resources Outside the JAR: When Is getFile() Appropriate?

`getFile()` is not an API that is always wrong. It is appropriate when the resource genuinely is a file on disk.

Example:

~~~java
import java.io.File;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource external =
        new FileSystemResource("/opt/app/config/catalog.json");

File file = external.getFile();
~~~

Here the source is a filesystem file, so calling `getFile()` matches its contract. You can also use `Path` directly:

~~~java
Path path = Path.of("/opt/app/config/catalog.json");

try (InputStream input = Files.newInputStream(path)) {
    // Read file outside the JAR.
}
~~~

Use files outside the JAR when data needs to:

- Be updated after deployment without rebuilding the artifact.
- Be mounted as a ConfigMap, Secret, or volume in a container.
- Be managed by an operator.
- Be writable and exist independently of the artifact lifecycle.
- Be passed to an API requiring a real filesystem path.

### 12.1. Resource location from configuration

In `application.yml`:

~~~yaml
app:
  catalog:
    location: file:/opt/app/config/catalog.json
~~~

Consumer:

~~~java
@Service
public class CatalogLocationService {

    private final Resource resource;

    public CatalogLocationService(
            @Value("${app.catalog.location}") Resource resource) {
        this.resource = resource;
    }

    public String read() throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Even when the location points to an external file, using `getInputStream()` remains valid and keeps the service independent of the resource type. Only call `getFile()` when an API genuinely requires a `File`.

### 12.2. Fallback from an external file to a classpath default

A common design is shipping a default template inside the JAR while allowing an external file override:

~~~properties
app.template.location=classpath:templates/default.txt
~~~

At deployment, an operator can switch it to:

~~~properties
app.template.location=file:/opt/app/templates/custom.txt
~~~

The service simply reads the injected `Resource` and does not need to know whether it came from the JAR or the filesystem.

This reduces the need for relative paths tied to the working directory, which can vary across IDEs, systemd, Docker, or Kubernetes.

### 12.3. Classpath resources should be treated as read-only

For resources inside an executable JAR, never expect to modify them directly with `Files.write(...)` or `FileOutputStream`. If the application needs to update data, use an external file, database, object storage, or an appropriate write mechanism.

Even when running in an IDE from an exploded directory where writing to `build/resources/main` might succeed, modifying that output file does not update `src/main/resources` and is not durable behavior in deployment.

## 13. Reading Multiple Resources with ResourcePatternResolver

Some applications need to read multiple files from a logical directory on the classpath, such as custom migration files or multiple templates packaged across modules.

`ResourcePatternResolver` supports finding resources by pattern:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

public class BundledCsvReader {

    private final ResourcePatternResolver resolver =
            new PathMatchingResourcePatternResolver();

    public List<String> filenames() throws IOException {
        Resource[] resources =
                resolver.getResources("classpath*:data/*.csv");

        List<String> names = new ArrayList<>();

        for (Resource resource : resources) {
            names.add(resource.getFilename());
        }

        return names;
    }
}
~~~

Here `classpath*:` searches across multiple classpath locations, not just the first matching resource. Wildcard patterns are processed by Spring's resource pattern resolution mechanism.

### 13.1. classpath: and classpath*: differ

| Prefix | Typical meaning |
| --- | --- |
| `classpath:` | Find one resource on the classpath |
| `classpath*:` | Find all matching resources across supported classpath locations |

Example where multiple JARs share the same resource name:

~~~text
module-a.jar!/config/features.yml
module-b.jar!/config/features.yml
~~~

`classpath:config/features.yml` typically finds a single resource via class loader resolution. `classpath*:config/features.yml` aims to locate multiple matching resources and return an array.

### 13.2. Do not rely on the returned order

When reading multiple resources, the order can depend on the classpath, class loader, and archive scanning behavior. If processing order matters to business logic, sort by a stable key, such as `getFilename()` or metadata inside the file, before processing.

Do not assume `Resource[]` is returned alphabetically or in module dependency order.

### 13.3. Wildcards and executable JARs

Spring supports pattern resolution for classpath and JAR resources, but root wildcard scanning and archive/class loader behavior have environment-specific limitations. When you need a guaranteed order and exact file list, an explicit **manifest** listing the resources is sometimes more reliable than wildcard scanning.

Example:

~~~text
data/files.txt
-----------
catalogs/electronics.csv
catalogs/books.csv
catalogs/games.csv
~~~

You read the manifest via a stream, then resolve each resource name explicitly. This does not depend on natural scan order and helps detect missing files.

In all cases, do not convert discovered `Resource` instances into `File` if they reside inside a JAR; continue using `getInputStream()`.

## 14. Distinguishing ClassPathResource and InputStreamResource

A common pitfall is thinking every `Resource` implementation supports calling `getInputStream()` multiple times.

A standard `ClassPathResource` can open a fresh stream on each access. By contrast, `InputStreamResource` wraps an **already-opened** stream and can usually only be read once.

Example:

~~~java
InputStream originalInput = new ByteArrayInputStream(
        "hello".getBytes(StandardCharsets.UTF_8)
);

Resource resource = new InputStreamResource(originalInput);
~~~

`InputStreamResource` is a poor choice to store in a singleton and read across multiple requests. Reopening it or computing `contentLength()` may consume the stream and cause subsequent reads to fail.

If data is already in a byte array and needs to be read multiple times, you can use `ByteArrayResource`:

~~~java
byte[] data = "hello".getBytes(StandardCharsets.UTF_8);

Resource reusable = new ByteArrayResource(data);

try (InputStream first = reusable.getInputStream();
     InputStream second = reusable.getInputStream()) {
    // Two separate streams can read from the in-memory data.
}
~~~

However, `ByteArrayResource` keeps the entire byte array in memory. For large resources, re-reading from the original resource via streaming generally uses less RAM.

### 14.1. contentLength() may not be side-effect free

For some `Resource` implementations, especially those wrapping a single-read stream, requesting `contentLength()` can force the implementation to read the stream to calculate its length.

Therefore, avoid calling `contentLength()` as a "harmless" check on arbitrary `Resource` objects. If you know the size from separate metadata, use that metadata; otherwise, process the stream and enforce byte limits as you read.

## 15. Using Resource in an HTTP Response

A controller sometimes needs to let users download a file packaged inside the JAR. Instead of calling `getFile()`, Spring MVC can write content from a `Resource` directly into the response.

Example endpoint to download a fixed document:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ManualController {

    @GetMapping("/manual")
    public ResponseEntity<Resource> download() {
        Resource manual =
                new ClassPathResource("documents/user-manual.pdf");

        if (!manual.exists()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename("user-manual.pdf")
                                .build()
                                .toString()
                )
                .body(manual);
    }
}
~~~

The example assumes `src/main/resources/documents/user-manual.pdf` exists in the artifact. With standard Spring MVC auto-configuration, `ResourceHttpMessageConverter` reads the resource and writes the content.

You do not need to call `manual.getFile()` to return the response. In particular, if streaming large resources, verify how the framework writes responses, sets Content-Length, and handles range requests and cache headers for your use case.

### 15.1. Static resources may not need a controller

Spring Boot MVC typically serves static resources from classpath locations such as:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

For example, `src/main/resources/static/images/logo.png` can usually be accessed via `/images/logo.png` when default static resource handling is active.

If you only want to serve CSS, JavaScript, or static images, consider Spring Boot's static resource handling before writing a manual streaming controller.

Never expose arbitrary classpath paths via user parameters, as doing so can leak configuration or internal resources.

## 16. Testing Resources: Why Unit Tests Can Miss getFile Bugs

Tests typically run against a directory-based classpath:

~~~text
build/classes/java/main/
build/resources/main/
build/classes/java/test/
build/resources/test/
~~~

As a result, a test using:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");
assertThat(resource.getFile()).exists();
~~~

can pass in an IDE or Gradle test run even though `getFile()` will fail when the application runs from an executable JAR.

**Do not use a passing `getFile()` call in a directory-classpath test to claim a resource in a JAR has a valid file path.** They are two different class loader environments.

### 16.1. Unit test reading a resource via InputStream

A simple JUnit 5 test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

class ClasspathResourceTest {

    @Test
    void readsTextFromClasspath() throws Exception {
        Resource resource =
                new ClassPathResource("templates/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            assertThat(text).contains("Hello");
        }
    }
}
~~~

This test does not require a `File`, making it suitable for designs that must run both in an IDE and in a JAR.

### 16.2. Testing through a Spring context

If a service uses `@Value` to inject `Resource`:

~~~java
@SpringBootTest
class WelcomeTemplateServiceTest {

    @Autowired
    private WelcomeTemplateService service;

    @Test
    void loadsBundledTemplate() throws Exception {
        String text = service.loadTemplate();
        assertThat(text).isNotBlank();
    }
}
~~~

This test exercises the application's actual dependency injection mechanism. However, it may still run against an exploded classpath, so it mainly checks resource name resolution and stream reading, not completely replacing packaged artifact verification.

### 16.3. Testing the packaged artifact

For an application released as an executable JAR, you can run the artifact in a production-like test environment:

~~~bash
# Example after the artifact has been built by the project pipeline:
java -jar build/libs/demo-app.jar
~~~

Then invoke the endpoint or workflow that uses the resource. If the application is a CLI, create an `ApplicationRunner` or specific command that reads the resource via stream.

What you want to confirm is that the resource is genuinely packaged inside the JAR and reading does not rely on `src/main/resources` or build directories on a development machine.

Do not write tests referencing a fixed path like `build/resources/main/...` just because it exists in the IDE; that is not a stable classpath resource location for a deployed artifact.

## 17. Checking Whether a Resource Is Packaged

If `getInputStream()` also fails, the cause may be that the resource is missing from the classpath or the path is wrong.

Check the project structure:

~~~text
src/main/resources/data/catalog.json
~~~

Check in code:

~~~java
Resource resource = new ClassPathResource("data/catalog.json");

if (!resource.exists()) {
    throw new IllegalStateException(
            "Missing resource: " + resource.getDescription()
    );
}
~~~

In a build pipeline, you can inspect the built artifact's contents to confirm the resource is inside the JAR:

~~~bash
jar tf build/libs/demo-app.jar
~~~

You can look for:

~~~text
BOOT-INF/classes/data/catalog.json
~~~

These commands are manual diagnostic tools during development and deployment. Do not build runtime logic that opens the executable JAR and looks up entries by hard-coded internal paths.

### 17.1. Reasons a resource goes missing

- File was mistakenly placed in `src/test/resources`, so it is absent from the production artifact.
- Case sensitivity mismatch in the path, especially when moving from Windows to Linux.
- File excluded by resource filtering or build configuration.
- Resource lives in a module/JAR not included on the runtime classpath.
- Code constructs the `classpath:` prefix incorrectly or redundantly includes `src/main/resources`.
- Using `Class.getResourceAsStream` but forgetting the leading slash when intending a root path.
- In Docker, a volume mount overwrites a directory containing external resources and hides expected files.

If a classpath resource exists in the JAR yet `getFile()` fails, that is not a packaging bug. It is an **inappropriate API choice**.

## 18. Exceptions and Sensible Error Handling

`Resource.getInputStream()` can throw `IOException` when a resource does not exist or cannot be read.

Depending on the file's role, the application must decide how to behave on failure.

### 18.1. Required resources

For a template required for the application to operate, fail fast:

~~~java
@Component
public class RequiredTemplate {

    private final Resource resource =
            new ClassPathResource("templates/required.txt");

    @PostConstruct
    public void verify() throws IOException {
        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Required template is missing: "
                            + resource.getDescription()
            );
        }

        try (InputStream input = resource.getInputStream()) {
            // Optionally verify header or parse essential data.
            input.read();
        }
    }
}
~~~

This example requires the appropriate imports for `Component`, `PostConstruct`, `Resource`, and `InputStream`. In a real application, if you need to parse the entire data at startup, consider caching the parsed result rather than reading a single byte during verification and re-reading repeatedly.

### 18.2. Optional resources

For optional files, a fallback may make sense:

~~~java
public String loadOptionalText(Resource resource) throws IOException {
    if (!resource.exists()) {
        return "";
    }

    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Only return an empty default if it makes business sense. Never silently ignore errors when reading a required file or a file containing security configuration.

### 18.3. Do not swallow IOException and return null unconditionally

Wrong:

~~~java
try {
    return new String(resource.getInputStream().readAllBytes(), UTF_8);
} catch (Exception exception) {
    return null;
}
~~~

This snippet both fails to close the stream and masks all errors as null. Downstream consumers may later encounter a `NullPointerException` far from the real cause.

It is better to let `IOException` propagate or wrap it in a domain exception carrying the resource location without exposing sensitive data:

~~~java
public String requireText(Resource resource) {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException exception) {
        throw new IllegalStateException(
                "Cannot read required resource: "
                        + resource.getDescription(),
                exception
        );
    }
}
~~~

## 19. Security When Reading Resources

Classpath resources are typically developer-packaged data that rarely changes. However, locations may come from properties, HTTP parameters, or messages. When they do, treat them as potentially harmful input unless controlled.

### 19.1. Do not use user-supplied paths to read arbitrary files

Dangerous example:

~~~java
@GetMapping("/read")
public String read(@RequestParam String path) throws IOException {
    Resource resource = resourceLoader.getResource(path);
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

If users can supply arbitrary locations such as `file:` or other URLs, the endpoint can allow accessing data outside the intended scope, including local filesystem files or outbound network access with the server's permissions.

Instead, restrict to an allowed set of resources:

~~~java
private static final Map<String, String> ALLOWED_TEMPLATES = Map.of(
        "welcome", "classpath:templates/welcome.txt",
        "receipt", "classpath:templates/receipt.txt"
);
~~~

Only use locations retrieved from the defined map. For external paths, validate and normalize paths and prevent traversal/symlink escapes per security requirements.

### 19.2. Do not read unbounded data into RAM

A user-controlled resource could be huge. Calling `readAllBytes()` or writing into an unbounded `ByteArrayOutputStream` can exhaust memory and destabilize the application.

For untrusted or large data, prefer streaming with byte-count limits, network timeouts if remote, and backpressure/cancellation per the framework in use.

### 19.3. Do not log secret content

`getDescription()` can help error messages, though some resource locations may include query parameters or sensitive information. Filter and minimize logged information before sending it to centralized observability systems.

Never log raw bytes or full contents of configuration files containing secrets just to diagnose a `getFile()` failure.

## 20. Common Issues and How to Fix Them

| Symptom | Primary cause | Fix |
| --- | --- | --- |
| Works in IDE, `java -jar` fails on `getFile()` | Classpath resource is now a JAR entry | Read using `getInputStream()` |
| `FileNotFoundException` says not in file system | Resource exists but has no physical file path | Do not call `getFile()`; use a stream |
| `resource.exists()` is true but `getFile()` fails | Logical existence differs from `File` representation | Identify resource location and required API |
| `ClassLoader.getResourceAsStream` returns null | Wrong path or file absent from runtime classpath | Check root path, resource packaging, and case |
| `new ClassPathResource("src/main/resources/...")` not found | Used source path instead of classpath path | Remove `src/main/resources/` |
| `Path.of(resource.getURI())` fails on `jar:` URI | URI is not a filesystem path | Use resource stream |
| Cannot parse JSON/CSV | Wrong charset or parser | Use UTF-8 and an appropriate parser library |
| Binary file corrupted after reading | Bytes were converted to text | Keep bytes/stream, do not decode to String |
| Re-reading resource fails | Single-use `InputStreamResource` or closed stream | Use a re-openable resource or manage stream lifecycle properly |
| `contentLength()` leaves stream unreadable | Single-use resource may be consumed | Do not call this method casually on one-shot streams |
| Parser only accepts `File` | Library API does not support InputStream | Copy to temp file, manage lifecycle, delete after use |
| File missing in production | File only in test resources or excluded from artifact | Inspect build resource packaging |
| Works on Windows, wrong name on Linux | Case sensitivity difference | Use exact-case paths |
| Cannot read file outside JAR | Filesystem permission or volume mount issue | Check permissions, mounts, and path |
| Edited classpath file, deployment unchanged | Resource packaged inside old artifact | Rebuild/redeploy or use external config |
| Classpath wildcard scan misses files | Class loader/pattern/archive scanning differences | Test packaged artifact or use an explicit manifest |

### 20.1. Quick diagnostic workflow

When encountering a resource issue in a Spring Boot application:

1. Confirm the file is stored in `src/main/resources` or the corresponding dependency JAR.
2. Verify the resource name is **relative to the classpath root**, not using the project source path.
3. Check whether code calls `getFile()`, `getURI()` to build a `Path`, or `FileInputStream`.
4. If you only need to read, switch to `Resource.getInputStream()`.
5. If a library strictly requires a `File`, check for a stream overload first; otherwise, copy to a temp file and clean up.
6. Check encoding/format and ensure the stream is closed.
7. Run in a packaged environment close to production to catch differences between exploded classes and JARs.
8. If it still fails, check whether the artifact packages the resource, the runtime classpath, read permissions, and path casing.

## 21. Choosing the Right API for Your Needs

| Need | Recommended solution | Is getFile() needed? |
| --- | --- | --- |
| Read small text from JAR | `Resource.getInputStream()` + UTF-8 | No |
| Parse bundled JSON | `ObjectMapper.readValue(InputStream, ...)` | No |
| Read CSV line by line | `InputStreamReader` + CSV parser | No |
| Stream PDF/images | `InputStream.transferTo(OutputStream)` | No |
| Return resource via Spring MVC | `ResponseEntity<Resource>` or static resource handling | No |
| Load resources from various locations | `ResourceLoader` | No |
| Scan multiple classpath resources | `ResourcePatternResolver` | No |
| Read/write external file with real path | `Files` / `FileSystemResource` | May be used |
| Legacy library accepting only File | Copy resource to temporary file | Only on the temp file |
| Runtime-modifiable configuration | External file/database/object storage | Do not rely on JAR |
| Cache small parsed content | Parse once and keep an immutable object | No |

A helpful question before picking an API: **do I need the data inside the resource, or do I genuinely need an OS file path?** If you only need the data, `InputStream` is the better abstraction.

## 22. Practice Exercises

### Exercise 1 — Reading text in IDE and JAR

Create `src/main/resources/templates/welcome.txt`. Write a service that reads the file using `ClassPathResource.getInputStream()` and `UTF_8`. Call the service when running from the IDE and when running the packaged JAR. Compare the behavior.

### Exercise 2 — Reproducing the getFile error

Write a method using `new ClassPathResource("templates/welcome.txt").getFile()`. Observe behavior when running from the exploded classpath. Then run from an executable JAR and explain why `getFile()` cannot supply a physical path.

### Exercise 3 — JSON with Jackson

Add `data/catalog.json` and a matching Java record. Use `ObjectMapper.readValue(InputStream, Catalog.class)`. Write a test asserting the number of items after parsing.

### Exercise 4 — Streaming binary data

Add a small image under `images/logo.png`. Write a method accepting an `OutputStream`, using `InputStream.transferTo` to copy bytes. Compute a checksum or compare bytes before and after without converting to String.

### Exercise 5 — External override

Configure a resource location property defaulting to `classpath:templates/welcome.txt`. Change the property to `file:/opt/app/templates/custom.txt` in a test environment with the corresponding file. Verify the service switches sources with no code changes.

### Exercise 6 — SDK requiring File

Simulate a parser that only accepts `File`. Write an adapter copying a classpath resource to `Files.createTempFile`, passing it to the parser, and deleting it in `finally`. Explain how to handle the case where the parser runs asynchronously.

### Exercise 7 — Reading multiple CSVs

Create two files `data/one.csv` and `data/two.csv`. Use `ResourcePatternResolver.getResources("classpath*:data/*.csv")` to locate them. Process each resource through `getInputStream()` and sort by filename before processing.

### Exercise 8 — Verifying stream lifecycle

Create one method that reads a resource with `try-with-resources` and another that attempts to store a stream in a singleton field. Compare close/reopen management and explain why keeping `Resource` is generally safer than keeping an open stream.

### Exercise 9 — Testing the packaged artifact

Add a stream-based resource test. Then in a packaging test pipeline, run the application from the executable JAR and invoke the workflow that uses the resource. Confirm there is no remaining dependency on `build/resources/main` or `src/main/resources`.

## 23. Key Takeaways

`Resource` is Spring's abstraction for multiple types of data locations. `ClassPathResource` finds resources by name on the classpath but **does not promise a physical file**. When running in an IDE, the resource may live in a directory and `getFile()` happens to work. Once packaged into an executable JAR, the same resource is usually a JAR entry, so `getFile()` may throw `FileNotFoundException` even while `exists()` remains true.

If you only need to read content, use **`Resource.getInputStream()`**, close the stream with `try-with-resources`, and choose appropriate data handling: `UTF-8` for text, stream-accepting parsers for JSON/CSV, and byte streams for PDFs and images. Do not convert `jar:` URLs/URIs into filesystem paths, and do not use `readAllBytes()` for unbounded large data.

When a library genuinely requires `File` or `Path`, look for a stream overload first or copy the resource to a temporary file and manage deletion according to the lifecycle. For files that need runtime edits, use external filesystem/config locations rather than resources inside the JAR.

Stream-based design does more than fix deployment errors: it makes code less coupled to packaging, easier to test, and more compatible with class loaders, dependency JARs, and container environments.
