# Safe File Downloads: Filenames, Destination Paths, and Handling Incomplete Downloads

## 1. The Problem: Receiving HTTP 200 Does Not Mean You Have a Safe File

A Java application downloading files over HTTP/HTTPS typically has to address **three independent risk categories**:

1. **Untrusted filenames:** The server may send `Content-Disposition: attachment; filename="../../outside.txt"`, a URL with a hard-to-control filename, or a user may supply a name containing path characters, reserved device names, or confusing Unicode characters.
2. **Destination path and filesystem:** Naively concatenating a filename onto a directory string can write outside the intended directory, overwrite an existing file, follow a symlink, or race with another process while saving.
3. **Incomplete download content:** The HTTP body may be cut off mid-stream due to network loss, timeout, out-of-disk-space, cancellation, premature server close, mismatched `Content-Length`, or checksum failure. If written directly to the final file, the application and user may assume a half-written file is ready.

A proper pipeline:

```text
Allowed HTTPS source
         |
         v
HttpClient with explicit redirect policy
         |
         v
Check status, content type, length/size limit
         |
         v
Choose filename per APPLICATION policy
         |
         v
Verify destination directory is managed/trusted
         |
         v
Create random .part file IN destination directory
         |
         v
Stream bytes in chunks + count bytes + hash
         |
         +--> HTTP/I/O error / over limit / hash/length mismatch? --> delete .part
         |
         v
Body ends validly and checks pass
         |
         v
Publish to final name (no unintended overwrite)
         |
         v
Only now report download success
```

**Key principle:** filename, path, and content each cross their own trust boundary. `Content-Type`, `Content-Disposition`, URL, `Content-Length`, and status code are **metadata supplied by the other party**, not proof that the file is safe or complete.

This lesson uses Java 17+ with `java.net.http.HttpClient` and `java.nio.file.Files/Path`. The runnable example uses **loopback HTTP** so it can be tested without Internet access; **production must prefer HTTPS and control connection destinations**.

## 2. Threat Model: What Are We Protecting?

| Input/Scenario | Risk | Mitigation |
| --- | --- | --- |
| `filename="../../app.properties"` from HTTP | Path traversal, modifying files outside download area | Do not use directly; application-selected name, allowlist |
| `filename="C:\\Windows\\..."` or `/etc/passwd` | Absolute path or cross-OS path separators | Validate single name, reject `/`, `\\`, `:`, and path segments |
| `filename="CON.txt"` on Windows | Reserved device name | Reject reserved names on supported platforms |
| Two tasks saving `report.pdf` concurrently | Overwrite, commit race | Unique temp file, publish without `REPLACE_EXISTING`, concurrency strategy |
| Final path is a symlink | Writing to an unintended target | Do not follow symlinks, keep destination directory trusted, prevent races |
| Server returns 404 with HTML body | Saving an error page with `.pdf` extension | Check status before creating final file |
| Server writes 20 MB then disconnects despite declaring 100 MB | Incomplete file | Handle stream exceptions, verify byte count where appropriate, checksum |
| Server sends gzip body but app expects raw ZIP/PDF | Wrong bytes/hash or saving wrong format | Explicit `Content-Encoding` policy and hash on the right representation |
| Very large file / no Content-Length | Disk exhaustion, memory pressure | Enforce total byte limit **while streaming** |
| Body downloads completely but contains malicious content | File exists but is unsafe to open | Validate format, security scan per policy, never auto-execute |
| User-supplied URL points to internal metadata | SSRF, internal network resource exposure | URL/host allowlist, restrict egress, control redirects/DNS |
| Network fails after partial download | Orphaned `.part` files and wrong displayed status | Cleanup, failed state, controlled retry/resume |

Do not solve this with a single `Path.normalize()` call and assume the entire problem is safe. Normalization only processes path components **syntactically**; it does not solve symlinks, permissions, races, or malicious content.

## 3. Prefer **Application-Decided Safe Filenames**

### 3.1. The simplest and strongest approach: do not take the storage name from the server

Suppose the application is downloading a report provided by an API. Instead of reading `Content-Disposition.filename` to build the path, name it deterministically from a **controlled ID** or an application-generated name:

```text
Trusted download directory: /srv/app/downloads
Application-selected name:  invoice-2026-001.pdf
Server Content-Disposition: attachment; filename="../../config.yml"

Final intended path: /srv/app/downloads/invoice-2026-001.pdf
Untrusted server filename: ignored, may be logged in escaped form if needed
```

The example above illustrates a Unix path; on Windows the same principle applies with different path syntax. If you need to keep the original name for UI display, store the **display name** as separate metadata rather than turning it directly into a filesystem name.

**Do not treat the Content-Disposition header as a command**. RFC 6266 treats the name suggested via `filename`/`filename*` as input that must be handled safely. It may contain percent encoding, Unicode, path separators, hidden names, misleading extensions, and attacks based on OS differences.

### 3.2. If users are allowed to name files, use a strict allowlist

A simple, portable policy:

```java
private static final Pattern SAFE_NAME =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,79}");

private static final Pattern WINDOWS_DEVICE = Pattern.compile(
        "(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?");

static String validateName(String name) {
    if (name == null || !SAFE_NAME.matcher(name).matches()
            || name.endsWith(".")
            || WINDOWS_DEVICE.matcher(name).matches()) {
        throw new IllegalArgumentException("Unsafe filename");
    }
    return name;
}
```

*Code snippet inside a class importing `java.util.regex.Pattern`; the same method is used in the standalone program in section 9.*

It intentionally allows only **ASCII single names** (up to 80 characters) starting with a letter/digit followed by characters in `[A-Za-z0-9._-]`. Thus it rejects `../secret`, `..\\secret`, `C:\\...`, `/tmp/x`, unusual whitespace, control characters, and `:`; it also excludes basic Windows device names such as `CON` and `NUL.txt`. Disallowing a trailing dot avoids certain name-interpretation discrepancies on Windows.

Do not treat this regex as the sole solution for **every** filename on every filesystem. In particular, if supporting Unicode, you need an NFC normalization policy, defenses against lookalike characters, special Windows names, trailing dots/spaces, filesystem case sensitivity, and path length **in bytes**. If a file extension is needed based on media type, **select the extension from the validated file type**, rather than simply copying the extension proposed by the server.

### 3.3. Filename sanitization approaches that look right but are insufficient

- `Paths.get(filename).getFileName()` is OS-dependent. On Unix, `\\` may not be treated as a separator; a Windows path string can slip through if you rely solely on this method.
- `filename.replace("../","")` only catches one traversal form, missing `..\\`, escaped variants, double encoding, and other separators.
- `URLDecoder.decode(...)` is not a filename validator; decoding can turn `%2f` into `/` or introduce Unicode differences.
- Using the URL basename after redirects is also not guaranteed safe; the URL path may be attacker-controlled and is not equivalent to an application storage name.
- Never treat an `.exe` or `.pdf` extension as proof of content: the server can send an HTML/error page or an executable while declaring an innocent-looking name.

If you must support `Content-Disposition`, use an RFC 6266/5987-compliant parser and **then still apply your own naming policy**. Prefer `filename*` per the standard's rules when both appear, but **never grant the parsed result authority over the path**.

## 4. Destination Paths: `Path.resolve`, `normalize`, and the Truth About Symlinks

Do not concatenate strings like:

```java
// COUNTEREXAMPLE: filename could be "../secret.txt".
Path bad = Path.of(downloadDirString + "/" + serverFilename);
```

*Snippet intentionally omits variable declarations; do not use in production.*

Once you have a trusted name, use Java NIO:

```java
Path directory = trustedDirectory.toAbsolutePath().normalize();
String safeName = validateName(chosenName);
Path destination = directory.resolve(safeName);
if (!destination.getParent().equals(directory)) {
    throw new IOException("Destination escaped directory");
}
```

*Snippet placed inside a method with corresponding variables and imports; the runnable program in section 9 uses the same logic.* A `/` in a string should not be how you "manually join paths"; `resolve` uses the filesystem's path semantics.

**Layered path checks:**

1. **The root directory must be managed:** obtain it from trusted service configuration, not directly from a request body/HTTP header. Create the directory with appropriate permissions and do not allow untrusted users to write files or symlinks into it.
2. **The child name must be a single filename**, not a multi-segment relative path. Run `validateName` *before* `resolve`.
3. **Containment check** using `Path` components (`startsWith`/`getParent`) is an additional line of defense; avoid raw string prefix comparisons like `"/data/reports2".startsWith("/data/reports")`.
4. **Symlinks/hardlinks:** `normalize()` and lexical containment checks do **not** eliminate the risk of a directory component or target file being replaced with a symlink. `Files.isDirectory(..., LinkOption.NOFOLLOW_LINKS)` is a useful check for the final component, but it does not lock the path during the operation.
5. **TOCTOU (time-of-check to time-of-use):** between `Files.exists` and `Files.move`, another actor can swap the file/path. Proper filesystem permissions, an application-owned directory, non-overwriting operations, and synchronization design are required.
6. **An adversary with write access to the destination directory** is a much harder problem. Consider `SecureDirectoryStream` when supported by the provider, operations relative to a directory handle, or low-level OS APIs with appropriate no-follow/atomic semantics. Do not attribute absolute safety to a `resolve().normalize()` call.

A practical policy: the service creates the download directory itself, only the service has write permission, end users only read/receive the path after completion, and uploads/arbitrary user files are never allowed to create symlinks in the same directory.

## 5. Why You Must Use a Temporary File in the **Same Directory**

Principle: **never download directly to the final filename**.

Do not do this:

```java
// COUNTEREXAMPLE: if the stream dies mid-way, report.pdf already exists
// but may contain only 20% of the content.
Files.copy(response.body(), destination);
```

Instead:

```java
Path partial = Files.createTempFile(directory, ".download-", ".part");
boolean committed = false;
try {
    // Stream bytes -> partial; check length, size limit, digest...
    // Only publish to final destination when all checks PASS.
    Files.move(partial, destination); // Do not pass REPLACE_EXISTING.
    committed = true;
} finally {
    if (!committed) {
        Files.deleteIfExists(partial);
    }
}
```

*This is an illustrative skeleton; not a complete program as variables and byte-writing code are omitted.*

Benefits:

- A **random** temporary name avoids collisions between concurrent downloads.
- Calling `createTempFile(directory, ...)` directly **inside the destination directory** avoids accidentally copying across filesystems on commit and makes managing unfinished files easier.
- An incomplete file has a `.part` extension and is not mistaken for the final document.
- On error, the application **deletes only the temporary file created by that download attempt**; it does not delete the final file or delete all `*.part` files regardless of owner.
- In `finally`, if `move` fails, `partial` is deleted; any pre-existing final file remains intact.

**Warning about atomicity:** `Files.move(partial, destination)` **without `ATOMIC_MOVE`** means Java does not guarantee that publishing is atomic or crash-safe across all filesystems/providers. On many local filesystems, move/rename within the same directory behaves nearly atomically, but **you cannot infer a general API guarantee from that**.

If the system requires an atomic commit, you must verify that the filesystem supports `StandardCopyOption.ATOMIC_MOVE` and a **no-overwrite** strategy. With `ATOMIC_MOVE`, Java states that behavior **when the target already exists is implementation-specific**; do not conclude that simply adding `ATOMIC_MOVE` provides both atomicity and strict no-clobber. You may need a name-reservation mechanism, single-writer locking/coordination, no-clobber hard-linking on supported filesystems, or an OS primitive with the desired semantics.

**Durability on power loss** is also distinct from atomicity: where high durability is required, you may need `FileChannel.force(...)` and directory fsync as supported by the platform. A completed download at the application layer does not automatically guarantee bytes have been physically flushed before power loss.

## 6. Checking Status and Headers Before Writing

For full-file downloads via `GET`, an easily verifiable rule is to accept only **`200 OK`** (and apply a dedicated protocol if you explicitly support other statuses):

| HTTP status | Meaning in a simple downloader |
| --- | --- |
| `200 OK` | May be a full representation; still must stream completely and verify |
| `206 Partial Content` | **Must not** be treated as a full file without a specific range/resume protocol |
| `301/302/307/308` | Redirect; do not auto-follow if the target is not yet permitted by policy |
| `304 Not Modified` | No new response body to download; only use with cache validators and a verified cached copy |
| `401/403` | Auth/permission failure; do not save error page as destination file |
| `404` | Not found; do not save error content under the requested filename |
| `416 Range Not Satisfiable` | Invalid range/resume; do not treat as complete data |
| `429/503` | Rate-limited/overloaded; apply conditional retry/backoff, do not publish |
| Other success statuses, e.g. `204` | Do not assume a full file; requires an explicit API contract |

**Note:** `HttpClient.Redirect.NEVER` can be configured on Java's `HttpClient` to avoid following redirects automatically. If redirects are allowed, you must validate **every** new location/target against HTTPS, host allowlist, and anti-SSRF policy. Do not assume that starting on HTTPS means every redirect stays on HTTPS.

### 6.1. `Content-Length` is a byte count, not proof of integrity

The `Content-Length` value counts HTTP content bytes per protocol rules, **not characters**. When a server returns gzipped content, it typically reflects the encoded bytes; if a library decodes content coding before delivering the body to the app, you must understand whether the bytes read by the app still correspond to the header.

A streaming downloader should:

- Enforce `MAX_BYTES` from **application policy**, not from the server's `Content-Length`.
- If the server declares a Content-Length larger than max, it may **reject early**.
- While reading, still **count actual bytes** and fail immediately before writing past the limit.
- When a declared Content-Length is present and the app receives the exact bytes described by the header, it can compare the received byte count after stream EOF.
- When Content-Length is absent (e.g. chunked HTTP/1.1 or HTTP/2), still enforce max bytes and handle HTTP stack completion/errors.
- Remember that if Content-Length is accurate but the server sends **a different file of the same size**, length checking will not detect it. Use a trusted checksum or signature/manifest when integrity is required.

Do not pre-allocate a byte array sized to an untrusted Content-Length. Use an `InputStream` and an 8 KiB/64 KiB buffer with a byte-counting limit.

### 6.2. `Content-Encoding` and byte representation

If the server returns `Content-Encoding: gzip`, there are two distinct goals:

1. **Save the raw encoded HTTP content:** the file will contain gzip bytes; the digest and Content-Length apply to those encoded bytes.
2. **Save the decoded representation:** you must gunzip, set a **separate limit for decompressed bytes**, compute the appropriate digest, and have a clear extension/media-type policy.

In the section 9 example, the downloader **only accepts no Content-Encoding or `identity`**, so compressed bytes are not turned into a file with a misleading extension. For applications supporting gzip, you must design the pipeline and limits accordingly; never mix encoded and decoded bytes arbitrarily.

### 6.3. `Content-Disposition` is a hint, not permission to write a file

A header might look like:

```http
Content-Disposition: attachment; filename="../../outside.txt"
Content-Type: text/plain
Content-Length: 22
```

The example intentionally includes a traversal name. The downloader **ignores that filename** and only uses the trusted name `report.txt`. This is the actual tested behavior of the program below.

Do not copy raw headers into unescaped logs if they contain CR/LF or control characters; many HTTP parsers filter header syntax, but logging/reporting code must still protect itself.

## 7. What Counts as an "Incomplete Download" and How Do You Know It Is Complete?

A download stream can stop for many reasons:

```text
CONNECTED
    |
    v
HTTP HEADERS RECEIVED
    |
    +--> invalid status / declared size > limit -> REJECT
    |
    v
TEMP_CREATED
    |
    v
STREAMING BYTES
    |
    +--> timeout / premature EOF / read IOException -> FAILED + DELETE TEMP
    +--> disk full / write IOException -> FAILED + DELETE TEMP
    +--> actual bytes > max -> FAILED + DELETE TEMP
    |
    v
STREAM ENDED SUCCESSFULLY
    |
    +--> declared size mismatch -> FAILED + DELETE TEMP
    +--> trusted digest mismatch -> FAILED + DELETE TEMP
    +--> media-type/content policy fail -> FAILED + DELETE TEMP
    |
    v
COMMIT TO FINAL PATH
    |
    +--> destination already exists / move fail -> FAILED
    |
    v
COMPLETE
```

**The minimum safe completion indicators** are: appropriate HTTP status, body streaming throws no exception, byte limit is not exceeded, policy-required expected size/hash checks pass, and **publishing succeeds**. Do not treat HTTP 200, the creation of the temp file, or receiving the first N bytes as "download finished."

Specifically:

- **HTTP/1.1 Content-Length:** if the server declares 100 bytes but the connection sends only 25 and closes, the HTTP client can report an error for an incomplete body. Java's `HttpClient.BodyHandlers.ofInputStream()` helps detect this via an exception during reading, because `send(...)` returning does not mean the InputStream has been fully consumed.
- **Chunked HTTP/1.1:** a connection may close before the **terminating zero-size chunk**; a compliant HTTP stack typically reports a framing error rather than a normal EOF.
- **HTTP/2:** streams have their own framing/end-of-stream signaling; do not rely on TCP close to know a stream succeeded. The HTTP library is responsible for handling and reporting errors.
- **No length or trusted digest:** a response that the server **closes cleanly while declaring a shorter payload than the true content** can still be a valid HTTP message; the downloader cannot guess the missing portion from the observed bytes alone. To know it is the exact expected file, you must have an **expected length/checksum from a trusted channel**.
- **Disk write failure:** even if the network is completely fine, writing to a full disk or lacking permissions is a download failure at the application layer. Never publish an incomplete file.
- **Process crash/power loss:** `finally` only runs during normal execution via stack unwinding; **it is not guaranteed to run when the process is killed or power is lost**. You need a startup inventory/recovery mechanism for stale `.part` files by owner/session/age, taking care not to delete files currently in use by another task.

Checking a hash alone does not resolve whether the file source is trustworthy. **The expected SHA-256 must come from an independent/trusted source**, such as a signed manifest or protected and authenticated metadata; if you take the digest sent alongside the payload by a compromised server, an attacker can replace both.

## 8. Designing a Streaming Downloader on Java 17

Relevant Java classes:

| API | Role |
| --- | --- |
| `HttpClient.newBuilder()` | Configure connection, proxy/redirect, connect timeout |
| `HttpRequest.newBuilder(uri).GET()` | Create GET request |
| `HttpResponse.BodyHandlers.ofInputStream()` | Return response body as a stream for chunked processing |
| `HttpResponse.statusCode()` | Separate error responses from file content |
| `HttpHeaders.firstValueAsLong("Content-Length")` | Inspect declared length, which may be absent |
| `Files.createTempFile(directory, ..., ".part")` | Create a unique temp file in the destination directory |
| `Files.newOutputStream(partial, WRITE)` | Write bytes without holding the entire file in RAM |
| `MessageDigest.getInstance("SHA-256")` | Compute hash incrementally while streaming |
| `Files.move(partial, destination)` | Publish step under a non-unintended-overwrite policy |
| `Files.deleteIfExists(partial)` | Clean up temp file when not committed |
| `LinkOption.NOFOLLOW_LINKS` | Check target without following links where supported by the API |

Critical order of operations in a download method:

1. Validate **filename and path configuration** before the network request.
2. Permit only URIs allowed by policy (the demo program hardcodes loopback); set an explicit redirect policy.
3. Send the request, **close the response InputStream** on every branch, including error statuses.
4. Accept only the expected status, reject unsupported content codings, and reject a known Content-Length exceeding the threshold.
5. Create `.part`, stream the body through a small byte array; update size and hash **on the exact bytes written**.
6. After valid EOF, validate length and expected digest.
7. Publish to the approved name; if publishing does not complete, delete the temp file in `finally`.
8. Return success **only after** the publish step completes.

**Java 17's `HttpClient` is not `AutoCloseable`**, so do not use `try (HttpClient client = ...)` in examples targeting `--release 17`. The client is reused across multiple requests.

## 9. Complete Java 17 Program: One Success and Six Errors That Must Be Rejected

This example runs entirely on loopback and creates its own temporary directory for testing. Its characteristics:

- `HttpServer` returns a normal body and intentionally sends `Content-Disposition` with filename `../../outside.txt`. The application **does not use the server's filename**, choosing `report.txt` instead.
- `HttpClient` sets `Redirect.NEVER`, has demo-level connect and request timeouts, and receives the body via `ofInputStream()`.
- The file is streamed via `.part`; max bytes and SHA-256 hash are provided by the caller.
- Before publishing, the code checks size, hash, and status; it omits `REPLACE_EXISTING` to avoid unintended overwrites.
- The program tests traversal, an existing file, wrong checksum, oversized response, truncated stream, and HTTP 404.
- At the end of the test, the directory contains only **one successful file** (the report file). Temp files from failed attempts have been deleted.

**File `SafeHttpDownloadDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class SafeHttpDownloadDemo {
    private static final Pattern SAFE_NAME =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,79}");
    private static final Pattern WINDOWS_DEVICE = Pattern.compile(
            "(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?");

    static String validateName(String name) {
        if (name == null || !SAFE_NAME.matcher(name).matches()
                || name.endsWith(".")
                || WINDOWS_DEVICE.matcher(name).matches()) {
            throw new IllegalArgumentException("Unsafe filename");
        }
        return name;
    }

    static long download(HttpClient client, URI uri, Path trustedDirectory,
            String chosenName, long maxBytes, String expectedSha256)
            throws Exception {
        String filename = validateName(chosenName);
        if (!"http".equalsIgnoreCase(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost())) {
            throw new IllegalArgumentException("Demo permits loopback only");
        }
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Invalid byte limit");
        }

        Path directory = trustedDirectory.toAbsolutePath().normalize();
        if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Not a trusted physical directory");
        }
        Path destination = directory.resolve(filename);
        if (!destination.getParent().equals(directory)) {
            throw new IOException("Destination escaped directory");
        }
        if (Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) {
            throw new FileAlreadyExistsException(destination.toString());
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<InputStream> response = client.send(request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream stream = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Expected HTTP 200");
            }
            if (response.headers().firstValue("Content-Encoding")
                    .filter(v -> !v.equalsIgnoreCase("identity"))
                    .isPresent()) {
                throw new IOException("Unexpected content coding");
            }
            long declared = response.headers()
                    .firstValueAsLong("Content-Length").orElse(-1L);
            if (declared > maxBytes) {
                throw new IOException("Declared content too large");
            }

            Path partial = Files.createTempFile(directory,
                    ".download-", ".part");
            boolean committed = false;
            try {
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                long count = 0;
                byte[] buffer = new byte[8192];
                try (OutputStream output = Files.newOutputStream(partial,
                        StandardOpenOption.WRITE)) {
                    int n;
                    while ((n = stream.read(buffer)) != -1) {
                        if (n > maxBytes - count) {
                            throw new IOException("Stream exceeds byte limit");
                        }
                        output.write(buffer, 0, n);
                        sha.update(buffer, 0, n);
                        count += n;
                    }
                }
                if (declared >= 0 && count != declared) {
                    throw new IOException("Content-Length mismatch");
                }
                String actualHash = HexFormat.of()
                        .formatHex(sha.digest());
                if (expectedSha256 != null
                        && !actualHash.equalsIgnoreCase(expectedSha256)) {
                    throw new IOException("SHA-256 mismatch");
                }
                Files.move(partial, destination); // No REPLACE_EXISTING.
                committed = true;
                return count;
            } finally {
                if (!committed) {
                    Files.deleteIfExists(partial);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = "Hello, safe download!\n".getBytes(
                StandardCharsets.UTF_8);
        Path directory = Files.createTempDirectory("safe-download-example-");
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/good", exchange -> {
            try (exchange) {
                exchange.getResponseHeaders().set("Content-Disposition",
                        "attachment; filename=\"../../outside.txt\"");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.createContext("/truncated", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(200, bytes.length + 10);
                exchange.getResponseBody().write(bytes, 0, 3);
            } catch (IOException expectedAbort) {
                // The response was intentionally truncated.
            }
        });
        server.createContext("/too-large", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            } catch (IOException earlyClose) {
                // Client can close after checking Content-Length.
            }
        });
        server.createContext("/missing", exchange -> {
            try (exchange) {
                byte[] msg = "Missing".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(404, msg.length);
                exchange.getResponseBody().write(msg);
            }
        });
        server.start();
        try {
            String prefix = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String expectedHash = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
            long saved = download(client, URI.create(prefix + "/good"),
                    directory, "report.txt", 1024, expectedHash);
            System.out.println("saved bytes=" + saved
                    + ", contentMatch=" + MessageDigest.isEqual(
                            bytes, Files.readAllBytes(
                                    directory.resolve("report.txt"))));
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "../outside.txt", 1024, expectedHash);
                throw new AssertionError("Traversal should be rejected");
            } catch (IllegalArgumentException expected) {
                System.out.println("traversal: rejected");
            }
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "report.txt", 1024, expectedHash);
                throw new AssertionError("Existing file should be rejected");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("existing file: preserved");
            }
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "bad-checksum.bin", 1024,
                        "0".repeat(64));
                throw new AssertionError("Checksum should fail");
            } catch (IOException expected) {
                System.out.println("checksum: rejected");
            }
            try {
                download(client, URI.create(prefix + "/too-large"),
                        directory, "too-large.bin", 4, null);
                throw new AssertionError("Oversize should fail");
            } catch (IOException expected) {
                System.out.println("oversize: rejected");
            }
            try {
                download(client, URI.create(prefix + "/truncated"),
                        directory, "truncated.bin", 1024, null);
                throw new AssertionError("Truncation should fail");
            } catch (IOException expected) {
                System.out.println("truncated: rejected");
            }
            try {
                download(client, URI.create(prefix + "/missing"),
                        directory, "missing.bin", 1024, null);
                throw new AssertionError("404 should fail");
            } catch (IOException expected) {
                System.out.println("HTTP 404: rejected");
            }

            try (var paths = Files.list(directory)) {
                System.out.println("remaining files="
                        + paths.count());
            }
        } finally {
            server.stop(0);
            try (var files = Files.list(directory)) {
                files.forEach(p -> {
                    try {
                        Files.delete(p);
                    } catch (IOException ex) {
                        throw new RuntimeException(ex);
                    }
                });
            }
            Files.delete(directory);
        }
    }
}
```

Compile and run with JDK 17 (the `jdk.httpserver` module is used to create the local server):

```bash
javac --release 17 --add-modules jdk.httpserver SafeHttpDownloadDemo.java
java --add-modules jdk.httpserver SafeHttpDownloadDemo
```

**Stdout verified by compiling and running:**

```text
saved bytes=22, contentMatch=true
traversal: rejected
existing file: preserved
checksum: rejected
oversize: rejected
truncated: rejected
HTTP 404: rejected
remaining files=1
```

### 9.1. Why is each test meaningful?

- `saved bytes=22`: all 22 payload bytes were written, verified with the trusted SHA-256 from the test data, and compared byte-for-byte after publishing.
- `traversal: rejected`: the name `../outside.txt` fails the validator; no path outside the directory is created.
- `existing file: preserved`: the second download is not allowed to overwrite the existing `report.txt`.
- `checksum: rejected`: the streamed data is valid HTTP, but **differs from the expected digest**, so only a temporary `.part` file exists during receipt; the final file `bad-checksum.bin` is not created.
- `oversize: rejected`: the declared Content-Length of 22 bytes exceeds the 4-byte limit, so the client closes the body and does not publish.
- `truncated: rejected`: the server declares more bytes but writes only 3 bytes and closes; reading the body throws an error or fails the length check, and `truncated.bin` is not published.
- `HTTP 404: rejected`: the error page is not saved as a successful download.
- `remaining files=1`: only `report.txt` remains after all tests; no abandoned `.part` files remain. After printing the results, the program deletes the test data in the temporary directory it created.

**This is a demo, not a complete production downloader.** It intentionally restricts URLs to `http://127.0.0.1` for safe testing without TLS. For real use, do **not** simply relax the check to "any HTTP/HTTPS URI"; you need HTTPS, an origin allowlist, and an egress policy. The example also assumes `trustedDirectory` is controlled by the application and no attacker swaps a symlink during execution; `isDirectory(NOFOLLOW_LINKS)` and `getParent()` checks do not solve every race on their own. The `Files.move` call without `ATOMIC_MOVE` should not be advertised as an atomic publish on all platforms.

### 9.2. Why not use `BodyHandlers.ofFile(destination)` right away?

`BodyHandlers.ofFile(...)` is convenient for ordinary downloads, but if the application needs **temp files, size limits, checksums, header checks before publishing, cleanup, and safe filenames**, writing directly to the final destination creates difficulties:

- The file may already be created and hold incomplete bytes when the request fails.
- Status 404/500 still has a response body; without separating by status, you may save an error page.
- It is hard to prevent other consumers from reading the file before it finishes and is verified.
- If the target already exists, you must ensure it is not overwritten per policy.

`ofFileDownload(directory, options...)` is also a convenience API and **does not replace all controls** over filename, path, trusted content, and recovery. When specific security requirements apply, `BodyHandlers.ofInputStream()` paired with an explicit commit step is easier to audit.

## 10. Distinguishing Content-Length, EOF, Checksum, and Complete Response

| Mechanism | What can it detect? | What can it NOT detect? |
| --- | --- | --- |
| HTTP status 200 | Server claims the request was processed successfully | Whether bytes are complete, the right file, or safe |
| Declared Content-Length | Expected byte count of HTTP content in applicable cases | Two files with the same byte count; a server lying while keeping framing self-consistent |
| HTTP stream completion | Body was read by the HTTP stack to a valid end | Whether the content matches the application's manifest |
| Enforced byte limit | Does not exceed the configured download budget | A file under the limit that is malicious |
| SHA-256 from a trusted manifest | Downloaded bytes match the expected digest with negligible collision probability | Whether the manifest source is trustworthy if it is also attacker-controlled |
| Media format / file signature analysis | Not all byte sequences are valid for the expected format | Malware inside a valid document, parser bugs, usage permissions |
| Temp + commit | Final file is not exposed while download/validation has not passed in normal flow | Atomicity/durability across all filesystems, unhandled crashes/symlink races |

**Subtle case:** if the server returns `200 OK` with a 100-byte body and `Content-Length: 100`, whereas the real file should be 1 MB, all HTTP framing mechanisms can complete normally. Without an **independently trusted** expected digest/size, the client cannot tell that this file was *logically* truncated by the server. Therefore, "handling incomplete downloads" requires both layers:

- **Protocol-level incomplete:** missing bytes per framing, TCP reset, streaming exception.
- **Application-level incomplete/wrong:** valid framing, but not the expected artifact. Requires a digest, version, manifest, or trusted metadata.

If a checksum mismatches, **preserve the old final file and delete the temp file**—never "recover by appending a few bytes" arbitrarily to a file considered complete.

## 11. Resuming Interrupted Downloads: `Range`, `If-Range`, `ETag`

A **resume** strategy can save bandwidth for very large files, but it is harder than retrying from scratch:

```text
Attempt 1:
  GET /large.bin
  200 OK, ETag: "strong-v1", Content-Length: 5000000
  received 2000000 bytes -> network drops
  keep .part + control metadata: URI, validator, count, hash state

Attempt 2:
  GET /large.bin
  Range: bytes=2000000-
  If-Range: "strong-v1"

Server may respond:
  206 Partial Content + Content-Range: bytes 2000000-4999999/5000000
    -> append only when range, identity, size, coding, and validator are valid
  200 OK
    -> representation changed / Range ignored; re-download FROM THE START
  416 Range Not Satisfiable
```

**This is a diagram, not complete resume code.** When implementing, you must:

1. Tie each `.part` filename to its job and corresponding metadata; never mix data from two different resources or two different versions.
2. Use a **strong validator** such as a strong ETag for `If-Range` whenever possible; a weak ETag cannot be used equivalently as an `If-Range` validator.
3. Verify that `206` actually carries a `Content-Range` matching the requested offset, total size, server validator, and already-saved data.
4. When receiving `200` instead of `206`, **do not append** the new body to the old file. You must restart from byte 0 with a new temporary file.
5. If the response uses content coding, ensure byte offsets correspond to the right representation; many resume workflows require `Accept-Encoding: identity` per server contract.
6. When the download finishes, verify the total length and **trusted digest** of the entire file, not just the newly received segment.
7. Maintain TTL limits, disk quotas, and cleanup for leftover temp files after crashes; do not keep them forever or let users read them as complete files.

For small/medium files, **retrying from scratch into a new temporary file** is usually simpler and less error-prone than resuming. Do not implement Range unless there is a real need and the server guarantees reliable validators.

## 12. Redirects, HTTPS, and SSRF: A Valid File from the Wrong Source Is Still Dangerous

A downloader that accepts a user-supplied URI can be abused to access **internal services** from the server running the downloader:

```text
User-controlled URL -> http://127.0.0.1:... 
                    -> http://169.254.169.254/...
                    -> http://internal-db/...
                    -> redirect from a public host to a private host
```

Such URLs must be rejected by policy in untrusted-URL ingestion scenarios. The demo test uses `127.0.0.1` **only because the server and client run in the same JVM**, not as a suggestion to open loopback/metadata services in production.

A production system should:

- Download only from **allowed origins/hosts** over the HTTPS scheme; validate certificates/hostnames per standard TLS policy.
- Disallow redirects by default or **revalidate every hop**—host, scheme, port, and destination IP. Never allow an HTTPS → HTTP downgrade.
- Enforce an **egress firewall/network policy** blocking internal/metadata/loopback/link-local IPs when the downloader serves untrusted URIs, including defenses against DNS rebinding.
- Do not log tokens/cookies in URLs and never automatically forward `Authorization` to a host outside the allowlist via redirect.
- Limit ports, DNS lookups, redirect count, response headers/body, download duration, and total concurrency.
- Do not consider a domain name safe just because it looks valid if DNS resolves to a private IP or changes during connection.

Saving a file to the right path is still unsafe if **the download source is an attacker**. Likewise, HTTPS only authenticates transport to the endpoint per certificate/hostname policy; it **does not guarantee the document inside is free of malware**.

## 13. Timeouts, Cancellation, Retries, and Resource Cleanup

### 13.1. Not all timeouts are the same

`HttpClient.Builder.connectTimeout(Duration)` limits the **connection establishment** phase per the API. `HttpRequest.Builder.timeout(Duration)` sets the request response wait time per `HttpClient`'s mechanism. However, when using `BodyHandlers.ofInputStream()`, **`client.send(...)` can return as soon as headers/body stream are ready, before the entire file is downloaded**.

Therefore, **do not assume the request timeout bounds every `InputStream.read()` until the file completes**. In a real system, you must also measure and manage an **overall download deadline, idle-read timeout, minimum throughput, cancellation, and byte limits**; you can use an async streaming handler, close the stream, or run jobs with explicit cancellation and deadline tracking.

The demo code uses a 3-second connect timeout and a 5-second request timeout to avoid basic test hangs; it does not represent a guaranteed end-to-end production timeout for all stream reads.

### 13.2. When the user cancels

If cancelled mid-download:

1. Close the response `InputStream` / cancel the subscription per the API to stop consuming bytes.
2. Close the `OutputStream` and file handles before deleting `.part`.
3. Transition the job state to `CANCELLED`; do not publish.
4. If publishing already succeeded before the cancellation arrived, apply a **race resolution** rule: do not blindly delete the final file now used by another job or client.
5. Do not delete all files starting with `.download-` belonging to others; use owner/job ID metadata and separate TTL cleanup.

### 13.3. When retrying

- Retry transient errors (timeout, connection reset, 429/503 per policy) with exponential backoff, jitter, and a retry cap.
- Each retry from scratch creates a **separate temporary file**; never append to an incomplete file from a previous attempt unless using a verified resume protocol.
- Do not retry infinitely, as that wastes bandwidth and resources.
- Before retrying, verify the source/URI is still permitted; if there was a redirect or URL expiration, refresh tokens through a secure flow.
- If the destination file already appeared from another attempt while waiting, do not overwrite it; report a collision or use a managed filename version.

## 14. Publishing Correctness and Handling Duplicate Filenames

On the filesystem, two requirements must be stated clearly:

**(A) Do not overwrite existing files.** In the demo, `Files.exists(destination, NOFOLLOW_LINKS)` is checked and `Files.move(partial, destination)` is called **without passing `REPLACE_EXISTING`**. Under the default semantics of `Files.move`, an existing target causes the move to fail except in cases specified by the API. With multiple competing tasks/processes, the `exists` check still has a **race**; stronger guarantees require filesystem-level exclusive creation/publication and testing on the actual provider.

**(B) Do not expose an incomplete file at the final name.** Writing to `partial` first, verifying, and then publishing reduces the risk of consumers reading a half-written file. However, if you need guaranteed atomic visibility/crash consistency across all filesystems, the demo's plain `Files.move` is not enough. You need to try `ATOMIC_MOVE` where supported **and** build a separate no-clobber strategy, because `ATOMIC_MOVE` behavior when the destination already exists is provider-specific. Never use `REPLACE_EXISTING` carelessly.

You can apply a collision-avoiding naming policy using a server-side ID:

```text
invoice-7f4b8c2d.pdf     // name based on assigned random/unique ID
invoice-7f4b8c2d.pdf.part-<random>  // independent temporary file
```

However, **randomizing filenames does not replace access controls**, symlink protection, or safe destination file creation in a hostile environment. For applications with multiple workers, store job metadata in a database with a uniqueness constraint (job ID/destination) to coordinate publishing and retries.

## 15. Validating Downloaded Content: Do Not Rely Only on Extension and `Content-Type`

After downloading all bytes, there is a content-validation layer:

| Document type | Useful checks |
| --- | --- |
| PDF | Magic bytes, file structure, page/size limits, handling by a safe PDF reader |
| ZIP | ZIP magic/container, entry count, path traversal inside archive, total decompressed bytes/ratio limits |
| PNG/JPEG | Format headers and bounded decoders; avoid trusting extension |
| JSON | Valid UTF-8, safe parser, schema/size/depth constraints |
| Executable/script | Strict download/execution policy; never auto-execute downloaded files |
| Any type | Trusted hash/signature if available, valid source, size limits, scanner if required |

**Zip Slip** is a distinct but related issue: if you download and **extract** a ZIP, entry names like `../../config.yml` also need validation when calling `resolve` into the extraction directory, plus symlink and quota protections. A safe download path does not automatically make the extraction path safe.

In addition, when the UI serves a file for browser download, the HTTP response needs appropriate `Content-Disposition`/`Content-Type`/`X-Content-Type-Options` policies; never render HTML from an untrusted source directly on an origin holding login sessions.

## 16. Common Mistakes to Avoid

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Writing `response.body()` directly to a server-supplied filename | Path traversal and dangerous names | Application chooses name, allowlist, and trusted directory |
| Treating `Path.normalize()` as a symlink sandbox | Only normalizes path syntax | Control directory ownership, no-follow, races |
| Ignoring existing files | Can overwrite data | No-clobber policy and collision handling |
| Writing directly to the final file before the stream ends | Others see an incomplete file | Create `.part` and publish after verification |
| Checking only HTTP status 200 | Body can still be truncated or the wrong file | Stream completion, length, trusted digest |
| Trusting `Content-Length` alone | Server can misdeclare or omit it | Count actual bytes, enforce limit, and checksum |
| Calling `readAllBytes()` on unbounded files | Can consume huge amounts of RAM | Stream with a small buffer and max bytes |
| Using `BodyHandlers.ofFile(final)` and treating file existence as success | Mixes incomplete/error files with published files | Write temp, verify, commit |
| Ignoring HTTP 206 and blindly appending | Corrupts content due to wrong offset/version | Validate Range, If-Range, Content-Range |
| Retrying a download and appending to an old `.part` without verification | Mixes multiple resource versions | Restart or resume with a strong validator |
| Ignoring gzip `Content-Encoding` | File is saved in a different representation than expected | Choose to keep encoded or decompress with limits |
| Taking the checksum from the same attacker-controlled response | Attacker can replace both file and checksum | Digest from an independently verified manifest/source |
| Deleting the final file in `catch` on retry failure | Can delete an already-complete existing copy | Delete only the partial file owned by this attempt |
| Using unrestricted redirects for untrusted URLs | SSRF and HTTPS downgrade | Allowlist/revalidate each hop or `Redirect.NEVER` |
| Opening a file just because it has a `.pdf` extension | Bytes may be HTML/executable | Validate magic/format, scan per policy |
| Forgetting to close the response `InputStream` | Connection/resource leak | `try (InputStream stream = response.body())` |
| Using Java 17 `HttpClient` in try-with-resources | Java 17 does not implement `AutoCloseable` | Reuse client; manage per JDK |
| Assuming plain `Files.move` is atomic/durable | Java does not guarantee this across all providers | Design appropriate commit semantics and fsync |
| Assuming request timeout covers the entire body stream | `ofInputStream()` has its own read loop | Deadline/idle timeout/cancel at the download job level |

## 17. Test Matrix for a Real-World Downloader

| Test case | Input | Expected outcome |
| --- | --- | --- |
| Successful download | 200, complete bytes, valid hash | Final file has all bytes, no partial left |
| Traversal name | `../outside.txt`, `..\\outside.txt` | Rejected before request, no file created outside directory |
| Special OS names | `CON.txt`, trailing dot | Rejected or safe rename policy applied |
| Malicious Content-Disposition | `filename="../../outside.txt"` | No effect on final path |
| Final file already exists | Pre-existing `report.txt` | Not overwritten, old file remains intact |
| Connection closes prematurely | Declares 32 KB, sends 4 KB then closes | Incomplete, delete partial, do not publish |
| Truncated chunked/HTTP2 | Stream ends with framing error | Do not publish, cleanup |
| Body without Content-Length | Valid complete data | Count bytes, enforce limit, digest if available |
| 404 returning HTML | Body has data but error status | Not saved as document |
| Unrequested 206 | Partial response | Rejected, not treated as full download |
| Body exceeds quota | Large header or stream exceeds max | Rejected; stop reading, delete partial |
| SHA-256 mismatch | Bytes differ from manifest | Do not publish |
| gzip-encoded body | `Content-Encoding` header | Decode with limit or reject per policy |
| Two concurrent downloads | Same final filename | Only one publishes per collision/lock strategy |
| Symlink in directory | Path swapped during write | Does not escape directory; OS-specific tests needed |
| Process killed mid-write | Leftover `.part` | Recovery cleanup by owner/age after restart |
| Out of disk space | `OutputStream.write` throws error | Do not publish, log & cleanup |
| URL redirects to private IP | 302 to internal metadata | Rejected / egress denied |
| Resume Range offset mismatch | 206 `Content-Range` mismatch | Do not append, restart or fail |
| Resume and server returns 200 | Server refuses partial | Re-download completely from the start |

You should also test on both Windows and Linux because filename/symlink/collision handling differs; test on the actual filesystem the service will use (local, network share, container overlay) before claiming atomicity.

## 18. Practice Exercises

**Exercise 1.** The server returns `Content-Disposition: attachment; filename="../../credentials.txt"`. Why is `Path.of(downloadDir).resolve(filename).normalize()` not enough to be considered safe? How should you choose the storage name?

**Exercise 2.** `GET` returns HTTP 200, `Content-Length: 10000`. The client reads 3000 bytes and then `InputStream.read()` throws `IOException`. What should the status of the job and final file be?

**Exercise 3.** The server sends 800 bytes and declares `Content-Length: 800`. A trusted manifest states the file must have a different SHA-256. Can the download be considered successful just because the length matches?

**Exercise 4.** A download is currently writing `report.pdf.part`. The UI detects that file on disk. Should the UI offer a button to open the report before commit?

**Exercise 5.** Two workers concurrently download to `report.pdf` and both observe `Files.exists(...) == false`. What risk remains? Should `ATOMIC_MOVE` be assumed to guarantee no-overwrite by default?

**Exercise 6.** A download has `Content-Encoding: gzip`; the server declares Content-Length 40 KiB, but the decompressed bytes are 200 MiB. At which layer(s) do limits need to be enforced?

**Exercise 7.** A resumable download holds 5 MB of file version A. The client sends `Range: bytes=5000000-`, but the server returns `200 OK` containing the entire file version B. May response B be appended to `.part` file A?

**Exercise 8.** A URL starts at `https://trusted.example.com/file` but redirects to `http://127.0.0.1/admin`. Should the downloader follow it?

**Exercise 9.** `BodyHandlers.ofInputStream()` returns a response containing a stream. Can a successful `HttpClient.send(...)` call be treated as meaning all bytes of the file have arrived?

**Exercise 10.** Without Content-Length and without a trusted digest from the source, can the client reliably detect that the server sent a logically truncated file while closing the HTTP message validly?

### Suggested Answers

1. Normalization does not prevent all filename injection, symlinks, or races. Discard the server-provided name; use an application-managed name + allowlist + trusted directory.
2. Mark as FAILED/INCOMPLETE, close streams, delete the `.part` file created by the job, and **do not** publish the final file.
3. No; different bytes of the same length can still be substituted. Compare the hash against a trusted manifest and reject on mismatch.
4. No; only publish/return the download link after streaming and all checks succeed.
5. There is a TOCTOU race; you need no-clobber publication and a filesystem-appropriate synchronization strategy. `ATOMIC_MOVE` when the target exists has implementation-specific semantics.
6. Limit both **encoded bytes** downloaded from the network and **decoded bytes**/compression ratio/time when decompressing; prevent decompression bombs.
7. No. `200` is not a range continuation; discard or preserve the old partial per recovery policy, then re-download from the start; the validator/ETag must match.
8. No. This is an HTTP downgrade/SSRF; every redirect hop must be validated, and `Redirect.NEVER` is preferred.
9. No. `send(...)` can return as soon as headers are received; the stream must be read completely and verified before publishing.
10. No. HTTP framing can be valid for a shorter representation; an expected digest/size/manifest from a trusted source is required.

## 19. Official References

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): requests, redirect policy, version, and connection timeout.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `GET`, request timeout, URI.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream()`, `ofFile()`, download handler.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `move`, `exists`, `deleteIfExists`, and filesystem semantics.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `getParent`.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): operations relative to a directory handle when supported by the provider, preventing certain path races.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): incremental SHA-256 updates over byte chunks.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): Content-Length, Range/If-Range, Content-Range, response status.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): message framing and incomplete data.
- [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266.html): handling `filename` and `filename*` as untrusted advice.
