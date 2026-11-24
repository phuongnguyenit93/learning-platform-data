# Passing Data from Controller to View with `@ModelAttribute` in Spring MVC

## 1. Objective: Controller Prepares Data, View Presents Data

In a **server-side HTML rendering Spring MVC** application (JSP, Thymeleaf, and compatible template engines), the controller is responsible for preparing data for the screen and returning a view name or `ModelAndView`. The view then reads **model attributes** supplied by the controller to display information, populate default form values, and show error messages.

For example, when a user opens `GET /products/new`:

1. The controller creates an empty `ProductForm` and puts it into the model under the name `productForm`.
2. The controller returns the view name `"products/form"`.
3. Spring locates the corresponding view, such as `src/main/resources/templates/products/form.html` via Thymeleaf.
4. The template accesses `productForm.title` and `productForm.quantity`, renders HTML, and sends it to the browser.
5. The user fills out the form and submits `POST /products`; Spring binds request parameters into a new `ProductForm` and runs validation.
6. If there are errors, the controller returns the view again along with the model/form/errors so the user can fix them. If successful, the controller can redirect to the detail page.

**`@ModelAttribute` has two main usages**:

- **On a method**: contributes data to the model **before** request handlers in the same controller execute; typically used for information shared across multiple views.
- **On a method parameter**: retrieves an object from the model or instantiates one if not present, then binds HTTP data into the object; this object is also placed in the model for the view.

In addition, a controller can put data into the model via `Model.addAttribute(...)`, `ModelMap`, or `ModelAndView`. Thus `@ModelAttribute` is not the only way to pass data to a view; its value lies in combining **model population** and **binding** within the Spring MVC lifecycle.

Lesson scope: **Spring MVC Servlet stack**, Java 17+, Spring Boot 3.x examples, Thymeleaf, and Jakarta Bean Validation. Spring WebFlux has a similar annotation but a different reactive execution path. `@RestController` / `@ResponseBody` are used to return HTTP bodies directly (typically JSON), so do not treat a `String` returned from a REST controller as a view name.

## 2. Model, ModelAndView, ViewResolver, and Templates

In a typical request:

```text
Browser GET /products/new
          |
          v
DispatcherServlet -> HandlerMapping/HandlerAdapter
          |
          v
@Controller
  @ModelAttribute methods (prepare shared data)
  @GetMapping handler (adds productForm)
          |
          v
Model = {
  "catalogName": "Product Catalog",
  "productForm": ProductForm(...)
}
View name = "products/form"
          |
          v
ViewResolver (Thymeleaf/JSP depending on configuration)
          |
          v
Render HTML using model
          |
          v
HTTP 200 + text/html
```

- **Model** is a structure holding *name → value* pairs for the current rendering operation. `org.springframework.ui.Model` is the interface controllers typically accept as a parameter.
- **View name** is a logical name such as `"products/form"`. The view resolver and engine configuration decide which template resource it maps to.
- **View** uses model attributes to render HTML. In Thymeleaf, `${productForm}`, `${product.title}`, or `th:object` / `th:field` read model data.
- **`ModelAndView`** bundles both the model and the view name in a single return value when needed.
- **`@Controller`** is typically used for HTML. `@RestController` is equivalent to `@Controller + @ResponseBody`, meaning a `String` is written to the HTTP response body, **not treated by default as a template name**.

The Model here has **single-request rendering** semantics. It does not automatically persist data between two HTTP requests. Across redirects, you need `RedirectAttributes` / flash attributes; for multi-step workflows, `@SessionAttributes` may be considered. These mechanisms are distinguished in later sections.

## 3. Three Ways to Pass Data to a View

### 3.1. Adding to `Model` Directly Inside the Handler

```java
@Controller
class WelcomeController {

    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Welcome to Spring MVC");
        model.addAttribute("visitors", 42);
        return "welcome";
    }
}
```

The snippet above is an **illustrative controller class**, requiring imports for `@Controller`, `@GetMapping`, and `Model` plus a `welcome` template. When Thymeleaf renders, the template can use:

```html
<h1 th:text="${message}">Fallback heading</h1>
<p th:text="${visitors}">0</p>
```

`th:text` HTML-escapes values by default when displaying them, which is safer than intentionally rendering raw HTML with `th:utext`. However, output escaping does not replace input validation or authorization checks.

Attribute names must match: `model.addAttribute("message", ...)` corresponds to `${message}`. If the model sets `"msg"` while the view reads `"message"`, the template will not receive the expected value.

### 3.2. Method-Level `@ModelAttribute` to Share Data

```java
@Controller
@RequestMapping("/products")
class ProductController {

    @ModelAttribute("catalogName")
    String catalogName() {
        return "Product Catalog";
    }

    @GetMapping("/new")
    String newForm(Model model) {
        model.addAttribute("productForm", new ProductForm());
        return "products/form";
    }
}
```

The `catalogName()` method is invoked by Spring MVC to add the `catalogName` attribute to the model **before the `@GetMapping` handler** in this controller runs. Any template rendered by matching handlers can read `${catalogName}`.

When multiple controllers need shared data, `@ModelAttribute` methods can be declared in a `@ControllerAdvice` with appropriate selectors. Do not place expensive database queries in a global method that runs for every endpoint if many endpoints do not need that data.

A method can also add multiple attributes:

```java
@ModelAttribute
void populateFormOptions(Model model) {
    model.addAttribute("regions", List.of("north", "south"));
    model.addAttribute("pageTitle", "Create product");
}
```

This is a **method fragment** inside a controller/advice and requires importing `java.util.List`. A `void` method receives `Model` and has no single return object to auto-name.

`@ModelAttribute` methods can accept many MVC-supported arguments, though not necessarily every argument supported by `@RequestMapping` (in particular, do not use them to replace body-reading handlers). They can cause side effects or performance overhead if invoked repeatedly before many handlers; keep them focused on building the model.

### 3.3. Returning `ModelAndView` When Bundling Is Desired

```java
@GetMapping("/summary")
ModelAndView summary() {
    ModelAndView result = new ModelAndView("products/summary");
    result.addObject("count", 10);
    return result;
}
```

This is a **method fragment**; it requires importing `org.springframework.web.servlet.ModelAndView` and a `products/summary` template. It is equivalent in intent to populating `Model` and returning a view name. You are not required to use `ModelAndView` for every handler; many applications find `Model + String` cleaner and easier to read.

## 4. Comparing `@ModelAttribute` on Methods vs. Parameters

| Placement | Example | What Happens? | When to Use? |
| --- | --- | --- | --- |
| Non-handler method | `@ModelAttribute("catalogName") String name()` | Return value is added to the model before handlers in the same scope run | Titles, option lists, shared data |
| `void` method | `@ModelAttribute void add(Model model)` | Method adds one or more entries directly to the model | Multiple auxiliary data items for forms |
| Handler parameter | `save(@ModelAttribute("productForm") ProductForm form)` | Retrieves/creates model attribute, binds request values, makes it available to view | HTML form submission, data binding |
| Handler method | `@GetMapping @ModelAttribute("item") Item getItem()` | Handler return value is treated as a model attribute rather than body/view name | Want to return an object directly into the model |
| Annotation on `@RestController` | Method `@ModelAttribute` may populate model, but handler has `@ResponseBody` | Direct HTTP response does not auto-render a template | Usually unnecessary for passing data to HTML views |

**Beware the `String` ambiguity:** If a handler in `@Controller` returns `"products/form"` without `@ResponseBody`, that is normally a **view name**; however, a method annotated with `@ModelAttribute("label")` returning `String` supplies the **attribute value** for `label`, not a view name.

Spring derives the model attribute name from the type when no explicit name is given. However, when forms/templates depend on a specific name or use `BindingResult`, specifying an explicit name (such as `"productForm"`) prevents name drift when refactoring Java types and keeps tests stable.

## 5. Data Flow When Binding a Form to a `@ModelAttribute` Parameter

Suppose an HTML form submits:

```http
POST /products HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=Notebook&quantity=3
```

The controller declares:

```java
@PostMapping("/products")
String create(@ModelAttribute("productForm") ProductForm form) {
    // form.getTitle() == "Notebook"
    // form.getQuantity() == 3
    return "products/result";
}
```

This is a method fragment, requiring a `ProductForm` class, controller, and `products/result` view. Spring MVC performs these basic steps:

1. Looks up an existing model attribute named `productForm` if present; depending on declarations, it may come from a `@ModelAttribute` method or related model/session mechanisms.
2. If absent, Spring instantiates an appropriate object, typically via a supported constructor (default or primary constructor).
3. `WebDataBinder` uses request data sources to bind properties/constructor arguments. Servlet request parameters include query parameters and form-encoded data; in certain configurations, URI path variables/headers may also participate when not overridden by parameters.
4. `ConversionService`/property editors convert strings into Java types, such as `"3"` into `Integer(3)`.
5. If `@Valid` or `@Validated` is present, the validator is invoked; binding/validation errors are recorded.
6. The object and binding metadata can be exposed in the model so the view can re-display the user's entered values.

**`@ModelAttribute` is not equivalent to `@RequestBody`**:

- `@ModelAttribute` suits form/query/path/header data via data binding.
- `@RequestBody` uses an `HttpMessageConverter` (e.g., Jackson) to read a JSON/XML body according to content type.
- Sending JSON `{"title":"Notebook"}` with `Content-Type: application/json` to an endpoint declaring only `@ModelAttribute ProductForm` **does not cause Jackson to deserialize the JSON into the form**.
- For REST JSON APIs, typically choose `@RequestBody` and return `ResponseEntity`/DTO instead of a view name.

When a method parameter is a complex object not handled by another resolver, Spring MVC may infer an **implicit `@ModelAttribute`**. However, declaring it explicitly clarifies the contract and aids AOT/native-image analysis.

## 6. Runnable Example: Product Creation Form with Thymeleaf

The sample application uses **Spring Boot 3.x, Java 17+, Spring MVC Servlet + Thymeleaf + Jakarta Validation**. You can observe the full cycle:

```text
GET /products/new
    -> Model {"productForm", "catalogName"}
    -> render templates/products/form.html

POST /products
    -> @ModelAttribute("productForm") binds form data
    -> @Valid + BindingResult
       |
       +-- invalid -> re-render templates/products/form.html (HTTP 200)
       |
       +-- valid   -> store in-memory
                      addFlashAttribute("notice")
                      redirect:/products/{id} (HTTP 302)
                          |
                          v
                      GET /products/{id}
                      -> Model {"product", "catalogName", "notice"}
                      -> render templates/products/detail.html
```

HTTP 302 in the Post-Redirect-Get flow is the common default behavior of Spring MVC view redirects; a specific redirect status (such as 303) can be configured when required by contract, though the sample leaves the default status unchanged.

### 6.1. Dependencies

In a Spring Boot 3.x project that already has plugins, repositories, Java toolchain, and dependency management, add to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **Gradle configuration fragment**, not a complete build file. The Thymeleaf starter provides view resolver/template integration; the validation starter provides the Jakarta Bean Validation provider. If using Maven, declare the corresponding starters in `pom.xml` managed by the Spring Boot BOM.

### 6.2. Java Code

Create **`src/main/java/demo/modelview/ModelViewApplication.java`**:

```java
package demo.modelview;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
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

@SpringBootApplication
public class ModelViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelViewApplication.class, args);
    }
}

// Form DTO: bind only fields the user is allowed to enter.
class ProductForm {
    @NotBlank
    private String title;

    @NotNull
    @Min(1)
    private Integer quantity;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}

// View object contains only data permitted for display.
class Product {
    private final long id;
    private final String title;
    private final int quantity;

    Product(long id, String title, int quantity) {
        this.id = id;
        this.title = title;
        this.quantity = quantity;
    }

    public long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getQuantity() {
        return quantity;
    }
}

@Controller
@RequestMapping("/products")
class ProductController {

    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Product> products =
            new ConcurrentHashMap<>();

    @ModelAttribute("catalogName")
    String catalogName() {
        return "Product Catalog";
    }

    @GetMapping("/new")
    String newForm(Model model) {
        model.addAttribute("productForm", new ProductForm());
        return "products/form";
    }

    @PostMapping
    String create(
            @Valid @ModelAttribute("productForm") ProductForm form,
            BindingResult errors,
            RedirectAttributes redirects) {

        if (errors.hasErrors()) {
            return "products/form";
        }

        long id = sequence.incrementAndGet();
        Product saved = new Product(
                id, form.getTitle(), form.getQuantity());
        products.put(id, saved);

        redirects.addFlashAttribute(
                "notice", "Product created successfully");
        return "redirect:/products/" + id;
    }

    @GetMapping("/{id}")
    String detail(@PathVariable long id, Model model) {
        Product product = products.get(id);
        if (product == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }

        model.addAttribute("product", product);
        return "products/detail";
    }
}
```

This is **a single valid Java file** in a Boot 3 project, where only `ModelViewApplication` is public and the remaining classes are package-private. Spring Boot scans package `demo.modelview` to discover `@Controller`.

Key points:

- `catalogName()` is a `@ModelAttribute` method that always adds the heading to the model before handlers in `ProductController`.
- `newForm(Model model)` puts an empty `ProductForm` into the model with the explicit key `"productForm"`.
- Upon submission, `@ModelAttribute("productForm") ProductForm form` binds form parameters; `@Valid` checks `@NotBlank`, `@NotNull`, and `@Min(1)`.
- `BindingResult errors` must appear **immediately after** `form`. Otherwise, validation errors typically raise an exception before the controller has a chance to re-render the form.
- On error, return view `products/form` within the **same request**. The model retains the form and `BindingResult` so Thymeleaf can read the errors.
- On success, the controller stores the demo data, adds a **flash attribute** `notice`, and redirects to the detail GET endpoint. The rendered data of the post-redirect response is prepared by the **new GET request**.
- Use a dedicated `ProductForm` with only bindable fields; do not bind directly to entities or beans containing `role`, `priceOverride`, `isAdmin`, or sensitive fields clients must not modify.
- `ConcurrentHashMap` is for illustration only: there is no database, transaction, durable storage, or shared state across multiple instances. Do not take this in-memory choice into production without replacing it with proper persistence architecture.

### 6.3. Thymeleaf Form Template

Create **`src/main/resources/templates/products/form.html`**:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Create Product</title>
</head>
<body>
  <h1 th:text="${catalogName}">Catalog Name</h1>
  <h2>Create Product</h2>

  <form th:action="@{/products}" th:object="${productForm}" method="post">
    <div>
      <label for="title">Product Title</label>
      <input id="title" type="text" th:field="*{title}">
      <small th:if="${#fields.hasErrors('title')}"
             th:errors="*{title}">Title error</small>
    </div>

    <div>
      <label for="quantity">Quantity</label>
      <input id="quantity" type="number" th:field="*{quantity}">
      <small th:if="${#fields.hasErrors('quantity')}"
             th:errors="*{quantity}">Quantity error</small>
    </div>

    <button type="submit">Create</button>
  </form>
</body>
</html>
```

Thymeleaf explanation:

- `th:object="${productForm}"` selects the form object in the model as the context for `*{...}` expressions.
- `th:field="*{title}"` reads the property value and generates matching HTML `name`/`id`/`value` attributes for form binding.
- `#fields.hasErrors('title')`/`th:errors` read binding/validation errors for the `productForm` attribute. Spring also places error metadata into the model under a key like `org.springframework.validation.BindingResult.productForm`.
- `th:text="${catalogName}"` retrieves the data provided by the `@ModelAttribute("catalogName")` method.
- When form submission is invalid, the template is re-rendered with errors instead of redirecting, preserving the user's entered values.

**If Spring Security with CSRF protection is enabled**, POST forms in a real application must carry a valid CSRF token; Thymeleaf/Spring Security integration can automatically add a hidden token depending on configuration. The dependency example above excludes Spring Security so that requirement is absent here. Do not disable CSRF indiscriminately just to make a demo work.

### 6.4. Thymeleaf Detail Template

Create **`src/main/resources/templates/products/detail.html`**:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Product Details</title>
</head>
<body>
  <h1 th:text="${catalogName}">Catalog Name</h1>
  <p th:if="${notice}" th:text="${notice}">Notice</p>

  <dl>
    <dt>ID</dt>
    <dd th:text="${product.id}">0</dd>
    <dt>Title</dt>
    <dd th:text="${product.title}">Sample Title</dd>
    <dt>Quantity</dt>
    <dd th:text="${product.quantity}">0</dd>
  </dl>

  <a th:href="@{/products/new}">Add Product</a>
</body>
</html>
```

`${product.id}`, `${product.title}`, and `${product.quantity}` are read by Thymeleaf/Spring EL from `Product`'s JavaBean getters. The model in the current GET request has `product` set via `model.addAttribute("product", product)`.

`notice` does not come from `@ModelAttribute("catalogName")`: it is a **flash attribute** from the preceding POST redirect. If a user opens the detail URL directly, `notice` may not exist; `th:if="${notice}"` prevents rendering the notice block.

### 6.5. Running and Checking the Result

Run the configured Spring Boot project:

```bash
./gradlew bootRun
```

Open `http://localhost:8080/products/new` in a browser. The form view should display:

```text
Product Catalog
Create Product
Product Title: [             ]
Quantity:      [             ]
[Create]
```

This is a **visual UI mockup**, not Java stdout. Enter title "Notebook", quantity "2", and submit. The browser receives a redirect to `/products/1001` (if no other POST occurred since startup), then displays the details along with the notice.

You can observe responses with curl:

```bash
curl -i 'http://localhost:8080/products/new'

curl -i -X POST 'http://localhost:8080/products' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Notebook' \
  --data-urlencode 'quantity=2'
```

A valid POST returns a redirect status, typically **302 Found**, with a `Location` header pointing to `/products/{id}`. `curl` does not follow redirects without `-L`, so the initial response will not yet be the detail HTML. To follow the next request, use `curl -L`, noting how the client handles HTTP methods on redirect; browsers will normally GET the target page after a form POST.

Invalid POST:

```bash
curl -i -X POST 'http://localhost:8080/products' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=' \
  --data-urlencode 'quantity=0'
```

When validation fails, the method returns `"products/form"` directly: typically HTTP **200 OK**, containing the HTML form with error messages on title/quantity. This is standard HTML form handling, though **not appropriate by default for JSON APIs**; REST APIs typically return 400 with an error body instead of rendering a form.

## 7. When Are `@ModelAttribute` Methods Invoked?

By Spring MVC mechanics, `@ModelAttribute` methods in the same controller execute **before the matching `@RequestMapping` method** to prepare the model. Such methods can also be placed in `@ControllerAdvice` to be shared across multiple controllers, depending on selectors and advice ordering.

Example:

```java
@ControllerAdvice(assignableTypes = ProductController.class)
class ProductViewAdvice {

    @ModelAttribute("footerText")
    String footer() {
        return "© Demo Catalog";
    }
}
```

This is an add-on fragment for the example project in Section 6; it requires importing `org.springframework.web.bind.annotation.ControllerAdvice` and `ModelAttribute`. Adding this class to the same package allows `ProductController`'s views to read `footerText`.

Do not use `@ModelAttribute` methods as an interceptor controlling the entire HTTP lifecycle, because they only participate in MVC controller handling per invocation rules. They are not guaranteed to run for static assets, requests blocked by filters/security before MVC, or certain errors occurring before a handler is selected.

### Is a `Model` Parameter Mandatory in a `@ModelAttribute` Method?

No. There are two main patterns:

```java
@ModelAttribute("applicationName")
String applicationName() {
    return "Spring Training";
}
```

The return value is added under the name `applicationName`, or:

```java
@ModelAttribute
void setup(Model model) {
    model.addAttribute("applicationName", "Spring Training");
    model.addAttribute("displayCurrency", "VND");
}
```

In the second pattern, the method adds multiple entries itself. These are **alternative fragments**; do not define both with the same attribute name and overwrite one another without a clear rule.

### `@ModelAttribute` on the Handler Method Itself

Spring also allows:

```java
@GetMapping("/current-product")
@ModelAttribute("product")
Product currentProduct() {
    return productService.current();
}
```

This is a fragment using an application-defined service. `@ModelAttribute("product")` on a handler method makes the **return value be interpreted as a model attribute**, rather than treating a `String` as a view name or using `@ResponseBody` to write JSON. If the method does not specify an explicit view name, Spring may use its default mechanism to infer the view name from the request URL; ensure a matching view resolver/template exists.

Do not use this style on a controller serving a JSON API while accidentally expecting the response to be serialized; in REST controllers, use `@ResponseBody`/`ResponseEntity` explicitly per contract.

## 8. `@ModelAttribute` Method vs. `Model.addAttribute`: Which to Choose?

| Scenario | Solution | Reason |
| --- | --- | --- |
| Each page needs distinct data just loaded by the handler | `Model.addAttribute("product", product)` | Data source is clear inside the method |
| Multiple views in the same controller share a catalog title | `@ModelAttribute("catalogName")` method | Avoids repeating logic |
| Multiple controllers share a language/label selector | `@ControllerAdvice` with `@ModelAttribute` method | Shared via appropriate selector |
| Handler returns both model and view name | `ModelAndView` | Single clear return object |
| Form submission needs binding and error display | `@Valid @ModelAttribute("productForm")` + `BindingResult` | Spring manages binding/errors |
| Redirect after a successful POST | `RedirectAttributes.addFlashAttribute(...)` | Passes brief notices to the next request |
| Data spans multiple steps of a wizard | `@SessionAttributes` (use cautiously) | Model attributes kept in HTTP session for workflow |
| REST API returning JSON | `@RequestBody`, `@ResponseBody`, `ResponseEntity` | Bypasses view templates |

Design rule: do not dump entire database records or sensitive objects into the model just because a template needs a few fields. Passing a **focused view model/DTO** avoids unnecessary data and the risk of accidentally rendering private fields.

## 9. `BindingResult` Must Immediately Follow the Form Object

For form validation, the standard pattern is:

```java
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("form") ProductForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "products/form";
    }

    // Perform save operation, then redirect.
    return "redirect:/products";
}
```

This is a **fragment** inside a controller; the `form` variable, view path, and destination must match the real application.

`BindingResult` or `Errors` must be declared **immediately after** the validated parameter. Spring uses it to record type-conversion and validation errors and exposes them to the view engine. In the view:

```html
<form th:object="${form}">
  <input th:field="*{title}">
  <span th:if="${#fields.hasErrors('title')}"
        th:errors="*{title}">Error</span>
</form>
```

If `BindingResult` is missing or misplaced, errors can trigger an exception before the controller body executes. In Spring Framework 6.1+, if a handler places constraints directly on method parameters enabling native method validation, the exception path may be `HandlerMethodValidationException`; do not rigidly assume every form validation failure produces only one exception type.

### Type Mismatch Binding Before Validation

If a form has `Integer quantity` and the client sends `quantity=abc`, Spring cannot convert it to `Integer`. A **type mismatch** error is recorded in `BindingResult` (with appropriate handler configuration), even though `@Min(1)` never received a valid number to evaluate. Templates need to display conversion errors rather than only considering constraint annotations.

Similarly, `@NotNull` on `Integer` does not catch an unconvertible string input in the same way as a Java `null` value; both binding errors and validation errors should be surfaced.

## 10. Data Binding Security: Preventing Mass Assignment

`@ModelAttribute` can bind multiple object properties from a request; this convenience leads to **mass assignment / over-posting** if you bind directly to a domain entity:

```java
// Example NOT recommended directly with entities containing sensitive fields.
@PostMapping("/users/update")
String update(@ModelAttribute UserEntity user) {
    repository.save(user);
    return "redirect:/users";
}
```

A client could try sending extra parameters like `isAdmin=true` or `balance=999999` if the object has writable properties with those names. Binding directly to an entity lets attackers modify fields not exposed in the UI.

Countermeasures:

1. Use a **dedicated form DTO** containing only data meant to be accepted from the client, like `ProductForm` in the example.
2. Accept only editable fields and avoid writable setters on sensitive fields.
3. When property binding on a complex object is required, configure `WebDataBinder#setAllowedFields(...)` via `@InitBinder` to allowlist permitted fields.
4. Do not treat `@ModelAttribute(binding=false)` as a general authorization filter; it **disables binding** for the selected object, while database updates still require authorization checks.
5. Enforce authorization, ownership, and business rules in the service/domain layer; never trust client-submitted form data.
6. Apply CSRF protection suitable for HTML forms with cookie-based authentication.

Example restricting fields:

```java
@InitBinder("productForm")
void productBinder(WebDataBinder binder) {
    binder.setAllowedFields("title", "quantity");
}
```

This is a **method fragment** in a controller or advice, requiring imports `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. It illustrates blocking binding of any fields beyond the two allowed ones. If the DTO already contains only `title` and `quantity`, this adds defense in depth, though forms with nested properties or collections should be tested carefully as they may require detailed allowed-field patterns.

**Constructor binding** is also a safe option when designing clear immutable form DTOs, provided your framework version and parameter naming match. With the example's bean setters, binding is easy to observe; do not blindly apply that style to rich entity types.

## 11. Redirects Do Not Preserve the Previous Request's Model

When a controller returns `"redirect:/products/1001"`, Spring sends an HTTP 3xx and the browser issues a **new HTTP request**. The POST's model **does not automatically survive** into the GET. There are three ways to pass data to a redirect target:

1. **Path/query parameters**: use a URL like `/products/1001` or `?view=compact` so the GET handler loads the needed data itself.
2. **`RedirectAttributes.addAttribute(...)`**: appends URI variables / query attributes to the redirect URL per contract. Data may appear in the address bar, logs, and browser history.
3. **`RedirectAttributes.addFlashAttribute(...)`**: temporarily stores notices or data for the post-redirect request; usually held briefly in the HTTP session and placed into the target request's model.

In the main example:

```java
redirects.addFlashAttribute("notice", "Product created successfully");
return "redirect:/products/" + id;
```

This fragment already appeared in Section 6. After redirecting, the GET controller adds `product` to its own model; `notice` is retrieved by Spring from the **input FlashMap** and put into the target request's model. Flash attributes are **not long-term session state** and are normally consumed once.

Downside of passing data via URL:

```java
redirects.addAttribute("notice", "Product created");
```

If this parameter is used to build the redirect URL, the text can appear in the query string and be recorded in browser history, referrers, and logs. Choose flash attributes for transient display notices, and never put secrets in URIs.

**Warning about redirect models:** MVC configuration may allow certain model attributes to be appended to the redirect URI automatically if `RedirectAttributes` is not used. Therefore, to prevent accidental data exposure in URLs, explicitly specify which attributes are allowed for redirects and consider configuring `ignoreDefaultModelOnRedirect` according to your framework contract.

## 12. `@ModelAttribute`, `@SessionAttributes`, and `@SessionAttribute`

These three annotations have similar names but serve different purposes:

| Annotation | Placement | Meaning |
| --- | --- | --- |
| `@ModelAttribute` | Controller method/parameter | Populates or accesses/binds MVC model data |
| `@SessionAttributes` | **Controller class** | Stores **selected model attributes** in the HTTP session for a controller workflow |
| `@SessionAttribute` | **Method parameter** | Reads an existing value from the HTTP session; does not directly manage workflow models |

Example with a multi-step form:

```java
@Controller
@SessionAttributes("draft")
class OrderWizardController {

    @ModelAttribute("draft")
    OrderDraft draft() {
        return new OrderDraft();
    }

    @GetMapping("/wizard")
    String show() {
        return "orders/wizard";
    }

    @PostMapping("/wizard/finish")
    String finish(
            @ModelAttribute("draft") OrderDraft draft,
            SessionStatus sessionStatus) {
        // Perform valid save.
        sessionStatus.setComplete();
        return "redirect:/orders";
    }
}
```

This is an **illustrative fragment**, requiring `OrderDraft` and templates; add imports `@SessionAttributes`, `SessionStatus`, `@ModelAttribute`, `@Controller`, `@GetMapping`, and `@PostMapping`. In practice, `@Valid` and CSRF/auth/transaction safeguards are needed before completion.

`@SessionAttributes("draft")` tells Spring to keep the `draft` model attribute in the session across the controller workflow; `SessionStatus#setComplete()` marks completion so Spring cleans up the model attributes managed via `@SessionAttributes`. It **does not** invalidate the entire user session or log the user out.

Do not use `@SessionAttributes` merely because multiple pages need a site name or currency label. Shared read-only information can be loaded from config/services via `@ModelAttribute` or global advice; sessions hold per-user state and increase concurrency and lifecycle complexity.

## 13. `@ModelAttribute(binding=false)` and Pre-Existing Object Sources

Sometimes a controller needs an object from the DB in the model, yet **must not let request parameters mutate that object**.

Example:

```java
@ModelAttribute("product")
Product product(@PathVariable long id) {
    return catalogService.getRequired(id);
}

@PostMapping("/products/{id}/review")
String review(
        @ModelAttribute(binding = false) Product product,
        @Valid @ModelAttribute("reviewForm") ReviewForm form,
        BindingResult result) {
    // Check permissions, contract, and save review.
    return "redirect:/products/" + product.getId();
}
```

These fragments illustrate the pattern; `catalogService`, `ReviewForm`, mappings, and authorization must be implemented by the application. `binding=false` prevents request parameters from directly mutating `product`, while `reviewForm` is still bound and validated.

The order of adding objects to the model and their sources must be verified against actual request mappings. For some types, Spring may instantiate a model attribute via converter/constructor if absent; do not assume it automatically queries a repository just because `@ModelAttribute("product")` is present.

## 14. Testing Model, View, and Binding with MockMvc

Create **`src/test/java/demo/modelview/ModelViewApplicationTests.java`**:

```java
package demo.modelview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class ModelViewApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormIncludesAttributesAndResolvesView() throws Exception {
        mvc.perform(get("/products/new"))
            .andExpect(status().isOk())
            .andExpect(view().name("products/form"))
            .andExpect(model().attributeExists(
                    "catalogName", "productForm"))
            .andExpect(model().attribute(
                    "catalogName", "Product Catalog"));
    }

    @Test
    void invalidFormKeepsFormAndValidationErrors() throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "")
                .param("quantity", "0"))
            .andExpect(status().isOk())
            .andExpect(view().name("products/form"))
            .andExpect(model().attributeHasFieldErrors(
                    "productForm", "title", "quantity"));
    }

    @Test
    void validFormRedirectsToCreatedProduct() throws Exception {
        MvcResult created = mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Notebook")
                .param("quantity", "2"))
            .andExpect(status().is3xxRedirection())
            .andExpect(flash().attribute(
                    "notice", "Product created successfully"))
            .andReturn();

        String destination = created.getResponse().getRedirectedUrl();
        assertNotNull(destination);
        assertTrue(destination.matches("/products/[0-9]+"));

        // MockMvc does not follow redirects automatically; test GET separately.
        mvc.perform(get(destination).flashAttrs(created.getFlashMap()))
            .andExpect(status().isOk())
            .andExpect(view().name("products/detail"))
            .andExpect(model().attributeExists(
                    "product", "catalogName"))
            .andExpect(model().attribute(
                    "notice", "Product created successfully"));
    }

    @Test
    void unknownProductReturns404() throws Exception {
        mvc.perform(get("/products/9223372036854775807"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./gradlew test
```

With the files from Section 6 and Boot 3 dependencies configured, **four tests are expected to pass**. This is an expectation based on the sample code, not a report of an executed Gradle run. The tests verify:

- `model().attributeExists(...)` confirms the controller placed data into the model.
- `view().name(...)` verifies a view name was selected rather than returning JSON directly.
- `attributeHasFieldErrors(...)` checks that binding/validation errors appear in the model on invalid input.
- `flash().attribute(...)` confirms the flash message was added prior to the redirect.
- A successful POST creates the new resource URI; the subsequent GET has the `product` model attribute and right view. `flashAttrs(created.getFlashMap())` simulates re-attaching flash attributes to the GET request in an isolated test.

**MockMvc limitations:** it does not fully verify proxy behavior, real browsers, CSRF when Security is integrated, multi-node session stores, or client-side JavaScript. For products with critical UIs, combine view/MockMvc tests with browser integration tests.

### Testing Type Mismatch on Form Submission

Add a case with `quantity=abc` and assert `model().attributeHasFieldErrors("productForm","quantity")`. This proves Spring captures the conversion failure to render the view instead of letting Java throw `NumberFormatException` after controller invocation. Avoid asserting specific English error messages since they depend on `MessageSource`/locale.

## 15. Comparing Model Access in Thymeleaf, JSP, and REST

### Thymeleaf

Typically uses:

```html
<span th:text="${catalogName}">Fallback</span>
<input th:field="*{title}">
```

The first reads a model attribute. The second must sit inside a form with `th:object="${productForm}"` to use the selection expression `*{title}`. Spring integration handles binding/error state.

### JSP + Spring Form Tags

Illustrative fragment in a JSP with JSTL/taglibs configured:

```jsp
<spring:eval expression="catalogName" var="catalogNameText"/>
<p>${catalogNameText}</p>
```

This is a **conceptual JSP fragment**, not code to paste verbatim without declaring the appropriate taglibs. In real JSPs, JSP Expression Language usually reads `${catalogName}` directly from model attributes exposed in request scope; Spring form tags handle form binding and errors according to the form model. When using Thymeleaf in the sample app, **no JSP configuration is needed**.

### JSON REST

```java
@RestController
class CatalogApi {
    @GetMapping("/api/catalog")
    java.util.Map<String, String> catalog() {
        return java.util.Map.of("name", "Product Catalog");
    }
}
```

Here `Map` is the **response body** serialized by a message converter (typically JSON), not a model for a template. If inside `@RestController` you return `"products/form"`, the body will contain the literal text `products/form` rather than rendering an HTML page. This is a common mistake when migrating code from MVC views to REST APIs.

## 16. Common Mistakes When Using `@ModelAttribute`

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Template cannot see `productForm` | Controller forgot `model.addAttribute("productForm", ...)` or used a different name | Set an explicit model attribute name and assert with MockMvc |
| Form submission does not bind to object | Input `name` differs from property or wrong content type | Use `th:field` or verify form names / setters / constructors |
| Browser prints literal `products/form` | Using `@RestController`/`@ResponseBody` | Change HTML-serving controller to `@Controller` |
| HTML form has errors but none display | Missing `BindingResult` next to form or template omits `th:errors` | Check parameter order and `th:object` name |
| Invalid form redirects and loses errors/values | Redirecting in the validation-failure branch | Render directly in the same request or design flash models carefully |
| Success notice disappears after redirect | Putting notice in POST's Model | Use `RedirectAttributes.addFlashAttribute` |
| Model holds stale data across GETs | Expecting request Model to persist automatically | Reload data on GET; use session/flash only if truly needed |
| User modifies admin fields outside the form | Binding directly to an entity with public setters | Dedicated form DTO and allowed fields |
| `@ModelAttribute` method runs unexpectedly often | Method populates model for many handlers | Reduce side effects, cache where appropriate, and narrow scope |
| Model never renders | Method returns `@ResponseBody`/`ResponseEntity` | Templates render only when handler returns a view name or ModelAndView |
| `@SessionAttributes` is never cleaned up | Forgot `SessionStatus#setComplete()` | Complete the wizard lifecycle properly |
| URL variants behind a reverse proxy redirect wrongly | Context path/gateway prefix out of sync | Check `RedirectView`, trusted forwarded headers, and test deployment paths |

Observed symptoms can be affected by other configurations (Spring Security, view resolvers, filters, input errors); tests and logs should be your source of truth rather than guesswork.

## 17. Key Considerations When Upgrading Spring Versions

**Spring Framework 5.x / Boot 2.x:** `@Controller`, `Model`, and `@ModelAttribute` share the core semantics described here. For Bean Validation, the namespace is typically `javax.validation.Valid`. JSP/Thymeleaf integration depends on Boot starters and versions.

**Spring Framework 6.x / Boot 3.x:** Java 17+ baseline; Jakarta EE namespaces switch to `jakarta.validation.Valid` and `jakarta.servlet.*`. Spring 6 supports constructor binding, Servlet data binding, and MVC model mechanisms. The lesson's examples use Boot 3.x with Thymeleaf. Native MVC method validation introduced in Framework 6.1 can affect exceptions on some handlers when constraints appear directly on method parameters.

**Spring Framework 7.x / Boot 4.x:** the concepts of `@ModelAttribute` methods, parameter binding, model/view, and flash attributes remain. However, dependency coordinates, starter modules, and other integrations may change; verify template engine / Spring MVC BOMs for your version. Do not copy Boot 3 build snippets into Boot 4 without checking the migration guide.

A specific note for **GraalVM native image/AOT**: Spring recommends **declaring `@ModelAttribute` explicitly** on complex-type method arguments so reflection hints for data binding are generated properly; relying on implicit `@ModelAttribute` can limit AOT inference.

These version changes do not turn `@ModelAttribute` into a JSON parser or an automatic session mechanism. Always frame data-handling problems in terms of **view rendering vs. request binding vs. API response**.

## 18. Checklist for Safe and Maintainable Forms

- [ ] HTML-serving controllers use `@Controller` and return valid view names.
- [ ] GET form handlers add the form object to the model with an explicit key; template `th:object` uses that exact key.
- [ ] Template resources exist in the engine-configured folder matching the view name.
- [ ] Shared model attributes via `@ModelAttribute` methods do not execute redundant queries or cause unintended state changes.
- [ ] POST binds only to allowed DTO/form objects, never directly to entities containing sensitive fields.
- [ ] `@Valid`/`@Validated` matches constraints; `BindingResult` sits immediately after the form parameter.
- [ ] On error, return the form in the same request, preserving errors and entered values.
- [ ] On success, persist first and then redirect via Post-Redirect-Get, using flash attributes for short notices.
- [ ] Never place sensitive data in URLs via redirect attributes.
- [ ] If using `@SessionAttributes`, keep the lifecycle and `SessionStatus#setComplete()` clear.
- [ ] Forms have CSRF protection when using cookie-based authenticated actions.
- [ ] Tests cover model attributes, view names, field errors, redirects, and flash attributes.
- [ ] Never assume model/flash is a persistence store or cross-request cache.

## 19. Practice Exercises

1. Add a `@ModelAttribute("currentYear")` method in `ProductController` and display the year in both the form and detail templates. Why is `model.addAttribute("currentYear", ...)` unnecessary inside each handler?
2. In the form template, change `th:object="${productForm}"` to `${product}`. What happens if the model only contains `productForm`? How would MockMvc catch this error?
3. Remove `BindingResult` from POST `create` and submit `quantity=0`. Trace the validation flow, exception, and default status.
4. Change POST `create` to `@RestController` and return `"products/detail"`. Why does the browser no longer render a view?
5. A client submits an extra `isAdmin=true` parameter alongside the HTML fields. Explain why binding entities with many setters is risky; add `@InitBinder#setAllowedFields` or switch to a form DTO.
6. Write a test where `POST /products` succeeds, extracts the URL from `Location`, sends a follow-up GET request, and asserts the model has the `product` attribute.
7. Try switching the success notice from `addFlashAttribute` to `addAttribute`. Contrast flash/session vs. query strings and URL logging risks.
8. Build a three-step wizard using `@SessionAttributes("draft")`. Upon completion, why should you call `SessionStatus#setComplete()` instead of invalidating the entire session?
9. Update the form to accept quantity as an `Integer` and submit `quantity=abc`. Inspect the field error from conversion and explain how it differs from a `@Min(1)` error.
10. Use `@ControllerAdvice` to supply a region option list to two controllers. How do you scope the advice to only the appropriate view controllers and avoid running DB queries on every REST endpoint?

## 20. Official Documentation

- [Spring Framework — Model and `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html): method-level attribute population.
- [Spring Framework — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding, validation, object creation, `binding=false`, and AOT.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `Model`, `BindingResult`, `RedirectAttributes`, `@SessionAttributes`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): String view name, ModelAndView, Model/Map, ResponseBody.
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html): passing data via URI and flash attributes, `ignoreDefaultModelOnRedirect`.
- [Spring Framework — Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html): FlashMap, lifecycle, concurrency.
- [Spring Framework — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): model/session workflow.
- [Spring Framework — Data Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html): `DataBinder`, binding, and allowed fields.
- [Thymeleaf — Spring Integration Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): `th:object`, `th:field`, form errors, and Spring model.
