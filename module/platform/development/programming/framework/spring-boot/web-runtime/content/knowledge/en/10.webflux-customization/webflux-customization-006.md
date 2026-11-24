# Configuring spring.webflux.base-path and Resource Mapping in Spring WebFlux

Spring WebFlux lets you organize an entire application's URLs under a shared prefix while also controlling which URLs serve CSS, JavaScript, images, documentation, and WebJars. Spring Boot supports these needs with dedicated properties; when extra mappings are required, the application can use `WebFluxConfigurer` while preserving Boot's auto-configuration.

This lesson focuses on four questions:

1. What prefix does `spring.webflux.base-path` add to HTTP endpoints?
2. How does `spring.webflux.static-path-pattern` determine static file URLs?
3. How does `spring.web.resources.static-locations` determine where files are loaded from?
4. When should you use `WebFluxConfigurer.addResourceHandlers`, and how do you test to avoid 404s, duplicated prefixes, or file exposure?

Examples use Spring Boot **3.5.16**, Spring WebFlux, Java 17+, and embedded Reactor Netty. Some package names or behaviors may change in other major versions. Always consult the documentation for the version managed by your project.

## 1. Three Concepts to Distinguish

| Setting | What does it change? | Example value | Expected impact |
|---|---|---|---|
| spring.webflux.base-path | Shared URL prefix for web handlers in a reactive application | /app | GET /api/ping becomes GET /app/api/ping externally |
| spring.webflux.static-path-pattern | URL pattern for Boot's static resources | /assets/** | File site.css is accessible at /assets/site.css before applying the base path |
| spring.web.resources.static-locations | List of locations to search for static files | classpath:/static/ | Determines which directory holds site.css, not the public URL |
| spring.webflux.webjars-path-pattern | Dedicated URL pattern for WebJars content | /webjars/** | Serves assets inside dependencies packaged in WebJar layout |
| WebFluxConfigurer.addResourceHandlers | Additional mapping declared by the application | /manual/** → classpath:/manual/ | Adds a document path outside the default static mapping |

**Base path is the outer URL prefix; path pattern is the request matching condition; resource location is where the resource bytes live.** They are not three ways to set the same variable.

For example, when configured with:

~~~yaml
spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
~~~

and having `src/main/resources/static/site.css`, the external URL is typically:

~~~text
http://localhost:8080/app/assets/site.css
~~~

You do not create `src/main/resources/static/app/assets`. `/app` and `/assets` belong to **URL space**, while the physical file can remain under **classpath:/static/**.

## 2. Request Flow and Path Resolution

You can picture a request moving through layers:

~~~text
Client: GET /app/assets/site.css
           |
           v
Embedded reactive HTTP server (Reactor Netty)
           |
           v
WebFlux base path: /app
           |
           v
Path matched against web handlers: /assets/site.css
           |
           v
Resource handler pattern: /assets/**
           |
           v
ResourceWebHandler resolves classpath:/static/site.css
           |
           v
HTTP response: CSS
~~~

For a controller `/api/ping`, the matching request is `GET /app/api/ping`. For a functional router `GET /fn/ping`, the matching request is `GET /app/fn/ping`. The base path applies across handlers in the WebFlux application, not just `@GetMapping` methods.

**Do not repeat `/app` inside `@RequestMapping`, `RouterFunctions.route()`, or `addResourceHandler`** just because `spring.webflux.base-path=/app` is set. Adding it manually in both places easily produces `/app/app/...` URLs or routes that fail to match.

Quick check table:

| Definition inside the application | Client URL when base path=/app |
|---|---|
| @GetMapping("/api/ping") | /app/api/ping |
| RouterFunction.GET("/fn/ping") | /app/fn/ping |
| Boot static-path-pattern="/assets/**", file static/site.css | /app/assets/site.css |
| addResourceHandler("/manual/**"), file manual/guide.txt | /app/manual/guide.txt |
| No base path (default) | No /app prefix |

This table applies to a Spring Boot WebFlux app running on one HTTP port; reverse proxies, gateways, or a management server on another port can introduce their own prefixes and must be verified against your actual architecture.

## 3. spring.webflux.base-path Is Not server.servlet.context-path

Spring MVC running on the Servlet stack normally uses:

~~~properties
server.servlet.context-path=/app
~~~

A Spring WebFlux reactive application uses:

~~~properties
spring.webflux.base-path=/app
~~~

These two properties belong to **two different application models**. If you are running a Spring Boot WebFlux app with only `spring-boot-starter-webflux`, do not rely on `server.servlet.context-path` to change reactive URLs.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot normally prefers MVC/Servlet unless the application type is explicitly configured. In that case, WebFlux base path may not take effect as expected because the app is not using the WebFlux server as intended.

With a Spring WebFlux server, there is no reason to add `@EnableWebFlux` just to turn on `base-path`. Spring Boot reads the property and configures the web application via auto-configuration.

### 3.1. Base Path Is Not a Security Mechanism

Adding `/app` does not stop anyone from calling endpoints; it only shifts endpoint locations in the URL. Authentication, authorization, TLS, CORS, and rate limiting remain separate responsibilities. A static resource served publicly under `/app/assets` must still be treated as publicly accessible unless protected by an explicit security policy.

### 3.2. Base Path Does Not Change Port or Host

`server.port` controls the embedded server's HTTP port; `spring.webflux.base-path` controls the path prefix. With `server.port=8080` and `base-path=/app`, the illustrative address is `http://localhost:8080/app/...`, not a separate server.

## 4. Default Static Resource Mapping

Spring Boot supports static resources in WebFlux through `ResourceWebHandler` and the framework's resource handling. By default, the classpath locations typically checked are:

- classpath:/META-INF/resources/
- classpath:/resources/
- classpath:/static/
- classpath:/public/

Example files:

~~~text
src/main/resources/static/site.css
src/main/resources/static/images/logo.svg
~~~

When `static-path-pattern` is unchanged and no base path is set, the files are served at:

~~~text
/site.css
/images/logo.svg
~~~

By default `spring.webflux.static-path-pattern` is `/**`. That gives the resource handler a broad URL scope, though it does not synthesize missing files; requests for nonexistent filenames still return 404.

To cleanly separate APIs and static assets, you can configure:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
~~~

Then `static/site.css` is served at `/assets/site.css` instead of `/site.css`. Adding `base-path=/app` makes the external path `/app/assets/site.css`.

**Documentation mentions `/static`, `/public`, `/resources`, and `/META-INF/resources` as source folders on the classpath**, not four default URL prefixes. Putting a file in `static/js/app.js` does not make its URL `/static/js/app.js`.

## 5. Changing Resource Locations vs. Changing URL Patterns

Two commonly confused properties:

~~~properties
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
~~~

Meaning:

- URL pattern `/assets/**` decides **which requests** match the resource handler.
- Location `classpath:/static/` decides **where to read bytes** after the resource handler strips the relative path.

For instance, with `static/css/site.css` on the classpath, base `/app`, and static pattern `/assets/**`, the URL is `/app/assets/css/site.css`.

### 5.1. Overriding static-locations Replaces the Default List

If you set:

~~~yaml
spring:
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
        - "classpath:/shared-assets/"
~~~

the application does not automatically retain the default locations alongside them. To keep using `static/`, you must include `"classpath:/static/"` in the list. Welcome-page detection also depends on these new locations; if `index.html` is in an old folder no longer listed, it may no longer be detected as before.

To **add an extra resource route without replacing default static locations**, prefer `WebFluxConfigurer.addResourceHandlers` rather than overwriting the whole list with `static-locations`.

### 5.2. Classpath Locations vs. Filesystem Paths

- `classpath:/static/` reads resources packaged inside the JAR or runtime classpath.
- `file:/opt/app/assets/` reads an external filesystem directory if permitted by the application and environment.
- `src/main/resources/static/` is a path in the **source tree**; at build time, it typically becomes `classpath:/static/`.

Using filesystem locations for user-uploaded or frequently updated content requires attention to permissions, file updates, backups, and path safety. Never expose a directory containing secrets or sensitive data via `ResourceWebHandler`.

## 6. Complete Sample Project: API, RouterFunction, and Two Resource Groups

This example mounts the app at `/app`; the API controller at `/api/ping`, the functional route at `/fn/ping`; Boot static assets under `/assets/**`; and a separate documentation folder under `/manual/**`. All are served beneath `/app` to external clients.

The project uses **Spring Boot 3.5.16**, **Java 17+**, and Maven. Only `spring-boot-starter-webflux` is used for the reactive web server; `spring-boot-starter-web` is not included.

Structure:

~~~text
webflux-path-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/pathdemo/
    │   │   ├── PathDemoApplication.java
    │   │   ├── ApiController.java
    │   │   ├── FunctionalRoutes.java
    │   │   └── ExtraResourceConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       ├── static/site.css
    │       └── manual/guide.txt
    └── test/
        └── java/com/example/pathdemo/PathMappingTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-path-demo</name>

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
~~~

The Spring Boot parent manages dependency versions. Maven needs access to the appropriate dependency repository on the first build if the local cache does not yet hold the libraries.

### 6.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
~~~

`spring.web.resources.static-locations` is omitted because the project wants to **keep Boot's default static locations** and only add an extra resource handler for documentation.

### 6.3. PathDemoApplication.java

~~~java
package com.example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathDemoApplication.class, args);
    }
}
~~~

### 6.4. ApiController.java

~~~java
package com.example.pathdemo;

import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

The controller definition **does not include `/app`**. When a client requests `/app/api/ping`, Spring Boot applies the base path and WebFlux matches `/api/ping` against `@RequestMapping` and `@GetMapping`.

### 6.5. FunctionalRoutes.java

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> pingRoute() {
        return RouterFunctions.route(
                RequestPredicates.GET("/fn/ping"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("fn-ok"));
    }
}
~~~

The route definition also **does not include `/app`**. Externally, clients request `/app/fn/ping`. WebFlux.fn uses `ServerRequest` and `ServerResponse`; it does not require controller annotations.

### 6.6. ExtraResourceConfiguration.java

~~~java
package com.example.pathdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ExtraResourceConfiguration implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual/**")
                .addResourceLocations("classpath:/manual/")
                .setCacheControl(CacheControl.noCache());
    }
}
~~~

This adds a new mapping: `/manual/**` reads from `classpath:/manual/`. Implementing `WebFluxConfigurer` **does not require `@EnableWebFlux`** and should not include `@EnableWebFlux` when the goal is preserving Spring Boot's resource and codec auto-configuration.

`CacheControl.noCache()` instructs browsers/caches to revalidate before reusing a stored copy, not that responses are never cached; for sensitive documents, use authorization and `no-store` caching where appropriate.

### 6.7. Resource Files

**src/main/resources/static/site.css**

~~~css
body {
    color: #234567;
    font-family: sans-serif;
}
~~~

**src/main/resources/manual/guide.txt**

~~~text
This guide is served by an extra WebFlux resource mapping.
~~~

After building, `site.css` resides at `classpath:/static/`, while `guide.txt` resides at `classpath:/manual/`. Do not create `app/assets` or `app/manual` folders in the source tree.

### 6.8. Running the Application

From `webflux-path-demo`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Requests to test with `curl`:

~~~bash
curl -i http://localhost:8080/app/api/ping
curl -i http://localhost:8080/app/fn/ping
curl -i http://localhost:8080/app/assets/site.css
curl -i http://localhost:8080/app/manual/guide.txt
~~~

Expected results:

| Request | Status | What to verify |
|---|---|---|
| GET /app/api/ping | 200 | JSON with `status` equal to `ok` |
| GET /app/fn/ping | 200 | Body `fn-ok` |
| GET /app/assets/site.css | 200 | CSS containing `color: #234567` |
| GET /app/manual/guide.txt | 200 | Guide text from `manual/` |
| GET /api/ping | 404 | Missing `/app` base path |
| GET /app/site.css | 404 | Missing `/assets` resource prefix |
| GET /app/app/api/ping | 404 | Unintended duplicated base path |

Example API body:

~~~json
{"status":"ok"}
~~~

Server logs, header order, and exact 404 formatting vary by runtime and should not be treated as fixed output. Verify the HTTP status, `Content-Type`, and meaningful body content.

## 7. Integration Testing with WebTestClient

A reliable verification is starting the real application on a random port and calling the URLs clients actually use. `WebTestClient` can be auto-configured by Boot for WebFlux applications.

**src/test/java/com/example/pathdemo/PathMappingTest.java**

~~~java
package com.example.pathdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PathMappingTest {

    @Autowired
    private WebTestClient client;

    @Test
    void annotatedApiUsesBasePath() {
        client.get()
                .uri("/app/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void functionalRouteUsesBasePath() {
        client.get()
                .uri("/app/fn/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("fn-ok");
    }

    @Test
    void bootStaticResourceUsesBothPrefixes() {
        client.get()
                .uri("/app/assets/site.css")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("color: #234567"));
    }

    @Test
    void additionalResourceMappingIsAccessible() {
        client.get()
                .uri("/app/manual/guide.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("extra WebFlux resource mapping"));
    }

    @Test
    void missingOrDuplicatedPrefixDoesNotMatch() {
        client.get().uri("/api/ping")
                .exchange().expectStatus().isNotFound();

        client.get().uri("/app/app/api/ping")
                .exchange().expectStatus().isNotFound();

        client.get().uri("/app/site.css")
                .exchange().expectStatus().isNotFound();
    }
}
~~~

This test suite simultaneously verifies annotations, `RouterFunction`, Boot static resources, the custom `ResourceHandler`, and three negative URLs. It shows that `base-path` does not force the app to edit every mapping manually.

Run:

~~~bash
mvn test
~~~

When tests pass, Maven exits with code 0. Do not hardcode log output or random ports; rely on assertions rather than printed port numbers. If a proxy sits in front of production, add smoke tests through the proxy to verify real external URLs.

## 8. When You Only Want to Change Resource URLs Without Changing APIs

If APIs must stay at `/api/ping` while CSS/JS move from `/site.css` to `/assets/site.css`, do not use `spring.webflux.base-path`; configure only:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
~~~

Then:

- `@GetMapping("/api/ping")` stays at `/api/ping`.
- `static/site.css` moves to `/assets/site.css`.
- There is no `/app` prefix across the whole app.

This is the proper approach when requirements concern only asset paths.

Conversely, if **all** endpoints and resources belong under `/app`, use `base-path`, combined with `static-path-pattern` if you also want an explicit `/assets` group.

## 9. When You Only Want to Change File Sources Without Changing URLs

If the URL stays `/assets/site.css` but files live in a different classpath folder, configure locations:

~~~yaml
spring:
  webflux:
    base-path: /app
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/frontend/"
        - "classpath:/static/"
~~~

`classpath:/frontend/site.css` or `classpath:/static/site.css` can be resolved for `/app/assets/site.css`, following location order and active resource resolvers.

Do not confuse locations with URLs: `classpath:/frontend/` does not create a `/frontend/` URL unless the path pattern is also configured that way.

**Beware of replacing defaults:** setting `static-locations` to only `frontend/` can stop files in the default `public/` folder from being served. To add an independent file group, use `addResourceHandlers` as shown in the example rather than replacing the base list.

## 10. When Should You Use WebFluxConfigurer.addResourceHandlers?

Use it when you need a specialized mapping that global properties cannot express well, such as:

- `/manual/**` served from `classpath:/manual/` with its own cache policy.
- `/downloadable-docs/**` served from a controlled location with specific content-type/cache policies.
- An asset group requiring its own `ResourceResolver`/`ResourceTransformer` or versioning.
- Serving multiple URL namespaces with distinct resource sources and policies.

Another caching example (illustrative only—do not replace the class in the sample project):

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/vendor/**")
            .addResourceLocations("classpath:/vendor/")
            .setCacheControl(CacheControl.maxAge(
                    7, java.util.concurrent.TimeUnit.DAYS));
}
~~~

Points to consider:

1. Patterns in `addResourceHandler` are written in **internal handler space**, without prepending `/app` base-path.
2. Use narrow patterns like `/manual/**`, avoiding `/**` that collides with defaults.
3. Resource locations should end with `/` so relative paths resolve unambiguously.
4. Cache policies must match file mutability; versioned/hashed filenames can be cached longer.
5. Never expose directories containing configs, keystores, private uploads, or secrets over HTTP.
6. Do not add `@EnableWebFlux` just to register an additional resource handler.

A custom handler does not replace all of Spring Boot's static configuration; if you only need to change the prefix use `static-path-pattern`, and if you only need to change sources use `static-locations`.

## 11. WebJars Have Their Own Path Pattern

WebJars package frontend libraries inside dependency JARs in WebJar layout. With Spring Boot and an appropriate dependency, resources can be served under the WebJars URL namespace.

Property:

~~~properties
spring.webflux.webjars-path-pattern=/vendor/**
~~~

adjusts the pattern for WebJars, not the general `static-path-pattern`. With `base-path=/app`, clients prepend `/app` before the configured WebJars URL.

Do not use `spring.web.resources.static-locations` expecting it to alter paths inside a WebJar. Final paths and whether version segments can be omitted depend on the dependency, WebJar packaging, and resolver capabilities. Verify real URLs with HTTP tests.

If your application does not use WebJars, you do not need this property group.

## 12. Welcome Page and SPA Fallback

Spring Boot supports detecting `index.html` in configured static resource locations and can serve it as a welcome page when no other route matches. When `static-locations` changes, the set of folders searched for the welcome page changes too.

However, do not assume the welcome page and `static-path-pattern` are the exact same mechanism. When switching the pattern to `/assets/**`, behavior for `/app/` and `/app/assets/index.html` should be tested explicitly depending on mappings, handler ordering, and app configuration. The sample project relies only on concrete file URLs, not an implicit SPA fallback.

**Single Page Applications:** frontends often expect `/app/dashboard` and `/app/settings` to serve `index.html` so a client-side router takes over. That is a separate requirement and is not fulfilled automatically by `spring.webflux.base-path` or `static-path-pattern`.

For SPA fallbacks:

- Keep API and asset namespaces unambiguous.
- Forward/serve `index.html` only for valid frontend routes.
- Never turn every API 404 into a 200 HTML response, as that hides errors.
- Ensure `/api/**`, `/assets/**`, and `/actuator/**` never fall back improperly.
- Test direct browser refreshes on deep SPA routes as well as API 404s.

WebFlux.fn supports routing to static resources with predicates, which is an explicit routing solution rather than an automatic consequence of `base-path`.

## 13. Actuator and Management Port: Avoid Guessing Prefixes

If an application adds Spring Boot Actuator, management paths have their own property:

~~~properties
management.endpoints.web.base-path=/actuator
~~~

When management endpoints share **the same HTTP port** as the WebFlux application, `management.endpoints.web.base-path` is resolved relative to `spring.webflux.base-path`. For instance, with `base-path=/app` and management `base-path=/actuator`, the expected URL is `/app/actuator/health`, provided `health` is exposed and security permits access.

When using a separate **`management.server.port`**, management endpoints are configured relative to `management.server.base-path` on the management port. Do not prepend `/app` to the management port URL in that setup.

Changing `base-path` can break ingress/load-balancer health checks if they call the wrong path. After deployment, verify both application URLs and the actual health probe path.

Actuator is not included in the sample project dependencies; adding management properties alone does not create health endpoints without the starter.

## 14. Base Path Behind a Reverse Proxy or API Gateway

Three parties can alter the path:

1. The client sends a public URL, e.g., `/edge/app/api/ping`.
2. A reverse proxy/ingress may preserve the path or strip the `/edge` prefix.
3. Spring Boot WebFlux applies `base-path` to the path the server actually receives.

If the proxy **strips `/edge`** before forwarding, Spring Boot receives `/app/api/ping` and `base-path=/app` matches.

If the proxy **keeps `/edge/app/api/ping`**, routes/rewrites must align with what the app receives. Do not blindly add `/edge` to `spring.webflux.base-path` without knowing what the proxy does.

Forwarded headers such as `Forwarded` or `X-Forwarded-Prefix` can influence external URL generation depending on strategy and infrastructure. Configure `server.forward-headers-strategy` only for trusted proxies; never trust arbitrary headers sent directly by clients. Absolute URLs in redirects, CORS callbacks, cookie `Path` attributes, and CSS/JS asset references are common breakage points when deploying under prefixes.

### 14.1. Why Does Localhost Work While Production Returns 404?

Common causes:

- An ingress route already added `/app`, and the application also added `/app` inside controllers.
- The proxy stripped a prefix differently than expected.
- Frontend builds emitted absolute `/assets/site.css` URLs while the app lives at `/app/assets/site.css`.
- CDNs or reverse proxies cached old URLs after changing `static-path-pattern`.
- Security filters or CORS configs still match patterns against old URLs.
- Health probes still call `/actuator/health` while the actual endpoint moved to `/app/actuator/health`.

Document an **end-to-end URL table**: public URL, post-proxy path, path received by WebFlux, internal handler pattern, and resource location.

## 15. Mapping Order, 404s, and Subtle Masking Bugs

WebFlux uses multiple `HandlerMapping`s to select handlers. Annotated controllers, functional routers, and resource handlers all participate in request handling, with specific route specificity and ordering rules. Never assume static files always outrank APIs or vice versa across arbitrary custom setups.

With the default `static-path-pattern` of `/**`, an unmatched API request can fall into `ResourceWebHandler`. If no matching file exists, the final result is still 404, though the exception/logs differ from an unmatched route. With a narrow pattern like `/assets/**`, separating API and resource URLs is much clearer to observe.

**URL patterns are not filesystem paths.** Configuring `/assets/**` does not let URLs read arbitrary disk files; WebFlux resource resolvers remain scoped to configured locations. Still, opening a broad filesystem root introduces real exposure risks.

When debugging, check in order:

1. Which port, host, scheme, and path is the HTTP request actually hitting?
2. Is a reverse proxy stripping or adding a prefix?
3. Is Spring Boot truly running **reactive WebFlux**, or Spring MVC due to another starter?
4. Is `spring.webflux.base-path` configured properly?
5. Is the internal pattern `@GetMapping`, `RouterFunction`, or `static-path-pattern`?
6. Does the resource location actually contain the file inside the packaged JAR?
7. Did `spring.web.resources.add-mappings` disable default mappings?
8. Did a security rule block the request with 401/403 before handlers ran?
9. Is an SPA fallback or custom router claiming too broad a URL pattern?
10. Do direct requests to the app port match requests through ingress?

Selective debug logging in test environments can help inspect registered mappings. Do not turn on verbose request/body logging with credentials or personal data in production.

## 16. Cache-Control, ETags, and Resource Versioning

Resource handling supports cache headers and resource chains. Common practices:

- CSS/JS with versioned or content-hashed filenames can be cached long-term when deployments manage versions.
- HTML entrypoints generally need short cache lifetimes because they reference newly versioned assets.
- Frequently changing resources should use revalidation or `no-store` depending on sensitivity.
- `ResourceWebHandler` can handle `Last-Modified` and conditional GET requests depending on locations and configuration.

Spring Boot exposes properties under `spring.web.resources.cache.*` and `spring.web.resources.chain.*`. For a separate resource namespace with custom needs, `addResourceHandlers` can declare its own cache policy.

Illustrative general configuration:

~~~yaml
spring:
  web:
    resources:
      cache:
        cachecontrol:
          max-age: 1h
~~~

This configures caching for Boot-managed resource handlers and does not override handlers that explicitly call `setCacheControl` in Java. Do not apply long TTLs to all static responses without considering invalidation, versioning, and data sensitivity.

## 17. Resource Security and Deployment Constraints

Resource handlers make serving images, CSS, and public docs easy, but keep in mind:

- **Never place credentials, config secrets, database backups, private keys, or customer data** in statically served locations.
- External filesystem resource locations require strict file permissions and symlink/path controls.
- Static resources under `/app` do not become private just because the URL has a prefix.
- Documents requiring per-user permissions should be served via controllers/services enforcing authorization, rather than exposing a folder statically.
- With Spring Security WebFlux, configure `SecurityWebFilterChain` for public URLs and the actual base path; test unauthenticated requests, not just logged-in clients.
- Check `Content-Type`, `X-Content-Type-Options`, cache headers, and download policies for potentially risky file types.
- Changing `static-path-pattern` can break hardcoded frontend paths, manifests, source maps, and service worker scopes; verify in a real browser.

Spring WebFlux applications do not use `src/main/webapp` the way Servlet WARs do. For executable JARs, place static content under `src/main/resources/...` so it is packaged; do not expect an unpackaged `webapp` folder to be served automatically.

## 18. Summary of Scenarios and Configuration Decisions

| Need | Preferred solution |
|---|---|
| Put all APIs and assets under `/app` | `spring.webflux.base-path=/app` |
| Move only CSS/JS to `/assets/**` | `spring.webflux.static-path-pattern="/assets/**"` |
| Keep URLs but change asset source folders | `spring.web.resources.static-locations` |
| Add `/manual/**` with its own source and cache policy | `WebFluxConfigurer.addResourceHandlers` |
| Change only the WebJars path | `spring.webflux.webjars-path-pattern` |
| Separate health/metrics port | `management.server.port` and `management.server.base-path` with Actuator |
| Spring MVC/Servlet app | Look at `server.servlet.context-path` and `spring.mvc.static-path-pattern`, not WebFlux settings verbatim |
| Running behind a gateway | Verify rewrite rules and forwarded headers before changing base path |

## 19. Pre-Deployment Checklist

- [ ] `spring-boot-starter-webflux` is present and the app truly runs WebFlux/`DispatcherHandler`.
- [ ] `spring.webflux.base-path` has one clear prefix without duplicating it in controllers/routers.
- [ ] `spring.webflux.static-path-pattern` is understood as a URL pattern, not a filesystem directory.
- [ ] `spring.web.resources.static-locations` is overridden only when intentionally replacing default locations.
- [ ] Static files are actually included in the runtime JAR/classpath.
- [ ] Custom resource handlers use `WebFluxConfigurer` without `@EnableWebFlux` when keeping Boot defaults.
- [ ] APIs, `RouterFunction`s, assets, and custom mappings all have HTTP tests using full URLs.
- [ ] Negative tests cover missing prefixes, duplicated prefixes, and retired static URLs.
- [ ] Asset URLs in HTML/JS/CSS respect the base path.
- [ ] Proxy rewrites, forwarded headers, CDN rules, and health probes are reviewed.
- [ ] Security and caching are designed explicitly; base path is not authorization.
- [ ] Static resource mapping is never used to expose data requiring access control.

## 20. Key Takeaways

**`spring.webflux.base-path`** sets the common prefix for web handlers in Spring Boot WebFlux. **`spring.webflux.static-path-pattern`** selects which URLs belong to Boot's static resource serving. **`spring.web.resources.static-locations`** determines where files are read from. **`WebFluxConfigurer.addResourceHandlers`** adds extra custom mappings.

For example, with `base-path=/app` and `static-path-pattern=/assets/**`, `classpath:/static/site.css` is served at `/app/assets/site.css`. Never duplicate `/app` in `@GetMapping`, `RouterFunction`, or `addResourceHandler`. Testing both valid and invalid paths is the most reliable way to catch prefix errors before deployment.

## Official Documentation

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Framework 6.2 — WebFlux Config: Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Boot — Monitoring over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)