# Vary and Correctness When Responses Change by Header

## 1. Why Can One URL Have Multiple Response Versions?

Suppose two clients both call `GET /greeting`, yet client A sends `Accept-Language: vi` and receives `Xin chào!`, while client B sends `Accept-Language: en` and receives `Hello!`. Or both call `GET /assets/app.js`: a browser supporting `gzip` receives compressed data, whereas another client receives uncompressed content.

**The same method and URL do not always mean the same representation.** The server may choose content, language, media type, or encoding based on **request headers**. If a browser cache, reverse proxy, or CDN uses only the URL as its reuse key, it can return **the wrong response copy** to the next client.

HTTP solves a crucial part of this with the **`Vary`** response header.

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: vi
Cache-Control: public, max-age=60
Vary: Accept-Language

Xin chào!
~~~

`Vary: Accept-Language` indicates that representation selection may depend on the `Accept-Language` request header. A compliant HTTP cache must consider that header's value when deciding whether a stored response can be reused.

**After this lesson**, you will understand:
- What `Vary` is, which request headers it applies to, and how it changes cache keys.
- Why `Accept-Encoding`, `Accept-Language`, `Accept`, and `Origin` are classic cases.
- How to handle content negotiation, compression, CORS, and personalized responses without leaking content.
- How to add `Vary` in Spring MVC/WebFlux, verify headers with `curl`, and test caches/CDNs.
- The relationship between `Vary`, `Cache-Control`, `ETag`, `304 Not Modified`, and subtle bugs that often surface only behind a reverse proxy.

> **Practical scope:** Java 17+ examples use Spring Boot 3.5.x, Spring MVC, and Spring Web. In Spring Boot 4.x, the Spring MVC starter is split into `spring-boot-starter-webmvc`; the HTTP `Vary` mechanism and `ResponseEntity.varyBy(...)` API retain their corresponding roles. Some headers added by servers, gateways, or CORS filters can differ by version and configuration, so always measure actual responses.

## 2. How Is `Vary` Defined in HTTP?

According to **RFC 9110, section 12.5.5**, `Vary` is a **response header field** describing the request header fields that can influence the origin server's choice of representation, alongside the method and target URI. Its value is normally a list of header names, not the specific values of those headers.

Valid examples:

~~~http
Vary: Accept-Encoding
Vary: Accept-Language
Vary: Accept, Accept-Encoding
Vary: Origin
Vary: *
~~~

### `Vary` Does Not Contain Request Header Values

Correct:

~~~http
Vary: Accept-Language
~~~

Incorrect usage of the standard:

~~~http
Vary: Accept-Language: vi
~~~

The incorrect line above is not a valid `field-name` list per `Vary` syntax. The response states **which fields to examine**, while the cache remembers what value those fields had in the **request that produced the response**.

### What Conditions Does the Cache Check?

According to **RFC 9111, section 4.1**, a cache holding a stored response with `Vary` must not use it to satisfy a new request **if the headers listed in `Vary` do not match** those in the original request that produced the stored response, unless the response is appropriately revalidated.

Simple mental model:

~~~text
Basic cache identity: method + target URI

GET /greeting
    |
    +--- Vary: Accept-Language
           |
           +--- request Accept-Language: vi -> Vietnamese representation
           |
           +--- request Accept-Language: en -> English representation

GET /assets/app.js
    |
    +--- Vary: Accept-Encoding
           |
           +--- request supports gzip -> gzip variant
           |
           +--- request does not support gzip -> identity variant
~~~

This is a **logical** model; it does not assert every CDN physically stores objects keyed by concatenating fields as a string. Cache implementations may normalize headers or perform revalidation. Regardless, the outcome **must not serve the wrong representation** to an incompatible request.

### “Matching” Does Not Always Mean Byte-for-Byte Comparison

RFC 9111 permits normalization according to field syntax and semantics, for example:
- Removing or adding valid whitespace.
- Combining header lines with the same name when field rules permit.
- Normalizing values known to be semantically equivalent, such as case differences in case-insensitive fields.

If a header listed in `Vary` was **absent** in the original request, it only matches a new request where that header is also absent, after valid normalization steps. Do not treat an absent `Accept-Encoding` and `Accept-Encoding: gzip` as equivalent.

**Do not write your own proxy cache by naively comparing raw header strings** unless you understand the RFC and gateway behavior. The safest approach is to let a standards-compliant HTTP cache handle `Vary`.

## 3. Classic Bug: Wrong Cache Hit Due to Missing `Vary`

Suppose the origin produces content by language:

| Request | Origin should return | If cache keys only on URL |
|---|---|---|
| `GET /greeting` + `Accept-Language: vi` | `Xin chào!` | May store the Vietnamese copy |
| `GET /greeting` + `Accept-Language: en` | `Hello!` | May wrongly serve the Vietnamese copy |
| `GET /greeting` + `Accept-Language: vi` | `Xin chào!` | Vietnamese copy may look right by coincidence |

If the origin sends `Cache-Control: public, max-age=300` **without sending** `Vary: Accept-Language`, a shared cache can reuse the stored copy for clients requesting other languages. This bug often stays hidden during local development without a cache, then surfaces once a CDN is enabled.

Fix at the origin:

~~~http
Cache-Control: public, max-age=300
Vary: Accept-Language
Content-Language: vi
~~~

And across **all corresponding variants**, including the default English copy when a request omits `Accept-Language`, apply a consistent `Vary` policy. Adding `Vary` only to the Vietnamese response while omitting it on the default response easily causes wrong reuse on subsequent requests.

**What `Vary` does NOT do:** it does not translate languages, does not generate extra files, does not automatically enable a CDN, and does not decide whether a response is cacheable. The server still has to pick the right variant; `Vary` simply conveys the metadata caches need to reuse it properly.

## 4. Table of Headers That Commonly Change Content

| Influencing request header | What the origin may change | Common `Vary` | What to check |
|---|---|---|---|
| `Accept-Encoding` | Compressed `gzip`/`br` body or identity | `Vary: Accept-Encoding` | Whether `Content-Encoding` and body bytes match the client |
| `Accept-Language` | Text language | `Vary: Accept-Language` | `Content-Language` and language selection policy |
| `Accept` | Media type such as JSON, XML, HTML | `Vary: Accept` | `Content-Type`, 406, message converters |
| `Origin` | CORS headers, especially `Access-Control-Allow-Origin` | `Vary: Origin` | CORS policy, caching of preflight/actual responses |
| `Access-Control-Request-Method` | CORS preflight outcome | `Vary: Access-Control-Request-Method` | Only in preflight if outcome depends on method |
| `Access-Control-Request-Headers` | CORS preflight outcome | `Vary: Access-Control-Request-Headers` | Outcome depends on requested headers |
| `User-Agent` | HTML/assets tailored per UA | Possibly `Vary: User-Agent` | Huge number of variants, cache-hit drop |
| Client Hints | Image/UI quality per client hints | `Vary` on fields actually used | Privacy, client support, cardinality |
| `Cookie` | Per-session/per-user content | Generally **should not** rely on `Vary: Cookie` for security | Use `Cache-Control: private` or `no-store` when needed |

Do not add a header to `Vary` just because the request contains it. List only fields that can genuinely affect representation selection or cached response headers. `User-Agent` and `Cookie` create too many variants and typically degrade cache efficiency.

## 5. Relationship to `Accept-Encoding` and HTTP Compression

### 5.1. Uncompressed and gzip Formats Are Not Byte-Equivalent

Client A:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: gzip
~~~

The server may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/javascript
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: public, max-age=3600

<gzip-compressed-bytes>
~~~

Client B:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: identity
~~~

The server may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/javascript
Vary: Accept-Encoding
Cache-Control: public, max-age=3600

<uncompressed-javascript-bytes>
~~~

The two blocks show structure; strings inside angle brackets are **placeholders**, not actual bodies.

`Accept-Encoding` declares which content codings the client accepts; `Content-Encoding` describes the coding applied to the response. `Content-Type` still describes the **underlying media type** of the content. If a cache serves a gzip copy to a client that does not support gzip, the client may receive unreadable bytes or fail decoding.

### 5.2. In Spring Boot, the Server/Container Can Manage Compression

Spring Boot supports response compression for supported embedded servers such as Tomcat, Jetty, and Reactor Netty. With Boot 3.5:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - text/plain
      - text/html
      - application/json
      - application/javascript
    min-response-size: 2KB
~~~

Per Boot 3.5 documentation, `server.compression.enabled` defaults to `false` and the default threshold is **2KB**; default supported media types include text/plain, JSON, CSS, JavaScript, etc. Both the list and threshold can be changed. A small response may **not be compressed** even if the browser sends `Accept-Encoding: gzip`; therefore never assume every request carrying gzip must receive `Content-Encoding: gzip`.

Depending on server, HTTP version, proxy, and how the response is written, emitting `Vary: Accept-Encoding` may be handled by the server/proxy layer. **Observe actual headers along the deployed request path**, rather than assuming enabling compression alone makes every cache layer handle variants accurately.

### 5.3. Common Bugs When Two Layers Compress

Example:
- Origin already gzip-compressed the response.
- Reverse proxy applies another transformation or its cache key ignores `Accept-Encoding`.
- CDN serves compressed bytes to an unsupported client, or emits `Content-Encoding: gzip` mismatched with the body.

The usual fix is to designate **which layer owns compression**, preserve/normalize `Vary` properly, avoid double compression, set `Content-Encoding` accurately, and test the real path from origin through proxies to the client.

`Cache-Control: no-transform` can be used when intermediaries must not transform the representation, though it does not mean “origin may not compress” and does not replace `Vary` when multiple encoding variants exist.

## 6. `Accept-Language`: Language Content Negotiation Example

Request:

~~~http
GET /greeting HTTP/1.1
Accept-Language: vi
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: vi
Vary: Accept-Language
Cache-Control: public, max-age=60

Xin chào!
~~~

Another language:

~~~http
GET /greeting HTTP/1.1
Accept-Language: en
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: en
Vary: Accept-Language
Cache-Control: public, max-age=60

Hello!
~~~

`Content-Language` describes the language of the selected content. `Vary` indicates the selecting field; `Cache-Control` states how caches may store/reuse it for a period.

### An Advanced Note: q-values and Language Normalization

Real browser headers can be complex:

~~~http
Accept-Language: en-US,en;q=0.9,vi;q=0.7
~~~

This is a preference list, not a simple single string. Production applications should use **locale negotiation** appropriate for Spring MVC/Servlet or WebFlux instead of parsing naively with `startsWith("vi")`, because regions, quality factors, default languages, and language tags must be handled.

For sites with a fixed set of languages, distinct URLs such as `/vi/greeting` and `/en/greeting` can help CDNs cache more effectively than one URL varying across arbitrary raw `Accept-Language` strings from many browsers. Either way, keep URL and header semantics consistent.

## 7. Java 17 Practice with Spring Boot: Setting `Vary` Correctly

Create a project using **Spring Initializr**, Java 17+, Gradle, Spring Boot **3.5.x**, dependency **Spring Web**. No Redis, Spring Security, or CDN is required for this part.

In a project already configured with the Boot Gradle plugin/dependency management, the dependency for Boot 3.5 is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

On Spring Boot 4.x, choose the corresponding `spring-boot-starter-webmvc` starter. This is a dependency fragment for a Boot project, not a complete Gradle file.

Create `src/main/java/demo/vary/VaryDemoApplication.java`:

~~~java
package demo.vary;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class VaryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaryDemoApplication.class, args);
    }

    @GetMapping(value = "/greeting", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> greeting(
            @RequestHeader(value = "Accept-Language", required = false)
            String acceptLanguage) {

        // Simple rule solely for the two curl cases: "vi" and "en".
        boolean isVietnamese = acceptLanguage != null
                && acceptLanguage.toLowerCase(Locale.ROOT).startsWith("vi");

        String language = isVietnamese ? "vi" : "en";
        String body = isVietnamese ? "Xin chào!" : "Hello!";

        return ResponseEntity.ok()
                .varyBy("Accept-Language")
                .cacheControl(
                    CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic()
                )
                .header("Content-Language", language)
                .contentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)
                )
                .body(body);
    }

    @GetMapping(value = "/payload", produces = MediaType.TEXT_PLAIN_VALUE)
    public String payload() {
        return "A".repeat(4096);
    }
}
~~~

The code above is **a complete runnable Boot class** in a project with the proper starter. `ResponseEntity.ok().varyBy(...)` is the official Spring Framework API and can accept multiple request header names. `CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic()` is appropriate here only because the content is **completely public**.

**Intentional limitation of the demo:** `startsWith("vi")` clearly demonstrates only the two curl commands `Accept-Language: vi` and `en`. It is not a proper language selection algorithm for arbitrary `Accept-Language` values with `q` factors. In real systems, use a standard locale resolver/negotiation mechanism; `Vary` must still list all headers affecting the content.

To also test HTTP compression, create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
    mime-types:
      - text/plain
    min-response-size: 2KB
~~~

Start from the project root created by Spring Initializr:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 7.1. Testing Two Languages

With the application running:

~~~bash
curl -sS -i -H 'Accept-Language: vi' http://localhost:8080/greeting
~~~

Expected response body:

~~~text
Xin chào!
~~~

Expected key headers (exact ordering/casing and additional server headers are not guaranteed):

~~~http
HTTP/1.1 200
Vary: Accept-Language
Content-Language: vi
Cache-Control: public, max-age=60
~~~

Command for the other client:

~~~bash
curl -sS -i -H 'Accept-Language: en' http://localhost:8080/greeting
~~~

Expected response body:

~~~text
Hello!
~~~

And relevant headers:

~~~http
Vary: Accept-Language
Content-Language: en
~~~

When `Accept-Language` is omitted, the demo picks the default English copy **yet still sends `Vary: Accept-Language`**. This is essential so caches know the default variant also participates in the selection rule.

Plain `curl` **does not act as a shared HTTP cache**, so these commands verify origin responses and headers rather than real CDN hit/miss behavior. To evaluate real caching, run through your configured proxy/CDN and inspect that system's cache-status headers/logs.

### 7.2. Testing Compression with a Sufficiently Large Body

The `/payload` endpoint returns **4,096 'A' characters**, easily exceeding the 2KB compression threshold on supported servers.

Client not requesting gzip:

~~~bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/payload
~~~

Client requesting gzip; `--compressed` tells curl to automatically decode supported content codings:

~~~bash
curl -sS --compressed -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/payload
~~~

Observe `Content-Encoding`, `Vary`, `Content-Length`/`Transfer-Encoding`, and the body when needed; compressed bodies should not be printed raw to a terminal. In many Tomcat/Boot 3.5 setups, gzip appears on the second request, though **exact headers are not guaranteed identical across every container, proxy, and version**.

**Important to know:** the `/greeting` body is far shorter than the 2KB threshold; a request with `Accept-Encoding: gzip` to `/greeting` may not be compressed. Do not use a tiny test response to conclude compression or `Vary` is working or broken system-wide.

## 8. Distinguishing `Vary: Accept` from `Vary: Accept-Encoding`

The two headers serve different roles:

- `Accept`: the client announces the **media types** it accepts, such as `application/json` or `application/xml`.
- `Accept-Encoding`: the client announces **representation encodings** such as `gzip`, `br`, or `identity`.

Example of one resource having two representation types:

~~~http
GET /profile/public HTTP/1.1
Accept: application/json
~~~

The response may be:

~~~http
Content-Type: application/json
Vary: Accept

{"name":"Example"}
~~~

Another client:

~~~http
GET /profile/public HTTP/1.1
Accept: application/xml
~~~

The response may be:

~~~http
Content-Type: application/xml
Vary: Accept

<profile><name>Example</name></profile>
~~~

If the server does not support the requested type and has no fallback, the result can be `406 Not Acceptable`. In Spring MVC/WebFlux, media type negotiation can be handled via `produces` mappings and message converters; verify actual headers on the served route.

If the same route also serves gzip and identity, you may need:

~~~http
Vary: Accept, Accept-Encoding
~~~

Before adding `Vary: Accept` mechanically, confirm the response can actually vary by `Accept`. An endpoint that always returns JSON without media-type negotiation may not need `Vary: Accept` just “to be safe”.

## 9. `Vary: Origin` and CORS

When a browser makes a cross-origin API call, the request may carry:

~~~http
Origin: https://app.example.test
~~~

If the origin server allows that specific origin, the response may emit:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

For requests from another origin in the allowlist, `Access-Control-Allow-Origin` can change value. **Even when the JSON response body is identical**, CORS metadata varies by `Origin`, so shared caches must not mistakenly serve origin A's CORS headers to origin B. `Vary: Origin` keeps them distinct.

Spring MVC/WebFlux handles CORS at the HandlerMapping/Filter layer. In certain configurations, the framework also emits preflight-related `Vary` fields such as:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

This does not mean you must manually add all three to **every endpoint**. Inspect your CORS configuration, check whether requests are preflight or actual requests, and ensure `Vary` accurately reflects the request headers used to select the outcome.

### CORS Is Not `Vary`

- **CORS** governs which browser JavaScript origins are permitted to read cross-origin responses.
- **`Vary`** helps caches distinguish responses by headers.
- `Vary: Origin` **does not grant CORS permission**.
- `Access-Control-Allow-Origin` **does not guarantee shared caches serve the right response** unless cache behavior is also configured properly.

When enabling CORS with credentials, do not blindly set `Access-Control-Allow-Origin: *`; Spring restricts wildcards when `allowedCredentials=true`. Allow only trusted origins under explicit policies; CORS is also not a user authentication mechanism.

## 10. How Does `Vary` Differ from `Cache-Control`?

One response can carry both:

~~~http
Cache-Control: public, max-age=600
Vary: Accept-Language
~~~

Meaning:
- `Cache-Control`: whether eligible caches may store the response and treat it as fresh for how long.
- `Vary`: if a cache wants to reuse it, **which additional request header names** must be checked.

Table:

| Header / Directive | Question it answers |
|---|---|
| `Vary: Accept-Language` | Is this response copy valid for a request with this language? |
| `Cache-Control: max-age=60` | How long can the response be considered fresh under cache rules? |
| `Cache-Control: public` | May shared caches use it if other conditions are met? |
| `Cache-Control: private` | Are shared caches forbidden from storing the response for multiple users? |
| `Cache-Control: no-store` | Are caches asked not to store the associated request/response? |
| `Cache-Control: no-cache` | Must the stored response be revalidated before reuse? |
| `ETag: "..."` | Is there a validator to revalidate the representation? |

**Specifically:** `no-cache` does not mean “do not store”; it allows storage while requiring revalidation before reuse. `no-store` is what requests no storage. `private` blocks shared-cache storage, while potentially allowing private browser caches depending on other directives.

### User/Cookie/Auth-Dependent Responses

If `GET /api/me` returns account details based on a `JSESSIONID` cookie or `Authorization` token, **do not rely solely on**:

~~~http
Vary: Cookie
~~~

This creates high-cardinality cache keys that are hard to verify and does not replace data-protection policies. Choose a response policy like:

~~~http
Cache-Control: private, no-store
~~~

for sensitive or non-storable info. For personal content where device-local caching is acceptable, `private` with an appropriate TTL may be tolerable depending on the threat model; analyze risks around logout, shared devices, and data updates.

The RFC defines specific rules for requests with `Authorization` and shared caches. Nevertheless, **do not rely solely on proxy defaults** to protect confidential data; explicitly configure sensitive responses and test through real infrastructure.

## 11. What Does `Vary: *` Mean?

~~~http
Vary: *
~~~

This wildcard value indicates that representation selection depends on factors the recipient cannot determine solely from a list of header field names. Under RFC 9111, a stored response containing `Vary: *` **always fails to match** under normal cache matching rules.

However, **`Vary: *` is not equivalent to `Cache-Control: no-store`**:
- `Vary: *` is about whether a stored response can be reused for subsequent requests.
- `no-store` is about the obligation not to store the request/response in a cache.

In practice, when the goal is **not to store sensitive data**, use `Cache-Control: no-store` appropriately rather than treating `Vary: *` as a security mechanism. `Vary: *` also reduces cache reusability; do not use it to avoid identifying which headers actually affect the representation.

## 12. ETag, Last-Modified, 304, and Compressed Versions

`Vary` and conditional requests must coordinate so a cache does not “revalidate the right URL with the wrong variant”.

### 12.1. What Are Validators?

- `ETag` is an entity tag for comparing representation versions.
- `If-None-Match` is the condition sent by a client/cache to check whether a stored representation changed.
- `Last-Modified` and `If-Modified-Since` provide time-based validation.

For GET, if valid conditions show the representation has not changed, the origin can return **304 Not Modified** and the client/cache reuses the appropriate stored body. Never return 304 for a variant incompatible with the selecting headers in `Vary`.

### 12.2. ETag for gzip and identity

Imagine a JavaScript body that is identical after decompression yet differs in raw bytes:

~~~text
Identity bytes: [function hello() {...}]
Gzip bytes:     [gzip header + compressed bytes]
~~~

A **strong ETag** asserts strong byte-level equivalence of representation data; using the **same strong ETag** for two byte-different representations can violate validator semantics. Some servers/CDNs generate distinct ETags per content coding or adjust validator generation accordingly.

Illustrative example:

~~~http
Content-Encoding: gzip
Vary: Accept-Encoding
ETag: "app-v12-gzip"
~~~

And identity:

~~~http
Vary: Accept-Encoding
ETag: "app-v12-identity"
~~~

The two ETags above are merely hypothetical strings showing how to differentiate them, **not automatic Spring Boot values**. A weak validator `W/"..."` can denote weak equivalence where appropriate; however, using strong/weak validators correctly requires adhering to RFC rules and how your server/transformer actually generates ETags.

### 12.3. 304 Also Needs Representation Selection Info

A 304 response needs to emit relevant headers such as `ETag`, `Cache-Control`, and `Vary` when they would appear in the corresponding 200, per HTTP semantics. If a proxy drops `Vary` on a 304 response and corrupts stored metadata, the cache could pick the wrong variant on subsequent requests.

When debugging “works on first request, wrong on second”, inspect not only **200** but also **304**, `If-None-Match` requests, and cache revalidation metadata.

## 13. Browser, Reverse Proxy, and CDN Caches Can Behave Differently

Diagram:

~~~text
Browser
  | Cookie / Accept-Language / Accept-Encoding
  v
Browser cache
  |
  v
CDN edge / shared cache
  |
  v
Reverse proxy / load balancer
  |
  v
Spring Boot origin
~~~

Each layer may:
- Cache or skip caching a response.
- Normalize request headers, e.g., `Accept-Encoding`.
- Add/remove headers or perform content compression.
- Serve stale responses per specific settings.
- Enforce custom cache-key rules that do not automatically follow what the origin expects in every scenario.

When using a CDN, **do not test only the origin**. Configure the edge infrastructure so it preserves relevant `Vary` headers, never merges incompatible variants, and understands your CDN product's official cache key behavior. Some CDNs limit which headers can enter cache keys or cache/normalize a fixed set of `Accept-Encoding` values; read the specific vendor's documentation.

### Cache Key Explosion

If you use:

~~~http
Vary: Accept-Language, User-Agent, Cookie
~~~

the number of combinations can become huge, driving hit ratios near zero, wasting memory/CDN cache space, and increasing origin load. Better options include:
- Mapping languages to a normalized set, or using language-specific URL paths.
- Not varying on cookies for personal content: use `private`/`no-store`.
- Using only genuinely necessary client hints.
- Enabling compression at one consistent layer with vendor-supported encoding cache keys.

Optimizing cache-hit ratio is only worthwhile when **correctness and security are not compromised**.

## 14. Writing `Vary` in Spring MVC and WebFlux

### Spring MVC — ResponseEntity

In the runnable example, the standard API is:

~~~java
return ResponseEntity.ok()
        .varyBy("Accept-Language")
        .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic())
        .header("Content-Language", language)
        .body(body);
~~~

This is a controller **fragment**. `varyBy(String... requestHeaders)` accepts one or more header names; it adds them to `Vary` and avoids duplicating the same name within what the builder manages. When multiple selecting fields are needed:

~~~java
return ResponseEntity.ok()
        .varyBy("Accept", "Accept-Language")
        .body(body);
~~~

Only add `Accept` if content/media type truly depends on that field. The `varyBy` API is clearer and less error-prone than assembling raw `"Vary: ..."` strings manually; if filters/proxies also modify `Vary`, always inspect the final header.

### Spring WebFlux — ResponseEntity / Functional Endpoints

In WebFlux annotated controllers, `ResponseEntity` and `varyBy(...)` are also usable:

~~~java
@GetMapping("/reactive-greeting")
public Mono<ResponseEntity<String>> greeting() {
    return Mono.just(
            ResponseEntity.ok()
                .varyBy("Accept-Language")
                .body("Hello!")
    );
}
~~~

This is a **fragment**; `@RestController`, imports, and the WebFlux dependency must exist in the project. It demonstrates the header-setting API, not a real language-negotiating endpoint. With WebFlux functional routing, equivalent builder APIs produce the Vary header. Choose MVC or WebFlux based on your application's web stack; do not accidentally mix both starters.

### Spring Security, CORS, and Filters

A filter, Spring Security, CORS processor, or reverse proxy may add `Vary` fields. When multiple layers contribute values, the final output must preserve **all selecting fields**. Do not overwrite:

~~~text
Vary: Accept-Encoding
~~~

with just:

~~~text
Vary: Origin
~~~

if both conditions affect the response. You must append/merge:

~~~http
Vary: Accept-Encoding, Origin
~~~

through a valid mechanism and verify proper behavior. Calling `ResponseEntity.varyBy(...)` in a controller alone is not enough to prove downstream proxies won't strip or overwrite it.

## 15. Correctness Testing Workflow

### 15.1. Origin Testing with `curl`

The commands in section 7 verify:
- For the same `/greeting`, the body changes with `Accept-Language`.
- Both `vi` and `en` responses include `Vary: Accept-Language`.
- `Content-Language` matches the body.
- Public responses carry an explainable cache policy.

**Do not run plain `curl` and claim “the cache hit”**, because `curl` does not represent a stateful browser/CDN cache.

### 15.2. Testing Through a Real Shared Cache

When infrastructure has a configured CDN or reverse proxy cache, run this sequence against the same URL:

| Order | Request | What to check |
|---|---|---|
| 1 | `Accept-Language: vi` | Cache may MISS, Vietnamese body |
| 2 | Repeat `Accept-Language: vi` | Cache may HIT, still Vietnamese body |
| 3 | `Accept-Language: en` | Must not wrongly reuse Vietnamese copy; may MISS |
| 4 | Repeat `Accept-Language: en` | Cache may HIT, still English body |
| 5 | Omit `Accept-Language` | Must not grab wrong variant just because header is absent |
| 6 | `Accept-Encoding: gzip` | If compressed variant, gzip headers/body match |
| 7 | `Accept-Encoding: identity` | Must not receive gzip bytes under identity encoding |
| 8 | With `Origin` A and B | CORS headers match each allowed origin |
| 9 | `If-None-Match` for matching variant | 304/revalidation never mixes bodies or validators across variants |

`HIT`/`MISS` are **possible** outcomes depending on policy, TTL, cache eligibility, and implementation; two identical requests are not guaranteed to HIT. The **mandatory** requirement is that response bodies and headers are **correct for the request** with no data leaks.

### 15.3. Multi-Layer Observability

Collect all of:
- Request headers seen at **browser → CDN** and **CDN → origin**.
- Response headers at **origin → CDN** and **CDN → browser**.
- `Vary`, `Cache-Control`, `Content-Encoding`, `Content-Type`, `Content-Language`.
- `ETag`, `Age`, and cache-status headers actually emitted by your infrastructure.
- Content hashes or real body comparisons after decoding.
- 304 revalidations, redirects, and error responses.

If `Age` increases alongside a wrong response, a cache layer is likely reusing an invalid copy. Note that not every CDN emits `Age` or identical cache-status headers; rely on your provider's logs/settings.

## 16. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix or verification |
|---|---|---|
| English browser receives Vietnamese content after another request | Missing `Vary: Accept-Language` on cacheable response | Add Vary consistently including default variant; inspect CDN key |
| Client without gzip support receives gzip body | Shared cache merged encoding variants or wrong headers | Inspect `Vary: Accept-Encoding`, `Content-Encoding`, and compression config |
| Origin returns right copy, CDN returns wrong one | CDN ignores/overwrites `Vary`, mis-normalizes headers | Compare headers on both sides, configure cache key |
| `Vary` is present yet cache still leaks user data | Relying on `Vary: Cookie` instead of privacy cache policy | Use `private`/`no-store`, protect auth, verify CDN |
| Default language gets mis-cached frequently | Default response omits `Vary` | Apply identical Vary across all representations |
| After enabling gzip, ETag/304 serves wrong data | Invalid validator used across coded variants | Check strong/weak ETags, revalidation, and Vary on 304 |
| Cache hit ratio plunges | Varying on `User-Agent`, `Cookie`, or overly granular headers | Reduce cardinality, use normalized URLs/locales |
| `Vary` header left with only `Origin` | Proxy/filter replaced existing Vary values | Merge instead of overwriting; check final response |
| `Vary: Origin` present yet browser still blocks CORS | Missing/wrong `Access-Control-Allow-Origin` and credentials policy | Configure CORS; do not treat Vary as granting access |
| `Accept-Encoding: gzip` sent yet no compression seen | Compression off, MIME excluded, body too small, proxy transform | Check server config, min-response-size, response size |
| Two `curl` calls never show HIT | curl is not a shared cache by itself | Test through real cache/CDN and inspect logs/status |
| Enabled `Vary: *` thinking storage is disabled | Confusing Vary with no-store | Use `Cache-Control: no-store` when no storage is required |

### Pre-Deployment Checklist

- [ ] Clear list of request headers that **genuinely** alter representations or response policies.
- [ ] All variants, including defaults, return `Vary` consistently when needed.
- [ ] `Content-Type`, `Content-Language`, `Content-Encoding` match actual body.
- [ ] Cache-Control clearly separates public resources from per-user content.
- [ ] Not relying on `Vary: Cookie` as a security mechanism instead of `private`/`no-store`.
- [ ] Compressors, origin, proxies, and CDNs do not overwrite/drop selecting fields.
- [ ] ETag/revalidation/304 obey per-variant semantics.
- [ ] Tested with/without `Accept-Language` and `Accept-Encoding`, and multiple `Origin`s.
- [ ] Not assuming a high cache-hit ratio means responses are correct.
- [ ] Tested through the **production-like path**, not only direct localhost calls.

## 17. Self-Check Questions

**Question 1.** Two requests hit the same URL: one sends `Accept-Language: vi`, one sends `en`; the server returns different content. What should the response include?

**Answer:** `Vary: Accept-Language` on cacheable variant responses so caches do not mix languages.

**Question 2.** Does `Vary: Accept-Encoding` force the server to gzip every response?

**Answer:** No. The header only states `Accept-Encoding` can affect the representation; actual compression depends on request, MIME, size, server config, and other conditions.

**Question 3.** Does `Cache-Control: public, max-age=600` automatically guarantee the right language?

**Answer:** No. It governs cache eligibility and freshness; proper `Vary`/cache keys are required when representations depend on request headers.

**Question 4.** If data depends on a session cookie, is adding `Vary: Cookie` safe enough?

**Answer:** No. For personal/sensitive content, pair proper `Cache-Control: private` or `no-store` policies with authentication/authorization and CDN configuration.

**Question 5.** Is `Vary: *` the same as `no-store`?

**Answer:** No. `Vary: *` makes stored responses fail normal reuse matching; `no-store` instructs caches not to store.

**Question 6.** If bodies and CORS headers change by `Origin`, what should be watched?

**Answer:** `Vary: Origin` keeps shared caches from mixing CORS responses across origins; however, by itself it does not grant CORS access or replace the `Access-Control-Allow-Origin` policy.

**Question 7.** Should the same strong ETag be shared between byte-different gzip and identity bodies?

**Answer:** No. Strong validators must reflect strong representation equivalence; verify compression, validator generation, and 304 behavior per variant.

**Question 8.** Sending `Accept-Language: en` then `vi` with curl and observing two correct bodies—does that prove the CDN cache is safe?

**Answer:** Not yet. It only proves the origin responds properly to two requests. Test through the real shared cache and compare headers, bodies, hit/miss, and 304 behavior.

### Extension Exercise

Starting from the Java project in section 7, add a French `fr` option to `GET /greeting` and ensure responses include `Content-Language: fr` and `Vary: Accept-Language`. Then place it behind a test cache where HIT/MISS can be observed, send `vi → en → fr → vi` sequentially, and record when the cache is permitted to reuse responses. Finally, create a `/account/me` endpoint simulating per-user content and explain why `Cache-Control: private, no-store` is chosen instead of `Vary: Cookie`.

## 18. References and HTTP Standards

- [RFC 9110 `12.5.5 — Vary (HTTP Semantics)](https://www.rfc-editor.org/rfc/rfc9110.html#name-vary)
- [RFC 9111 `4.1 — Calculating Cache Keys with Vary](https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-cache-keys-with)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [Spring Framework — ResponseEntity.HeadersBuilder.varyBy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html)
- [Spring Boot 3.5 — Embedded Web Servers / Enable HTTP Response Compression](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [MDN — HTTP caching, Vary, content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**Closing note:** `Vary` is part of the **correctness contract between origin and cache**. It neither determines how long data is cached nor secures personal data. Whenever responses depend on request headers, identify the selecting headers, emit `Vary` consistently, configure appropriate cache policies, and test every layer from origin to CDN/browser.