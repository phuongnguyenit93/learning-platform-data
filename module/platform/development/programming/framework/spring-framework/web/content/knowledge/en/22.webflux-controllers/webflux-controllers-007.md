# Returning Views, Model, and Integrating Reactive Template Engines in Spring WebFlux

## 1. When WebFlux Returns More Than JSON

Spring WebFlux is often introduced via `@RestController` returning `Mono<Product>`, `Flux<Product>`, and JSON. Yet WebFlux also serves **server-side rendered HTML**: a browser sends a GET request, `@Controller` prepares a **Model**, returns a **logical view name** or a `Rendering` object, and a template engine like Thymeleaf produces HTML.

Three components to distinguish:

- **View**: the output presentation template, e.g., `src/main/resources/templates/catalog.html`, resolved via logical view name `"catalog"`.
- **Model**: a name → data map read by the template, e.g., `title = "Products"`, `products = Flux<Product>`.
- **Reactive view resolution/rendering**: the framework takes the return value, selects a `ViewResolver`, resolves reactive model attributes appropriately, and writes HTML to the HTTP response. Reactor `Mono`/`Flux` does not automatically turn templates into unbounded HTML streams.

Lesson objectives:

1. Understand the flow `DispatcherHandler → HandlerResult → ViewResolutionResultHandler → ViewResolver → View → ServerHttpResponse`.
2. Return a `String` logical view name from `@Controller` and pass data via `Model`.
3. Distinguish `@Controller` returning a view from `@RestController`/`@ResponseBody` returning a JSON or text body.
4. Understand `Mono<String>` view names, `Mono<Rendering>`, and a `Model` holding `Mono<T>` or `Flux<T>` attributes.
5. Grasp the difference between a `Flux<T>` attribute (often collected into a `List<T>` before view rendering) and HTTP SSE/streaming.
6. Configure Thymeleaf WebFlux integration in Spring Boot 3 and compare FreeMarker/Mustache with reactive template engines.
7. Build a runnable Java 17 application with list and detail pages, 404 handling, redirect, reactive model, JSON API, and `WebTestClient` tests.
8. Diagnose missing templates, unrendered HTML, event-loop blocking in templates, unescaped data, caching, CSRF, and Servlet/WebFlux misconceptions.

**Scope:** Spring Framework 6.x, Spring Boot 3.x, Java 17+, and the **Spring WebFlux** reactive stack. Runnable examples use Boot 3.3.13 with default Reactor Netty, `spring-boot-starter-webflux`, and `spring-boot-starter-thymeleaf`. Do not use JSP/Servlet-specific ViewResolvers or `org.springframework.web.servlet.ModelAndView` for WebFlux examples.

## 2. Why Can View Rendering Also Be Reactive?

Imagine a catalog page needing product data from a remote API. If the controller uses WebClient or a reactive repository, it can return or place a `Mono<List<Product>>` into the model **without blocking a Servlet worker waiting for data**. WebFlux uses publishers to await the result and then render the view.

Overview flow:

```text
GET /pages/home
   │
   ▼
Reactor Netty HTTP server
   │
   ▼
DispatcherHandler (Spring WebFlux, not DispatcherServlet)
   │
   ├─ HandlerMapping: selects @Controller method
   └─ HandlerAdapter: invokes method, gets view name and Model
         │
         │ model["title"] = "Catalog"
         │ model["products"] = Flux<Product>
         │ model["featured"] = Mono<Product>
         ▼
HandlerResult
   │
   ▼
ViewResolutionResultHandler
   ├─ selects logical view name "home"
   ├─ queries appropriate ViewResolvers
   ├─ resolves Mono/Flux model attributes before view rendering
   │      ├─ Mono<Product> → Product or attribute absent
   │      └─ Flux<Product> → List<Product> (may need entire sequence)
   └─ renders via Thymeleaf reactive integration
           │
           ▼
      ServerHttpResponse: text/html
```

Spring Framework allows the model to hold reactive wrappers and resolves them before the view actually consumes the data. This is a key difference from standard Spring MVC models.

### 2.1. Reactive Does Not Mean HTML Streams Out on Every Flux Emit

Suppose `Flux<Product>` emits 10,000 rows. If the view renderer needs a complete collection before opening an HTML loop, the framework may **collect them into a List**. In that case:

- The template must wait for the Flux to complete.
- Many items may be held in memory.
- An infinite Flux never completes → the view may never finish.
- An error mid-resolution can prevent normal HTML from being built.

Some template technologies (notably Thymeleaf's reactive integration) support chunked rendering depending on configuration, yet **do not infer from a Flux in the model that the browser receives one HTML item per onNext**. If the goal is continuous live updates, consider SSE, WebSocket, HTML fragment streaming, or pagination.

### 2.2. View Rendering vs JSON Serialization

| Need | Common return | Final component |
| --- | --- | --- |
| GET HTML page | `String` or `Rendering` in `@Controller` | `ViewResolver` + template engine |
| GET JSON data | `Mono<Product>` in `@RestController` | `HttpMessageWriter` / JSON codec |
| GET multiple JSON items | `Flux<Product>` with `@ResponseBody` | JSON encoding, possibly as an array |
| SSE updates | `Flux<ServerSentEvent<?>>` with `text/event-stream` | Streamed response writer |
| Browser redirect | `"redirect:/pages/home"` | Redirect view/status and Location |
| No content | `Mono<ResponseEntity<Void>>` returning 204 | HTTP status/headers, no template |

Content negotiation can also participate in view selection, yet a view-oriented controller does not automatically support both HTML and JSON for every Accept header.

## 3. @Controller, @RestController, and @ResponseBody: Big Differences

### 3.1. @Controller Returning String Is a Template Name

```java
@Controller
class WelcomeController {
    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Hello!");
        return "welcome";
    }
}
```

Spring WebFlux interprets `"welcome"` as a **logical view name**, not a literal response string. With default Thymeleaf auto-config, the view resolver looks for `classpath:/templates/welcome.html` and renders it.

### 3.2. @RestController Returning String Is a Body

```java
@RestController
class WelcomeApi {
    @GetMapping("/api/welcome")
    String welcome() {
        return "welcome";
    }
}
```

Spring writes the string **welcome** to the HTTP response body; it does not look for `welcome.html`. `@RestController` has `@Controller + @ResponseBody` semantics.

### 3.3. @ResponseBody on a Method of @Controller

```java
@Controller
class MixedController {
    @GetMapping("/page")
    String page() {
        return "welcome"; // view name
    }

    @ResponseBody
    @GetMapping("/raw")
    String raw() {
        return "welcome"; // literal body
    }
}
```

**Classic mistake:** using `@RestController`, returning `"home"`, and expecting `home.html` to render. The result is the plain text "home". When the goal is rendering HTML via templates, use `@Controller` and a view name.

### 3.4. @ModelAttribute Does Not Automatically Turn a Method into REST

In an HTML controller, a returned object (other than special simple types) may be treated as a model attribute. `@ModelAttribute("product")` also lets you name the attribute. However, if a method returns `String`, the framework normally interprets it as a **view name**; use `@ModelAttribute` explicitly if you want that String treated as a model attribute, or call `model.addAttribute(...)` for clarity.

## 4. Model: Data Passed into the Template

`org.springframework.ui.Model` is the interface used in both MVC and WebFlux. Example:

```java
@GetMapping("/pages/hello")
String hello(Model model) {
    model.addAttribute("title", "WebFlux Course");
    model.addAttribute("user", new UserView("Lan"));
    return "hello";
}
```

The above is a **snippet**; it requires a `UserView` class and a complete `@Controller`. Model is a map of named attributes. In the template:

```html
<h1 th:text="${title}">Sample Title</h1>
<p th:text="${user.name()}">Sample Name</p>
```

`th:text` passes data through Thymeleaf's HTML escaping mechanism, unlike `th:utext` which renders unescaped markup. Never pass user data into `th:utext` unless the source is genuinely trusted/sanitized under a clear policy.

### 4.1. Mono in Model

Spring WebFlux allows:

```java
@GetMapping("/pages/profile")
String profile(Model model) {
    Mono<Profile> profileMono = service.loadProfile();
    model.addAttribute("profile", profileMono);
    return "profile";
}
```

Before view rendering, reactive model attributes can be resolved into a concrete `Profile` value. Never call `profileMono.block()` inside a WebFlux handler.

### 4.2. Flux in Model

```java
@GetMapping("/pages/items")
String items(Model model) {
    Flux<Item> all = service.findAll();
    model.addAttribute("items", all);
    return "items";
}
```

The WebFlux view infrastructure can resolve `Flux<Item>` into `List<Item>` before rendering. If the source never completes or contains a million items, that is a problem. Therefore HTML lists should paginate and limit at the repository/query level—**never** use an unbounded `collectList` or assume templates solve UI backpressure automatically.

### 4.3. Model Containing Mono.empty()

If `profileMono` completes empty, the model attribute may have no corresponding value. A template writing `${profile.name}` may fail or render unexpectedly. Define clear semantics:

- If the resource does not exist: return 404 with an appropriate view before rendering.
- If the information is optional: provide a fallback or conditional rendering.
- If a remote service errors: do not blindly turn every `onError` into empty, as that hides outages.

A service returning `Mono.empty()` does not mean the framework automatically chooses HTTP 404 for the page.

### 4.4. @ModelAttribute Methods

```java
@ModelAttribute
void common(Model model) {
    model.addAttribute("siteName", "Learn Spring");
}
```

`@ModelAttribute` methods can run before request handlers in the same controller to prepare shared data. However, placing blocking I/O directly inside `@ModelAttribute` still blocks the request path. Use reactive publishers/async style and proper error handling.

### 4.5. Avoid Retaining State Across Requests

A `@Controller` is a singleton Spring bean by default. Never use a mutable field like `private String currentUserName` to store the current request's model data. Concurrent requests can leak one user's data to another. Use local method variables, appropriate request/session scopes, or controlled context.

## 5. How Do ViewResolutionResultHandler and ViewResolver Work?

Spring WebFlux uses `DispatcherHandler` as its front controller. When a handler returns a result, `HandlerResultHandler` implementations process each return-value type. For view rendering, `ViewResolutionResultHandler` selects a `View` from registered `ViewResolver` beans.

Overview steps:

1. `HandlerMapping` selects the method/controller.
2. `HandlerAdapter` executes it and produces a `HandlerResult` containing the return value and Model.
3. `ViewResolutionResultHandler` determines the logical view name from String/Rendering/default translation.
4. The matching `ViewResolver` finds the `View` for that name and locale.
5. Reactive model attributes are resolved per the view contract.
6. The view engine generates HTML and writes it to `ServerHttpResponse` under a publisher reflecting completion.

**Do not import Servlet classes by mistake:**

| Spring MVC Servlet | Spring WebFlux |
| --- | --- |
| `DispatcherServlet` | `DispatcherHandler` |
| `org.springframework.web.servlet.ViewResolver` | `org.springframework.web.reactive.result.view.ViewResolver` |
| `org.springframework.web.servlet.View` | `org.springframework.web.reactive.result.view.View` |
| `ModelAndView` (Servlet) | `Rendering` (reactive view scenarios) |
| `HttpServletRequest` | `ServerHttpRequest`/`ServerWebExchange` |
| `HttpMessageConverter` | `HttpMessageReader`/`HttpMessageWriter` |
| Servlet `Filter` | WebFlux `WebFilter` |

Spring MVC supports reactive return types in certain cases, yet that does **not** turn MVC into WebFlux. Always verify the active application type when debugging.

### 5.1. String Logical Name

```java
return "catalog";
```

With default Thymeleaf, the resolver typically looks up `classpath:/templates/catalog.html`. Never return a filesystem path or URL controlled by user input: logical names must stay within an application-controlled allowlist/trust boundary.

### 5.2. Default View Name

If a view controller returns no name and the handler result qualifies, WebFlux can derive a view name from the request path (stripping leading/trailing slashes). For example, `/pages/default` maps to logical view `pages/default` and template `templates/pages/default.html`.

This is a framework feature, yet **returning an explicit view name** is usually less confusing and easier to refactor. For REST controllers, void/null semantics differ depending on response handling.

### 5.3. Redirects

```java
@GetMapping("/pages/old")
String old() {
    return "redirect:/pages/home";
}
```

The `redirect:` prefix is recognized by the view infrastructure to return a redirect to the target route. The default status in WebFlux `RedirectView` may be 303 See Other; redirect tests should assert 3xx + Location rather than hardcoding 302 unless a specific status policy is configured.

Do not use `forward:` as in Servlet MVC: **WebFlux does not support Servlet FORWARD dispatches**. A redirect triggers a new client request, not a server-side internal forward.

### 5.4. Content Negotiation and Default Views

`ViewResolutionResultHandler` can match `Accept` against view media types. WebFlux provides `HttpMessageWriterView` to render a model as JSON/XML via codecs when configuring default views.

However, that is advanced configuration. For most applications, separate them cleanly:

- `GET /pages/products` → HTML.
- `GET /api/products` → JSON.

Mixing HTML and JSON on a single endpoint demands strict Content-Type, caching, error-handling, and `Accept` testing rules.

## 6. Integrating Reactive Thymeleaf into Spring Boot

### 6.1. Required Dependencies

With Maven and Spring Boot 3:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

The first starter selects the WebFlux/reactive HTTP runtime; the second auto-configures WebFlux-compatible Thymeleaf. Do not also add `spring-boot-starter-web`: when both MVC and WebFlux starters are present, Spring Boot selects **MVC/Servlet application** by default.

### 6.2. Default Template Location

```text
src/main/resources/
├── templates/
│   ├── home.html
│   ├── detail.html
│   └── missing.html
└── static/
    └── css/site.css
```

Boot looks for templates under `classpath:/templates/`. For view name `"home"` and suffix `.html`, the corresponding resource is `classpath:/templates/home.html`.

Do not place server-rendered templates in `src/main/resources/static/` and expect `th:text` expressions to execute. The static handler serves files verbatim.

### 6.3. Common Properties

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

This is a **development profile** to make template edits immediately visible. In production, enable template caching (usually true by default) to avoid repeatedly parsing and compiling templates. Template caching is **distinct** from HTTP response caching and **does not automatically cache data/models**.

### 6.4. Thymeleaf WebFlux Classes

Thymeleaf's reactive integration (maintained by the Thymeleaf project) includes concepts such as:

- `SpringResourceTemplateResolver`.
- `SpringWebFluxTemplateEngine`.
- `ThymeleafReactiveViewResolver`.
- `ThymeleafReactiveView` and reactive view support.

With Boot auto-configuration, **you do not need to manually declare all of those beans**. Customize them manually only when genuinely changing template resolver paths/encoding/engine/dialects or running multiple engines. Misconfiguring a manual resolver can lose auto-config defaults and cause templates to return 500.

### 6.5. Thymeleaf Template Syntax

Common expressions:

| Syntax | Purpose |
| --- | --- |
| `th:text="${title}"` | Escape and display model attribute |
| `th:each="item : ${items}"` | Iterate over model collection |
| `th:if="${item != null}"` | Conditional rendering |
| `th:href="@{/pages/products/{id}(id=${item.id()})}"` | Build URL from path variable |
| `th:object="${command}"` | Select form-backing bean |
| `th:field="*{title}"` | Bind form field |
| `#{message.key}` | Read locale message bundle |
| `th:utext="${rawHtml}"` | Unescaped HTML; requires XSS controls |

When using Java records in templates, the most reliable way to read fields is calling record accessors `item.name()`, `item.id()` per SpringEL/Thymeleaf support. Use `th:utext` only with trusted or strictly sanitized HTML.

## 7. Rendering: View Name, Model, and Status in One Value

Spring WebFlux provides `org.springframework.web.reactive.result.view.Rendering` to build a return value carrying view, model, status, and headers.

```java
@GetMapping("/products/{id}")
Mono<Rendering> detail(@PathVariable long id) {
    return service.findById(id)
        .map(item -> Rendering.view("detail")
                .modelAttribute("product", item)
                .build())
        .switchIfEmpty(Mono.just(
            Rendering.view("missing")
                .status(HttpStatus.NOT_FOUND)
                .modelAttribute("id", id)
                .build()));
}
```

This is a **snippet** requiring controller/service and imports; the complete example is in section 11. Key point: HTTP 404 is decided **before rendering**, rather than expecting Thymeleaf to turn `Mono.empty()` into 404 automatically.

### 7.1. Mono<Rendering> vs Mono<DTO>

- `Mono<Rendering>`: on subscription, emits instructions for **which view to render**.
- `Mono<Product>` in `@RestController`: on completion, the framework serializes a Product to JSON.
- `Mono<String>` in `@Controller`: the String is usually a **view name**, not body text.
- `Mono<ResponseEntity<Product>>` in REST: determines HTTP status/body from the object.
- `Mono<Void>`: represents completion without a payload, or default view name in special cases; do not use it to represent arbitrary views.

### 7.2. Rendering Status and Redirects

If a redirect needs a specific status, you can use `Rendering.redirectTo(...)` and configure status/headers per API version. However, simple `return "redirect:/pages/home";` is often clearest.

Never pass an unvalidated external redirect target from a query param like `return "redirect:" + request.getParameter("next")`; that creates an **open redirect** vulnerability. Use an internal route allowlist or validate hosts/paths.

## 8. Reactive Model: Resolving Data Sources Before Rendering

### 8.1. Putting Mono/Flux Directly into the Model

```java
@GetMapping("/catalog")
String catalog(Model model) {
    model.addAttribute("featured", service.featured()); // Mono<Product>
    model.addAttribute("products", service.findAll());   // Flux<Product>
    model.addAttribute("count", service.findAll().count()); // Mono<Long>
    return "catalog";
}
```

When the view renders, the publishers are subscribed to and resolved into template data. You do not need to call `block()`. However, note:

- Each call to `service.findAll()` can create a new source; the list and count above could execute **two separate queries** if backed by R2DBC.
- When you need a consistent snapshot, design one service call returning a combined DTO instead of invoking uncoordinated publishers.
- If `Flux<Product>` is large, paginate before passing it to the view.
- `Mono.empty()` can leave an attribute absent; implement proper fallback/conditional view logic.
- Model attributes with non-idempotent side effects must never rely on uncontrolled subscription counts.

### 8.2. Preparing Data Before Selecting the View

Alternatively, the controller composes publishers first and then emits `Rendering`:

```java
@GetMapping("/catalog/summary")
Mono<Rendering> summary() {
    return service.findAll()
        .collectList()
        .map(items -> Rendering.view("summary")
            .modelAttribute("total", items.size())
            .modelAttribute("items", items)
            .build());
}
```

Pros: data is concrete, allowing empty/error and status handling. Con: `collectList()` buffers the entire Flux, unsuitable for infinite or large datasets. In production, queries should use pagination and hard limits.

### 8.3. Putting a Mono in Model Does Not Guarantee HTML Streaming

Accepting a `Mono<Product>` or `Flux<Product>` does not turn a template into a continuous push connection. Views normally require concrete model values before rendering. To keep an HTML page open and push incremental updates, design specifically around Thymeleaf reactive modes or WebFlux fragment streaming/SSE.

### 8.4. Model and Reactive Context

WebFlux is not a Servlet application when running on Reactor Netty. Therefore:

- Never cast `ServerWebExchange` to `HttpServletRequest`.
- Never rely on a Servlet filter's ThreadLocal to render the right user/locale across thread switches.
- Use Spring Security's reactive context, Reactor Context, and corresponding APIs for principal, locale, and request data.
- During template rendering, avoid calling blocking services from custom dialects/expressions on the event loop; supply data via properly configured services into the model.

## 9. Reactive Template Engines vs REST Response Streaming

Several flows are commonly confused:

| Flow | Input data | Response |
| --- | --- | --- |
| Standard Thymeleaf | Resolved model (possibly from Mono/Flux) | HTML document |
| Thymeleaf chunked/data-driven | Reactive model + supported config/mode | HTML chunks per engine policy |
| FreeMarker/Mustache | Model for view building | HTML document per engine integration |
| `Flux<ServerSentEvent<?>>` | Continuous emitted events | `text/event-stream`, browser receives events |
| `Flux<DTO>` / JSON | Reactive elements | JSON array or streaming JSON per media type |
| `Flux<Fragment>` / fragment renderer | HTML fragments | HTML fragments per supported API and media type |

**UX decision:** If users need an HTML page to read or submit forms, server-side rendering is usually appropriate. If real-time updates are needed, use SSE/WebSocket or HTML-over-the-wire streaming with a clear DOM-update contract. Never put an infinite Flux in the model of an ordinary HTML page.

### 9.1. FreeMarker and Mustache

Spring Boot supports FreeMarker, Thymeleaf, and Mustache with WebFlux. With the right starters or dependencies, templates are loaded from `src/main/resources/templates` per each engine's conventions. FreeMarker has dedicated WebFlux support; do not assume every Servlet form macro works identically to MVC.

Thymeleaf provides native WebFlux integration maintained by the Thymeleaf project itself. When troubleshooting templates, identify which engine Boot actually auto-configured and which resolver bean handles the view name.

### 9.2. JSP and Servlet-Only Engines

JSP depends on a Servlet/JSP container and is not a suitable view engine for WebFlux running on Reactor Netty. Never place `/WEB-INF/jsp/*.jsp` and configure MVC's `InternalResourceViewResolver` in a reactive WebFlux project expecting Servlet MVC behavior.

### 9.3. HTML Fragments and HTMX

Recent Spring WebFlux versions support fragment-oriented responses such as `Fragment` and `FragmentsRendering`. The goal is returning one or more HTML fragments for a frontend (HTMX/Hotwire) to insert into the DOM, optionally via streaming. These APIs evolve across framework minor/major versions; before copying snippets from another version's docs, verify exact classes, packages, and media types for your 6.x/7.x version.

The runnable example below keeps the **whole-page view** model for clarity and stability on Boot 3.3.

## 10. Template-Related Bugs and Security

### 10.1. Cross-Site Scripting (XSS)

If a user enters a name:

```text
<script>alert("hello")</script>
```

And the template uses:

```html
<p th:text="${name}">name</p>
```

Thymeleaf HTML-escapes the text, so the browser displays the characters as text without executing the script. Conversely:

```html
<p th:utext="${name}">name</p>
```

HTML characters are rendered as markup; **dangerous** when `name` comes from untrusted input. Always validate/sanitize rich HTML if genuinely required, apply context-appropriate escaping for HTML/attributes/JavaScript/URLs, and add CSP where appropriate. Template expression escaping does not replace comprehensive XSS defenses.

### 10.2. Template Name Injection

Never do this:

```java
@GetMapping("/unsafe")
String unsafe(@RequestParam String template) {
    return template; // user controls the view name
}
```

The snippet above is an **anti-pattern**. Template engines can access Spring application beans or resources inside the trust boundary; letting users control template names or content risks template injection, resource disclosure, or open redirects. Use server-controlled allowlists and never allow untrusted users to upload/edit templates.

### 10.3. Form POST / CSRF

Server-rendered HTML typically pairs with session cookies. If browsers perform POST/PUT/DELETE with ambient credentials, configure CSRF in **Spring Security WebFlux**. Reactive security uses `SecurityWebFilterChain`, not Servlet `SecurityFilterChain`. Forms may require hidden CSRF inputs per dialect/security integration; never disable CSRF merely because the app is reactive.

### 10.4. Per-Resource Authorization

Simply hiding a “Delete” button with `th:if` **does not** protect the DELETE endpoint. The backend must check authorization against object ID, owner, and tenant. Model data should contain only fields authorized for the current request; if caching HTML responses, ensure user A's content is never served to user B.

### 10.5. Content Security Policy and URL Escaping

Never build raw HTML with StringBuilder in a controller and skip escaping. Use a template engine and an appropriate CSP. Template-generated URLs must be safe and encoded; prevent open redirects to unvalidated external hosts. Never place access tokens or private data in query strings, logs, or HTML source.

### 10.6. Template Caching vs HTTP Caching

- **Template cache**: stores parsed/compiled template structures for faster rendering; **does not** retain per-user HTML responses.
- **HTTP cache**: browsers/CDNs can cache responses per Cache-Control, ETag, and Vary; consider privacy implications.
- **Service/data cache**: stores business data by key/TTL and invalidation rules.

A user-specific dashboard is unsafe for `Cache-Control: public` simply because Thymeleaf template caching is enabled.

## 11. Runnable Application: Spring Boot 3 + Java 17 + WebFlux + Thymeleaf

The project demonstrates:

- `GET /pages/home`: template `home.html` with a title and three reactive model attributes.
- `GET /pages/products/1`: uses `Mono<Rendering>`, renders `detail.html` with HTTP 200.
- `GET /pages/products/999`: not found, renders `missing.html` with HTTP 404.
- `GET /pages/summary`: `Mono<String>` chooses the template name after counting finishes.
- `GET /pages/greeting?name=...`: HTML escaping via `th:text`.
- `GET /pages/old`: redirects to the new page.
- `GET /api/products`: same service, yet `@RestController` returns a JSON Flux, contrasting view vs body.
- `GET /pages/default`: default template path when a handler returns no explicit view name.

There is no database or remote network so the example stays self-contained; `CatalogService` intentionally uses only a small `List`, `Mono`, and `Flux`. When replacing the service with R2DBC/WebClient, manage subscriptions, errors, and timeouts.

### 11.1. Project Structure

```text
webflux-reactive-views/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── ReactiveViewsApplication.java
    │   │   ├── Product.java
    │   │   ├── CatalogService.java
    │   │   ├── PageController.java
    │   │   └── CatalogApiController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── detail.html
    │           ├── missing.html
    │           ├── summary.html
    │           ├── greeting.html
    │           └── pages/default.html
    └── test/
        └── java/example/ReactiveViewsTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webflux-reactive-views</artifactId>
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
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Only `spring-boot-starter-webflux` is included so Boot does not silently switch to Servlet MVC. The Thymeleaf starter auto-configures the view engine; `@EnableWebFlux` is unnecessary because Boot already provides WebFlux auto-configuration.

### 11.3. ReactiveViewsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveViewsApplication.class, args);
    }
}
```

### 11.4. Product.java

```java
package example;

public record Product(long id, String name, long priceVnd) {}
```

The record holds display data without exposing persistence entities containing sensitive fields.

### 11.5. CatalogService.java

```java
package example;

import java.util.List;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private final List<Product> products = List.of(
        new Product(1L, "Spring WebFlux", 120000L),
        new Product(2L, "Spring Boot", 99000L),
        new Product(3L, "Project Reactor", 85000L)
    );

    public Flux<Product> all() {
        return Flux.defer(() -> Flux.fromIterable(products));
    }

    public Mono<Product> find(long id) {
        return all()
            .filter(item -> item.id() == id)
            .next();
    }
}
```

Both `all()` and `find()` are cold publishers. The example intentionally avoids database access so it is clear the model resolver does not need `block()`. Real applications should include pagination limits, caching/transactions, and data-source error handling.

### 11.6. PageController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/pages")
public class PageController {

    private final CatalogService catalog;

    public PageController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/home")
    public String home(Model model) {
        model.addAttribute("title", "Product catalog");
        model.addAttribute("products", catalog.all());
        model.addAttribute("featured", catalog.find(1L));
        model.addAttribute("count", catalog.all().count());
        return "home";
    }

    @GetMapping("/products/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return catalog.find(id)
            .map(product -> Rendering.view("detail")
                .modelAttribute("product", product)
                .build())
            .switchIfEmpty(Mono.just(
                Rendering.view("missing")
                    .status(HttpStatus.NOT_FOUND)
                    .modelAttribute("id", id)
                    .build()));
    }

    @GetMapping("/summary")
    public Mono<String> summary(Model model) {
        return catalog.all()
            .count()
            .map(count -> {
                model.addAttribute("count", count);
                return "summary";
            });
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Guest") String name,
            Model model) {
        model.addAttribute("name", name);
        return "greeting";
    }

    @GetMapping("/old")
    public String oldPage() {
        return "redirect:/pages/home";
    }

    @GetMapping("/default")
    public void defaultView(Model model) {
        model.addAttribute("message", "Page selected by path");
        // No explicit view name returned; WebFlux can infer
        // logical view name "pages/default" from the request path.
    }
}
```

Meaning:

- `home(Model)` uses reactive attributes; the template engine receives concrete values at render time.
- `detail()` uses the reactive service and selects the view accordingly without blocking the event loop. 404 does not rely on a `Mono.empty` default.
- `summary()` returns `Mono<String>`, emitting the logical view name "summary" once the count is ready.
- `greeting()` renders escaped text through the template.
- `oldPage()` redirects via the `redirect:` prefix.
- `defaultView()` illustrates convention. In production, returning `"pages/default"` explicitly is clearer and less path-coupled.

### 11.7. CatalogApiController.java

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class CatalogApiController {

    private final CatalogService catalog;

    public CatalogApiController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/products")
    public Flux<Product> products() {
        return catalog.all();
    }
}
```

The `/api/products` route uses the JSON HTTP response writer rather than `home.html`. The same `CatalogService` can serve both HTML and JSON without duplicating business logic.

### 11.8. application.properties

```properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

This is development config. Set `spring.thymeleaf.cache=true` for production after verifying hot reload and deployment pipelines.

### 11.9. home.html

File `src/main/resources/templates/home.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${title}">Catalog</title>
</head>
<body>
    <h1 th:text="${title}">Catalog</h1>
    <p id="count" th:text="|Product count: ${count}|">
        Product count: 0
    </p>

    <h2>Featured product</h2>
    <p id="featured" th:if="${featured != null}"
       th:text="${featured.name()}">Product</p>

    <h2>List</h2>
    <ul id="products">
        <li th:each="item : ${products}">
            <a th:href="@{/pages/products/{id}(id=${item.id()})}"
               th:text="${item.name()}">Product name</a>
            <span th:text="${item.priceVnd()}">0</span>
        </li>
    </ul>

    <p><a th:href="@{/pages/summary}">View summary</a></p>
</body>
</html>
```

Thymeleaf iterates with `th:each` after the model Flux resolves. `th:text` escapes content. `@{...}` URL expressions build application links from record accessors rather than unencoded string concatenation.

### 11.10. detail.html

File `src/main/resources/templates/detail.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Product details</title>
</head>
<body>
    <h1>Product details</h1>
    <p id="item-id" th:text="${product.id()}">0</p>
    <p id="item-name" th:text="${product.name()}">Name</p>
    <p id="item-price" th:text="${product.priceVnd()}">0</p>
    <a th:href="@{/pages/home}">Back to list</a>
</body>
</html>
```

The HTTP status of this page is 200 because `Rendering.view("detail")` does not override the status.

### 11.11. missing.html

File `src/main/resources/templates/missing.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Not found</title>
</head>
<body>
    <h1>Product not found</h1>
    <p>Product ID:
        <span id="missing-id" th:text="${id}">0</span>
    </p>
    <a th:href="@{/pages/home}">Catalog</a>
</body>
</html>
```

The “Not found” HTML content and HTTP status 404 are two separate things. `Rendering.status(HttpStatus.NOT_FOUND)` sets the proper status rather than merely showing a message on the page.

### 11.12. summary.html

File `src/main/resources/templates/summary.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Summary</title>
</head>
<body>
    <h1>Catalog summary</h1>
    <p id="summary-count"
       th:text="|Product count: ${count}|">Product count: 0</p>
</body>
</html>
```

`summary(Model)` returns `Mono<String>` that computes `count` before emitting the view name. There is no manual `block()` or `subscribe()`.

### 11.13. greeting.html

File `src/main/resources/templates/greeting.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Welcome</title>
</head>
<body>
    <h1>Welcome</h1>
    <p id="greeting-name" th:text="${name}">Guest</p>
</body>
</html>
```

When `name` is `<script>alert(1)</script>`, `th:text` escapes it into safe text within the HTML context. This example does not test all XSS vectors; it simply contrasts escaping with raw output.

### 11.14. pages/default.html

File `src/main/resources/templates/pages/default.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Default page</title>
</head>
<body>
    <h1>Default page</h1>
    <p id="default-message"
       th:text="${message}">Content</p>
</body>
</html>
```

When `defaultView(Model)` returns void and the framework picks an implicit logical view name from the path, this template is found as `pages/default`. With custom router/view configs, test it or return an explicit view name rather than relying on convention.

## 12. Running and Observing Results

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Fetch the HTML page:

```bash
curl -i http://localhost:8080/pages/home
```

Expected HTTP 200, `Content-Type: text/html` (possibly with charset), and HTML containing:

```html
<h1>Product catalog</h1>
<p id="count">Product count: 3</p>
```

The rendered list contains `Spring WebFlux`, `Spring Boot`, and `Project Reactor`. Actual HTML formatting/indentation may differ from the template, so do not compare byte-for-byte.

Detail:

```bash
curl -i http://localhost:8080/pages/products/1
```

Expected 200 and content showing `Spring WebFlux`.

Missing:

```bash
curl -i http://localhost:8080/pages/products/999
```

Expected HTTP 404 with **the HTML of missing.html**, not just a default JSON error.

Summary:

```bash
curl -i http://localhost:8080/pages/summary
```

Expected 200 and `Product count: 3`.

Redirect:

```bash
curl -i http://localhost:8080/pages/old
```

Expected 3xx with `Location: /pages/home`. Use `curl -L` to follow the redirect.

REST JSON:

```bash
curl -i http://localhost:8080/api/products
```

Expected JSON array:

```json
[
  {"id":1,"name":"Spring WebFlux","priceVnd":120000},
  {"id":2,"name":"Spring Boot","priceVnd":99000},
  {"id":3,"name":"Project Reactor","priceVnd":85000}
]
```

JSON key ordering/indentation is not part of the contract; tests should check fields. The JSON endpoint uses the same service data yet does **not** run Thymeleaf.

### 12.1. Seeing the Difference Between @Controller and @RestController Clearly

If you change `@Controller` on PageController to `@RestController`, `home()` returns the literal string `"home"` as the response body and the page will not render as expected. This is a good mental check to avoid controllers returning view names as raw text.

## 13. WebTestClient: Testing Reactive Views Over HTTP

Tests run with a real Spring Boot context and an embedded reactive web server. Assert HTML against stable text fragments rather than exact rendered whitespace.

File `src/test/java/example/ReactiveViewsTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveViewsTest {

    @Autowired
    WebTestClient client;

    @Test
    void homeRendersHtmlWithResolvedReactiveAttributes() {
        client.get().uri("/pages/home")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Product catalog"));
                    assertTrue(html.contains("Product count: 3"));
                    assertTrue(html.contains("Spring WebFlux"));
                    assertTrue(html.contains("Spring Boot"));
                    assertTrue(html.contains("Project Reactor"));
                });
    }

    @Test
    void detailUsesReactiveRenderingAndReturns200() {
        client.get().uri("/pages/products/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Product details"));
                    assertTrue(html.contains("Spring WebFlux"));
                });
    }

    @Test
    void missingProductIsExplicitHtml404() {
        client.get().uri("/pages/products/999")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Product not found"));
                    assertTrue(html.contains("999"));
                });
    }

    @Test
    void monoViewNameRendersSummary() {
        client.get().uri("/pages/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> assertTrue(
                    html.contains("Product count: 3")));
    }

    @Test
    void greetingEscapesUntrustedHtml() {
        client.get().uri(builder -> builder
                .path("/pages/greeting")
                .queryParam("name", "<script>alert(1)</script>")
                .build())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertFalse(html.contains("<script>"));
                    assertTrue(html.contains("&lt;script&gt;"));
                });
    }

    @Test
    void redirectHasLocationHeader() {
        client.get().uri("/pages/old")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/pages/home");
    }

    @Test
    void jsonApiDoesNotRenderThymeleaf() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].name").isEqualTo("Spring Boot")
                .jsonPath("$[2].priceVnd").isEqualTo(85000);
    }

    @Test
    void implicitPathViewCanResolveTemplate() {
        client.get().uri("/pages/default")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> assertTrue(
                    html.contains("Page selected by path")));
    }

    @Test
    void homeDoesNotExposeThymeleafExpressionsLiterally() {
        client.get().uri("/pages/home")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertFalse(html.contains("th:text="));
                    assertFalse(html.contains("th:each="));
                });
    }
}
```

**Why test both HTML and JSON?** This is the clearest proof that `ViewResolutionResultHandler` and `HttpMessageWriter` are two distinct processing paths inside the same WebFlux application. `homeRendersHtmlWithResolvedReactiveAttributes` also catches bugs where the model renders `Mono/Flux.toString()` literally instead of resolved concrete data.

### 13.1. Tests Can Fail Due to Version/Encoding; Do Not Guess

- If an HTML test fails with 500, inspect the exception for a missing template or Thymeleaf expression error.
- If rendered HTML differs in spacing, use an HTML parser or assert structural semantics rather than raw whitespace.
- If the running app uses Servlet MVC because `spring-boot-starter-web` was accidentally added, verify the actual application type before debugging views.
- If the implicit view test fails due to customized router/view config, return `"pages/default"` explicitly in production; this test intentionally illustrates the WebFlux 6.x convention.
- If an escaping assertion fails in another engine version, inspect how output is escaped and DOM behavior rather than disabling escaping.

The tests above are **provided sample code**; only report “tests PASS” after running Maven and observing actual results.

## 14. Data Optimization Patterns for Reactive HTML Pages

### 14.1. Avoid Calling the Database Three Times

In the home demo:

```java
model.addAttribute("products", catalog.all());
model.addAttribute("featured", catalog.find(1L));
model.addAttribute("count", catalog.all().count());
```

With an in-memory List this is negligible. Yet if `catalog.all()` is a real R2DBC query, the home screen could execute **two list queries** plus one featured query.

In production, a better approach builds a view model in the service:

```java
record CatalogPage(
        String title,
        long count,
        List<Product> products,
        Product featured) {}

Mono<CatalogPage> page = service.loadCatalogPage(limit, pageIndex);
```

This is a conceptual snippet, not a standalone method. The service can return a single paginated snapshot DTO. The controller uses:

```java
return page.map(p ->
    Rendering.view("home")
        .modelAttribute("title", p.title())
        .modelAttribute("count", p.count())
        .modelAttribute("products", p.products())
        .modelAttribute("featured", p.featured())
        .build());
```

This snippet forms the return value of a `Mono<Rendering>` handler using the `page` variable above. It avoids having the view resolver resolve multiple reactive attributes independently and enforces data consistency.

### 14.2. Limit Data Before Rendering

If a list has 1 million rows, the browser does not need HTML for every item at once. Typically:

1. Accept a page/cursor with a bounded limit.
2. Validate page size on the server.
3. Run a DB query with a limit, rather than `flux.take(20)` after fetching everything.
4. Render only the current page's records.
5. Let the client load the next page or use HTMX/infinite scroll with an explicit contract.

### 14.3. Set Timeouts Before the Rendering Stage

A reactive data source that never completes can hang the HTML view. Apply a business timeout before passing data to the model:

```java
Mono<Product> featured =
    service.featured()
        .timeout(Duration.ofSeconds(2));
```

This is a snippet requiring `Duration` import and an error policy. On timeout, the view can fall back to an empty featured product or render an error page, rather than silently treating a database timeout as “no products.”

### 14.4. Template Processing Consumes CPU

Reactive I/O avoids tying up threads waiting on remote connections, yet the template engine still parses expressions, loops over records, escapes HTML, and allocates bytes. For very large pages, rendering can consume significant CPU and allocations even when the model is reactive.

Monitor event-loop lag/CPU, template latency, memory, encoder buffers, and GC. If heavy CPU or blocking work is required, design appropriate schedulers/bulkheads or offload to a dedicated service; never assume everything inside a template is non-blocking.

### 14.5. Caching Catalogs and Models

Infrequently changing public data can be cached at the service level. However, per-user/session caches must use exact keys and TTL/invalidation rules. Never apply unbounded `Mono.cache()` to a publisher containing private data and share that bean/controller across requests.

## 15. Forms, Binding, and Validation in WebFlux Views

Template engines help build forms:

```html
<form th:action="@{/pages/products/create}" method="post">
    <label for="name">Product name</label>
    <input id="name" type="text" name="name">
    <button type="submit">Create</button>
</form>
```

HTML `application/x-www-form-urlencoded` forms require data binding and validation. In an annotated WebFlux controller, `@ModelAttribute` and `BindingResult` can be used following the proper parameter ordering rules. With reactive binders/validators, understand `WebExchangeBindException` for binding/validation failures.

Illustrative example:

```java
@PostMapping("/pages/products/create")
Mono<String> create(
        @Valid @ModelAttribute ProductForm form,
        BindingResult errors,
        Model model) {
    if (errors.hasErrors()) {
        model.addAttribute("form", form);
        return Mono.just("create-form");
    }
    return service.create(form)
                  .thenReturn("redirect:/pages/home");
}
```

This is a **non-standalone snippet**: it requires `ProductForm`/service/validator imports, a `create-form` template, and Security/CSRF configuration. In WebFlux, validation also depends on method signatures and reactive inputs; do not copy Servlet MVC form code assuming every annotation and method overload behaves identically. When using `BindingResult`, place it immediately after the validated `@ModelAttribute` argument per the framework contract.

### 15.1. Preventing Over-Posting / Mass Assignment

Never bind form requests directly into a JPA entity containing `role`, `ownerId`, `isAdmin`, or server-controlled pricing fields. Use a dedicated command DTO, restrict bindable fields, and derive identity from the principal. Template hidden fields cannot be trusted because clients can modify them.

### 15.2. Displaying Validation Errors

Thymeleaf provides `th:errors` and `#fields` for form binding per its integration. A real flow must:

1. Validate input.
2. Re-render the form view on error, keeping the binding result in the model per convention.
3. Escape all submitted values.
4. Never commit transactions/DB writes when the form is invalid.
5. Include CSRF tokens in forms when login/sessions require them.
6. Redirect on success (PRG: Post/Redirect/Get) to reduce accidental duplicate POSTs.

## 16. Common Mistakes and Fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Browser shows only literal text `home` | `@RestController` returning String body | Use `@Controller` for views |
| 500 TemplateInputException | Wrong logical view name or missing `templates/home.html` | Check prefix/suffix/classpath |
| HTML still contains raw `th:text`/`th:each` | Template served under `static` or bypassed resolver | Place under `templates` and return view name |
| IDE imports Servlet ModelAndView | Mixing up MVC and WebFlux | Use reactive `Rendering` |
| HTML page hangs indefinitely | Model contains an uncompleting Flux | Pagination/take/timeout/streaming |
| Created Mono yet `block()` errors | Blocking on Netty event loop | Compose operators / return Publisher |
| Flux in Model does not stream items one by one | View resolver collects full List | Use SSE/fragments if incremental updates are needed |
| Empty detail page without 404 | `Mono.empty()` does not set HTTP status automatically | Use `Rendering.status(NOT_FOUND)` |
| 404 page shows error text yet status is 200 | Rendered missing view without setting HTTP 404 | Set status via Rendering |
| `Model` prints `Mono<User>` string | Custom view engine lacks reactive attr support | Verify view resolver/engine integration |
| XSS via field name | Used `th:utext` on untrusted input | Use `th:text`/escaping |
| Open redirect via URL param | Returned `redirect:` + user input | Server-controlled target allowlist |
| Users allowed to upload arbitrary templates | Template expressions can access beans | Never render editable templates from untrusted users |
| Form POST returns 403 | Spring Security CSRF/roles | Add CSRF token and proper security policy |
| Form submits yet causes over-posting | Direct entity binding | DTO with allowed fields |
| High CPU per page | Heavy template rendering/loops | Page limits, caching, profiling |
| Reactor `Mono.cache` leaks across users | Reused session A publisher for B | Partition by principal, TTL/invalidation |
| 404 on /pages/default | Missing template for default name/path | Add pages/default.html or return explicit name |
| Redirect status is not 302 | WebFlux RedirectView default semantics | Assert 3xx+Location or configure explicit status |
| WebFlux project runs DispatcherServlet | Both MVC and WebFlux starters present | Check app type/dependencies |
| JSP templates fail to resolve on Netty | JSP requires Servlet/JSP infrastructure | Use Thymeleaf/FreeMarker/Mustache |
| Server returns 200 without text/html | `@ResponseBody` or different converter | Inspect controller annotations |
| Invalid HTML contains raw script | Unescaped expression/custom dialect | Escape/sanitize, test XSS |
| JSON API emits wrong keys/format | DTO/Jackson contract or Content-Type | JSON tests, schema, negotiation |

### 16.1. Layer-by-Layer Debugging Process

1. **Runtime:** check whether Boot is running WebFlux reactive (default Reactor Netty) or MVC Servlet.
2. **Mapping:** does the route match `GET /pages/home` and reach `@Controller`?
3. **Return value:** is `"home"` treated as a view name or a String body?
4. **View resolver:** does the Thymeleaf reactive view resolver bean exist, and what is the resolved template path?
5. **Model:** do the added keys match what the template reads? How do Mono/Flux complete or error?
6. **Render:** check Thymeleaf syntax, SpringEL, escaping, fragments, locale, and message bundles.
7. **HTTP:** are status, `Content-Type: text/html`, caching, security, and redirect headers right?
8. **Metrics:** template rendering latency, memory, codec buffering, and event-loop CPU under realistic load.

## 17. Pre-Deployment Design Checklist

- [ ] Use `@Controller` for HTML and `@RestController` for REST APIs.
- [ ] Return view names from a server-controlled allowlist; never use untrusted URLs as template names.
- [ ] Place templates under `classpath:/templates/` using a WebFlux-compatible engine.
- [ ] Model data contains only authorized fields needed for display.
- [ ] `Mono.empty()` has clear semantics (missing, optional, or error) with proper status codes.
- [ ] `Flux`/collections are bounded by pagination, never rendered unbounded.
- [ ] Never call `block()` or blocking clients directly on the request event loop.
- [ ] Template expressions use escaping; never use `th:utext` on untrusted user input.
- [ ] Configure CSRF/AuthN/AuthZ when using sessions and form mutations.
- [ ] HTTP caching never leaks private HTML through shared proxies.
- [ ] Resource URLs, CSP, and redirect targets are validated.
- [ ] Tests verify HTML 200, HTML 404, redirects, escaping, and JSON APIs.
- [ ] Monitor template render time, codec buffers, event-loop lag, and GC.
- [ ] Never add Servlet-only JSP resolvers to a Reactor Netty app.
- [ ] Understand that view caches differ from HTTP response caches and data caches.

## 18. Review Questions

**1.** Can WebFlux render server-side HTML templates?  
**Answer:** Yes. It provides view resolution via ViewResolutionResultHandler and view engines like Thymeleaf.

**2.** What is the String `"home"` typically interpreted as inside `@Controller`?  
**Answer:** A logical view name.

**3.** What is the String `"home"` typically interpreted as inside `@RestController`?  
**Answer:** A literal response body.

**4.** Which package is `Model` in?  
**Answer:** `org.springframework.ui.Model`.

**5.** What does `ViewResolutionResultHandler` do?  
**Answer:** Selects a View via ViewResolver and coordinates rendering with the Model.

**6.** Where is Thymeleaf's default Boot template directory?  
**Answer:** `src/main/resources/templates/`.

**7.** For view name `"detail"`, which file does default Thymeleaf look for?  
**Answer:** `classpath:/templates/detail.html`.

**8.** Is a `Mono<Product>` placed in the model resolved before rendering?  
**Answer:** Yes, per Spring WebFlux view model resolution.

**9.** Does a `Flux<Product>` in the model necessarily stream HTML items immediately one by one?  
**Answer:** No; the framework may collect it into a List before view rendering.

**10.** How does a Flux that never completes affect a normal view?  
**Answer:** The view may never finish rendering if it waits for the entire model.

**11.** Does `Mono.empty()` from a repository automatically return 404 for an HTML page?  
**Answer:** No; select a Missing view + explicit 404 status.

**12.** Does WebFlux use Servlet `ModelAndView` for view controllers?  
**Answer:** No; `Rendering` is the appropriate API on the reactive stack.

**13.** What does `Mono<Rendering>` represent?  
**Answer:** An asynchronous decision about the template, model, status, and headers.

**14.** What can `Mono<String>` represent in an HTML controller?  
**Answer:** A view name supplied asynchronously.

**15.** Why doesn't `@RestController` render Thymeleaf `home.html` when returning `"home"`?  
**Answer:** Because the return value is written as the response body under `@ResponseBody` semantics.

**16.** How does `th:text` differ from `th:utext`?  
**Answer:** `th:text` escapes HTML, while `th:utext` does not.

**17.** Is it safe to use an untrusted template name?  
**Answer:** No; use a template-name allowlist and validate redirect targets.

**18.** How does returning `redirect:/pages/home` differ from `forward:...`?  
**Answer:** Redirect is a 3xx response triggering a new request; WebFlux does not support Servlet forward dispatches.

**19.** Does template caching store user A's page and serve it to user B?  
**Answer:** Template caching mainly caches compiled template structures and should not be confused with HTTP response caching.

**20.** Does reactive view rendering eliminate template CPU usage?  
**Answer:** No; rendering still consumes CPU, memory, and HTML encoding resources.

**21.** Do form POSTs using cookie sessions require CSRF consideration?  
**Answer:** Yes, an appropriate Spring Security WebFlux policy is needed.

**22.** If both WebFlux and MVC starters are present, which stack does Boot select by default?  
**Answer:** Usually MVC/Servlet.

**23.** Why does rendering HTML from a large Flux require pagination?  
**Answer:** To avoid excessive wait times and holding large amounts of data in the heap.

**24.** Should HTML tests compare strings down to exact whitespace?  
**Answer:** No; prefer asserting status, media type, structure, and key text.

**25.** If you want to update HTML incrementally as new data arrives, what must you consider?  
**Answer:** Thymeleaf reactive streaming modes, fragments, SSE/HTML-over-the-wire, proxy buffering, and browser update logic.

## 19. Official Documentation

- [Spring Framework 6.2 — DispatcherHandler / View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): `ViewResolutionResultHandler`, logical view names, reactive model attributes, redirects.
- [Spring Framework 6.2 — View Technologies](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html): Thymeleaf, FreeMarker, Script Views, fragments, and HTTP message writer views.
- [Spring Framework 6.2 — Controller Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html): `Model`, model binding, request handling.
- [Spring Framework 6.2 — Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-modelattrib-methods.html): reactive attributes, `@ModelAttribute` lifecycle.
- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): `String` view names, Rendering, Model, and HTTP body cases.
- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): ViewResolver/Content Negotiation configuration.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): template engines, WebFlux/Boot auto-configuration, Reactor Netty runtime.
- [Thymeleaf — Spring Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring expressions, forms, reactive integration guidance.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): reactive HTTP testing.

**Conclusion:** WebFlux does more than return JSON `Mono`/`Flux`. With `@Controller`, `Model`, and a view resolver like reactive Thymeleaf, you can render server-side HTML without blocking the event loop waiting for data. However, **reactive attributes may be collected before rendering**, so you must design pagination, timeouts, escaping, authorization, and streaming strategies according to actual requirements. Clearly distinguishing **view name**, **model data**, and **HTTP response body** is the key to avoiding confusion between WebFlux, REST-only APIs, and Servlet MVC.
