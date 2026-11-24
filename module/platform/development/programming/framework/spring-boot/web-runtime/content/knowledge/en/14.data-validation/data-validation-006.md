# BindingResult in Spring MVC and Controller Handling Conditions

## 1. Objective and Real-World Scenario

An HTML form can submit an empty username, an improperly formatted email, or a non-numeric age. A Spring MVC application must distinguish data that **cannot bind to Java types**, data that **binds yet violates validation rules**, and data that is **valid for business processing**.

`BindingResult` informs the controller about errors occurring during **data binding** and **validation** of a specific object. This lets the controller decide whether to re-render the form page with error messages, or proceed to save data and redirect when input is valid.

Core example:

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "signup/form";
    }

    return "redirect:/signup/success";
}
```

Two points to remember right away:

1. **`BindingResult` must stand immediately after the parameter it inspects**, here `@Valid @ModelAttribute("signup") SignupForm form`.
2. **`@Valid` does not automatically prevent the controller from running when a valid `BindingResult` sits beside it.** The controller receives the errors and must explicitly branch on `hasErrors()` before calling business logic.

This lesson focuses on the **Spring MVC/Servlet stack**, with examples in Spring Boot **3.5.x**, Java **17**, Thymeleaf, and MockMvc. Spring WebFlux has corresponding binding/validation APIs, but its execution flow differs and MVC details do not automatically apply everywhere.

## 2. Binding, Conversion, and Validation Are Related Yet Distinct Concepts

| Stage | Responsibility | Success Example | Error Example |
|---|---|---|---|
| Data binding | Maps request fields to object properties | `fullName=Lan` → `form.fullName` | Unbound field or mismatched path |
| Type conversion | Converts HTTP strings to property types | `age=25` → `Integer.valueOf(25)` | `age=abc` cannot convert to `Integer` |
| Bean Validation | Checks constraints on the bound object | `age=25` satisfies `@Min(18)` | `age=16` violates `@Min(18)` |
| Business validation | Checks context-dependent business rules | Email does not exist yet, plan is valid | Email already registered, quota exceeded, or access denied |

`BindingResult` can hold **field errors** produced by conversion/binding or Bean Validation, as well as **global errors** relating to the whole object. Business validation can also explicitly add errors via `rejectValue` or `reject` before deciding how to proceed.

Example for the same `age` field:

- `age=abc`: type conversion fails, typically creating a field error with code `typeMismatch`.
- `age=15`: conversion succeeds, but `@Min(18)` fails.
- `age=20`: passes constraints, yet may still violate a business rule such as requiring a higher age for a specific product.

Do not conclude that an object bound successfully is automatically safe to write to the database; nor treat `BindingResult` as a substitute for authentication/authorization.

## 3. How It Works in Spring MVC

For an `application/x-www-form-urlencoded` form:

```text
POST /signup
fullName=Lan&email=lan@example.org&age=25
             |
             v
DispatcherServlet
             |
             v
HandlerMapping -> HandlerAdapter
             |
             v
@ModelAttribute("signup") SignupForm
  - create/retrieve form object
  - WebDataBinder binds request parameters
  - ConversionService converts String -> field types
  - Validator checks constraints if @Valid is present
             |
             v
BindingResult for object "signup"
  - FieldError if a field fails
  - ObjectError if the whole object fails
             |
             v
Controller submit(form, bindingResult)
  - hasErrors() == true -> return "signup/form"
  - hasErrors() == false -> process -> redirect
             |
             v
ViewResolver + Thymeleaf -> HTML / redirect response
```

`WebDataBinder` combines request data, conversion, and validators; results are stored in a `BindingResult` tied to a **specific model attribute name**. When rendering a form, Spring MVC exposes both the object and binding error metadata in the model so the template engine can display them.

**Important condition:** placing a `BindingResult` in the method signature does not by itself enable Bean Validation. You need `@Valid`, `@Validated`, or an explicit validator invocation; meanwhile conversion errors can be recorded during binding even without validation annotations.

## 4. What Is BindingResult and Which Methods Can Be Used?

Correct import for Spring MVC:

```java
import org.springframework.validation.BindingResult;
```

`BindingResult` is an interface extending `Errors`. It adds access to binding metadata, the model, and field values beyond the error-reporting APIs of `Errors`.

| API | Purpose |
|---|---|
| `hasErrors()` | Is there at least one field or global error? |
| `getErrorCount()` | Total number of recorded errors |
| `hasFieldErrors("email")` | Does the `email` field specifically have errors? |
| `getFieldError("age")` | Retrieves a `FieldError` for the field |
| `getFieldErrors()` | List of all field errors |
| `getGlobalErrors()` | List of object-level errors |
| `getAllErrors()` | All `ObjectError` and `FieldError` instances |
| `getObjectName()` | Name of the bound object, e.g., `signup` |
| `rejectValue(field, code, message)` | Manually adds an error for a field |
| `reject(code, message)` | Manually adds an object-level error |
| `getFieldValue(field)` | Field value suited for re-displaying after binding |
| `getSuppressedFields()` | Fields suppressed per binder configuration |
| `getModel()` | Map containing the object and its BindingResult |

Example check:

```java
if (bindingResult.hasFieldErrors("email")) {
    // Email has an error; do not continue email-dependent processing.
}
if (bindingResult.hasErrors()) {
    return "signup/form";
}
```

Do not blindly log `getRejectedValue()` or the entire `BindingResult`, because rejected values can contain emails, addresses, tokens, or personal data. Logging **error codes**, **field names**, and a suitable request ID is much safer.

## 5. Mandatory Position of BindingResult in the Controller Signature

**Correct:**

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult bindingResult,
        Model model) {
    // BindingResult binds directly to the form preceding it.
    return bindingResult.hasErrors()
        ? "signup/form"
        : "redirect:/signup/success";
}
```

**Incorrect or error-prone:**

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        Model model,
        BindingResult bindingResult) {
    // BindingResult does not immediately follow the bound object.
    return "signup/form";
}
```

In Spring MVC, `Errors` / `BindingResult` must immediately follow the corresponding object so the handler argument resolver knows exactly where to bind error results. If separated by `Model`, `RedirectAttributes`, `@RequestParam`, or another object, runtime may throw an exception or fail to capture errors as desired.

When there are **multiple form objects**, each object needs its own `BindingResult` immediately after it:

```java
public String process(
        @Valid @ModelAttribute("customer") CustomerForm customer,
        BindingResult customerErrors,
        @Valid @ModelAttribute("address") AddressForm address,
        BindingResult addressErrors) {
    if (customerErrors.hasErrors() || addressErrors.hasErrors()) {
        return "checkout/form";
    }
    return "redirect:/checkout/success";
}
```

This snippet is illustrative; `CustomerForm` and `AddressForm` are hypothetical classes, and the method needs a mapping annotation. Do not share a single `BindingResult` across two form objects.

## 6. Dependencies and Practice Project Structure

Create a Spring Boot **3.5.x**, **Java 17**, Maven project with Spring Web, Thymeleaf, and Validation. Inside `pom.xml` with a Spring Boot parent or dependency management, include:

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

This is the dependencies section, **not a complete POM file**. Without the validation starter or an equivalent Jakarta Bean Validation provider, annotations like `@NotBlank` and `@Min` may not execute as expected.

File organization:

```text
src/main/java/com/example/forms/
    FormsApplication.java
    SignupForm.java
    SignupController.java
src/main/resources/
    application.properties
    templates/
        signup/
            form.html
            success.html
src/test/java/com/example/forms/
    SignupControllerTest.java
```

The Java code below consists of files for a Maven/Spring Boot project; it cannot be compiled purely with JDK `javac` because it depends on Spring, Jakarta Validation, and Thymeleaf.

## 7. Creating an Input Data Model with Clear Constraints

File `src/main/java/com/example/forms/SignupForm.java`:

```java
package com.example.forms;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class SignupForm {

    @NotBlank(message = "Full name must not be blank")
    @Size(min = 2, max = 40,
          message = "Full name must be between 2 and 40 characters")
    private String fullName;

    @NotBlank(message = "Email must not be blank")
    @Email(message = "Email format is invalid")
    private String email;

    @NotNull(message = "Age is required")
    @Min(value = 18, message = "Must be at least 18 years old")
    @Max(value = 120, message = "Invalid age")
    private Integer age;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Why use `Integer` instead of `int`? Because `Integer` can be `null` when age is left empty, pairing cleanly with `@NotNull`. Input `age=abc` produces `typeMismatch` because the string cannot convert to `Integer`; `age=16` converts yet violates `@Min(18)`.

`@Email` checks email format per the provider; **it does not verify real email addresses or mailbox ownership**. `@NotBlank` requires non-empty/non-blank text. `@Size` checks string length per the constraint rule; business validation must still be added where needed.

## 8. @SpringBootApplication and Basic Configuration

File `src/main/java/com/example/forms/FormsApplication.java`:

```java
package com.example.forms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormsApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.thymeleaf.cache=false
```

`spring.thymeleaf.cache=false` is suitable only during development for quick template edits; production should normally keep caching enabled to reduce rendering cost. You do not need to register a `BindingResult` bean manually: Spring MVC creates the binding result for each model attribute per request.

## 9. Controller: Checking Errors Before Deciding Processing

File `src/main/java/com/example/forms/SignupController.java`:

```java
package com.example.forms;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class SignupController {

    @GetMapping("/signup")
    public String showForm(Model model) {
        model.addAttribute("signup", new SignupForm());
        return "signup/form";
    }

    @PostMapping("/signup")
    public String submit(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult bindingResult,
            RedirectAttributes redirectAttributes) {

        if ("admin".equalsIgnoreCase(form.getFullName())) {
            bindingResult.rejectValue(
                    "fullName",
                    "name.reserved",
                    "This name cannot be used");
        }

        if (bindingResult.hasErrors()) {
            return "signup/form";
        }

        // Demo does not persist data; illustrates valid branch only.
        redirectAttributes.addFlashAttribute(
                "notice", "Registration data is valid");
        return "redirect:/signup/success";
    }

    @GetMapping("/signup/success")
    public String success() {
        return "signup/success";
    }
}
```

Key logic:

1. GET `/signup` puts an empty `SignupForm` into the model.
2. POST automatically binds form fields onto `SignupForm`, converts `age`, and runs Bean Validation due to `@Valid`.
3. `BindingResult` stands **immediately after** form and holds field/global errors.
4. The controller adds a custom rule: name `admin` is rejected with `rejectValue`.
5. On errors, `return "signup/form"` **re-renders the form in the same request** without redirecting.
6. When valid, redirects to the success page via `redirect:/signup/success` and a flash attribute.

This code does not write to a database, send emails, or create real accounts. In real applications, call persistence services **only after** `bindingResult.hasErrors()` is `false`, and then handle business errors, transactions, and concurrent data changes.

**Technical condition:** `@Controller` returns view names; if replaced with `@RestController`, the string `"signup/form"` would become the HTTP response body rather than being resolved as a template by ViewResolver.

## 10. Thymeleaf Template to Display the Form and Field Errors

File `src/main/resources/templates/signup/form.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign Up</title>
</head>
<body>
<h1>Sign Up</h1>

<form th:action="@{/signup}" th:object="${signup}" method="post">

    <label for="fullName">Full Name</label>
    <input type="text" th:field="*{fullName}">
    <p th:if="${#fields.hasErrors('fullName')}"
       th:errors="*{fullName}">Full name error</p>

    <label for="email">Email</label>
    <input type="text" th:field="*{email}">
    <p th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}">Email error</p>

    <label for="age">Age</label>
    <input type="text" th:field="*{age}">
    <p th:if="${#fields.hasErrors('age')}"
       th:errors="*{age}">Age error</p>

    <div th:if="${#fields.hasGlobalErrors()}">
        <p th:each="err : ${#fields.globalErrors()}"
           th:text="${err}">Global error</p>
    </div>

    <button type="submit">Submit</button>
</form>

</body>
</html>
```

In Thymeleaf:

- `th:object="${signup}"` selects the form-backing bean in the model.
- `th:field="*{email}"` generates HTML `name`, `id`, and value attributes from the model and binding state.
- `#fields.hasErrors('email')` checks errors on a field.
- `th:errors="*{email}"` renders error messages provided by the validator/binder.
- `#fields.hasGlobalErrors()` and `#fields.globalErrors()` support object-wide errors.
- `th:field` performs appropriate HTML escaping when rendering values, preventing untrusted raw HTML injection into the page.

The age input intentionally uses `type="text"` so you can submit `age=abc` and observe server-side type conversion errors. Production forms may use `type="number"`, yet you must never rely solely on browser validation because HTTP clients can send arbitrary data.

Spring MVC automatically adds BindingResult metadata to the model when rendering the form via the standard flow. You do not need to call `model.addAttribute("bindingResult", bindingResult)`; adding it manually under an arbitrary key does not guarantee the template engine will read it as standard form errors.

## 11. Success Template and Redirect Handling

File `src/main/resources/templates/signup/success.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Registration Valid</title>
</head>
<body>
<h1>Valid Registration Data Received</h1>
<p th:if="${notice}" th:text="${notice}">Notice</p>
<a th:href="@{/signup}">Back to form</a>
</body>
</html>
```

When the form is valid, the controller returns `redirect:/signup/success`. The browser receives a redirect response, typically **302 Found**, then performs a new GET to the success page. The flash attribute `notice` is carried temporarily to the target request.

This is the **Post/Redirect/Get (PRG)** pattern: after a successful POST, reloading does not accidentally resubmit the form under normal browser behavior.

**Conversely, when the form has errors**, return the `signup/form` view directly within the POST request to retain the form object and BindingResult. Redirecting on error can lose rejected values and error messages unless flash attributes are carefully engineered.

Re-rendering the form with HTTP **200 OK** on validation failure is standard behavior for server-rendered MVC forms; it does not mean the API accepted the data. If a contract requires 400/422 for an HTML form, set the status explicitly rather than relying solely on `BindingResult`.

## 12. Testing with Maven and curl

Start from the project root containing Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Open the form in a browser:

```text
http://localhost:8080/signup
```

Valid POST:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=Lan Nguyen' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'age=25'
```

In the sample project, the response is typically a redirect:

```http
HTTP/1.1 302
Location: http://localhost:8080/signup/success
```

The Location line is illustrative; Spring may use a relative/full URL or different headers depending on environment. `curl -i` does not follow redirects unless `-L` is added.

POST with validation and conversion errors:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=A' \
  --data-urlencode 'email=not-an-email' \
  --data-urlencode 'age=abc'
```

This normally returns **200** with the form HTML, showing at least errors for `fullName`, `email`, and `age`. Exact byte-for-byte HTML output is not guaranteed: message text may depend on the Bean Validation provider, MessageSource config, and escaping.

POST rejected by the custom rule:

```bash
curl -i -X POST http://localhost:8080/signup \
  --data-urlencode 'fullName=admin' \
  --data-urlencode 'email=admin@example.org' \
  --data-urlencode 'age=25'
```

`rejectValue("fullName", ...)` adds an error even though `@NotBlank`, `@Size`, `@Email`, and `@Min` all pass.

If the project includes Spring Security, form POSTs may require a CSRF token; the `curl` commands above assume **no Spring Security starter has been added**.

## 13. Distinguishing FieldError and ObjectError

`BindingResult.getFieldErrors()` returns `FieldError` objects, which typically have:

- `getField()`: field name, such as `age`.
- `getCode()` or `getCodes()`: error codes, such as `typeMismatch`, `Min`, `NotBlank`.
- `getDefaultMessage()`: display/fallback message.
- `getRejectedValue()`: the rejected value when available, which may contain personal data.
- `isBindingFailure()`: indicates a field binding failure, helping distinguish binding errors from validation errors when applicable.

`BindingResult.getGlobalErrors()` returns `ObjectError` objects not tied to a single field, such as an invalid start/end date combination.

Example logging only field names and error codes:

```java
for (var fieldError : bindingResult.getFieldErrors()) {
    String name = fieldError.getField();
    String code = fieldError.getCode();
    // Send name/code to a controlled logging system if needed.
}
```

This code is a fragment inside a controller/service that already has a `bindingResult` reference. Never dump full objects or rejected values into production logs.

To inspect errors:

```java
boolean invalid = bindingResult.hasErrors();
boolean ageInvalid = bindingResult.hasFieldErrors("age");
int count = bindingResult.getErrorCount();
```

In a form with a `typeMismatch` error, the Java property value on the form object may be `null`, yet `BindingResult` retains the error metadata and user-entered value to support re-rendering. Do not inspect `form.getAge()` alone and conclude the user left the field empty.

## 14. rejectValue and reject: Adding Business Errors in the Controller

When a rule cannot easily be expressed as a Bean Validation annotation, a controller or dedicated validator can add errors.

**Field-specific error:**

```java
if ("admin".equalsIgnoreCase(form.getFullName())) {
    bindingResult.rejectValue(
        "fullName", "name.reserved",
        "This name cannot be used");
}
```

**Object-wide error:**

```java
if (form.getAge() != null
        && form.getEmail() != null
        && form.getEmail().endsWith("@example.org")
        && form.getAge() < 21) {
    bindingResult.reject(
        "signup.age.email",
        "Registering with this example email requires being at least 21");
}
```

The second snippet is purely a demo rule, not a real age requirement for any product. It is an **object error**, as it depends on combining multiple fields. In real work, move reusable business validation into a separate service/validator so controllers stay lean.

After adding errors, check `hasErrors()` again **before calling services or redirecting**. If business logic depends on a field that might have had a conversion error, check `hasFieldErrors(field)` and ensure null-safety to avoid NPEs or checking invalid data.

## 15. Writing a Custom Validator and Registering It with @InitBinder

When multiple forms share a rule, you can extract it into `org.springframework.validation.Validator`:

```java
public final class SignupBusinessValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(
            Object target,
            org.springframework.validation.Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getFullName())) {
            errors.rejectValue(
                "fullName", "name.reserved",
                "This name cannot be used");
        }
    }
}
```

This is an illustrative class that can be placed in `com.example.forms`. If using this validator in the demo app, **remove the `admin` rule from the controller** to avoid adding duplicate errors.

Registering in the controller:

```java
@InitBinder("signup")
public void configureBinder(WebDataBinder binder) {
    binder.addValidators(new SignupBusinessValidator());
}
```

Required imports are `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. This code is a fragment placed in `SignupController`. The validation binder runs registered compatible validators alongside `@Valid`; verify `supports` compatibility when applying across different objects.

**Do not** use `binder.setValidator(...)` carelessly if it overwrites the default Jakarta Bean Validation validator. Use `addValidators` when augmenting, and test that `@NotBlank`/`@Min` still execute.

## 16. hasErrors Is a Flow Control Condition, Not an Annotation

A maintainable controller pattern:

```text
POST form
   |
   v
Bind + Validate
   |
   v
Add domain validation if needed
   |
   v
bindingResult.hasErrors()?
    | YES                     | NO
    v                         v
Return form view           Call service
preserve errors + input    commit succeeded?
    |                         |
    v                         v
Display field errors       Redirect via PRG
```

If a controller calls the service first and checks errors afterward, it may persist incomplete data, trigger NPEs, or cause pointless transaction rollbacks.

**However, `hasErrors() == false` does not guarantee business execution will succeed**: database unique constraints can fail due to race conditions, downstream services can fail, accounts can lose permissions, or records can change concurrently. Those failures require independent service/transaction/exception handling.

Separate:

- **Input validation**: form structure and constraints, using BindingResult.
- **Domain validation**: data validity under the business model.
- **Authorization**: who is permitted to act—never replaceable by validation.
- **Persistence errors**: unique constraints, transactions, and retry/compensation.

## 17. Why Shouldn't You Redirect When the Form Has Errors?

When `BindingResult.hasErrors()` is `true`:

```java
return "signup/form";
```

`BindingResult` and the form object remain in the request/model, allowing Thymeleaf to use `th:field` and `th:errors` to re-display user-entered values along with the errors.

If you use:

```java
return "redirect:/signup";
```

The client makes a **new GET request**, normally losing the POST's form object and BindingResult. Error messages vanish and the form resets. Information can be passed via `RedirectAttributes` in custom designs, but preserving multiple field errors and rejected values cleanly is much more complex; traditional HTML forms should return the view directly when invalid.

Conversely, **after a successful save**, PRG is helpful to prevent resubmissions on page reload. Do not confuse `return "signup/form"` with a redirect, nor `redirect:/signup/success` with a template filename.

## 18. @Valid, @Validated, Bean Validation, and Method Validation

`@Valid` belongs to `jakarta.validation.Valid`; `@Validated` belongs to `org.springframework.validation.annotation.Validated`. For `@ModelAttribute` objects, both can trigger validation when a compatible validator exists. `@Validated` also supports **validation groups** in Spring.

Example class with constraints on fields:

```java
public class SignupForm {
    @NotBlank
    private String fullName;
    // ...
}
```

If the controller does not use `@Valid`/`@Validated` and does not invoke a validator manually, `@NotBlank` will not run automatically just because the class has the annotation. However, **binding/type conversion errors can still occur**.

Spring Framework 6.1+ distinguishes two important exception branches:

1. **Per-argument validation of an `@ModelAttribute`, `@RequestBody`, or `@RequestPart` object:** when there is no adjacent `BindingResult` to handle it locally, defaults can raise `MethodArgumentNotValidException`.
2. **Method validation:** when `@Constraint` annotations are placed directly on method parameters or return values, `HandlerMethodValidationException` can be thrown. Method validation has specific rules for interacting with `Errors/BindingResult` parameters.

`@Valid` **is not itself a constraint annotation** that triggers method validation; `@NotNull`, `@Min`, `@NotBlank` directly on method parameters are what trigger method validation.

Do not confuse `BindingResult` with a mechanism that catches **every** validation error in a controller. If an error occurs on another parameter **without** an `Errors` argument immediately following it, method validation can still throw an exception before the controller body runs.

If a controller class uses class-level `@Validated` to apply AOP method validation, check its interaction with Spring Framework 6.1+ built-in method validation; Spring documentation recommends removing class-level `@Validated` to leverage the newer built-in MVC method validation.

## 19. Comparing @ModelAttribute Forms and @RequestBody JSON

Two common input shapes:

| Aspect | HTML MVC Form | JSON REST API |
|---|---|---|
| Binding | `@ModelAttribute("signup") SignupForm` | `@RequestBody SignupDto` |
| Data source | Request parameters (form/query...) | JSON body via `HttpMessageConverter` |
| Validation | `@Valid` or `@Validated` | `@Valid` or `@Validated` |
| BindingResult | Placed immediately after object to re-render form | Can be placed immediately after body object to handle validation locally |
| On error | Usually returns HTML view, keeping model errors | Usually returns HTTP 400 with API error structure |
| On success | Usually redirects via PRG | Usually returns response body/status per REST contract |

REST example:

```java
@PostMapping("/api/signup")
public ResponseEntity<?> apiSignup(
        @Valid @RequestBody SignupDto dto,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
            Map.of("error", "INVALID_SIGNUP"));
    }
    return ResponseEntity.ok().build();
}
```

This is an **illustrative method**: `SignupDto` is a hypothetical DTO, requiring imports for `Map`, `ResponseEntity`, `@RequestBody`, `@PostMapping`, `@Valid`, and `BindingResult`. Spring MVC supports local validation handling with `@RequestBody` and an adjacent `Errors/BindingResult` in standard configurations.

For **unparseable JSON** (malformed JSON), `HttpMessageNotReadableException` can occur **before object creation**; BindingResult is not a mechanism for catching all deserialization errors. An API typically uses `@RestControllerAdvice`/`ResponseEntityExceptionHandler` to standardize errors such as 400/415 instead of redirecting to an HTML form.

## 20. BindingResult in the Model and Internationalized Error Messages

Spring MVC typically adds to the model:

```text
signup -> SignupForm instance
org.springframework.validation.BindingResult.signup -> BindingResult instance
```

The second key uses the `BindingResult.MODEL_KEY_PREFIX` prefix plus the model attribute name. Thymeleaf looks up binding state and `FieldError` metadata based on `th:object="${signup}"`.

Do not rename `@ModelAttribute("signup")` in the controller to `@ModelAttribute("user")` while forgetting to update template `th:object` and tests.

Message codes can be generated at descending specificity levels, for example:

```text
NotBlank.signup.fullName
NotBlank.fullName
NotBlank.java.lang.String
NotBlank
```

`MessageCodesResolver` and `MessageSource` help map error codes to localized messages.

Example in `src/main/resources/messages.properties`:

```properties
name.reserved.signup.fullName=This name cannot be used
typeMismatch.signup.age=Age must be a number
```

Message codes must be checked against your actual `MessageCodesResolver` configuration; the example above illustrates common codes without guaranteeing fallback order across all customizations.

You can use `messages_vi.properties` and `messages_en.properties` for multiple locales. Do not tie validation message text to business logic (e.g., comparing message strings to pick branches), because translations can change.

## 21. @InitBinder, Allowed Fields, and Mass Assignment

`@ModelAttribute` lets Spring MVC bind request parameters into objects. If you bind directly to an **entity** containing sensitive fields like `role`, `enabled`, or `balance`, a client can try sending extra field names to overwrite values unintentionally.

**Best practice:** create a DTO/form object containing only fields the client is allowed to enter, such as `SignupForm` with `fullName`, `email`, `age`. Then map to your domain/entity inside the service after validation succeeds.

You can add an allowlist via `@InitBinder`:

```java
@InitBinder("signup")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "email", "age");
}
```

This fragment belongs in a `@Controller` and requires importing `InitBinder` and `WebDataBinder`. If a client sends `role=ADMIN` when the binder only permits those three fields, `role` is ignored; suppressed fields can be inspected via `bindingResult.getSuppressedFields()`.

**Note:** a suppressed field does not automatically create a validation error. If policy requires **rejecting** requests containing disallowed fields, inspect and return an error explicitly. Do not treat `allowedFields` as authentication/authorization; the service must still verify permissions and guard sensitive data.

## 22. MockMvc: Testing Form Errors, Type Mismatch, and the Success Path

Add `spring-boot-starter-test` to your Maven project:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/forms/SignupControllerTest.java`:

```java
package com.example.forms;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getFormReturnsView() throws Exception {
        mvc.perform(get("/signup"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup/form"))
            .andExpect(model().attributeExists("signup"));
    }

    @Test
    void invalidFormKeepsViewAndErrors() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "A")
                .param("email", "not-an-email")
                .param("age", "abc"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup/form"))
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "fullName", "email", "age"));
    }

    @Test
    void underAgeIsValidationError() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "Lan Nguyen")
                .param("email", "lan@example.org")
                .param("age", "16"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "age"));
    }

    @Test
    void reservedNameIsRejected() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "admin")
                .param("email", "admin@example.org")
                .param("age", "25"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrors(
                    "signup", "fullName"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/signup")
                .param("fullName", "Lan Nguyen")
                .param("email", "lan@example.org")
                .param("age", "25"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signup/success"))
            .andExpect(view().name("redirect:/signup/success"))
            .andExpect(flash().attribute(
                    "notice", "Registration data is valid"));
    }
}
```

In a Maven project with Maven Wrapper:

```bash
./mvnw test
```

Tests use `MockMvc` to run MVC handlers without opening a real HTTP socket. The assertions prove:

- GET form populates the model attribute.
- POST with invalid data **does not redirect**, instead returning the view with field errors.
- Type mismatch `age=abc` is recorded in BindingResult.
- Age 16 is a validation error, distinct from a conversion error.
- The `rejectValue` rule adds a form error.
- Valid data follows the PRG branch and sets the flash message.

`MockMvc` tests do not replace browser integration tests for CSS, accessibility, cookies, sessions, or CSRF once Spring Security is added.

## 23. Common Errors and How to Fix Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `BindingResult` does not receive the right errors | Not placed immediately after `@ModelAttribute` | Move it directly next to the bound object |
| `@NotBlank` has no effect | Missing `@Valid` or missing Bean Validation provider | Add the annotation/dependency appropriately |
| `hasErrors()` is always false for `age=abc` | Controller does not go through expected object binding, converter/handler altered | Check request content type, mapping, and method signature |
| Form renders literal text `signup/form` | Using `@RestController` instead of `@Controller` | Use an MVC view controller |
| Template does not display errors | Wrong `th:object` or missing `th:errors`/`#fields` | Match model attribute name and error bindings |
| User input is lost after errors | Redirecting on invalid input | Return the same form view within the request |
| Database written despite errors | Calling service before `hasErrors()` | Check before committing |
| Server returns 400 before reaching controller | Missing BindingResult, method validation, or JSON deserialization failure | Identify the actual exception type |
| POST returns 403 with Spring Security | Missing CSRF token or unauthorized user | Configure CSRF/login properly; never disable security to hide errors |
| Multiple objects have errors but only one is read | Only one BindingResult or wrong order | Place a dedicated BindingResult right after each object |
| Email/password leaked in logs | Logging `getRejectedValue()` or full requests | Log only safe error codes and field names |
| Client sets `role` or `enabled` fields | Binding directly to entity / mass assignment | Use a form DTO and allowlist |
| Raw error codes shown untranslated | `MessageSource` or message codes misconfigured | Create message bundles and test locales |
| Validation passes yet saving fails | Unique constraint / race condition | Handle transactions and domain errors separately |

## 24. Checklist Before Finishing a Form-Handling MVC Controller

1. `@ModelAttribute` uses a DTO containing only fields the client is allowed to edit.
2. `@Valid`/`@Validated` is present when automatic constraint validation is desired.
3. The project includes a Bean Validation provider, usually via `spring-boot-starter-validation`.
4. `BindingResult` stands **immediately after** the bound object, before other parameters.
5. The controller calls `hasErrors()` **before** persisting data or triggering side effects.
6. Field-specific errors use `rejectValue`; whole-object errors use `reject`.
7. On errors, return the form view in the same request to preserve form values and BindingResult.
8. On success, consider Post/Redirect/Get and flash attributes.
9. Templates use `th:object`, `th:field`, `th:errors` with consistent model attribute names.
10. Tests cover type conversion errors, Bean Validation, custom rejections, and the redirect branch.
11. Do not confuse `@ModelAttribute` validation with `@RequestBody` JSON parsing errors.
12. Handle security: auth/CSRF, mass assignment, output escaping, and secrets/logging.
13. Do not use validation to replace permission checks, unique constraints, or service-layer business rules.
14. When applying method validation, account for `HandlerMethodValidationException` and accompanying `BindingResult` rules.

## 25. Conclusion

`BindingResult` is the bridge between **Spring MVC data binding/validation** and **controller flow decisions**. A method with `@Valid @ModelAttribute("signup") SignupForm form, BindingResult result` captures errors in place; `result.hasErrors()` lets you return the form to display errors rather than throwing an exception or processing invalid data.

Remember three principles:

- **Right position:** `BindingResult` must sit directly beside the bound/validated parameter.
- **Right branching:** render the form on errors; execute business logic and redirect when valid.
- **Sufficient layers:** validation does not replace domain rules, security, transactions, or downstream error handling.

## 26. Official References

- Spring Framework 6.2 — `@ModelAttribute` and `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Validation of MVC Handler Methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@RequestBody` Validation and Local `Errors`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@InitBinder` and `WebDataBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — MVC Validation Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Boot 3.5 — Jakarta Bean Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Framework — `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingResult.html
- Thymeleaf 3.1 — Integration with Spring, Form Binding, and Validation Errors: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
