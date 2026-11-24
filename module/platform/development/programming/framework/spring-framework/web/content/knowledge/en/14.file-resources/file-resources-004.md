# StreamingResponseBody, Resource, and Content-Disposition for Downloads in Spring MVC

## 1. Objectives and Scope

When building an API to download documents, CSV reports, images, or stored files, a Spring MVC controller must decide **where the data comes from**, **how the HTTP response body is written**, and **whether the browser should display or download the file**. Three tools are directly involved:

- **`Resource`**: Spring's abstraction for a data source such as a file, classpath resource, byte array, or stream; can be returned via `ResponseEntity<Resource>`.
- **`StreamingResponseBody`**: a callback for the application to write chunks into the response's `OutputStream`, suitable when generating or transferring large data without building the entire body on the heap.
- **`Content-Disposition`**: a response header instructing how to handle the content, notably `attachment` with a download filename or `inline` when appropriate.

After this lesson, you will understand Spring MVC's render/download flow, how to set `Content-Type`, `Content-Length`, and `Content-Disposition`, the difference between buffered and streaming downloads, HTTP Range scenarios, the Servlet stack's async mechanism, and how to test **status + headers + actual bytes** with MockMvc.

**Code sample versions:** Java 17+, Spring Framework 6.x, Spring Boot 3.x, **Spring MVC Servlet stack** (`spring-boot-starter-web`). These are not WebFlux examples: `Flux<DataBuffer>`, reactive backpressure, and `ServerResponse` belong to a different mechanism.

## 2. A Download Is Really an HTTP Response

A normal file download response might look like this:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Disposition: attachment; filename="sample.txt"
Content-Length: 17
X-Content-Type-Options: nosniff

Hello Spring MVC
~~~

Key points to understand:

1. **HTTP status** expresses the outcome: `200 OK` when returning the whole file, `206 Partial Content` for a valid fulfilled range, `404 Not Found` when no authorized resource exists, `403 Forbidden` when lacking permission, and `416 Range Not Satisfiable` when the requested range cannot be served under HTTP rules.
2. **`Content-Type`** describes the byte format. For example, `application/pdf`, `image/png`, `text/csv`, or `application/octet-stream` when representing generic binary data. This header is **distinct** from the filename.
3. **`Content-Disposition`** indicates `attachment`/`inline` handling and passes a filename if needed. Browsers may apply their own policies; the header does not guarantee a "Save As" dialog will always appear.
4. **`Content-Length`** is the byte count of the response representation **when known and accurately declarable**. For example, `Hello Spring MVC\n` in UTF-8 is 17 bytes, including the LF newline character.
5. The body can be bytes read from a file, generated from a report, or fetched from object storage. It does not have to be JSON; `ResponseEntity<byte[]>`, `ResponseEntity<Resource>`, and `ResponseEntity<StreamingResponseBody>` can all return files.
6. `HEAD`, HTTP Range, caching, proxies, reverse proxies, and content compression are additional concerns to address in the API contract.

For file responses, **never** wrap raw file bytes inside a JSON string hoping the browser will magically treat it as a file. If metadata must accompany the file, provide a separate metadata API or well-defined headers; avoid arbitrarily changing the body's media type.

## 3. `Resource`: Abstraction for Reading Bytes From a Source

The `org.springframework.core.io.Resource` interface extends `InputStreamSource` and provides capabilities such as:

| API | Role | Notes |
| --- | --- | --- |
| `getInputStream()` | Opens a stream to read the content | Callers must generally close the stream properly |
| `exists()` | Checks whether the resource exists | Does not replace access-control checks |
| `isReadable()` | Whether it is readable | Can change between check time and read time |
| `contentLength()` | Determines size if supported by the source | Some stream types may consume content to compute length |
| `getFilename()` | Gets the resource name if known | Never blindly trust client-supplied names |
| `getURI()`, `getURL()` | Resource location if supported | Not every resource has a filesystem path |
| `isFile()`, `getFile()` | Checks/accesses a real file when applicable | Resources inside a JAR are usually not standalone files |

Important implementations:

| Implementation | Data source | When to use |
| --- | --- | --- |
| `ByteArrayResource` | Byte array already in memory | Small content, test fixtures, pre-built in-memory files |
| `FileSystemResource` | File on the filesystem | Downloads from controlled server storage |
| `PathResource` | `java.nio.file.Path` | When code operates via `Path` |
| `ClassPathResource` | Resource packaged on the classpath/JAR | Downloading fixtures/assets distributed with the app |
| `UrlResource` | Accessible URL | Only with server-controlled URLs; avoid SSRF from user URLs |
| `InputStreamResource` | Open stream / stream source | **Requires special care** for one-shot streams and `contentLength()` |

A Spring MVC controller commonly returns:

~~~java
@GetMapping("/sample")
public ResponseEntity<Resource> sample() {
    Resource resource = new ClassPathResource("downloads/sample.txt");
    return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"sample.txt\"")
            .body(resource);
}
~~~

This is an **illustrative handler** requiring imports for `Resource`, `ClassPathResource`, `ResponseEntity`, `MediaType`, `HttpHeaders`, and `GetMapping`. The file `src/main/resources/downloads/sample.txt` must exist. In real applications, verify resource existence, permissions, and handle `IOException`; never let a missing file leak stack traces or internal paths.

When returning a `Resource`, Spring MVC typically uses **`ResourceHttpMessageConverter`** to read the source and write the response body. Depending on the resource/type/headers, Spring may supply metadata and support Range requests. This does **not** mean Spring automatically enforces file permissions or path traversal protection.

### Why Is `ByteArrayResource` Unsuitable for Very Large Files?

~~~java
byte[] wholeFile = Files.readAllBytes(path);
Resource resource = new ByteArrayResource(wholeFile);
~~~

This is an illustrative snippet inside a method with `Path path`. `Files.readAllBytes` loads the entire file onto the heap. If 200 users download a 200 MiB file concurrently, heap usage can grow uncontrollably. For files already on disk, `FileSystemResource`/`PathResource` typically avoids making an in-memory byte-array copy of the whole file. If data is **generated incrementally**, `StreamingResponseBody` usually expresses that intent more clearly.

## 4. `Content-Disposition`: attachment, inline, and Filenames

Common HTTP response headers:

~~~http
Content-Disposition: attachment; filename="report.csv"
~~~

or:

~~~http
Content-Disposition: inline; filename="diagram.png"
~~~

- **`attachment`**: hints to the user agent to treat the response as downloadable/saveable content, typically using `filename` as the suggested name.
- **`inline`**: allows the browser to display the content directly if capable and permitted by policy, such as images or PDFs. Not guaranteed to render in every environment.
- **`filename`** is only a **suggested name**, not a filesystem path, not an access control, and not a security value you can blindly trust.
- **`filename*`** with appropriate encoding helps transmit names containing Unicode characters, such as Vietnamese names. User agents may differ in how they prioritize `filename`/`filename*`.

### 4.1. Using Spring's `ContentDisposition` Builder

Instead of manually concatenating a header string with quotes and delimiters:

~~~java
String disposition = ContentDisposition.attachment()
        .filename("report.csv")
        .build()
        .toString();

return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
        .body(resource);
~~~

This is an **illustrative snippet inside a method** with a `Resource resource` variable; requires imports for `org.springframework.http.ContentDisposition`, `HttpHeaders`, and `ResponseEntity`. The builder produces valid header syntax and escapes characters in the filename per implementation rules.

For Unicode filenames, Spring Framework 6.x supports:

~~~java
String disposition = ContentDisposition.attachment()
        .filename("báo-cáo.csv", StandardCharsets.UTF_8)
        .build()
        .toString();
~~~

Per the Javadoc, `filename(String, Charset)` encodes the name according to RFC 5987, supporting UTF-8 and API-permitted charsets. For HTTP response `Content-Disposition` downloads, this can be very useful. **Do not apply this overload to `Content-Disposition` in `multipart/form-data` requests**, because RFC 7578 forbids using RFC 5987's `filename*` mechanism in multipart form uploads.

**Avoid interpolating raw user input into filenames:** filenames can contain quotes, CR/LF, path separators, or control sequences. The builder handles header escaping, yet the application must still restrict display names and dangerous characters, and always use **server-managed names/paths**. Never let a `filename` request parameter decide which file is read.

### 4.2. Never Pick `Content-Type` Arbitrarily From the Extension

For example, PDFs have MIME `application/pdf`; CSVs can use `text/csv`; unknown binary data can use `application/octet-stream`. Never blindly trust `MultipartFile.getContentType()`, filename extensions, or user-entered metadata from an earlier upload step.

If the server serves user-uploaded files, validate the actual file type and choose the appropriate `Content-Type`. For content that should not render inline, use `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and a storage/download origin with appropriate security policies. `attachment` or `nosniff` are defensive layers, not a guarantee that every browser stops every attack if the response carries dangerous active content.

## 5. `Resource`, Range, and Limitations of `StreamingResponseBody`

With an appropriate `ResponseEntity<Resource>`, Spring MVC can handle an HTTP `Range` request to return part of a file, enabling resumable downloads and media seeking. For example, a client requests `Range: bytes=0-4` on a 17-byte representation; a successful partial response typically looks like:

```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-4/17
Content-Length: 5

Hello
```

These are **byte offsets**, not Unicode character indices. `206` is only valid when the server actually serves the corresponding range; an unsatisfiable range can lead to `416 Range Not Satisfiable`. Caching conditions such as `ETag`, `If-Range`, and representation encoding must be considered for safe resumable downloads.

Key distinction for choosing a download API: a `Resource` can get HTTP Range support in Spring MVC through the appropriate message converters, whereas `StreamingResponseBody` is just a callback writing to `OutputStream` — **it does not automatically provide HTTP Range/206**. A one-shot `InputStreamResource` should likewise not be treated like a `FileSystemResource` that supports random-access byte ranges and repeatable size checks. Details on Range variants, multi-range responses, `ResourceRegion`, and `416` are covered in the dedicated lesson right after downloads in this chapter.

## 6. `StreamingResponseBody`: Writing Directly to OutputStream

Spring MVC provides the functional interface:

~~~java
@FunctionalInterface
public interface StreamingResponseBody {
    void writeTo(OutputStream outputStream) throws IOException;
}
~~~

This is an **abbreviated signature representation**, not the full Spring library source. A handler can return `StreamingResponseBody` or `ResponseEntity<StreamingResponseBody>`:

~~~java
@GetMapping("/download-stream")
public ResponseEntity<StreamingResponseBody> download() {
    StreamingResponseBody body = outputStream -> {
        for (int i = 1; i <= 3; i++) {
            byte[] bytes = ("row-" + i + "\n")
                    .getBytes(StandardCharsets.UTF_8);
            outputStream.write(bytes);
        }
        outputStream.flush();
    };

    return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                            .filename("rows.txt").build().toString())
            .contentType(MediaType.TEXT_PLAIN)
            .body(body);
}
~~~

This is an illustrative controller handler requiring imports and a Spring MVC app with async support. It sends:

~~~text
row-1
row-2
row-3
~~~

Byte order is deterministic because the callback writes sequentially in the loop. This is **not** an SSE stream and does not open an endless event connection; it is simply a file response written in chunks.

### 6.1. Strengths

- No need for a `ByteArrayOutputStream` to buffer an entire large file or CSV before sending.
- Can copy from an `InputStream` opened inside the callback, or generate report rows on the fly while writing.
- Can combine with `ResponseEntity` to set status, headers, MIME type, and filename **before writing the body**.
- Reduces heap pressure from holding all bytes in memory; well-suited for sequentially generated data or reads from large data stores.

### 6.2. What `StreamingResponseBody` Does Not Do

- It uses **Servlet MVC asynchronous request processing**, yet standard `OutputStream.write(...)` calls themselves can still be **blocking**. It does not magically turn the server into non-blocking reactive I/O or provide Reactor-style backpressure.
- It does not automatically implement HTTP Range, virus scanning, authentication, rate limiting, checksums, compression, or retry/resume.
- It does not automatically solve client disconnects, storage failures, connection timeouts, or thread pool saturation.
- It does not set `Content-Length` if you do not know the size beforehand. Responses may use chunked transfer in HTTP/1.1 or different framing in HTTP/2.
- It does not guarantee the browser immediately receives bytes after every `write`; buffers in the Servlet container, proxies, HTTP stack, and client can delay delivery.

### 6.3. Streaming an Existing File With `Files.copy`

If you have already authorized access and hold a safe `Path` pointing to an existing file:

~~~java
StreamingResponseBody body = outputStream -> {
    try (InputStream input = Files.newInputStream(authorizedPath)) {
        input.transferTo(outputStream);
    }
    outputStream.flush();
};
~~~

This snippet sits inside a method with a `Path authorizedPath` resolved from server metadata and already checked for permissions. `InputStream.transferTo` uses a reasonable buffer to copy the stream without loading the whole file into a byte array.

**Opening the input inside the callback** is critical because the callback may execute on an executor **after the controller method returns**. Never open an `InputStream` in a try-with-resources inside the handler method and close it before the streaming task starts.

Do not close the container-owned `outputStream` yourself in normal handlers; flush when appropriate and let the framework/container manage the response lifecycle.

## 7. Async Servlet, Thread Pool, and Processing Timeouts

When a handler returns `StreamingResponseBody`, Spring MVC uses async request processing to run the callback in a background task. The original request-handling thread can be returned to the container while the callback continues writing data on a thread from **`AsyncTaskExecutor`**.

For production, Spring MVC documentation recommends **explicitly configuring an appropriate executor**. Do not rely on a default executor ill-suited for real load if the system serves many long-running streaming requests. An example using Spring MVC Java config:

~~~java
@Configuration
public class DownloadAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public DownloadAsyncConfig(
            @Qualifier("downloadExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Bean(name = "downloadExecutor")
    public static ThreadPoolTaskExecutor downloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("download-");
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(60_000L);
    }
}
~~~

This class illustrates the full configuration structure; it requires Spring imports for `@Configuration`, `@Bean`, `@Qualifier`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor`, `WebMvcConfigurer`, and `AsyncSupportConfigurer`. Section 9 provides full imports for the runnable app.

**Note:** core/max pool 4/8, queue 64, and 60-second timeout are demo values, **not optimal defaults for every application**. Executor sizing must reflect storage throughput, transfer times, concurrent clients, memory, application-level backpressure/throttling, and reverse proxy timeouts. Servlet container/proxy timeouts may differ from the MVC-configured timeout.

If you have Spring Security, Servlet filters, or `ThreadLocal`-based MDC/tracing, verify async dispatch and **context propagation**. Never assume every thread-local is automatically copied to worker threads. Use Spring Security/Micrometer integration mechanisms and configure appropriate filter dispatch types.

### Errors After the Response Is Committed

Once response bytes start going out, status and headers may already be **committed**. If the file disappears mid-stream or the output stream throws an `IOException`, the server **cannot simply switch** from 200 to 500 with a clean error JSON. The client may receive a truncated response or a connection reset.

Therefore:

1. Check permissions, existence, metadata, content type, and size **before returning the body**.
2. Inside the callback, use `try/finally` or try-with-resources to close the **input source**.
3. Let `IOException` propagate to proper error handling/logging instead of swallowing it and claiming the file completed.
4. Clients must handle incomplete content, timeouts, and checksums when the use case demands it.
5. For dynamically generated reports with a high failure risk, consider generating the complete file/job in the backend first and then providing a download URL once ready.

## 8. Comparing `Resource`, `byte[]`, and `StreamingResponseBody`

| Criterion | `ResponseEntity<byte[]>` | `ResponseEntity<Resource>` | `ResponseEntity<StreamingResponseBody>` |
| --- | --- | --- | --- |
| Data form | All bytes already in memory | Resource abstraction | Callback writing in chunks |
| Memory for large files | High if building a whole `byte[]` | Depends on Resource: files can stream | Can keep memory low |
| Row-by-row report generation | Must buffer all bytes first | Can use a pre-generated resource | Very well suited |
| Serving a file from disk | Possible but suboptimal | `FileSystemResource`/`PathResource` usually fits | `Files.copy` when custom streaming logic is needed |
| `Content-Length` | Known from `byte[]` | Often known via Resource | Set only if computed accurately beforehand |
| Range requests | Not automatically applied like Resource | Supported by Spring MVC for suitable resources | App must handle manually if needed |
| Async callback | No | Not this streaming callback API | Yes, via Servlet async processing |
| Complexity | Low | Low–moderate | Higher: executor, timeout, stream lifecycle |
| Sensitive data | Must check permissions | Must check permissions | Must check permissions |

There is no "always best" choice. For files already in storage, returning a `Resource` can be simpler and more reliable. For CSV reports generated on the fly while writing the response, or data read sequentially from huge stores, `StreamingResponseBody` is often the cleaner choice.

## 9. Runnable Example: File Resource and Streaming CSV Report

The sample application has three endpoints:

- `GET /api/downloads/resource`: returns `Hello Spring MVC\n` as a text file using `ByteArrayResource`, with `Content-Disposition: attachment` and an exact `Content-Length`.
- `GET /api/downloads/stream`: generates a three-row CSV using `StreamingResponseBody`, sets `Content-Disposition`, and avoids buffering the entire report in RAM.
- `GET /api/downloads/inline`: demonstrates `Content-Disposition: inline` with a short text snippet, contrasting with `attachment`.
  
The demo uses deterministic bytes so output can be verified accurately without reading arbitrary local files. **For large production files, replace `ByteArrayResource` with `FileSystemResource`/`PathResource` or stream from controlled storage.**

Create a Spring Initializr project:

- Java: **17+**.
- Spring Boot: **3.x**.
- Build: Maven.
- Dependencies: **Spring Web**, **Spring Boot Starter Test**.
- Base package: `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/DownloadAsyncConfig.java
src/main/java/com/example/demo/DownloadController.java
src/test/java/com/example/demo/DownloadControllerTest.java
~~~

### 9.1. Bootstrap `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. Executor Configuration `DownloadAsyncConfig.java`

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class DownloadAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public DownloadAsyncConfig(
            @Qualifier("downloadExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Bean(name = "downloadExecutor")
    public static ThreadPoolTaskExecutor downloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("download-");
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(60_000L);
    }
}
~~~

`ThreadPoolTaskExecutor` has its lifecycle managed by Spring when registered via `@Bean`. The `@Bean` method is `static` to avoid circular initialization between the `@Configuration` instance and the executor dependency produced by the same configuration class. When the application context starts, Spring injects the executor instance into the constructor.

### 9.3. Download Endpoints in `DownloadController.java`

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/downloads")
public class DownloadController {

    private static final byte[] SAMPLE =
            "Hello Spring MVC\n".getBytes(StandardCharsets.UTF_8);

    private static final String NOSNIFF = "X-Content-Type-Options";

    @GetMapping("/resource")
    public ResponseEntity<Resource> resource() {
        Resource body = new ByteArrayResource(SAMPLE);

        String disposition = ContentDisposition.attachment()
                .filename("sample.txt")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(SAMPLE.length)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }

    @GetMapping("/stream")
    public ResponseEntity<StreamingResponseBody> stream() {

        StreamingResponseBody body = out -> {
            out.write("id,name\n".getBytes(StandardCharsets.UTF_8));

            for (int i = 1; i <= 3; i++) {
                String line = i + ",item-" + i + "\n";
                out.write(line.getBytes(StandardCharsets.UTF_8));
            }
            out.flush();
        };

        String disposition = ContentDisposition.attachment()
                .filename("report.csv")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(
                        MediaType.parseMediaType("text/csv;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }

    @GetMapping("/inline")
    public ResponseEntity<Resource> inline() {
        Resource body = new ByteArrayResource(
                "Preview\n".getBytes(StandardCharsets.UTF_8));

        String disposition = ContentDisposition.inline()
                .filename("preview.txt")
                .build()
                .toString();

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header(NOSNIFF, "nosniff")
                .body(body);
    }
}
~~~

**Important details:**

1. All three endpoints return bytes rather than converting data to JSON. `@RestController` tells Spring MVC to handle return values directly as the HTTP response; for `ResponseEntity<Resource>`, the appropriate converter reads the resource and writes bytes.
2. `SAMPLE` contains **17 UTF-8 bytes**, consisting of the 16 ASCII characters `Hello Spring MVC` plus one LF. Because the exact size is known, the resource endpoint sets `Content-Length: 17`.
3. `ByteArrayResource` in this sample holds small static data. In production with large files, swap in an appropriate stream/file source instead of loading large files into a `byte[]`.
4. `/stream` emits a CSV header then three rows; the callback writes line by line to the output. `Content-Length` is omitted because the demo does not precompute total size; the HTTP stack picks appropriate framing.
5. `ContentDisposition.attachment()` creates a suggested download filename. `ContentDisposition.inline()` lets the browser render the text when supported, without necessarily opening a save dialog.
6. `X-Content-Type-Options: nosniff` is a MIME-sniffing defense, not a replacement for validation or authorization.
7. The dedicated pool for `StreamingResponseBody` must be monitored as long-lived connections increase. In real apps, handle client disconnects and timeouts deliberately.

## 10. Testing With curl

Start from the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if no Maven Wrapper is present, use `mvn spring-boot:run` with Maven installed.

### 10.1. Downloading a `Resource`

~~~bash
curl -i http://localhost:8080/api/downloads/resource
~~~

Status **200 OK**, `Content-Type: text/plain`, `Content-Disposition` with `attachment; filename="sample.txt"`, `Content-Length: 17`, body:

~~~text
Hello Spring MVC
~~~

The Markdown block renders a single text line; **the actual bytes include a trailing LF**. For binary files, do not use `curl -i` to print the body directly in a terminal, because control bytes can corrupt terminal output; use:

~~~bash
curl -fL -D headers.txt   -o sample.txt   http://localhost:8080/api/downloads/resource
~~~

`-D headers.txt` saves headers, `-o sample.txt` saves bytes, and `-f` fails on HTTP 4xx/5xx. Without `-o`, `curl` writes the body to stdout.

### 10.2. Downloading a Streaming CSV Report

~~~bash
curl -i http://localhost:8080/api/downloads/stream
~~~

Expected response body:

~~~csv
id,name
1,item-1
2,item-2
3,item-3
~~~

`Content-Disposition` suggests the filename `report.csv`. A client can confirm the file is complete only after reading the entire body cleanly without errors. Never assume `Content-Length` is present on a streaming response.

### 10.3. Trying `inline`

~~~bash
curl -i http://localhost:8080/api/downloads/inline
~~~

Browsers may render `Preview` instead of forcing a download if they support `text/plain` and no other policy interferes. `curl` only displays bytes and **does not replicate browser display decisions**.

### 10.4. Trying Byte Range With Resource

~~~bash
curl -i   -H "Range: bytes=0-4"   http://localhost:8080/api/downloads/resource
~~~

With Spring MVC's range handling for `ByteArrayResource`, the response is typically **206 Partial Content**, `Content-Range: bytes 0-4/17`, and body `Hello`. If an endpoint, filter, or proxy alters bodies/headers, verify with real integration tests. `StreamingResponseBody` does not automatically provide this range behavior.

The shell commands above use `\` for line continuation on Linux/macOS/Git Bash. On Windows PowerShell, use `curl.exe` on one line or PowerShell's backtick continuation.

## 11. MockMvc: Checking Headers, Bytes, asyncDispatch, and Range

Create **`src/test/java/com/example/demo/DownloadControllerTest.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DownloadControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void resourceReturnsAttachmentAndExpectedBytes() throws Exception {
        mockMvc.perform(get("/api/downloads/resource"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.txt\""))
                .andExpect(header().longValue(
                        HttpHeaders.CONTENT_LENGTH, 17L))
                .andExpect(content().bytes(
                        "Hello Spring MVC\n".getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void streamReturnsCsvAsynchronously() throws Exception {
        MvcResult pending = mockMvc.perform(get("/api/downloads/stream"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"report.csv\""))
                .andExpect(content().string(
                        "id,name\n"
                        + "1,item-1\n"
                        + "2,item-2\n"
                        + "3,item-3\n"));
    }

    @Test
    void inlineResponseUsesInlineDisposition() throws Exception {
        mockMvc.perform(get("/api/downloads/inline"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "inline; filename=\"preview.txt\""))
                .andExpect(content().string("Preview\n"));
    }

    @Test
    void resourceHandlesSingleByteRange() throws Exception {
        mockMvc.perform(get("/api/downloads/resource")
                        .header(HttpHeaders.RANGE, "bytes=0-4"))
                .andExpect(status().isPartialContent())
                .andExpect(header().string(
                        HttpHeaders.CONTENT_RANGE, "bytes 0-4/17"))
                .andExpect(content().bytes(
                        "Hello".getBytes(StandardCharsets.UTF_8)));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

**Key test takeaways:**

- Assert **status** and **exact bytes**, not just `Content-Disposition`.
- Verify `attachment` and `inline` as distinct dispositions.
- With `StreamingResponseBody`, the controller initiates **async processing**. In MockMvc, wait and run `asyncDispatch(pending)` before asserting the complete response. Asserting right after `perform(...)` may see an incomplete body.
- The Range test verifies the resource can serve `206 Partial Content` for a valid byte slice in the sample setup.
- `@SpringBootTest` + `@AutoConfigureMockMvc` runs the MVC context with the project's actual executor configuration. If Spring Security is present, GET tests may require authentication according to configured rules.
- MockMvc does not prove network streaming throughput or identical behavior through reverse proxies/Servlet connectors; real large-file downloads need HTTP integration and performance tests.

## 12. Downloading Real Files From the Filesystem: Paths and Authorization

Real applications store files and serve requests like `GET /api/documents/{id}/download`. **Never accept an absolute path directly from the client.** Look up metadata by a server-managed ID, verify the current user has permission for the document, and then resolve the approved storage key.

**Illustrative example separate from the project in section 9**:

~~~java
@GetMapping("/documents/{id}/download")
public ResponseEntity<Resource> download(@PathVariable UUID id)
        throws IOException {

    DocumentRecord record = documentService.findAuthorized(id);
    Path file = storageService.resolveApprovedPath(record.storageKey());

    if (!Files.isRegularFile(file) || !Files.isReadable(file)) {
        return ResponseEntity.notFound().build();
    }

    Resource resource = new FileSystemResource(file);
    String header = ContentDisposition.attachment()
            .filename(record.safeDownloadName(), StandardCharsets.UTF_8)
            .build().toString();

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .contentLength(Files.size(file))
            .header(HttpHeaders.CONTENT_DISPOSITION, header)
            .header("X-Content-Type-Options", "nosniff")
            .body(resource);
}
~~~

**This is only an illustrative controller method:** `DocumentRecord`, `documentService`, and `storageService` must be defined; it is not a standalone Java file. Required imports include `UUID`, `Path`, `Files`, `IOException`, `Resource`, `FileSystemResource`, `ContentDisposition`, `StandardCharsets`, `ResponseEntity`, `MediaType`, `HttpHeaders`, `GetMapping`, and `PathVariable`.

Security notes:

1. **Check authorization before streaming.** Do not expose sensitive differences between 403 and 404 if policy requires hiding resource existence.
2. `storageKey` is server-managed with an allowlist/canonical path. `root.resolve(input).normalize().startsWith(root)` only checks **lexical paths**, which is insufficient against symlinks or races. On filesystems exposed to attacker-controlled symlinks, isolate storage and open files safely (canonical real paths, `SecureDirectoryStream` where appropriate, OS permissions).
3. **Never use `MultipartFile.getOriginalFilename()` directly as a file path** and never build `Content-Disposition` from raw filenames.
4. `Files.isRegularFile` followed by `Files.size` and opening the file can hit a **TOCTOU race**: the file can change between steps. In storage with concurrent writes, use versioning/locking/object immutability if size/ETag consistency must be guaranteed.
5. If metadata records a trusted verified MIME type, return that media type; otherwise, `application/octet-stream` with `attachment` and `nosniff` is a prudent default.
6. Log a `documentId`/request ID instead of full storage paths, tokens, or file contents.
7. For very large downloads from S3/GCS/object storage, consider **short-lived presigned URLs** when the security model permits, instead of proxying every byte through the Spring server; validate permissions before issuing URLs.

## 13. Do Not Use `InputStreamResource` Like a Regular `FileSystemResource`

`InputStreamResource` wraps an already-open stream and is typically **single-read**. An anti-pattern:

~~~java
InputStream input = Files.newInputStream(file);
Resource resource = new InputStreamResource(input);

// Avoid calling resource.contentLength() manually in this situation:
long length = resource.contentLength();
~~~

This is an illustrative snippet. Because computing `contentLength()` on a one-shot stream may consume the stream, the body may no longer have its bytes left to send. Spring Framework has special-case handling in some places for the exact `InputStreamResource` class, yet subclasses or manual length calls easily break.

The `ResponseEntity` documentation recommends that if you must use `InputStreamResource`, consider an **on-demand `InputStreamSource`**, and in custom subclasses control `contentLength()` so it does not consume the stream. In most cases:
- File on disk → `FileSystemResource` / `PathResource`.
- Small file in memory → `ByteArrayResource`.
- Sequentially generated/read stream with custom logic → `StreamingResponseBody` with the input opened inside the callback.

Never assume every `Resource` supports reopening, repeatable streams, or ranges identically. The underlying source's characteristics determine that.

## 14. `Content-Length`, Transfer-Encoding, HTTP/2, and Buffering

### Exact Size Known

For a byte array, `contentLength(bytes.length)` is exact. For a stable file via `Files.size(file)`, size is appropriate, though you must consider whether the file can be modified during download.

### Size Not Known Ahead of Time

For a CSV generated on the fly, there is no need to build the entire file just to learn `Content-Length`. Omit the header and let the container/proxy pick the appropriate HTTP mechanism. In HTTP/1.1, responses can use `Transfer-Encoding: chunked`; in HTTP/2, HTTP/1.1-style `Transfer-Encoding: chunked` does not exist.

**Never manually set `Transfer-Encoding`** from a controller as an application concern: the HTTP server owns framing. Never assign an estimated `Content-Length`; clients may receive corrupted/truncated files if actual bytes differ from the header.

### Multi-Layer Buffering

`OutputStream.flush()` pushes server-side buffers, yet does not guarantee bytes immediately traverse reverse proxies, CDNs, and browsers. Real streaming requires measuring at the client and configuring proxy buffering and timeouts appropriately. Many long-lived streaming requests occupy executor threads and network resources, requiring concurrency controls, rate limiting, and telemetry.

### Compression and Content Encoding

When responses are compressed (`Content-Encoding: gzip`), `Content-Length`, Range, and ETag must reflect the **encoded representation bytes**. Avoid declaring the uncompressed `Content-Length` if HTTP middleware transforms the payload on the wire. Test end-to-end whenever gzip is enabled at the proxy or container.

## 15. HTTP Caching, ETag, and Conditional Requests

Download APIs can support caching to save bandwidth when resources are non-sensitive or properly authorized/cached safely:

- `ETag` identifies a version of the representation.
- `Last-Modified` indicates modification time.
- `Cache-Control` governs cacheability and freshness lifetime.
- `If-None-Match` or `If-Modified-Since` can produce `304 Not Modified` when preconditions match.
- `If-Range` pairs with Range to ensure clients do not splice bytes from two different file versions.

Example metadata for a versioned public file:

~~~http
HTTP/1.1 200 OK
ETag: "report-v3"
Cache-Control: public, max-age=3600
Content-Disposition: attachment; filename="report-v3.csv"
~~~

This is only a **header example**: in production, `ETag` must genuinely track content/version. For sensitive files, `Cache-Control: private` or `no-store` is usually needed per threat model so shared caches/CDNs do not accidentally store private data.

Do not compute an ETag by reading an entire large file on every request just to hash it; store the content hash/version in metadata at upload/publish time. Never return 304 without properly evaluating HTTP preconditions.

## 16. Choosing Status Codes and Handling Download Errors

| Scenario | Usually appropriate HTTP status | Notes |
| --- | --- | --- |
| Resource exists, authorized for full read | 200 | Body contains file bytes |
| Valid byte Range fulfilled | 206 | Includes matching `Content-Range` |
| Client requests out-of-bounds range | 416 | Follow range and representation rules |
| ID does not exist or existence is hidden | 404 | Never leak filesystem paths |
| Resource exists but user lacks permission | 403 or 404 per policy | Authorize before sending bytes |
| Backend storage fails before response commit | 500/503 depending on cause | Consistent error response possible before commit |
| Stream fails after partial body sent | Connection may drop / truncated body | Status can no longer be changed cleanly |
| Backend report generation still running | 202 or job status endpoint | Do not try to stream an indeterminate response when a job is needed |

Ensure consistent exception handling; however, once bytes are partially sent, a `@RestControllerAdvice` cannot guarantee turning the outcome into a valid JSON error body. Critical download clients should verify total byte length, checksums/versions, or separate integrity metadata.

## 17. Common Pitfalls

### 17.1. "Empty" Download Despite Controller Returning 200

Often caused by closing the `InputStream` before the callback runs, consuming it via `contentLength()`, or container cleanup deleting an upload temp file before download. Check the source's lifecycle and where the stream is opened, and use `FileSystemResource`/on-demand streams properly.

### 17.2. Browser Displays PDF/HTML Instead of Downloading

`Content-Disposition` may lack `attachment`, `Content-Type` may be misconfigured, or browser policies may intervene. Use `ContentDisposition.attachment().filename(...)` when the product truly requires downloading.

### 17.3. Downloaded Filename Contains Garbled Characters

Never concatenate raw Unicode filenames into headers without encoding. Use `ContentDisposition.attachment().filename(name, UTF_8)` from Spring 6.x and test against target browsers. Choose validated display names and never treat the filename as a path.

### 17.4. `StreamingResponseBody` Works in Dev but Stalls Under Many Clients

The callback performs blocking I/O on the async executor. Too few executor threads or an oversized queue, slow storage, slow clients, or proxy buffering can stall throughput. Configure bounded executors, timeouts, metrics, and application-level backpressure.

### 17.5. MockMvc Stream Test Returns Empty Body

If the test omits `asyncDispatch`, it may assert the request **before the callback finishes**. Use `request().asyncStarted()`, `MvcResult`, and `asyncDispatch` before asserting bytes.

### 17.6. Assuming Every `Resource` Automatically Supports Resumable Downloads

False. It depends on the `Resource` implementation, converter setup, conditional requests, reverse proxies, and whether the source provides repeatable metadata. In particular, `InputStreamResource` does not replace `FileSystemResource` for Ranges.

### 17.7. Trusting a Client Filename to Read Server Files

Wrong. Never use `root.resolve(request.getParameter("path"))` or an uploaded `getOriginalFilename()` as a download path. Map server-managed IDs to storage keys and check ACLs/canonical paths/symlinks.

### 17.8. Trying to Switch the Response to 500 JSON After Stream Commit

Not reliably possible. Perform preflight checks before streaming, report operational failures via logs/metrics, and design clients to detect incomplete downloads.

### 17.9. Using `ByteArrayResource` for Every Large File

If bytes are loaded via `Files.readAllBytes`, memory grows with file size and concurrent requests. Choose file-backed `Resource` types or appropriate streaming.

### 17.10. Setting Inconsistent `Content-Length` and `Content-Encoding`

If gzip middleware alters the bytes, `Content-Length` must match the representation actually transmitted; when unsure, omit manual size headers. Test behind the reverse proxy rather than relying solely on MockMvc.

## 18. Review Questions

**1. How do `Resource` and `StreamingResponseBody` differ?**

`Resource` describes a data source for Spring's `HttpMessageConverter` to write to the response; `StreamingResponseBody` lets the application directly control chunked writes to `OutputStream` under async MVC processing.

**2. Does `Content-Disposition: attachment` guarantee the browser opens a Save As dialog?**

No. It is a disposition hint; browsers and user settings may auto-download to a folder or behave differently.

**3. Why should filenames be built via `ContentDisposition` builder?**

The builder generates valid header syntax and quotes/escapes the filename; the UTF-8 overload supports encoding Unicode names. Filenames still require validation and must never be used to select storage paths.

**4. Is `StreamingResponseBody` non-blocking WebFlux?**

No. It uses Servlet async processing to run the callback on an executor, while `OutputStream` writes remain blocking.

**5. Why can `InputStreamResource` cause bugs when computing length?**

Because the underlying stream is usually single-read; some operations computing `contentLength()` can exhaust the stream. Never call it blindly on non-repeatable sources.

**6. When does a client receive 206?**

When the server fulfills a valid Range request, returning only a slice of bytes with the matching `Content-Range`. Chunked streaming alone does not produce 206.

**7. Should `Content-Length` be set on a dynamically streamed CSV report?**

Only when the exact byte count is known beforehand and no transformation layer alters it. Otherwise, let the server choose HTTP framing.

**8. If an error happens after sending the first 100 KiB of a file, can you return 500 JSON?**

Not reliably. The response is likely already committed. Log the error, abort/cancel cleanly, and ensure clients detect incomplete downloads.

## 19. Production Checklist

- Choose `ResponseEntity<Resource>` when the source is an appropriate file/resource; choose `StreamingResponseBody` when generating or forwarding sequential data without buffering everything.
- Set `Content-Type` matching verified content; use the `ContentDisposition` builder for filenames and disposition.
- Declare `Content-Length` only when exact; test behind content encoding and proxies if present.
- Verify access permissions, metadata, file existence, and storage path **before starting the body**.
- For large stored files, avoid `Files.readAllBytes`/heap buffering and non-repeatable `InputStreamResource` when Ranges are needed.
- If resume/range is needed, pick a suitable `Resource`, and test `206`, `Content-Range`, `ETag`/`If-Range`, and invalid range responses.
- Configure async executor bounds, timeouts, quotas, metrics, and reverse-proxy buffering for `StreamingResponseBody`.
- Never serve dangerous active content inline unless required and properly sandboxed; use `attachment`, `nosniff`, authorization, and origin isolation as needed.
- Test **status + filename/headers + MIME + bytes**, and use `asyncDispatch` for streaming tests in MockMvc.
- For very large files or heavy download traffic, consider object storage/CDN/presigned URLs, immutable versions, and integrity verification.
- Never let client-controlled filenames dictate file read paths or unescaped headers.
- Design streaming error handling knowing responses cannot roll back after commit.

## Official References

- [Spring Framework 6.2 — Asynchronous Requests and StreamingResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — HTTP Range Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-range.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Spring Framework 6.2 — ContentDisposition.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ContentDisposition.Builder.html)
- [Spring Framework — Core Resource interface](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [RFC 9110 — HTTP Semantics (Content-Disposition, Range, caching)](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266.html)
- [OWASP — File Upload Cheat Sheet (related to stored files and downloads)](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
