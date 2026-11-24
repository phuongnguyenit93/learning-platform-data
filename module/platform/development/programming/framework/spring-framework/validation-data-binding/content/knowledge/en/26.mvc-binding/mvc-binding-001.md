# @ModelAttribute and Binding Form or Query Data to Objects in Spring MVC

In Spring MVC, users can send data from a URL query string or an HTML form as name–value pairs. Instead of reading each parameter with `@RequestParam` and manually assigning them to an object, a controller can declare **`@ModelAttribute` on an object-typed parameter**. Spring finds or creates that object, uses `WebDataBinder` to convert request data into the object's properties/constructor arguments, records binding errors, and then passes the object into the handler.

Example request:

~~~http
GET /catalog/search?term=spring&page=2&sort=recent HTTP/1.1
Host: localhost:8080
~~~

and controller:

~~~java
@GetMapping("/search")
public String search(@ModelAttribute("filter") SearchForm form) {
    return form.getTerm() + " - page " + form.getPage();
}
~~~

with a JavaBean `SearchForm` having corresponding `term` and `page` properties, it will receive `"spring"` and `2`; if the method returns a string as above in a `@RestController`, the string is written to the HTTP response. This is only **binding**: if you want to check conditions such as non-blank or page greater than 0, separate validation is needed.

This lesson focuses on **`@ModelAttribute` as a Spring MVC handler parameter** in Spring Framework 6.x / Spring Boot 3.x, Java 17+. At the end, there is a runnable example with GET query, POST form, type conversion, Bean Validation, `BindingResult`, and restricting bindable fields.

## 1. What problem does `@ModelAttribute` solve?

A form often sends multiple fields:

~~~text
term=spring
page=3
sort=recent
~~~

There are two ways to receive the data:

~~~java
// Reading each field individually:
@GetMapping("/search")
public String search(
        @RequestParam String term,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "relevance") String sort) {
    return term + " / " + page + " / " + sort;
}
~~~

~~~java
// Grouping fields into an object:
@GetMapping("/search")
public String search(@ModelAttribute SearchForm form) {
    return form.getTerm() + " / "
        + form.getPage() + " / "
        + form.getSort();
}
~~~

These two snippets only illustrate handler signatures; imports/controller and the `SearchForm` definition are needed in the complete example section. `@ModelAttribute` is especially useful when a form has many fields, when you need to reuse a DTO across handlers, when there are nested properties, when whole-object validation is needed, or when the object must stay in the model to re-render HTML.

Points to remember:

- `@ModelAttribute` on a **handler parameter** binds request data into a model object.
- `@ModelAttribute` on a **controller method** is typically used to create or populate attributes in the model before the handler runs; this is a different use case, explained in section 8.
- `@ModelAttribute` does not by default read a JSON body via Jackson; JSON bodies typically use `@RequestBody`.
- Successfully binding an object does not mean it is valid according to business rules or has been saved to a database.

## 2. Where does the input data come from?

For Spring MVC running on the Servlet stack, **request parameters** include:

1. **Query string**: `GET /catalog/search?term=java&page=2`.
2. **URL-encoded form data**: name–value pairs in the `application/x-www-form-urlencoded` body of a POST request.
3. **Additional MVC sources**: URI path variables and request headers can also participate in binding by name when not shadowed by a request parameter with the same name; hyphenated header names are handled according to binder rules.

For example, GET and POST can go into the **same DTO**:

~~~http
GET /catalog/search?term=java&page=2 HTTP/1.1
Host: localhost:8080
~~~

~~~http
POST /catalog/submit HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

term=java&page=2
~~~

If the DTO has `term` as `String` and `page` as `Integer`, Spring takes the strings `"java"` and `"2"` and converts `"2"` to the integer `2` via `ConversionService`. With `@ModelAttribute("filter")`, the name `filter` is the **model attribute name**; the request still uses keys `term` and `page`, and does not necessarily have to use `filter.term` and `filter.page`.

**Note on data sources:** Query parameters can be bound in many HTTP methods, including a POST that has both a query string and a form body. If the same key appears from multiple sources, check the Servlet parameter map and binder semantics; do not design contracts based on assuming an arbitrary merge rule. For JSON APIs, use `@RequestBody`/`HttpMessageConverter` for its intended purpose.

### Annotation selection table

| Goal | Suitable annotation/signature |
|---|---|
| A single value from query/form | `@RequestParam("page") int page` |
| Multiple fields building one object from query/form | `@ModelAttribute SearchForm form` |
| ID in the path `/orders/{id}` | `@PathVariable Long id` |
| Specific header | `@RequestHeader("X-Request-Id") String id` |
| JSON body converted to DTO | `@RequestBody CreateOrderRequest request` |
| A part in a multipart body | `@RequestPart`, or `MultipartFile` as appropriate |
| Access an existing object in the model and bind additional values | `@ModelAttribute("name") SomeType value` |
| Access a model object **without binding request parameters** | `@ModelAttribute(binding = false)` |

`@ModelAttribute` can also be used when handling `multipart/form-data` with appropriate multipart configuration, for example a DTO containing `MultipartFile`; it does not automatically turn every MIME type into form fields.

## 3. Argument resolution and data binding flow

When Spring MVC locates a handler, the argument resolution mechanism must produce the arguments to invoke the method. With `@ModelAttribute`, the general sequence is:

~~~text
HTTP request
     |
     v
DispatcherServlet -> HandlerMapping -> HandlerAdapter
                                      |
                                      v
                          ModelAttribute argument resolver
                                      |
                      find existing object in Model
                      or instantiate suitable object
                                      |
                                      v
                                WebDataBinder
                      +---------------------------------+
                      | extract request parameter values|
                      | constructor/property binding    |
                      | convert String -> Java type     |
                      | record binding errors           |
                      +---------------------------------+
                                      |
                        @Valid / @Validated if present
                                      |
                            BindingResult / exception
                                      |
                                      v
                            invoke controller method
~~~

Four mechanisms cooperate with distinct responsibilities:

- **Argument resolver:** decides how to create/obtain the model attribute and method argument.
- **`WebDataBinder`:** performs binding and type conversion according to the allowed properties/fields.
- **Validation:** if `@Valid`/`@Validated` and a validator are present, checks object constraints after binding.
- **`BindingResult`:** holds binding/validation errors for **that exact object** and must appear immediately after the model attribute whose errors are being handled.

A model attribute can come from an object already prepared in the model, from session via `@SessionAttributes`, from a suitable converter, or be created by Spring via a constructor. Therefore, `@ModelAttribute` does not always mean `new DTO()`.

## 4. How does Spring instantiate the object?

### 4.1. Constructor + setter/property binding

With a JavaBean having a no-arg constructor and setters:

~~~java
public class SearchForm {
    private String term;
    private Integer page = 1;

    public SearchForm() {
    }

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }
}
~~~

Spring can instantiate `SearchForm` using the no-arg constructor and invoke setters for request fields with matching names. When `page` is absent from the request, the default value `1` is preserved in the example. If the request contains `page=5`, the binder converts it to `Integer(5)` and calls `setPage(5)`.

**Do not assume Java field names automatically match any request key regardless of configuration.** With property binding, a matching writable property is required (a JavaBeans setter, unless direct field binding has been configured). A `private` field without a setter is not automatically written by the property binder just because its name matches.

### 4.2. Constructor binding, records, and immutable objects

Modern Spring MVC also supports **constructor binding**. With an immutable DTO:

~~~java
public record SearchQuery(String term, Integer page) {
}
~~~

the handler can be written as:

~~~java
@GetMapping("/search-record")
public SearchQuery search(
        @ModelAttribute SearchQuery query) {
    return query;
}
~~~

This is an illustrative handler snippet that must be placed inside a `@RestController`; `SearchQuery` is a separate record. Spring uses the canonical/primary constructor and maps request arguments by matching names. Ensure parameter name metadata is preserved at compile time, typically via the `-parameters` build tool configuration when using regular class constructors; records also retain canonical component information. There is no need to add setters for a record.

Since Spring Framework 6.1, `@BindParam` helps map a request name when it differs from the constructor argument name:

~~~java
public final class SearchCriteria {
    private final String term;

    public SearchCriteria(
            @org.springframework.web.bind.annotation.BindParam("q")
            String term) {
        this.term = term;
    }

    public String getTerm() {
        return term;
    }
}
~~~

With constructor binding, a request `?q=spring` can supply the value for `term`. This is an example of **a separate class**, not part of the main demo below. `@BindParam` is a Spring MVC annotation for constructor binding and does not replace `@RequestParam` on a handler.

**By default, Spring allows both constructor binding and property binding** for eligible model objects. If you want to block all property binding and allow only constructors, you can set `WebDataBinder.setDeclarativeBinding(true)`; security details are in section 9.

### 4.3. Retrieving an existing object from the model

A method-level `@ModelAttribute` can create the DTO beforehand:

~~~java
@ModelAttribute("filter")
public SearchForm createForm() {
    return new SearchForm();
}
~~~

Then the handler receives:

~~~java
@GetMapping("/search")
public String search(@ModelAttribute("filter") SearchForm form) {
    return form.getTerm();
}
~~~

These two snippets are a separate example inside a `@Controller`; do not copy them into the main demo unless needed. Spring retrieves the object named `filter` from the model and binds the request onto it. In server-rendered applications, the object can also be exposed to the view to re-display user-entered values when errors occur.

That does **not** mean prior data in the object is always preserved: bound request fields will overwrite existing values; binding onto a domain entity can be dangerous if sensitive properties are inadvertently exposed.

## 5. Complete Spring Boot example: GET query and POST form with the same DTO

The example consists of three files in package `com.example.binding`, using **Java 17+**, Spring Boot 3.x, the Spring MVC Servlet stack, and Jakarta Validation. This is a runnable application within a valid Spring Boot project, not a plain JDK program runnable with only `javac`.

### 5.1. Gradle dependencies

In a project that already has the Spring Boot Gradle plugin and dependency version management, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

`spring-boot-starter-web` provides Spring MVC and the embedded web server; `spring-boot-starter-validation` provides Jakarta Validation integration and the appropriate provider. When using Spring Boot 3, import `jakarta.validation.*` instead of mixing legacy `javax.validation.*`.

### 5.2. Input DTO — `SearchForm.java`

Path:

`src/main/java/com/example/binding/SearchForm.java`

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SearchForm {

    @NotBlank
    private String term;

    @NotNull
    @Min(1)
    private Integer page = 1;

    private String sort = "relevance";

    public SearchForm() {
    }

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }

    public String getSort() {
        return sort;
    }

    public void setSort(String sort) {
        this.sort = sort;
    }
}
~~~

**Mapping explanation:**

- `term=java` → calls `setTerm("java")`.
- `page=2` → converts string `"2"` to `Integer 2` and calls `setPage(2)`.
- Omitting `page` → keeps the default `1` on the new JavaBean.
- Omitting `sort` → keeps the default `"relevance"`.
- `@NotBlank`, `@NotNull`, and `@Min(1)` are enforced only when a validator is invoked, such as via `@Valid` on the handler parameter.

This DTO is designed **specifically for request data**. It has no permission fields, internal identifiers, or admin flags.

### 5.3. Controller — `SearchController.java`

Path:

`src/main/java/com/example/binding/SearchController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class SearchController {

    @InitBinder("filter")
    public void configureFilterBinder(WebDataBinder binder) {
        binder.setAllowedFields("term", "page", "sort");
    }

    @GetMapping("/search")
    public ResponseEntity<SearchResult> search(
            @Valid @ModelAttribute("filter") SearchForm form,
            BindingResult errors) {
        return makeResult(form, errors);
    }

    @PostMapping(
        path = "/submit",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<SearchResult> submit(
            @Valid @ModelAttribute("filter") SearchForm form,
            BindingResult errors) {
        return makeResult(form, errors);
    }

    private ResponseEntity<SearchResult> makeResult(
            SearchForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            SearchResult invalid = new SearchResult(
                false, null, null, null, errors.getErrorCount());
            return ResponseEntity.badRequest().body(invalid);
        }

        SearchResult valid = new SearchResult(
            true, form.getTerm(), form.getPage(), form.getSort(), 0);
        return ResponseEntity.ok(valid);
    }

    public record SearchResult(
        boolean valid,
        String term,
        Integer page,
        String sort,
        int errorCount
    ) {
    }
}
~~~

There are five key points:

1. `@GetMapping("/search")` and `@PostMapping("/submit")` accept **the same `SearchForm` type**, whether the data source is a query string or a form body.
2. `@ModelAttribute("filter")` assigns the object name in the model; the request fields themselves are still named `term`, `page`, `sort`.
3. `@InitBinder("filter")` restricts **property binding** on this attribute to those exact three fields. It does not change formatting, does not validate by itself, and does not eliminate the need for a safe DTO.
4. `@Valid` triggers Bean Validation after binding. `BindingResult errors` is placed **immediately after** `SearchForm form` so the handler can inspect errors.
5. When there are errors, the controller returns HTTP 400 with the error count. When the data is valid, it returns HTTP 200 with a JSON result DTO. `@RestController` is used to focus on the binding mechanism without needing a template engine.

Why place `BindingResult` immediately after `@ModelAttribute`? Because Spring associates binding/validation results with each object argument by position. Placing another parameter in between breaks the handler argument contract for inline error handling.

### 5.4. Application entry point — `BindingDemoApplication.java`

Path:

`src/main/java/com/example/binding/BindingDemoApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

All files reside in the same package, so Spring Boot component scanning from the main package picks up `SearchController`.

### 5.5. Running and testing via HTTP

In the Gradle project directory containing the wrapper and Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Send a GET request with query parameters:

~~~bash
curl -i "http://localhost:8080/catalog/search?term=java&page=2&sort=recent"
~~~

Expected **HTTP 200**, with a JSON response containing these values (JSON key order is not part of the contract):

~~~json
{
  "valid": true,
  "term": "java",
  "page": 2,
  "sort": "recent",
  "errorCount": 0
}
~~~

Send a POST request with a URL-encoded form:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/submit" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "term=spring" \
  --data-urlencode "page=3"
~~~

Expected **HTTP 200** with JSON having `term="spring"`, `page=3`, `sort="relevance"`, and `errorCount=0`. Because `sort` was not sent, the JavaBean keeps its default value.

Data violating constraints:

~~~bash
curl -i "http://localhost:8080/catalog/search?term=%20%20&page=0"
~~~

Expected **HTTP 400** with:

~~~json
{
  "valid": false,
  "term": null,
  "page": null,
  "sort": null,
  "errorCount": 2
}
~~~

`term` contains only whitespace, violating `@NotBlank`; `page=0` violates `@Min(1)`. `@NotNull` still passes because the value is `0`, so there are exactly two errors. The output only reports the **error count**, independent of the order of interpolated messages.

If the request sends `page=abc`, the binder cannot convert the string to `Integer`, resulting in a **binding/type mismatch error**. `BindingResult` lets the controller handle that error without letting the application throw an unhandled exception. The exact error count when combining a type mismatch with other constraints depends on the data and binding behavior; do not assume a value for a field that failed conversion.

### 5.6. Corresponding HTML form

A browser can submit a form as follows:

~~~html
<form action="/catalog/submit" method="post">
  <label>
    Keyword:
    <input type="text" name="term" required>
  </label>

  <label>
    Page:
    <input type="number" name="page" min="1" value="1">
  </label>

  <label>
    Sort:
    <select name="sort">
      <option value="relevance">Relevance</option>
      <option value="recent">Most recent</option>
    </select>
  </label>

  <button type="submit">Search</button>
</form>
~~~

The current REST controller example returns JSON, so a browser will display JSON after submission. If you want to re-render an HTML view, use `@Controller` and a template engine such as Thymeleaf with the same binding principles, returning a view name and keeping errors/objects in the model. HTML attributes like `required`/`min` only assist client-side UX; validation must still run on the server because HTTP clients can send arbitrary requests.

## 6. `BindingResult`: type conversion errors vs validation errors

Two common error sources:

| Error source | Example | Indicator |
|---|---|---|
| **Binding/conversion** | `page=abc` while `page` is `Integer` | `typeMismatch` and corresponding error in `BindingResult` |
| **Bean Validation** | `page=0` violates `@Min(1)` | Constraint violation translated into field/object errors |
| **Both** | `page=abc`, `term` blank | Can have both a binding error on `page` and a validation error on `term` |
| **Disallowed field** | Request attempts to send a field rejected by the allowlist | Observable via `getSuppressedFields()`; do not assume it is a constraint violation |

Example of detailed error handling inside a controller:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        System.out.println(
            fieldError.getField() + ": " + fieldError.getCode());
    }
}
~~~

The snippet above is a **snippet inside a handler** that already has the `errors` variable, not a standalone Java class. `getFieldErrors()` can return errors for multiple fields; the return order and messages can vary by provider/locale, so do not write tests that depend on pre-translated message strings.

When a handler does not declare `BindingResult`/`Errors` immediately after the model attribute, Spring MVC typically handles binding/validation failure via an exception, commonly `MethodArgumentNotValidException`. If the handler itself also has direct parameter constraints leading to **method validation** in Spring MVC 6.1+, the exception type may be `HandlerMethodValidationException`. Do not lump every scenario into a single fixed exception type.

### Differences between `@Valid` and `@Validated`

- `@Valid` (`jakarta.validation.Valid`) triggers validation for the default group and supports cascading onto nested beans.
- `@Validated` (`org.springframework.validation.annotation.Validated`) is a Spring annotation that allows selecting validation groups such as `@Validated(Create.class)`.
- Annotations like `@NotBlank`, `@Min`, `@Size` on a DTO are **constraint declarations**.
- `@ModelAttribute` by itself is primarily for binding; binding does not imply automatically checking all constraints without an appropriate activation mechanism.

For nested DTOs, you can declare:

~~~java
public class AddressForm {
    @jakarta.validation.constraints.NotBlank
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class CustomerForm {
    @jakarta.validation.Valid
    private AddressForm address = new AddressForm();

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }
}
~~~

These are two **separate illustrative classes**; place each public class in a Java file of the same name. A request `address.city=Hanoi` can be bound by Spring's property binder onto the nested `address` object; `@Valid` on the `address` field enables the provider to cascade validation into `AddressForm.city` when the top-level object is validated. If a nested object has constraints but lacks cascading, do not assume top-level validation will recurse into it.

## 7. Type conversion and data formatting

HTTP parameters are inherently strings. `WebDataBinder` uses `ConversionService`, converters, formatters, and sometimes configured property editors to convert them into suitable Java types.

Examples:

| Request field | Java property | Mechanism |
|---|---|---|
| `page=12` | `Integer page` | String → Integer |
| `active=true` | `Boolean active` | String → Boolean |
| `sort=RECENT` | `SortMode sort` (enum) | String → Enum by matching name |
| `from=2026-11-06` | `LocalDate from` with `@DateTimeFormat(iso=ISO.DATE)` | Date formatter |
| `tags=java&tags=spring` | `List<String> tags` | Multi-value binding to collection when type fits |
| `address.city=Hanoi` | nested property `address.city` | Property path traversal and nested object access |

LocalDate example:

~~~java
@org.springframework.format.annotation.DateTimeFormat(
    iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE
)
private java.time.LocalDate from;
~~~

This is an illustrative field to place inside a DTO with matching getter/setter or constructor binding. When a request sends `from=2026-11-06`, Spring's configured formatter converts it into `LocalDate`. If the value cannot be converted, it is a binding error; do not rely on `@NotNull` in place of handling type mismatches.

If you want to convert a custom string to a value object, register a `Converter<String, T>` or `Formatter<T>` with `ConversionService`; during form binding, Spring will use the corresponding conversion mechanism. Do not repeatedly parse strings manually in every controller just because a field has a non-String type.

### Collections and nested paths

A form can send:

~~~text
items[0].name=Book
items[0].quantity=2
items[1].name=Pen
items[1].quantity=5
~~~

The binder can process indexed property paths when the DTO declares a collection structure and supports instantiating corresponding elements. Constructor binding also supports indexed arguments for certain container types. Limits such as the auto-grow collection limit and nested object creation rules must be controlled; do not assume any arbitrary index will be instantiated safely. For complex payloads with deeply nested arrays/maps, JSON with `@RequestBody` may be a better choice for a clearer API contract.

## 8. `@ModelAttribute` on methods and the role of the Spring Model

`@ModelAttribute` can appear in several places that must be distinguished:

### 8.1. On a handler parameter: bind object

~~~java
@PostMapping("/save")
public String save(@ModelAttribute("profile") ProfileForm form) {
    return "result";
}
~~~

This snippet illustrates a `@Controller` handler returning a **view name**, not a REST endpoint. Spring retrieves or creates the attribute named `profile` and binds the request onto it.

### 8.2. On a model-initialization method

~~~java
@ModelAttribute("sortOptions")
public java.util.List<String> sortOptions() {
    return java.util.List.of("relevance", "recent");
}
~~~

Inside a `@Controller`, Spring typically invokes this kind of `@ModelAttribute` method **before `@RequestMapping` handlers** to populate data in the model. A similar method in `@ControllerAdvice` can share data across multiple controllers. The `sortOptions` list is suitable for form options; it does not mean the request automatically binds into that list.

A method can also return the form object itself:

~~~java
@ModelAttribute("profile")
public ProfileForm loadProfile() {
    return new ProfileForm();
}
~~~

Then `@ModelAttribute("profile") ProfileForm form` in the handler uses the existing object. When loading an entity with real data for editing, **do not** hand the entire entity directly to the property binder if the entity contains sensitive fields.

### 8.3. On a handler return value

In an HTML controller, `@ModelAttribute` on a handler method can indicate that the return value should be treated as a model attribute rather than written directly to the HTTP response. `@RestController`/`@ResponseBody` handles the return value as a response body through a different mechanism; determine the controller type before inferring the behavior:

~~~java
@GetMapping("/profile")
@ModelAttribute("profile")
public ProfileForm profile() {
    return new ProfileForm();
}
~~~

This example is for use in a `@Controller` and requires a view selection/rendering mechanism to render the model as HTML. It does not behave like `@RequestBody`.

### 8.4. When you only want to read a model attribute without binding

You can use:

~~~java
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountService.findById(id);
}

@PostMapping("/account/{id}/activate")
public String activate(
        @ModelAttribute(value = "account", binding = false)
        Account account) {
    accountService.activate(account);
    return "redirect:/accounts";
}
~~~

This is an illustrative snippet inside a controller with an `accountService` bean; it is not a standalone runnable class. `binding = false` tells Spring **not to bind request values onto that object**, which is useful when you want the handler to receive a freshly loaded entity without letting an HTTP form modify the entity's fields. If editing is actually intended, accept a separate DTO and deliberately apply only approved fields onto the entity.

### 8.5. `@SessionAttributes` and multi-step forms

In some server-rendered workflows, class-level `@SessionAttributes("profile")` allows a model attribute to be kept in the HTTP session across related requests; upon completion, `SessionStatus.setComplete()` must be called to clear that workflow attribute. `@SessionAttributes` is a controller-level model/session mechanism, distinct from `@SessionAttribute` which reads an existing session attribute. Do not assume `@ModelAttribute` persists to the session by default.

## 9. Data binding security: do not bind directly to domain entities

### 9.1. The mass assignment / over-posting problem

Suppose an entity has:

~~~java
public class Account {
    private String displayName;
    private boolean administrator;

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public void setAdministrator(boolean value) {
        this.administrator = value;
    }
}
~~~

If a handler accepts `@ModelAttribute Account account` directly and allows default property binding, an HTTP client can try sending:

~~~text
displayName=Alice&administrator=true
~~~

If matching fields/constructors/properties are unrestricted, the binder can write to the administrator property that business logic never intended users to change. **Do not use a request DTO identical to a domain entity just to save a mapping step.** Designing a DTO containing only allowed input fields and mapping it to the entity in the service layer is the safe default path.

### 9.2. `@InitBinder` with `setAllowedFields`

In the main demo we had:

~~~java
@InitBinder("filter")
public void configureFilterBinder(WebDataBinder binder) {
    binder.setAllowedFields("term", "page", "sort");
}
~~~

`allowedFields` is the set of **property paths permitted for property binding**; this is an allowlist, which is clearer and more effective than setting `disallowedFields` and trying to remember every sensitive field. Choose a minimal list tailored to the form. Scoping it via `@InitBinder("filter")` applies it only to the matching model attribute name, avoiding unintended changes to other objects in the controller.

Key distinctions:

- `setAllowedFields` primarily limits **property binding**. It is neither user authorization nor validation of received data.
- **Constructor binding** has its own constructor argument selection rules; use dedicated DTOs/constructors containing only approved inputs to prevent unintended request binding.
- Suppressed fields can be inspected via `BindingResult.getSuppressedFields()`; depending on application policy, attempting to send disallowed fields can be treated as a request to reject or log for monitoring.
- Do not assume that omitting an input in HTML prevents a client from sending that key; clients can craft requests manually.

### 9.3. `setDeclarativeBinding(true)` for constructor-only binding

Spring Framework 6.1+ supports:

~~~java
@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

When `declarativeBinding` is enabled, Spring prefers **constructor binding**; **property binding is disabled by default** unless you explicitly declare `allowedFields`. This is a good choice for records or immutable DTOs that only have the constructor arguments needed for the request. Do not copy this snippet into the mutable `SearchForm` demo without updating the design, because the main example relies on setters; if you enable constructor-only mode with a no-arg constructor, form fields `term` and `page` will not be populated as intended.

### 9.4. Recommended defensive steps

1. Build **dedicated request DTOs** exposing only approved fields.
2. Prefer immutable constructor binding for inputs where it fits.
3. If using mutable bean/property binding, restrict allowed fields and review bindable nested/indexed paths.
4. Validate data types and constraints; enforce authorization in the business/service layer.
5. Copy only permitted fields from the DTO to the entity after validation; do not use the request directly to replace an existing object.
6. For stateful/session forms, understand the exact origin of the model object to avoid accidentally binding onto an entity or state unrelated to the request.

Data binding security is about **which object is created, which fields can be modified, and who is authorized to modify them**, beyond simply whether `@Valid` is present.

## 10. When to choose `@RequestParam`, `@ModelAttribute`, or `@RequestBody`?

| Scenario | Common choice | Explanation |
|---|---|---|
| One or two simple query params | `@RequestParam` | Clear and concise |
| HTML form submitting multiple inputs | `@ModelAttribute` | Groups and binds inputs into a form object |
| GET endpoint with multi-field filters | `@ModelAttribute` | DTO provides type conversion and validation |
| REST API receiving JSON | `@RequestBody` | Uses HTTP message converters/Jackson |
| HTML form submission with errors needing re-rendering | `@Valid @ModelAttribute` + `BindingResult` | Provides both object and errors for the view |
| File upload alongside form fields | `@ModelAttribute` DTO with `MultipartFile` when multipart is configured | Form binding uses multipart infrastructure |
| Handler only needs a loaded entity, no further binding | `@ModelAttribute(binding=false)` | Prevents request from mutating entity via property binding |
| An identifying path segment | `@PathVariable` | Data comes from the URI template |

A request with a JSON body `{"term":"java","page":2}` and Content-Type `application/json` is **not** handled by `@ModelAttribute` by automatically invoking Jackson to deserialize JSON. For typical JSON bodies:

~~~java
@PostMapping(
    path = "/search-json",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public SearchResult searchJson(
        @Valid @RequestBody SearchRequest request) {
    // Process the DTO deserialized from JSON.
}
~~~

This is an illustrative snippet; it requires `SearchRequest` and `SearchResult` classes and is not part of the runnable main demo code. `@RequestBody` uses message converters, whereas `@ModelAttribute` uses a binder to create/populate a model object. Both can be combined with `@Valid`, but they follow different input-processing paths.

## 11. Testing with MockMvc

A curl smoke test confirms the HTTP endpoint works; an integration test with `MockMvc` automatically verifies Spring's query/form binding, type conversion, and error recording. In a Boot 3 project you can add:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Save the file:

`src/test/java/com/example/binding/SearchControllerTest.java`

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SearchControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void queryParametersPopulateObject() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", "java")
                .param("page", "2")
                .param("sort", "recent"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.valid").value(true))
            .andExpect(jsonPath("$.term").value("java"))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.sort").value("recent"))
            .andExpect(jsonPath("$.errorCount").value(0));
    }

    @Test
    void formBodyPopulatesObject() throws Exception {
        mvc.perform(post("/catalog/submit")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("term", "spring")
                .param("page", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.term").value("spring"))
            .andExpect(jsonPath("$.page").value(3))
            .andExpect(jsonPath("$.sort").value("relevance"));
    }

    @Test
    void beanValidationErrorsAreCaptured() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", " ")
                .param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.valid").value(false))
            .andExpect(jsonPath("$.errorCount").value(2));
    }

    @Test
    void typeMismatchIsABindingError() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", "java")
                .param("page", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.valid").value(false));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Or on Windows:

~~~powershell
.\gradlew.bat test
~~~

With Spring Boot 3.x and the Web and Validation starters, these tests are expected to **PASS**. They verify request mapping and binding through HTTP simulation instead of manually calling setters. `MockMvc.param(...)` simulates request parameters; in the POST test, Content-Type is set to `application/x-www-form-urlencoded` to match the form endpoint.

If a real application includes Spring Security, CSRF, or custom filters, POST tests may require additional setup; the demo project only includes Web + Validation.

### Adding a test for the allowlist

If a sensitive setter is accidentally added to the DTO in the future, there should be a test verifying that a request field outside `allowedFields` does not modify that property. `BindingResult.getSuppressedFields()` can help observe rejected fields. The demo model only has three public fields so it is safer by design; use the allowlist as an additional layer of restriction.

## 12. Common errors and how to diagnose them

| Symptom | Common cause | How to check/fix |
|---|---|---|
| Controller receives an object but all properties are `null` | Request keys do not match, missing setters, constructor-only enabled on a mutable bean, or JSON body sent to `@ModelAttribute` | Check Content-Type, DTO constructor/setters, `@InitBinder`, and field names |
| `page` remains `1` even when `page=2` is sent | Field is not bound or blocked by allowlist | Check `setAllowedFields`, request key name, and setter |
| `page=abc` causes an error | Cannot convert string to integer | Read `BindingResult`, return HTTP 400 with structured errors |
| `@NotBlank` does not report an error | Validation not triggered or provider missing | Add `@Valid`/`@Validated` in the right place and Validation starter |
| Errors occur but handler does not run | `BindingResult` not declared immediately after attribute or MVC takes the exception path | Place `BindingResult` properly or use `@ControllerAdvice` |
| JSON body sent but `SearchForm` has no values | `@ModelAttribute` does not deserialize JSON via Jackson | Choose `@RequestBody` for JSON |
| Request field `filter.term` does not bind as expected | Confusing model attribute name with request key prefix | Simple form uses `term=...`, `page=...` |
| Sensitive field gets modified | Direct binding to a domain entity with setters or uncontrolled constructor inputs | Use a request DTO, allowlist, or constructor-only binding where appropriate |
| Nested field like `address.city` is not populated | Nested object or writable property path is invalid | Check classes, getters/setters, constructors, and binder limits |
| Field error even though user sent a valid date | Incompatible date formatter/locale | Use `@DateTimeFormat` or an appropriate converter/formatter |
| `@InitBinder("filter")` does not run as expected | Actual model attribute has a different name | Match `@ModelAttribute("filter")` name and binder scope |
| Form POST returns `415 Unsupported Media Type` | Handler requires `application/x-www-form-urlencoded` but client sends another type | Fix Content-Type or choose an appropriate handler |
| BindingResult still has errors despite setting a default | Request supplies an invalid value or fails a constraint | Distinguish defaults for missing keys from present but invalid keys |
| Using a record results in empty binding | Missing constructor parameter names/annotation mapping, or Spring version lacks expected support | Check Spring version, Java bytecode parameter metadata, and `@BindParam` |
| Template re-renders form incorrectly | Model attribute name mismatch between controller and template | Use explicit names and keep `BindingResult`/model aligned |
| Multi-step form loses the object | Appropriate session model mechanism not used | Consider `@SessionAttributes` and `SessionStatus.setComplete()` |
| Native image run fails on reflection binding | Implicit model attribute lacks sufficient AOT hints | Add explicit `@ModelAttribute` and verify native configuration |

Practical debugging workflow: **HTTP method/Content-Type → request parameter names → attribute name/object origin → constructor or setter → `WebDataBinder`/allowlist/converter → `BindingResult` → Bean Validation → handler logic**. Do not modify the DTO or randomly add `@Autowired` if the actual cause is sending JSON to a form binder.

## 13. Real-world scenarios for choosing the right binding approach

### Search filters with GET

GET queries make sense when users want to copy URLs, bookmark pages, or create links with filter state. `@ModelAttribute SearchForm` groups multiple fields, but avoid putting sensitive information in queries because URLs can appear in browser history and logs. Enforce page/size/sort limits on the server and use clear defaults.

### Data creation forms with POST

URL-encoded POST forms are the traditional submission style for HTML forms. `@ModelAttribute` receives the DTO; `@Valid` and `BindingResult` report errors. In server-rendered HTML apps, the controller typically returns the view when errors exist and calls the service only after the form is valid.

### Editing an existing object in the database

Do not load a full entity and arbitrarily bind request fields onto it. Use a dedicated DTO, verify the user has permission to edit, and then copy valid fields onto the entity inside a service/transaction. If you need to pass a loaded entity to the handler as read-only data, `@ModelAttribute(binding=false)` is useful.

### Forms with collections or nested objects

Use property names like `address.city` or `items[0].name` if the DTO and binder permit them. Check depth/index limits and allowlists; do not let clients dictate the entire object graph of a domain model.

### APIs receiving JSON

Use `@RequestBody` and a type-safe DTO; do not force a form binder to handle JSON just because a DTO shares the same fields. Both `@ModelAttribute` and `@RequestBody` can use Bean Validation, depending on the endpoint's data source and contract.

## 14. Self-check questions

**1. Can request `GET /search?term=java&page=2` bind into `@ModelAttribute SearchForm`?**

Yes, provided the DTO has compatible constructor/property binding and request keys match input names; Spring converts `page` to the appropriate Java type.

**2. Why does `@ModelAttribute("filter")` not require the request to send `filter.term=java`?**

`filter` is the object's name in the Spring model. The binder uses request parameter names like `term` to map to the corresponding properties or constructor arguments.

**3. Does sending `Content-Type: application/json` with body `{"term":"java"}` automatically go through `@ModelAttribute`?**

Not via standard JSON deserialization. Use `@RequestBody` for JSON bodies.

**4. Does `@ModelAttribute` automatically check `@NotBlank` on a DTO?**

Binding does not mean validation. Add `@Valid` or `@Validated` appropriately, ensure a validation provider is present, and handle errors via `BindingResult` or an exception.

**5. Why must `BindingResult` be placed immediately after the model attribute?**

So Spring binds errors to the exact handler object argument. Inserting another parameter in between violates the inline error-handling signature contract.

**6. With `page=abc` when the Java field is `Integer`, what kind of error is this?**

A type conversion error during binding. `BindingResult` can hold a corresponding field error, independent of `@Min` logic.

**7. A DTO has setter `setAdministrator(boolean)`, but the form does not render an admin input. Is that safe enough?**

No. A client can still manually send the key `administrator=true`. You need a properly scoped DTO, an allowlist or controlled constructor binding, and authorization checks in the service layer.

**8. How does `setDeclarativeBinding(true)` affect a mutable JavaBean that only has a no-arg constructor and setters?**

Property binding no longer runs by default unless allowed fields are declared; data may not be populated into setters as before. You must choose a DTO/constructor compatible with that mode.

**9. When should `@ModelAttribute(binding=false)` be used?**

When an object is already in the model and the controller only needs to access it without allowing the request to modify its properties.

**10. Why should tests use MockMvc instead of just calling `new SearchForm(); form.setPage(2);`?**

Manual setters do not test Spring MVC's argument resolver, HTTP parameter parsing, type conversion, binder rules, Bean Validation, or `BindingResult`.

## 15. Implementation checklist for `@ModelAttribute`

- [ ] Determine whether the endpoint receives query/form parameters or JSON to choose `@ModelAttribute` or `@RequestBody`.
- [ ] Choose a DTO containing only allowed input fields; verify constructors, parameter names, setters, or record binding.
- [ ] Set `@ModelAttribute("name")` explicitly if a stable name or native-image/AOT hints are needed.
- [ ] For HTML forms/GET queries, verify input `name` attributes match DTO properties or constructor arguments.
- [ ] Check `ConversionService`, `Formatter`, enum/date conversion, and nested field paths.
- [ ] Enable Bean Validation if needed: `@Valid`/`@Validated`, provider, and constraints on the DTO.
- [ ] Place `BindingResult` immediately after the attribute if the handler should process binding/validation errors itself.
- [ ] With property binding, restrict `allowedFields` or use constructor-only/declarative binding when appropriate.
- [ ] Do not bind directly to entities containing sensitive fields; map DTO to entity in the service layer after authorization.
- [ ] Test GET queries, URL-encoded POSTs, missing inputs, wrong-type inputs, invalid constraints, and requests with disallowed fields.
- [ ] If returning HTML, verify model names, view rendering, and re-displaying field errors.
- [ ] If a multi-step form uses session model state, clean up `@SessionAttributes` upon completion.

**Key takeaway:** `@ModelAttribute` retrieves **an object** from the Spring MVC model and binds **query/form** data via `WebDataBinder`; constructor/property binding converts HTTP values into Java types. `@Valid`/`@Validated` adds data checks, `BindingResult` holds errors, and DTOs/allowed fields protect which data can be modified. For JSON bodies, the primary mechanism is `@RequestBody`.

## Official references

- [Spring MVC — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — @ModelAttribute methods to initialize the model](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html)
- [Spring MVC — @InitBinder and model design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
