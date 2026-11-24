# Never Trust Client-Supplied Filenames, Headers, or Attributes

> **Topic:** Request Data in Spring Boot **3.5.x**, Java **17+**, focusing on Spring MVC on the Servlet stack along with key WebFlux differences. This lesson teaches **never granting trust or authority to client-asserted data**, especially multipart filenames, HTTP headers, and request attributes. The Maven project below is runnable, though it intentionally omits authentication, authorization, malware scanning, quotas, and production operations.

## 1. Trust Boundary: Clients May Send Data, Never Decide Permissions

An HTTP client controls most parts of a request: URL, query string, form fields, JSON body, multipart headers, filenames, cookies, HTTP headers, and uploaded file bytes. Frontend validation never protects the server from curl, Postman, or custom clients.

~~~http
POST /api/files HTTP/1.1
Host: arbitrary.example
X-User-Role: admin
X-Tenant-Id: victim
X-Request-Id: fake-audit-id
Content-Type: multipart/form-data; boundary=example
~~~

Multipart metadata can claim:

~~~http
Content-Disposition: form-data; name="file"; filename="../../config/application.yml"
Content-Type: image/png
~~~

Nothing here proves the sender is an admin, belongs to that tenant, uploaded a real PNG, or provided a safe filesystem path.

| Value | Typical source | Rule |
|---|---|---|
| `MultipartFile.getOriginalFilename()` | Filename claimed by client in multipart | Never use directly as a path |
| `MultipartFile.getContentType()` | MIME type claimed by client | Never treat as proof of content |
| `X-User-Role`, `X-Tenant-Id` | Client/proxy | Not identity or authorization |
| `Host`, `X-Forwarded-Host` | Client/proxy chain | Trust only within an explicit trust boundary |
| `Origin`, `Referer` | Browser or arbitrary client | Never use for authentication |
| `@RequestAttribute("tenant")` | Placed on request by server/filter/framework | Verify the provenance of the value |
| Server-generated UUID | Application | Trusted source/syntax; still requires resource authorization |
| Verified Spring Security Principal | Authenticated session/token | Use as basis for scoped authorization |

Six distinct tasks exist: **provenance** (where the value came from), **syntax validation**, **content/business validation**, **authentication**, **authorization**, and **output encoding**. A filename matching a regex does not prove the user may upload; a valid UUID does not prove permission to download.

## 2. Multipart Filenames Are Data, Not Storage Paths

In Spring MVC:

~~~java
@PostMapping("/upload")
public void upload(@RequestParam("file") MultipartFile file) {
    String originalName = file.getOriginalFilename();
}
~~~

This is only a fragment explaining `MultipartFile`, not safe file-saving code. `getOriginalFilename()` can be `null`, empty, or contain path separators or special characters. None of the following strings can be trusted as filenames:

~~~text
../../application.yml
..\..\secret.txt
/var/app/config.yml
C:\Windows\System32\drivers\etc\hosts
invoice.pdf.exe
CON
NUL.txt
evil%00.png
name<script>.txt
~~~

**Dangerous approach:**

~~~java
// DO NOT DO THIS:
Path destination = Path.of("/app/uploads")
        .resolve(file.getOriginalFilename());

file.transferTo(destination);
~~~

If paths are built from client input, attackers can attempt path traversal, file overwrites, absolute paths, or symlink abuse. Stripping literal `../` with `replace` misses backslashes, encodings, symlinks, reserved device names, Unicode normalization, and TOCTOU races.

**Recommended design:**

1. Generate a **server-side** file ID such as a UUID, then construct the storage key from that ID and a server-controlled extension.
2. Configure a fixed storage root supplied by the deployer, outside public, static, or executable directories.
3. Enforce size limits, file counts, quotas, and body caps across proxies, servlet multipart config, and application logic.
4. Validate **actual bytes/content** with an appropriate parser. Client-supplied extensions and Content-Type values are untrusted metadata.
5. Create new files with `CREATE_NEW`; never overwrite arbitrarily.
6. Harden directory permissions; guard against symlinks and races if untrusted processes share the directory.
7. If storing the original name for display, bound its length as metadata and **escape it when rendering HTML, logs, or headers**.
8. Uploads shared with other users require malware scanning, quarantine, or content disarming based on risk, plus access controls and retention policies.

### Why normalize() Alone Is Still Not Enough

~~~java
// Fragment illustrating ONLY ONE layer of checks:
Path root = Path.of("/srv/uploads").toAbsolutePath().normalize();
Path candidate = root.resolve(untrustedName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Traversal");
}
~~~

`startsWith(Path)` compares path segments rather than string prefixes, yet `normalize()` only resolves `.` and `..` syntactically. It does not prevent symlinks or race conditions. For new uploads, keep client filenames out of filesystem paths altogether.

### Filename, MIME Type, and Bytes Are Independent

| Component | Example | Nature |
|---|---|---|
| Original filename | `image.png` | Client can set arbitrarily |
| Multipart Content-Type | `image/png` | Client can claim arbitrarily |
| File content | PNG signature, decodable image, valid UTF-8 text | Must be verified for actual format |

`Files.probeContentType` or extension checks assist classification but do not prove a file is safe. For images, bound dimensions/pixels and decode/re-encode; for ZIP archives, guard against Zip Slip and zip bombs; for PDF/Office files, keep parsers patched and inspect embedded content.

## 3. Headers Are Not Authentication Sources

### 3.1. Self-Asserted Roles and Tenants

~~~java
// Unsafe fragment:
@GetMapping("/admin")
public String admin(@RequestHeader("X-User-Role") String role) {
    return "admin".equals(role) ? "secret" : "denied";
}
~~~

Anyone can send `X-User-Role: admin`. The same applies to `X-User-Id`, `X-Tenant-Id`, and `X-Is-Admin`. Use Spring Security or real authentication: verify token signatures, issuer, audience, and expiration or server-side sessions, then check permissions on the target resource.

If a trusted API gateway injects `X-Authenticated-User`, the backend may trust it only when guaranteed that: the gateway **strips spoofed client headers**, authenticates before injecting the header, the backend has no untrusted direct network path, and internal connections/protocols are secured. Merely seeing a header present never equals an authenticated identity.

### 3.2. Host and Forwarded Headers

~~~text
Host: example.com
Forwarded: for=203.0.113.10;proto=https;host=example.com
X-Forwarded-For: 203.0.113.10
X-Forwarded-Host: example.com
X-Forwarded-Proto: https
X-Forwarded-Prefix: /public
~~~

These headers can be spoofed if an edge proxy fails to strip or overwrite client-supplied values, or if the backend is reachable directly. Never use them directly to generate password-reset links, OAuth redirects, IP-based ACLs, billing identities, or security audit records.

`server.forward-headers-strategy` in Spring Boot handles proxy URL metadata under proper configuration, **not authenticating forwarded headers on its own**. Derive public base URLs for sensitive callbacks or emails from trusted deployment configuration, never from `request.getHeader("Host")`.

### 3.3. Request IDs, Logs, and Other Headers

`X-Request-Id` helps tracing, yet attackers can submit duplicate IDs, huge strings, or control characters. Enforce length/character limits and structured logging; tamper-resistant audit trails need a separate **server-owned ID**.

- `Origin` is used for CORS; non-browser clients can forge it. CORS never replaces authentication.
- `Referer` can be omitted or forged; never use it for identity checks.
- `Cookie` is trustworthy only after the server validates the session or signed token.
- `User-Agent` and `Accept-Language` are arbitrary client strings.
- `Content-Type` describes how to interpret the body, not a guarantee of the bytes inside.
- `Content-Length`/`Transfer-Encoding` must be handled properly by the HTTP server/proxy; the app still needs request-size limits.
- Never log raw `Authorization`, `Cookie`, or all headers indiscriminately.
- Avoid reflecting arbitrary headers into `Location`, `Set-Cookie`, or `Content-Disposition` via raw string concatenation.

## 4. Request Attributes Differ from Request Headers

In Spring MVC there are three ways to read inputs:

~~~java
// Fragment inside a controller method:
@RequestHeader("X-Tenant-Id") String tenantFromHeader
@RequestParam("tenant") String tenantFromQuery
@RequestAttribute("tenantContext") TenantContext context
~~~

`TenantContext` is an illustrative domain type; the snippet is not a standalone Java method.

- `@RequestHeader` reads headers sent by the HTTP client or proxy.
- `@RequestParam` reads client-controlled query/form parameters.
- `@RequestAttribute` reads an attribute placed earlier on `HttpServletRequest` by **server-side code**.

**Important nuance:** a client cannot send a raw HTTP header to call `HttpServletRequest#setAttribute()` directly on the server. Request attributes typically originate from filters, interceptors, forwards, the servlet container, or Spring Framework. However, **they are still untrusted if the writer copied unvalidated client data**.

Broken example:

~~~java
// Fragment inside a filter - UNSAFE:
String claimed = request.getHeader("X-Tenant-Id");
request.setAttribute("verifiedTenant", claimed);

// A controller reading the attribute:
String tenant = (String) request.getAttribute("verifiedTenant");
~~~

Naming it `verifiedTenant` does not verify the input. Proper design: authenticate the principal; identify the requested tenant; verify tenant membership/resource ownership using trusted server data; then store a server-owned typed tenant context. Authentication and authorization checks are still required at resource access time.

Intentional pseudocode (not standalone compilable):

~~~java
VerifiedTenantContext context =
    membershipService.authorize(
        authenticatedPrincipal, requestedTenantId);

request.setAttribute("trusted.tenantContext", context);
~~~

`requestedTenantId` may come from the client, yet is **used only after the authorize step**. Framework-populated request attributes (such as forward/path/error attributes) do not automatically confer authorization either.

## 5. Spring Boot 3.5 Project: UTF-8 Upload with Server-Generated Storage Keys

This Maven demo accepts only UTF-8 text **up to 64 KiB**. Because of that small limit, reading bytes into RAM is acceptable for demonstrating validation. Never apply this pattern to large uploads or complex binary files.

~~~text
safe-request-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/saferequest/
    SafeRequestApplication.java
    UploadStore.java
    UploadController.java
  src/test/java/com/example/saferequest/
    UploadSecurityIntegrationTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-request-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. application.properties

~~~properties
server.port=8080

# Limits at the multipart resolver:
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB

# Root chosen by deployer, never from client:
app.storage.root=./target/demo-uploads
~~~

`./target/demo-uploads` is only for lab use; `mvn clean` deletes it. In production, store files in a dedicated data volume with least-privilege process permissions outside public, static, or executable roots.

### 5.3. Main Class

`src/main/java/com/example/saferequest/SafeRequestApplication.java`:

~~~java
package com.example.saferequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeRequestApplication.class, args);
    }
}
~~~

### 5.4. UploadStore.java

`src/main/java/com/example/saferequest/UploadStore.java`:

~~~java
package com.example.saferequest;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class UploadStore {

    private static final int MAX_BYTES = 64 * 1024;
    private final Path root;

    public UploadStore(Environment environment) {
        String configured = environment.getRequiredProperty(
                "app.storage.root");
        this.root = Path.of(configured).toAbsolutePath().normalize();
    }

    public UUID saveText(MultipartFile file) throws IOException {
        if (file.isEmpty() || file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload size");
        }

        // Reading the whole file only because the demo caps size at 64 KiB.
        byte[] bytes = file.getBytes();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload size");
        }

        validateUtf8(bytes);
        Files.createDirectories(root);

        // Never use getOriginalFilename() or getContentType()
        // to build a storage path.
        UUID id = UUID.randomUUID();
        Path target = root.resolve(id.toString() + ".txt");

        Files.write(target, bytes,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
        return id;
    }

    private static void validateUtf8(byte[] bytes) {
        try {
            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes)).toString();

            if (text.indexOf('\0') >= 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "NUL is not allowed");
            }
        } catch (CharacterCodingException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Expected valid UTF-8 text", ex);
        }
    }
}
~~~

Security controls applied:

1. `getOriginalFilename()` and `getContentType()` play no part in building the storage key or verifying text content.
2. `root` comes strictly from deployment config, and `target` uses a server UUID plus a fixed extension.
3. Both `getSize()` and `bytes.length` are bounded; multipart limits also apply at the framework/server level.
4. The UTF-8 decoder uses `CodingErrorAction.REPORT`, rejecting malformed byte sequences; note this is not malware scanning.
5. `CREATE_NEW` prevents overwriting existing files. The directory still needs filesystem permissions and symlink/race safeguards if untrusted local writers exist.
6. A random ID does not grant read or write authorization. Download endpoints must check principal/resource ownership.

### 5.5. UploadController.java

`src/main/java/com/example/saferequest/UploadController.java`:

~~~java
package com.example.saferequest;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
public class UploadController {

    private static final Pattern SAFE_REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final UploadStore store;

    public UploadController(UploadStore store) {
        this.store = store;
    }

    @PostMapping(
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            @RequestHeader(
                name = "X-Request-Id", required = false
            ) String claimedRequestId) throws IOException {

        UUID fileId = store.saveText(file);
        String requestId = safeRequestId(claimedRequestId);

        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Request-Id", requestId)
                .body(new UploadReceipt(
                        fileId.toString(), "stored"));
    }

    private static String safeRequestId(String value) {
        if (value != null &&
                SAFE_REQUEST_ID.matcher(value).matches()) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    public record UploadReceipt(String id, String status) {
    }
}
~~~

`X-Request-Id` is used solely as **format-filtered correlation metadata**; it never grants roles, tenants, or authentication. Clients can still supply any request ID matching the regex; trustworthy audit trails must generate a separate server-owned ID. The controller never uses client headers to derive file paths or IDs.

**Important:** This demo intentionally omits Spring Security, so the upload endpoint is unauthenticated. Never deploy publicly to production without adding authentication/authorization, quotas, rate limiting, per-tenant policies, and appropriate content scanning.

## 6. Running and Verifying with curl

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Create a text file in Bash:

~~~bash
printf 'hello\n' > note.txt
~~~

Normal upload:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -H "X-Request-Id: trace_42" \
  -F "file=@note.txt;type=text/plain"
~~~

Expected HTTP `201 Created`, header `X-Request-Id: trace_42`, body shaped like:

~~~json
{"id":"550e8400-e29b-41d4-a716-446655440000","status":"stored"}
~~~

The UUID above **only illustrates the format**; every real request receives a new ID. The file is saved under `target/demo-uploads/<actual-id>.txt`, ignoring the original filename.

Spoofing filename/MIME:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -F 'file=@note.txt;filename=../../outside.png;type=image/png'
~~~

Because the byte payload is valid UTF-8 text, it is accepted, yet stored under a UUID + `.txt`. The filename `../../outside.png` is never used as a path, and client-claimed MIME is not treated as proof of format.

Spoofing role headers:

~~~bash
curl -i "http://localhost:8080/api/files" \
  -H "X-User-Role: admin" \
  -H "X-Tenant-Id: victim" \
  -F "file=@note.txt"
~~~

This still returns 201 only because **the demo has no authentication**; it does not mean the client gained admin privileges. Those headers do not participate in file storage decisions. Production systems must enforce real authentication and authorization.

Empty file:

~~~bash
: > empty.txt
curl -i "http://localhost:8080/api/files" \
  -F "file=@empty.txt"
~~~

The service returns 400. Multipart uploads exceeding limits may be rejected before reaching the controller; exact error status/body details depend on exception handlers and server configuration and must be tested on real infrastructure.

## 7. Automated Tests with MockMvc

Create `src/test/java/com/example/saferequest/UploadSecurityIntegrationTest.java`:

~~~java
package com.example.saferequest;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(
    properties = "app.storage.root=./target/demo-uploads-test"
)
class UploadSecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper mapper;

    @Test
    void ignoresUntrustedFilenameAndMime() throws Exception {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../outside.png", "image/png", bytes);

        MvcResult result = mockMvc.perform(
                multipart("/api/files").file(file)
                    .header("X-User-Role", "admin")
                    .header("X-Request-Id", "bad request id"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(header().exists("X-Request-Id"))
            .andReturn();

        JsonNode json = mapper.readTree(
                result.getResponse().getContentAsString());
        String id = json.path("id").asText();

        assertDoesNotThrow(() -> UUID.fromString(id));
        assertEquals("stored", json.path("status").asText());

        String returnedRequestId =
                result.getResponse().getHeader("X-Request-Id");
        assertNotEquals("bad request id", returnedRequestId);
        assertDoesNotThrow(
                () -> UUID.fromString(returnedRequestId));

        Path saved = Path.of("target/demo-uploads-test")
                .resolve(id + ".txt");

        assertTrue(Files.isRegularFile(saved));
        assertArrayEquals(bytes, Files.readAllBytes(saved));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "empty.txt", "text/plain", new byte[0]);

        mockMvc.perform(multipart("/api/files").file(file))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidUtf8() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.png", "text/plain",
                new byte[]{(byte) 0xC3, (byte) 0x28});

        mockMvc.perform(multipart("/api/files").file(file))
                .andExpect(status().isBadRequest());
    }

    @Test
    void preservesOnlySafeCorrelationHeader() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "x.txt", "text/plain",
                "ok".getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/files").file(file)
                    .header("X-Request-Id", "trace_42"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    "X-Request-Id", "trace_42"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Tests verify that traversal filenames never control storage paths, claimed MIME types are not trusted as formats, self-asserted role headers do not grant permissions, invalid request IDs are replaced, and empty/malformed UTF-8 files are rejected. `MockMvc` simulates Spring MVC inside the Spring context, **without testing real HTTP sockets, proxies/WAFs, real Servlet multipart parsers, or HTTP framing**. Add integration tests against the real web server/ingress before production deployment.

## 8. Complex File Uploads Require Additional Validation Layers

**Images:** accept only required formats, verify signatures and actually decode using patched libraries, cap width/height/pixel counts, and consider re-encoding to strip dangerous metadata.

**PDF/Office:** keep parsers patched, inspect for macros/scripts/embedded links, run virus scanning or content disarming if untrusted files are shared, and bound CPU/memory/time.

**ZIP/TAR:** archives can contain entries like `../../config.yml` even after the outer archive is renamed to a UUID. Validate every entry path against Zip Slip, reject symlinks, and cap entry count, total uncompressed bytes, and nesting depth against zip bombs.

**Object storage:** generate server-side object keys scoped to the authenticated tenant namespace and a fresh ID, use scoped + expiring bucket policies or pre-signed URLs, and verify resource ownership before reads/downloads.

**Downloads:** a valid UUID is not authorization. Before serving a file, verify principal/tenant/resource permissions. Use a server-determined Content-Type, safe Content-Disposition, `X-Content-Type-Options: nosniff`, and proper cache headers. Never concatenate raw original filenames into response headers.

Illustrative fragment creating Content-Disposition with a server-controlled name:

~~~java
String value = org.springframework.http.ContentDisposition.attachment()
        .filename("download.txt", StandardCharsets.UTF_8)
        .build().toString();

responseHeaders.set(
        org.springframework.http.HttpHeaders.CONTENT_DISPOSITION,
        value);
~~~

`responseHeaders` here assumes an `HttpHeaders` instance created in an appropriate scope; this fragment is not a standalone Java file.

## 9. WebFlux Also Requires Provenance Analysis

In WebFlux, the corresponding equivalents are:

| Servlet MVC | Reactive WebFlux |
|---|---|
| `MultipartFile.getOriginalFilename()` | `FilePart.filename()` |
| `HttpServletRequest.getHeader()` | `ServerWebExchange.getRequest().getHeaders()` |
| `HttpServletRequest.getAttribute()` | `ServerWebExchange.getAttributes()` |
| Servlet `Filter` | Reactive `WebFilter` |
| Spring Security `SecurityFilterChain` | `SecurityWebFilterChain` |

`FilePart.filename()` remains client-asserted data. `ServerWebExchange.getAttributes()` is populated by the framework or filters, yet **may hold values copied from headers**; a `WebFilter` must never store raw `X-Tenant-Id` as a verified context without authentication.

WebFlux fragment (not a standalone class):

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange, WebFilterChain chain) {

    String clientTenant = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Tenant-Id");

    // clientTenant is unverified => never use it for authorization.
    return chain.filter(exchange);
}
~~~

WebFlux non-blocking I/O **does not automatically prevent** path traversal, MIME spoofing, or auth bypasses. For large files, use streaming/bounded processing and avoid `block()` or blocking filesystem calls on the event loop.

## 10. Dangerous Security Shortcuts

| Shortcut | Why it is wrong | Replace with |
|---|---|---|
| `filename.replace("../", "")` | Misses alternate path forms and symlinks | Server UUID + trusted root |
| `originalName.endsWith(".png")` | Filename does not prove file bytes | Format allowlist + parser |
| `getContentType()=="image/png"` | Client controls MIME header | Real content inspection |
| `X-User-Role=="admin"` | Unauthenticated self-assertion | Spring Security principal |
| `X-Tenant-Id` passes regex | Does not prove membership | Tenant/resource authorization |
| `request.setAttribute("trusted", header)` | Changes storage location, not trust | Verify provenance first |
| Using `Origin` as identity | CORS is not authentication | Token/session validation |
| Trusting every `X-Forwarded-For` | Clients can spoof headers | Trusted proxy chain |
| Building reset links from `Host` | Host header poisoning | Configured public base URL |
| Treating file UUIDs as secrets | Guessed/leaked IDs still need auth | Resource-level permission checks |
| Reading every upload into `byte[]` | Memory DoS on large files | Multipart limits + streaming |
| Saving uploads in static root | Exposed or dangerously served | Private upload storage |

## 11. Pre-Production Checklist

- [ ] Server never uses original filenames in paths; saved extensions are server-determined.
- [ ] File size, file count, and file types are bounded across proxy, server, and application.
- [ ] Content is checked by decoders/parsers; complex files undergo scanning/quarantine where needed.
- [ ] Storage has least-privilege permissions, is not unintentionally public, and cannot modify configs or certificates.
- [ ] Protected against path traversal, Zip Slip, symlinks/races, and unauthorized overwrites.
- [ ] Both uploads and downloads enforce authentication and tenant/resource ownership checks.
- [ ] Client-sent `X-User-Role`, `X-User-Id`, and `X-Tenant-Id` never grant permissions.
- [ ] Trusted proxies strip/overwrite forwarded and identity headers, and the backend exposes no direct bypass route.
- [ ] Host header never drives password-reset or redirect links; callback URLs use an allowlist.
- [ ] Request IDs are bounded in format and size, with separate server-owned IDs for audits.
- [ ] Never log secrets or unsanitized original filenames; encode HTML and header outputs properly.
- [ ] Request attributes carrying identity have audited writers and data flows.
- [ ] Tests cover spoofed headers, tenants, filenames, MIME types, file sizes, encodings, and malformed multipart requests.
- [ ] Integration tests run against a real HTTP server/gateway, not solely MockMvc.
- [ ] Quotas, rate limiting, cleanup jobs, and monitoring exist for upload abuse.

## References

- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html) — `MultipartFile` and multipart binding.
- [Spring Framework — Request Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html) — `@RequestHeader`.
- [Spring Framework — Request Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattribute.html) — `@RequestAttribute`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html) — Servlet stack and multipart handling.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — multipart limits and proxy-related configuration.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — defense in depth.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) — traversal attacks.
- [PortSwigger Web Security Academy — HTTP Host Header Attacks](https://portswigger.net/web-security/host-header) — Host header poisoning.

**Conclusion:** Clients submit filenames and headers purely as unverified claims; **never use them as storage paths, roles, or authenticated tenants**. Request attributes are set server-side, yet their values are trustworthy only when their origin and verification steps are trustworthy. Generating IDs on the server, inspecting content alongside quotas, enforcing proxy trust boundaries, and applying independent authentication and authorization are foundational to securing Spring Boot web applications.
