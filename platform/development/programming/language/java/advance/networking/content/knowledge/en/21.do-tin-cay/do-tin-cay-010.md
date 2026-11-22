# Input Validation, Destination Checks, Redirects, and Payload Size Limits

## 1. Four Trust Boundaries of a Java Networking Application

A Java program can call HTTP APIs, download documents, receive webhooks, process uploaded data, or forward requests to other services. The path from input to result **is not safe just because a URI parses or HTTP returns status 200**.

```text
Input provided by user / upstream
     |
     v
[1] Validate type, syntax, length, schema, resource permissions
     |
     v
[2] Validate destination: scheme, host, port, DNS/IP, proxy, TLS
     |
     v
    HTTP request with timeout/concurrency limits
     |
     +-- 3xx --> [3] Re-validate new destination + redirect limit
     |
     v
[4] Validate response status, content type/coding,
    Content-Length, actual bytes received, decompressed size
     |
     v
Parse/validate content, save .part if needed
     |
     v
Business commit / publish file once complete
```

If any layer is missing:

- **SSRF:** a user enters a URL pointing to a metadata service, loopback, or internal service; the Java app acts as a "proxy" accessing resources beyond its authority.
- **Redirect chain:** the initial URL is an allowed host, but the server returns `Location` pointing to a disallowed host/port; the client auto-follows if uncontrolled.
- **Unbounded stream:** `Content-Length` is missing, misdeclared, or heavily compressed; calling `readAllBytes()` exhausts RAM/disk/CPU.
- **Content confusion:** a 404 response contains HTML, gzip data is parsed as JSON, or a file has the wrong format even though headers look valid.
- **Truncation:** the connection drops while receiving the body, yet the code still uses the incomplete temporary file as the result.
- **Credential leakage:** automatically copying `Authorization`/cookies from the initial request to an origin introduced by a redirect.

The goal of this article is to design **defense-in-depth that is easy to audit**, know which layer handles what, write Java 17 code using `java.net.http.HttpClient`, and understand the limits of application-layer checks. The demo runs locally on loopback in Section 15, without calling the Internet or creating repository files.

## 2. Distinguishing Validation, Authorization, and Network Policy

| Check | Question | Example |
| --- | --- | --- |
| Syntax/type | Is the input in the right data format? | ID is an alphanumeric string of at most 64 characters |
| Schema/semantics | Are the fields mutually consistent? | `start <= end`, max size > 0 |
| Authorization | Does the user/tenant have permission to access this resource? | User A cannot download User B's report |
| URL destination policy | Does the URI belong to an allowed origin/route/port? | Only `https://reports.example.com:443` |
| Network egress policy | Does the **actual** connection reach an allowed address? | Block internal/metadata/loopback IPs when URL is untrusted |
| Redirect policy | Does every hop continue to satisfy the rules above? | Do not follow HTTPS → HTTP or to a different host |
| Response policy | Does the received data match the status/type/byte limit? | 200, UTF-8 JSON, max 2 MiB |
| Completion/integrity | Is the data complete and the right artifact? | Stream read completely, SHA-256 matches trusted manifest |

**A syntactically valid URI does not mean the URL is allowed.** Similarly, parseable JSON does not mean the user is allowed to modify the object contained in the JSON. Authorization must be tied to the user, tenant, resource, and request time, not just a one-time request path check.

## 3. Validating Input Before Building an HTTP Request

### 3.1. The Less Control Over the Destination, the Better

If the application only needs to download a report by ID, accept a **report ID** and build the URL from a trusted configured base URI instead of letting the user enter an arbitrary URL:

```java
// Fragment: baseUri is the configured HTTPS URI of the service.
String reportId = "report-2026-001";
if (!reportId.matches("[A-Za-z0-9_-]{1,64}")) {
    throw new IllegalArgumentException("Invalid report ID");
}
URI download = baseUri.resolve("/api/reports/" + reportId);
```

The code above is a fragment and requires `import java.net.URI;`. If the ID allows Unicode, `/`, spaces, or `?`, you must encode the **exact URI component** according to the contract rather than concatenating strings. When the report ID is a path segment, using a simple allowlist as above greatly reduces the attack surface.

Before using input data:

1. Define required vs. optional fields; reject null, empty, or duplicate fields outside the contract.
2. Validate numeric types, signs, ranges, and overflow; do not allocate based on unvalidated integers.
3. Limit the number of fields/headers/query parameters, individual lengths, and total length.
4. Set body limits **in bytes**; Java's `String.length()` is the number of **UTF-16 code units**, not UTF-8 bytes.
5. For JSON/XML, limit nesting depth, element count, string length, entity expansion, and parser CPU; validate the schema after parsing.
6. Use value/enum/route allowlists; do not just blacklist a few strings like `"../"`.
7. If input contains Unicode, specify normalization clearly and check for spoofing; do not arbitrarily apply NFKC to tokens, signatures, URLs, or resource names.
8. Escaping when outputting to HTML/SQL/URL is an **output context** responsibility separate from input validation; use SQL parameters and HTML escaping accordingly.
9. Tie to authorization: the resource ID belongs to the right user/tenant, not just having a valid format.
10. Limit rate and concurrent jobs: a small request that triggers many outbound calls can still cause DoS.

### 3.2. The Mistake of Assuming a String Has the Same Size Everywhere

```java
String body = "Xin chào";
System.out.println(body.length()); // 8 UTF-16 code units
System.out.println(body.getBytes(StandardCharsets.UTF_8).length);
// 9 UTF-8 bytes
```

This fragment requires `import java.nio.charset.StandardCharsets;`. For wire protocols, `Content-Length`, network quotas, file lengths, and stream budgets use **actual bytes**. With some emojis, a single Unicode code point can occupy two code units and four UTF-8 bytes.

## 4. Parsing URIs Properly Instead of Trusting String Prefixes

A common mistake:

```java
// COUNTEREXAMPLE: "https://trusted.example.evil.test/" also passes.
if (rawUrl.startsWith("https://trusted.example")) {
    // Do not treat this as a valid destination!
}
```

Instead, parse it:

```java
URI uri = URI.create(rawUrl);
String scheme = uri.getScheme();
String host = uri.getHost();
int explicitPort = uri.getPort();
String userInfo = uri.getRawUserInfo();
String path = uri.getRawPath();
String query = uri.getRawQuery();
String fragment = uri.getRawFragment();
```

*Fragment, requires importing `java.net.URI` and the variable `rawUrl`.*

Evaluation steps:

- The scheme must belong to the allowed set, typically **`https`** for the Internet. Reject `file:`, `jar:`, `ftp:`, `data:`, `javascript:`, and `http:` unless there is a specific use case.
- The host must exist (`getHost()!=null`) and belong to an **exact host allowlist** or an explicitly approved subdomain rule; do not check `rawUrl.contains("trusted")`.
- The port must belong to the allowed list. `getPort()==-1` means **no port was specified**; infer the default from the scheme (HTTPS=443, HTTP=80), and do not connect to port -1.
- Reject userinfo when unnecessary: `https://trusted.example@evil.example/path` has hostname **`evil.example`**, while `trusted.example` is userinfo.
- The fragment `#...` is not sent to the HTTP server but can cause confusion in validation/logs; reject it if the contract does not allow it.
- The query must have field count/size limits and must not contain unvalidated nested URLs; many file-download APIs do not need user-supplied queries at all.
- The path must match the route; distinguish encoded slashes/dots, path segments, trailing slashes, and authorization.

**Never use `URI.normalize()` as an SSRF defense.** It only normalizes some path components at the URI syntax level; it does not address DNS, proxies, network permissions, symlinks, differing URL decoding across systems, or resource access permissions.

## 5. Hostnames, IPv4/IPv6, IDN, and Policy Bypass Tricks

The URIs below require different handling:

```text
https://EXAMPLE.COM/
https://example.com.:443/
https://example.com.evil.test/
https://user@example.com/
https://example.com/a/../hidden
https://example.com/%2e%2e/hidden
http://127.0.0.1/
http://[::1]/
```

- DNS hostnames are case-insensitive, but **do not** just do `endsWith("example.com")` (which can match `evil-example.com`). For a subdomain policy, check the dot boundary.
- A trailing dot can represent a DNS absolute name. Accept this normalization only when explicitly designed for.
- For internationalized domain names (IDN), verify the canonical ASCII/IDNA form using an appropriate mechanism. Watch out for lookalike characters (homographs).
- IPv4 loopback/private/link-local, IPv6 loopback/ULA/link-local, IPv4-mapped IPv6 addresses, aliases, and unusual numeric IP forms must be handled consistently. **Do not block SSRF by checking only the string `127.0.0.1`**.
- `%2e`, `%2f`, `..`, or double encoding can cause confusion between the Java layer, proxy, and backend. One side decoding while the other does not can lead to a bypass. Restrict input paths and design consistent canonicalization.
- A redirect like `Location: //other.example/path`: even **without a scheme**, the authority has changed. A redirect `Location: ../admin` can change the route.
- Do not use a hostname allowlist as a substitute for checking the actual connected IP.

**Best security option:** do not let the user decide the hostname; if you truly must fetch a user-supplied URL, additionally control network egress and every redirect, not just add regexes.

## 6. SSRF: A Host Allowlist Is Still Not Enough If the Actual IP Changes

Server-side request forgery risk:

```text
Attacker-controlled input URL
  |
  v
Java application expects to reach a public website
  |
  +--> DNS returns internal/loopback/link-local IP
  +--> Public server returns 302 to metadata endpoint
  +--> DNS rebinding after validation
  +--> Proxy/tunnel connects to forbidden service
  |
  v
Private/internal service receives request from the Java server itself
```

Sensitive address groups to consider (examples only, not an exhaustive blocklist):

- Loopback: `127.0.0.0/8`, `::1`.
- RFC1918 IPv4 private: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- Link-local: `169.254.0.0/16` and IPv6 link-local; cloud metadata endpoints often reside in sensitive ranges.
- IPv6 Unique Local Addresses, unspecified, multicast, reserved, or reachable internal addresses.
- Public IPs belonging to disallowed internal/partner services, even when the IP is not in RFC1918.

**DNS rebinding and TOCTOU:**

```text
1. App calls InetAddress.getAllByName("allowed.example")
   -> gets 203.0.113.10, passes IP preflight.

2. Later HttpClient.send(request) connects on its own.
   -> resolver may return a different IP, e.g. 127.0.0.1.

3. The actual request can go to a policy-forbidden destination.
```

Therefore **calling DNS once before the request does not guarantee HttpClient will connect to the exact IP that was checked**. Standard Java `HttpClient` does not let you implicitly "pin" the DNS lookup just performed with `InetAddress.getAllByName`. If infrastructure must handle untrusted URLs, use an **egress firewall/secure outbound proxy** that controls the actual connection destination, together with a host/port allowlist and appropriate DNS constraints. For TLS, you must still verify the certificate against the logical hostname; do not rewrite the hostname to an IP and disable verification.

### Proxies Make Policy More Complex

If the application only connects to the proxy's IP, that does **not** prove the proxy will not access internal targets:

```text
Java application -> approved outbound proxy -> internal metadata service
```

Destination policy must be enforced at the proxy/egress layer, controlling CONNECT, DNS resolvers, and ports. With TLS interception, proxy operators must also manage CAs and secure logging. Never automatically copy HTTP credentials/session cookies across different domains when following redirects.

## 7. HTTPS/TLS Is Identity Verification, Not Just Byte Encryption

For production outbound APIs:

- Use **HTTPS** by default, verifying the certificate chain and hostname/SAN.
- Reject HTTPS → HTTP downgrades in redirects unless there is an approved reason.
- Do not use a trust-all `TrustManager`, skip hostname verification, or disable TLS to "fix certificate errors."
- A valid TLS connection/certificate **does not mean the server's content is trustworthy**; you still need status/type/size/schema/integrity checks.
- HTTP/2 and HTTP/1.1 are HTTP protocol versions; falling back to HTTP/1.1 **within HTTPS** does not mean dropping TLS.
- Client auth/mTLS or pinning may be required by specific policies; do not implement them arbitrarily.
- Do not store tokens in URL queries if a better option exists; queries/URLs can leak into proxy/access logs.
- In multi-tenant applications, credentials/sessions must be scoped to the exact origin/user rather than using uncontrolled client-global headers.

If an initial URL starts with HTTPS but redirects to HTTP or another host, the final request can be completely different from what was expected. Redirect policy must verify **every hop**.

## 8. HTTP Redirects: Treat Them Like a New Request

Example of a normal relative redirect:

```http
HTTP/1.1 302 Found
Location: /download/verified
Content-Length: 0

```

Suspicious example:

```http
HTTP/1.1 302 Found
Location: http://127.0.0.1:9999/admin
Content-Length: 0

```

Validating only the initial URL is **not enough** if the Java client automatically follows redirects.

### 8.1. Java 17's Three `HttpClient.Redirect` Options

| Policy | Meaning | When to Use |
| --- | --- | --- |
| `NEVER` | Do not auto-follow HTTP redirects | Best when every Location must be validated |
| `NORMAL` | Follow per implementation, but do not redirect from HTTPS to HTTP | Usable for already trusted destinations; does not replace an origin allowlist |
| `ALWAYS` | Follow redirects including scheme downgrades per policy | Not a safe default for untrusted URLs |

For user-controlled URLs, prefer:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

*Fragment: requires importing `HttpClient` and `Duration`.* If you choose NORMAL, **new hosts are not automatically checked against the application allowlist**; this policy only covers the restrictions defined by the Java HTTP client.

### 8.2. Manual Redirect Algorithm for GET

```text
validateTarget(current)
    |
    v
send GET(current), redirects NEVER
    |
    +-- HTTP 200 --> validate response + bounded body
    |
    +-- HTTP 301/302/303/307/308
           |
           +-- maxRedirects budget remaining?
           +-- Location is a single parseable value?
           +-- next = current.resolve(Location)
           +-- validateTarget(next) before any network request?
           +-- URI not in seen? total deadline remaining?
           +-- set current=next, continue
    |
    +-- other status --> controlled failure
```

Rules:

1. Limit hops, e.g., `maxRedirects=3` in the demo. Even though `Set<URI>` detects A→B→A, an attacker can keep changing the query to avoid repeating; a hop budget is still mandatory.
2. Resolve relative `Location` values against the **current URI**, not the first URI.
3. **Revalidate every destination after resolution:** scheme, host, port, path, userinfo, IP/egress, TLS, authorization.
4. Do not follow a missing, malformed, or ambiguous Location in an ad-hoc way.
5. Close unused response bodies before the next hop to avoid leaking resources/connections.
6. Enforce a **total deadline** for the entire redirect chain, not just a timeout per request.
7. Check credential scope; do not copy raw `Authorization`/`Cookie` headers to a different host.

### 8.3. POST/PUT/PATCH Are Not Like GET

The demo only handles GET. For requests with side effects:

- `301/302/303` have redirect semantics and method/body behavior defined by standards/implementations; some redirects turn POST into GET.
- `307/308` preserve the method and body, but **the body cannot always be replayed**; resending a POST can duplicate side effects.
- If an order-creation/money-transfer command was already processed on the server but the response was lost, automatically resending it as a new command is very dangerous.
- Use stable idempotency keys, backend deduplication/transactions, and explicit redirect policies.

**Do not turn HttpClient auto-redirect into a business retry mechanism.** They are two different kinds of orchestration.

## 9. Response Validation: Status, Content-Type, Content-Encoding, Content-Length

An HTTP request that connects successfully can still return unsuitable data. Before parsing or writing to a file, check:

| Metadata | What to Check? | Failure If Skipped |
| --- | --- | --- |
| HTTP status | Accept only success statuses per contract, e.g., `200` | Saving 404 HTML as JSON |
| `Content-Type` | Accepted media type, e.g., `application/json` | Parser receives wrong binary/text |
| `Content-Encoding` | Decode or reject unsupported content codings | Parsing gzip bytes as UTF-8 |
| `Content-Length` | If present: valid, non-negative, within limit | Excessive preallocation, parse errors |
| Actual byte stream | Does not exceed max; HTTP stream completes without error | OOM, incomplete download |
| Charset | Decode text according to specified charset/media type | Mojibake/corrupted strings |
| Schema/file signature | Actual content matches contract | Wrong commands, malicious files |
| Integrity | Hash/signature/trusted manifest if needed | Same-size file with different content |

**Do not use `Content-Type` as proof that content is safe.** Headers are metadata provided by the server; a file claiming `image/png` can still contain malformed bytes. You need bounded decoders/validators and dedicated security policies for downloaded files.

**Do not force binary data through `new String(bytes, UTF_8)`**. When downloading images/zips, keep the bytes and process them with an appropriate parser. For JSON exchanged between systems, UTF-8 is the standard encoding per RFC 8259.

## 10. Content-Length Limits and Actual Bytes Read

`Content-Length` is measured in **octets (bytes)** per HTTP semantics, not UTF-16 code units:

```java
String s = "Xin chào";
int units = s.length(); // 8
int actualBytes = s.getBytes(StandardCharsets.UTF_8).length; // 9
```

For HTTP responses, two layers are needed:

1. **Precheck declared size:** if Content-Length (when valid and applicable) is 1 GiB while the application only allows 10 MiB, reject immediately to save bandwidth.
2. **Hard cap while reading:** if Content-Length is **missing, misdeclared, or the response uses chunked encoding**, still accumulate actual bytes read and reject before exceeding max.

Do not count `String.length()`, and do not allocate `new byte[(int)contentLength]` from an untrusted header. Use an `InputStream` and a buffer, checking:

```java
if (n > maxBytes - consumed) {
    throw new IOException("HTTP body exceeds byte budget");
}
consumed += n;
```

*Fragment: `n` is the byte count from `read`, and `maxBytes` and `consumed` are non-negative longs.* Subtraction-style checking avoids integer overflow in `consumed + n`.

### 10.1. Bounded Read Helper for Small Payloads

```java
static byte[] readAtMost(InputStream in, long maxBytes)
        throws IOException {
    if (maxBytes < 0) throw new IllegalArgumentException();
    ByteArrayOutputStream result = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    long total = 0;
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > maxBytes - total)
            throw new IOException("Body too large");
        result.write(buffer, 0, n);
        total += n;
    }
    return result.toByteArray();
}
```

*Fragment: requires importing `InputStream`, `ByteArrayOutputStream`, and `IOException`.* This function holds the entire result in RAM, so only use it with a **small, controlled** `maxBytes`. For large files, stream to a temporary file, compute a checksum, verify, and commit after completion.

### 10.2. Content-Length Is Not the Only Framing Indicator

- HTTP/1.1 with `Transfer-Encoding: chunked` has its own framing; applications should let the HTTP stack handle it.
- HTTP/2 and HTTP/3 have their own data streams/frames/end-of-stream signals and do not use HTTP/1.1 chunked syntax.
- A `HEAD` response **has no body** even though it may send the Content-Length corresponding to a GET.
- `304 Not Modified` **has no response body**; Content-Length, if present, has its own semantics.
- `204` or `1xx` responses have no body per protocol rules.
- Duplicate or conflicting `Content-Length`/`Transfer-Encoding` headers must be handled properly by the HTTP stack/proxy to prevent request smuggling.

**Headers obtained from `HttpHeaders.allValues(...)` have already been parsed by the Java HTTP stack**; do not treat the demo application code as a raw HTTP parser defending against all framing ambiguities. At the application layer, if metadata violates the contract, fail closed; at the protocol layer, use an up-to-date HTTP implementation.

## 11. Compressed Content: Set Both Encoded and Decoded Budgets

A server might send:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Content-Length: 2048

<gzip bytes>
```

2 KiB of compressed data can decompress to hundreds of MiB depending on the content. A limit that only measures **compressed wire bytes** is insufficient against a decompression bomb:

- **Encoded-byte quota:** actual content bytes received/read in encoded form.
- **Decoded-byte quota:** bytes after decoding `gzip/br/deflate` for supported content codings.
- **CPU/time/expansion ratio quota:** prevents tiny payloads that take excessive resources to decompress.
- **Parser quota:** JSON depth/array/string count, ZIP entries/unpacked size, XML entity expansion.

Snippet illustrating a two-layer limit:

```java
// Fragment, when Content-Encoding is exactly "gzip" and the app wants to decode.
byte[] compressed = readAtMost(encodedBody, MAX_ENCODED);
try (GZIPInputStream gzip = new GZIPInputStream(
        new ByteArrayInputStream(compressed))) {
    byte[] decoded = readAtMost(gzip, MAX_DECODED);
    // Choose parser/charset according to the validated Content-Type.
}
```

*This is a fragment using the helper in Section 10 and importing `GZIPInputStream`, `ByteArrayInputStream`.* For large files, use a bounded streaming decoder instead of creating two arrays in RAM.

In the runnable example in Section 15, the client **rejects every `Content-Encoding` other than `identity`**, so it does not accidentally parse compressed bytes as raw UTF-8. This is an appropriate policy for the demo, not a claim that HTTP clients cannot support gzip.

## 12. Truncated Bodies, Transport Errors, and Incomplete Artifacts

A body can fail in several ways:

```text
HttpResponse 200
    |
    v
Body InputStream
    |
    +--> read IOException / framing fail --> ERROR
    +--> actual bytes > max             --> ERROR
    +--> declared count mismatch        --> ERROR
    +--> expected digest mismatch       --> ERROR
    +--> schema/format invalid          --> ERROR
    |
    v
Complete + validated
    |
    v
Commit/publish
```

There are two distinct cases:

- **Protocol-level incomplete:** the server declares N bytes but sends fewer, drops the terminating chunk, or closes the HTTP/2 stream abnormally; HttpClient can report an error while reading.
- **Application-level incomplete:** the server sends a valid HTTP message with a matching Content-Length, yet the logical artifact should be longer or have a different hash. Detecting this requires an **expected size/hash/signature from a trusted source**, not just status/length.

For file downloads: write to a **temporary `.part` file** inside an application-managed directory; compute hash/byte count while streaming; on error, delete only the temporary file created by that download attempt; only publish the final name after all validations pass. Do not rely on `Files.exists(destination)` to assert that a file is complete. The final path must prevent path traversal, symlink races, unintended overwrites, and permission issues.

On remote timeout, disk full, or user cancellation, close the body stream, mark the job FAILED/CANCELLED, and clean up. `finally` runs during normal exception handling, **not guaranteed to run when the process is killed or loses power**; clean up stale `.part` files at startup by owner/TTL.

## 13. Deadlines and Backpressure: Small Bytes Do Not Mean a Cheap Request

A server can send 1 byte per minute; the byte quota is never exceeded, yet the request is held open indefinitely. Beyond byte limits, you need:

- **Connect timeout:** `HttpClient.Builder.connectTimeout(...)` for the connection phase.
- **Request timeout:** `HttpRequest.Builder.timeout(...)` per the Java client contract.
- **Idle-read timeout:** maximum wait time for the next byte, requiring a corresponding monitor/cancellation mechanism.
- **Total job deadline:** total time across DNS, TLS, redirect hops, stream reading, decoding/parsing, saving, and committing.
- **Redirect limit:** maximum hops, independent of the deadline.
- **Retry budget:** number of retries/total time for transient errors, with exponential backoff + jitter.
- **Concurrency/queue limits:** in-flight requests, buffered body bytes, worker threads, pending task count.
- **Rate limits:** per account/IP/API token/tenant to prevent floods.

**Note on `BodyHandlers.ofInputStream()`:** `client.send(...)` can return as soon as response headers/stream are ready **before the entire body is read**. Do not assume `HttpRequest.timeout(...)` automatically guarantees a hard deadline for all subsequent `InputStream.read()` operations. In production, enforce clear cancellation/deadlines for the entire job and close the stream on cancellation.

Do not blindly retry non-idempotent POSTs; if side effects may already have occurred, use idempotency keys and server-side deduplication/result lookup.

## 14. Server-Side Request Validation and Uploads

For a Java HTTP server, apply similar controls to **inbound request bodies**:

| Component | Measure |
| --- | --- |
| HTTP request target/path | Route allowlist, URL length, consistent decoding, authorization |
| Query/headers | Count/byte limits, reject invalid schema or out-of-contract duplicates |
| `Content-Length` | Can reject early if greater than max; do not trust it as sufficient |
| Request stream | Count actual bytes on every `read`, enforce size/time limits |
| JSON/XML | Limit nesting/string/array length/entity expansion and schema |
| Multipart | Limit part count, per-file/total size, filename, content coding |
| Archive/ZIP | Limit decompressed bytes, entry count, path traversal on extraction |
| Authorization | Resource belongs to principal/tenant; check before mutation |
| Request concurrency | Bounded threads/queues/rate limits |
| Error handling | Appropriate status, do not expose stack traces/secrets |

A malformed request can return `400`; an oversized body `413 Content Too Large`; an unsupported media type `415`; missing permissions `401/403` per semantics; rate limiting `429`. Do not return 200 with a malformed-schema object and expect the client to "guess the error."

**The server must never trust a user-provided `Content-Length` to allocate `byte[]`** because it can be wrong, negative, huge, or overflow. Let the HTTP stack handle message framing; the application enforces a hard cap while reading.

## 15. Complete Java 17 Example: Destination, Redirects, and Byte Quota

This example **runs locally** with JDK 17, without needing the Internet. The server uses `com.sun.net.httpserver.HttpServer` on `127.0.0.1` and an OS-assigned port. The client is built with `Redirect.NEVER`, validates the target before every request, and reads the body using `ofInputStream()` with a limit.

Test cases:

1. `/start` → valid `302 Location: /data` → GET receives `Xin chào` (9 UTF-8 bytes).
2. A URI with userinfo and an unlisted path are blocked.
3. Redirects to `example.invalid`, another port, and a loop are blocked.
4. An oversized `Content-Length` and a chunked stream exceeding the quota are blocked.
5. A Content-Type other than `text/plain`, an unsupported content coding, HTTP 404, and a truncated body are all blocked.

**File `GuardedHttpFetchDemo.java`:**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class GuardedHttpFetchDemo {
    static final Set<String> PATHS = Set.of(
            "/start", "/data", "/oversize", "/stream", "/offhost",
            "/offport", "/loop-a", "/loop-b", "/missing", "/badtype",
            "/encoded", "/truncated");
    static final int MAX_REDIRECTS = 3;

    record Download(URI finalUri, byte[] bytes, int redirects) {}

    static void validateUri(URI uri, int port) {
        if (!"http".equalsIgnoreCase(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost())
                || uri.getPort() != port
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null
                || uri.getRawQuery() != null
                || !PATHS.contains(uri.getRawPath())) {
            throw new IllegalArgumentException("URI is outside demo policy");
        }
    }

    static Download fetch(HttpClient client, URI start, int port, long limit)
            throws Exception {
        if (limit < 0) throw new IllegalArgumentException("Invalid limit");
        URI current = start;
        Set<URI> seen = new HashSet<>();
        int redirects = 0;
        while (true) {
            validateUri(current, port); // Before every network request.
            if (!seen.add(current)) throw new IOException("Redirect loop");
            HttpRequest req = HttpRequest.newBuilder(current)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<InputStream> response = client.send(
                    req, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                int status = response.statusCode();
                if (status == 301 || status == 302 || status == 303
                        || status == 307 || status == 308) {
                    if (redirects >= MAX_REDIRECTS)
                        throw new IOException("Redirect budget exhausted");
                    List<String> locations = response.headers()
                            .allValues("Location");
                    if (locations.size() != 1)
                        throw new IOException("Missing/ambiguous Location");
                    URI location;
                    try {
                        location = URI.create(locations.get(0));
                    } catch (IllegalArgumentException bad) {
                        throw new IOException("Malformed Location", bad);
                    }
                    URI next = current.resolve(location);
                    validateUri(next, port); // Block off-policy redirects.
                    current = next;
                    redirects++;
                    continue;
                }
                if (status != 200) {
                    throw new IOException("Unexpected status " + status);
                }
                List<String> types = response.headers()
                        .allValues("Content-Type");
                if (types.size() != 1 || !types.get(0)
                        .split(";", 2)[0].trim()
                        .equalsIgnoreCase("text/plain")) {
                    throw new IOException("Unexpected Content-Type");
                }
                List<String> coding = response.headers()
                        .allValues("Content-Encoding");
                if (coding.size() > 1 || coding.size() == 1
                        && !coding.get(0).equalsIgnoreCase("identity")) {
                    throw new IOException("Unexpected Content-Encoding");
                }
                List<String> lengths = response.headers()
                        .allValues("Content-Length");
                if (lengths.size() > 1) {
                    throw new IOException("Ambiguous Content-Length");
                }
                long declared = -1;
                if (lengths.size() == 1) {
                    try {
                        String literal = lengths.get(0);
                        if (!literal.matches("[0-9]+"))
                            throw new NumberFormatException();
                        declared = Long.parseLong(literal);
                    } catch (NumberFormatException bad) {
                        throw new IOException("Invalid Content-Length", bad);
                    }
                    if (declared > limit)
                        throw new IOException("Declared body exceeds limit");
                }
                ByteArrayOutputStream received = new ByteArrayOutputStream();
                byte[] chunk = new byte[256];
                long count = 0;
                int n;
                while ((n = body.read(chunk)) != -1) {
                    if (n > limit - count)
                        throw new IOException("Stream exceeds limit");
                    received.write(chunk, 0, n);
                    count += n;
                }
                if (declared >= 0 && count != declared)
                    throw new IOException("Truncated or excessive response");
                return new Download(current, received.toByteArray(),
                        redirects);
            }
        }
    }

    static void send(HttpExchange exchange, int status, String contentType,
            byte[] bytes) throws IOException {
        try (exchange) {
            if (contentType != null)
                exchange.getResponseHeaders().set(
                        "Content-Type", contentType);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    static void redirect(HttpExchange exchange, String location)
            throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set("Location", location);
            exchange.sendResponseHeaders(302, -1);
        }
    }

    static void expectFailure(String label, RunnableWithException job)
            throws Exception {
        try {
            job.run();
            throw new AssertionError(label + " should fail");
        } catch (IOException | IllegalArgumentException expected) {
            System.out.println(label + ": blocked");
        }
    }

    @FunctionalInterface
    interface RunnableWithException {
        void run() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        byte[] hello = "Xin chào".getBytes(StandardCharsets.UTF_8);
        server.createContext("/start", ex -> redirect(ex, "/data"));
        server.createContext("/data", ex ->
                send(ex, 200, "text/plain; charset=UTF-8", hello));
        server.createContext("/oversize", ex ->
                send(ex, 200, "text/plain", "1234567890123456"
                        .getBytes(StandardCharsets.US_ASCII)));
        server.createContext("/stream", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0); // Chunked HTTP/1.1.
                ex.getResponseBody().write(
                        "0123456789".getBytes(StandardCharsets.US_ASCII));
            } catch (IOException closedByClient) {
                // Client can stop after limit exceeded.
            }
        });
        server.createContext("/offhost", ex ->
                redirect(ex, "http://example.invalid/secret"));
        server.createContext("/offport", ex ->
                redirect(ex, "http://127.0.0.1:9/data"));
        server.createContext("/loop-a", ex ->
                redirect(ex, "/loop-b"));
        server.createContext("/loop-b", ex ->
                redirect(ex, "/loop-a"));
        server.createContext("/missing", ex ->
                send(ex, 404, "text/plain", "missing"
                        .getBytes(StandardCharsets.US_ASCII)));
        server.createContext("/badtype", ex ->
                send(ex, 200, "application/octet-stream", hello));
        server.createContext("/encoded", ex -> {
            ex.getResponseHeaders().set("Content-Encoding", "gzip");
            send(ex, 200, "text/plain", hello);
        });
        server.createContext("/truncated", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, hello.length + 6);
                ex.getResponseBody().write(hello, 0, 3);
            } catch (IOException expectedAbort) {
                // Deliberately incomplete response body.
            }
        });
        server.start();
        try {
            int port = server.getAddress().getPort();
            URI origin = URI.create("http://127.0.0.1:" + port);
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            Download ok = fetch(client, origin.resolve("/start"),
                    port, 32);
            System.out.println("success: redirects=" + ok.redirects()
                    + " bytes=" + ok.bytes().length
                    + " text=" + new String(ok.bytes(),
                            StandardCharsets.UTF_8));
            expectFailure("userinfo", () -> fetch(client, URI.create(
                    "http://alice@127.0.0.1:" + port + "/data"), port, 32));
            expectFailure("unlisted-path", () -> fetch(client,
                    origin.resolve("/private"), port, 32));
            expectFailure("foreign-host-redirect", () -> fetch(client,
                    origin.resolve("/offhost"), port, 32));
            expectFailure("wrong-port-redirect", () -> fetch(client,
                    origin.resolve("/offport"), port, 32));
            expectFailure("redirect-loop", () -> fetch(client,
                    origin.resolve("/loop-a"), port, 32));
            expectFailure("oversize-header", () -> fetch(client,
                    origin.resolve("/oversize"), port, 4));
            expectFailure("stream-limit", () -> fetch(client,
                    origin.resolve("/stream"), port, 4));
            expectFailure("wrong-media-type", () -> fetch(client,
                    origin.resolve("/badtype"), port, 32));
            expectFailure("unexpected-coding", () -> fetch(client,
                    origin.resolve("/encoded"), port, 32));
            expectFailure("HTTP-404", () -> fetch(client,
                    origin.resolve("/missing"), port, 32));
            expectFailure("truncated-body", () -> fetch(client,
                    origin.resolve("/truncated"), port, 32));
        } finally {
            server.stop(0);
        }
    }
}
```

**Compile and run on JDK 17** (test server in the `jdk.httpserver` module):

```bash
javac --release 17 --add-modules jdk.httpserver GuardedHttpFetchDemo.java
java --add-modules jdk.httpserver GuardedHttpFetchDemo
```

**Observed stdout:**

```text
success: redirects=1 bytes=9 text=Xin chào
userinfo: blocked
unlisted-path: blocked
foreign-host-redirect: blocked
wrong-port-redirect: blocked
redirect-loop: blocked
oversize-header: blocked
stream-limit: blocked
wrong-media-type: blocked
unexpected-coding: blocked
HTTP-404: blocked
truncated-body: blocked
```

### 15.1. Interpreting the Tests

**Success:** the server returns a relative redirect `/data` within the same origin/path allowlist; the client follows exactly one hop and receives 9 UTF-8 bytes of `Xin chào`, under the 32-byte max.

**Userinfo/unlisted-path:** rejects input before any network request; a syntactically valid URI is not enough.

**Foreign-host/wrong-port:** rejects `Location` pointing to a different hostname or port 9 before connecting; this is a key boundary of manual redirects.

**Loop:** server A→B→A, the seen set detects the already-visited URI; max hops is still needed for redirects that do not repeat the exact same URI.

**Oversize-header:** the server declares 16 bytes against a max of 4 → rejected immediately without downloading the body as an artifact.

**Stream-limit:** an HTTP/1.1 chunked response has no fixed length → the byte loop stops at max 4, without relying on headers.

**Wrong media type/unsupported content coding:** rejected before parsing, avoiding treating binary/gzip as allowed text.

**HTTP 404:** the network request succeeded, but the business contract only accepts status 200.

**Truncated-body:** the server declares a body longer than the bytes actually sent; the HTTP client reports an error or fails the length check instead of returning partial data.

### 15.2. This Is Only a Fixture Policy, Not a Production SSRF Library

The example intentionally uses HTTP loopback `127.0.0.1` only to run in the same JVM. It does **not** address:

- HTTPS certificate/hostname validation or mutual TLS.
- Domain DNS rebinding, multiple A/AAAA records, custom resolvers, outbound proxies, or egress firewalls.
- Dynamic URI queries, complex percent-decoding, or cross-origin auth header scoping.
- JSON schema validation or bounded gzip decompression.
- Large file uploads/downloads and durable hash/commit.
- Whole-stream deadlines when peers read/write very slowly, or multi-GB concurrent downloads.
- HTTP/1.1 framing ambiguity/hardening of reverse proxies or raw parsers.

Use standard Java `HttpClient` together with unified egress/network policies and application routing guards when designing for production. Do not replace the `http://127.0.0.1` condition in the demo with "any URL is fine" and call it SSRF protection.

## 16. Implementing Large File Downloads Durably

For artifacts that can reach hundreds of MiB, do not use `ByteArrayOutputStream`. One workflow:

```text
Validated destination (HTTPS, allowlist, egress)
    |
    v
GET with controlled redirects, status & metadata checks
    |
    v
Create unique .part file inside trusted download directory
    |
    v
Bounded InputStream -> OutputStream in chunks
    |
    +--> count bytes, SHA-256, deadline, cancel checks
    +--> fail if max exceeded, EOF error or disk write fails
    |
    v
Validate complete HTTP body and trusted expected digest/schema
    |
    v
No-clobber publish final name (filesystem semantics considered)
    |
    v
Success reported only after publish
```

Things that must not be skipped:

- Choose the final filename from **application ID/logic**; do not take it directly from `Content-Disposition: filename=../../...`.
- Prevent path escapes via `..`, absolute paths, backslashes/Unicode, and symlinks; `Path.normalize` does not handle all symlinks/races.
- Each job creates and owns its temporary file; only delete the job's own partial file on failure.
- HTTP status 200 and a matching Content-Length **do not prove** the artifact is valid; use a trusted checksum/manifest/signature when needed.
- `Files.move(partial, final)` does not guarantee atomicity/durability by default across all filesystems/providers; do not use `REPLACE_EXISTING` if you want to preserve an existing version.
- If supporting Range resume, verify `206 Content-Range`, strong ETag/If-Range, offset, and checksum; `200` instead of `206` means re-downloading from the start rather than blindly appending.

## 17. Controlling Uploads and Inbound Requests

When the problem is an **HTTP server receiving input**, enforce hard caps at both the gateway and request-handling code:

```text
HTTP server request
   |
   +-- reject invalid path/method/query/header
   +-- authenticate & authorize principal
   +-- Content-Length precheck (if valid)
   +-- streaming byte limit even without header
   +-- decoded-size limit for gzip/multipart/archive
   +-- schema/format validation
   +-- store in temp/safe path or transaction
   +-- commit and return status
```

Statuses should carry clear semantics: 400 syntax error, 401/403 authentication/authorization, 413 body size exceeded, 415 unsupported media type, 422 payload semantically invalid per contract, 429 rate-limited. Do not include stack traces or internal paths in error responses.

On an HTTP/1.1 server, the HTTP stack must handle `Transfer-Encoding` and `Content-Length` properly so a raw parser cannot misread boundaries and enable request smuggling. The application still needs quotas, because a completely valid HTTP request can carry huge payloads or deeply nested JSON.

## 18. Operations: Measure Both Rejected Attempts and Consumed Budgets

Metrics/logs worth tracking:

| Metric | Meaning |
| --- | --- |
| `outbound_rejected_target_total` | Input URL outside scheme/host/port/IP allowlist |
| `redirect_hops_per_request` | Number of times the server changed destination |
| `redirect_rejected_total` | Redirects to forbidden host/port/scheme/route |
| `ssrf_egress_denied_total` | Firewall/proxy blocked destination |
| `download_declared_bytes` / `received_bytes` | Compare declared length vs. actual bytes |
| `response_oversize_total` | Data blocked for exceeding max at precheck/stream |
| `decompressed_bytes_total` | Check compression ratio/quota |
| `response_truncated_total` | EOF/framing/incomplete body errors |
| `http_errors_by_status` | Distinguish 4xx/5xx from network errors |
| `outbound_timeout_total` | Connect/idle/total deadlines |
| `active_http_jobs` / `queue_depth` | Backpressure, overload |
| `retry_attempts_total` | Prevent retry storms |

**Redaction:** do not log full URLs if queries contain tokens, cookies, Authorization headers, raw response payloads, or unnecessary private IPs/hostnames. Log job hashes/identifiers, schemes, policy outcomes, hop counts, byte counts, and controlled statuses.

A dashboard showing "200 requests = 99.9%" **is not enough** to prove reliability if 200 responses have the wrong media type, incomplete bodies, or the app fails to receive the right artifact.

## 19. Common Pitfalls Table

| Mistake / Misconception | Risk | Fix |
| --- | --- | --- |
| `rawUrl.startsWith("https://trusted.example")` | Prefix spoof | Parse URI, compare exact host |
| Treating `URI.create(url)` as safe | SSRF to syntactically valid addresses | Validate origin + network egress |
| Blocking only literal `127.0.0.1` | Misses private/IPv6/link-local/aliases | Full IP/network policy |
| Looking up DNS first, then letting HttpClient re-resolve | TOCTOU/rebinding | Enforce network restriction at actual connect |
| Auto-following redirects after initial URL preflight | SSRF/credential leakage | NEVER + validate every Location |
| Limiting redirects only with a URI Set | Ever-changing URIs can loop infinitely | Hop budget + total deadline |
| Allowing any port on a valid host | Hits admin/debug endpoints | Port allowlist |
| Disabling certificate validation to fix HTTPS | MITM | Fix CA/hostname/trust store |
| Copying Authorization across all redirects | Secret leakage | Origin-scoped credentials |
| Allocating from Content-Length | OOM/overflow | Bounded stream |
| Only prechecking Content-Length | Chunked/no-length bypass | Count actual bytes |
| Using String.length() for network quotas | Multi-byte Unicode | UTF-8 byte count |
| Parsing raw gzip bytes as JSON | Wrong payload | Decode with quota, verify MIME |
| Checking only 200 then saving file | Error/truncation/integrity failure | Completion + expected digest |
| Using readAllBytes on untrusted responses | RAM exhaustion | Buffer & hard cap |
| Not closing redirect/404 response bodies | Resource leak | try-with-resources |
| Setting only request timeout, skipping idle-read | Stream can stall for a long time | Total/idle deadline + cancel |
| Blindly retrying non-idempotent POST | Duplicate side effects | Idempotency key/transaction |
| Committing file before EOF and hash | Incomplete file gets final name | .part + validate + publish |
| Logging raw URL/query/headers | Credential leakage | Redact and scope audits |

## 20. Security and Reliability Test Matrix

| Test Case | Input or Server Behavior | Expected Result |
| --- | --- | --- |
| Contract URL | HTTPS with valid origin/path | Request allowed, contract response |
| Userinfo | `user@host` | Reject |
| Host prefix spoof | `trusted.example.evil.test` | Reject |
| Out-of-policy schemes | `http/file/ftp` | Reject |
| Forbidden port | Valid host on admin port | Reject |
| Encoded path | `%2e%2e`/double decoding | Reject per router/contract |
| Valid redirect | Relative `/data` | Bounded follow |
| Off-origin redirect | Different Location host | Reject |
| HTTPS→HTTP redirect | Downgrade | Reject |
| Redirect loop | A→B→A | Detect or hit max hops |
| Non-repeating redirect chain | Continuously new URLs | Max hops/deadline |
| DNS rebinding | Public DNS switches to private IP | Blocked at egress/connect |
| IPv6 loopback/private | Internal IPv6 address | Reject when policy forbids |
| Proxy forwarding | Proxy to metadata IP | Proxy/network guard rejects |
| Large Content-Length header | Declared > max | Reject early |
| Large chunked body | No fixed length | Reject when stream exceeds max |
| Truncated response | Closes before declared bytes | Fail, do not commit |
| Wrong MIME | text/html instead of JSON | Reject |
| Out-of-policy Content-Encoding | gzip when client only accepts identity | Reject |
| Compression bomb | 1 KiB compressed → 100 MiB | Decoded limit/CPU budget |
| Deeply nested JSON | Small body but high parser CPU | Depth quota |
| Wrong digest | Same byte length, wrong data | Do not publish |
| Slow response | 1 byte / minute | Idle & total deadline |
| HTTP 404 with HTML body | App expects JSON | Do not parse as success |
| Concurrent downloads | 1000 simultaneous jobs | Bounded concurrency/queue |
| Redirect with Authorization | Target on different domain | Do not forward secret |
| Process crash during download | Stale `.part` remains | Recovery cleanup by owner/TTL |

**The test scope of the Section 15 demo only covers GET/redirects/headers/streams and a few error cases**; it does not prove TLS, DNS rebinding, proxy egress, production idempotency, or load safety. Those topics require integration tests with controlled infrastructure and fault injection.

## 21. Self-Check Exercises

**Question 1.** Why must `https://trusted.example@evil.example/path` not be validated with `startsWith("https://trusted.example")`? What is the real host?

**Question 2.** The client initially sends GET to `https://reports.example.com`, and the server returns `302 Location: http://127.0.0.1/admin`. If the policy only allows HTTPS origin A, should it follow?

**Question 3.** The application checks DNS before `client.send`, and later DNS returns a different IP. What kind of risk is this, and where should the policy be enforced?

**Question 4.** The body has no Content-Length and the server streams 20 MiB. The application max is 5 MiB. Is checking `Content-Length` alone enough?

**Question 5.** `String s = "Xin chào";`. What is `s.length()`, and what is `s.getBytes(StandardCharsets.UTF_8).length`?

**Question 6.** The server declares a 4 KiB gzip body that decompresses to 500 MiB. Is a separate limit needed for decoded bytes?

**Question 7.** The server returns HTTP 200 with Content-Length 10000, but closes after 1000 bytes. Should the client commit the file?

**Question 8.** Content-Length and the stream complete validly, but the SHA-256 differs from the trusted manifest. Should the data be considered valid?

**Question 9.** A redirect chain A→B→C→D→... keeps changing query parameters so the exact URI never repeats. What additional guards are needed?

**Question 10.** Why should you not copy the Authorization header from request A to B on redirect if B is not in the allowlist?

**Question 11.** An upload request has a small declared length, but the actual body is huge; who must enforce the quota? Can you allocate an array from the header?

**Question 12.** `client.send(..., ofInputStream())` returns quickly, but reading the stream takes a very long time. What deadlines are needed beyond connect/request timeout?

**Question 13.** The application only verifies the proxy IP of the outbound connection. The proxy then accesses an internal metadata host. Why is this not enough?

**Question 14.** The server returns 404 text/html while the application expects JSON. What should be done before parsing?

**Question 15.** The sample Java code only allows localhost, a test port, and a few paths. Can you copy it as SSRF protection for Internet URLs?

### Suggested Answers

1. Because `trusted.example` is userinfo; the real host is `evil.example`. Parse the URI and reject userinfo.
2. No, it violates both the HTTPS and origin policies; every redirect must be validated.
3. DNS rebinding/TOCTOU; enforce at the actual egress/connect layer, combining allowlists and a firewall/proxy.
4. No. Count actual bytes in the stream read loop and reject before exceeding the quota.
5. 8 UTF-16 code units and 9 UTF-8 bytes.
6. Yes. Limit compressed bytes, decoded bytes, ratio/time/CPU.
7. No. The body is incomplete per framing; handle IOException/length mismatch and do not publish.
8. No. This is an application-level integrity mismatch; fail closed.
9. Max redirect hops and a total time budget; the seen URI set is only a supporting check.
10. Because secrets are origin-scoped; forwarding to B risks credential leakage.
11. Both the server/framework and the application streaming reader must enforce body quotas. Never allocate from an untrusted header.
12. Total job deadline, idle-read timeout, and body stream cancellation/closing.
13. The proxy makes the actual connection; policy must be enforced on the destination at the proxy/egress layer.
14. Handle the status/type error; do not parse it as successful business data.
15. No. The demo omits TLS, DNS, proxies, egress, and many production policies; a defense-in-depth architecture is required.

## 22. Official Documentation and References

- [Java SE 17 — URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): parsing, `getScheme/getHost/getPort/getRawUserInfo`, `resolve`, and `normalize`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): creating clients and executing requests.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): redirect policy, connect timeout, proxy, SSL.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER/NORMAL/ALWAYS` and downgrade restrictions.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request URI/method/timeout.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofByteArray`, streaming behavior.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): `allValues` and `firstValue`.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): redirects, status, Content-Type, Content-Encoding, and Content-Length.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): message framing, truncated bodies, and parsing ambiguity.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html): JSON UTF-8 and content validation.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlists, IP egress, DNS rebinding, redirects.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): schema/range/type checks, allowlists, and canonicalization.
