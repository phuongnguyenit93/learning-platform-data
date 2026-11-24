# ETag, Last-Modified, and Conditional Requests in Spring MVC

## 1. Lesson Objectives

When a client fetches the same resource multiple times, it does not necessarily need to receive the entire JSON/HTML/file every time. HTTP allows a client to keep a received representation and ask the server: **"Has this content changed?"**. If it has not changed, the server can return **304 Not Modified** without a response body. For update operations, HTTP also lets clients say: **"Only write if the resource is still the exact version I read"**, thereby preventing many *lost update* scenarios.

Spring MVC (Servlet stack) supports this mechanism via `ResponseEntity.eTag(...)`, `lastModified(...)`, `WebRequest.checkNotModified(...)`, and other HTTP caching components. This lesson uses **Java 17+, Spring Framework 6.x / Spring Boot 3.x**; do not treat these Servlet MVC examples as guidance for Spring WebFlux.

After this lesson, you will be able to:

- Explain `ETag` and `Last-Modified` as **response validators**, not replacements for `Cache-Control`.
- Use `If-None-Match` and `If-Modified-Since` for conditional GET/HEAD, and understand why 304 carries no body.
- Use `If-Match` and `If-Unmodified-Since` for optimistic concurrency; distinguish `412 Precondition Failed` from `409 Conflict` and `428 Precondition Required`.
- Understand strong vs. weak ETags, comparison rules per HTTP Semantics (RFC 9110), precondition precedence, and timestamp precision.
- Add validators to controllers via `ResponseEntity`; understand limitations of `ShallowEtagHeaderFilter`, proxies/caches, and `Vary` variants.
- Practice a runnable controller and in-memory atomic update in Spring Boot 3; test with `curl` and MockMvc, inspecting expected statuses and headers.
- Avoid bugs such as caching private data, ETags inconsistent with representations, and non-atomic version checks.

**Important:** `ETag`/`Last-Modified` only describe the state of a resource or representation at a given moment. They do not grant access permissions, do not guarantee safe caching of user data, and do not prevent races if backend update logic is not atomic.

## 2. When to Use HTTP Conditional Requests?

Suppose a client performs a GET on a document:

```http
GET /api/documents/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

First response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "doc-1"
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
Cache-Control: no-cache

{"id":1,"text":"Xin chào","version":1}
```

The client keeps the body along with the validator and sends another request:

```http
GET /api/documents/1 HTTP/1.1
If-None-Match: "doc-1"
```

If the representation is still that version:

```http
HTTP/1.1 304 Not Modified
ETag: "doc-1"
Cache-Control: no-cache

[no response body]
```

The `[no response body]` text in the sample is an **annotation**, not bytes transmitted over the wire. A 304 response **has no message body**; the client/cache reuses the response body stored from the previous 200. If the validator does not match, the server returns 200 with the current representation and new validator.

Similarly, before modifying a document, the client can send `If-Match: "doc-1"`. If another user already changed the version to `"doc-2"`, the stale modification request must be rejected with **412** (barring special cases under the RFC) instead of silently overwriting.

These two goals are very different:

| Goal | Request header | Status when condition prevents normal processing |
| --- | --- | --- |
| Revalidate cached GET/HEAD | `If-None-Match`, `If-Modified-Since` | **304 Not Modified** when the client's copy is still valid |
| Prevent overwriting newer version | `If-Match`, `If-Unmodified-Since` | **412 Precondition Failed** when precondition fails |
| Create only if resource does not exist | `If-None-Match: *` on unsafe method when applicable | **412** if the resource already exists |
| Require clients to always send preconditions on writes | Application policy, e.g. requiring `If-Match` | **428 Precondition Required** if missing |

`304` does not mean an error; `412` indicates failure of a specific HTTP precondition; `428` reflects a server policy requiring conditional requests.

## 3. Distinguishing Cache-Control from Response Validators

The two groups of headers answer different questions:

| Header | Answers | Examples |
| --- | --- | --- |
| `Cache-Control` | May it be stored/reused? When must it revalidate? | `no-cache`, `private`, `max-age=60` |
| `ETag` | Version/identity of the selected representation | `"doc-1"` |
| `Last-Modified` | Time the server believes the representation last changed | HTTP-date |
| `Vary` | Request headers that affect the selected representation | `Accept`, `Accept-Language` |
| `Expires` | Absolute expiration timestamp for HTTP caches | HTTP-date |

**`Cache-Control: no-cache` does not mean "do not store."** Under HTTP caching semantics, a cache may store the response, but must revalidate with the origin before reusing it (subject to other conditions). If data must never be stored, use `no-store`. When user-specific data is involved, review `private`, `Authorization`/cookies, shared caches, and security policy.

When public JSON has `Cache-Control: max-age=60`, caches can reuse the fresh response without sending a conditional GET every time. After 60 seconds, caches can revalidate using `ETag`/`Last-Modified`. **Adding an ETag alone does not make a response cacheable**, nor does it guarantee fewer server requests if clients/caches do not store the response.

## 4. ETag: What Is an Entity Tag?

An `ETag` (entity tag) is a validator for a **selected representation** of an HTTP resource. Common forms:

```http
ETag: "v17"
ETag: "sha256-abc123"
ETag: W/"semantic-v17"
```

Double quotes are an essential syntactic part of an ETag. The `W/` prefix marks a **weak validator**. The string inside is an opaque tag; clients **should not parse its contents** or infer business data from it. The server may generate it from a revision, version token, or consistent hash.

### 4.1. Strong ETag vs. Weak ETag

- **Strong validator** (e.g. `"abc"`): used when the server guarantees the representation is identical strictly enough for strong comparison. For payloads served in multiple variants, ETag generation must reflect differences that affect the representation byte-for-byte.
- **Weak validator** (e.g. `W/"abc"`): used when the server treats byte-different yet semantically equivalent representations as one version for cache validation.
- Strong ETags are generally suited for `If-Match` to prevent overwrites, whereas weak ETags can work with `If-None-Match` for revalidation.
- Do not blindly prepend `W/` just because it sounds "lighter"; understand validator precision/semantics and choose per contract.

Example:

| Values | `If-None-Match` using weak comparison | `If-Match` using strong comparison |
| --- | --- | --- |
| Current ETag `"v1"` vs. client `"v1"` | Match | Match |
| Current `"v1"` vs. client `W/"v1"` | Match | **No** match |
| Current `W/"v1"` vs. client `W/"v1"` | Match | **No** match |
| Current `"v2"` vs. client `"v1"` | No match | No match |

Per RFC 9110, `If-Match` uses **strong comparison**, while `If-None-Match` uses **weak comparison**. A weak ETag is never treated as matching a strong tag for write preconditions protecting against lost updates.

### 4.2. Is an ETag from a Database Revision Always Strong?

Not necessarily. If the JSON response adds a field, changes serializer ordering, changes language, changes compression/variant, or incorporates external data without incrementing the revision, an ETag derived solely from JPA `@Version` might **no longer accurately represent** the representation's bytes. To use a strong ETag, the version must reliably cover **every meaningful change to the selected representation**, or be hashed from the canonical/appropriate representation bytes.

In the example below, the API fixes **a single JSON representation** built from `id`, `text`, and `version`, and every text modification increments the revision. That is a learning model where a strong tag like `"doc-{version}"` works. In production, changing serializers, media types, or response schemas without bumping the revision requires re-evaluating validator generation; you cannot simply share the same strong ETag across JSON and XML.

### 4.3. ETag Is Not a Secret

Never embed passwords, tokens, PII, hashes susceptible to probing sensitive data, or internal secret keys inside an ETag. ETags can also enable tracking if designed to attach user-specific identifiers across multiple resources/sites; avoid using validators as substitute cookies.

## 5. Last-Modified: Modification Timestamp

`Last-Modified` tells clients when the server believes the selected representation was last modified, formatted as an **HTTP-date**, typically:

```http
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
```

Do not send Java's `Instant.toString()` directly as HTTP `Last-Modified`. Spring MVC `ResponseEntity.lastModified(...)` formats the header per HTTP rules. HTTP-dates are written in GMT with **one-second** precision.

### 5.1. Advantages

- Easy to adopt when the system already maintains an `updatedAt` timestamp for a resource.
- Clients can send `If-Modified-Since` to ask whether the resource changed after that timestamp.
- Can supplement `ETag` for clients/caches that rely on date validators.

### 5.2. Limitations

- **One-second resolution**: two updates within the same second can share the same `Last-Modified`, causing clients using only date validators to risk receiving an unintended 304.
- Clocks across replicas/servers can drift; client-reported timestamps are untrustworthy.
- A file regenerated from source with new metadata may have a newer timestamp despite identical content, hurting revalidation efficiency.
- An `updatedAt` field reflecting only one database row is insufficient if the JSON joins multiple tables, caches, or translations.
- `If-Unmodified-Since` is not as strong an optimistic locking tool as **strong If-Match** under rapid concurrent writes.

If a resource changes multiple times per second, prefer an accurate `ETag` and ensure freshness. Always rely on a server-authoritative modification time rather than client machine dates or locale formatting.

## 6. Conditional GET with If-None-Match

`If-None-Match` checks whether the selected representation has an ETag matching one of the tags listed by the client.

```http
If-None-Match: "v1"
If-None-Match: W/"v1"
If-None-Match: "v1", "v2", "v3"
If-None-Match: *
```

For **GET/HEAD**, if the `If-None-Match` condition evaluates to **false** because the selected representation matches a tag the client already holds, the server normally returns **304** without a body. If the tag differs, normal GET processing continues, typically returning **200** with the new body.

`If-None-Match: *` means the condition is true only when **no current representation exists**; on a GET for an existing resource, the condition evaluates to false and can return 304. For unsafe methods (POST/PUT), `If-None-Match: *` is commonly used for "create only if absent"; if the resource already exists, return **412**.

If a cache/client holds a stale body and sends tag `"old"` while the server is at `"new"`, the server **must supply the current representation** when other conditions allow, not return 304 merely because `If-None-Match` is present.

## 7. Conditional GET with If-Modified-Since

A client can send:

```http
If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT
```

For GET/HEAD, if the selected representation **has not changed since that time**, the server normally returns 304. If it has changed, it returns 200 with the new body.

The condition uses a valid HTTP-date. RFC 9110 requires ignoring `If-Modified-Since` when:

- The request contains `If-None-Match` (`ETag` is the more accurate validator).
- The header date is invalid or syntactically malformed with multiple values.
- The method is neither GET nor HEAD.

In HTTP, servers should not blindly use a future client timestamp to return 304 if resource metadata is unreliable. Spring handles date parsing in controllers, but you must still supply an accurate modification time.

### When Both Conditions Are Present

```http
If-None-Match: "stale-tag"
If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT
```

**If-None-Match takes precedence over If-Modified-Since**: if the current ETag differs from `"stale-tag"`, the request still receives 200 **even if** the timestamp has not passed the date in the header. Never write `if (etagMatched || notModifiedSince) return 304`, because that violates the precedence rules.

## 8. If-Match and If-Unmodified-Since: Preventing Lost Updates

Scenario:

```text
T0: Document version 7
A: GET /documents/1 -> ETag "doc-7"
B: GET /documents/1 -> ETag "doc-7"
B: PUT If-Match: "doc-7" -> succeeded, version 8
A: PUT If-Match: "doc-7" -> 412 Precondition Failed
A: GET version 8 again -> decide to merge, then PUT "doc-8"
```

**`If-Match`** requires the server to execute the method only if the selected representation **currently matches the client's strong tag**. A list of tags or `*` (resource exists) can be sent, though an API may enforce a policy requiring an exact revision to prevent blind overwrites. `If-Match: W/"doc-7"` fails strong comparison and will not allow writes based on a weak tag.

**`If-Unmodified-Since`** uses a date precondition: process only if the resource was not modified after the client-specified timestamp. It is weaker in applications with multiple updates per second and must be ignored when `If-Match` is present.

### Why Not Just Check in the Controller and Then Save?

An unsafe pattern:

```java
Document before = repository.findById(id).orElseThrow();
if (before.version() == clientVersion) {
    repository.save(update(before)); // race between check and save!
}
```

This is an **anti-pattern snippet**, not standalone compilable code. Two requests can both pass the check before either saves. You need CAS, a conditional SQL UPDATE (`UPDATE ... WHERE id=? AND version=?`), or real optimistic locking (JPA `@Version`) inside a transaction, mapping row-count/optimistic-lock conflicts to `412` per the HTTP precondition contract.

If policy requires `If-Match` and the client omits it, the server can return **428 Precondition Required** (RFC 6585). If the client sends a stale ETag, return **412 Precondition Failed**. If the user submits business-rule conflicts unrelated to HTTP preconditions, **409 Conflict** or another domain error may be appropriate.

## 9. Request Precondition Precedence per RFC 9110

When multiple conditional headers are present, evaluation order is not arbitrary. Summary for an origin server:

1. **`If-Match`**: evaluate first; if false, normally 412. Uses strong comparison.
2. Only if **`If-Match` is absent**, evaluate **`If-Unmodified-Since`**; if false, normally 412.
3. **`If-None-Match`**: if false, GET/HEAD → 304; other methods → 412.
4. For GET/HEAD, only if **`If-None-Match` is absent**, evaluate **`If-Modified-Since`**; if false → 304.
5. When `Range`/`If-Range` are present and prior conditions pass, partial content (`206`) may be considered; outside this demo's scope.
6. If no condition blocks it, process the method normally.

This is a condensed overview; the RFC includes exceptions such as state-changing requests that already succeeded previously and notes that preconditions need not be evaluated if the request would fail regardless. For instance, authentication/authorization should normally run before confirming a resource's existence or version to an unauthorized caller.

### Behavior Table

| Method | Conditional header | When matched / unchanged | When different / changed |
| --- | --- | --- | --- |
| GET | `If-None-Match: "v1"` | 304 | 200 (new representation) |
| HEAD | `If-None-Match: "v1"` | 304 | HEAD 200 without body |
| GET | `If-Modified-Since` | 304 if unchanged since date | 200 |
| PUT | `If-Match: "v1"` | Write only if current version matches | 412 if current ETag differs |
| DELETE | `If-Match: "v1"` | Delete if precondition matches and authorized | 412 if mismatched |
| PUT create-only | `If-None-Match: *` | 412 if resource already exists | Can create if absent |
| PUT | `If-Unmodified-Since` | Write only if unchanged since date | 412 if modified |

In the table, the "matched" column for `If-None-Match` means **the ETag matches**, causing the "none match" precondition to fail; do not confuse boolean evaluation with the status code.

## 10. Where Does Spring MVC Help?

Spring Framework provides several mechanisms:

- `ResponseEntity.ok().eTag(...).lastModified(...).cacheControl(...).body(dto)`: declares validators and cache directives on the response. Spring MVC handles conditional GET/HEAD accordingly to return 304 when tag/date match, without manually constructing 304 in common cases.
- `WebRequest.checkNotModified(...)`: controllers can proactively check validators before constructing an expensive body and exit early when appropriate.
- `ShallowEtagHeaderFilter`: computes an ETag from the already-rendered response content; saves bandwidth but **does not avoid the work of generating the body**.
- Static resource handling: Spring MVC provides built-in caching/conditional request support for static resources and `Resource`, when properly configured.
- `CacheControl`: builds `Cache-Control` headers in `ResponseEntity`.
- `ServletWebRequest`/`HttpServletResponse`: lower-level options when fine-grained control is required.

Official reference: Spring Framework — HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html

### 10.1. Short ResponseEntity Example

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookResponse> get(@PathVariable long id) {
    BookResponse book = service.find(id);
    return ResponseEntity.ok()
        .eTag("\"book-" + book.version() + "\"")
        .lastModified(book.updatedAt().toEpochMilli())
        .cacheControl(CacheControl.noCache())
        .body(book);
}
```

**This is a controller snippet** assuming `service`, `BookResponse` record, and imports already exist, not a standalone compilable app. Ensure ETag/`updatedAt` metadata stays consistent with the returned body. Spring MVC handles `If-None-Match` and `If-Modified-Since` on this `ResponseEntity`.

### 10.2. checkNotModified Before Rendering an Expensive View

```java
@GetMapping("/reports/{id}")
public String report(
        @PathVariable long id, WebRequest request, Model model) {

    String etag = reportService.currentEtag(id);

    if (request.checkNotModified(etag)) {
        return null; // MVC already prepared 304 / conditional response.
    }

    model.addAttribute("report", reportService.render(id));
    return "report";
}
```

This is also a **snippet** requiring appropriate beans and imports. It avoids generating an expensive report when preconditions allow returning 304, **provided** the metadata is trustworthy enough to decide up front. Always check authentication/authorization before checking validators to avoid leaking resource existence or state to unauthorized callers.

### 10.3. ShallowEtagHeaderFilter Is Not a Deep Validator

A shallow ETag filter typically has to render the response (and buffer/capture its content) before computing a checksum. It can save **bandwidth on 304 responses**, but it does not save controller, DB, or serialization work on the check request. For large or streaming responses, buffering can consume significant RAM/latency and is unsuitable.

When you know the revision or update timestamp quickly from metadata, a **deep ETag** in the controller/service is usually better. If using `ShallowEtagHeaderFilter`, read the documentation on conditional handling, async dispatch, response wrapping, and exclusions; do not enable it blindly across streaming/file endpoints.

## 11. Runnable Example: Document with Conditional GET and PUT If-Match

The sample app uses **Spring Boot 3.x + Java 17** and Maven:

- `spring-boot-starter-web`: Spring MVC / Jackson.
- `spring-boot-starter-validation`: validation for the PUT body.
- `spring-boot-starter-test` (test scope): JUnit / MockMvc.

No database is needed. A document is stored in an `AtomicReference`. Both the precondition check and the update commit are combined via `compareAndSet`, illustrating race prevention within a **single JVM**. Multi-instance production deployments must use DB transactions/conditional updates or equivalent distributed state mechanisms.

Files:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  DocumentController.java
src/test/java/com/example/demo/
  DocumentControllerTest.java
```

### 11.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.2. DocumentController.java

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(
                1L, "Xin chào", 1L,
                Instant.parse("2026-10-01T10:00:00Z")));

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<DocumentResponse> find(
            @PathVariable long id) {

        State current = state.get();
        if (id != current.id()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .eTag(etag(current))
                .lastModified(current.updatedAt().toEpochMilli())
                .body(new DocumentResponse(
                    current.id(), current.text(), current.version()));
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> replace(
            @PathVariable long id,
            @RequestHeader(value = HttpHeaders.IF_MATCH,
                           required = false) String ifMatch,
            @Valid @RequestBody UpdateRequest input) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        if (ifMatch == null || ifMatch.isBlank()) {
            // API policy: reject PUT without precondition.
            return ResponseEntity.status(
                    HttpStatus.PRECONDITION_REQUIRED).build();
        }

        // CAS couples version check with update.
        for (;;) {
            State before = state.get();

            if (!strongIfMatch(ifMatch, etag(before))) {
                return ResponseEntity.status(
                        HttpStatus.PRECONDITION_FAILED).build();
            }

            State after = new State(
                    before.id(),
                    input.text(),
                    before.version() + 1,
                    Instant.now().truncatedTo(ChronoUnit.SECONDS));

            if (state.compareAndSet(before, after)) {
                // Do not return a body with 204.
                return ResponseEntity.noContent().build();
            }
            // Concurrent PUT won CAS; re-read version and re-check.
        }
    }

    private static String etag(State current) {
        return "\"doc-" + current.version() + "\"";
    }

    private static boolean strongIfMatch(
            String header, String currentEtag) {

        String value = header.trim();

        // If-Match: * when the resource exists.
        // Do not use * to prevent overwrites: it only requires existence.
        if ("*".equals(value)) {
            return true;
        }

        // Example only produces tags like "doc-N" without commas;
        // this split parser does NOT replace a general RFC grammar parser.
        return Arrays.stream(value.split(","))
                .map(String::trim)
                .anyMatch(candidate -> candidate.equals(currentEtag));
        // W/"doc-N" will not match strong currentEtag.
    }

    private record State(
            long id, String text, long version, Instant updatedAt) {}

    public record DocumentResponse(
            long id, String text, long version) {}

    public record UpdateRequest(
            @NotBlank @Size(max = 2000) String text) {}
}
```

**Parser limitations in demo:** `strongIfMatch` supports server-generated `"doc-N"` tags, lists of such tags, and `*`. It is not a full RFC ETag parser for arbitrary opaque tags containing commas or escapes; if your API supports broad clients, use a compliant parser or dedicated framework component. `W/"doc-N"` fails strong matching, consistent with `If-Match` semantics.

**Timestamp limitations:** `updatedAt` is truncated to seconds; two PUTs within the same second can share the same `Last-Modified`. The example prioritizes the `ETag` revision and underscores not relying on `Last-Modified` alone to guard high-rate writes. If a system requires accurate IMS-only behavior under concurrency, design appropriate timestamps or use `ETag` as the primary validator.

**Cache/storage limitations:** `AtomicReference` only protects data within **a single process**, loses state on restart, and does not synchronize across multiple pods. Use database `@Version` or conditional SQL updates in real applications, mapping conflicts to `412`. Do not confuse in-memory Java CAS with distributed transactions.

**Access control limitations:** The demo has authentication/authorization disabled. Production code must verify the user has read/write permission on the document before confirming version or existence. Use `CacheControl.noCache().cachePrivate()` or `noStore()` depending on sensitivity. Never publicly cache personal data.

## 12. Running the Demo and Verifying with curl

Run inside the created Boot 3 Maven project:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

The application listens on port 8080 unless `server.port` is changed. The Java file depends on Spring libraries; standalone `javac DocumentController.java` will lack the classpath.

### 12.1. Initial GET: 200 + Validators

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/documents/1
```

Right after app startup (before any PUT), expected output:

```http
HTTP/1.1 200 OK
ETag: "doc-1"
Last-Modified: Thu, 01 Oct 2026 10:00:00 GMT
Cache-Control: no-cache
Content-Type: application/json

{"id":1,"text":"Xin chào","version":1}
```

Other HTTP headers may be added by Boot/server; JSON field ordering is determined by Jackson. The date is the hardcoded startup timestamp in the demo, **not** the current request time.

### 12.2. Conditional GET by ETag: 304

```bash
curl -i -H 'If-None-Match: "doc-1"' \
  http://localhost:8080/api/documents/1
```

Expect **304 Not Modified** with no response body. If using Windows PowerShell or cmd, quote/escape properly for your shell; for example, PowerShell can use `curl.exe -i -H 'If-None-Match: "doc-1"' URL`.

Try a weak tag:

```bash
curl -i -H 'If-None-Match: W/"doc-1"' \
  http://localhost:8080/api/documents/1
```

Expect **304**, because `If-None-Match` uses weak comparison. Once the state advances to a newer version, both old headers will stop matching and GET will return **200** with the new version.

### 12.3. Conditional GET by Timestamp

```bash
curl -i \
  -H 'If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT' \
  http://localhost:8080/api/documents/1
```

Before any update, it normally returns **304**. After a successful PUT at a later time, a request using the old date returns **200** with the new JSON.

### 12.4. If-None-Match Takes Precedence Over If-Modified-Since

```bash
curl -i \
  -H 'If-None-Match: "not-current"' \
  -H 'If-Modified-Since: Thu, 01 Oct 2026 10:00:00 GMT' \
  http://localhost:8080/api/documents/1
```

Expect **200**, because the ETag differs and the date condition must be ignored when `If-None-Match` is present. This test catches servers that implement conditional checks with broken OR logic.

### 12.5. PUT Without If-Match: 428

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  --data '{"text":"Nội dung mới"}' \
  http://localhost:8080/api/documents/1
```

The demo returns **428 Precondition Required** due to its policy requiring `If-Match` on writes. Not every server must enforce this policy; `428` is a deliberate API choice.

### 12.6. PUT with Matching Version: 204 Then GET New Version

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "doc-1"' \
  --data '{"text":"Nội dung mới"}' \
  http://localhost:8080/api/documents/1
```

If no prior PUT occurred, returns **204 No Content**. Then:

```bash
curl -i http://localhost:8080/api/documents/1
```

Expect **200**, body:

```json
{"id":1,"text":"Nội dung mới","version":2}
```

The ETag header is now `"doc-2"`. Re-GET after PUT to obtain the new validator; the demo does **not** attach the new ETag to the 204 response.

### 12.7. PUT with Stale ETag: 412

```bash
curl -i -X PUT \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "doc-1"' \
  --data '{"text":"Nội dung stale"}' \
  http://localhost:8080/api/documents/1
```

Expect **412 Precondition Failed**, leaving document version 2 untouched. Sending `If-Match: W/"doc-2"` also returns `412` because weak validators do not strong-match. Sending `If-Match: *` semantically checks existence only and **does not prevent overwriting changes between GET and PUT**; users must understand this distinction.

### 12.8. GET Non-Existent Resource: 404

```bash
curl -i http://localhost:8080/api/documents/999
```

Expect **404 Not Found**. Never return `304` just because a client sent some cached ETag; another resource's validator does not apply to a different URI.

## 13. MockMvc: Testing Conditional GET and Concurrent Updates

Create `src/test/java/com/example/demo/DocumentControllerTest.java` in a project with `spring-boot-starter-test`.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    private String currentTag() throws Exception {
        MvcResult result = mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().exists(HttpHeaders.ETAG))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andReturn();

        return result.getResponse().getHeader(HttpHeaders.ETAG);
    }

    @Test
    void matchingTagReturns304WithoutBody() throws Exception {
        String tag = currentTag();

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, tag))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void weakValidatorAlsoMatchesForGet() throws Exception {
        String tag = currentTag();

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, "W/" + tag))
            .andExpect(status().isNotModified());
    }

    @Test
    void staleTagOverridesDateValidator() throws Exception {
        MvcResult initial = mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk()).andReturn();

        String lastModified = initial.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);

        mvc.perform(get("/api/documents/1")
                .header(HttpHeaders.IF_NONE_MATCH, "\"not-current\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, lastModified))
            .andExpect(status().isOk());
    }

    @Test
    void putRequiresVersionAndRejectsStaleWrites() throws Exception {
        String old = currentTag();

        mvc.perform(put("/api/documents/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"New content\"}"))
            .andExpect(status().isPreconditionRequired());

        mvc.perform(put("/api/documents/1")
                .header(HttpHeaders.IF_MATCH, old)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"New content\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(put("/api/documents/1")
                .header(HttpHeaders.IF_MATCH, old)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Stale overwrite\"}"))
            .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.text").value("New content"));
    }
}
```

The test suite shares a singleton controller with in-memory state, so each test fetches the **current ETag** instead of hardcoding revision 1. Do not run concurrently with other tests modifying the same resource if you want deterministic assertions; if using JUnit parallel execution, isolate state/repository per test. The `lastModified` test depends on the server clock; do not let a precedence test rely on a timestamp that might change within the same second.

Run:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

This is **sample test code**, not a claim that it was executed on the user's repository. When Spring Security is enabled, PUT tests may be blocked with `403` by CSRF/authorization filters before reaching the controller; add `spring-security-test`, `with(csrf())`, and an authorized user per policy, then verify `428`/`412`.

### Useful Additional Tests

- Unconditional GET returns `200`, body, and both `ETag`/`Last-Modified`.
- GET with `If-Modified-Since` matching the date returns `304`, and an older date returns `200`.
- `If-None-Match` with multiple tags where the second tag matches still returns `304`.
- GET with a different ETag returns `200` and a fresh body.
- PUT with `If-Match: W/"doc-N"` returns `412`.
- PUT with malformed JSON or blank text returns `400` before write logic runs.
- Concurrent PUTs with the same ETag: **only one request succeeds**, and the other gets `412` under CAS.
- Verify `304` contains no body while retaining appropriate validator/cache headers.
- GET for a non-existent resource returns `404`; never leak versions to unauthorized callers.
- With a real HTTP server, check whether proxies/caches strip or alter `ETag`, `Vary`, or `Content-Encoding`.

## 14. Last-Modified in Spring MVC and One-Second Resolution

Database `Instant` values can hold milliseconds or nanoseconds, whereas HTTP-date only represents **seconds**. If you compare a raw `Instant` against `If-Modified-Since` and return `200` when nothing actually changed, it may simply be a sub-second difference. Conversely, if an update occurs within the same second, a date-only validator can wrongly return `304` for a changed resource.

Therefore:

1. Define an authoritative `updatedAt` with accurate semantics for the **entire representation**.
2. When serving date validators, normalize comparisons to HTTP-date precision rather than comparing raw milliseconds arbitrarily.
3. For frequent updates, prefer `ETag`; clients should send `If-None-Match` when available.
4. Do not use `Last-Modified` from row A if the JSON response also depends on row B, which has changed.
5. Never use client-provided dates as the source of truth for updating metadata.
6. Across server replicas, keep validators consistent for the same resource version.
7. Do not rely on date-only `If-Unmodified-Since` as OCC when sub-second writes can occur.

`Instant.now().truncatedTo(ChronoUnit.SECONDS)` in the demo keeps HTTP-date formatting clean; **it does not turn a date validator into a strong optimistic locking mechanism**.

## 15. Vary, Content-Encoding, and Representation Variants

One resource can return JSON or XML or multiple languages:

```http
GET /articles/7
Accept: application/json
Accept-Language: vi-VN
Accept-Encoding: gzip
```

If the representation varies by these headers, caches must distinguish the corresponding variants. The `Vary` header tells caches which request headers participate in representation selection:

```http
Vary: Accept, Accept-Language, Accept-Encoding
```

This is an **example**—include only headers that genuinely affect the representation. Compression, content negotiation, or CDNs may add `Vary` depending on infrastructure; do not blindly list every header.

`ETag` must also correspond to the **selected representation**. A strong ETag for JSON with different bytes from XML or a Vietnamese version may need to differ; if two variants are considered semantically equivalent, consider weak validators with appropriate semantic rules. A hash computed from uncompressed JSON bytes cannot be reused verbatim as a strong tag for a gzipped byte stream without accounting for HTTP representation coding semantics.

**The cache key is not just the URL** when `Vary` is present. If a personal response is publicly cached by URL without accounting for `Authorization`/cookies, `ETag` will not fix the data leak. `private`, `no-store`, security, and CDN settings must be designed cohesively.

## 16. Cache-Control: no-cache, no-store, private, max-age

| Directive | Primary meaning |
| --- | --- |
| `no-cache` | May be stored, but **must revalidate** before reuse |
| `no-store` | Do not store the response content per cache directive |
| `private` | Only private caches (e.g. browsers) may store per policy; shared caches must not |
| `public` | Permits shared caching when relevant conditions are met |
| `max-age=60` | Fresh for 60 seconds per HTTP age semantics |
| `must-revalidate` | Once stale, caches must revalidate before reuse per rules |
| `immutable` | Resource is expected not to change during freshness lifetime when applicable |

For personal/secret data, `CacheControl.noStore()` is usually preferable to conditional GET if caching is disallowed. For public data that rarely changes and needs bandwidth savings, use `maxAge(...)` paired with `ETag`/`Last-Modified` after expiration. For data that must be checked with the server every time, `noCache()` plus a validator is a common pattern.

`ETag` does not replace `Cache-Control`. `304` is a revalidation response with no body; caches apply metadata update rules to the stored response upon receiving `304`.

## 17. 304 and Which Headers to Preserve

A **304 Not Modified** response has no message body. The server must supply appropriate cache/validator metadata per RFC 9110 and RFC 9111, including relevant headers that a corresponding `200` would send, such as `ETag`, `Cache-Control`, `Content-Location`, `Date`, `Expires`, and `Vary` as specified.

Not every `304` necessarily carries the exact same `Content-Type` as a `200`; check standard header requirements and framework behavior. Never call `response.getWriter().write(...)` after deciding on `304` and never return JSON like `{"message":"not modified"}` as a 304 body.

Without a stored copy in the cache/client, a `304` response alone **cannot** produce content. Clients should not send validators arbitrarily unless they actually hold the corresponding stored state, and when no cached body exists they must fetch a `200` again.

## 18. HEAD, Range, If-Range, and Large Files

`HEAD` shares `GET` metadata semantics without a response body. `If-None-Match`/`If-Modified-Since` also apply to conditional `HEAD`.

For file downloads:

- `Range` can request a partial slice of a representation.
- `If-Range` tells the server to return partial content only if the validator matches; otherwise, ignore `Range` and return the full representation.
- `If-Range` requires an appropriate validator; **never use a weak ETag** for byte-range conditions.
- Partial responses can be **206 Partial Content** or **416 Range Not Satisfiable** depending on the request.
- Conditional requests and `Range` follow specific RFC ordering/rules; do not turn every `Range` request with `If-None-Match` into a `206`.

This example does not implement file ranges. If a large-file download API needs resume support, use Spring `Resource` and built-in controller/static resource features, testing over real HTTP with `ETag`, `If-Range`, `Accept-Ranges`, `Content-Range`, and proxies. Do not hand-roll byte-range parsers just to save a few lines.

## 19. Multi-Instance Optimistic Locking and Databases

A multi-replica backend cannot use a per-pod `AtomicReference`: pods have separate state and conflicting ETags. Move the authoritative version into a database (or transactionally consistent storage).

Conceptual SQL example:

```sql
UPDATE documents
SET text = :newText,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND version = :expectedVersion;
```

If row count = 1, the update succeeded. If row count = 0, distinguish missing resource / permission change from a stale version per contract, typically returning `404`/`403`/`412`. Every precondition must be checked **at the same atomic point as the mutation**, never separating a version GET from an unconditional UPDATE.

Spring Data JPA `@Version` provides entity optimistic locking, though exceptions or flush timing can occur anywhere inside the transaction; controllers/services must map conflicts properly instead of swallowing errors into `200`. When using `If-Match`, avoid trusting unvalidated version tokens or tokens mismatched to the resource/user.

### 412 vs. 409

- `412 Precondition Failed`: the request's `If-Match`/`If-Unmodified-Since`/`If-None-Match` header does not match current state.
- `409 Conflict`: conflict with domain state/business rules outside preconditions (e.g., an order state that cannot be canceled).
- `428 Precondition Required`: the server requires conditional requests, and the client omitted the condition.

Do not turn every optimistic locking exception into `409` if the HTTP contract specifies `If-Match`. Conversely, a missing precondition is not automatically `428` unless the API defines that policy.

## 20. Common Mistakes

1. **Omitting quotes on ETags:** `If-None-Match: abc` is not the valid syntax for tag `"abc"`.
2. **Using weak ETags for strong If-Match:** fails strong matching; usually yields 412.
3. **Treating ETag as a password/secret identifier:** can be leaked, cached, logged, or tracked.
4. **Assigning the same strong ETag to JSON and XML with different bytes:** validator fails to reflect the selected representation.
5. **Relying only on the main table's updatedAt when JSON joins multiple tables:** data changes while the validator stays stale.
6. **Assuming ETag alone makes caching safe:** requires `Cache-Control`, auth, and cache policies.
7. **Confusing no-cache with no-store:** `no-cache` still permits storage but requires revalidation.
8. **Writing `If-None-Match OR If-Modified-Since` manually:** breaks precedence when both headers are sent.
9. **Using nano precision in Last-Modified HTTP headers:** HTTP-date only has one-second resolution.
10. **Using date-only optimistic locking with multiple writes per second:** risks lost updates.
11. **Returning a JSON body with 304:** violates HTTP semantics.
12. **Returning 304 when the resource does not exist:** confused with 404.
13. **Checking version and saving non-atomically afterward:** two clients can overwrite each other.
14. **Enabling ShallowEtagHeaderFilter thinking it avoids queries/serialization:** the filter needs the rendered body to hash.
15. **Checksumming large bodies on every request assuming it's free:** consumes CPU, RAM, and buffering.
16. **Ignoring Vary with multiple representations/locales:** shared caches can serve the wrong variant.
17. **Using personalized ETags with public caching:** leaks data and tracks users.
18. **Failing to check auth before returning validators:** can disclose existence or version.
19. **Using If-Match: * to prevent overwrites:** `*` only checks existence.
20. **Relying on controller-read version instead of DB locking:** check/write race remains.
21. **Trying to return 304 on PUT:** when `If-None-Match` is false on non-GET/HEAD methods, status is normally `412`.
22. **Not testing 412/428:** frontends silently overwrite other users' changes.
23. **Not testing that 304 has an empty body:** clients may mishandle cache entries.
24. **Not measuring bandwidth and server CPU separately:** shallow validators save bandwidth, not rendering work.
25. **Not testing through proxies/CDNs:** edges may strip/rewrite validators or compress/alter representations.
26. **Missing migration/invalidation on serialization/schema changes:** old strong ETags may become invalid.

## 21. Production Deployment Checklist

### Resources and Representations

- [ ] Does the validator accurately represent the resource/representation and change whenever public content changes?
- [ ] Were strong vs. weak ETags chosen deliberately according to semantics?
- [ ] Are ETag values opaque, leaking no secrets or PII?
- [ ] Is `Last-Modified` a server-authoritative HTTP-date with same-second risks addressed?
- [ ] With multiple variants, are `Vary` and `ETag` aligned with representation selection?
- [ ] Does personal data use `Cache-Control` `private`/`no-store` appropriately without accidental `public` caching?

### Conditional Reads

- [ ] Does unconditional GET return `200`, body, and `ETag` (plus `Last-Modified` if used)?
- [ ] Does matching `If-None-Match` return `304` **with no body**?
- [ ] Does stale `If-None-Match` return `200` with the new body?
- [ ] When both `If-None-Match` and `If-Modified-Since` are sent, is precedence tested?
- [ ] Are invalid dates and inapplicable methods handled properly?
- [ ] Does `304` preserve required cache/validator headers?
- [ ] Do auth/tenant checks run before disclosing any resource validator?

### Conditional Writes

- [ ] Are `If-Match` strong tags compared properly, with weak tags rejected for lost-update protection?
- [ ] Does a missing precondition return `428` if required by the API?
- [ ] Does a stale precondition return `412` without mutating state?
- [ ] Are check + update atomic in the DB/transaction or equivalent CAS?
- [ ] Across multiple pods/instances, is the version consistent?
- [ ] Are races tested rather than relying on a separate read-before-write?
- [ ] Does GET after update provide the new validator to clients?

### System

- [ ] Do MockMvc tests cover headers, bodies, status codes, and header precedence?
- [ ] Are there HTTP integration tests through the servlet container, reverse proxy, and CDN?
- [ ] Is shallow ETag avoided on streaming/large content unless explicitly justified?
- [ ] Are cache hits, revalidation, bandwidth, CPU, and DB load measured separately?
- [ ] Is monitoring of `304`/`412`/`428` and logging free of sensitive data inside ETags?

## 22. Self-Check Questions

**1.** How does `ETag` differ from `Cache-Control`?

**Answer:** `ETag` is a representation validator; `Cache-Control` governs storage, reuse, and revalidation. Having an ETag does not mean public caching is permitted.

**2.** When GET sends `If-None-Match` matching the current ETag, what does the server return?

**Answer:** Typically `304 Not Modified` with an empty body; the client reuses its cached body.

**3.** What happens when PUT sends a stale `If-Match` after someone else updated the resource?

**Answer:** `412 Precondition Failed` when the precondition fails, without performing the mutation.

**4.** Does `If-Match: W/"abc"` match a strong current ETag `"abc"`?

**Answer:** No. `If-Match` uses strong comparison.

**5.** What if GET carries both a stale `If-None-Match` and an `If-Modified-Since` matching the current date?

**Answer:** `If-None-Match` takes precedence. The stale tag does not block the new body, so the request can return `200`.

**6.** Why is `Last-Modified` hard to use to guard rapid writes?

**Answer:** HTTP-date only has one-second resolution, so it cannot distinguish two modifications within the same second.

**7.** Why doesn't `ShallowEtagHeaderFilter` save DB queries?

**Answer:** It computes the ETag from the already-rendered response body, so it generally cannot skip building the body.

**8.** Does `If-Match: *` prevent lost updates?

**Answer:** No. It only requires that the resource exist, not that it match a specific version.

**9.** Do multiple pods running separate `AtomicReference` instances prevent system-wide lost updates?

**Answer:** No. You need authoritative state, transactions, and versioning in a shared database or storage.

**10.** May a `304` response include JSON describing "not modified"?

**Answer:** No. `304` has no message body; return standard validator/cache metadata instead.

**11.** Why might an ETag from a table's version column fail to be strong for JSON?

**Answer:** JSON can change due to serializers, locales, related entities, or fields outside that row's version, so the tag doesn't fully represent the bytes.

**12.** When `If-Match` is missing on a PUT, when should `428` be returned?

**Answer:** When the API requires a precondition to protect writes; `428` is a server policy, not mandatory for every PUT.

## 23. References

- Spring Framework — HTTP Caching (controllers, CacheControl, ShallowEtagHeaderFilter): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- Spring Framework — ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html
- Spring Framework — ServletWebRequest Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html
- Spring Framework — ShallowEtagHeaderFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html
- Spring Framework — CacheControl API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/http/CacheControl.html
- RFC 9110 — HTTP Semantics, conditional request fields `If-Match`, `If-None-Match`, `If-Modified-Since`, `If-Unmodified-Since`, `If-Range`, `304`/`412`: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9111 — HTTP Caching (`Cache-Control`, `Vary`, validation, 304 updates): https://www.rfc-editor.org/rfc/rfc9111.html
- RFC 6585 — Additional HTTP Status Codes (`428 Precondition Required`): https://www.rfc-editor.org/rfc/rfc6585.html
- Spring Data JPA — Optimistic Locking/`@Version` use: https://docs.spring.io/spring-data/jpa/reference/
- Jakarta Persistence specification: https://jakarta.ee/specifications/persistence/
