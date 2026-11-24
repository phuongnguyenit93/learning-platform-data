# Handling Trailing Slashes, Encoded Characters, and Unmatched Paths in Spring MVC

## 1. Objectives and Scope

In a Spring Boot application using Spring MVC, two seemingly equivalent URLs like **/api/items** and **/api/items/** can lead to two different outcomes. Data containing spaces, slashes, percent signs, Vietnamese accents, or special characters placed into URLs can also alter path structure if encoded/decoded improperly. Furthermore, HTTP 404 errors do not always stem from a missing controller: static resource handlers, servlet containers, proxies, and `@RequestMapping` conditions all affect the result.

This lesson focuses on **customizing the Spring MVC path-matching flow on the Servlet stack**, with the common embedded Tomcat container. Examples use **Java 17+**, **Spring Boot 3.5.x**, Spring Framework 6.2, and Maven.

After this lesson, you will be able to:

1. Distinguish **trailing slashes**, URI paths, path segments, query parameters, and percent-encoding.
2. Explain how **DispatcherServlet**, **HandlerMapping**, and **PathPatternParser** select a controller for a request.
3. Choose a consistent policy for **/resource** and **/resource/**: explicit routes, canonical URL redirects, or controlled rewrites.
4. Handle URLs containing **%20**, **%2B**, **%26**, Unicode, and especially **%2F** accurately and safely.
5. Distinguish HTTP **400**, **404**, **405**, **406**, **415**, and errors from Spring Security/proxies.
6. Diagnose **NoHandlerFoundException**, **NoResourceFoundException**, static resources, context paths, and reverse proxies.
7. Write a Spring Boot application with tests for trailing slashes, percent-encoded input, and unmatched paths.

**Version note:** Starting in Spring Framework 6.0, Spring MVC no longer matches trailing slashes implicitly by default; the legacy option enabling optional trailing slashes was deprecated in 6.0 and removed in Spring Framework 7.0. Spring Framework 6.2 added **UrlHandlerFilter** to normalize or redirect URLs with trailing slashes. If using Spring Boot 2.x, consult the corresponding behavior and documentation instead of copying Boot 3.x/4.x defaults.

## 2. What Steps Does a Request Pass Through Before Matching a Route?

~~~mermaid
flowchart TD
    A[HTTP client] --> B[CDN / Gateway / Reverse Proxy if any]
    B --> C[Tomcat connector: parse, validate, normalize URI]
    C --> D[Servlet Filter chain: Security, canonical URL...]
    D --> E[DispatcherServlet]
    E --> F[HandlerMapping: PathPatternParser + conditions]
    F --> G{Matching handler?}
    G -->|Yes| H[HandlerAdapter invokes controller]
    G -->|No| I[404 / static resource / error handling]
    H --> J[HTTP response]
    I --> J
~~~

Each layer has distinct responsibilities:

| Layer | Key Decision | Example |
|---|---|---|
| Client | Builds URL, percent-encodes each component | Value **Cà phê** becomes **C%C3%A0%20ph%C3%AA** |
| Proxy/gateway | May rewrite paths, normalize slashes, reject URIs, or run WAF checks | **/public/api** is rewritten to **/api** |
| Servlet container | Validates request-target, decodes URI, manages encoded slashes and illegal characters | Tomcat rejects **%2F** in path under default policy |
| Servlet Filter | Redirects/rewrites URLs, authentication, authorization | **UrlHandlerFilter**, Spring Security |
| Spring MVC HandlerMapping | Matches path and conditions for HTTP method, params, headers, consumes, produces | **@GetMapping("/api/items/{id}")** |
| Controller | Receives bound **@PathVariable** or **@RequestParam** | id, query, body |
| Error handling | Produces appropriate status and error response | **404** for endpoint not found |

**Important note:** if Tomcat or a proxy returns **400** before `DispatcherServlet` is invoked, modifying **@ControllerAdvice** or **@GetMapping** will not fix that error. Conversely, if the URL is valid yet `HandlerMapping` finds no mapping, changing the request body charset will not make the route match either.

## 3. Spring MVC Uses PathPatternParser to Match Paths

Modern Spring MVC prefers **PathPatternParser**. Spring Boot 3.5 uses this strategy by default.

Given the example:

~~~java
@GetMapping("/api/orders/{orderId}")
public String findOrder(@PathVariable String orderId) {
    return orderId;
}
~~~

- **/api/orders/42** matches and binds **orderId=42**.
- **/api/orders/42/** does not necessarily match because of the extra trailing slash.
- **/api/orders/42/items** does not match a single **{orderId}** variable.
- **/api/orders/C%C3%A0-ph%C3%AA** can be UTF-8 decoded and bound to the accented value, if the connector/proxy permits it.

### 3.1. PathPatternParser and AntPathMatcher

**PathPatternParser** splits the request path into segments and matches against pre-parsed patterns, avoiding decoding the entire path into a single `String` before matching. This matters because decoding characters like **%2F** (the `/` character) too early can alter segment count and security semantics.

**AntPathMatcher** is the historical String-based pattern matcher. In compatible Boot 3.x versions, you can configure:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

This is the default; normally **it does not need to be declared**. If a legacy app relies on incompatible patterns, Boot 3.5 still offers **ant-path-matcher** for special cases:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

However, **do not switch to AntPathMatcher just to "fix" a 404**. Doing so alters matching rules, affecting encoding, pattern specificity, and security. Find the root cause of the wrong URL/mapping first, and only use the fallback when backed by tests and concrete compatibility requirements.

**Path patterns to understand:**

| Pattern | Scope | Notes |
|---|---|---|
| **/api/items/{id}** | One dynamic path segment | **{id}** does not represent multiple segments automatically |
| **/api/items/{id:[0-9]+}** | Segment of digits only | Input failing regex does not match mapping |
| **/assets/*.png** | PNG filenames in a single segment | Does not include subdirectories |
| **/assets/** | Zero or more trailing segments | `**` in PathPattern must sit at the end of the pattern |
| **/assets/{*path}** | Captures multiple trailing segments into one variable | Valid only in trailing position |
| **/api/items** | Exact path | Does not automatically match **/api/items/** under MVC 6.x defaults |

In **PathPatternParser**, `**` cannot be placed arbitrarily in the middle of a pattern; for example, **/resources/**/file.png** is invalid. Use concrete patterns or redesign the path.

### 3.2. No More Implicit Suffix Matching

Since Spring MVC 5.3, suffix pattern matching where **/person** automatically matched **/person.json** is no longer enabled by default. Use the **Accept** header for media type negotiation, or declare explicit mappings if paths genuinely carry extensions.

Do not assume routes **/api/report**, **/api/report.json**, **/api/report/**, and **/api/report//** are equivalent.

## 4. Trailing Slashes: /resource and /resource/

A trailing slash is a final **/** at the end of a URL path; it is not the same as **/** separating segments in the middle.

Example:

~~~text
GET /api/products
GET /api/products/
~~~

With Spring MVC 6.x and a controller declaring only:

~~~java
@GetMapping("/api/products")
public List<Product> list() {
    // ...
}
~~~

the first URL has a handler, while the second **does not automatically** match. Depending on static resources and error handling configuration, clients may receive HTTP 404.

There is no single right answer for every API. Pick a **canonical URL policy**: whether the official public URL has a trailing slash or not, and how the app responds to the other variant.

### 4.1. Approach A: Declare Both Routes Explicitly

Suitable when only a few legacy endpoints must accept both forms:

~~~java
@GetMapping({"/api/products", "/api/products/"})
public List<Product> list() {
    // ...
}
~~~

Pros: explicit, avoids redirects, helpful for maintaining compatibility with legacy clients.

Cons: hard to keep policies synchronized across hundreds of endpoints; both URLs are processed directly, which can split cache keys, metrics, and URL canonicalization. If the app uses Spring Security, evaluate authorization rules for **both URLs** rather than assuming they are treated identically.

**Do not** apply this everywhere by adding two mappings to every method without reason and tests. For new APIs, prefer one consistent canonical URL.

### 4.2. Approach B: Redirect to the Canonical URL

If you choose the URL without a slash as canonical, a request:

~~~text
GET /api/hello/
~~~

can be redirected to:

~~~text
GET /api/hello
~~~

One option is **HTTP 308 Permanent Redirect**, which instructs clients to preserve the HTTP method and body when following the redirect. It fits long-term URL canonicalization. However, check caches, proxies, HTTP clients, SDKs, and retry behavior for `POST`/`PUT` or non-idempotent operations. Do not assume every client automatically follows redirects.

In Spring Framework 6.2, **UrlHandlerFilter** lets you configure trailing-slash redirects. Example:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/hello/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
~~~

This snippet uses imports **org.springframework.web.filter.UrlHandlerFilter** and **org.springframework.http.HttpStatus**; you must register the filter with the Servlet container, not merely assign a local variable. The complete example in Section 8 does this.

**Pros:** a single canonical URL for routing, caching, documentation, and access policies; clients can update the URLs they call.

**Cons:** redirects add a round-trip; caches or proxies may cache redirects for a long time; clients that do not follow redirects must be adjusted. Do not enable redirects blindly if HTTP method/body preservation or backward compatibility has not been verified.

### 4.3. Approach C: Rewrite the Request Before HandlerMapping

**UrlHandlerFilter** also has a **wrapRequest()** mode to present the slashless URL to Spring MVC without sending a redirect to the client.

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/hello/**")
        .wrapRequest()
        .build();
~~~

This is an illustrative snippet that must be registered as a Servlet Filter. The client still calls the URL with a slash, while downstream processing sees the normalized form. Because it returns no redirect, it can suit certain legacy systems, though **Filter order and URL-based authorization** require close attention.

When **ForwardedHeaderFilter** and Spring Security are present, the URL normalization filter should run **after** processing trusted forwarded headers and **before** security filters so Security and MVC see the exact same path. This is a requirement that must be tested, not merely a stylistic choice.

### 4.4. Why Not Re-Enable Implicit Trailing Slash Matching?

Spring Framework deprecated matching multiple paths automatically to the same handler because it could cause mismatches between authorization rules and MVC mappings. For example, Security protects **/admin** yet treats **/admin/** under a different rule while MVC considers them identical. A safer model is **explicit URL canonicalization** in a filter/gateway or explicit mapping declarations.

In Spring Framework 7.0, the old trailing slash match option was removed; therefore new code should adopt a long-term solution instead of deprecated APIs.

## 5. URI Encoding Is Not HTTP Body Character Encoding

A URI has distinct components:

~~~text
https://example.com/api/items/C%C3%A0%20ph%C3%AA?lang=vi#section
                     |---- path ------------|-- query --| fragment
~~~

The **fragment** after `#` is normally not sent to the server. In a URI path, **/** separates segments; in a query, **&** and **=** delimit key-value pairs.

**Percent-encoding** turns bytes into **%HH** sequences. For Unicode, characters are typically encoded as UTF-8 bytes and then required bytes are percent-encoded.

| Input | When Used as a Path Segment | When Used as a Query/Form Value |
|---|---|---|
| **Cà phê** | **C%C3%A0%20ph%C3%AA** | **C%C3%A0+ph%C3%AA** in form-style |
| **A+B** | **A+B** may be valid literally in a path | **A%2BB** to preserve the literal plus sign |
| **A&B** | **A&B** may be valid segment data but encode as needed | **A%26B** to avoid splitting parameters |
| **100%** | **100%25** when encoding a literal percent | **100%25** |
| **x/y** | Two segments if kept as literal `/` | If representing a single data value, see encoded slash notes |
| **foo#bar** | **foo%23bar** when `#` is data | **foo%23bar** |

**Never** use **URLEncoder.encode** to encode an entire URI or path: this Java API encodes according to **application/x-www-form-urlencoded** rules, turning spaces into plus signs (`+`). A plus sign in a path is not equivalent to a space as it is when decoding form values.

### 5.1. Building URIs Safely with UriComponentsBuilder

When a value is data, pass it as a URI template variable so Spring encodes it according to context:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String path = UriComponentsBuilder
        .fromPath("/api/items/{name}")
        .encode()
        .buildAndExpand("Cà phê & trà")
        .toUriString();

System.out.println(path);
~~~

Expected output:

~~~text
/api/items/C%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
~~~

This is an **illustrative snippet** in a project with Spring Web, not a standalone Java file without class, imports, and dependencies. In the URL, **&** is encoded because it is **data inside a path variable**, not a query separator.

Do not **pre-percent-encode** a value and then pass it again into an encoding builder; otherwise `%` can become **%25**, causing double-encoding. Similarly, do not URL-decode a **@PathVariable** a second time after Spring has already bound it, because double-decoding can introduce unexpected slashes or control characters.

### 5.2. Distinguishing @PathVariable and @RequestParam

With an endpoint:

~~~java
@GetMapping("/api/items/{id}")
public String item(@PathVariable String id) {
    return id;
}
~~~

**@PathVariable** extracts data from a path segment. Query parameters use **@RequestParam**:

~~~java
@GetMapping("/api/search")
public String search(@RequestParam String q) {
    return q;
}
~~~

For free-form values containing slashes, spaces, and reserved characters, a **query parameter** or JSON request body is usually easier to design than a path segment because it does not collide directly with route structure.

Setting **server.tomcat.uri-encoding: UTF-8** instructs Tomcat to decode URIs with UTF-8. It does not fix clients that encoded URLs incorrectly, does not force proxies to keep paths intact, and does not replace request body charset configuration.

## 6. Encoded Slash %2F and Sensitive Characters

**%2F** is a percent-encoded **/**. This is not merely an accented-character or charset issue: decoding it at different stages can change route structure.

For example, suppose a product code is entered as:

~~~text
group/item
~~~

If embedded raw into a URL segment:

~~~text
/api/items/group/item
~~~

Spring sees **two segments** after **/api/items/**, so mapping **/api/items/{id}** does not match.

If the client sends:

~~~text
/api/items/group%2Fitem
~~~

then **Tomcat 10.1 rejects encoded solidus in the request path with HTTP 400 by default** when property **encodedSolidusHandling** uses its default **reject**. Other connectors or proxies may have different policies. Do not write tests assuming `%2F` is always decoded into a slash character inside `@PathVariable`.

Tomcat offers these encoded solidus handling modes:

| Connector Mode | Basic Meaning | Risks to Consider |
|---|---|---|
| **reject** (Tomcat 10.1 default) | Rejects paths containing **%2F** | Prevents path ambiguity |
| **decode** | Decodes into a slash | Can change path segment count or routing |
| **passthrough** | Passes encoded sequence to downstream layers | Requires controlling decoding downstream and alignment with proxies |

This is a **Tomcat connector property**, not a universal MVC property across all servers. Do not change this policy just to make a malformed request URL succeed. If a business identifier contains slashes, a simpler and safer solution is passing it in a **query parameter**, **request body**, or mapping it to a slash-free ID.

Additional characters and patterns to watch out for:

- **%5C**: encoded backslash, prone to discrepancies across OSes, proxies, and backends.
- **%2E** or **.** and **..** segments: can relate to path normalization/traversal.
- **%25**: encoded literal percent; double-decoding can synthesize new escape sequences.
- **;**: path parameter/matrix variable; parsers and containers enforce specific rules—do not strip or allow them indiscriminately.
- **%00**: NUL or control characters should not be broadly accepted.
- **//**: repeated slashes may be normalized differently by proxies/containers; do not rely on implicit behavior.

**Spring's segment-based `PathPatternParser`** avoids several problems of decoding the whole path eagerly, yet it **cannot bypass connector or WAF rejection policies**. Having `PathPatternParser` does not automatically make all encoded slashes safe either.

### 6.1. Why Not Broaden relaxed-path-chars Indiscriminately?

Tomcat has options such as **relaxedPathChars** and **relaxedQueryChars** for certain characters in the request-target. Their general purpose is not to "re-decode every URL," and they do not replace **encodedSolidusHandling**. Expanding accepted characters can introduce discrepancies with gateways, Spring Security's firewall, or caches.

If you are forced to support a special URI form, build a threat model, verify behavior at each layer, scope it narrowly, and add integration tests for path traversal, double encoding, authorization, and caching.

## 7. An Unmatched Path Does Not Always Mean HTTP 404

**@RequestMapping** has multiple conditions: URL path, HTTP method, request params, headers, **consumes**, and **produces**. Even with a valid URL path, a handler may still fail to match because of the other conditions.

| Request | Possible Cause | Typical HTTP Status |
|---|---|---|
| **GET /api/items/42** | Matching GET + path | **200**, or controller's response |
| **GET /api/items/42/** | Mapping declares only **/{id}**; extra trailing slash | **404** |
| **GET /api/unknown** | No matching controller/static resource | **404** |
| **POST /api/items/42** | Path has a GET handler but not POST | **405 Method Not Allowed** |
| **POST /api/items** with wrong **Content-Type** | Mapping requires JSON, sent `text/plain` | **415 Unsupported Media Type** |
| **GET /api/items** with unsupported **Accept** | Mapping/produces has no matching media type | **406 Not Acceptable** |
| **GET /api/items/abc** to **@PathVariable long id** | Numeric conversion fails once mapping is chosen | **400 Bad Request** |
| Request has malformed percent escape or blocked encoded slash | Container or proxy rejects URI | **400**, sometimes blocked before Spring |
| Request to protected endpoint | Unauthenticated or insufficient permissions | **401/403**, depends on Security |
| URL through canonical redirect | Redirect policy active | **308** or configured redirect status |

Not every row occurs in every application; exact status depends on controllers, exception handlers, static mappings, and server configuration. This table guides **layer-by-layer diagnosis**, not fixed values for every project.

### 7.1. NoHandlerFoundException and NoResourceFoundException

In Spring Boot Servlet MVC, static content is typically mapped to `/**` (a wildcard pattern of `/` followed by two asterisks). Because the static resource handler can act as a catch-all handler, a request matching no controller may still be routed to **ResourceHttpRequestHandler**. When no matching file exists, Spring MVC can throw **NoResourceFoundException** instead of **NoHandlerFoundException**.

To avoid syntax ambiguity, the default static resource pattern can be written in code as:

~~~text
/**
~~~

Important takeaway: **do not** rely solely on `@ExceptionHandler(NoHandlerFoundException.class)` and assume it will catch every 404. In Spring Boot 3.5, if no controller handler is found and default static resource mapping is active, the error normally flows through the resource handler mechanism.

If an application is REST-only and intentionally **does not serve static resources**, you can disable static resource mappings:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

Then **NoHandlerFoundException** can be triggered more directly for unmatched routes. However, disabling these mappings also affects static files, welcome pages, or UI assets if the project uses them. Only change this after evaluating product requirements and testing.

Another option is scoping static resource mappings:

~~~yaml
spring:
  mvc:
    static-path-pattern: /assets/**
~~~

This confines static resources to the **/assets/** URL region, reducing the chance of the static resource handler catching nonexistent API requests. Error behavior varies by deployment setup.

### 7.2. Where Is 404 Handled?

**Spring MVC** has resolvers and handlers for errors occurring inside `DispatcherServlet`. **Spring Boot** also provides the Servlet error mechanism at **/error**, where status/body can differ by **Accept** header and error-handling properties. If a container or gateway returns 400/404 before the request reaches the application, controller advice will never see that exception.

For APIs, use **ProblemDetail**, **@RestControllerAdvice**, or a structured error contract with safe messages if needed. Do not return HTTP 200 with error JSON saying "route not found" for every request.

### 7.3. Server Path and Context Path Configuration

An unmatched URL can also result from a modified prefix:

~~~yaml
server:
  servlet:
    context-path: /app
  port: 8081
~~~

If a controller maps **/api/items**, the effective URL is:

~~~text
http://localhost:8081/app/api/items
~~~

Do not put **/app** in every **@RequestMapping**; the container context path is handled at a separate layer. Likewise, when a reverse proxy adds or strips a **/gateway** prefix, verify routing rules before editing controller mappings.

**spring.mvc.servlet.path** and `DispatcherServlet` prefix mapping have specific limitations with path matching in certain Boot releases. Do not switch to a servlet path prefix without understanding its effects; for adding a public prefix, consider context path or properly configured gateway routing.

## 8. Complete Spring Boot Example: Slash Routes, Redirect, Query, and Encoded Path

The example below uses Spring Boot **3.5.0**, Java **17**, and Maven. It demonstrates **two different policies on different routes** for comparison:

- **/api/catalog** and **/api/catalog/** both match because the controller declares two mappings.
- **/api/hello** is the canonical URL; **/api/hello/** is redirected by a **UrlHandlerFilter** to the URL without a slash.
- **/api/items/{id}** uses a path variable; **/api/search?q=...** uses a query parameter.
- **/api/unknown** has no controller; Spring Boot returns 404 according to active error handling.

### 8.1. Structure

~~~text
mvc-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   ├── RoutingController.java
    │   │   └── CanonicalUrlConfig.java
    │   └── resources/application.yml
    └── test/java/com/example/routing/
        └── RoutingTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-routing-demo</artifactId>
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

Dependencies have versions managed by Spring Boot, with no need to declare `spring-webmvc` or Tomcat separately. In a production project, use a Spring Boot patch release on an actively maintained and organization-approved branch.

### 8.3. RoutingApplication.java

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

### 8.4. RoutingController.java

~~~java
package com.example.routing;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RoutingController {

    @GetMapping({"/catalog", "/catalog/"})
    public Map<String, String> catalog() {
        return Map.of("result", "catalog");
    }

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }

    @GetMapping("/items/{id}")
    public ItemResult item(@PathVariable String id) {
        return new ItemResult(id);
    }

    @GetMapping("/search")
    public QueryResult search(@RequestParam String q) {
        return new QueryResult(q);
    }

    public record ItemResult(String id) {}
    public record QueryResult(String q) {}
}
~~~

The records are DTOs serialized to JSON by Jackson. With **@GetMapping("/items/{id}")**, an ID with an internal slash is not automatically a valid single segment. If a business ID contains a slash, such as **team/project**, design the API to use a query/body parameter instead of modifying the connector to allow encoded slashes.

### 8.5. CanonicalUrlConfig.java

~~~java
package com.example.routing;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

@Configuration
public class CanonicalUrlConfig {

    @Bean
    public FilterRegistrationBean<UrlHandlerFilter> canonicalSlashFilter() {
        UrlHandlerFilter filter = UrlHandlerFilter
                .trailingSlashHandler("/api/hello/**")
                .redirect(HttpStatus.PERMANENT_REDIRECT)
                .build();

        FilterRegistrationBean<UrlHandlerFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.addUrlPatterns("/*");
        return registration;
    }
}
~~~

Notes:

- **FilterRegistrationBean** registers `UrlHandlerFilter` with the Servlet container. The filter only **performs the redirect behavior** on paths matching its configured rules.
- Pattern **/api/hello/** is used to demonstrate narrow scoping; route **/api/catalog/** has its own policy and is not altered by this filter.
- With proxies and Spring Security, **filter order** must be designed so trusted forwarded headers are processed first, and authorization decisions see the same canonical path form as MVC. This simple example includes neither Spring Security nor a reverse proxy.
- If normalizing multiple endpoints, define scope clearly and add tests for exceptions; do not enable rewrites for all URLs without assessing impact.

### 8.6. application.yml

~~~yaml
server:
  port: 8080
  tomcat:
    uri-encoding: UTF-8

spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

These two properties illustrate related configuration. They do not enable optional trailing slash matching automatically; the configured routes and filter handle that rule.

### 8.7. Running and Testing with curl

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or build the JAR and run it:

~~~bash
mvn clean package
java -jar target/mvc-routing-demo-1.0.0.jar
~~~

**Test A – Two Explicit Mappings**

~~~bash
curl -i "http://localhost:8080/api/catalog"
curl -i "http://localhost:8080/api/catalog/"
~~~

Both requests expect **HTTP 200** with body:

~~~json
{"result":"catalog"}
~~~

**Test B – Canonical URL and Redirect**

~~~bash
curl -i "http://localhost:8080/api/hello"
curl -i "http://localhost:8080/api/hello/"
~~~

The first URL expects **HTTP 200** with:

~~~json
{"message":"hello"}
~~~

The second URL expects **HTTP 308** with a **Location** header pointing to the slashless URL. A redirect does not mean the controller ran for the first request; the client must follow through to the canonical URL.

To test a client following the redirect:

~~~bash
curl -i -L "http://localhost:8080/api/hello/"
~~~

**Test C – Unicode in Path**

~~~bash
curl -i "http://localhost:8080/api/items/C%C3%A0%20ph%C3%AA"
~~~

If the connector accepts valid UTF-8 URIs, expected response:

~~~json
{"id":"Cà phê"}
~~~

Do not take this test as a guarantee that **%2F** is also accepted: encoded slashes have a separate policy.

**Test D – Query Parameter with Special Characters**

~~~bash
curl -i --get \
  --data-urlencode "q=Cà phê & trà" \
  "http://localhost:8080/api/search"
~~~

Expected response body:

~~~json
{"q":"Cà phê & trà"}
~~~

**Test E – Nonexistent Route**

~~~bash
curl -i "http://localhost:8080/api/unknown"
~~~

Expect **HTTP 404**. The body depends on the error handler and `Accept` header, so do not assume a fixed JSON body when unconfigured.

**Test F – Wrong HTTP Method**

~~~bash
curl -i -X POST "http://localhost:8080/api/hello"
~~~

Expect **HTTP 405 Method Not Allowed** because the controller only declares `GET`.

**Test G – Encoded Slash Rejected by Tomcat Default**

~~~bash
curl -i "http://localhost:8080/api/items/team%2Fproject"
~~~

With default Tomcat 10.1 configuration, expect the request to be rejected (usually **HTTP 400**) before the controller binds the path variable. Do not reconfigure Tomcat just to make this test return 200; it proves the safety policy is working.

Multi-line `curl` commands use Bash syntax. On PowerShell, use **curl.exe** on a single line with appropriate escaping.

## 9. Automated Testing with MockMvc

**MockMvc** tests mappings, filters registered in the test context, and Spring MVC status codes. However, it **does not open a real Tomcat socket**, so it does not replace the encoded slash check in Section 8, where the connector can reject the request before Spring is called.

Create file **src/test/java/com/example/routing/RoutingTest.java**:

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsBothExplicitCatalogRoutes() throws Exception {
        mvc.perform(get("/api/catalog"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("catalog"));

        mvc.perform(get("/api/catalog/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("catalog"));
    }

    @Test
    void redirectsTrailingSlashOnCanonicalHello() throws Exception {
        mvc.perform(get("/api/hello/"))
                .andExpect(status().isPermanentRedirect());
    }

    @Test
    void respondsOnCanonicalHello() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("hello"));
    }

    @Test
    void retainsUnicodeQueryValue() throws Exception {
        mvc.perform(get("/api/search").param("q", "Cà phê & trà"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.q").value("Cà phê & trà"));
    }

    @Test
    void unknownPathIsNotFound() throws Exception {
        mvc.perform(get("/api/unknown"))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodIsNotAllowed() throws Exception {
        mvc.perform(post("/api/hello"))
                .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Tests succeed when Maven exits with code 0. Test plugin stdout summaries can vary by version; do not rely on a fixed log string.

**Distinguishing test scope:** `MockMvc` is well-suited for Spring MVC routes and exception resolvers, yet integration tests against **real embedded Tomcat** or a gateway environment are necessary to evaluate encoded slashes, invalid request-targets, reverse proxy rewrites, and firewall policies. Filter ordering in environments with Spring Security must also be verified empirically.

## 10. Step-by-Step Diagnosis of 404, 400, and Path-Matching Failures

When a URL does not reach the expected controller, proceed in this order:

1. **Capture the actual HTTP request:** method, exact URL (including trailing slash and percent escapes), `Host`, query, `Content-Type`, `Accept`, and status. Use **curl -i** or **curl -v** and check proxy logs.
2. **Confirm whether the request reached the backend:** if blocked at ingress/WAF/Tomcat, Spring MVC mapping never gets a chance to run.
3. **Check context path and proxy prefix:** the external gateway URL may differ from the URL `DispatcherServlet` sees.
4. **Check canonical form:** are **/resource** and **/resource/** declared separately or handled by a redirect filter?
5. **Check encoded characters:** were **%2F**, **%25**, `+` signs, Unicode, and escaped reserved characters generated properly by the client?
6. **Check mapping annotations:** class-level + method-level paths, HTTP method, params, headers, `consumes`, `produces`, path variable regexes, and wildcard paths.
7. **Check matching strategy:** default `PathPatternParser`, whether the pattern is valid, and whether specificity selected another handler.
8. **Check static resources:** is a wildcard **/** handler covering the path and throwing `NoResourceFoundException`?
9. **Check security/filters:** are authorization rules different for the canonical URL versus the URL with a trailing slash?
10. **Write a reproducing test:** one MVC mapping test, one real HTTP test with Tomcat, and one test through the proxy if production uses a gateway.

### 10.1. Using Actuator to Inspect Actual Mappings

In environments where observability is appropriate, you can add **spring-boot-starter-actuator** and inspect the **mappings** endpoint to see registered handlers. This endpoint **should never be exposed publicly to the Internet**; expose it only over an admin network or with appropriate access controls.

Example enabled in a local development environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,mappings
~~~

Verify the actuator path according to application configuration and protect the mappings endpoint. It shows registered routes, though it does not replace testing URLs behind proxies or container policies.

### 10.2. Controlled Diagnostic Logging

You can temporarily enable logs in a dev environment:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.servlet.DispatcherServlet: DEBUG
~~~

These loggers are helpful for investigating handler mappings; do not leave `TRACE` enabled long-term in production or log URLs containing tokens or sensitive information without a redaction policy.

### 10.3. @ExceptionHandler Cannot Fix Every URL

**@RestControllerAdvice** can standardize the body of Spring MVC errors once a request is handed to the framework. However, if a URL never reaches the backend, Tomcat returns 400, a WAF blocks it, or a Spring Security filter rejects the request, `ControllerAdvice` will not intervene automatically.

If unified error JSON is needed across all layers, design an error contract across the proxy, security filters, and backend rather than putting all responsibility on one advice class.

## 11. Security: Canonical Paths Must Align with Authorization

Paths can be interpreted differently between:

- CDN/gateway and backend.
- Spring Security matchers and Spring MVC `HandlerMapping`.
- Servlet container and custom filters.
- Initial request and path after redirect/rewrite.

For example, if a security rule protects **/admin** yet not **/admin/**, an MVC setup allowing both paths into the same controller can cause an access-control discrepancy. That is why Spring encourages explicit path canonicalization.

Principles:

1. Choose a canonical URL for each endpoint, and update API docs and link generation.
2. If supporting trailing slashes, place the redirect/rewrite policy in the right position relative to Spring Security.
3. Do not change connector properties for encoded slashes/backslashes without evaluating path traversal and authorization bypass risks.
4. Never double URL-decode; decoding an already decoded percent string can synthesize new path structures.
5. Never blindly trust **X-Forwarded-\*** headers from the Internet; accept headers only when set/reset by a trusted proxy.
6. Cross-test **/admin**, **/admin/**, **/admin%2F**, repeated slashes, and casing variants whenever security rules depend on paths.
7. Do not automatically redirect every unknown request to a valid endpoint; 404 errors help detect mistyped routes and separate API namespaces.
8. Broaden route patterns only to match genuine business needs; never use overly wide wildcards as a "catch-all" to work around mismatches.

For public APIs, a **308** redirect is usually clearer about the canonical URL than a silent rewrite, though the choice must factor in client redirect-following capabilities and supported API contracts.

## 12. Quick Error and Resolution Table

| Symptom | Typical Cause | Preferred Fix |
|---|---|---|
| **/api/items** returns 200, **/api/items/** returns 404 | Trailing slash does not auto-match | Choose canonical URL; declare two routes or use `UrlHandlerFilter` |
| Trailing slash returns 308 yet client fails | Client does not follow redirects, or gateway/cache holds redirect | Update client URL and redirect policy |
| Accented Vietnamese characters in path are corrupted | Client/proxy did not UTF-8 encode properly | Check URI percent-encoding, **server.tomcat.uri-encoding** |
| **%2F** returns 400 | Tomcat/WAF rejects encoded slash | Use query/body for IDs with slashes; do not relax connector casually |
| **A+B** in query becomes **A B** | `+` was not encoded as `%2B` in form-style | Use a URI builder or `data-urlencode` |
| Path matches yet returns 405 | Wrong HTTP method | Fix client method or mapping explicitly |
| POST JSON returns 415 | `Content-Type` does not match `consumes` | Set `Content-Type` and inspect mapping |
| GET returns 406 | `Accept` incompatible with `produces` | Adjust `Accept`/media type |
| **/api/123** misses `@GetMapping` with regex ID | Input does not match `PathPattern` regex | Check constraint and pattern |
| 404 bypasses `NoHandlerFoundException` | Static resource `/**` catches request first | Check **NoResourceFoundException** or adjust static path pattern |
| MockMvc test passes, production fails | Proxy/Tomcat normalization or Security filter differences | Test over real HTTP and through gateway |
| 404 occurs only after changing context path | Client URL missing prefix | Check **server.servlet.context-path** and proxy routing |
| Wrong handler captures another endpoint | Overly broad wildcard or mapping specificity | Use tighter patterns and inspect Actuator mappings |
| 403 appears only on URL with trailing slash | Authorization matcher and MVC interpret path differently | Normalize before Security and test all variants |

## 13. Pre-Production Checklist

- [ ] Identify exact Spring Boot/Spring Framework/Tomcat versions and actual path matching strategy.
- [ ] Publish a canonical URL policy for trailing slashes, including redirect status if applicable.
- [ ] Ensure HTTP clients/SDKs construct each URI component with a compliant URI builder.
- [ ] Set UTF-8 for URI encoding; test non-ASCII characters and plus signs in queries/forms.
- [ ] Never decode URLs twice, and do not enable encoded slashes by default to patch routing bugs.
- [ ] Verify path matching for HTTP methods, params, headers, `consumes`, `produces`, and wildcards.
- [ ] Verify static resource paths and distinguish `NoHandlerFoundException` from `NoResourceFoundException`.
- [ ] Verify Filter ordering and Security matchers with both slash and slashless URLs.
- [ ] Include both `MockMvc` tests **and** real Tomcat/gateway tests for encoded slashes, percent signs, and path normalization.
- [ ] Differentiate 400/404/405/308 in logs and metrics without leaking sensitive URLs.
- [ ] Expose Actuator `mappings` only under appropriate access controls.
- [ ] Maintain API documentation and a migration plan when changing canonical URLs.

## 14. Official References

1. Spring Framework 6.2 – Path Matching: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html
2. Spring Framework 6.2 – Mapping Requests and PathPattern: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
3. Spring Framework 6.2 – Filters and UrlHandlerFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
4. Spring Framework 6.2 – URI Links / Encoding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html
5. Spring Boot 3.5 – Servlet Web Applications, Path Matching, and NoHandlerFoundException: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. Apache Tomcat 10.1 – HTTP Connector, encodedSolidusHandling/URIEncoding: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
8. RFC 3986 – URI Generic Syntax: https://www.rfc-editor.org/rfc/rfc3986
9. Spring Security – HTTP Firewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html

**Conclusion:** Handling trailing slashes, encoded characters, and unmatched paths properly requires clarifying the boundaries across **client → proxy → Servlet container → Filter/Security → Spring MVC HandlerMapping**. Spring MVC 6.x does not treat **/resource/** as equivalent to **/resource** automatically. Use canonical URLs and `UrlHandlerFilter` or explicit dual mappings; let a URI builder encode data per component; keep safe connector policies; and diagnose 400/404/405 at the exact layer where they arise. Always test both Spring MVC and the real HTTP path.
