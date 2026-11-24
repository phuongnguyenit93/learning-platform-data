# Relationship Between Jersey, Static Resources, and DispatcherServlet in Spring Boot

**Context:** Spring Boot → web-runtime → **Extending the Web Platform**. This lesson explains how **Jersey (JAX-RS/Jakarta REST)**, **Spring MVC DispatcherServlet**, and the **Spring MVC static resource handler** can coexist in a single Spring Boot application. The focus is not "just add both dependencies and you're done," but **Servlet URL mapping at the container**, the difference between **Jersey ServletContainer (servlet)** and **Jersey filter**, static resource paths, fallback mechanisms, `@ApplicationPath`/`spring.jersey.application-path` configuration, architectural choices, security, and hard-to-diagnose 404 cases.

**Hands-on environment:** Java 17+, Maven, Spring Boot **3.5.16**, Spring MVC on embedded Tomcat, Jersey 3.x using the `jakarta.ws.rs.*` API. The demo project has **Jersey at `/api/*`**, MVC at `/mvc/*`, static HTML/CSS at `/` and `/assets/*`, and real HTTP tests. Spring Boot 3.5.16 is the final OSS release of the 3.5 line (released 25/06/2026); production deployments should choose a branch or maintenance plan that still receives security updates. The code pins the version to study Boot 3.5 syntax, not as a recommendation to stay on an end-of-support version forever.

## 1. Three Distinct Routing Systems — Keep Them Separate

A Spring Boot web application can contain multiple Servlets, yet the Servlet container does not ask every Servlet in turn whether it wants to handle a URL. It **selects one Servlet by registered URL pattern**. Once selected:

- If **`DispatcherServlet`** is selected, Spring MVC then uses its `HandlerMapping` implementations to locate `@Controller`, `@RestController`, `RouterFunction`, welcome pages, or the **static resource handler**.
- If **Jersey `ServletContainer`** is selected, Jersey then uses the JAX-RS model (`@Path`, `@GET`, `@Produces`, `@Provider`, ...) to locate REST resources.
- If **Jersey operates in Filter mode**, it participates in the Servlet filter chain ahead of a downstream Servlet; depending on configuration, Jersey can handle the response itself or **forward** when no Jersey route exists.

~~~text
HTTP GET /assets/site.css
          │
          ▼
     Embedded Tomcat
          │
          │  [STEP 1] Servlet URL mapping
          │
          ├──── /api/* ─────► Jersey ServletContainer
          │                      │
          │                      └── JAX-RS @Path/@GET matching
          │
          └──── / (default) ► Spring MVC DispatcherServlet
                                 │
                                 │ [STEP 2] Spring HandlerMappings
                                 ├── @RestController / @GetMapping
                                 ├── WelcomePageHandlerMapping
                                 └── ResourceHttpRequestHandler
                                       │
                                       └── classpath:/static/assets/site.css
~~~

**Important consequence:** A file existing under `src/main/resources/static` does not mean every HTTP request to that path will automatically be served by Spring Boot. If the Servlet container picks Jersey first, `DispatcherServlet` and `ResourceHttpRequestHandler` **are not called**. Jersey may return 404 even though the CSS file sits in the exact right folder.

In this lesson, "static resources" mainly refer to HTML/CSS/JavaScript/images/fonts on the classpath, **distinct from** a **JAX-RS resource** (a class annotated with `@Path` handling REST requests). Both use the word "resource," yet they are routed by two completely different systems.

## 2. What Is Jersey? How Does It Differ from Spring MVC?

**Jersey** is an implementation of **Jakarta RESTful Web Services (JAX-RS)**. It exposes HTTP APIs via annotations in `jakarta.ws.rs`. **Spring MVC** is Spring's web framework running on the Servlet API via `DispatcherServlet` and `org.springframework.web.bind.annotation` annotations.

| Aspect | Jersey / JAX-RS | Spring MVC |
| --- | --- | --- |
| Typical HTTP entry point | `org.glassfish.jersey.servlet.ServletContainer` (Servlet or Filter) | `org.springframework.web.servlet.DispatcherServlet` |
| Endpoint registration | `ResourceConfig#register`, `@Path`, `@GET`, `@POST` | `@Controller`/`@RestController` + `@GetMapping`/`@PostMapping` |
| URL base | `@ApplicationPath` or `spring.jersey.application-path` | Servlet mapping, usually `/`; optionally `spring.mvc.servlet.path` |
| Response serialization | JAX-RS `MessageBodyWriter` and providers | Spring `HttpMessageConverter` |
| Exception mapping | JAX-RS `ExceptionMapper` | Spring MVC `@ExceptionHandler`/`@ControllerAdvice` |
| Validation | Jakarta/Jersey integration via providers | Spring MVC validation integration |
| Static file auto-serving | **No**, not by merely registering a JAX-RS resource | Spring MVC `ResourceHttpRequestHandler` via Boot auto-config |
| Can it use Spring beans? | **Yes**, when Jersey/Spring integration is configured properly | Spring-managed controllers/services by default |

The same HTTP method and URL can be **defined in source code by both frameworks**, yet which framework runs depends on **container mapping/Servlet filter chain**, not on annotation naming priority.

### 2.1. Example of the Same Functionality with Different APIs

Jersey endpoint (illustrative snippet):

~~~java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/hello")
public class JerseyHelloResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "hello from Jersey\n";
    }
}
~~~

Equivalent MVC endpoint:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SpringHelloController {
    @GetMapping(value = "/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello from MVC\n";
    }
}
~~~

**These two snippets are separate classes for comparison, not a runnable project.** For Jersey, you also need a `ResourceConfig` to register the class and Servlet/Filter mapping. For MVC, you need `DispatcherServlet`/a Spring MVC web application. When both classes define `/hello`, **the container does not compare JAX-RS `@Path` against Spring `@GetMapping` to pick the "right" handler**. The safe approach is separating namespaces.

### 2.2. Spring Beans in Jersey

Spring Boot provides native integration so a Jersey resource class can be `@Component` and inject Spring services via constructor/supported injection. For Jersey to know which resources are endpoints, you still must register them in `ResourceConfig` (for example `register(HelloResource.class)`). **Spring component scanning does not turn `@RestController` into a Jersey resource**; conversely, `@Path` does not make `DispatcherServlet` treat the class as a Spring MVC controller.

When `@Component` is placed on a Jersey resource, Spring can manage its lifecycle and DI; however, JAX-RS routing/converters/exception mappers remain Jersey's. Do not mix `@GetMapping` and `@Path` on a single handler method expecting both pipelines to apply together.

## 3. The Most Critical Step: Servlet URL Mapping

The Jakarta Servlet 6.0 specification defines the relative precedence by which the container matches a Servlet:

1. **Exact path mapping:** e.g., `/health`.
2. **Longest path-prefix mapping:** e.g., `/api/*` matches URLs under `/api/`.
3. **Extension mapping:** e.g., `*.jsp`, when no exact/prefix mapping matches.
4. **Default mapping:** `/`, when no higher-precedence mapping matches.

In the Servlet spec, `/` and `/*` **do not play the same role**:
- `/` is the **default Servlet mapping**, suitable as a fallback when no other mapping applies.
- `/*` is a **very broad path-prefix mapping**, which captures nearly all URLs ahead of a Servlet with default mapping `/`.
- `/api/*` is a narrower path-prefix mapping that routes only matching URLs to Jersey.

In a typical Spring Boot Servlet application, `DispatcherServlet` is registered at **`/`**. When Jersey runs in **default Servlet mode**, Boot registers it with **`/*`** unless you configure a base path. That is why an app with both MVC and default Jersey can suddenly return 404 for static files.

### 3.1. Comparing Two Mappings

~~~text
RISKY configuration:
    Jersey ServletContainer  -> /*
    DispatcherServlet        -> /

GET /assets/site.css:
    Jersey's /* mapping takes precedence over "/" default.
    Jersey has no @Path("/assets/site.css") -> 404.
    MVC ResourceHttpRequestHandler never receives this request.

SEPARATED configuration:
    Jersey ServletContainer  -> /api/*
    DispatcherServlet        -> /

GET /api/hello:
    /api/* -> Jersey @Path("/hello") -> 200.

GET /mvc/hello:
    /     -> DispatcherServlet -> Spring MVC controller -> 200.

GET /assets/site.css:
    /     -> DispatcherServlet -> static resource handler -> 200.
~~~

With separated namespaces, routing happens **before** Spring MVC selects controllers or static handlers. Adding `@Order` on a `@Controller` or `WebMvcConfigurer` cannot change which Servlet Tomcat already picked.

### 3.2. Who Owns Which URL in the Recommended Model?

| Request path | Selected Servlet | Expected Handler |
| --- | --- | --- |
| `GET /api/hello` | Jersey `/api/*` | JAX-RS resource `@Path("/hello")` |
| `GET /api/mvc/hello` | Jersey `/api/*` | 404 if no matching JAX-RS route exists; **does not** try MVC |
| `GET /mvc/hello` | `DispatcherServlet` at `/` | Spring MVC `@GetMapping("/mvc/hello")` |
| `GET /assets/site.css` | `DispatcherServlet` | Spring MVC `ResourceHttpRequestHandler` |
| `GET /` | `DispatcherServlet` | Welcome page if `static/index.html` exists |
| `GET /api/assets/site.css` | Jersey `/api/*` | Typically 404, even if `static/api/assets/site.css` exists |
| `GET /unknown` | `DispatcherServlet` | MVC static handler may end with `NoResourceFoundException`/404 |

**Do not deduce the target Java class solely from the URI path**: you must verify runtime mappings. A public URL may also be rewritten by a CDN, Nginx, or gateway before reaching Tomcat.

### 3.3. `@ApplicationPath` and `spring.jersey.application-path`

In Spring Boot, the simplest way to change Jersey's servlet mapping is annotating the `ResourceConfig` subclass:

~~~java
import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
    }
}
~~~

In Jersey servlet mode, this mapping becomes **`/api/*`**, and `@Path("/hello")` inside is resolved relative to **`/api`**. Hence the final URL is **`/api/hello`**, not `/api/api/hello`.

Alternatively, use the property:

~~~properties
spring.jersey.application-path=/api
~~~

**If set, this property overrides `@ApplicationPath`** per Spring Boot. To avoid two competing configuration sources, pick one clear option and write mapping tests. If `ResourceConfig` has no `@ApplicationPath` and no property is set, the default Jersey servlet can register broadly at `/*`.

**`spring.jersey.type=servlet`** is the default mode in Boot 3.5; setting it explicitly in the lab project improves readability. Jakarta REST's `@ApplicationPath` does not replace the application-wide `server.servlet.context-path`.

### 3.4. Context Path and Proxy Prefix Are Not Jersey's Base Path

Suppose you configure:

~~~properties
server.servlet.context-path=/portal
spring.jersey.application-path=/api
~~~

Then the Servlet context path is prepended to **every** route in the application: Jersey normally receives `/portal/api/hello`; MVC receives `/portal/mvc/hello`; static files receive `/portal/assets/site.css`. The context path `/portal` is neither Jersey's `@Path` nor `/api`.

When a proxy exposes `/shop/api/...` publicly while the backend receives `/api/...`, design proxy rewrites/forwarded prefixes properly; **do not** blindly change `@ApplicationPath("/shop/api")` unless the backend actually receives that path. When diagnosing a 404, record **both the public URI and the upstream URI**, because Servlet mappings cannot be fixed by tweaking media types or CORS.

## 4. How Does Spring Boot Serve Static Resources?

When Spring MVC is auto-configured and `DispatcherServlet` is selected, Boot registers static resource handlers via `ResourceHttpRequestHandler`.

Default classpath locations include:

~~~text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
~~~

Spring Boot can also serve files from the root of the `ServletContext` depending on configuration. Examples:

~~~text
src/main/resources/static/index.html          -> GET /
src/main/resources/static/assets/site.css    -> GET /assets/site.css
src/main/resources/public/logo.svg           -> GET /logo.svg
src/main/resources/META-INF/resources/help.html -> GET /help.html
~~~

**Do not** include `/static/` in the public URL just because the directory is named `static`. In the example, the file at `classpath:/static/assets/site.css` has the public path `/assets/site.css`, not `/static/assets/site.css`.

### 4.1. Resource Handler Is Not Tomcat's Default Servlet

Spring Boot MVC **serves static files via the Spring MVC handler by default**, not by relying on Tomcat's default servlet. Standalone embedded applications generally **do not enable** the container's own default Servlet under Boot defaults.

The property:

~~~properties
server.servlet.register-default-servlet=true
~~~

enables the container default servlet when you have a specific reason and understand container mappings. It is **not** the right fix for Jersey `/*` swallowing all URLs: URLs matched by Jersey may never reach the default servlet. If an application has only a Jersey Filter and **no** downstream servlet to serve requests Jersey ignores, you may need the default servlet; **however, if `DispatcherServlet` is present**, it already acts as the downstream handler for MVC/static requests.

### 4.2. Two Easily Confused Static Configurations

~~~properties
# Default MVC static handler is typically mapped to /**
spring.mvc.static-path-pattern=/**

# Example: move static URLs to /resources/** instead of /**.
# spring.mvc.static-path-pattern=/resources/**
~~~

`spring.mvc.static-path-pattern` changes the **URL pattern**, not necessarily the physical directory. If a file lives at `classpath:/static/assets/site.css` and you set `/resources/**`, the public URL becomes **`/resources/assets/site.css`** when that handler mapping is used.

~~~properties
# Example replacing the default classpath locations:
# spring.web.resources.static-locations=classpath:/assets/
~~~

`spring.web.resources.static-locations` changes the **locations where Spring searches for bytes**, without automatically changing the public URL prefix. With this property, files must go under `src/main/resources/assets/` instead of the default `static` unless you keep the old locations in the list.

**Do not confuse the two properties:** one changes the **URL**, the other changes **where files are loaded from**. Both only take effect when the request reaches **DispatcherServlet/the static handler**; neither pulls a URL away from the Jersey servlet into MVC.

### 4.3. Why Can an Unknown URL Throw `NoResourceFoundException`?

With the default MVC static mapping `/**`, Spring MVC can find a **matching resource handler for the path**, even when **no file exists**. The handler looks for the file and raises a 404, typically `NoResourceFoundException` in modern Spring Framework. Thus not every unmatched MVC request throws `NoHandlerFoundException`.

To distinguish them:
- Request **never enters `DispatcherServlet`** → inspect Servlet mappings/Jersey.
- Request enters the MVC static handler but **the file does not exist** → check classpath locations, JAR build, and case-sensitive filenames.
- Request enters an MVC controller and returns an error → check controller/exception handler and HTTP method/content negotiation.

Narrowing `spring.mvc.static-path-pattern` to a tighter prefix or setting `spring.web.resources.add-mappings=false` changes MVC fallback behavior, but **will not restore** MVC handling if Jersey is claiming the path at the Servlet layer.

### 4.4. Static Index, Caching, and WebJars

If `src/main/resources/static/index.html` exists, Boot MVC typically treats it as the **welcome page** at `/` when no higher-priority route matches. WebJars are served under `/webjars/**` if JAR dependencies follow the WebJar layout.

Caching/resource chains can be configured via `spring.web.resources.cache.*`, `spring.web.resources.chain.*`, and `WebMvcConfigurer`. However, disabling cache, clearing browser cache, or renaming files will not solve a **Jersey servlet `/*` hijacking static URLs**. First confirm which servlet receives the request; only then tune caching/versioning/MIME.

### 4.5. JAR Packaging and Static Directories

During `spring-boot:repackage`, resources under `src/main/resources/static` are packaged onto the executable JAR's classpath, e.g., under `BOOT-INF/classes/static`. Do not make the servlet container read files from an external `src/main/resources/...` path once packaged.

Do not rely on `src/main/webapp` as a default static location for executable JARs: Spring Boot docs warn that directory suits WARs better and may be ignored in JARs. For user-uploaded content, **never** place it under public static classpath directories; use dedicated storage and authorization.

## 5. How Does Spring Boot Auto-Configure Jersey?

When `spring-boot-starter-jersey` and **one** valid `ResourceConfig` bean are present, Boot provides Jersey auto-configuration. Two main modes:

| Mode | Property | Typical Spring Boot registration | Mechanism |
| --- | --- | --- | --- |
| **Servlet** | `spring.jersey.type=servlet` (default) | `ServletRegistrationBean` named `jerseyServletRegistration` | URL is routed by Servlet container to Jersey servlet; no automatic fallback to MVC |
| **Filter** | `spring.jersey.type=filter` | `FilterRegistrationBean` named `jerseyFilterRegistration` | Jersey runs in the filter chain; can forward to a downstream Servlet if configured |
| Filter order | `spring.jersey.filter.order` | Order value for the Jersey filter | Meaningful only in filter mode |
| Servlet startup | `spring.jersey.servlet.load-on-startup` | Load-on-startup policy | Not route/JAX-RS ordering |
| Init parameters | `spring.jersey.init.*` | Params passed to Jersey Servlet/Filter | Used only when Jersey configuration requires them |

`@Component public class JerseyConfig extends ResourceConfig` is already treated by Spring as **one `ResourceConfig` bean**. Do not also declare another `@Bean ResourceConfig`, as that can unintentionally create **multiple `ResourceConfig` beans**. Register REST classes explicitly:

~~~java
@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        // register(MyExceptionMapper.class);
        // register(MyFeature.class);
    }
}
~~~

This snippet is **conceptual**; imports and the complete project appear in Section 6.

For advanced customization, you can provide `ResourceConfigCustomizer` or custom registration beans following Boot's contract. However, **never keep default auto-registration active while also registering another Jersey `ServletContainer`** on the same URL, which causes mapping conflicts or duplicate filter/servlet execution.

## 6. Complete Project: Jersey `/api/*` + Spring MVC `/mvc/*` + Static HTML/CSS

This is the **recommended coordination pattern for applications needing both frameworks in distinct namespaces**: run Jersey as a **Servlet** under `/api/*`, while Spring MVC `DispatcherServlet` stays default at `/`. No Jersey Filter, no MVC ordering tweaks, and no Tomcat default servlet needed.

### 6.1. Directory Structure

~~~text
jersey-mvc-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jerseymvcdemo/
    │   │   ├── DemoApplication.java
    │   │   ├── JerseyConfig.java
    │   │   ├── HelloResource.java
    │   │   └── MvcHelloController.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/
    │           ├── index.html
    │           └── assets/site.css
    └── test/java/com/example/jerseymvcdemo/
        └── WebRoutingIntegrationTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>jersey-mvc-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jersey</artifactId>
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

The two starters serve **two programming models**, Spring MVC and Jersey. Maven resolution manages compatible transitive dependencies through Boot's BOM. Do not use `javax.ws.rs.*` in Boot 3.5/Jersey 3.x; the modern annotations use the **`jakarta.ws.rs.*`** namespace.

### 6.3. `src/main/java/com/example/jerseymvcdemo/DemoApplication.java`

~~~java
package com.example.jerseymvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.4. `src/main/java/com/example/jerseymvcdemo/JerseyConfig.java`

~~~java
package com.example.jerseymvcdemo;

import jakarta.ws.rs.ApplicationPath;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.stereotype.Component;

@Component
@ApplicationPath("/api")
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
    }
}
~~~

**Why `@ApplicationPath("/api")`?** It narrows the Jersey Servlet mapping from the overly broad `/*` to `/api/*`, allowing non-API paths to reach `DispatcherServlet`. `ResourceConfig#register` informs Jersey that `HelloResource` handles HTTP requests. No manual `ServletRegistrationBean` is needed because Boot auto-registers Jersey when a `ResourceConfig` is present.

### 6.5. `src/main/java/com/example/jerseymvcdemo/HelloResource.java`

~~~java
package com.example.jerseymvcdemo;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.springframework.stereotype.Component;

@Component
@Path("/hello")
public class HelloResource {
    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        return "jersey-ok\n";
    }
}
~~~

This is a **JAX-RS resource**, not a Spring `@RestController`. The effective URL is `/api/hello`, because `/api` comes from the servlet base mapping and `/hello` is the class-level JAX-RS path. `@Component` enables Spring lifecycle/DI integration; `register(HelloResource.class)` binds the endpoint in Jersey.

### 6.6. `src/main/java/com/example/jerseymvcdemo/MvcHelloController.java`

~~~java
package com.example.jerseymvcdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MvcHelloController {

    @GetMapping(value = "/mvc/hello",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "mvc-ok\n";
    }
}
~~~

This is a Spring MVC controller discovered by `DispatcherServlet` via `RequestMappingHandlerMapping`. It handles `/mvc/hello` when the container picks the default `/` Servlet. If you copy this mapping to `/api/mvc/hello` while keeping the Jersey Servlet at `/api/*`, the MVC endpoint will **not be called**, even though Spring registers the method in the `ApplicationContext`.

### 6.7. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=jersey-mvc-demo

# Explicit for readers: Jersey runs as a Servlet.
spring.jersey.type=servlet

# Do not set spring.jersey.application-path:
# @ApplicationPath("/api") on JerseyConfig defines the base path.

# Keep default MVC servlet mapping "/" and static handlers.
# Do not add @EnableWebMvc or custom DispatcherServlet registration.
~~~

If you use `spring.jersey.application-path=/api` instead of the annotation, **remove the annotation or accept the property override** and write integration tests. Never leave Jersey mapped too broadly while expecting Spring MVC's static handler to reclaim URLs on its own.

### 6.8. `src/main/resources/static/index.html`

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Jersey and MVC demo</title>
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
  <h1>Jersey and MVC demo</h1>
  <p>Servlet mapping separates Jersey and Spring MVC.</p>
  <ul>
    <li><a href="/api/hello">Jersey REST</a></li>
    <li><a href="/mvc/hello">Spring MVC</a></li>
  </ul>
</body>
</html>
~~~

Because `index.html` lives in **classpath:/static** and Boot MVC supports welcome pages, `GET /` normally serves this HTML when no MVC controller handles root ahead of it. The CSS is referenced via `/assets/site.css`, not `/static/assets/site.css`. With a context path or reverse proxy prefix, use context-aware links; the absolute paths above are solely for this root-context lab.

### 6.9. `src/main/resources/static/assets/site.css`

~~~css
body {
  font-family: sans-serif;
  color: #246;
}
h1 {
  margin-bottom: 0.5rem;
}
~~~

This file is served by Spring MVC `ResourceHttpRequestHandler` at `GET /assets/site.css`, provided `DispatcherServlet` is selected. You do not need to write `@GetMapping("/assets/site.css")` for static files.

### 6.10. Running the Application

From the root folder `jersey-mvc-demo`:

~~~bash
java -version
mvn spring-boot:run
~~~

Once the app starts on port 8080, open another terminal:

~~~bash
curl -i http://localhost:8080/api/hello
curl -i http://localhost:8080/mvc/hello
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/
curl -i http://localhost:8080/api/unknown
~~~

**Results to verify** (controller bodies are exact; full HTTP headers may vary by environment):

| Request | Expected Status | Content/Processing Path |
| --- | --- | --- |
| `GET /api/hello` | **200 OK** | Body `jersey-ok\n`, Jersey JAX-RS resource |
| `GET /mvc/hello` | **200 OK** | Body `mvc-ok\n`, Spring MVC controller |
| `GET /assets/site.css` | **200 OK** | CSS containing `color: #246;`, MVC static handler |
| `GET /` | **200 OK** | HTML containing `Jersey and MVC demo`, MVC welcome page |
| `GET /api/unknown` | **404 Not Found** | Jersey selected because of `/api/*`, no JAX-RS endpoint |
| `GET /unknown` | **404 Not Found** | No matching MVC controller or static resource |

**Important:** `curl -i` prints headers, `Date`, `Content-Type`, `Connection`, and encoding that can differ by embedded server version. The expected statuses and bodies above are **design-derived results from the source code**, not a claim of execution on every host. Both `"jersey-ok\n"` and `"mvc-ok\n"` have trailing newlines matching the Java code.

In PowerShell you may need `curl.exe` if `curl` is aliased to `Invoke-WebRequest`. On Windows, copying text files with CRLF can change line endings in CSS/HTML compared to the code fences; avoid raw byte-for-byte equality checks on CSS/HTML unless file encoding and creation are controlled.

### 6.11. Integration Test with a Real Embedded Server

File **`src/test/java/com/example/jerseymvcdemo/WebRoutingIntegrationTest.java`**:

~~~java
package com.example.jerseymvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRoutingIntegrationTest {

    @LocalServerPort
    int port;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    @Test
    void jerseyHandlesApi() {
        String body = RestClient.create().get()
                .uri(url("/api/hello")).retrieve().body(String.class);
        assertEquals("jersey-ok\n", body);
    }

    @Test
    void dispatcherServletHandlesMvc() {
        String body = RestClient.create().get()
                .uri(url("/mvc/hello")).retrieve().body(String.class);
        assertEquals("mvc-ok\n", body);
    }

    @Test
    void mvcServesStaticCss() {
        String body = RestClient.create().get()
                .uri(url("/assets/site.css")).retrieve().body(String.class);
        assertTrue(body.contains("color: #246;"));
    }

    @Test
    void mvcServesIndexWelcomePage() {
        String body = RestClient.create().get()
                .uri(url("/")).retrieve().body(String.class);
        assertTrue(body.contains("Jersey and MVC demo"));
    }

    @Test
    void unknownApiPathDoesNotBecomeMvcResource() {
        assertThrows(HttpClientErrorException.NotFound.class, () ->
                RestClient.create().get()
                    .uri(url("/api/unknown"))
                    .retrieve().toBodilessEntity());
    }
}
~~~

Run:

~~~bash
mvn test
mvn clean package
java -jar target/jersey-mvc-demo-0.0.1-SNAPSHOT.jar
~~~

**Why `RANDOM_PORT`?** This project teaches **Servlet URL mappings** — a container-level configuration. Standalone `MockMvc` tests only exercise Spring MVC handlers and **do not** recreate real Jersey Servlet registration. `@SpringBootTest(webEnvironment=RANDOM_PORT)` starts the embedded container, so requests over sockets are routed for real. In CI/CD, also run tests against the packaged executable JAR to verify static resources are on the classpath.

If the 404 test receives 500 or a redirect instead of `HttpClientErrorException.NotFound`, inspect startup/exception configuration and the actual response before jumping to conclusions. This test expresses the contract **Jersey returns 404 for a URL inside Jersey's namespace with no JAX-RS route**, not a diagnosis of every HTTP status possible in a production app with security/gateways.

## 7. Second Option: Jersey Filter Yielding to Spring MVC

Separating the Jersey Servlet into `/api/*` is the simplest approach. However, some systems want **Jersey and MVC to share a namespace**, e.g., Jersey tries handling the request first, and if no JAX-RS route matches, MVC handles the rest. For that case, Spring Boot supports Jersey as a **Servlet Filter**, paired with Jersey's feature to forward **bodyless 404s** down the filter chain.

### 7.1. Two Configuration Changes

**Change 1:** in `application.properties`, set:

~~~properties
spring.jersey.type=filter
~~~

**Change 2:** in `ResourceConfig`, enable:

~~~java
property(ServletProperties.FILTER_FORWARD_ON_404, true);
~~~

Import `org.glassfish.jersey.servlet.ServletProperties`. Per Jersey 3.x Javadoc, **`FILTER_FORWARD_ON_404` is only meaningful in Filter mode**. When Jersey is about to return a **404 with an empty entity body**, Jersey can forward the request to the downstream filter/servlet while resetting the response status appropriately for downstream handling. If Jersey already created an error response **with an entity body**, fallback is not guaranteed; furthermore, a JAX-RS endpoint matcher may execute business logic before deciding on 404.

### 7.2. Complete Variant of `JerseyConfig`

**Apply only when testing an alternative to Section 6**; do not keep two `JerseyConfig` classes simultaneously. To apply the Jersey filter broadly and demonstrate MVC/static fallback, **remove `@ApplicationPath("/api")`** (and ensure `spring.jersey.application-path=/api` is not set). `JerseyConfig.java` in the Filter approach:

~~~java
package com.example.jerseymvcdemo;

import org.glassfish.jersey.server.ResourceConfig;
import org.glassfish.jersey.servlet.ServletProperties;
import org.springframework.stereotype.Component;

@Component
public class JerseyConfig extends ResourceConfig {
    public JerseyConfig() {
        register(HelloResource.class);
        property(ServletProperties.FILTER_FORWARD_ON_404, true);
    }
}
~~~

Properties replacing servlet mode:

~~~properties
server.port=8080
spring.jersey.type=filter

# Do not set spring.jersey.application-path=/api for the shared-namespace demo.
# Only applies filter forwarding on 404 when no entity body is present.
~~~

Now, without the JAX-RS base `/api`, Jersey's `@Path("/hello")` route appears at **`GET /hello`**; `GET /api/hello` is no longer a REST route in this setup. `GET /mvc/hello` and `GET /assets/site.css` **are designed to fall through the Jersey filter to `DispatcherServlet`** when Jersey has no matching endpoint and produces a bodyless 404. Meanwhile, `GET /hello` is served by Jersey.

Test:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/mvc/hello
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/
~~~

**Do not keep the `jerseyHandlesApi()` integration test from Section 6 unchanged when switching to the filter variant**: Jersey's expected path changed from `/api/hello` to `/hello`. Update tests alongside configuration and verify route dispatch against a real server.

### 7.3. When Is Filter Better, and When Is Namespace-Separated Servlet Better?

| Criterion | Jersey servlet `/api/*` | Jersey filter + `FILTER_FORWARD_ON_404` |
| --- | --- | --- |
| Routing authority | Container separates namespaces cleanly | Jersey tries first, then may yield to a downstream Servlet |
| Static files outside `/api` | Received directly by MVC | May pass through Jersey filter then forward to MVC |
| Path/security auditability | **High** when namespaces are clear | Must check all fallback rules, 404 with/without body |
| Cost of a static request | Never enters Jersey runtime | Can pass through Jersey matcher first |
| When Jersey lacks an endpoint | 404 inside Jersey's namespace | Can forward if 404 has no entity |
| Endpoint overlap risk | Reduced via prefix separation | Higher if Jersey and MVC share paths |
| Core config | `@ApplicationPath("/api")` or property | `spring.jersey.type=filter` and `FILTER_FORWARD_ON_404=true` |
| Downstream default servlet | Unneeded when MVC serves static | Needs a downstream Servlet for fall-through requests, usually `DispatcherServlet` |

**Architectural recommendation:** Prefer **separate Servlet mappings** whenever possible. Choose **Filter mode/fallback** only when system design demands a shared namespace or phased endpoint migration, with tests covering collisions, auth, and 404 semantics.

### 7.4. Pitfall: `FILTER_FORWARD_ON_404` Does Not "Forward Every Error to MVC"

Per Jersey `ServletProperties`, only a **404 response with no entity** qualifies for forwarding. It **does not** automatically forward:
- 401/403 from Jersey authentication/authorization;
- 405 Method Not Allowed when a URI matches a resource but the HTTP method does not;
- 406/415 content negotiation/media type errors;
- 500 from exceptions;
- 404 produced by a custom `ExceptionMapper` returning a JSON error body;
- proxy errors already returned before reaching the backend;
- URLs outside the filter URL mapping if the filter is restricted to a prefix.

Do not use fallback as a way to hide security errors. When Jersey and MVC share overlapping routes, unexpected "Jersey 404 → MVC endpoint" fallthroughs can happen. Write tests asserting **which routes are allowed to fall through**, not just the final status code.

### 7.5. `FILTER_STATIC_CONTENT_REGEX` and Restricting Filter Paths

Jersey offers `ServletProperties.FILTER_STATIC_CONTENT_REGEX` to specify a regex for paths to hand over to the Servlet engine instead of treating them as REST resources. This is an advanced option; never blindly copy a `.*` regex that disables most of Jersey. Jersey docs note the regex applies against the matching incoming servlet path; test against your actual context/base path.

If static paths are clearly delimited, a simpler option is usually **restricting the Jersey filter mapping to `/api/*`** via `@ApplicationPath`/property so asset URLs outside `/api` never pass through the filter. Even then, understand fallback conditions inside `/api`; do not force a shared namespace if unnecessary.

## 8. Default Servlet, `DispatcherServlet`, and Static Handler: Who Needs Which?

Some older guides recommend enabling the container default servlet to serve static files. In modern Spring Boot MVC, however, there are three distinct concepts:

1. **`DispatcherServlet`:** Spring MVC's Servlet, receiving requests via Servlet mapping.
2. **`ResourceHttpRequestHandler`:** MVC's internal handler invoked by `DispatcherServlet` for static files when a URL matches.
3. **Container default servlet:** A Servlet provided by the web container to serve files from the `ServletContext` root as a fallback when configured.

In an executable Spring Boot JAR with the MVC starter, 1 + 2 are usually sufficient for classpath static content. Option 3 **should not be enabled** solely to work around Jersey `/*` 404s.

### 8.1. Why Enabling the Default Servlet Does Not Rescue a `/*` Mapping

Suppose:

~~~text
Jersey Servlet      = /*
DispatcherServlet   = /
Tomcat default      = /  (cannot arbitrarily share the exact same mapping in one context)
~~~

The Servlet spec picks one servlet by mapping; `/*` still beats default `/` for matching URLs. Furthermore, two servlets **cannot arbitrarily share the exact same URL pattern** in effective registration — doing so can cause startup/registration conflicts. Thus the core fix is **separating Jersey's path** or switching Jersey to a **Filter with `forwardOn404`**, not "enabling the default servlet" and hoping the container calls all three.

### 8.2. When Jersey Filter Is Used Without an MVC Servlet

If an application uses primarily a Jersey Filter with no `DispatcherServlet` or other servlet handling fall-through requests, then `forwardOn404` needs a downstream Servlet. Spring Boot docs note you can enable:

~~~properties
server.servlet.register-default-servlet=true
~~~

**Only when appropriate for setups with no other Servlet receiving requests** — do not paste this property into the MVC/Jersey sample project in Section 6. Enabling the default servlet does not make Jersey render JSP/Thymeleaf, does not create Spring MVC `ResourceHttpRequestHandler`, and does not expose classpath resources publicly unless the runtime maps them properly.

## 9. MVC Auto-Configuration: Choices That Easily Break Static Handling

### 9.1. `@EnableWebMvc`

In Spring Boot MVC, auto-configuration provides static mappings, message converters, welcome page, and WebJars support. Adding `@EnableWebMvc` to "fix a route" can **switch to manual MVC configuration**, losing many Boot defaults unless you re-declare the handlers.

When customizing static paths, prefer **`WebMvcConfigurer` without `@EnableWebMvc`**:

~~~java
// Illustrative snippet, unnecessary in Section 6's project.
@Configuration
class StaticConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/files/**")
                .addResourceLocations("classpath:/files/");
    }
}
~~~

This is only a code snippet requiring imports for `Configuration`, `WebMvcConfigurer`, and `ResourceHandlerRegistry`. And **it only runs after `DispatcherServlet` receives the request**; if Jersey `/*` captures `/files/foo`, adding the handler above will not save it.

### 9.2. `spring.web.resources.add-mappings=false`

~~~properties
spring.web.resources.add-mappings=false
~~~

Disables Boot MVC's default static resource mappings. If CSS/JS were previously served by `ResourceHttpRequestHandler` and now return 404, check this property and custom `WebMvcConfigurer` beans. Disabling static mappings can fit API-only deployments, but should not be used just to alter status codes for unknown routes when the app has a frontend bundle.

### 9.3. Prefixing the MVC Servlet

The `spring.mvc.servlet.path` property can change `DispatcherServlet`'s path prefix in some setups. However, Boot 3.5 docs note **`PathPatternParser` matching is incompatible with setting a Servlet path prefix** in this way unless the matching strategy is adjusted. When separating Jersey and MVC, **prefer putting Jersey under `/api/*` and keeping MVC at `/`**, which is simpler than moving both `DispatcherServlet` and static handlers.

If you truly use `spring.mvc.servlet.path=/ui`, verify that static URLs also shift namespaces, check context path/proxy rewrites, and verify path-matching strategy compatibility. Do not treat `spring.mvc.servlet.path` as an alias for `spring.jersey.application-path`.

### 9.4. Routing Behind a Reverse Proxy

An API gateway might rewrite public `/v1/api/hello` to backend `/api/hello`, or vice versa. If direct backend tests pass while public URLs return 404:
- check the URI the container **actually receives** after rewrites;
- verify Jersey/MVC Servlet mappings on the backend;
- check how `X-Forwarded-Prefix`, `Forwarded`, and host/scheme affect URL generation (they do not automatically remap backend paths);
- inspect Nginx `proxy_pass` with or without a trailing slash, and regex ingress rewrite rules;
- compare responses from proxy, Jersey, and MVC via logs and headers.

Never rely solely on a 404 status code to conclude a static file is missing.

## 10. Security When Multiple Web Frameworks Run Together

Using multiple frameworks does not automatically unify security policies. The **Servlet filter chain** (such as Spring Security `DelegatingFilterProxy` → `FilterChainProxy`) can protect HTTP requests before Jersey/MVC handler selection when filter mappings cover the paths, yet that **does not automatically ensure** Jersey JAX-RS resources use Spring MVC annotations or exception handling.

### 10.1. Choosing Route Security by Namespace

Example policy concept:
- `/api/**`: JAX-RS resources, requiring bearer tokens or appropriate authN.
- `/mvc/**`: MVC controllers, requiring session or roles per business rules.
- `/assets/**`: public static JS/CSS if part of the frontend.
- `/actuator/**`: strictly managed and protected per policy.

Ensure **a `SecurityFilterChain` with specific matchers** covers APIs and any fallback chain applies cleanly to remaining URLs. If you only secure `/mvc/**` using a `securityMatcher` and leave `/api/**` outside every chain, Jersey endpoints may **bypass Spring Security**. Conversely, `anyRequest().authenticated()` can cause CSS/`index.html` to return 401 if necessary assets are not permitted.

### 10.2. Jersey Exception Mapping Differs from Spring MVC

When a Jersey method throws `jakarta.ws.rs.WebApplicationException` or another exception, Jersey applies JAX-RS `ExceptionMapper`/`Response` semantics. Spring MVC `@RestControllerAdvice`/`@ExceptionHandler` is generally **not** the global handler for the Jersey runtime.

Do not write a `@ControllerAdvice` returning JSON errors and expect the Jersey servlet to use it. Design consistent error contracts using `ExceptionMapper<Throwable>` in Jersey and `@ControllerAdvice` in MVC where needed, and test HTTP behavior across both endpoints. Avoid catch-all mappers that swallow security errors or return 200 on exceptions.

### 10.3. Jersey + Spring Security Method Security

Spring Boot advises that when protecting Jersey endpoints with Spring Security method-level rules, Jersey should be configured to use `setStatus` instead of `sendError` so Spring Security can handle authentication/authorization failures before the response commits. Example snippet inside `ResourceConfig`:

~~~java
property("jersey.config.server.response.setStatusOverSendError", true);
~~~

This is a **security-case option**, not mandatory for the lab's public endpoints. Do not confuse it with `ServletProperties.FILTER_FORWARD_ON_404`: the former affects how HTTP status/errors are written, while the latter is a fallback mechanism **only in filter mode**.

### 10.4. CORS and Preflight

CORS is a browser origin policy, not Servlet mapping. MVC `WebMvcConfigurer#addCorsMappings` applies to MVC routing; it **does not automatically configure Jersey resources** identically. Jersey has its own response filters or CORS features, and Spring Security offers `http.cors(...)` ahead of authorization when integrated. When coexisting:
- designate a single owner responsible for CORS headers and origin allowlists;
- test `OPTIONS` for both `/api/**` and `/mvc/**`;
- avoid two filters emitting duplicate/conflicting `Access-Control-Allow-Origin` and other CORS headers;
- do not treat a passing `curl` GET as proof that browser CORS/preflight passes;
- if sessions/cookies are used, CSRF and `SameSite` policies are independent of framework routing.

### 10.5. Static Directories Are Not for Private Data

Any file placed in public static locations and exposed by the MVC resource handler can be fetched via GET if routing/security permits. **Never** put private user uploads, config backups, secrets, or sensitive files inside `src/main/resources/static`. The Jersey namespace does not protect static assets outside `/api`; build dedicated authorization and file-serving controls.

### 10.6. Avoiding Route Collisions and API Bypasses

When migrating from Jersey Servlet `/api/*` to Jersey Filter `/*` + `forwardOn404`, a URL that previously returned 404 might **fall into an MVC route** with different behavior. If the system relied on 404s to hide endpoints or partition resources by namespace, fallback can introduce unintended access paths. Test authorization, methods, media types, and 404 semantics before migrating.

## 11. Runtime Inspection: Which Servlet Actually Received the Request?

### 11.1. Inspecting Servlet Registrations

You can use `ServletContext#getServletRegistrations()` to print mappings of registered Servlets. **Diagnostic snippet, not part of Section 6's runnable project**:

~~~java
@Bean
ApplicationRunner printServletMappings(ServletContext context) {
    return args -> context.getServletRegistrations().forEach((name, reg) ->
        System.out.println("SERVLET " + name
                + " class=" + reg.getClassName()
                + " mappings=" + reg.getMappings()));
}
~~~

Imports required: `jakarta.servlet.ServletContext`, `org.springframework.boot.ApplicationRunner`, and `org.springframework.context.annotation.Bean`, placed in a Spring `@Configuration` class. Enable only in controlled dev/staging environments; never expose debug endpoints publicly leaking mappings.

Expected output in clear-prefix Servlet mode:
- One servlet related to `DispatcherServlet` with mapping `/`.
- One servlet related to Jersey `ServletContainer` with mapping `/api/*` (container-generated names can vary).
- No two registrations unintentionally sharing the exact same URL pattern.
- In Jersey Filter mode, Jersey appears under **filter registrations**, not as a second Jersey servlet.

### 11.2. Inspecting the Mapping Assigned to a Request

Since Servlet 4.0+, `HttpServletRequest#getHttpServletMapping()` reveals the URL mapping match for a request. Example MVC controller **diagnostic snippet**:

~~~java
@GetMapping("/debug/servlet")
@ResponseBody
public String servletMapping(HttpServletRequest request) {
    var m = request.getHttpServletMapping();
    return m.getServletName() + " pattern=" + m.getPattern()
            + " match=" + m.getMappingMatch();
}
~~~

Place the method in a `@Controller` with appropriate imports. This endpoint **only runs when MVC is selected**, so to observe the Jersey servlet similarly you must inject JAX-RS `@Context HttpServletRequest` in a Jersey resource or measure in a Servlet filter ahead of routing. Do not leave debug routes enabled in production because they can disclose internal structure.

### 11.3. Logging Filters, DispatcherServlet, and Jersey

Temporarily enable logging in staging:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.resource=TRACE
logging.level.org.glassfish.jersey=INFO
~~~

Read actual logs rather than guessing "Jersey 404 log" = "MVC static file missing." Attach a correlation ID and record the request URI, Servlet mapping (dev-only), selected handler, and status. Spring Boot Actuator `/actuator/mappings` can assist in inspecting Servlet/MVC mappings depending on version and exposure, though it **does not replace container testing**; secure Actuator against public access.

### 11.4. Interference from DevTools and Browser Cache

During development, editing a static file in an IDE without seeing changes can involve resource copying, DevTools restarts, build outputs, or caching. Before altering Jersey config:
1. Call the static URL directly with `curl -i`.
2. Verify the source file exists at `src/main/resources/static`.
3. Verify the file was copied into `target/classes/static` or the packaged JAR.
4. Check mappings to see whether the request hits `DispatcherServlet` or Jersey.
5. Only then inspect browser/CDN caches and cache headers.

If `curl -i /assets/site.css` returns a Jersey error body even though the static file is inside the JAR, that is a strong signal the URL entered an overly broad Jersey Servlet.

## 12. Symptoms, Causes, and Fixes Table

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `GET /api/hello` 404 | `ResourceConfig` missing resource registration; wrong base path; wrong class annotation | Check `@ApplicationPath`/property override, `@Path`, Jersey startup log |
| `GET /assets/site.css` 404 only after adding Jersey | Default Jersey Servlet `/*` captures URL | Map Jersey to `/api/*` or choose Filter + `forwardOn404` |
| `GET /mvc/hello` 404 while controller exists | Container selects Jersey or MVC disabled/mapped elsewhere | Inspect Servlet registrations and effective URI |
| `GET /` does not render `index.html` | Jersey `/*`, missing static file, altered MVC auto-config | Check servlet mapping first; then file/`WelcomePageHandlerMapping` |
| `GET /static/assets/site.css` 404 | Physical directory name included in URL | Use `/assets/site.css` |
| Jersey API works but HTML/CSS fail | Jersey API routing works, MVC static never receives URL | Separate Jersey prefix; test `/assets` directly |
| Static file exists in JAR yet 404 | Servlet selects Jersey, static mappings disabled, or wrong public path | Check mappings, `add-mappings`, path pattern |
| `NoResourceFoundException` in MVC | `ResourceHttpRequestHandler` matches path but file not found | Check classpath, spelling/case, handler locations |
| `NoHandlerFoundException` behaves unexpectedly | Static mapping does not catch path or MVC config changed | Inspect handler mappings and `static-path-pattern` |
| Jersey `@GET` method does not run | Missing registration, wrong base path, media type/method, or router did not pick Jersey | Check route/JAX-RS providers, GET/POST, `Accept` |
| MVC `@ControllerAdvice` ignores Jersey errors | Two distinct exception pipelines | Separate Jersey `ExceptionMapper` and MVC advice |
| `@EnableWebMvc` breaks static files | Boot MVC auto-config disabled | Remove `@EnableWebMvc` unless intentionally managing all MVC config |
| `spring.web.resources.add-mappings=false` | Disables MVC default static handler | Re-enable mappings or register resources manually |
| `spring.mvc.static-path-pattern=/resources/**` yet calling `/assets/...` | Static URL was remapped | Request `/resources/assets/...` |
| Filter mode fallback still 404 | `FILTER_FORWARD_ON_404` disabled; Jersey error has body; no downstream Servlet | Check config, entity-less 404, `DispatcherServlet`/default servlet |
| Jersey 405 instead of MVC GET | Container selected Jersey but HTTP method invalid | Fix JAX-RS routes; Filter `forwardOn404` does not forward 405 |
| CORS GET works but OPTIONS fails | Security/Jersey/MVC CORS settings differ | Test preflight per route and final CORS headers |
| Actuator 404 after adding Jersey | Jersey `/*` captures `/actuator/**` or management path changed | Check mappings and actuator exposure/security |
| OAuth callback/redirect wrong prefix | Inconsistent proxy rewrite/context path | Compare public URI, upstream URI, context path, forwarded headers |
| MockMvc test passes yet JAR 404s static | MockMvc does not simulate Servlet container/Jersey mapping | Use `RANDOM_PORT` integration tests |
| `javax.ws.rs`/`jakarta.ws.rs` mismatch on upgrade | Old API namespace used | Boot 3.x/Jersey 3.x uses `jakarta.ws.rs.*` |
| Two Jersey resources fire unexpectedly | Duplicate registration, class scanning + manual register, providers | Single consistent `ResourceConfig`, inspect startup |

### 12.1. Ordered Debugging Workflow (Avoid Fixing the Wrong Layer)

1. Record the actual `GET path` **at Tomcat** after ingress rewrites, HTTP method, `Accept`, and status.
2. List **Servlet URL mappings** for `DispatcherServlet` and Jersey; see if requests fall into Jersey `/*` unintentionally.
3. If routed to Jersey: inspect `ResourceConfig` registrations, `@ApplicationPath`, `spring.jersey.application-path` override, JAX-RS methods/media types, and Jersey exception mappers.
4. If routed to MVC: inspect `@GetMapping`, `WelcomePageHandlerMapping`, `ResourceHttpRequestHandler`, static locations, `spring.web.resources.add-mappings`, and `spring.mvc.static-path-pattern`.
5. If using Jersey Filter: inspect `spring.jersey.type=filter`, filter order, URL pattern, `FILTER_FORWARD_ON_404`, and the bodyless 404 condition.
6. Compare local `curl -i` against the public gateway URL; if different, inspect proxy rewrites/caching.
7. Test `/api/hello`, `/mvc/hello`, `/assets/site.css`, `/`, and specific 404 paths.
8. Verify security/CORS/CSRF per route, especially whether API endpoints lack Spring Security protection or assets return 401.
9. Test the packaged build via `mvn clean package` then `java -jar`, not just dev mode.
10. Lock in regression tests before migrating URL bases or switching Jersey Servlet ↔ Filter.

## 13. Anti-Patterns to Avoid

**Anti-pattern 1 — Jersey `/*` then raising MVC controller order.** The Servlet container already routed to Jersey; MVC `@Order`/`@GetMapping` cannot reclaim it. Fix Jersey's mapping.

**Anti-pattern 2 — Letting Jersey and MVC both claim `/api/hello` and expecting "the framework will pick right."** Servlet/Filter runs first, handler routing second. Define clear API owners; during migration, define fallback policies and tests.

**Anti-pattern 3 — Enabling `server.servlet.register-default-servlet=true` as a silver bullet.** The default servlet cannot beat Jersey `/*`. It can create file exposure/registration issues. Use only when architecture requires Servlet fallback and you understand the consequences.

**Anti-pattern 4 — Creating a custom `ServletRegistrationBean<ServletContainer>` while forgetting Boot auto-registers Jersey.** Causes duplicate mappings or two instances. Prefer `@ApplicationPath`/properties first; override registration only for well-understood requirements.

**Anti-pattern 5 — Adding `@EnableWebMvc` just to fix a static 404.** Boot MVC resource configuration gets overridden; identify whether the 404 comes from Jersey or MVC before taking over all MVC config.

**Anti-pattern 6 — Mixing `javax.ws.rs.*` and `jakarta.ws.rs.*`.** Spring Boot 3.5/Jersey 3.x uses the Jakarta namespace; Jersey 2.x/Boot 2.x code snippets may not even compile cleanly.

**Anti-pattern 7 — Thinking `spring.mvc.static-path-pattern=/assets/**` pulls files from Jersey back to MVC.** This property only adjusts static handler URL mappings **once the request enters `DispatcherServlet`**.

**Anti-pattern 8 — Enabling Filter fallback while forgetting Jersey's 404 response body.** `FILTER_FORWARD_ON_404` only forwards when the contract conditions hold; a custom `ExceptionMapper` can prevent fallback.

**Anti-pattern 9 — Exposing private documents under `classpath:/static/`.** The static handler serves public static assets according to routing/security; files with secrets need dedicated storage and authorization.

**Anti-pattern 10 — Testing controllers solely with Mockito/standalone MockMvc and assuming servlet routes work.** This is a Servlet container URL routing concern; run integration tests against embedded Tomcat/JAR and through any proxy.

## 14. Deployment and Upgrade Checklist

| Check | Passing Criterion |
| --- | --- |
| Architecture | Clear reason for choosing Jersey over MVC or running both together |
| Namespace | Jersey Servlet is scoped (e.g., `/api/*`) or Filter fallback has a formal contract |
| MVC | `DispatcherServlet` mapping remains correct (usually `/`), not hijacked by Jersey `/*` |
| JAX-RS | Single `ResourceConfig` registers `@Path`/providers accurately; `@ApplicationPath`/property consistent |
| Static | HTML/CSS/JS packaged in JAR classpath at proper locations and requested at proper public paths |
| Welcome | `GET /` returns `index.html` or MVC controller as designed |
| 404 semantics | Jersey 404, MVC missing handler, and MVC static `NoResourceFound` are distinguished |
| Filter fallback | `spring.jersey.type=filter` + `FILTER_FORWARD_ON_404` tested for bodyless 404s; no assumption that all errors forward |
| Security | Servlet filters protect both Jersey and MVC APIs; allowed asset paths and Actuator declared |
| Exceptions | Jersey `ExceptionMapper` and MVC `@ControllerAdvice` are not confused as one pipeline |
| CORS/CSRF | Preflight, authentication, and cross-origin tested across all URL namespaces |
| Proxy | Public path, backend URI, context path, and forwarded prefix align |
| Startup | No duplicate servlet/filter registrations, no mapping conflicts |
| Testing | `@SpringBootTest(RANDOM_PORT)` and `java -jar` verify Jersey + MVC + static + 404 |
| Operations | Logs/metrics, readiness, patch management, and zero-route-breakage rollouts in place |

A clear namespace architecture is usually easier to maintain than Filter fallback when route counts grow or strict security auditing is needed. Still, Filter fallback remains useful for phased endpoint migrations between Jersey and MVC, provided fallback semantics and test coverage are designed upfront.

## 15. Self-Check Questions

1. Why is a Jersey class with `@Path("/hello")` not a Spring MVC `@RestController`?
2. Are `DispatcherServlet` and `ResourceHttpRequestHandler` at the same level inside the Servlet container?
3. In Servlet mapping, how do `/*` and `/` differ?
4. When Jersey defaults to `/*`, why can `GET /assets/site.css` return 404 even though the file exists in `static/assets`?
5. How do you configure the Jersey Servlet to receive `/api/*` instead of `/*`?
6. Does `spring.jersey.application-path` override `@ApplicationPath`?
7. With Jersey at `/api/*` and MVC at `/`, who handles `GET /mvc/hello`?
8. In the example, what is the URL for `src/main/resources/static/assets/site.css`?
9. If you set `spring.mvc.static-path-pattern=/resources/**` while keeping the file in the same place, what does the URL become?
10. Do `spring.web.resources.static-locations` and `spring.mvc.static-path-pattern` change the same thing?
11. Why doesn't `server.servlet.register-default-servlet=true` automatically fix Jersey `/*`?
12. How does `spring.jersey.type=filter` differ from `servlet`?
13. What condition must Jersey's response satisfy for `ServletProperties.FILTER_FORWARD_ON_404`?
14. If Jersey returns a 404 with a JSON body, is MVC guaranteed to be called when Filter mode enables fallback?
15. In Spring Boot MVC, which class serves static files and at which routing step does it sit?
16. How can `@EnableWebMvc` cause Boot's default static support to disappear?
17. Why does MVC's `@ControllerAdvice` not automatically handle Jersey resource exceptions?
18. How do `securityMatcher("/api/**")` and Jersey Servlet path `/api/*` relate? Do they automatically guarantee the endpoint is protected?
19. Why is `@SpringBootTest(RANDOM_PORT)` more trustworthy than standalone MockMvc for this scenario?
20. If `/api/hello` works yet `/actuator/health` returns 404 after adding Jersey, which layer do you check first?
21. When switching Jersey servlet to Filter, why might `/api/hello` change to `/hello` in the lab variant?
22. Should private user uploads be placed in `src/main/resources/static` so Jersey checks permissions first?
23. When a reverse proxy rewrites public URLs, which paths should you record for debugging?
24. Are all Jersey `@GET` methods discovered by Spring MVC's `@GetMapping`?
25. Can `GET /api/not-found` ever automatically "try" `DispatcherServlet` if Jersey was selected via Servlet `/api/*`?

**Short answers:** (1) Two programming models, two runtimes. (2) No, the resource handler sits **inside** MVC `DispatcherServlet`. (3) Broad path-prefix matching vs. default servlet mapping. (4) The Servlet container selects Jersey so MVC's static handler never runs. (5) `@ApplicationPath("/api")` or `spring.jersey.application-path=/api`. (6) Yes. (7) MVC `DispatcherServlet`. (8) `/assets/site.css`. (9) `/resources/assets/site.css`. (10) No: locations vs. URL pattern. (11) It does not beat the `/*` prefix mapping. (12) Runs in the Filter chain and can forward down to a Servlet. (13) Jersey 404 **without an entity body**. (14) No. (15) `ResourceHttpRequestHandler` once `DispatcherServlet` is selected. (16) Disables many MVC auto-config defaults when taking manual control. (17) Jersey uses `ExceptionMapper`. (18) The security filter chain must match properly and define an authorization policy. (19) Tests real Servlet mappings. (20) Check Jersey `/*` and Actuator/MVC mappings. (21) The `@ApplicationPath("/api")` base was removed. (22) No, use authorized storage. (23) Public URI, upstream URI, servlet context path, Jersey base path, and proxy prefix. (24) No. (25) No, unless you design **Filter** with fallback; a Servlet does not auto-retry another Servlet.

## 16. Official Reference Sources

- **Spring Boot 3.5 — Servlet Web Applications**, Spring MVC static content, welcome page, JAX-RS/Jersey auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- **Spring Boot 3.5 — How-to: Jersey**, using Jersey alongside another web framework and security `setStatusOverSendError`: https://docs.spring.io/spring-boot/3.5/how-to/jersey.html
- **Spring Boot 3.5 — Common Application Properties**, `spring.jersey.application-path`, `spring.jersey.type`, `spring.jersey.filter.order`, `spring.mvc.static-path-pattern`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- **Jakarta Servlet 6.0 Specification, Chapter 12**, URL mapping: exact, path-prefix, extension, and default: https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html
- **Jersey 3.x ServletProperties API**, `FILTER_FORWARD_ON_404`/`FILTER_STATIC_CONTENT_REGEX`: https://eclipse-ee4j.github.io/jersey.github.io/apidocs/latest3x/jersey/org/glassfish/jersey/servlet/ServletProperties.html
- **Spring Framework MVC static resources**, resource handlers and pipeline: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html
- **Spring Framework DispatcherServlet**, request processing/HandlerMapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html
- **Spring Boot 3.5.16 System Requirements**, Java 17+ and Tomcat Servlet 6.0: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- **Spring Boot 3.5.16 release announcement**, ending OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/