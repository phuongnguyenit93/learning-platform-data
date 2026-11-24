# ResourceHandler, Static Resource Locations, and Mapping Precedence in Spring MVC

## 1. The Practical Problem

A Spring Boot project contains these files:

```text
src/main/resources/static/css/site.css
src/main/resources/static/images/logo.svg
src/main/resources/templates/home.html
src/main/resources/manuals/intro.txt
```

The browser requests `GET /css/site.css`: Spring MVC needs to locate the right file and return CSS. Yet `GET /manuals/intro.txt` normally does not work if you only drop a `manuals` folder onto the classpath. Meanwhile, `GET /products/42` should invoke a controller even though Spring Boot's default static resource handler uses the URL pattern `/**`.

From those three scenarios, this lesson answers:

1. **What is a ResourceHandler?** A URL pattern mapped to `ResourceHttpRequestHandler` to locate and serve static files.
2. **Where must resources live?** Boot's default folders, classpath locations, servlet context paths, JAR/WAR packaging, and custom-configured locations.
3. **How does mapping precedence work?** Controller `HandlerMapping`s normally take precedence over the default resource handler; within resource mappings, more specific patterns are chosen over broad wildcards.
4. **When should you use `WebMvcConfigurer#addResourceHandlers`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, or `spring.web.resources.add-mappings`?**
5. **How do you use caching, versioned URLs, conditional GET, content types, and security?**
6. **How do you test it?** Build a Spring Boot 3 / Java 17 app with default static files, a custom folder, and a controller route colliding with a static file URL; verify outcomes with MockMvc.

**Scope:** Spring MVC on the Servlet stack, Spring Framework 6.x / Spring Boot 3.x, Java 17+. WebFlux uses `ResourceWebHandler` and `WebFluxConfigurer`, **not** Servlet MVC's `ResourceHttpRequestHandler`.

## 2. What Does "Static Resource" Mean?

A static resource is content returned primarily as a file/bytes rather than running a controller to build a fresh document: CSS, JS, icons, images, fonts, public PDFs, downloadable assets. "Static" **does not mean** lacking dynamic HTTP headers: Spring can still compute `Last-Modified`, return `304 Not Modified`, or apply cache policies.

Example:

```http
GET /css/site.css HTTP/1.1
Host: localhost:8080
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: text/css
Cache-Control: max-age=300

body { color: #123456; }
```

Exact status, content type, and headers depend on configuration and the resource, but the core flow is locating the file, opening a stream, and writing bytes. The client sees only the **public URL**, never needing to know the source file sits under `src/main/resources/static/`.

**Distinguish three concepts:**

- **Resource location**: the source directory such as `classpath:/static/`. This is server-side configuration.
- **URL mapping pattern**: the URL path pattern the client requests, such as `/**` or `/assets/**`.
- **Resource path**: the remaining path after the URL pattern used to locate the file, e.g., `css/site.css`.

Configuration example:

```java
registry.addResourceHandler("/files/**")
        .addResourceLocations("classpath:/downloadable/");
```

When a client calls `GET /files/guide.pdf`, the server looks for `classpath:/downloadable/guide.pdf`. It does not look in `src/main/resources/static/files/guide.pdf` unless that directory is also in the corresponding locations.

## 3. Components of the Spring MVC Resource Pipeline

A typical request:

```text
Client GET /assets/main.css
   │
   ▼
DispatcherServlet
   │
   ├── HandlerMapping: find handler for URL
   │     ├── Controller @GetMapping(...)
   │     ├── View controller / welcome page...
   │     └── Resource handler mappings
   │
   ▼
ResourceHttpRequestHandler (when URL maps to static handler)
   │
   ├── resolve relative path from matched URL
   ├── search registered locations
   ├── ResourceResolver chain
   │     ├── version / encoded / webjar resolver if configured
   │     └── PathResourceResolver to locate allowed file
   ├── verify file exists, is accessible, and is readable
   ├── determine media type, Last-Modified, cache headers
   └── stream resource content into HttpServletResponse
```

**Classes to distinguish:**

| Component | Package / role |
| --- | --- |
| `ResourceHandlerRegistry` | Configuration API via `WebMvcConfigurer#addResourceHandlers`; registers patterns and locations |
| `ResourceHandlerRegistration` | Return value of `addResourceHandler(...)`; configures locations, cache, and resource chain |
| `ResourceHttpRequestHandler` | MVC `HttpRequestHandler` that actually serves static resources |
| `HandlerMapping` | Decides whether a request URL goes to a controller or static handler |
| `ResourceResolver` | Resolves URLs/resources: paths, versions, WebJars, encoded resources, etc. |
| `ResourceTransformer` | Transforms resource responses when needed, e.g., rewriting URLs in CSS |
| `org.springframework.core.io.Resource` | Abstraction for accessing classpath, filesystem, or ServletContext resources |
| `ViewResolver` | **Not a static resource handler**; used when a controller returns a logical view name |

`ResourceHandlerRegistry` does not receive GET requests and write bytes directly. It builds mappings for `ResourceHttpRequestHandler` at startup; at request runtime, `HandlerMapping` selects this handler.

### 3.1. HandlerMapping Differs From ViewResolver

Controller:

```java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home";
    }
}
```

`"home"` is a logical view name, typically resolved by Thymeleaf/JSP resolvers to render HTML. Meanwhile, `static/main.css` is served by `ResourceHttpRequestHandler` as a file, without a logical view name or Thymeleaf rendering.

Do not try to set `spring.thymeleaf.prefix=classpath:/static/` to resolve CSS URLs. The template engine and HTTP static resources are two separate pipelines.

### 3.2. Static Handler Differs From @ResponseBody

A controller can return `ResponseEntity<Resource>` to download a file:

```java
@GetMapping("/download/{id}")
ResponseEntity<Resource> download(@PathVariable long id) {
    // Check authorization, look up private Resource by id,
    // and return appropriate headers.
}
```

This is a **non-standalone illustrative snippet**, suitable when business logic, permissions, user-uploaded content, auditing, or ID validation is needed. Conversely, public CSS/JS/logos at conventional URLs should be handled by static resource handlers. Never use a public file handler in a way that accidentally exposes private documents.

## 4. Default Static Resource Locations in Spring Boot

In Spring Boot Servlet MVC 3.x under default auto-configuration, resources are served from these classpath locations:

1. `classpath:/META-INF/resources/`
2. `classpath:/resources/`
3. `classpath:/static/`
4. `classpath:/public/`

Beyond classpath locations, the ServletContext root may also apply in servlet webapp deployments. With executable JARs, placing assets under `src/main/resources/static/` is common, easy to package, and clear.

Examples:

| Project file path | Default URL | Notes |
| --- | --- | --- |
| `src/main/resources/static/css/site.css` | `/css/site.css` | No `/static` in the URL |
| `src/main/resources/public/images/logo.svg` | `/images/logo.svg` | Also serves as a resource location |
| `src/main/resources/resources/manual.pdf` | `/manual.pdf` | Another default location |
| `src/main/resources/META-INF/resources/favicon.ico` | `/favicon.ico` | Matches convention of some JARs |
| `src/main/resources/templates/home.html` | **No default static URL** | For the template engine, not served directly |
| `src/main/resources/config/secrets.yml` | **No default static URL** | Secrets must never be exposed |
| `src/main/resources/manuals/intro.txt` | **No default static URL** | Must register a location to expose publicly |

**Note:** The table shows where each location works when a matching file exists; it does not guarantee a long-term application contract for "which wins if two locations contain the same relative path." Avoid placing two public files with the same relative path in different static locations; keep one unambiguous copy.

### 4.1. static Does Not Mean /static

The file `src/main/resources/static/css/site.css` is served at:

```text
http://localhost:8080/css/site.css
```

Not by default at:

```text
http://localhost:8080/static/css/site.css
```

To require a `/static` URL prefix, configure a dedicated URL mapping such as `spring.mvc.static-path-pattern=/static/**` (section 6). Even then, the URL and the file directory remain two distinct concepts.

### 4.2. Should You Use src/main/webapp?

`src/main/webapp/` is a familiar location for traditional WAR/Servlet apps. For Spring Boot executable JARs, this folder is **not a reliable way to package static content**; many build setups do not include it in the JAR as you might expect. Use `src/main/resources/static/` or one of the default classpath locations.

JSPs under `WEB-INF/jsp/` are likewise not public static resources. If an application uses JSP, it needs a compatible Servlet/JSP engine, `ViewResolver`, and supported packaging.

### 4.3. Welcome Page index.html

If `src/main/resources/static/index.html` exists, Boot can use it as the **welcome page** for `GET /`. An explicitly mapped controller `@GetMapping("/")` is normally chosen ahead of the welcome-page mapping. This is a specific rule within the `HandlerMapping` chain, not that Boot "unconditionally serves index.html before controllers."

Example:

```text
static/index.html exists
  → GET / can be served by the welcome-page handler
  → GET /index.html is served by the static handler

Add @GetMapping("/")
  → GET / executes the controller instead of the welcome page fallback
```

If both a static index and a template index exist, Boot checks the static index first by default and then the template index, provided no higher-priority explicit route takes over.

## 5. Mapping Precedence Is HandlerMapping Order, Not Filename

When Spring MVC resolves a handler for a URL, `HandlerMapping`s can specify `order` values. According to `ResourceHandlerRegistry#setOrder(...)`, the default static resource mapping has order:

```text
Integer.MAX_VALUE - 1
= 2147483646
= Ordered.LOWEST_PRECEDENCE - 1
```

This is a **very low priority**: common MVC controller mappings have smaller order values and are evaluated first. That keeps static resources as a fallback behind explicitly declared dynamic routes.

Simple diagram:

```text
GET /catalog/42
  │
  ├── RequestMappingHandlerMapping has @GetMapping("/catalog/{id}")
  │        → MATCH → run controller → JSON
  │
  └── Default ResourceHandlerMapping "/**"
           → not reached for this request

GET /assets/site.css
  │
  ├── No controller for this URL
  │
  └── Resource handler "/**"
           → MATCH → locate static/assets/site.css
           → return CSS
```

**Accuracy note:** ordering among `HandlerMapping` types can change with MVC or Spring Boot configuration, and other mappings exist such as `RouterFunctionMapping` or `WelcomePageHandlerMapping`. `Integer.MAX_VALUE - 1` is the default of `ResourceHandlerRegistry` in Spring Framework 6.2, **not a universal guarantee for every handler mapping**.

### 5.1. Mapping Order Differs From Path Specificity

There are **two levels** of resolution:

1. **Across `HandlerMapping`s**: lower order is queried first. Once a `HandlerMapping` matches a handler, selection typically stops—even if another `HandlerMapping` has a URL pattern that "looks more specific."
2. **Within one `HandlerMapping`**: the system compares URL patterns, generally selecting the more specific matching pattern per the configured matching strategy.

Example with two resource patterns registered on the same `ResourceHandlerRegistry`:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/brand-assets/");

registry.addResourceHandler("/**")
        .addResourceLocations("classpath:/fallback-assets/");
```

Within the same mapping, `/assets/logo.svg` has `/assets/**`, which is more specific than `/**`. However, **do not** rely on the order of two Java statements as a priority guarantee; matching follows the configured `PathPattern`/Ant matcher rules.

With Spring Boot already providing the default `/**` mapping, registering `/manuals/**` via `addResourceHandlers` can still work because the pattern is more specific within the MVC resource mappings; always test if you alter order or enable `@EnableWebMvc`.

### 5.2. Why Can the /** Wildcard Make Debugging 404s Harder?

When Boot registers the default `/**` static handler, a URL with no matching controller like `/not-found-route` can still **match `ResourceHttpRequestHandler`**, only to find no corresponding file. The outcome is still 404, yet the exception may be `NoResourceFoundException` (Spring 6.1+) instead of "No handler found".

Consequences:

- Do not assume every HTTP 404 means `DispatcherServlet` failed to find a handler.
- Setting `spring.mvc.throw-exception-if-no-handler-found=true` does not automatically solve every 404 while `/**` matches the resource handler.
- Inspect the logged handler type and source exception; distinguish missing controller routes from missing static resource files.

**Never give a resource handler higher priority than all controllers just to prioritize CSS**, because an overly broad pattern can swallow dynamic routes.

### 5.3. Distinguishing Filter Order and HandlerMapping Order

Servlet `FilterRegistrationBean#setOrder(...)` controls filter order in the Servlet container; `HandlerMapping#setOrder(...)` controls MVC handler selection. `ViewResolver#setOrder(...)` applies only when a controller returns a logical view name. These three orders are independent.

```text
Servlet Filter order
  → DispatcherServlet
      → HandlerMapping order
          → controller or resource handler
              → ViewResolver order (ONLY when there is a view name)
```

Changing `@Order` on a filter does not change static-vs-controller precedence. Changing `ViewResolver` does not make CSS files serve faster.

## 6. Four Commonly Confused Configuration Tools

### 6.1. spring.mvc.static-path-pattern: Changing the URL Pattern

By default, static resources are mapped under `/**`. To expose them under the `/resources/` URL prefix:

```properties
spring.mvc.static-path-pattern=/resources/**
```

Then `classpath:/static/css/site.css` is accessed at `GET /resources/css/site.css` under standard defaults.

This property **does not move files on the classpath**. Do not confuse it with directory locations. Also note that welcome-page mapping may be affected by the static path pattern, so test `GET /` after changing it.

### 6.2. spring.web.resources.static-locations: Changing the Source

To use only a custom directory instead of the default classpath locations:

```properties
spring.web.resources.static-locations=classpath:/site-assets/
```

Boot then serves static resources from this configured location (and potentially the ServletContext root in Servlet MVC), instead of appending to all default classpath locations. **This is a REPLACE, not an append** in how Boot processes the property.

So if you set a custom location and `static/css/site.css` stops working, check whether you accidentally replaced the default locations.

To include both custom and default sources, declare the full list explicitly:

```properties
spring.web.resources.static-locations=classpath:/site-assets/,classpath:/static/
```

Do not use this property for a folder needing its own distinct URL policy when `addResourceHandlers` expresses it more clearly.

### 6.3. spring.web.resources.add-mappings=false: Disabling Auto-Mappings

```properties
spring.web.resources.add-mappings=false
```

When set to false, Boot stops adding **its default static mappings**. Resource handlers you explicitly register can still exist through your MVC configuration. This is useful for API-only services, when a CDN/reverse proxy serves static files, or when you want full control over mappings.

**Do not enable this property just to fix a 404**: it can break working CSS/JS/favicon/welcome pages. After changing it, test public URLs and primary controller routes.

### 6.4. addResourceHandlers: Adding Explicit Mappings

To expose `classpath:/manuals/` specifically at `/manuals/**`:

```java
@Configuration
class StaticResourceConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}
```

*Illustrative configuration snippet; requires imports for `Configuration`, `WebMvcConfigurer`, `ResourceHandlerRegistry`, `CacheControl`, and `Duration`. Full runnable project is in section 9.*

This adds a mapping with a clear URL namespace; it **does not replace** the default `/**` static path. When an application has distinct file groups (images, public manuals, bundles), design explicit paths such as `/assets/**`, `/manuals/**`, or `/webjars/**`.

### 6.5. @EnableWebMvc in Spring Boot

Never add `@EnableWebMvc` just to register a resource mapping. In Spring Boot, that annotation makes you responsible for most MVC configuration yourself, disabling many Boot defaults.

Prefer:

- Boot properties for simple changes.
- `@Configuration implements WebMvcConfigurer` overriding `addResourceHandlers` for additional mappings.
- `@EnableWebMvc` only when intentionally taking full Framework-level MVC control and re-providing all required components.

## 7. Caching and Versioned URLs for Static Resources

`ResourceHttpRequestHandler` does more than read static files; responses can also carry **caching headers** and handle **conditional GET**. Distinguish these three responsibilities instead of flipping one property and assuming everything is solved:

| Responsibility | HTTP/Spring mechanism | Design decision |
| --- | --- | --- |
| Cache for a duration | `Cache-Control`, e.g., `max-age` | Unversioned files must not be cached long if bytes can change at the same URL |
| Freshness revalidation | `Last-Modified` / `If-Modified-Since` and status `304` | Not every `Resource` source provides an accurate timestamp |
| Avoid stale cache after deploy | Resource chain, content-hashed URLs, or fixed version | Must emit new URLs in HTML/templates and retain old assets long enough |

For example, for relatively stable resources, a custom handler can set a 5-minute cache:

```java
registry.addResourceHandler("/manuals/**")
        .addResourceLocations("classpath:/manuals/")
        .setCacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic());
```

This is a fragment inside `WebMvcConfigurer#addResourceHandlers`; requires imports for `CacheControl`, `Duration`, and proper bean configuration. Responses can contain `Cache-Control: max-age=300, public`. If the client sends `If-Modified-Since` and the resource exposes matching update metadata, the server can reply `304 Not Modified` without resending the body.

For long-cached static assets like CSS/JS, **content-hashed paths** ensure the URL changes whenever bytes change. Yet generating versioned URLs does not automatically set proper `Cache-Control`, and enabling `VersionResourceResolver` does not automatically rewrite hardcoded paths in HTML. Ensure asset URLs are generated/rewritten via templates, `ResourceUrlProvider`, the corresponding filter, or a bundler manifest. Never attach a version resolver to every custom resource handler without verifying which mapping actually serves it; a custom resolver must also never bypass path containment.

The next lesson on **resource chains and content fingerprinting** covers configuring `ContentVersionStrategy`/`FixedVersionStrategy`, `VersionResourceResolver`, URL rewriting, Java config, and rolling-deployment testing. Here, the key point is identifying **which `HandlerMapping` serves a static file** before choosing its caching policy.

## 8. Security: Public Files Are Not Where Secrets Belong

A static resource handler should normally serve only **publicly shareable content**. The following files must never live inside public static locations:

```text
application-prod.yml containing credentials
secret.key
private-invoices/customer-123.pdf
.env
backup.sql
.git/ repository
```

Why: if a broad mapping exists and a file ends up under a resource root, clients can request its URL directly. Placing files in `/WEB-INF/`, keeping them outside the web root, or protecting them with proper access control is the application's responsibility.

### 8.1. Path Traversal

Attack examples attempting to fetch:

```text
GET /manuals/../config/secret.txt
GET /manuals/%2e%2e%2fconfig%2fsecret.txt
```

Spring MVC together with `PathResourceResolver` and the Servlet container protects against paths escaping allowed resource locations. However:

- Never disable path validation or manually concatenate request paths into `new File(...)`.
- Rejection may occur in a Servlet firewall, container, or path matching before the resource handler; the exact HTTP status depends on configuration.
- Do not test "one traversal variant returned 404" and assume all encoding variants are blocked.
- Keep Spring/containers updated, restrict locations, and test both authorized and unauthorized file access in your deployment environment.

### 8.2. Spring Security and Static Assets

ResourceHandler **does not automatically bypass Spring Security**. The Servlet security filter chain applies to CSS/JS/image requests as well. If the login page is missing CSS, check your authorization rules:

```java
// Policy idea inside SecurityFilterChain,
// not a complete security configuration:
.requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
.anyRequest().authenticated()
```

*Illustrative snippet to understand the policy; requires a project with Spring Security and full configuration.*

Prefer `permitAll()` for public static assets instead of disabling all security filters with `web.ignoring()` when you want to retain security headers and protections. Never open `/**` publicly if the API or site has protected resources.

### 8.3. CORS, Content Type, and Content Sniffing

If assets are loaded cross-origin, CORS may need configuration depending on request type and usage; static handlers can have their own CORS policies. Never add `Access-Control-Allow-Origin: *` unconditionally across all resources when credentials or sensitive data exist.

Ensure media types are accurately resolved (e.g., `text/css`, `application/javascript`, `image/svg+xml`) and consider `X-Content-Type-Options: nosniff`. Certain formats—especially user-uploaded SVG/HTML/JS—can execute scripts in various contexts: **never place untrusted uploads in a public static directory without strict policy/validation**.

## 9. Runnable Spring Boot 3 + Java 17 Project

The demo is designed to show **both the default static mapping and a custom mapping**, while proving controller routes take precedence over the wildcard static fallback.

### 9.1. Behaviors to Verify

- `static/assets/site.css` is served at `GET /assets/site.css` (default `/**` static mapping).
- `manuals/guide.txt` is served at `GET /manuals/guide.txt` after registering `/manuals/**`.
- `static/catalog/7` exists, yet `GET /catalog/7` runs the controller returning JSON (dynamic mapping wins).
- `GET /manuals/absent.txt` returns 404; the request matches the resource handler, but no file exists.
- `GET /index.html` serves the static welcome-file asset; when running in a real Servlet container, `GET /` can use welcome-page support.
- The response for `/manuals/guide.txt` includes cache-control `max-age=300` (demo policy).

Uses Java 17+, Maven, Spring Boot **3.3.13**, and Spring MVC.

### 9.2. Directory Structure

```text
resource-handler-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/ResourceHandlerDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── static/
    │       │   ├── index.html
    │       │   ├── assets/site.css
    │       │   └── catalog/7
    │       └── manuals/guide.txt
    └── test/java/example/ResourceHandlerDemoTest.java
```

### 9.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>resource-handler-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
```

### 9.4. ResourceHandlerDemoApplication.java

Create `src/main/java/example/ResourceHandlerDemoApplication.java`. Supporting package-private classes live in the same file; only the main class is public.

```java
package example;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ResourceHandlerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceHandlerDemoApplication.class, args);
    }
}

@Configuration
class PublicManualsConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // Map /manuals/** to classpath:/manuals/
        // without replacing Boot's default static handler.
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}

@RestController
class CatalogController {
    @GetMapping("/catalog/{id}")
    Map<String, Object> product(@PathVariable int id) {
        return Map.of("id", id, "source", "controller");
    }
}
```

**Why does this code run cleanly?**

- `@SpringBootApplication` enables Spring Boot MVC auto-configuration when `spring-boot-starter-web` is present.
- `PublicManualsConfig implements WebMvcConfigurer` only **adds** a resource mapping without adding `@EnableWebMvc`, so Boot defaults remain intact.
- `registry.addResourceHandler("/manuals/**")` registers the URL namespace; `addResourceLocations("classpath:/manuals/")` points to the folder packaged by Maven from `src/main/resources/manuals/`.
- `CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic()` sets a 300-second public cache policy; this is a demo policy, not right for every document.
- `CatalogController` receives `/catalog/7` ahead of the resource fallback; the conflicting static file is included **intentionally** to demonstrate precedence.

### 9.5. application.properties

File `src/main/resources/application.properties`:

```properties
# Keep defaults explicit to observe mapping precedence.
spring.web.resources.add-mappings=true
spring.mvc.static-path-pattern=/**
```

We omit `spring.web.resources.static-locations` to keep Boot's default classpath locations alongside the custom location via `WebMvcConfigurer`. There is no need to set `registry.setOrder(...)` without a clear requirement.

### 9.6. static/assets/site.css

File `src/main/resources/static/assets/site.css`:

```css
body {
    font-family: system-ui, sans-serif;
    color: #123456;
}
```

The URL is `/assets/site.css`. Browsers do not request `/static/assets/site.css`; `static` is only the folder name on the classpath.

### 9.7. manuals/guide.txt

File `src/main/resources/manuals/guide.txt`:

```text
Welcome to the public manual.
```

The URL is `/manuals/guide.txt` thanks to the custom mapping. This file sits outside the four default static classpath locations, proving that merely "being under resources" does not automatically publish a URL.

### 9.8. static/catalog/7 (Intentional Route-Colliding Resource)

File `src/main/resources/static/catalog/7`:

```text
STATIC-FALLBACK-SHOULD-NOT-WIN
```

When calling `GET /catalog/7`, the controller still wins and returns JSON `{"id":7,"source":"controller"}` (key order is not fixed). This file is purely a fixture to test routing precedence; in production projects avoid useless duplicate URLs.

### 9.9. static/index.html

File `src/main/resources/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Static Resource Demo</title>
    <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
    <h1>Public index page</h1>
</body>
</html>
```

This is a static HTML file, not a Thymeleaf template: it has no view-engine expressions and is accessible at `/index.html`. In Boot Servlet MVC, it can also serve as the welcome page at `/` when no dedicated controller route exists.

When an app has a context path, use relative URLs or context-aware URL builders in templates; a literal `href="/assets/site.css"` targets the origin root, so it fits demos running without a context path.

### 9.10. Running and Testing With cURL

Requires JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/manuals/guide.txt
curl -i http://localhost:8080/catalog/7
curl -i http://localhost:8080/index.html
curl -i http://localhost:8080/manuals/not-found.txt
```

Expected results:

| URL | Status | Main content |
| --- | ---: | --- |
| `/assets/site.css` | 200 | CSS containing `color: #123456;` |
| `/manuals/guide.txt` | 200 | Text `Welcome to the public manual.` |
| `/catalog/7` | 200 | JSON `{"id":7,"source":"controller"}` |
| `/index.html` | 200 | HTML containing `Public index page` |
| `/manuals/not-found.txt` | 404 | No resource in the configured location |

For `/manuals/guide.txt`, the `Cache-Control` response header includes `max-age=300`. `curl -i` prints additional Tomcat/Boot headers. Never compare the entire response byte-for-byte including dates and auto-generated headers.

To test conditional HTTP (depending on the resource's `Last-Modified`):

```bash
curl -I http://localhost:8080/manuals/guide.txt
# Read Last-Modified if present, then send:
curl -i -H 'If-Modified-Since: <date-from-last-modified>' \
  http://localhost:8080/manuals/guide.txt
```

Substitute the exact date returned by the server. If the resource has not changed and the server supports the appropriate validator, the response can be HTTP 304. The angle-bracketed value here is a placeholder **only in the CLI command**, not a literal HTTP value.

## 10. MockMvc Verifying Default/Custom/Mapping Precedence

File `src/test/java/example/ResourceHandlerDemoTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.resource.ResourceHttpRequestHandler;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceHandlerDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void defaultBootStaticLocationServesCss() throws Exception {
        mvc.perform(get("/assets/site.css"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                    ResourceHttpRequestHandler.class))
            .andExpect(content().string(
                    containsString("color: #123456;")));
    }

    @Test
    void customResourceHandlerServesManual() throws Exception {
        mvc.perform(get("/manuals/guide.txt"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                    ResourceHttpRequestHandler.class))
            .andExpect(content().string(
                    containsString("Welcome to the public manual.")));
    }

    @Test
    void customManualHasFiveMinuteCachePolicy() throws Exception {
        mvc.perform(get("/manuals/guide.txt"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Cache-Control", containsString("max-age=300")));
    }

    @Test
    void controllerTakesPrecedenceOverStaticWildcard()
            throws Exception {
        mvc.perform(get("/catalog/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.source").value("controller"));
    }

    @Test
    void missingCustomResourceIsNotFound() throws Exception {
        mvc.perform(get("/manuals/absent.txt"))
            .andExpect(status().isNotFound());
    }

    @Test
    void indexHtmlIsAvailableAsStaticFile() throws Exception {
        mvc.perform(get("/index.html"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    containsString("Public index page")));
    }

    @Test
    void staticIsNotAUrlPrefixByDefault() throws Exception {
        mvc.perform(get("/static/assets/site.css"))
            .andExpect(status().isNotFound());
    }
}
```

Run `mvn test`. The tests verify not only status codes, but also the **handler type** for resources and the **file contents**. For `/catalog/7`, the JSON assertions prove the controller actually executes despite the colliding static file.

`@SpringBootTest` with `@AutoConfigureMockMvc` loads Boot auto-configuration and the custom `WebMvcConfigurer` without opening a network port. However, differences can exist when deploying WAR/executable JARs or behind a reverse proxy. To verify welcome-page `GET /`, browser caching, and container-added headers, add integration tests running an embedded server on a random port.

### 10.1. Why Not Test by Simply Asserting "Any 404 Is OK"?

`/manuals/absent.txt` may be matched by the resource `HandlerMapping` and then fail to locate a file. A bare 404 check only proves no resource was returned without explaining **which branch** caused the 404. To analyze further, assert `handler().handlerType(ResourceHttpRequestHandler.class)` when a handler matches, inspect the resolved exception if needed, or enable debug logging. In Spring Framework 6.1+, `NoResourceFoundException` can be thrown when a resource is missing.

## 11. Resource Locations Outside the Classpath

Sometimes files are public uploaded images or live in an admin-managed directory updated after the JAR is built. You can use a `file:` location:

```java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/media/**")
            .addResourceLocations("file:/srv/myapp/public-media/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(10)));
}
```

The snippet above is **illustrative only**. File paths differ across Windows/Linux, container images, and cloud mounts. If choosing a public filesystem root, configure permissions/ownership tightly, never mix with private directories, and keep source files strictly inside the allowed location.

### 11.1. Why Never Read Paths From Query Parameters?

Never implement something like this:

```java
// Bad example: NEVER use with user input.
Path file = Paths.get(request.getParameter("path"));
return Files.readAllBytes(file);
```

This bypasses all checks provided by the resource handler and path resolver, risking path traversal or arbitrary file reads. If you must serve files by business ID, map the ID to trusted server metadata, check ownership, and use a controlled file-download API.

### 11.2. Storing Files in S3/CDN/Object Storage

Large, high-traffic static content can live in a CDN or object storage. In that setup, a Spring MVC resource handler is not necessarily the optimal place to stream all bytes. You can return signed URLs, controlled redirects, or use CDN origins with proper permissions. Multi-tenant resources need precise ACL policies; never simply point a resource location at a public bucket and consider it secure.

## 12. Interaction With Templates, Frontend Bundlers, and Reverse Proxies

### 12.1. Thymeleaf/JSP Referencing Static URLs

In Thymeleaf:

```html
<link rel="stylesheet" th:href="@{/assets/site.css}">
<img th:src="@{/images/logo.svg}" alt="Logo">
<script th:src="@{/js/app.js}" defer></script>
```

The template engine generates proper URLs accounting for any context path. Actual files still reside in `static/assets/site.css`, `static/images/logo.svg`, or a custom-mapped folder. With a versioned resource chain, ensure URL rewriting is fully configured.

Do not reference `@{/static/assets/site.css}` out of habit when the URL mapping is still `/**`.

### 12.2. When Frontend Tools Build Bundles

Bundlers can emit:

```text
dist/assets/main-48abd3.css
dist/assets/main-93cf12.js
```

Build outputs can be copied into `src/main/resources/static/` during packaging, or a resource location can be pointed at the appropriate output. In production, the build pipeline must keep emitted filenames and `index.html` references synchronized. Never serve raw React/Vue project source files as static production assets if browsers cannot run unbuilt modules.

### 12.3. Reverse Proxy / Ingress

Nginx, Apache, a CDN, or a gateway may serve static assets **before requests ever reach Spring Boot**. In that case you can see 404/403/cache headers without Spring MVC ever running. Diagnose layer by layer:

```text
Browser
  → CDN/browser cache
  → Reverse proxy
  → Servlet container
  → Spring Security filters
  → DispatcherServlet
  → HandlerMapping / ResourceHttpRequestHandler
```

Check whether requests reach the app, host/path rewrites, forwarded headers, cache keys, and asset deployment timing. Do not tweak `ResourceHandlerRegistry` if the 404 comes from a CDN pointing to the wrong directory.

## 13. Fastest Debugging Checklist in Order

1. **Verify the browser-facing URL**: `/assets/site.css` or `/static/assets/site.css`?
2. **Verify the actual file**: is it present in `target/classes/static/` or inside the built JAR?
3. **Check Boot config**: `spring.web.resources.add-mappings`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, and active profile properties.
4. **Check handler mappings**: does a controller route collide with the URL? Does a custom registry pattern cover the URL?
5. **Check the resource handler**: the URL matched, so are the relative path and location right?
6. **Check ordering**: across `HandlerMapping`s, controllers usually run before resource fallbacks; do not confuse with filter or view resolver order.
7. **Check Security/CORS**: is the request actually hitting 401/403 or a login redirect?
8. **Check caching**: stale content, 304, `Cache-Control`, and content-versioned URLs correct?
9. **Check reverse proxy**: does the request reach the Servlet container, or is the path rewritten?
10. **Use MockMvc** to verify resource URLs and controller precedence; use HTTP integration tests to verify Servlet container/cache headers and deployment packaging.

During development you can enable logging:

```properties
logging.level.org.springframework.web.servlet.resource=DEBUG
logging.level.org.springframework.web.servlet.handler=DEBUG
```

Do not leave DEBUG logging enabled across the whole web framework long-term in production if it produces excessive logs or risks leaking data.

## 14. Common Mistakes

| Misconception | Consequence | How to fix |
| --- | --- | --- |
| "Any file in resources is automatically public" | `manuals/guide.txt` returns 404 | Put in a default static dir or register via `addResourceHandlers` |
| "Static file URLs must include /static" | Wrong URL, 404 | Remember `classpath:/static/` does not mean URL `/static/` |
| "Changing static-path-pattern changes the source folder" | Requests still search the old location | Use `static-locations` to change locations |
| "static-locations appends to defaults automatically" | Old CSS disappears | It replaces defaults; list all needed locations |
| "ResourceHandlerRegistry runs before controllers if written earlier in config" | Misunderstood precedence | `HandlerMapping` order governs, not statement order |
| "/** wildcard always beats @GetMapping" | Thinking dynamic routes won't run | Controller mappings usually have higher priority |
| "Every 404 is NoHandlerFoundException" | Exception handler misses static 404s | Inspect `NoResourceFoundException` and `/**` mapping |
| "@EnableWebMvc just turns on MVC for Boot" | Loses many auto-configurations | Use `WebMvcConfigurer` when only customizing mappings |
| "ViewResolver serves CSS" | Misconfigured template prefix | Use resource mappings and `ResourceHttpRequestHandler` |
| "Cache static files for 1 year without versioned URLs" | Users get stale files | Add content hashes/versions or shorten cache TTL |
| "Enabling VersionResourceResolver rewrites HTML URLs automatically" | Mismatched URLs, caching bugs | Integrate `ResourceUrlProvider` / encoding |
| "Enable CORS * for every file" | Overly broad exposure | Tailor CORS policy to actual needs and credentials |
| "PathResourceResolver makes all uploads safe" | XSS, data leaks through public files | Keep uploads private, validate MIME/ACLs |
| "Servlet root and classpath static behave identically" | WAR vs JAR deployment differences | Understand exact packaging and resource loading |
| "Security must ignore all static assets" | Loses security headers/protections | Use `permitAll` on public paths in `SecurityFilterChain` when appropriate |
| "Seeing Cache-Control guarantees 304" | Misunderstood HTTP caching semantics | 304 depends on conditional requests and validators |
| "CSS didn't update in browser so fix the mapping" | Fixing the wrong layer | Check browser/CDN cache first |
| "Static files always resolve in alphabetical folder order" | Unintended duplicate path shadowing | Avoid duplicate relative paths across locations |

## 15. Self-Check

**1.** What URL does `src/main/resources/static/css/main.css` have under Boot defaults?  
**Answer:** `GET /css/main.css`, not `/static/css/main.css`.

**2.** Does `src/main/resources/manuals/intro.txt` get a URL automatically?  
**Answer:** No, it is not in the default locations; add a mapping or move the file.

**3.** Given `addResourceHandler("/public/**")` and `addResourceLocations("classpath:/assets/")`: where does `/public/site.css` look for the file?  
**Answer:** `classpath:/assets/site.css`.

**4.** What does `ResourceHttpRequestHandler` do?  
**Answer:** Receives mapped static requests, resolves the file, and serves bytes/headers.

**5.** Is `ViewResolver` a `ResourceHttpRequestHandler`?  
**Answer:** No; `ViewResolver` resolves logical view names in the rendering pipeline.

**6.** What is the default `HandlerMapping` order of the resource registry in Spring 6.2?  
**Answer:** `Integer.MAX_VALUE - 1`, very low priority.

**7.** When `@GetMapping("/catalog/{id}")` and static `catalog/7` both exist, which normally wins?  
**Answer:** The controller, because `RequestMappingHandlerMapping` is evaluated before the resource fallback.

**8.** Is `/assets/**` always evaluated before `/**` simply because it was declared earlier in Java?  
**Answer:** No; path specificity and mapping rules decide within the same `HandlerMapping`.

**9.** Which setting changes the URL prefix of static assets?  
**Answer:** `spring.mvc.static-path-pattern`.

**10.** Which setting changes Boot's static resource locations?  
**Answer:** `spring.web.resources.static-locations`; it replaces the default locations.

**11.** How do you turn off Boot's automatic static mappings?  
**Answer:** `spring.web.resources.add-mappings=false`.

**12.** Why can adding `@EnableWebMvc` make static files disappear?  
**Answer:** You take over MVC configuration, disabling many Boot defaults.

**13.** If `/manuals/not-found.txt` returns 404, does that prove no handler matched?  
**Answer:** No; the resource handler may have matched and then failed to find the file.

**14.** When should content-versioned URLs be used?  
**Answer:** When long-term caching is desired while assets can change across releases; hashed/versioned URLs enable cache busting.

**15.** What status can `If-Modified-Since` produce if the file has not changed?  
**Answer:** `304 Not Modified`, depending on the resource validator and HTTP policy.

**16.** Is placing private user PDFs in `static/` safe?  
**Answer:** Not by default; static locations are public per URL mapping and require dedicated access control.

**17.** What is the role of the `X-Content-Type-Options: nosniff` header?  
**Answer:** Restricts browsers from sniffing a MIME type different from the server's declaration, adding a defense against type confusion.

**18.** When a CDN returns 404, is Spring's `ResourceHandlerRegistry` definitely misconfigured?  
**Answer:** No; the request may never have reached Spring.

**19.** Why should you inspect inside the built JAR?  
**Answer:** A file sitting in the source tree is not guaranteed to be packaged onto the runtime classpath.

**20.** What test should you write to prove controller vs static precedence?  
**Answer:** Create a controller route and a static file at the same URL, and assert that the response comes from the controller and expected handler.

## 16. Official References

- [Spring Framework 6.2 — Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html): `addResourceHandlers`, cache control, versioned resource URLs, resource resolver chain.
- [Spring Framework 6.2 — ResourceHandlerRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/servlet/config/annotation/ResourceHandlerRegistry.html): `addResourceHandler` and `setOrder`, default `Integer.MAX_VALUE - 1`.
- [Spring Framework 6.2 — ResourceHttpRequestHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/resource/ResourceHttpRequestHandler.html): resolving and serving resources, conditional requests/`Last-Modified`.
- [Spring Framework 6.2 — VersionResourceResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/web/servlet/resource/VersionResourceResolver.html): content/fixed version strategies.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): static content locations, `static-path-pattern`, `static-locations`, welcome page, WebJars.
- [Spring Framework — Handler Mappings](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping.html): how MVC selects handlers by URL and order.
- [Spring Framework 6.2 — MVC Test Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc and handler testing.

**Remember:** `ResourceHandler` binds a **URL pattern** to **real file/resource locations** so `ResourceHttpRequestHandler` can serve them. Spring Boot provides default classpath static locations and a `/**` fallback; controller mappings are normally evaluated first. When a file fails to appear, check **URL path → `HandlerMapping` order → resource location → packaging → security/cache/proxy** instead of guessing or tweaking `ViewResolver`.
