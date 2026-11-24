# ETag, Last-Modified, and Conditional HTTP Requests in Spring Boot

When a browser requests a URL again, the server does not always need to resend the entire JSON, HTML, CSS, or image. If the client already has a valid copy, a **conditional request** lets it verify the version it holds: **304 Not Modified** indicates that the stored copy is still usable, while **200 OK** carries new content if the representation has changed. Two common HTTP validators are **ETag** and **Last-Modified**. They also support **write preconditions** to prevent overwriting someone else's updates, typically using **If-Match** and **412 Precondition Failed**.

This lesson belongs to the topic **Spring Boot - web-runtime / HTTP Caching and Compression**. The main examples use **Spring Boot 3.3.x, Java 17+, Spring MVC/Servlet**, explaining HTTP first before applying it to controllers, static resources, gzip compression, proxy/CDN, common pitfalls, and tests. Note the distinction: **HTTP caching is not equivalent to Spring Cache (@Cacheable)**; ETag does not automatically cache data in the database, and 304 does not automatically eliminate all server-side processing.

## 1. Objectives and Prerequisites

After completing this lesson, you will be able to:

1. State the roles of **ETag**, **Last-Modified**, **Cache-Control**, **If-None-Match**, **If-Modified-Since**, and how they work together.
2. Distinguish **freshness** (cache is still fresh and reusable without asking the server) from **validation/revalidation** (asking the server whether the cached copy has changed).
3. Explain accurately when the server returns **200**, **304**, **412**; why 304 has no response body and does not mean the resource is empty.
4. Distinguish **strong ETag** and **weak ETag**; understand the one-second precision limit of HTTP-date and the precedence order among HTTP preconditions.
5. Create a Spring MVC endpoint returning **ResponseEntity** with ETag, Last-Modified, and Cache-Control; test conditional GETs with **MockMvc**.
6. Know how to use **WebRequest.checkNotModified(...)** to check validators early, and understand the limitations of **ShallowEtagHeaderFilter**.
7. Avoid risks when APIs require authentication, have multiple JSON/language representations, return gzip/brotli, or pass through a proxy/CDN.
8. Design validators stable enough across clusters/rolling deploys yet responsive whenever content genuinely changes.

Prerequisites: HTTP requests/responses, headers, status codes, REST controllers, JSON, Java 17, Spring Boot Maven/Gradle, and calling APIs with curl.

## 2. Two Different Problems: Cache Freshness and Cache Validation

### 2.1. Freshness: Using the Cache Immediately While Fresh

When the server returns:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=600
ETag: "catalog-v7"
Content-Type: application/json

{"version":7,"items":["A","B"]}
~~~

**max-age=600** indicates that the response can be considered fresh for up to 600 seconds under HTTP caching rules. When the cache is eligible and still fresh, the client or intermediate cache **can return the stored copy without sending a request to the origin**. Because no request is sent, there is no 304; this saves an entire network round-trip and can reduce origin load.

Cache-Control is the **policy**; ETag is the **validator**. Having an ETag does not guarantee browsers always store the response, and having cache headers does not guarantee reuse in every scenario (it still depends on method, status, Vary, private/public, cache implementation, authentication, and other policies).

### 2.2. Revalidation: Checking the Old Copy When Needed

When the cached copy is stale or the policy requires revalidation, the cache sends:

~~~http
GET /api/catalog HTTP/1.1
Host: localhost:8080
If-None-Match: "catalog-v7"
~~~

The server computes or looks up the current validator:

- If the selected representation **is still equivalent** to the client's validator, it responds **304 Not Modified** with appropriate cache metadata, **without resending the body**.
- If there is a change, it responds **200 OK** with a **new ETag** and new content (provided the request is valid and authorized).
- If the request must return 401, 403, 404, or another normal error, preconditions do not turn that error into 304 merely because the client previously held an ETag.

Flow:

~~~text
Request 1: GET /api/catalog
        |
        v
200 OK + ETag: "catalog-v7" + JSON body
        |
        v
Client/cache stores body + metadata (if permitted)

Request 2: GET + If-None-Match: "catalog-v7"
        |
        +-- current representation is still v7
        |       |
        |       v
        |     304 Not Modified + useful headers, NO body
        |       |
        |       v
        |     cache reuses JSON body from previous response
        |
        +-- representation has become v8
                |
                v
              200 OK + ETag: "catalog-v8" + v8 body
~~~

**304 is only useful if the client/cache already has a representation to reuse.** Running a single curl command with If-None-Match without having stored an old body will show an empty 304; this does **not** mean the API returns empty JSON. In applications, the cache layer combines 304 metadata with the stored copy.

### 2.3. Why Doesn't Every 304 Save CPU?

A validator may already exist as metadata such as a record **version**, a reliable timestamp, or a precomputed hash. In that case, the server checks early and can skip JSON serialization or expensive queries. However, if it has to build the full response and then hash the body to determine the ETag, **bandwidth is saved, yet the cost of generating content remains**. This is why we distinguish **deep/application-level ETags** from **shallow ETags**.

## 3. ETag: Validator by Representation Version

### 3.1. Syntax

ETag is a response header representing the validator of the **selected representation**:

~~~http
ETag: "product-42-v17"
ETag: W/"product-42-v17"
~~~

- **"product-42-v17"**: **strong** ETag, without the W/ prefix.
- **W/"product-42-v17"**: **weak** ETag.
- **Double quotes are part of the entity-tag syntax**. Do not send an unquoted ETag like product-42-v17.
- The inner string is chosen by the server: it can be based on revision, content hash, or a versioned key. It does not have to be a cryptographic checksum and **does not prove data integrity/authenticity**.

**Do not use ETag as a session token or secret.** ETags can expose version structure; if different users share the same URL with different content, pay attention to cache policies, Vary, and per-representation validator generation.

### 3.2. How Do Strong and Weak Differ?

| Characteristic | Strong ETag | Weak ETag |
| --- | --- | --- |
| Example | **"v17"** | **W/"v17"** |
| Meaning | Strong identification of the exact bytes of the selected representation | Two representations can be semantically equivalent even if bytes differ |
| If-None-Match | Usable; applies **weak comparison** | Usable; applies **weak comparison** |
| If-Match | Uses **strong comparison** | Does not match a strong ETag; unsuitable as an overwrite-protection precondition |
| Range/If-Range | Can use a compliant strong ETag | Weak tags are invalid as If-Range validators |
| Typical use case | Byte-stable representation whose version changes whenever bytes change | Semantically equivalent content where output details may vary |

**Strong does not mean more cryptographically secure.** Strong/weak classifies representation equivalence, not digital signature verification. A system can use a revision as a strong ETag **if** it guarantees that any transformation of the selected representation's bytes changes the validator; if the serializer, locale, or content encoding changes without changing the tag, the strong assumption breaks.

**If-None-Match uses weak comparison**, so a request can receive 304 when the client sends W/"abc" and the server has "abc" for semantically equivalent representations. **If-Match uses strong comparison**, so W/"abc" does not satisfy "abc" in a write precondition. Do not write raw string equals comparisons when implementing HTTP preconditions without handling syntax, ETag lists, wildcards, and strong/weak rules.

### 3.3. ETag Must Represent the Selected Variant

One URL may return JSON or HTML, Vietnamese/English, differently sized images, or gzip/uncompressed versions. The validator should reflect the **selected representation**, not just the resource name.

Bad example:

~~~text
GET /api/report?lang=vi -> Vietnamese body, ETag "report-v3"
GET /api/report?lang=en -> English body, ETag "report-v3"
~~~

If two different byte bodies advertise the **same strong ETag**, clients/caches can reuse the wrong variant. Fix: encode the variant (lang/media type/schema/version) into the validator, use weak semantics when truly equivalent, or adjust URL/Cache-Control/Vary appropriately.

Do not assume a "hash of the database row" is always sufficient for a strong ETag: JSON can contain computed fields, schema changes, formatters, authorization-specific columns, and content negotiation that differ from the raw row.

### 3.4. ETag Is Not an Automatic Stale-Write Guard

ETag is used for **GET cache validation** when the client sends If-None-Match, and can also be used for **concurrency control** when the client writes and sends If-Match. A **GET /resource** having an ETag does not automatically make **PUT /resource** reject stale updates; the server must **enforce the write precondition** before committing.

## 4. Last-Modified: Timestamp-Based Validator

### 4.1. HTTP-date Syntax

~~~http
Last-Modified: Tue, 02 Jan 2024 03:04:05 GMT
~~~

**Last-Modified** indicates when the representation was last modified according to server metadata. Clients can send **If-Modified-Since**:

~~~http
GET /api/catalog HTTP/1.1
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

If the selected resource's last modification time is **not later than** the value sent by the client, the server can reply **304** (for GET/HEAD). If the modification time is newer, it returns a normal response, such as **200 + body + new Last-Modified**.

Regarding Last-Modified:
- HTTP-date is transmitted at **second** resolution, not milliseconds or nanoseconds.
- Timestamps should come from a reliable source kept consistent across instances and data versions.
- Do not generate Last-Modified via **Instant.now() on every request**, as the validator would constantly change even when content does not.
- Do not report a Last-Modified in the future relative to when the response is generated; RFC 9110 specifies handling for future time metadata.
- If no reliable modification time exists, do not fabricate one just to always emit the header.

### 4.2. Limitations of Second-Resolution Validators

Suppose an article is updated twice within the same second: HTTP-date can remain unchanged even though bytes changed. Or clocks on two servers drift apart, causing Last-Modified to jump forward/backward unexpectedly.

Therefore:
- For frequently changing resources or strict write preconditions, **revision/ETag is more suitable**.
- When using **If-Unmodified-Since** to prevent overwrites, be aware of its lower precision compared to If-Match.
- Do not automatically use build/deploy timestamps as Last-Modified for a business resource if data can change independently of deployments.
- You can send **both ETag and Last-Modified** when good metadata is available; modern clients usually prefer ETag for revalidation.

### 4.3. Last-Modified Is Not Last-Accessed

Last-Modified describes **when the data/representation was changed**; it is not when the client last accessed it, is unrelated to HttpSession idle timeout, and is not when the response was last cached.

Do not set Last-Modified=current request time to “make it look fresh”; when content is unchanged, this destroys the benefit of conditional GETs.

## 5. Conditional Request Headers and Status Codes

| Request header | Purpose | Comparison / key outcome |
| --- | --- | --- |
| **If-None-Match** | Execute only if **no** matching tag exists; GET revalidation | Uses weak comparison. Match on GET/HEAD → **304**; match on other methods → **412**. |
| **If-Modified-Since** | GET/HEAD only if resource is newer than the given time | If not newer → **304**; evaluated only when no valid If-None-Match is present. |
| **If-Match** | Execute only if current representation matches tag | Uses **strong comparison**; mismatch usually → **412**, especially for PUT/PATCH/DELETE. |
| **If-Unmodified-Since** | Execute only if representation has not changed after given time | If changed, usually → **412**; ignored when If-Match is present. |
| **If-Range** + **Range** | Resume a partial resource download if validator still matches | Match → possibly **206 Partial Content**; mismatch → ignore Range and return full **200**. |
| **If-None-Match: *** | Typically used to create a resource only if it does not exist yet | If a representation exists and method is not GET/HEAD → **412**, useful to prevent overwrites on creation. |

### 5.1. What Do 200, 304, and 412 Communicate?

**200 OK**: the server sends the new/requested representation for a valid GET; has a body for GET (possibly empty if the resource is inherently empty). A conditional GET whose validator does not match still normally returns 200.

**304 Not Modified**: intended for **conditional GET/HEAD** when the client already has a reusable copy. **Must not send a body or trailers in 304**. The response needs appropriate updated cache metadata; per RFC 9110, the origin must send required fields among **Date, ETag, Vary, Content-Location, Cache-Control, Expires** if they would also be sent in the corresponding 200. Last-Modified is also useful when updating cache metadata.

**412 Precondition Failed**: the request failed a precondition, especially on PUT/PATCH/DELETE using **If-Match** or **If-Unmodified-Since**. Do not use 304 to tell a **PUT** it failed due to ETag. Use 412 so the client knows to fetch the current version before updating.

**404 Not Found / 401 Unauthorized / 403 Forbidden**: normal resource/authorization errors still take precedence over conditional requests. Knowing a previous ETag **does not grant access rights**. Authentication and authorization checks must occur before providing data or confirming private state.

**428 Precondition Required**: depending on API design, the server can require clients to always send If-Match before updating protected resources; this is an optional design rule, distinct from 412.

### 5.2. Precedence When Multiple Headers Appear Together

RFC 9110 defines precondition evaluation order; do not pick whichever condition you prefer in arbitrary order in Java code:

1. **If-Match** first; only if absent, evaluate **If-Unmodified-Since**.
2. Next, **If-None-Match**.
3. For GET/HEAD **without If-None-Match**, evaluate **If-Modified-Since**.
4. Finally, for GET with Range and If-Range, handle range validation accordingly.

Example:

~~~http
GET /api/articles/42 HTTP/1.1
If-None-Match: "old"
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

Suppose the current tag is **"article-42-v7"**, and Last-Modified equals the date above. **If-None-Match does not match**, so the request should proceed to **200 OK** with the body; do not use If-Modified-Since to automatically return 304. ETag takes precedence over the date validator for cache revalidation.

Conversely, if If-None-Match matches, GET can receive 304 even if If-Modified-Since is much older. The server should not “AND” these two checks together.

### 5.3. Weak Comparison Differs from Strong Comparison

~~~http
ETag: "rev-8"
If-None-Match: W/"rev-8"
~~~

With **If-None-Match**, weak and strong versions of the same tag match under **weak comparison**, so a conditional GET can receive 304.

~~~http
ETag: "rev-8"
If-Match: W/"rev-8"
~~~

With **If-Match**, strong comparison does not allow a weak tag to match. If a client uses a weak ETag as a write precondition, the result is typically **412**. Do not write logic that strips W/ before comparing every condition; doing so breaks the safety semantics of If-Match.

## 6. How Does Cache-Control Interact with Validators?

### 6.1. Common Directives

| Cache-Control | Basic meaning | When to use |
| --- | --- | --- |
| **max-age=600** | Caches may treat the response as fresh for a limited duration | Public, rarely changing content allowing reuse without asking the server. |
| **no-cache** | May **store**, but must **revalidate before reuse** | When keeping the old copy for 304 while always checking the origin before use. |
| **no-store** | Must not store request/response per cache policy | Sensitive personal content, tokens, pages containing secrets. |
| **private** | Only private caches (e.g., browsers) may store; shared proxies must not reuse | Per-user content if policy permits caching. |
| **public** | Allows shared caches to store per HTTP rules | Truly public resources with proper keys/variants. |
| **immutable** | Signals content will not change during freshness lifetime | Assets with hash/content-versioned names whose URL never changes content. |

**no-cache differs from no-store.** Setting **Cache-Control: no-cache** alongside an ETag can be very effective: the browser keeps the body but sends If-None-Match whenever it wants to reuse it; if unchanged, the server sends 304. With **no-store**, the cache does not keep the body, so normal revalidation has no purpose.

For authenticated JSON, **private, no-cache** can fit when browser caching is desired without sharing through proxies. For highly sensitive data, use **no-store**, accepting that you won't get 304 benefits from caches. Base the decision on sensitivity, legal policies, and logout behavior, not performance alone.

### 6.2. HTTP Caching Differs from Spring Cache (@Cacheable)

**HTTP caching** lives in browsers, reverse proxies, CDNs, and clients; it uses headers like Cache-Control, Vary, ETag, Last-Modified, and status 304.

**Spring Cache** such as **@Cacheable** optimizes server-side method/service/database calls. Enabling @Cacheable does not automatically generate valid ETags, does not automatically return 304, and an ETag response does not automatically cache repository queries. Both layers can be combined but require separate invalidation and consistency design.

### 6.3. Vary and Variants

~~~http
Vary: Accept-Encoding
~~~

**Vary** tells caches that the response can differ by the listed request headers, such as **Accept-Encoding**, **Accept-Language**, or **Accept**. A strong ETag must not be blindly reused across different byte bodies.

For user-specific JSON, **Vary: Authorization** is not a magic shield to protect data: you must use **private/no-store** cache policies and proper keying to avoid shared caches storing/reusing personal responses. In environments with cookies, sessions, and CDNs, explicitly design cache ownership.

## 7. Complete Example: ResponseEntity with ETag + Last-Modified

The sample application serves an article **kept fixed in code for demonstration**. This ensures deterministic test results and demonstrates how MVC automatically handles conditional GETs from ResponseEntity headers. In a real application, obtain **version and lastModified** from the same data snapshot and update them whenever the representation changes.

### 7.1. Create the Project

Create a Maven project from **https://start.spring.io** with **Java 17**, Spring Boot **3.3.x**, group **com.example**, artifact **http-validator-demo**, package **com.example.httpvalidator**, and dependencies **Spring Web** and **Spring Boot Starter Test**. You can use the Maven wrapper from the project.

Structure:

~~~text
http-validator-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/httpvalidator/
    HttpValidatorApplication.java
    ArticleController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/httpvalidator/
    ArticleControllerTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>http-validator-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

The Spring Boot parent manages Spring MVC, Jackson, Servlet, and test library versions. The version is pinned as a learning baseline; in real deployments use a patch version supported and maintained by your organization, and avoid arbitrarily upgrading Spring Framework incompatibly on its own.

### 7.3. Main Class

**src/main/java/com/example/httpvalidator/HttpValidatorApplication.java**

~~~java
package com.example.httpvalidator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpValidatorApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpValidatorApplication.class, args);
    }
}
~~~

### 7.4. Controller with Stable Validators

**src/main/java/com/example/httpvalidator/ArticleController.java**

~~~java
package com.example.httpvalidator;

import java.time.Instant;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ArticleController {
    private static final Instant LAST_MODIFIED =
            Instant.parse("2024-01-02T03:04:05Z");

    private static final String ARTICLE_ETAG = "\"article-42-v7\"";

    public record Article(long id, String title, long version) { }

    @GetMapping("/api/articles/{id}")
    public ResponseEntity<Article> getArticle(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        Article article = new Article(42L,
                "HTTP conditional requests", 7L);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache().cachePrivate())
                .eTag(ARTICLE_ETAG)
                .lastModified(LAST_MODIFIED.toEpochMilli())
                .body(article);
    }
}
~~~

**Explanation of key lines:**

1. **ARTICLE_ETAG** includes double quotes per entity-tag syntax. ResponseEntity.BodyBuilder.eTag(...) can also add quotes if needed; the demo declares it in canonical form.
2. **LAST_MODIFIED** is fixed to keep tests deterministic. For real resources, retrieve the update timestamp stored in the DB or reliable metadata; do not use **Instant.now()** on every call.
3. **CacheControl.noCache().cachePrivate()** lets private caches keep the body while requiring revalidation, and disallows sharing in shared proxies.
4. **ResponseEntity** gives Spring MVC the ETag/Last-Modified info to support conditional GETs. If the request carries a matching validator, MVC can return **304** without writing the body. However, the sample code still constructs the **Article** object before ResponseEntity finishes; this is **not yet a deep CPU optimization strategy**.
5. **404** for any id other than 42 remains 404, regardless of whether the client sends If-None-Match. Validators must correspond to a selected representation that actually exists.
6. The sample does not access a database or perform authentication; do not use this code as a production API without adding authorization, a data source, and version consistency.

With real data, if the same URL has multiple representations by language or Accept, include the variant in the ETag or choose another caching strategy. If the title changes while version stays 7, the example's strong ETag is **no longer valid**; always update the version when the representation changes.

### 7.5. Runtime Configuration

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: http-validator-demo

server:
  port: 8080
~~~

There is no global Spring Boot property to "enable ETag for all controllers". Controllers/code decide validators, or you can use a filter for shallow ETags as needed. In the example, ETag/Last-Modified headers are produced by ResponseEntity.

### 7.6. Run and Test with curl

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows:

~~~text
mvnw.cmd spring-boot:run
~~~

Or package:

~~~bash
./mvnw clean package
java -jar target/http-validator-demo-0.0.1-SNAPSHOT.jar
~~~

Normal call:

~~~bash
curl -i http://localhost:8080/api/articles/42
~~~

Response has status **200**, ETag **"article-42-v7"**, Last-Modified **Tue, 02 Jan 2024 03:04:05 GMT**, Cache-Control in the form **no-cache, private** or equivalent, and JSON body:

~~~json
{"id":42,"title":"HTTP conditional requests","version":7}
~~~

Verify ETag (conditional GET):

~~~bash
curl -i -H 'If-None-Match: "article-42-v7"' \
  http://localhost:8080/api/articles/42
~~~

On Linux/macOS, this command normally receives **304 Not Modified** with **no body**. On Windows CMD, quoting syntax differs; you can use PowerShell with `curl.exe` and shell-appropriate quote escaping, or Postman/an HTTP client to avoid shell quoting errors.

Verify Last-Modified:

~~~bash
curl -i -H 'If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT' \
  http://localhost:8080/api/articles/42
~~~

Expect **304** because the resource time is not newer than the sent timestamp. If you change the request to **If-None-Match: "old"**, the response should be **200** with the body.

Verify precedence rules:

~~~bash
curl -i \
  -H 'If-None-Match: "old"' \
  -H 'If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT' \
  http://localhost:8080/api/articles/42
~~~

Expect **200**, because when If-None-Match is present and does not match, If-Modified-Since must not be used to return 304. If the actual response differs from expectations, inspect proxies/filters/containers and whether HTTP headers were quoted properly by the shell.

### 7.7. MockMvc: Testing Status, Body, and Precondition Precedence

**src/test/java/com/example/httpvalidator/ArticleControllerTest.java**

~~~java
package com.example.httpvalidator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ArticleControllerTest {
    @Autowired
    MockMvc mvc;

    private static final String PATH = "/api/articles/42";
    private static final String ETAG = "\"article-42-v7\"";
    private static final String MODIFIED =
            "Tue, 02 Jan 2024 03:04:05 GMT";

    @Test
    void normalGetReturnsBodyAndValidators() throws Exception {
        mvc.perform(get(PATH))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ETAG, ETAG))
                .andExpect(header().string(
                        HttpHeaders.LAST_MODIFIED, MODIFIED))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void matchingETagReturns304WithoutBody() throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void unchangedDateReturns304WithoutBody() throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_MODIFIED_SINCE, MODIFIED))
                .andExpect(status().isNotModified())
                .andExpect(content().string(""));
    }

    @Test
    void ifNoneMatchTakesPriorityOverIfModifiedSince()
            throws Exception {
        mvc.perform(get(PATH)
                .header(HttpHeaders.IF_NONE_MATCH, "\"older\"")
                .header(HttpHeaders.IF_MODIFIED_SINCE, MODIFIED))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                        .value("HTTP conditional requests"));
    }

    @Test
    void missingResourceRemains404() throws Exception {
        mvc.perform(get("/api/articles/99")
                .header(HttpHeaders.IF_NONE_MATCH, ETAG))
                .andExpect(status().isNotFound());
    }
}
~~~

Run tests:

~~~bash
./mvnw test
~~~

This is a **Spring MVC layer integration test** using MockMvc; it verifies headers/status/body and validator check order through Spring MVC. It **does not** test CDN behavior, browser caching, network-connector gzip, or real reverse proxies. Those require HTTP integration tests in the deployment environment.

**Output verification accuracy:** The JSON body in the example has 3 fields with fixed values. **304 has no body**; `curl -i` will only display headers and a blank line, without printing old JSON because curl is not a browser cache. Date, Connection, Content-Length, and Transfer-Encoding headers may vary by server/HTTP version; do not write tests depending on every default header byte.

## 8. WebRequest.checkNotModified: Evaluating Before Building an Expensive Body

For large resources, if the controller serializes the entire JSON/HTML before hashing, 304 may only save bandwidth. Spring MVC provides **WebRequest.checkNotModified(...)** to check conditions as soon as cheap metadata is retrieved.

Example **illustrative method snippet inside a @Controller with a service/repository**, not a standalone Java file:

~~~java
@GetMapping("/articles/{id}")
public String viewArticle(
        @PathVariable long id,
        WebRequest webRequest,
        Model model) {

    ArticleMetadata metadata = articleService.metadata(id);

    String etag = "\"article-" + id
            + "-v" + metadata.version() + "\"";
    long lastModifiedMillis =
            metadata.updatedAt().toEpochMilli();

    if (webRequest.checkNotModified(etag, lastModifiedMillis)) {
        return null; // Spring has prepared the conditional response.
    }

    model.addAttribute("article",
            articleService.loadFullArticle(id));
    return "article";
}
~~~

Requires importing **org.springframework.web.context.request.WebRequest**, **org.springframework.ui.Model**, **@GetMapping**, **@PathVariable**, and real domain types. **articleService.metadata** must be authorized for reading and return metadata for the exact selected resource/variant; do not invent dummy implementations just to make this snippet look standalone.

The benefit is that **loadFullArticle(...)** is only called when the body needs to be built. Still, conditions apply:
- Authentication/authorization must happen before disclosing any resource info, including validators.
- Metadata and body must be consistent; if the resource changes between the two queries, the tag could describe v7 while the body is v8.
- You can use a transaction snapshot, version check, or re-read metadata if consistency guarantees are required.
- **checkNotModified(...)** has overloads for ETag, lastModified, or both; Spring handles conditional GET/HEAD scenarios, and certain preconditions on mutating methods can result in 412.
- Do not return null arbitrarily with response-body methods without understanding the framework contract; the Spring MVC View Controller example above follows the pattern documented in the reference guide.

**ResponseEntity.eTag(...)** in section 7 is concise when the controller already holds a cheap representation. **WebRequest.checkNotModified(...)** is typically useful when metadata is many times faster to fetch than the body.

## 9. ShallowEtagHeaderFilter: Saves Bandwidth, Does Not Save Processing by Default

Spring Framework's **ShallowEtagHeaderFilter** computes an ETag from the **generated response bytes**, typically using MD5, and compares it against If-None-Match. If it matches, the client can receive **304** without downloading the body again.

Model:

~~~text
Controller/service runs, produces response
          |
          v
Filter buffers response body
          |
          v
Computes shallow ETag over body
          |
          +-- If-None-Match matches -> 304, no body sent
          |
          +-- no match -> sends normal response + ETag
~~~

**Advantages:** minimal controller code, reduces bytes transferred over the network when large responses are unchanged.

**Important limitations:**
- The full response has already been computed before the filter compares, so **it does not significantly save CPU/DB/serialization**.
- Buffering can increase memory overhead and is unsuitable to apply blindly to very large or streaming responses.
- This filter is **not** a complete solution for **If-Match / If-Unmodified-Since** on update APIs.
- For async Servlet requests, the filter needs to be mapped for **DispatcherType.ASYNC** to work properly across async dispatches.
- If the response body varies by user/language/encoding, ETags and cache policies must reflect the variant; never let shared caches reuse wrong data.
- MD5 in shallow ETag here is a way to detect body changes to save bandwidth, **not a security signature** or tamper-proof checksum.

For expensive data APIs, prefer **application-level version/ETag + early conditional checks**. For static assets, deliberately use resource handlers/versioned URLs, Cache-Control, and Last-Modified/ETag rather than adding a broad filter without measuring performance.

## 10. Static Resources: Last-Modified, ETag, and Versioned URLs

Spring MVC **ResourceHttpRequestHandler** can serve static resources (CSS, JS, images, fonts) and use **Resource.lastModified()** metadata to support **Last-Modified/If-Modified-Since** where available. With default Spring Boot web, files in classpath:/static/, classpath:/public/, etc. can be served via static resource mappings; actual configuration affects cache headers.

Example **WebMvcConfigurer** configuration solely to illustrate a dedicated handler for public assets:

~~~java
package com.example.httpvalidator;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AssetConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/assets/")
                .setCacheControl(CacheControl.maxAge(
                        Duration.ofMinutes(10)).cachePublic());
    }
}
~~~

This snippet is **a standalone Java file in section 7's sample project** if placed in the right package. When adding it, put CSS files in **src/main/resources/assets/css/app.css**; the public URL is **/assets/css/app.css**. If unnecessary, do not register a custom handler; Spring Boot provides default static locations.

**Caching recommendations:**
- **Unversioned** assets whose content can change at the same URL: use short caches or no-cache/revalidation.
- Assets **with content hashes in the URL** (e.g., /assets/app.7d2e5c.css): can use long caching and **immutable** if the URL always changes when bytes change and the release pipeline does not delete old versions too soon.
- **index.html** of an SPA usually needs short caching or revalidation because it references new bundles.
- User-private files should not be placed in the public static root.

Spring MVC provides **VersionResourceResolver** to generate/support content-based versioned URLs. When using **EncodedResourceResolver** together with **VersionResourceResolver** to serve gzip/brotli pre-encoded files, Spring Framework documentation recommends registering **EncodedResourceResolver before VersionResourceResolver** so versions are stably computed from the unencoded resource. Do not confuse asset fingerprint URLs (cache busting) with ETag headers: they solve related problems, not the same one.

## 11. HTTP Compression, Vary, and ETag Correctness

### 11.1. Enabling Compression in Spring Boot

With **Spring Boot 3.3**, HTTP response compression can be enabled:

**src/main/resources/application.yml** (**optional** configuration, not required for small demos):

~~~yaml
server:
  compression:
    enabled: true
    min-response-size: 2KB
    mime-types: application/json,text/html,text/plain,text/css
~~~

Depending on server/config, gzip is negotiated when the client sends an appropriate **Accept-Encoding** and the response meets the minimum size and MIME type. Spring Boot supports compression on Tomcat, Jetty, Reactor Netty, and Undertow. In Boot 3.3, the default minimum is typically **2 KB**. The JSON demo in section 7 is too small and therefore may **not be compressed** even with enabled=true.

### 11.2. Compression and Validation Optimize Two Different Things

- **Compression (gzip/brotli):** reduces the **number of bytes in the body** when the body must be sent.
- **ETag/Last-Modified/304:** can avoid **sending the body altogether** when the cached copy is still valid.
- **Cache freshness:** can avoid **sending a request** to the origin while the response is still fresh.

These three layers complement each other; they are not the same technique. A 304 has no body to gzip; a gzipped 200 still transmits the compressed body; a fresh cache hit may never touch the Spring Boot server.

### 11.3. Vary: Accept-Encoding

When both gzip and identity (uncompressed) versions exist, caches must distinguish representations:

~~~http
Vary: Accept-Encoding
Content-Encoding: gzip
ETag: "article-v7-gzip"
~~~

If the server returns the uncompressed copy:

~~~http
Vary: Accept-Encoding
ETag: "article-v7-identity"
~~~

The example uses **distinct strong ETags** to illustrate that representation body bytes after content coding are not identical. Per HTTP semantics, a **strong validator must be valid for the selected representation**; do not let two byte-different gzip/identity variants share the same strong tag merely because the decompressed JSON matches. A **weak ETag** may be more appropriate when only wishing to indicate semantic equivalence across variants.

**Note:** Specific headers produced by a real Servlet container/proxy may differ from the example above. Do not claim Spring Boot automatically generates the string "article-v7-gzip"; that is an illustrative tag from a variant-aware system. If using ETags in controllers and letting a proxy compress the body, verify the proxy/container adjusts ETag and Vary properly rather than copying one strong tag across different byte streams.

### 11.4. Common Bugs After Enabling gzip/CDN

1. Client reports 304, yet cached body does not match the requested representation.
2. Same URL returns compressed/uncompressed variants without **Vary: Accept-Encoding**.
3. Proxy alters Content-Encoding without adjusting validators or cache keys properly.
4. ETag changes on every deploy despite unchanged content, defeating 304.
5. ETag **does not change** when schema/locale/serializer changes, risking incorrect reuse.
6. Small responses below **min-response-size** lead to the false conclusion that compression is off.
7. CDN caches user-specific JSON because the application set an inappropriate **public, max-age**.

Debug by comparing **status, ETag, Last-Modified, Vary, Cache-Control, Content-Encoding, Content-Type** across multiple real requests with different Accept-Encoding values. Use **curl --compressed -i** to inspect gzip; when a reverse proxy is present, test both the origin directly (where permitted) and the URL via proxy/CDN.

## 12. Caching with Dynamic Data and Concurrent Updates

### 12.1. ETag Derived from Business Version

Suppose an article has revision 7:

~~~http
GET /api/articles/42 HTTP/1.1

HTTP/1.1 200 OK
ETag: "article-42-v7"
Content-Type: application/json

{"id":42,"title":"Draft A","version":7}
~~~

A user edits the content and sends:

~~~http
PUT /api/articles/42 HTTP/1.1
If-Match: "article-42-v7"
Content-Type: application/json

{"title":"Draft B"}
~~~

If the data is still at version 7, the server can perform a conditional update and bump to v8:

~~~http
HTTP/1.1 200 OK
ETag: "article-42-v8"
Content-Type: application/json

{"id":42,"title":"Draft B","version":8}
~~~

If someone else already updated to v8 beforehand, the request carrying **If-Match: "article-42-v7"** is no longer valid: the server typically returns **412 Precondition Failed**, without overwriting.

**Very important:** To prevent races, do not simply **read version → compare → UPDATE** in three separate unsynchronized operations. Two requests could both read v7 and overwrite each other. Use **optimistic locking (@Version in JPA)**, version-conditional UPDATE, or sufficiently strong transactions/locking, and translate version conflict errors into a 412 response per the API contract.

### 12.2. Distinguishing 412 from 409 and 428

- **412 Precondition Failed:** the client sent an HTTP precondition and it was not satisfied.
- **409 Conflict:** a business state conflict that may occur without necessarily involving a precondition header; choose per specific contract.
- **428 Precondition Required:** the API requires clients to supply a precondition such as If-Match to curb lost updates; use when that is an intentional policy.

Do not default every failed update due to validation to 412. For input validation errors, 400/422 or an appropriate domain status fits better. For access rights, 401/403 remain essential.

### 12.3. If-None-Match: * on Creation

If a client wants to create a resource **only if it does not already exist**, it can send the precondition:

~~~http
PUT /api/articles/100 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"title":"New article"}
~~~

If a representation already exists, the precondition fails and an unsafe request typically receives **412**. Existence checking must be implemented **atomically** in the database/storage; do not use "check first then insert" if two clients can race to create the same ID.

### 12.4. Last-Modified for Conditional Updates

**If-Unmodified-Since** can support cases where a client lacks an ETag, though second-resolution HTTP-date timestamps may not distinguish closely timed edits. When serious lost-update protection is needed, prefer **If-Match with a strong ETag** tied to a consistently maintained revision.

## 13. Conditional Requests with HEAD, Range, and Streaming

### 13.1. HEAD

**HEAD** matches GET in metadata but **sends no response body**. A conditional HEAD can still receive 304 per HTTP semantics. However, a 200 HEAD also has no body, so data savings from conditional HEAD are usually minimal; RFC 9110 notes there is rarely a reason to use conditional HEAD.

Do not inspect HEAD's empty body to conclude a resource is empty.

### 13.2. Range and If-Range

For large files, a client may send:

~~~http
GET /downloads/big-file.zip HTTP/1.1
Range: bytes=1000-1999
If-Range: "file-v12"
~~~

If If-Range is a matching strong validator, the server can return **206 Partial Content** with the requested byte range. If the validator does not match, the server **ignores Range** and returns **200** with the full new copy, rather than 412 in the If-Range case.

Do not use a weak ETag as If-Range. If an application does not support byte ranges, it may return 200; do not write complex Range logic just to produce 304 for ordinary JSON APIs.

### 13.3. SSE, Streaming, File Uploads

For streaming/SSE, responses may never finish or may change continuously; shallow ETag buffering the entire response is usually unsuitable. For large file uploads/downloads, validators must accurately match bytes and Content-Encoding/Range. For precondition-guarded uploads, enforce authorization and atomic persistence before confirming success.

## 14. Security and Personal Data Issues

HTTP caching is an external layer that can sit in browsers, CDNs, or reverse proxies. Never let revalidation or ETags become a bypass around authorization:

- **Verify access rights before returning 304** for private resources. A client holding an old ETag does not retain permission to view data after access is revoked.
- Account data, health/financial info, or sensitive content should prioritize **Cache-Control: no-store** per policy, rather than public caches.
- If browser caching of user-specific data is allowed, use **private** and verify logout/session/account switching; never let a shared proxy reuse another person's body.
- Do not put tokens, emails, easily guessable sensitive data, or hashes that leak secrets via side channels into ETags.
- Do not use ETag as a CSRF token, session ID, or authentication mechanism.
- **401/403/404** responses must preserve their appropriate status/body, not turn into 304 when authentication conditions are no longer met.
- If cache keys are URL-based while data varies by header/tenant/user, design Vary, Cache-Control, and edge cache configurations properly; do not simply emit an ETag and hope the CDN infers tenants.

Public static resources are much better candidates for shared caching. APIs with JWT/cookies/sessions require dedicated policies.

## 15. Debugging Common ETag/Last-Modified Issues

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| **Every GET is 200 even when content hasn't changed** | No validator, request lacks If-None-Match, ETag changes every call, cache doesn't store body | Compare ETag across 2 responses; inspect Cache-Control, request headers, and Vary. |
| **304 yet curl shows no JSON** | 304 sends no body per HTTP | Cache uses body from prior 200; standalone `curl -i` is not a browser cache. |
| **Last-Modified is always the current time** | Code uses Instant.now() per request | Use the real modification time from resource/version. |
| **Data changed yet still 304** | Tag/version not incremented, ETag omits variant, stale proxy cache | Compare body, version, locale, Accept, Content-Encoding, and CDN metadata. |
| **If-None-Match didn't match yet 304 returned** | Code evaluated If-Modified-Since in wrong order | Follow RFC 9110: If-None-Match takes precedence over If-Modified-Since. |
| **PUT with weak If-Match still updated** | Stripped W/ before string comparison instead of strong comparison | Fix precondition parser/logic; verify transaction concurrency. |
| **ETag changes after every deploy despite identical body** | Relies on build timestamp/random ID/unstable JSON key order | Base on stable version/hash of selected representation. |
| **CPU remains high despite many 304s** | ShallowEtagHeaderFilter still builds the body | Fetch cheap metadata and check conditions before serializing. |
| **Enabling gzip broke caching** | Shared strong ETag across gzip and identity; missing Vary | Check Content-Encoding/Vary; differentiate validators by representation. |
| **CDN caches wrong user's account data** | Wrong public Cache-Control, key missing user/variant, authorization skipped | Use no-store/private, fix edge policy, and purge bad entries. |
| **If-Modified-Since never returns 304** | Invalid Last-Modified sent, timestamp changes per request, method not GET/HEAD | Verify HTTP-date, stored time, method, ETag precedence. |
| **Static asset lacks ETag** | Resource handler may only support Last-Modified, filter not enabled | Inspect actual response; Last-Modified suffices for many use cases. |
| **Range download corrupted after update** | Client stitched bytes from two versions | Use strong validator with If-Range or restart full download. |
| **Tests pass yet browser still reloads** | MockMvc does not simulate browser cache/proxy | Check Network tab: memory/disk cache, request headers, response policy. |
| **304 appears after user logs out** | Auth/cache bypassed or test observing 304 from cache | Check response source, origin authorization, and private/no-store policy. |

### Layer-by-Layer Verification Workflow

1. **Origin:** call Spring Boot directly where permitted; record status, ETag, Last-Modified, Cache-Control, Vary.
2. **Conditional request:** resend If-None-Match and If-Modified-Since; note 304/200 and body. Verify precedence when both are present.
3. **Data change:** actually update the resource and prove ETag/Last-Modified change accordingly; do not test only immutable datasets.
4. **Browser:** DevTools Network to see whether requests are sent or served directly from memory/disk cache.
5. **Proxy/CDN:** compare edge responses with origin; note the edge may return 304 or cached 200 without calling origin.
6. **Compression/variants:** test Accept-Encoding, Accept-Language, Accept; verify Content-Encoding, Vary, and validators.
7. **Security:** test unauthenticated, revoked access, and between two different users; ensure no body/304 leaks.
8. **Metrics:** measure bytes transferred, 304 rate, response generation time, DB queries, and cache hit rates separately. Many 304s alone do not prove CPU dropped.

## 16. Practice Exercises

### Exercise 1: Distinguish Freshness and Revalidation

Suppose the server returns **Cache-Control: public, max-age=120** and **ETag: "v9"**.

- After 30 seconds, a compliant browser cache can reuse the response without calling the origin.
- After becoming stale, the browser can send **If-None-Match: "v9"**.
- If version is still v9 → 304 without body; if v10 → 200 with new body.
- Explain why you cannot require “every cache hit returns 304”: fresh cache hits do not necessarily send a request.

### Exercise 2: Header Precedence

The server has **ETag: "x2"** and **Last-Modified** matching the date sent by the client. The client sends:

~~~http
GET /api/data HTTP/1.1
If-None-Match: "x1"
If-Modified-Since: Tue, 02 Jan 2024 03:04:05 GMT
~~~

According to semantics, the outcome should be **200** if nothing else prevents it, because If-None-Match does not match and takes precedence over If-Modified-Since.

### Exercise 3: Preventing Lost Updates

Clients A and B both read resource v4. A updates it to v5 with **If-Match: "v4"**. B sends a stale update with **If-Match: "v4"** afterward. Design an atomic version-checked repository update and return 412 to B. Explain why checking the version then running an UPDATE without locking/optimistic versioning is insufficient.

### Exercise 4: Choosing Cache Policies

Choose a policy for: **public versioned JS**, **SPA index HTML**, **public search results API**, **personal bank statement API**. Explain why hashed assets can be cached long-term/immutable while a personal statement API needs no-store or a very strict policy.

### Exercise 5: Testing Compression and Validators

Increase the JSON response size, enable compression, and call with a gzip-accepting client. Compare **Content-Encoding**, **Vary**, **ETag**, and 200/304 statuses. Try adding a compressing proxy and verify you do not misuse strong ETags across different byte representations.

## 17. Pre-Merge or Pre-Deployment Checklist

- [ ] Every representation has a **stable and accurate** ETag or Last-Modified if conditional GET is desired.
- [ ] ETag changes when bytes/variants change; weak/strong is chosen with proper semantics.
- [ ] Last-Modified comes from real metadata, not Instant.now() on every request.
- [ ] Evaluate **If-None-Match before If-Modified-Since** and **If-Match before If-Unmodified-Since**.
- [ ] Matching conditional GET/HEAD receives 304 **with no body**; mismatches return 200/body when valid.
- [ ] PUT/PATCH/DELETE have write preconditions if lost-update protection is needed, returning 412 when unmet.
- [ ] Persistence updates are controlled atomically via optimistic locking/transactions.
- [ ] Cache-Control distinguishes **no-cache**, **no-store**, **private/public**, and TTLs by data class.
- [ ] HTTP caching is not confused with Spring Cache/@Cacheable.
- [ ] Checked Vary and validators when Accept-Encoding/gzip, Accept-Language, or content negotiation apply.
- [ ] If using ShallowEtagHeaderFilter, aware it **does not reduce body computation cost**, and evaluated streaming/async impact.
- [ ] Static assets have policies matching versioned/hashed URLs and old bundles are not deleted too early.
- [ ] Auth and authorization remain mandatory even when requests carry old ETags; private data stays out of shared caches.
- [ ] MockMvc tests for 200/304/precedence/404 pass; HTTP tests run against the real runtime when proxy/CDN/compression matter.
- [ ] Logs/metrics do not leak tokens or sensitive data; CPU and bandwidth are measured separately.

## 18. Self-Check Questions

**1. Does Cache-Control: no-cache forbid storing the response?** No. It requires revalidation before reuse. To forbid storage, use no-store.

**2. Why does 304 have no JSON body?** The client/cache already has the prior representation; 304 only confirms reusing the old copy and updates metadata. A standalone curl has no cached body to display.

**3. If both ETag and Last-Modified exist and the client sends both conditions, which takes precedence?** If-None-Match before If-Modified-Since on conditional GET. Do not combine them with custom OR/AND logic.

**4. Can a weak ETag prevent overwrites with If-Match?** Not under the strong comparison of If-Match; use a strong validator tied to an exact version.

**5. Why might a DB row version not be a valid strong ETag?** Because one row version can produce multiple byte-different bodies: locale, serializer, schema, compression, viewer permissions. The validator must reflect the selected representation.

**6. When using ShallowEtagHeaderFilter, does 304 prove the DB was not queried again?** No. The filter typically buffers and hashes the body after the controller runs, so it mainly reduces bandwidth.

**7. Can Last-Modified miss two edits within the same second?** Yes; HTTP-date has one-second resolution. When strong concurrency control is required, use version/If-Match/optimistic locking.

**8. Does Spring MVC automatically handle conditional GETs with ResponseEntity.eTag(...)?** Yes, on supported MVC execution paths; test exact status/headers/body on your target Spring Framework version.

**9. Can gzip compression make sharing the same strong ETag with uncompressed responses invalid?** Yes: if representation bytes differ, choose per-representation validators or appropriate weak semantics and Vary.

**10. Does having an ETag mean the client can view a resource after logging out?** No. ETag does not replace authorization; private resources must check permissions even when the request includes If-None-Match.

## 19. Official Documentation

1. [RFC 9110 — HTTP Semantics, Conditional Requests](https://httpwg.org/specs/rfc9110.html): defines ETag, Last-Modified, If-None-Match, If-Match, If-Modified-Since, If-Unmodified-Since, If-Range, precondition order, and 304/412.
2. [RFC 9111 — HTTP Caching](https://httpwg.org/specs/rfc9111.html): Cache-Control, freshness, revalidation, updating cached responses after 304.
3. [Spring Framework — HTTP Caching (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ResponseEntity.eTag/lastModified, CacheControl, WebRequest.checkNotModified, and Shallow ETag.
4. [Spring Framework — Shallow E Tag Filter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): ShallowEtagHeaderFilter, CPU limitations, and async dispatch.
5. [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): ResourceHttpRequestHandler, Last-Modified, ResourceResolver, and versioned URLs.
6. [Spring Boot 3.3 — Enable HTTP Response Compression](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): server.compression.enabled, min-response-size, mime-types.
7. [MDN — ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag): examples of strong/weak tags and conditional requests.

**Summary:** **Cache-Control** determines when a cached response can be used; **ETag/Last-Modified** let you ask the server whether an old copy is still valid; **304** saves bandwidth when a cached copy can be reused; **If-Match + 412** can protect concurrent updates if persistence enforces the condition atomically. In Spring Boot, prefer **validators based on stable metadata/versions**, test 200/304/412 as appropriate for your domain, and verify cache policy/Content-Encoding/Vary alongside security before going to production.