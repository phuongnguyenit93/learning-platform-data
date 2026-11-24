# Charset, Stream Closing, and the Lifecycle of Self-Opened Resources

In a Spring Boot application, reading auxiliary config files, CSVs, JSONs, templates, sample data, or user-uploaded files often takes only a few lines of Java. Yet those few lines sit at the intersection of three easily overlooked issues:

- **Charset**: how should bytes be converted to characters so Vietnamese diacritics or data contents are not corrupted?
- **Closing streams**: who must call `close()`, when should it be called, and how can we guarantee closure even when an exception occurs?
- **Resource lifecycle**: which resources are opened by the application and must be closed by it, which are managed by Spring/the container, and when must we not close on behalf of the owner?

These three issues often show up together. A UTF-8 file read with the default charset can turn **"Tiếng Việt"** into garbled characters. An unclosed InputStream can hold onto file descriptors or network connections. A stream closed too early can cause asynchronous processing or an HTTP response to fail mid-flight.

This lesson explains how to handle these three responsibilities when working with the **Spring Resource abstraction**, files inside the classpath/executable JARs, filesystem files, HTTP uploads/downloads, and long-lived resources in the ApplicationContext.

## 1. Distinguishing Byte, Character, Stream, and Resource

First, separate the concepts clearly:

| Concept | Responsibility |
|---|---|
| **Byte** | Unit of binary data. Files, sockets, and many protocols store/transmit bytes. |
| **Character/String** | Text representation at the Java layer. |
| **Charset** | Rules for encoding characters into bytes and decoding bytes into characters. |
| **InputStream** | Reads a sequence of bytes from a source. |
| **OutputStream** | Writes a sequence of bytes to a destination. |
| **Reader** | Reads text data as characters. |
| **Writer** | Writes text data as characters. |
| **Resource** | Spring's abstraction describing a resource and providing a way to open a stream to read it; not synonymous with an already-opened stream. |

Reading flow for a text file:

~~~text
Classpath file / file on disk / network response
                       │
                       ▼
                 Source bytes
                       │
                       ▼
                  InputStream
                       │
                 Charset decoder
                       │
                       ▼
               InputStreamReader
                       │
                       ▼
                BufferedReader
                       │
                       ▼
                  String / text
~~~

Reverse writing flow:

~~~text
String / text
      │
      ▼
    Writer
      │
  Charset encoder
      ▼
 OutputStream
      │
      ▼
File / response body / network destination
~~~

An InputStream does not know whether a file contains UTF-8, UTF-16, ISO-8859-1, or binary data. Only when code decodes bytes into characters does the charset become a mandatory decision.

## 2. What Is a Charset?

A **Charset** defines how text is encoded or decoded. For example, UTF-8 is a Unicode encoding widely used in modern applications.

Java provides standard charsets in:

~~~java
import java.nio.charset.StandardCharsets;
~~~

Example:

~~~java
String message = "Xin chào, Hà Nội!";

byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

When encoding and decoding use the same appropriate charset, the string is restored accurately.

### 2.1. When is a charset actually used?

When reading **raw bytes**, there is no decoding step:

~~~java
byte[] data = inputStream.readAllBytes();
~~~

But when constructing a String from bytes:

~~~java
String text = new String(data, StandardCharsets.UTF_8);
~~~

a charset has been chosen. Similarly, creating an InputStreamReader decides how decoding happens:

~~~java
Reader reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8);
~~~

For images, PDFs, ZIPs, or binary data, never read into a String and write it back out. Handle them as bytes via InputStream/OutputStream, or use a format-specific parser.

### 2.2. Why specify the charset explicitly?

Two snippets may look similar yet differ in meaning:

~~~java
String text = new String(bytes);
~~~

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

The first uses the runtime's **default charset**. The default charset can vary across Java versions, JVM flags, or deployment environments. Modern Java commonly defaults to UTF-8, but relying on defaults leaves the data contract ambiguous.

The second asserts that the source data is UTF-8 encoded. It depends less on machine settings and is easier to test.

Guideline to follow: **every byte ↔ text conversion boundary should specify an explicit charset**, whenever the format or protocol permits.

### 2.3. How does the wrong charset corrupt data?

A file saved as UTF-8 but read with a different charset can produce:

~~~text
Original data:    Nguyễn Văn Bình
Wrong decoding:   Nguyá»…n VÄƒn BÃ¬nh
~~~

This phenomenon is commonly called **mojibake**: the same byte sequence is interpreted under the wrong character table.

Other failures include:

- Strange characters or replacement characters appearing in strings.
- String comparisons, searches, or data signature verifications failing.
- CSV headers containing unexpected characters, breaking column-name lookups.
- Data being re-saved with the wrong encoding, propagating corruption to other systems.

Not every Vietnamese diacritic issue is a Spring Boot bug. Verify what encoding the source file was actually saved in and which charset each read/write step selects.

## 3. Reading UTF-8 Text from the Filesystem

For files on the filesystem, Java NIO offers charset-explicit APIs.

### 3.1. Small files: Files.readString

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileReader {

    public String load(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
~~~

This is concise and appropriate when the entire file fits in memory.

If a file holds hundreds of MBs or multiple GBs, `Files.readString` can spike memory usage by allocating the entire String.

### 3.2. Large files: Files.newBufferedReader

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextLineCounter {

    public long countNonEmptyLines(Path path) throws IOException {
        long count = 0;

        try (BufferedReader reader =
                     Files.newBufferedReader(
                             path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    count++;
                }
            }
        }

        return count;
    }
}
~~~

This code reads line by line without holding the entire file in RAM. Upon exiting try-with-resources, the BufferedReader closes automatically.

### 3.3. Writing text with an explicit charset

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextReportWriter {

    public void writeReport(Path target) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(
                             target, StandardCharsets.UTF_8)) {

            writer.write("Revenue report");
            writer.newLine();
            writer.write("Branch: Hanoi");
            writer.newLine();
        }
    }
}
~~~

When the writer closes, buffered data is flushed and underlying resources are released. Note: **close/flush does not guarantee every byte has been durably synced to physical storage before a power loss**. High-durability requirements need dedicated file I/O policies, potentially including fsync, transactions, and atomic moves.

### 3.4. Do not use charset-less String.getBytes() at storage/transport boundaries

Avoid:

~~~java
byte[] body = report.getBytes();
~~~

Prefer:

~~~java
byte[] body = report.getBytes(StandardCharsets.UTF_8);
~~~

Similarly, avoid relying on the default charset when creating InputStreamReader or OutputStreamWriter if external data specifies an encoding contract.

## 4. What Roles Do InputStreamReader and BufferedReader Play?

An InputStream returns bytes. To read text line by line, it is commonly wrapped with:

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                inputStream, StandardCharsets.UTF_8));
~~~

- **InputStreamReader**: decodes bytes into characters using UTF-8.
- **BufferedReader**: reduces small read calls and provides `readLine()`.

Do not treat `readLine()` as a complete CSV parser. A CSV field can contain commas, double quotes, or embedded newlines per CSV rules. If you need compliant CSV parsing, use a proper library or parser.

### 4.1. BufferedReader must be closed

Example:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                inputStream, StandardCharsets.UTF_8))) {

    String firstLine = reader.readLine();
    System.out.println(firstLine);
}
~~~

**Closing BufferedReader closes the inner InputStreamReader and the InputStream it wraps.**

Thus, if you own the underlying InputStream, placing the outermost wrapper in try-with-resources is enough. You do not have to declare all three wrapper layers as separate resource variables when the ownership contract is clear.

Important point: if the underlying InputStream **belongs to the caller** and was only lent to you to read, closing BufferedReader will also close a stream you do not own. Determine ownership before closing; a later section explains this in detail.

## 5. Byte Order Mark (BOM) and Subtle Signs at the Start of a File

Some UTF-8 files begin with three BOM bytes:

~~~text
EF BB BF
~~~

A BOM can serve as an encoding marker. UTF-8 does not require a BOM, yet export tools sometimes still add one.

When reading UTF-8 files via standard APIs, the BOM can appear in text as the character **U+FEFF** at the start of the data.

Example:

~~~text
Visible file:    id,name
Actual string:   U+FEFF + id,name
~~~

If a parser compares the header strictly against **id**, the match can fail.

### 5.1. Stripping BOM when the format allows

Example handling the first line of a text file with an optional BOM convention:

~~~java
String firstLine = reader.readLine();

if (firstLine != null
        && !firstLine.isEmpty()
        && firstLine.charAt(0) == '\uFEFF') {
    firstLine = firstLine.substring(1);
}
~~~

Only strip the BOM according to the source format's contract. Do not blindly delete arbitrary leading special characters when data must be preserved. If your JSON/XML/CSV library already handles BOMs per spec, use that parser instead of stacking duplicate logic.

### 5.2. Do not guess charset from filename alone

Extensions like **.txt**, **.csv**, or **.properties** do not prove data is UTF-8. If the source is a legacy system with another encoding, confirm from documentation or trusted metadata.

For incoming data of unknown charset, establish clear detection/validation rules and report errors instead of decoding with the default charset and continuing with corrupted data.

## 6. The Spring Resource Abstraction in Spring Boot

Spring provides the interface:

~~~java
org.springframework.core.io.Resource
~~~

Resource represents a readable data source along with metadata like filename, URL, existence, and readability.

Common implementations:

| Type | Use case |
|---|---|
| **ClassPathResource** | File packaged on the application classpath or in a dependency JAR. |
| **FileSystemResource** | Actual file on the filesystem. |
| **UrlResource** | Resource identified by an appropriate URL. |
| **ByteArrayResource** | Byte data already in RAM, supporting re-opening streams. |
| **InputStreamResource** | Wraps an existing InputStream, typically suitable for single-read use only. |

Example:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.csv");
~~~

In a Spring Boot project:

~~~text
src/
└── main/
    └── resources/
        └── data/
            └── catalog.csv
~~~

The classpath path is **data/catalog.csv**, not **src/main/resources/data/catalog.csv** once the application is packaged.

### 6.1. Resource does not equal an already-open InputStream

For a typical ClassPathResource or FileSystemResource, the Resource object mainly describes **where to find data**. Calling:

~~~java
InputStream in = resource.getInputStream();
~~~

opens a stream to read content.

Normally you can call `getInputStream()` multiple times to open independent streams from the same ClassPathResource or FileSystemResource, provided the resource still exists and supports it.

Notable exception: **InputStreamResource** wraps an already-opened stream and generally cannot be re-read. Do not assume every Resource is repeatable.

### 6.2. Do you need to close(Resource)?

The Resource interface is not an `AutoCloseable` resource in the conventional sense. For a Resource descriptor like ClassPathResource, you do not call `resource.close()`.

What you need to close is:

~~~java
InputStream in = resource.getInputStream();
~~~

and any other Reader/Writer/stream that your code opened or owns.

Do not confuse the lifecycle of a **Resource bean** with the lifecycle of an **InputStream** opened from that Resource.

## 7. Reading Classpath Files with ClassPathResource

Sample file:

~~~text
src/main/resources/data/regions.txt
~~~

UTF-8 content:

~~~text
Hà Nội
Đà Nẵng
Thành phố Hồ Chí Minh
~~~

Reading code:

~~~java
package com.example.demo.resources;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class RegionLoader {

    public List<String> loadRegions() throws IOException {
        Resource resource =
                new ClassPathResource("data/regions.txt");

        List<String> regions = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        resource.getInputStream(),
                        StandardCharsets.UTF_8))) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    regions.add(line);
                }
            }
        }

        return regions;
    }
}
~~~

Points to note:

1. Path is resolved relative to the runtime classpath.
2. **getInputStream()** opens the data; may throw IOException.
3. **InputStreamReader** decodes UTF-8.
4. **BufferedReader** supports line-by-line reading.
5. **try-with-resources** closes the stream even if the loop or parsing fails.

For large data files, returning the entire List still consumes RAM proportional to line count. This example uses a small catalog file. For large files, process sequentially while the stream remains open.

### 7.1. Why not use new File("src/main/resources/...")?

In an IDE, the path:

~~~java
new File("src/main/resources/data/regions.txt")
~~~

may happen to exist because the process launches from the project root directory.

But after building an executable JAR:

~~~text
app.jar
└── BOOT-INF
    └── classes
        └── data
            └── regions.txt
~~~

the classpath file is an entry inside the artifact. It does not necessarily correspond to a standalone file on the filesystem.

Therefore, code relying on the source tree's working directory fails when deployed. **ClassPathResource.getInputStream()** is the right API for reading resources inside a JAR.

### 7.2. Avoid Resource.getFile() for classpath entries in a JAR

Risky example:

~~~java
File file = new ClassPathResource(
        "data/regions.txt").getFile();
~~~

When running from a classes directory in an IDE, `getFile()` might succeed. When running from an executable JAR, the resource is no longer an individual file and `getFile()` can throw FileNotFoundException/IOException or related errors.

Prefer:

~~~java
try (InputStream in = new ClassPathResource(
        "data/regions.txt").getInputStream()) {
    // Read bytes or wrap with a Reader using the appropriate charset.
}
~~~

Only call `Resource.getFile()` when the application's contract strictly requires a filesystem file and you have guaranteed the resource sits on the filesystem, not inside a JAR.

## 8. ResourceLoader and Configured Locations

When a source can switch between classpath and filesystem, use **ResourceLoader**:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

Resource resource = resourceLoader.getResource(
        "classpath:data/catalog.csv");
~~~

Illustrative location forms:

~~~text
classpath:data/catalog.csv
file:/opt/app/input/catalog.csv
https://example.invalid/catalog.csv
~~~

`ResourceLoader` creates the corresponding Resource by protocol/prefix and environment. Not every Resource type behaves identically: classpath, file, and network sources have different readability, performance, and security rules.

### 8.1. Service injecting ResourceLoader via constructor

~~~java
package com.example.demo.resources;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ResourceLoader resourceLoader;

    public CatalogService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public long countLines(String location)
            throws IOException {

        Resource resource =
                resourceLoader.getResource(location);

        long count = 0;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        resource.getInputStream(),
                        StandardCharsets.UTF_8))) {

            while (reader.readLine() != null) {
                count++;
            }
        }
        return count;
    }
}
~~~

The service opens the stream **within the scope of each read**, closes it afterward, and retains ResourceLoader as a Spring-managed dependency.

You do not need and should not attempt to close ResourceLoader after each call: it is the component providing resource lookup, not a per-request InputStream.

### 8.2. Locations from untrusted sources

The `countLines(String location)` example above illustrates the API; **never allow untrusted HTTP clients to supply arbitrary strings** such as `file:/...` or `https://...` for the server to read.

If an application reads locations from untrusted requests, it can lead to:

- Reading internal files outside permitted areas.
- Unintended network requests (SSRF).
- Huge resources exhausting RAM/bandwidth.
- Slow connections hanging worker threads.

In real applications, configure locations from trusted administrative sources or use explicit allowlists/sandboxes. Never treat ResourceLoader as an access-control boundary.

## 9. Resource.exists(), isReadable(), and Handling I/O Errors

You can check:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.csv");

boolean exists = resource.exists();
boolean readable = resource.isReadable();
~~~

However, `exists()`/`isReadable()` checks are only point-in-time observations. A file can vanish or change permissions before `getInputStream()` executes. A network resource can also time out after metadata looked valid.

Hence, code must still handle IOException around open/read operations:

~~~java
public String firstLine(Resource resource)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

Do not rely solely on:

~~~java
if (resource.exists()) {
    // Assume every subsequent read will definitely succeed.
}
~~~

If content is required at startup, decide clearly: should startup fail when unreadable, or does the application have a safe fallback? Never swallow IOException and return empty data as success when the data is critical.

## 10. try-with-resources and Stream-Closing Responsibility

Java supports **try-with-resources** for objects implementing `AutoCloseable`, including InputStream, Reader, Writer, and many other resource types.

Syntax:

~~~java
try (InputStream in = resource.getInputStream()) {
    // Read data.
}
~~~

Upon exiting the try block, Java calls `close()` even when:

- The file finishes reading normally.
- Returning early.
- An exception is thrown while reading.
- An exception is thrown during parsing logic.

Example:

~~~java
public byte[] read(Resource resource) throws IOException {
    try (InputStream in = resource.getInputStream()) {
        return in.readAllBytes();
    }
}
~~~

**`readAllBytes()` does not close the InputStream itself.** In the example, try-with-resources is what guarantees stream closure.

### 10.1. Closing the outermost wrapper typically closes inner streams

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                resource.getInputStream(),
                StandardCharsets.UTF_8))) {
    return reader.readLine();
}
~~~

Closing `BufferedReader` also closes the underlying `InputStreamReader` and `InputStream`.

Avoid:

~~~java
InputStream in = resource.getInputStream();
BufferedReader reader = new BufferedReader(
        new InputStreamReader(in, StandardCharsets.UTF_8));
// Process without closing reader or in.
~~~

Unmanaged code without closing risks leaks both when reading completes and when errors occur.

### 10.2. Closing in reverse order with multiple resources

~~~java
try (InputStream in = resource.getInputStream();
     Reader reader = new InputStreamReader(
             in, StandardCharsets.UTF_8);
     BufferedReader buffered = new BufferedReader(reader)) {

    System.out.println(buffered.readLine());
}
~~~

Java closes resource variables in reverse order: `buffered`, `reader`, `in`. Here, closing the outer wrapper already closes the inner layers; extra `close()` calls on the same stream are redundant though tolerated by most implementations.

Usually declaring just the outermost wrapper in try-with-resources is cleaner and makes ownership clearer. For multiple independent resources, declare each object separately.

### 10.3. How are exceptions during close() handled?

If code inside the `try` block throws an exception and `close()` also throws an exception, Java preserves the original exception and attaches the close error as a **suppressed exception**.

Example:

~~~java
try (InputStream in = resource.getInputStream()) {
    parse(in);  // May fail.
}
~~~

When diagnosing failures, do not read only the first line of the stack trace; suppressed exceptions can explain resource-release issues.

Avoid manually writing `finally` blocks that close streams and accidentally mask the primary exception. try-with-resources handles this safely.

## 11. Who Owns the Stream and Who Must Close It?

The most important resource rule is **ownership**: which party owns lifecycle management responsibility?

Three common patterns exist:

1. **Opened and consumed locally**: code calling `getInputStream()`/`Files.newBufferedReader()` usually must close it in the same scope.
2. **Received from caller (borrowed)**: code may not automatically close it; follow the API contract.
3. **Handed off to framework/container (transferred)**: the framework takes over using and closing the resource; code must not close it prematurely.

### 11.1. Close where opened

This is the simplest case:

~~~java
public long countBytes(Resource resource) throws IOException {
    try (InputStream in = resource.getInputStream()) {
        long count = 0;
        byte[] buffer = new byte[8192];

        int read;
        while ((read = in.read(buffer)) != -1) {
            count += read;
        }
        return count;
    }
}
~~~

The method **called `getInputStream` itself**, so it closes the InputStream before returning.

### 11.2. APIs accepting a caller's InputStream

Example of a helper that only processes data:

~~~java
public long countBytesBorrowed(InputStream in)
        throws IOException {

    long count = 0;
    byte[] buffer = new byte[8192];

    int read;
    while ((read = in.read(buffer)) != -1) {
        count += read;
    }
    return count;
}
~~~

This helper **does not close** the InputStream. Because the caller passed the stream in, the caller might still need it after this method returns.

Caller-side lifecycle:

~~~java
try (InputStream in = resource.getInputStream()) {
    long size = countBytesBorrowed(in);
    System.out.println(size);
}
~~~

Do not assume every API accepting an InputStream leaves it open. Some libraries specify that the API **takes ownership** and closes it after use. Read the specific contract; when designing your own APIs, state clearly:

- Does the method close the passed stream?
- Does the method consume the entire stream?
- Does the method retain the stream for use after returning?
- May the caller continue using the stream?

### 11.3. Avoid accidentally closing a borrowed stream via a Reader wrapper

A subtle bug:

~~~java
public String readFirstLine(InputStream borrowed)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    borrowed, StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

This method **closes the borrowed InputStream** when closing BufferedReader. If the caller still needs the stream afterward, a "stream closed" error results.

The fix is not simply removing try-with-resources haphazardly. **Redesign the ownership contract**:

- If the helper gets ownership of the stream, rename/document parameter ownership transfer and keep try-with-resources.
- If only borrowing, avoid closing a wrapper whose close propagates to the original stream, or let the caller manage the wrapper/Reader where appropriate.
- Better yet, for application resource-reading APIs, **pass Resource/Path** to the helper so the helper opens and closes its own stream.

Example API with clear ownership:

~~~java
public String readFirstLine(Resource resource)
        throws IOException {

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8))) {

        return reader.readLine();
    }
}
~~~

`Resource` is the descriptor passed by the caller; the method owns the stream it opens.

### 11.4. Do not return an already-closed stream

Wrong example:

~~~java
public InputStream openData(Resource resource)
        throws IOException {

    try (InputStream in = resource.getInputStream()) {
        return in;
    }
}
~~~

Upon returning, Java still exits the `try` block and calls `close()`. The caller receives a closed stream.

If the API's intent is **transferring stream ownership** to the caller, open and return it **without closing it inside this method**:

~~~java
public InputStream openData(Resource resource)
        throws IOException {
    return resource.getInputStream();
}
~~~

The caller takes responsibility:

~~~java
try (InputStream in = openData(resource)) {
    // Read data.
}
~~~

This style can still become hard to track if streams pass across many layers; prefer APIs that return processed results or accept a `Resource` and manage the stream within a clear scope.

## 12. Common Resource Ownership Table in Spring Boot

| Resource/API | Who usually manages close? | Notes |
|---|---|---|
| `Resource.getInputStream()` | Code calling to open the stream | Use try-with-resources within the read scope. |
| `Files.newBufferedReader(path, charset)` | Code calling to open the reader | Close BufferedReader. |
| `Files.lines(path, charset)` | Code creating the line Stream | Stream must be closed, typically with try-with-resources. |
| `BufferedReader.lines()` | Code owning the BufferedReader | Terminal operations do not close the reader automatically. |
| `MultipartFile.getInputStream()` | Code calling to open the stream | Read/close before the request and temp upload data expire. |
| `InputStream` received from caller | Depends on contract | Do not close automatically if only borrowed. |
| `HttpServletResponse.getOutputStream()` | Servlet container/framework | Do not close manually in ordinary controllers/services. |
| `Resource` returned via `ResponseEntity` | Spring MVC message converter | Framework reads/writes and manages the stream per response lifecycle. |
| JDBC `Connection` obtained from `DataSource` | Code borrowing the connection | Call `close()` after operation; with a pool this returns it to the pool. |
| Spring-managed `DataSource` bean | `ApplicationContext` | Do not close the pool per request; closed on context shutdown. |
| Client with `@Bean(destroyMethod="close")` | Spring `ApplicationContext` | Closed when the bean is destroyed per lifecycle. |
| `ResourceLoader` bean | `ApplicationContext` | Do not close after each `getResource()` call. |

These are **general rules**, not replacements for individual library contracts. In particular, a wrapper or adapter may transfer ownership differently from the API it wraps.

## 13. Reading Uploaded Files with MultipartFile

In a Spring MVC application, a controller can receive an uploaded file via **MultipartFile**:

~~~java
package com.example.demo.upload;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ImportController {

    @PostMapping("/imports/count-lines")
    public ResponseEntity<Long> countLines(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        long count = 0;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        file.getInputStream(),
                        StandardCharsets.UTF_8))) {

            while (reader.readLine() != null) {
                count++;
            }
        }

        return ResponseEntity.ok(count);
    }
}
~~~

In this example:

- `MultipartFile` represents the framework-handled upload.
- Code opens an InputStream via `getInputStream()`.
- Code closes the reader/stream it opened.
- No reference to the stream is retained for use after the request finishes.

### 13.1. Do not trust client-supplied charset or filename

An upload may contain:

- A non-UTF-8 file.
- A binary file masquerading as a CSV.
- Content exceeding size limits.
- A filename with path segments or unsafe characters.
- Malformed data or payloads harmful when opened by other software.

The controller above illustrates reading a UTF-8 file per **API contract**. Production applications need to:

1. Enforce upload size limits.
2. Validate media type, format, and data structure.
3. Enforce supported charsets.
4. Never use `originalFilename` directly as a write path.
5. Limit oversized field values or line counts.
6. Handle errors with appropriate API responses without leaking system paths.

### 13.2. MultipartFile.getBytes() vs getInputStream()

~~~java
byte[] content = file.getBytes();
~~~

`getBytes()` loads the whole content into a byte array; convenient for small files but memory-heavy for large uploads.

~~~java
try (InputStream in = file.getInputStream()) {
    // Read sequentially.
}
~~~

`getInputStream()` allows stream processing. Even so, whether uploading uses RAM or temp files during reception also depends on multipart resolver/container settings, not only on how the controller reads it.

### 13.3. Do not pass upload streams to background jobs without lifecycle management

Lifecycle bug example:

~~~java
public void scheduleImport(MultipartFile file) {
    executor.execute(() -> {
        try (InputStream in = file.getInputStream()) {
            // Process after the request has already ended.
        } catch (IOException ex) {
            // ...
        }
    });
}
~~~

The temporary file backing `MultipartFile` can be cleaned up by the framework/container after the request. A background task must not assume it stays around.

If async processing is needed, proactively **persist the upload into application-managed storage** under security policy, then pass a valid identifier or `Path` to the background worker. The worker opens and closes its own resource when processing.

## 14. Returning File Downloads with ResponseEntity<Resource>

A controller can return a `Resource` so Spring MVC reads it into the response automatically:

~~~java
package com.example.demo.download;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TemplateDownloadController {

    @GetMapping("/downloads/import-template")
    public ResponseEntity<Resource> download() {
        Resource source =
                new ClassPathResource("templates/import.csv");

        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"import.csv\"")
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .body(source);
    }
}
~~~

In this case:

- The controller does not open an InputStream itself.
- The controller returns a Resource descriptor.
- Spring MVC/the message converter opens and reads the data while writing the HTTP response.
- Stream lifecycle during response writing is managed by the framework via the corresponding converter.

This is an example of **transferring reading responsibility** to the framework; do not open the stream in try-with-resources and close it before the response is sent.

### 14.1. Do not return a shared InputStreamResource as a singleton

Risky example:

~~~java
@Bean
Resource exportResource() throws IOException {
    return new InputStreamResource(
            new FileInputStream("/tmp/export.csv"));
}
~~~

**InputStreamResource** wraps an already-opened InputStream and can typically only be consumed once. If a singleton bean serves multiple download requests:

- The first request may exhaust the stream.
- Later requests may hit EOF or a closed stream.
- The stream may be opened too early in the ApplicationContext lifecycle.
- Metadata operations like content length may consume the stream in implementations without re-read support.

For filesystem files, use `FileSystemResource`/`PathResource` which can open a new stream per request. For small in-memory data, `ByteArrayResource` may fit because it creates a new stream from the byte array. For packaged files, use `ClassPathResource`.

### 14.2. InputStreamResource is single-use

Example:

~~~java
InputStream in = resource.getInputStream();
InputStreamResource oneShot = new InputStreamResource(in);
~~~

`oneShot` normally represents that exact opened stream, not a re-readable file. Do not let it outlive the underlying stream, reuse it after a response converter consumes it, or assume metadata access is always safe.

Where the framework supports one-time streaming, `InputStreamResource` can still be useful, provided you understand its **single-use** contract and who is ultimately responsible for closing.

## 15. StreamingResponseBody and the Servlet Output Stream

When downloads are dynamically generated or large, Spring MVC provides **StreamingResponseBody**. It allows streaming data out without building a full `byte[]` in RAM.

Example copying a classpath file to the response:

~~~java
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class ExportController {

    @GetMapping("/exports/data")
    public ResponseEntity<StreamingResponseBody> export() {
        Resource resource =
                new ClassPathResource("data/export.csv");

        StreamingResponseBody body = output -> {
            try (InputStream in = resource.getInputStream()) {
                in.transferTo(output);
            }
            output.flush();
        };

        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"export.csv\"")
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .body(body);
    }
}
~~~

Ownership breakdown:

- **InputStream in** is opened inside the callback: the application must close it, handled via try-with-resources.
- **OutputStream output** is supplied by Spring MVC/servlet container: code writes and flushes as needed, **never calling `close()` directly**, because the framework/container orchestrates HTTP response lifecycle.
- **Resource resource** is a descriptor captured so the callback opens the stream when writing actually begins.

In real applications, configure executors for MVC async processing, concurrency limits, timeouts, and client-disconnect handling. Streaming large volumes of data does not eliminate the need to manage worker counts and server resources.

### 15.1. Why not wrap the servlet output in try-with-resources?

Pattern to avoid in ordinary controllers/services:

~~~java
try (OutputStream out = response.getOutputStream()) {
    // ...
}
~~~

The container manages the stream and response lifecycle. Closing the stream at the application layer can terminate the response prematurely, preventing downstream filters/handlers from running properly or causing container-dependent behavior.

Calling `close()` does not fail in every situation; the rule is to **let the proper owner decide when to close**.

## 16. Files.lines and Java Streams Also Need Closing

Java's Stream API often feels like an in-memory collection pipeline. Yet some Streams backed by file I/O hold **underlying system resources**.

Example:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public long countLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

**`Files.lines()`** opens a resource to read the file. Terminal operations like `count()`, `toList()`, or `forEach()` **do not automatically replace `Stream.close()`** for those I/O resources.

### 16.1. Incorrect case

~~~java
Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8);
long count = lines.count();
// Stream is never closed.
~~~

Repeated across many files, this can prevent file handles from being released promptly.

### 16.2. BufferedReader.lines() also requires clear ownership

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(
                     path, StandardCharsets.UTF_8)) {

    long count = reader.lines().count();
    return count;
}
~~~

Here try-with-resources closes **reader**, the resource owning the file handle. The stream's terminal operation does not close the reader by itself.

### 16.3. Files.walk and Files.find

Some filesystem traversal APIs return Streams backed by internal I/O resources:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

Check the contract of any API returning a Stream. A Stream created from a pure collection carries no file-handle closing duty; an I/O-backed Stream likely requires closing.

## 17. Do Not Let a Stream Outlive Its Resource Scope

Wrong example:

~~~java
public Stream<String> readLines(Path path)
        throws IOException {

    try (BufferedReader reader =
                 Files.newBufferedReader(
                         path, StandardCharsets.UTF_8)) {
        return reader.lines();
    }
}
~~~

The method returns a **lazy Stream** backed by a reader that was already closed at the end of the `try` block. When the caller invokes `count()`, `forEach()`, or `toList()`, reading the file can fail.

Better designs:

**Option A — Read/process completely inside the method**:

~~~java
public long countLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(
                         path, StandardCharsets.UTF_8)) {
        return reader.lines().count();
    }
}
~~~

**Option B — Return a Stream owned by the caller**:

~~~java
public Stream<String> openLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}
~~~

The caller must close it:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.forEach(System.out::println);
}
~~~

Option B requires clear API documentation because callers might forget to close. For business APIs, Option A or passing a callback executed within the stream scope reduces leak risks.

## 18. Asynchronous Processing: Do Not Close the Stream Before the Worker Reads

Suppose a task needs to run in the background:

~~~java
public CompletableFuture<Long> countAsync(Resource resource) {
    // ...
}
~~~

A common bug is opening the stream on the calling thread, scheduling background work, and closing the stream right away:

~~~java
public CompletableFuture<Long> broken(Resource resource)
        throws IOException {

    try (InputStream in = resource.getInputStream()) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return (long) in.readAllBytes().length;
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }
}
~~~

The calling thread can exit `try` and close the stream **before** the background worker even starts reading. The result is a stream-closed error or truncated data.

### 18.1. Open and close inside the worker itself

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.core.io.Resource;

public CompletableFuture<Long> countAsync(
        Resource resource, Executor ioExecutor) {

    return CompletableFuture.supplyAsync(() -> {
        try (InputStream in = resource.getInputStream()) {
            long total = 0;
            byte[] buffer = new byte[8192];
            int n;

            while ((n = in.read(buffer)) != -1) {
                total += n;
            }
            return total;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }, ioExecutor);
}
~~~

Here the worker opens the stream when execution starts and closes it right after finishing. A Resource descriptor can be passed across threads as long as the underlying resource remains available and supports opening a new stream.

Do not use this pattern verbatim with an `InputStreamResource` wrapping a single-use stream or a `MultipartFile` whose temporary backing storage may be deleted after the request. Ensure the source remains valid throughout the worker's read.

### 18.2. Choosing an executor for blocking I/O

Standard InputStream file reads are **blocking I/O**. When running asynchronously, bound task/connection counts to avoid spawning too many threads or exhausting file handles.

If the application uses Spring WebFlux/a reactive stack, never run blocking file I/O directly on the event loop. Use appropriate reactive resource handling or offload blocking work to a managed scheduler/executor.

## 19. Resource Beans and the ApplicationContext Lifecycle

Spring Boot manages the lifecycle of beans in the ApplicationContext. However, **not every resource used inside the application is automatically closed by Spring**.

Distinguish three cases:

| Case | Who is responsible |
|---|---|
| A bean created by Spring with a configured lifecycle/destroy callback | Spring destroys the bean when the context closes. |
| An `InputStream` opened by a service from a `Resource` per call | The service closes the stream after use. |
| A stream or client instantiated with `new` outside Spring's management | Owning code must manage its lifecycle. |

Example:

~~~java
@Component
public class ConfigReader {

    private final Resource resource =
            new ClassPathResource("data/config.txt");

    public String read() throws IOException {
        try (InputStream in = resource.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

**ConfigReader** is a Spring bean, and `Resource` is a descriptor held by the bean. Because each `read()` call opens a new `InputStream`, the method still must close it; Spring managing `ConfigReader` **does not close per-invocation InputStreams**.

### 19.1. Do not hold a shared InputStream in a singleton bean

Risky example:

~~~java
@Component
public class BrokenConfigReader {

    private final InputStream stream;

    public BrokenConfigReader() throws IOException {
        this.stream = new ClassPathResource(
                "data/config.txt").getInputStream();
    }

    public String readAgain() throws IOException {
        return new String(
                stream.readAllBytes(),
                StandardCharsets.UTF_8);
    }
}
~~~

Problems:

- The stream is opened early when the singleton bean initializes.
- The first read consumes all content; subsequent calls hit EOF.
- If multiple requests share it, they race over the same stream read position.
- Without an appropriate destroy callback, the stream can stay open far too long.
- If only a one-time read was needed, retaining the stream afterward is unnecessary.

Better design: a singleton holds a **Resource descriptor** or properly loaded immutable data, rather than holding a long-lived open stream unless there is a clear reason and explicit lifecycle.

### 19.2. Beans holding long-lived resources use destroy callbacks

Some objects are meant to live alongside the ApplicationContext, such as clients with connection pools, worker executors, or file watchers.

Example of a class managing its own executor:

~~~java
package com.example.demo.lifecycle;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ManagedReportWorker implements AutoCloseable {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @Override
    public void close() {
        executor.shutdown();
    }
}
~~~

Register as a Spring bean with a destroy callback:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {

    @Bean(destroyMethod = "close")
    ManagedReportWorker reportWorker() {
        return new ManagedReportWorker();
    }
}
~~~

When the ApplicationContext destroys the bean, Spring calls `close()` per the configured lifecycle. Calling `executor.shutdown()` alone does not guarantee all tasks have finished; if graceful shutdown must wait for in-flight work, `ManagedReportWorker` needs await-termination policies, timeouts, and handling for unfinished tasks.

Spring infers destroy methods like `close`/`shutdown` for many `@Bean` definitions when appropriate, though declaring it explicitly makes ownership clearer.

### 19.3. @PreDestroy for component-owned resources

For a component that opens a long-lived resource itself, you can use a lifecycle callback:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class LongRunningClientHolder {

    private final ManagedClient client = new ManagedClient();

    @PreDestroy
    public void shutdown() {
        client.close();
    }
}
~~~

`ManagedClient` is an illustrative type with a `close()` method. This example illustrates lifecycle only: when Spring manages the bean and the context shuts down gracefully, the callback runs to release resources.

If the JVM crashes or is forcefully killed, there is no guarantee `@PreDestroy` will run. Production systems still require resource limits, timeouts, and recovery mechanisms.

### 19.4. Do not close shared beans after each request

When Spring manages a shared `DataSource`, HTTP client, or managed executor, an individual request must not run:

~~~java
sharedClient.close();
~~~

after every operation, unless that client's contract explicitly defines it as a **per-request session/handle** owned by the caller.

Distinguish **clients/pools** that live with the application from **connections/streams/response handles** opened for individual operations.

## 20. Comparison Example: JDBC Connection and DataSource

JDBC illustrates ownership in Spring Boot very clearly.

**DataSource** is typically a bean configured by the framework or application, often a shared connection pool. Yet when code calls `getConnection()`, it receives a `Connection` that must be closed after executing SQL.

Example:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class ProductRepository {

    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int countProducts() throws SQLException {
        String sql = "select count(*) from products";

        try (Connection connection =
                     dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {

            result.next();
            return result.getInt(1);
        }
    }
}
~~~

Here:

- **DataSource**: shared dependency; never closed inside the method.
- **Connection**: handle acquired by the method, must be closed after use; with a pooled DataSource, `close()` normally returns the connection to the pool.
- **PreparedStatement** and **ResultSet**: JDBC resources created for the operation, closed via try-with-resources.

In applications using Spring transaction management, acquiring and managing connections may be handled by `JdbcTemplate` or the framework. When using `JdbcTemplate`, you usually do not manually open/close Connections. Follow the contract of your chosen API and transaction manager, and avoid mixing multiple connection-management styles.

**General lesson:** the framework managing a bean does not mean every handle borrowed from that bean skips closing.

## 21. InputStreamResource, ByteArrayResource, and FileSystemResource

Choosing the right Resource type prevents lifecycle and re-read bugs.

### 21.1. ByteArrayResource: re-readable, but holds byte[] in RAM

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

byte[] bytes =
        "Hello\n".getBytes(StandardCharsets.UTF_8);

Resource resource = new ByteArrayResource(bytes);
~~~

Typically, each `getInputStream()` call on a `ByteArrayResource` returns a fresh stream reading from the in-memory byte array.

Pros:

- Easy for small tests.
- Can be read multiple times.
- Does not depend on a file remaining on the filesystem.

Cons:

- All data resides in RAM.
- Creating one from very large data consumes significant memory.
- Unsuitable for turning every large upload/download into `byte[]`.

### 21.2. InputStreamResource: tied to an already-opened stream

~~~java
InputStream in = fileResource.getInputStream();
Resource oneShot = new InputStreamResource(in);
~~~

The advantage is forwarding an existing InputStream to an API accepting `Resource`. Keep in mind:

- Usually can be read only once.
- Do not assume it can be reopened after EOF.
- Do not let it outlive the underlying backing source.
- Watch out when frameworks compute content length or read metadata before actual consumption.
- Clarify who ultimately owns closing.

Do not use `InputStreamResource` as a "forever-reusable file" singleton if its backing source is a single InputStream.

### 21.3. FileSystemResource: opens the file per read

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Path path = Path.of("/opt/app/data/catalog.csv");
Resource resource = new FileSystemResource(path);
~~~

While the file exists, the Resource can open a new stream on each read. This pattern fits when data lives on the filesystem and must be read across multiple requests/runs.

It does not mean the file will exist forever: files can be deleted, have permissions changed, or be modified mid-read. Code must still handle IOException and data consistency per business rules.

### 21.4. ClassPathResource: suited to application-bundled files

~~~java
Resource resource =
        new ClassPathResource("templates/invoice.txt");
~~~

This fits reference data, templates, or static content packaged with the artifact. If documents need updates without rebuilding, an external file or updatable storage is better suited.

## 22. Charset at the HTTP Boundary and When Exporting CSV

In HTTP, payloads can be JSON, text/plain, CSV, or binary. **Content-Type** describes the media type and can include charset information for text formats that require it.

CSV response example:

~~~java
return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(
                "text/csv;charset=UTF-8"))
        .body(resource);
~~~

This header tells the client the CSV response is UTF-8 text. However, headers never fix bytes that were already encoded wrongly. If you wrote a String via `OutputStreamWriter` with a different charset, or the source file itself uses another encoding, the data will still be corrupted.

### 22.1. Align on one encoding contract at both ends

For a CSV export system, verify:

1. Which encoding turns Java Strings into bytes?
2. What does the HTTP response Content-Type/charset declare?
3. Which charset does the receiving client expect?
4. Does a specific consumer require a BOM for compatibility?
5. Is standard CSV escaping/quoting handled properly?

If a target system requires UTF-8 with a BOM, add the BOM per that contract. Never assume every UTF-8 CSV must have a BOM; many consumers do not need it and some parsers treat it as part of the first header character.

### 22.2. Use framework converters for JSON when appropriate

In Spring MVC, returning an object from `@RestController` lets Jackson and message converters serialize JSON. You do not need to manually build Strings and call `getBytes()` for every response.

Example:

~~~java
@RestController
public class GreetingController {

    @GetMapping("/greeting")
    public Map<String, String> greeting() {
        return Map.of("message", "Hello");
    }
}
~~~

Spring MVC uses the appropriate HTTP message converters to write the response. Avoid manually opening and closing the servlet output stream unnecessarily; let the framework manage encoding and response lifecycle.

If using WebFlux, reactive HTTP bodies and data buffers introduce additional rules. Never mix blocking InputStream logic directly into a reactive pipeline without managing schedulers and cleanup.

## 23. Avoid Buffering Everything in Memory Unnecessarily

Several convenient APIs have distinct behaviors:

| Reading approach | Characteristics |
|---|---|
| `Files.readString(path, UTF_8)` | Reads entire text into a String. |
| `Files.readAllBytes(path)` | Reads entire binary file into `byte[]`. |
| `InputStream.readAllBytes()` | Reads all remaining bytes of the stream. Does not close it. |
| `BufferedReader.readLine()` | Reads line by line, enabling streaming processing. |
| `Files.lines(path, UTF_8)` | Returns a lazy Stream of lines; must be closed. |
| `InputStream.transferTo(output)` | Copies sequentially; does not close either stream. |

Example copying a large resource to a destination file:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.Resource;

public void copyResource(Resource source, Path destination)
        throws IOException {

    try (InputStream in = source.getInputStream();
         OutputStream out = Files.newOutputStream(destination)) {

        in.transferTo(out);
    }
}
~~~

This copies raw bytes: **no charset conversion occurs**. Correct for binary files or copy operations where you must not alter encoding.

### 23.1. transferTo does not close streams automatically

**`InputStream.transferTo(OutputStream)`** transfers bytes from source to destination until EOF, but it does not replace closing either source or destination. In the example, the method opened both streams, so both are closed via try-with-resources.

If the destination is a servlet container output stream, the method must not close the destination as in the file-copy example; follow response ownership rules.

### 23.2. Writing files should account for partial output

If copying to a final destination fails halfway, the destination file may contain partial data. For critical data, you can:

1. Write to a temporary file in the same suitable filesystem region.
2. Finish closing/flushing the stream and verify the result.
3. Move the temporary file to the final path using a move matching the filesystem's atomicity guarantees.
4. Clean up the temporary file if the operation fails.

This policy concerns file consistency, **separate from closing streams**. Closing a stream releases resources and flushes relevant buffers; it does not magically make a partial write transactional.

### 23.3. Limit data when the source is untrusted

Streaming lowers the risk of buffering entire files in RAM, yet does not solve every risk. A huge or unending source can still tie up workers and disk space.

For uploads or network resources, also enforce:

- Maximum size limits.
- Reasonable timeouts.
- Concurrency limits.
- Format validation.
- Write-path protection.
- Task cancellation when clients disconnect or exceed limits.

Do not equate "using InputStream" with "safe for any file size".

## 24. Testing Charset and Closing with Unit Tests

Encoding and ownership behavior are ideal candidates for unit testing with controlled byte inputs. Tests do not need to boot an entire Spring Boot web application.

### 24.1. Creating a reader unit under test

~~~java
package com.example.demo.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public class Utf8ResourceReader {

    public String readAll(Resource resource) throws IOException {
        try (InputStream in = resource.getInputStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

For small files, this works cleanly for testing. If production needs to read very large files, replace with a Reader/buffered streaming approach.

### 24.2. Verifying UTF-8 preserves diacritics

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

class Utf8ResourceReaderTests {

    private final Utf8ResourceReader reader =
            new Utf8ResourceReader();

    @Test
    void preservesVietnameseCharacters() throws Exception {
        String expected = "Cà phê, Hà Nội, Đà Nẵng";
        Resource resource = new ByteArrayResource(
                expected.getBytes(StandardCharsets.UTF_8));

        assertThat(reader.readAll(resource))
                .isEqualTo(expected);
    }
}
~~~

This test proves the reader decoded the provided UTF-8 byte sequence accurately. It does not test BOMs, filesystem files, or upload APIs; test each scenario separately per contract.

### 24.3. Verifying the method closes the opened stream

You can create an InputStream that tracks `close()`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;

final class CloseTrackingInputStream
        extends ByteArrayInputStream {

    private boolean closed;

    CloseTrackingInputStream(byte[] data) {
        super(data);
    }

    @Override
    public void close() throws IOException {
        closed = true;
        super.close();
    }

    boolean wasClosed() {
        return closed;
    }
}
~~~

Test:

~~~java
@Test
void closesResourceStreamAfterReading() throws Exception {
    byte[] bytes = "Hà Nội".getBytes(StandardCharsets.UTF_8);
    CloseTrackingInputStream in =
            new CloseTrackingInputStream(bytes);

    Resource resource = new InputStreamResource(in);

    assertThat(reader.readAll(resource))
            .isEqualTo("Hà Nội");
    assertThat(in.wasClosed()).isTrue();
}
~~~

Here `InputStreamResource` is single-use, yet the test reads exactly once. The goal is verifying that **Utf8ResourceReader** closed the stream obtained from the Resource.

### 24.4. Testing filesystem files with @TempDir

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.FileSystemResource;

class FileResourceTests {

    @TempDir
    Path tempDir;

    @Test
    void readsUtf8FileThroughSpringResource()
            throws Exception {

        Path path = tempDir.resolve("sample.txt");
        Files.writeString(path, "Tiếng Việt",
                StandardCharsets.UTF_8);

        Utf8ResourceReader reader =
                new Utf8ResourceReader();

        assertThat(reader.readAll(
                new FileSystemResource(path)))
                .isEqualTo("Tiếng Việt");
    }
}
~~~

`@TempDir` avoids relying on a fixed working directory and cleans up files after the test.

### 24.5. Testing when a Resource does not exist

~~~java
@Test
void missingResourceReportsIOException() {
    Resource missing = new ClassPathResource(
            "data/does-not-exist.txt");

    assertThatThrownBy(() -> reader.readAll(missing))
            .isInstanceOf(IOException.class);
}
~~~

This snippet requires static importing `assertThatThrownBy` from AssertJ, plus imports for `Resource`, `ClassPathResource`, and `IOException`.

If the application defines a fallback when a file is missing, the test should verify that fallback **per business requirements** rather than blindly swallowing every IOException.

## 25. Diagnosing Charset Bugs and Resource Leaks

When troubleshooting a corrupted file or a gradually slowing service, separate the two cause categories.

### 25.1. Charset error category

Symptoms:

- Vietnamese text turns into garbled characters.
- `U+FFFD` replacement characters appear in data.
- CSV header fails column-name matching due to BOM.
- JSON/XML parser reports invalid text input.
- Output on a developer machine differs from server/container.

Diagnostic steps:

1. Which charset created the source file?
2. Which charset is code passing to `InputStreamReader`/`Files.readString`?
3. Is an intermediate layer performing an encoding conversion?
4. Is there a BOM or special newline convention?
5. Does HTTP `Content-Type` accurately describe the actual payload?
6. Did a framework parser already handle encoding while code decoded a second time?

Never fix encoding by randomly guessing charsets until text "looks right". Confirm the **source bytes** and decoding rules first.

### 25.2. Stream lifecycle error category

Symptoms:

- **Too many open files** or file-descriptor exhaustion.
- Files cannot be deleted/renamed in certain environments due to open handles.
- Connections to data sources stay open longer than expected.
- **Stream closed** in async tasks.
- First download request succeeds, subsequent ones return empty data.
- Memory grows from retaining many byte arrays or resources long-term.

Diagnostic steps:

1. Where does code call `getInputStream()`, `Files.lines()`, or `Files.newBufferedReader()`?
2. Is try-with-resources wrapping the usage scope?
3. Is a lazy Stream/Reader returned out of a closed scope?
4. Is `InputStreamResource` being reused?
5. Is an InputStream held in a singleton bean?
6. Was a servlet output stream or shared client closed by mistake?
7. Does a background task use temporary upload data after the request ends?
8. Are concurrency limits and timeouts set on I/O sources?

Not every memory or file-handle issue stems from a missing `close`; it can also stem from long-blocked tasks, single-use resources, or unnecessary `byte[]` retention. Thread dumps, metrics, and logs help narrow the cause.

## 26. Common Errors and Fixes

### 26.1. Reading Vietnamese text with the default charset

**Symptom:** text renders properly on one machine but garbles on another.

**Cause:** code uses `new InputStreamReader(in)`, `new String(bytes)`, or `getBytes()` without specifying a charset.

**Fix:** confirm the source data encoding and explicitly use `StandardCharsets.UTF_8` or the actual charset specified in the data contract.

### 26.2. Creating a File from a classpath resource

**Symptom:** works in IDE, fails with file-not-found when running an executable JAR.

**Cause:** code uses `src/main/resources/...` or `ClassPathResource.getFile()`, assuming resources are always filesystem files.

**Fix:** use `ClassPathResource.getInputStream()` or `ResourceLoader` to read classpath contents. Only use `File`/`Path` when the source genuinely sits on the filesystem.

### 26.3. Forgetting to close getInputStream()

**Symptom:** repeated file reads or resource downloads cause open file handles and connections to climb.

**Cause:** stream is opened outside try-with-resources or missed along exception paths.

**Fix:** open and close the stream in the same method, or transfer ownership explicitly to the caller/framework.

### 26.4. Thinking readAllBytes() closes the stream automatically

**Symptom:** concise code that leaks streams after obtaining `byte[]`.

**Cause:** confusing reading to EOF with calling `close()`.

**Fix:**

~~~java
try (InputStream in = resource.getInputStream()) {
    return in.readAllBytes();
}
~~~

For large files, avoid loading everything into RAM; use buffers or streaming.

### 26.5. Closing a stream before returning it

**Symptom:** caller receives an InputStream whose very first read reports stream closed.

**Cause:** returning the stream from inside try-with-resources.

**Fix:** either return processed results or return an open stream while documenting that the caller must close it.

### 26.6. Closing a borrowed InputStream through BufferedReader

**Symptom:** code calls a one-line reader helper and can no longer use the stream afterward.

**Cause:** helper wraps the stream in a reader and closes the reader, closing the caller's underlying stream too.

**Fix:** agree on whether the API takes ownership; prefer passing `Resource`/`Path` so the helper opens and closes its own stream.

### 26.7. Using InputStreamResource for multiple responses

**Symptom:** first download works, second returns an empty file or throws an exception.

**Cause:** reusing a single-use stream.

**Fix:** use `ClassPathResource`, `FileSystemResource`, or `ByteArrayResource` as appropriate so every request gets a valid readable source.

### 26.8. Closing the servlet response output

**Symptom:** response terminates early or the framework fails while processing response bodies/filters.

**Cause:** controller/service closes a stream owned by the container.

**Fix:** when the framework supplies `OutputStream` to `StreamingResponseBody`, write/flush as needed and let the framework manage closing.

### 26.9. Reading MultipartFile too late in a background thread

**Symptom:** background worker cannot find temporary upload file or the stream is invalid.

**Cause:** upload data follows the request lifecycle and may be cleaned up once the request completes.

**Fix:** copy the upload to application-owned storage before scheduling async processing; the worker opens and closes streams on the new source.

### 26.10. Forgetting to close Files.lines()

**Symptom:** program scans many files and hits OS resource errors.

**Cause:** assuming Stream terminal operations like `count()` release file handles.

**Fix:** wrap `Files.lines()`, `Files.walk()`, and other I/O-backed streams in try-with-resources.

### 26.11. Returning a lazy Stream from a closed Reader

**Symptom:** method returns a Stream cleanly, yet caller cannot iterate it.

**Cause:** reader closed on method return, while the stream reads data only when a terminal operation runs later.

**Fix:** execute the terminal operation inside the reader's scope, or return a Stream with explicit close ownership.

### 26.12. Holding an InputStream in a singleton bean

**Symptom:** first usage reads data, next hits EOF or concurrent requests race over stream position.

**Cause:** a stateful InputStream shared across requests.

**Fix:** hold a Resource descriptor; open a fresh stream per read. If caching small data, read once and store an appropriate data object instead of retaining the stream.

### 26.13. Forgetting to close a pooled JDBC Connection

**Symptom:** pool exhausts and requests block waiting for connections even though the database is healthy.

**Cause:** calling `getConnection()` without closing or mishandling JDBC transaction contracts.

**Fix:** use `JdbcTemplate`/Spring JDBC where appropriate, or try-with-resources for method-scoped connections/statements/result sets.

### 26.14. Closing DataSource after each query

**Symptom:** subsequent queries fail because the pool was shut down.

**Cause:** confusing per-operation `Connection` with the singleton `DataSource`.

**Fix:** close the borrowed connection; let `ApplicationContext` manage the pool bean.

### 26.15. Using streaming on huge files without task limits

**Symptom:** despite avoiding `readAllBytes` heap exhaustion, the app hangs due to too many concurrent I/O tasks or unbounded sources.

**Cause:** neglecting timeouts, size limits, and concurrency controls.

**Fix:** add quotas, timeouts, bounded queues, executor sizing, and cancellation handling.

### 26.16. BOM in CSV breaking header lookups

**Symptom:** header visually looks like **id** yet column mapping fails to find `id`.

**Cause:** `U+FEFF` sits at the start of the first line or the parser handles BOMs differently than expected.

**Fix:** inspect source bytes, choose a BOM-aware parser, or strip the BOM per format contract.

### 26.17. Ignoring IOException and silently losing data

**Symptom:** empty list returned even though reading the file actually failed.

**Cause:** catching `IOException` and returning a default without distinguishing an empty file from a broken read.

**Fix:** propagate errors to the appropriate layer, log non-sensitive causes, and only fall back when business rules allow.

## 27. Misconceptions to Avoid

**"InputStream knows my file is UTF-8."**  
No. InputStream only reads bytes; the charset is selected when decoding into characters.

**"Java defaults to UTF-8, so specifying a charset is unnecessary."**  
Do not rely on that at data boundaries. Explicit encoding contracts keep behavior consistent across JVMs, libraries, and environments.

**"Wrong charset only affects display, not data."**  
No. It can corrupt keys, signatures, comparisons, parsers, and persisted values.

**"ClassPathResource can always be converted to a File."**  
No. Resources inside an executable JAR may have no standalone filesystem file.

**"Resource objects need close() called after each use."**  
No. For standard Resource descriptors, you close the InputStream/Reader opened from the Resource.

**"resource.exists() guarantees it is readable."**  
No. Resources can change after checking, and reading can still throw IOException.

**"Reading all bytes closes the stream automatically."**  
No. EOF, `readAllBytes()`, or `transferTo()` do not replace `close()`.

**"Closing BufferedReader does not affect the underlying InputStream."**  
No. Closing a wrapper typically closes underlying streams/readers.

**"An API taking an InputStream must always close it itself."**  
No. Ownership contracts vary: the stream may simply be borrowed from the caller.

**"Streams returned by Files.lines() are plain collections."**  
No. They hold underlying I/O resources and must be closed.

**"Returning a Resource ensures every HTTP download can be read multiple times."**  
No. `InputStreamResource` is typically single-use; repeatability depends on the Resource type.

**"Spring manages the bean, so it closes any streams opened inside its methods."**  
No. Bean lifecycle and per-read InputStream lifecycle are separate scopes.

**"The controller opens and closes the response output stream."**  
False in typical Servlet models. The framework/container owns the HTTP response stream lifecycle.

**"A MultipartFile can be retained indefinitely after the request."**  
No. It may rely on temporary storage tied to the request lifecycle.

**"@PreDestroy always runs when the process exits."**  
No. Crashes, forced kills, or power loss can bypass callbacks.

**"Closing Connection and closing DataSource are the same thing."**  
No. Closing a pooled Connection usually returns it to the pool; `DataSource`/the pool is a shared context-managed resource.

**"Streaming guarantees the program will never run out of resources."**  
No. It avoids holding entire payloads in RAM, but you still need bounds on concurrent streams, network timeouts, and file handles.

## 28. Workflow for Choosing APIs and Deciding Where to Close

When reading or writing a resource in Spring Boot, follow these steps:

### Step 1: Identify the source

Is the source a classpath file, filesystem file, multipart upload, network URL, or in-memory byte array?

- Classpath → `ClassPathResource` or `ResourceLoader` with `classpath:`.
- Filesystem → `Path`/`Files` API or `FileSystemResource`.
- Upload → `MultipartFile` within the request lifecycle.
- Small bytes in RAM → `ByteArrayResource`.
- Existing stream → clarify ownership contract and single-read constraints.

### Step 2: Determine whether data is text or binary

- Binary → `InputStream`/`OutputStream` or an appropriate binary API.
- Text → `Reader`/`Writer` or `Files.readString`/`writeString` with an explicit charset.
- Structured formats like JSON, XML, or CSV → prefer a dedicated parser and configure its encoding.

### Step 3: Determine size and processing mode

- Small, well-bounded data → reading into a `String` or `byte[]` is fine.
- Large data → buffered streaming, chunk/line processing, and resource limits.
- Lazy Stream → keep the underlying source open until the terminal operation completes.

### Step 4: Determine ownership

~~~text
Did you open the resource yourself?
             │
       ┌─────┴──────┐
       │            │
      Yes           No
       │            │
       ▼            ▼
Close after use   Who owns it?
       │            │
       │     ┌──────┴─────────┐
       │     │                │
       │   Caller         Framework
       │     │                │
       ▼     ▼                ▼
try-with-resources     Follow lifecycle/API contract
~~~

If a method opens a stream from a Resource, it should close it. If a method returns an open stream, document that the caller must close it. If a stream belongs to the HTTP response/container, do not close it on the framework's behalf when ownership was not transferred.

### Step 5: Verify close timing

- Has reading/writing finished?
- Are there early returns or exceptions?
- Is an async callback still using the stream?
- Will a lazy Stream be consumed after the method returns?
- Does the source expire when the request ends?

### Step 6: Error handling and observability

- Never swallow `IOException` without reason.
- Preserve the cause chain for diagnostics.
- Never log sensitive files or full payloads inadvertently.
- Enforce timeouts, file sizes, concurrency limits, and cleanup.
- Test both Vietnamese diacritic charsets and missing-resource scenarios.

## Core Takeaways

**Charset** answers "which rule turns bytes into characters?". For UTF-8 text contracts, explicitly pass **`StandardCharsets.UTF_8`** when reading and writing. If the actual data uses another encoding, determine the true encoding rather than decoding with defaults.

**try-with-resources** is the standard way to close `InputStream`, `Reader`, `Writer`, and I/O-backed streams owned by your code, even when exceptions occur. Exhausting a stream does not close it; wrappers like `BufferedReader` can close underlying streams; `Files.lines()` needs closing; and lazy Streams must not outlive their data source.

**Resource lifecycle** follows ownership. Read files inside executable JARs with **`Resource.getInputStream()`**, without assuming a physical `File`. Code that opens a stream from a Resource closes it; Spring MVC/the servlet container usually manages response output; `ApplicationContext` manages long-lived bean resources via destroy callbacks, without closing short-lived streams opened inside service methods. Mastering these three principles prevents charset corruption, file-handle leaks, stream-closed errors, and hard-to-spot failures when moving from IDE to real deployments.
