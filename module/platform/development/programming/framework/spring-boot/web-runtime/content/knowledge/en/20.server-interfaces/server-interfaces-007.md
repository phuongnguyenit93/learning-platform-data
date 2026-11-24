# View Rendering Capabilities of MVC and WebFlux by Template Engine

## 1. What Is Server-Side View Rendering?

In a web application, the server can return JSON so the frontend builds the UI, send prebuilt static HTML files, or **combine data with an HTML template to generate dynamic HTML** before returning it to the client. This last approach is called *server-side view rendering*.

For example, a browser sends `GET /hello?name=Mai`. The controller prepares the model `visitor = "Mai"`, selects the `welcome.html` template, and the engine substitutes the data into the right places and returns an HTTP response containing HTML. The browser receives the final HTML and **does not need to understand Thymeleaf or FreeMarker syntax**.

Both Spring Boot web stacks can perform this work:

- **Spring MVC (Servlet):** `DispatcherServlet` coordinates handlers, pairs `Model` + view name, and uses `ViewResolver` and `View` to render.
- **Spring WebFlux (Reactive):** `DispatcherHandler` coordinates handlers, `ViewResolutionResultHandler` resolves view names/models, and a reactive `View` writes the response under a `Mono<Void>` contract.

Both can use **Thymeleaf**, **FreeMarker**, and **Mustache**. The major differences lie in the HTTP pipeline, return types, and how asynchronous model data is prepared; the HTML template itself can remain identical.

**Objective:** learn how to choose an engine, write controllers and templates that run on MVC/WebFlux, understand rendering constraints in reactive environments, and handle errors, performance, and escaping for HTML UIs.

## 2. Distinguishing View, Model, Template, and JSON Body

| Concept | Role | Example |
|---|---|---|
| **Model** | Data consumed by the view; typically name–value pairs | `visitor = "Mai"`, `courses = List.of(...)` |
| **Logical view name** | Name the controller asks to render | `"welcome"` |
| **ViewResolver** | Finds a `View` matching the logical name, locale/media type/config | Maps `welcome` to a Thymeleaf template |
| **Template** | HTML/text template containing expressions and loops/conditionals | `src/main/resources/templates/welcome.html` |
| **Template engine** | Processes template and model to produce HTML/text | Thymeleaf, FreeMarker, Mustache |
| **View** | Framework contract used to render the model into an HTTP response | MVC `org.springframework.web.servlet.View`; WebFlux `org.springframework.web.reactive.result.view.View` |
| **HTTP response** | Status, headers, and body actually received by the client | `200 OK`, `Content-Type: text/html`, HTML bytes |

**Important:** a `@Controller` method returning `String "welcome"` is typically treated as a **view name**; a method on `@RestController` (equivalent to `@Controller` + `@ResponseBody`) returning `"welcome"` writes **that literal string as the body**, without looking up `welcome.html`.

```java
// Render HTML via ViewResolver (placed in @Controller):
@GetMapping("/page")
public String page(Model model) {
    model.addAttribute("visitor", "Mai");
    return "welcome";
}

// Return text data (placed in @RestController or annotated with @ResponseBody):
@GetMapping("/text")
@ResponseBody
public String text() {
    return "welcome";
}
```

The two methods above are **illustrative snippets inside appropriate controllers**, not a standalone Java file. The difference comes from `@ResponseBody`, not just because both return `String`. With `ResponseEntity<String>` or `@ResponseBody`, the framework writes the body using message converters/codecs; views require the resolve/render step.

## 3. Template Engines and Support Matrix in Spring Boot 3.3

Spring Boot auto-configures view rendering when a matching template starter is on the classpath, unless overridden by the application.

| Technology | Spring MVC | Spring WebFlux | Notes |
|---|---|---|---|
| **Thymeleaf** | Yes, via Thymeleaf Spring MVC integration | Yes, via Thymeleaf Reactive integration | Uses natural HTML templates, `th:text`, `th:each`, `th:if` |
| **FreeMarker** | Yes | Yes | WebFlux does not support all FreeMarker features available on the Servlet stack; check specific features |
| **Mustache** | Yes | Yes | Minimal-logic templates, suited for basic data interpolation |
| **Groovy Markup Templates** | Boot provides MVC auto-configuration | Not in Boot 3.3's auto-configured template engine list for WebFlux | Avoid assuming it works out of the box on the reactive stack just by adding the dependency |
| **JSP/JSTL** | Belongs to Servlet/MVC with packaging limits on embedded servers | Not supported as Servlet-style JSP | WebFlux does not use a Servlet/JSP rendering pipeline |

Typical starters: `spring-boot-starter-thymeleaf`, `spring-boot-starter-freemarker`, `spring-boot-starter-mustache`. By default, Boot looks for templates under `src/main/resources/templates`. Do not mix multiple template engines just to resolve the same view names unless truly needed; that can introduce multiple resolvers and confusing view selection order.

In apps using **`spring-boot-starter-web`**, Boot normally selects MVC/Servlet. With **`spring-boot-starter-webflux`** (and without the web starter), Boot selects reactive WebFlux. When both are present, Boot normally defaults to Servlet/MVC; adding `WebClient` does not automatically switch the server to reactive.

Distinguish the **template engine** from the **HTTP stack**: Thymeleaf does not turn MVC into non-blocking; adding FreeMarker does not turn WebFlux into Servlet. Templates define how content is generated, while the stack defines how requests and responses are executed.

## 4. How Spring MVC Resolves Views

```text
Browser GET /hello
       │
       ▼
Tomcat/Jetty → Servlet Filter → DispatcherServlet
                                │
                                ▼
                     HandlerMapping / HandlerAdapter
                                │
                                ▼
                          @Controller
                  model.addAttribute("visitor", ...)
                  return "welcome"
                                │
                                ▼
                     ViewResolver (logical name)
                                │
                                ▼
             ThymeleafView / FreeMarkerView / ...
                                │
                                ▼
                    Template + model → HTML
                                │
                                ▼
                         HTTP 200 + HTML
```

Specifically:

1. `DispatcherServlet` receives the request after container filters.
2. Spring selects the handler, binds parameters/path variables, and invokes the controller.
3. The controller can populate `Model`/`ModelMap` or return `ModelAndView`. A `String` returned from `@Controller` is typically a view name.
4. `ViewResolver` resolves a `View` based on the logical name, locale, and configuration. With Thymeleaf, `"welcome"` resolves to `classpath:/templates/welcome.html` by default.
5. The `View` processes the template and model; the output is written to `HttpServletResponse` with appropriate status and headers.

If the controller returns `ModelAndView`, it bundles both the view name and the model in one object. `redirect:/target` in MVC typically produces a redirect response (rather than rendering a template in the current request). If a handler has `@ResponseBody`, the view-resolution step above is skipped.

Template rendering can consume CPU, allocate objects, invoke expressions/formatters, and in poorly designed apps even trigger database queries from inside the view. Keep queries and DTO preparation in services/controllers so templates receive only the data needed for display.

## 5. How Spring WebFlux Resolves Views

WebFlux also has the concept of view name + model, using reactive components:

```text
Browser GET /hello
       │
       ▼
HTTP server (typically Reactor Netty)
       │
       ▼
WebFilter → DispatcherHandler
                 │
                 ▼
        HandlerMapping / HandlerAdapter
                 │
                 ▼
          @Controller returns:
          Mono<Rendering>
                 │
                 ▼
      ViewResolutionResultHandler
                 │
                 ▼
     Reactive ViewResolver / View
                 │
                 ▼
    Model + template → HTML response
```

Key return types to know in a WebFlux `@Controller`:

- `String`: logical view name when `@ResponseBody` is absent.
- `Mono<String>`: view name emitted asynchronously; avoid confusing with JSON/text if `@ResponseBody` is not present.
- `Rendering` or `Mono<Rendering>`: object combining view name, model, status, and headers; this is `org.springframework.web.reactive.result.view.Rendering`, analogous to `ModelAndView` in MVC.
- `Model` or model attributes: data for the template; WebFlux supports certain reactive values in the model and awaits their resolution per framework contract.
- In WebFlux functional endpoints, `ServerResponse.ok().render("welcome", model)` returns a `Mono<ServerResponse>` to render a view.

**A reactive server does not mean every template engine streams HTML element by element.** Many engines/views build HTML from a resolved model before writing the response. A `Flux` placed into the model may need to be collected or handled via an engine-specific mechanism. Never assume templates stream HTML lines immediately as a `Flux` emits. Thymeleaf has dedicated reactive/streaming support, but it requires appropriate configuration and model types; the basic examples below **render a complete page**.

Unlike MVC, a controller can await non-blocking data via `Mono` before constructing `Rendering`, without calling `block()` on the Netty event loop just to obtain page data.

## 6. Complete Example A: Spring MVC + Thymeleaf

A standalone Java 17+, Spring Boot 3.3.13, Gradle project. `GET /hello?name=Mai` renders `welcome.html` with the user's name and a list of courses.

**Structure:**

```text
mvc-view-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/mvcview/MvcViewApplication.java
    └── resources/
        ├── application.properties
        └── templates/welcome.html
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
# Uses default Thymeleaf configuration:
# spring.thymeleaf.prefix=classpath:/templates/
# spring.thymeleaf.suffix=.html
```

**`src/main/java/com/example/mvcview/MvcViewApplication.java`:**

```java
package com.example.mvcview;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@SpringBootApplication
public class MvcViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcViewApplication.class, args);
    }
}

@Controller
class HtmlPageController {

    @GetMapping("/hello")
    public String hello(
            @RequestParam(defaultValue = "Lan") String name,
            Model model) {

        model.addAttribute("visitor", name);
        model.addAttribute("courses", List.of("Java", "Spring MVC", "Thymeleaf"));
        return "welcome"; // View name, NOT response text.
    }

    @GetMapping("/plain")
    @ResponseBody
    public String plain() {
        return "welcome"; // Text body because of @ResponseBody.
    }
}
```

This file has one top-level `public class`, `MvcViewApplication`; `HtmlPageController` is a valid package-private class in the same file. Boot component scanning picks up the controller because it resides in the same package as the application class.

**`src/main/resources/templates/welcome.html`:**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome Page</title>
</head>
<body>
    <main>
        <h1 th:text="|Hello, ${visitor}!|">Hello!</h1>
        <p>Topics currently being studied:</p>
        <ul>
            <li th:each="course : ${courses}"
                th:text="${course}">Course</li>
        </ul>
    </main>
</body>
</html>
```

Thymeleaf syntax used:

- `th:text` inserts text into the HTML element and **escapes** special characters in the data so text cannot become dangerous HTML.
- `|...${visitor}...|` is Thymeleaf *literal substitution*, combining text and expressions.
- `th:each` loops over `courses`; the inner `th:text` renders each element.
- `xmlns:th` helps templates/IDEs recognize the `th` namespace, though the browser never runs Thymeleaf; the server already rendered the output.

**Run and test:**

```bash
gradle bootRun
```

In a project with a Gradle Wrapper, you can run `./gradlew bootRun` on macOS/Linux or `.\gradlew.bat bootRun` on Windows PowerShell. Use JDK 17+ and a Gradle version compatible with Spring Boot 3.3.

```bash
curl -i "http://localhost:8080/hello?name=Mai"
curl -i "http://localhost:8080/plain"
```

The `/hello?name=Mai` request is expected to return **HTTP 200**, `Content-Type` matching `text/html`, and rendered HTML containing lines like:

```html
<h1>Hello, Mai!</h1>
<li>Java</li>
<li>Spring MVC</li>
<li>Thymeleaf</li>
```

Those HTML lines are **output excerpts**, not the full body; whitespace and formatting may vary. The `/plain` request returns the body string `welcome` instead of rendered HTML. If `/hello` is called without `name`, Thymeleaf displays `Hello, Lan!`.

**Actual path:** request → `hello` controller → adds `visitor`/`courses` to model → returns view name `welcome` → `ThymeleafViewResolver` finds `welcome.html` → template produces HTML → response sent to browser. That is server-side rendering; raw `th:*` template source is never sent to the browser to evaluate.

## 7. Complete Example B: Spring WebFlux + Thymeleaf

The next exercise uses a **separate project** so we do not mix `spring-boot-starter-web` and `spring-boot-starter-webflux` and accidentally run MVC. The HTML template matches Example A to highlight that the main change is the controller/pipeline.

**Structure:**

```text
webflux-view-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/fluxview/FluxViewApplication.java
    └── resources/
        ├── application.properties
        └── templates/welcome.html
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
```

**`src/main/java/com/example/fluxview/FluxViewApplication.java`:**

```java
package com.example.fluxview;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FluxViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(FluxViewApplication.class, args);
    }
}

@Controller
class ReactivePageController {

    @GetMapping("/hello")
    public Mono<Rendering> hello(
            @RequestParam(defaultValue = "Lan") String name) {

        return Mono.delay(Duration.ofMillis(20))
                .map(tick -> Rendering.view("welcome")
                        .modelAttribute("visitor", name)
                        .modelAttribute(
                                "courses",
                                List.of("Java", "Spring WebFlux", "Thymeleaf"))
                        .build());
    }

    @GetMapping("/plain")
    @ResponseBody
    public Mono<String> plain() {
        return Mono.just("welcome");
    }
}
```

**`src/main/resources/templates/welcome.html`:** reuse the **exact** HTML template from Example A without changing syntax. Because this is a standalone project, you still need to create `welcome.html` inside Project B's `templates` directory.

Here `Mono.delay(Duration.ofMillis(20))` merely **simulates asynchronously arriving data** without requiring a database. Once the `Mono` emits, `Rendering.view("welcome")` bundles the view name and model; WebFlux renders it to HTML via the Thymeleaf integration. In real applications, replace the timer with non-blocking sources like `WebClient` or R2DBC, with proper timeout and error handling.

**Run and test:**

```bash
gradle bootRun
```

If running both projects simultaneously, each uses its own port per the examples. With WebFlux on port 8081:

```bash
curl -i "http://localhost:8081/hello?name=Mai"
curl -i "http://localhost:8081/plain"
```

`/hello?name=Mai` is expected to return **HTTP 200 + HTML**, containing `Hello, Mai!` and lines for `Java`, `Spring WebFlux`, and `Thymeleaf`. `/plain` returns text body `welcome` (without resolving a template) because of `@ResponseBody`.

Even though the return type `Mono<Rendering>` is reactive, that **does not guarantee individual HTML elements are streamed independently**. In this simple example, the model is resolved, the template renders into an HTML page, and then the response is written. Any CPU-heavy template evaluation or blocking calls inside templates remain costs that must be managed.

## 8. WebFlux Functional Endpoints Can Render Views Too

Beyond `@Controller`, WebFlux supports functional routing with `RouterFunction<ServerResponse>`. `ServerResponse.ok().render(...)` goes directly from a handler function to the view renderer.

Example **to add as a `@Configuration` class inside the WebFlux project** (the snippet below is a complete class):

```java
package com.example.fluxview;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class FunctionViews {

    @Bean
    RouterFunction<ServerResponse> viewRoutes() {
        return route(GET("/functional"), request ->
                ServerResponse.ok().render("welcome", Map.of(
                        "visitor", "Guest",
                        "courses", List.of("WebFlux.fn", "Thymeleaf"))));
    }
}
```

Save this class as `FunctionViews.java` in package `com.example.fluxview`, keeping the `welcome.html` template. Visit `http://localhost:8081/functional` to render a page greeting `Guest`, along with `WebFlux.fn` and `Thymeleaf`. `ServerResponse.ok().render(...)` returns a `Mono<ServerResponse>` managed by the framework.

**Do not confuse:** `ServerResponse.ok().bodyValue(map)` builds a response from a body (usually serialized to JSON by codecs), whereas `render(viewName, model)` requests a view/template. In MVC annotated controllers you return a view name or `ModelAndView`; in WebFlux annotated controllers you return a view name or `Rendering`; in WebFlux.fn you call `ServerResponse.render`.

## 9. Asynchronous Models and Practical Limits of Reactive Rendering

Spring WebFlux can fetch data in a non-blocking manner before rendering:

```java
// Snippet inside a WebFlux @Controller;
// service.findProfile(id) returns a Mono<Profile> defined in the app.
@GetMapping("/profiles/{id}")
public Mono<Rendering> profile(@PathVariable String id) {
    return service.findProfile(id)
            .map(profile -> Rendering.view("profile")
                    .modelAttribute("profile", profile)
                    .build());
}
```

This is an **illustrative snippet**, not a standalone runnable file: it assumes `service`, `Profile`, a `profile.html` template, and imports for `PathVariable`/`Rendering`. This keeps data fetching non-blocking and constructs the rendering only once the profile is ready.

In WebFlux, `Model` can also contain reactive attributes like `Mono<Account>` (the framework can resolve reactive values depending on model/view type). However, not every engine supports rendering an **infinite `Flux`** the way you might expect. Before placing a `Flux` in the model, verify:

- Is the `Flux` finite or infinite?
- Will all items be collected before rendering? If so, bound memory and item count.
- Does the view engine genuinely provide a **reactive streaming/data-driver mode** for that view and template?
- If the client disconnects, are the data source and cleanup cancelled properly?
- Does rendering evaluate expressions that call blocking APIs or heavy synchronous code on the event loop?

**Do not call `block()` inside a WebFlux controller** just to turn `Mono<Profile>` into `Profile`. It can block the event loop and hurt concurrency. Compose with `map`/`flatMap` and return a publisher as shown above.

A template engine may expose a reactive API externally while still performing CPU-bound or synchronous HTML formatting internally. WebFlux reduces thread blocking when **waiting on I/O**, not CPU cost when formatting HTML. Avoid claiming "Thymeleaf on WebFlux always streams element by element" or "WebFlux always renders HTML faster than MVC."

## 10. Configuring View Resolvers, Template Paths, and Caching

With the Thymeleaf starter, Spring Boot 3.3 auto-configures most common components. Under default configuration, view name `"welcome"` looks for `classpath:/templates/welcome.html`.

Example development configuration:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

Set `cache=false` only when you need convenient template reloading during development. Production should normally enable caching to avoid repeatedly loading and parsing templates. Template engine `cache` is not the same as HTTP caching in browsers or CDNs; those are configured separately.

For FreeMarker, corresponding options include `spring.freemarker.template-loader-path`, `spring.freemarker.suffix`, and `spring.freemarker.cache`. Template files use `.ftlh` under standard Boot FreeMarker defaults. For Mustache, templates default to `.mustache` (with starter `spring-boot-starter-mustache`). **Do not copy MVC resolver configurations into WebFlux** where APIs live in different packages; prefer Boot properties for the starter actually in use.

The configurer interfaces also differ:

- MVC: `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, resolvers/views in `org.springframework.web.servlet...`.
- WebFlux: `org.springframework.web.reactive.config.WebFluxConfigurer`, `org.springframework.web.reactive.result.view...`.

When customizing FreeMarker, Spring MVC and WebFlux register resolvers differently; for instance, WebFlux provides `configureViewResolvers(ViewResolverRegistry registry)` and `registry.freeMarker()`, paired with an appropriate `FreeMarkerConfigurer`. For Thymeleaf on WebFlux, Thymeleaf provides dedicated reactive integration (such as `ThymeleafReactiveViewResolver`). If the Boot starter already supplies the required beans, do not register duplicate resolvers to redo what auto-configuration already handles.

Do not blindly add `@EnableWebMvc` or `@EnableWebFlux` when using Boot: these annotations hand broad configuration control back to the application and can alter Boot's default auto-configured helpers. When only a small hook is needed, use a configurer or properties.

## 11. Handling Forms, Fragments, Redirects, and Status Codes

Template-rendered HTML works well for list pages, forms, and HTML fragments.

**Forms:** In MVC, a controller can place a form-backing object in the model; Spring MVC/Thymeleaf binds inputs and displays validation errors. WebFlux annotated controllers also support model binding and validation, though **data types and asynchronous handling differ**. When re-rendering an invalid form, the model must carry both submitted values and error details; apply CSRF protection suitable for authenticated/session-based apps.

**Fragments:** Thymeleaf supports reusable structure:

```html
<!-- templates/fragments/footer.html -->
<footer th:fragment="footer">
    <small>Example copyright</small>
</footer>
```

Another page can include it:

```html
<div th:replace="~{fragments/footer :: footer}"></div>
```

These two HTML snippets illustrate fragment syntax; you must create the corresponding footer file inside `templates`. This is a **Thymeleaf capability**, not decided separately by MVC vs. WebFlux. For HTML-over-the-wire/HTMX, fragments can be rendered instead of whole pages, though returning multiple fragments or streaming them depends on the Spring Framework version and app contract; do not assume every Boot 3.3 project includes newer Framework fragment APIs.

**Redirects:** MVC commonly uses view name `"redirect:/dashboard"` to trigger a redirect. In a WebFlux annotated controller, `Rendering.redirectTo("/dashboard").build()` is an explicit API; redirect responses carry a 3xx status + `Location` without rendering the dashboard template in the initial request.

**Status/headers:** MVC provides `ModelAndView`, `ResponseEntity`/`@ResponseStatus`, and return-type-specific mechanisms. WebFlux `Rendering.view("...").status(HttpStatus.CREATED).header("X-...", "...").build()` attaches status and headers through its API. Never assume an HTML view always returns 200, as redirects, errors, or custom settings can yield other statuses.

## 12. Escaping and Trust Boundaries in Templates

Templates are server-side code/logic with access to model objects and, in some engines, privileged beans or expressions. **Never let users edit or supply arbitrary template expressions** to be rendered with application privileges.

For example, a user-supplied `name` query string could contain `<script>...`. In Thymeleaf:

- `th:text` inserts **HTML-escaped text**.
- `th:utext` inserts **unescaped HTML**, suitable only when content has been explicitly verified/sanitized for that contract and purpose.
- Never pass `?view=...` directly as a view name without an allowlist; that can lead to unintended template selection, resource exposure, or expression/template injection depending on configuration.
- Never put secrets, session tokens, internal DTOs, or data not meant for the browser into the model merely because templates run on the server.
- For authenticated forms, use CSRF protection, cookies, and headers aligned with the framework and threat model; automatic HTML escaping does not replace authorization, CSRF checks, or dangerous-URL validation.

**Context-sensitive HTML escaping:** Inserting text into element content, HTML attributes, URLs, JavaScript, or CSS carries distinct risks. In particular, never concatenate user data into JavaScript strings or `href="javascript:..."` and assume `th:text` elsewhere makes the page safe. Use context-appropriate expressions, URL builders, and validation at each point.

Security differences here depend primarily on **how the engine and data sources are used**, not a claim that MVC is inherently safer or that WebFlux blocks XSS automatically.

## 13. Performance and Strategy: Choosing MVC or WebFlux for HTML Rendering

| Question | Guiding Thought |
|---|---|
| Does the app mainly render a few HTML pages from synchronous/JPA data? | MVC + a template engine is usually simpler and well suited |
| Does data come from genuinely reactive APIs/drivers? | WebFlux helps compose async I/O, though view rendering cost still remains |
| Do you need chunked HTML streaming like SSE or HTML-over-the-wire? | Check the engine, renderer type, and exact framework version APIs; do not assume standard templates stream automatically |
| Does a page render huge lists? | Paginate or lazy-load; avoid rendering hundreds of thousands of HTML nodes in one response |
| Is template parsing frequent? | Enable production caching, measure rendering cost, and keep templates simple |
| Does a template call databases/APIs during evaluation? | Move queries to services before rendering and bound latency/concurrency |
| Do you need SEO / fast initial HTML? | Server-rendered HTML helps because the browser gets HTML immediately, though caching and payload size still matter |

Do not judge WebFlux by the label "reactive" while ignoring your data sources. Running blocking JDBC directly on Reactor Netty event loops harms throughput; without truly reactive data sources, MVC is often easier to build, observe, and operate. Conversely, MVC also supports asynchronous request processing; do not claim MVC is "completely incapable of async."

On both stacks, SSR decisions depend on user experience, SEO needs, application lifecycle, render cost, template engine availability, and the data ecosystem. One project can both render HTML and serve JSON APIs; doing both does not require splitting into two separate web servers.

## 14. Testing and Detecting Rendering Errors

### 14.1. Inspecting Real HTTP Content

After starting the apps, run:

```bash
curl -i "http://localhost:8080/hello?name=Lan"
curl -i "http://localhost:8081/hello?name=Lan"
```

In both examples, the HTML response should include the greeting and the items `Java`, `Spring ...`. Inspect the **rendered HTML body**, not just HTTP status 200. If an app returns literal `welcome`, check whether the controller has `@RestController`/`@ResponseBody`.

### 14.2. Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Browser receives literal `welcome` instead of a page | Method belongs to `@RestController`/`@ResponseBody`, writing the string as body | Switch to `@Controller` returning a view name, or return an appropriate `Rendering` |
| `TemplateInputException` / template not found | Wrong path, case mismatch, wrong suffix/prefix, template not packaged on classpath | Check `src/main/resources/templates`, filename, and engine config |
| Controller returns 200 but body lacks data | Wrong attribute name, missing value in model, wrong template expression | Match `model.addAttribute("visitor",...)` with `${visitor}` |
| Using Thymeleaf in an app without the starter | Missing resolver/engine on classpath | Add `spring-boot-starter-thymeleaf` and check the dependency tree |
| Expected WebFlux, actually running MVC | Both `starter-web` and `starter-webflux` present; Boot prefers Servlet | Check dependencies and `ApplicationContext` type |
| Template changes do not appear in development | Template cache is enabled | Check `spring.thymeleaf.cache=false` in the `dev` profile |
| Poor performance under load | Heavy rendering, huge model, blocking queries inside template | Measure render latency, profile CPU, paginate, move I/O out of templates |
| HTML injection/XSS | `th:utext` or unvalidated HTML concatenation | Switch to `th:text` for plain text and check context escaping |
| WebFlux hangs waiting for data | `block()` or synchronous I/O on the event loop | Inspect thread dumps/traces, use non-blocking Publishers, offload blocking if unavoidable |
| 404 when requesting static CSS | Static assets belong in static folders, not template HTML | Check `resources/static` and stack URL mappings |
| Unexpected HTML error page | Error view conventions, handlers, and content negotiation differ by stack | Check `error` templates and Boot MVC/WebFlux documentation separately |

### 14.3. Distinguishing HTML Tests from JSON Tests

When testing views, verify `Content-Type: text/html` and the rendered HTML rather than asserting only the view name. MVC can use `MockMvc` to assert view name and model; WebFlux has `WebTestClient` for live/mock HTTP verification. For integration tests with a real server, both stacks support `@SpringBootTest(webEnvironment = RANDOM_PORT)` to make HTTP requests and assert the response body. Testing the template engine over HTTP catches path bugs, expression errors, and view resolver misconfigurations that pure controller unit tests miss.

## 15. Misconceptions to Avoid

- **"WebFlux is only for JSON APIs and cannot render HTML."** False: WebFlux supports view resolution and Thymeleaf/FreeMarker/Mustache.
- **"Just adding `spring-boot-starter-thymeleaf` makes a `@RestController` render templates."** False: `@ResponseBody` writes data directly to the body.
- **"With the same template engine, MVC and WebFlux share the same `ViewResolver` classes."** False: framework classes and APIs live in different packages, even though template syntax can stay the same.
- **"`Mono<Rendering>` guarantees HTML streams element by element."** False: reactive composition is separate from engine output streaming.
- **"Thymeleaf templates are executed by the browser."** False: the engine runs on the server; the browser receives the resulting HTML.
- **"Using WebFlux means all rendering is non-blocking."** False: template rendering can still consume CPU or run synchronous code.
- **"JSP works identically for MVC and WebFlux."** False: JSP is tied to the Servlet stack; WebFlux does not use JSP as a standard view technology.
- **"`th:text` and `th:utext` provide equal protection."** False: `th:utext` emits unescaped HTML into the output.
- **"A view name is always the literal full filename."** False: `ViewResolver` combines the logical name with prefix, suffix, locale, and other settings.

## 16. Official Reference Documentation

1. Spring Boot 3.3, Servlet Web Applications — Template Engines and static resources: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
2. Spring Boot 3.3, Reactive Web Applications — Template Engines (Thymeleaf, FreeMarker, Mustache): https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
3. Spring Framework — MVC View Resolution: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html
4. Spring Framework — MVC View Technologies: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
5. Spring Framework — WebFlux View Technologies (Thymeleaf/FreeMarker, security notes): https://docs.spring.io/spring-framework/reference/web/webflux-view.html
6. Spring Framework 6.1 — `Rendering` API for WebFlux: https://www.springframework.org/spring/docs/6.1.0-RC2/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html
7. Thymeleaf — Spring integration and HTML escaping documentation: https://www.thymeleaf.org/documentation.html

**Takeaway:** Both MVC and WebFlux support server-side template rendering. Choose `@Controller` with a view name or `Rendering`, supply an appropriate model, let the resolver locate the template, and return rendered HTML. With WebFlux, non-blocking I/O helps prepare data asynchronously, yet actual rendering and streaming still depend on the engine and model design; on both stacks, watch escaping, caching, and performance.