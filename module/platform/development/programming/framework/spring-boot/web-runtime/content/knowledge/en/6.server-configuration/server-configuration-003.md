# server.servlet.context-path, spring.mvc.servlet.path, and spring.webflux.base-path in Spring Boot

> **Scope:** Spring Boot **3.5.x**, Java **17+**. This lesson distinguishes three URL configuration properties in a Spring Boot application, how they affect **Spring MVC (Servlet)** and **Spring WebFlux (reactive)**, how the final URL is calculated, runnable Maven examples, integration tests, and common errors. The examples set the Spring Boot version to **3.5.0** for consistent dependency/import structure; when upgrading, read the documentation for your running version.

## 1. Three Properties That All Talk About "Paths", Yet Act at Three Different Layers

In HTTP, a URL can be pictured as:

~~~text
scheme://host:port / context-path / servlet-path / controller-mapping ? query

MVC example:
http://localhost:8080 /portal       /api          /hello

WebFlux example:
http://localhost:8081 /gateway                    /hello
~~~

**Note:** This is a mental model for combining path parts, not configuration syntax or URL decomposition rules applicable to every server. In the case of the Servlet API, `contextPath` and `servletPath` are also concrete concepts in `HttpServletRequest`.

| Property | Applies To | Impact Level | When endpoint is `@GetMapping("/hello")` |
|---|---|---|---|
| `server.servlet.context-path=/portal` | **Servlet** applications like Spring MVC | Context path of the web application inside the servlet container | `/portal/hello` if DispatcherServlet is at default |
| `spring.mvc.servlet.path=/api` | **Spring MVC** | Mapping/prefix of `DispatcherServlet` | `/api/hello` if context path is default |
| `spring.webflux.base-path=/gateway` | **Spring WebFlux** | Base path for WebFlux web handlers | `/gateway/hello` in a reactive app |
| `server.port=8080` | Both types when using the corresponding embedded server | TCP port | Only changes `host:port`, does not add a prefix |

These properties **cannot be arbitrarily substituted for one another**. Switching from Servlet MVC to WebFlux means changing the web stack and dependencies, not merely renaming a property.

The default values are usually an empty/root context path, DispatcherServlet mapping `/`, and no WebFlux base path prefix. When paths are unchanged, a `/hello` controller usually has the URL `http://localhost:8080/hello`.

## 2. `server.servlet.context-path`: The Path of the Entire Servlet Application

This is the **web application context path** according to the Servlet API, used by embedded Tomcat/Jetty/Undertow when running Spring MVC. In `application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/portal
~~~

Simple controller:

~~~java
@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
~~~

If `spring.mvc.servlet.path` is not configured, the URL to test is:

~~~http
GET http://localhost:8080/portal/hello
~~~

Not `http://localhost:8080/hello`.

**Impact scope:** the context path places the Servlet application under the `/portal` prefix. It can affect servlets, filters, MVC controllers, servlet registrations, static resources, endpoints deployed in the same context, and session cookie paths. This is why this property should be preferred when the requirement is "run the entire Servlet application under `/portal`".

Servlet API example: on a `/portal/hello` request, `request.getContextPath()` is typically `/portal`. The controller still declares `@GetMapping("/hello")`: there is no need to add `/portal` to the annotation.

**Do not confuse with a reverse proxy:** if the application runs in a container at context path `/portal` while an API gateway exposes `https://example.com/app/portal/hello`, the `/app` part may be added or rewritten by the proxy. `server.servlet.context-path` only describes the context served by the servlet container inside the application.

## 3. `spring.mvc.servlet.path`: Prefix of DispatcherServlet in Spring MVC

`DispatcherServlet` is Spring MVC's central servlet: it receives requests destined for MVC and coordinates `HandlerMapping`, controllers, converters, and view resolvers. By default it handles the root of the Servlet context, usually mapped at `/`.

In an MVC application:

~~~properties
spring.mvc.servlet.path=/api
~~~

A `@GetMapping("/hello")` controller will be accessed via `/api/hello` (with the default context path). This property **changes the mapping of DispatcherServlet**, not the Servlet context path of the entire application.

Suppose the application registers an additional standalone servlet that does not go through Spring MVC. That servlet can have its own mapping, is subject to `server.servlet.context-path`, and is **not automatically** subject to the MVC DispatcherServlet prefix. This is the practical difference between the two properties.

### 3.1. Mandatory Note in Spring Boot 3.5: PathPatternParser

In Spring Boot 3.5.x, Spring MVC uses the `PathPatternParser` strategy by default to match URLs against controllers. According to the official documentation, this strategy is **incompatible with setting a prefix via `spring.mvc.servlet.path`**.

Therefore, when using a DispatcherServlet prefix in Spring Boot 3.5.x, you need to configure a different strategy:

~~~properties
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

When setting only `server.servlet.context-path` while leaving DispatcherServlet at its default mapping, there is no need to switch to `ant-path-matcher` because the context path alone does not create a servlet path prefix mapping.

**Design consequence:** changing the matching strategy can affect how route patterns, trailing slashes, placeholders, and wildcard patterns are interpreted. After changing it, re-run tests for controller mappings with complex patterns. Do not copy the configuration above to another Boot version without checking that version's documentation.

The Boot 3.5 documentation explicitly notes this incompatibility and gives the `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` example in the Servlet Web Applications section.

## 4. When Combining Both Spring MVC Prefixes

Example:

~~~properties
server.port=8080
server.servlet.context-path=/portal
spring.mvc.servlet.path=/api
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

With:

~~~java
@RestController
@RequestMapping("/v1")
class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }
}
~~~

The path is assembled as follows:

~~~text
/portal      + /api              + /v1       + /hello
(context)      (DispatcherServlet) (class)     (method)

=> /portal/api/v1/hello
~~~

The URL to call is `http://localhost:8080/portal/api/v1/hello`.

Do not change the controller to `@RequestMapping("/portal/api/v1")`: once both prefixes are configured, doing so duplicates the prefixes in the path (and easily causes 404). Controller annotations describe the route **inside Spring MVC**, not the context path or the mapping of DispatcherServlet itself.

Example table with the same `@GetMapping("/hello")` method, **without class-level `@RequestMapping`**:

| `server.servlet.context-path` | `spring.mvc.servlet.path` | Outermost Path |
|---|---|---|
| Not set | Not set | `/hello` |
| `/portal` | Not set | `/portal/hello` |
| Not set | `/api` | `/api/hello` |
| `/portal` | `/api` | `/portal/api/hello` |
| `/store` | `/rest` | `/store/rest/hello` |

In rows where `spring.mvc.servlet.path` differs from the default, examples in this lesson using Spring Boot 3.5.x assume `ant-path-matcher` is configured.

## 5. Complete Runnable Spring MVC Maven Example

Set up a project with the structure:

~~~text
mvc-path-demo/
  pom.xml
  src/
    main/
      java/
        com/example/mvcpaths/
          MvcPathsApplication.java
          HelloController.java
      resources/
        application.properties
    test/
      java/
        com/example/mvcpaths/
          HelloControllerIntegrationTest.java
~~~

### 5.1. Maven build

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
    <artifactId>mvc-path-demo</artifactId>
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

The project uses `spring-boot-starter-web`, meaning **Spring MVC on the Servlet stack**. Setting `spring.webflux.base-path` in this project does not change MVC controller paths.

### 5.2. Controller and Entry Point

Create `src/main/java/com/example/mvcpaths/MvcPathsApplication.java`:

~~~java
package com.example.mvcpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcPathsApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/mvcpaths/HelloController.java`:

~~~java
package com.example.mvcpaths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1")
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello mvc";
    }
}
~~~

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Entire Servlet application runs under /portal:
server.servlet.context-path=/portal

# Spring MVC DispatcherServlet runs under /api:
spring.mvc.servlet.path=/api

# Spring Boot 3.5: DispatcherServlet prefix is incompatible
# with the default PathPatternParser:
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or build the JAR:

~~~bash
mvn clean package
java -jar target/mvc-path-demo-1.0.0.jar
~~~

Correct request:

~~~bash
curl -i http://localhost:8080/portal/api/v1/hello
~~~

Expected controller response body:

~~~text
hello mvc
~~~

Try calling while missing one prefix:

~~~bash
curl -i http://localhost:8080/portal/v1/hello
curl -i http://localhost:8080/api/v1/hello
~~~

In the sample app (with no other controllers for those two paths), the requests will not match a controller and will typically return HTTP **404 Not Found**.

If `8080` is already in use, you can run on another port via program arguments:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

The port changes to 9090, while **the path `/portal/api/v1/hello` stays the same**.

### 5.3. Integration Testing on a Dynamic Port

Create `src/test/java/com/example/mvcpaths/HelloControllerIntegrationTest.java`:

~~~java
package com.example.mvcpaths;

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
class HelloControllerIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void receivesRequestWithContextAndServletPrefix() throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/portal/api/v1/hello");
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());
        assertEquals("hello mvc", response.body());
    }

    @Test
    void doesNotMatchWhenServletPrefixIsMissing() throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/portal/v1/hello");
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(404, response.statusCode());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

In the test, `RANDOM_PORT` starts a real embedded server on an OS-chosen port; `@LocalServerPort` receives the actual port. `server.servlet.context-path` and `spring.mvc.servlet.path` still apply, because `RANDOM_PORT` changes the port rather than removing prefixes.

**Note on `MockMvc`:** when using mock requests instead of a real web server, you may need to specify `contextPath` and `servletPath` in the request builder to accurately reproduce the servlet URL. If the goal is to verify the final URL a client calls, a real HTTP integration test as above is clearer.

## 6. `spring.webflux.base-path`: Base Path for WebFlux Applications

Spring WebFlux is Spring's reactive programming stack. When an application uses WebFlux running on Reactor Netty (without Spring MVC's Servlet context), the property:

~~~properties
spring.webflux.base-path=/gateway
~~~

sets the base path for **WebFlux web handlers**. For example, a reactive controller `@GetMapping("/hello")` is accessed at `/gateway/hello`.

This configuration is not an alias for `server.servlet.context-path` and is not a `DispatcherServlet` mapping: a pure WebFlux application does not process HTTP through the MVC DispatcherServlet.

### 6.1. Standalone WebFlux Maven Project

Create a **separate** project with the structure:

~~~text
webflux-path-demo/
  pom.xml
  src/main/java/com/example/webfluxpaths/ReactivePathsApplication.java
  src/main/resources/application.properties
~~~

`pom.xml`:

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
    <artifactId>webflux-path-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/java/com/example/webfluxpaths/ReactivePathsApplication.java`:

~~~java
package com.example.webfluxpaths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactivePathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactivePathsApplication.class, args);
    }
}

@RestController
class ReactiveHelloController {
    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("hello reactive");
    }
}
~~~

To put both classes in this file, only `ReactivePathsApplication` is `public`; `ReactiveHelloController` is a package-private top-level class, **valid syntax in Java 17**. The filename matches the public class.

`src/main/resources/application.properties`:

~~~properties
server.port=8081
spring.webflux.base-path=/gateway
~~~

Run:

~~~bash
mvn spring-boot:run
~~~

Call:

~~~bash
curl -i http://localhost:8081/gateway/hello
~~~

Response body:

~~~text
hello reactive
~~~

If there is no other handler, `http://localhost:8081/hello` typically returns **404** because `/gateway` is missing. When using WebFlux router functions (`RouterFunction`) instead of annotated controllers, the WebFlux base path still applies to the web handlers configured by Spring Boot.

In this standalone WebFlux project, `server.servlet.context-path` and `spring.mvc.servlet.path` are **not needed**: they belong to Servlet/MVC and are not how URLs are configured for Reactor Netty WebFlux.

### 6.2. When Both Web Starters Are Present

If a project has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally **prefers the Servlet MVC application type** when auto-detecting the web application type. A WebFlux dependency does not automatically switch controllers to the reactive stack.

Therefore, if you configure `spring.webflux.base-path=/gateway` and MVC URLs do not change, check your dependencies and the actual web application type running. Do not try mixing all three properties to force URLs to work. Determine whether the application is on **MVC** or **WebFlux** first, then pick the property matching the stack.

## 7. YAML Equivalents and Environment-Based Configuration Changes

### 7.1. Spring MVC (Servlet)

`application.yml`:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /portal

spring:
  mvc:
    servlet:
      path: /api
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

These values are equivalent to the MVC example in `application.properties`. Do not put the **same property with two conflicting values** in multiple configuration sources and guess the override order by intuition: precedence also depends on command-line args, environment variables, profiles, and config sources.

### 7.2. WebFlux

`application.yml`:

~~~yaml
server:
  port: 8081

spring:
  webflux:
    base-path: /gateway
~~~

If you only want a public API to appear under a prefix, the configuration choice can reside at the **application** or the **gateway/ingress**. When a reverse proxy performs rewrites, you must determine whether the proxy forwards the prefix to the backend or strips it; configuring it twice at both the proxy and the app can lead to **404** or duplicated URLs.

### 7.3. Corresponding Environment Variables

Spring Boot supports relaxed binding for property keys; common environment variable names in containers:

~~~text
SERVER_SERVLET_CONTEXT_PATH=/portal
SPRING_MVC_SERVLET_PATH=/api
SPRING_WEBFLUX_BASE_PATH=/gateway
~~~

Set **only the variables meaningful for the current web stack**. If using `spring.mvc.servlet.path` with Spring Boot 3.5.x, remember the matching strategy, for example `SPRING_MVC_PATHMATCH_MATCHINGSTRATEGY=ant-path-matcher` or placing the configuration in a file.

## 8. Explanation by Request Processing Layer

### 8.1. Servlet MVC

A request reaches an MVC application through a simplified chain:

~~~text
HTTP client
    |
    v
embedded Servlet container (Tomcat/Jetty/Undertow)
    |
    +-- matches Servlet context: /portal
    |
    +-- routes servlet mapping: /api/*
            |
            v
        Spring MVC DispatcherServlet
            |
            +-- looks up controller for /v1/hello
                    |
                    v
              @RequestMapping("/v1") + @GetMapping("/hello")
~~~

Two configuration levels sit outside the controller's mapping. When inspecting `HttpServletRequest`, the three methods `getContextPath()`, `getServletPath()`, and `getPathInfo()` help identify how the container split the request. The exact values of `servletPath` and `pathInfo` depend on the servlet mapping style, so do not always assume they are segments like a simple `split("/")`.

### 8.2. WebFlux on Reactor Netty

~~~text
HTTP client
    |
    v
Reactive server (e.g. Reactor Netty)
    |
    +-- WebFlux base-path: /gateway
            |
            v
        WebFlux HandlerMapping
            |
            +-- route /hello
                    |
                    v
              @GetMapping("/hello") or RouterFunction
~~~

In this WebFlux application there is no Servlet context path per the Servlet API, so do not add `server.servlet.context-path` onto `spring.webflux.base-path`.

## 9. Spring Security, Actuator, Static Files, and OpenAPI

These three properties do not only affect controllers. Changing a prefix can impact configuration and paths of subsystems.

### Spring Security

With Spring MVC, the security filter chain is part of the Servlet application, and request matchers may evaluate the servlet path in ways depending on the matcher type and Spring Security version. If you change `spring.mvc.servlet.path`, inspect **all API protection rules**; do not assume a pattern used before changing the prefix still matches identically afterward.

Key tests: public endpoints must be accessible, authenticated endpoints must return 401/appropriate redirect, role-restricted endpoints must return 403 when denied, and malformed URLs must not accidentally bypass authentication.

With WebFlux, security relies on the reactive `SecurityWebFilterChain`, which differs from the servlet `SecurityFilterChain`. Do not copy matchers verbatim between the two stacks.

### Spring Boot Actuator

When the Actuator dependency is present and management endpoints use the **same port** as the application, the default management base path is usually `/actuator`. According to Spring Boot documentation, `management.endpoints.web.base-path` is resolved **relative to `server.servlet.context-path`** in Servlet MVC, or **`spring.webflux.base-path`** in WebFlux. Hence, for example:

~~~properties
server.servlet.context-path=/portal
management.endpoints.web.base-path=/actuator
~~~

implies a same-context management URL like `/portal/actuator/health`, depending on endpoint exposure and security configuration. Do not speculatively add `spring.mvc.servlet.path=/api` to the Actuator URL. When the management server uses a separate port (`management.server.port`), the base path is determined according to the separate management server configuration.

**Important:** the Maven examples above do not add Actuator, so `/actuator/health` will not be available; this section only applies when the Actuator starter is actually integrated.

### Static Resources, Welcome Page, and 404 Errors

Spring MVC has resource handlers and static mappings; when changing the context path or DispatcherServlet mapping, URLs for JS/CSS, favicons, and welcome pages may also change. Check paths in HTML/templates, relative/absolute URLs, and proxy caching. With WebFlux, `spring.webflux.static-path-pattern` differs from `spring.webflux.base-path`: the first changes the route for static resources, while the second sets the reactive application-level prefix.

A 404 error is not always the controller's fault: it may be caused by servlet mapping, static resource handlers, or gateway rewrites. Inspect the **actual URL the browser sends**, not just the path constructed by the frontend.

### OpenAPI/Swagger and Callback/Redirect URLs

If using springdoc or another OpenAPI system, verify where API docs, Swagger UI, and server URLs in the schema are served after changing prefixes. Similarly, OAuth callbacks, webhooks, and redirect URLs may need updates in external systems. Do not assume every integration automatically picks up the new prefix.

## 10. Reverse Proxy, Load Balancer, and X-Forwarded-Prefix

A reverse proxy may receive:

~~~text
https://example.com/public/v1/hello
~~~

and forward to the backend:

~~~text
http://127.0.0.1:8080/portal/api/v1/hello
~~~

The URL the frontend sees and the URL the backend receives can **differ**, depending on whether the proxy keeps, adds, or strips prefixes. Therefore:

1. Capture/log the request path at both the proxy and the application when debugging.
2. Check rewrite rules, path prefixes, context paths, servlet mappings, and controller mappings.
3. Inspect `Forwarded` and `X-Forwarded-*` headers and how Spring Boot processes them when running behind a trusted proxy.
4. Avoid configuring the prefix at both the proxy and the app if the proxy already forwards the final path.
5. Check links/redirects generated from requests, while verifying the actual public scheme and host.

`server.forward-headers-strategy` can help the application process forwarded headers in appropriate environments, but it **does not automatically fix every prefix rewrite bug**. Only trust forwarded headers from trusted proxies; in environments allowing direct client requests, trusting client-supplied headers can produce incorrect URLs.

## 11. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| Calling `/hello` returns 404 | Context path, servlet path, or base path is set | Recalculate the URL for your stack and include all prefixes |
| Only set `spring.mvc.servlet.path` and mappings fail | Boot 3.5 default `PathPatternParser` is incompatible with DispatcherServlet prefix | Use `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` and retest routes |
| Set `spring.webflux.base-path` but MVC URL does not change | Application is still Spring MVC | Check starters and `WebApplicationType` |
| Set `server.servlet.context-path` but reactive Netty URL does not change | Property belongs to the Servlet stack | Use `spring.webflux.base-path` for WebFlux |
| URL becomes `/portal/api/portal/api/hello` | Prefix added to both properties and controllers/gateway | Keep the prefix only at the intended layer |
| MockMvc tests pass but real HTTP returns 404 | Mock tests do not simulate the Servlet context/mapping accurately | Add `@SpringBootTest(RANDOM_PORT)` with real HTTP requests |
| Actuator path differs from predicted URL | Management base path and management port have their own scope | Check `management.endpoints.web.base-path`, `management.server.port`, and docs |
| Wrong cookie/redirect paths | Context path changed, proxy keeps a different prefix | Check Set-Cookie Path, Location, and forwarded headers |
| Security rules no longer match as before | Servlet prefix/stack affects request matchers | Test 401/403 rules against actual URLs |
| Same port but internal/external networks use different URLs | Proxy/Ingress rewrite | Compare request path at each hop |

Step-by-step 404 diagnostic process:

1. Confirm whether the app runs **Servlet MVC or WebFlux** via dependencies and startup logs.
2. Read **effective properties** for the active profile/environment, especially context/servlet/base path.
3. Inspect controller mappings: class-level `@RequestMapping` and method-level `@GetMapping`/`@PostMapping`.
4. Build the expected URL from your stack: Servlet MVC can have **context + servlet + controller**; WebFlux has **base + controller**.
5. Call the URL with curl directly against the backend, bypassing the proxy to isolate the bug (when the environment allows).
6. If direct backend calls succeed but the public URL fails, inspect rewrites and forwarded headers at the proxy.
7. Test APIs, static resources, security/Actuator, and redirects to catch prefix mismatches.

## 12. Property Selection Rules

**Choose `server.servlet.context-path` when:** the application runs Servlet MVC and you want to move *the entire Servlet web application* under a context, such as `/portal`; this is clearer if the requirement is simply "put the app under a prefix".

**Choose `spring.mvc.servlet.path` when:** the application uses Spring MVC and you have a specific requirement to map **only DispatcherServlet** under `/api`, separate from other servlets' mappings. With Spring Boot **3.5.x**, resolve the `PathPatternParser` incompatibility with an appropriate matching strategy and test thoroughly.

**Choose `spring.webflux.base-path` when:** the application is actually running the **WebFlux reactive** stack, such as Reactor Netty, and you want to set a WebFlux handler-level prefix; do not apply MVC context/servlet paths to reactive URLs.

**Do not set all three at once** trying to give one API multiple prefixes: identify the runtime stack and each layer's responsibility first. If there is a proxy, treat the public URL as the external contract; internal path configuration must stay consistent with that contract.

## Official References

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — describes `server.servlet.context-path`, `spring.mvc.servlet.path`, and `spring.webflux.base-path`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html) — notes that `PathPatternParser` is incompatible when DispatcherServlet uses a path prefix, and how to select `ant-path-matcher`.
- [Spring Boot — Spring MVC Configuration](https://docs.spring.io/spring-boot/how-to/spring-mvc.html) — setting the path for `DispatcherServlet`.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html) — WebFlux architecture.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html) — Actuator paths relative to context/base path or management server.
- [Spring Framework — Path Matching for Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html) — servlet mapping, `requestURI`, `servletPath`, and `pathInfo`.

**Practical conclusion:** In MVC, the path to a controller is determined by the Servlet context path, DispatcherServlet mapping, and controller mapping; in WebFlux, it is the WebFlux base path plus the route. Changing the right property for the right stack, while testing the real URL over HTTP, avoids most 404 errors caused by path prefixes.