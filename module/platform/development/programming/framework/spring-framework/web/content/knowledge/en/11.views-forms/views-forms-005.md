# Form Binding, `BindingResult` Display, and Error Messages in Spring MVC

## 1. Objectives and Scope

In a Spring MVC application with **HTML views**, users enter data into a form, submit a POST, and expect their entered values to be preserved and errors shown next to the exact fields if anything is invalid. This lesson covers the entire form GET/POST cycle, data binding, validation, Thymeleaf error rendering, and Post/Redirect/Get.

After this lesson, you will know how to:

- Use `@Controller`, `Model`, `@ModelAttribute`, and a form backing object/DTO to connect HTML with Java.
- Distinguish type conversion errors (`typeMismatch`), Bean Validation errors (`NotBlank`, `Min`, `Email`), business errors, and object-level global errors.
- Place `BindingResult` immediately after the form argument; inspect `FieldError`, `ObjectError`, rejected values, and suppressed fields.
- Preserve form data when returning the view on error; display errors with `th:object`, `th:field`, `th:errors`, `th:errorclass`, and `#fields`.
- Build a runnable **Java 17+, Spring Boot 3.x/Spring Framework 6.x, Thymeleaf 3.1/Spring 6, Jakarta Bean Validation** example in a Spring Web/Thymeleaf/Validation project.
- Test with MockMvc to verify both that the model contains errors **and that the user actually sees the messages in rendered HTML**.

Spring WebFlux uses different mechanisms and APIs; the examples here use Spring MVC on the Servlet stack. When using Spring Boot 4 or Spring Framework 7, check APIs, dialects, and test setup against your actual version.

## 2. The Complete Form Lifecycle

```text
Browser GET /register
    -> @Controller.showForm(Model)
    -> model["registration"] = new RegistrationForm
    -> Thymeleaf templates/registration.html
       th:object="${registration}", th:field="*{fullName}"
    -> HTML has input name="fullName", name="age", ...

Browser POST /register
    -> application/x-www-form-urlencoded
    -> @ModelAttribute("registration") RegistrationForm
    -> WebDataBinder: String parameters -> String, Integer, LocalDate
    -> @Valid: checks Jakarta constraints
    -> BindingResult stores binding errors + validation errors
    -> @Controller.submit(form, result, redirectAttributes)
         |
         +-- result.hasErrors()
         |      -> return "registration"
         |      -> re-render entered values, th:errors for field/global
         |
         +-- no errors
                -> service processes business logic
                -> addFlashAttribute(...)
                -> redirect:/register/success
                -> Browser GET /register/success
```

Not every class runs validation automatically. `@Valid` or `@Validated` triggers the validator when a provider is configured, while binding/conversion occurs as Spring resolves the argument. HTML forms normally send `application/x-www-form-urlencoded`; JSON `@RequestBody` goes through `HttpMessageConverter` rather than property binding.

## 3. Form Backing Objects and Property Names

A form DTO contains **only the fields the browser is allowed to submit**, not necessarily a JPA entity or domain object. For example, a `RegistrationForm` DTO includes `fullName`, `email`, `age`, and `startDate`.

```html
<form method="post" action="/register">
  <input name="fullName" value="Lan">
  <input name="age" value="20">
</form>
```

The browser sends `fullName=Lan&age=20`. `WebDataBinder` locates matching property names and assigns them onto the Java object, performing type conversion as needed. An input's `name` determines the request parameter name; `id` is for labels/CSS/JS and does not replace `name`.

Reasons to use a dedicated form DTO:

- Clients cannot arbitrarily bind into `isAdmin`, `role`, `ownerId`, or persistence fields outside the contract.
- Forms can define validation rules and UX-friendly messages that database entities should not carry.
- When validation fails, the object still retains successfully bound values; values that failed conversion can remain available in `BindingResult`.
- Small DTOs make presentation changes easy without coupling views to the database schema.
- Even with a DTO, **authorization** in the service layer remains mandatory; a field existing on a DTO does not mean every client is permitted to modify it.

### Missing, Empty, and Invalid Inputs Differ

| Form parameter | Java target | Typical outcome |
| --- | --- | --- |
| `age` omitted | `Integer age` | `null`, may fail `@NotNull` |
| `age=` | `Integer age` | May convert to `null`, then fail `@NotNull` |
| `age=abc` | `Integer age` | Unconvertible, `FieldError` with `typeMismatch` |
| `age=15` | `Integer age` | Converts successfully, then `@Min(18)` fails |
| `age=20` | `Integer age` | Conversion and validation succeed |
| `fullName=   ` | `String` | Whitespace-only string; `@NotBlank` fails |
| `startDate=tomorrow` | `LocalDate` with ISO date | Formatter/conversion error |

An HTML form does not use `Content-Type: application/json` just because a field looks like JSON. Use `@ModelAttribute` for form-urlencoded data, and `@RequestBody`/Jackson for JSON. If a POST sends the wrong media type, you may hit `415` before validation runs.

## 4. `@ModelAttribute` and `BindingResult`

`@ModelAttribute("registration")` specifies the model object name so Spring creates/retrieves the object and binds request parameters. Example POST handler method:

```java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result,
        RedirectAttributes redirectAttributes) {

    if (result.hasErrors()) {
        return "registration";
    }
    redirectAttributes.addFlashAttribute("notice", "Registration received");
    return "redirect:/register/success";
}
```

This is an illustrative method snippet inside a controller; the full controller code appears below.

**`BindingResult` must immediately follow the argument being bound/validated.** Placing `Model`, `RedirectAttributes`, `@RequestParam`, or any other argument in between can prevent Spring from associating errors with the target and cause an exception. If a handler has multiple form objects, each `BindingResult` must follow its respective object immediately.

Practical methods:

| Method | Purpose |
| --- | --- |
| `hasErrors()` / `getErrorCount()` | Detect errors and count them |
| `getFieldErrors()` | Retrieve field errors (a field may have multiple) |
| `hasFieldErrors("age")` | Check errors on the age field |
| `getGlobalErrors()` | Object-level errors not tied to a single field |
| `getAllErrors()` | All `FieldError` and `ObjectError` instances |
| `FieldError.getField()` | Corresponding field name |
| `FieldError.getCode()` | Primary error code such as `typeMismatch`, `Min`, `NotBlank` |
| `FieldError.getCodes()` | Specific-to-general code list used for message resolution |
| `FieldError.getRejectedValue()` | Rejected input value; avoid logging/exposing sensitive data |
| `FieldError.isBindingFailure()` | Indicates a binding/conversion failure vs. a validator failure |
| `rejectValue("field", "code", "fallback")` | Add a custom field error |
| `reject("code", "fallback")` | Add a global error |
| `getSuppressedFields()` | Fields rejected by the binder, not necessarily creating a FieldError |

In the error branch, the controller returns `"registration"`. Spring MVC keeps the `registration` attribute and its companion `BindingResult` in the model. **Do not instantiate a new DTO after a POST has errors**, as doing so can wipe out what the user just entered and lose rejected values that Thymeleaf needs to re-display.

### Conversion Errors Can Also Appear in `BindingResult`

`age=abc` is not a number. The binder cannot assign an `Integer`, so it records a field error whose primary code is typically `typeMismatch`. `age=15` converts into an Integer, yet fails `@Min(18)`, producing code `Min`. These are two distinct cases; display helpful, tailored messages for each.

If a JSON body contains `"age":"abc"` and is handled via `@RequestBody`, Jackson may throw `HttpMessageNotReadableException` before Bean Validation, **not necessarily creating the same `FieldError` as `@ModelAttribute`**.

## 5. Jakarta Bean Validation in Forms

Spring Boot 3 uses the `jakarta.validation` namespace, and projects require `spring-boot-starter-validation`. Common constraints:

| Annotation | Meaning |
| --- | --- |
| `@NotBlank` | String must contain at least one non-whitespace character |
| `@Email` | Validates email syntax per validator; does not verify mailbox existence |
| `@Size(max=80)` | Valid length bounds |
| `@NotNull` | Value must not be `null` |
| `@Min(18)` | Number >= 18; `null` is typically allowed separately by `@Min` |
| `@PastOrPresent` | Date not in the future when required by business rules |

When age is required, use `Integer age` with `@NotNull @Min(18)`. A primitive `int` defaults to `0` before checks run, erasing whether the field was omitted/null. For dates, `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` tells the binder to expect `yyyy-MM-dd` for `LocalDate`; `startDate=tomorrow` is a conversion error. `@NotNull` cannot tell whether a malformed string represents a past or future date.

A single field can carry multiple constraints and produce multiple errors. Do not rely on message ordering in tests; assert error codes or the presence of at least one expected message.

## 6. Thymeleaf Form Binding

The Thymeleaf Spring dialect provides:

```html
<form th:action="@{/register}"
      th:object="${registration}" method="post">
  <label for="fullName">Full Name</label>
  <input id="fullName" type="text" th:field="*{fullName}">
</form>
```

- `th:object="${registration}"` binds the form backing object placed in the model by the controller.
- `th:field="*{fullName}"` generates and manages `name`, `id`, and `value` attributes aligned with Spring form binding.
- `th:action="@{/register}"` builds the URL relative to the application/context path instead of hardcoding an absolute address.
- GET and POST controllers must agree on the model name `registration`; renaming it to `form` in one place without updating the others breaks binding/rendering.
- `@Controller` returns a view name; `@RestController` implies `@ResponseBody`, so returning `"registration"` writes literal text into the body instead of rendering HTML.

When a POST fails, Thymeleaf can use `BindingResult`'s rejected value to restore raw unconvertible input. If you use `<input type="number">` for `age=abc`, some browsers block or clear non-numeric text. This learning example uses `type="text" inputmode="numeric"` so `abc` and the error can be observed accurately; in production, pick input types based on tested UX needs.

## 7. `th:errors`, `th:errorclass`, `#fields`, and Error Messages

```html
<label for="email">Email</label>
<input id="email" type="text" th:field="*{email}"
       th:errorclass="invalid" aria-describedby="emailError">
<p id="emailError" class="error"
   th:if="${#fields.hasErrors('email')}"
   th:errors="*{email}">
  Invalid email
</p>
```

Meaning:

- `#fields.hasErrors("email")`: are there errors for this field?
- `th:errors="*{email}"`: renders one or more resolved messages for the field.
- `th:errorclass="invalid"`: adds a CSS class when the field has errors.
- `#fields.errors("email")`: list of messages if you want to iterate manually with `th:each`.
- `#fields.hasGlobalErrors()` and `#fields.globalErrors()`: errors not tied to a specific field.
- `#fields.hasErrors("all")` / `#fields.allErrors()`: all errors if you want a summary banner at the top of the form.

Global errors can be displayed as:

```html
<ul th:if="${#fields.hasGlobalErrors()}">
  <li th:each="err : ${#fields.globalErrors()}"
      th:text="${err}">Form-level error</li>
</ul>
```

Combine text messages with CSS rather than relying solely on a red border. Add `label` and `aria-describedby` to support screen readers; when invalid, `aria-invalid` can be set with Thymeleaf. User-entered text must be HTML-escaped: use `th:text`/`th:errors` and avoid `th:utext` for untrusted content.

## 8. Runnable Example: Spring Boot 3 + Thymeleaf + Validation

Create a Java 17+ Maven project with `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `spring-boot-starter-validation`, and `spring-boot-starter-test`. The example needs no database; registration simply simulates accepting a valid form.

File structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  RegistrationForm.java
  RegistrationController.java
src/main/resources/templates/
  registration.html
  registration-success.html
src/test/java/com/example/demo/
  RegistrationControllerTest.java
```

### 8.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.2. RegistrationForm.java

```java
package com.example.demo;

import java.time.LocalDate;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.format.annotation.DateTimeFormat;

public class RegistrationForm {
    @NotBlank(message = "Please enter your full name")
    @Size(max = 80, message = "Full name must be at most 80 characters")
    private String fullName;

    @NotBlank(message = "Please enter your email")
    @Email(message = "Invalid email format")
    private String email;

    @NotNull(message = "Please enter your age")
    @Min(value = 18, message = "Must be at least 18 years old")
    private Integer age;

    @NotNull(message = "Please enter a start date")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    public RegistrationForm() {}

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }
}
```

Use `Integer` for nullable/blank input and `LocalDate` for a date without a time zone. After POST, the getters/setters allow the binder to populate values. The DTO has no role, ID, admin status, or database fields.

### 8.3. RegistrationController.java

```java
package com.example.demo;

import jakarta.validation.Valid;
import java.util.Locale;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("registration", new RegistrationForm());
        return "registration";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        // Purely to illustrate a global error, not a universal rule.
        if (form.getEmail() != null
                && form.getEmail().toLowerCase(Locale.ROOT)
                    .endsWith("@blocked.example")) {
            errors.reject(
                    "registration.emailDomainBlocked",
                    "This email domain is not allowed to register");
        }

        if (errors.hasErrors()) {
            return "registration";
        }

        // Demo does not write to a DB. Real apps invoke a service here,
        // after validation and business authorization checks pass.
        redirectAttributes.addFlashAttribute(
                "notice", "Registration has been received");
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    public String success() {
        return "registration-success";
    }
}
```

Controller highlights:

- GET places one object in the model; POST receives the exact same model name.
- `BindingResult errors` immediately follows the form argument.
- `errors.reject(...)` creates a global error. The domain rule here is just a demo; production apps should use dedicated validators/services so controllers stay focused on HTTP/view concerns.
- On errors: return the same view, do not create a new object, and do not call the persistence service.
- On no errors: use Post/Redirect/Get. `addFlashAttribute` carries the message to the next GET, which is not persistence.
- `redirect:/register/success` lets Spring build the Location header, keeping the browser on a GET URL on refresh.

### 8.4. registration.html

File `src/main/resources/templates/registration.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registration</title>
  <style>
    body { max-width: 40rem; margin: 2rem auto; padding: 1rem;
           font-family: system-ui, sans-serif; line-height: 1.5; }
    label { display: block; font-weight: 600; margin-top: 1rem; }
    input { width: 100%; box-sizing: border-box; padding: .5rem; }
    input.invalid { border: 2px solid #b42318; }
    .error { color: #b42318; margin: .3rem 0 .6rem; }
    .global-error { border: 2px solid #b42318; padding: .6rem; }
    button { margin-top: 1.5rem; padding: .6rem 1rem; }
  </style>
</head>
<body>
  <h1>Registration</h1>
  <p>Please fill in all fields. Minimum age is 18.</p>

  <form method="post" th:action="@{/register}"
        th:object="${registration}">

    <div class="global-error" role="alert"
         th:if="${#fields.hasGlobalErrors()}">
      <p>The form could not be accepted:</p>
      <ul>
        <li th:each="err : ${#fields.globalErrors()}"
            th:text="${err}">Form-level error</li>
      </ul>
    </div>

    <label for="fullName">Full Name</label>
    <input id="fullName" type="text" th:field="*{fullName}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('fullName')}"
           aria-describedby="fullNameError">
    <p id="fullNameError" class="error"
       th:if="${#fields.hasErrors('fullName')}"
       th:errors="*{fullName}">Invalid full name</p>

    <label for="email">Email</label>
    <input id="email" type="text" th:field="*{email}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('email')}"
           aria-describedby="emailError">
    <p id="emailError" class="error"
       th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}">Invalid email</p>

    <label for="age">Age</label>
    <input id="age" type="text" inputmode="numeric"
           th:field="*{age}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('age')}"
           aria-describedby="ageError">
    <p id="ageError" class="error"
       th:if="${#fields.hasErrors('age')}"
       th:errors="*{age}">Invalid age</p>

    <label for="startDate">Start Date (yyyy-MM-dd)</label>
    <input id="startDate" type="text" placeholder="2026-10-21"
           th:field="*{startDate}"
           th:errorclass="invalid"
           th:attr="aria-invalid=${#fields.hasErrors('startDate')}"
           aria-describedby="dateError">
    <p id="dateError" class="error"
       th:if="${#fields.hasErrors('startDate')}"
       th:errors="*{startDate}">Invalid date</p>

    <button type="submit">Submit Registration</button>
  </form>
</body>
</html>
```

`th:field` ensures entered values are restored when re-rendering the form, including cases like `age=abc` that failed to convert to Integer (stored in `BindingResult`'s rejected value). To observe this error, the example uses `type="text" inputmode="numeric"`; many browsers discard non-numeric values in `type="number"` inputs.

Thymeleaf `th:errors` renders the resolved messages. `th:errorclass` adds the CSS class only if the field has errors. `th:attr` sets ARIA attributes from `#fields.hasErrors`; the page provides textual messages rather than relying solely on red color.

When an application enables Spring Security, HTML POST forms may require a CSRF token. With Thymeleaf Spring integration, Spring Security can automatically inject a hidden input via `RequestDataValueProcessor` when rendering `th:action`; **inspect the rendered HTML** to confirm the token is present, or integrate CSRF per security guidelines. Never disable CSRF globally just to make a form POST work.

### 8.5. registration-success.html

File `src/main/resources/templates/registration-success.html`:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registration Successful</title>
</head>
<body>
  <h1>Form Received</h1>
  <p th:if="${notice != null}" th:text="${notice}">
    Registration has been received
  </p>
  <a th:href="@{/register}">Submit another form</a>
</body>
</html>
```

The template still renders safely when accessed via direct GET without a flash message. `th:text` escapes the message safely; avoid `th:utext` when messages contain untrusted client data.

### 8.6. Running the Application

From a Maven project with wrapper:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

By default, visit `http://localhost:8080/register` if `server.port` is unchanged. These Java files require Spring Web, Thymeleaf, and Bean Validation on the classpath; they will not compile with standalone `javac` without dependencies.

## 9. HTTP Practice: Valid, Validation Failure, Conversion Failure, Global Failure

### 9.1. GET the Form

```bash
curl -i http://localhost:8080/register
```

Expect HTTP 200, `Content-Type` compatible with `text/html`, and HTML containing inputs `name="fullName"`, `name="email"`, `name="age"`, `name="startDate"`. The client receives rendered HTML without raw `th:field` attributes.

### 9.2. Valid POST

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=2026-10-21"
```

Expect an HTTP 302 redirect response (new URL `/register/success`), since the controller had no errors and executed Post/Redirect/Get. Actual `Location` headers may reflect context path or gateway settings.

### 9.3. Validation-Failure POST

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=" \
  --data-urlencode "email=bad-email" \
  --data-urlencode "age=15" \
  --data-urlencode "startDate=2026-10-21"
```

In the demo, the controller returns the `registration` view; normally HTTP 200 when re-rendering HTML with errors. This **does not mean data was saved**, because the handler checked `hasErrors()`. Other applications may deliberately return 400/422 per UX/HTTP contracts, though default form views usually return 200.

### 9.4. Conversion Error with Value Retained

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=abc" \
  --data-urlencode "startDate=2026-10-21"
```

`age=abc` fails to parse as an Integer, `BindingResult` records `typeMismatch`; Thymeleaf normally re-renders the text input with `value="abc"` and a message asking for a valid number. If the POST method created `new RegistrationForm()` after detecting errors, the rejected value would be lost.

### 9.5. Global Error

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@blocked.example" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=2026-10-21"
```

This case passes Bean Validation's email syntax check yet violates the demo rule; `errors.reject(...)` adds a global error and the template displays it at the top of the form.

### 9.6. Date Format Error

```bash
curl -i http://localhost:8080/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "fullName=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "age=20" \
  --data-urlencode "startDate=tomorrow"
```

`startDate=tomorrow` does not match the ISO date format expected by the formatter; binding records a `typeMismatch` error for the date, distinct from having a valid `LocalDate` that a business rule disallows.

## 10. MockMvc Testing for Both Model and HTML

File `src/test/java/com/example/demo/RegistrationControllerTest.java`, using `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void getFormShowsFields() throws Exception {
        mvc.perform(get("/register"))
            .andExpect(status().isOk())
            .andExpect(view().name("registration"))
            .andExpect(model().attributeExists("registration"))
            .andExpect(content().string(containsString("name=\"fullName\"")));
    }

    @Test
    void invalidInputIsShownInHtml() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "")
                .param("email", "bad-email")
                .param("age", "15")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(view().name("registration"))
            .andExpect(model().attributeHasFieldErrors(
                    "registration", "fullName", "email", "age"))
            .andExpect(content().string(
                    containsString("Please enter your full name")));
    }

    @Test
    void invalidIntegerRetainsRejectedText() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@example.com")
                .param("age", "abc")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasFieldErrorCode(
                    "registration", "age", "typeMismatch"))
            .andExpect(content().string(containsString("value=\"abc\"")));
    }

    @Test
    void globalRuleAddsGlobalError() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@blocked.example")
                .param("age", "20")
                .param("startDate", "2026-10-21"))
            .andExpect(status().isOk())
            .andExpect(model().attributeHasErrors("registration"))
            .andExpect(content().string(containsString(
                    "This email domain is not allowed to register")));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/register")
                .param("fullName", "Lan")
                .param("email", "lan@example.com")
                .param("age", "20")
                .param("startDate", "2026-10-21"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/register/success"))
            .andExpect(flash().attributeExists("notice"));
    }
}
```

Run `./mvnw test` (PowerShell: `.\mvnw.cmd test`). This test suite is a **source template for a Boot 3 project with the right dependencies**, not executed inside any user repository. If the application enables Spring Security, tests must be configured with `spring-security-test` and proper CSRF/tokens/roles; a missing CSRF token can yield HTTP 403 before reaching the controller.

Why assert both model and HTML? `model().attributeHasFieldErrorCode(...)` confirms Spring detected `typeMismatch`, yet users still might not see any message if the template is broken. Checking HTML catches forms that forgot `th:errors`/`th:object` or failed to retain rejected input.

## 11. `MessageSource` and Localized Messages

Messages like `@NotBlank(message="...")` can be placed directly in annotations for demos. In larger applications, use error codes and resource bundles for internationalization. Spring can generate codes for an age conversion error such as:

```text
typeMismatch.registration.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

Example `src/main/resources/messages.properties`:

```properties
typeMismatch.registration.age=Age must be a valid integer
typeMismatch.registration.startDate=Date must follow yyyy-MM-dd
typeMismatch=Invalid value format
```

When multiple languages are needed, use `messages_vi.properties`/`messages_en.properties` and configure locale resolution accordingly. `MessageSource`/Bean Validation message interpolation separates display wording from logic; avoid surfacing `exception.getMessage()` or sensitive rejected values straight to the UI.

The `typeMismatch` code comes from binding, whereas `NotBlank`, `Email`, and `Min` come from validation. `getCodes()` typically holds specific-to-general codes for object/field/type so messages resolve by priority. Do not hardcode a single locale string in tests if the application switches locales; pin a fixed locale for HTML tests.

## 12. Global Errors, Cross-Field Errors, and Custom Validation

A condition spanning multiple fields, such as `startDate` before `endDate`, can produce a global error:

```java
errors.reject(
    "registration.invalidPeriod",
    "End date must be after start date");
```

This is just a snippet inside a method with `BindingResult errors`; the demo DTO does not include `endDate`. When you know the exact input to fix, use:

```java
errors.rejectValue(
    "startDate",
    "registration.startDateInvalid",
    "Start date is not accepted");
```

`reject(...)` creates a global `ObjectError`. `rejectValue(...)` creates a `FieldError`. Thymeleaf renders them using `#fields.globalErrors()` or `th:errors="*{startDate}"` respectively. Complex business validation should reside in appropriate validators/services to keep controllers free of heavy rules or expensive DB queries before format checks even pass.

## 13. `WebDataBinder`, Allowed Fields, and Security

A form DTO limits the input surface, yet nested binding or mass assignment still merits attention. You can place inside the controller:

```java
@InitBinder("registration")
public void customizeBinder(WebDataBinder binder) {
    binder.setAllowedFields(
        "fullName", "email", "age", "startDate");
}
```

This is a **method snippet you can add to the sample controller** with imports `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. It is not strictly mandatory when the DTO is already minimal, though it provides defense in depth.

Fields blocked by the allowlist are typically recorded in `BindingResult.getSuppressedFields()`; they do not always create a `FieldError`, nor do they necessarily make `hasErrors()` true. If policy requires rejecting forms carrying unexpected fields:

```java
if (errors.getSuppressedFields().length > 0) {
    errors.reject(
        "registration.unexpectedFields",
        "Form contains disallowed fields");
}
```

Use this only after actually configuring an allowlist. `@InitBinder` can also configure `Formatter`, `PropertyEditor`, and `StringTrimmerEditor`. Trimming whitespace-only strings to `null` can alter the distinction between missing, empty, and blank inputs; retest all cases after adding it.

## 14. Form Errors and Post/Redirect/Get

| POST outcome | Common action | Reason |
| --- | --- | --- |
| Binding/validation error | `return "registration"` | Keeps object and `BindingResult`, renders errors and rejected input |
| Business rule error shown in form | `errors.reject` or `rejectValue`, then same view | Displays error at proper field/global level |
| POST processed successfully | `redirect:/register/success` | Browser refreshes GET, avoiding duplicate POST |
| Business conflict after DB check | Decided by app contract: form error/409/redirect | Separates user errors from server errors |
| System/backend failure | Proper error handling, never confirm success | Never swallow errors as success |

HTTP 200 with form-error HTML only means the view rendered successfully, **not** that data was saved or accepted by business logic. If a client API requires 400 or 422, explicitly set that status; traditional MVC forms returning views typically use 200. Redirecting in the error branch loses `BindingResult` unless flash/error preservation is explicitly wired; hence the demo does not redirect on errors.

Flash attributes pass short notices to the next GET request and are not durable data storage or a place for passwords. When the success GET URL is visited directly, the template should remain safe even if `notice` is absent.

## 15. Accessibility and Content Safety

- Every input should have a clear label, error text next to the right field, and matching `id`/`aria-describedby`.
- Combine text with CSS/classes; avoid relying on color alone to indicate errors.
- Consider an error summary with links to fields and focus management for large forms, especially with server-side validation.
- Client-entered data is escaped when displayed. `th:text`/`th:errors` are safer than injecting unescaped HTML via `th:utext`.
- Never log `rejectedValue` containing passwords, tokens, payment cards, or PII; log error codes and field names instead for observability.
- If putting an email or name into flash messages, consider privacy. The demo uses a generic message to avoid echoing PII.
- HTML5 `required`/`min` improve UX but do not replace server validation; attackers can send raw requests manually.
- When using Spring Security, verify the POST form's CSRF token, GET/POST access controls, and prevent unauthorized object modification.

## 16. Common Pitfalls and How to Debug

1. **GET forgets to add the form object:** template `th:object` has no target.
2. **GET/POST/template use three different names:** errors/values fail to connect.
3. **`BindingResult` placed in the wrong position:** Spring cannot bind errors properly and may throw an exception.
4. **Forgot `@Valid`/validation dependency:** constraints do not run as expected.
5. **Creating a new `RegistrationForm` in the POST error branch:** wipes entered input and `BindingResult`.
6. **Redirecting on form error without preserving flash state:** user loses error messages.
7. **Showing only a generic error:** user cannot tell which field needs fixing.
8. **Confusing type conversion error with a `Min` message:** `abc` is not a number below 18.
9. **Manual `th:value` overriding `th:field`:** rejected values may fail to reappear.
10. **Changing text input to `type="number"` and expecting the browser to display `abc`:** browsers may clear non-numeric values.
11. **Forgetting global error display:** `reject` object errors never show beside any single field.
12. **Using `@RestController` to return a logical view name:** browser shows literal `registration` instead of HTML.
13. **Binding a JPA entity directly:** over-posting and exposing disallowed fields.
14. **Ignoring `getSuppressedFields()`:** suppressed fields do not automatically trigger `hasErrors()`.
15. **Overlooking security/CSRF:** POST fails with 403 before reaching the binder.
16. **Skipping HTML tests:** model has errors yet template fails to render them.
17. **Exposing error messages containing internal exceptions:** leaks classes, SQL, or client data.
18. **Performing side effects before checking `hasErrors()`:** saves invalid form data.
19. **Switching locales while tests hardcode wording:** tests break unrelated to behavior.
20. **Not testing multi-value params:** clients sending repeated fields can trigger unexpected binder behavior.
21. **Hardcoding form action with wrong context path:** POST hits a different URL than mapped.
22. **Assuming browser validation is enough:** curl and custom clients still submit invalid requests.

## 17. Verification Checklist

- [ ] GET renders the right template with model attribute named `registration`.
- [ ] POST uses `@Valid @ModelAttribute("registration")` with `BindingResult` immediately following.
- [ ] DTO contains only client-submittable fields; never bind sensitive entities directly.
- [ ] Validation covers required, blank, range, date format, and email syntax.
- [ ] Invalid forms retain the object/`BindingResult` and do not invoke the persistence service.
- [ ] Template uses `th:object`, `th:field`, `th:errors`, and `th:errorclass`.
- [ ] Global errors appear in a prominent area.
- [ ] Conversion errors can preserve rejected input (matching HTML input type).
- [ ] Tests verify both model `BindingResult` and rendered HTML.
- [ ] Valid POST redirects and uses flash messages appropriately.
- [ ] CSRF tokens and authorization checks are present when using Spring Security.
- [ ] Text/errors/inputs are HTML-escaped without leaking sensitive data.
- [ ] Resource bundles/message codes match locales when multilingual support is required.

## 18. Self-Check

**1.** Why must `BindingResult` come immediately after `@Valid @ModelAttribute`?

**Answer:** So Spring associates errors with that exact model argument. Misplacing it can cause argument resolution errors or bypass controller handling.

**2.** What error does `age=abc` produce when bound to `Integer`?

**Answer:** A binding conversion error, typically coded `typeMismatch`. It differs from `@Min` because no numeric value was produced yet.

**3.** What about `age=15`?

**Answer:** It converts to `Integer` successfully and then fails the `@Min(18)` constraint.

**4.** What is used to display errors for the `email` field?

**Answer:** `#fields.hasErrors('email')` to check, `th:errors="*{email}"` to render messages, and `th:errorclass` to add a CSS class.

**5.** How are global errors displayed?

**Answer:** Use `errors.reject(...)` and `#fields.hasGlobalErrors()`/`#fields.globalErrors()` in the template.

**6.** Why avoid creating a new object when a POST fails?

**Answer:** It can overwrite already-bound values and discard rejected values/messages held in `BindingResult`.

**7.** Why should a valid POST redirect?

**Answer:** Post/Redirect/Get moves the browser to a GET request so refreshing does not resubmit the POST.

**8.** Does `hasErrors()==false` guarantee no unexpected fields were submitted?

**Answer:** No. Check `getSuppressedFields()` if using an allowlist and enforcing a policy against unexpected fields.

**9.** Is a MockMvc assertion on field errors enough to prove users see the error?

**Answer:** Not yet. Verify the rendered HTML, field values, and error text/classes as well.

**10.** With a CSRF filter active, what does a POST without a token typically return before reaching the controller?

**Answer:** Usually 403, depending on configuration. That is a security filter failure, not form Bean Validation.

## 19. References

- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — MVC validation and `BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `WebDataBinder` / `@InitBinder`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — Type conversion/formatting: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Thymeleaf 3.1 + Spring integration, form binding and error messages: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Thymeleaf `#fields` API: https://www.thymeleaf.org/apidocs/thymeleaf-spring6/3.1.1.RELEASE/org/thymeleaf/spring6/expression/Fields.html
- Spring Framework — `RedirectAttributes` and `FlashMap`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
