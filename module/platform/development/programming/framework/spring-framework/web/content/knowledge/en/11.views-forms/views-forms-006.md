# Redirect, Forward, and the Post/Redirect/Get Pattern in Spring MVC

## 1. Why Distinguish Redirect, Forward, and Post/Redirect/Get?

In web applications using **Spring MVC** and HTML forms, after handling an HTTP request, a controller can:

1. Return a **view** to render immediately within the current response.
2. **Redirect**: ask the browser to send a new request to another URL.
3. **Forward**: transfer the same request to another resource/handler inside the server via the Servlet `RequestDispatcher`.
4. Apply **Post/Redirect/Get (PRG)**: process the `POST` data, then redirect to a `GET` so the user can view the result more safely when refreshing.

These behaviors are not equivalent. Confusing them can cause users to accidentally resubmit forms, lose success messages, expose data in URLs, or produce tests returning unexpected HTTP statuses.

For example, a user opens the book creation form at `GET /books/new`, enters a title, and clicks "Save". If the `POST /books` handler writes to the database and then **returns success HTML directly to the POST**, clicking Refresh can cause the browser to warn about resubmitting the form. PRG turns the result display step into a separate GET, such as `GET /books/42`.

**Scope:** Spring Web MVC **Servlet stack**, controllers returning views (Thymeleaf/JSP), and browser forms. Complete examples use **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**. HTTP redirect concepts also relate to REST APIs, though this is not the automatic navigation mechanism of JavaScript SPAs or Spring WebFlux.

## 2. Three HTTP Processing Flows from the Client's Perspective

### 2.1. Rendering a View Immediately

```text
Browser                    Spring MVC
   | GET /books/new              |
   |---------------------------->|
   |                             | controller returns "books/new"
   | 200 OK + HTML               | -> ViewResolver -> Thymeleaf
   |<----------------------------|
   |
Address bar: /books/new
```

There is no redirection. The controller specifies the **view name** `books/new`; Thymeleaf renders HTML. The browser keeps showing the original URL.

If a controller handles `POST` and also returns `"books/result"` directly, that response belongs to the POST request; refreshing the page can prompt the browser to resend the POST.

### 2.2. Redirect: Two Independent Requests

```text
Browser                           Spring MVC
   | POST /books                        |
   |---------------------------------->|
   |                                    | validate + save
   | 302 Found                          |
   | Location: /books/42                |
   |<----------------------------------|
   |                                    |
   | GET /books/42                      |
   |---------------------------------->|
   |                                    | load + render detail view
   | 200 OK + HTML                      |
   |<----------------------------------|
   |
Address bar: /books/42
```

The controller can return `"redirect:/books/42"`. Spring MVC processes the special `redirect:` prefix, creating a redirect view to return a `3xx` status and `Location` header to the browser. The browser decides whether to follow the redirect and send a new request; `curl` does not follow redirects automatically unless passed `-L`.

**A redirect is not a forward:** the new GET request has its own request parameters, headers, body, and lifecycle. Request-scoped objects, the previous `Model`, and the previous `BindingResult` do not carry over automatically. Required data must be passed via URL params or flash attributes depending on semantics.

### 2.3. Forward: The Same Request Transferred Inside the Server

```text
Browser                          Spring MVC / Servlet
   | GET /books/forward-demo              |
   |------------------------------------->|
   |                                       | handler A
   |                                       | return "forward:/books/forward-target"
   |                                       | RequestDispatcher.forward(...)
   |                                       | handler B / target resource
   | 200 OK + HTML from target             | (no HTTP 3xx)
   |<-------------------------------------|
   |
Address bar: /books/forward-demo
```

`forward:` in Spring MVC triggers an internal transfer via Servlet `RequestDispatcher.forward()` when handled by a supporting `UrlBasedViewResolver`. The browser **does not receive a Location redirect**, does not send a new request, and keeps showing the original URL in the address bar.

In a forward, the request and response remain within the same Servlet dispatch lifecycle. Request attributes can be shared with the target resource; filters/interceptors may run differently depending on `DispatcherType.FORWARD`, mappings, and the container. This is **not** a way to reach an external host from the browser.

### Quick Comparison

| Criterion | Direct view rendering | Redirect | Forward |
| --- | --- | --- | --- |
| Does browser make a new request? | No | **Yes**, if it follows the redirect | No |
| Intermediate HTTP response | `200` or handler status | `3xx` + `Location` | No `3xx` from forward |
| Address bar URL | Keeps original URL | Changes to target URL | Keeps original URL |
| Request method to target | No target request | Depends on `3xx` and client; PRG typically switches to GET | Keeps current request (e.g., POST stays POST) |
| Request attributes | Available in current request | Not carried over automatically | Can be reused |
| Model & flash data | Model renders view immediately | URL attrs / flash attrs | Data passed via request attributes/model depending on view |
| To another domain | No | Possible, if permitted | No |
| Suitable after successful POST | May cause resubmission | **Yes, per PRG** | Cannot replace PRG |

## 3. Redirects in Spring MVC: Two Implementation Approaches

### 3.1. Returning a Logical View Name Starting with `redirect:`

A controller using `@Controller` (not `@RestController`) can return a string:

```java
@PostMapping("/books")
public String create() {
    // Data saved successfully, received ID 42.
    return "redirect:/books/42";
}
```

This is an **illustrative method** to be placed inside a controller class with annotations/imports. `redirect:` is a **view name prefix**, not text to send as an HTTP response body. If the method belongs to `@RestController`, a `String` is normally treated as the **response body**, so the client may see the literal text `redirect:/books/42` instead of being redirected.

For `redirect:/books/42`, `RedirectView` usually uses HTTP `302 Found` by default for HTTP/1.0 compatibility in Spring MVC 6.1. Modern browsers usually perform a GET when following a `302` after POST, but if you need **explicitly enforced GET** semantics, HTTP `303 See Other` is the better choice (see Section 4).

Spring MVC recognizes the `redirect:` prefix through its view resolution infrastructure, so this name **differs** from `"books/42"` (which is treated as a template name). Relative URLs, leading `/`, context paths, and reverse proxies can affect the final `Location` URL. Verify behavior with `server.servlet.context-path` if the application is deployed under a context other than `/`.

### 3.2. Returning `RedirectView` When Customizing Status

```java
@GetMapping("/go")
public RedirectView go() {
    RedirectView view = new RedirectView("/books/42");
    view.setContextRelative(true);
    view.setHttp10Compatible(false);
    return view;
}
```

This is also a snippet inside a controller, importing `org.springframework.web.servlet.view.RedirectView`. Setting `http10Compatible=false` makes `RedirectView` use **`303 See Other` by default** on HTTP/1.1 paths instead of relying on `sendRedirect` with 302. You can also set `setStatusCode(HttpStatus.SEE_OTHER)` in appropriate configurations.

For PRG requiring `303`, the typical logic is to save data successfully on POST and then return a `RedirectView` pointing to the GET URL. However, do not mix `Model` and `RedirectView` arbitrarily; use `RedirectAttributes` to control which values appear in the URL/flash.

### 3.3. For REST APIs That Do Not Render Views

For a pure JSON endpoint, an HTTP redirect can still be returned with `ResponseEntity<Void>`:

```java
return ResponseEntity.status(HttpStatus.SEE_OTHER)
        .location(URI.create("/api/orders/42"))
        .build();
```

This snippet belongs inside a method returning `ResponseEntity<Void>`, importing `HttpStatus`, `ResponseEntity`, and `java.net.URI`. `303` informs the client to use GET to access another representation. Do not assume every `fetch()`/HTTP client automatically navigates the UI like a browser; JavaScript clients have their own redirect/fetch handling. REST APIs creating resources also commonly return `201 Created` and `Location`; status selection must follow the application contract rather than forcing every JSON API into PRG.

## 4. Understanding 301, 302, 303, 307, and 308 Properly

| HTTP status | Primary semantics | Method of follow-up request |
| --- | --- | --- |
| `301 Moved Permanently` | Resource moved permanently | For POST, some user agents **may switch to GET** per HTTP rules |
| `302 Found` | Temporary redirect | For POST, browsers usually switch to GET, though do not rely on it as a method guarantee |
| `303 See Other` | View another resource/confirmation after the prior request | **Client performs a retrieval request (typically GET)**; ideal for PRG |
| `307 Temporary Redirect` | Temporary redirect preserving method and body | **Does not change method** per HTTP semantics |
| `308 Permanent Redirect` | Permanent redirect preserving method and body | **Does not change method** per HTTP semantics |

**For a data-writing POST, do not use 307/308 as a PRG mechanism**: clients will resend POST to the new URL and still risk unintended writes. `302` is the common default in Spring MVC, while `303` expresses the intent "POST succeeded → view GET" more clearly.

For an old GET URL permanently moved to a new GET URL, `301/308` can be appropriate, though redirect caching and method preservation must be considered. Never pick a redirect code solely based on being in the `3xx` range.

**Do not assume:** "HTTP 302 always guarantees GET." Different HTTP clients and method cases behave differently. Contract tests should verify that the server sends the right `Location` and status; separate browser/integration tests should verify that user agents follow the path you expect.

## 5. Post/Redirect/Get (PRG): Solving Form Resubmission

### 5.1. The Problem with Returning a View Directly from POST

Flow **without PRG**:

```text
GET /books/new -> form
POST /books    -> saves book and returns success HTML immediately
Refresh        -> may resubmit POST /books
                   -> creates duplicate record / duplicate payment / re-processes
```

If the form only displays information without mutating server state, the risk is low; however, for order creation, money transfers, bookings, or account registration, resubmission can have serious consequences. Modern browsers sometimes warn before resubmitting, but UI warnings must never be relied on as business safeguards.

### 5.2. PRG Turns the Final Page into a GET

```text
1. GET /books/new
   -> HTML form

2. POST /books with title=Clean+Code
   -> validate
   -> if valid: save book ID 42
   -> HTTP 302 (or 303), Location: /books/42

3. GET /books/42
   -> fetch newly saved book
   -> render detail view, HTTP 200

4. Refresh
   -> GET /books/42
   -> does not re-run POST /books
```

This is a **two-step interaction pattern for successful write operations**. The final GET URL can be bookmarked, shared, refreshed, and in HTTP terms queries an existing resource.

**PRG does not guarantee exactly-once processing.** Users can double-click and send two POSTs before receiving a redirect; proxy/client retries or timeouts before the redirect can also produce duplicate requests. Critical transactions need **idempotency keys**, unique constraints, transactional guards, optimistic locking, or equivalent protections. PRG primarily solves UX and form-refresh resubmission after POST, not server-side deduplication.

### 5.3. Redirect on Success, Re-Render Form on Validation Failure

Standard rule:

- **Valid POST:** save → redirect to GET.
- **Invalid POST:** keep `BindingResult` and the form object in the **same request**, return the form view name to display errors; no redirect needed.
- **Detail GET:** load fresh data from the service/database and render; do not expect the entire form object from the POST request to still exist.

Because `BindingResult` is request/model data, redirecting automatically on validation failure discards errors unless you **explicitly** transport the form and binding errors via flash/session. The direct approach is `return "books/new"` when errors exist.

## 6. `RedirectAttributes`: URL Data and Flash Attributes

Spring MVC provides `org.springframework.web.servlet.mvc.support.RedirectAttributes` to control data carried across a redirect. There are two branches that **must be distinguished**:

```java
redirectAttributes.addAttribute("id", book.id());
redirectAttributes.addFlashAttribute(
        "success", "Book created successfully");
return "redirect:/books/{id}";
```

This is a snippet inside a POST handler, not a standalone Java program.

### 6.1. `addAttribute`: URL Path/Query

`addAttribute("id", 42)` can fill the `{id}` placeholder of `redirect:/books/{id}`, producing Location `/books/42`. Any remaining primitive/string redirect attributes not consumed by URL expansion may be turned into **query parameters** by Spring.

Example:

```java
redirectAttributes.addAttribute("tab", "details");
return "redirect:/books/{id}";
```

If `id=42` is present and `tab` is also added, the URL can become `/books/42?tab=details`. URL-encoded query strings fit **non-sensitive** navigational data. Never use query params for passwords, tokens, card details, session secrets, or internal notices you do not want recorded in browser history or proxy logs.

Note Spring MVC's historical behavior of promoting **default model attributes** into the redirect URL: simple values in the model can become query parameters if left uncontrolled. Declaring `RedirectAttributes` and adding only needed fields reduces this risk. In complex applications, you can evaluate `ignoreDefaultModelOnRedirect` on `RequestMappingHandlerAdapter`, though avoid altering global configuration without testing the impact.

### 6.2. `addFlashAttribute`: Temporary Data for the Next GET

`addFlashAttribute("success","Book created")` temporarily stores the success notice in the output flash map. After the redirect, Spring places the flash data into the target request's model when matched; the template can read `${success}`.

Advantages:

- Keeps notices out of URLs, browser history, and access logs.
- Avoids sending newly created payloads through query strings.
- Ideal for one-time notices such as "Saved" or "Updated successfully".

Limitations to remember:

- Flash attributes are **typically stored temporarily in the HTTP session** and popped when the target request matches; they are not a database.
- Once consumed, the message is not guaranteed to persist on a second refresh or later bookmark visit.
- Spring uses `FlashMap` / `FlashMapManager`. `RedirectView` can stamp the target path/query onto the flash map to reduce the chance of another request picking it up by mistake, yet this **does not completely eliminate race conditions** under concurrent tabs or polling.
- Never store large business objects, passwords, tokens, or results requiring high durability in flash storage.
- With distributed sessions/multiple instances, session storage must be configured appropriately; flash does not replace a database.
- If a client disables/loses session cookies or redirects to another environment not sharing the session, the flash message may never arrive.

### 6.3. Flash Is Not a Long-Term Session Attribute

`@SessionAttributes` and `HttpSession` serve multi-request state; flash serves temporary handoff across a single redirect. When durable notifications or resource authorization checks are needed, the target GET must query the service/database. Never treat a flash message as proof that the user is authorized to view a resource.

## 7. Complete Spring Boot Example: Form, Redirect, Flash, and Forward

This example provides a working Spring MVC application with Java 17 and Maven, covering:

- `GET /books/new`: displays the HTML form.
- `POST /books`: validates `title`; on success creates the book in memory and returns `redirect:/books/{id}`.
- `GET /books/{id}`: renders the detail page, displaying the flash message right after redirect.
- `GET /books/forward-demo`: sets a request attribute and forwards internally to `/books/forward-target`.
- `GET /books/forward-target`: renders a view using the request attribute.

The demo uses in-memory `ConcurrentHashMap` and `AtomicLong` solely to run standalone, **not for production persistence**. Real systems require services/repositories, transactions, authorization, CSRF protection (if using web login/sessions), and idempotency for critical operations.

### 7.1. Project Structure

```text
prg-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/prg/
    │   │   ├── PrgDemoApplication.java
    │   │   ├── BookCatalog.java
    │   │   ├── BookForm.java
    │   │   └── BookController.java
    │   └── resources/templates/books/
    │       ├── new.html
    │       ├── detail.html
    │       └── forward-target.html
    └── test/java/example/prg/
        └── BookControllerTests.java
```

Each public Java class must be saved with the exact filename and package shown in the directory tree.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>prg-demo</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

**`src/main/java/example/prg/PrgDemoApplication.java`**

```java
package example.prg;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrgDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrgDemoApplication.class, args);
    }
}
```

### 7.2. In-Memory Catalog

**`BookCatalog.java`**

```java
package example.prg;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    public record Book(long id, String title) {}

    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    public Book create(String title) {
        long id = sequence.incrementAndGet();
        Book book = new Book(id, title);
        books.put(id, book);
        return book;
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }
}
```

`AtomicLong` generates incrementing IDs per instance; `ConcurrentHashMap` is safe for concurrent access within the demo scope. When the server restarts, data disappears. Do not implement real orders this way: you need durable storage, concurrency control, transactions, and duplicate/idempotency rules.

### 7.3. Form DTO with Bean Validation

**`BookForm.java`**

```java
package example.prg;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class BookForm {
    @NotBlank
    @Size(max = 80)
    private String title;

    public BookForm() {}

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

This is a dedicated **input DTO** for the form, not a database entity. `@NotBlank` rejects empty or whitespace-only strings, and `@Size(max=80)` enforces a length limit. `@Valid @ModelAttribute` triggers validation when the POST is bound, and `BindingResult` lets the controller read errors.

### 7.4. Controller: Valid POST Redirects, Invalid POST Re-Renders Form

**`BookController.java`**

```java
package example.prg;

import example.prg.BookCatalog.Book;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/books")
public class BookController {

    private final BookCatalog catalog;

    public BookController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("bookForm", new BookForm());
        return "books/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("bookForm") BookForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "books/new";
        }

        Book book = catalog.create(form.getTitle().strip());

        redirectAttributes.addAttribute("id", book.id());
        redirectAttributes.addFlashAttribute(
                "success", "Book created successfully");

        return "redirect:/books/{id}";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        Book book = catalog.find(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Book not found"));
        model.addAttribute("book", book);
        return "books/detail";
    }

    @GetMapping("/forward-demo")
    public String forwardDemo(HttpServletRequest request) {
        request.setAttribute("forwardMarker", "from-first-handler");
        return "forward:/books/forward-target";
    }

    @GetMapping("/forward-target")
    public String forwardTarget(
            HttpServletRequest request, Model model) {
        Object marker = request.getAttribute("forwardMarker");
        model.addAttribute("marker",
                marker == null ? "none" : marker);
        return "books/forward-target";
    }
}
```

Key observations in this file:

1. `@Controller` (not `@RestController`) so `String` is interpreted as a **view name**.
2. `@Valid @ModelAttribute("bookForm")` binds form data rather than requiring a JSON body. `BindingResult` stands **immediately after** the validated object.
3. On error, the controller returns `"books/new"` within the **current POST** so Thymeleaf reads `BindingResult` and displays errors. No book is created and no redirect occurs.
4. When valid, `catalog.create` runs **once during the POST request**, generating an ID.
5. `addAttribute("id", id)` fills the `{id}` placeholder; `addFlashAttribute("success",...)` holds the one-time notification.
6. `"redirect:/books/{id}"` generates 3xx + Location; the browser follows it to `GET /books/{id}`.
7. `detail` reloads the data by ID rather than reading `Book` from flash. The `success` flash attribute is automatically added by Spring to the matching GET model.
8. `forwardDemo` sets a request attribute and `forward:` transfers the same request to the second handler; `forwardTarget` reads `marker` and renders the view.
9. If the ID does not exist, `ResponseStatusException` produces a `404` response per Spring Boot configuration. The `detail` template is never rendered with a dummy object.
10. `/books/new` and `/books/forward-demo` are more specific than `/books/{id}`; Spring selects the exact mapping without manual `id` checks for fixed paths.

In real systems, `@ControllerAdvice` or error views can present consistent `404` pages; this is outside the focus on PRG.

### 7.5. Thymeleaf Form Template

**`src/main/resources/templates/books/new.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Create Book</title>
</head>
<body>
    <h1>Create Book</h1>
    <form th:action="@{/books}" th:object="${bookForm}"
          method="post">
        <label for="title">Title</label>
        <input id="title" type="text" th:field="*{title}"
               maxlength="80" required>
        <p th:if="${#fields.hasErrors('title')}"
           th:errors="*{title}">Title error</p>
        <button type="submit">Save</button>
    </form>
</body>
</html>
```

The `th:object="${bookForm}"` and `th:field="*{title}"` expressions connect the template to the model/form DTO; Spring MVC + Thymeleaf integration retrieves `BindingResult`. HTML `required` and `maxlength` assist user experience, **not replace** server-side Bean Validation (clients can bypass any HTML checks).

### 7.6. Detail and Flash Message Template

**`src/main/resources/templates/books/detail.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Book Details</title>
</head>
<body>
    <p th:if="${success}" th:text="${success}">
        Notice
    </p>
    <h1 th:text="${book.title}">Book Title</h1>
    <p>
        ID: <span th:text="${book.id}">0</span>
    </p>
    <a th:href="@{/books/new}">Create another book</a>
</body>
</html>
```

Right after redirecting from a valid POST, the first GET normally sees the `success` flash attribute. On refreshing GET or opening the detail link directly, the notice section does not appear because the flash has already been consumed; book details still come from `catalog.find(id)`.

With Thymeleaf, `th:text` escapes standard HTML output; never use `th:utext` for user-entered content unless a proper sanitization strategy is in place. This is a benefit of template escaping, though it does not replace authorization or other security rules.

### 7.7. Template Illustrating Forward

**`src/main/resources/templates/books/forward-target.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Forward target</title>
</head>
<body>
    <h1>Forward reached target</h1>
    <p th:text="${marker}">none</p>
</body>
</html>
```

Open `GET /books/forward-demo`. The initial controller sets request attribute `forwardMarker`. `forward:/books/forward-target` performs an internal transfer; the target handler reads the attribute and places `marker` into the view. The browser keeps displaying `/books/forward-demo`; there is no 302 Location.

**Why not use forward after a book-creating POST?** Forward **keeps the POST method**, leaving the final page as the response to the original POST without issuing a new GET request. Refreshing can resubmit the POST or trigger a browser warning. PRG must use redirect.

## 8. Manual Testing with Browser and curl

From the `prg-demo` directory, with Java 17+ and Maven installed:

```bash
mvn test
mvn spring-boot:run
```

The two commands are **sequential steps**; `mvn test` completes before running `mvn spring-boot:run`. By default the example uses `localhost:8080` unless `server.port` is changed.

### 8.1. View the Form

Open in a browser:

```text
http://localhost:8080/books/new
```

Expect `200 OK` with a form containing a `title` field. There is no database so the form does not list books; it simply creates an in-memory record on POST.

### 8.2. Valid POST: Observe Redirect Without Auto-Following

```bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Clean Code'
```

Expected output includes:

```http
HTTP/1.1 302
Location: http://localhost:8080/books/1
```

Spring/the container may write `Location` as an absolute or relative URL depending on configuration, reverse proxy, and context path. What needs contract testing is **3xx and target `/books/1`**, not necessarily identical host/Location formatting across every environment. On a fresh instance, the first ID is `1`; if books were created earlier, the ID will be higher.

Browsers follow redirects automatically on form submission. `curl` **does not follow redirects by default**; use `curl -L` if you want to follow and inspect the final response. When issuing POST via curl, avoid combining `-X POST` with `-L` when testing method switching, because `-X` forces the specified method across redirects instead of standard automatic switching. Use:

```bash
curl -i -L \
  -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Domain-Driven Design' \
  http://localhost:8080/books
```

`-c/-b` saves and sends session cookies across requests as curl follows redirects, which is necessary to receive session-backed flash attributes. If you suspect POST-to-GET switching behaves inconsistently across clients/tools, inspect redirect methods with `curl -v` and status codes; for strict PRG, use 303 as shown in Section 10.

### 8.3. GET the Detail Page

Once you know the created ID, call:

```bash
curl -i http://localhost:8080/books/1
```

Response `200 OK` with HTML containing book ID 1 **if the book was created in the current running instance**. If not created yet or after a server restart, `/books/1` returns `404`, matching the in-memory catalog demo.

### 8.4. Invalid POST

```bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=   '
```

Expect HTTP `200 OK` with the form view showing `@NotBlank` validation errors, **no** `Location` redirect header, and **no** new record. This pattern does not return status `400` because traditional HTML forms typically render errors on the same `200` page; for REST JSON APIs, returning `400` per contract is standard.

### 8.5. Internal Forward

```bash
curl -i http://localhost:8080/books/forward-demo
```

Expected response is `200 OK` with no 3xx redirect; HTML contains `from-first-handler`. `curl` does not need `-L` because no redirect is sent to the client. The browser address bar remains `/books/forward-demo`.

## 9. Testing with MockMvc

`MockMvc` verifies status, view name, redirect location, flash map, and forward dispatches without needing a real HTTP server port. With the Thymeleaf example, `@SpringBootTest` loads the full application context, renderer, and `BookCatalog` bean.

**`src/test/java/example/prg/BookControllerTests.java`**

```java
package example.prg;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormRendersView() throws Exception {
        mvc.perform(get("/books/new"))
           .andExpect(status().isOk())
           .andExpect(view().name("books/new"))
           .andExpect(model().attributeExists("bookForm"));
    }

    @Test
    void validPostRedirectsAndStoresFlashMessage() throws Exception {
        mvc.perform(post("/books")
                    .param("title", "Clean Code"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrlPattern("/books/*"))
           .andExpect(flash().attribute(
                    "success", "Book created successfully"));
    }

    @Test
    void invalidPostRendersFormWithBindingError() throws Exception {
        mvc.perform(post("/books")
                    .param("title", "   "))
           .andExpect(status().isOk())
           .andExpect(view().name("books/new"))
           .andExpect(model().attributeHasFieldErrors(
                    "bookForm", "title"));
    }

    @Test
    void forwardDoesNotReturnRedirectStatus() throws Exception {
        mvc.perform(get("/books/forward-demo"))
           .andExpect(status().isOk())
           .andExpect(forwardedUrl("/books/forward-target"));
    }

    @Test
    void missingBookReturnsNotFound() throws Exception {
        mvc.perform(get("/books/999999999"))
           .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
mvn test
```

If all 5 test methods pass, Maven finishes with exit code `0` and output along the lines of `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. Exact log ordering, timing, and report layout depend on the environment.

**Note on MockMvc forward:** The `forwardedUrl(...)` matcher checks the URL MVC forwarded to, which **does not mean** it re-executes the full request into controller B like a real browser and servlet container. To verify HTML actually rendered by the target through a forward, run an integration test with an embedded server (`RANDOM_PORT`) and an HTTP client/browser.

**Note on flash:** `flash().attribute(...)` asserts the output flash map on the redirect response. To test that the message appears in the follow-up GET request, the test must simulate the redirect **and propagate flash/session state properly** rather than assuming `MockMvc` automatically follows redirects like a browser. In critical systems, add a two-request integration test to guard flash behavior.

## 10. Using Explicit 303 See Other for PRG

In the sample program, `return "redirect:/books/{id}"` typically produces 302. If an API needs strict HTTP method-switching guarantees, after saving successfully you can return a `RedirectView` configured for 303.

Snippet **replacing the post-creation logic** in the POST handler:

```java
RedirectView redirect =
        new RedirectView("/books/" + book.id());
redirect.setContextRelative(true);
redirect.setHttp10Compatible(false);
redirect.setExposeModelAttributes(false);
return redirect;
```

This requires changing the **method return type from `String` to `RedirectView` or `View`**, and importing `org.springframework.web.servlet.view.RedirectView`. This is not a patch you can paste below `return "redirect:..."` without updating the method signature; adopt it as a distinct approach. `RedirectAttributes.addFlashAttribute(...)` is still processed when returning a Spring MVC `RedirectView`, though with model exposure disabled, the URL must be constructed explicitly as shown.

Another API-oriented option is returning `ResponseEntity.status(HttpStatus.SEE_OTHER).location(...).build()`. If serving HTML forms with views and flash messages, `RedirectView` is usually more convenient. **Do not switch 302 to 307/308** when the goal is GET after POST.

## 11. Redirect and Forward: Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Browser prints literal `redirect:/books/1` | Controller is `@RestController`/`@ResponseBody` | Use `@Controller` returning a view name, or return an explicit HTTP redirect via `ResponseEntity` |
| Refresh creates a second record | POST returns view directly or client resends POST | Use PRG; add idempotency/transactions/unique constraints for critical logic |
| GET after redirect lacks POST data | Redirect is a new request | GET queries database/service by ID; use flash for transient display notices |
| Flash message does not appear | Client did not follow Location, dropped session cookie, or flash already consumed | Check HTTP client/session and redirect path |
| Flash message occasionally vanishes across tabs | `FlashMap` has concurrency/race limitations | Never use flash for durable state; minimize competing requests |
| Form validation errors lost after redirect | `BindingResult` belongs to the old request | Re-render the form when invalid; if redirecting, propagate binding errors intentionally |
| Sensitive info appears in `Location` | `addAttribute` added query params to redirect | Use safe IDs, flash for transient notices, and never put secrets in URLs |
| Redirect points to wrong URL under context path | Misconfigured relative/absolute URL or proxy | Check context path, forwarded headers, and `RedirectView.contextRelative` |
| Returning `forward:` fails to run as expected | View resolver lacks prefix support or target resource cannot be dispatched | Check `UrlBasedViewResolver` and target Servlet mapping |
| Refresh remains POST after forward | Forward preserves request/method | Use redirect for PRG |
| Redirect 307/308 keeps POST at destination | Those statuses preserve method and body | Use 303 or 302 per PRG requirements |
| Browser reports redirect loop | A redirects to B and B redirects back to A | Inspect auth guards/mappings, `Location` chain, and cookies |
| Detail page lacks flash after bookmark/refresh | Flash is single-use | Load primary data from service; treat messages as transient notifications |
| Open redirect to external domain | Directly feeding client `next`/`returnUrl` into `redirect:` | Allowlist internal destinations; validate and normalize URIs |
| POST succeeds yet GET returns 404 | Uncommitted data, read-after-write lag, wrong ID, lost memory state | Check transactions, consistency, persistence, and `Location` path |
| Spring Security returns 403 on form submit | Missing or invalid CSRF token | Enable CSRF per policy, embed token in HTML form, and test with CSRF |

### Using POST/Redirect/Get with Spring Security

The sample project omits `spring-boot-starter-security`, so no Spring Security CSRF filter is active. In applications with session/cookie login and Spring Security, state-changing POSTs are normally protected by **CSRF tokens**. When using Thymeleaf with Spring Security integration, Spring can auto-inject tokens into forms; still inspect rendered markup and write `MockMvc` tests with `csrf()`. Never disable CSRF just to make a PRG demo work.

**PRG does not replace authorization**: `GET /books/{id}` must check permissions for the book if it is a private resource. A "saved" flash notice does not prove the GET caller is authorized to view the content.

### Open Redirect: Major Security Risk

Do not do this:

```java
// ANTI-PATTERN: redirecting to a client-supplied URL without validation.
@GetMapping("/go")
public String unsafe(@RequestParam String next) {
    return "redirect:" + next;
}
```

Attackers can craft links redirecting to phishing sites. If a destination must come from the client, validate it against a host/path **allowlist**, permit only trusted internal paths, normalize, and reject `//external.example`, unusual schemes, double URL encoding, or bypass variants. Better yet, store server-controlled destination keys mapped to fixed URLs instead of accepting raw target URLs.

## 12. Distinguishing PRG from Idempotency and Transactions

PRG issues a GET request after POST, yet in distributed systems **a POST can still execute twice before redirecting**. A payment flow needs multiple layers of protection:

```text
Browser -> POST /payments (Idempotency-Key: unique-operation-id)
             |
             v
      Check existing operation / uniqueness
             |
        +----+---------+
        |              |
        v              v
   first request    duplicate request
   transactional    return prior result
   write                 |
        |----------------|
        v
   303 See Other
   Location: /payments/{id}
        |
        v
   GET /payments/{id}
```

This diagram is conceptual only; there is no runnable payment code in this lesson. Keys must be scoped per principal/operation, persisted long enough, handle races, and replay consistently. If a client sends two requests with different bodies under the same key, the server needs a proper error rule. Database unique constraints usually guard invariants better than non-transactional check-then-insert logic.

For ordinary CRUD forms, PRG + unique constraints may suffice. For payments, ticket booking, money transfers, and order placement, idempotency keys and proper business transactions are required. Never confuse "refreshing GET does not resubmit POST" with "the server guarantees a POST is never processed twice".

## 13. Choosing the Right Mechanism for Each Requirement

| Scenario | Recommended Approach |
| --- | --- |
| GET HTML page or immediate form error display | Return normal view name |
| Valid form POST creating a resource and moving to detail page | **PRG: redirect** |
| Invalid form POST needing binding errors displayed | Return same view, preserving `BindingResult` |
| One-time success notice after redirect | `RedirectAttributes.addFlashAttribute` |
| Public ID or filter visible in URL | `RedirectAttributes.addAttribute` |
| Transferring the same request to an internal servlet/handler | `forward:...` when genuinely needed |
| Requiring the browser to definitely use GET after write | HTTP **303 See Other** |
| Temporary redirect preserving POST method/body | `307` for specialized cases; **never for PRG** |
| Permanently moving an old GET URL to a new URL | Consider `301/308` and cache/method effects |
| REST JSON creating a resource and returning JSON | `201 Created` + `Location` is usually appropriate |
| Strict duplicate-POST prevention | Idempotency/DB constraint/transaction **beyond PRG** |

## 14. Self-Check Exercises

1. When a `@Controller` handler returns `"redirect:/books/42"`, what does the browser receive? Does it send a new request?
2. When a handler returns `"forward:/books/forward-target"`, how do the browser address bar URL and target request HTTP method change?
3. Why does PRG reduce resubmission risk on refresh without replacing an idempotency key?
4. In `RedirectAttributes`, how do `addAttribute` and `addFlashAttribute` differ in data placement and lifetime?
5. Why should validation failure return the form view instead of redirecting by default?
6. Why does `303` express PRG intent better than `307`?
7. A method inside `@RestController` returns the string `"redirect:/books/42"`. What can happen?
8. If a flash success message disappears after refreshing the GET page, is that a bug requiring long-term flash storage?
9. When a controller uses `return "redirect:/books/{id}"`, what is the purpose of `addAttribute("id",42)`?
10. If a client sends `?next=https://untrusted.example` and the server appends it to a redirect URL, what is the risk?
11. Why should `GET /books/42` load book details from the service instead of relying on the POST's `BookForm`?
12. When testing `forwardedUrl` with `MockMvc`, does that prove the entire target HTML rendered through a real Servlet container?

**Answer hints:** (1) HTTP 3xx + Location; the client follows it with a new request. (2) Browser URL stays unchanged; the same request/method transfers internally. (3) Two POSTs can still arrive before the redirect. (4) `addAttribute` targets URL/path/query; flash uses temporary storage (usually session) for the target request. (5) `BindingResult` lives in the current request. (6) `303` specifies retrieval/GET, while `307` keeps the method. (7) It may return the string as the response body instead of redirecting. (8) No; flash is designed to be transient and single-use. (9) Fills the `{id}` placeholder. (10) Open redirect/phishing. (11) GET is an independent/bookmarkable contract. (12) No; a real integration test is needed for full forward dispatch.

## 15. References

- [Spring Framework 6.1 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Framework 6.1 — Flash Attributes](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/flash-attributes.html)
- [Spring Framework — View Resolution, Redirecting and Forwarding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Framework 6.1 — RedirectView Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html)
- [Spring Framework 6.1 — RedirectAttributes Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/support/RedirectAttributes.html)
- [Spring Framework — MVC Model and View](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-methods.html)
- [Spring Boot 3.3 — Spring MVC and Thymeleaf](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [RFC 9110 — HTTP Semantics, redirection 3xx](https://www.rfc-editor.org/rfc/rfc9110.html)

**Summary:** Redirect sends a new destination so the client issues a new request; forward transfers internally inside the server; PRG is the workflow *POST saves successfully → 3xx redirect → GET displays*. In Spring MVC, `redirect:`, `forward:`, `RedirectAttributes`, and view resolvers provide the implementation mechanisms. Use flash for short-lived notices, use services/databases for real data, and always combine validation, authorization, and CSRF/idempotency when security or duplicate-processing protection is required.
