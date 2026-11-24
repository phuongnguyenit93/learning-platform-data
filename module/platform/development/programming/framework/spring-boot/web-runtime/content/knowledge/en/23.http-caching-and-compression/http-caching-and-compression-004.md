# 304 Not Modified Responses and Avoiding Resending Unchanged Content in Spring Boot

## 1. Scenario and Key Takeaway

Suppose a browser downloads a 250 KB document from Spring Boot. The user returns to the page a few minutes later, yet the document content has not changed. If the server keeps returning `200 OK` with the entire 250 KB, the application wastes bandwidth and transfer time unnecessarily.

HTTP provides **conditional requests**. After the first download, the client/cache remembers the content and the **validator** returned by the server — usually `ETag` or `Last-Modified`. When it needs to confirm whether the stored copy is still valid, the client sends a request with `If-None-Match` or `If-Modified-Since`. If the selected representation has not changed, the server replies:

```http
HTTP/1.1 304 Not Modified
ETag: "report-v7"
Cache-Control: no-cache
Date: Sun, 08 Nov 2026 01:00:00 GMT
```

**`304 Not Modified` contains no response body**. The client/cache continues using the previously stored `200` content and updates cache info from the `304` metadata. The server does not have to resend the document's bytes. However, **there is still an HTTP round trip** for confirmation. To avoid even that round trip while the resource is fresh, configure freshness lifetime using an appropriate `Cache-Control`.

Lesson objectives:

- Understand how **`200`, network-free cache hits, `304`, and `412`** differ.
- Use `ETag`/`If-None-Match` and `Last-Modified`/`If-Modified-Since` according to specification.
- Know the precedence order when a request carries **both validators**.
- Apply them in Spring MVC, WebFlux, static resources, and API endpoints.
- Avoid recomputing expensive content only to return `304` at the end.
- Test with Java 17+, Spring Boot, and `curl`, while knowing pitfalls around private caches, HTTP compression, and `Vary`.

**One misconception to eliminate:** `304` does not mean “the server does nothing”. The server still receives the request, determines the current representation, evaluates preconditions, and returns metadata. How much CPU/query work is saved depends on how the validator is computed: checking an existing version can be very cheap; computing an ETag by rendering all HTML and hashing it only saves bandwidth.

## 2. Distinguishing Fresh Cache, Revalidation, and Fetching New Content

A typical lifecycle:

```text
Request 1
Browser                            Spring Boot
  | GET /api/report                   |
  |---------------------------------->|
  | 200 OK                            |
  | ETag: "report-v7"                 |
  | Cache-Control: no-cache           |
  | Body: ... data ...                |
  |<----------------------------------|
  | Store body + ETag                 |

Request 2 (validation needed)
  | GET /api/report                   |
  | If-None-Match: "report-v7"        |
  |---------------------------------->|
  | compare ETag                      |
  | 304 Not Modified                  |
  | ETag: "report-v7"                 |
  | NO body                           |
  |<----------------------------------|
  | Reuse stored body                 |

Request 3 (data changed)
  | GET /api/report                   |
  | If-None-Match: "report-v7"        |
  |---------------------------------->|
  | representation is now version 8   |
  | 200 OK                            |
  | ETag: "report-v8"                 |
  | Body: ... new data ...            |
  |<----------------------------------|
  | Replace body + validator in cache |
```

If the first response includes `Cache-Control: max-age=300` and the cache evaluates the response as still **fresh**, the browser/cache can normally use the stored copy for 300 seconds **without asking the server**, subject to HTTP caching conditions. Once expired, `ETag` enables revalidation and receives `304` if the data has not changed.

| State | Request sent to server? | Network status (typical) | Body resent? | Meaning |
| --- | --- | --- | --- | --- |
| Cache still fresh, reusable | No | No new response from origin | No | Direct cache reuse |
| Cache needs validation, content unchanged | Yes | `304 Not Modified` | No | Reuse stored `200` body |
| Cache needs validation, content changed | Yes | `200 OK` | Yes | Update content and validator |
| No suitable prior body in cache | Yes | Usually `200 OK` | Yes | Full content needed |
| Write precondition unmet | Yes | `412 Precondition Failed` | Conditional action not executed | Protects data updates, not a cache hit |

Browser DevTools sometimes shows “from memory cache”, “from disk cache”, or presents the internal response as `200` even after a `304` network validation. When investigating, distinguish **status on the network** from the **final content used by the browser**.

## 3. What Is `ETag`? Why Is It Suitable for Checking Changes?

`ETag` (entity tag) is a validator assigned by the server to **a selected representation**. Example header:

```http
ETag: "product-42-v9"
```

The client uses that value in a subsequent request:

```http
If-None-Match: "product-42-v9"
```

The server compares against the current ETag. For `GET`/`HEAD`, if the `If-None-Match` condition is **false** because an existing representation matches the tag, the server can return `304` per HTTP rules. If the tag does not match, the server handles the request normally, likely returning `200` and the new representation.

**ETag does not have to be a hash.** It can be built from a record version number, content hash, build file version, or revision ID, as long as it is consistent with the representation and does not leak confidential information. Do not generate an ETag solely from the current timestamp on every request — if the tag always changes, the browser will never receive `304`.

### Strong and Weak ETag

- **Strong ETag**, e.g., `"sha256-abc"`: represents a representation with strict byte-level equivalence per HTTP.
- **Weak ETag**, e.g., `W/"article-17"`: identifies content that is **semantically equivalent** even though bytes may differ.
- `If-None-Match` uses **weak comparison** when checking `GET`/`HEAD`; thus it can match appropriate weak tags.
- `If-Match` for optimistic concurrency on mutating requests uses **strong comparison**; a weak ETag is not an arbitrary substitute.
- For range requests/`If-Range`, strong validators have specific requirements; do not use a weak ETag to claim gzip and plain copies are byte-identical.

Example:

```http
ETag: "rev-18"
ETag: W/"semantic-rev-18"
```

The two lines above are **two independent examples**, not two `ETag` headers recommended to be sent together in one response.

### ETag Is Tied to a Representation, Not Just a Database Row

If an endpoint returns different data by language, JSON format, permissions, user, or content encoding, **the validator must reflect the exact representation the client can store**. For instance, a Vietnamese document differs from an English one and should not share one strong ETag when bytes differ. Variant-scoped versions can be used; `Vary` must be coordinated so caches pick the right copy.

An ETag from a version ID allows fast checks without rebuilding the body:

```text
read metadata: resourceId=42, version=9
request If-None-Match: "product-42-v9"
=> match -> 304 (skip expensive body query/rendering)
```

If you only have `SHA-256(renderEntireResponse())`, the server still has to build the content before comparing ETags; `304` then primarily saves **network**, not necessarily CPU.

### `If-None-Match` Can Contain Multiple Tags or `*`

```http
If-None-Match: "v7", "v8", W/"v9"
```

A client/cache can send a list of tags for representations it has stored. `If-None-Match: *` means “condition fails if any representation currently exists”; for a `GET` on an existing resource, it can lead to `304`, whereas for a `PUT` creating a resource conditionally (“create only if it does not exist”), the unmet condition leads to `412`. Do not compare the raw header string against a single tag if implementing HTTP handling manually; use framework APIs.

## 4. `Last-Modified` and `If-Modified-Since`

`Last-Modified` is an HTTP-date (GMT), for example:

```http
Last-Modified: Mon, 01 Jan 2024 00:00:00 GMT
```

Afterward, the client can send:

```http
If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT
```

If the selected representation is no newer than the stated time, the server can respond `304` (for `GET`/`HEAD` requests without `If-None-Match`). When data is newer, the server returns the current content such as `200`.

**Precision:** HTTP-date has one-second resolution. A resource can be modified **twice within the same second**, making Last-Modified insufficient to distinguish them; clock differences across systems or timestamp handling can also cause discrepancies. For rapidly changing data, an ETag from a version sequence or content digest is usually more reliable.

If the server only has a “last accessed” timestamp rather than **last content modification**, do not use it as Last-Modified. If generating per-user representations, a global table timestamp is insufficient to capture changes in viewing permissions or rendered output.

### When a Request Carries Both Conditions

According to HTTP Semantics (RFC 9110), **`If-None-Match` takes precedence over `If-Modified-Since`**. The server must ignore `If-Modified-Since` if the request includes `If-None-Match`.

For example, the current ETag is `"v8"`, while the client sends:

```http
If-None-Match: "v7"
If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT
```

If the ETag does not match, **do not return `304` simply because the Last-Modified date satisfies the old condition**. The server must evaluate ETag in precedence order to avoid letting the client continue using a different cached version.

Cases to remember:

| Request | Current validator | Expected outcome |
| --- | --- | --- |
| `If-None-Match: "v8"` | `ETag: "v8"` | `304` for conditional GET/HEAD |
| `If-None-Match: "v7"` | `ETag: "v8"` | Usually `200` and new body |
| Only `If-Modified-Since` equal to or later than modified time | Matching Last-Modified | `304` |
| Wrong `If-None-Match` **and** matching `If-Modified-Since` | Current ETag does not match | Do not use date condition to return 304 |
| First `GET` request with no validators | Content exists | Usually `200` with body/validators |

## 5. What Does `304 Not Modified` Have and Not Have?

`304` confirms a stored response is still usable under HTTP conditions. **It is not a new body**. Do not send JSON `{"message":"not modified"}`, HTML, or a line of text inside a `304` response. If an application needs to return a “data unchanged” message with a body for a non-caching client, that is a **different application semantics**, not a misuse of status 304.

Under RFC 9110, a `304` response must include relevant metadata that a corresponding `200` response would carry when applicable, such as `Date`, `ETag`, `Vary`, `Cache-Control`, `Expires`, `Content-Location`. `Last-Modified` can also be useful depending on context. `304` **must not contain a message body or trailers**.

```http
HTTP/1.1 304 Not Modified
Date: Sun, 08 Nov 2026 01:00:00 GMT
ETag: "report-v7"
Cache-Control: private, max-age=0, must-revalidate
Vary: Accept-Encoding
```

This is an example header block, not fixed output from the project in section 8; actual `Date` and header set depend on server/configuration.

### Who Reuses the Old Body?

The browser or an intermediate HTTP cache retrieves the body from the stored `200` response. It can update the stored entry's metadata from the `304` response, then serve the client using the appropriate old body. **The server does not send the old body inside `304`**.

If a custom-written HTTP client did not save the prior body/metadata, receiving `304` leaves it with no data to display. The client must manage its own cache or send an unconditional `GET` to retrieve the body. Do not treat `304` as “an empty `200`”.

### Is `304` a Redirect?

It belongs to the 3xx status group, yet it is **not a redirect to another URL**, does not require `Location`, and does not instruct the client to fetch a new path. It directs the client/cache to continue using the stored representation.

### Does `304` Apply to `POST`, `PUT`, `DELETE`?

Conditional request rules for `If-None-Match`: if the condition **fails**, `GET` or `HEAD` can return **`304`**, while other methods can return **`412 Precondition Failed`**. `If-Match` is typically used for optimistic concurrency on data modifications, not for cache retrieval. Do not handle `PUT` with `304` to say “data unchanged”.

`HEAD` inherently has no body, so conditional HEAD usually yields less bandwidth savings than conditional GET, though it still follows HTTP semantics.

## 6. Freshness and Revalidation: `Cache-Control` Is Not ETag

`Cache-Control` describes caching storage and usage policies. `ETag` and `Last-Modified` only help **check whether a stored copy is still valid**. The two groups complement each other.

| Directive | Common effect | Network request needed on reuse? |
| --- | --- | --- |
| `Cache-Control: max-age=600` | Allows using the fresh copy for 600 seconds if cache conditions hold | No during freshness window |
| `Cache-Control: no-cache` | **May store**, but must confirm with origin before reuse | Typically involves revalidation |
| `Cache-Control: no-store` | Disallows cache from storing response | Does not rely on stored copy; `304` usually gives no benefit |
| `Cache-Control: private` | Private caches such as browsers may store; shared CDN/proxies must not store as shared | Depends on freshness; useful for personal content |
| `Cache-Control: public` | Allows shared caches to store per HTTP rules | Depends on freshness and other constraints |
| `must-revalidate` | Once stale, must not reuse without validating aside from standard exceptions | Needs validation before reusing stale |
| `immutable` | Hints that representation is not expected to change while fresh | Reduces unnecessary revalidation when used correctly |

**Trap #1:** `no-cache` does not mean “do not store”. It requires revalidation before reuse; with an ETag, the result is typically `304` when data is unchanged.

**Trap #2:** a `no-store` response is not always optimal for static resources. If public content is cacheable, using versioned/hashed filenames + `max-age` is more effective.

**Trap #3:** `max-age` **does not mean** “after that time the browser must re-download the entire body”. Once expired, the client can use a conditional request to get `304`, retain the old body, and update metadata.

### Pragmatic Policy Patterns

- **Fingerprinted static files** like `/assets/app.8a2bf.js`: typically use `Cache-Control: public, max-age=31536000, immutable` if that URL is truly immutable on each deploy.
- **Mutable HTML**: consider `no-cache` and ETag/Last-Modified so caches confirm new versions.
- **Non-sensitive general APIs**: pick `public`/`private` and moderate `max-age` matching update frequency; ETag assists revalidation.
- **Pages/APIs with per-user data**: consider `private, no-cache` if suitable for browser storage with mandatory revalidation; for secret data that shouldn't be stored, use `no-store`.
- **Sensitive auth/authorization data**: do not rely on ETag or `Vary` alone to “protect” it; enforce permission checks and cache policies preventing cross-user sharing.

Choose policies based on business requirements and threat models; **do not apply a very long `max-age` across every API** just to boost cache hits.

## 7. Spring Boot and Conditional Request Mechanisms

Spring Framework provides APIs supporting ETag/Last-Modified for both Servlet MVC and reactive WebFlux.

### 7.1. Spring MVC with `ResponseEntity`

Example snippet inside a `@RestController`:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> book(@PathVariable long id) {
    BookDto dto = bookService.read(id);
    return ResponseEntity.ok()
            .eTag("\"book-42-v5\"")
            .cacheControl(CacheControl.noCache())
            .body(dto);
}
```

This is an **illustrative snippet**; `BookDto` and `bookService` are provided by the application. Spring MVC can automatically evaluate conditional requests when handling a `ResponseEntity` with `ETag`/`Last-Modified`, returning `304` without writing the body if the validator matches.

Note: in the example above, `bookService.read(...)` **already ran before Spring inspected the ResponseEntity**. This is simple and saves bandwidth, though it may not save queries/serialization. When generating content is expensive, **separate fetching version metadata from fetching the body** and check early as in section 7.2.

### 7.2. Spring MVC with `WebRequest.checkNotModified` for Early Branching

`WebRequest` provides these overloads:

```java
request.checkNotModified(String etag);
request.checkNotModified(long lastModifiedTimestamp);
request.checkNotModified(String etag, long lastModifiedTimestamp);
```

The above shows **illustrative API signatures**, not a standalone Java class. `lastModifiedTimestamp` is milliseconds since the Unix epoch. For conditional `GET`/`HEAD`, Spring evaluates preconditions and sets the HTTP status, typically `304`, when content transmission is unnecessary.

Control pattern:

```java
@GetMapping("/reports/{id}")
public String report(@PathVariable long id, WebRequest request) {
    String eTag = reportRepository.readCheapVersion(id);
    if (request.checkNotModified(eTag)) {
        return null;   // Spring has marked the request not modified.
    }

    return expensiveReportRenderer.render(id);
}
```

This is a **hypothetical snippet** assuming `reportRepository` and `expensiveReportRenderer` are provided; to compile, it needs imports and an enclosing class. Key technical point: `readCheapVersion` must genuinely be cheap and reflect every change affecting the body. If `render` customizes by locale/user, the version must reflect those variants too.

In a `@RestController`, returning `null` after `checkNotModified` lets Spring handle the `304` response that was set. In a `@Controller` returning view names, Spring also supports returning `null` when `checkNotModified` returns `true`. Do not emit an empty `200` response in place of `304`.

### 7.3. Spring WebFlux

In WebFlux, the equivalent API lives on `ServerWebExchange`:

```java
@GetMapping("/reactive/report")
public Mono<String> report(ServerWebExchange exchange) {
    String etag = "\"report-v7\"";
    if (exchange.checkNotModified(etag)) {
        return Mono.empty();
    }
    return expensiveReactiveReport();
}
```

This is a **WebFlux snippet**, not a standalone program; `expensiveReactiveReport()` returns `Mono<String>`. `checkNotModified` is called before creating/subscribing to expensive work. If the version must be read from a reactive repository, do so in the pipeline and only build the render step after checking; never call `.block()` on the event loop.

WebFlux also supports `ResponseEntity` with `eTag`/`lastModified`. Receiving/handling `304` shares the same HTTP meaning, though runtime classes differ from Servlet MVC. Do not copy MVC `HttpServletResponse`/`WebRequest` code directly into WebFlux.

### 7.4. Static Files

Spring MVC `ResourceHttpRequestHandler` and WebFlux `ResourceWebHandler` support conditional requests for static resources; `Last-Modified` can be derived from `Resource#lastModified()`. Spring Boot serves resources from standard classpath locations, and you can configure `Cache-Control` for static files.

For CSS/JS/images, the best approach is usually **naming files by content hash** and using long caching, avoiding unnecessary requests. `304` remains useful for HTML or files with stable URLs that must check for updates.

## 8. Runnable Spring Boot MVC Example with Java 17+

The example includes three endpoints:

- `GET /api/report`: generates `ETag` from version; calls `WebRequest.checkNotModified` **before rendering the body**.
- `POST /api/report/revise`: increments the version to simulate updated content.
- `GET /api/static-info`: uses `ResponseEntity` with both `ETag` and `Last-Modified` to observe Spring handling 304 automatically.

**Spring Boot 3.5.0** is chosen so the POM uses a released version; the example is for learning, not a production project configured with authentication/CSRF. For real projects, use a maintained patch version aligned with your organization's policy.

### 8.1. Project Structure

```text
conditional-http-demo/
├── pom.xml
└── src/main/java/com/example/httpcache/
    └── ConditionalHttpApplication.java
```

### 8.2. Complete `pom.xml`

```xml
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
    <artifactId>conditional-http-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Maven starter web brings in Spring MVC and default embedded Tomcat. There is no need to manually add `ShallowEtagHeaderFilter` for conditional requests in this example.

### 8.3. Complete Java Source

File `src/main/java/com/example/httpcache/ConditionalHttpApplication.java`:

```java
package com.example.httpcache;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@SpringBootApplication
public class ConditionalHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConditionalHttpApplication.class, args);
    }
}

@RestController
class CacheDemoController {

    private final AtomicInteger revision = new AtomicInteger(1);

    // Simulates a cheap version lookup before the body rendering step.
    @GetMapping(value = "/api/report",
            produces = "text/plain;charset=UTF-8")
    public String report(WebRequest request,
                         HttpServletResponse response) {

        int version = revision.get();
        String etag = "\"report-v" + version + "\"";

        // no-cache: storable, but must revalidate before reuse.
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");

        if (request.checkNotModified(etag)) {
            return null;  // 304, neither builds nor sends the report body.
        }

        // Only build content after the validator does NOT match.
        return "Report revision " + version + "\n";
    }

    // Local test only: POST increments the resource's version.
    @PostMapping(value = "/api/report/revise",
            produces = "text/plain;charset=UTF-8")
    public String revise() {
        int version = revision.incrementAndGet();
        return "Now revision " + version + "\n";
    }

    // ResponseEntity lets Spring evaluate ETag + Last-Modified automatically.
    @GetMapping(value = "/api/static-info",
            produces = "text/plain;charset=UTF-8")
    public ResponseEntity<String> staticInfo() {
        long modifiedAt = Instant.parse(
                "2024-01-01T00:00:00Z").toEpochMilli();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag("\"static-v1\"")
                .lastModified(modifiedAt)
                .contentType(MediaType.TEXT_PLAIN)
                .body("Static information v1\n");
    }
}
```

**Why does this code work?**

1. There is one `public` class matching the filename; the package-private controller in the same package is still picked up by component scanning.
2. `AtomicInteger` models thread-safe version updates across requests within **one JVM**. This is not a production version store; multiple instances require a shared DB/real versioning.
3. The ETag string includes double quotes in valid `"report-v1"` format. `WebRequest.checkNotModified` accepts the ETag and lets Spring compare it against `If-None-Match`.
4. `no-cache` allows browsers to store the response to use the ETag while **requiring revalidation**.
5. `POST` increments the version to demonstrate switching from `304` to `200`. No real data persistence occurs; production systems must protect updates with auth, CSRF, and access control.
6. `/api/static-info` uses a fixed body and fixed modification time, enabling both `ETag` and `Last-Modified`. This lets you study the mechanism without clock drift.
7. `ResponseEntity` with ETag/Last-Modified is checked by Spring MVC when writing the HTTP response; since the fixed body is already constructed in the controller, this example primarily shows **reduced body transmission**.

**Clear limitation:** When requests hit multiple instances, each instance's `AtomicInteger` can differ; for accurate ETags, retrieve the version synchronized with business data. Do not use this demo as a production caching mechanism without real data/transactions.

### 8.4. Run the Application

Inside the `conditional-http-demo` directory, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Open a second terminal. The command sequence below assumes the application just started, initial version is 1, and port 8080 is available.

**Step A — initial unconditional download:**

```bash
curl -i http://localhost:8080/api/report
```

Key response part:

```http
HTTP/1.1 200
ETag: "report-v1"
Cache-Control: no-cache

Report revision 1
```

This is an **example of the headers/body to observe**, not the entire raw Tomcat output: protocol/version formatting, `Date`, `Content-Type`, and other headers may appear. The exact body is `Report revision 1` followed by a newline.

**Step B — send the stored copy's ETag:**

```bash
curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/api/report
```

Expected HTTP status is **`304 Not Modified`**, with the matching ETag and **no response body**. `curl -i` still prints HTTP headers.

**Step C — modify content via the demo endpoint:**

```bash
curl -s -X POST http://localhost:8080/api/report/revise
```

Exact body:

```text
Now revision 2
```

Then retry the old ETag:

```bash
curl -i -H 'If-None-Match: "report-v1"' \
  http://localhost:8080/api/report
```

Since the current version is 2, expect **`200 OK`**, header `ETag: "report-v2"`, and body:

```text
Report revision 2
```

Finally test the new validator:

```bash
curl -i -H 'If-None-Match: "report-v2"' \
  http://localhost:8080/api/report
```

Expect **`304`** and no body.

**Step D — verify `Last-Modified` on the fixed resource:**

```bash
curl -i http://localhost:8080/api/static-info
```

The `200` response has `ETag: "static-v1"`, `Last-Modified: Mon, 01 Jan 2024 00:00:00 GMT`, and body `Static information v1`.

Send a request using only the modification date:

```bash
curl -i \
  -H 'If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT' \
  http://localhost:8080/api/static-info
```

Expect `304 Not Modified` with no body.

Send both validators where **ETag does not match**:

```bash
curl -i \
  -H 'If-None-Match: "static-v0"' \
  -H 'If-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT' \
  http://localhost:8080/api/static-info
```

Expect **`200`** and the current body, because `If-None-Match` takes precedence and the old date is not used to return `304`.

### 8.5. Notes When Running Commands

- The shell commands above use Bash/Linux/macOS. On Windows PowerShell, use `curl.exe` and keep each command on one line (or use PowerShell line continuation syntax).
- Use shell-appropriate quoting when passing `If-None-Match`, because double quotes **are part of the ETag**, not just presentation formatting.
- `curl` has no automatic cache like a browser; sending manual conditional requests demonstrates the protocol, not that a browser will always send `304` requests.
- If you called `/api/report/revise` multiple times, the next version differs from 2; restart the demo to reset to initial data.
- If port 8080 is occupied, run the project with `--server.port=8081` via Spring Boot/Maven args and update the URLs accordingly.
- You can build a standalone executable JAR with `mvn clean package` and `java -jar target/conditional-http-demo-1.0.0.jar`.

## 9. Why Does Checking ETag Before Building the Body Reduce CPU?

There are two common strategies:

### 9.1. Shallow ETag: Hash the Entire Response Then Compare

Spring MVC provides `ShallowEtagHeaderFilter`. The filter caches response content in memory, computes an ETag (usually by hashing content), compares it with `If-None-Match`, and returns `304` on match.

```text
Read database -> render JSON/HTML -> serialize -> compute hash
    -> compare ETag -> 304 if matching -> skip sending BODY
```

**Pros:** relatively convenient to add ETags, saves bandwidth. **Cons:** querying/rendering/serialization work still occurs; can consume memory buffering the response, especially for large/streaming responses. Never promise “adding ETag reduces CPU” when using shallow ETags.

### 9.2. Early Check: Look Up Metadata Before Building the Body

```text
Read version/lastModified from metadata (cheap)
    -> compare If-None-Match/If-Modified-Since
       -> match: 304, STOP
       -> mismatch: heavy query -> render/serialize -> 200 + body
```

This is the preferred approach for large APIs, complex reports, or CPU-intensive resources. For early checks to be correct:

- Metadata must change **whenever** content or viewing permissions affecting the representation change.
- Perform normal access control checks **before** returning metadata/cached responses; do not leak existence/version of unauthorized resources.
- If the resource has multiple variants by locale/encoding/user, the validator must distinguish them properly.
- If data changes between reading the version and rendering, use a consistent transaction/snapshot strategy so an old ETag is never attached to a new body.
- Do not call an expensive `HEAD`/`GET` to “check ETag cheaply” if computing the version already requires running the full query; measure in practice.

For static resources with content hashes in filenames, the most efficient approach is usually long-term fresh caching, **avoiding revalidation requests altogether**.

## 10. `Vary` and HTTP Compression: Relationship to ETag/304

A single URL can produce multiple **representations** depending on request headers:

- `Accept-Encoding: gzip` -> response has `Content-Encoding: gzip`.
- `Accept-Encoding: br` -> Brotli-compressed response if the server supports it.
- No compression requested -> identity/uncompressed response.
- `Accept-Language: vi`/`en` -> may be two different bodies.
- `Accept: application/json`/`text/html` -> different content negotiation.

For caches to store/select the right variant, the server sends an appropriate `Vary`, for example:

```http
Vary: Accept-Encoding
```

or if the response also depends on language:

```http
Vary: Accept-Encoding, Accept-Language
```

**`Vary` does not turn one URL into multiple distinct URLs**, but instructs caches to include those request headers in representation selection logic. Missing `Vary` can cause caches to serve the wrong gzip/plain, wrong language, or wrong content; a seemingly valid `304` could update the wrong stored variant.

### Strong ETag with gzip and identity

A **strong ETag** is tied to the byte-level representation. A gzip-compressed copy and an uncompressed copy have different bytes, so **the same strong ETag should not be reused** for both encoded representations. You can:

- Use **different** strong ETags per content coding/variant;
- Use weak ETags with consistent semantics when identifying the same logical content, if permitted by HTTP rules;
- Let the framework/proxy/CDN manage ETags in the proper compression order and inspect actual headers per variant.

Never assume every `ETag` is a checksum of the plaintext body. If a proxy modifies compression or re-encodes responses, ensure validators and `Vary` remain accurate.

### 304 Is Not “Zero-Sized” gzip

`304` **has no body**, so you cannot describe it as “a response body compressed to 0 bytes”. Compression `gzip`/`br` shrinks the body when it **needs to be sent** (e.g. `200`). `304` revalidation avoids sending the body altogether. The two techniques complement each other:

1. Cache still fresh: no request to origin.
2. Cache stale + validator matches: small request, bodyless `304`.
3. Resource changed: `200` with optionally compressed body, updated ETag/metadata.

**Measure bandwidth across multiple layers**: a CDN proxy may return `304` while the Spring Boot origin sees no request; or the browser may serve local cache while the network panel displays it according to its own convention.

## 11. Static Resources in Spring Boot: 304 or Asset Fingerprinting?

Spring Boot auto-configures static resource handling when an appropriate web starter is present. Resources like CSS, JS, and images in `classpath:/static/` and configured locations can be served by Spring via `ResourceHttpRequestHandler` (MVC) or `ResourceWebHandler` (WebFlux).

Depending on the resource and configuration, the handler can use the file's `Last-Modified` to handle `If-Modified-Since`. Cache policies can be configured in Spring MVC:

```java
@Configuration
class AssetCacheConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofDays(7)).cachePublic());
    }
}
```

This is an **MVC configuration snippet**, not a complete class since it needs Spring imports and `Duration`. Place the class in a component-scanned package of the app, and do not add `@EnableWebMvc` if you only want to add resource mappings.

If an asset has an unchanged URL while its content changes during `max-age=7d`, browsers can retain the old copy without sending a request until expiration. Therefore:

- Use **fingerprinting/content hashes** in URLs to bump the version every time content changes; e.g., `/assets/app.4bf21.css`.
- Use long `Cache-Control` lifetimes for **immutable** URLs.
- For HTML entry points or mutable config, choose `no-cache`/short lifetimes and suitable validators.
- Never attach `public, max-age=31536000, immutable` to responses containing user content or resources editable at the same URL.

### 304 and Version Resolvers Differ

`VersionResourceResolver` can support content-based versioning and generate/resolve fingerprinted URLs when configured properly. Merely enabling the resolver **does not rewrite hardcoded URL strings in static HTML**; templates/resource URL providers or the build pipeline must also output the corresponding URLs.

If files already have a version/hash in their path, fresh browser caches usually skip asking the server, so `304` appears less often. This is **not a bug**; it can be even more effective caching.

## 12. ETag and Per-User Data: Security, Authorization, and Invalidation

A cache validator is not an authentication mechanism. Suppose `GET /api/profile` returns a different body per logged-in user:

- Do not emit `Cache-Control: public` if a shared cache could serve user A's response to user B.
- Use `private` or `no-store` depending on sensitivity; if using private browser caching, consider logout, account switching, and sensitive data remaining on shared machines.
- ETag must reflect the per-user and per-permission representation, not a single `"profile-v1"` shared across everyone.
- The server **must still verify authentication and authorization**, even if the client sends `If-None-Match`; never return `304` for a resource the client is unauthorized to access.
- `Vary: Cookie` or `Vary: Authorization` does not make an endpoint safe for public caching and does not replace `private`/`no-store`.
- If roles/permissions change while the data row version stays the same, the personalized resource may still differ. Validators must capture all state affecting content.

### Invalidation: Data Changes Must Change Validators

A wrong ETag causes a dangerous bug: the server returns `304` when the new body **has changed**, causing the client to reuse stale data. Sources of change can include:

- Business record updates or recalculating a component in a report.
- Template changes, different layout/locale/formatting.
- Viewing permissions or allowed visible fields changing.
- Documents depending on data across multiple tables, needing a composite revision.
- Compression or content negotiation selecting a different representation.

Do not just increment a single record's `version` while ignoring dependencies that alter the body. For multi-component dynamic endpoints, use a composite snapshot version/timestamp or a sufficiently comprehensive hash; weigh validator calculation cost and read consistency.

## 13. Automated Testing with MockMvc

You can add the following test dependency to `pom.xml` in section 8 (a snippet placed inside `<dependencies>`, not a standalone POM):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

The following Java test is a **complete additional class** at `src/test/java/com/example/httpcache/CacheControllerTest.java`:

```java
package com.example.httpcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CacheControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void matchingEtagReturns304WithoutBody() throws Exception {
        mvc.perform(get("/api/report")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"report-v1\""))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void nonMatchingEtagReturns200WithBody() throws Exception {
        mvc.perform(get("/api/report")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"report-v0\""))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, "\"report-v1\""))
                .andExpect(content().string("Report revision 1\n"));
    }

    @Test
    void lastModifiedCanReturn304() throws Exception {
        mvc.perform(get("/api/static-info")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Mon, 01 Jan 2024 00:00:00 GMT"))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }
}
```

Run:

```bash
mvn test
```

These tests use a fresh context starting at version 1 and none of them invoke `revise`. Because `AtomicInteger` lives on a singleton bean in the test context, if you add tests that mutate the version, reset data between tests or design isolated fixtures to avoid execution-order dependencies.

If using a different Java/Spring Boot version, check the matching test auto-configuration annotations. Tests assert an empty body on `304`, not just the status code.

### Recommended HTTP Test Matrix

| Case | Request headers | Expected status |
| --- | --- | --- |
| GET without validator | No `If-*` | `200` + body |
| GET with matching ETag | Matching `If-None-Match` | `304` without body |
| GET with stale ETag | Different `If-None-Match` | `200` + new ETag/body |
| GET with matching `If-Modified-Since` | No `If-None-Match` | `304` |
| Both present and ETag mismatches | Wrong `If-None-Match`, “unchanged” date | `200`; ETag takes precedence |
| Missing resource | GET nonexistent URL | `404`, do not pretend `304` |
| Unauthorized user | Header matching another user's copy | Appropriate `401`/`403`, no cache leak |
| Asset with `Vary` | Varying `Accept-Encoding`/`Accept-Language` | Selects proper variant body/validator |
| `no-store` cache | Sensitive response | Client does not rely on stored body |
| Still fresh cache | Active `max-age` | Cache may avoid contacting origin |

## 14. Observing Real Performance

After enabling 304, measure rather than assuming success:

1. **Bandwidth:** bytes from origin to client/CDN and `200`/`304` ratio.
2. **Latency:** p50/p95/p99, including network round trips; `304` still incurs a request and may wait on the backend.
3. **CPU and DB:** cost of computing validators versus querying/rendering the body. With `ShallowEtagHeaderFilter`, CPU may barely decrease.
4. **Memory:** client/CDN cache size and server-side buffering when hashing content.
5. **Fresh-hit ratio:** share of requests completely avoiding the origin via `Cache-Control`; counting `304` alone does not tell whether caching is optimal.
6. **Correctness:** how often the body actually changed yet the server returned 304; this is a severe bug caused by wrong validators/variants.
7. **Security:** audit responses with personal data stored by shared caches or reused by prior users after logout.
8. **Compression:** check `Content-Encoding`, `Vary`, and strong/weak validators on both gzip and identity variants.

With a CDN/reverse proxy, the status logged by Spring Boot can differ from what the browser sees, because intermediate caches may handle requests. Observe each layer and distinguish origin-emitted `304` from cache hits that never reach the origin.

**Never place session IDs, tokens, or sensitive data inside ETags.** ETags can appear in responses/headers/logs/CDNs and risk becoming tracking identifiers if designed carelessly.

## 15. Common Errors and Fixes

| Error/symptom | Cause | Solution |
| --- | --- | --- |
| Browser always re-downloads `200` body | Missing validator or ETag changes every time | Emit stable representation-based ETag/Last-Modified; inspect response |
| Browser does not send `If-None-Match` | Cache not storing, `no-store`, non-cacheable response, or still fresh | Inspect `Cache-Control`, storage, requests, and DevTools |
| `304` has a JSON body | App manually built a response violating semantics | Let framework return bodyless 304; never write a body for 304 |
| `304` occurs yet page stays slow | Server still performs heavy render/query to compute ETag | Early check with cheap metadata/version |
| Current timestamp used as Last-Modified | Value constantly changes unrelated to content | Use real modification timestamp |
| Data edited twice in same second yet still `304` | Last-Modified is too coarse | Use ETag/version distinguishing every change |
| Client sends both validators and server prioritizes date | Incorrect RFC 9110 implementation | Prioritize `If-None-Match`; prefer Spring APIs |
| Gzip and identity share a strong ETag | Encoded representation bytes differ | Generate per-variant/encoding tags or suitable weak validators |
| Wrong language content returned | Missing `Vary: Accept-Language` or variant validator | Fix `Vary` and per-representation ETag |
| User A receives User B's old body | Shared cache misconfigured for personalized data | `private`/`no-store`, auth checks, and proper validators |
| Trying to use `304` when client has no old body | Custom client does not manage a cache | Have client store prior 200 or perform unconditional GET |
| `ResponseEntity` 304 yet DB still queried | Body built before framework check | Use `WebRequest.checkNotModified` early |
| Cached for a year yet file edited at same URL | Fresh cache does not revalidate immediately | Change URL fingerprint when content changes |
| Using `If-None-Match` on PUT to guard stale updates | Confusing cache retrieval condition with optimistic locking | Use `If-Match`/`If-Unmodified-Since` appropriately, handle `412` |
| Browser behavior differs from `curl` | `curl` does not manage a browser cache | Use DevTools, request headers, and cache storage to verify |

### A Quick Debugging Workflow

1. Call the endpoint with `curl -i` without `If-*`: confirm `200` with body, ETag/Last-Modified, Cache-Control, and Vary are correct.
2. Call again with the exact `If-None-Match` header received: confirm `304`, **no body**.
3. Call again with a non-matching tag: should return the new body or normal response per resource state.
4. If dates are supported, test `If-Modified-Since` and the case with both validators present.
5. Modify actual data, verify version/ETag changes; verify permissions and locale/encoding variants.
6. Open DevTools → Network: distinguish memory/disk cache, network 304, and 200 body; check proxy/CDN.
7. Measure CPU/DB and network; if only saving bytes while server stays slow, move to early validation or asset fingerprinting.

## 16. Self-Assessment Questions

1. **Does `304` resend the document for the browser to update?** No. `304` has no body; the cache reuses the stored document.
2. **Does `304` mean the request didn't reach the server?** No. It is usually the result of a conditional request. Fresh caches can reuse without contacting the server.
3. **Does `Cache-Control: no-cache` forbid storing the response?** No. It requires revalidation before reuse.
4. **How does `Cache-Control: no-store` differ from `no-cache`?** `no-store` forbids caches from storing the response; `no-cache` may store it but must revalidate.
5. **Must ETag be a SHA-256 hash?** No. It is a representation validator; a stable, meaningful version can also be used.
6. **Why is Last-Modified not always enough?** Second-level resolution and timestamps may fail to distinguish closely timed edits.
7. **If a request carries both If-None-Match and If-Modified-Since, which one is used?** Prioritize `If-None-Match`, ignore `If-Modified-Since`.
8. **What does `ShallowEtagHeaderFilter` save?** Mainly bandwidth; the response still must be computed before hashing.
9. **Why shouldn't gzip and uncompressed share the same strong ETag?** The two representations have different bytes; validators must match the selected representation along with `Vary`.
10. **Should an HTML page with user data use `public, max-age=31536000`?** No. Keep it out of shared caches and consider `private`/`no-store`.
11. **When does `304` stop yielding big gains?** When fingerprinted assets stay fresh in cache, requests usually don't need to be sent to the origin at all.
12. **What if the API returns `304` yet the client never stored a `200`?** The client has no body to reuse; it must fetch content via an unconditional GET.
13. **What happens if data is edited by changing only the body without changing ETag?** It can cause false `304`s, leaving clients on stale copies; this is an invalidation bug.
14. **Does `curl -H 'If-None-Match: "v1"'` by itself prove browsers will cache?** No. It only tests how the server responds to a specific request header.

## 17. Production Deployment Checklist

- [ ] Is the resource public or personalized? Should browsers/shared caches store it?
- [ ] Choose the right `Cache-Control`: freshness, private/public, no-cache/no-store.
- [ ] If revalidation is needed, emit a stable `ETag` per **representation**; add `Last-Modified` if suitable metadata exists.
- [ ] Prefer early validator checks before expensive queries/rendering.
- [ ] If ETag comes from data version, ensure the version reflects all content and access-permission changes.
- [ ] For multi-variant JSON/HTML, configure `Vary` and validators properly for content negotiation/encoding.
- [ ] For fingerprinted static files, use long-term fresh caching when URLs are truly immutable.
- [ ] Matching conditional GETs must return bodyless `304`; stale ETags return `200`/current body.
- [ ] `If-None-Match` takes precedence over `If-Modified-Since` when both appear.
- [ ] Distinguish `If-Match`/`412` semantics for mutating requests.
- [ ] Verify authentication/authorization before deciding to return 304 for restricted content.
- [ ] Test across browsers, `curl`, proxy/CDN, and multiple instances; do not rely solely on single-controller unit tests.
- [ ] Measure network bytes **and** DB/CPU time; do not mistake 304 for end-to-end performance.
- [ ] When changing cache policies, evaluate the impact on old cached copies issued by previous releases.

## 18. Official References

- [RFC 9110 — HTTP Semantics, If-None-Match/If-Modified-Since preconditions and 304](https://www.rfc-editor.org/rfc/rfc9110.html).
- [RFC 9111 — HTTP Caching, freshness, revalidation, updating stored responses](https://www.rfc-editor.org/rfc/rfc9111.html).
- [Spring Framework — Spring MVC HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html).
- [Spring Framework — Spring WebFlux HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html).
- [Spring Framework — Static Resources in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html).
- [Spring Framework — Shallow ETag filter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304).
- [MDN — ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag).
- [MDN — HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).

**Conclusion:** `304 Not Modified` is a way to **confirm a cached copy is still valid without retransferring the body**. To apply it effectively in Spring Boot, combine **`Cache-Control` to decide when a request is needed**, **`ETag`/`Last-Modified` to identify representations**, **`If-None-Match`/`If-Modified-Since` to revalidate**, and **early checks in controllers** when CPU/DB savings are needed. Do not forget `Vary`, HTTP compression, authorization, and per-user cache management.