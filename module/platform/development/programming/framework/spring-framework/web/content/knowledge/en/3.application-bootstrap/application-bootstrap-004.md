# Servlet Mapping, Context Path, and Application Paths in Spring Web

When a client calls `http://localhost:8080/store/api/books/42?lang=vi`, the entire string `/store/api/books/42` does not belong to `@GetMapping`. The Servlet container must determine the **web application (context)**, then choose the **servlet receiving the request**, and only then does Spring MVC locate the **controller handler**. Understanding these three layers helps configure URLs accurately, deploy WARs/JARs, handle reverse proxies, and diagnose seemingly inexplicable 404/405 errors.

This lesson focuses on **Spring MVC running on the Jakarta Servlet stack**, matching the Spring Framework 6 / Spring Boot 3, Java 17+ architecture. Spring WebFlux is a different web stack; do not use MVC's `DispatcherServlet` structure to reason about WebFlux.

## 1. Objectives and the Three Mapping Layers

After this lesson, you will be able to:

- Distinguish **context path**, **servlet URL pattern**, and **controller mapping**.
- Understand why patterns `/`, `/*`, `/api/*`, and `*.do` differ and which servlet is selected.
- Accurately read `getRequestURI()`, `getContextPath()`, `getServletPath()`, `getPathInfo()`, and `getQueryString()`.
- Configure `server.servlet.context-path`, understand the meaning of `spring.mvc.servlet.path`, and place `@RequestMapping` in the right spot.
- Know how a servlet is registered at application startup: Spring Boot embedded server or WAR on a standalone container.
- Test the actual endpoint with an HTTP client and distinguish errors originating from the container, Spring MVC, or a reverse proxy.

Overview model:

~~~text
Client
  GET /store/api/books/42?lang=vi
               |
               v
Servlet container (Tomcat, Jetty, ...)
  selects web application by context path: /store
               |
               v
Servlet URL mapping
  selects DispatcherServlet by URL pattern, e.g. "/"
               |
               v
Spring MVC DispatcherServlet
  selects handler for GET + "/api/books/42"
               |
               v
Controller method
  @GetMapping("/{id}") → id=42
               |
               v
Response: HTTP status + headers + body
~~~

**Principle:** the external browser URL is shaped by the **server origin**, **context path**, **servlet mapping**, and **application routes**. The query string is query data, not a part matched by the servlet container against URL mappings.

## 2. Dissecting a URL Before Adding Annotations

Hypothetical example:

~~~text
http://localhost:8080/store/api/books/42?lang=vi#details
|______ origin _____| |context| |controller path| |query| fragment
                     /store    /api/books/42    lang=vi
~~~

The notation above only illustrates the layout; in an actual URL, the **origin** consists of scheme `http`, host `localhost`, and port `8080` (if present). `#details` is a client-side fragment and **is not sent in the HTTP request-target**. When `DispatcherServlet` is mapped to `/`, the servlet does not add a separate path segment to the URL; requests reach the controller via the path `/api/books/42`.

| Component | Example Value | Who Decides? |
| --- | --- | --- |
| Scheme, host, port | `http://localhost:8080` | Server/network, client, and possibly a reverse proxy |
| Context path | `/store` | Web application/servlet container deployment configuration |
| Servlet mapping | `/` | Servlet registration; in this case adds no prefix to the URL |
| Controller mapping | `/api/books/42` | Spring MVC `@RequestMapping` + `@GetMapping` |
| Query string | `lang=vi` | Client; separated from path mapping |
| Fragment | `#details` | Used by the client, not transmitted to the HTTP server |

If `DispatcherServlet` is mapped with prefix `/mvc/*`, the application URL might be `/store/mvc/api/books/42`. Then **`/mvc` belongs to the servlet mapping**, while the Spring MVC handler still maps the portion inside the servlet: `/api/books/42`.

### 2.1. What Is the Context Path?

A **Servlet context** represents a web application deployed in a container. The context path is the URL prefix the container uses to identify that application. For example, the same host can serve two independent applications:

~~~text
https://example.test/shop/...   → web application "shop"
https://example.test/admin/...  → web application "admin"
~~~

In an application with context path `/shop`, a request to `/shop/api/items` is routed into that application first and only then checked against servlet mappings. The context path is **not a controller `@RequestMapping`**.

Per the Servlet specification, an application at the root context has `request.getContextPath()` equal to the **empty string `""`**, even though users often say the application runs at the root path `/`. When configured with context path `/shop`, `getContextPath()` is typically `"/shop"`. Do not assume the root value returned is `"/"`.

### 2.2. What Is Servlet Mapping?

Within each context, the servlet container registers servlets with a name and one or more URL patterns, such as `/api/*`, `*.action`, `/health`, or `/`. When a request enters the application, the container applies Servlet URL matching rules to decide **which servlet is invoked**. This layer sits **before Spring MVC controller mapping**.

In Spring MVC, the central servlet is `org.springframework.web.servlet.DispatcherServlet`, acting as a *front controller*. It receives requests routed by the container and delegates work to `HandlerMapping`, `HandlerAdapter`, controllers, and other Spring MVC components.

### 2.3. What Is Controller Mapping?

Class-level `@RequestMapping`, `@GetMapping`, `@PostMapping`, and similar annotations select a **handler method inside Spring MVC**. For example:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    public String read(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

This is an **illustrative controller snippet** that must be placed inside a Spring MVC application with annotation imports and component scanning. The method's effective mapping is `GET /api/books/{id}` within `DispatcherServlet`'s scope; do not prepend `/store` to the annotation.

## 3. Servlet URL Mapping per the Jakarta Servlet Specification

The Servlet specification allows a servlet to register several forms of URL patterns. Within the resolved context, the container selects according to the following precedence:

1. **Exact match**: matches the path verbatim, such as `/health`.
2. **Longest path-prefix match**: picks the longest prefix among patterns like `/path/*`.
3. **Extension match**: matches filename extensions, such as `*.jsp` or `*.action`.
4. **Default servlet mapping**: the `/` pattern is used when no higher-priority pattern matches.

These are **servlet selection rules**, not the precedence order among `@GetMapping` methods in Spring MVC.

| Pattern | Type | Matching Examples | Notes |
| --- | --- | --- | --- |
| `/health` | Exact | `/health` | Does not automatically match `/health/details`. |
| `/api/*` | Path-prefix | `/api/books`, `/api/books/42` | Any path under the prefix; may compete with exact/longer prefixes. |
| `/api/admin/*` | Longer path-prefix | `/api/admin/users` | Takes precedence over `/api/*` when both match. |
| `*.action` | Extension | `/orders/create.action` | Selected by suffix when no exact/prefix matches. |
| `/` | Default mapping | Paths not matched by higher-priority mappings | **Different from `/*`**, not a regular path-prefix pattern. |
| `/*` | Catch-all path-prefix | Nearly every path in the context | Can intercept routes to JSPs/default servlet or other servlets unless a higher-priority exact/prefix matches. |
| `""` | Context-root exact | Requests to the context root | Special case; different from `/`. |

**`/` and `/*` are the most error-prone pair.** Mapping `DispatcherServlet` to `/` makes it act as the default servlet mapping, so other servlets with exact/prefix/extension mappings can still receive requests according to precedence. Mapping to `/*` creates a broad path-prefix mapping: it can intercept requests intended for extension mappings/JSPs, causing 404s and processing conflicts. When building a standard Spring MVC app, **mapping `/` is the appropriate default**.

### 3.1. Example of Two Servlets Competing for a Request

Suppose a web application at `/store` has:

~~~text
catalogServlet  → /api/*
adminServlet    → /api/admin/*
statusServlet   → /health
jspServlet      → *.jsp
defaultServlet  → /
~~~

URLs are matched as follows:

| Request path excluding `/store` | Selected Servlet | Reason |
| --- | --- | --- |
| `/health` | `statusServlet` | Exact match |
| `/api/books/1` | `catalogServlet` | `/api/*` prefix |
| `/api/admin/users` | `adminServlet` | Longer prefix |
| `/views/home.jsp` | `jspServlet` | Extension match |
| `/images/logo.png` | `defaultServlet` | No higher-priority match |

The table above **only tells which servlet is called**, not that the servlet will return 200: it must still support the HTTP method, resource, and corresponding business logic.

### 3.2. Request Path Anatomy in the Servlet API

The Servlet API splits the request URI into parts. In typical scenarios (ignoring encoding/special character edge cases), you can visualize:

~~~text
requestURI ≈ contextPath + servletPath + (pathInfo if any)
~~~

Do not treat that equation as raw string concatenation for every URL: `getRequestURI()` preserves an undecoded URI differently from `getServletPath()`/`getPathInfo()`; containers apply rules to decode, normalize, and reject suspicious URIs.

| API | Meaning | Includes Query? |
| --- | --- | --- |
| `request.getRequestURI()` | Path portion of the request URI, usually including context path | **No** |
| `request.getContextPath()` | Application context prefix; root context returns empty string | No |
| `request.getServletPath()` | Path portion corresponding to the matched servlet mapping | No |
| `request.getPathInfo()` | Path portion outside the servlet path for certain mapping types, or `null` | No |
| `request.getQueryString()` | Raw query after `?`, or `null` | Query only |
| `request.getRequestURL()` | Request URL reconstructed by the container, without query string | No |

Example with **`DispatcherServlet` mapped to `/mvc/*`**, context path `/store`:

~~~text
GET /store/mvc/api/books/42?lang=vi HTTP/1.1

getRequestURI()   = "/store/mvc/api/books/42"
getContextPath()  = "/store"
getServletPath()  = "/mvc"
getPathInfo()     = "/api/books/42"
getQueryString()  = "lang=vi"
~~~

Example with **`DispatcherServlet` mapped to `/`**, still context path `/store`:

~~~text
GET /store/api/books/42?lang=vi HTTP/1.1

getRequestURI()   = "/store/api/books/42"
getContextPath()  = "/store"
getServletPath()  = "/api/books/42"
getPathInfo()     = null
getQueryString()  = "lang=vi"
~~~

The difference in `servletPath`/`pathInfo` is a **consequence of the servlet mapping type**, not a reason for controller paths to change. You can inspect the exact active mapping via `request.getHttpServletMapping()` in Jakarta Servlet 4.0+.

## 4. Spring MVC Routing After the Servlet Container Selects DispatcherServlet

A request traverses multiple layers:

~~~text
HTTP request
  → Servlet container resolves context
  → Servlet mapping selects DispatcherServlet
  → Filter chain runs according to configured mapping/dispatcher type
  → DispatcherServlet
      → HandlerMapping selects handler (method, path, and other conditions)
      → HandlerAdapter invokes handler
      → controller / service
      → HttpMessageConverter or view rendering
  → HTTP response
~~~

Controller example:

~~~java
@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping("/books/{id}")
    public String find(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

The handler mapping is `GET /api/books/{id}`. With context path `/store` and dispatcher mapping `/`, the client calls `GET /store/api/books/42`. With a `/mvc/*` dispatcher prefix, the expected URL is `GET /store/mvc/api/books/42`. Spring MVC resolves the path **within the servlet's scope** to match handlers, rather than requiring `@GetMapping` to include the context name.

Spring MVC also evaluates additional mapping conditions: HTTP method, `params`, `headers`, `consumes`, and `produces` when specified. Thus matching the path alone is not always enough: sending POST to a GET-only handler usually yields 405, while incompatible media types/Accept headers can yield 415/406, depending on context.

### 4.1. PathPatternParser, Encoded Characters, and Servlet Prefixes

Modern Spring MVC supports `PathPatternParser` for **segment-by-segment** matching, avoiding issues from decoding the full path before string matching. Since Spring Framework 6, this is Spring MVC's default strategy. However, **the Spring Boot version and `spring.mvc.servlet.path` configuration may have compatibility constraints**; some Boot 3 lines note that the default `PathPatternParser` is incompatible with Boot's servlet prefix mapping mechanism. If a prefix is required, consult the documentation for your **exact Boot version**, choose a supported matching strategy, and test routing rather than assuming every configuration behaves identically.

Do not build routes manually using:

~~~java
// Avoid this simplified assumption in production code:
String path = request.getRequestURI()
                     .substring(request.getContextPath().length());
~~~

The snippet above illustrates **an approach to avoid**, not a safe API example: it fails to account for servlet prefixes, encoded slashes, matrix variables, proxy path rewriting, and cases where Servlet API methods return differently decoded/normalized values. In Spring MVC, prefer `@RequestMapping`, `@PathVariable`, `@RequestParam`, and the framework's official URI-building APIs.

## 5. Configuring Context Path When Running Spring Boot

Spring Boot with an embedded Servlet container initializes the web server and registers `DispatcherServlet` automatically when the appropriate MVC starter is present. In a typical Spring Boot 3 application, DispatcherServlet is mapped at `/`. The context path defaults to root so URLs carry no application-specific prefix.

To set a **context path**:

~~~properties
# src/main/resources/application.properties
server.port=8080
server.servlet.context-path=/store
~~~

Or the YAML equivalent:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /store
~~~

With controller mapping `/api/books/{id}`, the direct public URL will be:

~~~text
http://localhost:8080/store/api/books/42
~~~

**Do not add `/store` to `@RequestMapping`**. If you write `@RequestMapping("/store/api/books")` while `server.servlet.context-path=/store` is configured, the application's route becomes `/store/store/api/books/...` and clients calling the expected URL will fail. Fix this by separating configuration layers properly instead of duplicating prefixes.

These configuration properties belong to Spring Boot, not mandatory standard properties for every Spring Framework app running on an external container. When deploying a WAR to standalone Tomcat, the **container/deployment** can determine the context path via config, WAR filename, or descriptor; do not assume `server.servlet.context-path` always takes effect the same way as in an executable JAR with an embedded server.

### 5.1. Spring MVC Servlet Path: A Different Layer

Spring Boot provides the property:

~~~properties
spring.mvc.servlet.path=/mvc
~~~

In meaning, this property changes the **DispatcherServlet registration** path under a prefix, for example from `/` to a mapping equivalent to `/mvc/*`. If `server.servlet.context-path=/store` is also set, the `@GetMapping("/api/books/{id}")` handler will be accessed at the expected URL:

~~~text
http://localhost:8080/store/mvc/api/books/42
~~~

Use this setting only when you genuinely need a **dedicated URL space for DispatcherServlet** or must run additional servlets. Do not confuse:

| Component | Property/Annotation | Effect |
| --- | --- | --- |
| Web application context | `server.servlet.context-path=/store` | Prefix applied to the entire web application |
| DispatcherServlet registration | `spring.mvc.servlet.path=/mvc` | Prefix for URLs routed to the MVC servlet (if supported by the version/matching strategy) |
| Controller route | `@RequestMapping("/api/books")` | Path inside Spring MVC |
| URL port | `server.port=8080` | Listening port of the embedded server |

**Compatibility note:** in some Spring Boot 3.x releases, `spring.mvc.pathmatch.matching-strategy=path-pattern-parser` does not work alongside servlet prefix mapping; Boot documentation notes this limitation. If startup fails or routes fail to match when setting `spring.mvc.servlet.path`, check the documentation for your exact version, verify whether `ant-path-matcher` is supported, or redesign the mapping using context path and controller routes. Do not apply this workaround mechanically across all Spring versions.

### 5.2. An API Path Prefix Does Not Have to Be a Servlet Path

Suppose you only want endpoints under `/api/v1/books`; you can simply write:

~~~java
@RestController
@RequestMapping("/api/v1/books")
class BookController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

If the server is at the root context and the dispatcher defaults to `/`, the URL is `/api/v1/books/42`. Changing `spring.mvc.servlet.path` is unnecessary. Conversely, changing the servlet path solely to add `/api` affects **every route handled by DispatcherServlet**, including non-API routes, MVC views/error handling, or dynamic resources depending on configuration. Choose the smallest change that fits the goal.

## 6. Complete Spring Boot 3 Example: Observing How the Path Is Split

This is a **Java 17+** example in a Spring Boot 3 project with the `spring-boot-starter-web` dependency. File `src/main/java/demo/web/WebPathApplication.java` contains a public main class and a package-private controller; both reside in package `demo.web`, ensuring component scanning finds the controller.

~~~java
package demo.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebPathApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public PathResult describe(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String lang,
            HttpServletRequest request) {

        return new PathResult(
                id,
                lang,
                request.getRequestURI(),
                request.getContextPath(),
                request.getServletPath(),
                request.getPathInfo(),
                request.getQueryString()
        );
    }

    record PathResult(
            long id,
            String lang,
            String requestURI,
            String contextPath,
            String servletPath,
            String pathInfo,
            String queryString
    ) {}
}
~~~

This example uses no external database. `@RestController` causes Spring MVC to serialize `PathResult` to JSON via the appropriate `HttpMessageConverter` (Jackson with the default web starter). `HttpServletRequest` is passed into the handler method by Spring from the live request.

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/store
~~~

Leave **`spring.mvc.servlet.path` unconfigured**, meaning the default dispatcher mapping is used. If the Gradle project is already configured with the Spring Boot plugin and web starter, run from the project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use:

~~~powershell
.\gradlew.bat bootRun
~~~

The commands above apply only if the **Gradle project has a wrapper and proper Spring Boot configuration**; the standalone Java snippet cannot be run via `javac WebPathApplication.java` because it depends on Spring/Servlet libraries.

Call the endpoint with curl:

~~~bash
curl -i "http://localhost:8080/store/api/books/42?lang=vi"
~~~

A successful response has **HTTP 200** and JSON equivalent to:

~~~json
{
  "id": 42,
  "lang": "vi",
  "requestURI": "/store/api/books/42",
  "contextPath": "/store",
  "servletPath": "/api/books/42",
  "pathInfo": null,
  "queryString": "lang=vi"
}
~~~

Actual JSON field order/whitespace/headers may vary by Jackson/container configuration, yet these path values are expected for a simple URL, `/store` context, and `/` dispatcher mapping. Note three points:

1. `requestURI` includes `/store` but **excludes** `?lang=vi`.
2. `contextPath` is `/store`, while `servletPath` is the entire path inside the context when DispatcherServlet uses default mapping `/`.
3. `pathInfo` is `null` in that default mapping case; its value is **not** `"/42"`.

If you change the URL to:

~~~bash
curl -i "http://localhost:8080/api/books/42?lang=vi"
~~~

You are missing `/store`, so the request normally **does not enter the desired context** and receives the corresponding error response (typically 404). If you instead use `/store/api/books/42` without a query, `lang` will be `"vi"` due to the default value in `@RequestParam`, while `queryString` will be `null`.

### 6.1. Experiment: Changing the Context Path

Change `server.servlet.context-path=/store` to:

~~~properties
server.servlet.context-path=/catalog
~~~

Restart the application. The now-valid URL is:

~~~text
http://localhost:8080/catalog/api/books/42?lang=vi
~~~

The controller **does not change a single character**. The response will have `contextPath="/catalog"`, `requestURI="/catalog/api/books/42"`, and `servletPath="/api/books/42"`. This is a visual test demonstrating that the **context path belongs to the container**, not the controller's route.

### 6.2. Experiment: Observing Servlet Prefix Mapping (Version-Dependent)

Assume DispatcherServlet is registered with pattern `/mvc/*` and Spring MVC is configured compatibly with prefix mapping. Then:

~~~text
Request            /store/mvc/api/books/42?lang=vi
Context path       /store
Servlet path       /mvc
Path info          /api/books/42
Controller route   /api/books/{id}
~~~

These values illustrate the **Servlet specification**. Do not enable `spring.mvc.servlet.path=/mvc` in a running application without reading the matching strategy compatibility notes in section 5.1.

## 7. Registering DispatcherServlet at Application Startup

A servlet receives requests only after **being registered with the container** with a name/instance and URL mapping. There are two common deployment environments.

### 7.1. Spring Boot Executable JAR with Embedded Servlet Container

Typically:

1. Run `SpringApplication.run(...)`.
2. Spring Boot initializes the `ApplicationContext` and embedded server if the app is a Servlet web app.
3. Boot auto-configures `DispatcherServlet` and registers the servlet with the container, defaulting to `/`.
4. The container begins accepting requests on the configured port.
5. Spring MVC uses handler mappings from the `ApplicationContext` to locate controllers.

When using the standard MVC starter, **you do not need to declare `DispatcherServlet` manually in `web.xml`**. If custom servlet registrations or special MVC configurations exist, do not assume Boot defaults remain untouched.

### 7.2. Traditional Spring MVC Application Deployed as a WAR

An external Servlet container can read `WEB-INF/web.xml` to register DispatcherServlet. Minimal example illustrating servlet mapping:

~~~xml
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
    <load-on-startup>1</load-on-startup>
</servlet>

<servlet-mapping>
    <servlet-name>dispatcher</servlet-name>
    <url-pattern>/</url-pattern>
</servlet-mapping>
~~~

**This is only the mapping declaration snippet**, not a complete `web.xml` with full schema, Spring context/config, and application configuration. Modern projects can use a Java initializer instead of XML. The core point is that `url-pattern` selects the servlet at the Servlet container layer, whereas `@RequestMapping` selects the controller at the Spring layer.

With Java configuration, Spring MVC supports `WebApplicationInitializer` and helper classes such as `AbstractAnnotationConfigDispatcherServletInitializer`. An example initializer for a WAR:

~~~java
package demo.web;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class WebInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebMvcConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
~~~

Here `WebMvcConfig` is the **application's Spring MVC configuration class that must already exist**, e.g. `@Configuration`, `@EnableWebMvc`, `@ComponentScan`; the initializer snippet is not a standalone Java file that runs without that class. Use only **one deliberate, consistent registration mechanism**; registering the same servlet via both XML and an initializer can cause conflicts.

### 7.3. Registering an Additional Servlet Alongside DispatcherServlet

Spring Boot can register an additional `Servlet` via `ServletRegistrationBean` when an independent traditional servlet endpoint is needed. Below is an **example configuration class** placed in a Spring Boot Servlet application with the servlet API:

~~~java
package demo.web;

import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ExtraServletConfig {

    @Bean
    ServletRegistrationBean<HttpServlet> extraServlet() {
        HttpServlet servlet = new HttpServlet() {
            @Override
            protected void doGet(
                    HttpServletRequest request,
                    HttpServletResponse response) throws IOException {
                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write("legacy servlet");
            }
        };

        return new ServletRegistrationBean<>(servlet, "/legacy/*");
    }
}
~~~

If the context path is `/store`, the URL `/store/legacy/test` is mapped by the container to this servlet via the `/legacy/*` prefix. According to Servlet matching, `/legacy/*` takes precedence over DispatcherServlet's default `/` mapping. Exact illustrative response body:

~~~text
legacy servlet
~~~

Do not create `@GetMapping("/legacy/test")` expecting it to handle this request; in this example **the extra servlet already intercepted the request first**, so Spring MVC controllers do not participate. Remember that `Filter`s also have their own mappings and can apply to both servlets depending on registration.

## 8. Distinguishing Servlet Mapping and Filter Mapping

A `Filter` (e.g., logging, authentication, CORS handling depending on the system) can be registered with a URL pattern or servlet name. This belongs to the **container filter chain**, not `@RequestMapping`, and does not directly select a controller method.

Example:

~~~text
Filter mapping: /*          → runs for matching paths in the context
DispatcherServlet: /         → default MVC servlet
LegacyServlet: /legacy/*     → separate servlet
~~~

When calling `/store/legacy/test`, a filter matching `/*` can still execute; then the container selects LegacyServlet. The exact same URL pattern `/*` used for **filter mapping** has a different meaning from registering **DispatcherServlet mapping** as `/*`.

Filters do not automatically apply to every dispatch type unless configured: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, and `ERROR` can all affect execution. Check `DispatcherType` and actual chain ordering when handling errors, forwards, or async requests.

## 9. Reverse Proxies, Ingress, and External Application Paths

In real deployments, the URL seen by the browser may **differ from the URL received by the container**. For example:

~~~text
Client:
  https://example.test/platform/store/api/books/42
       |
       v
Reverse proxy:
  strips /platform prefix
  forwards to http://backend:8080/store/api/books/42
       |
       v
Spring Boot:
  context path = /store
  DispatcherServlet = /
  controller mapping = /api/books/{id}
~~~

In this example, `/platform` belongs to the **proxy route**, not automatically `request.getContextPath()`. If the app generates redirect links from its internal URL without knowing the external prefix, clients may be redirected to a URL missing `/platform`.

Proxies can pass metadata such as `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Prefix`. Spring Boot Servlet apps offer mechanisms like `server.forward-headers-strategy` (e.g., `NATIVE` or `FRAMEWORK`) to process forwarded headers when the environment allows. **Trust forwarded headers only from a trusted reverse proxy**: if external Internet clients can spoof them, generated redirects or detected host/scheme values can be wrong or insecure.

Do not simultaneously add `/platform` to the ingress rewrite, context path, and controller mapping just because the browser URL displays that prefix. First determine **whether the proxy preserves or strips the prefix**, then configure a single clear owner.

### 9.1. Static Resources and the Root Path

In Spring Boot MVC, static resources can be served from standard classpath directories such as `/static` and `/public` under default configurations; the static resource handler mapping may use the `/**` pattern. This is a **Spring MVC resource handler mapping**, distinct from the **default servlet URL mapping `/`** in the Servlet container.

Therefore, a request returning 404 does not always mean "no servlet matched": the request may have entered DispatcherServlet, been matched by the static resource handler, and failed because the file did not exist. These differences affect which exceptions are thrown and how `@ControllerAdvice` observes 404s.

## 10. Debugging Workflow When a Path Returns 404 or 405

Suppose you expect `GET /store/api/books/42`:

1. **Check origin and context path.** Which port is the server listening on? Is the app deployed at `/store`, `/`, or another WAR name?
2. **Check servlet registration/mapping.** Is DispatcherServlet mapped to `/`, `/mvc/*`, or `/*`? Does another servlet have a higher-priority exact/prefix/extension mapping?
3. **Check effective controller mapping.** What is the combination of class-level and method-level `@RequestMapping`? Do the annotations match method/params/headers/consumes/produces?
4. **Compare request path after proxy.** Does the proxy keep or strip prefixes? Is there URL rewriting, trailing slash handling, encoded paths, or gateway routing?
5. **Inspect the actual response.** 404 usually relates to a non-matching path/resource; 405 indicates the method is not allowed in that context; 401/403 may come from a security filter before reaching the controller.
6. **Check logs/tracing and handler mappings.** If using Spring Boot Actuator with the mappings endpoint enabled/authorized appropriately, you can inspect registered mappings. Do not expose this endpoint publicly outside administrative environments.

Test with curl:

~~~bash
curl -i "http://localhost:8080/store/api/books/42?lang=vi"
curl -i "http://localhost:8080/api/books/42?lang=vi"
curl -i -X POST "http://localhost:8080/store/api/books/42"
~~~

With the example controller having only `@GetMapping`:
- The first request normally succeeds with 200.
- The second request lacks `/store`, so it normally returns 404.
- The third request hits the right URI in the context, yet the method is unsupported by the controller; it normally results in 405 (unless another filter/proxy/handler intervenes).

**Do not look only at the JSON error body.** HTTP status, the `Allow` header in 405, security config, proxy routing, and logs showing the selected handler help identify which layer rejected the request.

### 10.1. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Controller looks right yet `/api/...` returns 404 | `server.servlet.context-path=/store` is set | Call `/store/api/...`; do not change the controller. |
| URL has `/store/store/api/...` | Context prefix was also added to the controller | Remove `/store` from handler mappings. |
| Prefix `/mvc` causes routes not to match | Servlet prefix differs from controller path or matching strategy conflict | Check registration, Servlet API path parts, and version compatibility. |
| JSP/extension routes suddenly break | Overly broad `/*` dispatcher mapping | Revisit default mapping `/` and servlet matching precedence. |
| Endpoint accepts GET yet rejects POST | Method mapping does not support POST | Use the right HTTP method or add a POST handler per API contract. |
| Service behind ingress redirects to wrong hostname/path | Forwarded headers or rewrite misconfigured | Check external/internal URLs, trusted proxies, and forwarding strategy. |
| Static file returns 404 even though other controllers work | Incorrect static resource location/pattern | Check resource handlers and file locations. |
| `getServletPath()` differs from expectation | Servlet mapping is not `/` | Read `getHttpServletMapping()` and `getPathInfo()` instead of parsing the URL manually. |

## 11. Practice Exercises and Answers

**Exercise 1.** An application has `server.servlet.context-path=/academy`, DispatcherServlet mapping `/`, and controller:

~~~java
@RestController
@RequestMapping("/courses")
class CourseController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "course-" + id;
    }
}
~~~

Which URL invokes the method for id 7? If the app runs at origin `http://localhost:8080` and no other route intervenes, what is the response body?

**Exercise 2.** With context path `/academy` and DispatcherServlet URL pattern `/mvc/*`, the request is `/academy/mvc/courses/7?lang=vi`. Give the values of `requestURI`, `contextPath`, `servletPath`, `pathInfo`, and `queryString`.

**Exercise 3.** In the same application, Servlet A maps `/`, Servlet B maps `*.jsp`, and Servlet C maps `/api/*`. Which servlet receives `/api/books`, `/view.jsp`, and `/favicon.ico`?

**Exercise 4.** Why is changing `@RequestMapping("/courses")` to `@RequestMapping("/academy/courses")` the wrong way to handle context path `/academy`?

**Exercise 5.** A proxy serves `/platform/academy/courses/7` yet forwards internally as `/academy/courses/7`. When reading `getContextPath()` inside the app, will it see `/platform/academy` or `/academy` for a normal internal request? What else must the app consider when generating external links?

### Answers with Explanations

1. URL `http://localhost:8080/academy/courses/7`. Text body `course-7` (with default converters/configuration supporting `String` responses); do not write the context path in controller route annotations.
2. `requestURI="/academy/mvc/courses/7"`, `contextPath="/academy"`, `servletPath="/mvc"`, `pathInfo="/courses/7"`, `queryString="lang=vi"`, for a simple path per the Servlet specification.
3. `/api/books` goes to C (prefix mapping); `/view.jsp` goes to B (extension mapping); `/favicon.ico` goes to A (default mapping).
4. Because the context path is already applied by the container. Adding `/academy` in the controller produces `/academy/academy/courses/7` under that configuration.
5. For a normal internal request, the context path is `/academy`, not `/platform/academy`. When generating links, account for the external URL, prefix rewrites, and forwarded headers from a trusted proxy.

## 12. Mental Checklist When Constructing URLs in Spring Web

To determine the exact URL, answer in order:
1. **Where is the application running?** What scheme/host/port does the client hit; how does any proxy rewrite paths?
2. **Which application receives the request?** What is the actual context path?
3. **Which servlet receives the request?** What URL pattern is registered for DispatcherServlet or an auxiliary servlet?
4. **Which handler is selected?** Do controller class/method mappings and HTTP conditions match?
5. **What did the container actually see?** Check Servlet API path components, mapping type, request URL, and logs.

Four principles to keep in mind: **context path** is the web application prefix; **servlet mapping** selects the servlet at the container layer; **controller mapping** selects the handler inside Spring MVC; **proxy path** is an independent layer that may rewrite URLs. Separating these responsibilities makes JAR/WAR deployment, prefix changes, and routing debugging far more consistent.

**Official reference documentation:** Jakarta Servlet Specification 6.0, sections *Request Path Elements* and *Mapping Requests to Servlets* (https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html); Spring Framework MVC *DispatcherServlet* and *Path Matching* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html); Spring Boot Reference *Servlet Web Applications*, *Spring MVC*, and *Embedded Web Servers* (https://docs.spring.io/spring-boot/reference/web/servlet.html; https://docs.spring.io/spring-boot/how-to/spring-mvc.html).