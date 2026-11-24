# Spring MVC — @ModelAttribute and Form Data Binding

## 1. Objectives

After this lesson, you will be able to:

- Explain `@ModelAttribute` on a **controller parameter**: retrieve/create a model object and bind HTTP request values to Java properties.
- Receive HTML forms (`application/x-www-form-urlencoded`) and query parameters without reading each field individually via `@RequestParam`.
- Understand JavaBean/property binding, constructor binding, nested properties, lists, and type conversion.
- Combine `@Valid` or `@Validated` with `BindingResult` to handle input errors.
- Distinguish `@ModelAttribute` on a **parameter** vs on a **method**; distinguish `@ModelAttribute`, `@RequestParam`, and `@RequestBody`.
- Restrict which fields are allowed to bind to prevent clients from modifying unintended properties.

Context: **Spring MVC (Servlet stack)**, Java 17+; practical examples use Spring Boot 3.5.0 and Spring Framework 6.2.x. Do not confuse MVC mechanisms with Spring WebFlux.

## 2. From an HTML form to a Java object

A form sends a request like this:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan%20Nguyen&email=lan%40example.com&age=22&address.city=Da%20Nang&interests=java&interests=spring
~~~

The body contains `name=value` pairs and can repeat the `interests` key. In Spring MVC, Servlet request parameters include both the **query string** and **form data** decoded by the Servlet container; therefore Spring can use them to populate an object:

~~~java
@PostMapping("/register")
public String register(@ModelAttribute("registration") RegistrationForm form) {
    // form.getFullName(), form.getAge(), form.getAddress()...
    return "success";
}
~~~

This snippet only illustrates the handler signature; for a standalone runnable project, see section 8.

Typical **processing flow**:

1. Spring MVC selects the handler based on URL, HTTP method, and mapping conditions.
2. Spring looks up the model attribute named `registration` (if already present in the model/session per configuration) or creates a new instance.
3. `WebDataBinder` extracts request data, binds to constructor arguments or writable properties, and converts strings to Java types.
4. If `@Valid`/`@Validated` is present, Spring runs validation after binding.
5. Spring passes the object and error results (if the controller declares `BindingResult`) to the handler.
6. The handler decides whether to return a view, a redirect, or an HTTP response.

Under modern Spring MVC mechanics, bound values can come from request parameters, URI path variables, and headers. On name collisions, request parameters take precedence over path variables/headers; hyphenated header names are normalized per binder rules. For ordinary forms, focus on field names and request parameters, and avoid implicitly relying on other sources.

## 3. Designing a form object following JavaBean rules

~~~java
public class ProfileForm {
    private String displayName;
    private Integer age;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Handler:

~~~java
@PostMapping("/profiles")
public String save(@ModelAttribute("profile") ProfileForm form) {
    // The displayName and age fields have been bound.
    return "profile-success";
}
~~~

HTML form:

~~~html
<form method="post" action="/profiles">
  <label>Name <input type="text" name="displayName"></label>
  <label>Age <input type="number" name="age"></label>
  <button type="submit">Save</button>
</form>
~~~

`name="displayName"` matches property `displayName`; `name="age"` matches `age`. With JavaBean-based property binding, setters give Spring a way to assign values. Typically, Spring instantiates the object via its no-arg constructor and then invokes matching setters; Spring also supports **constructor binding** based on constructor parameter names. Both strategies can participate in binding under default configuration.

Do not assume that the `@ModelAttribute` annotation automatically creates database tables or saves user data: it only prepares the object in the request/model. Business operations and persistence belong in the service/repository layer.

### 3.1. What does the model attribute name mean?

`@ModelAttribute("profile")` sets the attribute name to `profile`. This name is used to look up/place the object in the model, target `@InitBinder("profile")`, and attach the object's `BindingResult`. The **bound property names** remain `displayName`, `age`, etc.; HTML inputs do not need a `profile.` prefix when binding this top-level object.

If the name is not specified, Spring can infer it from the object type, e.g., `ProfileForm` → `profileForm`. Use an explicit name when view structures and binders need consistency. For complex parameters not handled by another argument resolver, Spring MVC may implicitly treat them as `@ModelAttribute`; declaring it explicitly improves clarity and is safer for native/AOT applications.

## 4. Nested fields, lists, and type conversion

Suppose a form class:

~~~java
public class OrderForm {
    private Customer customer = new Customer();
    private List<String> tags = new ArrayList<>();

    public Customer getCustomer() { return customer; }
    public void setCustomer(Customer customer) { this.customer = customer; }
    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }

    public static class Customer {
        private String name;
        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
    }
}
~~~

Requires importing `java.util.ArrayList` and `java.util.List`. Corresponding form data:

~~~text
customer.name=Lan
tags=java
tags=spring
~~~

- `customer.name`: nested property path, populated into `orderForm.getCustomer().getName()`.
- Two `tags` fields: Spring can receive multiple values for the same key and convert them into `List<String>`.
- For object elements inside a list, syntax like `items[0].name` can be supported by the binder if the object structure, writability, and configuration allow it; avoid generating excessively large indices from untrusted data.

A curl example:

~~~bash
curl --get 'http://localhost:8080/orders/preview' \
  --data-urlencode 'customer.name=Lan' \
  --data-urlencode 'tags=java' \
  --data-urlencode 'tags=spring'
~~~

The command above illustrates **how to send request parameters**; the `/orders/preview` endpoint is not implemented in the sample application in section 8.

### 4.1. Type conversion

Data binding uses Spring's data conversion mechanism:

| Request parameter | Java property | Typical result |
| --- | --- | --- |
| `age=22` | `Integer age` | Integer `22` |
| `active=true` | `Boolean active` | `true` |
| `birthDate=2026-05-01` | `LocalDate birthDate` with `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` | Date `2026-05-01` |
| `age=abc` | `Integer age` | Type mismatch error, recorded in binding errors |
| `address.city=Hue` | Nested property `address.city` | `address.getCity() == "Hue"` if object/binder permit |

Date example:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate birthDate;
~~~

Requires importing `java.time.LocalDate` and `org.springframework.format.annotation.DateTimeFormat`. For custom formats or domain types, register an appropriate `Converter`, `Formatter`, or configure `ConversionService`. Type conversion and **validation** are two separate steps: `age=abc` is a conversion error; `age=17` converts successfully but violates a minimum-age constraint.

## 5. @ModelAttribute and validation with BindingResult

When a DTO has Bean Validation constraints:

~~~java
public class SignUpForm {
    @NotBlank
    private String username;

    @Email
    @NotBlank
    private String email;

    // Constructor, getters, setters per JavaBean...
}
~~~

A controller can receive both the object and errors directly in the same handler:

~~~java
@PostMapping("/signup")
public String signup(
        @Valid @ModelAttribute("signUp") SignUpForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "signup-form";
    }
    return "signup-success";
}
~~~

`SignUpForm` and the views in this snippet are illustrative; the complete runnable version is in section 8.

**Mandatory rule:** `BindingResult` (or `Errors`) must **immediately follow** the `@ModelAttribute` argument it represents. Do not place `Model`, `@RequestParam`, or other parameters in between. The following example has the wrong order:

~~~java
// Wrong: Model placed between the validated object and BindingResult.
public String signup(@Valid @ModelAttribute("signUp") SignUpForm form,
                     Model model,
                     BindingResult errors) { /* ... */ }
~~~

When declared adjacently, the handler can read both conversion errors and validation errors. If there is no `BindingResult` to handle them, argument resolution can throw `MethodArgumentNotValidException`; when method-level validation applies, the exception type may differ (such as `HandlerMethodValidationException`). Do not assume every form error automatically returns the same string or JSON structure: how responses are returned depends on the application's exception handling.

Useful `BindingResult` APIs:

- `hasErrors()`: are there any errors?
- `hasFieldErrors("email")`: does the `email` field specifically have errors?
- `getFieldErrors()`: list of field-level errors.
- `getFieldValue("age")`: value recorded by the binder for the field (may be the rejected value).
- `getSuppressedFields()`: fields suppressed by the binder when field restrictions are configured.

### 5.1. In an HTML interface

Example flow using a view template:

~~~java
@Controller
@RequestMapping("/signup")
class SignupPageController {
    @GetMapping
    String showForm(Model model) {
        model.addAttribute("signUp", new SignUpForm());
        return "signup-form";
    }

    @PostMapping
    String submit(@Valid @ModelAttribute("signUp") SignUpForm form,
                  BindingResult errors) {
        if (errors.hasErrors()) {
            return "signup-form";
        }
        return "redirect:/signup/success";
    }
}
~~~

To run this snippet, you need the full `SignUpForm` class, an appropriate view/template engine, the `signup-form` view definition, and the `/signup/success` route. This is a **view-based MVC flow sketch**, not a standalone Java program.

A template engine (such as Thymeleaf) can re-render user-entered data and error messages from the model; in Spring MVC, `BindingResult` is also exposed in the model under a conventional name. Remember to handle CSRF when POSTing from browser forms if the application has Spring Security enabled.

## 6. @ModelAttribute on a method: preparing model data

This annotation has **two roles** to distinguish:

| Placement | Example | Role |
| --- | --- | --- |
| Handler parameter | `submit(@ModelAttribute("profile") ProfileForm form)` | Retrieve/create model object, bind request values into the object |
| Controller or `@ControllerAdvice` method | `@ModelAttribute("countries") List<String> countries()` | Pre-populate data into the model before the handler for view use |
| On a request-handling method | `@ModelAttribute("profile") @GetMapping ...` | Interpret the return value as a model attribute instead of the default return handling |

Model example for a country list:

~~~java
@Controller
class ProfilePageController {
    @ModelAttribute("countries")
    public List<String> countries() {
        return List.of("VN", "SG", "JP");
    }

    @GetMapping("/profiles/new")
    public String show(Model model) {
        model.addAttribute("profile", new ProfileForm());
        return "profile-form";
    }
}
~~~

`countries()` is invoked by Spring MVC to prepare the attribute for eligible handlers in the controller; if wider scope is needed, a similar method can be placed in `@ControllerAdvice`. This snippet requires the classes/views declared in a real application and is not standalone code. Method-level `@ModelAttribute` does not mean sending data directly in the HTTP response; objects in the model are used by the view or handler.

**Important ordering:** A model object may already be created/placed in the model by a `@ModelAttribute` method before the handler parameter is resolved; the controller then proceeds to bind request values into that object if binding is enabled.

### 6.1. Disabling property binding when only retrieving a prepared object

~~~java
@ModelAttribute("account")
public Account findAccount(@PathVariable String accountId) {
    return accountService.getById(accountId);
}

@PostMapping("/accounts/{accountId}/action")
public String action(@ModelAttribute(value = "account", binding = false) Account account) {
    accountService.performAction(account);
    return "redirect:/accounts";
}
~~~

Here `binding = false` indicates that the `account` object is provided but **does not receive property values from the request** via this annotation; this is useful when a domain object was fetched from the DB and you do not want clients modifying its fields. This illustrative snippet requires the `Account` type, service, and corresponding endpoint.

## 7. Data safety: preventing mass assignment / over-posting

Suppose a `User` entity has `name`, `email`, `role`, and `isAdmin`. If you bind requests directly to an entity that has setters for every field, a client can send extra parameters like `role=ADMIN` or `isAdmin=true` even if the HTML form does not display those fields.

**Practical recommendations:**

1. Design a **dedicated form DTO** containing only the fields the client is allowed to provide. After validation, map it to the entity in the service; sensitive fields like `role`, `id`, `owner`, prices, or status come from the server.
2. When using **property binding**, configure `WebDataBinder#setAllowedFields(...)` with the list of fields allowed to be assigned, especially on objects that may expose many setters.
3. With immutable DTOs, you can choose constructor binding and explicitly design which parameters are bound; Spring supports constructor argument names and `@BindParam` when a different parameter name is needed.
4. Always enforce business authorization checks in the service layer; restricting binding alone does not replace authorization.

Restricting property binding by attribute name:

~~~java
@InitBinder("registration")
public void initRegistrationBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "fullName", "email", "age", "address.city", "interests");
}
~~~

`@InitBinder` applies within the controller scope (or via advice configuration) and can configure the binder. `setAllowedFields` restricts setting **properties** via property binding; do not assume it replaces reviewing constructor arguments, authorization checks, or validation. Disallowed fields can be suppressed, and you can inspect `BindingResult#getSuppressedFields()` if tracking is needed.

## 8. Complete runnable example with Spring Boot + Java 17

This small REST application demonstrates form binding, a nested address, an interests list, numeric conversion, validation, and field whitelisting. It returns JSON for quick testing with `curl`, without needing a template engine.

Structure:

~~~text
model-attribute-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ModelAttributeDemoApplication.java
    ├── RegistrationForm.java
    └── RegistrationController.java
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>model-attribute-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 8.2. ModelAttributeDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModelAttributeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelAttributeDemoApplication.class, args);
    }
}
~~~

### 8.3. RegistrationForm.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {
    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    @Valid
    private Address address = new Address();

    private List<String> interests = new ArrayList<>();

    public RegistrationForm() {
    }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }

    public List<String> getInterests() { return interests; }
    public void setInterests(List<String> interests) { this.interests = interests; }

    public static class Address {
        @NotBlank
        private String city;

        public Address() {
        }

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
~~~

Thanks to `@Valid` on `address`, constraints on the nested object are validated. With `Integer age`, `@NotNull` catches a missing field while `@Min(18)` catches ages under 18. Use `jakarta.validation` for Spring Boot 3.x instead of the legacy `javax.validation` package.

### 8.4. RegistrationController.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RegistrationController {
    @InitBinder("registration")
    public void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "email", "age", "address.city", "interests");
    }

    @PostMapping(
            path = "/register",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            List<String> errors = result.getFieldErrors().stream()
                    .map(error -> error.getField() + ": " + error.getDefaultMessage())
                    .toList();
            return ResponseEntity.badRequest().body(Map.of("errors", errors));
        }

        return ResponseEntity.ok(Map.of(
                "fullName", form.getFullName(),
                "email", form.getEmail(),
                "age", form.getAge(),
                "city", form.getAddress().getCity(),
                "interests", form.getInterests()));
    }
}
~~~

**Why does this example work?**

- Spring receives the `application/x-www-form-urlencoded` request body from the Servlet container as request parameters.
- `@ModelAttribute("registration")` creates/retrieves `RegistrationForm`, and the binder populates `fullName`, `email`, `age`, `address.city`, and `interests`.
- `@InitBinder("registration")` restricts which properties can be bound.
- `@Valid` validates the constraints; `BindingResult` immediately after the form tells the controller which fields failed.
- When valid, the `Map` is serialized to JSON by `@RestController` and Jackson provided by `spring-boot-starter-web`.

### 8.5. Running and testing

Requires Java 17+ and Maven; inside the `model-attribute-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Submit a valid form:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan Nguyen' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=22' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'interests=java' \
  --data-urlencode 'interests=spring'
~~~

The returned body has values equivalent to the following JSON (JSON object key order is not guaranteed):

~~~json
{
  "fullName": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 22,
  "city": "Da Nang",
  "interests": ["java", "spring"]
}
~~~

Submit a form violating validation:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=' \
  --data-urlencode 'email=wrong-format' \
  --data-urlencode 'age=17' \
  --data-urlencode 'address.city='
~~~

Expected result: HTTP **400 Bad Request** with JSON containing `errors` (fields such as `fullName`, `email`, `age`, `address.city`). Validation message ordering and language depend on configuration, so do not fixate on exact verbatim strings.

Submit an invalid data type:

~~~bash
curl -i -X POST 'http://localhost:8080/api/register' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=abc' \
  --data-urlencode 'address.city=Hue'
~~~

`age=abc` cannot be converted to `Integer`, so the binder records a `typeMismatch` error; `BindingResult` enables returning HTTP 400 rather than proceeding with an invalid object.

With Windows PowerShell, you can replace `curl` with `curl.exe` and adapt line continuation to PowerShell syntax (for example, writing the entire command on one line); the `\` line continuations above are for Unix shells.

### 8.6. Do not send JSON to an endpoint expecting @ModelAttribute

The following request is **not compatible** with the `/api/register` endpoint above:

~~~http
POST /api/register HTTP/1.1
Content-Type: application/json

{"fullName":"Lan","age":22}
~~~

The endpoint specifies `consumes = application/x-www-form-urlencoded`, so an `application/json` request typically receives HTTP **415 Unsupported Media Type**. If the API requires JSON, change the handler to `@RequestBody RegistrationRequest dto` with `consumes=application/json` and declare an appropriate DTO. Do not equate form binding with JSON deserialization.

## 9. Constructor binding and @BindParam

Modern Spring MVC also supports binding request values directly into constructor parameters, which is useful for immutable objects. Illustrative example (not part of the runnable project in section 8):

~~~java
import org.springframework.web.bind.annotation.BindParam;

public class SearchForm {
    private final String keyword;
    private final int page;

    public SearchForm(@BindParam("q") String keyword,
                      @BindParam("page") int page) {
        this.keyword = keyword;
        this.page = page;
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
}
~~~

A request `?q=spring&page=2` can supply `keyword="spring"` and `page=2` to the constructor. Constructor parameter names must be preserved in bytecode when relying on inferred names; `@BindParam` lets you specify the source name explicitly. When choosing immutable objects, avoid unnecessary setters or property binding. Do not assume `@InitBinder#setAllowedFields` filters all constructor arguments: the two binding forms have different control boundaries.

## 10. Comparing common annotations

| Annotation | Best suited for | Note |
| --- | --- | --- |
| `@RequestParam("page") int page` | A single named query/form parameter | Easy to read for simple inputs |
| `@ModelAttribute("form") FormDto form` | Multiple request fields mapped into an object, including nested/list fields | Includes data binding, conversion, and validation |
| `@RequestBody FormDto form` | JSON/XML body via HTTP message converters | Depends on `Content-Type`, not form-property binding |
| `@PathVariable Long id` | A URL segment such as `/users/42` | Does not replace an entire form |
| `@RequestPart MultipartFile file` | A part of a multipart request, especially files | Can be combined with form fields via multipart handling |

Choose based on the **shape of the HTTP request** and the controller's purpose. For example, registration from an HTML form naturally fits `@ModelAttribute`; a REST API receiving JSON naturally fits `@RequestBody`.

## 11. Common errors and how to fix them

1. **Input name does not match property:** `name="full_name"` does not automatically bind to JavaBean property `fullName`. Use consistent naming or constructor mapping/`@BindParam` when appropriate.
2. **Missing suitable constructor/setters:** With property binding, Spring needs a writable object and accessible properties; with constructor binding, Spring needs to recognize the parameters accurately and convert types.
3. **Nested field is null or cannot be instantiated:** Ensure nested objects have an initialization path, e.g., `private Address address = new Address()`.
4. **Assuming `@Valid` renders UI errors automatically:** `BindingResult` lets you inspect field errors, but the controller/view must decide how to display them.
5. **Placing `BindingResult` away from the form argument:** This can cause a method signature error or fail to attach errors to the right object.
6. **Omitting `spring-boot-starter-validation` in a Boot app:** Without a Bean Validation provider, constraint annotations may not execute as expected.
7. **Sending JSON to a form endpoint:** Check `Content-Type` and `consumes`; use `@RequestBody` for JSON.
8. **Binding domain/persistence entities directly:** Clients can over-post hidden fields. Use explicit DTOs, allowed fields, and authorization in the service layer.
9. **Treating type conversion errors like business rule errors:** `age=abc` is a binding/type mismatch, distinct from `age=17` which converted to a number successfully but failed `@Min(18)`.
10. **Confusing the model with HTTP session:** Model attributes are normally scoped to request processing; only when using `@SessionAttributes` and related rules are they stored across multiple requests in the session.

## 12. Self-check exercises

**Exercise 1 — Form object:** Write `ContactForm` with `name`, `email`, `message`; create a POST handler accepting `@ModelAttribute("contact")`, and identify the three HTML input names to submit.

**Exercise 2 — Nested + list:** Design `BookingForm` with `guest.name` and `preferences` (`List<String>`). Construct HTTP request data with two preferences and explain how Spring populates each field.

**Exercise 3 — Validation:** Add `@NotBlank` to `name` and `@Email` to `email`, declare `@Valid` and `BindingResult` in the right positions; distinguish the errors for `age=abc` vs `age=17` when `@Min(18)` is present.

**Exercise 4 — Security:** Suppose `AccountEntity` has `role` and `balance` alongside `displayName`. Explain why you should not bind the entity directly, and propose an `AccountUpdateForm` and allowed-fields set.

**Exercise 5 — Annotations:** For a client sending `Content-Type: application/json`, choose between `@ModelAttribute` and `@RequestBody`; when would you use `@ModelAttribute` at the method level instead of on a parameter?

*Hints:* Form names match JavaBean properties; nested fields use dots; repeated keys can become lists; `BindingResult` immediately follows the form; DTOs limit client-supplied fields; JSON fits `@RequestBody`.

## 13. Official references

- [Spring Framework — MVC `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html) — retrieving/creating objects, binding, validation, `BindingResult`, constructor binding.
- [Spring Framework — MVC model methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html) — `@ModelAttribute` on methods to prepare model data.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html) — `WebDataBinder` and conversion.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html) — validation/exception rules.
- [Spring Framework — MVC `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html) — configuring binders per controller/advice.
