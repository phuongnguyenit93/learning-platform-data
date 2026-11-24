# Configuring spring.web.resources.* and static resource paths in Spring Boot

## 1. Why must you understand both paths and resource mapping?

When you have `src/main/resources/static/css/app.css`, Spring Boot can return its contents at `/css/app.css` without needing a controller. However, if you change the URL to `/assets/css/app.css` or move resources to another directory, you must distinguish **two types of paths**:

- **Resource lookup path**: `spring.web.resources.static-locations` determines where Spring Boot looks for files, such as `classpath:/static/`, `classpath:/public/`, or `file:/opt/app/public/`.
- **HTTP access path**: `spring.mvc.static-path-pattern` in a Spring MVC app, or `spring.webflux.static-path-pattern` in WebFlux, determines which URLs are routed to the resource handler.

The `spring.web.resources.*` properties also control enabling/disabling default mappings, HTTP caching, server-side caching, versioning, and precompressed file selection.

**Lesson objectives:** explain the static resource serving mechanism; configure locations, URL prefixes, context paths, and caching yourself; distinguish MVC from WebFlux; inspect files inside a JAR; troubleshoot 404 errors, stale browser caches, and risks of exposing sensitive files.

> **Versions:** the property section applies to Spring Boot 3.5 and 4.x where supported. The runnable example uses Spring Boot 3.5.x, Java 17+, and Spring MVC; if using Boot 4.x, create the project with `spring-boot-starter-webmvc` instead of `spring-boot-starter-web`. Always verify the property list against your project's exact version.

## 2. Static mechanism and default structure

Spring Boot serves static files through the web framework:

- **Spring MVC / Servlet**: `ResourceHttpRequestHandler` handles requests matching resource mappings.
- **Spring WebFlux / Reactive**: `ResourceWebHandler` performs the equivalent role.
- The framework extracts the relative path from the URL, searches configured `ResourceLocation` entries, verifies access, and returns HTTP content with the appropriate media type and headers.

By default, Boot searches the following classpath directories:

~~~text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
~~~

These are **locations inside the classpath at runtime**, not four URL prefixes. In Gradle/Maven apps, files in `src/main/resources/static/` are placed on the classpath during build; in an executable Boot JAR, they usually reside under `BOOT-INF/classes/static/`.

Example layout:

~~~text
src/main/
  java/com/example/assets/AssetsApplication.java
  resources/
    application.yml
    static/
      index.html
      css/
        app.css
      js/
        app.js
      images/
        logo.svg
~~~

With the app running at the HTTP root and the default `/**` mapping:

| File in project | URL |
|---|---|
| `src/main/resources/static/css/app.css` | `GET /css/app.css` |
| `src/main/resources/static/js/app.js` | `GET /js/app.js` |
| `src/main/resources/static/images/logo.svg` | `GET /images/logo.svg` |
| `src/main/resources/static/index.html` | `GET /index.html`; can also serve as the welcome page for `/` |

**Do not put `/static` in the URL** merely because the folder holding the files is named `static`. Do not mix static resources with dynamic templates in `src/main/resources/templates/`: templates must be rendered by a view engine/controller via a different mechanism.

Spring MVC also supports resources from the `ServletContext` root. For a Boot executable JAR, `src/main/webapp` is not recommended for static resources; WebFlux does not use the `ServletContext` mechanism and does not use that directory. Avoid keeping identical resource names in multiple static locations because lookup/overriding becomes hard to control.

## 3. Two property groups that must be kept distinct

| Property | Role | Default or note |
|---|---|---|
| `spring.web.resources.static-locations` | Root list holding static files | Defaults to the four classpath locations above; declaring a custom value **replaces** this list |
| `spring.web.resources.add-mappings` | Enables Boot-registered static resource mappings | Default `true` |
| `spring.mvc.static-path-pattern` | URL pattern for Spring MVC | Default `/**` |
| `spring.webflux.static-path-pattern` | URL pattern for WebFlux | Default `/**` |
| `server.servlet.context-path` | Prefix of the Servlet application | Not synonymous with static path pattern |
| `spring.webflux.base-path` | Base path of the WebFlux application when configured | Not a static location |
| `spring.web.resources.cache.period` | HTTP cache duration for resources | Can use `10m`, `1h`, `7d` |
| `spring.web.resources.cache.cachecontrol.max-age` | Cache-Control `max-age` directive | Can write `1h`; part of fine-grained `cachecontrol` settings |
| `spring.web.resources.cache.cachecontrol.cache-public` | Allows shared caches to store public resources | Do not set indiscriminately on private content |
| `spring.web.resources.cache.cachecontrol.no-store` | Prevents storing the resource in HTTP caches | Avoid combining with long-cache settings that conflict |
| `spring.web.resources.cache.use-last-modified` | Supports conditional caching via `Last-Modified` | Default `true` |
| `spring.web.resources.chain.enabled` | Enables the resource chain | Disabled by default when no strategy requires it |
| `spring.web.resources.chain.cache` | Caches resource lookups on the server | Default `true` when chain is used |
| `spring.web.resources.chain.strategy.content.enabled` | Versions resources by content hash | Used alongside versioned URL generation/rewriting |
| `spring.web.resources.chain.strategy.content.paths` | URL patterns using content versioning | Default `/**` when strategy is enabled |
| `spring.web.resources.chain.strategy.fixed.enabled` | Enables fixed version strategy | Used with `fixed.version` and `fixed.paths` |
| `spring.web.resources.chain.compressed` | Searches for precompressed `.gz`/`.br` files | Does not compress all files on the fly |

The `spring.web.resources.*` prefix holds **shared Boot configuration** for resource handling, whereas the URL pattern property name depends on the web application type. Consequently, changing `spring.mvc.static-path-pattern` will not control mappings in a pure WebFlux application.

## 4. Understanding the mapping mechanism through an example

Given this configuration:

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

Suppose the application has `src/main/resources/frontend/css/site.css`.

~~~text
Request: GET /assets/css/site.css
             |
             +--- pattern /assets/** matched
             |
             +--- relative path: css/site.css
                        |
                        v
ResourceHttpRequestHandler
                        |
                        +--- location: classpath:/frontend/
                        |
                        v
Lookup: classpath:/frontend/css/site.css
                        |
                        v
HTTP 200 (if found and allowed to be returned)
~~~

These are four different names:

- `/assets/css/site.css`: **request URL**.
- `/assets/**`: **URL pattern** used by MVC to route to the resource handler.
- `css/site.css`: **relative path** after stripping the static prefix.
- `classpath:/frontend/css/site.css`: **file lookup target** at runtime.

In this example, changing the URL prefix to `/assets` **does not require** adding an `assets` folder inside the file location. Likewise, changing `static-locations` to `frontend` **does not automatically make** the URL contain the word `frontend`.

If a separate controller also registers `/assets/css/site.css`, you must check handler precedence; do not assume the static handler always beats every controller.

## 5. Runnable example: changing the static URL and location

Create a project from Spring Initializr: **Spring Boot 3.5.x**, Gradle, Java 17+, dependency **Spring Web**. The generated project includes a Gradle wrapper. Place the following files:

~~~text
src/main/
  java/demo/assets/AssetsApplication.java
  resources/
    application.yml
    frontend/
      hello.txt
      css/
        site.css
~~~

**File `src/main/java/demo/assets/AssetsApplication.java`**

~~~java
package demo.assets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetsApplication.class, args);
    }
}
~~~

The class above is a complete Spring Boot application when the project includes the MVC starter mentioned. No controller is needed for static resources.

**File `src/main/resources/application.yml`**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      add-mappings: true
      static-locations:
        - "classpath:/frontend/"
      cache:
        period: 10m
~~~

**File `src/main/resources/frontend/hello.txt`** contains:

~~~text
Hello static!
~~~

**File `src/main/resources/frontend/css/site.css`** contains:

~~~css
body {
    color: #174ea6;
}
~~~

From the root directory of the created project, run:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the application starts, send a request from another terminal:

~~~bash
curl -fsS http://localhost:8080/assets/hello.txt
~~~

**Expected response body:**

~~~text
Hello static!
~~~

Check CSS:

~~~bash
curl -fsS http://localhost:8080/assets/css/site.css
~~~

**Expected response body:**

~~~css
body {
    color: #174ea6;
}
~~~

Inspect both status and headers:

~~~bash
curl -i http://localhost:8080/assets/hello.txt
curl -i http://localhost:8080/hello.txt
~~~

When only the files and configuration in this lesson exist, the first URL returns 200 and the second normally returns 404: the static mapping moved to `/assets/**`, so that file is no longer served at `/hello.txt`. Headers depend on the HTTP server and caching policy, so do not assume verbatim full headers.

**When using Boot 4.x:** select the Spring Web MVC starter (`spring-boot-starter-webmvc`); `AssetsApplication.java` and these properties work the same way.

## 6. Custom locations: replacing defaults and declaring multiple sources

### Case 1: using only a custom directory

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

The default list `META-INF/resources`, `resources`, `static`, `public` **is not automatically appended**. If a CSS file remains in `src/main/resources/static/css/app.css`, setting locations to only `frontend` prevents Boot from finding CSS from the default `static` location.

### Case 2: keeping old directories and adding a new one

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/frontend/"
~~~

If the project still needs `META-INF/resources`, `resources`, or `public`, include those corresponding locations back in the list as well. Do not arbitrarily duplicate the same filename across multiple sources; maintain clear namespace conventions.

### Case 3: using a directory outside the JAR

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "file:/opt/my-app/public-assets/"
~~~

If the host running the app has `/opt/my-app/public-assets/manual.pdf` and the default `/**` URL pattern, the file is accessible at `/manual.pdf`. With the `/assets/**` pattern, the URL becomes `/assets/manual.pdf`; the filesystem path stays the same.

**Deployment notes:**
- `file:/opt/...` is resolved against the filesystem **of the application process**. Inside Docker, that is the container's filesystem, not automatically a host path.
- The folder must exist and the service user needs read permissions. When mounting a volume, verify the actual mount inside the container.
- Only point to directories approved for public access. Never configure `file:/` or directories containing `application.yml`, private keys, backups, or private uploads.
- Do not accept a file path from users and concatenate it onto a public directory without checking IDs, permissions, path traversal, and symlinks. For protected files, use a file-download API with authorization.

## 7. Context path and reverse proxies

Example Servlet app:

~~~yaml
server:
  servlet:
    context-path: "/shop"

spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
~~~

With `frontend/css/site.css`, the client calls:

~~~text
GET /shop/assets/css/site.css
~~~

`/shop` comes from the **Servlet context path**. It is not added to `classpath:/frontend/` and does not need to be repeated inside `spring.mvc.static-path-pattern`.

If a reverse proxy, CDN, or ingress sits in front using a prefix, check whether the proxy **preserves or rewrites the prefix** before forwarding to Boot. Double-applying a prefix can cause 404s for assets. If the frontend renders root-relative URLs (starting with `/assets`), check whether the `/shop` prefix or a context-aware URL helper is needed.

In WebFlux, the base path property is `spring.webflux.base-path`, not `server.servlet.context-path`. Confirm whether you are actually running the Servlet or Reactive stack.

## 8. Comparing MVC and WebFlux

### Spring MVC

~~~yaml
spring:
  mvc:
    static-path-pattern: "/media/**"
  web:
    resources:
      static-locations:
        - "classpath:/public-files/"
~~~

`ResourceHttpRequestHandler` uses the `/media/**` URL to look up `classpath:/public-files/`. If `public-files/icons/logo.svg` exists, the URL is `/media/icons/logo.svg`.

### Spring WebFlux

~~~yaml
spring:
  webflux:
    static-path-pattern: "/media/**"
  web:
    resources:
      static-locations:
        - "classpath:/public-files/"
~~~

`ResourceWebHandler` fulfills the equivalent role. Resource locations and URL prefix semantics are the same; URL configuration uses `spring.webflux.static-path-pattern`.

If an application has both MVC and WebFlux starters on the classpath, Boot usually favors the **SERVLET/MVC** web application type. An MVC project having `WebClient` does not mean its resource handler switched to reactive. Inspect the starters and running application context rather than merely seeing a WebFlux dependency.

## 9. Cache-Control: browser caching duration

For static CSS/JS that remain unchanged for a period, HTTP caching reduces load and transfer time. A simple configuration:

~~~yaml
spring:
  web:
    resources:
      cache:
        period: 15m
~~~

To specify `Cache-Control` directives in detail:

~~~yaml
spring:
  web:
    resources:
      cache:
        cachecontrol:
          cache-public: true
          max-age: 1h
~~~

`cache.period` is a duration for the resource handler. `cachecontrol.max-age` and the other `cachecontrol.*` properties provide finer control over HTTP cache directives and can override the simple cache policy generation. Do not set `no-store: true` together with `cache-public: true` and `max-age: 365d` and expect a consistent policy.

### Choosing TTL based on file mutability

- Files **without a version in the URL** like `/css/app.css` should use a conservative TTL or require revalidation, since contents can change after deployment.
- Files **with a content hash in the name** like `/css/app-<hash>.css` are good candidates for a long TTL, because new versions carry new URLs.
- Frontend `index.html` usually needs a short cache lifetime or revalidation so it learns about new assets; keeping HTML cached too long can leave the page pointing to old or deleted assets.

Use:

~~~bash
curl -i http://localhost:8080/assets/hello.txt
~~~

to inspect actual headers. Do not conclude the browser cached a file just because YAML has `period`; verify `Cache-Control` and the browser's Network tools.

### Conditional requests and Last-Modified

`spring.web.resources.cache.use-last-modified` defaults to `true`. When the resource and handler have suitable modification timestamp metadata, the response can include `Last-Modified`. Clients send `If-Modified-Since` when revalidating; if unchanged, the server can return `304 Not Modified`.

`ETag` is a separate mechanism; do not assume every static resource always includes an ETag simply because `use-last-modified=true`. For files inside classpath/JARs, metadata and caching behavior can differ from filesystem files.

## 10. Resource chain: internal caching and versioning

The resource chain handles resource resolution, version strategies, and related steps. Distinguish:

- **HTTP cache**: browser/proxy reuses responses according to `Cache-Control`.
- **`spring.web.resources.chain.cache`**: caches lookup results inside the **server-side resource chain**; it does not determine browser TTL.
- **Version strategy**: produces versioned URLs to prevent mixing new assets with stale ones.

Example enabling the chain:

~~~yaml
spring:
  web:
    resources:
      chain:
        enabled: true
        cache: true
~~~

The default value of `chain.cache` is `true`, though it only applies when the resource chain is active. The resource chain can enable itself automatically when a relevant strategy is configured; check the property reference for your specific version.

### 10.1. Content hash strategy

~~~yaml
spring:
  web:
    resources:
      chain:
        strategy:
          content:
            enabled: true
            paths:
              - "/css/**"
              - "/js/**"
~~~

Conceptually, the resource handler can resolve versioned URLs:

~~~text
/css/app-<content-hash>.css
/js/app-<content-hash>.js
~~~

`<content-hash>` is a **placeholder**, not an actual hash value. When contents change, the version in the URL changes.

**Key point:** merely enabling the property **does not rewrite every hardcoded URL inside a static HTML page**. For HTML to reference the hashed URLs, you need URL generation/rewriting (for example URL rewriting integration in Spring MVC/templates, `ResourceUrlProvider`) or a frontend bundler that already generates hashed asset filenames. Inspect rendered HTML and live requests to verify the version strategy works.

### 10.2. Fixed version strategy

~~~yaml
spring:
  web:
    resources:
      chain:
        strategy:
          fixed:
            enabled: true
            version: "v12"
            paths:
              - "/js/lib/**"
~~~

With proper versioned URL generation, the asset `/js/lib/library.js` can be referenced as `/v12/js/lib/library.js`. The physical file does not need to sit inside a directory named `v12`. Each release must update the version consistently and ensure HTML points to the deployed version.

You can use the content strategy for application code and the fixed strategy for libraries, but keep `paths` cleanly separated to avoid unpredictable pattern overlaps.

### 10.3. Precompressed resources

~~~yaml
spring:
  web:
    resources:
      chain:
        compressed: true
~~~

The resource chain can serve precompressed `.gz` or `.br` versions if the artifact contains those files and the HTTP client sends a matching `Accept-Encoding`. It **does not automatically compile or compress** all JS/CSS at runtime. Verify the generated files in the build output, `Content-Encoding`, and `Vary` headers; dynamic server compression is a separate configuration feature.

## 11. Disabling auto mapping or adding a custom handler

### Disabling Boot-registered mappings

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

This disables **Boot's default static resource handling**, which is useful for API-only services or apps managing their own resource handlers. Controllers and other custom mappings continue working; this property is not a switch to disable all HTTP endpoints.

### Adding a custom mapping in MVC

When requirements go beyond properties, you can add a resource handler. This is a **Java configuration fragment** placed in an MVC app with Spring dependencies, not a standalone Java class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ExtraAssetsConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/");
    }
}
~~~

The snippet above adds a `/manuals/**` mapping to `classpath:/manuals/`. It does not alter `spring.web.resources.static-locations` and does not require disabling default mappings. Avoid using `@EnableWebMvc` solely to add one mapping: that annotation alters how Boot auto-configures MVC and can stop many default behaviors from working as expected.

In WebFlux, use `WebFluxConfigurer.addResourceHandlers` and `ResourceWebHandler` respectively; do not use MVC APIs to configure a reactive app.

## 12. Welcome page, WebJars, APIs, and SPA routing

**Welcome page:** `index.html` in configured static locations can act as the welcome page at `/`, with proper precedence relative to controllers/routers. When locations change, welcome page lookup follows the new locations. However, do not infer that every frontend path falls back to `index.html`.

**WebJars:** WebJar resources are packaged inside JARs in a specific layout. Boot commonly maps `/webjars/**`, configurable via `spring.mvc.webjars-path-pattern` or `spring.webflux.webjars-path-pattern` depending on the stack. Do not confuse this with arbitrarily dumping JS libraries at the classpath root.

**API routes:** with the `/**` static pattern, the resource handler can catch a request unhandled by any controller and report a missing resource. Thus an error for `/api/unknown` sometimes manifests as a missing static resource error rather than proving an API controller exists. Check routes/controllers, `HandlerMapping` order, and URL paths before changing code.

**SPA routing:** a React/Vue app using a client-side router may load `/` yet return 404 when reloading `/dashboard`. You must design a fallback at the proxy or controller/routing layer for frontend routes. Never return `index.html` for `/api/**` or every resource error, as doing so can turn real API errors into 200 HTML responses.

## 13. Inspecting packaged artifacts and operations

In the created Gradle project, run:

~~~bash
./gradlew bootJar
~~~

Then inspect the files inside the JAR:

~~~bash
jar tf build/libs/your-app.jar
~~~

`your-app.jar` is an illustrative name; use your actual built filename. In an executable Boot JAR for the lab example, look for entries matching:

~~~text
BOOT-INF/classes/frontend/hello.txt
BOOT-INF/classes/frontend/css/site.css
~~~

If it works under `bootRun` yet fails when running the JAR, inspect the packaged files and runtime profiles/configuration before blaming Spring's handler. For `file:/opt/my-app/public-assets/`, files **do not need** to be inside the JAR; they must exist on the host/container running the service.

To verify after deployment, record:
- The actual URL requested by the browser, including context path and proxy prefix.
- Spring MVC vs. WebFlux, the corresponding `static-path-pattern`, and effective locations list.
- Status codes/headers: 200, 304, 404, 302, 401, 403; `Cache-Control`, `Last-Modified`, `Content-Type`, `Content-Encoding`.
- Whether the file contents exist in the artifact or runtime directory.
- Whether the security/filter chain permits public static routes.

## 14. Common errors and how to diagnose them

| Symptom | Common cause | Resolution |
|---|---|---|
| `GET /css/app.css` returns 404 after URL change | `spring.mvc.static-path-pattern=/assets/**` | Try `/assets/css/app.css`; verify pattern matches the stack |
| `/assets/css/app.css` returns 404, file is still in `static/css` | `static-locations` was changed to `classpath:/frontend/` | Move the file or include `classpath:/static/` in the list |
| Works locally, JAR lacks the file | File placed in wrong folder or excluded from artifact | Run `jar tf`, check `BOOT-INF/classes` |
| Changing `spring.mvc.*` has no effect | App runs WebFlux | Use `spring.webflux.static-path-pattern` |
| `add-mappings=false` makes public files disappear | Boot no longer registers the static handler | Re-enable or add a manual handler |
| Stale JS/CSS after deployment | Same URL with long cache duration | Use versioned/hashed URLs, review `index.html` TTL |
| Content strategy enabled yet HTML still requests old URL | Missing URL rewriting step | Integrate `ResourceUrlProvider`/templates or a bundler |
| Compressed enabled yet no gzip/br returned | Missing precompressed files or client didn't request it | Check build outputs, `Accept-Encoding`, and headers |
| `file:` works on host yet breaks in container | Container lacks the directory, mount, or permissions | Verify the exact path inside the container |
| Static request returns 302/401/403 | Security or proxy acts before the handler | Inspect filter chain and public asset policies |
| `/shop/assets/logo.svg` returns 404 | Mismatch across URL prefix, context path, and proxy rewrite | Trace external URL → internal URL → pattern → location |
| SPA navigation works via click yet F5 on deep route fails | Missing fallback from frontend router to `index.html` | Add fallback for frontend routes while keeping API routes accurate |
| API path throws missing static resource error | Default `/**` static handler caught it when no controller matched | Check controller mappings and consider `/assets/**` prefix |

### Sequence for debugging a 404 error

1. Record the exact request URL from the Network tab or `curl`.
2. Verify context path and proxy rewrites.
3. Identify MVC vs. WebFlux and the active `static-path-pattern`.
4. Strip the URL prefix to isolate the relative resource path.
5. Inspect the effective `static-locations`; remember custom values replace defaults.
6. Verify the file exists inside the JAR or runtime directory, not only in IDE sources.
7. If the file exists, check custom handlers, Security/filters, and route precedence.
8. Finally, adjust caching, restart, or invalidate CDN based on actual headers.

**Segment-by-segment example:** URL `/shop/assets/css/site.css`, context path `/shop`, pattern `/assets/**`, and location `classpath:/frontend/` mean Spring looks for `classpath:/frontend/css/site.css`; not `frontend/assets/css/site.css`.

## 15. Safety and verification checklist

- [ ] Clearly distinguish URL pattern, relative resource path, classpath/file location, and context path.
- [ ] Choose the right URL property for MVC or WebFlux.
- [ ] Every custom location actually exists in the JAR or runtime environment.
- [ ] If default resources are still needed, required locations were re-declared.
- [ ] Do not expose directories holding secrets, backups, or unauthorized uploads.
- [ ] CSS/JS/versioned URLs and `Cache-Control` match the deployment strategy.
- [ ] Verify `/`, asset links, API paths, and SPA deep links independently.
- [ ] Verify HTTP status, `Content-Type`, `Cache-Control`, and 304 when applicable.
- [ ] Do not use `@EnableWebMvc`/`@EnableWebFlux` solely to change one URL.
- [ ] Test running from the packaged JAR/container and verify real folders/paths before production.

## 16. Self-check exercises

**Question 1.** At what URL is `src/main/resources/static/images/logo.svg` served under default configuration and no context path?

**Answer:** `/images/logo.svg`.

**Question 2.** If `static-locations=classpath:/frontend/` is set, will `classpath:/static/` still be searched automatically?

**Answer:** No. A custom list replaces defaults; to retain it, re-declare it.

**Question 3.** Given `frontend/docs/guide.pdf`, MVC pattern `/assets/**`, and location `classpath:/frontend/`, what is the right URL?

**Answer:** `/assets/docs/guide.pdf`.

**Question 4.** To change static URLs in WebFlux, which property is appropriate?

**Answer:** `spring.webflux.static-path-pattern`, not `spring.mvc.static-path-pattern`.

**Question 5.** Is `cache.period=1h` the same as `chain.cache=true`?

**Answer:** No. One configures the HTTP cache policy for clients; the other caches server-side resource resolution.

**Question 6.** Why does a static HTML page with hardcoded `/css/app.css` still request the old URL even after enabling the content hash strategy?

**Answer:** You need a versioned URL generation/rewriting mechanism or a bundler emitting hashed URLs; enabling the strategy does not rewrite hardcoded strings automatically.

**Question 7.** Why shouldn't you serve an entire user upload directory via `file:`?

**Answer:** It risks exposing private files, path traversal, broken access control, and caching sensitive data. Use authentication, authorization, and an appropriate file storage/download endpoint.

**Extended lab:** in the section 5 example, create `frontend/docs/readme.txt` containing `Docs ready`. Access `/assets/docs/readme.txt`. Then change only `spring.mvc.static-path-pattern` to `/files/**`; predict the new URL `/files/docs/readme.txt` and verify that moving the file is unnecessary. Use `curl -i` to observe cache headers when changing `cache.period` from `10m` to `1h`.

## 17. References

- [Spring Boot — Servlet Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications / Static Content](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html)
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)

**Remember:** `spring.web.resources.static-locations` specifies **where to read files from**; `spring.mvc.static-path-pattern` or `spring.webflux.static-path-pattern` specifies **which URLs route to the handler**; `spring.web.resources.cache.*` and `spring.web.resources.chain.*` govern **caching and versioning**. Verify URLs, artifacts, and HTTP responses when evaluating configuration.
