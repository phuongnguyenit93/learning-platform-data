# Static resource serving mechanism in Spring MVC and Spring WebFlux

**Scope:** Spring Boot 3.5.x, Java 17+, Spring MVC (Servlet stack) and Spring WebFlux (reactive stack). This lesson explains **how HTTP requests are mapped to CSS, JavaScript, images, fonts, static HTML, and WebJars**, how to configure storage locations/URLs, caching, the resource chain, security, and how to diagnose issues when packaging and running a JAR.

## 1. What is a static resource?

A **static resource** is a pre-existing file that the server sends to an HTTP client without dynamically building a response from business data on every request. Examples:

- `index.html`: an HTML page that can be sent directly;
- `css/site.css`: stylesheet;
- `js/site.js`: JavaScript;
- `images/logo.svg`, `images/banner.png`: images;
- `fonts/app.woff2`: font;
- JavaScript/CSS libraries packaged as a WebJar.

The term “static” describes **how the server retrieves the content from a resource**, not that JavaScript won't run in the browser. A static HTML file can still use `fetch()` to call a REST API for dynamic data.

Comparison of three commonly confused content sources:

| Source | Example directory | Processing mechanism | Suitable for |
| --- | --- | --- | --- |
| **Static resource** | `src/main/resources/static/` | Resource handler locates the file and writes the HTTP response | CSS, JS, images, HTML not needing server-side rendering |
| **Server-side template** | `src/main/resources/templates/` | A view engine like Thymeleaf/FreeMarker renders a model into HTML | UIs with server-rendered data |
| **REST/controller endpoint** | Java `@RestController`, `@GetMapping` | Java handler processes the request and creates the response | JSON, business operations, dynamic content |

Do not place secrets, private keys, configuration files containing credentials, or per-user authorized data inside public static directories. By default, static resources are designed to be accessible via URL unless blocked by a security layer.

## 2. HTTP processing flow: similar in concept, different in handler

Conceptually, when a browser requests `GET /css/site.css`:

1. The HTTP server receives the request.
2. The routing/handler mapping system checks whether the path matches a controller or a static resource mapping.
3. When matching the static resource handler, the framework extracts the relative path (for example `css/site.css`).
4. The framework searches for the resource in permitted locations, passing through `ResourceResolver` instances if a resource chain is configured.
5. If found, the framework selects an appropriate media type, applies cache/conditional headers, and sends the file contents.
6. If no valid file exists, it returns **404** via the application's error-handling mechanism; some requests may be blocked earlier with **401/403** at the security layer.

~~~text
Browser: GET /css/site.css
           │
           ▼
  HTTP server (Tomcat/Jetty/Netty...)
           │
      Handler mapping
           │
           ├── Specific Controller/RouterFunction match ─► application handler
           │
           └── Static mapping / ** (default) ───────────► resource handler
                                                             │
                                                ResourceResolver / Transformer
                                                             │
                                                   classpath:/static/
                                                   classpath:/public/
                                                   classpath:/resources/
                                                   classpath:/META-INF/resources/
                                                             │
                                         ┌───────────────────┴─────────────────┐
                                         ▼                                     ▼
                                   Valid file found                      No file found
                                   200 / 304 / ...                            404
~~~

**In Spring MVC:** requests flow through `DispatcherServlet`; the static resource handler is `org.springframework.web.servlet.resource.ResourceHttpRequestHandler`. Resource sources can reside on the classpath and, in suitable Servlet applications, at the `ServletContext` root. Static serving is normally handled by the Spring MVC resource handler; do not rely on the container's “default servlet” to serve them instead.

**In Spring WebFlux:** requests flow through the reactive `DispatcherHandler`; the corresponding handler is `org.springframework.web.reactive.resource.ResourceWebHandler`. WebFlux does not depend on the Servlet API, so it neither uses the servlet-context root in the MVC manner nor treats `src/main/webapp` as a static location for a reactive app.

The static handler **is not a Java controller you are required to write yourself**. Spring Boot provides auto-configuration that creates the default resource handlers when the application is configured as an appropriate web application.

### Why can a URL be handled by a controller instead of a file?

The default static mapping is broad: `/**`. Controller routes with appropriate priority ordering can still handle their own URLs; the static mapping acts to serve remaining resources. Consequently, `@GetMapping("/api/ping")` is not “swallowed” by the `/**` resource handler in a normal Boot setup.

Conversely, when no controller exists for `/some-path`, the broad static resource mapping may catch the request and fail to find a file. **Spring MVC** may then throw `NoResourceFoundException` instead of `NoHandlerFoundException`. Different exceptions do not necessarily mean different statuses: it is usually still HTTP 404. If you want a clean separation for API routing, you can narrow the static pattern to `/assets/**`.

## 3. The four default static locations in Spring Boot

Spring Boot automatically searches for resources in the following classpath locations (ordered as in the default configuration list):

1. `classpath:/META-INF/resources/`
2. `classpath:/resources/`
3. `classpath:/static/`
4. `classpath:/public/`

In standard Maven or Gradle projects, these directories are usually created under `src/main/resources`. For example:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/demo/DemoApplication.java
    └── resources/
        ├── static/
        │   ├── index.html
        │   ├── css/site.css
        │   ├── js/site.js
        │   └── images/logo.svg
        ├── public/
        │   └── robots.txt
        └── templates/
            └── dashboard.html
~~~

With the default `/**` URL pattern and the app running at the HTTP root:

| File on the classpath | HTTP URL | Served directly? |
| --- | --- | --- |
| `static/index.html` | `/index.html`, and usually `/` via welcome page | Yes |
| `static/css/site.css` | `/css/site.css` | Yes |
| `static/js/site.js` | `/js/site.js` | Yes |
| `static/images/logo.svg` | `/images/logo.svg` | Yes |
| `public/robots.txt` | `/robots.txt` | Yes |
| `templates/dashboard.html` | `/dashboard.html` | **No**, not merely because it is in templates; requires an appropriate view controller/renderer |

**The `static` directory does not appear in the URL.** `/static/css/site.css` usually returns 404 because the framework looks for a file with relative path `static/css/site.css` under `classpath:/static/`, resulting in a duplicated “static”.

If the same relative path exists in multiple locations simultaneously (for instance `static/logo.svg` and `public/logo.svg`), file selection depends on the **order of locations**; avoid confusing duplicate names rather than relying on incidental packaging results.

**Packaging differences to keep in mind:**
- For a Spring Boot **executable JAR**, placing files in `src/main/resources/static/` is the standard approach; when packaged, they appear on the JAR's classpath (typically in `BOOT-INF/classes/static/`).
- `src/main/webapp` is the traditional layout for **WAR/Servlet** applications; in a JAR-based Spring Boot application it may be ignored, and WebFlux does not support WAR servlet conventions. Do not use `src/main/webapp` for static assets in a JAR application.
- `META-INF/resources` can reside inside dependency JARs, which is convenient for frontend resources or WebJars; it does not mean all files in dependencies are copied into `static`.

## 4. URL pattern and resource location are two distinct concepts

A **URL pattern** is the path an HTTP client uses to request a resource. A **resource location** is where the server looks for the file. They are two consecutive mappings.

Example MVC configuration:

~~~properties
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/site-assets/
~~~

With the file `src/main/resources/site-assets/css/app.css`, the URL becomes **`/assets/css/app.css`**, while `/css/app.css` is no longer routed by that static mapping. Having no `assets` directory on disk is completely normal: `/assets/**` is purely a **URL prefix**.

Direct comparison table:

| Component | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Static handler | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Default URL pattern | `/**` | `/**` |
| URL pattern property | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Locations property | `spring.web.resources.static-locations` | `spring.web.resources.static-locations` |
| Programmatic extension | `WebMvcConfigurer#addResourceHandlers` | `WebFluxConfigurer#addResourceHandlers` |
| Additional static from servlet root | Yes, in suitable MVC/Servlet apps | Does not use `ServletContext` root |
| WebJars integration | Supported | Supported |

**Note on the shared property:** `spring.web.resources.static-locations` **replaces the default list**, rather than appending to it. If you only declare `classpath:/site-assets/`, files previously in `classpath:/static/` may no longer be served as before (in Servlet MVC, the servlet-context root has separate handling conditions). To keep multiple locations, declare all of them:

~~~properties
spring.web.resources.static-locations=classpath:/site-assets/,classpath:/static/,classpath:/public/
~~~

If the application uses multiple profiles, verify the **effective configuration** after properties from environment files, environment variables, command-line options, and profiles are applied; sometimes a production profile property overrides all locations.

### Base path, context path, and reverse proxies

An MVC application configured with `server.servlet.context-path=/shop` exposes URLs such as `/shop/css/site.css`. In WebFlux, `spring.webflux.base-path=/shop` can be used in the reactive stack. This is the **application base path**, not a resource directory name.

If an HTML page uses an absolute link `href="/css/site.css"`, the browser looks at the **domain root**, which can break when the app lives under `/shop` or behind a reverse proxy adding a prefix. A relative link `href="./css/site.css"` inside `/shop/index.html` can work better; server-side template applications should generate URLs with the context path. Always verify proxy forwarded headers and actual deployment routing instead of randomly renaming files.

## 5. Spring MVC: configuration and handler

In an application with `spring-boot-starter-web`, Boot configures MVC and the static resource handler. For ordinary needs, **simply place files in `src/main/resources/static/`** rather than writing a controller that calls `Files.readAllBytes(...)`.

If you need to add a custom directory while **keeping Boot's auto-configuration**, register a `WebMvcConfigurer`:

**File `src/main/java/com/example/demo/ExtraMvcAssets.java`**, in the **MVC project**:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraMvcAssets implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/extra/**")
                .addResourceLocations("classpath:/custom-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
    }
}
~~~

If you have `src/main/resources/custom-assets/manual.pdf`, the URL `/extra/manual.pdf` maps to that file. `setCacheControl` configures caching for the newly registered mapping without needing to apply it to all static resources. Directory locations should have a trailing `/` so relative paths resolve properly.

**Do not add `@EnableWebMvc` to the configuration above** if you want to preserve Spring Boot MVC auto-configuration. That annotation hands full MVC configuration control to your application and can disable Boot's default mappings or customizations. If you require complete manual control, you must register all configurations you depend on yourself.

**Common pitfall:** MVC's `ResourceHandlerRegistry` lives in package `org.springframework.web.servlet.config.annotation`; it is not the class with the same name in the reactive stack. Mixing the wrong import will either fail to compile or fail to take effect.

## 6. Spring WebFlux: same problem, non-blocking model

A Spring Boot WebFlux application typically uses `spring-boot-starter-webflux` and a reactive HTTP runtime, commonly Reactor Netty. When a client requests `GET /css/site.css`, `DispatcherHandler`/handler mappings route to `ResourceWebHandler`. The file is served via Spring's `Resource` abstraction and reactive response handling.

The default static locations and URL patterns are conceptually **similar to MVC**. The main differences are the **web runtime type**, configuration APIs, reactive response handling, and the fact that WebFlux **has no servlet context root or default servlet**.

Example changing the URL prefix in **WebFlux**:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

With `src/main/resources/static/css/site.css`, clients use `/assets/css/site.css`. The MVC-specific property `spring.mvc.static-path-pattern` will not control static routing in a WebFlux app.

Adding a custom directory in WebFlux via `WebFluxConfigurer`:

**File `src/main/java/com/example/demo/ExtraFluxAssets.java`**, in the **WebFlux project**:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraFluxAssets implements WebFluxConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/extra/**")
                .addResourceLocations("classpath:/custom-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
    }
}
~~~

Just like in MVC, `custom-assets/manual.pdf` is served at `/extra/manual.pdf` if security permits. Do not put **both `ExtraMvcAssets` and `ExtraFluxAssets` into a single project just for “compatibility”**; choose the right web stack.

If a project declares **both** `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally prioritizes the **Servlet/MVC application type**; the WebFlux dependency is sometimes only present for `WebClient`. Check the dependency tree and application type; do not assume “WebFlux is running” solely because code uses `Mono` or the WebFlux dependency is present.

## 7. Runnable example: same static files for two separate applications

Create **two independent project directories**: `mvc-static-demo` and `webflux-static-demo`. Each project has a `pom.xml` with exactly **one** web starter (MVC or WebFlux), using JDK 17+, Maven, and Spring Boot 3.5.0. The HTML/CSS/JS files are identical; the Java main class and controller are nearly identical. No database and no Thymeleaf are needed.

Directory tree for **each** project:

~~~text
<project>/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/demo/
   │  ├─ DemoApplication.java
   │  └─ PingController.java
   └─ resources/static/
      ├─ index.html
      ├─ css/site.css
      └─ js/site.js
~~~

### 7.1. `pom.xml` for the MVC project

~~~xml
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
  <artifactId>mvc-static-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

### 7.2. `pom.xml` for the WebFlux project

~~~xml
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
  <artifactId>webflux-static-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
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

Use the separate `pom.xml` matching each project; **do not** combine the two dependencies just to test the example. For newer Spring Boot versions, check Java requirements and update the parent version and corresponding dependencies accordingly.

### 7.3. Shared Java main file

Place this in **both projects** at `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.4. API test controller — pick the one for your project

Use the following **`PingController.java`** file in the **MVC project**:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public PingResponse ping() {
        return new PingResponse("pong");
    }

    public record PingResponse(String message) {}
}
~~~

Use the following **`PingController.java`** file in the **WebFlux project**:

~~~java
package com.example.demo;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/api/ping")
    public Mono<PingResponse> ping() {
        return Mono.just(new PingResponse("pong"));
    }

    public record PingResponse(String message) {}
}
~~~

Both controllers demonstrate that **the `/api/ping` URL is handled by the application**, while CSS/JS/HTML are served by the resource handler. No controller like `@GetMapping("/css/site.css")` is required.

### 7.5. Three shared static files

**`src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spring static resources</title>
  <link rel="stylesheet" href="./css/site.css">
  <script defer src="./js/site.js"></script>
</head>
<body>
  <main>
    <h1>Static resources work</h1>
    <p id="status">Calling /api/ping...</p>
  </main>
</body>
</html>
~~~

**`src/main/resources/static/css/site.css`:**

~~~css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem;
  line-height: 1.5;
}
h1 {
  color: #245c8a;
}
~~~

**`src/main/resources/static/js/site.js`:**

~~~javascript
document.addEventListener("DOMContentLoaded", async () => {
  const status = document.querySelector("#status");
  try {
    const response = await fetch("./api/ping");
    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    const data = await response.json();
    status.textContent = "API returned: " + data.message;
  } catch (error) {
    status.textContent = "Failed to call API: " + error.message;
  }
});
~~~

Writing relative URLs for CSS, JS, and the API in this example assumes **`index.html` is at the root or a consistent base path**. If you move index into a deeper sub-route, redesign the relative URLs accordingly; when behind a proxy prefix, verify using the browser's Network tab.

### 7.6. Running and verifying

In **one** of the two project directories:

~~~bash
java -version
mvn spring-boot:run
~~~

Wait for the application to open the default port **8080** (unless configured otherwise). Open `http://localhost:8080/` in a browser: the page shows the heading “Static resources work”, styled by CSS, and JavaScript updates the status to **“API returned: pong”** when the API request succeeds.

In another terminal:

~~~bash
curl -i http://localhost:8080/index.html
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/site.js
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/not-exists.css
~~~

Verifiable expectations:
- `/index.html`: **200 OK**, body starts with `<!doctype html>`;
- `/css/site.css`: **200 OK**, CSS-appropriate `Content-Type`;
- `/js/site.js`: **200 OK**, JavaScript-appropriate `Content-Type`;
- `/api/ping`: **200 OK** and exact JSON body **`{"message":"pong"}`**;
- `/not-exists.css`: **404 Not Found** in the default configuration.

In real environments, additional headers (Date, cache, server, transfer encoding) and 404 error body formats may vary depending on the container, Boot configuration, and security filters. **Do not** assert the entire HTTP response byte-for-byte without running the specific stack.

To verify whether files were packaged into the JAR:

~~~bash
mvn -q clean package
jar tf target/mvc-static-demo-0.0.1-SNAPSHOT.jar
~~~

In the **WebFlux project**, change the JAR name to `webflux-static-demo-0.0.1-SNAPSHOT.jar`. Look for the entries `BOOT-INF/classes/static/index.html`, `.../css/site.css`, and `.../js/site.js`. If they are missing, the problem lies in the resource packaging step before even examining handler mappings.

## 8. Configuration examples: changing the URL prefix, changing resource locations

**Case A — change only the URL prefix, keep files in `static`:**

`application.properties` in the MVC project:

~~~properties
spring.mvc.static-path-pattern=/assets/**
~~~

The equivalent configuration for the same goal in the WebFlux project:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

Then `static/css/site.css` has the URL `/assets/css/site.css`. Because HTML is also static, the sensible direct path to test is `/assets/index.html`; do not assume the root URL `/` continues behaving identically after changing the pattern. With `index.html` at `/assets/index.html`, the relative link `./css/site.css` will correctly resolve to `/assets/css/site.css`. In the JavaScript example, `./api/ping` would now become `/assets/api/ping` (**wrong**); to call the `/api/ping` API, update how the API URL is constructed for the active route. Distinguishing the **static URL prefix** from the **API endpoint path** is crucial.

**Case B — change where files are stored, keep the default URL:**

~~~properties
spring.web.resources.static-locations=classpath:/frontend/
~~~

Place the file at `src/main/resources/frontend/css/site.css` and request `/css/site.css`. The new location **replaces** the default list; `src/main/resources/static/css/site.css` is no longer scanned at that default location.

**Case C — add a dedicated mapping instead of replacing everything:**

Keep the default static files and add `src/main/resources/custom-assets/manual.pdf`. Use `ExtraMvcAssets` (MVC) or `ExtraFluxAssets` (WebFlux) from sections 5–6 to expose the URL `/extra/manual.pdf`; there is no need to change the global `spring.web.resources.static-locations`.

**Case D — disable Boot-provided static mappings (when genuinely needed):**

~~~properties
spring.web.resources.add-mappings=false
~~~

Once disabled, files present only in `static` will no longer be served by Boot's default mapping. If you declare other custom resource handlers or routers, behavior is governed by your custom configuration. Pay special attention to this in API-only apps or applications upgraded from self-managed MVC/WebFlux configurations.

## 9. Caching, conditional GET, resource chain, and cache busting

Static content is typically read very frequently. A CDN or browser cache reduces app load and latency, yet incorrect caching can leave users with stale CSS/JS. Distinguish between **HTTP caching** and **Spring's internal resource chain**.

### 9.1. Cache-Control and Last-Modified

Example general cache configuration for the Boot resource handler:

~~~properties
spring.web.resources.cache.period=3600
spring.web.resources.cache.use-last-modified=true
~~~

`3600` here is in **seconds**, equivalent to 1 hour. With proper configuration, responses can include `Cache-Control: max-age=3600`. If the resource has a determinable modification timestamp, the handler can send `Last-Modified`. Clients use a conditional `If-Modified-Since` request; when the resource is unchanged, the server can return **304 Not Modified** without sending the body again.

Example inspecting headers:

~~~bash
curl -I http://localhost:8080/css/site.css
~~~

To test conditional GET reliably, take the exact `Last-Modified` value returned by the server and send it back in `If-Modified-Since`. If subsequent calls return 304, the browser/proxy can reuse its stored copy. **Do not assume every response includes an ETag**: Spring can serve `Last-Modified` without automatically generating an ETag; ETags require appropriate configuration, handlers, or filters.

Some deployments have a reverse proxy or CDN, so final headers seen by the client may differ from what the resource handler sets. Verify with an actual HTTP client rather than reading `application.properties` alone.

### 9.2. Cache-busting: changing the URL when content changes

Suppose HTML points to `/css/site.css` and browsers cache it for 1 year. After deploying new CSS, because the URL is unchanged, browsers may continue using the old file. **Cache busting** solves this by changing the URL whenever the content changes:

~~~text
/css/site.css
        ↓ content-based versioning
/css/site-<content-hash>.css
~~~

Spring Boot supports the resource chain and version strategies:

~~~properties
spring.web.resources.chain.strategy.content.enabled=true
spring.web.resources.chain.strategy.content.paths=/**
~~~

This is a **strategy configuration**. The framework can serve content-versioned paths when versioned links/URLs are generated properly. **It does not automatically rewrite every hardcoded path string in static `index.html`.** With Spring MVC + Thymeleaf/FreeMarker, Spring Boot integrates URL rewriting in view templates; with JSP or other stacks, you must configure or use `ResourceUrlProvider` accordingly.

In **WebFlux**, do not assume static HTML will automatically rewrite URLs through the reactive `ResourceResolver` chain. If an application needs hashed filenames on the frontend, a pragmatic approach is having a bundler (Vite/Webpack…) produce hashed files and generate `index.html` along with matching manifest/URLs during the build step.

For JavaScript module imports and dynamic imports, **filename-changing** strategies require testing because module loaders may reference internal paths. Spring supports a **fixed version strategy** (version in the path) as an alternative. Choose a strategy by asset type rather than blindly applying content hashes to every file.

**Practical caching recommendation:** For assets whose **URL changes whenever content changes**, you can set long cache lifetimes and use the `immutable` directive where appropriate. For the `index.html` entrypoint that keeps a fixed URL, choose a **short or revalidating** policy so browsers quickly pick up new CSS/JS URLs. Setting long cache lifetimes across `/**`, including the HTML entrypoint, easily causes “stale HTML, new assets” issues during frontend deployments.

### 9.3. What do ResourceResolver and ResourceTransformer do?

A resource chain can include steps such as:
- `PathResourceResolver`: locates and verifies resources in permitted locations;
- `VersionResourceResolver`: locates/validates versions in URLs;
- resolvers for pre-compressed files (when the feature and corresponding resources are enabled);
- transformers to modify content or links in specific scenarios.

This pipeline is **not** meant for running dynamic business logic or validating business data. Enabling the resource chain does not automatically guarantee gzip/Brotli on every response; compression depends on pre-compressed files, `Accept-Encoding`, and compatible settings. Nor does the resource handler automatically sanitize arbitrary `.svg` or uploaded files into safe content.

## 10. WebJars and resources in dependencies

A **WebJar** packages JavaScript/CSS into a JAR using a web resource layout. Spring Boot provides default access support under the `/webjars/**` prefix when the proper dependency and resource layout are present. Typical URLs include a **version**:

~~~text
/webjars/<library-name>/<version>/<file-path>
~~~

Some version-discovery mechanisms for “versionless” paths require adding a dependency like `webjars-locator-lite`; do not assume every WebJar or every Spring Boot version automatically supports versionless URLs.

**Choosing:** WebJars are useful when frontend assets are managed as Java app dependencies. For large frontends built with Vite/Webpack, placing the build output in `static` or serving from a CDN is usually simpler. Do not copy raw frontend sources or the entire `node_modules` directory onto the classpath, accidentally exposing every file publicly.

## 11. Security and the boundary between public and private resources

By design, static handlers serve **files from a server-trusted list of locations**; do not use them as an API to read arbitrary files from client-supplied paths.

- Place only **public** content in static locations. Files whose names contain tokens, credential configs, secret-containing source maps, `.env` files, and DB dumps must never be public.
- With Spring Security, you may need to **allow GET access** to static assets like `/css/**`, `/js/**`, `/images/**`, favicon, `/`, and `/index.html`. MVC's `authorizeHttpRequests().requestMatchers(...).permitAll()` and WebFlux's `authorizeExchange().pathMatchers(...).permitAll()` are **two different** APIs. Keep rules tight around public paths; do not open all of `/**` just to fix a CSS 403 error.
- `permitAll` is an authorization decision, distinct from bypassing the security filter chain entirely. When ignoring filters, you may also omit security headers and other controls added by the chain.
- Do not map entire external filesystem directories using `file:/` purely for development convenience. If external static files are truly needed, restrict the served directory, permissions, and deployment setup; never allow users to specify arbitrary filesystem paths.
- **User-uploaded** files require scanning/validation, authorization checks, separate storage names, `Content-Type`/`Content-Disposition` policies, and possibly object storage/CDN. Never treat them as public static files by default.
- Third-party controlled HTML/SVG data can carry active content that executes in browsers. Verify CSP policies, `X-Content-Type-Options`, and embedding methods; “static file” does not mean “harmless”.
- If an SPA page is blocked by login, returning `index.html` for every 404 will not fix authentication failures; configure routes and security properly, keeping APIs returning clear error statuses.

## 12. SPAs, fallback routes, and the “blank page” bug

A Single Page Application (React/Vue/Angular…) usually consists of one `index.html`, many hashed assets, and a JavaScript router. When a browser navigates directly to `/orders/42`, it sends **GET /orders/42** to the server; if the server only has `/index.html`, the static handler will not automatically forward every URL to index.

To make SPA deep links work, you need a **conditional fallback** for frontend routes, for example under an `/app/**` prefix. Depending on the stack, you can use an MVC view controller/forward, a reactive router/filter, or reverse proxy rules. The fallback design should:
1. Not intercept `/api/**`, `/actuator/**`, or `/webjars/**`.
2. Not turn requests for `/assets/missing.js` or `/css/missing.css` into **HTTP 200 with HTML**, as the browser will report a MIME error and render a blank page.
3. Fall back only for frontend routes with appropriate HTTP methods—typically GET/HEAD—while checking the `Accept` header or route rules.
4. Verify asset locations and caching, especially newly hashed assets after deployment.

This is an **addition** to static resource handling, not a default behavior of `ResourceHttpRequestHandler` or `ResourceWebHandler`.

## 13. Common errors and how to verify

| Symptom | Likely cause | How to check / fix |
| --- | --- | --- |
| `GET /static/css/site.css` → 404 | Incorrectly included “static” in the URL | Use `/css/site.css` with the `/**` mapping |
| `GET /css/site.css` → 404 after prefix change | `spring.mvc.static-path-pattern` or `spring.webflux.static-path-pattern` changed | Use `/assets/css/site.css` or revert to the expected pattern |
| CSS/JS returns 404 when running JAR, works in IDE | Files are missing from the packaged classpath | Run `jar tf target/*.jar` and check `BOOT-INF/classes/static/` |
| Files in `src/main/webapp` inside an executable JAR | Directory is not treated as a static classpath location | Move to `src/main/resources/static` |
| CSS/JS returns **403** | Spring Security rules do not permit them | Check the exact matcher, prefix, HTTP method, and filter chain |
| CSS/JS returns **200 but Content-Type: text/html** | SPA fallback returns index instead of missing file | Exclude asset/API paths from fallback; verify files inside the JAR |
| Browser reports wrong MIME type, module fails to run | JS URL returns HTML/error; wrong MIME type | Check Network tab, response headers, and actual body |
| HTML loads but CSS/JS fail when deployed under `/shop` | Absolute links point to the wrong base path | Use context-aware URLs, check proxy prefixes |
| File placed in `templates` returns 404 at `/file.html` | Templates are not direct static resources | Add a view controller or move the file to `static` if appropriate |
| Custom `static-locations` makes old files disappear | Property **replaced** the default list | Explicitly list all desired locations |
| Custom MVC config breaks default mappings | `@EnableWebMvc` is present or auto-config was replaced | Remove `@EnableWebMvc` if you want Boot auto-config |
| WebFlux dependency present, custom WebFlux handler inactive | App is actually running MVC because web starter is also present | Inspect `pom.xml`, application type, and runtime logs |
| Stale CSS after deployment | Browser/CDN caches unchanged asset URL | Use hashed URLs, manage TTLs, and control HTML caching |
| “No static resource ...” on an API URL | MVC `/**` static mapping caught a path with no matching controller | Check URL/API mapping; consider a dedicated static path pattern |
| `GET /` does not show index | Wrong location, missing index, prioritized route, or pattern changed | Check `/index.html`, startup config, and route collisions |
| CSS-embedded image paths return 404 | `url(...)` in CSS is relative to the **CSS file's location** | Resolve URL from `/css/site.css`, e.g., `../images/logo.svg` |
| File exists on disk yet returns 404 | Local disk differs from classpath inside Docker/JAR | Verify resource is inside the image/JAR or an external location is mapped |
| Resource missing through CDN/proxy | Wrong path rewrite, cache, or upstream route | Compare direct app requests vs. proxied requests; inspect statuses/headers |

### Concise debugging workflow with sufficient evidence

1. **Separate URL from file path:** record the exact URL the browser calls and the file actually present in the package.
2. **Check HTTP status + Content-Type + body:** use `curl -i` and the Network tab; avoid guessing between 404 and 403.
3. **Check the stack:** is it actually MVC or WebFlux? Are both starters present? Which custom configs are active?
4. **Check effective properties:** static path pattern, static locations, `add-mappings`, context/base path, and security rules.
5. **Check the artifact:** locate the path under `BOOT-INF/classes` or the relevant dependency JAR.
6. **Check cache/CDN:** test a fresh URL, request the instance directly, and check `Last-Modified`/`Cache-Control` and stale HTML.
7. **Check controllers/routers/SPA fallback:** is a route intercepting the resource path or turning a 404 into a 200 HTML response?

## 14. Performance and production deployment

- Use response caching and a CDN under heavy asset traffic; Spring Boot's resource handler is convenient for small apps or UIs bundled inside the same JAR, while CDNs/object storage suit frontends needing independent scaling.
- Do not stream static files manually through a controller reading an `InputStream` without a specific reason. Resource handlers already handle response streaming, MIME types, caching, and standard HTTP mechanics.
- Enable compression at the container/proxy and use pre-compressed resources where appropriate; inspect actual `Content-Encoding`, `Vary: Accept-Encoding`, and cache rules.
- Frontend builds must ensure asset references in `index.html` point to the correct post-deploy versions. If assets are cached long-term, URLs must change when contents change.
- Do not add both MVC and WebFlux hoping to “serve static files faster”: throughput is usually governed by CDN/caching, file size, bandwidth, TLS, and cache hit ratio rather than making a reactive controller.
- Changing base-path or custom URL prefixes affects service worker scope, CSP, CORS, frontend routers, and client caches. Verify all of them when changing routes.
- When Spring Security or a reverse proxy is involved, test assets along the **exact browser request path**, not solely with unit tests calling the resource handler directly.

## 15. Self-check questions

1. Given `src/main/resources/static/css/site.css` in a default MVC project, which URL is right: `/css/site.css` or `/static/css/site.css`? Why?
2. Is `src/main/resources/templates/dashboard.html` automatically served at `/dashboard.html`? When should a template engine be used?
3. Name the two handlers for MVC and WebFlux; why do they have different `ResourceHandlerRegistry` import packages?
4. With `spring.web.resources.static-locations=classpath:/frontend/`, will a file existing only in `classpath:/static/` still be scanned via the default list?
5. With `spring.webflux.static-path-pattern=/assets/**` and the file `static/js/site.js`, what is the resource URL?
6. If a controller has `@GetMapping("/api/ping")` under default MVC, why doesn't the `/**` static mapping necessarily take over this route?
7. The browser receives `200 text/html` for `/js/app.js`. Why does the JavaScript file still fail to run?
8. Why shouldn't an unversioned `index.html` be cached with `max-age=31536000` in an SPA with hashed JS/CSS?
9. Does enabling content versioning automatically rewrite every hardcoded path inside a static HTML file?
10. An app is deployed at `/shop`, yet HTML points to `/css/site.css`. What URL does the browser actually request, and how should the link be redesigned?
11. For a Spring Boot executable JAR, why is `src/main/webapp` not where static assets should be placed?
12. When `/css/site.css` returns 403, what check makes more sense than increasing `spring.web.resources.cache.period`?

**Key answers:** (1) `/css/site.css` because `static` is a resource location; (2) no, templates require rendering; (3) MVC `ResourceHttpRequestHandler`, WebFlux `ResourceWebHandler`, each stack has its own config package; (4) not in the replaced list, unless another location is configured separately; (5) `/assets/js/site.js`; (6) handler mappings are distinct and ordered by precedence; (7) SPA fallback/response returned the wrong MIME type; (8) stale HTML won't update to the newly hashed asset URLs; (9) no; (10) it usually requests domain root `/css/site.css` missing the prefix, needing context-aware links; (11) files there are not packaged according to executable JAR conventions; (12) check Spring Security authorization/filter chain.

## 16. Official documentation

The following documentation helps verify details when upgrading Spring Boot/Spring Framework. Examples and properties in this lesson are written in the context of **Spring Boot 3.5.x**; when upgrading major versions, check whether APIs and dependencies have changed.

- Spring Boot 3.5, Servlet static content, cache busting, and welcome page: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, WebFlux static content and URL patterns: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, application properties reference (`spring.web.resources.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework, MVC static resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Framework, WebFlux static resources: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework, HTTP caching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
