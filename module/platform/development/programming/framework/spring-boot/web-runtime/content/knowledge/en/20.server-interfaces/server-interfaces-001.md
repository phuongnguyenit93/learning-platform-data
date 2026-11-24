# @Controller, Model, and View Names in Web Applications

In Spring Boot, a **server-side rendering (SSR)** application can build HTML on the server and send the result to the browser. Three components typically work together: **`@Controller`** (receives the request, invokes business logic, and selects the result), **`Model`** (presentation data for the request), and the **view name** (the logical name used to locate a template). If a controller returns `"products/list"`, Spring MVC can locate `src/main/resources/templates/products/list.html`, render it with Thymeleaf, and return HTML.

**Distinguish this right from the start:** in a regular `@Controller` method, `return "home"` selects the view named `home`; it does not send the literal text `home`. If the handler is annotated with `@ResponseBody` or resides inside a `@RestController`, the returned string is written as the HTTP response body. This lesson uses **Spring Boot 3.x, Spring MVC, Thymeleaf, and Java 17+**.

## 1. Learning Outcomes

After this lesson, you can:

- Describe the `DispatcherServlet` → `@Controller` → `Model` → `ViewResolver` → template → HTML flow.
- Write handlers that return a view name, add data using `Model.addAttribute`, and place templates in the right location.
- Distinguish between view name, URL mapping, file path, and HTTP response body.
- Use `@ModelAttribute`, form DTOs, `@Valid`, and `BindingResult` with HTML forms.
- Explain `redirect:`, `forward:`, Post/Redirect/Get (PRG), and flash attributes.
- Avoid common pitfalls: missing templates, model key mismatches, mass assignment, XSS, and mutable state on controllers.
- Run a Java 17+ project with three HTML pages, validation, and a body-returning endpoint for self-verification.

## 2. Request Flow for an HTML Page

```text
Browser: GET /?name=Lan
   |
   v
Servlet container / Embedded Tomcat
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping locates @GetMapping("/")
   +--> HandlerAdapter invokes PageController.index(...)
   |       |
   |       +--> model.addAttribute("name", "Lan")
   |       +--> return "index"
   |
   +--> ViewResolver resolves view name "index"
   |       |
   |       +--> ThymeleafView
   |       +--> templates/index.html + Model
   v
HTTP 200, Content-Type: text/html
   |
   v
Browser displays "Hello, Lan!"
```

`DispatcherServlet` is the front controller of Spring MVC. `HandlerMapping` finds the handler matching the URL/HTTP method, and `HandlerAdapter` handles invoking the handler with arguments such as `Model`, `@RequestParam`, and `@ModelAttribute`. If the handler returns a `String` as a view name, `ViewResolver` locates the corresponding `View` object, and the template engine merges the Model into HTML. That is the traditional HTML flow; handlers returning JSON, files, redirects, or performing async processing can take different branches.

| Component | Role | Common Misconception |
| --- | --- | --- |
| `@Controller` | Bean that handles requests, selects a view or another result type | Not synonymous with `@RestController` |
| `@GetMapping`/`@PostMapping` | Defines URL + HTTP method | Does not determine the template file |
| `Model` | Key/value pairs supplied for rendering | Not a database or HTTP session |
| `String` returned from an HTML MVC handler | Logical view name | Not a text body when `@ResponseBody` is absent |
| `ViewResolver` | Finds a view based on the logical name | Does not route HTTP requests |
| Thymeleaf | Renders templates into HTML | Does not replace a business service |
| `redirect:` | Sends an HTTP redirect to a URL | Does not render a template in the current handler |

## 3. @Controller, @RestController, and @ResponseBody

`@Controller` is a stereotype detected by Spring component scanning. Methods annotated with `@RequestMapping`, `@GetMapping`, `@PostMapping`, and so on can handle HTTP requests.

Snippet for an HTML page:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class WelcomeController {
    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("message", "Hello Spring MVC");
        return "welcome";
    }
}
```

This is a **snippet**; it requires a Spring Boot application and the template `src/main/resources/templates/welcome.html`. It receives `GET /welcome`, adds `message`, and then selects the `welcome` view. It does not directly return the literal body `welcome`.

Meanwhile:

```java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "home"; // Selects the home view
    }

    @GetMapping("/plain")
    @ResponseBody
    public String plain() {
        return "OK"; // Response body is OK
    }
}

@RestController
class ApiController {
    @GetMapping("/api/status")
    public String status() {
        return "OK"; // Response body is OK
    }
}
```

This is a **comparison snippet**; it requires importing the corresponding annotations and having a `home` template for the `/page` route. `@RestController` combines the effects of `@Controller` and `@ResponseBody` at the class level. When returning a DTO via `@RestController`, Spring typically uses an appropriate message converter to serialize JSON; with a `String`, the value is written into the body. Do not change an HTML controller into `@RestController` and expect `return "home"` to still render a template.

**Design boundary:** A controller should accept input, call a service, place presentation results into the Model, and choose a view or redirect. Do not put all business logic, SQL, or per-request mutable state inside a controller. Controller beans are typically singletons and may handle concurrent requests.

## 4. Model: Data for a Single Render Pass

`org.springframework.ui.Model` is an interface for attributes accessed by a template. Spring MVC provides an appropriate Model when a handler declares a `Model` parameter:

```java
@GetMapping("/books")
public String books(Model model) {
    model.addAttribute("pageTitle", "Book List");
    model.addAttribute("count", 3);
    model.addAttribute("books", bookService.findVisibleBooks());
    return "books/list";
}
```

This is a **snippet**, with `bookService` and the view assumed to exist. In Thymeleaf:

```html
<h1 th:text="${pageTitle}">Title</h1>
<p th:text="|There are ${count} books|">Book count</p>
<ul>
  <li th:each="book : ${books}" th:text="${book.title}">
    Book title
  </li>
</ul>
```

Keys must **match by name**: `addAttribute("books", ...)` pairs with `${books}`; it does not automatically become `${items}`. If the Model is missing a key, the expression may evaluate to empty or throw an error depending on how the template accesses it.

### 4.1. Model Does Not Store Persistent Data

- **Model:** the dataset serving the view of the current request.
- **Form DTO / View DTO:** an object placed into the Model, not synonymous with an entity.
- **Session/flash:** data carried across multiple requests via a separate mechanism.
- **Database entity/repository:** the persistent storage source, which must not be replaced by `Model.addAttribute`.

After `redirect:`, the browser makes a new request and the previous request's default Model is no longer intact as before. To display a one-time notice after a redirect, use `RedirectAttributes.addFlashAttribute`; to keep content retrievable later, save it in a service/repository and fetch it via GET by ID.

### 4.2. ModelAndView, ModelMap, and Map

Alongside `Model`, Spring MVC accepts `ModelMap` or `Map<String, Object>` as parameters; `ModelAndView` combines both data and the view name into one object:

```java
@GetMapping("/summary")
public String summary(Model model) {
    model.addAttribute("title", "Overview");
    return "summary";
}

@GetMapping("/summary-alt")
public ModelAndView summaryAlt() {
    ModelAndView page = new ModelAndView("summary");
    page.addObject("title", "Overview");
    return page;
}
```

These two methods are **snippets** requiring `ModelAndView` and the `summary.html` template. Both approaches have the same semantic result. `Model` + view name is usually more concise; `ModelAndView` is convenient when you want to bundle the view, Model, and optionally an HTTP status.

## 5. View Names: Different from URLs and File Paths

In Spring Boot 3.x with the Thymeleaf starter, the default configuration is equivalent to:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
```

That means:

| Handler Returns | Corresponding Template File | Possible URL |
| --- | --- | --- |
| `"index"` | `src/main/resources/templates/index.html` | `/` |
| `"orders/list"` | `src/main/resources/templates/orders/list.html` | `/orders` |
| `"users/edit"` | `src/main/resources/templates/users/edit.html` | `/settings` |
| `"redirect:/orders"` | Does not render a template in that handler | Client redirects to `/orders` |
| `"forward:/internal"` | Server performs an internal dispatch | Browser usually keeps the URL |

You should not return `"index.html"` if the suffix is already `.html`; nor should you return `src/main/resources/templates/index.html` as the view name. `ViewResolver` accepts a **logical view name**, not an arbitrary file path. With FreeMarker or another engine, the configuration may differ; check the exact `ViewResolver` in use.

**Templates** in `src/main/resources/templates` are normally processed through a controller. **Static resources** such as `src/main/resources/static/main.css` or `static/logo.svg` are served as static assets, not Thymeleaf views. Returning `"index"` is not a request to `/templates/index.html`.

### 5.1. Symptoms of a View Not Being Found

If the application matched the handler but fails at the rendering step, check:

1. Is `spring-boot-starter-thymeleaf` present?
2. Is the file actually `templates/index.html` or `templates/home.html`?
3. Is there a case mismatch between `Index.html` and `index.html` on Linux?
4. Were `spring.thymeleaf.prefix`/`suffix` modified so the resolver looks at a different path?
5. Was the template packaged into the JAR?
6. Does the template contain an expression accessing an attribute missing from the Model?

A rendering error can result in an HTTP 500 with a template exception, whereas a missing URL mapping is usually a 404. Do not attribute every "page not showing" error to the same cause.

## 6. How Thymeleaf Receives Data from the Model

Common expressions and attributes:

| Syntax | Meaning |
| --- | --- |
| `${attribute}` | Expression accessing a variable in the Model/context |
| `th:text="${title}"` | Inserts text into an element, HTML-escaped |
| `th:each="x : ${items}"` | Iterates over a collection |
| `th:if="${visible}"` | Renders conditionally |
| `th:unless="${visible}"` | Renders if the condition is false |
| `th:href="@{/orders}"` | Generates a link relative to the context path |
| `th:action="@{/submit}"` | Generates an action URL for a form |
| `th:object="${form}"` | Selects the form object |
| `th:field="*{name}"` | Binds an input to the `name` field |
| `th:errors="*{name}"` | Displays field validation errors |

`th:text` escapes HTML by default. For example, if a Model value is `<script>alert(1)</script>`, it is rendered as text rather than producing an executable script tag. `th:utext` allows unescaped HTML; do not use it with untrusted input. When constructing URLs, JavaScript, or CSS, apply context-appropriate escaping, along with separate authorization/CSRF checks.

## 7. @ModelAttribute: Two Roles

**Providing common Model data:** a method annotated with `@ModelAttribute` returns an object to be added as a Model attribute:

```java
@ModelAttribute("siteName")
public String siteName() {
    return "Java Learning Portal";
}
```

This is a snippet inside a `@Controller`, requiring `ModelAttribute` to be imported. Even though the method returns a `String`, it does **not** set the view name because it is declared as an attribute-populating method. `@ControllerAdvice` can be used to supply common data across multiple controllers within an appropriate scope; avoid running heavy database queries on every request just to build a header.

**Receiving form data:** `@ModelAttribute("profileForm")` on a handler parameter binds request parameters to the object:

```java
@PostMapping("/profile")
public String submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

This is a snippet assuming `ProfileForm` and a template. `BindingResult` must follow **immediately after** the bound/validated parameter so the handler can inspect errors; if it is missing or misplaced, validation may be handled via an exception instead of entering `result.hasErrors()`. On error, re-render the form in the current request to preserve submitted values and field errors.

## 8. Complete Spring MVC + Thymeleaf Project, Java 17+

The demo includes:

- `GET /?name=Mai`: an HTML page with a greeting and a list.
- `GET /hello-form`: a form for entering a name.
- `POST /hello-form`: validation; re-renders the form on error, redirects to `/done` when valid.
- `GET /done`: receives a flash message after the redirect.
- `GET /ping`: plain-text body `pong` for comparison with view names.

### 8.1. Initializing with Spring Initializr

Choose **Java 17+**, **Spring Boot 3.x** (for example, the 3.3.x line), Gradle/Groovy, and dependencies **Spring Web**, **Thymeleaf**, and **Validation**. In the `build.gradle` generated by Initializr, the core dependencies block is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is the **dependencies block**, not a complete standalone `build.gradle` file; it requires the Boot plugin, Java plugin, repositories, and Gradle Wrapper generated by Initializr. Do not manually pin versions on individual starters because Boot manages dependency versions. Spring Boot 4.x may use different starter names, so if creating a 4.x project, check the documentation for that major version.

Create the files:

```text
src/main/
  java/demo/
    MvcViewsApplication.java
    GreetingForm.java
    PageController.java
  resources/templates/
    index.html
    hello-form.html
    done.html
```

### 8.2. MvcViewsApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcViewsApplication.class, args);
    }
}
```

Place the file at `src/main/java/demo/MvcViewsApplication.java`. `@SpringBootApplication` is in package `demo` so component scanning detects controllers in the same package.

### 8.3. GreetingForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class GreetingForm {

    @NotBlank(message = "Please enter a name")
    @Size(max = 60, message = "Name must not exceed 60 characters")
    private String name;

    public GreetingForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

`src/main/java/demo/GreetingForm.java` is the form DTO; `@NotBlank` checks that the name is not empty or whitespace-only, and `@Size` limits its length. These constraints are enforced by the provider from `spring-boot-starter-validation`. The HTML `maxlength` attribute only assists UX; the server must still validate.

### 8.4. PageController.java

```java
package demo;

import java.util.List;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class PageController {

    @GetMapping("/")
    public String index(
            @RequestParam(defaultValue = "Friend") String name,
            Model model) {

        model.addAttribute("name", name);
        model.addAttribute(
                "topics", List.of("Controller", "Model", "View"));
        return "index";
    }

    @GetMapping("/hello-form")
    public String showForm(Model model) {
        model.addAttribute("greetingForm", new GreetingForm());
        return "hello-form";
    }

    @PostMapping("/hello-form")
    public String submit(
            @Valid @ModelAttribute("greetingForm") GreetingForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "hello-form";
        }

        redirectAttributes.addFlashAttribute(
                "successMessage",
                "Sent greeting to " + form.getName().strip());
        return "redirect:/done";
    }

    @GetMapping("/done")
    public String done() {
        return "done";
    }

    @GetMapping("/ping")
    @ResponseBody
    public String ping() {
        return "pong";
    }
}
```

Placed at `src/main/java/demo/PageController.java`. Breakdown:

1. `index` adds `name` and `topics` to the Model, and `return "index"` selects the template.
2. `showForm` creates an object under the key `greetingForm`, matching the name referenced by the form template.
3. `submit` binds request data into the DTO, `@Valid` triggers validation, and `BindingResult` captures errors.
4. If there are errors, `return "hello-form"` renders within the current request to keep error details and input.
5. If valid, `addFlashAttribute` holds a one-time message for the target request; `redirect:/done` generates an HTTP redirect.
6. `done` returns the template, and the framework places the flash message into the target request's Model.
7. `ping` returns a text body because of `@ResponseBody`, without looking up `ping.html`.

You do not need to define a separate `ViewResolver` bean when the Thymeleaf starter and Boot auto-configuration already configure it properly.

### 8.5. index.html

File `src/main/resources/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Home</title>
</head>
<body>
    <h1 th:text="|Hello, ${name}!|">Hello!</h1>
    <h2>Three Core Components</h2>
    <ul>
        <li th:each="topic : ${topics}"
            th:text="${topic}">Topic</li>
    </ul>
    <a th:href="@{/hello-form}">Open form</a>
</body>
</html>
```

`th:text` reads data from the Model and escapes text; `th:each` iterates over `topics`. The inline text in HTML serves as a fallback when opening the static file; during server rendering, Thymeleaf expressions determine the output content.

### 8.6. hello-form.html

File `src/main/resources/templates/hello-form.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Greeting Form</title>
</head>
<body>
    <h1>Enter a Name</h1>

    <form method="post"
          th:action="@{/hello-form}"
          th:object="${greetingForm}">

        <label for="name">Name</label>
        <input id="name" type="text"
               th:field="*{name}" maxlength="60">

        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}">Error message</p>

        <button type="submit">Submit</button>
    </form>

    <a th:href="@{/}">Home</a>
</body>
</html>
```

`th:object="${greetingForm}"` matches the Model attribute and `@ModelAttribute("greetingForm")`. `th:field="*{name}"` binds the input to the form DTO property, preserving the user's input when validation fails. `th:errors` displays messages from Jakarta Validation. If you add Spring Security and CSRF protection, the POST form must include a valid token according to the project's Spring MVC/Thymeleaf configuration; this minimal example does not add the security starter.

### 8.7. done.html

File `src/main/resources/templates/done.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Done</title>
</head>
<body>
    <h1>Form Submitted</h1>

    <p th:if="${successMessage != null}"
       th:text="${successMessage}">Submitted successfully</p>

    <p th:unless="${successMessage != null}">
        No new message. Please submit the form.
    </p>

    <a th:href="@{/hello-form}">Back to form</a>
</body>
</html>
```

When visiting `/done` after a successful redirect, the Model contains the `successMessage` flash attribute; if accessed directly without flash data, the fallback paragraph appears. Flash attributes must not be used as a long-term store for records or transactional data.

## 9. Running and Verifying over HTTP

In the project root directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The application defaults to port 8080 if `server.port` is unchanged. With Spring dependencies, running `javac PageController.java` alone without a classpath will not compile; use the Gradle Wrapper to download dependencies, compile, and run.

### 9.1. GET Page

```bash
curl -s 'http://localhost:8080/?name=Mai'
```

In the HTML response, the body content may look like:

```html
<h1>Hello, Mai!</h1>
<ul>
    <li>Controller</li>
    <li>Model</li>
    <li>View</li>
</ul>
```

This is an **illustrative rendered fragment**; the full response includes the HTML head/body and whitespace according to the template.

### 9.2. POST with Invalid Data

```bash
curl -i -d 'name=' http://localhost:8080/hello-form
```

`@NotBlank` triggers an error; the handler returns the `hello-form` view in the same request, typically with default HTTP 200; the HTML contains `Please enter a name`. You can design a different status per application requirements, but you should not redirect when you need to preserve `BindingResult` errors in the same request.

### 9.3. Valid POST, Followed by Redirect

```bash
curl -i -d 'name=Lan' http://localhost:8080/hello-form
```

The response is typically HTTP `302 Found` with `Location: /done` (or the equivalent URL under the context path). The browser then sends a GET to `/done`. Use `curl` with a cookie jar to follow the redirect and retain flash attributes:

```bash
curl -s -L -c cookies.txt -b cookies.txt \
  -d 'name=Lan' http://localhost:8080/hello-form
```

The target page HTML contains `Sent greeting to Lan`. PowerShell can invoke `curl.exe` and pass arguments on a single line. The demo app **does not write to a database**; submitting only demonstrates the web flow.

### 9.4. Direct Text via @ResponseBody

```bash
curl -s http://localhost:8080/ping
```

Exact response body:

```text
pong
```

No `pong.html` template needs to be created.

## 10. Redirect, Forward, and PRG

- `return "hello-form"`: renders the view in the current request, preserving validation errors and the Model.
- `return "redirect:/done"`: responds with a 3xx redirect; the browser performs a new request, and the previous request's Model does not automatically remain intact.
- `return "forward:/internal"`: transfers processing internally on the server to another URL/handler; the browser typically keeps the original URL, with no redirect round-trip.

**Post/Redirect/Get (PRG)** is suitable when a POST has succeeded and you want to avoid the browser prompting to resubmit the form on refresh. PRG reduces the risk of accidental POST resubmission on refresh; it does **not** replace an idempotency key, transactions, or duplicate-submission protection for payments and side-effecting operations.

### 10.1. RedirectAttributes and Flash

```java
redirectAttributes.addAttribute("id", 42);
// The attribute may be appended to the redirect URL as a query parameter.

redirectAttributes.addFlashAttribute("notice", "Saved");
// Short notice for the next request after the redirect.
```

This is a **snippet** inside a handler that has a `RedirectAttributes redirectAttributes` parameter. Do not put sensitive information in the URL; flash attributes are typically managed in the session and are intended only for short-lived data transfer, not storing large objects. When a detail page is needed, redirect with a valid ID and fetch the data again from a service/repository.

### 10.2. Regular Model Is Not Flash

Counterexample when you want a message to appear only in the target redirected request:

```java
model.addAttribute("message", "Saved");
return "redirect:/done"; // Do not rely on regular Model for flash data
```

Some scalar model attributes may be converted into query parameters depending on redirect configuration; do not assume the entire Model is carried over to the new request. Use `RedirectAttributes` explicitly.

## 11. Common Form and Template Mistakes

### 11.1. Mismatched Model Key and Form Name

If the controller calls `model.addAttribute("userForm", new UserForm())`, then the template must use `th:object="${userForm}"`, not `${profileForm}`. In the POST handler, `@ModelAttribute("userForm")` must use the same name. A mismatched name can prevent form fields from binding or cause the view to report a missing form-backing object.

### 11.2. Misplaced BindingResult

The `BindingResult` parameter for a form object must be placed immediately after that object:

```java
public String submit(
        @Valid @ModelAttribute("userForm") UserForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "users/form";
    }
    return "redirect:/users";
}
```

This is a **snippet** (without full mapping, class, and DTO). If `@Valid` or the validation provider is missing, annotations like `@NotBlank` may not run. If `BindingResult` is placed in the wrong position, a validation exception may be thrown instead of the controller handling the errors.

### 11.3. Directly Binding Sensitive Entities

Do not directly bind an entity containing `isAdmin`, `role`, `price`, or properties that users must not modify from a form. Clients can submit extra parameters beyond the visible HTML inputs (*mass assignment*). Use a DTO containing only allowed fields, validate it, and map it into the domain model inside a service. Hiding inputs on the frontend is not access control.

### 11.4. Using Mutable State on a Singleton Controller

Counterexample:

```java
private String currentName;

@GetMapping("/hello")
public String hello(@RequestParam String name) {
    currentName = name; // One request can overwrite another request
    return "hello";
}
```

The snippet above lacks a `Model` and stores the name in a shared field. Controllers are usually singletons, so race conditions or cross-user data leaks can occur. Keep per-request data in local variables or `Model`, and use a dedicated mechanism for any state that must persist longer.

### 11.5. Taking View Names Directly from Untrusted Input

```java
@GetMapping("/preview")
public String preview(@RequestParam String template) {
    return template; // No allowlist
}
```

This is an **anti-pattern**: users must not arbitrarily choose views or special prefixes like `redirect:`/`forward:`. Map user choices to a list of valid views and enforce authorization checks.

## 12. Security and Performance When Rendering UI

**XSS:** use `th:text` to escape text, and do not pass user-supplied content into `th:utext` without sanitization. For values placed into URLs, JavaScript, or HTML attributes, use context-appropriate safe expressions rather than concatenating HTML strings in the controller.

**CSRF:** when an app uses cookie/session authentication, state-changing POST forms require proper CSRF protection. Spring Security integration must ensure the token is present and valid on form submission. Do not treat a minimal demo with security disabled as a complete production configuration.

**Authorization:** hiding a button in a template does not prevent a user from sending a direct request. Controllers and services must still enforce access and modification permissions.

**Pass only the data needed for rendering:** querying large lists and putting everything into the Model consumes memory and slows down rendering. Use view DTOs, pagination, cache reference data, and avoid calling repositories or running heavy business logic directly in templates.

**Template caching:** in development you can use:

```properties
spring.thymeleaf.cache=false
```

In production, consider keeping caching enabled to avoid repeated template parsing. Do not log secrets or entire sensitive Models just to debug a view.

**Context-path-aware URLs:** use `th:href="@{/...}"` and `th:action="@{/...}"` so Spring/Thymeleaf generates links matching the application deployment. Hardcoded paths can break when deployed under a different context path.

## 13. Quick Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Browser displays literal text `index` | Handler has `@ResponseBody`/`@RestController` | Use `@Controller` when returning a logical view |
| 404 | No matching mapping | Check `@GetMapping`, HTTP method, context path |
| Template not found | Wrong view name, file, or missing starter | Check `templates` and the Thymeleaf resolver |
| HTML missing data | Model key differs from expression | Compare `addAttribute` and `${...}` |
| Form shows template error | Missing `greetingForm` object | Initialize the form and match `th:object` |
| Validation reports no errors | Missing `@Valid`/starter/`BindingResult` | Check dependencies and handler signature |
| Errors disappear after redirect | Request Model/BindingResult is gone | Re-render the form when invalid |
| Refresh prompts to resend POST | Returning a view directly after valid submit | Use PRG: redirect to a GET |
| Flash not visible with curl | Not following redirect/cookies | Use `curl -L -c -b` |
| XSS | Rendering untrusted raw HTML | Use escaping and validate context |
| Page slow with many records | Query/Model/template too heavy | Pagination and view DTOs |
| Same data appears across users | Mutable controller field | Keep per-request data local or in Model |

To distinguish errors, inspect `curl -i` or the Browser Network tab: status 404 relates to routing, HTTP 3xx has a `Location` header, and template exceptions occur after the handler returns a view name. Follow Spring MVC and Thymeleaf logs at the exact failure point.

## 14. Self-Check Exercises

**1.** A `@Controller` returns `"orders/list"`. Which template does Thymeleaf look for by default?  
**Answer:** `src/main/resources/templates/orders/list.html`; the URL is determined by the request mapping.

**2.** If a `@RestController` returns `"home"`, will HTML be rendered?  
**Answer:** No, the response body will normally be the text `home`.

**3.** The Model key is `items` but the template uses `${products}`. Will they connect automatically?  
**Answer:** No. The key and expression must match.

**4.** A user submits an empty form, and the DTO has `@NotBlank`. What is required to show the error?  
**Answer:** `@Valid @ModelAttribute`, `BindingResult` immediately after it, the `hasErrors()` branch returning the form, and `th:errors` in the template.

**5.** Why does a valid POST usually return `redirect:`?  
**Answer:** To perform a GET after POST (PRG) so refreshing does not unintentionally resubmit the POST.

**6.** Is `Model.addAttribute("notice","OK")` followed by a redirect guaranteed to behave as a flash attribute?  
**Answer:** No; use `RedirectAttributes.addFlashAttribute` for messages that must appear in the target redirected request.

**7.** Why shouldn't you bind a `User` entity containing `isAdmin` directly from a form?  
**Answer:** It is vulnerable to mass assignment; use a form DTO restricting allowed fields and enforce authorization in the service.

**8.** Why is `th:text` safer than `th:utext` for usernames?  
**Answer:** `th:text` escapes HTML, preventing untrusted data from becoming executable HTML tags.

## 15. Implementation Checklist

- [ ] Choose `@Controller` for SSR, `@ResponseBody`/`@RestController` for direct response bodies.
- [ ] Define URL mappings and logical view names intentionally, rather than inferring them from filenames.
- [ ] Place templates in the right folder matching the engine's prefix/suffix.
- [ ] Match Model keys with Thymeleaf expressions.
- [ ] Include only data needed for rendering in the Model, never secrets or huge collections.
- [ ] Use a DTO with only bindable fields, getters/setters, and server-side validation for forms.
- [ ] Place `BindingResult` immediately after `@Valid @ModelAttribute`.
- [ ] Return the form view on the error branch to preserve field errors.
- [ ] Use PRG and flash attributes on successful submission when appropriate.
- [ ] Never use singleton controller fields to store per-request state.
- [ ] Escape user output according to context, and enforce CSRF and access control.
- [ ] Test HTML GET, invalid POST, valid POST, redirect, flash, and `@ResponseBody` responses.

## Official Documentation

- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Boot 3.3 — Servlet Web Applications & Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Thymeleaf — Tutorial: Thymeleaf + Spring](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)

For server-rendered HTML pages, keep the contract clear: **`@Controller` receives the request and decides navigation, `Model` carries data for the render pass, and the view name identifies the template for `ViewResolver` to locate and generate HTML**. Keeping these three roles distinct speeds up debugging, improves testability, and prevents confusing SSR with REST APIs.
