# Customizing resource handlers and avoiding API conflicts

A Spring Boot application can serve both **REST APIs** (e.g., `/api/orders`) and **static resources** (CSS, JavaScript, images, fonts, PDFs, favicons). In Spring MVC, both groups typically pass through the same **DispatcherServlet**, yet are processed by different handlers. Proper configuration keeps browsers loading assets reliably, ensures APIs preserve their status/body contracts, and prevents paths from being shadowed by catch-all rules or SPA fallbacks.

This lesson uses **Spring Boot 3.x, Java 17+, Spring MVC (Servlet)**. Examples center on a clear, verifiable organization: **/api/** for business endpoints, **/assets/** for public files. Spring WebFlux has an equivalent resource handler mechanism using **WebFluxConfigurer** and distinct properties; do not copy `WebMvcConfigurer` code verbatim into WebFlux.

## 1. Objectives

After studying this lesson, you will be able to:

1. Explain how Spring MVC selects **RequestMappingHandlerMapping** for controllers and **ResourceHttpRequestHandler** for static files.
2. Distinguish **URL patterns** (e.g., `/assets/**`) from **resource locations** (e.g., `classpath:/site-assets/`).
3. Customize asset serving using **spring.mvc.static-path-pattern**, **spring.web.resources.static-locations**, or **WebMvcConfigurer.addResourceHandlers(...)** according to your needs.
4. Maintain boundaries across **/api/**, **/assets/**, **/actuator/**, and other routes; understand the effects of catch-all routes, SPA fallbacks, and exception handling.
5. Design appropriate caching, URL versioning, access control, and CORS; prevent internal files from becoming public downloads.
6. Write integration tests proving APIs are not shadowed by static handlers and valid/missing files return sensible statuses.

Prerequisites: familiarity with Java annotations, Spring Boot auto-configuration, `@RestController`/`@GetMapping`, HTTP statuses, JSON, `src/main/resources` layout, and running Gradle/Maven.

## 2. Where does the resource handler sit in the HTTP flow?

### 2.1. Two handler groups with different responsibilities

~~~text
HTTP request
      |
      v
Servlet filter chain (e.g., Spring Security if enabled)
      |
      v
DispatcherServlet
      |
      +--> RequestMappingHandlerMapping
      |       +--> @RestController / @Controller (@GetMapping,...)
      |       +--> handler method -> service -> JSON / status
      |
      +--> ResourceHandlerMapping
              +--> ResourceHttpRequestHandler
              +--> search files in resource locations
              +--> respond with CSS / JS / PNG / fonts / PDF
~~~

This diagram is a conceptual model. `DispatcherServlet` checks **HandlerMappings in priority order** and invokes the first matching handler. In a typical Spring MVC setup, controller mappings are evaluated before static resource mappings. Thus, a properly registered `@GetMapping("/api/status")` still handles its requests even when the default static mapping is `/**`.

**Still, do not rely on priority ordering alone when designing URLs.** The `/**` mapping can act as a fallback for nonexistent API routes, sending 404 errors through the static resource path rather than an API controller flow. A catch-all controller, SPA fallback, or custom `HandlerMapping` with an improper order can create real collisions. Separating namespaces and writing tests remain the safest approach.

### 2.2. A URL pattern is not a file path

Given:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/site-assets/");
~~~

a request **`GET /assets/css/site.css`** requests the content of **`classpath:/site-assets/css/site.css`**. The `/assets/` segment is the **public URL prefix**, whereas `site-assets/` is **where resources are looked up inside the application**. Users should not infer from the URL that files sit at `/assets` on disk.

**`@GetMapping("/api/status")`** maps requests to a Java method; **`addResourceHandler("/assets/**")`** maps requests to resource lookup. Do not place APIs under `/assets/**` or static files under `/api/**`, even if current handler precedence happens to resolve them.

### 2.3. What does Spring Boot do by default?

With Spring MVC auto-configuration and standard web starters, Spring Boot searches static resources in these classpath locations:

- **classpath:/static/**
- **classpath:/public/**
- **classpath:/resources/**
- **classpath:/META-INF/resources/**

By default, static content uses the **`/**`** pattern. For instance, **`src/main/resources/static/css/site.css`** can be requested at **`GET /css/site.css`**. The handler is **`ResourceHttpRequestHandler`**; it locates resources, determines content types, and supports caching/conditional requests. For executable JARs, place assets in **`src/main/resources`** so they are packaged onto the classpath; **`src/main/webapp`** is not a reliable option for all executable JARs.

**404 note:** When the default static handler is `/**`, a request like **`GET /api/nonexistent`** can still be caught by a resource handler as a resource path. Starting with Spring Framework 6.1 (Spring Boot 3.3), when no file is found, **`NoResourceFoundException`** is normally handled as HTTP **404**. When moving the static mapping to `/assets/**` and no API mapping exists, the path goes through **`NoHandlerFoundException`**. The HTTP status is still 404, yet the exception differs; an overly broad `@ControllerAdvice` catching all `Exception`s indiscriminately could convert it into the wrong body/status.

## 3. Designing namespaces to avoid conflicts

A maintainable URL contract:

| URL prefix | Owner | Examples | Rule |
| --- | --- | --- | --- |
| **/api/** | REST controllers | `/api/status`, `/api/orders/42` | JSON/status per API contract; never used for assets. |
| **/assets/** | `ResourceHttpRequestHandler` | `/assets/css/site.css`, `/assets/logo.svg` | Public files only; GET/HEAD, 404 when missing. |
| **/actuator/** | Spring Boot Actuator if dependency added | `/actuator/health` | Operational endpoints with separate exposure/security. |
| **/webjars/** | WebJars mechanism if used | `/webjars/...` | Keep intentionally mapped when frontend JAR libraries are needed. |
| **/** or UI routes | UI and SPA navigation | `/`, `/products/42` | HTML fallback only for real navigation; must not cover APIs/assets. |

These prefixes are **lesson design conventions**, not mandatory Spring keywords. In practice you can use `/static/**`, `/public-assets/**`, or a dedicated domain/CDN, provided the rules are clear and tested.

**Important design points:**

- Use a specific static prefix such as **/assets/** instead of registering a custom resource handler on **`/**`** or **`/api/**`**.
- Do not create an overly broad API controller matching every path and expect static files to always win. `HandlerMapping` uses **order**, not merely comparing pattern specificity across different handler mapping types.
- If the frontend runs as an SPA, only return **`index.html`** for **GET/HEAD navigation accepting `text/html`**; do not turn misspelled APIs, missing CSS files, or POST requests into 200 HTML.
- Never place private uploads or config files (`application.yml`, `.env`, credentials, logs, source code) inside public resource locations.
- When changing servlet context path or running behind a reverse proxy, remember external application prefixes can make the full URL differ from internal `DispatcherServlet` path mappings.

## 4. Approach 1: Use Spring Boot properties alone when special resource logic is unnecessary

If all assets are packaged files and you only want to move static URLs from `/**` to `/assets/**`, prefer built-in configuration.

**src/main/resources/application.yml**

~~~yaml
spring:
  mvc:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
~~~

Place **`src/main/resources/static/css/site.css`**. The file is served at:

~~~text
GET /assets/css/site.css
~~~

In the configuration above, **`spring.mvc.static-path-pattern`** is the URL pattern for MVC static content auto-config. **`spring.web.resources.static-locations`** specifies where Spring Boot searches for resources, and setting it **replaces the default static locations list**. If you still need `/public` or `/META-INF/resources`, add them back deliberately. Do not add another Java handler on `/assets/**` just to duplicate configuration.

Pros: minimal code, preserves auto-configuration and related defaults. Limits: when you need multiple prefixes with distinct caching, specialized locations, custom resolvers/transformers, or path-based versioning, you need a custom **`WebMvcConfigurer`**.

**Note when changing `static-path-pattern`:** paths to favicons, index, WebJars, welcome pages, or templates may need adjustment depending on how the application actually uses them. Do not treat changing the prefix as an operation affecting only CSS; test your UI's primary URLs.

## 5. Approach 2: Custom resource handler with WebMvcConfigurer

When you need explicit control over URLs and locations, create an MVC configuration bean. To give this example **only one static namespace `/assets/**`** without keeping the default `/**` fallback, disable **Spring Boot's automatic static mappings** with **`spring.web.resources.add-mappings=false`**, then register the handler manually. This also removes default automatic resource/welcome page behaviors: choose this approach only when the application controls the paths it serves.

**Important:** **`spring.web.resources.add-mappings=false`** disables registration of **Boot's default resource handler**; it does not prevent **`WebMvcConfigurer.addResourceHandlers(...)`** from registering handlers you write yourself. The simpler approach in section 4 is usually sufficient if fine-grained control is unnecessary.

### 5.1. Creating the project

Create a Spring Boot 3.x project via Spring Initializr with:

- Java 17+, group **`com.example`**, artifact **`resource-routes`**, package **`com.example.resourceroutes`**.
- Dependencies **Spring Web** and **Spring Boot Starter Test**.
- Gradle build tool with the generated Gradle wrapper.

File tree to add:

~~~text
resource-routes/
  src/
    main/
      java/com/example/resourceroutes/
        ResourceRoutesApplication.java
        ApiController.java
        StaticAssetsConfig.java
      resources/
        application.yml
        site-assets/
          css/
            site.css
          js/
            app.js
    test/
      java/com/example/resourceroutes/
        RouteIsolationTest.java
~~~

No standalone Tomcat installation is needed since the Web starter includes the appropriate embedded server.

### 5.2. Main

**src/main/java/com/example/resourceroutes/ResourceRoutesApplication.java**

~~~java
package com.example.resourceroutes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceRoutesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceRoutesApplication.class, args);
    }
}
~~~

The main class resides in the parent package so component scanning finds the controller and configuration in the same package.

### 5.3. Dedicated API at /api/**

**src/main/java/com/example/resourceroutes/ApiController.java**

~~~java
package com.example.resourceroutes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    public record Status(String status) { }

    @GetMapping("/api/status")
    public Status status() {
        return new Status("ok");
    }
}
~~~

The controller returns a Java record, serialized by Spring Web's Jackson into JSON:

~~~json
{"status":"ok"}
~~~

Do not add `@GetMapping("/assets/**")` to a controller; if you have a business requirement for authenticated user file downloads, build a dedicated endpoint with authorization and appropriate response headers rather than mixing it with public assets.

### 5.4. Custom resource handler

**src/main/java/com/example/resourceroutes/StaticAssetsConfig.java**

~~~java
package com.example.resourceroutes;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class StaticAssetsConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/site-assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10))
                        .cachePublic());
    }
}
~~~

**Explanation:**

1. **`WebMvcConfigurer`** adds a piece of MVC configuration while preserving the rest of Spring Boot's setup. **Do not add `@EnableWebMvc`** solely to declare a handler; `@EnableWebMvc` shifts broader MVC configuration responsibility to you and causes many of Boot's MVC auto-configurations to stop applying.
2. **`addResourceHandler("/assets/**")`** declares the public URLs handled by the resource handler.
3. **`addResourceLocations("classpath:/site-assets/")`** sets the root of allowed files. The trailing **`/`** at the end of the location ensures relative paths join properly.
4. **`setCacheControl(...)`** returns cache headers for assets. 10 minutes is simply a balanced sample duration when filenames are unhashed; choose production policies based on actual file update practices.
5. **Do not register `"/**"`** because it would cover non-asset paths. Do not register `"/api/**"` on the resource handler.

Spring Framework can serve resources with a **`Last-Modified`** header and handle matching conditional requests. `Cache-Control` applies only to responses from the resource handler; it does not automatically cache JSON responses from `@RestController`.

### 5.5. Disabling only Boot's default static mappings

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: resource-routes
  web:
    resources:
      add-mappings: false

server:
  port: 8080
~~~

This application publishes assets exclusively under the custom **`/assets/**`** mapping; **`/api/status`** still belongs to `@RestController`. This setting **does not disable Spring MVC, controllers, JSON conversion, or `DispatcherServlet`**. It disables automatic resource mappings, so if you previously relied on `/webjars/**` or the default welcome page, you must design them explicitly.

Do not simultaneously copy the configuration from **section 4** into this project and expect both mechanisms to combine seamlessly. Sections 4 and 5 are **two separate implementation options** for the same goal; pick one clear static URL management model.

### 5.6. Creating sample assets

**src/main/resources/site-assets/css/site.css**

~~~css
body {
    background-color: #f5f7ff;
}
~~~

**src/main/resources/site-assets/js/app.js**

~~~javascript
console.log("assets ready");
~~~

These files are packaged on the executable JAR's classpath. Do not place them under **`src/main/java`** or confuse **`classpath:/site-assets/`** with an external disk directory path.

### 5.7. Running and manual verification

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell or CMD:

~~~text
gradlew.bat bootRun
~~~

Second terminal:

~~~bash
curl -s http://localhost:8080/api/status
curl -s http://localhost:8080/assets/css/site.css
curl -s http://localhost:8080/assets/js/app.js
~~~

Expected response bodies respectively:

~~~json
{"status":"ok"}
~~~

~~~css
body {
    background-color: #f5f7ff;
}
~~~

~~~javascript
console.log("assets ready");
~~~

Inspect headers and statuses:

~~~bash
curl -i http://localhost:8080/assets/css/site.css
curl -i http://localhost:8080/assets/missing.css
curl -i http://localhost:8080/api/missing
~~~

Observed outcomes: existing files return **200**, missing files and missing APIs both return **404** under this setup. CSS normally includes **`Content-Type: text/css`** and the configured **`Cache-Control`**. Do not assert exact error bodies or every header verbatim, as they depend on the Spring Boot minor version, error handler configuration, and environment.

Verify resources inside the JAR by running **`./gradlew bootJar`** and listing entries using JDK/zip tools. Classpath files are typically packaged under **`BOOT-INF/classes/site-assets/`**. If it works from the IDE yet the JAR returns 404, inspect actual resource paths inside the artifact rather than randomly changing handler mappings.

## 6. Integration tests verifying the boundary between assets and APIs

A path change can break APIs even when you only intended to adjust CSS. Therefore, test both **positive** cases (valid assets and APIs) and **negative** cases (nonexistent routes returning 404).

**src/test/java/com/example/resourceroutes/RouteIsolationTest.java**

~~~java
package com.example.resourceroutes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteIsolationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void apiRouteKeepsJsonContract() throws Exception {
        mvc.perform(get("/api/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void assetRouteServesClasspathFile() throws Exception {
        mvc.perform(get("/assets/css/site.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/css")))
                .andExpect(content().string(
                        containsString("background-color: #f5f7ff;")));
    }

    @Test
    void missingAssetIsNotAnApiResponse() throws Exception {
        mvc.perform(get("/assets/not-found.css"))
                .andExpect(status().isNotFound());
    }

    @Test
    void missingApiDoesNotBecomeHtml() throws Exception {
        mvc.perform(get("/api/not-found"))
                .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
./gradlew test
./gradlew bootJar
~~~

**Why are these tests valuable?**

- Verifies `@RestController` still returns JSON with status **`ok`**. Simply checking HTTP 200 across requests is insufficient.
- Verifies static content carries **`text/css`** and the exact file contents, rather than accidentally returning an SPA's HTML index with status 200.
- Verifies invalid asset URLs return 404 instead of unintentionally redirecting to login or UI.
- Verifies invalid API URLs return 404 rather than hitting an SPA fallback returning **`index.html`** with status 200.
- Later, if you add Spring Security, add tests covering roles and unauthenticated requests; valid 401/403 statuses per security policy may differ from the initial baseline.

This is a **Spring MVC test via `MockMvc`**, starting the application context without opening a real TCP port. When verifying reverse proxies, HTTPS, servlet context paths, CDNs, or gateway routing, add tests over real HTTP.

## 7. Why can mappings conflict even when code looks reasonable?

### 7.1. Default `/**` static handler catching unmapped API requests

Suppose `@GetMapping("/api/orders")` exists, yet a client calls **`/api/order`** (missing the `s`). In default Boot, **`RequestMappingHandlerMapping`** finds no match, and then the **`/**` resource mapping** can receive the request as a filename. `ResourceHttpRequestHandler` searches for a file, fails, and throws **`NoResourceFoundException`** (Spring Framework 6.1+). The default response remains 404.

**Consequence:** if a `@ControllerAdvice` has **`@ExceptionHandler(Exception.class)`** always returning 500, missing route errors can accidentally turn into 500s. Do not conclude the resource handler “stole” a valid API; the issue is **unmapped API fallback** and **error formatting**.

Design solution: change the static URL to **`/assets/**`** as in section 4, or disable auto static `/**` and register a custom `/assets/**` as in section 5; keep exception handling properly categorized. If APIs must return a uniform problem JSON, configure error handlers for **`NoHandlerFoundException`**, **`NoResourceFoundException`**, and API errors in their proper scopes.

### 7.2. Catch-all controller encroaching on assets

A controller with an overly broad pattern matching all requests or a `RouterFunction` with higher order can intercept **`/assets/css/site.css`** before the resource handler and return HTML or JSON instead. Result: the asset returns 200, yet the browser reports a MIME type error, CSS is ignored, and JavaScript fails to run.

Solution: restrict controllers to **`/api/**`** and required UI routes. Avoid the rule “every non-API URL returns `index.html`” unless you exclude assets, actuator, webjars, and genuine error paths. When URLs overlap, inspect **`HandlerMapping` order** rather than comparing only pattern specificity across two separate handler mappings.

### 7.3. SPA fallback swallowing 404s

In an SPA frontend, a browser may navigate directly to **`/products/42`** and expect **`index.html`** so the client router handles it. However, a naive fallback like **every GET → `index.html`** can cause:

~~~text
GET /api/unknown        -> 200 text/html  (wrong)
GET /assets/missing.js  -> 200 text/html  (wrong)
GET /products/42        -> 200 text/html  (potentially right for SPA navigation)
~~~

Only fall back for **GET/HEAD navigation** carrying **`Accept: text/html`**, after excluding API, asset, management, authentication prefixes, and file extensions per your architecture. Return genuine 404s for missing assets/APIs. Another option is delegating all static/SPA fallback to a reverse proxy or CDN, leaving Spring Boot to handle `/api/**` only. Choose **one** owner for fallback routing and add integration tests for both deep links and invalid URLs.

### 7.4. WebMvcConfigurer versus @EnableWebMvc

**`@Configuration + implements WebMvcConfigurer`** adds rules onto Spring Boot's existing MVC auto-configuration. **`@EnableWebMvc`** switches MVC configuration to a manual mode, which can alter static mappings, message converters, WebJars, or the welcome page. Do not add `@EnableWebMvc` as a random fix when a handler fails to match.

If you only need to change a prefix, consider Boot properties first. If you need custom resolvers, locations, or distinct caching, use `addResourceHandlers` with patterns that do not overlap APIs. Choose `@EnableWebMvc` only when you intentionally want full manual MVC configuration and understand which defaults you must re-declare.

### 7.5. Exact pattern duplication across multiple handlers

Another `WebMvcConfigurer` or auto-config may also register **`/assets/**`**. Outcomes depend on registry/condition order; you might get a handler that ignores your expected location instead of naturally “merging” file roots. Do not treat multiple `addResourceHandler` calls for the same pattern as a default location-merging mechanism.

Solution: centralize ownership of the `/assets/**` mapping, or intentionally supply multiple **`addResourceLocations(...)`** on **a single** registration when multiple lookup folders are required. Keep the locations list short and never expose internal directories.

## 8. Adding locations, caching, and controlled versioning

### 8.1. Multiple file sources in one namespace

Example **illustrating only a method fragment**, not a standalone Java file:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations(
                "classpath:/site-assets/",
                "classpath:/shared-public-assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofMinutes(10)));
~~~

Spring searches configured locations in order. If two files share the same relative path, location order influences which file is returned; do not create colliding names expecting automatic resolution by context. Never arbitrarily add **`classpath:/`** because it widens searchable files beyond intended boundaries.

**Files outside the JAR:** Spring supports file resource locations such as **`file:/srv/app/public-assets/`** on Linux. Only use a directory explicitly designated as public, with defined read permissions/ownership and an update strategy. Never map an entire home directory, private upload folder, or root filesystem.

### 8.2. Caching and hashed URLs

With stable filenames like **`/assets/css/site.css`**, long caching can keep users on stale versions after deployment. There are two strategy categories:

| Resource | URL / update approach | Recommended caching |
| --- | --- | --- |
| Unversioned CSS/JS | Fixed name; server may update contents | Short cache or require revalidation. |
| Content-hashed CSS/JS | E.g., `site-<hash>.css`; URL changes when bytes change | Long/immutable cache works well if the pipeline ensures correct URLs and old assets remain available during rollout. |
| SPA index HTML | Usually references new JS/CSS versions | Short cache or `no-cache`/revalidation to avoid pointing to stale bundles. |
| Sensitive or per-user files | Outside public asset roots | Serve via authorized endpoints with dedicated cache policies. |

Spring MVC provides **`VersionResourceResolver`** and the resource chain for versioned URLs. Alternative replacement method fragment (do not use simultaneously with the previous registration):

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/site-assets/")
        .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic())
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
~~~

This addition requires importing **`org.springframework.web.servlet.resource.VersionResourceResolver`**. It registers the content-version resolution strategy, yet **does not automatically rewrite hardcoded URL strings inside HTML/JS**. Generate proper public URLs via **`ResourceUrlProvider`** or an appropriate frontend build pipeline; verify generated hashed paths are accessible and old assets behave smoothly during rolling deployments. With unchanged filenames, do not slap a one-year cache onto `/assets/**` merely because `VersionResourceResolver` was added.

When serving CSS/JS through a CDN, align **`Cache-Control`, compression, content type, and invalidation** between origin and CDN. Do not delete old assets immediately while client-cached HTML still references those versions.

### 8.3. MIME types and conditional requests

`ResourceHttpRequestHandler` determines media types from resources, so CSS should return **`text/css`**, JavaScript a valid JavaScript media type, and images an appropriate `image/*` type. Never serve arbitrary files as `text/html`. Browsers may refuse to execute scripts or stylesheets if MIME types are wrong, especially when **`X-Content-Type-Options: nosniff`** is active.

When the server has suitable metadata, conditional requests like **`If-Modified-Since`** can return **`304 Not Modified`** to save bandwidth. Cache headers and versioning are separate mechanisms; 304 does not mean a new file was generated, and long caching does not guarantee versioned URLs are generated properly.

## 9. Security: do not confuse a static handler with access control

### 9.1. Public resource locations are a security decision

**`addResourceLocations(...)`** declares directories searchable for public serving. Although Spring Framework validates paths and applies resource handler protections, you must still never map directories holding configs, credentials, private reports, or user uploads. Never write a custom handler that builds file paths by directly appending user input into **`new File(...)`** and reading arbitrarily.

If users are only allowed to download files when authorized, design a dedicated download controller/endpoint checking identity, authorization, MIME type, filename, `Content-Disposition`, and size limits rather than publishing that folder as static assets.

### 9.2. Spring Security if the project includes the Security starter

The resource handler **does not automatically bypass the Spring Security filter chain**. Once Spring Security is added, you must decide which assets are public and which APIs require authentication. The example below is an **illustrative additional configuration** that compiles only when the project includes the Spring Security dependency and corresponding imports; it is not part of the minimal Spring Web project in section 5:

~~~java
package com.example.resourceroutes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/assets/**")
                        .permitAll()
                        .requestMatchers(HttpMethod.HEAD, "/assets/**")
                        .permitAll()
                        .requestMatchers("/api/**")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

This is a minimal example demonstrating **permission separation**, not a complete production security configuration: real apps need proper authentication, HTTPS, CSRF handling, API authentication, session/cookie policies, and system-specific routes. An unauthenticated request to a mistyped API URL may receive 401/403 before route existence is revealed; test public and protected routes against your contract. Never open **`/api/**`** to everyone merely because a frontend client needs to fetch public images.

### 9.3. CORS

CORS controls whether JavaScript from another origin can **read responses**; it does not replace authentication or file access control. When frontend and API share the same origin, extra CORS configuration is usually unnecessary. If the frontend uses a different origin, configure CORS deliberately for **`/api/**`** and assets separately if needed; avoid broad wildcards on credentialed endpoints.

Illustrative **`WebMvcConfigurer` method fragment** when needed for a cross-origin frontend:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/assets/**")
            .allowedOrigins("https://frontend.example")
            .allowedMethods("GET", "HEAD");
}
~~~

Requires importing **`org.springframework.web.servlet.config.annotation.CorsRegistry`**. When Spring Security is also enabled, integrate CORS properly within the security filter chain; adding MVC CORS alone may not suffice when Security blocks preflight requests.

## 10. Distinguishing Spring MVC, WebFlux, servlet context path, and reverse proxies

- **Spring MVC:** configure URLs via **`spring.mvc.static-path-pattern`** or `WebMvcConfigurer.addResourceHandlers`; primary handler is **`ResourceHttpRequestHandler`**.
- **Spring WebFlux:** uses **`spring.webflux.static-path-pattern`**, **`WebFluxConfigurer.addResourceHandlers`**, and **`ResourceWebHandler`**. Do not import `WebMvcConfigurer` into a pure WebFlux app expecting it to execute as Servlet.
- **`server.servlet.context-path=/shop`** (Servlet): internal route **`/api/status`** has external URL **`/shop/api/status`** unless rewritten by a proxy. Assets similarly become **`/shop/assets/css/site.css`**.
- **Reverse proxy or CDN:** may rewrite prefixes, cache, or route static assets separately. When getting 404s, verify **whether requests even reached Spring Boot** before changing `@GetMapping`/`addResourceHandlers`.
- **Spring Actuator:** manages operational endpoints and can run on a separate management port; never cover `/actuator/**` with an SPA fallback or expose sensitive endpoints just to make UI features work.

If a project includes both Spring Web and WebFlux dependencies, auto-configuration rules select the web application type; do not assume `WebFluxConfigurer` beans take effect in a Servlet runtime. Verify the active web stack and test directly over HTTP.

## 11. Diagnosing errors by symptom

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| **GET /assets/css/site.css → 404** | URL prefix, resource location, filename/case, or resource omitted in build | Check pattern and relative path inside the JAR; test a simple file. |
| **GET /api/status → 404** | `@RestController` not scanned, method/path mismatch, context path/proxy rewrite | Inspect startup mappings and MockMvc test; check host/port/prefix. |
| **GET /api/unknown → 500** | `@ControllerAdvice` catches `NoResourceFoundException` as a server error | Identify the exception type and 404 handling rules; narrow the static handler. |
| **CSS/JS returns 200 yet browser reports MIME error** | SPA fallback returns HTML or proxy returns an error page with HTTP 200 | Check Network tab: response body and `Content-Type`, not just status. |
| **Resources prompt for login** | Spring Security filter chain blocks assets | Check `requestMatchers` for `/assets/**` and actual public policy. |
| **JS/CSS still stale after deployment** | `Cache-Control` too long, unchanged URL, CDN/browser cache | Inspect response headers and request URLs; add versioning/hashing. |
| **`/webjars/**` suddenly returns 404** | Disabled default `add-mappings` or changed mappings without re-declaring | Check WebJars dependency and registered resource handlers. |
| **`/assets` works locally yet fails after deployment** | Resource not packaged, case-sensitive FS, proxy prefix, wrong base URL | List JAR contents, inspect access logs and absolute URLs. |
| **Static breaks right after adding `@EnableWebMvc`** | MVC auto-configuration altered | Remove `@EnableWebMvc` if only customizing one handler; use `WebMvcConfigurer`. |
| **Private asset accidentally downloadable** | Public location points too broadly, missing authorization | Stop exposing folder, inspect owners and file list, build a protected controller. |
| **`/api/**` and `/**` overlap and are hard to debug** | Catch-all controller/`RouterFunction`, custom handler order | Print/test mappings, narrow prefixes; test both existing and missing URLs. |

### Evidence-based debugging workflow

1. Record **HTTP method, URL, status, `Content-Type`, response body**, and check for proxies/gateways.
2. Verify **resources exist on the classpath/JAR**, watching case sensitivity and trailing **`/`** on locations.
3. Identify the **actual handler executing**: controller method or `ResourceHttpRequestHandler`; in tests inspect the handler on `MvcResult`, or enable `DEBUG` logging for Spring MVC in development.
4. Test **route completeness**: valid API, invalid API, valid asset, missing asset, and SPA navigation.
5. Only then modify mappings or error handlers; avoid changing configuration, caching, and Security simultaneously so you know which change resolved the issue.

If the application returns 404 for a nonexistent API request, that may be the intended behavior. Bugs to fix are **existing APIs captured by another route**, **bodies/statuses violating contracts**, or **exposing directories that should stay private**.

## 12. Extension exercises

### 12.1. Add an image file and test wrong casing

Add **`src/main/resources/site-assets/images/logo.svg`**, then request **`/assets/images/logo.svg`** and **`/assets/images/LOGO.svg`**. On deployments with case-sensitive filesystems, mismatched casing returns 404. Use the exact path and check that `Content-Type` is `image/svg+xml`.

### 12.2. Enable bounded caching

Change `CacheControl` from 10 minutes to 30 seconds, rebuild, and inspect headers with **`curl -i`**. Explain why modifying a file on the server does not force clients to re-download immediately while cache remains fresh. Then try hashed URLs via `ResourceUrlProvider` or a frontend build pipeline to understand cache invalidation.

### 12.3. Trigger NoResourceFoundException

Create a control project using the default `/**` static mapping; request **`/api/missing`**, observe status 404 and the exception type in logs or the exception resolver. Then change the static pattern to `/assets/**` and compare. Do not force both exceptions into HTTP 500; this exercise is about **error-handling paths**, not catching every exception indiscriminately.

### 12.4. Verify SPA fallback with tests

If your app hosts an SPA, test at least:

~~~text
GET /products/42 with Accept: text/html  -> can return index.html
GET /api/unknown                         -> 404, not 200 HTML
GET /assets/unknown.js                   -> 404, not 200 HTML
POST /products/42                        -> does not fall back to HTML merely because the path exists
~~~

UI routing policy depends on the product; the invariant is never letting fallback shadow APIs or assets.

## 13. Pre-merge / pre-deploy checklist

- [ ] API routes all reside under the chosen namespace, e.g., **/api/**; assets under **/assets/**.
- [ ] No catch-all `/**` controller or custom resource handler exists unless explicitly justified and tested.
- [ ] Picked **one** static management approach: Boot properties or custom registration; no conflicting configurations.
- [ ] Java config uses **`WebMvcConfigurer`**, without enabling `@EnableWebMvc` solely to add a static handler.
- [ ] Resource locations contain only approved public files and are properly packaged or mounted.
- [ ] Existing APIs return proper JSON/status; invalid APIs return appropriate errors; valid assets return exact bytes/MIME; missing assets return 404.
- [ ] SPA fallback, if present, applies only to valid navigation and excludes `/api/**`, `/assets/**`, and `/actuator/**`.
- [ ] `Cache-Control` and URL versioning match the release strategy; avoid long caching on files mutated at the same URL without proper revalidation.
- [ ] If Spring Security is used, policies for public assets and protected APIs are tested separately.
- [ ] If reverse proxies/CDNs/context paths are used, test real external URLs and verify rewrites.
- [ ] No private files, credentials, protected uploads, or logs are exposed inside public resource roots.

### Self-check questions

**1. If `/api/status` has `@GetMapping` and the static handler is `/**`, will the static handler always steal the controller route?** No. In standard MVC setup, matching controller mappings take precedence. The common risk is **unmatched APIs** falling through to static fallback or another catch-all rule altering handling.

**2. Why does `/api/unknown` sometimes raise `NoResourceFoundException`?** The `/**` static mapping can catch URLs unhandled by controllers; `ResourceHttpRequestHandler` fails to find a file. Starting in Spring Framework 6.1+, this exception is typically resolved as 404.

**3. When should you use only `spring.mvc.static-path-pattern`?** When you only need a straightforward change of static prefix and locations without per-handler custom resolvers or caching.

**4. When should you add `WebMvcConfigurer.addResourceHandlers`?** When you need multiple namespaces, separate file roots, or custom caching/resolvers/behavior while keeping Spring Boot MVC auto-configuration.

**5. Does `spring.web.resources.add-mappings=false` disable MVC controllers?** No. It disables Boot's automatic static resource mappings; custom handlers added via `WebMvcConfigurer` still work. Watch out for welcome pages/WebJars if the app depends on them.

**6. Why is a static handler unsuitable for serving private user uploads?** Static locations are typically publicly exposed by URL and lack per-file authorization; private downloads need proper access controls.

**7. Why might CSS return 200 yet fail to apply?** The actual response may be HTML from an SPA fallback, an incorrect `Content-Type`, stale cache, or a proxy-rewritten URL; inspect both body and headers.

### Official documentation

- [Spring Boot 3.3 — Servlet Web Applications: Static Content / MVC Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): default locations, `static-path-pattern`, `static-locations`, `@EnableWebMvc`, and 404 behavior.
- [Spring Framework — Web MVC Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): `WebMvcConfigurer`, `ResourceHandlerRegistry`, `CacheControl`, `VersionResourceResolver`, and `ResourceUrlProvider`.
- [Spring Framework 6.1 — NoResourceFoundException](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/resource/NoResourceFoundException.html): exception raised when a handler cannot find a resource.

By separating `/api/**` and `/assets/**`, configuring resource handlers explicitly, and testing both valid and invalid paths, you always know whether a request belongs to an **API controller**, a **static resource**, or **SPA navigation**. This forms the basis for returning accurate statuses, MIME types, caching, and access control during both development and deployment.
