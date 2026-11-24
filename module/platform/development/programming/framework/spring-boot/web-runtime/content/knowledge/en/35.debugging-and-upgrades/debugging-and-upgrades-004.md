# Diagnosing HTTP 404 Caused by Wrong Context Path, Servlet Path, Base Path, or Request Mapping in Spring Boot

## 1. Lesson Objectives

A Spring Boot application has started successfully, the controller has `@GetMapping("/ping")`, yet calling `http://localhost:8080/ping` returns **HTTP 404 Not Found**. The cause is not necessarily a missing controller: the HTTP request may be sent to the **wrong context path**, **wrong servlet path**, **wrong WebFlux base path**, **wrong class/method mapping**, rewritten by a reverse proxy, or the app matched the handler and the handler itself decided to return 404.

This article belongs to **Debugging and Upgrades** in the **Spring Boot - web-runtime** module. The goal is to know *which layers parse a request path*, pinpoint where the 404 originates using evidence rather than guesswork, fix the right layer, and write integration tests to prevent regressions.

After this lesson, you will be able to:

1. Distinguish `server.servlet.context-path`, `spring.mvc.servlet.path`, `spring.webflux.base-path`, and mappings in `@RequestMapping`/`@GetMapping`.
2. Compute the actual URL for Spring MVC/Servlet and WebFlux without miscalculating prefixes.
3. Distinguish 404 responses from **Tomcat/container**, **`DispatcherServlet`/`DispatcherHandler`**, **static resource handler**, **explicit controller/service logic**, and **reverse proxy/gateway**.
4. Use `curl`, startup mapping logs, `/actuator/mappings`, request attributes, and **`RANDOM_PORT`** tests to trace the root cause.
5. Understand the limitation of `PathPatternParser` with custom servlet paths in Spring Boot 3.5, changes in trailing-slash matching, HTTP method/media types, and static resource behavior.
6. Run two small Java 17+ projects: **MVC with context path** and **WebFlux with base path**, complete with real HTTP integration tests.
7. Check Actuator paths, management ports, proxy rewrites/forwarded headers, security, and environment configs during upgrades/deployments.

**Core method:** trace the path **client URL → proxy/gateway rewrite → server/context → servlet or reactive base → handler mapping → handler execution**. Do not prepend `/api` or `/app` randomly to URLs, and do not modify controllers before confirming the request actually reaches the right application.

## 2. Distinguishing Four Types of Prefix/Path

### 2.1. Servlet Context Path: `server.servlet.context-path`

This is the **context root of the Servlet web application**, managed by the servlet container such as Tomcat. Example:

```properties
server.port=8080
server.servlet.context-path=/shop
```

Controller:

```java
@RestController
@RequestMapping("/api")
class PingController {
    @GetMapping("/ping")
    String ping() {
        return "pong";
    }
}
```

With the default `DispatcherServlet` at `/`, the URL the client must call is:

```text
GET http://localhost:8080/shop/api/ping     -> expected route
GET http://localhost:8080/api/ping          -> wrong context path
```

Inside `@RequestMapping("/api")`, you **do not** need to write `/shop/api`. The context path is a container-level prefix, not part of the business route that controllers should repeat.

A request sent without `/shop` can receive a 404 from the container **before `DispatcherServlet` ever processes it**. Seeing no request logged when DEBUG handler mapping is enabled is a useful clue. Also check if multiple web applications share Tomcat or if a proxy is routing to the wrong host/port.

`server.servlet.context-path` is a property for **Servlet web applications**. It is **not** an alias for `spring.webflux.base-path` and should not be used to configure the base path of a WebFlux app running on Reactor Netty.

### 2.2. `DispatcherServlet` Path: `spring.mvc.servlet.path`

This is the **registration path of `DispatcherServlet`** in Spring MVC, defaulting to `/`. It is distinct from the context root:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
```

In an MVC setup compatible with a servlet prefix, a controller `@RequestMapping("/api")` + `@GetMapping("/ping")` is reached at:

```text
/shop + /internal + /api + /ping
= http://localhost:8080/shop/internal/api/ping
```

However, there is a **very important limitation in Spring Boot 3.5**: the default `PathPatternParser` strategy **is incompatible with configuring `DispatcherServlet` with a custom path prefix**. If you truly need `spring.mvc.servlet.path` on this release line, Boot docs instruct switching to the compatible matching strategy:

```properties
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
spring.mvc.servlet.path=/internal
```

`AntPathMatcher` is the older matching path and requires evaluating implications for URI parsing, security, and migration; do not switch the entire system just to mask a proxy/config mistake. When there is no specific technical requirement for a Servlet mapping prefix, it is usually simpler to keep `spring.mvc.servlet.path=/` and use the **context path** or **application route prefix** intentionally.

**Do not assume every Spring Boot version supports combining servlet path and parser the same way**: check the version, API docs, and integration tests during upgrades. With native Netty WebFlux, `spring.mvc.servlet.path` is not a prefix for reactive handlers.

### 2.3. WebFlux Base Path: `spring.webflux.base-path`

A **Spring WebFlux reactive** application has the property:

```properties
spring.webflux.base-path=/edge
```

WebFlux controller:

```java
@RestController
@RequestMapping("/api")
class ReactiveController {
    @GetMapping("/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

Client-side URL:

```text
GET http://localhost:8080/edge/api/ping     -> expected route
GET http://localhost:8080/api/ping          -> missing WebFlux base path
```

`spring.webflux.base-path` is the **base path for web handlers**. In a typical reactive Netty app, **do not use `server.servlet.context-path` or `spring.mvc.servlet.path` instead**. If using a Servlet-based reactive deployment or a separate gateway, verify the container/adapter instead of blindly applying the Netty recipe.

By default, Spring Boot selects **Spring MVC** if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath. When seeing a 404 because `base-path` has no effect, first determine whether the app is actually running Servlet or Reactive.

### 2.4. Handler Mapping: `@RequestMapping`, `@GetMapping`, `@PostMapping`

Controller and method mappings are combined **after** the context/servlet/base path layer:

```java
@RestController
@RequestMapping("/api/v1")
class OrderController {
    @GetMapping("/orders/{id}")
    Map<String, String> get(@PathVariable String id) {
        return Map.of("orderId", id);
    }
}
```

The internal mapping is `GET /api/v1/orders/{id}`. With MVC context path `/shop`, the external URL is `/shop/api/v1/orders/123`; with WebFlux base path `/edge`, it is `/edge/api/v1/orders/123`. **Do not mix both cases into a single URL**.

`@RequestMapping("/api")` on the class + `@GetMapping("/ping")` on the method produces `/api/ping`; `/ping` is not mapped automatically once a class-level path is specified.

`@GetMapping` restricts the HTTP method. If a client sends `POST` to a GET-only path, it usually receives **405 Method Not Allowed**, not 404. Likewise, a `consumes` mismatch typically gives 415, and a `produces`/`Accept` mismatch can give 406. If you receive 404, check whether the request reached controller mapping or was intercepted/returned by another layer.

## 3. URL Calculation Formula and Scenario Table

### 3.1. Spring MVC Servlet with Context and Servlet Path

When handling a Spring MVC endpoint with compatible layer configs:

```text
Client-side URL path
  = [servlet context path]
  + [DispatcherServlet mapping prefix, if customized]
  + [class-level @RequestMapping path]
  + [method-level @GetMapping/@PostMapping path]
```

This is a **mental model**, not naive string concatenation in source code: slashes `/` are normalized per routing config, and paths may involve URI variables, proxy rewriting, URL encoding, or patterns. A non-prefix servlet mapping (such as an extension mapping) also cannot be explained by simple string addition.

| MVC case | Context path | Servlet path | Controller + method | Expected URL path |
| --- | --- | --- | --- | --- |
| Default | root | `/` | `/api` + `/ping` | `/api/ping` |
| Custom context | `/shop` | `/` | `/api` + `/ping` | `/shop/api/ping` |
| Servlet prefix (with compatible strategy) | root | `/internal` | `/api` + `/ping` | `/internal/api/ping` |
| Both context + servlet prefix | `/shop` | `/internal` | `/api` + `/ping` | `/shop/internal/api/ping` |
| Route includes version | `/shop` | `/` | `/api/v1` + `/ping` | `/shop/api/v1/ping` |

**Do not "fix" a 404 by adding `/shop` to `@RequestMapping`** when the context path is already `/shop`: that turns the URL into `/shop/shop/api/ping` and introduces a new bug. Avoid hardcoding public base URLs in controllers/business logic; obtain them from deployment configuration or a safe URI builder when constructing links.

### 3.2. Spring WebFlux

```text
HTTP URL path = [spring.webflux.base-path] + [WebFlux handler mapping path]
```

| WebFlux base path | Controller + method | URL path |
| --- | --- | --- |
| Empty (default) | `/api` + `/ping` | `/api/ping` |
| `/edge` | `/api` + `/ping` | `/edge/api/ping` |
| `/platform` | `/v1` + `/orders/{id}` | `/platform/v1/orders/42` |

For functional `RouterFunction`, routes are declared using predicates rather than controller annotations; the base path remains part of WebFlux's routing configuration. If a functional route is not registered or not part of the running Spring context, users can see 404 even while annotated controllers work.

### 3.3. Distinguishing the Actuator Base Path

`management.endpoints.web.base-path` is **not an API base path**. It is the prefix for Actuator web endpoints, defaulting to `/actuator`.

In Spring Boot 3.5, when Actuator shares the **same port** as the application:

- Servlet MVC: Actuator base path is relative to `server.servlet.context-path`.
- WebFlux: Actuator base path is relative to `spring.webflux.base-path`.

If Actuator runs on a **separate port** via `management.server.port`, the Actuator base path is relative to `management.server.base-path` on the management server, **not added to the main app's context path using the same formula**.

MVC example:

```properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,mappings
```

Diagnostics URLs in the local demo:

```text
http://localhost:8080/shop/actuator/health
http://localhost:8080/shop/actuator/mappings
```

If separating the management server:

```properties
management.server.port=9090
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

When this config applies and the endpoints are exposed, diagnostics are expected on the **management server**:

```text
http://localhost:9090/ops/actuator/health
http://localhost:9090/ops/actuator/mappings
```

Since security/access/exposure can block them, a 404 on `/actuator/mappings` does not automatically prove a business route is missing. **Do not expose `mappings`/`env`/`configprops` publicly on the Internet**; they can leak API structure and configuration. In the examples below, we bind localhost only for a learning environment.

## 4. A 404 Can Originate from Multiple Layers

```text
Client: GET /shop/api/ping
         |
         v
Gateway / load balancer / ingress
  - wrong hostname, path rewrite, upstream, prefix? -> 404 from gateway
         |
         v
Tomcat Servlet context /shop
  - missing /shop, different context?       -> 404 from container
         |
         v
DispatcherServlet mapping /
  - /internal prefix?                       -> 404 or never reaches servlet
         |
         v
Spring RequestMappingHandlerMapping
  - is route /api/ping registered?          -> no handler found
         |
         v
Static resource handler /** (if enabled)
  - searches resource, not found?           -> NoResourceFoundException -> 404
         |
         v
Controller / service
  - record id does not exist?               -> explicitly returns 404
```

On WebFlux/Netty, replace the Servlet context/`DispatcherServlet` layers with **WebFlux base path + `DispatcherHandler`/HandlerMappings**, while the principles around gateways, handlers, and app-level 404s remain similar.

Commonly confused differences:

1. **404 from proxy**: the request may have **never reached the Java process**. The app has no corresponding trace/access log, and response headers/body come from the gateway (though headers are not absolute proof as they can be rewritten).
2. **404 from Tomcat context**: the port is right, yet the request falls outside the context path; Spring MVC filters and handler mappings may never see the request.
3. **404 from WebFlux base path**: Netty receives the request, yet WebFlux handlers fail to match the route due to the wrong path prefix.
4. **404 because no controller handler matched**: wrong annotation, component not scanned, wrong root package, or route mismatch.
5. **404 from static resource**: Spring MVC/WebFlux's static resource handler can accept the path under `/**` and return 404 when no file exists; the exception message differs from "No handler found".
6. **Intentional 404**: controller throws `ResponseStatusException(HttpStatus.NOT_FOUND)` or `@ExceptionHandler` maps domain not-found to 404. The mapping existed and executed.

**HTTP status 404 is not proof that the application "failed to start."** If health returns 200 at the right URL, the app is running; continue isolating the cause. Conversely, health 200 from a **different instance** or **different management port** does not prove the request reached the same backend.

## 5. Least-Effort-First 404 Diagnostic Workflow

### Step 1 — Pin Down the Exact Request Being Sent

Record:

- Scheme (http/https), hostname, port, method, URL path, query, `Host`, `Accept`, `Content-Type`.
- Response status, headers, body, timestamp, request ID/correlation ID if available.
- Are there 301/302/307/308 redirects before the 404? Any rewrite/forwarding through CDN, ingress, or service mesh?
- Is the client a browser, mobile app, curl, or reverse proxy health checker? Could it be caching an old base URL after a deploy?

First test from a **host with authorized backend access** (localhost/staging):

```bash
curl -i -v --max-time 5 "http://127.0.0.1:8080/shop/api/ping"
curl -i -v --max-time 5 "http://127.0.0.1:8080/api/ping"
```

Do not use `-L` to follow redirects automatically while tracing a 404 chain; a redirect can move to a different path/host and obscure the cause. Use `curl --path-as-is` in controlled path tests if checking normalization; **never test URL traversal on unauthorized systems**.

### Step 2 — Identify Servlet MVC vs. WebFlux

Check the dependency list / server startup log of the **exact artifact**:

- Has `spring-boot-starter-web`, `DispatcherServlet`, Tomcat/Jetty/Undertow servlet? → usually **Spring MVC**.
- Has `spring-boot-starter-webflux`, Reactor Netty, reactive `DispatcherHandler`? → usually **WebFlux**.
- Both starters present? Spring Boot normally **prioritizes MVC**; do not infer reactive just because a controller returns `Mono`.
- App sits behind Spring Cloud Gateway/nginx? Check gateway route config before changing app properties.

If it is genuinely MVC, focus on `server.servlet.context-path` + `spring.mvc.servlet.path` + controller mappings. If genuinely WebFlux, focus on `spring.webflux.base-path` + WebFlux handlers.

### Step 3 — Verify Effective Configuration

Check deployment configs, active profiles, command-line arguments, environment variables, and startup messages:

```properties
server.port=8080
server.servlet.context-path=/shop
spring.mvc.servlet.path=/
# For a separate WebFlux app; do not mix all properties into the same app:
# spring.webflux.base-path=/edge
```

Corresponding environment variables accepted via Spring Boot relaxed binding:

```text
SERVER_PORT
SERVER_SERVLET_CONTEXT_PATH
SPRING_MVC_SERVLET_PATH
SPRING_WEBFLUX_BASE_PATH
SPRING_PROFILES_ACTIVE
```

Just because `src/main/resources/application.properties` contains `/shop` **does not guarantee** runtime uses it: `application-prod.yml`, environment variables, command-line args, ConfigMap/Helm, remote config, test properties, container flags, or config imports can override it.

Do not dump all environment variables into production logs, as many contain passwords/tokens. If using Actuator `env`/`configprops` in managed environments, restrict to internal operators and keep sanitization enabled—never expose publicly.

### Step 4 — Verify the Controller Actually Registered Its Mapping

Verify the class has:

- Proper `@RestController` or `@Controller`.
- Located under the package scanned by `@SpringBootApplication`, or explicitly imported/scanned.
- What path do class-level `@RequestMapping` and method-level `@GetMapping` combine into?
- Is it conditional on a specific profile or `@Conditional*` bean?
- Could an older server version/instance without the new controller still be running?
- Do request method, headers/params, and `consumes`/`produces` match?

Example:

```java
@RestController
@RequestMapping("/api/v1")
class OrderController {
    @GetMapping("/orders/{id}")
    public Map<String, String> get(@PathVariable("id") String id) {
        return Map.of("orderId", id);
    }
}
```

The mapped path is `GET /api/v1/orders/{id}`, not `/orders/{id}` or `/api/orders/{id}`. With context path `/shop`, the URL must be `/shop/api/v1/orders/42`.

A `@Controller` missing `@ResponseBody` can also be routed to a **view resolver** instead of returning JSON, causing view-not-found or other errors. For REST APIs, use `@RestController` for clarity.

### Step 5 — Use Actuator `mappings` When Safe

In a **local or authorized internal environment**, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

and local configuration:

```properties
management.endpoints.web.exposure.include=health,mappings
```

Then call the Actuator URL **with the right context/base path/management port**, e.g.:

```bash
curl -i "http://127.0.0.1:8080/shop/actuator/health"
curl -i "http://127.0.0.1:8080/shop/actuator/mappings"
```

`/actuator/mappings` lists registered request mappings, showing controller handlers and route patterns. **The pattern reported in mapping metadata does not necessarily include the servlet context path**: treat it as internal handler info, then combine with container/gateway config to derive the public URL.

Do not immediately conclude from an Actuator 404 that the app lacks business routes: `mappings` might not be exposed, might be secured, or might live on another management port/path. With Spring Security, expose mapping info only to authenticated, authorized operators.

### Step 6 — Log a Controlled Request

You can enable handler-mapping logging in a **local/test profile**, not framework-wide DEBUG in production:

```properties
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.reactive.result.method.annotation.RequestMappingHandlerMapping=TRACE
```

These are two loggers for two different stacks; enable only the one for the running stack. Startup logs can list registered paths. Logger names and log formats vary across Spring Framework versions; verify empirically rather than depending on a fixed log message.

If a request enters Spring MVC, you can inspect `HttpServletRequest` attributes. For instance, a local debug filter/endpoint can inspect:

```java
String uri = request.getRequestURI();
String context = request.getContextPath();
String servlet = request.getServletPath();
String extra = request.getPathInfo();
```

This is a **snippet**, requiring `jakarta.servlet.http.HttpServletRequest`. The values have semantics depending on servlet mapping; `getRequestURI()` is the server-received URI path excluding query string, while `getContextPath()` and `getServletPath()` reveal prefix splits. Never log raw queries, cookies, `Authorization`, or user identifiers just to debug prefixes.

In reactive WebFlux, inspect the request path via `ServerHttpRequest.getURI().getRawPath()` or `ServerHttpRequest.getPath()` inside a test-only `WebFilter`. **Do not add filters that log every request body or PII** just to track down a 404.

### Step 7 — Compare Direct Backend vs. Proxy Path

Test the same request via both paths, within authorized scope:

```text
Direct backend: GET http://127.0.0.1:8080/shop/api/ping
Public gateway: GET https://app.example.test/portal/shop/api/ping
```

If direct backend returns 200 yet the gateway returns 404, investigate **gateway rules, host matching, path strip/rewrite, ingress service name/port, and target instances** before touching `@GetMapping`. If direct backend already returns 404, continue checking the app's context path and mappings.

Do not assume "the gateway generated the 404" solely from a `Server` header: proxies can alter headers, and the app can return custom error pages. Correlate ingress access logs, application access logs, request IDs, and timestamps before concluding.

## 6. Notes on `PathPatternParser`, Trailing Slash, and Static Resources

### 6.1. Custom Servlet Path Has Parser Constraints

In Spring Boot 3.5, the Web MVC docs explicitly state that the `PathPatternParser` matching strategy is incompatible with configuring `DispatcherServlet` with a **path prefix** via `spring.mvc.servlet.path`. For example, when a legacy servlet path is required:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

The test URL is then `/shop/internal/api/ping`, while `/shop/api/ping` lacks the servlet prefix. Before changing the parser, review existing patterns (wildcards, encoded slashes, matrix vars), security routing, and integration tests; switching from `PathPatternParser` to `AntPathMatcher` is **not merely a cosmetic setting**.

If the app only needs to expose APIs under `/internal` at the gateway, you can instead use a **route prefix in `@RequestMapping`**, context path, or intentional proxy rewrite, avoiding a matching strategy change unless required.

### 6.2. Trailing Slashes Are Not Equivalent by Default

```text
GET /shop/api/ping
GET /shop/api/ping/
```

On Spring Framework 6.x / Boot 3.x, do not assume the two paths match identically. Recent versions changed/deprecated transparent trailing-slash matching due to authorization mismatch risks. If a client sends `/ping/` while the controller declares `@GetMapping("/ping")`, it may get 404. **Pick one canonical URL** and handle redirects/normalization consistently at the edge/web filter, or declare explicit mappings when truly required.

Never enable arbitrary rewrites that bypass role-based security: security route matchers and controller routes must share identical semantics. Specifically distinguish `/admin` and `/admin/` in security tests.

### 6.3. Static Resource Handler Can Produce 404 Even Without a Controller Handler

Spring Boot MVC serves static resources by default from classpath locations such as:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

with `spring.mvc.static-path-pattern=/**`. Consequently, a URL **not matching any controller** can be picked up by the generic static resource handler looking for a file. When no file is found, it raises `NoResourceFoundException` (Spring Framework 6.1+), still returning HTTP 404.

This explains why searching logs only for `NoHandlerFoundException` can miss 404s. Boot docs explain: to catch `NoHandlerFoundException`, narrow the static path mapping, e.g.:

```properties
spring.mvc.static-path-pattern=/assets/**
```

or disable static resource mapping when no assets are served:

```properties
spring.web.resources.add-mappings=false
```

**Do not alter production static resource settings just to make 404 test logs prettier**: UI/assets could break. During diagnosis, distinguishing missing handler vs. missing resource via logs, mappings, and tests is sufficient. On WebFlux, use `spring.webflux.static-path-pattern` per reactive stack docs instead of `spring.mvc.static-path-pattern`.

### 6.4. Wrong Method, Media Type, and Path Are Not the Same Error

- `GET` mapping receiving `POST`: typically 405 (method not allowed).
- `@PostMapping(consumes="application/json")` receiving `text/plain`: typically 415.
- Mapping `produces` mismatching `Accept`: typically 406.
- Mismatched `params` or `headers` condition: HTTP status depends on matching and exception resolution; check logs/mappings rather than calling everything 404.
- Mismatched URI variable regex (e.g., digits only): path fails to match → 404.
- Case sensitivity, percent-encoding, duplicate slashes, and proxy path normalization can produce different routes.
- Controller matched, yet service throws `ResponseStatusException(404)` or `@ControllerAdvice` maps an error to 404: that is an **application-level not found**, not a missing mapping.

## 7. Hands-On MVC Project — Context Path Causing 404

The first project runs **Spring Boot 3.5.16 + Java 17+ + Spring MVC + embedded Tomcat**. It features:

- `server.servlet.context-path=/shop`.
- `@RequestMapping("/api")` + `@GetMapping("/ping")` creating internal endpoint `/api/ping`.
- Clients must call `/shop/api/ping`.
- An `/api/orders/{id}` endpoint demonstrating path variables.
- Actuator health/mappings for local debugging only.
- **Six HTTP integration tests** using `java.net.http.HttpClient` against an embedded `RANDOM_PORT` server, testing 200/404/405/actuator paths.

### 7.1. Directory Structure

```text
mvc-path-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   └── PingController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/routing/
            └── PrefixRoutingIntegrationTest.java
```

### 7.2. Valid `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-path-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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
```

`spring-boot-starter-web` brings Spring MVC/Tomcat; `spring-boot-starter-actuator` provides `/actuator/health` and `/actuator/mappings` when exposed; `spring-boot-starter-test` provides JUnit Jupiter. No database or external tools are required.

### 7.3. Main Class

**`src/main/java/com/example/routing/RoutingApplication.java`**

```java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
```

### 7.4. Controller: One Internal Route, One Prefixed Public URL

**`src/main/java/com/example/routing/PingController.java`**

```java
package com.example.routing;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/orders/{id}")
    public Map<String, String> order(
            @PathVariable("id") String id) {
        return Map.of("orderId", id);
    }
}
```

**Do not** put `/shop` in the annotation; the context path belongs to the Servlet container. The controller must reside under the root package `com.example.routing` so `@SpringBootApplication` scans it.

### 7.5. Localhost Configuration for Safe Diagnostics

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.address=127.0.0.1

server.servlet.context-path=/shop
# Default DispatcherServlet is /; stated explicitly to teach the two distinct prefixes.
spring.mvc.servlet.path=/

# For localhost/lab only; do not expose mappings to the Internet.
management.endpoints.web.exposure.include=health,mappings
```

`server.address=127.0.0.1` keeps the server on loopback in the learning environment. When running in a real container or behind a reverse proxy, configure the listen address for your topology rather than copying mechanically. The `mappings` endpoint can reveal route lists and should be secured/enabled per environment profile.

### 7.6. Send HTTP Requests Yourself to Reproduce the 404

Run in the MVC project directory:

```bash
java -version
mvn spring-boot:run
```

In another terminal:

```bash
curl -i "http://127.0.0.1:8080/shop/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i "http://127.0.0.1:8080/shop/api/orders/A-7"
curl -i "http://127.0.0.1:8080/shop/actuator/health"
curl -i "http://127.0.0.1:8080/shop/actuator/mappings"
```

Expected:

- `GET /shop/api/ping` → 200, JSON containing `{"message":"pong"}`.
- `GET /api/ping` → 404 due to missing `/shop`.
- `GET /shop/api/orders/A-7` → 200, JSON containing `{"orderId":"A-7"}`.
- `GET /shop/actuator/health` → 200, health JSON when exposed.
- `GET /shop/actuator/mappings` → 200 and mappings metadata in the **local lab**.
- `GET /actuator/health` → 404 due to missing context prefix.

HTTP timestamps, `Date`/`Connection` headers, and 404 error body shape may differ across Tomcat/`ErrorController`/configs. Do not assert a fixed JSON schema for container-generated 404s.

### 7.7. Six HTTP Integration Tests Over a Real Socket

**`src/test/java/com/example/routing/PrefixRoutingIntegrationTest.java`**

```java
package com.example.routing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class PrefixRoutingIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).GET().build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    private HttpResponse<String> post(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).POST(HttpRequest.BodyPublishers.noBody()).build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void routeWithContextPrefixReturns200() throws Exception {
        HttpResponse<String> response = get("/shop/api/ping");

        assertEquals(200, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("pong", body.get("message").asText());
    }

    @Test
    void missingContextPrefixReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    @Test
    void wrongRouteReturns404() throws Exception {
        assertEquals(404,
            get("/shop/api/does-not-exist").statusCode());
    }

    @Test
    void classAndMethodMappingsAreCombined() throws Exception {
        HttpResponse<String> response =
            get("/shop/api/orders/A-7");

        assertEquals(200, response.statusCode());
        assertEquals("A-7",
            mapper.readTree(response.body())
                .get("orderId").asText());
    }

    @Test
    void unsupportedHttpMethodReturns405() throws Exception {
        assertEquals(405,
            post("/shop/api/ping").statusCode());
    }

    @Test
    void actuatorPathAlsoUsesContextPrefix() throws Exception {
        HttpResponse<String> response =
            get("/shop/actuator/health");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("UP"));
    }
}
```

Run:

```bash
mvn test
```

**All six tests are designed to pass**, though this outcome is expected when the learner runs them—**not a claim that Maven was executed in the current workspace**. Unlike `MockMvc`, `RANDOM_PORT` starts a real embedded server and `HttpClient` calls over TCP loopback, catching context-root/servlet-registration bugs that unit/slice tests miss.

The second test intentionally asserts that a URL with the **wrong context path** returns 404; this is a valuable negative test confirming the prefix rather than only testing "valid route returns 200". The 405 test illustrates that method mismatches are distinct from 404.

### 7.8. Testing a Servlet Prefix on the Same MVC App

Once the baseline runs, to demonstrate `spring.mvc.servlet.path` **intentionally**, use application properties in a test profile or CLI args:

```properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/internal
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
```

After restarting with this config, the expected controller URL is:

```text
http://127.0.0.1:8080/shop/internal/api/ping
```

This is a **separate configuration variant**—do not leave it enabled alongside the baseline integration tests and expect them to pass, as the baseline tests assert `/shop/api/ping`. When changing the servlet prefix, update the test URL to `/shop/internal/api/ping` and add a negative case for `/shop/api/ping` to guard against misconfiguration.

Do not use the default `PathPatternParser` alongside a custom prefix and then blame every startup failure on "404 from controller." In Spring Boot 3.5, that is a **compatibility/configuration** issue that surfaces during mapping initialization and must be fixed before testing HTTP.

## 8. Hands-On WebFlux Project — Base Path Causing 404

The second project is **completely independent** of the MVC project, demonstrating `spring.webflux.base-path=/edge` with Spring WebFlux + Reactor Netty. Do not run both apps on port 8080 at the same time.

### 8.1. File Tree

```text
reactive-basepath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactivepath/
    │   │   ├── ReactiveBasePathApplication.java
    │   │   └── ReactivePingController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivepath/
            └── ReactiveBasePathIntegrationTest.java
```

### 8.2. WebFlux POM

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-basepath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

Only the WebFlux starter is present, with no MVC starter. Spring Boot selects a reactive web application and starts Reactor Netty (by default) when run as a web service.

### 8.3. WebFlux Properties

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.address=127.0.0.1
spring.main.web-application-type=reactive
spring.webflux.base-path=/edge
```

Note: do not set `server.servlet.context-path=/edge` expecting it to take effect on Netty; that is a Servlet-only property.

### 8.4. Reactive Main Class

**`src/main/java/com/example/reactivepath/ReactiveBasePathApplication.java`**

```java
package com.example.reactivepath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveBasePathApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveBasePathApplication.class, args);
    }
}
```

### 8.5. Reactive Controller

**`src/main/java/com/example/reactivepath/ReactivePingController.java`**

```java
package com.example.reactivepath;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ReactivePingController {

    @GetMapping("/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("message", "pong"));
    }
}
```

Like MVC, the internal mapping remains `GET /api/ping`, while the public URL passes through base path `/edge`.

### 8.6. Three Real HTTP WebFlux Integration Tests

**`src/test/java/com/example/reactivepath/ReactiveBasePathIntegrationTest.java`**

```java
package com.example.reactivepath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ReactiveBasePathIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path)
            ).GET().build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void basePathAndMappingTogetherReturn200() throws Exception {
        HttpResponse<String> response =
            get("/edge/api/ping");

        assertEquals(200, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("pong", body.get("message").asText());
    }

    @Test
    void missingReactiveBasePathReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    @Test
    void duplicatedReactiveBasePathReturns404() throws Exception {
        assertEquals(404,
            get("/edge/edge/api/ping").statusCode());
    }
}
```

Run in the reactive project directory:

```bash
mvn test
mvn spring-boot:run
```

While the app is running, test:

```bash
curl -i "http://127.0.0.1:8080/edge/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i "http://127.0.0.1:8080/edge/edge/api/ping"
```

Expected: 200, 404, 404 in order. **All three tests are expected to pass when running the exact source**; do not assume they have already been run in the reader's workspace. This is an **HTTP integration test**, unlike `WebTestClient.bindToController` or `@WebFluxTest`, which run against a mock exchange.

### 8.7. If Adding Actuator to the Reactive Project

When adding `starter-actuator` and exposing `health,mappings` (locally only), on the same port with `spring.webflux.base-path=/edge`, Actuator endpoints normally sit under:

```text
/edge/actuator/health
/edge/actuator/mappings
```

If `management.server.port` is moved to a separate port, the prefix depends on `management.server.base-path` on the management server rather than simply prepending the main server's WebFlux base path to the Actuator path.

## 9. Reverse Proxy/Ingress: A Very Common Cause of 404

Suppose the MVC app actually accepts:

```text
GET http://127.0.0.1:8080/shop/api/ping
```

Yet clients see the URL:

```text
GET https://service.example.test/portal/shop/api/ping
```

A reverse proxy can either **strip `/portal`** and send `/shop/api/ping` upstream, or **keep `/portal`** so upstream receives `/portal/shop/api/ping` and Tomcat fails to match context `/shop`.

Nginx example illustrating prefix stripping (placed inside a complete `server` block in an authorized environment):

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

With `proxy_pass` ending in a `/` URI as above and a simple `location /portal/`, Nginx replaces the matched location prefix with `/`; external `/portal/shop/api/ping` becomes upstream `/shop/api/ping`. Changing `proxy_pass` to the form **without a URI**:

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080;
}
```

when no other rewrite applies, makes Nginx forward the request URI as-is. **Exact behavior still depends on regex locations, rewrites, normalization, and actual config**; verify via upstream access logs rather than treating these two snippets as universal recipes for every Nginx deployment.

For Kubernetes Ingress, gateways, or service meshes:

- Check path match type (`Exact`/`Prefix`/`ImplementationSpecific`), service name, namespace, and service port.
- Is path stripping/rewriting configured? Could the rewrite target drop `/shop` or duplicate `/api`?
- Could host-based virtual routing send requests to a different backend when `Host` changes?
- Have the new manifests/Helm release been applied? Do Pods have the new controller/mappings version?
- Is the gateway health check calling `/health`, `/actuator/health`, or `/shop/actuator/health`? Is the management port separate?

**`X-Forwarded-Prefix` does not force a reverse proxy to rewrite the actual request path**. Forwarded headers relate to reconstructing public URLs, scheme/host/prefix, and link generation. If using `server.forward-headers-strategy=framework` or native forwarded-header processing, confirm whether the edge actually strips/rewrites the request path. Do not add `X-Forwarded-Prefix` again when the proxy did not strip or the app already includes that context path.

**Security:** trust `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and `X-Forwarded-Prefix` only from a **trusted proxy**; if clients can inject these headers directly, misconfiguration can corrupt redirects, absolute links, and authorization decisions. Strip or overwrite client-supplied forwarded headers at the edge.

## 10. 404 After Upgrading Spring Boot / Spring Framework

Key changes to check when upgrading from older versions to Boot 3.x / Framework 6.x:

1. **Jakarta namespaces:** `javax.servlet` → `jakarta.servlet` in filters/servlets; an unported custom filter may fail to register, affecting rewrites/dispatching.
2. **Default `PathPatternParser`:** Spring MVC uses parsed patterns, which are incompatible with certain custom servlet path configs; `ant-path-matcher` is the legacy option when required.
3. **Trailing slashes:** `/api/ping` and `/api/ping/` should not be assumed equivalent; tests must assert exact expectations.
4. **Static resource 404:** when static mapping `/**` catches a request, you may see `NoResourceFoundException` instead of `NoHandlerFoundException`.
5. **Controller package scan:** changing the main class package, module JARs, or component scan can prevent controllers from registering.
6. **Security behavior:** misleading 401/403/404 responses depending on authorization matchers and security config; never disable security to "fix" routing.
7. **Reverse proxy / Kubernetes Ingress:** changes to rewrite flags, service ports, hostnames, and path prefixes in deployment charts.
8. **Actuator management path:** separate management port or `management.endpoints.web.base-path` alters diagnostics URLs.
9. **Spring Boot MVC vs. WebFlux detection:** adding a starter or switching server stacks can make `spring.webflux.base-path` stop applying.
10. **Mapping regex/case/encoded paths:** different path parsing strategies can change matching; test both valid URLs and URLs expected to be rejected.

**Do not fix every 404 by downgrading or turning off `PathPatternParser`.** Before making broad behavioral changes, write an integration test reproducing the exact URL/scheme/method/Host and compare both versions under identical settings.

## 11. Testing to Prevent 404 Regressions

### 11.1. Why Controller Unit Tests Are Not Enough

A unit test:

```java
assertEquals(
    Map.of("message", "pong"),
    new PingController().ping()
);
```

only proves the Java method returns the right `Map`; it **does not** prove Spring scanned the controller, mounted the `/shop` context, or routed `/shop/api/ping`. Even `@WebMvcTest`/`MockMvc`—while great for testing mappings—does not fully replace **embedded Tomcat + random-port HTTP** when the bug involves actual context path or servlet registration.

### 11.2. Tests Should Cover Both Positive and Negative Paths

Cases worth keeping:

- `GET /shop/api/ping` → 200.
- `GET /api/ping` → 404 (omitted context).
- `GET /shop/api/does-not-exist` → 404 (no business route).
- `POST /shop/api/ping` → 405, distinguishing wrong method from mapping 404.
- `GET /shop/api/orders/A-7` → 200, verifying class/method path combination.
- `GET /shop/actuator/health` → 200 when health is exposed on the same port.
- If using a servlet prefix: positive `/shop/internal/api/ping`, negative `/shop/api/ping` with the compatible matching strategy.
- If using a WebFlux base path: positive `/edge/api/ping`, negative `/api/ping`, and duplicated-prefix `/edge/edge/api/ping`.
- If behind a proxy: an HTTP integration test through ingress/staging with production-like hostname and rewrite rules.

### 11.3. Do Not Hardcode Error Bodies or HTTP Ports

404 responses from the container, `BasicErrorController`, reactive error handler, or gateway can return different JSON/HTML. In negative path tests, **assert status 404** without necessarily asserting the raw body. With a `RANDOM_PORT` server, inject `@LocalServerPort` and build URLs at runtime to avoid port 8080 conflicts on CI.

If a standard error JSON schema is required, that is a **separate API contract**: implement `@ControllerAdvice`/`@RestControllerAdvice` or `ProblemDetail` deliberately and test the schema for app-scoped errors. Do not expect container-generated 404s outside the context to match controller-generated 404s.

### 11.4. Do Not Treat Actuator `mappings` as HTTP E2E

`/actuator/mappings` proves handlers are **registered in the application context** according to endpoint metadata. It **does not prove** the public proxy routes properly, the container path is stripped properly, security permits access, and clients get HTTP 200. Combine **`mappings` + startup logs + direct backend curl + public gateway curl + HTTP integration tests** to isolate where the path breaks.

## 12. Quick Symptom-Based Diagnostic Table

| Symptom | Plausible hypothesis | Check and fix |
| --- | --- | --- |
| `/api/ping` 404, `/shop/api/ping` 200 | Wrong Servlet context path | Verify `server.servlet.context-path`, fix client base URL |
| `/shop/api/ping` 404, `/shop/internal/api/ping` 200 | `DispatcherServlet` prefix set | Verify `spring.mvc.servlet.path` and matching strategy |
| App crashes/fails to start when setting servlet path | `PathPatternParser` incompatible | Review Boot version, switch strategy, or remove servlet prefix |
| WebFlux `/api/ping` 404, `/edge/api/ping` 200 | Omitted reactive base path | Check `spring.webflux.base-path` and actual stack |
| `/shop/shop/api/ping` works, normal URL 404 | Prefix duplicated in controller/proxy | Remove one duplicate layer, define canonical path |
| Direct backend 200, public gateway 404 | Wrong proxy rewrite/Host/port | Compare actual upstream path; check ingress rules |
| `/shop/actuator/health` 404, app route still 200 | Actuator not exposed, separate management port/path | Check actuator dependencies, exposure, management URL |
| `@GetMapping` in source, missing in `mappings` | Controller not scanned, wrong profile/condition/version | Check root package, JAR, active profiles, startup logs |
| Right path, POST returns 405 | HTTP method mismatch | Use the right verb; do not call it 404 |
| POST returns 415 | `Content-Type`/`consumes` mismatch | Send expected body media type |
| GET returns 406 | `Accept`/`produces` mismatch | Check content negotiation |
| `/api/ping` 200, `/api/ping/` 404 | Trailing-slash behavior | Canonicalize/redirect safely, test both |
| Logs mention `NoResourceFoundException` | Static mapping `/**` caught the URL | Check controller mapping, static resources, pattern |
| No app access log for failing request | Gateway/container may have responded before handler | Compare ingress log, container log, correlation ID |
| `/items/unknown` returns 404 despite right mapping | Domain record does not exist | Check service/database/error advice; do not alter prefix |
| Wrong `Host` returns 404 yet right `Host` returns 200 | Virtual host/ingress host match | Check DNS, `Host`, gateway config |
| Only some Pods return 404 after deploy | Inconsistent version/config | Check image tags, release rollout, service endpoints |
| 404 only on percent-encoded URLs | Decoding/normalization/URI variable pattern difference | Check raw path, parser, proxy/security behavior |
| Startup reports `Mapping ambiguous` | Duplicate mappings | Fix annotations; do not hide behind URL rewrites |

## 13. Debugger's Checklist

- [ ] Recorded exact URL, HTTP method, headers, `Host`, response status, and timestamp of the failure.
- [ ] Clearly separated **client URL** from **backend URL** after proxy rewrites.
- [ ] Confirmed whether the app is Spring MVC or WebFlux, server implementation, and artifact/version.
- [ ] Read **runtime effective config** for context path, servlet path, reactive base path, and port/profiles.
- [ ] Calculated URLs in proper prefix order without repeating prefixes in `@RequestMapping`.
- [ ] If using custom `spring.mvc.servlet.path` in Boot 3.5, checked `PathPatternParser` compatibility.
- [ ] Verified class/method annotations, package scan, active profiles, and conditional beans.
- [ ] Tested both positive and negative URLs with `curl -i -v` without following redirects automatically.
- [ ] Checked security/access logs, mapping startup logs, and container logs internally.
- [ ] Used `/actuator/mappings` on the right URL with authorization; never exposed publicly.
- [ ] Distinguished gateway/container/mapping/static-resource/business 404s.
- [ ] Remembered wrong method/media type typically gives 405/406/415 rather than 404.
- [ ] Checked trailing slashes, casing, percent-encoding, and resource handler `/**`.
- [ ] Checked separate Actuator management port/base path when debug endpoints are missing.
- [ ] Added a `RANDOM_PORT` integration test over real HTTP for the fixed path.
- [ ] Tested through the proxy in an authorized environment when the bug only occurs via ingress.
- [ ] Did not disable security, log credentials/PII, or trust forwarded headers from untrusted sources.
- [ ] Documented the root cause at the exact layer before altering app or deployment configs.

## 14. Self-Check Questions

**1. Controller `@RequestMapping("/api")`, `@GetMapping("/ping")`, context path `/shop`: which URL is right?**  
`/shop/api/ping`. Do not add `/shop` to the annotation.

**2. MVC has context `/shop` and servlet path `/internal`: which URL is right with a compatible matching strategy?**  
`/shop/internal/api/ping`. Do not confuse the servlet prefix with the context prefix.

**3. In Spring Boot 3.5, why can `spring.mvc.servlet.path=/internal` cause problems?**  
Because the default `PathPatternParser` is incompatible with a custom servlet prefix; evaluate switching the matching strategy to `ant-path-matcher` or dropping that prefix.

**4. On WebFlux/Netty, what is the equivalent property for base path?**  
`spring.webflux.base-path`. `server.servlet.context-path` belongs to Servlet contexts and does not replace the WebFlux base path.

**5. Does a 404 from a reverse proxy guarantee the request reached the controller?**  
No. It may have been returned before the request reached the app or servlet context.

**6. Why might you see `NoResourceFoundException` instead of `NoHandlerFoundException` on a bad URL?**  
Because the default static resource handler has a broad `/**` mapping and catches the request before concluding no file exists.

**7. Will sending `POST` to `@GetMapping("/ping")` always return 404?**  
No. It normally returns 405 when the path has a mapping that does not support that HTTP method.

**8. Are `/shop/api/ping` and `/shop/api/ping/` guaranteed to match the same route?**  
No. Do not rely on default trailing-slash matching; test both and enforce a canonical URL.

**9. Does `/actuator/mappings` returning 404 mean controllers aren't registered?**  
No. Actuator may not be exposed, may be secured, or may be on a different path/port.

**10. Is `@WebMvcTest` enough to prove the Tomcat context prefix works?**  
Not completely. Use an embedded `RANDOM_PORT` server with real HTTP requests to test context/servlet deployment.

**11. If direct backend returns 200 yet ingress returns 404, where do you investigate first?**  
Host/path rewrite/upstream routing in the ingress/gateway and deployment config, rather than immediately editing annotations.

**12. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, can you assume WebFlux is active?**  
No. Boot usually prioritizes MVC; verify the actual stack.

**13. If a controller explicitly throws `ResponseStatusException(HttpStatus.NOT_FOUND)`, is that a mapping error?**  
No. The mapping matched, and the business handler deliberately returned 404.

**14. Should `/actuator/mappings` be exposed publicly for easier debugging?**  
No. Only expose it inside protected internal environments to authorized operators.

## 15. Official Documentation

- Spring Boot 3.5 — **Common Application Properties**: `server.servlet.context-path`, `spring.mvc.servlet.path`, `spring.mvc.pathmatch.matching-strategy`, `spring.webflux.base-path`, static resource settings: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — **Servlet Web Applications**: MVC path matching strategy, servlet prefix compatibility, static resource handler, and `NoResourceFoundException`: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Reactive Web Applications**: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Framework — **Mapping Requests in Spring MVC**, class/method annotations and URI patterns: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — **WebFlux annotated request mapping**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Boot 3.5 — **Actuator Monitoring and Management over HTTP**, context/base path and separate management port: https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html
- Spring Boot — **Mappings Actuator Endpoint API**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html
- Spring Framework — **Web MVC URL handler/trailing slash considerations**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.5 — **Testing Spring Boot Applications**: `@SpringBootTest(RANDOM_PORT)`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Conclusion:** A 404 in Spring Boot can only be diagnosed accurately once you know **which layer the request reached**. In Spring MVC, the external path is typically composed of the Servlet context path, `DispatcherServlet` mapping (if non-default), and handler mapping; in WebFlux/Netty, it uses the WebFlux base path plus handler mapping. Reverse proxies can strip or preserve prefixes, Actuator has its own base path/port, and static resource handlers or business code can also emit 404s. Verify runtime configuration, actuator mappings, and actual HTTP routes; write real-server integration tests with both valid and invalid URLs to prevent regressions after upgrades.
