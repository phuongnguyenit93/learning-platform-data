# Thymeleaf, the `templates` Directory, and Template Cache Configuration in Spring Boot

**Scope:** Spring Boot web-runtime → Server Interfaces. This lesson explains Thymeleaf and server-side HTML rendering, how Spring Boot resolves views via the `templates` directory, `spring.thymeleaf.*` settings, caching in development and production, common pitfalls, and verification techniques. The complete example uses **Java 17+, Spring Boot 3.5.0, Spring MVC, and Maven**; Spring WebFlux is compared separately to avoid mixing up the two web stacks.

## 1. What Is Thymeleaf?

**Thymeleaf** is a Java template engine commonly used for **server-side HTML rendering (SSR)** from an HTML template file combined with data from the current request. A template holds page structure and `th:*` attributes; the controller puts data into a Spring `Model`; Thymeleaf evaluates expressions before sending the final HTML to the browser.

For example, a user requests `GET /catalog?q=java`. The controller reads the query parameter, filters a list, adds `q`, `products`, and `requestCount` to the `Model`, and returns the view name `catalog`. The view resolver locates `classpath:/templates/catalog.html`. Thymeleaf loads the template (from cache if enabled), evaluates `th:text` and `th:each` attributes against **this request's model**, and returns a `text/html` response.

~~~text
GET /catalog?q=java
        │
        ▼
Spring MVC DispatcherServlet
        │
        ▼
@Controller + Model
  q="java", items=[...], requestCount=...
        │
   return "catalog"
        │
        ▼
ThymeleafViewResolver / SpringTemplateEngine
        │
        ├─ logical name "catalog"
        ├─ template location "classpath:/templates/catalog.html"
        ├─ template cache: parsed template if enabled
        └─ evaluate th:* against current request's model
        │
        ▼
HTTP 200, Content-Type: text/html, rendered HTML body
~~~

Clear distinctions:

| Concept | Function | Example |
| --- | --- | --- |
| **Template** | Source file with data placeholders | `templates/catalog.html` |
| **Model** | Java data for the render pass | `model.addAttribute("name", "Lan")` |
| **Logical view name** | Name returned by controller to locate template | `return "catalog";` |
| **ViewResolver/TemplateEngine** | Locates, parses, and processes templates | `ThymeleafViewResolver` / `SpringTemplateEngine` |
| **HTML response** | Rendered HTML sent to the browser | `<h1>Lan</h1>` |
| **Template cache** | Reuses parsed template representations | `spring.thymeleaf.cache=true` |

A template can be cached while the data still varies per request. **Template caching does not by default cache the entire HTML response containing usernames, shopping carts, or access permissions.**

### Comparison with Static Files and JSON APIs

- `src/main/resources/static/css/site.css` is served by the static resource handler at `/css/site.css`. Thymeleaf does not need to process this file.
- `src/main/resources/templates/catalog.html` normally **has no direct public URL**; it must be selected as a view by a controller or router.
- `@RestController` returning an object typically serializes it to JSON via a message converter. With `@RestController` returning `"catalog"`, the result is usually the literal string `catalog` in the body, **without rendering `catalog.html`**.
- A `static/index.html` file is still HTML, but the server sends its raw contents; `th:text` attributes placed there **are not executed automatically**.

Thymeleaf fits forms, dashboards, admin pages, and SSR pages. It can coexist with CSS/JS and REST APIs without forcing every interaction to reload the page.

## 2. Default `templates` Directory and File Paths

In Spring Boot projects following Maven/Gradle conventions, views are typically stored in:

~~~text
src/main/resources/templates/
~~~

When packaged into an executable JAR, these files reside on the application classpath (usually under `BOOT-INF/classes/templates/`). Spring Boot 3.5 defaults to:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
~~~

These are **default values**: you do not need to write them in configuration if you accept the convention.

Examples of mappings:

| Java Controller Returns | Thymeleaf Looks For |
| --- | --- |
| `return "home";` | `classpath:/templates/home.html` |
| `return "catalog";` | `classpath:/templates/catalog.html` |
| `return "catalog/list";` | `classpath:/templates/catalog/list.html` |
| `return "admin/dashboard";` | `classpath:/templates/admin/dashboard.html` |

Formula:

~~~text
physical template path = prefix + logicalViewName + suffix

"classpath:/templates/" + "catalog/list" + ".html"
= "classpath:/templates/catalog/list.html"
~~~

**Do not return `"templates/catalog.html"` from a controller** when trying to render `templates/catalog.html` under default settings: it makes the resolver look in the wrong path. And do not treat `GET /templates/catalog.html` as an automatically exposed endpoint.

If you change:

~~~properties
spring.thymeleaf.prefix=classpath:/ui/
~~~

then `return "catalog";` resolves to `src/main/resources/ui/catalog.html`. All templates and fragments resolved by that resolver must also be reorganized under the new prefix. `spring.web.resources.static-locations` applies to static resources and **does not replace** `spring.thymeleaf.prefix`.

### Directory Tree for the Runnable Example

~~~text
template-demo/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/templatedemo/
   │  ├─ TemplateDemoApplication.java
   │  └─ CatalogController.java
   └─ resources/
      ├─ application.properties
      ├─ application-dev.properties
      ├─ application-prod.properties
      ├─ messages.properties
      ├─ templates/
      │  ├─ catalog.html
      │  └─ fragments/
      │     └─ common.html
      └─ static/
         └─ css/site.css
~~~

Templates live in `templates`; fragments are also sub-templates; stylesheets live in `static` and are served by a different handler. Do not use `src/main/webapp` for Boot executable JAR apps because packaging and classpath layout may ignore traditional webapp directories.

## 3. View Resolution: `@Controller`, `@RestController`, and View Names

In **Spring MVC/Servlet**, `DispatcherServlet` locates a handler for the request. If the handler is a `@Controller` returning `String` without `@ResponseBody`, Spring can interpret the return value as a **logical view name**.

~~~java
@Controller
class GreetingController {
    @GetMapping("/hello")
    String hello(Model model) {
        model.addAttribute("name", "Lan");
        return "hello"; // looks up templates/hello.html
    }
}
~~~

This is an **illustrative snippet**, omitting imports and project setup. If changed to `@RestController`, the Java `String` becomes a **direct response body**. A view name with special prefix `redirect:/hello` issues a redirect; `forward:/path` performs a server-side dispatch in MVC. Neither is equivalent to a template name.

**Debugging workflow when nothing renders:** verify which handler receives the URL, check `@Controller`, verify the returned view name, check prefix/suffix and whether the file actually exists on the classpath, and only then check caching. Never try to fix missing-file errors by turning off template caching.

## 4. Essential Thymeleaf Configuration Properties

Key Spring Boot 3.5.x properties:

| Property | Default | Purpose |
| --- | --- | --- |
| **`spring.thymeleaf.cache`** | **`true`** | Caches parsed/resolved template structures in the resolver/engine |
| `spring.thymeleaf.prefix` | `classpath:/templates/` | Base location of templates |
| `spring.thymeleaf.suffix` | `.html` | File extension |
| `spring.thymeleaf.mode` | `HTML` | Template mode |
| `spring.thymeleaf.encoding` | `UTF-8` | Template file encoding |
| `spring.thymeleaf.enabled` | `true` | Enables view resolution integration |
| `spring.thymeleaf.check-template` | `true` | Checks template existence during resolution |
| `spring.thymeleaf.check-template-location` | `true` | Checks that template location exists |
| `spring.thymeleaf.view-names` | unset by default | Restricts view names Thymeleaf handles |
| `spring.thymeleaf.excluded-view-names` | unset by default | View names excluded from the Thymeleaf resolver |
| `spring.thymeleaf.template-resolver-order` | unset by default | Resolver order when multiple template resolvers exist |

**Do not confuse:** `check-template-location=true` does not guarantee every template name returned by controllers exists. It checks the configured location directory. A wrong view name can still cause a render error (often HTTP 500 when the controller matched but no view rendered successfully).

If customization is unnecessary, **leave the defaults**. Change prefix/suffix or view names only when your app has a custom folder convention or multiple template engines coexisting.

## 5. Complete Spring Boot MVC Example (Java 17)

Self-contained example without a database. `GET /catalog` uses Thymeleaf with a mock list, search input, header fragment, message bundle, and CSS. `requestCount` increments per HTTP request to verify that template caching **does not freeze old model data**.

### 5.1. `pom.xml`

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
  <artifactId>template-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Thymeleaf starter brings in the Thymeleaf library and Spring integration with versions managed by Spring Boot. You do not need to declare `@Bean TemplateEngine` manually in a basic project.

### 5.2. `src/main/java/com/example/templatedemo/TemplateDemoApplication.java`

~~~java
package com.example.templatedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TemplateDemoApplication.class, args);
    }
}
~~~

### 5.3. `src/main/java/com/example/templatedemo/CatalogController.java`

~~~java
package com.example.templatedemo;

import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class CatalogController {
    private static final List<String> ITEMS =
            List.of("Java", "Spring Boot", "Thymeleaf", "Docker");

    private final AtomicLong requests = new AtomicLong();

    @GetMapping("/catalog")
    public String catalog(
            @RequestParam(defaultValue = "") String q,
            Model model) {
        String needle = q.strip().toLowerCase(Locale.ROOT);
        List<String> filtered = ITEMS.stream()
                .filter(item -> item.toLowerCase(Locale.ROOT)
                        .contains(needle))
                .toList();

        model.addAttribute("q", q);
        model.addAttribute("items", filtered);
        model.addAttribute("requestCount", requests.incrementAndGet());
        return "catalog";
    }
}
~~~

`q.strip()` and `Stream.toList()` are available in Java 17+. `AtomicLong` counts requests only within **a single JVM process**, resets on restart, and does not sync across replicas; do not use it for production analytics. It demonstrates that fresh model data is constructed on every request.

### 5.4. `src/main/resources/templates/catalog.html`

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{catalog.title}">Catalog</title>
  <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
  <header th:replace="~{fragments/common :: banner}">
    Sample header to be replaced.
  </header>

  <main>
    <h1 th:text="#{catalog.title}">Product Catalog</h1>

    <form th:action="@{/catalog}" method="get">
      <label for="q">Find name:</label>
      <input id="q" name="q" type="search" th:value="${q}">
      <button type="submit">Search</button>
    </form>

    <p>Requests in this JVM:
      <strong th:text="${requestCount}">0</strong>
    </p>

    <ul>
      <li th:each="item : ${items}" th:text="${item}">
        Sample item
      </li>
    </ul>

    <p th:if="${#lists.isEmpty(items)}">No matching results.</p>
  </main>
</body>
</html>
~~~

When rendered on the server, `th:text` replaces the element's placeholder content. `th:each` generates multiple `li` elements. `th:if` omits the element if the condition is false. `@{/css/site.css}` builds a context-path-aware URL (useful when deployed under `/shop`). `th:action="@{/catalog}"` ensures the form submits to the right URL; a GET form uses query parameters only and does not need a CSRF token for read requests in this example.

### 5.5. `src/main/resources/templates/fragments/common.html`

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<body>
  <header th:fragment="banner">
    <nav aria-label="Navigation">
      <a th:href="@{/catalog}">Catalog</a>
    </nav>
  </header>
</body>
</html>
~~~

`th:replace="~{fragments/common :: banner}"` locates the `banner` fragment in `templates/fragments/common.html` and replaces the **entire** host element. `th:insert` inserts the fragment **inside the host**, which can create unwanted nested tags if used carelessly. Placing fragments in a file under `templates` enables reusing headers, footers, and navigation.

### 5.6. `src/main/resources/messages.properties`

~~~properties
catalog.title=Technology Catalog
~~~

`#{catalog.title}` retrieves the value from the message bundle for the active locale. For multilingual interfaces, add `messages_vi.properties`, `messages_en.properties`, and configure a locale resolver/strategy per request. **Message bundle caching is separate from Thymeleaf template caching.**

### 5.7. `src/main/resources/static/css/site.css`

~~~css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem auto;
  max-width: 44rem;
  line-height: 1.5;
}
h1 { color: #245c8a; }
li { padding: 0.25rem 0; }
~~~

This CSS file is served by Spring as a **static resource** at `/css/site.css`. No controller is needed for CSS. Putting CSS inside `templates` just to keep it next to HTML breaks normal static asset URLs.

### 5.8. Three Configuration Files

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=template-demo
spring.thymeleaf.encoding=UTF-8
~~~

**`src/main/resources/application-dev.properties`:**

~~~properties
# Development: template changes can be re-read.
spring.thymeleaf.cache=false
~~~

**`src/main/resources/application-prod.properties`:**

~~~properties
# Production: true is already the default, set explicitly for clarity.
spring.thymeleaf.cache=true
~~~

A profile only takes effect when **activated**. Running without specifying `dev` or `prod` leaves Thymeleaf caching at its default **true**, unless a DevTools dependency or another configuration source changes the effective property.

### 5.9. Running and Testing with Browser/curl

From the project directory, with JDK 17+ and Maven installed:

~~~bash
java -version
mvn spring-boot:run -Dspring-boot.run.profiles=dev
~~~

In Windows PowerShell, if `-Dspring-boot.run.profiles=dev` gets split incorrectly by the shell, wrap the argument in quotes. Open `http://localhost:8080/catalog` in a browser. The page displays the heading **Technology Catalog**, four items **Java, Spring Boot, Thymeleaf, Docker**, and the request counter.

Try:

~~~bash
curl -i "http://localhost:8080/catalog?q=java"
curl -i "http://localhost:8080/catalog?q=not-found"
curl -i "http://localhost:8080/css/site.css"
curl -i "http://localhost:8080/templates/catalog.html"
~~~

Observations:
1. `/catalog?q=java` typically returns **200 OK**, HTML body, and only **Java** in the list.
2. `/catalog?q=not-found` returns HTML containing the line **No matching results.**
3. `/css/site.css` returns CSS (typically **200 OK**) via the static resource handler.
4. `/templates/catalog.html` is not a public route for the template; in this project it typically returns **404 Not Found**.
5. Refreshing `/catalog` repeatedly increments `requestCount`. It **also increments when running the prod profile with cache=true** because the controller builds a new model on every request.

Interpret body and status only within the scope of this example project; do not assume identical HTTP headers/whitespace across containers or after adding Spring Security/proxies.

Verify packaged files with Maven:

~~~bash
mvn clean package
jar tf target/template-demo-0.0.1-SNAPSHOT.jar
~~~

In the entry list, look for `BOOT-INF/classes/templates/catalog.html`, `BOOT-INF/classes/templates/fragments/common.html`, `BOOT-INF/classes/static/css/site.css`, and `BOOT-INF/classes/messages.properties`.

Run the JAR with the production profile:

~~~bash
java -jar target/template-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

After building, editing the source file `src/main/resources/templates/catalog.html` **does not update the contents inside the already packaged JAR**. You must build/deploy a new artifact; setting `cache=false` does not make an existing JAR read source files from elsewhere.

## 6. Thymeleaf Expressions You Should Know

| Expression | Role | Example |
| --- | --- | --- |
| `${...}` | Variable in Model/context | `th:text="${name}"` |
| `*{...}` | Property on the object selected by `th:object` | `th:field="*{email}"` |
| `#{...}` | Message bundle value | `th:text="#{catalog.title}"` |
| `@{...}` | Builds URL with context path and query params | `th:href="@{/catalog(q=${q})}"` |
| `~{...}` | References fragment/template | `th:replace="~{fragments/common :: banner}"` |

Common attributes:
- `th:text` outputs **HTML-escaped text**.
- `th:utext` outputs **unescaped HTML**; never use with untrusted data.
- `th:each` iterates over a collection.
- `th:if` and `th:unless` control conditional rendering.
- `th:href`, `th:src`, `th:action` build URLs.
- `th:fragment`, `th:replace`, `th:insert` organize pages into fragments.
- `th:object` and `th:field` support Spring form model binding.
- `th:errors` and `#fields.hasErrors(...)` display validation errors put into the model by the controller.

**XSS:** given user input `<script>alert(1)</script>`, `th:text` converts special HTML characters into escaped text instead of letting the browser interpret it as a script. `th:utext` is appropriate only when HTML content is explicitly trusted/sanitized. Never treat template features as a substitute for context-specific escaping (HTML, JavaScript, URL).

~~~html
<p th:text="${comment}">Comment will be escaped.</p>
<!-- Use only after safe sanitization from a trusted source. -->
<div th:utext="${trustedHtml}">HTML may render directly.</div>
~~~

`th:if="${isAdmin}"` only hides/shows UI elements; it is not API authorization. Controllers and services must enforce real permissions.

## 7. Form Binding and Validation (Integration Example, Not in Section 5 Project)

Spring MVC + Thymeleaf can bind forms into DTOs via `th:object`, `th:field`, `@ModelAttribute`, `@Valid`, and `BindingResult`. To run this example, add `spring-boot-starter-validation`, an appropriate `ProfileForm` DTO, imports, and controller setup; below only illustrates the relationship.

~~~java
@GetMapping("/profile/edit")
String edit(Model model) {
    model.addAttribute("profileForm", new ProfileForm());
    return "profile-edit";
}

@PostMapping("/profile/edit")
String save(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-edit";
    }
    // Validate authorization and save data per business rules.
    return "redirect:/profile";
}
~~~

~~~html
<form th:action="@{/profile/edit}" th:object="${profileForm}" method="post">
  <label for="email">Email</label>
  <input id="email" th:field="*{email}" type="email">
  <span th:if="${#fields.hasErrors('email')}"
        th:errors="*{email}">Invalid email</span>
  <button type="submit">Save</button>
</form>
~~~

`BindingResult` must appear **immediately after** the model attribute it validates in the handler signature. `th:object` must point to an object added to the model by the controller. For applications using cookies/sessions, state-changing POSTs must handle **CSRF**: Spring Security/Thymeleaf integration can inject hidden tokens automatically, but verify both the rendered form and `SecurityFilterChain`; never disable CSRF hastily just to silence a 403 error.

## 8. How Template Caching Works: What Is Cached and What Is Not?

Default in Spring Boot 3.5.x:

~~~properties
spring.thymeleaf.cache=true
~~~

When enabled, Thymeleaf can **cache the parsed template representation** and rendering metadata to avoid re-reading and re-parsing templates on subsequent requests. When disabled:

~~~properties
spring.thymeleaf.cache=false
~~~

the engine resolves/parses according to the resolver configuration without relying on the template cache as before, making file changes visible when the runtime can read the updated file, at the cost of higher parsing overhead and CPU usage.

Crucially, **the model is not frozen**:

~~~text
Request #1:
  Controller → Model(q="java", requestCount=1)
  Engine reads/parses catalog.html if not cached
  Renders HTML for request #1

Request #2:
  Controller → Model(q="docker", requestCount=2)
  Engine can reuse the parsed template from cache
  Renders HTML using model #2; does not reuse HTML generated in #1
~~~

On multi-user sites, engine template caching **does not act as a shared response cache serving personalized HTML**. If user A's page appears for user B, investigate response caches/proxies/CDNs, sessions, model/data handling, and authorization—do not blame Thymeleaf template caching by default.

### Three Cache Layers Often Confused

| Layer | What Is Typically Stored | Mechanism |
| --- | --- | --- |
| **Template cache** | Parsed templates/metadata to avoid repeated parsing | `spring.thymeleaf.cache` |
| **Static resource cache** | Resource resolvers/transformers and HTTP headers for CSS/JS/images | `spring.web.resources.chain.cache`, `spring.web.resources.cache.*` |
| **HTTP cache in browser/proxy/CDN** | Responses stored per HTTP caching semantics | `Cache-Control`, `ETag`, `Last-Modified`, proxy policy |

Setting `spring.thymeleaf.cache=false` does **not** disable browser caching for CSS/JS, alter reverse-proxy cache policies, or make a JAR update its files automatically. Likewise, setting `Cache-Control` on HTTP responses does not stop Thymeleaf from caching parsed templates.

**Template cache** is also distinct from **message bundle cache**, database/Redis data caches, Hibernate caches, and so on. When debugging, identify which layer is actually serving stale data.

## 9. Development: Template Edited but Page Remains Stale

### 9.1. Enabling `cache=false` During Development

In `application-dev.properties`:

~~~properties
spring.thymeleaf.cache=false
~~~

Run with `--spring.profiles.active=dev` or the Maven plugin profile. **Important:** if the app runs against files copied into `target/classes/templates/`, edits under `src/main/resources/templates/` must be **copied to the runtime classpath** by your IDE or build tool. If the copy on the classpath does not update, `cache=false` will still display the old HTML because the engine reads the unchanged file.

Verification steps:
1. Run the app in development mode and visit `/catalog`.
2. Change `"Find name:"` in the template to `"Find technology:"`.
3. Confirm the updated file is in the active classpath, e.g., `target/classes/templates/catalog.html` (if the IDE/build requires copying).
4. Refresh `/catalog` in the browser or via `curl`.
5. If still stale, check the effective `spring.thymeleaf.cache` property and actual `prefix` path before editing HTML again.

**Do not** conclude "`cache=false` doesn't work" simply because editing a source file in a project where the IDE hasn't updated runtime resources yet.

### 9.2. DevTools

You can add `spring-boot-devtools` to a development project:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-devtools</artifactId>
  <optional>true</optional>
</dependency>
~~~

DevTools applies development-time property defaults, including:

~~~properties
spring.thymeleaf.cache=false
spring.web.resources.cache.period=0
spring.web.resources.chain.cache=false
~~~

It also provides automatic restarts when classpath files change and supports browser LiveReload under suitable conditions. Edits under `templates`/`static` are typically **excluded from full restarts** by default, since resource-only updates rarely require restarting application code. However, DevTools does not guarantee every IDE copies files automatically, cannot refresh every browser without setup, and does not run as a development tool in standard packaged production JARs.

When both DevTools defaults and explicit properties exist, **inspect the effective configuration** instead of guessing from files. To be certain, set `cache=false` explicitly in the `dev` profile and `cache=true` in the `prod` profile.

### 9.3. Packaged JARs and Container Images

In a packaged JAR, template files are **embedded inside the artifact**. Editing the external source tree and refreshing the browser does not change the artifact contents. When deploying with Docker/Kubernetes, build a new image/JAR, roll it out, and verify all replicas run the same artifact. Setting `cache=false` does not turn a JAR into a hot-reloadable source directory.

If you intentionally load templates from an external filesystem or custom resolver, different rules apply; in that case, enforce access permissions, versioning, and cache invalidation so replicas do not see inconsistent template versions.

## 10. Production: What Benefits Does `cache=true` Provide?

In production, templates rarely change while serving many read requests, so caching reduces the cost of locating and parsing views/templates/fragments. Spring Boot enables `cache=true` by default; setting it explicitly in the production profile makes intent easy to audit:

~~~properties
spring.thymeleaf.cache=true
~~~

This **does not speed up database queries**; controllers/services still prepare the model for every request, the engine still evaluates expressions against current data, and the server still writes HTML to the response. If latency is high due to DB queries, N+1 issues, network calls, or controller logic, enabling template caching will not fix the root bottleneck.

How to measure impact:
- Compare identical workloads and datasets with caching enabled vs. disabled in a test environment.
- Measure CPU, throughput, p50/p95 latency, heap, GC, and 5xx rates after warm-up.
- With complex fragments/layouts, inspect parse/render times without sacrificing validation or security for speed.
- Do not confuse an **HTTP 304/CDN cache hit** with a **Thymeleaf template cache hit**. If a request never reaches the JVM because a CDN serves it, that is response caching outside Thymeleaf.

If HTML contains logged-in user data, configure `Cache-Control` and shared proxies/CDNs according to your data policy. Thymeleaf `cache=true` **never authorizes** shared HTTP caches to store and serve that HTML across users.

## 11. Fragments, Layouts, and Messages

Fragments help reuse headers, footers, navigation, form controls, and alerts. Syntax:

~~~html
<!-- fragments/common.html -->
<footer th:fragment="footer">
  <small>© Example Site</small>
</footer>

<!-- Catalog view -->
<div th:replace="~{fragments/common :: footer}"></div>
~~~

`th:replace` **replaces** the host element, whereas `th:insert` inserts **inside** the host. If a fragment already includes `<footer>`, using `th:insert` on a `<footer>` creates nested footers; pick the right one to keep HTML semantically valid.

Thymeleaf 3.1 supports passing parameters to fragments:

~~~html
<!-- fragments/common.html -->
<section th:fragment="notice(message)">
  <p th:text="${message}">Notice</p>
</section>

<!-- another page -->
<div th:replace="~{fragments/common :: notice('Saved successfully')}"></div>
~~~

**i18n:** `#{key}` looks up messages by locale. For example, you can create:
- `messages.properties` containing default messages;
- `messages_vi.properties` containing Vietnamese;
- `messages_en.properties` containing English.

Locale selection depends on `LocaleResolver`/WebFlux locale context and the request (such as `Accept-Language`). If keys render as `??catalog.title_vi??`, check bundle location, file encoding, locale, key spelling, and message source configuration. Modifying message bundles is not necessarily affected by `spring.thymeleaf.cache` because they use separate cache layers.

## 12. Security When Rendering HTML from the Model

Thymeleaf enforces restrictions against dangerous expression evaluation, yet applications must still protect inputs and enforce authorization. Core rules:

1. **Prefer `th:text`** for user-sourced text; it HTML-escapes output. Use `th:utext` only when HTML has passed through a trusted/sanitized pipeline.
2. Never put secrets, private keys, access tokens, or passwords into the model/HTML, even though template files cannot be downloaded directly.
3. Authorization logic belongs in controllers, services, and security filters; `th:if` only controls UI visibility, not access control.
4. Do not let template expressions trigger repeated database queries; compute the model in services to avoid N+1 and render-time queries.
5. When building dynamic URLs, check values that could cause open redirects or unsafe schemes. `@{...}` does not automatically sanitize an untrusted user-supplied URL.
6. POST forms using cookie/session authentication require proper CSRF protection; do not disable CSRF just to bypass a 403 error.
7. For dynamic HTML containing user-specific data, configure HTTP caching so shared caches cannot serve one user's response to another.

**The `templates` directory is not public by default**; this structural boundary is helpful, but it does not replace authorization on routes that render views.

## 13. Thymeleaf with Spring WebFlux

Spring Boot also supports Thymeleaf in **Spring WebFlux / reactive web**. Both stacks have different view resolution internals yet share the same concept: controllers return view names, models supply data, and the engine renders output.

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Web starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| View starter | `spring-boot-starter-thymeleaf` | `spring-boot-starter-thymeleaf` |
| HTTP engine | Servlet stack, `DispatcherServlet` | Reactive stack, `DispatcherHandler` |
| Template location | `classpath:/templates/` | `classpath:/templates/` |
| Cache property | `spring.thymeleaf.cache` | `spring.thymeleaf.cache` |
| View result | `String` logical view name | Can return reactive types such as `Mono<String>` |
| Extra options | Servlet view response | `spring.thymeleaf.reactive.*` such as chunk-size/full mode |

Illustrative WebFlux snippet (**not part of the MVC project in Section 5**):

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Mono;

@Controller
class ReactivePageController {
    @GetMapping("/reactive-page")
    Mono<String> page(Model model) {
        model.addAttribute("message", "Hello WebFlux");
        return Mono.just("reactive-page");
    }
}
~~~

Place `templates/reactive-page.html` containing `th:text="${message}"` inside a separate WebFlux project. If a project includes **both** `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot typically favors the Servlet/MVC application type; do not conclude "it's running WebFlux" solely because the WebFlux dependency or `Mono` is present. In WebFlux, avoid heavy blocking JDBC calls directly on the event loop; template caching does not fix blocking bottlenecks.

## 14. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Browser displays literal `catalog` | `@RestController`/`@ResponseBody` used | Use `@Controller` to return a logical view |
| `GET /templates/catalog.html` returns 404 | Confusing file path with URL route | Request `/catalog` per controller mapping |
| `TemplateInputException` / "Error resolving template" | Wrong view name, prefix/suffix, missing file | Compute `prefix + view + suffix`, inspect classpath |
| Controller route exists, response is 500 | Missing template, broken expression/fragment | Read rendering stack trace; fix template/Model |
| Works in IDE, fails in JAR | Files not copied/packaged | Run `jar tf target/...jar` and check `BOOT-INF/classes/templates` |
| Updated HTML not shown with `cache=true` | Template parse/cache still holds old version | Use `cache=false` in dev and check classpath |
| `cache=false` yet HTML remains stale | Source files not copied to runtime or old JAR running | Check `target/classes`/build process/redeploy |
| DevTools dependency present, cache still on | DevTools inactive or overridden by another property | Inspect effective `spring.thymeleaf.cache` |
| CSS fails to load | CSS in wrong folder, context path, or security block | Use `static` and `th:href="@{/css/...}"` |
| CSS is stale, HTML is updated | Browser/CDN/static resource cache | Check HTTP response headers and asset build |
| Fragment not found | Wrong `th:fragment` name, path, or prefix | Verify `fragments/common :: banner` |
| `${...}` appears literally | File served statically, Thymeleaf did not render | Ensure controller/view resolver handles it |
| Key `#{...}` not translated | Wrong bundle/locale/key | Check `messages*.properties` and locale |
| Form binding error | Wrong `th:object` name or missing DTO property | Match model attributes, DTO, and `th:field` |
| POST form returns 403 | Spring Security CSRF/authorization | Check filter chain and token |
| Disabling cache in prod increases CPU | Repeated template re-parsing | Set `cache=true`, benchmark performance |
| Error occurs on only one replica | Mismatched JAR/image version or proxy cache | Verify artifact versions across replicas |

**Distinguishing 404 and 500:** a URL without a matching controller or static resource typically yields 404. If a controller matched but the view/template fails to resolve or render, 500 is common. Custom exception handlers or security rules may produce different codes; never guess from status codes alone while ignoring stack traces.

### Practical Debugging Workflow

1. Record the exact request URL, HTTP status, and which controller actually ran.
2. Check whether the class uses `@Controller` or `@RestController` and the exact logical view name returned.
3. Compute `prefix + viewName + suffix` and verify the file exists on the **runtime classpath**.
4. Check the active profile, effective `spring.thymeleaf.cache`, and any custom view resolvers.
5. If data is missing, compare `model.addAttribute(...)` with `${...}` expressions; watch for NPEs.
6. For fragments, verify the file/path and `th:fragment` name; for i18n, verify key/locale.
7. If HTML updates while CSS/JS stay stale, check static URLs and HTTP caches rather than Thymeleaf.
8. With JARs, inspect the actually deployed artifact for the updated template instead of only checking the source tree.
9. Read logs and `curl -i` output from the failing instance itself. When enabling debug logs, avoid logging secrets.

## 15. Self-Check Exercises

1. A controller returns `"admin/users"` in default Boot Thymeleaf: where is the file looked up?
2. Why does `@RestController` returning `"catalog"` fail to render `catalog.html`?
3. If `static/index.html` contains `th:text`, will Thymeleaf process it when accessed directly in the browser?
4. Why does `requestCount` in the example still increment when `cache=true`?
5. `application-dev.properties` sets `cache=false`, yet the app runs with the default profile. Does it take effect automatically?
6. Caching is disabled, yet editing `src/main/resources/templates/catalog.html` leaves the runtime reading the old `target/classes/templates/catalog.html`. What should you check?
7. After building an old JAR, you edit the source file; does setting `cache=false` make the JAR pick up the new file?
8. How do `th:text` and `th:utext` differ for a string containing `<script>`?
9. How do `th:replace` and `th:insert` differ if the fragment is a `header`?
10. Why does `spring.web.resources.cache.period=0` not replace `spring.thymeleaf.cache=false`?
11. `/catalog` returns HTML normally, while `/css/site.css` returns 404—which directory should you inspect?
12. Why must HTTP shared caches still be controlled even though the template cache does not store per-user HTML?
13. Changing `spring.thymeleaf.prefix=classpath:/ui/` causes fragment `fragments/common` to be resolved where?
14. If both the MVC and WebFlux starters are present, which runtime stack usually runs by default?
15. Which signals should you evaluate before deciding to enable caching in production?

**Suggested answers:** (1) `classpath:/templates/admin/users.html`; (2) `@RestController` writes the response body; (3) no; (4) each request executes the controller and builds a fresh model; (5) no, the profile must be activated; (6) runtime classpath and build/IDE resource copying; (7) no, you must rebuild and redeploy; (8) escaped vs. unescaped, XSS risk with `th:utext`; (9) `th:replace` replaces the host element, `th:insert` preserves the host element; (10) static/HTTP caching differs from template parse caching; (11) inspect `static`, static URLs, and security rules; (12) rendered HTML responses can contain user-specific data; (13) `classpath:/ui/fragments/common.html`; (14) typically Servlet/MVC; (15) rendering traffic, CPU, parse overhead, and ability to deploy updated artifacts.

## 16. Official Documentation

- Spring Boot 3.5, Servlet Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5, Reactive Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5, Common Application Properties/Thymeleaf: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot Developer Tools and template cache defaults: https://docs.spring.io/spring-boot/reference/using/devtools.html
- Spring Boot Hot Swapping, Reload Templates: https://docs.spring.io/spring-boot/how-to/hotswapping.html
- Thymeleaf 3.1 Tutorial, expressions and fragments: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf + Spring, form binding and Spring context: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
