# Thymeleaf, FreeMarker, JSP: Roles and Usage Conditions in Spring MVC

> **Scope:** Spring Web MVC on the Servlet stack, Java 17+, and Spring Boot 3.x / Spring Framework 6.x. This topic explains the roles of the three server-side view technologies, how controller → Model → ViewResolver → template maps out, usage conditions for each technology, paths and dependencies, form binding, HTML escaping, JSP deployment limitations, along with runnable Java examples. Standalone snippets are clearly marked.

## 1. Where Does the View Fit in Spring MVC?

When building server-rendered web pages, a controller receives an HTTP request, prepares data in the **Model**, and returns a **logical view name**. `ViewResolver` finds the matching View; the view engine combines the model and template to generate HTML.

```text
GET /hello?name=Lan
        |
DispatcherServlet
        |
@Controller + Model
        | model.addAttribute("name", "Lan")
        | return "hello"
        v
ViewResolver
        | Thymeleaf: templates/hello.html
        | FreeMarker: templates/hello.ftlh
        | JSP: /WEB-INF/jsp/hello.jsp
        v
Rendered HTML --> Browser
```

Illustrative controller:

```java
@Controller
class GreetingController {
    @GetMapping("/hello")
    String hello(
            @RequestParam(defaultValue = "Guest") String name,
            Model model) {
        model.addAttribute("name", name);
        return "hello";
    }
}
```

Imports in the example: `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.GetMapping`, `RequestParam`, `org.springframework.ui.Model`.

**Note:** `return "hello"` in `@Controller` normally represents a **view name**. If the class is `@RestController` (or the method has `@ResponseBody`), the string `"hello"` is normally the **HTTP response body** itself, handled by `HttpMessageConverter`. When writing a REST API returning JSON/DTOs, you do not necessarily need to install any template engine.

## 2. Quick Selection Map

| Criterion | Thymeleaf | FreeMarker | JSP |
| --- | --- | --- | --- |
| Nature | Java HTML template engine emphasizing natural templates | Java template engine for HTML/text with directives and macros | Jakarta Server Pages compiled into servlets by the servlet container |
| Syntax | `th:text`, `th:each`, `th:object`, `th:field` | `${...}`, `<#if>`, `<#list>`, `<#macro>` | JSP EL `${...}`, JSTL `<c:...>`, Spring taglibs |
| Starter/engine | `spring-boot-starter-thymeleaf` | `spring-boot-starter-freemarker` | JSP compiler + Jakarta JSTL and container |
| Default templates in Boot 3.5 | `classpath:/templates/*.html` | `classpath:/templates/*.ftlh` | View resolver config, usually `/WEB-INF/jsp/*.jsp` |
| Strengths | Natural-looking HTML, Spring MVC forms and errors | Template macros, presentation structure, and text/HTML output | Maintaining existing Servlet/JSP/JSTL applications |
| Deployment notes | Templates must be present on the classpath | Choose proper HTML output format and escaping | Executable JAR does not support JSP; requires WAR/container setup |

All three engines perform **view rendering**; they do not replace controllers, business services, databases, validation, or security. For a new application packaged as an executable JAR, Thymeleaf or FreeMarker is usually easier to deploy than JSP because JSP has runtime/packaging constraints.

## 3. Thymeleaf: Natural HTML and Spring Form Integration

### 3.1. When to Use It?

Thymeleaf is suitable when the UI is primarily server-side HTML with Spring MVC forms, validation errors, lists, or reusable fragments. HTML templates remain structurally valid when opened directly for preview; `th:*` attributes are processed by the engine during server rendering.

With Spring Boot 3.x, declare:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

This is a `pom.xml` fragment using the Spring Boot parent/BOM; for a servlet application also add `spring-boot-starter-web`. Spring Boot 3.5 defaults:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
```

You do not need to write these lines if you use the exact defaults. `return "hello"` is mapped by the resolver to `src/main/resources/templates/hello.html`.

### 3.2. HTML Example

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Greeting</title>
</head>
<body>
  <h1 th:text="'Hello, ' + ${name}">Hello, guest</h1>
  <a th:href="@{/hello(name='Mai')}">Greet Mai</a>
</body>
</html>
```

- `${name}` retrieves the `name` attribute from the model.
- `th:text` writes **HTML-escaped** content into the element.
- `@{...}` is a URL expression, producing more accurate URLs than hardcoding when the application has a context path.
- The original HTML text `Hello, guest` is a preview placeholder; during rendering, the engine replaces it with the model value.

If a client passes `name=<script>alert(1)</script>`, `th:text` renders it as escaped text characters rather than a script tag. Avoid using `th:utext` with untrusted HTML because it can inject user-controlled markup into the DOM.

### 3.3. Loops, Conditionals, and Fragments

```html
<ul>
  <li th:each="book : ${books}"
      th:text="${book}">Sample book</li>
</ul>
<p th:if="${books.empty}">No books yet</p>
```

The controller needs to put the corresponding `books` model attribute. To reuse UI snippets:

```html
<!-- templates/fragments/common.html -->
<footer th:fragment="footer">Spring MVC Example</footer>
```

```html
<!-- in another template -->
<div th:replace="~{fragments/common :: footer}"></div>
```

### 3.4. Spring Form Binding

```html
<form th:action="@{/profiles}" th:object="${profileForm}" method="post">
  <label>Name
    <input type="text" th:field="*{displayName}">
  </label>
  <p th:if="${#fields.hasErrors('displayName')}"
     th:errors="*{displayName}">Name error</p>
  <button type="submit">Save</button>
</form>
```

In the controller, GET puts `profileForm` into the model, while POST declares `@Valid @ModelAttribute("profileForm") ProfileForm form` with `BindingResult` placed **immediately after** the form object. The `th:field` and `th:errors` helpers rely on Spring MVC's binding/validation infrastructure.

If using Spring Security with CSRF enabled, POST forms require a CSRF token. Thymeleaf provides integration to generate tokens under appropriate conditions, though you should always inspect the actual rendered HTML and security configuration. Do not treat hidden/disabled UI fields as security: clients can still craft arbitrary requests.

## 4. FreeMarker: Directives, Macros, and General-Purpose Templates

### 4.1. When to Use It?

FreeMarker fits systems with many templates/macros, complex presentation-layer loops/conditionals, or existing FreeMarker usage for HTML and other text formats. It is a template engine, not a servlet container/JSP.

Dependency with Spring Boot 3.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-freemarker</artifactId>
</dependency>
```

Spring Boot 3.5 defaults:

```properties
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.content-type=text/html
```

In particular, **the default suffix is `.ftlh`** in Boot 3.5, not `.ftl` as in many older tutorials. `return "hello"` points to `src/main/resources/templates/hello.ftlh`.

### 4.2. HTML Template

```html
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Greeting</title></head>
<body>
  <h1>Hello, ${name}!</h1>
  <#if books?has_content>
    <ul>
      <#list books as book>
        <li>${book}</li>
      </#list>
    </ul>
  <#else>
    <p>No books yet</p>
  </#if>
</body>
</html>
```

FreeMarker uses:
- `${name}` to insert a model value;
- `<#if>` / `<#else>` for conditionals;
- `<#list books as book>` for loops;
- `${name!'Guest'}` to supply a default value when `name` is missing.

With `.ftlh` templates and standard HTML output format, FreeMarker auto-escapes text in HTML. Do not disable escaping or use `?no_esc` for untrusted input. If using `.ftl` through legacy configuration, verify the HTML output format and escaping; renaming the file alone is not enough to guarantee XSS safety across all templates.

### 4.3. Macros, Forms, and Practical Considerations

```ftl
<#macro label value>
  <span class="label">${value}</span>
</#macro>

<@label value="Spring MVC" />
```

Macro snippets can be saved in a dedicated template and imported:

```ftl
<#import "macros.ftlh" as ui>
<@ui.label value="Book" />
```

FreeMarker does not use `th:object/th:field` syntax. Typical forms use HTML `name="displayName"` and model values:

```html
<form action="/profiles" method="post">
  <input type="text" name="displayName" value="${displayName!}">
  <button type="submit">Save</button>
</form>
```

This is only a UI fragment; for non-empty context paths, CSRF, validation errors, and data protection, Spring/FreeMarker macro integration or additional model/URL handling is required. Do not copy the snippet above as a production form without CSRF handling. Spring's macros support binding and error messages when properly configured/imported.

## 5. JSP: Traditional View in the Servlet/Jakarta Ecosystem

### 5.1. How Is JSP Rendered?

JSP (Jakarta Server Pages) is compiled into a servlet and executed by the servlet container. In Spring MVC, the controller still returns a logical view name; `InternalResourceViewResolver` typically forwards to the JSP file. JSP provides Expression Language (EL), JSTL tag libraries, and Spring JSP form tags.

Sample project structure:

```text
src/main/
├─ java/com/example/demo/DemoApplication.java
└─ webapp/
   └─ WEB-INF/
      └─ jsp/
         └─ hello.jsp
```

Typical view resolver configuration in Spring Boot:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

Thus `return "hello"` typically forwards internally to `/WEB-INF/jsp/hello.jsp`. Placing JSPs under `WEB-INF` prevents clients from accessing JSP files directly via ordinary paths, forcing requests through a controller/mapping. With JSP, `InternalResourceViewResolver` usually needs to sit **at the end of the ViewResolver chain** because it recognizes view names very broadly and can block earlier/later resolvers from working properly.

### 5.2. Important Limitations When Running Spring Boot

According to Spring Boot's documentation on embedded servlet containers:

- **Executable JARs do not support JSP.**
- With **Tomcat and Jetty**, JSP can work using **WAR packaging**; an executable WAR can run with `java -jar application.war`, and the WAR can be deployed to a compatible external container.
- **Undertow does not support JSP.**
- A custom `error.jsp` does not automatically replace Spring Boot's error view by default; dedicated error page setup is needed.
- The `src/main/webapp` path, build plugins, JSP engine, and Jakarta versions must all match. Do not place JSPs in `classpath:/templates` and expect a Boot JAR to render them like Thymeleaf.

Example WAR/Tomcat/JSP dependencies for **Spring Boot 3.x**:

```xml
<packaging>war</packaging>

<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apache.tomcat.embed</groupId>
    <artifactId>tomcat-embed-jasper</artifactId>
  </dependency>
  <dependency>
    <groupId>jakarta.servlet.jsp.jstl</groupId>
    <artifactId>jakarta.servlet.jsp.jstl-api</artifactId>
  </dependency>
  <dependency>
    <groupId>org.glassfish.web</groupId>
    <artifactId>jakarta.servlet.jsp.jstl</artifactId>
  </dependency>
</dependencies>
```

This is a **POM fragment**, not a standalone `pom.xml`. The Spring Boot BOM/parent must manage compatible versions. When deploying a WAR to an external container, the embedded container is typically configured with `provided` scope per Boot documentation; when running an executable WAR, keep the classpath and packaging aligned. Do not use old `javax.servlet`/JSTL dependencies with Spring Boot 3.x (Jakarta namespaces).

Application class supporting external WAR deployment:

```java
@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }
}
```

The snippet above requires the corresponding Spring Boot imports; this is an illustrative WAR configuration snippet, **not a complete program**.

### 5.3. JSP/JSTL Template

```jsp
<%@ page contentType="text/html; charset=UTF-8"
         pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Hello JSP</title></head>
<body>
  <h1>Hello, <c:out value="${name}" />!</h1>
  <ul>
    <c:forEach items="${books}" var="book">
      <li><c:out value="${book}" /></li>
    </c:forEach>
  </ul>
</body>
</html>
```

- JSP EL `${name}` accesses model values exposed to the view.
- JSTL `<c:out>` escapes XML/HTML characters in text regions.
- `<c:forEach>` iterates over a collection in the model.
- The URI `jakarta.tags.core` matches modern Jakarta JSTL; the legacy taglib `http://java.sun.com/jsp/jstl/core` is common in older Java EE apps and must be evaluated/migrated when upgrading.
- The Spring JSP form tag library can assist with binding/forms, but requires compatible JSTL/Spring tags setup and differs from Thymeleaf syntax.

### 5.4. When Should You Keep JSP?

Suitable when an existing system already has hundreds of JSP pages, standard WAR deployment with a compatible container, or relies on JSTL/Spring JSP taglibs with no compelling reason to migrate. If building a new Spring Boot service packaged as an executable JAR, Thymeleaf or FreeMarker usually has fewer constraints. Do not migrate JSP to another engine merely by changing file extensions: template syntax, taglibs, and form handling must all be converted.

## 6. ViewResolver, Model, Static Assets, and Return Values

A controller:

```java
@GetMapping("/catalog")
String catalog(Model model) {
    model.addAttribute("title", "Programming Books");
    return "catalog/list";
}
```

The same `"catalog/list"` can resolve to:

| Engine | File Under Common Configuration |
| --- | --- |
| Thymeleaf | `classpath:/templates/catalog/list.html` |
| FreeMarker | `classpath:/templates/catalog/list.ftlh` |
| JSP | `/WEB-INF/jsp/catalog/list.jsp` |

**Distinguish three types of output:**

1. **HTML Template:** the logical view name is resolved to a view file and rendered with the Model.
2. **Static asset:** CSS, JavaScript, and images placed under `src/main/resources/static/` (or configured static resource locations), served by a resource handler without template expression evaluation.
3. **REST response:** JSON/text body via `@RestController`/`@ResponseBody` and `HttpMessageConverter`, requiring no ViewResolver.

View resolver order is especially critical if multiple engines are registered. With the same view name `"hello"` and both Thymeleaf + FreeMarker starters present, resolvers may compete depending on resource conditions and ordering. The simplest approach is to **choose one primary template engine**; if multiple engines are mandatory, configure explicit `view-names` patterns and resolver order, and test both existing and missing views.

### 6.1. Redirect and Forward

```java
@GetMapping("/old")
String old() {
    return "redirect:/new";
}
```

`"redirect:/new"` triggers an HTTP redirect; the browser sends a follow-up request. `"forward:/internal"` performs an internal forward according to MVC/Servlet rules. A plain `return "hello"` is a logical view name and does not ask the browser to send a new request. After a successful POST, **Post/Redirect/Get** prevents duplicate form submissions on refresh.

## 7. Runnable Example — Spring Boot 3.x + Thymeleaf

To avoid `ViewResolver` collisions, the complete example uses a single engine: **Thymeleaf**. Create a project from [Spring Initializr](https://start.spring.io/), Java 17+, Maven, dependencies **Spring Web**, **Thymeleaf**, **Validation**. The corresponding dependencies:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
  </dependency>
</dependencies>
```

This is a POM fragment. When generated via Initializr, the Maven parent, plugins, versions, and project metadata are already set up.

### 7.1. File Structure

```text
src/main/
├─ java/com/example/demo/DemoApplication.java
└─ resources/
   └─ templates/
      ├─ books.html
      └─ book-form.html
```

### 7.2. Complete Java Controller and Form Bean

Place in `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class BookForm {
    @NotBlank
    @Size(max = 80)
    private String title = "";

    public BookForm() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}

@Controller
class PageController {
    private final List<String> books =
            new CopyOnWriteArrayList<>(List.of("Spring MVC"));

    @GetMapping("/books")
    public String list(Model model) {
        model.addAttribute("books", List.copyOf(books));
        return "books";
    }

    @GetMapping("/books/new")
    public String form(Model model) {
        model.addAttribute("bookForm", new BookForm());
        return "book-form";
    }

    @PostMapping("/books")
    public String create(
            @Valid @ModelAttribute("bookForm") BookForm form,
            BindingResult bindingResult,
            RedirectAttributes redirects) {
        if (bindingResult.hasErrors()) {
            return "book-form";
        }

        books.add(form.getTitle());
        redirects.addFlashAttribute("notice", "Book added");
        return "redirect:/books";
    }
}
```

- `PageController` is a `@Controller` so it returns **view names**.
- GET `/books` puts the `books` list into the Model; GET `/books/new` puts the `bookForm` bean into the Model.
- POST `/books` receives the form via `@ModelAttribute`; `@Valid` runs Bean Validation, and `BindingResult` must immediately follow the form parameter.
- If `title` is blank or exceeds 80 characters, the method returns `"book-form"` to re-render with errors.
- On success, it adds the book to the list, sets a flash message, and redirects to GET `/books`. This is PRG, rather than rendering HTML directly from POST.
- The demo uses an in-memory list with no database/security. Production code needs request DTOs containing only contracted fields, CSRF protection (if using session authentication), authorization, and persistence.

### 7.3. List Display Template

`src/main/resources/templates/books.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Book List</title>
</head>
<body>
  <h1>Added Books</h1>
  <p th:if="${notice}" th:text="${notice}"></p>
  <ul>
    <li th:each="book : ${books}"
        th:text="${book}">Sample book</li>
  </ul>
  <a th:href="@{/books/new}">Add Book</a>
</body>
</html>
```

With initial data, the page displays `Spring MVC`. After a POST adding `Effective Java`, the next GET request displays both items. Titles containing `<`/`>` characters are escaped by `th:text`.

### 7.4. Form Template

`src/main/resources/templates/book-form.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Add Book</title>
</head>
<body>
  <h1>Add New Book</h1>
  <form th:action="@{/books}" th:object="${bookForm}" method="post">
    <label for="title">Book Title</label>
    <input id="title" type="text" th:field="*{title}" maxlength="80">
    <p th:if="${#fields.hasErrors('title')}"
       th:errors="*{title}">Invalid book title</p>
    <button type="submit">Save</button>
  </form>
  <a th:href="@{/books}">Back</a>
</body>
</html>
```

Client-side `maxlength="80"` only assists the UI; server-side `@Size(max = 80)` is still required. Having validation and binding work does not mean CSRF/authorization is present; this example intentionally omits Spring Security to focus on views.

### 7.5. Running and Checking the Result

From the Maven project root:

```bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Open `http://localhost:8080/books` and `http://localhost:8080/books/new`. With default port and no custom context path, both GET requests return the corresponding HTML pages (status 200).

Valid POST request:

```bash
curl -i -X POST 'http://localhost:8080/books' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Effective Java'
```

Expected status is **302 Found** and a `Location` header pointing to `/books` (URL representation may vary with context path/config). The browser follows the redirect and displays the list containing `Effective Java`. If using cURL `-L`, cURL follows the redirect; do not assume the first response is the HTML list.

POST request with an empty title:

```bash
curl -i -X POST 'http://localhost:8080/books' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title='
```

The controller re-renders `book-form.html` with validation errors displayed via `th:errors`. Because this is a traditional form model and the method simply returns a view name, the response status in this example is typically **200 OK** even though the form is invalid; JSON APIs may choose a different error status.

The commands above use Bash `\` line continuation. In PowerShell, use `curl.exe` and put the entire command on a single line.

## 8. Switching the Same Controller to FreeMarker

To switch **engines** while keeping controller logic, replace `spring-boot-starter-thymeleaf` with `spring-boot-starter-freemarker` and convert templates to `*.ftlh` using FreeMarker syntax. A minimal list file `src/main/resources/templates/books.ftlh`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Book List</title></head>
<body>
  <h1>Added Books</h1>
  <#if notice??><p>${notice}</p></#if>
  <ul>
    <#list books as book>
      <li>${book}</li>
    </#list>
  </ul>
  <a href="/books/new">Add Book</a>
</body>
</html>
```

The content above illustrates the data model and list rendering, but **is not a complete port of the form**; you still need to add `book-form.ftlh`, the `title` input name, retained values, and Spring's validation error model/macros. Avoid leaving `th:object`/`th:field` inside FreeMarker templates. A hardcoded `/books/new` link works at the demo's root context; projects with a context path should use the engine/configuration's URL helper.

When only FreeMarker is present, the logical view name `"books"` looks for `books.ftlh` under Boot 3.5 defaults. If using `.ftl` files, set `spring.freemarker.suffix=.ftl` **and** verify HTML escaping/output format.

## 9. Switching to JSP and WAR Deployment

With JSP, keep the `@Controller` returning `"books"` but change packaging and paths: WAR + JSP engine/JSTL + `/WEB-INF/jsp/`. Set:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

Example `src/main/webapp/WEB-INF/jsp/books.jsp`:

```jsp
<%@ page contentType="text/html; charset=UTF-8"
         pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Book List</title></head>
<body>
  <h1>Added Books</h1>
  <c:if test="${not empty notice}">
    <p><c:out value="${notice}" /></p>
  </c:if>
  <ul>
    <c:forEach items="${books}" var="book">
      <li><c:out value="${book}" /></li>
    </c:forEach>
  </ul>
  <a href="<c:url value='/books/new' />">Add Book</a>
</body>
</html>
```

To fully port the application, you must also build `book-form.jsp` with JSP/Spring form tags, validation display, CSRF tokens, and URL helpers. Builds/tests must run inside JSP-capable Tomcat or Jetty with WAR packaging and matching Jakarta versions. Do not run an executable JAR and expect `.jsp` files to work automatically.

## 10. Security and Template Responsibility Boundaries

| Risk | Mitigation |
| --- | --- |
| XSS from user input | Thymeleaf `th:text`, FreeMarker HTML auto-escape, JSP JSTL `c:out`; encode for the proper context |
| Rendering user-uploaded/edited templates | Never execute untrusted templates inside the application context |
| CSRF on form POST | CSRF protection with tokens and verify the rendered HTML form |
| Mass assignment | Request DTOs/allowed fields, validation, explicit entity updates |
| Unauthorized access | Authorization in controllers/services/security, not merely hiding links in HTML |
| Object attribute leakage | Put only necessary data into the Model; keep sensitive data out of models |
| URL/path injection | Build href/action via engine URL helpers; do not concatenate arbitrary input into paths |
| Context-incorrect escaping | Never place unvalidated values into inline JS, HTML attributes, CSS, or raw HTML |
| Template caching | Disable cache intentionally in dev; consider enabling it in production |

**Important:** HTML escaping in a text context does not replace CSP or security rules for URL and JavaScript contexts. For example, input `<script>alert(1)</script>` passed through `th:text`, `${value}` in FreeMarker HTML output format, or `<c:out>` in JSP is displayed as text rather than creating a script tag. However, `th:utext`, `?no_esc`, or raw JSP EL can bypass this protection.

## 11. Which Engine to Choose in Real Projects?

**Choose Thymeleaf** when starting a new MVC web UI needing Spring-integrated forms, HTML templates designers can preview directly, and executable JAR deployment. Main cost: `th:*` syntax and learning how to handle fragments and form errors.

**Choose FreeMarker** when you already have complex macros/templates or need one template system for multiple content types; it still renders HTML well when output format and escaping are properly set. Main cost: FreeMarker syntax differs from natural HTML and MVC form/validation behavior must be wired intentionally.

**Keep JSP** when a legacy system has substantial JSP/JSTL assets/tags or deployment targets a WAR on a servlet container with JSP support. Main cost: WAR/container requirements, JSP compiler, Jakarta JSTL compatibility, and template maintenance. Do not choose JSP for a Spring Boot executable JAR.

**Need no engine at all** if the service provides REST JSON for React/Vue/mobile. Controllers return DTOs via `@RestController` and responses are serialized via `HttpMessageConverter`; that is a different architecture from server-rendered views.

## 12. Common Errors and How to Check Them

| Symptom | What to Check | How to Fix |
| --- | --- | --- |
| Page prints literal `books` instead of HTML | Does the method/class have `@ResponseBody`/`@RestController`? | Use `@Controller` for views |
| Template not found | Starter, prefix, suffix, file path | Place the file under `templates/` matching the logical view name |
| FreeMarker ignores `.ftl` files | Boot 3.5 defaults to `.ftlh` | Rename files/adjust config and verify escaping |
| JSP fails to render in executable JAR | JSP packaging is unsupported in JARs | Use WAR and a JSP-capable container |
| JSP taglib not found | Missing JSTL or wrong taglib URI/version | Align Jakarta JSTL API + implementation |
| `Circular view path` | View resolver forwards to the same request path | Adjust view name/prefix/suffix |
| Multiple engines render the wrong view | ViewResolvers have overlapping names/patterns | Pick one engine or separate `view-names`/order |
| CSS/JS returns 404 | Confusing static resources with templates | Place CSS/JS under `static/` and use correct URLs |
| Form submission fails with 403 | Likely missing or invalid CSRF token | Check Spring Security filters and HTML form |
| Validation errors do not appear | Wrong model attribute name, missing starter, misplaced `BindingResult` | Check `@Valid` and binding setup |
| Page vulnerable to XSS | Raw/unescaped input in HTML | Escape for the right context and never render untrusted templates |
| Adding JSP still causes 500 | Container, WAR config, JSP compiler/classpath | Test WAR build and actual JSP runtime |

When debugging, follow this order: HTTP mapping → controller return value → ViewResolver → resource path/suffix → engine dependency → runtime packaging → model variables → escaping/security. For JSP, verify **WAR and container** before editing controllers. For Thymeleaf/FreeMarker, verify **starters and classpath templates** before tweaking ViewResolvers.

## 13. Self-Check Questions

**1.** A `@RestController` method returns `"hello"` and `templates/hello.html` exists. Will Spring render the template?

**Answer:** No, the string is treated as the response body. To use a logical view name, use an appropriate `@Controller`.

**2.** With Boot 3.5 defaults, what file does `return "list"` resolve to in Thymeleaf and FreeMarker?

**Answer:** Thymeleaf `classpath:/templates/list.html`, FreeMarker `classpath:/templates/list.ftlh` when the corresponding starters/resolvers are configured.

**3.** If you replace `spring-boot-starter-thymeleaf` with FreeMarker and leave `th:field` in the HTML, will it work?

**Answer:** No. You must convert to appropriate FreeMarker template syntax and handle form binding/validation accordingly.

**4.** Why is a Spring Boot executable JAR a sign not to choose JSP?

**Answer:** Per Spring Boot documentation, JSP is not supported in executable JARs; use a WAR with JSP-capable Tomcat/Jetty if JSP is required.

**5.** Which approach is safer for inserting user strings into HTML?

**Answer:** Use `th:text`, FreeMarker HTML auto-escaping, or `<c:out>` (for text contexts), while encoding for the right context and validating input.

**6.** How does `return "redirect:/books"` differ from `return "books"`?

**Answer:** A redirect instructs the browser to send a new GET request; a view name renders a template for the current request. PRG commonly uses a redirect after a successful POST.

## 14. Official References

- [Spring Framework — View Technologies](https://docs.spring.io/spring-framework/reference/web/webmvc-view.html): Spring MVC pluggable view technologies, template trust boundaries.
- [Spring Framework — View Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-resolvers.html): ViewResolver ordering and configuration.
- [Spring Framework — Thymeleaf](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-thymeleaf.html): Thymeleaf principles in Spring MVC.
- [Spring Framework — FreeMarker](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-freemarker.html): FreeMarker integration, macros, and configuration.
- [Spring Framework — JSP and JSTL](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-jsp.html): JSP view resolver, JSTL, JSP tags.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): JSP limitations for WAR/JAR and servlet containers.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.thymeleaf.*`, `spring.freemarker.*`, `spring.mvc.view.*`.
- [Thymeleaf documentation](https://www.thymeleaf.org/documentation.html): HTML templates, expressions, fragments.
- [Apache FreeMarker Manual](https://freemarker.apache.org/docs/): FreeMarker directives, macros, and output escaping.

**Remember:** all three technologies handle the **View** layer in Spring MVC, yet differ in syntax, dependencies, and deployment requirements. Thymeleaf excels for Spring-integrated HTML/forms, FreeMarker shines for templates/macros, and JSP fits legacy Servlet systems using WARs and JSP containers. When deploying, always check the active engine, file path/suffix, logical view names, HTML escaping, validation, CSRF, and access control rather than only looking at rendered HTML.
