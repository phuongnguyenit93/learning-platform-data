# API Versioning Support in Spring 7: Resolution, Mapping, and Deprecation Notices

> **Scope:** Spring Framework **7.x** (Spring Web MVC on the Servlet stack) and Spring Boot **4.x**, Java 17+; resolving the API version from HTTP requests, distinguishing supported versions from mapped versions, handler selection rules with `@RequestMapping(version = ...)`, and `Deprecation` / `Sunset` / `Link` policies when retiring an API contract. This built-in API versioning feature was added in Spring Framework 7; it is **not** part of the `WebMvcConfigurer` API in Spring Framework 6.x / Spring Boot 3.x. The Java examples target Spring Framework 7.0.x, Boot 4.0.x; if using Spring 6.x you must implement your own version mapping approach or upgrade the stack in a planned manner.

## 1. Why version APIs?

An API used by clients over a long period will have to evolve. For example, on `GET /api/books`:

- Version 1 returns `{"title":"Spring"}`.
- Version 2 adds book ID, author name, or renames fields such as `{"id":1,"name":"Spring"}`.
- Older mobile apps still expect the `title` field; if the server abruptly returns a different shape without a migration path, older apps may break.
- The backend wants to announce that v1 is deprecated, giving clients time to migrate to v2 before considering retirement.

**API versioning** lets the server host multiple communication contracts simultaneously and select the response/behavior based on the version requested by the client.

```text
Client v1 --API-Version: 1.0--\
                              \
                               DispatcherServlet
                              /         |
Client v2 --API-Version: 2.0--/          v
                             ApiVersionResolver
                                      |
                             ApiVersionParser
                                      |
                           Validate supported version
                                      |
                              Handler mapping
                             /               \
                      version="1.0"      version="2.0+"
                          |                  |
                      V1 response          V2 response
                          |
                 Deprecation/Sunset hints
```

**API version is not a Maven library version:** `Spring Framework 7.0.9` is the platform version; `API-Version: 1.0` is an **application-defined contract**. Do not tie `API-Version` to the Spring Boot version or service deployment version.

**API versioning is also not the solution for every change:** many backward-compatible changes (adding optional fields, bug fixes, performance improvements) may not require a new version. Versioning should go hand in hand with compatibility rules, contract tests, and a clear lifecycle policy.

## 2. What is new in Spring Framework 7

Before Spring 7, applications often had to write their own:
- `/api/v1/books` and `/api/v2/books` on two separate paths;
- conditions like `headers="X-API-Version=1"`, query param `?v=2`, or vendor media types;
- `HandlerInterceptor` / `RequestCondition` / custom mappings for complex version handling;
- manual response headers announcing deprecation.

Spring Framework 7 introduces into MVC official configuration via `WebMvcConfigurer#configureApiVersioning(ApiVersionConfigurer)`, an `ApiVersionStrategy` coordinating the resolver, parser, validation, and deprecation handler, and the `version` attribute on request mapping annotations. <https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html>

### 2.1. Four components to distinguish

| Component | Responsibility | Used directly? |
| --- | --- | --- |
| `ApiVersionConfigurer` | Declares where to extract the version, parser, list of supported versions, missing/default policy, deprecation handler | **Yes**, inside `WebMvcConfigurer` |
| `ApiVersionResolver` | Extracts the raw version string from header, query, media type parameter, or path segment | Use built-in or custom |
| `ApiVersionParser` | Parses the raw value into a `Comparable<?>` for comparison/ordering | Default suffices for numeric versions like `1.2.3` |
| `ApiVersionStrategy` | Coordinates resolution, parsing, validation, mapping selection, and emitting deprecated version signals | Usually managed by the framework, not instantiated directly |
| `ApiVersionDeprecationHandler` | Produces deprecation/sunset metadata on response headers | Configure when managing lifecycle |
| `StandardApiVersionDeprecationHandler` | Standard implementation based on RFC 9745 and RFC 8594 | Built-in, used for lifecycle notices |

Logical flow (simplified):

```text
HTTP request
   |
ApiVersionResolver: "2.1"
   |
ApiVersionParser -> comparable version 2.1.0
   |
Validate 2.1 belongs to supported versions?
   |             \
   | yes          \ no -> InvalidApiVersionException -> 400
   v
Choose compatible @GetMapping(version=...)
   |
Execute handler (Model, service, converters...)
   |
If requested version deprecated:
  ApiVersionDeprecationHandler adds headers
   |
HTTP response
```

When API versioning is enabled, **clients must send a version by default**; omitting it triggers `MissingApiVersionException` and HTTP **400**. You can configure a default version or allow missing versions, but you must understand compatibility consequences before changing the default.

## 3. Configuring ApiVersionConfigurer in Spring MVC

The simplest approach is reading the version from the `API-Version` header.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ApiVersionWebConfig implements WebMvcConfigurer {
    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        configurer.useRequestHeader("API-Version");
    }
}
```

This is a **standalone config class snippet**, to be placed in a project with Spring Framework 7/Spring Web MVC. This API does not exist in Spring Boot 3.x managing Spring Framework 6.x.

**Key point:** calling `useRequestHeader("API-Version")` activates the versioning mechanism, yet controllers still must declare `@GetMapping(version = "1.0")` or intended compatible mappings. Adding the config does not automatically turn every endpoint into multiple versions.

### 3.1. Supported resolution strategies

| Source | Request form | Spring 7 configuration | Trade-off |
| --- | --- | --- | --- |
| Dedicated header | `API-Version: 2.0` | `configurer.useRequestHeader("API-Version")` | Stable URI; client must pass header |
| Query parameter | `GET /api/books?api-version=2.0` | `configurer.useQueryParam("api-version")` | Easy to test via URL; query is part of cache key; easy to share wrong link |
| Path segment | `GET /api/2.0/books` | `configurer.usePathSegment(1)` with path `/api/{version}/books` | Explicit in URI, easier CDN routing; prefixes must be consistent |
| Media type parameter | `Accept: application/json;version=2.0` | `configurer.useMediaTypeParameter(MediaType.APPLICATION_JSON,"version")` | Leverages content negotiation; clients/proxies must handle properly |
| Custom | Another header, composite strategy | `configurer.useVersionResolver(customResolver)` | Flexible, but must test sources, ambiguity, validation |

The table snippets are **mutually alternative approaches**; do not enable multiple resolvers simultaneously without a clear precedence/priority policy.

### 3.2. Header versioning

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version");
}
```

Client:

```bash
curl -i -H 'API-Version: 2.0' http://localhost:8080/api/books
```

This header represents the **API contract version**, not authorization. Clients choose a **supported** version; the server still checks authentication, tenant, and permissions as usual.

### 3.3. Query parameter versioning

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useQueryParam("api-version");
}
```

```http
GET /api/books?api-version=2.0
```

Define behavior when multiple query params share the same name; do not hand-roll “pick highest version” logic when the framework already provides parsers and policies. Caches, canonical links, OpenAPI, and client SDKs must send this query consistently.

### 3.4. Path segment versioning

With URL `/api/2.0/books`, 0-based path segments are typically `api` = 0, `2.0` = 1, `books` = 2:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.usePathSegment(1);
}
```

The controller path must contain a **URI variable** at the position where the version is resolved:

```java
@RestController
@RequestMapping("/api/{version}/books")
class PathBookController {
    @GetMapping(version = "2.0")
    public String booksV2() {
        return "books-v2";
    }
}
```

This is a separate controller snippet purely to illustrate the path resolver; do not merge it into the header demo in section 8. The path variable may be named something other than `version`, yet it must sit at the configured index. The path resolver does not return `null` when it cannot find a version (aside from variants taking a `Predicate<RequestPath>` to identify which paths carry versions). For applications having both `/health` and `/api/{version}/...` routes, configure the predicate/path prefix or separate routing config so non-versioned endpoints are not misparsed.

### 3.5. Media type parameter

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useMediaTypeParameter(
            MediaType.APPLICATION_JSON, "version");
}
```

```http
GET /api/books
Accept: application/json;version=2.0
```

The resolver can read the media type parameter from `Accept` or `Content-Type` per the API Javadoc when the media type is compatible with the configured type. Do not confuse `Accept` (which response type the client wants) with `Content-Type` (request body type). When using `Vary: Accept` and HTTP caching, configure/test caches so representations do not mix across versions.

### 3.6. Missing version in the request

By default when versioning is enabled, a missing version can produce:

```text
MissingApiVersionException -> HTTP 400 Bad Request
```

To use an intentional default version:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version")
            .setDefaultVersion("1.0");
}
```

Per the config API, setting a default version makes the version no longer required and assigns the default to requests without one. You can also use:

```java
configurer.setVersionRequired(false);
```

When a version is not required and **no default is set**, Spring may select the highest/latest version per strategy; this is dangerous for backward compatibility because silent clients can automatically switch response contracts when the server adds a new version.

**Recommendation:** production public APIs should explicitly define missing-version behavior: return 400 requiring clients to declare a version, or maintain a long-term default with a migration plan, rather than silently switching to the highest version.

## 4. ApiVersionParser: what does a version mean?

Spring 7 provides the default parser `SemanticApiVersionParser`: it accepts version numbers in `major`, `minor`, `patch` form; missing minor/patch default to 0.

| String | Parsed into components |
| --- | --- |
| `1` | `1.0.0` |
| `1.2` | `1.2.0` |
| `1.2.3` | `1.2.3` |
| `2.0` | `2.0.0` |

This allows comparing versions numerically rather than lexicographically. For example, 2.10 is numerically greater than 2.9, whereas lexicographic string comparison gets it wrong.

**Do not confuse the parser's name with full npm/SemVer:** although it supports major/minor/patch, do not assume arbitrary prerelease/build metadata syntax like `1.2.3-beta+7` is accepted or ordered like any given SemVer library. If an enterprise defines versions by date such as `2026-10` or custom codes, provide a custom `ApiVersionParser` conforming to `Comparable<?>` and test parse errors.

### 4.1. Custom resolver and parser

Spring provides extensions:
- `ApiVersionResolver` when the version source uses a mechanism without a built-in resolver.
- `ApiVersionParser<?>` for custom version formats.
- `ApiVersionStrategy` holding parser/resolver and comparing metadata.

Customize only when the contract genuinely needs it. If the version comes from token/tenant metadata instead of a request header, still ensure attackers cannot escalate/downgrade privileges by manipulating strings; API version only selects the contract and is **not** authorization.

## 5. Supported version vs. mapped version

This is an important and easily misunderstood concept in Spring 7:

1. **Supported version:** a version the application accepts as valid (validation).
2. **Mapped version:** a controller method selection condition, either fixed `"1.0"` or baseline `"2.0+"`.
3. **Selected version:** the version the client actually requested after resolver/parser/default.

By default Spring discovers supported versions from values declared in controller mappings. However, a **baseline mapping** can provide the implementation for higher versions **not explicitly listed in annotations**, once you add them to the supported versions list.

Example:

```java
@Override
public void configureApiVersioning(ApiVersionConfigurer configurer) {
    configurer.useRequestHeader("API-Version");
    configurer.addSupportedVersions("1.0", "2.0", "2.1");
}
```

And:

```java
@GetMapping(path = "/books", version = "1.0")
public String v1() {
    return "v1";
}

@GetMapping(path = "/books", version = "2.0+")
public String v2AndLater() {
    return "v2";
}
```

Result when the configuration and mappings work together:

| API-Version | Supported? | Candidate mapping | Result |
| --- | --- | --- | --- |
| `1.0` | Yes | Fixed `1.0` | `v1()` |
| `2.0` | Yes | Baseline `2.0+` | `v2AndLater()` |
| `2.1` | Yes, explicitly added | Baseline `2.0+` | `v2AndLater()` |
| `3.0` | No | Does not reach mapping because validation rejects it | 400 |
| Missing header | Missing | Not selected | 400 by default |

**The `+` here is not a general SemVer range parser**. It is a specialized syntax for the version condition on Spring request mappings meaning “from this baseline onward within the set of supported versions”.

### 5.1. Fixed mapping

```java
@GetMapping(version = "2.0")
```

Matches only versions equal to `2.0` per the parser. It does not automatically match `2.1`.

### 5.2. Baseline mapping

```java
@GetMapping(version = "2.0+")
```

Used for version 2.0 and higher versions **marked as supported**. It is especially useful when minor changes do not require a new controller: a single v2 implementation can continue serving 2.1.

**Contract safety note:** if v2 logic is incompatible with version 2.1 due to response shape changes, do not add 2.1 as supported just to avoid writing a mapping. A baseline mapping is a compatibility promise for the corresponding higher versions.

### 5.3. Mapping without declaring a version

```java
@GetMapping("/books")
```

If a method does not declare a version, it can match any version, yet more specific mappings take precedence. It can serve as an intentional fallback, though avoid letting an unversioned method hide compatibility bugs.

### 5.4. Closest version selection rule

Suppose there are four methods for the same URL/HTTP method:
- unversioned;
- fixed `1.1`;
- baseline `1.2+`;
- fixed `1.5`.

Spring 7 compares version conditions and selects the most specific matching mapping; a baseline matches only from its threshold upward, while a matching fixed version takes precedence for its exact version. For request `1.3`, baseline `1.2+` can win if `1.3` is declared supported. For request `1.5`, fixed `1.5` takes precedence over the older baseline rather than routing the request to the lower-version method.

**Do not assume merely writing `"1.2+"` makes 1.3, 1.4, 1.5... all valid:** validation still checks supported versions. Default support detection from mappings only collects explicitly declared versions; add intermediate versions when you want to support them.

## 6. Lifecycle changes: Deprecated, Sunset, and removed

API versioning is not just request resolution. An important part is **how to notify clients to prepare to move to a newer version**.

Distinguish:

| State | Meaning | Server/client action |
| --- | --- | --- |
| **Supported** | Valid version with an implementation | Server handles normally |
| **Deprecated** | Version still works, yet provider recommends migrating away | Return `Deprecation` header, `Link` to migration guide; monitor usage |
| **Sunset announced** | Scheduled milestone announced after which resource/version ends | Return `Sunset` and `Link` to policy details |
| **Removed/unsupported** | Version is no longer accepted by the server | Remove mapping/supported entry; return contract/API gateway error |

**Deprecated does not mean immediate 404, 410, or 400.** While the version remains supported, requests still succeed. Headers inform clients of the timeline/roadmap.

**A Sunset header does not set a timer to shut down the API automatically.** It is metadata stating the planned date. Once that time passes, actually shutting down the version requires config, code, and gateway changes plus ensuring migration policy compliance; Spring does not delete controller methods by date.

## 7. StandardApiVersionDeprecationHandler: standard notices

Spring Framework 7 provides `org.springframework.web.accept.StandardApiVersionDeprecationHandler`, aligned with:

- **RFC 9745 — Deprecation HTTP Response Header Field**.
- **RFC 8594 — The Sunset HTTP Header Field**.
- **Link** headers with `rel="deprecation"` or `rel="sunset"` pointing to the respective docs/guides.

Methods published in the Spring 7 Javadoc:

```java
StandardApiVersionDeprecationHandler handler =
        new StandardApiVersionDeprecationHandler();

handler.configureVersion("1.0")
        .setDeprecationDate(
                ZonedDateTime.parse("2026-07-01T00:00:00Z"))
        .setSunsetDate(
                ZonedDateTime.parse("2027-07-01T00:00:00Z"))
        .setDeprecationLink(
                URI.create("https://docs.example.test/api/migrate-v2"))
        .setSunsetLink(
                URI.create("https://docs.example.test/api/sunset-v1"));

configurer.setDeprecationHandler(handler);
```

This is a **snippet inside `configureApiVersioning(...)`**, requiring imports `java.net.URI`, `java.time.ZonedDateTime`, and `StandardApiVersionDeprecationHandler`. Domain `docs.example.test` is purely illustrative, not a live URL.

### 7.1. Header syntax and purpose

When a client requests version 1.0, the response can include:

```http
Deprecation: @1782864000
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://docs.example.test/api/migrate-v2>; rel="deprecation"; type="text/html"
Link: <https://docs.example.test/api/sunset-v1>; rel="sunset"; type="text/html"
```

**The lines above are illustrative** per the RFCs, not an assertion that containers will always use identical formatting/casing/ordering. `Deprecation` uses a structured-field timestamp (RFC 9745); `Sunset` uses an HTTP-date (RFC 8594); `Link` includes a relation type so clients can distinguish deprecation docs from sunset docs.

The dates in the example **do not mean** version 1.0 stops working at that exact time. In real production applications, use dates published by product/legal/ops rather than copying example dates as product schedules.

### 7.2. v2 remains active

For versions 2.0 and 2.1 not marked deprecated, the deprecation handler above does not emit the v1 deprecation headers. This ensures clients receive warnings **specific to the version used** rather than irrelevant notices.

### 7.3. Notifying a specific group of requests

`StandardApiVersionDeprecationHandler.VersionSpec#setRequestPredicate(Predicate<HttpServletRequest>)` lets you filter which requests should carry deprecation headers in their responses. For example, APIs under `/api/legacy/` need warnings, while `/actuator` does not. This is optional; grouping must align with real routes/features so you do not accidentally hide notices from clients that need to migrate.

### 7.4. When using a custom ApiVersionParser

The `StandardApiVersionDeprecationHandler(ApiVersionParser<?>)` constructor lets you use the same parser type as the application. If the application uses a custom version parser while the deprecation handler keeps the default parser, deprecated versions may compare wrongly or fail to match. Keep the same parser consistently across mapping/validation/deprecation.

### 7.5. Do not invent fake headers by guessing syntax

This example is **not** equivalent:

```http
Deprecation: true
Sunset: 2027-07-01
```

Because the newer RFCs define strict syntax for each header. Do not emit arbitrary values expecting clients to understand them. Prefer the standard handler or build a custom handler tested against the RFCs; document where to find the migration guide.

## 8. Complete runnable example — Java 17+, Spring Boot 4.x

This example uses Spring Boot **4.0.x** (managing Spring Framework 7.0.x), Java 17+, and **Spring Web MVC**, without a database or Spring Security, to focus on resolution, mapping, and deprecation headers.

**Do not** take `spring-boot-starter-web` from the Spring Boot 3 lesson and assume it is the recommended starter for Boot 4. Spring Boot 4 modularizes starters; the recommended Spring MVC starter is `spring-boot-starter-webmvc`, and its test companion is `spring-boot-starter-webmvc-test`.

### 8.1. Creating the Maven project

At [Spring Initializr](https://start.spring.io/), choose Maven, Java 17+, and Spring Boot 4.0.x, adding the **Spring Web MVC** dependency. Main dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
</dependencies>
```

This is a POM fragment. The Initializr project generates the parent/BOM, version, plugins, and required metadata. If upgrading to a newer Boot version, check the accompanying Spring Framework docs to avoid mixing up APIs between 7.0 and 7.1.

Structure:

```text
src/main/
  java/com/example/demo/DemoApplication.java
```

### 8.2. Full Java source

Place all of it in `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.time.ZonedDateTime;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.accept.StandardApiVersionDeprecationHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ApiVersionConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class ApiVersionWebConfiguration implements WebMvcConfigurer {

    @Override
    public void configureApiVersioning(ApiVersionConfigurer configurer) {
        // In this demo, the client selects the API contract via header.
        configurer.useRequestHeader("API-Version");

        // Two versions have mappings; 2.1 continues using the v2 baseline.
        configurer.addSupportedVersions("1.0", "2.0", "2.1");

        // If version is missing, Spring returns 400 (default policy).
        configurer.setVersionRequired(true);

        StandardApiVersionDeprecationHandler deprecated =
                new StandardApiVersionDeprecationHandler();

        deprecated.configureVersion("1.0")
                .setDeprecationDate(
                        ZonedDateTime.parse("2026-07-01T00:00:00Z"))
                .setSunsetDate(
                        ZonedDateTime.parse("2027-07-01T00:00:00Z"))
                .setDeprecationLink(URI.create(
                        "https://docs.example.test/api/migrate-v2"))
                .setSunsetLink(URI.create(
                        "https://docs.example.test/api/sunset-v1"));

        configurer.setDeprecationHandler(deprecated);
    }
}

record BookV1(String title) {
}

record BookV2(long id, String name, String author) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping(version = "1.0")
    public List<BookV1> booksV1() {
        return List.of(new BookV1("Spring"));
    }

    @GetMapping(version = "2.0+")
    public List<BookV2> booksV2() {
        return List.of(new BookV2(
                1L, "Spring", "Spring Team"));
    }
}
```

**Explanation:**
- `@Configuration` + `WebMvcConfigurer#configureApiVersioning` enables the resolver via `useRequestHeader("API-Version")`.
- `addSupportedVersions("1.0", "2.0", "2.1")` declares valid versions; versions in annotated mappings can also be auto-detected by default. Explicit declaration helps reviewers see that version 2.1 is genuinely accepted.
- `setVersionRequired(true)` emphasizes the default policy: clients omitting a version are rejected.
- The V1 fixed method `version="1.0"` returns the old shape.
- The V2 method `version="2.0+"` is a baseline mapping, so it also handles version 2.1 once declared supported.
- The old version handler emits `Deprecation`, `Sunset`, and `Link` metadata.
- Records are immutable, with no database/security; production requires authentication, authorization, rate limiting, input validation, and operational policies.
- Even though 2.1 uses the v2 handler, version 2.1 content remains a public contract that must be tested; do not assume backward compatibility merely because it shares a Java method.

### 8.3. Running

From the project root:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

If no port is specified, the server uses `http://localhost:8080` per standard Spring Boot configuration.

### 8.4. Calling version 1.0

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 1.0'
```

Key output:

```http
HTTP/1.1 200
Content-Type: application/json
Deprecation: @...
Sunset: Thu, 01 Jul 2027 00:00:00 GMT
Link: <https://docs.example.test/api/migrate-v2>; rel="deprecation"; type="text/html"
Link: <https://docs.example.test/api/sunset-v1>; rel="sunset"; type="text/html"

[{"title":"Spring"}]
```

The `Deprecation` header contains a timestamp generated from the configured date; `@...` is a descriptive placeholder, not a literal value to assert. `Link` headers may be combined/serialized in a different order, so verify the semantics of the relations rather than comparing raw responses verbatim. JSON body ordering/whitespace is also determined by the converter.

### 8.5. Calling version 2.0

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 2.0'
```

Response:

```json
[{"id":1,"name":"Spring","author":"Spring Team"}]
```

Status 200. v2 has no deprecation hints for v1 if only `configureVersion("1.0")` is set.

### 8.6. Calling version 2.1 using the baseline mapping

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 2.1'
```

Because 2.1 was added to `addSupportedVersions` and `@GetMapping(version="2.0+")`, the response body uses the v2 structure:

```json
[{"id":1,"name":"Spring","author":"Spring Team"}]
```

**Learning point:** `2.1` **does not necessarily require a new Java controller method**, provided the same implementation satisfies the contract. However, the new version still needs a release review.

### 8.7. Calling an unsupported version

```bash
curl -i 'http://localhost:8080/api/books' \
  -H 'API-Version: 3.0'
```

Because `3.0` is absent from the supported versions list and not discovered from mappings, Spring MVC throws `InvalidApiVersionException`, resulting in HTTP **400 Bad Request** per documentation. The actual HTTP error body depends on error configuration, so no fixed JSON body is shown here.

### 8.8. Omitting the version

```bash
curl -i 'http://localhost:8080/api/books'
```

With `setVersionRequired(true)` enabled and no default, Spring MVC throws `MissingApiVersionException`, HTTP **400 Bad Request**. This is completely distinct from `404 Not Found` (missing resource) or `406 Not Acceptable` (content negotiation).

### 8.9. PowerShell

Bash uses `\` for line continuation. In PowerShell, run `curl.exe` on one line:

```powershell
curl.exe -i "http://localhost:8080/api/books" -H "API-Version: 1.0"
```

The version header is a string value; use `1.0` rather than `v1` because the default parser does not arbitrarily understand any version name.

## 9. MockMvc testing on Spring Boot 4

Spring Boot 4 modularizes test starters; use `spring-boot-starter-webmvc-test` instead of copying Boot 3's old `spring-boot-starter-test` setup directly. Add to the Maven POM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc-test</artifactId>
    <scope>test</scope>
</dependency>
```

In Boot 4, `@AutoConfigureMockMvc` resides at `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`, **no longer** at the old package `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

### 9.1. Runnable test file

Create `src/test/java/com/example/demo/ApiVersioningTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiVersioningTest {

    @Autowired
    MockMvc mvc;

    @Test
    void v1ShouldReturnOldRepresentation() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "1.0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("Spring"));
    }

    @Test
    void v2AndV21ShouldUseV2Representation() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "2.0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("Spring"));

        mvc.perform(get("/api/books")
                        .header("API-Version", "2.1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].author")
                        .value("Spring Team"));
    }

    @Test
    void missingVersionShouldBeRejected() throws Exception {
        mvc.perform(get("/api/books"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownVersionShouldBeRejected() throws Exception {
        mvc.perform(get("/api/books")
                        .header("API-Version", "3.0"))
                .andExpect(status().isBadRequest());
    }
}
```

These tests verify mapping and missing/unsupported behavior. They do not yet verify the exact syntax of response deprecation headers, so a separate test is needed.

### 9.2. Testing deprecation headers

You can add a test:

```java
@Test
void v1ShouldExposeDeprecationHints() throws Exception {
    mvc.perform(get("/api/books")
                    .header("API-Version", "1.0"))
            .andExpect(status().isOk())
            .andExpect(header().exists("Deprecation"))
            .andExpect(header().exists("Sunset"))
            .andExpect(header().exists("Link"));
}
```

This is a method snippet **added to the existing test class**, requiring import:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
```

This test verifies the headers exist; in production you should parse and verify the `Deprecation` structured date, `Sunset` HTTP-date, `Link rel`, and migration dates against the contract. Also test that `API-Version: 2.0` does not receive v1 warnings.

### 9.3. Running tests

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

If another framework doc/starter changes test dependencies or mock setup, check the Boot 4.0.x Javadoc and Maven dependency tree. Do not accidentally mix both the Spring Boot 3 test auto-config package and the Boot 4 test starter.

## 10. Client support in Spring 7

According to the Spring Framework 7 documentation, client version support integrates with:
- `RestClient`;
- `WebClient`;
- declarative HTTP service clients (HTTP interfaces);
- testing with `MockMvc` and `WebTestClient`.

This does not mean the client guesses the server version. The client must select a version matching the API contract; client configuration can help attach version info to requests per the supported strategy. In an application using headers only, the clearest way is passing `API-Version` on each request or setting a default request header in the client builder via the corresponding API:

```java
// Illustrative RestClient fragment using Spring 7; URL is for demo only.
RestClient client = RestClient.builder()
        .baseUrl("https://api.example.test")
        .defaultHeader("API-Version", "2.0")
        .build();
```

Requires importing `org.springframework.web.client.RestClient` and Spring Boot 4-compatible client dependencies. Do not confuse `defaultHeader` with the server-side parser/configurer; use the exact same header name as `useRequestHeader("API-Version")`. For browser-based web apps, CORS must allow `API-Version` since it is not a CORS-safelisted request header, and caching layers must know the version resides in a header.

## 11. Choosing a versioning strategy for a real system

| Criterion | URL path `/v1/...` | Header `API-Version` | Query `?v=1` | Media type param |
| --- | --- | --- | --- | --- |
| Easy to test in browser | High | Needs header tool | High | Needs header |
| Separate URI per version | Yes | No | Different query | No |
| Reverse proxy/CDN routing | Relatively easy | Must mind header | Must include query | Mind Accept/Content-Type |
| Clarity for consumers | High | Depends on docs/SDK | High | Requires understanding content negotiation |
| Risk of cache mixing versions | Usually lower if URIs differ | **Must have Vary/header cache key** | Query cache key | **Vary: Accept**, media variants |
| Adds new URL when version changes | Yes | No | No | No |

No single strategy fits every organization. What matters is **publishing and maintaining a consistent contract**:
- When to increment major/minor versions.
- Which versions are supported concurrently.
- When bug fixes do not change the version.
- Whether clients receive 400 on missing/invalid versions or a default applies.
- Which headers/links emit migration warnings.
- How clients automatically generate/attach versions (SDKs, OpenAPI).
- How older versions are tested over time.

### 11.1. Caching with header-based versions

If a cache/CDN uses a single URI `/api/books` across multiple versions while **ignoring `API-Version`**, a cached v1 body can be served to a v2 client.

Example response:

```http
Vary: API-Version
```

When a resource is cacheable, `Vary` indicates the representation depends on the request header; the CDN/proxy must actually include that header in its cache key per product policy. If the API holds private data, also apply `Cache-Control: private/no-store` and an authorization-aware cache strategy; `Vary` does not protect secrets on its own.

### 11.2. Versioning does not replace content negotiation

`@GetMapping(version="2.0", produces="application/json")` can combine version mapping with a `produces` condition. Version decides the contract; media type decides the representation format. When using a media type parameter as the version source, ensure proxies/clients send the right `Accept` or `Content-Type`; do not assume `Accept: application/json` gets an inferred version if no default is configured.

### 11.3. Security and backward compatibility

- Never let version 1.0 bypass authentication/authorization just because it is “legacy”.
- Never leave a v1 endpoint exposing user B's data via mapping conditions just because v2 fixed permissions.
- Rate limits/CSRF/CORS/input validation must cover all supported versions.
- A requested version is not a token for privilege escalation.
- Critical security fixes generally must be backported to all still-supported versions, or a fast controlled sunset must be announced.

## 12. Version retirement policy: technical and product workflow

A straightforward roadmap:

1. **Publish v2:** mappings/API docs/SDK contract tests, migration guide.
2. **Observe v1 usage:** analyze by sanitized clientId/SDK version/tenant without logging access tokens.
3. **Mark v1 deprecated:** enable `StandardApiVersionDeprecationHandler`, Deprecation/Link headers.
4. **Announce Sunset:** set target date, add Sunset/Link, contact remaining v1 clients.
5. **Support the transition period:** detailed errors, legacy mappings operating per policy, avoiding sudden contract breaks.
6. **Actual Sunset:** update supported version list, controllers/gateway/SDKs, and error responses per approved schedule.
7. **Post-sunset monitoring:** track unsupported v1 requests, alerts, support policy, and rollback if needed.

### 12.1. Deprecation headers do not automatically “turn off” an endpoint

`configureVersion("1.0")` only registers deprecation metadata. It **does not remove 1.0 from supported versions**. To remove a version after sunset, deploy and test configuration/routing changes.

### 12.2. HTTP status for removed versions

When Spring 7 validation sees a version absent from the supported list, `InvalidApiVersionException` is handled by default as **400 Bad Request**. If an enterprise wants a custom response (such as error code `API_VERSION_RETIRED` or `410 Gone` for a sunset route), build explicit contract/error handling; **do not assume the framework automatically returns 410** once the date in the `Sunset` header arrives.

### 12.3. Deprecation and sunset timestamps differ

`Deprecation` states the time from which an API is declared obsolete; `Sunset` states the planned time when the resource stops being available per policy. The two dates can differ. Do not wait until the Sunset date to start notifying clients. Use timestamps with explicit timezones, preferably UTC, and track policy changes.

### 12.4. Migration guide links must stay stable

URIs in `Link rel="deprecation"` / `rel="sunset"` must be stable public URLs containing no tokens or sensitive data. If the docs host changes, maintain valid redirects. Do not construct links from arbitrary client-supplied `Host`/`X-Forwarded-Host` headers to prevent host-header poisoning.

## 13. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Boot 3 project reports missing `configureApiVersioning` | Running Spring Framework 6.x | Use Boot 4/Spring 7 or legacy versioning strategies |
| `@GetMapping(version=...)` does not compile | Dependency/framework version not new enough | Verify Spring 7.x and Web MVC starter |
| Version 2.1 returns 400 despite 2.0+ mapping | 2.1 not in supported versions | Add `addSupportedVersions("2.1")` or matching mapped version |
| Request missing header returns 400 | Version required by default | Client must send it; or configure intentional default |
| Enabling `setVersionRequired(false)` breaks old clients' shapes | Picks latest version when missing | Use a fixed default or require the header |
| Handler receives wrong version | Misunderstood fixed/baseline mapping | Review `version="1.0"` vs. `"2.0+"` and supported list |
| Path version returns 400 | Wrong segment index/prefix | Count path segments from 0; matching URI variable |
| Version `v1` is rejected | Default parser expects numeric version | Use `1.0` or a custom parser |
| Unsupported version does not return 404 | Validator runs before mapping | This is Spring 7's default 400 behavior |
| `Deprecation` header missing | Handler unconfigured or version not marked deprecated | `setDeprecationHandler` and `configureVersion("1.0")` |
| Sunset passed yet v1 still returns 200 | Handler only emits metadata | Removal policy must be deployed separately |
| `Deprecation` header does not look like an HTTP-date | RFC 9745 uses a structured timestamp | Parse per RFC, do not force Sunset format |
| Browser CORS preflight blocked | Custom `API-Version` header not allowed | CORS allowedHeaders, OPTIONS, auth setup |
| CDN returns v1 JSON for v2 | Cache key ignores `API-Version` | `Vary`/header-aware caching |
| MockMvc cannot find AutoConfigureMockMvc | Boot 4 changed package/test starter | Use `spring-boot-starter-webmvc-test` and new import |
| Ambiguous controller mappings | Duplicate path/method/version conditions | Reduce overlap, test handler resolution |
| Validation error turns into 200 | Custom `@ExceptionHandler` omits status | Preserve 400/`ProblemDetail` per contract |

## 14. Pre-deployment QA checklist

1. Truly running Spring Framework 7.x with compatible Boot 4.x management; not relying on Spring 6.x snippets.
2. `configureApiVersioning` defines one clear resolver (header/query/path/media) and a parser matching the version format.
3. Missing-version policy is intentional: 400 or a fixed default.
4. Supported versions are explicitly defined rather than implicitly granting every future version via baseline mappings.
5. Fixed and baseline mappings do not conflict ambiguously; test versions at boundaries.
6. v1/v2 response DTOs have contract tests comparing schemas, nullability, names, semantics, errors, and security.
7. Custom version headers have explicit CORS/caching/proxy handling.
8. Every version has appropriate authentication/authorization/validation and rate limits.
9. Deprecated versions emit RFC-compliant `Deprecation`/`Sunset`/`Link` headers whose links genuinely aid migration.
10. A version-removal roadmap and sanitized client metrics exist; do not rely on headers to turn off controllers automatically.
11. MockMvc/HTTP integration tests cover missing, malformed, unsupported, v1, v2, baseline v2.1, and deprecation notices.
12. Monitoring separates version selection errors from business/controller errors, avoiding 500s for unsupported version requests.

## 15. Self-check questions

**Question 1.** Where does the primary API versioning configuration live in Spring Web MVC 7?

**Answer:** In the `WebMvcConfigurer#configureApiVersioning(ApiVersionConfigurer)` callback; for example, `configurer.useRequestHeader("API-Version")`.

**Question 2.** Does `@GetMapping(version="2.0")` handle request `2.1` by default?

**Answer:** No. That is a fixed version. To reuse an implementation from 2.0 onward, consider baseline `version="2.0+"` and declare higher versions as supported.

**Question 3.** Why can version 2.1 return 400 even when a method has `version="2.0+"`?

**Answer:** Version 2.1 is not in supported versions yet; mapping compatibility and validation are two separate steps.

**Question 4.** What happens by default when the version header is omitted after enabling API versioning?

**Answer:** `MissingApiVersionException`, HTTP 400, unless you change the required/default policy.

**Question 5.** Does `Sunset: ...` cause the framework to delete the controller right at that timestamp?

**Answer:** No. It is informational metadata; discontinuing support requires corresponding release/config/gateway changes.

**Question 6.** Do `Deprecation` and `Sunset` share the exact same date format?

**Answer:** No. `Deprecation` per RFC 9745 uses a structured timestamp, while `Sunset` per RFC 8594 uses an HTTP-date.

**Question 7.** Why must you pay attention to `Vary: API-Version` when caching an unchanged URI?

**Answer:** So caches/clients know representations vary by header; if a CDN ignores it, the wrong version's body may be served.

**Question 8.** Is `API-Version: 2.0` enough to authenticate a user?

**Answer:** No. It only selects the contract. Authentication/authorization/CSRF and business security remain independent.

## 16. Official references

- [Spring Framework 7 — API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html): `ApiVersionStrategy`, `ApiVersionResolver`, `ApiVersionParser`, validation, deprecation.
- [Spring Framework 7 — MVC Config API Version](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/api-version.html): `configureApiVersioning`, header/query/path/media resolvers, supported versions.
- [Spring Framework 7 — Request Mapping API Version](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#_api_version): fixed, baseline, and unversioned mappings.
- [Spring Framework 7 — ApiVersionConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/config/annotation/ApiVersionConfigurer.html): method signatures.
- [Spring Framework 7 — StandardApiVersionDeprecationHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/accept/StandardApiVersionDeprecationHandler.html): deprecation/sunset/link strategies.
- [Spring Framework 7 — VersionSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/accept/StandardApiVersionDeprecationHandler.VersionSpec.html): `setDeprecationDate`, `setSunsetDate`, links.
- [Spring Blog — API Versioning in Spring (2025-09-16)](https://spring.io/blog/2025/09/16/api-versioning-in-spring/): design and motivation of the Spring 7 feature.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Java 17+, Spring Framework 7, Servlet baseline.
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters, test starter, and package changes.
- [RFC 9745 — Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745): deprecation syntax and deprecated concept.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594): sunset time and lifecycle hints.

**Conclusion:** starting in Spring Framework 7, you can configure where to extract versions via `ApiVersionConfigurer`, use `@RequestMapping(version = "x.y")` or `"x.y+"` to select handlers, validate the supported versions list, and signal lifecycle status with `StandardApiVersionDeprecationHandler`. To operate reliably, add compatibility tests, caching/CORS policies, security, and a real migration/sunset plan — rather than simply adding version annotations and leaving old clients behind.
