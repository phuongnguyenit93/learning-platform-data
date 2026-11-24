# Serving Resources and handling Range requests in Spring WebFlux

## 1. Problem statement and goals

WebFlux applications often have to return images, PDFs, videos, audio files, data exports, or downloadable documents. Spring represents these sources with the **org.springframework.core.io.Resource** abstraction. The controller describes the Resource to return; WebFlux uses an HTTP message writer to write the content into the response.

For large files, clients often do not want to download the entire content in a single request. A browser, media player, or download tool can send a **Range** header to request a byte segment:

~~~http
GET /api/files/sample HTTP/1.1
Host: localhost:8080
Range: bytes=2-5
~~~

If the resource has 10 bytes, the server can return the four bytes at positions 2 through 5 with status **206 Partial Content** and the header **Content-Range: bytes 2-5/10**.

Spring WebFlux supports byte ranges per **RFC 9110**. With an annotated controller returning **Resource** or **ResponseEntity<Resource>**, a functional endpoint serving a Resource, and static resource handlers, Spring can handle Range automatically. For controllers, there are two conditions to remember: the Resource must not be an **InputStreamResource**; if returning **ResponseEntity<Resource>**, the initial status must be **200 OK** for the framework's Range mechanism to be applied.

After this lesson, you will be able to:

- Understand the Resource abstraction and choose an implementation suitable for the data source.
- Grasp the meaning of Range, Accept-Ranges, Content-Range, 206, and 416.
- Serve a Resource via an annotated controller, a functional endpoint, and a static resource handler.
- Understand the roles of HttpRange, ResourceRegion, ResourceRegionEncoder, and ResourceHttpMessageWriter.
- Test byte ranges with curl and WebTestClient.
- Combine Range with caching, ETag, Last-Modified, and HTTP conditions.
- Serve files safely, avoiding path traversal, data leaks, and excessive memory consumption.

## 2. The Resource abstraction in Spring

**Resource** is Spring's interface for accessing a resource. It provides operations such as checking existence, readability, getting the filename, length, modification time, and opening an InputStream. Thanks to this abstraction, the controller does not need to know whether the data resides in the classpath, filesystem, or a URL.

| Type | Data source | When appropriate |
| --- | --- | --- |
| **ClassPathResource** | Resource in the classpath or JAR | Sample files, documents packaged with the application, static resources |
| **FileSystemResource** | Path on the filesystem | Files stored in a data directory |
| **UrlResource** | URL or URI | Resources accessed via a URL through the Resource mechanism |
| **ByteArrayResource** | In-memory byte array | Small content already available in a byte[] |
| **InputStreamResource** | An already-opened InputStream | Read-once stream, unsuitable for Range |
| **PathResource** | java.nio.file.Path | Working directly with Path |

Example:

~~~java
Resource classpath = new ClassPathResource("files/manual.pdf");

Resource file = new FileSystemResource(
    "/srv/app-data/manual.pdf"
);

Resource bytes = new ByteArrayResource(
    "Hello WebFlux".getBytes(StandardCharsets.UTF_8)
);
~~~

This snippet requires importing the corresponding Spring and Java classes.

### 2.1. Choose a repeatable-read Resource

To process byte ranges, the framework must be able to access different segments of the same resource. **InputStreamResource** usually represents an already-opened stream and does not guarantee it can be re-read or seek to an arbitrary position. Therefore, Spring WebFlux does not support Range for this Resource type.

Prefer:

- **FileSystemResource** or **PathResource** for files on disk.
- **ClassPathResource** for files packaged in the application.
- **ByteArrayResource** for small in-memory content.
- A custom Resource implementation capable of opening new streams and supporting reading regions of data appropriately.

Do not create an InputStreamResource from a single stream and expect the framework to re-read it multiple times to serve Range requests. For large files, avoid loading the entire file into a byte[]; use a file-based Resource or a source that supports region reads.

### 2.2. Resource and InputStream are different

A Resource is a description of where to obtain data; it has not necessarily opened a stream yet. For example, ClassPathResource can open a new InputStream whenever needed. By contrast, an already-opened InputStream is a data-consuming state; once read to the end, the stream does not automatically rewind to the beginning.

This difference matters when:

- The framework needs to determine the content length.
- The client sends multiple Range requests for the same file.
- The server needs to read a byte region in the middle of the file.
- The client disconnects and sends a new request to resume downloading.
- The Resource is used concurrently across multiple requests.

### 2.3. Content length and filename

Resource has commonly used methods:

- **exists()**: whether the resource exists.
- **isReadable()**: whether the resource can be read.
- **contentLength()**: content length in bytes.
- **lastModified()**: last modified timestamp.
- **getFilename()**: filename if available.
- **getInputStream()**: opens a stream to read the content.

Length is essential for calculating byte ranges and Content-Range. If a Resource cannot determine its length, some Range operations may not work as expected. For downloadable files, use an implementation that provides a reliable size.

## 3. How do HTTP Range requests work?

A Range request lets a client request one or more segments of a representation. With byte ranges, byte indices start at **0** and the end position is **inclusive**.

Suppose the content is:

~~~text
0123456789
~~~

The resource has 10 bytes. Examples:

| Range header | Meaning | Requested bytes |
| --- | --- | --- |
| **bytes=0-4** | From byte 0 to byte 4 | 01234 |
| **bytes=2-5** | From byte 2 to byte 5 | 2345 |
| **bytes=5-** | From byte 5 to the end | 56789 |
| **bytes=-3** | The last three bytes | 789 |
| **bytes=0-1,8-9** | Two separate segments | 01 and 89 |

Important range forms:

- **Closed range**: bytes=100-199, specifies both start and end positions.
- **Open-ended range**: bytes=100-, takes from position 100 to the end of the representation.
- **Suffix range**: bytes=-500, takes the last 500 bytes.
- **Multiple ranges**: bytes=0-99,200-299, requests multiple segments in a single request.

Byte ranges are calculated on **bytes of the representation**, not Java character count. With UTF-8, one character can occupy multiple bytes; a Range can start or end in the middle of a multi-byte character. Therefore, do not interpret byte offsets as character indices.

### 3.1. Important headers

| Header | Direction | Role |
| --- | --- | --- |
| **Range** | Request | Client requests one or more byte segments |
| **Accept-Ranges** | Response | Server advertises supported range units, usually bytes |
| **Content-Range** | Response | Indicates the segment sent and the total representation length |
| **Content-Length** | Response | Body length of the current response |
| **Content-Type** | Response | Content type of the representation or multipart response |

**Accept-Ranges: bytes** is a signal telling the client that the server supports byte ranges. This is advisory information; a client can still send Range even if it has not received this header yet.

### 3.2. Status 200, 206, and 416

- **200 OK**: the server returns the entire representation, usually when there is no Range or the server does not apply Range.
- **206 Partial Content**: the server returns one or more segments per a valid, satisfiable Range.
- **416 Range Not Satisfiable**: none of the ranges in the range set can be satisfied, or the range is rejected per server policy.

Example response for bytes=2-5:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 2-5/10
Content-Length: 4

2345
~~~

**Content-Range: bytes 2-5/10** means the response contains bytes 2 through 5 of a representation totaling 10 bytes. Content-Length is 4 because the body of this response has only four bytes.

When a range cannot be satisfied, RFC 9110 recommends the server return Content-Range in the form **bytes */10** in the 416 response so the client knows the current size of the representation. Check the actual headers of the framework/server version you are using if the application needs to rely on this information.

### 3.3. Multiple ranges and multipart/byteranges

When the client sends:

~~~http
Range: bytes=0-1,8-9
~~~

The server can return a 206 response with Content-Type:

~~~http
Content-Type: multipart/byteranges; boundary=...
~~~

Each part in the multipart body has its own Content-Range header. In a multi-part response, Content-Range is not in the overall HTTP response headers; it is inside each body part.

The boundary is dynamically generated by the server, so you should not write tests that depend on a fixed boundary string. Check the media type and the content of the parts according to the contract.

### 3.4. Range applies only to GET

According to HTTP semantics, GET is the method defined for processing Range. The server must ignore Range if the method does not support range semantics. Do not use Range to paginate business lists; use query parameters/page tokens for pagination.

## 4. Spring WebFlux handles Range automatically

In WebFlux, the main mechanisms include:

- **HttpRange**: parses the Range header and represents a byte segment.
- **ResourceRegion**: describes a region of a Resource by start position and byte count.
- **ResourceRegionEncoder**: encodes one or more ResourceRegions.
- **ResourceHttpMessageWriter**: writes a Resource to an HTTP response; on the server side it supports writing one or more ResourceRegions for a Range request.

When a controller returns Resource or ResponseEntity<Resource>, WebFlux can recognize the Range header, convert it into ResourceRegions, and write the right segments of data. Static resource handlers also have this support.

Important conditions for an annotated controller:

1. The response body must be **Resource** or **ResponseEntity<Resource>**.
2. The Resource must not be an **InputStreamResource**.
3. If returning ResponseEntity<Resource>, the ResponseEntity status must be **200 OK**. The Resource writer will handle Range and adjust the response to 206 when appropriate.
4. Do not set status 206 yourself in the controller and expect the framework to continue parsing Range.

Correct example:

~~~java
@GetMapping("/files/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new ClassPathResource("files/manual.pdf");

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .body(resource);
}
~~~

When a client sends a valid Range, Spring can return a partial response automatically. There is no need to slice byte[] yourself or write a file-reading loop in the controller.

Error-prone example:

~~~java
@GetMapping("/files/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new InputStreamResource(openManualStream());

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .body(resource);
}
~~~

InputStreamResource is unsuitable for Range because the stream does not guarantee re-reading or byte-region access. Return a Resource capable of re-opening/re-reading such as FileSystemResource or ClassPathResource.

### 4.1. ResourceHttpMessageWriter

**ResourceHttpMessageWriter** is the HttpMessageWriter specialized for writing Resources. In server-side processing, the writer:

1. Sets the appropriate Accept-Ranges.
2. Reads the ranges from the request headers.
3. When there is no Range, writes the entire Resource.
4. When there is a single range, calculates the corresponding region and writes one ResourceRegion.
5. When there are multiple ranges, encodes the regions as multipart/byteranges.
6. When the range has invalid syntax or cannot be satisfied, finishes the response with status 416 per writer logic.

The writer also determines Content-Type and Content-Length when possible. If the response transport supports zero-copy and the Resource is a suitable file, the framework may use an optimized write path; otherwise it uses the encoder/DataBuffer.

You should not instantiate ResourceHttpMessageWriter yourself in a controller. WebFlux already configures the writer via the server codec configuration. Only customize the codec when there is a specific integration requirement and you have checked the impact on other Resource responses.

### 4.2. HttpRange and ResourceRegion at the API level

When you need to handle Range in a custom layer, you can use these APIs:

~~~java
List<HttpRange> ranges = request.getHeaders().getRange();

List<ResourceRegion> regions =
    HttpRange.toResourceRegions(ranges, resource);
~~~

This snippet requires importing **org.springframework.http.HttpRange** and **org.springframework.core.io.support.ResourceRegion**. The **getRange()** method parses the Range header; **toResourceRegions(...)** converts ranges into regions corresponding to the Resource.

These APIs are low-level tools. If you only want to serve a file, returning Resource directly is usually simpler and makes full use of WebFlux's writer. When handling it yourself, you must check parse errors, invalid ranges, range count, content length, and multipart response format.

## 5. Serving a Resource in an annotated controller

A controller can return Resource directly:

~~~java
@RestController
@RequestMapping("/api")
public class DocumentController {

    @GetMapping(
        value = "/manual",
        produces = MediaType.APPLICATION_PDF_VALUE
    )
    public Resource manual() {
        return new ClassPathResource("files/manual.pdf");
    }
}
~~~

Or use ResponseEntity<Resource> to control status and headers:

~~~java
@GetMapping("/manual")
public ResponseEntity<Resource> manual() {
    Resource resource =
        new ClassPathResource("files/manual.pdf");

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.inline()
                .filename("manual.pdf")
                .build()
                .toString()
        )
        .body(resource);
}
~~~

Use **inline** when you want the browser to try displaying the content; use **attachment** when you want to suggest downloading. The filename in Content-Disposition must be controlled and encoded properly, especially if it originates from user data.

### 5.1. Do not set Content-Length yourself when unnecessary

The Resource writer can determine the length from the Resource and set Content-Length. If the controller sets a wrong number itself, the response may be truncated, the client may wait for more data, or range metadata may become inconsistent.

Set Content-Length yourself only when the application actually knows the exact length of the representation to be sent. With Range, the Content-Length of 206 is the size of the segment sent, not the total file size.

### 5.2. Do not slice the Resource yourself before returning

If the controller reads a byte segment itself and returns a ByteArrayResource, subsequent Range requests will be calculated against the sliced byte array, no longer against the original file. This easily produces a wrong Content-Range or prevents the client from reassembling parts.

Return the original Resource for the writer to handle, unless the application is building a separate representation with its own semantics and metadata.

## 6. Serving a Resource with a functional endpoint

WebFlux functional endpoints also support Range when the handler returns a Resource.

~~~java
@Configuration
public class DocumentRoutes {

    @Bean
    RouterFunction<ServerResponse> documentRoutes() {
        return RouterFunctions.route()
            .GET("/functional/manual", request -> {
                Resource resource =
                    new ClassPathResource("files/manual.pdf");

                return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_PDF)
                    .bodyValue(resource);
            })
            .build();
    }
}
~~~

The important point is that the body of ServerResponse is **Resource** and the response is built with status 200. WebFlux can apply Range at the message-writing layer.

Do not read the entire file into byte[] before calling bodyValue if the goal is to serve a large file. Returning Resource lets the framework read the content with an appropriate mechanism.

## 7. Serving static resources

If the application only needs to serve static images, CSS, JavaScript, PDFs, or pre-packaged documents, you can use the static resource handler instead of writing a separate controller for each file.

Spring Boot WebFlux serves static resources by default from several classpath locations such as:

- /static
- /public
- /resources
- /META-INF/resources

You can customize the mapping with **WebFluxConfigurer**:

~~~java
@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
        ResourceHandlerRegistry registry
    ) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/")
            .setCacheControl(
                CacheControl.maxAge(1, TimeUnit.DAYS).cachePublic()
            );
    }
}
~~~

Place files at:

~~~text
src/main/resources/static/
    logo.png
    guide.pdf
    app.css
~~~

Request:

~~~http
GET /assets/guide.pdf
Range: bytes=0-1023
~~~

ResourceWebHandler handles finding the Resource, applying resolvers/transformers if configured, and writing the response via ResourceHttpMessageWriter. Static resources also support Range.

### 7.1. Cache-Control and Last-Modified

The static resource handler can set **Cache-Control** to instruct browsers and proxies to cache content. Spring can also evaluate **Last-Modified** based on the Resource. If the client sends a matching condition and the content has not changed, the server can return **304 Not Modified** without sending a body.

Cache duration must match how likely the content is to change. For files with versioned/hashed URLs, a longer cache duration is usually appropriate. For files updated at a fixed URL, a short duration or a validator is needed to avoid clients keeping stale content too long.

### 7.2. ResourceResolver and ResourceTransformer

The static resource handler supports:

- **ResourceResolver**: finds the Resource from the request path or changes how URLs map to resources.
- **ResourceTransformer**: transforms a Resource before serving, such as rewriting URLs in CSS or optimizing asset paths.
- **VersionResourceResolver**: creates versioned/hashed URLs for effective caching.
- **PathResourceResolver**: the default resolver that looks up Resources in configured locations.

Do not add custom resolvers without understanding how path checking and allowed locations work. A resolver must restrict access strictly to allowed directories/resources.

## 8. Complete example: WebFlux Resource endpoint and Range requests

This example uses **Java 17+**, **Spring Boot 4.1.2**, and Maven. The endpoint serves a text file of exactly 10 bytes so byte offsets are easy to observe. The file resides in the classpath and is a **ClassPathResource**, not an InputStreamResource.

Structure:

~~~text
resource-range-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/rangedemo/
    │   │       ├── RangeDemoApplication.java
    │   │       └── SampleResourceController.java
    │   └── resources/
    │       ├── application.properties
    │       └── files/
    │           └── sample.txt
    └── test/
        └── java/
            └── com/example/rangedemo/
                └── SampleResourceControllerTest.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>resource-range-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter WebFlux provides the reactive web stack and the default embedded server. Starter test provides JUnit Jupiter, Spring Test, and WebTestClient. Do not add the MVC starter to this example.

### 8.2. Sample file sample.txt

Create **src/main/resources/files/sample.txt** with the exact content:

~~~text
0123456789
~~~

The file must have exactly **10 ASCII bytes**, with no trailing newline at the end. This lets Content-Range and test results be calculated directly.

### 8.3. Application class

File **RangeDemoApplication.java**:

~~~java
package com.example.rangedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RangeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            RangeDemoApplication.class,
            args
        );
    }
}
~~~

### 8.4. Controller returning Resource

File **SampleResourceController.java**:

~~~java
package com.example.rangedemo;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class SampleResourceController {

    @GetMapping(
        value = "/sample",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<Resource> sample() {
        Resource resource =
            new ClassPathResource("files/sample.txt");

        if (!resource.exists() || !resource.isReadable()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Sample resource not found"
            );
        }

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body(resource);
    }
}
~~~

The controller returns **ResponseEntity<Resource>** with status 200. When a Range header is present, WebFlux handles it at the message writer layer and can change the status to 206. The Resource is a ClassPathResource, satisfying the condition of not using InputStreamResource.

Do not set status PARTIAL_CONTENT yourself in the controller. Do not read request.getHeaders().getRange() yourself in this example because the writer handles that.

### 8.5. application.properties

~~~properties
spring.application.name=resource-range-demo
server.port=8080
logging.level.com.example.rangedemo=INFO
~~~

### 8.6. Testing with WebTestClient

File **SampleResourceControllerTest.java**:

~~~java
package com.example.rangedemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class SampleResourceControllerTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToController(new SampleResourceController())
            .build();
    }

    @Test
    void returnsWholeResourceWithoutRange() {
        client.get()
            .uri("/api/files/sample")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("0123456789");
    }

    @Test
    void returnsRequestedByteRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=2-5")
            .exchange()
            .expectStatus().isPartialContent()
            .expectHeader()
                .valueEquals(HttpHeaders.CONTENT_RANGE, "bytes 2-5/10")
            .expectBody(String.class)
            .isEqualTo("2345");
    }

    @Test
    void supportsSuffixRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=-3")
            .exchange()
            .expectStatus().isPartialContent()
            .expectHeader()
                .valueEquals(HttpHeaders.CONTENT_RANGE, "bytes 7-9/10")
            .expectBody(String.class)
            .isEqualTo("789");
    }

    @Test
    void rejectsUnsatisfiableRange() {
        client.get()
            .uri("/api/files/sample")
            .header(HttpHeaders.RANGE, "bytes=20-30")
            .exchange()
            .expectStatus()
            .isEqualTo(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE);
    }
}
~~~

The test uses **WebTestClient.bindToController(...)** to check the controller and message-writing pipeline in a WebFlux environment. It confirms:

- No Range: 200 response and full content.
- bytes=2-5: 206 response, accurate Content-Range, and body containing only 2345.
- bytes=-3: 206 response with the last three bytes.
- bytes=20-30: 416 response because the file is only 10 bytes long.

### 8.7. Running the application and testing

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Fetch the entire file:

~~~bash
curl -i http://localhost:8080/api/files/sample
~~~

Body result:

~~~text
0123456789
~~~

Request bytes 2 through 5:

~~~bash
curl -i -H "Range: bytes=2-5" http://localhost:8080/api/files/sample
~~~

Important response lines:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Type: text/plain
Content-Range: bytes 2-5/10
Content-Length: 4

2345
~~~

Request the last three bytes:

~~~bash
curl -i -H "Range: bytes=-3" http://localhost:8080/api/files/sample
~~~

Body:

~~~text
789
~~~

Request two regions:

~~~bash
curl -i -H "Range: bytes=0-1,8-9" http://localhost:8080/api/files/sample
~~~

The response is 206 with Content-Type **multipart/byteranges**. Each part has its own Content-Range; the boundary is dynamically generated so it will differ across responses.

Request outside file size:

~~~bash
curl -i -H "Range: bytes=20-30" http://localhost:8080/api/files/sample
~~~

The response status is **416 Range Not Satisfiable**. RFC 9110 recommends Content-Range in the form **bytes */10** to describe the current length; verify the actual header per the deployed Spring version.

## 9. Serving files safely from the filesystem

In a real application, files often reside in a data directory or object storage. You should not concatenate client-supplied strings directly into a filesystem path:

~~~java
// Unsafe:
Path file = Paths.get("/srv/files/" + userInput);
Resource resource = new FileSystemResource(file);
~~~

A client can try path traversal such as **../../etc/passwd** or a path to data outside the intended directory. Plain string normalization is not enough if symlinks exist.

### 9.1. Prefer lookup by ID

A better API usually accepts a file ID:

~~~http
GET /api/documents/42
~~~

The service looks up metadata for document 42, checks whether the user has read permission, and then obtains the Resource from storage. The client must not decide the physical path.

### 9.2. If you must accept a filename, restrict it within root

Illustrative example:

~~~java
Path root = Paths.get("/srv/app-data").toRealPath();

Path candidate = root.resolve(fileName).normalize();

if (!candidate.startsWith(root)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}

Path realFile = candidate.toRealPath();

if (!realFile.startsWith(root) || !Files.isRegularFile(realFile)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}

Resource resource = new FileSystemResource(realFile);
~~~

This snippet requires importing java.nio.file.* and Spring types. Checking after **toRealPath()** helps detect symlinks pointing outside the root. The application still needs to handle race conditions per its threat model and restrict filesystem permissions; best of all is using an ID looked up from a metadata store.

### 9.3. Check authorization before returning the Resource

Range requests can generate many small requests for the same file. Every request must go through the same authorization policy as a request downloading the full file.

Do not check permissions only on the first request and then allow subsequent Range requests to access the file via a public URL if the resource needs protection. Check permissions on each request or use a download token mechanism with clear lifetime, scope, and permissions.

### 9.4. Control Content-Disposition and filename

If the filename comes from metadata or a user:

- Strip CR/LF and control characters.
- Do not use the filename as a filesystem path.
- Use Spring's ContentDisposition builder to encode the header.
- Choose inline or attachment depending on resource type and application policy.
- Do not put internal paths or bucket names into the response.

## 10. Cache, ETag, Last-Modified, and Range

Range requests often appear together with caching and resumable downloads. A client may already have part of old data and want to download the rest; the server needs to ensure the reassembled parts belong to the same representation.

### 10.1. Cache-Control

**Cache-Control** instructs browsers/proxies how to store and reuse the response. Example:

~~~java
CacheControl cache = CacheControl
    .maxAge(1, TimeUnit.HOURS)
    .cachePrivate();
~~~

For personal data or files requiring access control, consider **private** and an appropriate authentication policy. Do not set public caching on private content just to speed up downloads.

### 10.2. Last-Modified

A Resource can provide **lastModified()**. The WebFlux static resource handler evaluates Last-Modified by default and can return 304 Not Modified when the client sends a matching condition.

304 has no body; it tells the client the cached representation can still be used. For files updated at the same URL, Last-Modified helps avoid retransmitting the entire content when unchanged.

### 10.3. ETag

**ETag** is a validator representing a version of a representation. A client can send If-None-Match to ask whether the content has changed. If the validator matches under GET conditions, the server can return 304.

With custom controllers, you can use **ServerWebExchange.checkNotModified(...)** to evaluate conditional requests before writing the body. Conceptual example:

~~~java
String etag = "\"manual-v42\"";
long lastModified = resource.lastModified();

if (exchange.checkNotModified(etag, lastModified)) {
    return null;
}

// Continue returning the Resource if the request needs a body.
~~~

This is an illustrative snippet for a handler method with ServerWebExchange and Resource. In real code, keep the return type signature and handle a response already marked 304 according to the handler's API. Do not generate a fake stable ETag if the content can change without the validator changing.

### 10.4. Preconditions are evaluated before Range

Per RFC 9110, HTTP preconditions are evaluated before applying Range. If a conditional GET already qualifies to return 304, the server does not need to send 206 for part of an unchanged representation.

**If-Range** lets a client send Range alongside a validator. If the validator still matches, the server applies Range; if it does not match, the server sends the entire representation as a 200 response so the client can replace old data.

The WebFlux Range Requests page describes automatic handling for the Range header. If the application has strict requirements around **If-Range**, check and test the behavior of the exact Spring version, server, and cache/proxy deployed; do not assume a custom validator is applied without verifying.

### 10.5. ETag must represent the exact representation

If the same URL has different content by access permissions, language, content encoding, or query parameters, the ETag needs to represent the exact representation the client receives. Otherwise, caches can splice data wrongly or return content from another version.

For frequently changing resources, you can use a version in metadata or a content checksum. Do not compute the hash of an entire large file synchronously on the event loop on every request; compute it on save/update or pre-store appropriate metadata.

## 11. Performance and lifecycle notes

### 11.1. Avoid reading an entire large file into memory

Avoid:

~~~java
byte[] allBytes = Files.readAllBytes(path);
return new ByteArrayResource(allBytes);
~~~

This consumes memory proportional to the file size per request, which can cause the heap to spike sharply when many clients download concurrently.

Use **FileSystemResource** or a storage-backed Resource capable of reading by region. The WebFlux Resource writer will write the content with an appropriate mechanism.

### 11.2. Zero-copy when possible

With some server transports and a real-file Resource, the framework can use **zero-copy** to transfer data from file to socket with fewer copies between user space and kernel space. This is a runtime- and Resource-type-dependent optimization; do not assume every Resource response is zero-copy.

### 11.3. Client disconnect and cancellation

A client can cancel a request mid-download. The response-writing pipeline can receive cancellation and stop reading further. For a static file, stopping reads avoids transmitting data that is no longer needed.

If creating the file has side effects or the download triggers a business workflow, cancellation does not automatically roll back completed side effects. Distinguish file reading from file creation/export actions clearly.

### 11.4. Limiting the number of Ranges

A request can contain many small or overlapping segments. Creating and writing many regions increases CPU, buffers, and metadata. Use an up-to-date Spring version, limit request rate/header size per environment, and if handling Range yourself, cap the region count and reject overly complex inputs.

Do not write a loop that creates thousands of ResourceRegions and holds them all in memory unbounded. For very large files or media streaming, measure load and test with many concurrent clients.

### 11.5. Content-Encoding and byte offsets

Range is calculated on bytes of the chosen representation. If the response is compressed or transformed, byte offsets of the encoded representation may differ from offsets of the original file. Therefore, align how compression, caching, and Range are handled; do not apply Range on bytes of the original file and then alter the representation afterward.

## 12. Implementing Range manually: when is it needed?

For common use cases, return Resource so WebFlux handles it automatically. Implement manually only when there are special requirements such as:

- Files coming from a storage API that supports reading only by offset/length.
- Per-region authorization is needed.
- Supporting a dynamically generated representation is needed.
- Controlling If-Range policy or range limits by business rules is needed.
- Streaming from object storage that cannot be represented by a standard Resource is needed.

If implementing manually, handle everything thoroughly:

1. Apply Range only to supported methods.
2. Parse Range and check units.
3. Determine total representation length.
4. Normalize closed/open/suffix ranges.
5. Check whether the range is satisfiable and avoid overflow when computing offsets.
6. Decide 200, 206, or 416.
7. For a single range, set Content-Range and Content-Length accurately.
8. For multiple ranges, produce multipart/byteranges with a boundary and Content-Range per part.
9. Evaluate conditional headers and If-Range per RFC.
10. Handle cancellation, backpressure, timeouts, and storage read errors.
11. Do not let a single client request an unlimited number of regions.
12. Test reassembling byte segments to restore the exact original representation.

### 12.1. Using HttpRange for parsing

Example of reading ranges from a request:

~~~java
List<HttpRange> ranges = request.getHeaders().getRange();

List<ResourceRegion> regions =
    HttpRange.toResourceRegions(ranges, resource);
~~~

Handle **IllegalArgumentException** when the header is malformed or a range does not fit the Resource. The HttpRange API provides a parser and conversion to ResourceRegion, but producing a proper HTTP response still requires the corresponding writer or multipart handling code.

Do not just set status 206 and send arbitrary bytes. The client needs accurate Content-Range and representation length to know where the received segment sits.

## 13. Common mistakes and how to fix them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Range request still receives 200 for the whole file | Body is not a Resource, Resource is InputStreamResource, or response status is not 200 | Return Resource/ResponseEntity<Resource> and keep initial status 200 |
| Response has no Content-Range | Range was ignored or server returned full representation | Check Range header, status, Resource type, and writer |
| Response 416 | Range out of bounds or invalid header | Check total bytes, start/end positions, and syntax |
| Large file causes heap spike | Reading all into byte[] or ByteArrayResource | Use FileSystemResource or storage supporting region reads |
| Cannot get content length | Resource cannot determine size | Choose a Resource with reliable length or handle streaming with a dedicated contract |
| Range works on small files but fails on large files | Numeric types, buffers, storage, or request limits unsuitable | Check numeric types, region reads, timeouts, and memory |
| Resumed download splices wrong content | Representation changed between requests | Use ETag/Last-Modified/If-Range properly and keep URL/version stable |
| Multiple ranges return hard-to-read body | Response is multipart/byteranges with dynamic boundary | Parse each part; do not compare whole body to a fixed string |
| Another file is accessed via URL | Client controls path and there is path traversal/symlink | Use ID lookup, canonical path, authorization, and root boundary |
| Broken filename or header injection | Filename taken directly from input | Use ContentDisposition builder and filter control characters |
| Client does not receive new content | Cache-Control too long or wrong validator | Choose cache policy per content nature, update ETag/version |
| Compression makes Range offsets wrong | Byte ranges and compressed representation are misaligned | Define representation, content coding, and filter order clearly |
| Download keeps running after client disconnects | Read source or auxiliary task does not react to cancellation | Use a Publisher supporting cancellation and manage resource lifecycle |
| Hand-rolled Range cannot be reassembled by client | Missing proper Content-Range, Content-Length, or multipart boundary | Follow RFC 9110 and test with real clients |

## 14. Checklist before deploying a download endpoint

- Is the Resource repeatable-read and not an InputStreamResource?
- Does the controller return Resource or ResponseEntity<Resource> with initial status 200?
- Is Content-Type determined properly?
- Does Content-Disposition have a safe filename and appropriate inline/attachment?
- Do Range requests return proper 206, Content-Range, and Content-Length?
- Have suffix/open-ended/multiple ranges been tested if needed?
- Do unsatisfiable ranges respond with an appropriate 416?
- Does the Resource have reliable content length and last-modified?
- Is authorization checked on every request?
- Can the client not choose an arbitrary filesystem path?
- Are large files streamed rather than read entirely into the heap?
- Are Cache-Control and validators suitable for the sensitivity/update frequency of the file?
- Does Content-Encoding not throw off byte offsets?
- Are cancellation and timeouts handled?
- Is the Spring Framework version patched/up to date?
- Are there tests with WebTestClient and checks with curl?

## 15. Practice exercises

**Exercise 1 — Basic range:** Use a 10-byte file 0123456789. Send bytes=2-5 and explain why the body is 2345 and Content-Range is bytes 2-5/10.

**Exercise 2 — Suffix range:** Send bytes=-3. Calculate start and end positions from the Resource length.

**Exercise 3 — Open-ended range:** Send bytes=7-. Verify the response has only the last three bytes.

**Exercise 4 — Unsatisfiable range:** Send bytes=20-30. Observe status 416 and check Content-Range per your framework version.

**Exercise 5 — Multiple ranges:** Send bytes=0-1,8-9. Analyze Content-Type multipart/byteranges and Content-Range in each part.

**Exercise 6 — InputStreamResource:** Replace ClassPathResource with InputStreamResource. Observe that Range is no longer supported as before and explain Resource repeatability.

**Exercise 7 — Static resources:** Place a PDF in classpath:/static, configure ResourceHandlerRegistry, and test Range on the static URL.

**Exercise 8 — Cache:** Configure Cache-Control and test Last-Modified/conditional requests. Determine when the server returns 304.

**Exercise 9 — ETag:** Generate an ETag based on the document's version. Send If-None-Match and inspect the response when the representation has not changed.

**Exercise 10 — Path security:** Write an endpoint accepting a document ID, looking up metadata, and checking authorization. Try path traversal and symlink payloads.

**Exercise 11 — Large files:** Use FileSystemResource for a large file. Measure heap during concurrent downloads and compare against reading everything with Files.readAllBytes.

**Exercise 12 — Segment reassembly test:** Download multiple separate byte segments and reassemble them by Content-Range. Compare the checksum against the original file to prove no data is lost or reordered.

## 16. Key takeaways

**Resource** is the abstraction for WebFlux to serve files or binary content. **Range** lets clients fetch part of a representation by byte offset. When a controller returns a suitable Resource, Spring uses **ResourceHttpMessageWriter**, **HttpRange**, and **ResourceRegion** to handle byte ranges; the response can be 200, 206, or 416 depending on the request.

For Range to work automatically, use a repeatable-read Resource, avoid InputStreamResource, and keep the initial status of ResponseEntity at 200. For large files, use a filesystem/storage-backed Resource capable of region reads. For private content, check access permissions on every request and do not let clients control physical paths.

Combine Range with ETag, Last-Modified, and cache policies so clients resume downloading the right version. If handling Range manually, follow RFC 9110, limit region count, write accurate Content-Range, and test both cancellation and unsatisfiable range cases.

## 17. References

- Spring Framework Reference — WebFlux Range Requests: https://docs.spring.io/spring-framework/reference/web/webflux/range.html
- Spring Framework Reference — WebFlux Static Resources: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework Reference — WebFlux HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- Spring Framework API — Resource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html
- Spring Framework API — HttpRange: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpRange.html
- Spring Framework API — ResourceRegion: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/support/ResourceRegion.html
- Spring Framework API — ResourceHttpMessageWriter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ResourceHttpMessageWriter.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9110 — HTTP Semantics, Range Requests and Content-Range: https://www.rfc-editor.org/rfc/rfc9110.html
- MDN — HTTP Range Requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests
