# Welcome page, `index.html`, and default page selection order in Spring Boot

## 1. Problem: why does visiting `/` display an HTML page?

In a Spring Boot web application, a user opening `http://localhost:8080/` might see a static HTML page, a Thymeleaf-rendered page, a controller's response, a login redirect, or an HTTP error. Simply having a file named `index.html` somewhere in the project does not mean Spring Boot automatically uses it. The **welcome page** is Spring Boot's auto-configured mechanism for providing a home page when the application has not defined a matching handler for the root path `/`.

To understand it accurately, you must separate **two selection steps**:

1. **Selecting the handler for URL `/`**: application-declared endpoints take precedence over the automatic welcome page.
2. **Selecting the content inside the welcome page**: Spring Boot prioritizes `index.html` in static resource locations; if no suitable static page exists, it then checks for a template named `index`.

Lesson scope: Spring Boot **3.3.x**, Spring MVC/Servlet with Java 17+; a WebFlux comparison appears at the end. Precedence conclusions assume default MVC auto-configuration and a request accepting HTML.

```text
GET / with Accept: text/html
        |
        +--> Functional route for "/" matches? --> Use functional route
        |
        +--> Controller mapping for "/" matches? --> Use controller
        |
        +--> Welcome page fallback?
                 |
                 +--> Static index.html in static locations, matching mapping?
                 |         |
                 |         +--> Yes --> Static welcome page
                 |
                 +--> Template engine recognizes template "index"?
                           |
                           +--> Yes --> Render template index
                           +--> No  --> No automatic welcome page
```

This is a diagram of responsibilities, not a guarantee that every application executes that exact sequence of Java methods. Security filters, servlet mappings, media types, proxy rewriting, and custom configurations can alter the outcome.

## 2. Three distinct concepts: static file, welcome mapping, route

| Concept | Where declared | Typical result |
| --- | --- | --- |
| Static file `index.html` | `src/main/resources/static/index.html` | Directly accessible at `GET /index.html` |
| Welcome page | Auto-detected by Spring Boot from static `index.html` or template `index` | Attached as a fallback for `GET /` |
| Route `/` | `@GetMapping("/")`, `RouterFunction` | Handles the root request using application logic |

A static `index.html` file is **not required** to be accessed only at `/index.html`. When recognized as a welcome page, it is also served at `/`. The two URLs are related but not identical: another route or pattern can cause `/` to be handled differently from `/index.html`.

Similarly, a template `templates/index.html` is not a static file; a template engine must recognize the logical view name `index` before Spring Boot can use it as a template welcome page. Without an appropriate engine, naming a file `index.html` inside `templates` will not automatically produce an HTML response.

## 3. Search locations for static `index.html` and default order

Spring Boot 3.3 provides four default classpath static locations. The order of the list in `WebProperties.Resources` is:

| Order | Static location | File in a typical Maven/Gradle project |
| --- | --- | --- |
| 1 | `classpath:/META-INF/resources/` | `src/main/resources/META-INF/resources/index.html` |
| 2 | `classpath:/resources/` | `src/main/resources/resources/index.html` |
| 3 | `classpath:/static/` | `src/main/resources/static/index.html` |
| 4 | `classpath:/public/` | `src/main/resources/public/index.html` |

The path `src/main/resources/resources/index.html` is valid: the first `src/main/resources` is the classpath root; the second `resources/` is an actual subdirectory corresponding to `classpath:/resources/`.

**You should place static home pages in `src/main/resources/static/index.html`**, as it is recognizable and convenient for developers. If multiple `index.html` files exist across static locations, the location searched first can take precedence. If the same path exists across multiple dependency JARs, classpath order can also affect selection; avoid creating competing index files.

In Servlet applications, Boot can also serve content from the `ServletContext` root depending on packaging. With executable JARs, `src/main/webapp` is not a reliable choice for static welcome pages; prefer resources packaged on the classpath.

Spring MVC's default static resource mapping is `/**`, handled by `ResourceHttpRequestHandler`. This is the **resource-serving layer** once a request has been mapped, not a reason a controller route would lose to a static file.

## 4. Handler precedence when processing `/`

According to Spring Boot 3.3 documentation, the relevant handler mappings in MVC have the following default order:

| Priority | Handler mapping | Created by |
| --- | --- | --- |
| First | `RouterFunctionMapping` | Functional routes registered via `RouterFunction` beans |
| Next | `RequestMappingHandlerMapping` | Routes from `@Controller`, `@RestController`, `@GetMapping` |
| After | `WelcomePageHandlerMapping` | Automatic welcome page |

Therefore, if a controller actually matches `GET /`, it returns its own result even when `static/index.html` exists. Likewise, a functional route for `GET /` takes precedence over the welcome page.

Example controller:

```java
package com.example.home;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RootController {

    @GetMapping("/")
    public String root() {
        return "ROOT_FROM_CONTROLLER";
    }
}
```

In a scenario with no interfering filter, calling `GET /` returns the exact body:

```text
ROOT_FROM_CONTROLLER
```

Meanwhile, if `static/index.html` exists and the static mapping is unchanged, the URL `/index.html` can still serve the static file. These two behaviors do not conflict: **the controller claims the `/` URL without deleting the `/index.html` resource**.

Note: `@RestController` returning a `String` as above means a response body. A regular `@Controller` returning `String "index"` typically indicates a **view name** to be rendered by a view resolver. Do not treat the two controller types as interchangeable when learning page selection.

Handler mappings can be configured with custom ordering in advanced applications; the table above describes the **defaults**.

## 5. Content selection order inside the welcome page

If the root request has not been handled by any route and the welcome page qualifies, Spring Boot applies these rules:

1. **Look for static `index.html`** in the configured static resource locations.
2. **If no suitable static welcome exists, look for a template named `index`** using the template availability providers of the template engines present in the application.
3. **If neither exists**, Boot does not automatically synthesize a welcome page from an arbitrary HTML file.

Example where both exist:

```text
src/main/resources/
├── static/
│   └── index.html       # WELCOME_FROM_STATIC
└── templates/
    └── index.html       # WELCOME_FROM_TEMPLATE
```

If Thymeleaf is installed, no `/` route exists, and static mappings are default, `GET /` chooses **static/index.html**. To verify the template fallback, temporarily rename or remove static index across all evaluated locations and restart the application.

**Important condition regarding `/**`:** In Boot's MVC mechanism, a static index normally becomes the welcome page when the static resource mapping uses the default `/**` pattern. If the application changes `spring.mvc.static-path-pattern` to `/assets/**`, the static index can still be loaded at `/assets/index.html`, but it is no longer the automatic static welcome at `/`. In that case, a recognized `index` template can still provide the fallback. Do not read “static before template” as ignoring the static mapping condition.

## 6. Auto-configuration that detects the welcome page

Spring Boot MVC auto-configuration coordinates the following components:

- `WebMvcAutoConfiguration`: provides default Spring MVC configuration, including static resource and welcome page support when auto-configuration conditions match.
- `WebProperties.Resources`: holds static resource locations and resource processing options.
- `TemplateAvailabilityProviders`: checks whether the logical template `index` is supported by an available engine.
- `WelcomePageHandlerMapping`: fallback mapping for the root path in Spring MVC.
- `ResourceHttpRequestHandler` and view resolvers: serve the static resource or render the corresponding template.

Conceptual startup flow:

```text
SpringApplication.run(...)
    |
    +--> Create Servlet web application context
    |
    +--> Enable MVC auto-configuration when conditions match
    |
    +--> Read static locations and static path pattern
    |
    +--> Check for static index or template "index"
    |
    +--> Register welcome handler if a valid page exists
    |
    +--> On incoming request, DispatcherServlet evaluates handler mappings in order
```

Spring Boot automatically **detects the welcome page during context configuration**, without the developer writing `new WelcomePageHandlerMapping(...)`. When adding, renaming, or removing an index file in a running application's source, **restart** to rule out stale mappings or an outdated running artifact.

Do not explain default welcome page selection as an automatic feature of embedded Tomcat: in the Spring Boot MVC model, Spring MVC handler mappings and resource handling play the primary role.

## 7. Lab A: application with a static welcome page and no controller

The following example uses **Spring Boot 3.3.13, Java 21**. It runs in a Gradle project with a Gradle Wrapper and requires no controller.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/home/WelcomeApplication.java`**

```java
package com.example.home;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WelcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WelcomeApplication.class, args);
    }
}
```

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Home</title>
</head>
<body>
  <h1>WELCOME_FROM_STATIC</h1>
  <p>Spring Boot automatically detects the static home page.</p>
</body>
</html>
```

From the project directory containing `gradlew`:

```bash
./gradlew bootRun
```

Open a browser or run:

```bash
curl -s -H 'Accept: text/html' http://localhost:8080/
curl -s -H 'Accept: text/html' http://localhost:8080/index.html
```

Both HTML responses contain **`WELCOME_FROM_STATIC`** if port 8080 is available, no filter/security blocks them, and static routing has not changed. This verifies that the static file is used at both the direct URL and the welcome fallback.

There is no need to write `@GetMapping("/")` just to serve a static HTML file. Other assets in `static/`, such as `css/site.css`, continue using normal static resource mapping rules.

## 8. Lab B: `/` route beats static index

Keep `static/index.html` and add `RootController` from section 4 to the same `com.example.home` package. Restart:

```bash
./gradlew bootRun
```

Test:

```bash
curl -s http://localhost:8080/
curl -s http://localhost:8080/index.html
```

The first result is `ROOT_FROM_CONTROLLER`; the second still contains `WELCOME_FROM_STATIC`. The reason is that the `/` route is evaluated in `RequestMappingHandlerMapping` before `WelcomePageHandlerMapping`.

When you remove or disable the controller and restart, root requests return to the static welcome page if the original conditions still hold. Use adding/removing routes as an experiment **to understand precedence**, not as a recommendation for overlapping routes in real applications.

## 9. Lab C: `index` template instead of static index

To observe the template fallback branch:

1. Remove `RootController` if added in Lab B.
2. Move or rename `src/main/resources/static/index.html`; verify no other static `index.html` remains in other default locations.
3. Add Thymeleaf to the project's dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The `dependencies` block above is a **replacement** for the corresponding block in Lab A; do not leave two identical blocks.

Create **`src/main/resources/templates/index.html`**:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Template page</title>
</head>
<body>
  <h1>WELCOME_FROM_TEMPLATE</h1>
</body>
</html>
```

Restart and verify:

```bash
./gradlew bootRun
curl -s -H 'Accept: text/html' http://localhost:8080/
```

The body must contain **`WELCOME_FROM_TEMPLATE`** when default template resolver configuration is active and no `/` route takes precedence. No controller is needed merely to enable the welcome template.

**Do not confuse:** `templates/index.html` does not automatically become a static file at `/index.html`. If you only create a template file without adding a supported template engine, Spring Boot usually lacks a view resolver to render it. Other template engines may use different file extensions; the underlying rule is that the logical template name `index` is recognized by the framework.

## 10. Customizing file lookup locations and access URLs

### 10.1. Changing static resource locations

**`application.properties`**

```properties
spring.web.resources.static-locations=classpath:/website/
```

This property **replaces the default classpath static locations list** with the declared location. To have a static welcome under the new configuration, place the file at:

```text
src/main/resources/website/index.html
```

If you leave the file in `static/` after changing locations to `classpath:/website/`, Boot will no longer look for a static index in the old directory by default.

If you want two locations, declare both explicitly:

```properties
spring.web.resources.static-locations=classpath:/website/,classpath:/static/
```

Earlier locations generally take precedence when both contain `index.html`; avoid duplication so behavior stays predictable. In servlet applications, configuration can also involve the `ServletContext` root, though for executable JARs the key is verifying the actual resources packaged onto the classpath.

### 10.2. Changing the static resources URL pattern

**`application.properties`**

```properties
spring.mvc.static-path-pattern=/assets/**
```

With `src/main/resources/static/index.html`, the direct resource-serving URL becomes:

```text
GET /assets/index.html
```

However, `GET /` is **not guaranteed** to still use the static index as before: because the static welcome depends on the `/**` mapping, `/assets/**` can remove the automatic static fallback at root. If you truly want a `/` route, define an explicit route or use a matching welcome template where appropriate.

Comparison of properties:

| Property | Changes |
| --- | --- |
| `spring.web.resources.static-locations` | Where static files are searched |
| `spring.mvc.static-path-pattern` | Which URLs are handled by the static resource handler |
| `spring.web.resources.add-mappings` | Whether default static resource mappings are registered |
| `server.port` | Port listening for HTTP connections |
| `server.servlet.context-path` | Path prefix for the entire Servlet app |

Changing `static-locations` does not change URL prefixes; changing `static-path-pattern` does not move files on disk; changing `context-path` does not create extra subdirectories inside `static`.

### 10.3. Context path differs from resource root path

```properties
server.servlet.context-path=/demo
```

Now the static welcome for the application root is normally accessed at:

```text
http://localhost:8080/demo/
```

You still keep the file at `src/main/resources/static/index.html`, without moving it to `static/demo/index.html`. For Spring MVC, the internal path to resolve remains `/`; the servlet context path is prepended to external URLs.

If there is a reverse proxy, base paths and rewrite rules can make the public URL differ from the backend URL. Inspect the actual request reaching the application before altering source resources.

## 11. `Accept`, Spring Security, and non-HTML requests

The welcome page is designed for web navigation to the home page. Browsers normally send an `Accept` header containing `text/html`, which matches the welcome mechanism. In MVC, the welcome mapping only applies when the request accepts an HTML media type. Do not assume an API client requesting only `application/json` will receive the welcome HTML.

Test:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/
curl -i -H 'Accept: application/json' http://localhost:8080/
```

The second outcome depends on the application's mappings and exception handling: it may yield a different result or an HTTP error. Do not assume a fixed 404 or 406 code in all cases.

Spring Security can run **before** `DispatcherServlet`. If requesting `/` requires authentication, a browser may receive a `302` redirect to `/login`, `401`, or `403`, depending on the security filter chain. This is not necessarily a `WelcomePageHandlerMapping` issue; inspect authentication/authorization policies before changing static locations.

For SPAs such as React/Vue/Angular packaged inside `static/`, the welcome page for `/` **does not automatically act as a catch-all fallback** for every URL like `/orders/123`. Client-side routing via deep links requires a dedicated server fallback mechanism while ensuring it does not accidentally swallow `/api/**` or genuinely missing resources.

## 12. Key differences between Spring MVC and WebFlux

Spring Boot supports welcome pages in both Servlet MVC and reactive WebFlux, sharing the **static index first, template index second; application route before fallback** principle. However, the implementations differ:

| Aspect | Spring MVC (Servlet) | Spring WebFlux |
| --- | --- | --- |
| Resource handler | `ResourceHttpRequestHandler` | `ResourceWebHandler` |
| Static resource pattern | `spring.mvc.static-path-pattern` | `spring.webflux.static-path-pattern` |
| Welcome handler | `WelcomePageHandlerMapping` | Welcome router function in reactive mappings |
| Static locations | `spring.web.resources.static-locations` | `spring.web.resources.static-locations` |
| Explicit route | MVC `@GetMapping` or `RouterFunction` | Reactive `@GetMapping` or `RouterFunction` |
| Template | MVC-compatible view resolver/template engine | WebFlux-compatible view resolver/template engine |

`spring.mvc.static-path-pattern` does not control WebFlux's resource handler. Similarly, `server.servlet.context-path` belongs to servlet deployments, not URL configuration for pure reactive applications.

If a project has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot by default infers **SERVLET**, so check `WebApplicationType` before concluding which stack handles `/`.

## 13. Prediction matrix for what appears at `/`

Assuming an HTML-accepting `GET /` request, default Spring MVC, no filter/security blockers, and static mapping `/**` unless noted otherwise:

| Route `/` | Valid static index | Valid template index | Precedence result |
| --- | --- | --- | --- |
| No | Yes | No | Static `index.html` |
| No | No | Yes | Template `index` |
| No | Yes | Yes | Static `index.html` |
| `@GetMapping("/")` matches | Yes | Yes | Controller |
| Functional `GET("/")` matches | Yes | Yes | Functional route |
| No | No | No | No automatic welcome page |
| No, static pattern `/assets/**` | Yes | No | No automatic static welcome at `/` |
| No, static pattern `/assets/**` | Yes | Yes | Template `index` can serve as fallback |

This matrix illustrates **precedence order**, not a substitute for testing when custom handler mappings, custom content negotiation, WAR servlet roots, or reverse proxy rules are involved.

## 14. Testing the application over real HTTP

The Lab A project already includes `spring-boot-starter-test`. You can write an integration test on a random port to verify the actual HTML body.

**`src/test/java/com/example/home/WelcomeHttpTest.java`**

```java
package com.example.home;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WelcomeHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void rootServesStaticIndex() {
        ResponseEntity<String> response =
                client.getForEntity("/", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("WELCOME_FROM_STATIC");
    }
}
```

Run:

```bash
./gradlew test
```

This test targets the **static-only scenario**: remove Lab B's `RootController`, use Lab A's static index, and keep the default context path. `RANDOM_PORT` starts a real embedded server; the HTTP response body provides clearer proof that the static welcome is served than merely seeing a resource handler bean.

When using `MockMvc`, distinguish between verifying a mapping/forward versus receiving the final body dispatched through a real server. For verifying that `GET /` actually renders the HTML file, an HTTP integration test like the one above is usually easier to interpret.

## 15. Diagnosing when the home page is wrong

Check from **routes, welcome mechanism, static locations, template engine** through Security and deployment layers:

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Root returns API text/JSON | A controller or functional route for `/` takes precedence | Search for `@GetMapping("/")` and `RouterFunction` |
| Root shows template despite static index in source | Static file is outside effective location, missing from artifact, or static pattern changed | Check packaged resources, `static-locations`, `static-path-pattern` |
| `/assets/index.html` works, `/` does not | Static path moved to `/assets/**`; no static root welcome remains | Define a dedicated root route or template if appropriate |
| Only `templates/index.html` exists yet root returns 404 | Missing template engine or view resolver did not recognize `index` | Check Thymeleaf/FreeMarker starter and template config |
| `/` renders template yet `/index.html` returns 404 | Templates are not static resources | Verify rendering setup and actual URL |
| Root redirects to login / returns 401 or 403 | Filter or Spring Security blocks it | Inspect filter chain and rules for `/` and assets |
| Root still shows old page | Stale artifact, proxy/browser cache, or forgot to restart | Check JAR/bootRun, refresh, test with `curl` |
| `/` works yet SPA deep links fail | Welcome mapping handles only root | Design a dedicated fallback for client routes |
| Using `server.servlet.context-path=/demo` while requesting `/` | External URL is missing the servlet prefix | Try `/demo/` |
| Auto resource behavior lost after `@EnableWebMvc` | Application replaced part of MVC auto-configuration | Prefer `WebMvcConfigurer` if you want Boot defaults |
| Multiple competing static indexes | Static location/classpath precedence | Remove extra copies and pick one clear source |

Useful commands during development:

```bash
curl -i -H 'Accept: text/html' http://localhost:8080/
curl -i http://localhost:8080/index.html
./gradlew bootRun --args='--debug'
```

`--debug` prints auto-configuration condition evaluations to aid investigation. If Spring Boot Actuator is present and an appropriate endpoint is intentionally exposed, `/actuator/mappings` can help inspect handler mappings; do not expose management endpoints publicly just to debug a welcome page.

With multiple Spring profiles, inspect the effective properties of the active profile. When deploying a JAR/WAR/container, verify `index.html` inside the **actual artifact**, not only in your working tree.

## 16. Common misconceptions and self-check

**Misconceptions:**

1. “An `index.html` anywhere becomes the home page.” False: it must sit in evaluated static locations or be an `index` template recognized by an engine.
2. “Template `index.html` beats static because templates are dynamic.” False: static comes before template in welcome fallback.
3. “Welcome page always beats `@GetMapping("/")`.” False: application routes are evaluated first.
4. “`templates/index.html` is always served directly at `/index.html`.” False: templates need a view engine and are not static assets by default.
5. “Changing `spring.mvc.static-path-pattern` is the same as changing `spring.web.resources.static-locations`.” False: one changes the URL, the other changes where files are looked up.
6. “Even after changing the static pattern, root always uses static index automatically.” False: the `/**` condition for static welcome must be considered.
7. “Once an SPA has an index, every deep link works automatically.” False: dedicated fallback routing is needed for client-side URLs.
8. “`@RestController` returning `"index"` means rendering a template.” False: that is the response body.
9. “Editing a source file automatically updates an already-built JAR.” False: resources must be synced and usually restarted.
10. “Root showing login means welcome wasn't found.” False: filters/security can run before MVC.

**Review questions:**

- Given `static/index.html`, `templates/index.html`, and Thymeleaf with no `/` route, which file is chosen by default?
- If `@GetMapping("/")` is added, why can `/` differ from `/index.html`?
- Why is `src/main/resources/resources/index.html` on the valid list?
- When setting `spring.web.resources.static-locations=classpath:/website/`, where must the static index be moved?
- Why does `/assets/index.html` still work while `/` loses its static welcome after setting `spring.mvc.static-path-pattern=/assets/**`?
- When is the logical template `index` rendered instead of the static index?
- With `server.servlet.context-path=/shop`, what is the external URL of the welcome page?
- What is the first diagnostic step if requesting `/` redirects to login?

**Practical rule of thumb:** For a simple static landing page, place **one** `index.html` in `src/main/resources/static/`, keep default static mappings, and do not define a duplicate root route. When dynamic HTML is needed, intentionally use a template/view controller. When the application needs special behavior at `/`, declare a clear route and treat the welcome page as a **fallback**.

### References

- Spring Boot 3.3 — Servlet web applications, Static Content / Welcome Page: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive web applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — MVC static resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Guide — Serving Web Content with Spring MVC: https://spring.io/guides/gs/serving-web-content