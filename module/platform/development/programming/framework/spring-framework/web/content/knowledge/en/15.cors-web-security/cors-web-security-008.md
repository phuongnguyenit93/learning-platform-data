# Controlling open redirects, uploaded content, and sensitive data in logs (Spring MVC)

## 1. Goal: three untrusted inputs, three additional protective layers

A Spring MVC application often receives **redirect target URLs**, **uploaded files**, and **request content** that gets written to logs. All three can contain data controlled by external users. When used without proper controls, they lead to distinct problems:

- **Open redirect**: an endpoint sends users to an attacker-chosen domain, abusing the main domain's trustworthiness for phishing, misdirecting OAuth flows, or leaking information.
- **Unrestricted file upload / unsafe file handling**: untrusted files are stored under dangerous names or directories, served as executable code or HTML, cause path traversal, carry malware, exhaust CPU/memory/disk, or bypass access control.
- **Sensitive-data logging and log injection**: tokens, session IDs, passwords, personal data, and form/multipart payloads enter logs; content with newlines/fake formatting corrupts or forges log records.

These three issues have distinct attack surfaces and mitigations. None of a single `@Valid`, a CORS configuration, or merely turning on Spring Security solves all three. General principles:

1. Identify **trust boundaries** before using input: URLs from query/form, file metadata, request headers, and raw bodies are not trustworthy simply because a controller received them.
2. Use **business-driven allowlists** instead of merely blocking a few dangerous strings.
3. Normalize processing and limit permissions/impact: redirect only to vetted destinations; give files server-generated names, verified formats, and isolated storage; log only fields needed for operations.
4. Apply limits on **size/time/rate**, authentication/authorization, CSRF, HTTP security headers, and infrastructure-layer defenses where appropriate.
5. Test both valid cases and adversarial inputs, verifying behavior across **HTTP responses**, the filesystem, and the observability pipeline.

This lesson belongs to the **Spring Framework - web** module under **CORS and web security**. The baseline sample code uses **Java 17+, Spring Boot 3.5.x / Spring Framework 6.2.x, Spring MVC Servlet**. The example does not enable Spring Security or provide production storage by itself; production sections specify the additional layers required.

## 2. Data flow model and trust decision points

```text
Client / Browser
     |
     +--- query/form "destination" ----> MVC controller
     |                                    |
     |                           ALLOWLIST target code
     |                                    |
     |                       Response 303 Location: /portal/...
     |                       never reflect raw URL
     |
     +--- multipart "file" -----------> multipart parser
     |                                    |
     |                        limit bytes, type/decoder,
     |                        dimensions, normalize image
     |                                    |
     |                          server-generated ID + name
     |                                    |
     |                      private storage outside webroot
     |                                    |
     |                         authenticated download handler
     |
     +--- request headers/body -------> servlet filters / MVC / app
                                          |
                                select safe event fields only
                                          |
                           structured log + newline escaping
                                          |
                            log sink with access/retention controls
```

Distinctions to keep clear:

- **Redirects** use a 3xx HTTP status and `Location` header. They do **not** prove the destination is trusted or that the user is authenticated.
- **CORS** controls whether browser JavaScript may read cross-origin responses per policy; it **does not prevent browsers from following HTTP redirects** or stop attackers from posting phishing links to users.
- **Content Security Policy (CSP)**, `X-Content-Type-Options: nosniff`, `Content-Disposition`, and cookie flags are helpful layers, yet **do not replace** file or redirect validation.
- Client-declared **MIME Content-Type** is merely input metadata. It can be wrong or intentionally forged.
- **Parameterized logging in logging frameworks** formats arguments and avoids string concatenation, yet **does not automatically strip PII, tokens, or CR/LF characters**.

## 3. What is an open redirect? Why is it dangerous?

Suppose an application exposes an endpoint:

```http
GET /login/continue?next=https://outside.example/collect HTTP/1.1
Host: trusted.example
```

If the server copies `next` verbatim into `Location`:

```http
HTTP/1.1 302 Found
Location: https://outside.example/collect
```

The user clicks a link starting with a trusted domain and is then sent to an external website. This is an **unvalidated redirect**. Attackers can:

- Use the trusted domain as a stepping stone in phishing campaigns.
- Bypass URL filters that check only **the domain of the initial link**.
- Manipulate **login/logout/return URL** flows.
- Combine flaws in OAuth/OIDC redirect registration, `state`, or token/code handling to leak data, depending on the model.
- Send users to malware-hosting sites or spoofed forms.

**Not every cross-domain redirect is a vulnerability.** Payments, SSO, or partner integrations sometimes require external redirects. The vulnerability lies in allowing **untrusted input to dictate the target without a sufficiently strict control policy**.

### 3.1. Anti-patterns in Spring MVC

```java
// DO NOT USE: request input directly dictates target URL.
@GetMapping("/go")
String go(@RequestParam String next) {
    return "redirect:" + next;
}
```

`redirect:` in MVC is a **directive to build a redirect view**, not a URL validator. Spring cannot know your business domain allowlist.

```java
// ALSO DO NOT USE: copying raw target into Location.
@GetMapping("/go")
ResponseEntity<Void> go(@RequestParam String next) {
    return ResponseEntity.status(HttpStatus.FOUND)
            .location(URI.create(next))
            .build();
}
```

These snippets illustrate security bugs, not recommended APIs. `URI.create` only parses URI syntax; it **does not decide** whether a domain or path is allowed.

### 3.2. Why blocking just the string "http" is insufficient

Forms worth checking when input is a URL/path:

| Client-proposed form | Danger |
| --- | --- |
| `https://attacker.example/path` | Absolute URL to an external domain |
| `//attacker.example/path` | Network-path reference: browser keeps current scheme yet uses external host |
| `\\\\attacker.example` or mixed slashes/backslashes | Different client/proxy/parser layers interpret separators differently |
| `https://trusted.example.attacker.example/` | Host starts like the trusted domain yet is actually different |
| `https://trusted.example@attacker.example/` | Part before `@` is userinfo; real host is after `@` |
| `https://TRUSTED.EXAMPLE./` | Domain case/trailing dot; requires canonicalization per policy |
| URL containing `%2f`, `%5c`, `%252f` | URL encoding and double-decoding ambiguity |
| URL containing CR/LF or encoded CR/LF | Header/log injection depending on downstream and validation |
| URL with `javascript:` / `data:` scheme | Not a safe HTTP(S) target for automatic redirection |
| Open-redirect endpoint on the trusted domain itself | Can become a **redirect chain** to an attacker |

Never rely on `next.startsWith("https://trusted.example")` or `next.contains("trusted.example")`. They can be fooled by `trusted.example.attacker.example`, userinfo, or a path containing the domain string.

## 4. Safest approach: accept a destination code, not a URL

If a feature only needs to redirect to a few internal pages, accept an **allowlisted destination code**, not a URL/path:

```text
Client sends: destination=dashboard
Server maps: "dashboard" -> "/portal/dashboard"

Client sends: destination=help
Server maps: "help" -> "/portal/help"

Client sends: destination=https://outside.example
Server: 400 Bad Request (no Location)
```

Advantages: no URL canonicalization issues, protocol-relative URLs, userinfo, IDN, or double encoding for unsupported targets. A server-owned fixed mapping is also easier to audit.

In section 9's sample code:

```java
String path = switch (destination) {
    case "dashboard" -> "/portal/dashboard";
    case "help" -> "/portal/help";
    default -> throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unsupported destination");
};

return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create(path))
        .build();
```

This is a **handler fragment**. Status `303 See Other` fits a completed form POST when you want the browser to perform a GET on the destination; for pure GET navigation, 302/303 depends on contract. **Never echo the raw destination back into HTML/logs/error messages**.

### 4.1. When external domain redirects must be supported

Consider only for flows with clear business requirements (payment partners, SSO). Design guidance:

1. Prefer **partner ID** → look up URL from trusted config, rather than letting the client supply an absolute URL.
2. If a URL really comes from the client, parse it with a URI parser and require scheme `https` (or explicit policy) plus an **exact host match** after canonicalization.
3. Use an **exact hosts / origins list**, not substrings or overly broad wildcards like `*.example.com`.
4. Account for **port, userinfo, path, query, trailing dot, IDN/punycode, fragment, percent encoding, and normalization**; reject ambiguous inputs rather than guessing.
5. If external consent is needed, show the destination host clearly to the user; never attach access tokens, session IDs, or passwords to URLs.
6. For OAuth2/OIDC, **`redirect_uri` must obey the provider's registration rules** and `state`/PKCE must be verified per flow; an "approximate allowlist" in the app does not replace protocol defenses.
7. Control redirect chains: a valid internal URL must not become a hop leading onward to an attacker.
8. Review differences between public base URLs, reverse proxies, trusted forwarded headers, and path prefixes during deployment.

**Common Spring misconception:** `RedirectView#setHosts(...)` or `UrlBasedViewResolver#setRedirectHosts(...)` uses host information during **URL encoding/session handling**, and is **not an absolute security allowlist to prevent open redirects**. Never use that setting in place of business validation/route mapping.

## 5. Redirects in Spring MVC: status, URI, scope, and data leakage

### 5.1. `redirect:` and `RedirectView`

A `@Controller` can return:

```java
@PostMapping("/save")
String save() {
    // Business save succeeded.
    return "redirect:/portal/dashboard";
}
```

This fragment uses a **server-fixed target**, unlike `"redirect:" + untrustedValue`. Spring creates a redirect view and typically emits status 302 by Servlet MVC default; 303/redirect view status can be configured per version/design.

With `ResponseEntity`:

```java
return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create("/portal/dashboard"))
        .build();
```

This pattern returns HTTP `303` directly and explicitly. A root-relative target `/portal/dashboard` assumes the app lives at the origin root. If deployed under `/shop` or a gateway prefix, construct the URL with the right **public** prefix; `RedirectView#setContextRelative(true)` can assist with context-relative view redirects. Avoid taking arbitrary hosts from clients to build external URLs.

### 5.2. Choosing the right status

| Status | Basic semantics | Notes |
| --- | --- | --- |
| `302 Found` | Temporary redirect; historical user agents may change POST to GET | Widely used for web navigation |
| `303 See Other` | Directs client to fetch representation at another URI, typically via GET | Ideal for Post-Redirect-Get |
| `307 Temporary Redirect` | Preserves HTTP method and body across redirect | Can inadvertently forward sensitive POST bodies if destination is untrusted |
| `308 Permanent Redirect` | Permanent redirect preserving method | Never use carelessly for temporary changes or user-controlled targets |
| `301 Moved Permanently` | Permanent move; clients/caches may store mapping | Careful with unstandardized links and auth/session flows |

If you redirect a POST containing a password or secret payload using `307/308` to an untrusted host, the client may resend the method/body to that host; this is a serious reason not to let clients dictate redirect targets. **303 does not by itself make a target safe**; it only changes follow-up method semantics.

### 5.3. Never put secrets in URLs, redirect models, or headers

Places where query parameters can leak: browser history, reverse-proxy access logs, analytics, monitoring, crash reports, referrers, or screenshots.

Never redirect like:

```text
Location: https://partner.example/landing?access_token=<secret>
Location: /portal/dashboard?password=<secret>
```

`RedirectAttributes.addAttribute(...)` can append values to the redirect URL; `addFlashAttribute(...)` stores temporary values for the next request (typically via session/FlashMap), suited for non-sensitive notices. **Flash attributes still reside in server state and are not a place to store secret tokens casually**.

For SPAs using OAuth redirects, follow proper OAuth/OIDC flows rather than emitting server tokens into URLs just for convenience.

## 6. File uploads: layers of untrusted input

A file upload request is usually `multipart/form-data`, for example:

```http
POST /api/images HTTP/1.1
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

<binary content>
--...--
```

All of `filename`, `Content-Type`, and the inner bytes are client-controlled. Attack types to watch out for:

- **Path traversal:** filenames like `../../config.yml` if concatenated directly into `Path`.
- **Extension confusion:** `photo.png.exe`, dots/special Unicode characters, case differences, double extensions, trailing dots/spaces; serving may misclassify content type or execute files.
- **MIME spoofing:** header claims `image/png` while body is HTML/script or another format.
- **Polyglot files:** one file can carry a valid signature of one format alongside dangerous secondary content; magic bytes alone cannot guarantee safety.
- **Malware and active content:** Office macros, SVG scripts, HTML, active PDF features, archive executables.
- **Archive extraction attacks:** ZIP slip (`../` in entry names), zip bombs, symbolic links, nested archives.
- **Image decompression bombs:** small compressed files that decode into enormous pixel dimensions.
- **Excessive resource usage:** huge uploads, excessive multipart parts, rapid repeated requests, disk quota exhaustion.
- **Unauthorized access:** private documents saved under guessable URLs or public static folders; missing owner checks on download.
- **File overwrite/race:** using original filename as target causing other files to be overwritten.
- **Log leakage:** writing raw original filenames or file contents into logs or trace/APM.

Controls must match **file type, user, trust level, and use case**, rather than enabling a single generic check and assuming all uploads are safe.

## 7. Strict upload policy: allowlist + content verification + storage isolation

### 7.1. File type allowlist

Pick a **short list needed for business**. For example, PNG profile pictures—do not open `image/*` and accept every image or script-bearing SVG. Distinguish:

1. **Extension**: merely a UX hint, not proof.
2. **Declared MIME**: `MultipartFile#getContentType()`, self-reported by the client.
3. **Signature/magic**: first few bytes; preliminary check, still insufficient for polyglots/complex formats.
4. **Decoder/parser validation**: structure successfully parsed by an appropriate library under resource limits.
5. **Canonicalization/CDR/transcoding**: rebuild a verified representation and strip dangerous metadata/sections where format allows.
6. **AV/sandbox scanning**: inspect for malware/executable traits per policy; does not replace validation and authorization.

**Never** take `file.getOriginalFilename()` and store it in `static/uploads/`; that pattern invites traversal, overwrites, public exposure, and unsafe type handling.

### 7.2. Multi-layer size limits

With Spring Boot 3.5 Servlet multipart:

```properties
# Example only for a demo accepting small PNGs:
spring.servlet.multipart.max-file-size=256KB
spring.servlet.multipart.max-request-size=320KB
```

These are **limits enforced by the multipart parser/container**. Still verify file bytes at the application layer and enforce quotas/rate limits at the gateway/server. Uploads may be rejected **before the controller runs**; errors typically involve `MaxUploadSizeExceededException` and HTTP 413 in configured error handling.

`max-file-size` differs from `max-request-size`: a request can have multiple parts and header overhead, so the total limit can exceed the per-file limit. Never trust `Content-Length` as exact in every request; chunked/streamed data can differ. For large streams, prefer streaming and byte-counting limits to avoid buffering everything in memory.

### 7.3. Store outside webroot with server-generated names

Recommended model:

```text
Upload request
  -> authentication + authorization + quota
  -> validate type/size/structure
  -> AV/CDR/normalization if needed
  -> quarantine area
  -> random generated storage key, never client filename
  -> private storage / object store
  -> save metadata record (owner, size, MIME, hash, status)
  -> download endpoint checking permissions
  -> safe Content-Disposition and Content-Type
```

In section 9's demo, **decoded and re-encoded PNGs** are saved into a random temporary directory created by the server using system-generated filenames, never served directly via Boot `static/**`. This is a **learning environment**, not durable production file storage; temp directories can be cleared, lack per-user isolation, and have no virus scanner.

### 7.4. Preventing path traversal and symlinks

Anti-pattern:

```java
// DANGEROUS: client-controlled filename determines path.
Path output = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(output);
```

If original filename contains `../` or an absolute path, unchecked resolve/normalize calls can escape the upload root. Race conditions can also arise if attackers can manipulate symlinks/paths inside the storage directory.

Prefer:

- Generating an opaque identifier via `UUID.randomUUID()` or a reliable random storage key.
- Creating files in a server-controlled private directory, e.g. `Files.createTempFile(root, "img-", ".png")`; never embed client filenames into paths.
- Never letting requests supply an **arbitrary relative path**.
- If client paths must be used, normalize/canonicalize, resolve the real path per policy, block traversal/symlinks, and check ownership, accounting for race conditions.
- Use storage APIs with dedicated key semantics on S3/GCS; do not confuse object-store keys with filesystem path security.

**Never store uploads in** `src/main/resources/static` / `public` / executable WAR/JAR directories assuming files are protected by auth. Those locations are meant for public static content.

## 8. HTTP communication on upload/download

A valid upload API can return `201 Created` with a server-assigned ID and `Location` pointing to the new resource:

```http
HTTP/1.1 201 Created
Location: /api/images/3a72ad90-f5cb-47ed-b97b-23278331fb9d
Content-Type: application/json

{"id":"3a72ad90-f5cb-47ed-b97b-23278331fb9d",
 "mediaType":"image/png"}
```

The ID here is a format example; real responses use server-generated random IDs. If uploads require **asynchronous malware scanning** before being considered ready, `202 Accepted` with processing/quarantine status is a sound design; **never publish files before they pass policy**.

Downloads must be governed **server-side**:

- Look up the record by opaque ID and verify the authenticated user has permission.
- Never concatenate an input ID directly into an arbitrary file path.
- Choose `Content-Type` from the **verified type**, never echoing raw upload content type.
- For content browsers might render actively like HTML/SVG/PDF, consider `Content-Disposition: attachment` alongside content scanning/sandboxing, CSP, or serving from an isolated origin.
- Set `X-Content-Type-Options: nosniff` where appropriate.
- Use `Cache-Control: private` or `no-store` for sensitive documents; do not assume public CDNs may cache every uploaded image.
- Never return filesystem paths, internal storage keys, or raw exception messages.

**Never treat a UUID as an authorization mechanism.** Hard-to-guess UUIDs hinder enumeration, yet GET/download must still verify the user's permission on the resource.

## 9. Runnable Spring Boot 3.5 / Java 17 example

The demo includes:

- `POST /navigation/continue?destination=dashboard|help` returning `303 Location` from an **allowlisted code**.
- `GET /portal/dashboard` and `GET /portal/help` to observe redirect targets.
- `POST /api/images` accepting only small PNGs via multipart; checking size before/after reading, using Java ImageIO to verify format, bounding width/height, **re-encoding PNG**, and saving under random names in a private temp directory.
- `GET /api/images/{uuid}` returning the normalized PNG as an **attachment** with `nosniff` and `Cache-Control: no-store`.
- Logging only server-generated IDs and output byte size; never logging request bodies, original filenames, or cookies/tokens.
- MockMvc tests for allowlist, invalid redirects, valid/invalid uploads, and downloads.

**Intentional demo limitations:** no authentication/authorization, AV scan, user quotas, shared persistent storage, key rotation, or moderation. **Never deploy an upload/retrieval endpoint publicly identical to this demo**; add those layers before production.

### 9.1. Gradle and multipart properties

In a Boot 3.5 project already configured with Boot plugin/repositories/Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a `build.gradle` fragment; add it to a standard Boot project rather than treating it as a standalone Gradle file. Java `ImageIO` belongs to the JDK `java.desktop` module (included in standard Java 17; keep the module in custom jlink images).

Create `src/main/resources/application.properties`:

```properties
spring.servlet.multipart.max-file-size=256KB
spring.servlet.multipart.max-request-size=320KB

# Do not proactively emit potentially sensitive request params/headers
# into Spring MVC debug logs:
spring.mvc.log-request-details=false
```

`spring.mvc.log-request-details=false` is Boot 3.5's usual default, yet stating it explicitly clarifies intent. This setting **does not suppress logs written by custom code, reverse proxies, servlet access logs, security filters, or other APMs**.

### 9.2. Java application/controller/upload logic

Create **`src/main/java/demo/safeweb/SafeWebApplication.java`**:

```java
package demo.safeweb;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SafeWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeWebApplication.class, args);
    }
}

@RestController
class NavigationController {
    @PostMapping("/navigation/continue")
    ResponseEntity<Void> continueTo(
            @RequestParam String destination) {

        String path = switch (destination) {
            case "dashboard" -> "/portal/dashboard";
            case "help" -> "/portal/help";
            default -> throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported destination");
        };

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(path))
                .build();
    }

    @GetMapping("/portal/dashboard")
    String dashboard() {
        return "dashboard";
    }

    @GetMapping("/portal/help")
    String help() {
        return "help";
    }
}

record ImageResponse(String id, String mediaType) {}

@RestController
@RequestMapping("/api/images")
class ImageController {
    private static final Logger log =
            LoggerFactory.getLogger(ImageController.class);

    private static final int MAX_INPUT_BYTES = 256 * 1024;
    private static final int MAX_DIMENSION = 1024;
    private static final int MAX_PIXELS = 1024 * 1024;
    private static final int MAX_OUTPUT_BYTES = 4 * 1024 * 1024;

    private final Path privateRoot;
    private final ConcurrentMap<UUID, Path> saved =
            new ConcurrentHashMap<>();

    // DEMO ONLY: random temporary directory, not public/static.
    // Production: dedicated private storage, access control and lifecycle.
    ImageController() throws IOException {
        privateRoot = Files.createTempDirectory("safe-image-demo-");
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<ImageResponse> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty() || file.getSize() > MAX_INPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid image size");
        }

        // Verify actual bytes, not originalFilename or declared MIME.
        byte[] input = file.getBytes();
        if (input.length == 0 || input.length > MAX_INPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid image size");
        }

        BufferedImage decoded = decodePng(input);

        // Re-encode the decoded pixels; do not serve the original bytes.
        ByteArrayOutputStream normalized = new ByteArrayOutputStream();
        if (!ImageIO.write(decoded, "png", normalized)) {
            throw new IOException("PNG encoder is unavailable");
        }
        byte[] canonicalPng = normalized.toByteArray();
        if (canonicalPng.length > MAX_OUTPUT_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Image output too large");
        }

        UUID id = UUID.randomUUID();
        Path generated = Files.createTempFile(
                privateRoot, "image-", ".png");

        try {
            Files.write(generated, canonicalPng);
            saved.put(id, generated);
        } catch (IOException ex) {
            Files.deleteIfExists(generated);
            throw ex;
        }

        // Log server-generated, bounded metadata only.
        log.info("image_upload_saved imageId={} bytes={}",
                id, canonicalPng.length);

        URI location = URI.create("/api/images/" + id);
        return ResponseEntity.created(location)
                .body(new ImageResponse(id.toString(), "image/png"));
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.IMAGE_PNG_VALUE)
    ResponseEntity<byte[]> download(@PathVariable UUID id)
            throws IOException {

        Path stored = saved.get(id);
        if (stored == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Image not found");
        }

        // DEMO ONLY: real application must verify owner/permission first.
        byte[] content = Files.readAllBytes(stored);
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_PNG)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"image.png\"")
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(content);
    }

    private static BufferedImage decodePng(byte[] bytes)
            throws IOException {

        try (ImageInputStream input =
                     ImageIO.createImageInputStream(
                             new ByteArrayInputStream(bytes))) {

            if (input == null) {
                throw invalidImage();
            }

            Iterator<ImageReader> readers =
                    ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw invalidImage();
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                if (!reader.getFormatName()
                        .equalsIgnoreCase("png")) {
                    throw invalidImage();
                }

                int width = reader.getWidth(0);
                int height = reader.getHeight(0);

                if (width < 1 || height < 1
                        || width > MAX_DIMENSION
                        || height > MAX_DIMENSION
                        || (long) width * height > MAX_PIXELS) {
                    throw invalidImage();
                }

                BufferedImage image = reader.read(0);
                if (image == null) {
                    throw invalidImage();
                }
                return image;
            } catch (IOException ex) {
                throw invalidImage();
            } finally {
                reader.dispose();
            }
        }
    }

    private static ResponseStatusException invalidImage() {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid PNG image");
    }
}
```

**Valid Java 17 single-file class structure:** only `SafeWebApplication` is public; the remaining controllers and record are package-private in the same package `demo.safeweb`. Java 17 provides switch expressions, `ImageIO`, and `UUID`. With Boot web dependencies and a full JDK, Spring component scan discovers both controllers.

**Important regarding assurance level:** ImageIO with bounded size/dimensions followed by re-encoding blocks many disguised files and strips unwanted metadata/raw payloads, yet is **still not a sandbox or antivirus**. Image decoders can have CVEs; small compressed inputs can still stress decoding; for high-risk file types, use process isolation, patched codecs, sandbox/AV/CDR, and stronger resource quotas. `MAX_INPUT_BYTES` bounds the raw file; `MAX_DIMENSION` and `MAX_PIXELS` bound pixel count; they do not replace OS-level memory/CPU limits.

**Storage details:** `Files.createTempDirectory` creates a private directory outside static resources; `Files.createTempFile` generates a server-controlled name, never using `MultipartFile.getOriginalFilename()`. `saved` is only an in-memory map — restarts lose mappings, temp files may remain uncleaned, and there is no retention management. In real deployments, replace with a metadata DB/storage service and policy-based cleanup/quotas.

**Download details:** the response is an `attachment` with a fixed filename, normalized MIME, and `nosniff`. Never let browsers inline-render uploaded HTML/SVG. Production requires auth/authorization on **both upload and download**, owner/tenant checks, and scan status verification.

### 9.3. Testing with curl

```bash
./gradlew bootRun
```

Navigate to an allowed page (use `-i` to inspect 303 instead of following the redirect):

```bash
curl -i -X POST \
  'http://localhost:8080/navigation/continue' \
  --data 'destination=dashboard'
```

Expected status `303 See Other` and `Location: /portal/dashboard`.

Try an external redirect proposed by the client:

```bash
curl -i -X POST \
  'http://localhost:8080/navigation/continue' \
  --data-urlencode 'destination=https://outside.example/collect'
```

Expected `400 Bad Request`, **with no attacker-controlled `Location`**.

Upload a valid PNG image (the file must actually be a PNG):

```bash
curl -i -X POST \
  'http://localhost:8080/api/images' \
  -F 'file=@avatar.png;type=image/png'
```

If the image is under 256 KiB, within 1024×1024 dimensions, and decodable, the server is expected to return `201 Created`, `Location: /api/images/<actual-uuid>`, and a JSON body with the ID. `<actual-uuid>` is an instructional placeholder, not a predictable ID.

Follow the received `Location` URL:

```bash
curl -i 'http://localhost:8080/api/images/<actual-uuid>'
```

Expected result: `200 OK`, `Content-Type: image/png`, `Content-Disposition: attachment; filename="image.png"`, `X-Content-Type-Options: nosniff`, and the normalized PNG. With `curl -o downloaded.png`, use the exact URL returned by 201.

Try renaming a text file to `avatar.png`: the endpoint rejects it because ImageIO cannot decode it as a valid PNG. If you send an oversized image, the multipart layer may block it before the controller; exact error status/body depends on exception/error handling and the container. Demo inputs are not to be considered malware-scanned.

## 10. Integration tests with MockMvc

Create **`src/test/java/demo/safeweb/SafeWebApplicationTests.java`**:

```java
package demo.safeweb;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeWebApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void knownDestinationRedirectsToInternalRoute()
            throws Exception {

        mvc.perform(post("/navigation/continue")
                .param("destination", "dashboard"))
            .andExpect(status().isSeeOther())
            .andExpect(header().string(
                    HttpHeaders.LOCATION, "/portal/dashboard"));
    }

    @Test
    void externalDestinationIsRejectedWithoutLocation()
            throws Exception {

        MvcResult result = mvc.perform(post("/navigation/continue")
                .param("destination",
                        "https://outside.example/collect"))
            .andExpect(status().isBadRequest())
            .andReturn();

        assertNull(result.getResponse()
                .getHeader(HttpHeaders.LOCATION));
    }

    @Test
    void protocolRelativeDestinationIsRejected()
            throws Exception {

        mvc.perform(post("/navigation/continue")
                .param("destination", "//outside.example/path"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void actualPngIsNormalizedAndDownloaded()
            throws Exception {

        BufferedImage small =
                new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        assertTrue(ImageIO.write(small, "png", output));

        // Client-controlled filename is deliberately suspicious.
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../private-config.yml",
                "application/octet-stream", output.toByteArray());

        MvcResult uploaded = mvc.perform(
                multipart("/api/images").file(file))
            .andExpect(status().isCreated())
            .andReturn();

        String location = uploaded.getResponse()
                .getHeader(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.matches(
                "/api/images/[0-9a-fA-F-]{36}"));

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(content()
                    .contentTypeCompatibleWith(MediaType.IMAGE_PNG))
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"image.png\""));
    }

    @Test
    void fakePngBytesAreRejected() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "image.png", "image/png",
                "not a png".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/images").file(file))
            .andExpect(status().isBadRequest());
    }

    @Test
    void oversizedFileIsRejectedAtApplicationLayer()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "large.png", "image/png",
                new byte[256 * 1024 + 1]);

        mvc.perform(multipart("/api/images").file(file))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownImageIdReturns404() throws Exception {
        mvc.perform(get("/api/images/"
                + "00000000-0000-0000-0000-000000000000"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./gradlew test
```

With the Boot 3.5 / JDK ImageIO code above, all seven tests are **designed to pass**. This is the expected outcome by inspection, **not the output of an actual test run**. `MockMvc` does not test OS filesystem permissions, proxy max body sizes, multi-node setups, upload quotas, antivirus/CDR, or log pipelines; add corresponding integration/security/penetration tests.

What the tests verify:

- Redirects reject full URLs or `//host`.
- Upload bodies must be decodable PNGs, not merely self-declared `Content-Type: image/png`.
- Uploads with suspicious filenames are still saved under generated names and never overwrite user-chosen paths.
- Downloads return server-chosen MIME and attachment handling.
- Oversized inputs in MockMvc are rejected by the controller.
- Nothing here implies the demo has **user authorization**, malware scanning, or production storage hardening.

## 11. Non-negotiable requirements for production uploads

### 11.1. Authentication, authorization, and ownership

- Only authorized users may upload.
- Each file record needs owner/tenant, scan/quarantine status, normalized MIME, size, storage key, creation time, and retention policy.
- Downloads check permissions **every time**, even when the caller knows the UUID.
- Prevent IDOR/BOLA: changing `/api/images/{id}` to another user's ID must not yield the file.
- For public files, use public object storage/CDNs with content rules; for private files, use short-lived signed URLs or authenticated download proxies.
- Scoped, time-limited signed URLs are themselves **credentials**; never log them verbatim or leak them in referrers.

### 11.2. Antivirus/sandbox and content disarm

Re-encoding a PNG does not guarantee the decoder has no security bugs or that images never carry dangerous payloads. For PDF, DOCX, ZIP, SVG, or active-content formats, dedicated handling is required:

| File type | Examples of extra controls |
| --- | --- |
| PNG/JPEG | Safe decoders, pixel/dimension limits, metadata stripping, re-encoding, image-library patching |
| SVG | Never treat as harmless image; scripts/links can exist; forbid or sanitize strictly and serve isolated |
| PDF | Type/content scanners, sandbox/CDR if needed, attachment or isolated viewer |
| DOCX/XLSX | CDR/macro policy, AV scan, never preview directly without sandboxing |
| ZIP/TAR | Limit file count, nested depth, decompressed size; prevent zip-slip/symlinks |
| HTML/JS | Never store/serve on the same authenticated origin without proper isolation |
| Executables | Disallow upload by default or allow only in strictly controlled workflows |

Never "check magic bytes only" and then open PDF/Office/ZIP files unrestricted; parsers and preview engines are themselves attack surfaces.

### 11.3. Transactions, consistency, and cleanup

- With async scanning, never expose files while status is `PENDING`; return job/upload status per contract.
- If a DB record is created yet object upload fails (or vice versa), perform rollback/compensation/cleanup.
- Enforce per-user/tenant quotas, max object counts, max daily bytes, lifecycle TTLs, and retention/deletion compliance.
- Use server-generated keys, avoid collisions/overwrites; choose appropriate write semantics and bucket permissions on object stores.
- Manage temp files created by both the multipart parser and the application; never let temp files accumulate unboundedly.
- Configure antivirus/decoder timeouts, memory/CPU/file-descriptor limits, and isolated processing workers.
- Image re-encoding can alter color profiles/alpha/metadata; verify outputs satisfy product requirements.

## 12. Sensitive data in logs: what must not be logged

The OWASP Logging Cheat Sheet lists items that generally must not be logged directly or must be masked/sanitized/hidden:

| Data | Risk if logged | Mitigation |
| --- | --- | --- |
| `Authorization: Bearer <token>` | Token can be replayed | Never log tokens; log auth result and event ID if needed |
| `Cookie` / `Set-Cookie` / `JSESSIONID` | Session hijacking | Strip session IDs completely from logs |
| Passwords, OTPs, reset tokens, private keys | Credential disclosure | Never log and never echo raw |
| OAuth codes, signed URLs, API keys | Account takeover or file access | Redact tokens and query parameters |
| Raw JSON/form bodies | May contain PII/passwords or financial data | Avoid logging bodies; log allowlisted validated metadata |
| Multipart filenames, bytes, document text | May contain PII, newline injection, malware payloads | Never log verbatim; use server-generated IDs instead |
| Emails, phone numbers, addresses, government IDs | Privacy/compliance impact | Log only when strictly required per law/policy with proper pseudonymization |
| Full exception messages/stack traces | May contain SQL, paths, inputs, secrets | Sanitize, classify errors; log stacks with access and retention controls |
| Full URLs/queries/referrers | Queries may carry tokens/passwords | Log route templates; drop or allowlist query keys |
| Raw IPs, User-Agents | PII or untrusted data | Per threat model, follow policy and sanitize |

**There is no rule saying "every log must be empty."** Security event logs are valuable for detecting attacks, yet should record only purposeful fields classified by sensitivity, with clear access controls and retention limits.

### 12.1. Parameterized logging is not redaction

Avoid:

```java
// Anti-pattern: logging raw password and token.
log.info("Login user={} password={} token={}",
        request.getParameter("user"),
        request.getParameter("password"),
        request.getHeader("Authorization"));
```

Safer form:

```java
// Fragment: fields selected according to policy.
log.info("login_attempt result={} authMethod={} requestId={}",
        "rejected", "password", trustedRequestId);
```

Here `trustedRequestId` must be server-generated or strictly validated from trusted infrastructure. Never switch to `log.info("userInput={}", rawInput)` assuming placeholders strip CR/LF; placeholders are **not content filters**.

### 12.2. Log injection / log forging

A request field can contain newline characters to forge fake log records:

```text
Malicious input (simulated):
  queryName = "Alice\r\n2026-01-01 ERROR admin-login-success"

If logged via direct concatenation:
  INFO queryName=Alice
  2026-01-01 ERROR admin-login-success
```

Log readers, SIEMs, or line-based parsers may misinterpret the second line as an independent event. Delimiters like `,`, `|`, tabs, JSON quotes, and control characters also cause trouble unless properly encoded.

Mitigations:

- Prefer **structured JSON logging** using a proper serializer rather than hand-building JSON strings.
- If client data must be logged in an allowed field, **sanitize CR/LF/control characters, escape for the sink**, and bound length and values.
- For User-Agent/referer/filename, consider logging a **classification** or appropriate hash/tokenization instead of raw text.
- Never suppress security event logging for "trusted" IPs/users; avoid blinding yourself to compromised accounts.
- Timestamp and tag log records using the trusted system, never accepting client timestamps verbatim.
- Store logs in access-restricted sinks with tamper resistance; configure SIEM retention and alerts appropriately.

A minimal helper if an untrusted string genuinely needs logging:

```java
static String safeLogField(String value) {
    if (value == null) {
        return "missing";
    }

    StringBuilder out = new StringBuilder();
    int limit = Math.min(value.length(), 120);

    for (int i = 0; i < limit; i++) {
        char c = value.charAt(i);
        if (Character.isISOControl(c)) {
            out.append('_');
        } else {
            out.append(c);
        }
    }
    return out.toString();
}
```

This is a **method fragment** illustrating only control-character normalization and length bounding. **It does not detect secrets/PII and does not replace escaping for JSON/XML/log sinks**. Never use this helper to "justify" logging passwords/tokens — those values must **never be logged**.

## 13. Log route templates, never repeat raw request URLs

Example with an endpoint:

```text
POST /api/images?access_token=SECRET
Authorization: Bearer SECRET
Cookie: JSESSIONID=SECRET
```

Do not log the full URI, query string, or raw headers. A more useful and less sensitive record:

```text
event=image_upload_saved requestId=<server-generated-id>
resourceId=<uuid> result=created outputBytes=1132
```

**The values above are examples**, not output from a live run. For performance analysis, record route template `/api/images`, HTTP status, duration buckets, and byte counts; never put file bytes or original filenames into tracing spans.

### 13.1. Generating correlation IDs properly

When a request correlation ID is needed, a simple approach is generating a UUID on entry, placing it in MDC, and **cleaning up in `finally`** when the filter finishes:

```java
@Component
class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String requestId = UUID.randomUUID().toString();
        MDC.put("requestId", requestId);
        try {
            response.setHeader("X-Request-Id", requestId);
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
```

This is a **standalone class fragment**, requiring Jakarta Servlet imports, `@Component`, `OncePerRequestFilter`, `MDC`, and `UUID`. Do not add it to the demo project unless needed; if added, configure registration/order so the server-generated request ID is present wherever expected.

For async/multi-threaded requests, MDC **does not automatically propagate across threads**. Use a context propagation strategy and per-thread/dispatch cleanup when business requirements demand it. Never keep `HttpServletRequest`/tokens in long-lived ThreadLocals.

If accepting a request ID from a proxy, trust only configured proxies, restrict charset/length, and prevent CRLF injection. When trust is uncertain, generate a fresh ID inside the application.

## 14. Log levels, filters, Spring Boot, and configuration scope

In Boot 3.5:

```properties
spring.mvc.log-request-details=false
logging.level.org.springframework.web=INFO
```

This restricts certain MVC debug/trace request details, yet **does not guarantee logs are completely free of sensitive data**.

Also check:

- Application loggers written by developers (`log.info/debug/error`).
- Spring Security authentication/authorization logs.
- Servlet container access logs; patterns may capture URLs/queries, cookies, or headers.
- API gateway/reverse proxy/WAF request logs.
- Distributed tracing/APM auto-instrumentation (span tags/header capture).
- Exception reporting/Sentry/crash dumps.
- CI/build deployment logs containing env vars/secrets.
- Message queue/integration adapters logging request/response bodies.
- Central logging platforms: who can access them, encryption at rest/in transit, retention, and deletion/incident response.

**Never enable framework-wide `TRACE` in production** without proper masking policies. For urgent incident debugging, use time-boxed flags/accounts with minimal scope, then disable and handle collected logs per retention/privacy rules.

### 14.1. Log errors without leaking exception inputs

Avoid:

```java
// Anti-pattern if ex.getMessage() contains raw request/token/SQL.
log.error("Upload failed, filename={}, cause={}",
        file.getOriginalFilename(), ex.getMessage(), ex);
```

Prefer:

```java
log.warn("image_upload_rejected reason={} requestId={}",
        "invalid_format", trustedRequestId);
```

Log exception stacks only when operationally justified and assessed not to leak secrets; if stacks are needed in an internal sink, protect that sink more tightly than public logs and never echo raw messages into HTTP error bodies.

## 15. How do Spring Security and CORS relate?

### 15.1. CORS does not prevent open redirects or malicious uploads

CORS is a browser mechanism deciding whether a **cross-origin** web page may read a response. If the browser is instructed to navigate to `https://outside.example` via Location, a CORS policy on JSON APIs is not a "wall" stopping redirects.

Likewise, a non-browser client can call a multipart endpoint if network and auth permit, **even when `Access-Control-Allow-Origin` allows no domains**. CORS is not authentication.

### 15.2. CSRF still matters

If upload and navigation endpoints use **cookie session authentication** and mutate server state, CSRF protection is required depending on the architecture. Cross-origin JavaScript/browsers can still trigger certain form requests even without reading responses. With Spring Security, configure `SecurityFilterChain` per endpoint and include CSRF tokens for HTML forms or appropriate SPA strategies.

Never disable CSRF application-wide just to make a multipart example test pass. The demo omits Spring Security to keep its scope focused; production needs authentication, authorization, CSRF, rate limits, tenant isolation, and content-type policies.

### 15.3. Response security headers

Headers commonly useful when serving user-uploaded content:

| Header | Purpose |
| --- | --- |
| `Content-Type` matching verified type | Tells browser the genuine media type |
| `X-Content-Type-Options: nosniff` | Reduces certain MIME sniffing risks |
| `Content-Disposition: attachment` | Reduces risk of browser rendering active content inline |
| `Cache-Control: no-store` / private | Restricts caching of private data |
| `Content-Security-Policy` | Restricts script/resource sources on relevant origins/views |
| `Referrer-Policy` | Reduces leaking paths/queries externally |
| `Strict-Transport-Security` over HTTPS | Enforces HTTPS for the domain when deployed properly |

**No single header lets you skip content validation.** For instance, serving raw SVG/HTML from an origin holding session cookies carries very different risks than serving a normalized PNG as an attachment.

## 16. When user-specified download filenames are needed

Common scenario: a product wants the browser to save a file with a user-chosen display name. Avoid concatenating raw filenames directly into HTTP headers:

```java
// Anti-pattern: CR/LF, quotes, or unusual characters in name pose risks.
response.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + originalFilename + "\"");
```

Better:

1. Store the display name separately in metadata DB, validated for Unicode, length, control chars, and policy.
2. Generate an independent storage filename; never use the display name as a filesystem path.
3. When emitting the header, use **Spring's `ContentDisposition` builder** with proper encoding/quoting instead of raw string concatenation.
4. For risky types, force a safe filename/extension derived from the verified media type rather than trusting the original extension.
5. If original names are unnecessary, always use a fixed name like the demo's `image.png`.

Fragment:

```java
ContentDisposition disposition =
        ContentDisposition.attachment()
                .filename(safeDisplayName, StandardCharsets.UTF_8)
                .build();

return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION,
                disposition.toString())
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(fileBytes);
```

This is a handler fragment requiring imports for `ContentDisposition`, `StandardCharsets`, and `HttpHeaders`, plus declared `safeDisplayName`/`fileBytes`. **The builder does not replace a business content allowlist**; `safeDisplayName` must be validated and bounded beforehand. `Content-Type: application/octet-stream` is not optimal for every format; choose per format and download purpose.

## 17. Error handling without information leaks

An invalid upload error should return a brief, stable error body:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Invalid image",
  "status": 400,
  "detail": "The uploaded file is not an accepted PNG image"
}
```

This is an **illustrative schema**, not a guarantee every Boot app automatically returns this exact body. With Spring Framework 6+, `ProblemDetail`/`@RestControllerAdvice` can standardize errors; avoid exposing internal exception messages like `/tmp/...`, raw filenames, or parser stack traces in responses.

Recommended classification:

| Scenario | Typically appropriate status |
| --- | --- |
| Unsupported redirect token | `400 Bad Request` |
| Uploaded content is not a valid PNG | `400 Bad Request` or `415 Unsupported Media Type` per API contract |
| File/request exceeds limits | `413 Content Too Large` (called `Payload Too Large` in some versions) |
| Unauthenticated upload/download | `401 Unauthorized` |
| Authenticated yet lacking permission | `403 Forbidden` |
| File ID absent/hidden | `404 Not Found` when appropriate |
| Scanner/storage unavailable | `503 Service Unavailable` or situation-appropriate status |
| Upload accepted yet scanning async | `202 Accepted` |
| Upload processed and created | `201 Created` |

Never hardcode every error as `200 OK` with `{"success":false}`. HTTP statuses help clients and monitoring distinguish failures. Never place raw user input into `ProblemDetail.detail` if it could leak tokens or sensitive content.

## 18. Deploying behind reverse proxies, gateways, and CDNs

A real system interprets URLs, bodies, and logs in many places:

```text
Browser
   |
CDN/WAF
   |
Reverse Proxy/API Gateway
   |
Servlet container (Tomcat...)
   |
Spring Security FilterChain
   |
Spring MVC controller
   |
Private object storage / scanner
   |
Central log/metrics/tracing
```

Checks must stay consistent across layers:

- **Redirects:** Gateways/proxies may normalize paths, schemes, and hosts; never trust client-sent `Host`/`X-Forwarded-Host` when constructing external URLs. Trust proxy headers only from verified sources.
- **Upload limits:** Proxy, connector, multipart parser, app validator, and object-store limits must align consistently; oversized requests may be blocked before entering the controller.
- **Storage:** Shared object storage needs bucket ACLs, encryption, retention, quarantine, and signed URL policies; never expose private keys directly.
- **Logs:** Proxies/CDNs may log full URLs/queries/cookies before Spring sees the request; configure masking right at that layer.
- **Caching:** Avoid public CDN caching for private downloads. Signed URLs are credentials needing short TTLs and log redaction.
- **Incident response:** Track counts of rejected redirects/uploads, scan failures, anomalous rates, and log injection attempts without storing raw malicious payloads or secrets in event feeds.

### Should the server call client-supplied URLs to "verify safety"?

No. If the server performs an HTTP GET to `next` to test the destination, it can introduce **SSRF**: attackers point it at internal addresses, cloud metadata, or DNS rebinding targets. Prevent open redirects via structural URL validation/policy and mapping, **never by fetching arbitrary URLs**.

## 19. Security testing: test both allowed and blocked paths

### Redirects

- `destination=dashboard` → 303, `Location` matches local path.
- `destination=help` → 303, other local path.
- Absolute HTTP(S) URL → 400, no external Location.
- `//outside.example` → 400.
- URLs with userinfo, backslashes, percent-encoded slashes, CRLF → 400.
- Missing/unknown destination → 400 per API contract.
- If real external partner redirects exist, test exact origin/scheme/port/host/path, URL normalization, and redirect chains.
- Check 302/303/307/308 status codes for body/method forwarding semantics.

### Uploads

- Valid PNG within limits → 201, server-generated ID, downloadable valid PNG.
- JPEG/GIF/SVG/HTML/TXT disguised with `image/png` header → rejected when policy is PNG-only.
- PNG file with filename `../secrets.txt` → no user-controlled path created; generated storage name used.
- PNG decompression bomb (huge metadata dimensions) → rejected before full decode where possible.
- Empty/oversized files, excessive parts, overly long names, malformed multipart boundaries → rejected/bounded.
- Multipart POST from unauthorized user → 401/403 when Security is enabled.
- Knowing another user's UUID → 403/404 per disclosure policy.
- Unscanned uploaded file → inaccessible publicly.
- Test storage permissions, cleanup, quotas/rate limits, scanning timeouts, and concurrent writes.

### Logging

- Inject CRLF into User-Agent/filename/query → produces no forged log events.
- Include tokens/emails/passwords in body/query → absent from application logs, access logs, and APM spans unless vetted by policy.
- Validation errors do not log rejected sensitive values.
- Error stack traces do not appear in HTTP responses.
- Tracing correlation IDs are always server-generated or validated, free of unusual characters.
- Only operational roles can read logs; retention and deletion policies are enforced.

**Do not test only that the API status is 400 or 201**; inspect the side effects themselves: `Location` headers, file bytes, file placement, and log records.

## 20. Common design mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Trusted domain redirects to strange site | Used `redirect:` + untrusted URL | Route via allowlisted target codes |
| Domain `startsWith` check bypassed | Userinfo, subdomain suffix, IDN, encoded URL | Exact canonical URI policy or partner ID |
| `setRedirectHosts` configured yet still redirects externally | Confused URL-encoding API with security validator | Validate business destination before redirecting |
| PNG avatar is actually HTML | Trusted `getContentType()` or extension | Decoder/format validation, normalized output |
| Upload overwrites server file | Trusted original filename/path | Random storage names, private directory |
| Small image causes OOM on decode | Huge compressed dimensions | Pixel limits, size limits, sandboxing |
| User guesses UUID and downloads another's file | Checked file ID only, not owner | Authorization/tenant checks |
| Uploaded PDF/SVG executes scripts | Served inline from authenticated origin | Forbid/sanitize/CDR, attachment/isolated origin |
| Disk fills up over time | Missing quotas/cleanup/retention | Background lifecycle/metrics, storage policies |
| Logs contain JWTs after enabling DEBUG | Raw requests/headers logged | Redaction policy across all layers, disable request details |
| Fake ERROR line appears in logs | CRLF/log injection | Structured encoding, bounded allowlisted fields |
| APM still captures query tokens though app logger is clean | Instrumentation records URL/query | Sanitize in tracing/gateway config |
| Redirect after POST loses or forwards body | Confused 303 with 307/308 | Pick status by semantics, disallow external targets |
| MockMvc passes yet proxy still accepts huge payload | Tested only MVC layer | HTTP integration through gateway/container |
| Download has `nosniff` yet still leaks PII | Missing auth or public cache | Auth/authorization + private/no-store |
| Scanned files still carry malware | Scanner limits or missing signatures | Defense in depth, sandbox/CDR, updates |

## 21. Spring Boot / Spring Framework version differences

| Platform | What to verify |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | Servlet API usually `javax.servlet.*`; MultipartFile/RedirectView exist; error responses differ from 6.x |
| Spring Framework 6.x / Boot 3.x | Java 17+, `jakarta.servlet.*`, `ProblemDetail`; properties `spring.servlet.multipart.*` and `spring.mvc.log-request-details` as shown |
| Spring Framework 7.x / Boot 4.x | Web/security APIs remain yet some modules/starters/JSON/test packages change; check migration guides, property metadata, and component registrations |

**Do not copy `javax.servlet.*` code from Boot 2 into Boot 3/4**. ImageIO is part of Java SE and works on JDK 17+, though custom runtimes must retain the required image/JDK modules. For native images, test reflection/codec/resource support separately.

Spring Security 6/7 handles authentication, authorization, CSRF, headers, and sessions via `SecurityFilterChain`; the demo endpoints **do not get these automatically** from `spring-boot-starter-web` alone. Add the Security starter and custom policies for production.

## 22. Pre-production checklist for web applications

- [ ] No redirect target constructed from raw `next`/`returnUrl`. Internal routes use allowlist codes; external partners come from controlled config.
- [ ] Destination policy validates scheme/host/port/path/canonicalization if external redirects are truly required.
- [ ] OAuth/OIDC callback URIs/state/PKCE are validated per protocol, never confused with generic redirects.
- [ ] Upload type allowlist has a business owner, file/request size limits, and max concurrency.
- [ ] Never trust `originalFilename` or `Content-Type`; verify bytes/parser, bound decompression, and re-encode/CDR where appropriate.
- [ ] AV/sandbox/quarantine policy exists for applicable data types; never publish before scan completion.
- [ ] Storage is outside public webroot with opaque generated keys, preventing traversal/symlinks/overwrites.
- [ ] Both upload and download enforce authentication/authorization, quotas, and CSRF if using cookie sessions.
- [ ] Download `Content-Type`/`Content-Disposition`/`nosniff`/cache headers are chosen by the server.
- [ ] No raw passwords/tokens/cookies/signed URLs/PII or multipart bodies are written to logs.
- [ ] Log events use allowlisted fields, control-char escaping, size limits, and structured formatting.
- [ ] Gateway/container/HTTP client/APM/SIEM also enforce log redaction and retention policies.
- [ ] HTTP error bodies omit stack traces, filesystem paths, SQL, and secrets.
- [ ] Tests cover malicious redirects, disguised/oversized/metadata uploads, unauthorized downloads, and log injection.
- [ ] Lifecycle/cleanup/retention of uploaded objects and incident-response processes are defined.
- [ ] Security metrics track event counts/statuses without collecting sensitive payloads.

## 23. Exercises and self-assessment questions

1. Why is `return "redirect:" + next` in Spring MVC an open redirect when `next` comes from the request? Does `RedirectView#setHosts` replace a domain validator?
2. A URL `https://portal.example.attacker.example` passes `startsWith("https://portal.example")`. Redesign this using partner IDs or an exact URI policy.
3. Compare 302, 303, 307, and 308 when a client sends a POST with a sensitive body. When are 307/308 dangerous if the target is attacker-chosen?
4. If `avatar.png` contains HTML bytes with header `image/png`, what happens when an API checks only extension/MIME? Add decoder validation.
5. Why is `Files.createTempFile(privateRoot,"image-",".png")` safer than `privateRoot.resolve(file.getOriginalFilename())`? Which risks does it still leave unresolved?
6. A small compressed PNG encodes 80,000×80,000 pixel dimensions. Why is a 256 KiB upload limit insufficient? How should limits be enforced before/inside the decoder?
7. A user does not know another user's UUID yet can guess/brute-force or receive leaked links. Why do downloads still require authorization?
8. An app allows SVG uploads and serves them inline from the same cookie-authenticated origin. What risks arise and how should serving/allowlisting change?
9. User-Agent input containing CR/LF causes a fake WARNING line in logs. Propose structured logging, escaping, max length, and tests.
10. With `spring.mvc.log-request-details=false`, if a proxy logs the full query containing a token, does the problem remain? Who is responsible for redaction?
11. Add a mock multipart test with original filename `../../passwords.txt` and a valid PNG body. Why should the test not assert the file was saved under that name?
12. Design async scanning with `202 Accepted`, statuses `PENDING/SAFE/REJECTED`, and download permissions; explain when a file may be published.
13. When Spring Security uses cookie authentication, does CORS prevent cross-origin form POSTs from causing CSRF? Which layers are required?
14. Explain why raw `Exception#getMessage()` should not be logged for every multipart/body parse error, and how to classify errors safely.
15. Write a verification checklist for uploads and logs across 3 environments: local Boot app, staging behind a gateway, and production with object storage.

## 24. Official references

- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): allowlisting destinations, avoiding raw return URLs.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): extension/MIME validation, storage isolation, AV/CDR, permissions, and CSRF.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data not to log, log injection, event collection, integrity.
- [OWASP — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF with cookie sessions and state-changing requests.
- [Spring Framework 6.2 — RedirectView API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html): redirect URLs, contextRelative, and redirect hosts semantics.
- [Spring Framework 6.2 — Multipart Support](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/multipart.html): multipart parsing, MultipartFile, and MVC Servlet.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.servlet.multipart.max-file-size`, `max-request-size`, `spring.mvc.log-request-details`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): request protection, cookie/session flows.
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): explicit redirect/create status and headers.
- [Java 17 — ImageIO](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html): image format decoder/encoder primitives; security resource limits remain application responsibility.
