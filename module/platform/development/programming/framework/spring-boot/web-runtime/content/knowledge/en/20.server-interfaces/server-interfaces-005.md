# Distinguishing Template Engines from Static HTML Resources

## 1. Learning Objectives and Scenario

A Spring Boot application can return two pages that both end in `.html`, yet the way they are produced is very different:

- **Static HTML:** an HTML file already stored on the classpath. The server locates the file and returns its contents to the client, normally without substituting variables per request.
- **HTML rendered by a template engine:** an HTML file serving as a **template**. A controller prepares data, and the engine merges the template and data to produce the HTML response at request time.

In the **Spring Boot – web-runtime** module, the goal is to identify **who creates the HTML response**, **where data comes from**, **who controls the URL**, and **when to choose each approach**. This lesson focuses on Spring MVC + Thymeleaf, while explaining principles that also apply to FreeMarker/Mustache and other template technologies.

After this lesson, you can:

1. Distinguish a file in `src/main/resources/static` from a file in `src/main/resources/templates` and understand why their URLs differ.
2. Describe the processing flow from an HTTP request to `ResourceHttpRequestHandler` or from `@Controller` to `ViewResolver`/Thymeleaf.
3. Use `Model`, `@GetMapping`, `th:text`, `th:each`, `th:if`, and `th:href` to return HTML driven by server data.
4. Distinguish a `@Controller` returning a view name from `@RestController`/`@ResponseBody` returning response body data.
5. Run a Java 17+ example and verify the differences using `curl`, a browser, and response inspection.
6. Avoid 404 errors, exposing templates, mixing up syntax, misconfiguring caches, and safety issues when displaying user data.

## 2. Definition: How Does Static HTML Differ from Template HTML?

**Static HTML resource:** the browser receives HTML content saved as a file, such as `static/about.html`. The server may add HTTP headers, caching, compression, or authorization checks, but it **does not evaluate Thymeleaf expressions inside this file** under the default static resource mechanism.

**Template engine:** software that accepts a template together with input values (for example, `name = "Lan"`), then outputs the final HTML. In Spring Boot, Thymeleaf is typically invoked from Spring MVC's view-returning flow. A template engine can perform text substitution, conditionals, loops over lists, fragment/layout composition, and context-path-aware URL generation. These features **only actually execute when the template goes through the engine**.

Two HTML pages that look completely identical in the browser can still belong to two different mechanisms. Identify the mechanism by tracing the request flow and response-generating code, not merely by looking at the `.html` extension.

| Criterion | Static HTML | HTML via Template Engine |
| --- | --- | --- |
| Default location in Spring Boot MVC | `classpath:/static/`, `/public/`, `/resources/`, `/META-INF/resources/` | `classpath:/templates/` with the corresponding template engine |
| Component producing the body | Static resource handler reads the file | Controller picks a view; view resolver + engine render it |
| Per-request values | Not substituted server-side automatically; JS may run in the browser | Can inject `Model` data into HTML before sending |
| URL | Usually the file's relative path under the static root | URL is determined by `@RequestMapping`/route; view name points to template |
| Thymeleaf `th:*` syntax | Left verbatim as stored in the file, not processed by Spring | Processed by Thymeleaf with the right template/context |
| Template engine dependency | Not required | Requires starter/dependency and engine configuration |
| Best suited for | Landing pages, help pages, rarely changing HTML | User pages, database-driven lists, role/locale-specific results |
| Caching | Usually easy to cache broadly if content is shared | Must separate template caching from personalized HTML caching |
| JavaScript | Can be included | Can also be included |
| Response format | Usually `text/html` for `.html` | Usually `text/html` for HTML views |

**Do not confuse "static HTML" with "an application without dynamic data."** A static HTML file can still use JavaScript to call an API and update the DOM. In that case, the initial HTML shell is served statically, while dynamic content is rendered on the **client**, not by a server-side template engine.

Conversely, a template can output HTML with no changing data; that **does not turn it into a static resource** in the Spring MVC pipeline.

## 3. Which Directory, Which Path, and Which URL?

With default Spring Boot MVC:

~~~text
src/main/resources/
├── static/
│   ├── index.html
│   ├── about.html
│   └── css/site.css
├── public/
│   └── help.html
├── resources/
│   └── docs/readme.html
├── META-INF/resources/
│   └── pages/faq.html
└── templates/
    ├── greeting.html
    └── account/profile.html
~~~

### 3.1. Static Resources

Files under the four static locations are served by the resource handler, typically mapped to `/**`:

| Path in Project | Default URL |
| --- | --- |
| `src/main/resources/static/index.html` | `GET /index.html`; can serve as the welcome page for `GET /` |
| `src/main/resources/static/about.html` | `GET /about.html` |
| `src/main/resources/public/help.html` | `GET /help.html` |
| `src/main/resources/resources/docs/readme.html` | `GET /docs/readme.html` |
| `src/main/resources/META-INF/resources/pages/faq.html` | `GET /pages/faq.html` |

The segments `static`, `public`, `resources`, and `META-INF/resources` **do not automatically become URL prefixes**. For `src/main/resources/static/about.html`, the default URL is `/about.html`, not `/static/about.html`.

### 3.2. Templates

Thymeleaf looks for templates in `classpath:/templates/` by default and appends the `.html` suffix. However, `templates/greeting.html` **does not automatically get a URL `/templates/greeting.html`**.

A controller can declare:

~~~java
@GetMapping("/hello")
public String hello(Model model) {
    model.addAttribute("name", "Lan");
    return "greeting";
}
~~~

Inside a `@Controller` class, `return "greeting"` is the **logical view name**. Thymeleaf locates `classpath:/templates/greeting.html`, renders it, and returns the result for **`GET /hello`**. If the template sits at `templates/account/profile.html`, the view name is typically `"account/profile"`; the URL is still decided by the controller and need not match the file path.

**Note on view names:** returning `"greeting"` matches the default Thymeleaf `.html` suffix. Do not assume `return "greeting.html"` is equivalent; when the resolver appends the suffix, the configuration may behave unexpectedly. Use logical view names by convention and verify the active configuration.

## 4. Two Paths in Spring MVC

### 4.1. Static HTML Request

~~~text
Browser -> GET /about.html
              |
              v
     DispatcherServlet / HandlerMapping
              |
              v
  ResourceHttpRequestHandler (static fallback)
              |
              v
   classpath:/static/about.html
              |
              v
   Returns file contents + HTTP headers
              |
              v
             Browser
~~~

No `@Controller` is needed for each static file. Under the default configuration, the resource handler does not invoke Thymeleaf to evaluate `${name}` or `th:*` attributes.

### 4.2. Template-Rendered HTML Request

~~~text
Browser -> GET /hello?name=Lan
              |
              v
        DispatcherServlet
              |
              v
      @Controller / @GetMapping
              |
              v
    Model {name: "Lan", items: [...]}
              |
              v
   return "greeting" (view name)
              |
              v
    ViewResolver -> Thymeleaf
              |
              v
    templates/greeting.html + Model
              |
              v
    Rendered HTML -> HTTP response
              |
              v
             Browser
~~~

**Boundary to remember:** the controller typically **does not return the full HTML as a String** in this flow; it returns a *view name*. Thymeleaf reads the template file and produces the HTML content.

When templates are compiled/cached and how execution happens depends on the engine and configuration. Conceptually, however, each request can use a different `Model` and produce a different HTML response.

### 4.3. When Both Share the Same URL

Controller mappings generally take precedence over the fallback static resource handler. For example, if both `@GetMapping("/about.html")` and `static/about.html` exist, the request can go through the controller instead of serving the file. Do not rely on colliding paths to distinguish the two mechanisms.

For the welcome page, Spring Boot looks for `index.html` in the static locations first; if not found, it checks for an `index` template when an appropriate template engine is present. An explicit `/` route declared in the application normally takes precedence over the welcome-page fallback. That is why `static/index.html` and `templates/index.html` **are not automatically merged**.

## 5. Runnable Example: An App with Both Static HTML and Thymeleaf

Create a Maven project with **Java 17+** and **Spring Boot 3.3.x**, including `spring-boot-starter-web` and `spring-boot-starter-thymeleaf`. The example pins `3.3.5` for a concrete Maven configuration, requiring no database or JavaScript build tool.

### 5.1. File Structure

~~~text
html-compare/
├── pom.xml
└── src/main/
    ├── java/com/example/htmlcompare/
    │   ├── HtmlCompareApplication.java
    │   ├── PageController.java
    │   └── ApiController.java
    └── resources/
        ├── application.properties
        ├── static/
        │   ├── index.html
        │   ├── hello-static.html
        │   └── css/site.css
        └── templates/
            └── greeting.html
~~~

### 5.2. Build and Configuration

**File `pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>html-compare</artifactId>
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

The Web dependency provides Spring MVC and embedded Tomcat; the Thymeleaf dependency provides the engine and Spring Boot auto-configuration. Neither `@EnableWebMvc` nor a manual `ViewResolver` bean is needed for this default setup.

**File `src/main/resources/application.properties`**

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

`spring.thymeleaf.cache=false` is for **learning/development** so template changes are immediately visible; it is not a production recommendation. Do not try to enable/disable template caching using static resource properties: they are **two separate cache mechanisms**.

### 5.3. Java: Startup Class and View-Returning Controller

**File `src/main/java/com/example/htmlcompare/HtmlCompareApplication.java`**

~~~java
package com.example.htmlcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HtmlCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(HtmlCompareApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/htmlcompare/PageController.java`**

~~~java
package com.example.htmlcompare;

import java.util.List;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PageController {

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "friend")
            String name,
            Model model) {
        model.addAttribute("name", name);
        model.addAttribute("items", List.of(
                "Spring MVC",
                "Thymeleaf",
                "Static HTML"
        ));
        return "greeting";
    }
}
~~~

Points to observe:

- `@Controller` allows the method to return a **view name**.
- `@GetMapping("/hello")` determines the **URL**, not the template directory path.
- `@RequestParam` reads the query parameter; when `name` is omitted, the default `"friend"` is used.
- `Model` holds data for this render pass. `name` varies by request, whereas `items` in this lab is a fixed list.
- `return "greeting";` makes Thymeleaf use `templates/greeting.html` per the default prefix/suffix.
- You do not instantiate Thymeleaf manually or call `Files.readString` or `getResourceAsStream` inside the controller.

**File `src/main/java/com/example/htmlcompare/ApiController.java`**

~~~java
package com.example.htmlcompare;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(name = "name", defaultValue = "friend")
            String name) {
        return Map.of("message", "Hello, " + name);
    }
}
~~~

The second controller illustrates a **different branch**: `@RestController` writes serialized Java values into the HTTP response body (typically JSON via Jackson). `Map.of(...)` is **not a view name** and does not invoke Thymeleaf. This avoids confusing returning data to a frontend with rendering HTML on the server.

### 5.4. Thymeleaf Template: HTML Rendered from the Model

**File `src/main/resources/templates/greeting.html`**

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thymeleaf Page</title>
  <link rel="stylesheet" th:href="@{/css/site.css}" href="/css/site.css">
</head>
<body>
  <h1>Hello, <span th:text="${name}">guest</span>!</h1>
  <p>This HTML was rendered on the server by Thymeleaf.</p>
  <h2>Example List</h2>
  <ul>
    <li th:each="item : ${items}" th:text="${item}">Sample item</li>
  </ul>
  <p th:if="${#lists.isEmpty(items)}">No items yet.</p>
  <a th:href="@{/}">Back to home</a>
</body>
</html>
~~~

Meaning:

- `th:text="${name}"` replaces the **text content** of the `span` with the value of `name`, escaped for HTML text context.
- `th:each="item : ${items}"` repeats an `li` for each element; `th:text="${item}"` displays each element's value.
- `th:if="${#lists.isEmpty(items)}"` keeps the paragraph only when the list is empty. In this example, the list has three items, so "No items yet." does not appear in the rendered response.
- `th:href="@{/css/site.css}"` builds a link respecting the application's context path instead of hardcoding a root path in prefixed deployments.
- Fallback content like `guest` or `Sample item` is useful when opening the template for design; when Thymeleaf runs, it replaces them accordingly.

Because this file lives inside `templates`, it is not served directly merely for being named `greeting.html`. Requesting `GET /templates/greeting.html` under default settings does not ask to "render the template," and normally returns 404 because it is neither a static resource URL nor a controller route.

### 5.5. Static HTML: Server Returns the File as Saved

**File `src/main/resources/static/index.html`**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Static and Template</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Static HTML Home Page</h1>
  <p>This file is served directly from the static folder.</p>
  <p><a href="/hello?name=Lan">View Thymeleaf page with name Lan</a></p>
  <p><a href="/hello-static.html?name=Lan">View static HTML with the same parameter</a></p>
  <p><a href="/api/hello?name=Lan">View JSON from RestController</a></p>
</body>
</html>
~~~

`static/index.html` acts as the welcome page for `GET /` when no `/` controller or higher-priority configuration exists. In this lab, `GET /` serves the static page.

**File `src/main/resources/static/hello-static.html`**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Static HTML</title>
  <link rel="stylesheet" href="/css/site.css">
</head>
<body>
  <h1>Hello, <span th:text="${name}">guest</span>!</h1>
  <p>This file does NOT go through Thymeleaf.</p>
  <p>Adding ?name=Lan to the URL does not substitute the name.</p>
  <a href="/">Back to home</a>
</body>
</html>
~~~

The `th:text="${name}"` attribute was placed intentionally in the **static** file to prove the difference: the server returns the raw `th:text` attribute in the HTML source, and a normal browser ignores Thymeleaf conventions and displays the fallback text `guest`. Changing the URL to `/hello-static.html?name=Mai` leaves the **HTML file identical**; the query string only alters data if you write server or client logic to read it.

**File `src/main/resources/static/css/site.css`**

~~~css
body {
  font-family: system-ui, sans-serif;
  max-width: 760px;
  margin: 2rem auto;
  line-height: 1.6;
}
h1 {
  color: #1d4ed8;
}
a {
  color: #0f766e;
}
~~~

The same static CSS can be referenced from static pages via `href="/css/site.css"` and from templates via `th:href="@{/css/site.css}"`. **Using HTML templates does not mean CSS/JS/images must also be templates.** Assets are normally served statically to benefit from caching.

## 6. Running and Observing Live Responses

In the `html-compare` project directory, using JDK 17+ and Maven, run:

~~~bash
mvn spring-boot:run
~~~

Once the app is listening on port 8080, try each request in turn:

~~~bash
curl -i http://localhost:8080/
curl -i "http://localhost:8080/hello?name=Lan"
curl -i "http://localhost:8080/hello?name=Mai"
curl -i "http://localhost:8080/hello-static.html?name=Lan"
curl -i "http://localhost:8080/api/hello?name=Lan"
curl -i http://localhost:8080/css/site.css
~~~

Expected results to verify (do not treat full response headers or whitespace as fixed):

| Request | Body Producer | Observable Content |
| --- | --- | --- |
| `GET /` | `static/index.html` | `Static HTML Home Page` |
| `GET /hello?name=Lan` | `PageController` + `greeting.html` | `Hello, Lan!`; includes three items |
| `GET /hello?name=Mai` | Same template, different `Model` | `Hello, Mai!`; includes three items |
| `GET /hello-static.html?name=Lan` | File `static/hello-static.html` | `Hello, guest!`; unchanged by `name` |
| `GET /api/hello?name=Lan` | `@RestController` + JSON converter | `{"message":"Hello, Lan"}` |
| `GET /css/site.css` | Static CSS file | CSS contents; bypasses view resolver |

For `GET /hello?name=Lan`, the HTML response contains a fragment equivalent to:

~~~html
<h1>Hello, <span>Lan</span>!</h1>
~~~

For `GET /hello-static.html?name=Lan`, the **HTTP body** still contains the raw source line:

~~~html
<h1>Hello, <span th:text="${name}">guest</span>!</h1>
~~~

This is observable evidence via `curl`: templates are processed; static HTML is returned verbatim as a file. HTML engines may normalize markup or whitespace differently depending on settings; verify **semantics and key elements** rather than matching every byte of the entire page.

For JSON, property order in a single-property example poses no issue, while real responses may include additional headers. In Windows PowerShell, if you encounter the `curl` alias, run `curl.exe -i ...`.

### 6.1. Trying a Name Containing HTML Tags: Escaping Difference

Run:

~~~bash
curl -i --get --data-urlencode "name=<script>alert(1)</script>" http://localhost:8080/hello
~~~

`th:text` escapes special HTML characters in text context, so the rendered output is equivalent to:

~~~html
<span>&lt;script&gt;alert(1)&lt;/script&gt;</span>
~~~

The browser displays the literal string `<script>alert(1)</script>` as text instead of turning it into an executable `script` element. This is a key difference between **escaped text output** and **intentionally inserted raw HTML**.

Never blindly change `th:text` to `th:utext` just to preserve formatting: `th:utext` writes **unescaped HTML**, which can lead to XSS if the input is untrusted. Escaping must match the output context; values placed inside JavaScript, CSS, URLs, or attributes each have their own rules. Never assume every interpolation is safe in every position.

### 6.2. Packaging the JAR and Inspecting the Classpath

Stop the application and run:

~~~bash
mvn clean package
jar tf target/html-compare-0.0.1-SNAPSHOT.jar
java -jar target/html-compare-0.0.1-SNAPSHOT.jar
~~~

In the `jar tf` listing, look for these entries:

~~~text
BOOT-INF/classes/static/index.html
BOOT-INF/classes/static/hello-static.html
BOOT-INF/classes/static/css/site.css
BOOT-INF/classes/templates/greeting.html
~~~

Those lines are the **paths to look for inside the JAR**, not the entire output. Compiled Java classes are also in the JAR. After starting the JAR, re-test the same URLs as when running via Maven. If a template is missing from the artifact, `/hello` can fail view resolution even though the Java classes packaged cleanly.

## 7. Annotations That Commonly Cause Confusion

### 7.1. @Controller and @RestController

The two snippets below show the exact behavior each annotation specifies:

~~~java
@Controller
class HtmlPageController {
    @GetMapping("/page")
    String page() {
        return "greeting";
    }
}
~~~

This is an **abbreviated snippet** for illustration: it can be used in an app that already has `templates/greeting.html` and Thymeleaf, after placing the class, annotations, and imports in the proper package. The value `"greeting"` is a **view name**.

~~~java
@RestController
class TextController {
    @GetMapping("/text")
    String text() {
        return "greeting";
    }
}
~~~

This is also an **abbreviated snippet**: the response body is the literal string `greeting`, typically with a text content type, **not the template's HTML**. `@RestController` essentially combines `@Controller` and `@ResponseBody` semantics for methods returning data.

Additionally, inside a `@Controller`:

~~~java
@GetMapping("/plain")
@ResponseBody
public String plain() {
    return "<p>This is a response body string</p>";
}
~~~

The return value is written as a text/HTML body according to the configured converter and content type, not treated as a template name. Returning HTML manually through the body requires handling encoding, content type, and escaping yourself; for pages with dynamic data, the view/template mechanism is usually clearer.

### 7.2. Model Is Data for the View, Not a Database

`Model` holds attributes supplied for rendering a single request. It is **not** persistent storage, not a JDBC connection, and does not automatically preserve data for the next request. Each request receives model data prepared by its own execution flow.

Example of a controller reading data from a service and adding it to the model:

~~~java
@GetMapping("/products")
public String products(Model model) {
    model.addAttribute("products", productService.findVisibleProducts());
    return "products";
}
~~~

This is **non-standalone illustrative code** because `productService` and `products.html` are not defined. The takeaway is the pattern **controller/service fetches data -> Model -> engine renders**; database access is a separate topic.

### 7.3. View Names Differ from Redirects and Static Paths

`return "greeting"` requests rendering a Thymeleaf view; `return "redirect:/hello?name=Lan"` requests an HTTP redirect to another URL; `return "forward:/..."` requests a server-side forward via Spring's view mechanism. These prefixes are special Spring MVC syntax, different from writing raw HTML to the response.

If the goal is to send a user from a controller to `static/about.html`, redirect to the proper URL, such as `"redirect:/about.html"`. Do not return `"static/about.html"` expecting it to be served as a static resource; Thymeleaf may instead try to look up a template under that view name.

## 8. Does Dynamic Data Always Require a Template Engine?

**No.** There are at least three common models:

| Model | Where Is Initial HTML Produced? | Where Does New Data Appear? | Example |
| --- | --- | --- | --- |
| Pure static HTML | Prebuilt file | None, or hardcoded content only | Fixed about page |
| Static HTML + JavaScript calling APIs | Prebuilt file | Browser calls JSON API and updates DOM | Simple web dashboard |
| Server-side rendering with a template engine | Server merges template + model | On the server before sending HTML; client can update further | Profile page or user-specific list |

The JavaScript snippet below is a **browser-side illustration**, not a required part of the Section 5 project:

~~~html
<p id="message">Loading...</p>
<script>
  fetch("/api/hello?name=Lan")
    .then(response => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(data => {
      document.getElementById("message").textContent = data.message;
    })
    .catch(() => {
      document.getElementById("message").textContent = "Failed to load data";
    });
</script>
~~~

HTML can be served from `static/` and still show a dynamic greeting via JS. Here, the server returns static HTML and JSON from `@RestController`, and the browser combines them. By contrast, Thymeleaf returns HTML already containing `Lan` as soon as the response arrives, even before the browser executes JavaScript.

Frameworks like React/Vue/Angular, static site generators, and prerendering/hydration have their own deployment models; do not lump them all together with Thymeleaf merely because they all produce HTML.

## 9. When to Choose a Template Engine vs. Static HTML

**Prefer static HTML** when content rarely changes per user, needs no server data at render time, and benefits from simple packaging/caching/CDNs—for example, user guides, about pages, or static health pages (where appropriate). An SPA project also typically has a server serve statically built HTML/JS/CSS bundles.

**Prefer a template engine** when the server already holds data needed per request, when you need reusable layouts/headers/footers, list/conditional rendering, or immediate content in the initial HTTP response—such as product details, receipts, forms, and validation messages.

**Both can be combined:** Thymeleaf renders pages while CSS, JS, images, and fonts live in `static/`. This is a common pattern: templates generate data-driven structure/content while the static handler serves shared assets.

| Practical Question | Recommended Direction |
| --- | --- |
| "Does content vary by user, permissions, or request?" | If yes and it should arrive in the initial HTML, consider templates |
| "Is it just a landing page and asset files?" | Static is usually simpler |
| "Does the frontend call REST APIs to update data?" | Static HTML or an SPA can both fit |
| "Do you need form validation and server-rendered errors?" | A template engine is convenient |
| "Do you want CDNs to cache CSS/JS for hours?" | Static assets with versioned/hashed filenames |
| "Do you want shared headers/footers across server-rendered pages?" | Template fragments/layouts work well |
| "Do you want minimal frontend JavaScript logic?" | Server-side templates are usually a good fit |
| "Must the app return JSON for mobile or other clients?" | API controllers return JSON; template HTML is a separate UI channel |

Do not choose solely on the belief that "static is always faster." Latency also depends on databases, caches, reverse proxies, HTML size, network, render frequency, gzip/Brotli, and deployment topology. Static files are easy to cache because content is request-independent, yet SSR can also be cached safely when designed for the right context.

## 10. Configuration and Caching Issues

### 10.1. Thymeleaf Template Resolver

With the Thymeleaf starter, Spring Boot typically auto-configures these properties:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=true
~~~

These illustrate **common defaults** for a Thymeleaf application. You do not need to write them when using defaults. `spring.thymeleaf.cache=true` reuses resolved/compiled template structures in production; it is **not** equivalent to caching personalized HTML across requests.

While learning, set `spring.thymeleaf.cache=false` so the engine picks up template edits more easily. When running from an executable JAR, editing local source files still requires rebuilding and repackaging if those changes are not inside the artifact; disabling template caching **does not hot-patch bytes inside an already running JAR**.

### 10.2. Static Resources

Spring Boot MVC serves static resources via `ResourceHttpRequestHandler` from default locations. Key properties:

~~~properties
# Example: change the static URL pattern to /assets/**
spring.mvc.static-path-pattern=/assets/**

# Example: replace the list of static resource locations:
spring.web.resources.static-locations=classpath:/static/
~~~

Both properties affect the **static handler**, not the Thymeleaf template resolver:

- `spring.mvc.static-path-pattern` changes the URL pattern. If set to `/assets/**`, `static/css/site.css` is served at `/assets/css/site.css`.
- `spring.web.resources.static-locations` **replaces the default list of static locations**. If set to only `classpath:/static/`, do not assume `public`, `resources`, or `META-INF/resources` remain included.
- Never set `spring.web.resources.static-locations=classpath:/templates/` to "enable templates": doing so can expose raw template source as static files instead of running them through the engine, causing security and functional bugs.
- Changing the static URL prefix does not change `@GetMapping("/hello")` URLs or Thymeleaf's prefix.

If you set `spring.mvc.static-path-pattern=/assets/**` while a template contains `th:href="@{/css/site.css}"`, you must update the asset's logical URL—for example, `@{/assets/css/site.css}`—unless a resource URL pipeline handles it.

### 10.3. HTTP Caching of HTML Differs from Template Caching

- **Template cache:** Thymeleaf's internal cache of parsed/resolved templates, reducing template-processing overhead.
- **HTTP cache:** browser/CDN/proxy caching of responses by URL, headers, and policy. For user-specific HTML, be very careful with `Cache-Control` and response variants to avoid leaking data.
- **Static asset cache:** CSS/JS/images can often be cached long-term with hashed/versioned filenames; Spring MVC's resource chain/versioning can manage those URLs.

A Thymeleaf page can be freshly rendered on every request **even while template caching is enabled**. Conversely, a static file can be cached by the browser without sending a new request. These are two independent cache layers.

## 11. Security and Common Pitfalls

### 11.1. Escaping Data When Rendering

`th:text` escapes HTML in text context, making it appropriate for displaying names, comments, and untrusted values. `th:utext` outputs raw HTML and should only be used when content is genuinely trusted or properly sanitized for display. For inline JavaScript, URLs, CSS, and event handlers, use context-appropriate escaping/URL builders and validate inputs.

Merely rendering HTML server-side does not automatically make an app immune to XSS, injection, CSRF, or data leaks. Enforce authorization in controllers, services, and security filters; **never** place private data inside a static directory. When a template view needs protection, configure security rules for both the route and the underlying data.

### 11.2. Diagnostics Table

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| Visiting `/hello` returns 404 | Missing controller mapping or wrong path/context path | Check `@GetMapping` and startup logs |
| `GET /hello` returns 500 with template-not-found error | Missing `templates/greeting.html`, wrong view name, or missing engine | Check path, Thymeleaf starter, prefix/suffix, and JAR |
| `GET /templates/greeting.html` returns 404 | `templates` is not a default static root | Call the controller URL `/hello` |
| `@RestController` returns `"greeting"`, browser shows text `"greeting"` | Return value written as response body | Use `@Controller` when resolving a view name |
| Placed `greeting.html` in `static` and `th:text` does not evaluate | Static handler does not invoke Thymeleaf | Move file to `templates` and render via controller |
| `Model` has data but HTML stays empty/unchanged | Wrong key name, wrong expression, or wrong template rendered | Match `addAttribute` with `${...}` |
| Template edited yet old page still appears | Template cache, browser/proxy cache, or stale JAR | Check dev config, headers, and deployed artifact |
| Page renders but CSS returns 404 | Wrong static path, context path, or missing file in JAR | Inspect Network tab and asset URL |
| One user's HTML leaks to another | HTTP caching or missing per-user authorization | Check `Cache-Control`, authentication, authorization, session |
| XSS after inserting dynamic HTML | Raw HTML/`th:utext` or wrong context escaping | Switch to escaped output and validate data |
| `/` does not show expected page | Competing static `index.html`, template `index`, and `/` route | Inspect fallback order and controllers |
| Works locally, fails in production JAR | Source files not packaged or case mismatch | Run `jar tf` and check exact paths |

### 11.3. Note on Routes and 404 Errors

Spring MVC separates controller mappings from the static resource handler. If `/hello` is unmapped and the `/**` static handler catches it, the server may log "no static resource found" rather than "no controller found." That message **does not mean `/hello` should be moved into the static folder**. Check controller routing first, then static resources.

### 11.4. Note on Editing Files While the App Is Running

When running from an IDE or dev plugin, resources may be copied or hot-reloaded depending on setup. When running from a JAR, resources live inside the archive. Therefore:

- Editing `src/main/resources/templates/greeting.html` does not guarantee an already running JAR changes immediately.
- `spring.thymeleaf.cache=false` cannot read updated source files if the runtime is reading old bytes inside a JAR.
- Adding cache headers for CSS does not make Thymeleaf cache all user HTML.

## 12. Applied Exercises and Self-Check

**Exercise A – Predict the response.** An app has `static/profile.html` containing:

~~~html
<h1 th:text="${name}">Sample Profile</h1>
~~~

When requesting `GET /profile.html?name=Lan`, will the default server replace `${name}` with `Lan`? If not, what will the user normally see?

**Exercise B – Predict the URL.** Given `templates/orders/list.html` and a controller with `@GetMapping("/orders")` returning `"orders/list"`, is the access URL `/orders` or `/templates/orders/list.html`? Why?

**Exercise C – Controller annotation.** Why does a `@RestController` returning the String `"home"` not cause Thymeleaf to render `templates/home.html`?

**Exercise D – Choose the architecture.** You need a public help guide shared by everyone and an order-detail page for a logged-in user. Which should go in `static` and which through a template? What additional controls are needed for the order page?

**Exercise E – Safety.** Why is `th:text` safer than `th:utext` when data comes from a user form? Should raw data be concatenated into a `<script>` tag?

**Exercise F – Experiment.** In the Section 5 app, change `name=Lan` to `name=Mai` on `/hello` and compare with `/hello-static.html`. Which parts of the HTML change, and why?

**Guided Answers:**

1. No. The static handler serves the file as-is, and the browser usually displays the fallback `Sample Profile`; the Thymeleaf attribute remains in the source.
2. `/orders`, because the controller routes the request; the view name `orders/list` only tells the engine where the matching template is located.
3. `@RestController` applies `@ResponseBody` semantics, writing the String into the body instead of resolving a view.
4. The shared guide can be static; the order page suits server rendering when driven by service data. You must enforce authentication, per-order authorization, and HTTP cache controls.
5. `th:text` escapes HTML in text context; `th:utext` can allow dangerous markup. For JS, use context-appropriate output encoding and avoid injecting raw untrusted data.
6. `/hello` updates the rendered name from the Model; `/hello-static.html` does not interpret query parameters or `th:text`.

## 13. Technical Summary

- **Static HTML** = pre-existing files, by default in static locations, typically served by `ResourceHttpRequestHandler`; query parameters do not automatically alter file content.
- **Template HTML** = template files in `templates`, selected by a `@Controller`'s view name and rendered with a `Model` by Thymeleaf or another configured engine.
- `@RestController` is typically used to return JSON or direct data, whereas `@Controller` is typically used to return HTML view names; `@ResponseBody` or configuration can alter this, so always verify the method's actual semantics.
- The `.html` extension does not determine whether a page is static or dynamic; **the request-handling pipeline** decides.
- Real-world apps often combine **templates for data-driven HTML pages** and **static assets for CSS, JS, and images**.
- When debugging, inspect the request URL, handler/controller, template path, HTTP response, and actual files inside the JAR. For security, control escaping, access permissions, and caching together.

## 14. References

- Spring Boot 3.3 — Servlet Web Applications (Static Content, Welcome Page, Template Engines): https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Annotated Controllers, Return Values, Model and Views: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — Static Resources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Thymeleaf 3.1 — Tutorial, `th:text`, `th:utext`, `th:each`, and URL expressions: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
