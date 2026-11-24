# If-None-Match, If-Modified-Since, and 304 Responses in Spring MVC

## 1. Objectives

A web page or REST client may already have downloaded the JSON, image, document, or HTML for a URL. If the resource **has not changed**, re-downloading all bytes wastes bandwidth. HTTP solves this with **conditional requests**: the server provides **validators** (`ETag`, `Last-Modified`); next time, the client sends conditions (`If-None-Match`, `If-Modified-Since`); the server checks the current version and can return **304 Not Modified** without re-sending the response content.

This lesson explains the full HTTP mechanism and how Spring MVC 6.x implements it. By the end, you will be able to:

- Distinguish **cache freshness** (`Cache-Control`) from **revalidation** (`If-None-Match`/`If-Modified-Since`).
- Understand strong/weak `ETag`, `Last-Modified`, HTTP-date formatting, and timestamp precision.
- Determine the exact precedence when **both conditions** appear; handle `If-None-Match: *`, multiple tags, mismatching tags, and older/newer timestamps.
- Explain how **304 differs from 200 and 204**, why 304 carries no message body, and why caches can still display the stored 200 response.
- Use `ResponseEntity.eTag(...).lastModified(...).cacheControl(...)` and `WebRequest.checkNotModified(...)` in Spring MVC.
- Test combinations with **MockMvc**, run `curl` to inspect status/headers/body, and account for cache proxies/CDNs/CORS.
- Avoid dangerous pitfalls when caching authenticated data, multiple languages/content encodings, changing files, and using `ShallowEtagHeaderFilter`.

**Scope:** HTTP/1.1 and HTTP/2 semantics per **RFC 9110 and RFC 9111**; Java 17+, **Spring Boot 3.x / Spring Framework 6.x / Spring MVC Servlet stack**. Do not confuse this with HTTP caching in WebFlux or internal `@Cacheable` caching.

## 2. HTTP Cache Revalidation Flow: 200 First, 304 Later

### 2.1. First Access

Suppose the client sends:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.com
Accept: application/json
~~~

The server returns the current representation along with validators:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=300
ETag: "book-7-v3"
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT

{"id":7,"title":"HTTP caching","version":3}
~~~

In the example, `ETag` is a **double-quoted** string per entity-tag syntax; `Last-Modified` is an **HTTP-date in GMT**. `Cache-Control: private, max-age=300` lets a private cache like a browser consider the representation fresh for about five minutes, while forbidding shared caches from reusing it across multiple users. Actual duration also depends on response/request directives and HTTP caching rules.

The client stores the **JSON body + cache metadata** if storage conditions permit.

### 2.2. When the Cache Needs to Revalidate

After the response loses freshness (or the client requests revalidation), the client can send:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.com
If-None-Match: "book-7-v3"
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

If the version is still `"book-7-v3"`, the server can return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "book-7-v3"
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT
Cache-Control: private, max-age=300

~~~

**No new body.** The client/cache reuses the **body stored from the earlier 200**, while updating permitted metadata from the 304 response. `304` does **not** mean an empty resource, is not an error code, and is not a failed mutation.

If the resource has changed—say to version 4—the server returns **200 OK**, a new ETag, and a new body:

~~~http
HTTP/1.1 200 OK
ETag: "book-7-v4"
Content-Type: application/json

{"id":7,"title":"HTTP caching - revised","version":4}
~~~

The messages above are minimal illustrations; real servers/proxies may add `Date`, `Vary`, and other headers.

### 2.3. Decision Diagram

~~~text
Does client have a cached representation?
     |
     +-- No  -> Normal GET -> 200 + body + validators (if any)
     |
     +-- Yes and still fresh -> can use cache, no request sent
     |
     +-- Needs revalidation -> GET + If-None-Match / If-Modified-Since
                                    |
                                    +-- Validator matches -> 304, no body
                                    |                          |
                                    |                          +-- reuse old body
                                    |
                                    +-- Resource changed -> 200 + new body
~~~

A request may force the server or cache to revalidate even if the cached copy has not truly expired (e.g., reload or differing cache directives). Conversely, while the cache is still fresh, **no network request is necessarily made** to observe a 304.

## 3. What Is an ETag: Representation Version, Not a Security Token

An **ETag (entity tag)** is a validator for a **selected representation** of a resource. It takes the form:

~~~http
ETag: "book-7-v3"
~~~

or a weak ETag:

~~~http
ETag: W/"book-7-v3"
~~~

- **Strong ETag** (`"abc"`) carries strong comparison semantics, suitable when guaranteeing byte-equivalent representation data per HTTP requirements.
- **Weak ETag** (`W/"abc"`) indicates semantic equivalence within a defined scope; it may not be byte-for-byte identical.
- **`If-None-Match` uses weak comparison** per RFC 9110: weak/strong tags with matching opaque values match for GET/HEAD revalidation.
- **`If-Match` uses strong comparison** (typically for optimistic concurrency on updates) and does not share `If-None-Match` semantics.
- The ETag must correspond to the returned **representation**. If the same URL has variants differing by `Accept-Language`, `Accept-Encoding`, content negotiation, user permissions, or query parameters, the ETag strategy must reflect the variant and set `Vary` appropriately.

An ETag is **not** a digital signature, access token, security checksum, or proof of authorization to read a resource. Never embed a secret in an ETag, and never use an ETag value for authorization.

### 3.1. How Should You Generate ETags?

Several options:

1. **Stored database version** (e.g., `bookId=7, version=3`), provided the version changes every time the representation content changes.
2. **Content hash** of the serialized representation, when a validator tied to actual bytes is needed; hashing per request can consume CPU.
3. **Asset build version** or object-storage version ID, suited for static assets and immutable documents.

Version-based example:

~~~java
String etag = "\"book-" + book.id() + "-v" + book.version() + "\"";
~~~

This is **one illustrative line**, assuming `book` is a DTO with `id()` and `version()`. A version-based ETag is only valid if **every change affecting the representation increments the version**. If JSON varies by user/locale/format under the same version, sharing one strong tag is wrong; you must distinguish representation variants.

### 3.2. When to Use a Weak ETag?

If an HTML view has minor byte differences (such as whitespace formatting) that the application treats as content-equivalent, a weak ETag can express that. However, weak ETags are **not** suitable where byte-exact validators are required, such as `If-Range` with a strong validator.

Do not convert all strong tags to weak tags just to "reduce risk" without understanding data semantics. Pick the validator type matching your consistency contract.

## 4. If-None-Match: Ways to Send and Evaluate

Example when the client already has an ETag:

~~~http
If-None-Match: "book-7-v3"
~~~

A request can send multiple values:

~~~http
If-None-Match: "book-7-v1", "book-7-v2", "book-7-v3"
~~~

If **any** tag matches the current entity tag under weak comparison, the `If-None-Match` condition evaluates to **false** (meaning the client says "I do not want a representation with this tag"). For GET/HEAD, the server returns **304 Not Modified** when the precondition fails. If no tag matches, the server executes GET/HEAD and returns the new representation, usually 200.

Wildcard example:

~~~http
If-None-Match: *
~~~

`*` behaves differently from literal tag lists: the condition fails whenever the resource has **any current representation**, regardless of tag. For GET/HEAD on an existing resource, standard handling can return 304; for a non-existent resource, it must not turn into 304. **Never mix `*` with literal tags** in the same header field — that syntax is invalid.

### 4.1. GET/HEAD vs. PUT/POST/DELETE

`If-None-Match` is **not** solely for caching. For example, a client uses `If-None-Match: *` on a create request to mean "create only if no representation exists yet." If the condition fails on an **unsafe method**, the server must return **412 Precondition Failed**, **not** 304.

| Method when `If-None-Match` evaluates false | Standard response when evaluating precondition |
| --- | --- |
| GET | 304 Not Modified |
| HEAD | 304 Not Modified |
| PUT | 412 Precondition Failed |
| POST | 412 Precondition Failed |
| DELETE | 412 Precondition Failed |

This table describes preconditions evaluated and failed under RFC 9110 rules; it does **not** mean Spring MVC automatically handles concurrency for every endpoint just because you attached an ETag to GET. For update operations, explicitly design transactions, versions, `If-Match`, or conditional writes.

### 4.2. Weak vs. Strong Comparison

Suppose the current strong ETag is `"v3"`. When a GET sends:

~~~http
If-None-Match: W/"v3"
~~~

the `If-None-Match` condition is still considered a **match**, and the server returns 304. In contrast, `If-Match: W/"v3"` does not pass strong comparison against `"v3"`.

Do not manually strip `W/` or quotes to compare with `String.equals`. HTTP defines exact entity-tag list syntax and comparison rules, and frameworks provide parsing support; if implementing custom logic, use a compliant parser.

## 5. If-Modified-Since: Comparing Modification Times

`Last-Modified` in a response indicates when the resource representation was last modified:

~~~http
Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT
~~~

A client can send:

~~~http
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

If the current modification time is **not later than** (earlier than or equal to) the client-supplied time, the server can return 304 for GET/HEAD. If the resource is newer than that timestamp, the server returns 200 and the new body.

**The timestamp must follow standard HTTP-date syntax**, not an arbitrary string like `2025-01-15T10:30:00` in the request header. ISO-8601 is helpful in JSON, but does not replace the HTTP-date format of `If-Modified-Since`.

Subtleties:

- `Last-Modified` HTTP-dates have **one-second resolution** in practice. If a resource changes twice within the same second, timestamps may fail to detect the change reliably.
- Clocks across nodes/servers or source metadata can differ; do not assign the current timestamp to an unchanged resource if stable revalidation is desired.
- Per RFC 9110, servers must **ignore `If-Modified-Since`** if the request contains `If-None-Match`, or if the field is not a valid HTTP-date, has invalid multiple values, or the method is not GET/HEAD.
- Reliable `Last-Modified` values usually come from resource/storage metadata rather than computing `Instant.now()` on every GET.
- For rapidly changing resources, a strong ETag is generally more accurate than second-granularity timestamps, provided it is generated accurately per representation.

### 5.1. Timeline Example

| Current Last-Modified | If-Modified-Since | Typical GET outcome |
| --- | --- | --- |
| 10:30:00 GMT | 10:30:00 GMT | 304 |
| 10:30:00 GMT | 10:31:00 GMT | 304 if precondition is validly evaluated |
| 10:30:01 GMT | 10:30:00 GMT | 200, new body |
| 10:30:00 GMT | Invalid value | Ignore header, process GET normally |

This table only evaluates `If-Modified-Since` **when If-None-Match is absent** and the current resource exists. Other preconditions, cache state, permissions, and resource availability can also affect the result.

## 6. Precedence Rule: If-None-Match Beats If-Modified-Since

This is the most error-prone point when implementing caching:

> **When a request includes both `If-None-Match` and `If-Modified-Since`, the recipient must ignore `If-Modified-Since` and evaluate `If-None-Match` instead.**

Suppose the current ETag is `"v4"` and the current `Last-Modified` is `Wed, 15 Jan 2025 10:30:00 GMT`.

**Case A: Tag matches, timestamp mismatches or is too old**

~~~http
If-None-Match: "v4"
If-Modified-Since: Tue, 14 Jan 2025 00:00:00 GMT
~~~

Because the tag matches, GET can return **304** even though the request timestamp is old. Do not evaluate them with AND logic.

**Case B: Tag mismatches, yet timestamp is new enough**

~~~http
If-None-Match: "v3"
If-Modified-Since: Thu, 16 Jan 2025 00:00:00 GMT
~~~

Because `If-None-Match` does not match the current tag, the server should return **200 with the new representation**, even though checking timestamp alone would look eligible for 304.

**Case C: No ETag condition, timestamp matches**

~~~http
If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT
~~~

GET can return **304** based on the time condition, because there is no `If-None-Match` taking precedence.

| If-None-Match | If-Modified-Since | Current validator | Typical GET outcome |
| --- | --- | --- | --- |
| Omitted | Omitted | Has ETag/time | 200 + body |
| Matches ETag | Omitted | Tag unchanged | 304 |
| Mismatches ETag | Omitted | Tag changed | 200 + new body |
| Omitted | Equal or newer date | Resource unchanged since date | 304 |
| Omitted | Older date | Resource modified after date | 200 |
| **Matches** | Older date | Tag unchanged | **304** |
| **Mismatches** | Newer date | Tag changed | **200** |
| `*` | Any | Existing resource | 304 |
| Invalid value | Valid date | Depends on HTTP parsing | Do not default to 304; verify actual behavior |

The last row reminds us that production code should not "auto-fix" malformed headers or treat an invalid ETag as a match; rely on compliant implementations and test actual responses.

## 7. Does 304 Not Modified Have a Body or Content-Length?

**304 has no message content**. Therefore, an API must never send a JSON DTO, the text `null`, or file bytes with status 304. Differences:

| Status | Meaning | Body |
| --- | --- | --- |
| 200 OK | Returns current representation | Can contain JSON/file/etc. |
| 204 No Content | Request succeeded, no response content | No body |
| 304 Not Modified | Conditional GET/HEAD confirms cache may use stored representation | No new body |
| 404 Not Found | Resource does not exist or existence is concealed | May contain error body |
| 412 Precondition Failed | Operation's precondition was not met | May contain error body |

A 304 response should carry metadata pertaining to the cached representation per HTTP rules, specifically:
- `Date` when appropriate;
- `ETag` and/or `Last-Modified` if applicable;
- `Cache-Control`, `Expires`, `Vary`, `Content-Location` if sent in the corresponding 200 response and needing update.

**A commonly misstated point:** RFC 9110 permits `Content-Length` on a 304 response **only if** that value equals the exact content length that would have been sent in a corresponding 200 response. Thus, do not write a test asserting "304 must never have a Content-Length header"; verify instead that the **actual body is empty** and metadata is accurate.

Upon receiving 304, the browser/cache reconstructs the application response from its cached body and updates metadata. In DevTools, you might see `200 (from disk cache)` or varied UI labels despite a 304 revalidation over the network; inspect the exact request/response in the Network panel.

## 8. `Cache-Control`: Deciding When to Revalidate

`ETag`/`Last-Modified` are **validators**; `Cache-Control` typically determines whether a response may be stored, reused, and when it must be revalidated.

| Directive | Practical meaning |
| --- | --- |
| `max-age=300` | Response may be treated as fresh for up to 300 seconds per caching rules |
| `private` | Allows private caching; prohibits shared caches from storing per directive |
| `public` | Allows shared caches to store under appropriate conditions |
| `no-cache` | **May be stored**, but must revalidate before reuse |
| `no-store` | Do not store the response per this directive; use for sensitive data needing strict policy |
| `must-revalidate` | Once stale, caches must not reuse without validating per rules |
| `immutable` | Hints the representation will not change while fresh, suited for versioned URLs |

**`no-cache` does not mean `no-store`.** This is a crucial distinction: `no-cache` means "can store, but revalidate before use," whereas `no-store` means "do not store."

Spring example:

~~~java
CacheControl cc = CacheControl.maxAge(Duration.ofMinutes(5))
        .cachePrivate();
~~~

The snippet above is an illustrative Java expression importing `org.springframework.http.CacheControl` and `java.time.Duration`. It builds a policy suitable when an **individual user** may cache for around five minutes. For highly sensitive data like secrets/tokens, `CacheControl.noStore()` is usually preferable.

Even with an ETag, while the client still considers its cached response fresh, **it does not need to send a revalidation GET**; not seeing a 304 does not mean caching isn't working.

## 9. Spring MVC Automatically Checks Conditional Headers on ResponseEntity

Spring MVC 6.x supports combining `ResponseEntity` with `ETag`, `Last-Modified`, and `Cache-Control`:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<Book> getBook(@PathVariable long id) {
    Book book = service.findById(id);
    if (book == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok()
            .eTag(book.etag())
            .lastModified(book.lastModified())
            .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                    .cachePrivate())
            .body(book);
}
~~~

**This is an abbreviated controller snippet**, not standalone: it requires `service` and a `Book` DTO with `etag()` and `lastModified()` methods. Spring MVC checks conditional request headers against the validators supplied on `ResponseEntity` and automatically responds with 304 when applicable.

With this response:
- Client sends normal GET → 200 + JSON + `ETag` + `Last-Modified` + `Cache-Control`.
- Client sends `If-None-Match` matching current ETag → 304 and **skips JSON body serialization**.
- Client sends `If-Modified-Since` equal to or newer than `lastModified`, with no `If-None-Match` → 304.
- If the validator changed → 200 + new body.

**Performance note:** in the example, `service.findById(id)` runs **before** Spring processes `ResponseEntity`, so 304 saves serialization and bandwidth but not necessarily the DB lookup. When cheap version/`lastModified` metadata is available, proactively check before building heavy payloads via `WebRequest.checkNotModified`.

### 9.1. How Spring Normalizes ETags

`ResponseEntity.BodyBuilder.eTag(String)` sets the entity tag header (unquoted strings may be quoted automatically by the API). To avoid ambiguity, this lesson's examples pass pre-quoted standard ETags such as `"\"book-7-v3\""`.

Never construct `ETag` from untrusted request input, never format `W/` improperly, and never share one tag across non-equivalent representations.

## 10. Spring MVC `WebRequest.checkNotModified`: Short-Circuiting in the Controller

Spring MVC provides `WebRequest.checkNotModified(...)`:

~~~java
@GetMapping("/reports/{id}")
public String showReport(
        @PathVariable long id,
        WebRequest request,
        Model model) {

    ReportMetadata info = reportService.findMetadata(id);
    if (info == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    if (request.checkNotModified(
            info.etag(), info.lastModified().toEpochMilli())) {
        return null;
    }

    ReportDto report = reportService.buildExpensiveReport(id);
    model.addAttribute("report", report);
    return "reports/detail";
}
~~~

**This is an illustrative method for an HTML `@Controller`**, not a standalone app; it needs `reportService`, `ReportMetadata`, `ReportDto`, and the `reports/detail` template. Required imports: `org.springframework.web.context.request.WebRequest`, `Model`, `HttpStatus`, `ResponseStatusException`, and MVC annotations.

Mechanism:

1. The server fetches **cheap metadata** (ETag/`lastModified`) from storage or a DB version column.
2. `checkNotModified(etag, lastModifiedMillis)` evaluates preconditions and sets status/validator headers when applicable.
3. If it returns **true**, conditions permit early exit: the controller returns `null` because the response is already handled (typically **304 for GET/HEAD**), skipping expensive DTO assembly or template rendering.
4. If **false**, continue building the model and rendering the new representation.

Spring provides overloads for ETag, `lastModified`, or both. For update methods, failed preconditions can lead to **412** instead of 304; do not blindly copy GET handlers onto PUT.

**Check authorization before short-circuiting**: for private data, returning 304 to an unauthorized caller can still disclose the existence or version of a resource.

## 11. Complete Spring Boot 3.x + Java 17 Example

The example exposes endpoints:

- `GET /api/books/7` → returns JSON with a fixed strong `ETag`, fixed `Last-Modified`, and 5-minute private `Cache-Control`.
- `GET /api/books/99` → returns 404; never turns a missing resource into 304.
- Tests unconditional GET, GET with matching/mismatching ETag, matching/older IMS, both headers combined, wildcard, HEAD, and empty 304 body.

Project built with Maven, **Java 17+**, Spring Boot **3.x**, dependencies **Spring Web** (`spring-boot-starter-web`) and **Spring Boot Starter Test** (`spring-boot-starter-test`). Package: `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/BookCacheController.java
src/test/java/com/example/demo/BookCacheControllerTest.java
~~~

### 11.1. `DemoApplication.java`

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

### 11.2. `BookCacheController.java`

~~~java
package com.example.demo;

import java.time.Duration;
import java.time.Instant;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookCacheController {

    // UTC; second-level precision to match HTTP-date.
    private static final Instant LAST_MODIFIED =
            Instant.parse("2025-01-15T10:30:00Z");

    // ETag already wrapped in double quotes per RFC 9110.
    private static final String ETAG = "\"book-7-v3\"";

    @GetMapping("/{id}")
    public ResponseEntity<Book> find(@PathVariable long id) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }

        Book book = new Book(7L, "HTTP caching", 3);

        return ResponseEntity.ok()
                .eTag(ETAG)
                .lastModified(LAST_MODIFIED)
                .cacheControl(CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePrivate())
                .body(book);
    }

    public record Book(long id, String title, int version) {}
}
~~~

**Why does the lab use fixed values?** So tests aren't affected by runtime clock or an external database. In production, `ETag` and `Last-Modified` must derive from real data/versions; do not hardcode `2025-01-15` and `v3` across resources or leave them unchanged when content updates.

A normal `GET /api/books/7` returns:

~~~json
{"id":7,"title":"HTTP caching","version":3}
~~~

with status 200, `ETag`, and `Last-Modified` headers as shown earlier. Exact JSON field order can depend on serializer/config; tests use `jsonPath` instead of raw string matching.

### 11.3. `BookCacheControllerTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookCacheController.class)
class BookCacheControllerTest {

    private static final String ETAG = "\"book-7-v3\"";
    private static final String LAST_MODIFIED =
            "Wed, 15 Jan 2025 10:30:00 GMT";

    @Autowired
    MockMvc mockMvc;

    @Test
    void firstGetReturnsRepresentationAndValidators() throws Exception {
        mockMvc.perform(get("/api/books/7"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(header().string(
                        HttpHeaders.LAST_MODIFIED, LAST_MODIFIED))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "max-age=300, private"))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void matchingEtagReturns304WithoutBody() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(content().string(""));
    }

    @Test
    void weakClientTagMatchesForIfNoneMatch() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH,
                                "W/\"book-7-v3\""))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void mismatchingEtagReturns200AndBody() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"book-7-v2\""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void unchangedLastModifiedReturns304() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                LAST_MODIFIED))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void olderIfModifiedSinceReturns200() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Tue, 14 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("HTTP caching"));
    }

    @Test
    void etagWinsEvenWhenIfModifiedSinceIsOld() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG)
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Tue, 14 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void differentEtagWinsOverNewerTimestamp() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "\"book-7-v2\"")
                        .header(HttpHeaders.IF_MODIFIED_SINCE,
                                "Thu, 16 Jan 2025 00:00:00 GMT"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void wildcardIsNotModifiedForExistingResource() throws Exception {
        mockMvc.perform(get("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, "*"))
                .andExpect(status().isNotModified());
    }

    @Test
    void missingResourceNeverBecomes304() throws Exception {
        mockMvc.perform(get("/api/books/99")
                        .header(HttpHeaders.IF_NONE_MATCH, "*"))
                .andExpect(status().isNotFound());
    }

    @Test
    void headWithMatchingEtagHasNoBody() throws Exception {
        mockMvc.perform(head("/api/books/7")
                        .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }
}
~~~

These tests are written for **Spring MVC 6.x with `@WebMvcTest`**. They verify:
- `200` returns JSON with `ETag`, timestamp, and `Cache-Control`;
- `304` contains no response content;
- `If-None-Match` takes precedence over `If-Modified-Since` in both conflicting directions;
- weak matching for `If-None-Match`;
- wildcard only applies when the resource exists;
- `HEAD` requests can also use validators without returning a body.

Run:

~~~bash
./mvnw test
~~~

On Windows use `mvnw.cmd test`; if there is no Maven wrapper and Maven is installed, run `mvn test`.

**MockMvc limitations:** it tests the MVC handler/controller/test slice, **not full browser caches, CDNs, gateways, or network compression**. End-to-end tests over a real HTTP port matter when the app sits behind a reverse proxy or changes content encoding, authorization, or personalization.

## 12. Testing Directly with curl

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

### 12.1. Receive 200 with Validators

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

Output includes **ETag: "book-7-v3"**, `Last-Modified: Wed, 15 Jan 2025 10:30:00 GMT`, `Cache-Control: max-age=300, private`, and the JSON body.

### 12.2. Send Matching ETag to Receive 304

~~~bash
curl -i   -H 'If-None-Match: "book-7-v3"'   http://localhost:8080/api/books/7
~~~

Expected status **304 Not Modified**, with no new body. The terminal still prints headers; do not mistake `curl -i` header output for a response body.

### 12.3. Stale ETag → Receive 200

~~~bash
curl -i   -H 'If-None-Match: "book-7-v2"'   http://localhost:8080/api/books/7
~~~

Expected status **200 OK** and the current JSON representation (version 3).

### 12.4. Using If-Modified-Since

~~~bash
curl -i   -H 'If-Modified-Since: Wed, 15 Jan 2025 10:30:00 GMT'   http://localhost:8080/api/books/7
~~~

Expected status **304**. With an older date like 14 January 2025, expected response is **200**.

### 12.5. Testing Precedence Between Two Validators

~~~bash
curl -i   -H 'If-None-Match: "book-7-v2"'   -H 'If-Modified-Since: Thu, 16 Jan 2025 00:00:00 GMT'   http://localhost:8080/api/books/7
~~~

Even though the client's timestamp is newer than the modification time, **the ETag does not match**, so `If-None-Match` takes precedence and GET returns `200` per standard semantics.

Commands using `\` follow line continuation for Linux/macOS/Git Bash. In Windows PowerShell, use `curl.exe` and appropriate quoting; `curl` may be an alias in some PowerShell environments.

**Important:** `curl` does not maintain a browser cache automatically. These examples explicitly attach conditional headers to test the origin server. A browser may send no request at all while cached entries remain fresh, so "I don't see 304" does not prove validators aren't working.

## 13. ShallowEtagHeaderFilter: Why Is It Not a CPU Optimization?

Spring MVC includes `org.springframework.web.filter.ShallowEtagHeaderFilter`, which computes an ETag from the **generated response content** and compares it against `If-None-Match`. This filter typically:
1. Lets the controller and view/serializer render the body.
2. Buffers/captures the response content.
3. Computes a content hash and compares ETags.
4. If matched, returns `304` and omits sending the body over the network.

Advantage: adds ETags to endpoints without manually managing versions in controllers.

**Major limitation:** the response must still be **generated** to hash it, so the filter mainly saves **bandwidth** and does **not** substantially reduce CPU, DB, or serialization work; for large responses it also incurs buffer memory overhead. Per Spring docs, the filter uses MD5 to compute shallow ETags, with a `writeWeakETag` option. Never treat the filter's MD5 as a security primitive for file signature verification.

Example filter registration in Spring Boot 3.x:

~~~java
@Configuration
public class EtagFilterConfig {

    @Bean
    public FilterRegistrationBean<ShallowEtagHeaderFilter> etagFilter() {
        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
                new FilterRegistrationBean<>(
                        new ShallowEtagHeaderFilter());

        registration.addUrlPatterns("/pages/*");
        registration.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC);
        registration.setOrder(10);
        return registration;
    }
}
~~~

**This is an additional illustrative class**, not part of the lab project in section 11. It requires imports for `@Configuration`, `@Bean`, `FilterRegistrationBean` from Spring Boot, `ShallowEtagHeaderFilter` from Spring Web, and `jakarta.servlet.DispatcherType`. When using the filter with async endpoints, registering `DispatcherType.ASYNC` allows the filter to run at the end of async dispatch per docs. Certain streaming scenarios must bypass content-caching wrappers; Spring provides `ShallowEtagHeaderFilter.disableContentCaching(request)` before writing output if needed.

**Do not enable the filter globally across all endpoints** when controllers already provide ETags, when responses are large/streaming, or when sensitive `no-store` data hasn't been audited for side effects. For APIs with DB versions and large payloads, checking validators early in the controller usually saves far more resources.

## 14. Static Resources, Files, and Versioned Assets

Static resources (CSS/JS/images) can be served by Spring MVC via `ResourceHttpRequestHandler`. Spring supports `Last-Modified` from resource metadata, `Cache-Control`, and resource chains / versioned URLs. With URLs like:

~~~text
/static/app.a1b2c3.js
~~~

if the hash is part of the **asset URL name** and the file is immutable, long cache TTLs work well; changing the file yields a new URL. This is an alternative to frequent revalidation on every request.

For user-uploaded files, download APIs can choose ETags from object-storage versions or reliable hashes/metadata. However:
- `Content-Type`, `Content-Encoding`, `Content-Disposition`, and response variants must remain consistent.
- Verify access permissions **before** revealing whether a resource has changed.
- For private documents, keep them out of CDNs/shared caches unless proper authorization-aware caching exists.
- When supporting HTTP `Range`, `If-Range` has its own semantics and usually requires a strong validator; do not conflate `If-Range` with `If-None-Match`.

## 15. ETag/Last-Modified vs. @Cacheable (Spring Cache)

Two distinct caching mechanisms:

| Concept | HTTP conditional cache | Spring `@Cacheable` |
| --- | --- | --- |
| Where cached | Browser, proxy/CDN, HTTP client | Server-side cache abstraction (in-memory, Redis, etc.) |
| Check mechanism | `ETag`, `Last-Modified`, request validators, `304` | Application-defined cache keys, hits/misses/eviction |
| 304 | Yes, when clients revalidate GET/HEAD | `@Cacheable` itself never returns `304` |
| Cache TTL | `Cache-Control` and HTTP semantics | Cache provider/TTL configuration |
| Goal | Reduce HTTP representation transfer | Reduce server computation, DB, or service calls |
| Access control | Requires HTTP cache/privacy/authorization rules | Cache key must include permission/user dimensions |

An endpoint can use **both**: the service reads data from `@Cacheable` on the server, and the controller emits an `ETag` for browser revalidation. They do not replace one another; a server cache with wrong tenant/user keys can leak data even when HTTP headers look right.

## 16. Private Data, Vary, and Multiple Representations

### 16.1. Personal Data and Shared Caches

An API response tied to a session cookie and personal data must never casually set:

~~~http
Cache-Control: public, max-age=86400
~~~

That is an example **never to apply to private data** if a shared cache/CDN could serve across users. Usually you need `private` with an appropriate TTL, or `no-store` for highly sensitive data. **304 having no body does not eliminate data leak risks**: a previously cached body can still be served if cache keys or authorization are wrong.

### 16.2. The Vary Header for Representation Variants

If an API serves localized content:

~~~http
Vary: Accept-Language
ETag: "book-7-vi-v3"
~~~

The English version can carry a different tag:

~~~http
Vary: Accept-Language
ETag: "book-7-en-v3"
~~~

With differing gzip/br or JSON/XML variants, account for `Accept-Encoding`, `Accept`, and corresponding representation variants. `Vary` instructs caches to include those request headers in the matching key; it does not replace access control. Caches must select the right representation variant before comparing validators.

Sharing one ETag across responses with different bytes can cause wrong 304s. For strong tags, never assign the same strong tag to different byte sequences after content coding when they are treated as distinct selected representations.

### 16.3. CORS and ETag in the Frontend

In CORS, `ETag` is not in the default list of response headers readable by JavaScript. If a cross-origin frontend needs to read `ETag` to store/revalidate manually, the server may need:

~~~http
Access-Control-Expose-Headers: ETag
~~~

Being allowed to read `ETag` does not imply authorization to read the response body or private data. You still need proper `Access-Control-Allow-Origin`, credentials, and authorization; an ETag is not an access token.

When the browser manages the HTTP cache natively, JavaScript may not need to read `ETag` manually. Do not manually attach `If-None-Match` to every request without understanding cache semantics, Fetch CORS, and validators.

## 17. Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Always 200, never 304 | Client omits conditional headers or cache is still fresh | Inspect Network request headers, test with `curl` + `If-None-Match` |
| Always 200 even though ETag "looks" identical | Quote mismatch, weak tag, variant mismatch, or changing content | Compare raw headers and check tag generation logic |
| Always 304 even when content changed | Version/`Last-Modified` not incremented on representation change | Fix validator strategy and update metadata atomically |
| 304 appears yet UI still shows JSON | Browser/cache reuses stored 200 body | This is the expected behavior of revalidation |
| Code sends body with 304 | Manually setting status 304 while still serializing DTO | Use framework conditional handling; never write a 304 body |
| Combined conditions produce wrong status | Evaluating IMS despite INM present, or using AND | Give `If-None-Match` precedence per RFC 9110 |
| Wrong timestamp comparison | Milliseconds vs. HTTP seconds, timezone, ISO strings | Use HTTP-date GMT, UTC, and one-second granularity |
| Private data cached at CDN | Using `public`/max-age or cache key ignoring user | Use `private`/`no-store` and configure shared caches properly |
| ETag leaks across tenants | Tag and cache key fail to reflect permissions/representation | Design validators/authorization per selected representation |
| Shallow filter doesn't reduce CPU | Filter still renders before hashing | Check version metadata early in the controller |
| Broken Range/downloads with weak ETag | Confusing `If-Range` with `If-None-Match` | Use strong validators for byte ranges when appropriate |
| JavaScript cannot read ETag header | CORS does not expose `ETag` | Add `Access-Control-Expose-Headers: ETag` and proper policy |
| Future Last-Modified header | Clock skew or wrong metadata | Sync metadata/clocks and avoid future timestamps |
| Tests find non-empty 304 body | Returning `ResponseEntity.status(304).body(...)` manually | Use `ResponseEntity` validator APIs or `checkNotModified` |

## 18. Quiz Questions

**1. When both `If-None-Match` and `If-Modified-Since` are present, which one takes precedence?**

`If-None-Match`. The server must ignore `If-Modified-Since` whenever `If-None-Match` is present.

**2. Current ETag is `"v4"`, and the client sends `If-None-Match: "v3"` with a future modification date. What does GET return?**

Normally **200 with the current body** because the ETag mismatches; never return 304 based on a future IMS date.

**3. What does `If-None-Match: *` do on a GET for an existing resource?**

The condition evaluates false because a current representation exists, so GET/HEAD can return **304** per HTTP precondition semantics.

**4. If `If-None-Match` fails on a PUT, should the server return 304?**

No. When a precondition is evaluated and fails on unsafe methods, the server must normally return **412 Precondition Failed**.

**5. Does a 304 response include a JSON body?**

No. `304` has no message content. The cache reuses the stored representation and updates relevant metadata.

**6. Does `no-cache` mean "never store data at all"?**

No. It permits storage but requires revalidation before reuse. `no-store` is what instructs caches not to store.

**7. Why doesn't `ShallowEtagHeaderFilter` necessarily make DB/CPU faster?**

Because the filter still needs the response body to be generated in order to hash it; its benefit is primarily bandwidth, not skipping body computation.

**8. Should user authentication run before returning 304?**

Yes, for private resources. Even without a body, 304 pertains to the resource and cached body/metadata; authorization must apply consistently.

## 19. Production Deployment Checklist

1. Identify the selected representation for every URL (language, encoding, user permissions, version).
2. Generate stable ETags that change whenever the representation actually changes; use strong/weak with proper semantics.
3. Supply `Last-Modified` from real metadata with appropriate precision, never arbitrary `Instant.now()`.
4. Combine `Cache-Control` per storage/freshness policy: `private`, `no-store`, and suitable TTLs.
5. In Spring MVC, prefer `ResponseEntity.eTag/lastModified/cacheControl`; use `WebRequest.checkNotModified` to short-circuit expensive work when metadata is cheap.
6. Ensure **If-None-Match takes precedence over If-Modified-Since** and handle `If-None-Match: *` properly.
7. Never send a body with 304; do not falsely assert that 304 can never carry a `Content-Length` header.
8. For private resources, check authorization before evaluating validators; never put personal data in shared caches.
9. Test 200, 304, 404, matching/mismatching ETags, equal/older IMS, and both conditions together; test HEAD if supported.
10. With CDNs/proxies, verify `Vary`, compression, ETag rewriting, caching policy, and responses at each layer.
11. Never enable `ShallowEtagHeaderFilter` on streaming or large-file responses without accounting for buffering cost.
12. Distinguish browser cache, `@Cacheable`, and application state; never call a 304 a "server cache hit" if representation building still ran.

## Official Sources

- [Spring Framework 6.2 — HTTP Caching (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html)
- [Spring Framework 6.2 — Filters / Shallow ETag](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.2 — WebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/WebRequest.html)
- [Spring Framework 6.2 — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/CacheControl.html)
- [RFC 9110 — HTTP Semantics, Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [MDN — Conditional Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests)
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304)
