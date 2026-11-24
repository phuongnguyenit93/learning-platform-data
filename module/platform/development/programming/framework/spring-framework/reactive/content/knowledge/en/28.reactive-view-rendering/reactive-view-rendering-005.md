# Redirects and Form Data in Spring WebFlux

**Module:** Spring Framework – reactive  
**Parent topic:** View Rendering

## Learning Objectives

After this lesson, you can:

1. Distinguish HTTP redirects from view rendering and internal forwarding.
2. Choose status 301, 302, 303, 307, or 308 according to purpose and method semantics.
3. Design Post/Redirect/Get (PRG) after form processing.
4. Use redirects in annotated controllers via the `redirect:` view name prefix or `Rendering.redirectTo`.
5. Create redirects in WebFlux functional endpoints using `ServerResponse`.
6. Receive `application/x-www-form-urlencoded` with `@RequestParam`, `@ModelAttribute`, `ServerRequest.formData()`, or `ServerRequest.bind()`.
7. Bind data into a form object, validate with Bean Validation, and handle errors via `BindingResult`.
8. Restrict allowed bind fields, prevent over-posting, and protect redirects against open redirects.
9. Build a Spring Boot application with a form, result page, 303 redirect, and integration tests using `WebTestClient`.

## 1. What Is a Redirect?

An HTTP redirect is a response instructing the client to send another request to the URI specified in the `Location` header. The server does not jump to another controller within the same request. The browser receives a 3xx response, reads Location, and issues a follow-up request according to the status semantics.

```http
HTTP/1.1 303 See Other
Location: /registrations/42
Content-Length: 0
```

The browser sends a GET request to `/registrations/42`; the server handles the new GET and returns the result page.

A redirect differs from:

- **View rendering:** the server picks a template and generates HTML for the current request.
- **Redirect:** the server returns 3xx and Location; the client issues a new request.
- **Internal forward:** handing the request to another server-side handler. WebFlux does not support Servlet-style FORWARD dispatches or the `forward:` prefix.
- **Proxy/gateway rewrite:** the proxy changes the URI before the request reaches the application; this is not a redirect response visible to the browser.

Redirects are commonly used after form submission, when a resource URL changes, or when guiding the user to another page.

### 1.1. Components of a Redirect Response

A redirect response typically includes a 3xx status and a Location header. The response body may contain descriptive content, though browsers rely on Location to navigate. Without Location, the client has no clear redirect target.

For internal redirects, use application-relative paths such as `/registrations/42`. For absolute URLs, validate the destination host before redirecting.

## 2. Important Redirect Status Codes

Do not treat all 3xx status codes as interchangeable. The main differences are whether the redirect is temporary or permanent and whether the follow-up request preserves the method and body.

| Status | Meaning | Follow-up Request Method | Common Use Case |
| --- | --- | --- | --- |
| **301 Moved Permanently** | Resource moved permanently | Browsers may change POST to GET due to historical compatibility behavior | Permanent URL changes, usually for GET. |
| **302 Found** | Temporary redirect | Common clients often change POST to GET; historical semantics are less explicit than 303 | Temporary redirect. |
| **303 See Other** | View result at another URI | Client performs GET (or HEAD if original request was HEAD) | PRG after form POST. |
| **307 Temporary Redirect** | Temporary redirect | Preserves original method and body | Temporary redirection where POST/PUT/PATCH must be kept. |
| **308 Permanent Redirect** | Permanent redirect | Preserves original method and body | Long-term API/resource move requiring method preservation. |

Two rules:

- Use **303 See Other** after POST when you want the browser to load the result page with GET.
- Use **307 or 308** when the server wants the client to resend the same method and body to the new URI.

301 and 308 are permanent redirects; clients or proxies may cache the decision. Do not use them for temporary changes. 302 carries legacy browser compatibility behavior; for PRG, 303 expresses intent more clearly.

**304 Not Modified** is not a navigation redirect. It is a cache validation response indicating the client can reuse its cached representation.

## 3. Post/Redirect/Get (PRG)

PRG is a three-step form-handling pattern:

```text
Browser                      WebFlux server
    |                              |
    | GET /registrations/new       |
    |----------------------------->|
    |<-----------------------------| 200 OK + form HTML
    |                              |
    | POST /registrations          |
    | form-urlencoded              |
    |----------------------------->| Validate and save
    |<-----------------------------|
    | 303 See Other                |
    | Location: /registrations/42  |
    |                              |
    | GET /registrations/42        |
    |----------------------------->|
    |<-----------------------------| 200 OK + result page
```

If the server returns HTML directly after POST, refreshing the page can resubmit the POST. With 303, the next request is GET; refreshing the result page simply reloads GET and avoids the form-resubmission prompt in normal flows.

PRG does not replace business-level duplicate protection. A user can double-click before receiving the redirect, the network can retry, or a client can resend POST. For payments, order creation, or operations with significant side effects, you still need idempotency keys, unique constraints, or duplicate-processing guards.

### 3.1. When Is a Redirect Not Needed?

- APIs called from JavaScript can return JSON with status 201 Created and Location.
- Background-processing endpoints can return 202 Accepted with a job-tracking URI.
- Forms with validation errors should re-render the form page showing the errors and submitted values.
- Operations that do not create a new resource can return a direct response if required by the contract.

PRG is especially useful for traditional HTML forms submitted and navigated by a browser.

## 4. Redirects in WebFlux Annotated Controllers

WebFlux supports redirects through view resolution.

### 4.1. View Names with the redirect: Prefix

```java
@Controller
public class HomeController {

    @GetMapping("/legacy-home")
    public String legacyHome() {
        return "redirect:/dashboard";
    }
}
```

`UrlBasedViewResolver` recognizes the `redirect:` prefix and creates a redirect view. The remainder is the target URL. The path `/dashboard` is resolved relative to the application.

In WebFlux, `RedirectView` defaults to status `303 See Other`. Another status can be configured when needed. Do not use `forward:` in WebFlux because there is no FORWARD dispatch.

This approach is concise when only a fixed URL is needed. If you need to configure status or model attributes, use `Rendering`.

### 4.2. Using Rendering.redirectTo

`Rendering` is the view-rendering return API in WebFlux. `Rendering.redirectTo` creates a redirect via `RedirectView`:

```java
@GetMapping("/old-dashboard")
public Rendering redirectDashboard() {
    return Rendering.redirectTo("/dashboard")
            .status(HttpStatus.SEE_OTHER)
            .build();
}
```

`status` sets the status explicitly. For PRG, use `HttpStatus.SEE_OTHER` to indicate that the next request must be GET.

You can use URI templates and model attributes:

```java
return Rendering.redirectTo("/registrations/{id}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("id", registration.getId())
        .build();
```

Only include data needed for the target URL in the redirect model. Avoid adding the entire form object or sensitive data because a redirect view can use model attributes as URI template variables or request parameters.

### 4.3. Using ResponseEntity When Not Rendering Views

A REST controller can return a redirect response directly:

```java
@PostMapping("/api/complete")
public Mono<ResponseEntity<Void>> complete() {
    URI location = URI.create("/api/results/42");

    return Mono.just(
            ResponseEntity.status(HttpStatus.SEE_OTHER)
                    .location(location)
                    .build());
}
```

This fits when the controller returns an HTTP response rather than a view name. For APIs consumed by JavaScript apps, consider returning JSON and letting the client handle navigation; a redirect from fetch does not necessarily navigate the entire browser window.

## 5. Redirects in WebFlux Functional Endpoints

WebFlux.fn uses `RouterFunction`, `HandlerFunction`, `ServerRequest`, and `ServerResponse`. Handlers return `Mono<ServerResponse>`.

```java
public Mono<ServerResponse> redirectToResult(ServerRequest request) {
    URI location = URI.create("/results/42");

    return ServerResponse.status(HttpStatus.SEE_OTHER)
            .location(location)
            .build();
}
```

`ServerResponse.status(...).location(...).build()` creates a 303 response with a Location header.

A route wiring the handler:

```java
@Bean
RouterFunction<ServerResponse> routes(ResultHandler handler) {
    return RouterFunctions.route()
            .GET("/old-result", handler::redirectToResult)
            .build();
}
```

This is an illustrative snippet. In a real application, the target URI should be constructed from a saved resource ID or an appropriate URI builder, never by concatenating arbitrary client-supplied URLs.

## 6. How Is Form Data Submitted?

HTML forms can submit using different encodings. Two common formats are URL-encoded and multipart.

| Encoding | Content-Type | How It Works | When Used |
| --- | --- | --- | --- |
| URL-encoded | `application/x-www-form-urlencoded` | Key/value pairs encoded in the request body | Forms with text, numbers, checkboxes, selects. |
| Multipart | `multipart/form-data; boundary=...` | Body consists of multiple parts, each with its own headers | Forms with file uploads or parts of different content types. |

Example URL-encoded form:

```html
<form method="post" action="/registrations">
    <input name="name" value="Lan">
    <input name="email" value="lan@example.com">
    <select name="category">
        <option value="spring">Spring</option>
    </select>
    <button type="submit">Submit</button>
</form>
```

The transmitted body looks roughly like:

```text
name=Lan&email=lan%40example.com&category=spring
```

HTML field names must match the property or parameter names expected by the controller. If the form uses `name="email"` while the DTO only has a `mail` property, Spring will not automatically treat those two names as equivalent without configured mapping.

### 6.1. URL-Encoded Forms and JSON Requests Are Different

`@ModelAttribute` is for form/query parameter binding; it is not a JSON decoder.

- HTML forms default to sending `application/x-www-form-urlencoded`.
- JavaScript sending JSON typically sets `Content-Type: application/json` and uses `@RequestBody`.
- Forms with files usually use `multipart/form-data`, receiving files via `@RequestPart` or `FilePart`.

Do not send a JSON body and expect `@ModelAttribute` to bind it like a URL-encoded form. Choose the annotation matching the Content-Type and request contract.

### 6.2. A Field with Multiple Values

A checkbox group or multi-select can send the same key multiple times:

```text
tag=java&tag=spring&tag=reactive
```

Spring can bind multiple values into a `List<String>`, an array, or a `MultiValueMap`. If only a single String variable is used, the application receives only one value according to resolver/conversion rules. Declare the data type matching the form.

## 7. Receiving Forms with @RequestParam

When there are only a few simple fields, `@RequestParam` is easy to read:

```java
@PostMapping(
        value = "/search",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<String> search(
        @RequestParam("keyword") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {

    return Mono.just("keyword=" + keyword + ", page=" + page);
}
```

`@RequestParam` retrieves values by parameter name. You can declare `required=false`, `defaultValue`, or a non-String target type for Spring to convert.

Use `@RequestParam` when the method only needs a few standalone fields, does not need an object representing the entire form, and wants to make required or defaulted parameters explicit. If a form has multiple related fields, group them into a form DTO for easier validation and management.

## 8. Receiving Forms with @ModelAttribute

`@ModelAttribute` binds form data and query parameters into an object. Spring performs type conversion, constructor binding, or property binding depending on the class design.

```java
public class SearchForm {
    private String keyword;
    private int page = 1;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}

@PostMapping(
        value = "/search",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<String> search(@ModelAttribute SearchForm form) {
    return Mono.just(
            "keyword=" + form.getKeyword()
                    + ", page=" + form.getPage());
}
```

The field names keyword and page bind to properties with the same names. page is converted from a string to int; if the value is invalid, Spring produces a binding error.

In WebFlux, `@ModelAttribute` can be declared directly or wrapped in a reactive type such as `Mono<SearchForm>`. When using a reactive wrapper, handle validation errors in the reactive chain. If you want to receive `BindingResult` directly, declare the model object without a reactive wrapper and place BindingResult immediately after it.

### 8.1. Initializing Data for Forms

When rendering the GET form, the controller adds the form object and choice lists to the model:

```java
@GetMapping("/search")
public String showSearchForm(Model model) {
    model.addAttribute("searchForm", new SearchForm());
    model.addAttribute("categories", List.of("java", "spring", "reactive"));
    return "search-form";
}
```

You can use a `@ModelAttribute` method to add shared data for views:

```java
@ModelAttribute("categories")
public List<String> categories() {
    return List.of("java", "spring", "reactive");
}
```

These attributes help templates render selects, checkboxes, or other supporting data. When re-rendering a form due to validation failure, you must supply the choice lists again.

### 8.2. Binding Numbers, Dates, and Enums

Spring uses its conversion service to convert strings to Java types:

- page=3 can bind to int.
- active=true can bind to boolean.
- category=SPRING can bind to enum `Category.SPRING`.
- Dates require a format matching the target type and binder configuration.

If date formats are not uniform, declare an explicit format or formatter. Do not assume the browser sends dates using the server's locale.

## 9. Validation and BindingResult

Form data is untrusted input. It must be validated before saving or running business logic.

```java
public class RegistrationForm {
    @NotBlank(message = "Name is required")
    @Size(max = 80, message = "Name must be at most 80 characters")
    private String name;

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    private String email;

    @NotBlank(message = "Please select a category")
    private String category;

    // getters and setters
}
```

The controller uses `@Valid` and `BindingResult`:

```java
@PostMapping("/registrations")
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }

    // Save data after validation succeeds.
    return "redirect:/registrations";
}
```

`BindingResult` must immediately follow the validated argument. When errors exist, the controller returns the form view so the template displays messages. When BindingResult is omitted, binding/validation errors are typically represented by `WebExchangeBindException`.

With WebFlux, you can validate a `Mono<RegistrationForm>` using `@Valid` and handle errors with `onErrorResume`. Distinguish validation errors from infrastructure or business errors; do not turn every exception into an invalid-form message.

### 9.1. Displaying Errors in Thymeleaf

```html
<form th:action="@{/registrations}"
      th:object="${registrationForm}"
      method="post">
    <label for="name">Full name</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}"></p>

    <label for="email">Email</label>
    <input id="email" type="email" th:field="*{email}">
    <p th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}"></p>

    <button type="submit">Submit</button>
</form>
```

`th:field` connects the input to the form object's property and helps repopulate entered values. `th:errors` displays validation errors for that field. Use a template engine with default escaping; do not concatenate input into HTML strings manually.

## 10. Protecting Data Binding

If you bind directly to a large entity, the client can send extra properties not shown in the form, such as role, enabled, ownerId, or approved.

Security principles:

1. Create a dedicated form DTO containing only fields the user is allowed to submit.
2. Do not bind directly to JPA/domain entities with many sensitive attributes.
3. With property binding, use `@InitBinder` and `setAllowedFields` to restrict fields.
4. Do not trust hidden inputs; users can modify them in DevTools or send crafted requests.
5. Check resource permissions based on the current identity; do not rely on a client-supplied ownerId.
6. Validate syntax and business rules on the server.
7. Do not place passwords, tokens, private emails, or sensitive data in query strings.

Example restricting fields:

```java
@InitBinder("registrationForm")
void limitRegistrationFields(WebDataBinder binder) {
    binder.setAllowedFields("name", "email", "category");
}
```

If a client also sends `admin=true`, the binder will not assign that field on the form object. This is an additional defense layer; access control and business checks must still be enforced in the service/security layer.

With Spring Security, state-changing forms require CSRF protection. Thymeleaf integration can inject the CSRF token according to the Security configuration. Do not disable CSRF just to make browser POSTs work.

## 11. Receiving Forms in Functional Endpoints

In WebFlux.fn, `ServerRequest.formData()` returns `Mono<MultiValueMap<String, String>>`:

```java
public Mono<ServerResponse> submit(ServerRequest request) {
    return request.formData()
            .flatMap(form -> {
                String name = form.getFirst("name");
                String email = form.getFirst("email");

                if (name == null || name.isBlank()) {
                    return ServerResponse.badRequest()
                            .bodyValue("Name is required");
                }

                return registrationService.save(name, email)
                        .flatMap(saved -> ServerResponse
                                .status(HttpStatus.SEE_OTHER)
                                .location(URI.create(
                                        "/registrations/" + saved.getId()))
                                .build());
            });
}
```

`formData()` is suitable for URL-encoded forms. The result is a MultiValueMap because a key can have multiple values. The handler validates data and returns errors before calling the service.

Registering the handler via a router:

```java
@Bean
RouterFunction<ServerResponse> registrationRoutes(
        RegistrationHandler handler) {

    return RouterFunctions.route()
            .POST("/fn/registrations",
                    contentType(MediaType.APPLICATION_FORM_URLENCODED),
                    handler::submit)
            .build();
}
```

For form objects, `ServerRequest.bind()` supports binding request parameters, URI variables, and headers; you can configure the `DataBinder` to restrict fields:

```java
Mono<RegistrationForm> form = request.bind(
        RegistrationForm.class,
        binder -> binder.setAllowedFields(
                "name", "email", "category"));
```

For large multipart uploads, consider streaming `PartEvent` instead of buffering files in memory. `DataBuffer` contents must be consumed, forwarded, or released according to their lifecycle to avoid memory leaks.

## 12. Passing Data After a Redirect

A redirect needs a target URL. There are three common ways for the target page to know which resource to display.

### 12.1. URI Template Variables

```java
return Rendering.redirectTo("/registrations/{id}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("id", registration.getId())
        .build();
```

Suitable for the detail page of a saved resource. The URL carries the ID; the GET page loads data from the repository/service.

### 12.2. Query Parameters

```java
return Rendering.redirectTo("/search?category={category}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("category", "spring")
        .build();
```

Query parameters fit non-sensitive filters or search state. Values must be properly URI-encoded. Never put secrets into a query string because URLs can appear in browser history, access logs, analytics, or the Referer header.

### 12.3. Session or Server-Side State

If you need a one-time notice or data that should not appear in the URL, you can store state on the server/session and redirect with a short reference key. Manage session expiration, access control, and concurrency.

Do not confuse Spring MVC's redirect/flash APIs with WebFlux. `RedirectAttributes` belongs to the Servlet MVC package; in WebFlux, use `Rendering`, `RedirectView`, model URI variables, or application-managed state storage.

## 13. Redirect Security

A redirect URL can be abused to send users to a phishing site if the server accepts arbitrary client-supplied URLs.

Dangerous example:

```java
@GetMapping("/login/success")
public Rendering success(@RequestParam String next) {
    return Rendering.redirectTo(next).build();
}
```

If next is `https://attacker.example`, the server navigates the user off the website. This is an open redirect vulnerability.

Mitigation:

- Prefer fixed internal routes or server-generated URI templates.
- If a returnUrl is needed, allow only validated internal relative paths.
- If redirecting to an external host is required, use an exact domain allow-list and verify the scheme.
- Do not merely check that the string starts with `https://trusted.example`; parse the URI and compare the normalized host to prevent `trusted.example.attacker.test`.
- Block dangerous schemes such as `javascript:` and protocol-relative URLs like `//attacker.example`.
- Do not place access tokens, passwords, session IDs, or personal data in Location.

Redirects after login/logout should coordinate with Spring Security. Never trust a redirect URL from a query parameter just because the request is authenticated.

## 14. Runnable Spring Boot 3.3.5 Application

This example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, Spring WebFlux, Thymeleaf, and Bean Validation. The app displays a registration form, binds data, validates it, saves to an in-memory store, and returns 303 on success. The result page is loaded with GET.

Project structure:

```text
webflux-form-prg/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── FormPrgApplication.java
    │   ├── RegistrationForm.java
    │   ├── Registration.java
    │   ├── RegistrationStore.java
    │   └── RegistrationController.java
    ├── main/resources/templates/
    │   ├── registration-form.html
    │   └── registration-detail.html
    └── test/java/demo/
        └── RegistrationControllerTest.java
```

### 14.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-form-prg</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 14.2. FormPrgApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormPrgApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormPrgApplication.class, args);
    }
}
```

### 14.3. RegistrationForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationForm {

    @NotBlank(message = "Name is required")
    @Size(max = 80, message = "Name must be at most 80 characters")
    private String name;

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    @Size(max = 160, message = "Email must be at most 160 characters")
    private String email;

    @NotBlank(message = "Please select a category")
    private String category;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }
}
```

### 14.4. Registration.java

```java
package demo;

public class Registration {
    private final long id;
    private final String name;
    private final String email;
    private final String category;

    public Registration(long id, String name, String email, String category) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.category = category;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getCategory() {
        return category;
    }
}
```

### 14.5. RegistrationStore.java

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RegistrationStore {
    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Registration> registrations =
            new ConcurrentHashMap<>();

    public Mono<Registration> save(RegistrationForm form) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();

            Registration registration = new Registration(
                    id,
                    form.getName().trim(),
                    form.getEmail().trim(),
                    form.getCategory());

            registrations.put(id, registration);
            return registration;
        });
    }

    public Mono<Registration> findById(long id) {
        return Mono.justOrEmpty(registrations.get(id));
    }
}
```

The store uses an in-memory map so the example runs standalone. When the application restarts, data is lost. Real systems replace this store with a reactive repository/database; do not call blocking JDBC directly on the event loop.

### 14.6. RegistrationController.java

```java
package demo;

import java.util.List;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    private static final List<String> CATEGORIES =
            List.of("java", "spring", "reactive");

    private final RegistrationStore store;

    public RegistrationController(RegistrationStore store) {
        this.store = store;
    }

    @InitBinder("registrationForm")
    void limitRegistrationFields(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "category");
    }

    @GetMapping("/new")
    public Rendering newForm() {
        return Rendering.view("registration-form")
                .modelAttribute("registrationForm", new RegistrationForm())
                .modelAttribute("categories", CATEGORIES)
                .build();
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<Rendering> submit(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(
                    Rendering.view("registration-form")
                            .modelAttribute("registrationForm", form)
                            .modelAttribute(
                                    BindingResult.MODEL_KEY_PREFIX
                                            + "registrationForm",
                                    errors)
                            .modelAttribute("categories", CATEGORIES)
                            .build());
        }

        return store.save(form)
                .map(saved -> Rendering
                        .redirectTo("/registrations/{id}")
                        .status(HttpStatus.SEE_OTHER)
                        .modelAttribute("id", saved.getId())
                        .build());
    }

    @GetMapping("/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return store.findById(id)
                .map(registration -> Rendering
                        .view("registration-detail")
                        .modelAttribute("registration", registration)
                        .build())
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
```

`BindingResult` immediately follows the form argument so the controller can handle validation errors itself. On error, the controller re-renders the view and puts the form object, binding result, and category list into the model. When valid, the store saves the data and redirects with 303 to the detail URL. There are no blocking operations in the controller.

### 14.7. registration-form.html

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Registration</title>
</head>
<body>
<h1>Registration</h1>

<form th:action="@{/registrations}"
      th:object="${registrationForm}"
      method="post">

    <div>
        <label for="name">Full name</label>
        <input id="name" type="text" th:field="*{name}">
        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}"></p>
    </div>

    <div>
        <label for="email">Email</label>
        <input id="email" type="email" th:field="*{email}">
        <p th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="category">Category</label>
        <select id="category" th:field="*{category}">
            <option value="">-- Select category --</option>
            <option th:each="category : ${categories}"
                    th:value="${category}"
                    th:text="${category}"></option>
        </select>
        <p th:if="${#fields.hasErrors('category')}"
           th:errors="*{category}"></p>
    </div>

    <button type="submit">Submit registration</button>
</form>
</body>
</html>
```

### 14.8. registration-detail.html

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Registration successful</title>
</head>
<body>
<h1>Registration saved</h1>
<p>Registration ID: <span th:text="${registration.id}"></span></p>
<p>Full name: <span th:text="${registration.name}"></span></p>
<p>Email: <span th:text="${registration.email}"></span></p>
<p>Category: <span th:text="${registration.category}"></span></p>
<a th:href="@{/registrations/new}">Create another registration</a>
</body>
</html>
```

### 14.9. RegistrationControllerTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RegistrationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void displaysRegistrationForm() {
        client.get()
                .uri("/registrations/new")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("name=\"name\"");
                    assertThat(html).contains("name=\"email\"");
                    assertThat(html).contains("name=\"category\"");
                });
    }

    @Test
    void invalidFormIsRenderedAgainWithErrors() {
        client.post()
                .uri("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("email", "not-an-email")
                        .with("category", ""))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("Name is required");
                    assertThat(html).contains("Email format is invalid");
                    assertThat(html).contains("Please select a category");
                });
    }

    @Test
    void validPostRedirectsWith303AndTheGetLoadsTheSavedRecord() {
        EntityExchangeResult<Void> result = client.post()
                .uri("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("email", "lan@example.com")
                        .with("category", "reactive"))
                .exchange()
                .expectStatus().isSeeOther()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .returnResult(Void.class);

        String location =
                result.getResponseHeaders().getFirst(HttpHeaders.LOCATION);

        assertThat(location).isNotBlank();

        client.get()
                .uri(location)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("Registration saved");
                    assertThat(html).contains("Lan");
                    assertThat(html).contains("lan@example.com");
                });
    }
}
```

The first test verifies that the form renders. The second test sends invalid data and verifies that the form page re-renders with all three errors. The third test sends a valid form, verifies the 303 response with Location, and then explicitly requests GET on that URL to verify the detail page displays the saved data.

### 14.10. Running the Application and Testing with curl

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Open the form in a browser:

```text
http://localhost:8080/registrations/new
```

Submit a valid form from the terminal:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "category=reactive"
```

The response looks like:

```http
HTTP/1.1 303 See Other
Location: /registrations/1
```

The exact ID depends on the number of saves in the current process. Use the URL from Location to request the result page:

```bash
curl -i http://localhost:8080/registrations/1
```

The GET response returns 200 OK and HTML containing the registration details. When running tests:

```bash
mvn test
```

Three integration tests verify the form page, validation errors, and the POST → 303 → GET flow. The application uses an in-memory store, so data persists only until the process stops.

## 15. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Returning HTML directly after POST when intending PRG | Refresh can resubmit POST | Return 303 and direct the user to GET. |
| Using 307/308 for PRG | Browser resends POST/body to new URL | Use 303 if the follow-up request should be GET. |
| Using 301/308 for a temporary URL change | Clients/proxies may cache redirect long term | Choose an appropriate temporary status. |
| Treating 302 and 303 as identical | Method handling is not expressed explicitly | Use 303 to explicitly switch to GET after POST. |
| Thinking redirect is an internal forward | Expecting server to invoke second controller in same request | Redirect returns 3xx and client sends a new request. |
| Using forward: in WebFlux | No corresponding Servlet FORWARD dispatch exists | Use view rendering or redirect with proper semantics. |
| Using @RequestBody for URL-encoded forms as if JSON | Codec does not bind as expected | Use @ModelAttribute, @RequestParam, or ServerRequest.formData(). |
| Binding entity directly to a form | Client can submit extra sensitive properties | Use a dedicated form DTO and restrict allowed fields. |
| Placing BindingResult far from @ModelAttribute | Spring does not pair errors with the right command object | Place BindingResult immediately after the validated argument. |
| Re-rendering form but forgetting select options | Select has no options or loses choices | Reload supporting data into the model when rendering error forms. |
| Using form field names that do not match properties | Values are not bound | Align names with properties or configure BindParam. |
| Trusting hidden inputs or IDs from the form | Users can alter ID/owner/role | Check permissions on the server and do not trust client values. |
| Passing entire form object into redirect model | Data may appear in the URL | Pass only the ID or needed public parameters. |
| Redirecting to a user-supplied URL | Open redirect and phishing | Use internal routes or an allow-list of hosts/paths. |
| Putting tokens or PII in query strings | Exposed in history, logs, or Referer | Store state server-side or use safe reference keys. |
| Assuming PRG prevents all duplicate requests | Double-clicks or retries can still create duplicates | Use idempotency keys and unique constraints for critical operations. |
| Redirecting a JSON API and expecting the browser tab to navigate | fetch may follow internal redirects without navigating top-level page | Return JSON/Location and let client navigate explicitly. |
| Calling block() in a reactive controller | Blocks the event loop and reduces concurrency | Return Mono/Flux and use reactive repositories. |

## 16. Self-Check Questions

**Question 1.** How does an HTTP redirect differ from view rendering?  
**Answer:** View rendering generates content for the current request. A redirect returns a 3xx status and Location so the client makes a new request.

**Question 2.** Why does PRG commonly use 303?  
**Answer:** 303 instructs the client to retrieve the target resource with GET after POST, so refreshing the result page does not resubmit POST in normal flows.

**Question 3.** When should 307 or 308 be used?  
**Answer:** When redirecting while preserving the original request's method and body; 307 is temporary, 308 is permanent.

**Question 4.** What does the redirect: prefix in WebFlux do?  
**Answer:** The view resolver recognizes this as a redirect URL and uses a redirect view to return a 3xx response. WebFlux does not support forward: dispatch.

**Question 5.** What is Rendering.redirectTo() used for?  
**Answer:** Creating a redirect view via the Rendering API, allowing configuration of URL, status, model attributes, and certain headers.

**Question 6.** When should @RequestParam vs @ModelAttribute be used?  
**Answer:** @RequestParam fits a few individual fields; @ModelAttribute fits a form object with multiple fields needing shared binding/validation.

**Question 7.** Where must BindingResult be placed?  
**Answer:** Immediately after the validated @ModelAttribute argument so the controller can read binding and validation errors for that object.

**Question 8.** Which APIs do functional endpoints use to read URL-encoded forms?  
**Answer:** ServerRequest.formData() returns Mono<MultiValueMap<String, String>>; ServerRequest.bind() can bind request data into an object.

**Question 9.** Why should you avoid binding directly to an entity in a form?  
**Answer:** Entities may hold sensitive properties or fields the user is not authorized to change; a dedicated DTO and allowed fields reduce over-posting risk.

**Question 10.** What is an open redirect?  
**Answer:** When the server redirects to an arbitrary client-supplied URL, which can be abused to send users to phishing sites. Use allow-lists or allow only internal routes.

## Key Takeaways

- A redirect is an HTTP 3xx response with Location; the client sends the next request. View rendering only builds content for the current request.
- Use 303 See Other for PRG after POST processing; use 307/308 when preserving method/body is required.
- WebFlux supports redirects via view names, Rendering.redirectTo, and ServerResponse in functional endpoints.
- Use @RequestParam for simple fields and @ModelAttribute for form objects; functional endpoints provide ServerRequest.formData() and bind().
- Validate with @Valid, place BindingResult right after the form argument, and re-render the form with errors when data is invalid.
- Bind into a dedicated DTO, restrict allowed fields, protect with CSRF, and never trust hidden inputs.
- Do not pass sensitive data via query strings or redirect URLs. Validate redirect targets to prevent open redirects.
- PRG reduces duplicate POSTs on refresh; critical operations still need idempotency to prevent duplicate processing.

### References

1. [Spring Framework – WebFlux Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): data binding and WebDataBinder.
2. [Spring Framework – @ModelAttribute in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): form binding, constructor/property binding, and BindingResult.
3. [Spring Framework – Validation in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): Bean Validation and validation errors.
4. [Spring Framework – DispatcherHandler and View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): view resolution, redirect prefix, and forward limitations.
5. [Spring Framework – Rendering Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): Rendering and redirect builder.
6. [Spring Framework – RedirectView Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/reactive/result/view/RedirectView.html): default redirect status and Location configuration.
7. [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): ServerRequest, formData, bind, and ServerResponse.
8. [Spring Framework – ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): building responses and the Location header.
9. [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics of redirect statuses and HTTP methods.
