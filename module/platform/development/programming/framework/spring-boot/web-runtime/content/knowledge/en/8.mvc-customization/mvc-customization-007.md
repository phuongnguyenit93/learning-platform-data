# PathPatternParser, Path Patterns, and Choosing a URL Matching Strategy in Spring MVC

> **Scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, **Spring MVC on the Servlet stack**. This document explains `PathPatternParser`, path pattern syntax and restrictions, specificity precedence across mappings, comparisons with `AntPathMatcher`, choosing the strategy in Spring Boot, impacts on prefixes/encoding/security, a runnable Maven example, and real HTTP tests. The end clearly distinguishes Spring WebFlux.

## 1. Where Does Path Matching Sit in the Spring MVC Flow?

Suppose a client requests:

~~~http
GET /api/catalog/featured HTTP/1.1
Host: localhost:8080
~~~

The application has two controller mappings:

~~~java
@GetMapping("/api/catalog/featured")
public String featured() { return "featured"; }

@GetMapping("/api/catalog/{slug}")
public String bySlug(@PathVariable String slug) {
    return slug;
}
~~~

Both patterns can match the path `/api/catalog/featured`. Spring MVC must determine the **most specific mapping**, rather than defaulting to the method declared earlier in the source file.

Simplified flow:

~~~text
HTTP client
     |
     v
Embedded Servlet container (Tomcat/Jetty/Undertow)
     |
     v
DispatcherServlet
     |
     v
RequestMappingHandlerMapping
     |
     +-- obtain the request path to match
     +-- check path, HTTP method, params, headers,
     |   consumes, produces conditions...
     +-- compare specificity if multiple mappings match
     |
     v
HandlerMethod
     |
     v
RequestMappingHandlerAdapter
     |
     v
Controller method -> response
~~~

`PathPatternParser` and `AntPathMatcher` relate to **how paths are represented and matched**, not replacing all of `HandlerMapping`. A request must still satisfy other conditions such as `GET`/`POST`, `consumes`, `produces`, and headers.

**Distinguishing four concepts:**

| Component | Role |
|---|---|
| `@GetMapping("/api/items/{id}")` | Path pattern string and request conditions declared by the developer |
| `PathPatternParser` | Compiles pattern strings into `PathPattern` objects for structured matching |
| `RequestPath` / `PathContainer` | Represents the request path broken into segments |
| `RequestMappingHandlerMapping` | Holds the mapping registry and selects the appropriate handler when a request arrives |

In legacy mode, `AntPathMatcher` performs string-based path matching; it does not produce a parsed `PathPattern` under the same model.

## 2. Why Did Spring Framework Switch to PathPatternParser?

Previously, MVC commonly used `AntPathMatcher`: taking the request path as a `String` and matching it against pattern strings. This approach was flexible, but posed challenges around URL encoding, delimiter characters, matrix variable handling, and performance when re-parsing many patterns.

`PathPatternParser` was introduced for Spring MVC in Spring Framework 5.3 and became the **default in Spring Framework 6.0**. Spring Boot 3.5.x is built on Spring Framework 6.2.x, so typical MVC applications use this strategy unless explicitly reconfigured.

Core mechanism:

1. When controller mappings are registered, pattern strings are parsed into `PathPattern` objects representing path elements.
2. When a request arrives, Spring parses the path into `RequestPath`/`PathContainer` with individual path segments.
3. `PathPattern` matches segment by segment instead of decoding the entire URL into a single `String` and matching on that.
4. If multiple mappings satisfy the conditions, MVC uses a specificity comparator tailored to the pattern type.
5. `HandlerMethod` is selected and invoked through `RequestMappingHandlerAdapter`.

Segment-by-segment parsing preserves path boundaries when encoded characters appear inside a segment, such as percent-encoded semicolons or slashes. However, **this does not mean every encoded slash will be accepted by every container, reverse proxy, or firewall**; outer layers can still reject the request.

Illustrative model:

~~~text
Pattern:     /api/files/{name}
                  |      |
Parsed:      literal  capture one segment

Request:     /api/files/readme.txt
                  |      |
RequestPath: literal  "readme.txt"

Result: matches, name = "readme.txt"
~~~

`PathPatternParser` is designed for web path handling; not every place using `AntPathMatcher` in the Spring ecosystem is forced to switch to this parser.

## 3. PathPatternParser Path Pattern Syntax

Commonly used tokens:

| Pattern | Meaning | Matching Example | Non-Matching Example / Note |
|---|---|---|---|
| `/api/health` | Exact literal path | `/api/health` | `/api/healthcheck` |
| `/api/items/{id}` | Captures **one** path segment into variable `id` | `/api/items/42` | `/api/items/42/details` |
| `/api/items/{id:[0-9]+}` | Variable with regex constrained to one segment | `/api/items/123` | `/api/items/abc` |
| `/assets/*.png` | `*`: 0 or more characters within **one** segment | `/assets/logo.png` | `/assets/img/logo.png` |
| `/pages/t?st.html` | `?`: exactly **one character** within one segment | `/pages/test.html` | `/pages/toast.html` |
| `/assets/**` | `**`: 0 or more path segments **at the end** of a pattern | `/assets/img/a.png` | `/assets/**/tail` is **invalid syntax** |
| `/assets/{*path}` | Captures the **rest of the path** into variable `path` | `/assets/img/a.png` | `/{*path}/tail` is invalid |
| `/v1/{type:[a-z]+}/info` | Mid-route variable with regex | `/v1/book/info` | `/v1/book123/info` |

### 3.1. `*` and `**` Are Not the Same

`*` only represents characters **within a single segment**. For example:

~~~text
Pattern:  /files/*
Match:    /files/a.txt
Not:      /files/2026/a.txt
~~~

`**` represents **multiple segments** and can also match an empty trailing path when placed at the end. For example:

~~~text
Pattern: /files/**
Match:   /files
Match:   /files/a.txt
Match:   /files/archive/2026/a.txt
~~~

With `PathPatternParser`, `**` **is only allowed at the end** so it does not create patterns whose specificity is hard to compare. The following examples are **invalid** for the parser:

~~~text
/**/admin
/assets/**/download
/{*path}/thumbnail
~~~

If legacy code uses `/**/admin`, you cannot simply keep that pattern verbatim when switching to `PathPatternParser`. Redesign the route or retain `AntPathMatcher` if legacy constraints truly require that syntax.

### 3.2. Variables `{id}` and Regex Variables

~~~java
@GetMapping("/products/{id}")
public String byId(@PathVariable String id) {
    return "product:" + id;
}
~~~

`{id}` captures **one segment**; for example, for `/products/42`, `id="42"`. Slashes separate segments, so `/products/42/spec` is a different URL.

To restrict the format:

~~~java
@GetMapping("/products/{id:[0-9]+}")
public String numericId(@PathVariable String id) {
    return "numeric:" + id;
}
~~~

The expression `[0-9]+` requires **at least one digit**; for instance, `/products/42` matches, while `/products/abc` does not match this pattern.

Note: regex inside a **URI variable pattern** does not replace Bean Validation or business rule checks. A `Long` path variable still needs type conversion, overflow handling, missing-ID handling, authorization, and data access checks.

In Java source, when writing regex containing backslashes such as `\d+`, escape the Java string properly, e.g., `"@GetMapping(...)"` with pattern `{id:\\d+}`; a simpler way in examples is `[0-9]+` to avoid multiple layers of escaping.

### 3.3. `{*path}` Capturing Multiple Segments

`{*path}` is the **capture-the-rest** syntax. For example:

~~~text
Pattern: /files/{*path}
Request: /files/reports/2026/summary.csv
Captured: path = "/reports/2026/summary.csv"
~~~

Unlike `{name}`, a catch-all variable can contain `/` characters. This is useful for handlers serving logical paths, resource routing, or inspecting the remainder of a route.

**Never use the catch-all value directly as an operating system file path.** Before accessing files/directories, enforce resource naming policies, path traversal checks, canonicalization, authorization, and path boundaries. Just because the parser matched the route does not mean the input is safe.

### 3.4. Literals, Wildcards, and Dots

Pattern `/files/{name}` can capture a name like `readme.txt`; the dot does not automatically become a file extension used to select another handler. In modern Spring MVC, legacy suffix pattern matching is no longer something to rely on. If an API wants `/files/{name}.json`, declare the route and response type explicitly.

For example, `/images/*.png` matches a single segment ending in `.png`; do not equate URL wildcards with shell globs or full Java regular expressions.

## 4. Valid Patterns vs. Migration-Error-Prone Patterns

| Pattern Written | `PathPatternParser` | How to Handle |
|---|---|---|
| `/api/{id}` | Valid | Captures one segment |
| `/api/{id:[0-9]+}` | Valid | Restricts ID format with regex |
| `/docs/**` | Valid | Trailing catch-all |
| `/docs/{*path}` | Valid | Trailing catch-all with variable |
| `/assets/**/thumb` | **Invalid** | Redesign URL or consider legacy matcher |
| `/**/admin` | **Invalid** | Convert to explicit prefix or concrete routes |
| `/{*path}/details` | **Invalid** | Do not place capture-the-rest before another segment |
| `/api/*/status` | Valid | Single-segment wildcard |
| `/api/v?/status` | Valid | Single-character wildcard |
| `/api/**/status/**` | **Invalid** | Do not use `**` in the middle |

An invalid route can throw `PatternParseException` when Spring parses mapping registrations at startup, rather than merely causing a 404 when called by a client. Therefore, before enabling the parser on a large legacy application, audit all `@RequestMapping`, `@GetMapping`, custom mappings, plugin endpoints, and library-provided patterns.

## 5. Which Mapping Does Spring MVC Pick When Multiple Patterns Match?

A controller may have:

~~~java
@GetMapping("/catalog/featured")
public String featured() {
    return "featured";
}

@GetMapping("/catalog/{slug}")
public String bySlug(@PathVariable String slug) {
    return "slug:" + slug;
}

@GetMapping("/catalog/{*path}")
public String nested(@PathVariable String path) {
    return "nested:" + path;
}
~~~

For request `GET /catalog/featured`, multiple patterns match, yet the literal mapping `/catalog/featured` is more specific than a single-segment variable and a catch-all, so it is selected. For `GET /catalog/books`, `{slug}` is chosen; for `GET /catalog/archive/2026`, `{*path}` serves the multi-segment path.

`PathPattern.SPECIFICITY_COMPARATOR` is the comparator for parsed patterns. Key ideas:

1. **Catch-all** patterns like `/**` and `/{*path}` rank below specific non-catch-all mappings.
2. Among non-catch-all mappings, structurally more specific paths (fewer wildcards/variables) take priority.
3. When complexity is equal, normalized length and other criteria distinguish them.
4. HTTP method, `params`, `headers`, `consumes`, `produces`, and request mapping configuration **also factor into** whether a handler is selected.

Do not guess that "the method declared first wins" or "regex always beats every other route." To guarantee behavior, keep URLs non-overlapping when possible and write regression tests for intersecting routes.

### Duplicate and Indistinguishable Mappings

If two annotated methods have identical mapping conditions, `RequestMappingHandlerMapping` can fail at startup with an **ambiguous mapping** error. If multiple mappings overlap only on certain requests, the ambiguity may surface when that specific request arrives.

Resolve this by differentiating paths, methods, media types, or other request conditions; **do not** rely on bean scan order.

## 6. Trailing Slashes, Case Sensitivity, and Segment Boundaries

### 6.1. Trailing `/` in Paths

In Spring Framework 6.2, `PathPatternParser` by default **does not treat** `/api/books` and `/api/books/` as the same route. Since Spring Framework 6.0, optional trailing separator matching has defaulted to `false`, and the corresponding configuration method was deprecated.

Example:

~~~text
@GetMapping("/api/books")

GET /api/books    => matches
GET /api/books/   => does not match automatically due to trailing "/"
~~~

In a simple app, a non-match typically produces HTTP 404. If the system wants to support both URL forms, you can declare both mappings explicitly, perform a canonical URL redirect at the edge/filter, or pick one URL convention and require clients to follow it. Do not re-enable legacy trailing slash matching indiscriminately, as it can introduce security discrepancies across layers.

### 6.2. Case Sensitivity

`PathPatternParser` is **case-sensitive** by default. `/api/books` and `/api/Books` are distinct. Establish a consistent API path naming convention, usually lowercase/kebab-case, rather than expecting the parser to normalize casing automatically.

Advanced parser configuration `setCaseSensitive(false)` exists, but changing it widens the set of matched URLs and requires testing security request matchers, cache keys, and URL canonicalization.

### 6.3. Encoding, Semicolons, and Matrix Variables

A request path may contain percent-encoded characters (such as `%20` for space) or semicolon path parameters. Parsed paths support segment-level processing and extracting matrix variables when a controller uses them.

Example URL syntax with matrix parameters:

~~~text
/cars/42;color=red;year=2026
~~~

Sections after a semicolon should not be parsed with ad-hoc `String.split(";")` in security-sensitive code. Proxies/containers/security firewalls may restrict semicolons; only use matrix variables when the API contract and infrastructure support them, and test end-to-end.

**Encoded slash (`%2F`)** is an important case: parsed matching processes segments with structural awareness, yet Tomcat, proxies, and firewalls may block requests containing encoded slashes. Never assume a URL containing `%2F` will reach your controller or automatically act as a valid segment in every environment.

## 7. Configuring the Strategy in Spring Boot 3.5

Spring Boot supports the property:

~~~properties
spring.mvc.pathmatch.matching-strategy=path-pattern-parser
~~~

The value above selects the **modern parser** and is the default strategy for Boot 3.5 MVC in standard configurations; you normally **do not need to declare it** if keeping the default.

If legacy path pattern compatibility is required:

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

This change impacts **MVC handler mapping**: code using `PathPatternParser`-specific syntax such as `{*path}` must be audited and may need rewriting when using the Ant matcher.

Equivalent YAML configuration:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

Or selecting legacy:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Do not place conflicting values across multiple config sources and assume the first one wins. Spring Boot enforces precedence across environment variables, profiles, command-line args, and config files; verify the effective value when debugging.

### 7.1. Why Not Revert to AntPathMatcher by Default?

`PathPatternParser` is recommended by Spring Framework for web routing due to clearer path structure, safer encoding handling, and optimized matching. `AntPathMatcher` is mainly useful for legacy syntax/Servlet mapping compatibility. Switching back to legacy as a "quick fix for 404" without understanding the root cause can mask URL bugs and create mismatches with security matchers.

Recommended workflow: **keep the default parser**, fix invalid patterns, test trailing slashes and encoding, and only switch to Ant when a genuine technical constraint requires it.

### 7.2. Scope of Application

`spring.mvc.pathmatch.matching-strategy` configures **Spring MVC** request mapping. It is not a property for changing Spring WebFlux's router, does not change the Tomcat/Jetty servlet container, does not automatically prepend prefixes to routes, and does not alter the client's HTTP method/path.

If a project has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot usually chooses **Servlet MVC** by default; verify the actual web application type before configuring.

## 8. Special Case: `spring.mvc.servlet.path` and `server.servlet.context-path`

These two properties mean different things:

- `server.servlet.context-path=/portal`: places the **Servlet application context** under `/portal`.
- `spring.mvc.servlet.path=/api`: sets the **`DispatcherServlet` mapping prefix** under `/api`.

For example, a controller `@GetMapping("/hello")` with both set will be called at URL `/portal/api/hello` when configured compatibly.

**Important note for Spring Boot 3.5:** Boot 3.5's Servlet Web Applications documentation explicitly states that the default `PathPattern` strategy **is not compatible with configuring a `DispatcherServlet` prefix via `spring.mvc.servlet.path`**. In that case, Boot instructs switching to:

~~~properties
server.port=8080
server.servlet.context-path=/portal
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

This does **not** mean that merely using `server.servlet.context-path` requires reverting to the Ant matcher. When `DispatcherServlet` still maps at the default `/`, the modern parser remains the right choice.

Note: Spring Framework-level documentation describes supporting certain simple servlet prefix mappings, but in Boot 3.5 applications follow the limitations and configuration published by Boot for that version. If you intend to use the parser alongside a custom Servlet mapping in an advanced setup, verify thoroughly with your actual version/framework setup rather than assuming default support.

**Important for code migration:** after enabling `ant-path-matcher`, a `@GetMapping("/files/{*path}")` as in the parser example below is no longer a compatible option. You must redesign the route (for example using `/files/**` and separately tested path extraction), rather than changing one line of properties and assuming the whole API stays identical.

## 9. Complete Spring MVC Maven Example Using PathPatternParser

Create a project with the structure:

~~~text
path-pattern-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/pathdemo/
    PathPatternDemoApplication.java
    PathController.java
  src/test/java/com/example/pathdemo/
    PathRoutingIntegrationTest.java
~~~

### 9.1. POM for Java 17+, Spring Boot 3.5

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>path-pattern-demo</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-web` brings in Spring MVC and the default embedded servlet server. `spring-boot-starter-test` brings in JUnit 5 and Spring Boot testing utilities. Use the parent POM to manage compatible library versions rather than overriding the Spring Framework version independently of Boot.

### 9.2. Java Entry Point

`src/main/java/com/example/pathdemo/PathPatternDemoApplication.java`:

~~~java
package com.example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathPatternDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathPatternDemoApplication.class, args);
    }
}
~~~

### 9.3. Literal, Single-Variable, Regex, and Catch-All Routes

`src/main/java/com/example/pathdemo/PathController.java`:

~~~java
package com.example.pathdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PathController {

    @GetMapping(
        path = "/catalog/featured",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String featured() {
        return "featured";
    }

    @GetMapping(
        path = "/catalog/{slug}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String catalogItem(@PathVariable String slug) {
        return "slug:" + slug;
    }

    @GetMapping(
        path = "/files/{name}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String file(@PathVariable String name) {
        return "file:" + name;
    }

    @GetMapping(
        path = "/files/{*path}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String nestedFile(@PathVariable String path) {
        return "nested:" + path;
    }

    @GetMapping(
        path = "/orders/{id:[0-9]+}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String numericOrder(@PathVariable String id) {
        return "order:" + id;
    }

    @GetMapping(
        path = "/docs",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String docs() {
        return "docs";
    }

    @GetMapping(
        path = "/case",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String caseSensitive() {
        return "lowercase";
    }
}
~~~

**Analysis:**

- `/catalog/featured` is a literal route; it is more specific than `/catalog/{slug}` when `slug="featured"`.
- `/files/{name}` captures only one segment and matches `/files/readme.txt`.
- `/files/{*path}` captures the remainder, e.g., for `/files/a/b`, variable `path` is `"/a/b"`. Capture-the-rest includes the leading `/`.
- `/orders/{id:[0-9]+}` only matches digit-only IDs per the regex.
- `/docs` and `/case` serve the two examples for trailing slashes and case sensitivity.
- Each method returns a `String` from `@RestController` with `produces=text/plain`, so the response body is plain text rather than a view name.
- No two methods share identical mapping signatures, so there is no registration conflict in this example.

### 9.4. Application Configuration

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Spring Boot 3.5: default choice, declared explicitly for study.
spring.mvc.pathmatch.matching-strategy=path-pattern-parser
~~~

The project does **not** set `spring.mvc.servlet.path`, so it avoids Boot 3.5's Servlet prefix limitation. No extra configuration is needed to use `{*path}`.

## 10. Running the Program and Testing URLs

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Or package as a JAR:

~~~bash
mvn clean package
java -jar target/path-pattern-demo-1.0.0.jar
~~~

With the application listening on port 8080, test sequentially:

~~~bash
curl -i http://localhost:8080/api/catalog/featured
curl -i http://localhost:8080/api/catalog/books
curl -i http://localhost:8080/api/files/readme.txt
curl -i http://localhost:8080/api/files/a/b
curl -i http://localhost:8080/api/orders/123
curl -i http://localhost:8080/api/orders/abc
curl -i http://localhost:8080/api/docs
curl -i http://localhost:8080/api/docs/
curl -i http://localhost:8080/api/Case
~~~

Expected response table with the configuration and source code above:

| URL | Status | Response Body / Reason |
|---|---|---|
| `/api/catalog/featured` | 200 | `featured` |
| `/api/catalog/books` | 200 | `slug:books` |
| `/api/files/readme.txt` | 200 | `file:readme.txt` |
| `/api/files/a/b` | 200 | `nested:/a/b` |
| `/api/orders/123` | 200 | `order:123` |
| `/api/orders/abc` | 404 | Does not match the order ID regex; no other route in sample app |
| `/api/docs` | 200 | `docs` |
| `/api/docs/` | 404 | Trailing slash is not accepted automatically by default |
| `/api/Case` | 404 | Default parser is case-sensitive |

The 404 codes above assume no custom fallback, redirect, security rule, or static resource serves those URLs. `curl -i` also prints the status line and HTTP headers; the body column shows only what the controller returns.

If port 8080 is already in use, you can run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

Then replace 8080 with 9090 in the `curl` commands. Changing the port does not alter path pattern selection rules.

## 11. Integration Testing with a Random Port

Create `src/test/java/com/example/pathdemo/PathRoutingIntegrationTest.java`:

~~~java
package com.example.pathdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PathRoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void literalIsMoreSpecificThanVariable() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/catalog/featured");

        assertEquals(200, response.statusCode());
        assertEquals("featured", response.body());
    }

    @Test
    void oneSegmentVariableMatches() throws Exception {
        HttpResponse<String> response =
                get("/api/files/readme.txt");

        assertEquals(200, response.statusCode());
        assertEquals("file:readme.txt", response.body());
    }

    @Test
    void catchAllCapturesMultipleSegments() throws Exception {
        HttpResponse<String> response =
                get("/api/files/a/b");

        assertEquals(200, response.statusCode());
        assertEquals("nested:/a/b", response.body());
    }

    @Test
    void regexVariableAcceptsDigits() throws Exception {
        HttpResponse<String> response =
                get("/api/orders/123");

        assertEquals(200, response.statusCode());
        assertEquals("order:123", response.body());
    }

    @Test
    void regexVariableRejectsNonDigits() throws Exception {
        assertEquals(404, get("/api/orders/abc").statusCode());
    }

    @Test
    void trailingSlashDoesNotMatchByDefault() throws Exception {
        assertEquals(200, get("/api/docs").statusCode());
        assertEquals(404, get("/api/docs/").statusCode());
    }

    @Test
    void pathsAreCaseSensitiveByDefault() throws Exception {
        assertEquals(404, get("/api/Case").statusCode());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` starts a real embedded HTTP server, and `@LocalServerPort` receives the bound port. This is an appropriate test for observing path matching over HTTP rather than testing Java methods in isolation. The suite covers specificity, single-segment variables, catch-all, regex, trailing slashes, and case sensitivity.

If running `@WebMvcTest` with `MockMvc`, you can test mapping logic at the MVC level; however, integration tests over a real socket reveal effects from Servlet context mapping, filters, the container, and internal proxies much more clearly.

## 12. When AntPathMatcher Must Be Used for Legacy Code

`AntPathMatcher` is a String-path-based strategy widely used in older Spring projects. Cases to consider keeping Ant:

- The system has legacy routes using `**` in the middle of a pattern, such as `/files/**/download`.
- A Spring Boot 3.5.x application needs `spring.mvc.servlet.path=/api` and wants to follow Boot's documented compatibility setup.
- Custom MVC mappings or legacy libraries rely on String path matching and have not been migrated yet.
- The cost of changing existing routing APIs outweighs migration benefits; the project has an explicit migration plan and regression tests.

**How to enable:**

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Dedicated example for the legacy style:

~~~java
@RestController
class LegacyController {

    @GetMapping("/legacy/**/download")
    public String download() {
        return "legacy download";
    }
}
~~~

This is an **illustrative class for use with the Ant matcher strategy**, excluded from the default parser project in Section 9 because `**` appears in the middle of the pattern. With the Ant matcher, `GET /legacy/a/b/download` can match this route. Other patterns, especially parser `{*path}`, must be audited and converted when changing strategies.

There is no recommendation that "switching back to Ant is always better." The choice involves tradeoffs:

| Criterion | `PathPatternParser` | `AntPathMatcher` |
|---|---|---|
| Pattern representation | Parsed `PathPattern` | `String` pattern |
| Path representation | Segment-based `RequestPath`/`PathContainer` | String lookup path |
| `**` in the middle | Not supported | Supported |
| `{*path}` capture the rest | Yes | Not directly compatible syntax |
| Encoded paths and semicolons | Designed for segment-aware handling | Requires careful string decoding/lookup path handling |
| Matching performance | Designed for efficient matching and less ambiguity | Higher String processing and pattern selection overhead |
| Default in Spring MVC 6.2/Boot 3.5 | Yes | No |
| When using `spring.mvc.servlet.path` in Boot 3.5 | Boot notes compatibility caveat | Boot recommends this strategy |
| Spring WebFlux | Uses parsed patterns | Not an option for replacing WebFlux's parser |

If switching strategies, test every route rather than smoke-testing a single endpoint. Regex URI variables, wildcards, catch-all routes, suffixes, trailing slashes, and encoding in particular can produce differences.

## 13. Advanced Parser Customization via WebMvcConfigurer

When you need to adjust a parser option, Spring MVC provides the `PathMatchConfigurer` API. Example **advanced configuration fragment**, not part of the sample project in Section 9:

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.util.pattern.PathPatternParser;

@Configuration
public class CustomPathMatching implements WebMvcConfigurer {

    @Override
    public void configurePathMatch(PathMatchConfigurer configurer) {
        PathPatternParser parser = new PathPatternParser();
        parser.setCaseSensitive(false);

        configurer.setPatternParser(parser);
    }
}
~~~

When registering that bean in the app, controller routes that previously matched only lowercase URLs can match uppercase URLs too; **the case-sensitivity test in Section 11 will no longer hold**. This illustrates configuration impact, not a default recommendation.

Do not use `@EnableWebMvc` just to adjust a path matching option: in Spring Boot, adding `@EnableWebMvc` can replace/disable part of MVC auto-configuration and cause side effects for static resource handling, converters, and CORS. Using `WebMvcConfigurer` is the lighter integration path when extended MVC configuration is needed.

If you need a prefix for **annotated controllers** rather than a servlet prefix, Spring MVC also supports:

~~~java
@Override
public void configurePathMatch(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
            "/api",
            org.springframework.web.method.HandlerTypePredicate
                    .forAnnotation(RestController.class)
    );
}
~~~

This is a **method fragment** inside a `WebMvcConfigurer`, not a standalone Java file. It adds a prefix to **the patterns of selected controllers**, which is a different configuration layer from `spring.mvc.servlet.path`. When choosing this approach, avoid duplicating prefixes already declared in `@RequestMapping`, and verify Security/Actuator paths accordingly.

Do not declare two `configurePathMatch` implementations on the same class just to combine snippets; when multiple customizations are needed, put them in one method and test them.

## 14. Distinguishing MVC PathPatternParser from WebFlux Routing

Spring WebFlux uses `DispatcherHandler` and a reactive mapping mechanism distinct from Spring MVC's `DispatcherServlet`. Although WebFlux also uses parsed `PathPattern`, the property:

~~~properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

**does not switch WebFlux to the Ant matcher**. In WebFlux, parsed patterns are the official routing model, and there is no equivalent option to use the Ant matcher across reactive handler mappings.

If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot usually selects **Servlet MVC** during web application type detection. Do not look solely at a WebFlux dependency on the classpath and conclude that all APIs are running reactive.

Also distinguish **WebMvc.fn RouterFunction** from annotated controllers. Both use Spring MVC, yet functional handler selection uses its own router predicates; do not assume every route-precedence behavior of WebMvc.fn is identical to `RequestMappingHandlerMapping`.

## 15. Common Errors and How to Resolve Them

### 15.1. `PatternParseException` at Startup

**Cause:** a route uses syntax forbidden by the parser, such as:

~~~java
@GetMapping("/legacy/**/download")
~~~

**Fix:** refactor into more specific routes, or place a catch-all at the end of the route when appropriate; only select `ant-path-matcher` if legacy compatibility is truly required and parser-specific endpoints have been tested.

### 15.2. Previously Working URL Now Returns 404 Because of Trailing Slash

**Cause:** `/api/orders` is no longer implicitly equivalent to `/api/orders/` in Framework 6.2. Resolve using canonical URL rules, explicit mappings, or appropriate redirects. Avoid assuming an old property will re-enable deprecated behavior.

### 15.3. `{*path}` Route Stops Matching After Switching to Ant

`{*path}` is syntax for parsed `PathPattern`. If switching to `ant-path-matcher` to support `spring.mvc.servlet.path`, change catch-all routes to an appropriate Ant pattern (e.g., trailing `/**`) and redesign how the remaining path is extracted. Do not leave `@PathVariable("path")` intact and expect parser-style binding.

### 15.4. `@GetMapping("/{id}")` Mistakenly Captures a Literal Path

When both `/catalog/featured` and `/catalog/{slug}` exist, Spring MVC picks the more specific route regardless of declaration order in Java. If a request reaches an unexpected handler, inspect path conditions, `consumes`/`produces`, class-level mappings, context path, and actual registered mappings.

### 15.5. Regex URI Variable Fails to Match

`/orders/{id:[0-9]+}` accepts digit strings, not letters. If UUIDs or slugs are needed, define the appropriate pattern; do not arbitrarily relax regex just to "fix 404". Check Java string escaping if using `\d`, `\w`, and special characters.

### 15.6. Encoded Slashes, Semicolons, or Unicode Behave Differently Across Environments

They can be altered or blocked by reverse proxies, embedded servers, WAFs, or Spring Security's firewall before reaching the controller. To diagnose, inspect the actual request URI at each hop, decode/normalization policies, and registered patterns. Never change the matcher just to try bypassing URL protection policies.

### 15.7. `spring.mvc.servlet.path` Is Incompatible with the Default Parser

In Boot 3.5, if you must set a `DispatcherServlet` prefix via `spring.mvc.servlet.path`, follow Boot's docs: `spring.mvc.pathmatch.matching-strategy=ant-path-matcher`. If you do not need a custom `DispatcherServlet` mapping, you can simply use `server.servlet.context-path` and keep the default parser.

### 15.8. Using `@EnableWebMvc` Breaks Several Boot Features

`@EnableWebMvc` can take over MVC configuration in place of Boot auto-config. Remove it if you do not genuinely need full MVC control. Switch to `WebMvcConfigurer` for incremental customizations, and re-check routing, formatters, CORS, and static resources.

### 15.9. Code Runs, Yet Security Matchers Protect the Wrong URLs

If Security uses a path matcher with different logic than MVC, unusual URLs can match a controller while bypassing a protection rule (or vice versa). Design security rules around explicit resources/HTTP methods, prefer stack-appropriate matchers, enforce deny-by-default, and test 401/403 responses for edge-case URLs, trailing `/`, encoded delimiters, and catch-all routes.

### 15.10. 404 Is Hard to Distinguish from Static File Errors

Spring Boot typically registers a static resource handler serving `/**`. A request matching no controller may be passed to the resource handler and then fail due to a missing file. Thus, logs or exceptions may show `NoResourceFoundException` instead of `NoHandlerFoundException`. Distinguish controller mappings from resource handlers when reading errors. Do not delete static resource mappings just to change the exception class if the app still needs to serve assets.

## 16. Migration and Pre-Deployment Testing Checklist

1. **Identify web stack and version**: Spring MVC Boot 3.5/Framework 6.2 vs. WebFlux; do not infer from a single dependency.
2. **Inventory routes** from annotations and custom mappings; look for mid-pattern `**`, `{*path}`, duplicate routes, complex regexes, and fallbacks.
3. **Keep default `PathPatternParser`** unless a concrete compatibility constraint exists. Only switch to Ant when you know the exact reason.
4. **Verify Servlet prefixes**: `server.servlet.context-path` differs from `spring.mvc.servlet.path`; in Boot 3.5, use the Ant matcher when configuring a `DispatcherServlet` prefix per Boot's instructions.
5. **Test match specificity**: literal vs. variable, single-segment vs. catch-all, intersecting mappings, mapping ambiguity.
6. **Test URL formats**: casing, trailing slashes, file extensions, encoded characters, semicolons, Unicode characters, and query strings.
7. **Test HTTP methods/media types**: GET/POST, `Accept`, `Content-Type`, 404/405/406/415.
8. **Cross-check security filters/rules** against controller matching, especially catch-all routes and proxy rewrites.
9. **Use real HTTP integration tests** on `RANDOM_PORT`; also verify through ingress/gateway when production uses a proxy.
10. **Inspect actual routes** via the Actuator `mappings` endpoint in a properly secured environment, controlled MVC logs, or dedicated unit tests.
11. **Do not release based solely on startup success**: run regression tests, assess impact on APIs/clients, and prepare a rollback plan.
12. **Do not rely on matching algorithms for authorization**: authorization must be enforced independently after the path handler is resolved.

## Official Documentation

- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): default parser, strategy property, and `spring.mvc.servlet.path` caveats.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.mvc.pathmatch.matching-strategy` property.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): URI patterns, request mapping conditions, and choosing matching patterns.
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html): decoded path segments and comparing parsed/string models.
- [Spring Framework 6.2 — MVC Path Matching Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/path-matching.html): `WebMvcConfigurer` and `PathMatchConfigurer`.
- [Spring Framework 6.2 — PathPattern Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/util/pattern/PathPattern.html): definitions of `*`, `?`, `**`, `{var}`, `{*var}`.
- [Spring Framework 6.2 — PathPatternParser Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html): parser options, case sensitivity, and trailing slash behavior.

**Conclusion:** `PathPatternParser` is the default and preferred choice for modern Spring MVC. Use proper segment syntax, place `**`/`{*path}` at the end, and test specificity and special URLs. Only select `AntPathMatcher` when there is a real compatibility need—especially with `spring.mvc.servlet.path` on Spring Boot 3.5—and always regression-test all handler mappings before deploying.
