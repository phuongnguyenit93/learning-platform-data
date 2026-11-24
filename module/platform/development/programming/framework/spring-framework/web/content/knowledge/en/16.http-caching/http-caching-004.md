# Spring MVC — WebRequest.checkNotModified and ResponseEntity Cache Configuration

## 1. Objectives

A news page, document, avatar image, or JSON endpoint is often requested repeatedly even when its content has not changed. If the server sends the entire response body every time, the system wastes bandwidth, transfer time, and serialization effort. HTTP caching offers two complementary mechanisms:

1. **Freshness caching:** the server sends `Cache-Control` so browsers/proxies know how long a response can be reused without contacting the server.
2. **Conditional request / revalidation:** the client sends a previously received validator such as `If-None-Match` or `If-Modified-Since`; if the representation has not changed, the server returns **304 Not Modified**, usually without a response body.

Spring MVC supports both through two main approaches:

- `WebRequest.checkNotModified(...)`: the controller **proactively checks conditions early**, able to stop before expensive view/body creation.
- `ResponseEntity`: the controller configures `Cache-Control`, `ETag`, and `Last-Modified` on the builder; Spring MVC **automatically handles conditional GET/HEAD** using the response validators.

Lesson objectives:

- Understand `ETag`, `Last-Modified`, `If-None-Match`, `If-Modified-Since`, `If-Match`, `If-Unmodified-Since`, and status codes **200/304/412**.
- Distinguish `Cache-Control: no-cache` from `no-store`, `private` from `public`, and `max-age` from revalidation.
- Properly use the three overloads `checkNotModified(long)`, `checkNotModified(String)`, and `checkNotModified(String,long)`.
- Build `ResponseEntity.ok().cacheControl(...).eTag(...).lastModified(...).body(...)` and know when Spring MVC converts the response to 304.
- Know the performance optimization boundary: checking metadata early before rendering a view vs. building the DTO/body first and letting the framework check afterward.
- Avoid bugs such as caching user data, wrong ETags when representations vary, missing `Vary` headers, unstable timestamps, and returning a body in 304.
- Run a Maven/Java 17/Spring Boot 3.5.0 example with both an HTML view and REST JSON, plus MockMvc tests covering conditional requests.

**Scope:** Spring Framework 6.2, **Spring MVC Servlet stack**. This lesson demonstrates HTTP caching; production deployments must consider proxies/CDNs, authentication, per-representation ETags, and sensitive-data cache policies.

## 2. HTTP Cache Is a Protocol, Not a Java Map

HTTP caching is not the same as Spring Cache `@Cacheable`.

| Mechanism | Who holds the content? | What is optimized? | Examples |
| --- | --- | --- | --- |
| HTTP browser cache | Browser or client-side HTTP cache | Bandwidth, reload latency | `Cache-Control`, `ETag` |
| Shared HTTP cache | CDN, gateway, or reverse proxy | Reduce requests hitting origin | `public, max-age, s-maxage` |
| Spring Cache `@Cacheable` | Application/cache provider (Caffeine, Redis...) | Avoid repeated service computation/queries | `@Cacheable("articles")` |
| Database query optimization | DB engine | Query latency/load | Indexes, execution plans |

An endpoint can use both Spring Cache and HTTP Cache, but **their lifecycles are independent**. `@Cacheable` does not emit `ETag`, and `ResponseEntity.cacheControl(...)` does not store a Java object in Redis.

### 2.1. HTTP Caching Has Two Phases

~~~text
GET /api/articles/42
  -> HTTP 200 OK
     Cache-Control: private, no-cache
     ETag: "article-42-v7"
     Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
     Body: {"id":42,"title":"HTTP caching","version":7}

Client stores representation + validators.

Subsequent GET:
  GET /api/articles/42
  If-None-Match: "article-42-v7"

If content has not changed:
  <- HTTP 304 Not Modified
     ETag: "article-42-v7"
     (does not resend representation body)

Browser reuses stored representation.
~~~

In the example, `no-cache` still **permits storage**, but requires checking with the server before reuse. Thus the `no-cache + ETag` pair is ideal for practicing conditional requests.

If the server sends `Cache-Control: max-age=300` for a cacheable response, the client may use the fresh representation within the freshness window per HTTP rules without **necessarily contacting the server**. To observe 304 in a browser, wait until stale, trigger revalidation, or send conditional headers explicitly.

## 3. Role of Cache-Control in Response Configuration

**Cache-Control** governs **storage, freshness, and reuse** of a response; `ETag` and `Last-Modified` only tell how to **revalidate** a stored representation. These are two distinct questions: a response with an ETag is not automatically cacheable, and a still-fresh response can be reused without sending a conditional GET.

Choose your policy before writing the controller: public data can use `max-age`; private data suits a private cache only if sensitivity allows; confidential responses should usually use `no-store`. **`no-cache`** still permits storage while forcing revalidation before reuse, completely distinct from **`no-store`**. **`private`** does not replace authentication/authorization or CDN cache-key rules.

When an endpoint returns variants by header/locale/user, verify `Vary`, access permissions, and per-representation ETags. Never set `public` just for speed; caching policies for personal data must be tested explicitly.

### 3.1. Spring CacheControl API

Spring provides `org.springframework.http.CacheControl`:

~~~java
CacheControl.noCache();                            // no-cache
CacheControl.noStore();                            // no-store
CacheControl.noCache().cachePrivate();             // no-cache, private
CacheControl.maxAge(Duration.ofMinutes(5));        // max-age=300
CacheControl.maxAge(Duration.ofHours(1))
        .cachePublic().mustRevalidate();           // max-age=3600, must-revalidate, public
~~~

Import `java.time.Duration`. Actual directive order may vary; test semantics rather than relying on exact string ordering unnecessarily. `CacheControl#cachePrivate()` and `#cachePublic()` express **HTTP semantics**, not user permission checks.

## 4. ETag: Stable Validator for the Selected Representation

An `ETag` is a server-issued identifier for a representation version, e.g., **"article-42-v7"**. Strong tags and weak tags (`W/` prefix) have different comparison semantics: `If-None-Match` for GET/HEAD uses weak comparison, whereas `If-Match` for updates requires strong comparison. An ETag **is not an authentication token** and does not verify read permissions.

In `ResponseEntity`, an ETag can come from a DB version or payload hash as long as every meaningful change to the representation updates the validator. If the same URL serves JSON in different languages/encodings, sharing a single strong ETag may be wrong; design variants with proper `Vary`. Hashing the full body per request can cost CPU; when version metadata exists, section 6 shows how to short-circuit early with `WebRequest.checkNotModified`.

### 4.2. Never Use the Current Timestamp as an ETag

Wrong:

~~~java
String etag = "\"" + System.currentTimeMillis() + "\"";
~~~

Every request generates a new ETag → the client can never successfully revalidate even when content is unchanged. Use a version, hash, or metadata **stable until content actually changes**.

Similarly, if the ETag is based solely on an ID while the body updates, clients may retain stale versions because the ETag never changes. Validators must reflect the representation version, not just resource identity.

### 4.3. If-None-Match and Condition Precedence

If a client sends:

~~~http
If-None-Match: "article-42-v7"
If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT
~~~

HTTP semantics dictate that `If-None-Match` takes precedence for deciding not-modified; never treat `If-Modified-Since` as an independent **OR** condition when the ETag does not match.

Other usages:

~~~http
If-None-Match: *
~~~

typically means the request requires no current representation to exist, useful for conditional create/update APIs per their semantics. Never treat `*` as a regular tag.

Compare with `If-Match`: that header serves optimistic concurrency, requiring standard strong validator matching for resource updates—a different goal from `If-None-Match`'s "lighter re-GET."

## 5. Last-Modified and If-Modified-Since

The server can emit:

~~~http
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
~~~

Next time, the client sends:

~~~http
If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT
~~~

If the representation has not been modified after that timestamp, the server can return 304. `Last-Modified` is the update time **of the representation/resource**, not when the server received the request.

### 5.1. Precision and Timestamp Limitations

HTTP-dates have **one-second** resolution. Java `Instant` holds nanoseconds, and DB `updated_at` may hold milli/nanoseconds. If a resource is edited **twice within the same second**, `Last-Modified` alone may fail to distinguish the two versions the way `ETag` does.

Recommendations:

- Use a real stored timestamp, never `Instant.now()` on every GET.
- Prefer a stable `ETag` when finer versioning precision is needed.
- You can send **both ETag and Last-Modified**; when both conditional headers are present, `ETag` takes proper precedence per spec.
- Never emit arbitrary future timestamps; clock skew can disrupt caching.
- Only send the `Last-Modified` of the represented content, not application startup time shared across all resources.

### 5.2. Last-Modified in Java Spring

`ResponseEntity.HeadersBuilder` supports:

~~~java
.lastModified(instant)
.lastModified(zonedDateTime)
.lastModified(epochMillis)
~~~

Here `instant` is `java.time.Instant` and `epochMillis` is `long` milliseconds since the Unix epoch. Prefer `Instant`/`ZonedDateTime` to avoid confusing seconds with milliseconds.

With `WebRequest.checkNotModified(long)`, the parameter **is in millis**, for example:

~~~java
long lastModifiedMillis = article.updatedAt().toEpochMilli();
if (webRequest.checkNotModified(lastModifiedMillis)) {
    return null;
}
~~~

This is an MVC view handler fragment; the complete runnable example is in section 10.

## 6. WebRequest.checkNotModified: Early Condition Check

Import:

~~~java
import org.springframework.web.context.request.WebRequest;
~~~

Three main overloads:

| Method | Validator checked | Usage |
| --- | --- | --- |
| `checkNotModified(long lastModifiedTimestamp)` | `Last-Modified` | When a reliable timestamp exists |
| `checkNotModified(String eTag)` | `ETag` | When an appropriate validator exists |
| `checkNotModified(String eTag, long lastModifiedTimestamp)` | Both `ETag` and `Last-Modified` | When publishing both validators |

Return value:

- **`true`:** the request needs no further content processing under current conditions; for matching GET/HEAD, Spring prepares a **304 Not Modified** response, while for unsafe methods/conditions it may prepare **412 Precondition Failed**.
- **`false`:** the request must be processed normally. You can prepare the model/view or continue application logic.

`WebRequest.checkNotModified(...)` also sets `ETag`/`Last-Modified` headers and the HTTP status on the servlet response in MVC. You do not need to write manual ETag string comparisons for normal conditional GETs.

### 6.1. View Handler Example

~~~java
@GetMapping("/articles/{id}/page")
public String articlePage(
        @PathVariable long id,
        WebRequest request,
        Model model) {

    Article article = store.find(id);
    if (request.checkNotModified(
            article.etag(), article.updatedAt().toEpochMilli())) {
        return null; // MVC handled the conditional request result.
    }

    model.addAttribute("article", article);
    return "article-detail";
}
~~~

This is a fragment inside a `@Controller` with a suitable view template and model/service. If unchanged, Spring skips building the model / rendering the view and returns 304. The 200 path still renders HTML normally.

**Benefit:** when you only need lightweight metadata from the DB to get version/timestamp, you can check early and **skip querying the full object graph or rendering the view/JSON body** if the client already has the representation. In this fragment, `store.find(id)` loads the whole article; maximum optimization comes when production separates a lightweight metadata query from the heavy content query.

### 6.2. Do Not Use WebRequest to Replace Business Preconditions

`checkNotModified` works with HTTP conditional headers per Spring's contract, **and does not automatically guarantee database optimistic locking**. For PUT/PATCH/DELETE, you still must verify permissions, entity version, and execute mutations atomically in a transaction to avoid races.

If the controller reads the version, checks `If-Match`, and another request updates the DB before your write, the earlier HTTP check does not prevent a race. Check the version right inside the SQL update or via optimistic locking (e.g., JPA `@Version`) and map conflicts properly.

### 6.3. GET, HEAD, and Unsafe Methods

- GET/HEAD with matching `If-None-Match` → normally 304, **with no response representation body**.
- PUT/POST/DELETE with a failed precondition → may be 412. Never turn 304 into an update outcome.
- `If-Match` is normally used with **strong comparison** for optimistic concurrency.
- `If-Unmodified-Since` is a timestamp-based precondition; weaker than a strong ETag when two edits happen in the same second.
- `304` does not mean the resource was updated; it only tells the client it may reuse its stored representation.

## 7. ResponseEntity: Cache Headers and Automatic Conditional Handling

In a REST controller returning `ResponseEntity<T>`, Spring provides a convenient builder:

~~~java
@GetMapping("/api/articles/{id}")
public ResponseEntity<ArticleDto> article(@PathVariable long id) {
    Article article = store.find(id);
    ArticleDto dto = new ArticleDto(
            article.id(), article.title(), article.body(), article.version());

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noCache().cachePrivate())
            .eTag(article.etag())
            .lastModified(article.updatedAt())
            .body(dto);
}
~~~

In Spring MVC 6.2, returning a `ResponseEntity` with `ETag`/`Last-Modified` enables the framework to **handle conditional responses** for GET/HEAD: when validators match, the client receives 304 without a body; you do not need to write:

~~~java
if (request.getHeader("If-None-Match").equals(etag)) {
    return ResponseEntity.status(304).build();
}
~~~

That manual anti-pattern lacks handling for weak/strong tags, validator lists, wildcards, precedence, and malformed headers. Rely on Spring's API and HTTP semantics.

**Optimization limit:** with `ResponseEntity` as above, the controller **has already executed `store.find` and built `dto` before the framework decides to send 304**. It still saves **serialization and network body transfer**, though not necessarily all queries/computation to build the DTO. When the body is very expensive, use `WebRequest.checkNotModified` early in the handler or query metadata first.

### 7.1. Builder Methods

| Builder | HTTP Header | Notes |
| --- | --- | --- |
| `.cacheControl(CacheControl.noCache())` | `Cache-Control: no-cache` | Cache must revalidate |
| `.cacheControl(CacheControl.noStore())` | `Cache-Control: no-store` | Must not store a copy |
| `.cacheControl(CacheControl.maxAge(Duration.ofMinutes(5)))` | `Cache-Control: max-age=300` | Permits freshness |
| `.eTag("article-42-v7")` | `ETag: "article-42-v7"` | Spring adds quotes automatically |
| `.eTag("W/\"article-v7\"")` | `ETag: W/"article-v7"` | Weak validator syntax |
| `.lastModified(Instant)` | `Last-Modified: <HTTP-date>` | Actual modification timestamp |
| `.varyBy(HttpHeaders.ACCEPT_LANGUAGE)` | `Vary: Accept-Language` | When response depends on language |
| `.body(dto)` | Serialized JSON representation | Not necessarily sent if 304 triggers |
| `.build()` | Bodyless ResponseEntity | E.g., `noContent()` or `notFound()` |

If the response also varies by `Accept-Encoding`, `Accept-Language`, `Origin`, or other request headers, make sure **`Vary` and validators match the representation**. Never add `Vary` arbitrarily if the response doesn't depend on that header; doing so multiplies cache variants unnecessarily.

### 7.2. When to Check WebRequest Proactively Instead of Only Using ResponseEntity?

Choose plain `ResponseEntity` when:

- Building the DTO is cheap or data is already loaded.
- You prefer concise code with cache policy right on the API response.
- Saving payload/serialization bandwidth is the primary benefit.

Choose early `WebRequest.checkNotModified` when:

- Version/`lastModified` metadata can be queried much more cheaply than full content.
- Rendering the view or preparing the representation is resource-intensive.
- You need to check conditions before calling a heavy service and your data design supports it.

**Avoid redundant double-checking:** if you use `WebRequest.checkNotModified` which already handles 304, do not layer manual ETag checks on top while leaving MVC auto-conditional handling active unpredictably. Pick one clear flow and test all response headers.

## 8. 304 Not Modified: Bodyless Response

Example request:

~~~http
GET /api/articles/42 HTTP/1.1
If-None-Match: "article-42-v7"
~~~

If the current ETag matches:

~~~http
HTTP/1.1 304 Not Modified
ETag: "article-42-v7"
Cache-Control: private, no-cache
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
~~~

**There is no JSON body** like `{"message":"not modified"}` in 304. The client must already hold a stored representation to reuse; 304 simply signals that the stored representation can be reused per cache semantics.

Never convert 304 into a 200 with an empty body. Likewise, never let a REST client try to parse JSON from a 304 as if every success were 200:

~~~javascript
const response = await fetch("/api/articles/42", {
  headers: {"If-None-Match": '"article-42-v7"'}
});

if (response.status === 304) {
  // Use the representation the client stored in its application cache.
} else if (response.ok) {
  const article = await response.json();
}
~~~

With a browser-managed HTTP cache, the browser handles revalidation internally and presents a suitable response to scripts; the JavaScript snippet above illustrates **client-managed validator tracking**, not a requirement for every browser cache implementation.

### 8.1. Headers on 304

A 304 should maintain relevant cache metadata such as `ETag`, `Last-Modified`, `Cache-Control`, and `Vary` per HTTP semantics and actual configuration. If the 304 omits the 200's cache policy or alters `Vary` inconsistently, shared caches/clients may behave unexpectedly.

Spring MVC populates these headers when validators are set, though custom filters, proxies, and manual conditional handling must be tested. Never attach `Content-Type: application/json` and attempt to write a JSON body into a 304.

### 8.2. 304 Is Not Just an HTTP Status

304 does not tell the server which payload the client holds. It relies on validators of the **selected representation** for the exact resource URL (and `Vary` variant). If you change format, language, or view permissions while keeping the old ETag, clients may reuse an inappropriate representation.

### 8.3. HEAD

`HEAD` matches `GET` retrieval semantics without sending a body. Cache validators apply as well. Test `HEAD` if your API supports it, and do not assume custom streaming/filters behave properly without verification.

## 9. Choosing Cache Policy by Sensitivity

| Endpoint | Suggested example policy | Rationale |
| --- | --- | --- |
| JS/CSS files with content-hash in URL | `public, max-age=31536000, immutable` | URL changes whenever bytes change |
| Rarely changing public catalog | `public, max-age=60` + ETag | CDN/clients may cache briefly |
| Frequently updated public article | `public, no-cache` + ETag | Allows storage, always revalidates |
| Personal dashboard | `private, no-cache` if policy allows storing | Prevents shared caches from holding per-user content |
| Sensitive response with tokens/secrets | `no-store` | Minimizes response storage risk |
| Event streams, certain mutation statuses | Evaluate separately; usually not cached like GET resources | Different HTTP semantics |
| Resource creation POST result | Typically not shared-cached by default; return 201 + Location | Client can GET resource afterward |

These are **design suggestions**, not rigid rules. For private data, some security policies mandate `no-store` instead of `private, no-cache`. `private` does not protect against XSS, unauthorized access to the client machine, or local browser exposure.

### 9.1. Caching Content with Authorization or Cookies

If a GET depends on user/session:

- Never mark it `public` just because the URL string looks the same for all users.
- Use `private` so shared caches do not store it, or `no-store` if clients must not retain data.
- The server must still enforce authentication/authorization on every request reaching the backend; 304 is never a permission bypass.
- If representations differ by language/encoding, use `Vary` and per-variant validators. **Do not treat `Vary: Cookie` as a complete security solution** — explicit cache policies and authorization come first.
- Ensure that on logout or account switch, cached data is not inappropriately presented against policy.

### 9.2. CDNs and Shared Caches

When a CDN is present, inspect `s-maxage`, `public/private`, proxy cache keys, `Vary`, authentication headers, and invalidation. A reverse proxy can serve GETs without hitting your Spring controller while entries remain fresh. That is why backend logs won't necessarily record every page load.

## 10. Runnable Project: WebRequest + ResponseEntity

This Spring Boot 3.5.0 / Java 17 project uses **an article at version 7** with a fixed timestamp `2026-01-01T10:00:00Z` to demonstrate stable validators. Endpoints:

- `GET /articles/42/page` returns HTML via Thymeleaf and checks early using `WebRequest.checkNotModified(...)`.
- `GET /api/articles/42` returns JSON via `ResponseEntity` with `Cache-Control`/`ETag`/`Last-Modified` and lets Spring MVC handle conditional GETs.
- `GET /api/private-example` demonstrates `CacheControl.noStore()` (containing no real sensitive data).

The app has no database and no authentication. It is a deterministic demo distinguishing 200 vs. 304, not a production template for user-data caching.

### 10.1. Structure

~~~text
http-cache-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/HttpCacheApplication.java
    │   └── resources/templates/article-detail.html
    └── test/java/demo/HttpCacheTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>http-cache-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 10.3. HttpCacheApplication.java

All Java code below resides in **a single file** `src/main/java/demo/HttpCacheApplication.java`. Only the startup class `HttpCacheApplication` is a public top-level class; the records and controllers are package-private.

~~~java
package demo;

import java.time.Instant;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Service;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}

record Article(
        long id,
        String title,
        String body,
        long version,
        Instant updatedAt) {

    String etag() {
        // Stable version: only changes when the selected representation changes.
        return "article-" + id + "-v" + version;
    }
}

record ArticleDto(
        long id,
        String title,
        String body,
        long version) {
}

@Service
class ArticleStore {
    private final Article article = new Article(
            42L,
            "HTTP caching",
            "ETag giúp kiểm tra representation có thay đổi hay chưa.",
            7L,
            Instant.parse("2026-01-01T10:00:00Z"));

    Article find(long id) {
        if (id != article.id()) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Article not found");
        }
        return article;
    }
}

@Controller
class ArticlePageController {
    private final ArticleStore store;

    ArticlePageController(ArticleStore store) {
        this.store = store;
    }

    @GetMapping("/articles/{id}/page")
    String page(
            @PathVariable long id,
            WebRequest request,
            Model model,
            HttpServletResponse response) {

        Article article = store.find(id);

        // Set cache policy before possibly terminating with 304.
        response.setHeader(
                HttpHeaders.CACHE_CONTROL, "private, no-cache");

        // WebRequest automatically checks conditional headers and sets status.
        if (request.checkNotModified(
                article.etag(),
                article.updatedAt().toEpochMilli())) {
            return null; // Skip template rendering when validator matches.
        }

        model.addAttribute("article", article);
        return "article-detail";
    }
}

@RestController
class ArticleRestController {
    private final ArticleStore store;

    ArticleRestController(ArticleStore store) {
        this.store = store;
    }

    @GetMapping("/api/articles/{id}")
    ResponseEntity<ArticleDto> getArticle(@PathVariable long id) {
        Article article = store.find(id);

        ArticleDto dto = new ArticleDto(
                article.id(),
                article.title(),
                article.body(),
                article.version());

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache().cachePrivate())
                .eTag(article.etag())
                .lastModified(article.updatedAt())
                .body(dto);
    }

    @GetMapping("/api/private-example")
    ResponseEntity<Map<String, String>> privateExample() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of("message", "Demo no-store"));
    }
}
~~~

**Why this example is focused:**

- The ETag value `article-42-v7` is normalized by Spring into HTTP header `ETag: "article-42-v7"`.
- The fixed timestamp is formatted by Spring as an HTTP-date rather than calling `Instant.now()` per request.
- The view controller checks before rendering; the HTML template **does not execute** if the request qualifies for 304.
- The REST controller returns a `ResponseEntity` carrying both validators and cache policy. Spring MVC checks conditions when processing the response, so the client receives a bodyless 304 even though the controller constructed the DTO.
- `private, no-cache` illustrates browser/private-cache storage with revalidation; do not use it for secrets requiring `no-store`.
- There is no update endpoint for the article, so validators stay constant throughout execution. Production must update version/timestamp **atomically** when representations change.

### 10.4. article-detail.html

Save to `src/main/resources/templates/article-detail.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Article Detail</title>
</head>
<body>
    <h1 th:text="${article.title}">Article title</h1>
    <p th:text="${article.body}">Article content</p>
    <small>
        Version:
        <span th:text="${article.version}">0</span>
    </small>
</body>
</html>
~~~

Thymeleaf `th:text` HTML-escapes content; avoid `th:utext` with unsanitized input. This HTML view uses dummy public data only. Cache policies for real per-user pages must be reviewed before deployment.

### 10.5. Running the Application

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Fetch JSON and inspect headers:

~~~bash
curl -i 'http://localhost:8080/api/articles/42'
~~~

Response looks like:

~~~http
HTTP/1.1 200
ETag: "article-42-v7"
Last-Modified: Thu, 01 Jan 2026 10:00:00 GMT
Cache-Control: no-cache, private
Content-Type: application/json

{"id":42,"title":"HTTP caching","body":"ETag giúp kiểm tra representation có thay đổi hay chưa.","version":7}
~~~

Header/directive ordering may vary; the shown JSON response is the equivalent representation from the code. If a converter or custom config changes byte ordering, review strong/weak ETags and representation consistency.

### 10.6. Conditional GET via ETag

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-None-Match: "article-42-v7"'
~~~

If the validator matches, the HTTP response is **304**, with no JSON body. Same for the view path:

~~~bash
curl -i 'http://localhost:8080/articles/42/page' \
  -H 'If-None-Match: "article-42-v7"'
~~~

`WebRequest.checkNotModified(...)` returns true and the view does not need to render.

### 10.7. Conditional GET via Last-Modified

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-Modified-Since: Thu, 01 Jan 2026 10:00:00 GMT'
~~~

With the demo's fixed representation/timestamp, the client receives HTTP **304**. To test the REST API with a **mismatching** ETag:

~~~bash
curl -i 'http://localhost:8080/api/articles/42' \
  -H 'If-None-Match: "article-42-v1"'
~~~

The server returns **200** + body, with current ETag `"article-42-v7"`. When sending both conditional headers, mind precedence: when ETag mismatches, `If-Modified-Since` alone must not force 304.

### 10.8. A JavaScript Client Tracking ETags

This example shows a client managing validators itself:

~~~javascript
let cachedArticle = null;
let previousEtag = null;

async function loadArticle() {
  const headers = {};
  if (previousEtag) {
    headers["If-None-Match"] = previousEtag;
  }

  const response = await fetch("/api/articles/42", {
    headers,
    cache: "no-store" // Only in this example so browser-managed cache doesn't obscure the flow.
  });

  if (response.status === 304) {
    return cachedArticle;
  }
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  const data = await response.json();
  cachedArticle = data;
  previousEtag = response.headers.get("ETag");
  return data;
}
~~~

This illustrates an *application-managed validator*. `cache: "no-store"` in Fetch affects the browser-managed HTTP cache, not the server's response `Cache-Control`. In real applications, pick **one consistent cache strategy** and avoid mixing Fetch cache modes unpredictably; behavior can vary across browser Fetch implementations. For cross-origin frontends, JavaScript reading the `ETag` response header requires CORS `Access-Control-Expose-Headers: ETag`, and sending a custom `If-None-Match` request header may trigger a preflight.

## 11. MockMvc Tests: Checking Real Responses and Validators

Create `src/test/java/demo/HttpCacheTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class HttpCacheTest {
    @Autowired
    MockMvc mvc;

    @Test
    void jsonFirstGetReturnsCacheMetadataAndBody() throws Exception {
        mvc.perform(get("/api/articles/42"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"article-42-v7\""))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-cache")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("private")))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void jsonConditionalGetByEtagReturns304WithoutBody()
            throws Exception {
        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(header().string(
                    HttpHeaders.ETAG, "\"article-42-v7\""))
            .andExpect(content().string(""));
    }

    @Test
    void jsonConditionalGetByLastModifiedReturns304()
            throws Exception {
        MvcResult first = mvc.perform(get("/api/articles/42"))
            .andExpect(status().isOk())
            .andReturn();

        String lastModified = first.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);
        assertNotNull(lastModified);

        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_MODIFIED_SINCE, lastModified))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void changedEtagRequiresBody() throws Exception {
        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v6\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void ifNoneMatchTakesPrecedenceOverIfModifiedSince()
            throws Exception {
        MvcResult first = mvc.perform(get("/api/articles/42"))
            .andReturn();
        String date = first.getResponse()
                .getHeader(HttpHeaders.LAST_MODIFIED);
        assertNotNull(date);

        mvc.perform(get("/api/articles/42")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v6\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, date))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void htmlPageUsesWebRequestCheckNotModified() throws Exception {
        mvc.perform(get("/articles/42/page"))
            .andExpect(status().isOk())
            .andExpect(view().name("article-detail"))
            .andExpect(content().string(containsString("HTTP caching")));

        mvc.perform(get("/articles/42/page")
                .header(HttpHeaders.IF_NONE_MATCH, "\"article-42-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void privateExampleForbidsCacheStorage() throws Exception {
        mvc.perform(get("/api/private-example"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(jsonPath("$.message").value("Demo no-store"));
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/articles/999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Key tests:**

1. Normal GET returns 200, `ETag`, `Last-Modified`, `Cache-Control`, and JSON.
2. Conditional matching ETag returns 304 without a body.
3. Matching `If-Modified-Since` can return 304.
4. Stale ETag returns 200; mismatching `If-None-Match` must take precedence over `If-Modified-Since`.
5. `WebRequest` view handler returns 304 without rendering HTML.
6. Simulated sensitive endpoint demonstrates `no-store`.

These tests run in MockMvc and do not verify CDNs, reverse proxies, out-of-process caches, or browser-managed cache behavior. Production requires integration/e2e tests for caching semantics against real infrastructure.

## 12. Conditional Updates: If-Match and 412 Precondition Failed

This lesson focuses on conditional GET, but you must clearly distinguish **optimistic concurrency** for write requests.

Suppose a client reads:

~~~http
GET /api/articles/42
ETag: "article-42-v7"
~~~

Then wishes to update the exact version it read:

~~~http
PUT /api/articles/42
If-Match: "article-42-v7"
Content-Type: application/json

{"title":"New title"}
~~~

If the server is now at version 8, the `If-Match` version 7 condition fails, and HTTP **412 Precondition Failed** is appropriate. This differs from GET's 304: here the goal is **preventing overwrites of a newer version**.

### 12.1. Never Separate ETag Checks from Updates

Concurrency bug:

~~~text
SELECT version FROM article WHERE id=42;  -- returns v7
IF-MATCH == v7? yes
... another request updates article to v8 ...
UPDATE article SET title='...' WHERE id=42; -- overwrites and loses newer data
~~~

You need an atomic operation, for example:

~~~sql
UPDATE article
SET title = :newTitle, version = version + 1
WHERE id = :id AND version = :expectedVersion
~~~

Check the affected row count to detect conflicts/precondition failures. With JPA, `@Version` and transactions support optimistic locking, though status mapping (`409`/`412`) must follow your API contract. HTTP `If-Match` uses **strong comparison**, so weak ETags are unsuitable as strong write preconditions.

### 12.2. Can WebRequest.checkNotModified Be Used for POST/PUT/DELETE?

Spring's `WebRequest.checkNotModified` includes conditional request handling for unsafe methods and can set `412` instead of `304` when a precondition fails. However, it **does not perform atomic database updates**, nor does it replace authentication, authorization, validation, transactions, or optimistic concurrency control.

To ensure contract compliance across all HTTP precondition headers and race conditions, consult RFC 9110 alongside the `WebRequest` implementation of your Spring version and test PUT/PATCH/DELETE separately. Never copy a GET example blindly onto payment or mutation operations.

## 13. Crucial Implementation Pitfalls

### 13.1. Calling checkNotModified After Doing All Heavy Work

~~~java
ArticleDto dto = veryExpensiveGraphMapping();
if (webRequest.checkNotModified(etag)) {
    return null;
}
~~~

This still saves body/network bandwidth, yet wastes effort computing the DTO. Where feasible, query version/`lastModified` first, check, and only then run the heavy path. Do not query the DB **twice** without evaluating trade-offs, transactional consistency, and data races.

### 13.2. Failing to Update ETag When Content Changes

If `article.title` changes without changing `article.version`, clients may wrongly receive 304 and display stale content. Tie the validator to a version incremented atomically when the selected representation changes, or to a canonical byte hash.

### 13.3. Using Last-Modified = Instant.now() on Every GET

Clients will never see "not modified" because the server claims the resource changed on every request. Use the stored timestamp from the source of truth, keeping one-second resolution in mind.

### 13.4. Treating no-cache as "Do Not Store Data"

`no-cache` allows storage while forcing revalidation; if the goal is preventing storage of sensitive content, use `no-store`. `private` only restricts shared caches, not browser caches.

### 13.5. Public Caching for Per-User Data

~~~http
Cache-Control: public, max-age=3600
~~~

on a response containing a personal profile can cause shared caches to store and serve sensitive data. Do not expect authentication middleware to magically adjust cache semantics; explicitly configure policies per resource and proxy.

### 13.6. ETag Independent of Vary/Variants

If the body differs by `Accept-Language`, you need a cache key / `Vary: Accept-Language` and per-representation validators. If gzip-encoded content differs from identity encoding, strong ETags must correspond to each octet representation (or use weak validators per contract). Never blindly reuse the same strong ETag.

### 13.7. 304 with a JSON Body

304 must never send a selected representation body. Never return `304 + {"cached":true}` like a standard JSON success response.

### 13.8. Parsing If-None-Match Manually with Single-String equals

Clients can send multiple ETags, weak tags, wildcards, and combined conditions. Prefer Spring `WebRequest`/`ResponseEntity` and HTTP libraries over writing naive string parsers.

### 13.9. CORS Hiding ETag from the Frontend

A cross-origin JS frontend can read JSON yet cannot read the `ETag` response header unless the server exposes it via:

~~~http
Access-Control-Expose-Headers: ETag
~~~

And if the frontend sends an `If-None-Match` request header manually, a CORS preflight may occur, requiring matching allowed headers. CORS and credentialed response rules still apply; never open wildcards recklessly to fix caching errors.

### 13.10. CDN Caches Serving Stale Data Despite Backend Changes

If a CDN still holds a fresh response, requests might never reach Spring. Use versioned URLs, suitable `max-age`/`s-maxage`, and invalidation policies if immediate updates are required. `ETag` does not force a CDN to contact the backend while cached entries remain fresh per directives.

### 13.11. 404 and 500 Errors

HTTP caching has rules for non-200 statuses; never assume all errors default to `no-store` or are all cached. If you want short-term caching for 404, configure it deliberately; for errors containing personal data or stacktraces, apply storage-blocking policies. Proxies/gateways may overwrite cache headers, so test real responses.

### 13.12. HEAD Differs from GET and Must Not Send a Body

`HEAD` can use validators and cache metadata. In custom filters, interceptors, or streaming responses, ensure no content body is written in violation of HTTP semantics.

## 14. Code Review Checklist

Before merging an endpoint supporting HTTP caching, answer:

- **Resource/representation:** What data does this URL represent? Does it vary by user, locale, compression, format, or auth?
- **ETag correctness:** Is the ETag stable across identical GETs and updated when the representation changes? Strong or weak? Any collisions?
- **Last-Modified correctness:** Does the timestamp come from real data, in millis for `WebRequest` and formatted as HTTP-date in responses? Are multiple updates per second possible?
- **Cache-Control:** Did you pick `no-store`, `private,no-cache`, `public,max-age`, or `immutable` according to sensitivity? Are CDNs/shared caches involved?
- **Conditional handling:** Does a matching validator yield 304 **with no body**? Does a mismatch yield 200 with the new body? Does `If-None-Match` take precedence?
- **Response metadata:** Does 304 preserve appropriate `ETag`/`Last-Modified`/`Cache-Control`/`Vary` metadata?
- **Performance:** Check before expensive work where possible; `ResponseEntity` automates 304, though the DTO may already have been constructed.
- **Auth:** Enforce authentication/authorization on every request and resource; ensure shared caches never leak per-user data.
- **Concurrency:** Use `If-Match` or `@Version`/atomic updates on write requests when needed; map `412`/`409` per contract.
- **Edge cases:** `HEAD`, weak tags, wildcards, malformed conditional headers, clock skew, one-second resolution, CORS, gateway caching.
- **Tests:** At minimum GET 200, `ETag`/`Last-Modified`, GET 304, mismatch 200, `Vary`/`Cache-Control`, `no-store` for sensitive data, and HTTP integration tests if a CDN is present.

## 15. Practice Exercises

**Exercise 1 — Explain states:** A client GETs `/books/1` and receives ETag `"book-v4"`. Next time it sends `If-None-Match: "book-v4"`. Sketch the HTTP 200/304 flow and state whether 304 carries a body.

**Exercise 2 — no-cache vs. no-store:** A public info endpoint needs revalidation on every view; a password-reset-token endpoint must never be stored. Pick the right `CacheControl` directives and explain why.

**Exercise 3 — WebRequest:** Write a method accepting `WebRequest`, `Model`, `article.version`, and `article.updatedAt`. Use `checkNotModified(String,long)` to return early if the GET is not modified.

**Exercise 4 — ResponseEntity:** Write a controller returning `ResponseEntity<BookDto>` with `CacheControl.maxAge(Duration.ofMinutes(2)).cachePublic()`, an ETag from hash/version, and `Last-Modified` from the DB.

**Exercise 5 — Condition precedence:** A client sends a stale ETag and an `If-Modified-Since` equal to the latest timestamp. Should the response be 200 or 304 if the ETag mismatches? Explain precedence.

**Exercise 6 — Per-user representation:** A `/api/me` response depends on a session cookie. Should a public CDN cache it? Choose `private/no-cache` or `no-store` by sensitivity and analyze access control.

**Exercise 7 — Concurrency:** Two clients both read version 7. Client A PUTs an update to version 8. Client B PUTs with `If-Match: "v7"`. Which status is appropriate and why must the version check and update be atomic?

**Exercise 8 — ETag variants:** An API returns different JSON by `Accept-Language`. Design `Vary` and ETags for `vi-VN`/`en-US`. What happens if two byte-different representations share the same strong ETag?

**Exercise 9 — MockMvc:** Write tests asserting `ETag`, `Last-Modified`, bodyless 304, a `no-store` endpoint, and a conditional GET with a mismatching validator.

**Exercise 10 — CDN:** A public article has `Cache-Control: public, max-age=300`, and the backend updates content 10 seconds later. Why might users still see the old version for up to 5 minutes? When should you use `no-cache`, short `max-age`, or versioned URLs?

## 16. Takeaways

- **HTTP caching** reduces network latency; it is distinct from Spring Cache `@Cacheable`.
- **`Cache-Control`** governs freshness, storage, and revalidation. `no-cache` allows storing while requiring revalidation; `no-store` forbids storage.
- **`ETag`** is a representation validator; **`Last-Modified`** is the modification timestamp. ETags can be more precise than one-second timestamps.
- **`If-None-Match` / `If-Modified-Since`** power conditional GET/HEAD: when matched, return **304 Not Modified with no body**.
- **`WebRequest.checkNotModified(...)`** lets controllers check early and skip rendering/computation if validators match.
- **`ResponseEntity.cacheControl(...).eTag(...).lastModified(...)`** emits cache headers and lets Spring MVC handle conditional responses, though the controller may have already built the DTO.
- **`private`/`public`/`no-store`** must match data sensitivity and shared caches; caching never replaces authentication/authorization.
- **Write preconditions** like `If-Match` combined with atomic updates prevent lost updates; do not confuse them with GET's 304.

## 17. Official Documentation

- [Spring Framework 6.2 — HTTP Caching (Servlet MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-caching.html).
- [Spring Framework 6.2 — WebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/WebRequest.html): `checkNotModified` overloads.
- [Spring Framework 6.2 — ServletWebRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/ServletWebRequest.html): status, ETag, and Last-Modified.
- [Spring Framework 6.2 — ResponseEntity.HeadersBuilder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html): `eTag`, `lastModified`, `cacheControl`, `varyBy`.
- [Spring Framework 6.2 — CacheControl API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/CacheControl.html).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): conditional requests, 304/412, validators, `If-Match`, and `If-None-Match`.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `Cache-Control` directives, freshness, stored responses, and shared caches.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): browser, proxy, and revalidation.
