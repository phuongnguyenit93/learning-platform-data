# Testing File Uploads, Downloads, Cookies, Sessions, and Static Resources in Spring Boot

A web API can return valid JSON yet still fail when a user uploads a file, a browser drops a cookie, a login session vanishes on the next request, or CSS/JavaScript fails to load from a packaged JAR. These bugs cannot be caught thoroughly by service unit tests alone. They sit at the intersection of **Spring MVC**, the **Servlet container**, **HTTP headers**, **client state**, the **session store**, the **resource handler**, the **reverse proxy**, and the **browser**.

This lesson belongs to **Web runtime testing**. The focus is **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet, JUnit 5, and MockMvc**. We will build a runnable project with:

- **Upload:** `POST /api/files` via `multipart/form-data`, storing small files in memory for testing.
- **Download:** `GET /api/files/{id}` returning exact bytes, content type, length, and `Content-Disposition: attachment`.
- **Cookie:** `POST /api/cookies/theme?value=dark` issuing `Set-Cookie`; `GET /api/cookies/theme` reading the cookie; a cookie-clearing endpoint.
- **Session:** `GET /api/session/visit` incrementing a counter in `HttpSession`; `POST /api/session/logout` invalidating the session.
- **Static:** `GET /assets/hello.txt` via `ResourceHttpRequestHandler`, without a hand-written `@GetMapping`.
- **Tests:** `MockMultipartFile`, `MockHttpSession`, assertions on `Set-Cookie`, bytes, status, static resources, plus a live HTTP test with `@SpringBootTest(RANDOM_PORT)` + Java `HttpClient`/`CookieManager`.

**Essential distinction:** `MockMvc` executes the Spring MVC pipeline using mock Servlet request/response objects; it **does not start a real HTTP server**, creates no browser cookie jar, and `multipart()` **does not exercise Tomcat's multipart parser**. A passing `MockMvc` test does not prove that the container, proxy, TLS, upload size limits, session cookies, or caching work properly over the network. Therefore, choose the right test layer for each behavior.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **upload** and **download**, request bodies, multipart field names, file bytes, HTTP statuses, and headers.
2. Write `MockMvcRequestBuilders.multipart()` tests with `MockMultipartFile` and recognize its simulation limits.
3. Compare downloaded file bytes, inspect `Content-Type`, `Content-Length`, `Content-Disposition`, `Cache-Control`, and 404 errors.
4. Test `Set-Cookie`, `Cookie`, and attributes `Path`, `Domain`, `HttpOnly`, `Secure`, `SameSite`, `Max-Age`.
5. Distinguish browser-sent cookies from server-managed `HttpSession`; test creation, reuse, invalidation, and timeouts.
6. Use `MockHttpSession` in `MockMvc` rather than expecting the mock container to manage `JSESSIONID` like Tomcat.
7. Verify static resources from `classpath:/static/`, default mappings, welcome pages, HTTP caching, and unauthorized private files.
8. Choose between `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc`, or `RANDOM_PORT` and understand the trade-offs.
9. Test upload limits at **two layers**: application validation and real multipart parser configuration.
10. Write positive and negative tests: empty/oversized files, invalid cookies, new/reused sessions, 404 resources, data leaks.
11. Analyze differences between `HTTP 200`, `206 Partial Content`, `304 Not Modified`, `400`, `403`, `404`, and `413`.
12. Incorporate security requirements for upload/download, cookies, sessions, and static resources into test plans.

## 2. Matrix: Which Layer Should Test What?

| Scenario | MockMvc | Real HTTP Server / RANDOM_PORT | Browser or Proxy E2E |
| --- | --- | --- | --- |
| Controller binds `file` field properly | Very suitable | Suitable | Usually not required |
| Uploaded body bytes handled properly | Suitable | Suitable | When client-specific |
| Multipart parser, boundary, container file size limit | **Insufficient** | **Required** | Required if passing through ingress |
| Download returns exact bytes + headers | Suitable | Suitable | When browser download UX matters |
| Browser interprets `Content-Disposition` filename properly | Test header | Test header | Needed across browsers/Unicode |
| `Set-Cookie` carries right flags | Direct header test | Real header test | Needed for browser policy |
| Client retains/resends cookie on next request | Not automatic; pass cookie in test code | Cookie-aware client can test | Browser is real behavior benchmark |
| `HttpSession` retains state across requests | Use `MockHttpSession` | Cookie jar + container/session store | Needed for SSO/auth flows |
| Session persistence across restarts/replica switches | Not proven | Requires real deployment & store | Needs cluster E2E |
| Classpath static asset can be served | Suitable with real context | Suitable with packaged JAR | Needed to check CDN/caching |
| `304` cache, `206` Range, gzip, reverse proxy | Can test some contracts | Needed to verify network behavior | Needed with CDN/gateway |
| Auth/CSRF and object-level authorization | Test with Spring Security | Test live | Test browser flow |

**No single test annotation replaces all layers.** The goal is not “every test must run the whole system,” but selecting the lowest layer capable of proving a contract while adding a few integration/E2E tests for container- or browser-dependent behaviors.

## 3. File Uploads via multipart/form-data

### 3.1. HTTP Multipart Structure

Browser submits form:

```html
<form action="/api/files" method="post"
      enctype="multipart/form-data">
  <input type="file" name="file">
  <button type="submit">Upload</button>
</form>
```

At the HTTP level, the equivalent request:

```http
POST /api/files HTTP/1.1
Content-Type: multipart/form-data; boundary=BOUNDARY123

--BOUNDARY123
Content-Disposition: form-data; name="file"; filename="example.txt"
Content-Type: text/plain

example content
--BOUNDARY123--
```

This is an illustrative wire format, not the exact byte body generated by a browser. The `boundary` is generated by the HTTP client library, and actual parts are separated per multipart syntax. Spring MVC binds the part with `name="file"` to `@RequestParam("file") MultipartFile file`.

Three easy mistakes:

- **Field name** `file` must match the controller parameter name. A client sending `name="avatar"` when the server expects `file` can cause 400 due to a missing required part/parameter.
- **Original filename** such as `../../secrets.txt` is **client-supplied** info; never use it directly as a storage path or trust it as safe.
- Part **`Content-Type`** can also be spoofed by clients. Checking extension/MIME headers is insufficient to ensure a file is safe; public uploads require allowlists, scanning, file signatures, and safe storage policies.

### 3.2. MockMultipartFile Does Not Mean Real Multipart Parsing Ran

In Spring Test:

```java
MockMultipartFile sample = new MockMultipartFile(
    "file",
    "sample.txt",
    "text/plain",
    "hello\n".getBytes(StandardCharsets.UTF_8)
);

mockMvc.perform(multipart("/api/files").file(sample));
```

`MockMultipartFile` builds a simulated `MultipartFile` with field name, filename, content type, and bytes. `multipart()` creates a `MockMultipartHttpServletRequest`; it **does not actually read/parse a raw multipart body through the servlet container**. Thus this test verifies mapping, validation, and service invocation, yet **does not** prove boundary parsing, disk-spill thresholds, or Tomcat's max upload size.

To prove requests from a real browser/`curl` work, include tests against a **real HTTP server** using a real multipart client.

### 3.3. What Should Upload Tests Assert?

- Success: status 201/200 per contract, response ID, and matching media type.
- Field name: send `file` properly; missing file yields 400 (may come from MVC binding).
- Empty file: reject/do not store if business rules forbid it.
- Oversized file: explicit app validation plus embedded servlet container body/part limits.
- Content: bytes not mangled by encoding, checksum matches if required.
- Unusual filenames: `../a.txt`, Unicode, control chars — must never dictate storage paths or response headers unsanitized.
- Spoofed MIME: do not trust `file.getContentType()` as proof of a clean file.
- Duplicates and concurrency: two uploads receive distinct IDs; never overwrite another tenant.
- Authorization: user A cannot download user B's file merely by guessing an ID.
- Cleanup: temporary files/storage do not linger indefinitely after failures.
- CSRF and authentication if browsers use session cookies.

### 3.4. Large Uploads and Memory

Never call `file.getBytes()` on multi-GB files in production; it copies the entire content into memory. In this small demo capped at 64 KiB, using byte arrays keeps tests clear. Real products must stream to disk/object storage and enforce quotas, timeouts, antivirus scanning, and cleanup. Never store user uploads in `src/main/resources/static`: that holds public build-time assets, not a private upload directory.

## 4. File Downloads: Verifying Bytes and HTTP Contracts

A server does more than return a byte array. Browsers/clients rely on:

| Header/Status | Meaning | What to Test |
| --- | --- | --- |
| `200 OK` | Response carries full representation | Exact body bytes |
| `Content-Type` | Content type | Never trust upload MIME; for unknown downloads use `octet-stream` |
| `Content-Length` | Length of transmitted representation | When length is known, matches bytes |
| `Content-Disposition: attachment` | Hints browser to download instead of render inline | Safe server-generated filename |
| `Cache-Control: no-store` | Do not cache private files in this sample | Not cached by shared caches |
| `X-Content-Type-Options: nosniff` | Reduces browser content-type sniffing | Present for user-uploaded files |
| `404 Not Found` | File absent or hidden | No internal paths leaked |
| `206 Partial Content` | Returns byte range per `Range` | `Content-Range` and exact slice bytes |
| `304 Not Modified` | Conditional request confirms unchanged representation | No full body |
| `416 Range Not Satisfiable` | Range invalid for representation | Does not wrongly return 200 with bad data |

**Note:** `206`/`416` relate to byte ranges and do not occur automatically for every return type. Spring MVC supports ranges for `Resource` or `ResponseEntity<Resource>` under framework conditions. `InputStreamResource` is unsuitable for this mechanism in cases noted in the range docs; use `ByteArrayResource` or a re-readable `Resource` when ranges are needed. Real downloads may have ranges handled independently by CDNs/object storage.

### 4.1. Never Use Client Filenames Directly in Content-Disposition

Counter-example:

```java
// Do not do this with unsanitized input:
String filename = multipartFile.getOriginalFilename();
```

Filenames can contain `../`, slashes/backslashes, quotes, control characters, or tricky Unicode. Use a generated/allowlisted name or proper sanitization and `ContentDisposition.attachment().filename(...)`, never manual header string concatenation from arbitrary input.

### 4.2. Byte Equality Differs from Text Equality

If a file contains NUL, `0xFF`, PNG images, or ZIP archives, testing `response.getContentAsString()` can corrupt bytes via encoding. Use:

```java
assertThat(result.getResponse().getContentAsByteArray())
    .isEqualTo(expectedBytes);
```

For large files, you can compare SHA-256 hashes and content lengths. Never assert only filename or status and assume the download is uncorrupted.

### 4.3. HEAD, Range, and Conditional Requests

- `HEAD` needs matching GET headers/status without a response body.
- `Range: bytes=0-3` expects `206` and the first 4 bytes when supported; `Content-Range` should be present.
- `If-Modified-Since` or `If-None-Match` can trigger `304` when the server provides matching `Last-Modified`/`ETag`.
- Without validators, `304` is not expected.
- `Cache-Control` is a policy; `Last-Modified`/`ETag` are validators; **do not equate** them.
- With CDN/proxy caching, verify at the real hop; `MockMvc` does not simulate proxies.

With Spring Boot's static resource handler, `Last-Modified` is usually supported from resource metadata; `If-Modified-Since` can yield `304`. A file packaged in a JAR has timestamps, second-level truncation, and behavior dependent on build/resource implementation; write contract tests against the received header rather than hardcoding timestamps.

## 5. Cookies: Set-Cookie Is a Response Header, Cookie Is a Request Header

Browser receives:

```http
Set-Cookie: theme=dark; Path=/; Max-Age=600; HttpOnly; SameSite=Lax
```

On subsequent same-origin requests, if cookie rules allow, browser sends:

```http
Cookie: theme=dark
```

**`Set-Cookie` and `Cookie` play different roles.** The server issues a cookie via `Set-Cookie`; the browser decides whether to store and resend it based on `Domain`, `Path`, `Secure`, `SameSite`, expiration, third-party cookie policies, and privacy modes.

### 5.1. Attributes to Test

| Attribute | Practical Meaning | What to Verify |
| --- | --- | --- |
| `Path=/` | Restricts URL path scope sending the cookie | Does the chosen path fit the app? |
| `Domain` | Host/subdomain scope | Do not set overly broad; host-only is safer |
| `HttpOnly` | `document.cookie` JS cannot read directly | Does not replace auth/CSRF; cookie still sent in HTTP |
| `Secure` | Browser normally sends only over HTTPS (localhost exceptions/details) | Production must enforce TLS and `Secure` |
| `SameSite=Strict/Lax/None` | Sending policy in cross-site contexts | Does not replace CSRF validation when needed |
| `Max-Age`, `Expires` | Cookie lifetime | Value 0 typically deletes it |
| Cookie value | Client-returned data | No unnecessary plaintext passwords/secrets |

**`HttpOnly` does not encrypt cookies.** **`Secure` does not prevent XSS across a site.** **`SameSite=Lax` does not replace CSRF tokens** for state-changing actions in applicable threat models. For cross-site `SameSite=None`, modern browsers normally require `Secure`; with CORS credentials, configure complete origin/cookie policies.

### 5.2. Why Does MockMvc Not Act as a Cookie Jar?

In `MockMvc`, each new request starts with a fresh mock request. If the first response returns `Set-Cookie`, the test has no automatic browser to store/resend it on the next request. To test a controller reading a cookie:

```java
mockMvc.perform(get("/api/cookies/theme")
        .cookie(new Cookie("theme", "dark")))
    .andExpect(jsonPath("$.theme").value("dark"));
```

This tests **the app with a test-supplied cookie**, not proving a browser will persist it when `Secure`/`SameSite`/`Domain` are set. Test real cookie jars with `HttpClient` or a browser against a live server.

### 5.3. Clearing Cookies Must Match Scope

When deleting, send `Set-Cookie` with the same **name**, **`Path`**, and matching **`Domain`** if used, plus `Max-Age=0`. If a cookie was set on `Path=/app` and cleared on `Path=/`, the browser may keep the old cookie. Tests should verify not just `Max-Age=0`, but also matching name/path/domain and subsequent browser state.

### 5.4. Cookies Are Not Sessions

A cookie can store a simple theme/language preference, yet **do not assume cookies themselves are server-side sessions**. Conversely, a `JSESSIONID` session cookie is normally just a **session identifier**; `HttpSession` state such as carts/visits/CSRF state resides in the container session store or Spring Session repository. Never ship raw Java session objects in cookies by default.

## 6. HttpSession: Testing Creation, Reuse, and Invalidation

Servlet `HttpSession` is where the server stores state tied to a session ID. Example:

```java
@GetMapping("/api/session/visit")
public Map<String, Integer> visit(HttpSession session) {
    Integer current = (Integer) session.getAttribute("visits");
    int next = current == null ? 1 : current + 1;
    session.setAttribute("visits", next);
    return Map.of("visits", next);
}
```

This is a **snippet**; the full controller is in section 10. First call on a new session returns `{"visits":1}`; subsequent calls on the same session return `{"visits":2}`. If the client omits the right session identifier, the server creates a new session and restarts at 1.

### 6.1. Testing with MockHttpSession

```java
MvcResult first = mockMvc.perform(get("/api/session/visit"))
    .andExpect(jsonPath("$.visits").value(1))
    .andReturn();

MockHttpSession session =
    (MockHttpSession) first.getRequest().getSession(false);

mockMvc.perform(get("/api/session/visit").session(session))
    .andExpect(jsonPath("$.visits").value(2));
```

This tests server-side state. **`JSESSIONID` `Set-Cookie` is not required in MockMvc**. Spring Framework docs note MockMvc has no real servlet container and by default lacks `jsessionid` cookies or network container dispatch semantics. Therefore, never write a `MockMvc` test demanding the container emit `JSESSIONID` automatically and treat its failure as a Spring session bug.

### 6.2. Invalidation

`session.invalidate()` marks the session invalid. With `MockHttpSession` you can assert `isInvalid()`. In a real browser/session client, logout may also require cookie deletion and security context cleanup, depending on the system. Do not equate “session invalidated” with “browser stops sending the old cookie,” because browsers may keep sending an old identifier until expiry/deletion; the server must reject it or start a fresh session for an invalid ID.

### 6.3. Timeouts and Distribution

- `server.servlet.session.timeout=15m` configures Servlet session timeout.
- Session timeout differs from cookie expiry; session cookies may lack `Max-Age` and expire when the browser session ends per browser policy.
- In multi-instance apps, an in-memory `HttpSession` on Pod A does not automatically appear on Pod B.
- With Spring Session Redis/JDBC, test the repository, serialization, TTL, session invalidation, and network failures.
- Session fixation protection on login, session ID rotation, and re-authentication belong to security framework/config responsibilities.
- Unit/MockMvc tests with `MockHttpSession` do not prove sessions survive restarts/pod failovers.

### 6.4. JSESSIONID Cookie and Authentication

`JSESSIONID` can be generated by the Servlet container once a real session is created. The cookie name can change via `server.servlet.session.cookie.name` or Spring Session/security configs. In the demo using defaults, the live test checks cookie persistence via `HttpClient.CookieManager`.

**Caution:** never log session IDs or put them into metric labels, URLs, or public support tickets. A session identifier acts as a bearer credential in many apps; anyone possessing it can hijack the session if no other defenses exist.

## 7. Static Resources: Routes, Classpath, and Caching

Spring Boot 3.3 (when MVC auto-configuration is intact) serves static content by default from:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`
- Certain locations under `ServletContext` root per config.

The default mapping is `/**`, typically handled by `ResourceHttpRequestHandler`. For instance, `src/main/resources/static/assets/hello.txt` is served at **`GET /assets/hello.txt`**, not `GET /static/assets/hello.txt`.

### 7.1. Do Not Use src/main/webapp for Executable JARs

Spring Boot docs emphasize that `src/main/webapp` is meant primarily for WAR packaging; when building an executable JAR, static files placed there may be ignored. Put assets in `src/main/resources/static` or another configured location so they are packaged inside the JAR.

### 7.2. Welcome Page and Route Precedence

An `index.html` at `classpath:/static/index.html` can be served at `/` as a welcome page when no higher-priority controller mapping exists. A `@GetMapping("/")` controller can override the welcome page per handler mapping order. Test the actual route rather than only checking the file on disk.

### 7.3. Public Static vs Private Uploads

**Never place user-uploaded files inside `classpath:/static/`** unless you intend everyone to fetch them by URL. In the demo, uploads live in memory and are served via a controller by ID; production requires object-level authorization before returning bytes. Static directories should contain only public assets (CSS, JS, images, icons) without environment secrets, backups, or customer data.

### 7.4. Testing Static Bytes and 404

With `@SpringBootTest + @AutoConfigureMockMvc`, Spring Boot configures MVC mappings/resource handlers like the real app (barring mock container differences):

```java
mockMvc.perform(get("/assets/hello.txt"))
    .andExpect(status().isOk())
    .andExpect(content().string("asset-ok\n"));

mockMvc.perform(get("/private-note.txt"))
    .andExpect(status().isNotFound());
```

In the demo, `private-note.txt` lives at `src/main/resources/private/private-note.txt`, **outside** default static resource locations. The 404 test verifies it is not served by the default resource handler. Still, security scans should check for secret files, archive/backup extensions, and special paths; testing one path does not prove all paths are safe.

### 7.5. Cache-Control, Last-Modified, and 304

For rarely changing public assets, you can configure:

```properties
spring.web.resources.cache.period=60s
spring.web.resources.cache.use-last-modified=true
```

This enables caching resources for 60 seconds and using `Last-Modified` metadata when available. `Cache-Control` and `Last-Modified` serve two distinct purposes:

- `Cache-Control: max-age=60` guides cache freshness.
- `Last-Modified` paired with `If-Modified-Since` enables conditional GET; when unchanged, it can return `304` without the full body.

When using hash-based asset versioning, you can configure resource chains; content-hashed filenames suit longer cache periods. Conversely, private uploads/downloads need the opposite policy, like `Cache-Control: no-store`. Never apply long caching globally and accidentally cache personal documents.

### 7.6. Static Resources Should Not Be Tested Like Business Controllers

`@WebMvcTest(SomeController.class)` is a narrow slice that may omit full resource configs or beans present in the full app. When verifying classpath static files and auto-configuration, a **full application context with MockMvc** usually fits better than a controller slice. For JAR packaging/CDN behavior, add `bootJar` + real HTTP server + browser/edge tests.

## 8. Complete Spring Boot 3.3, Java 17+ Project

We build a small yet complete application for hands-on practice. It **omits Spring Security** to keep focus on transport/session/resource testing; in production every file/session endpoint requires authentication, authorization, quotas, CSRF, and monitoring.

### 8.1. Gradle Build

Generate from [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot **3.3.x**, Gradle/Groovy, Spring Web. To pin a specific 3.3 release like `3.3.13`, update the Gradle file generated by Initializr:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is the core `build.gradle` with plugins/dependencies and Java 17. Use the Gradle Wrapper supplied by Initializr; do not force Spring MVC/Jackson/JUnit versions out of sync with the BOM. On Spring Boot 4.x, packages and test auto-configuration names may differ; this lesson intentionally pins **Boot 3.3.x**.

`settings.gradle`:

```groovy
rootProject.name = 'runtime-files-test'
```

Directory structure:

```text
build.gradle
settings.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      RuntimeFilesTestApplication.java
      FileStore.java
      FileController.java
      CookieSessionController.java
    resources/
      application.properties
      static/index.html
      static/assets/hello.txt
      private/private-note.txt
  test/
    java/demo/
      WebRuntimeMockMvcTest.java
      WebRuntimeHttpIntegrationTest.java
```

All Java classes reside in package `demo` so Spring Boot component scanning finds controllers/services cleanly. `src/main/resources/private/private-note.txt` exists specifically to test that the `private` directory is not inadvertently served.

### 8.2. RuntimeFilesTestApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeFilesTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RuntimeFilesTestApplication.class, args);
    }
}
```

### 8.3. FileStore.java — Storing Small Files in Memory

```java
package demo;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class FileStore {

    private static final int MAX_BYTES = 64 * 1024;

    private final ConcurrentMap<String, byte[]> files =
            new ConcurrentHashMap<>();

    public String save(MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "File must not be empty");
        }

        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.valueOf(413),
                    "File too large");
        }

        byte[] bytes = file.getBytes();

        if (bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.valueOf(413),
                    "File too large");
        }

        // Do not trust originalFilename as a filesystem path.
        String id = UUID.randomUUID().toString();
        files.put(id, bytes.clone());
        return id;
    }

    public byte[] load(String id) {
        byte[] value = files.get(id);

        if (value == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "File not found");
        }

        return value.clone();
    }
}
```

Save at `src/main/java/demo/FileStore.java`.

This is a **memory-only lab**. `ConcurrentHashMap` provides basic thread-safe map operations across requests; `UUID` generates harder-to-guess IDs than sequential numbers, yet is **not authorization**. Files are copied into RAM with a 64 KiB cap and are **lost on restart**. Production uses disk/object storage with quotas, file-type validation, antivirus, multi-tenant permissions, TTL, and cleanup. Never use `file.getOriginalFilename()` as a storage key/path and never store private data inside a static directory.

Why check both `file.getSize()` and `bytes.length`? `getSize` rejects early at the application layer; after reading bytes, we still verify the actual length. Neither replaces limits on the servlet multipart parser/gateway because the upload may already consume resources before reaching the service.

### 8.4. FileController.java — Upload and Download

```java
package demo;

import java.io.IOException;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class FileController {

    private final FileStore store;

    public FileController(FileStore store) {
        this.store = store;
    }

    public record UploadedFile(String id) {
    }

    @PostMapping(path = "/api/files",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public UploadedFile upload(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        return new UploadedFile(store.save(file));
    }

    @GetMapping("/api/files/{id}")
    public ResponseEntity<Resource> download(
            @PathVariable("id") String id) {

        byte[] bytes = store.load(id);

        ContentDisposition disposition =
                ContentDisposition.attachment()
                        .filename("download.bin")
                        .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        disposition.toString())
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(bytes.length)
                .body(new ByteArrayResource(bytes));
    }
}
```

Notable points:

- Upload responds `201 Created` with JSON `{"id":"..."}`; JSON field name comes from the record accessor.
- `MultipartFile` binds from field name `file`, not arbitrary file field names.
- Download returns `ResponseEntity<Resource>` + `ByteArrayResource`, allowing Spring MVC to support range handling for `Resource` when conditions hold. Avoid `InputStreamResource` when testing resumable downloads.
- Server-generated `Content-Disposition` uses fixed name `download.bin`, never arbitrary original filenames.
- `application/octet-stream` and `nosniff` suit untrusted or unknown file types.
- `Cache-Control: no-store` avoids caching uploaded documents in the demo; public/immutable files need different caching strategies.
- No authorization in the demo. Production **must** check owner/tenant permissions before `store.load(id)`; UUIDs do not replace access control.
- `Content-Length` on a full 200 equals the byte length; during Range 206 responses, Spring adjusts headers for the partial representation.

### 8.5. CookieSessionController.java

```java
package demo;

import java.time.Duration;
import java.util.Map;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CookieSessionController {

    @PostMapping("/api/cookies/theme")
    public ResponseEntity<Map<String, String>> setTheme(
            @RequestParam("value") String value,
            HttpServletRequest request) {

        if (!"dark".equals(value) && !"light".equals(value)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "theme must be dark or light");
        }

        ResponseCookie cookie = ResponseCookie
                .from("theme", value)
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .maxAge(Duration.ofMinutes(10))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .cacheControl(CacheControl.noStore())
                .body(Map.of("theme", value));
    }

    @GetMapping("/api/cookies/theme")
    public Map<String, String> readTheme(
            @CookieValue(value = "theme", required = false)
            String value) {

        return Map.of("theme",
                value == null ? "unset" : value);
    }

    @PostMapping("/api/cookies/theme/clear")
    public ResponseEntity<Void> clearTheme(
            HttpServletRequest request) {

        ResponseCookie expired = ResponseCookie
                .from("theme", "")
                .path("/")
                .httpOnly(true)
                .secure(request.isSecure())
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .build();
    }

    @GetMapping("/api/session/visit")
    public ResponseEntity<Map<String, Integer>> visit(
            HttpSession session) {

        Integer previous =
                (Integer) session.getAttribute("visits");

        int next = previous == null ? 1 : previous + 1;

        session.setAttribute("visits", next);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("visits", next));
    }

    @PostMapping("/api/session/logout")
    public ResponseEntity<Void> logout(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

Save at `src/main/java/demo/CookieSessionController.java`.

**Key technical notes:**

- `secure(request.isSecure())` solely allows the demo to run over local HTTP and test simulated HTTPS via `MockMvc.secure(true)`. **Production must enforce HTTPS and `Secure` cookies** via trusted TLS termination/forwarded headers; never trust raw `X-Forwarded-Proto` from the Internet without stripping/validating it.
- The `theme` cookie is `HttpOnly` in the demo to illustrate the flag; a real theme cookie might be JS-readable if needed—decide by threat model rather than copying flags blindly.
- `SameSite=Lax` does not replace CSRF tokens for state-changing POSTs when using cookie-based session authentication.
- `Map.of(...)` rejects nulls; the controller maps missing cookies to `"unset"`.
- `HttpSession` is created when a request hits `visit`. `MockMvc` tests must pass the same `MockHttpSession` to the second request.
- `logout` invalidates the server session; it **does not automatically delete all browser cookies**. For real authentication, use Spring Security logout handling and matching cookie deletion.
- Do not read raw `Cookie[]` just to log them; session IDs and cookie tokens are sensitive data.

### 8.6. Static Files

Create `src/main/resources/static/assets/hello.txt` containing one line ending in a newline:

```text
asset-ok
```

The test asserts the exact string `"asset-ok\n"`. Keep the trailing newline.

Create `src/main/resources/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Web runtime lab</title></head>
<body>
  <h1>Spring Boot web runtime lab</h1>
  <p><a href="/assets/hello.txt">Static asset</a></p>
</body>
</html>
```

Create `src/main/resources/private/private-note.txt`:

```text
NOT_PUBLIC
```

Files in `private/` sit on the classpath yet outside Boot's static resource locations. `GET /private-note.txt` must not return its contents via the default static handler.

**No `@Controller` is needed for `/assets/hello.txt`**. With Boot 3.3 MVC auto-configuration, `ResourceHttpRequestHandler` serves it from the classpath.

### 8.7. application.properties

```properties
server.port=8080

# Servlet Session: lab. Production requires HTTPS/Secure.
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Container limits when receiving real multipart requests.
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB

# Short-term cache for public static resources.
spring.web.resources.cache.period=60s
spring.web.resources.cache.use-last-modified=true

# Keep Boot MVC auto-configuration and static mappings.
spring.web.resources.add-mappings=true
```

Save at `src/main/resources/application.properties`.

**Multipart limits in properties and validation in `FileStore` serve two different layers.** `spring.servlet.multipart.max-file-size`/`max-request-size` govern the real server's multipart parser. Because `MockMvc.multipart()` builds a `MockMultipartHttpServletRequest`, the parser does not run as in live Tomcat; testing an oversized upload in MockMvc only verifies `FileStore`'s 64 KiB guard.

In production, enable `server.servlet.session.cookie.secure=true` over HTTPS, and ensure reverse proxy forwarded headers are processed only at the trust boundary. The local HTTP demo deliberately avoids forcing `Secure` on `JSESSIONID` so cookie-jar tests can run; **never deploy lab properties as production security config**.

### 8.8. Running the Application

```bash
./gradlew clean test bootRun
```

PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

To package a JAR:

```bash
./gradlew bootJar
java -jar build/libs/runtime-files-test-0.0.1-SNAPSHOT.jar
```

These commands run once the Gradle Wrapper from Initializr exists and the project follows the structure above. Do not compile `FileController.java` individually with `javac` because it requires Spring/Jakarta dependencies from Gradle.

## 9. Testing with MockMvc: Full Spring MVC Context

`@SpringBootTest` defaults to `webEnvironment=MOCK`, without starting an embedded HTTP server. `@AutoConfigureMockMvc` wires `MockMvc` to the MVC context. Because we want to test **static handlers, multipart mappings, cookie endpoints, and sessions together**, choose full context instead of single-controller `@WebMvcTest`.

Create `src/test/java/demo/WebRuntimeMockMvcTest.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebRuntimeMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    @Test
    void uploadAndDownloadKeepExactBytes() throws Exception {
        byte[] expected = new byte[] {
                0, 1, 2, 10, 13, 65, (byte) 255
        };

        MockMultipartFile part = new MockMultipartFile(
                "file",
                "../untrusted.txt",
                "text/plain",
                expected
        );

        MvcResult upload = mvc.perform(
                multipart("/api/files").file(part))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").isNotEmpty())
            .andReturn();

        String id = json.readTree(
                upload.getResponse().getContentAsString())
                .get("id").asText();

        MvcResult download = mvc.perform(
                get("/api/files/{id}", id))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    containsString("attachment")))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    containsString("download.bin")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andReturn();

        assertThat(download.getResponse()
                .getContentAsByteArray())
            .isEqualTo(expected);

        assertThat(download.getResponse()
                .getContentLength())
            .isEqualTo(expected.length);
    }

    @Test
    void rejectsEmptyAndExcessivelyLargeFile() throws Exception {
        MockMultipartFile empty =
                new MockMultipartFile("file", new byte[0]);

        mvc.perform(multipart("/api/files").file(empty))
            .andExpect(status().isBadRequest());

        MockMultipartFile tooLarge = new MockMultipartFile(
                "file", "big.bin", "application/octet-stream",
                new byte[64 * 1024 + 1]
        );

        mvc.perform(multipart("/api/files").file(tooLarge))
            .andExpect(status().is(413));
    }

    @Test
    void missingDownloadReturns404() throws Exception {
        mvc.perform(get(
                "/api/files/00000000-0000-0000-0000-000000000000"))
            .andExpect(status().isNotFound());
    }

    @Test
    void cookieHasExpectedAttributes() throws Exception {
        mvc.perform(post("/api/cookies/theme")
                .param("value", "dark")
                .secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.SET_COOKIE,
                allOf(
                    containsString("theme=dark"),
                    containsString("Path=/"),
                    containsString("HttpOnly"),
                    containsString("SameSite=Lax"),
                    containsString("Max-Age=600"),
                    containsString("Secure")
                )));

        mvc.perform(get("/api/cookies/theme")
                .cookie(new Cookie("theme", "dark")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("dark"));

        mvc.perform(get("/api/cookies/theme"))
            .andExpect(jsonPath("$.theme").value("unset"));

        mvc.perform(post("/api/cookies/theme/clear")
                .secure(true))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                    HttpHeaders.SET_COOKIE,
                    allOf(
                        containsString("theme="),
                        containsString("Path=/"),
                        containsString("Max-Age=0")
                    )));
    }

    @Test
    void cookieRejectsUnexpectedValue() throws Exception {
        mvc.perform(post("/api/cookies/theme")
                .param("value", "malicious"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void sessionPersistsOnlyWhenExplicitlyReused()
            throws Exception {

        MvcResult first = mvc.perform(
                get("/api/session/visit"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visits").value(1))
            .andReturn();

        MockHttpSession sameSession =
                (MockHttpSession) first.getRequest()
                        .getSession(false);

        assertThat(sameSession).isNotNull();

        mvc.perform(get("/api/session/visit")
                .session(sameSession))
            .andExpect(jsonPath("$.visits").value(2));

        // New request without passing the old session.
        mvc.perform(get("/api/session/visit"))
            .andExpect(jsonPath("$.visits").value(1));

        mvc.perform(post("/api/session/logout")
                .session(sameSession))
            .andExpect(status().isNoContent());

        assertThat(sameSession.isInvalid()).isTrue();
    }

    @Test
    void staticAssetIsPublicButPrivateResourceIsNot()
            throws Exception {

        mvc.perform(get("/assets/hello.txt"))
            .andExpect(status().isOk())
            .andExpect(content().string("asset-ok\n"));

        mvc.perform(get("/private-note.txt"))
            .andExpect(status().isNotFound());
    }
}
```

**Why are these tests important?**

- The download test uses bytes including `0x00` and `0xFF` to avoid “text looks fine” while binary data is corrupted; the binary response is compared **byte-for-byte**.
- The uploaded filename deliberately contains `../`; the server does not use it as a storage path or download header. This is not a comprehensive path-traversal/storage test.
- 413 in `MockMvc` comes from the application guard; it **does not confirm** `spring.servlet.multipart.max-file-size` is enforced by Tomcat.
- The cookie test checks `Set-Cookie` attributes with header matchers; `secure(true)` simulates HTTPS on the request to exercise `request.isSecure()`.
- `.cookie(new Cookie(...))` merely simulates a client sending a cookie, without a real browser cookie jar.
- The session test passes `MockHttpSession` to the second request and checks invalidation; a new request omitting the session sees the counter start over.
- The static test exercises the full application context's resource handler, yet still does not check JAR packaging/CDN.
- Tests write no files to the filesystem, so no upload directory cleanup is needed.

**Note on imports:** `StandardCharsets` is imported in the listing to facilitate UTF-8 test variants; Java permits unused imports in standard compilation. Other assertions use AssertJ/Hamcrest/MockMvc from `spring-boot-starter-test`.

### 9.1. Do Not Confuse HTTP Status Across Multipart Failure Layers

The oversized `MockMultipartFile` test exercises `FileStore`'s branch and expects `413`. On live Tomcat, a request may be rejected **before the controller runs** by the multipart resolver/container. With a custom `@ControllerAdvice`, the status body may differ. Test real oversized multipart requests independently; if the contract requires a consistent `413` on all overflows, add a global exception handler for `MaxUploadSizeExceededException` and test it against a live server.

### 9.2. How to Check MIME/Charset?

Do not assert an arbitrary `Content-Type` if the project does not prescribe one. For instance, static `hello.txt` normally receives `text/plain`; the charset parameter can vary by container/config. For the download demo, the method explicitly sets `application/octet-stream`, so asserting it is safe. For JSON error responses, Spring Boot 3.3 and problem details configs affect the body; do not hardcode default error JSON as a business contract.

### 9.3. Testing Range in MockMvc Helps, Yet Needs Live Tests

When Spring MVC sees `GET /api/files/{id}` returning `ResponseEntity<Resource>` with status 200, it supports `Range` under the conditions documented. An extra assertion can test:

```java
mvc.perform(get("/api/files/{id}", id)
        .header(HttpHeaders.RANGE, "bytes=0-3"))
    .andExpect(status().isPartialContent())
    .andExpect(header().exists(
            HttpHeaders.CONTENT_RANGE));
```

This is an **additional snippet** needing an `id` uploaded during test setup, not a standalone test method. If it fails, inspect the `Resource` type, status/headers, HTTP message converters, and Spring version rather than ignoring the failure. Even if MockMvc returns 206 cleanly, test against a live server when resumable/large downloads matter.

## 10. Testing Over Real HTTP with RANDOM_PORT

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Boot starts embedded Tomcat on a random port. Java `HttpClient` issues real TCP HTTP requests; `CookieManager` retains cookies across requests within the same test. This differs from MockMvc and is invaluable for `JSESSIONID`, cookie headers, runtime static resource packaging, and container behavior.

Create `src/test/java/demo/WebRuntimeHttpIntegrationTest.java`:

```java
package demo;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRuntimeHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void realCookieJarReusesServletSession()
            throws Exception {

        CookieManager cookies =
                new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(cookies)
                .build();

        URI uri = URI.create(
                "http://localhost:" + port + "/api/session/visit");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> first = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        HttpResponse<String> second = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(first.statusCode()).isEqualTo(200);
        assertThat(second.statusCode()).isEqualTo(200);

        assertThat(first.body()).contains("\"visits\":1");
        assertThat(second.body()).contains("\"visits\":2");

        assertThat(cookies.getCookieStore().getCookies())
            .anySatisfy(cookie ->
                assertThat(cookie.getName())
                    .isEqualTo("JSESSIONID"));
    }

    @Test
    void staticAssetIsServedOverActualHttp()
            throws Exception {

        HttpClient client = HttpClient.newHttpClient();

        URI uri = URI.create(
                "http://localhost:" + port
                + "/assets/hello.txt");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("asset-ok\n");
    }
}
```

This is an integration test against a **real container**, without browser automation. `CookieManager` verifies that the Java HTTP client receives `JSESSIONID` and sends it back so the server increments the counter on the same session. It does not prove Chrome/Safari share identical third-party cookie policies, does not test TLS since the URL is localhost HTTP, and does not verify multi-pod session persistence.

**Important note on transactions:** under `RANDOM_PORT`, the HTTP server handles requests in a different thread/transaction than the test method. A `@Transactional` annotation on the test thread will not automatically roll back database changes made through the HTTP request. When testing with real repositories, use deterministic fixtures, an isolated database, and reliable cleanup.

### 10.1. Testing the Application's Own Cookies via a Real Client

The test above exercises the container's session cookie. To test `theme` specifically, send `POST /api/cookies/theme?value=dark` through the same `HttpClient.CookieManager`, then `GET /api/cookies/theme` and assert the body returns `dark`. Use Java's `HttpRequest.BodyPublishers.noBody()` with matching headers/URI, or try with `curl` as in section 11. Do not assume `HttpOnly` stops Java's HTTP client from sending cookies: `HttpOnly` mainly blocks access from JavaScript inside a browser.

### 10.2. Sending Real Multipart Requests from Integration Tests

`java.net.http.HttpClient` has no built-in multipart builder as convenient as Spring Test; you must construct the boundary and raw body in valid format, or use a multipart-capable HTTP client library. For this lesson, `curl -F` is a fast, reliable way to verify container parsing and limits. Never use `MockMultipartFile` to claim Tomcat parsed a raw multipart boundary.

## 11. Practicing with curl Against the Running App

After running `./gradlew bootRun` or the JAR, use another terminal.

### 11.1. Uploading a Small File

Create a local file:

```bash
printf 'hello-file\n' > demo-upload.txt
```

Send a real multipart request:

```bash
curl -i -F 'file=@demo-upload.txt;type=text/plain' \
  http://localhost:8080/api/files
```

Typical response:

```http
HTTP/1.1 201
Content-Type: application/json

{"id":"<server-generated-uuid>"}
```

The UUID is random, not fixed. `curl -F` generates the multipart boundary automatically; never manually set `Content-Type: multipart/form-data` without a boundary when building a raw body.

### 11.2. Downloading and Comparing Bytes

Substitute the actual ID:

```bash
curl -i \
  'http://localhost:8080/api/files/PUT-UUID-HERE'
```

Or save bytes:

```bash
curl -sS -o downloaded.bin \
  'http://localhost:8080/api/files/PUT-UUID-HERE'
```

Compare:

```bash
cmp demo-upload.txt downloaded.bin
```

`cmp` exits with code 0 when bytes match on Unix-like systems. On Windows, use PowerShell `Get-FileHash` with SHA-256, or a Java/Python test computing a hash. Do not rely on a text editor to confirm a binary file is uncorrupted.

Expected download headers include `Content-Disposition: attachment; filename="download.bin"`, `Content-Type: application/octet-stream`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, and the file's `Content-Length`.

### 11.3. Uploading Past the Real Limit

Create a file larger than 64 KiB:

```bash
dd if=/dev/zero of=big-demo.bin bs=1024 count=65
```

Send:

```bash
curl -i -F 'file=@big-demo.bin' \
  http://localhost:8080/api/files
```

Here the **real server multipart parser** can reject the request before `FileStore.save`. Observe the status, error type, access/application logs, and cleanup. If the contract mandates a uniform `413` for all size overflows, add a global exception handler for `MaxUploadSizeExceededException` and test live. Do not assume every Boot/container version emits the exact same JSON error.

### 11.4. Testing Cookies with a curl Jar

On Unix, create a dedicated test directory and temporary cookie jar file:

```bash
jar="$(mktemp)"
curl -sS -c "$jar" -b "$jar" -X POST \
  'http://localhost:8080/api/cookies/theme?value=dark'

curl -sS -c "$jar" -b "$jar" \
  'http://localhost:8080/api/cookies/theme'

rm -f "$jar"
```

First body returned by the controller:

```json
{"theme":"dark"}
```

Second body is also expected to be `{"theme":"dark"}` if the cookie jar actually stored and resent the cookie. Cookie files in other apps can hold session IDs and sensitive info; **never commit them to Git, never paste jar contents into chat/tickets**, and delete them when done.

On localhost HTTP, the `theme` cookie sets `Secure` according to `request.isSecure()` so the demo can be tried. **Production must run HTTPS and `Secure`**, never dropping `Secure` just so browsers send cookies over public HTTP.

### 11.5. Testing HttpSession with the Same Jar

```bash
jar="$(mktemp)"

curl -sS -c "$jar" -b "$jar" \
  http://localhost:8080/api/session/visit

curl -sS -c "$jar" -b "$jar" \
  http://localhost:8080/api/session/visit

rm -f "$jar"
```

Expected bodies respectively:

```json
{"visits":1}
```

```json
{"visits":2}
```

Calling the second time without `-b "$jar"` or with another jar yields a different session and restarts the counter. This demonstrates the **client retaining the session identifier**, not storing the count inside the cookie.

### 11.6. Static Resources and Caching

```bash
curl -i http://localhost:8080/assets/hello.txt
curl -i http://localhost:8080/
curl -i http://localhost:8080/private-note.txt
```

Expect the static asset and welcome page to return 200, and the private resource to return 404. The static asset carries roughly a 60-second cache policy per properties. Try `HEAD`:

```bash
curl -I http://localhost:8080/assets/hello.txt
```

`HEAD` returns no body in the HTTP protocol even though headers describe the representation. To test `304`, copy `Last-Modified` from the GET response and resend it in `If-Modified-Since` with the exact format rather than hardcoding an arbitrary timestamp.

### 11.7. Testing Byte Ranges

```bash
curl -i -H 'Range: bytes=0-3' \
  http://localhost:8080/assets/hello.txt
```

When Spring's resource handler serves `Range` over HTTP, bytes 0..3 of `asset-ok\n` are `asse`, and the response is typically `206 Partial Content` with `Content-Range: bytes 0-3/9`. Verify this behavior against the real server/container/proxy; if the server returns a full `200` response, inspect handler routing, Range support, compression/edge behavior, and headers before drawing conclusions. Do not mix range tests with a proxy that transforms compressed content on the fly.

### 11.8. Inspecting Cookie Attributes with Browser DevTools

On HTTPS staging, open DevTools → Application/Storage → Cookies to check `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, and expiry; check the Network tab for `Set-Cookie`/`Cookie` on requests. Browsers may refuse to store a cookie due to `Secure`/`SameSite`/`Domain` or third-party policies even when the server sent syntactically valid `Set-Cookie`. That is why E2E is required for login/session flows.

## 12. How to Choose Between @WebMvcTest, MockMvc, and RANDOM_PORT?

### 12.1. @WebMvcTest — Slice, Fast Yet Minimal Beans

`@WebMvcTest(FileController.class)` typically scans MVC controllers, filters, converters, and selected MVC infrastructure without scanning all `@Service`/repository beans. Because `FileController` in the demo depends on `FileStore`, a slice test needs to mock/import that dependency. It fits verifying argument binding, statuses, validation/exception mapping, and headers of one controller; it is unsuitable as proof of full static resource packaging, distributed session stores, or server multipart configuration.

With Spring Boot 3.3, use `@MockBean` or `@Import` for slice collaborators. Check annotations for your version; for example, Boot 3.3 differs from Spring Boot 4.x in the package location of several test annotations.

### 12.2. @SpringBootTest(MOCK) + @AutoConfigureMockMvc

This is the model of `WebRuntimeMockMvcTest`: loads the full application context while mocking Servlet objects. Fits testing multiple controllers, filters, static resource mappings, and session attributes together. Opens no port.

### 12.3. @SpringBootTest(RANDOM_PORT)

`RANDOM_PORT` starts a real web server. Clients can use `TestRestTemplate`, Java `HttpClient`, or live-configured `WebTestClient`. Suits real cookie persistence, HTTP headers, multipart parsers, response statuses, embedded container behavior, and static packaging. Usually slower and requires cleaning up DB/files/session state.

### 12.4. Browser/E2E with Proxy/CDN

When bugs occur only with HTTPS/`SameSite`/third-party cookies, CDN 304, reverse proxy upload body limits, or browser file download UX, run through a **production-like path**. Localhost `RANDOM_PORT` does not represent TLS termination, ingress headers, browser restrictions, or shared caches.

## 13. Security Tests: Upload and Download

### 13.1. Object-Level Authorization

In the demo, `GET /api/files/{id}` is unauthenticated. In production, tests must prove:

- User A uploads a file and receives an ID.
- User B cannot read User A's file (403 or 404 per policy, avoiding enumeration).
- Anonymous users cannot upload/download when disallowed.
- Admins can access per explicit permissions, with auditing when required.
- Unpredictable IDs are still **not** authorization.
- Path traversal via filenames, URL encoding, percent-encoded slashes, and Unicode cannot escape the storage root.

A single test returning 200 for User A is insufficient; **negative permission tests** are mandatory.

### 13.2. CSRF with Browser Session Cookies

If the application uses Spring Security and session/cookie login, upload POST, set-theme POST, and logout POST may require CSRF tokens. Spring Security test support offers:

```java
mvc.perform(multipart("/api/files")
        .file(sample)
        .with(csrf()))
    .andExpect(status().isCreated());
```

This is a **snippet for projects with `spring-security-test`, Spring Security's filter chain, and `sample` already created**—not part of the Security-free demo. Do not paste it into a project having only `spring-boot-starter-web` expecting it to compile. When CSRF is enabled, tests must also verify missing/invalid tokens are rejected.

For multipart requests, the ordering between multipart parsing and the CSRF filter involves trade-offs: placing the token in a header from JavaScript clients is often cleaner than placing it inside the multipart body where the server may have to parse the body to extract CSRF. Consult Spring Security's guide on Multipart and CSRF.

### 13.3. Defending Against Malicious Uploads

In production:

1. Cap part/file/request bytes at both the edge and the servlet container.
2. Cap part/file counts and concurrent uploads.
3. Use generated storage keys; never trust user filenames/paths.
4. Allowlist file types per business need; inspect content signatures, not just extensions.
5. Scan for malware and quarantine temporary uploads; require clean scan results before serving downloads.
6. Never serve untrusted files on the same origin holding sensitive cookies if active content poses a risk.
7. Serve downloads as attachments with `nosniff` and safe headers.
8. Enforce AuthN/AuthZ, tenant isolation, and quotas.
9. Clean up orphaned files when transactions or scans fail.
10. Never log raw uploaded bytes, sensitive filenames, or auth headers.

Tests should cover fake PDFs, ZIPs, SVGs/HTML, oversized files, empty files, filenames with `../`, fake extensions, and MIME mismatches—using **harmless controlled fixtures**.

### 13.4. Caching Private Files

`Cache-Control: no-store` states the intent not to cache private file responses. However, CDNs/proxies with custom rules may still require bypass policies; verify User A's file is never served from cache to User B. With signed URLs, test expiration, signature validation, post-revocation downloads, and clock skew.

## 14. Cookie and Session Security Tests

### 14.1. Session Fixation

Upon login, Spring Security normally changes the session ID or migrates the session per configured strategy to defeat fixation. Tests should verify the post-auth session does not reuse an attacker-supplied pre-login identifier while preserving needed business state if configured. Since the demo has no authentication, do not invent custom fixation logic.

### 14.2. Logout Must Invalidate the Session

Proper logout needs server invalidation/security context cleanup and matching cookie handling. Test:

- After logout, the old cookie/session ID cannot access authenticated endpoints.
- Resending the old cookie does not restore an authenticated session.
- Browsers retain no valid credentials.
- Distributed session repositories delete/expire entries cleanly.
- Old CSRF tokens can no longer be used under the new security context.
- Logging back in issues a valid session per policy.

In the demo, `logout` only calls `session.invalidate()` and returns 204—suitable for testing the Servlet session lifecycle, **not a production authentication implementation**.

### 14.3. HttpOnly, Secure, SameSite

| Test | How to Verify |
| --- | --- |
| `HttpOnly` cookie | Assert in `Set-Cookie`; verify browser `document.cookie` cannot read it |
| `Secure` | Assert on HTTPS/secure requests and test HTTPS browser; verify proxy forwarded scheme |
| `SameSite=Lax` | Header + browser cross-site navigation behavior |
| `SameSite=None` | Also test `Secure` and CORS credentials/third-party policy |
| Cookie expiration | Test `Max-Age` and browser jar; do not merely sleep in unit tests |
| `Path`/`Domain` | Test cookie is sent only within scope |
| Session cookie rotation | Test live login flow with security |
| Cookie tampering | Test server never trusts user-controlled cookies for privileges |

Browser cookies obey client-side policies too; Java's HTTP client might accept a cookie that Safari/Chrome blocks. Hence cross-site login flows need browser E2E alongside server assertions.

### 14.4. Session State Across Multiple Pods

If sessions live in Tomcat's memory on Pod A, the next request hitting Pod B will not see `visits=2`. Sticky sessions mitigate some cases yet fail when Pod A dies. When shared sessions are required, configure Spring Session Redis/JDBC and test multi-replica behavior, TTL, serialization, failover, and invalidation.

### 14.5. Timeout Tests Should Avoid Long Thread.sleep

`MockHttpSession` allows adjusting times/attributes in tests, yet does not fully simulate expiration by a real container. For integration tests, use short timeouts in isolated environments and clock/test hooks where supported; avoid `Thread.sleep(15*60*1000)` as slow and flaky. Test boundaries (before/after expiry) and authentication outcomes.

## 15. Static Resource Caching, Range, Security, and Packaging

### 15.1. Cache-Control and 304

`spring.web.resources.cache.period=60s` adds `Cache-Control` headers to static assets, though `max-age` itself is not a validator. When a resource has `Last-Modified` and the client sends a matching `If-Modified-Since`, the handler can return 304. If `ETag` is configured by the framework/Filter/CDN, `If-None-Match` can use `ETag`; **never assume every static response emits `ETag` by default**.

Test per contract:

- GET asset returns 200, exact bytes, and content type.
- HEAD returns no body.
- `Cache-Control` matches policy.
- If `Last-Modified` is present, a matching conditional GET yields 304 and an empty body.
- `Range` if supported: 206, `Content-Range`, and exact bytes.
- Missing asset: 404, no unexpected HTML or private data.
- Versioned asset URL: when content changes, hash/version changes; immutable caching applies only to versioned files.

### 15.2. NGINX/CDN vs Embedded Resource Handler

A CDN may serve 304 from cache without requests ever reaching Spring Boot; ingress may gzip/resize responses; CDNs also have cache keys with/without query strings or cookies. Thus `MockMvc` tests do not prove CDN 304/206, and local JAR tests do not prove multi-replica cache invalidation.

### 15.3. Resource Locations and Security Boundaries

Default static locations are **public resources**. Never put `application.properties` holding secrets, private uploads, DB dumps, or sensitive source maps inside `static`. Spring Boot does not serve `classpath:/private/` over `/**`, yet when configuring `spring.web.resources.static-locations=file:/...` or custom `addResourceHandlers`, audit roots carefully so private filesystem directories are never exposed.

Test traversal attempts with encoded paths and dot segments using a live HTTP client because mock request canonicalization and container normalization can differ. Never test just one `../` string and declare all path traversal blocked.

### 15.4. JAR Packaging Regression

A project running from an IDE may locate `src/main/resources/static/assets/hello.txt`, while a misconfigured fat JAR build omits the resource. At minimum run:

```bash
./gradlew bootJar
java -jar build/libs/runtime-files-test-0.0.1-SNAPSHOT.jar
curl -i http://localhost:8080/assets/hello.txt
```

You can inspect the JAR listing with `jar tf` in local builds, though checking filenames alone is insufficient to verify routing, `Content-Type`, caching, or static security.

## 16. Negative Test Cases and Error Diagnostics

| Scenario | Test | What to Distinguish |
| --- | --- | --- |
| Missing multipart field `file` | POST multipart with another field | Binding error 400, not 500 |
| Empty file | `MockMultipartFile("file",new byte[0])` | Contract rejects 400 |
| App-level oversized file | 65 KiB `MockMultipartFile` | `FileStore` returns 413 |
| Tomcat-level oversized file | `curl -F` 65 KiB | Container rejects before controller |
| Missing download ID | GET random ID | 404; no filesystem path leaked |
| Another user's download ID | Authenticated User B GETs A's file | 403/404 per policy |
| Invalid cookie value | `value=malicious` | 400, does not reflect arbitrary header |
| Missing cookie | GET `readTheme` without Cookie | `theme=unset` |
| Tampered cookie | Client sends non-allowlisted cookie | Server validates, grants no privileges |
| Session not reused | New MockMvc request without `session(...)` | Counter resets to 1 |
| Session invalidated | POST logout + test invalid | Does not restore auth/session |
| Session timeout | Live short timeout/clock control | Does not automatically match cookie expiry |
| Missing static asset | `GET /assets/missing.txt` | 404 |
| Private resource | `GET /private-note.txt` | 404 despite file being on classpath |
| Static caching | GET + conditional GET | 304 only with matching validator |
| Partial download | Valid/invalid byte ranges | 206/416 per support |
| Reverse proxy upload limit | Upload through NGINX ingress | Proxy may return 413 before app |
| HTTPS cookie policy | `Secure`/`SameSite`/CORS | Real browser may block even if MockMvc passes |

A container-level bug must never be “fixed” by relaxing a `MockMvc` test; inspect the real boundary at the right layer.

### 16.1. First Diagnostics When Upload Returns 400/413

1. Did the client use `multipart/form-data` with an auto-generated boundary?
2. Does `@RequestParam("file")` match the exact field name?
3. Is the file empty, part name wrong, or content encoding broken?
4. Did file size exceed `max-file-size` or total size exceed `max-request-size`?
5. Does NGINX enforce its own `client_max_body_size`/WAF limit?
6. Did Spring Security return 403 for CSRF/auth before the controller?
7. Are client timeouts/broken pipes on long uploads logged safely and classified?
8. Does the app map `MaxUploadSizeExceededException` to a consistent response?
9. Are storage quotas/permissions/virus scans causing 500s?
10. Does the upload response include a correlation ID to find logs without logging file contents?

### 16.2. Diagnostics When Sessions Reset on Every Request

1. Did the browser/client save `Set-Cookie`?
2. Does the cookie have the right `Domain`/`Path`? Is `Secure` set over HTTP? Is `SameSite` blocking cross-site?
3. Does client `fetch` use the right credentials mode? Does the server configure CORS credentials and origin allowlists?
4. Did the cookie expire or get blocked by browser third-party policies?
5. Was the session cookie name changed, or do multiple services collide on the same cookie name?
6. Is a load balancer routing to a Pod with a separate session store?
7. Was the session invalidated by logout, TTL, security, or app restart?
8. Did a reverse proxy strip `Set-Cookie`/`Cookie` or rewrite domain/path wrongly?
9. Did the `MockMvc` test pass `MockHttpSession` explicitly?
10. Are session cookies being mixed up with theme cookies/CSRF tokens?

### 16.3. Static 404 Diagnostics

1. Is the file actually in `src/main/resources/static`?
2. Did the JAR build package the file?
3. Does the URL mistakenly include `/static/`?
4. Is there a custom `spring.mvc.static-path-pattern` or `spring.web.resources.static-locations`?
5. Did `@EnableWebMvc` disable some Boot auto-configuration?
6. Are controller/forward/security routes blocking `/assets/**`?
7. Are frontend base path/context path/ingress rewrites correct?
8. Is static/CDN caching holding a stale 404?
9. Do OS path case-sensitivities differ?
10. Is the file in a private resource location or a `webapp` directory skipped in JAR builds?

## 17. Combining Spring Security in Tests

The demo omits Security, yet in real products enabling Security changes outcomes:

- `@WebMvcTest` can auto-apply security filters, causing 401/403 unless a test principal is configured.
- Spring Security test supports `@WithMockUser`, `user(...)`, `csrf()`, and request post-processors.
- Multipart POST and logout POST under cookie auth may require CSRF.
- HTTP GET of private files must check object ownership/tenant, not merely `authenticated()` on the URL.
- Public static CSS/JS can be `permitAll`, restricted only to public assets; do not abuse `web.ignoring()` to bypass all security filters carelessly.
- Session fixation/migration on login should be tested at the security integration layer.
- Session repository/CSRF cookie policies can make live flows behave differently from MockMvc.
- With stateless OAuth2 bearer tokens, do not expect `JSESSIONID` as in traditional cookie-session logins.

**Never use `@AutoConfigureMockMvc(addFilters=false)` just to turn tests green** when the goal is verifying authentication/CSRF behavior. Only disable filters when intentionally isolating a controller and security is verified elsewhere.

## 18. WebFlux and Reactive File Transfer Differ from MVC

Spring WebFlux uses `WebTestClient`, `ServerWebExchange`, and reactive `Flux<DataBuffer>`. It does not share identical `MockMvc`/`MultipartFile` semantics with Spring MVC.

- Reactive uploads use `FilePart` and `transferTo`; test via `WebTestClient` or HTTP clients.
- Reactive downloads use `Resource` or streaming bodies with backpressure.
- Buffer ownership/retain/release differ from Servlet; never join large files entirely in memory just to test or log.
- Cookies and sessions in WebFlux use `WebSession`, not `jakarta.servlet.http.HttpSession`.
- Static resources and caching still require runtime/packaging/CDN verification, though handler classes differ from MVC.

Never add `spring-boot-starter-webflux` just to “use `WebTestClient`” and assume the application switched to non-blocking. When both MVC/WebFlux starters exist, Spring Boot picks the web application type by precedence rules; identify the active stack before choosing test APIs.

## 19. CI and Test Data

### 19.1. Tests Must Not Depend on Personal Machines

- Use small, synthetic fixture files containing zero customer data.
- Never depend on `C:\Users\...` or `/home/me/Downloads`.
- Never hardcode TCP ports for integration tests; use `RANDOM_PORT`.
- Use generated filenames/IDs; never assume request ordering in parallel tests.
- Delete temporary files/cookie jars after runs.
- When using real storage, provision isolated test containers/object buckets and clean up.
- Never commit session cookies, access tokens, or HTTP captures containing PII.
- Record expected checksums for critical binary fixtures.
- Define clear contracts for 400/403/404/413/206/304 and test at the appropriate layer.

### 19.2. Avoiding Time/Cookie Flakiness

Never `Thread.sleep(15*60*1000)` waiting for a session timeout; use short timeouts/clock hooks supported in test environments. With `Last-Modified`, one-second granularity can make 304 tests flaky if a resource is created/modified within the same second. Do not assert exact byte-for-byte `Set-Cookie` formatting when attribute order varies by container; assert required attributes and browser behavior.

### 19.3. CI Runs Two Groups of Tests

- **Fast tests:** controller binding, guards, bytes, `MockHttpSession`, and static handlers via `MockMvc`.
- **Live server tests:** cookie jars, multipart parser, session cookies, HTTP resources, Range/conditional requests, real statuses/headers.
- **Deployment smoke tests:** `bootJar`, ingress/CDN caching, HTTPS cookie policy, private file permissions, large uploads, and multi-pod session stores.

Not every browser E2E test must run on every commit if costly, yet a regression suite must cover vital contracts.

## 20. Self-Check Questions

**1.** Does a passing `MockMvc.multipart()` prove Tomcat reads multipart boundaries properly?  
**Answer:** No. `MockMvc` builds `MockMultipartHttpServletRequest`, bypassing the real request parser. A live HTTP multipart test is needed.

**2.** Why compare `getContentAsByteArray()` instead of `getContentAsString()` for ZIP files?  
**Answer:** Binary data contains non-UTF-8 bytes; converting to `String` can corrupt content.

**3.** What do `Content-Disposition: attachment` and `Content-Type` do?  
**Answer:** `attachment` hints downloading; `Content-Type` states the representation type. Safe filenames and `nosniff` are required when serving user uploads.

**4.** Does an `HttpOnly` cookie stop the browser from sending it on HTTP requests?  
**Answer:** No. `HttpOnly` primarily blocks JavaScript access via `document.cookie`; browsers still send it if scope/policies allow.

**5.** Is a `Secure` cookie appropriate on plain HTTP in production?  
**Answer:** Production uses HTTPS + `Secure`; over plain HTTP, browsers normally refuse to store or send it.

**6.** Does `MockMvc` automatically extract `JSESSIONID` from a response and attach it to the next request?  
**Answer:** No. Use `MockHttpSession` in tests or a cookie-aware HTTP client live.

**7.** Does seeing `Set-Cookie` guarantee the browser stores the cookie?  
**Answer:** No. `Domain`/`Path`/`Secure`/`SameSite`/third-party policies can make the client reject it.

**8.** After `session.invalidate()`, can a browser still send the old `JSESSIONID` cookie?  
**Answer:** Yes. The server must treat the old session as invalid; clearing the browser cookie requires matching the cookie's exact scope.

**9.** Is `src/main/resources/private/secret.txt` served automatically by Boot's static handler?  
**Answer:** Not under default static locations; only configured public static folders are exposed. Custom configs can alter this.

**10.** Why might static resources in `src/main/webapp` be missing from an executable JAR?  
**Answer:** Boot docs warn that directory suits WAR packaging and may be omitted by build tools in JARs.

**11.** Does `Cache-Control: max-age=60` mean every request gets 304?  
**Answer:** No. 304 requires a conditional request and matching `Last-Modified`/`ETag` validators.

**12.** Why must byte Range tests check both 206 and `Content-Range`?  
**Answer:** To confirm the server returned the exact partial slice rather than the whole file or corrupt offsets.

**13.** Does an in-memory HTTP session on Pod A automatically appear on Pod B?  
**Answer:** No. A distributed session store like Spring Session plus failover testing is needed.

**14.** Does a hard-to-guess UUID file ID replace authorization on downloads?  
**Answer:** No. Owner/tenant/resource permissions must still be checked.

**15.** Why does a MockMvc 65 KiB upload returning 413 still not prove `spring.servlet.multipart.max-file-size=64KB`?  
**Answer:** That 413 came from `FileStore`'s guard; Tomcat's parser does not run in MockMvc.

**16.** With cookie-session login, does an upload POST need a CSRF test?  
**Answer:** Normally yes per Spring Security policy, unless the model is stateless or uses a safe explicit exception.

## 21. Execution Checklist

- [ ] Test uploads with exact multipart field name, bytes, status, and response ID.
- [ ] Test empty files, oversized files, malformed multipart requests, and spoofed content types.
- [ ] Verify container limits independently over real HTTP; not just `MockMultipartFile`.
- [ ] Never use original filenames as filesystem paths/storage keys.
- [ ] Download tests verify exact bytes, `Content-Disposition`, `Content-Type`, `Content-Length`, `Cache-Control`, and `nosniff`.
- [ ] Non-existent/unauthorized files return 404/403 per contract.
- [ ] Range 206/416 and conditional requests tested when supported by the product.
- [ ] `Set-Cookie` sets proper `Path`/`Domain`/`HttpOnly`/`Secure`/`SameSite`/`Max-Age`.
- [ ] Cookie jar/browser resends the right cookie; MockMvc receives `Cookie` manually.
- [ ] Session reuse uses `MockHttpSession`; live tests check `JSESSIONID` via cookie-aware clients.
- [ ] Session invalidation, timeouts, fixation, and multi-pod stores tested per threat model.
- [ ] Static files reside in valid public classpath locations and inside the built JAR.
- [ ] Private file paths are never served, even through custom static mappings.
- [ ] `Cache-Control`/`Last-Modified`/`ETag` and CDN invalidation policies are verified.
- [ ] Spring Security/CSRF/ownership tested without disabling filters carelessly.
- [ ] E2E HTTPS browser checks `Secure`/`SameSite`/CORS for cross-site flows.
- [ ] Tests use zero customer data and never log cookies/sessions/file contents.
- [ ] Clean up temporary files, cookie jars, and test repository data.
- [ ] CI runs MockMvc tests, `RANDOM_PORT` tests, and deployment-path smoke checks.
- [ ] Distinguish controller, multipart parser, reverse proxy, browser, and session store errors.

## Official References

1. [Spring Boot 3.3 — Servlet Web Applications, Static Content](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
2. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework 6.1 — MockMvc](https://docs.spring.io/spring-framework/reference/6.1/testing/mockmvc.html)
5. [Spring Framework 6.1 — MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/6.1/testing/mockmvc/vs-end-to-end-integration-tests.html)
6. [Spring Framework — MockMultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mock/web/MockMultipartFile.html)
7. [Spring Framework — MockHttpSession Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mock/web/MockHttpSession.html)
8. [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-config/static-resources.html)
9. [Spring Framework — Range Requests](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-range.html)
10. [Spring Framework — ResponseEntity and Resource](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/responseentity.html)
11. [Spring Guide — Uploading Files](https://spring.io/guides/gs/uploading-files/)
12. [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
13. [Spring Security — CSRF and Multipart](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
14. [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
15. [MDN — HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests)
16. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

**Conclusion:** web runtime testing does not stop at asserting a controller returns 200. **Uploads** demand proper multipart fields/bytes and parser/size limits, **downloads** demand exact bytes/headers/authorization, **cookies** demand proper scope/flags and real client retention/resending, **`HttpSession`** demands lifecycle/identifier/store verification, and **static resources** demand JAR classpath packaging, handler routing, caching, and zero exposure of private files. Pairing **MockMvc for MVC contracts** with **`RANDOM_PORT`/browser/edge tests for container & real client behavior** prevents false assumptions and keeps deployments safe.