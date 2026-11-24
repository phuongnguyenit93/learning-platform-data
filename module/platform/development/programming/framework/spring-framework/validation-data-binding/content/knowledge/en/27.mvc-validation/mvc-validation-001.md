# @Valid or @Validated on @ModelAttribute in Spring MVC

## Objectives

`@ModelAttribute` turns data from HTML forms, query parameters, and compatible request values into a Java object. However, **successful binding does not mean the data is valid**: the string `""` can still bind to a `String`, a malformed email is still a string, and an age of `16` can still be converted to `Integer` even if the application requires at least 18 years old. Spring MVC can automatically check the bound object using `@Valid` or `@Validated`, then place errors into `BindingResult`.

This lesson belongs to the **Validation in MVC** section and focuses on annotations **on the `@ModelAttribute` parameter of a controller**. You will:

- Distinguish `jakarta.validation.Valid` from `org.springframework.validation.annotation.Validated`, especially validation groups.
- Understand the sequence of data binding, type conversion, Bean Validation, `BindingResult`, and re-rendering the view.
- Properly use `@Valid @ModelAttribute("registrationForm")` or `@Validated(...) @ModelAttribute(...)`.
- Write a Java 17+/Spring Boot 3 example with two actions, *Save draft* and *Final submit*; test it with MockMvc.
- Identify when you receive `MethodArgumentNotValidException` or `HandlerMethodValidationException` instead of handling errors yourself.
- Resolve common issues related to nested forms, rejected values, the default group, templates, security, and Spring AOP.

## 1. Mechanism from request to BindingResult

For example, the browser sends:

~~~http
POST /register/draft
Content-Type: application/x-www-form-urlencoded

fullName=Lan&email=lan@example.com&age=21&address.city=Ha+Noi
~~~

The controller receives:

~~~java
@PostMapping("/register/draft")
String save(
        @ModelAttribute("registrationForm") RegistrationForm form) {
    // Process the bound form
    return "registration";
}
~~~

`@ModelAttribute` specifies that the handler needs an object named `registrationForm`. Spring looks up an existing object in the model or creates a new one using the appropriate mechanism, and uses `WebDataBinder` to convert and assign request values to constructor arguments/properties. For example, `"21"` is converted to `Integer.valueOf(21)` if the `age` property is `Integer`.

When `@Valid` or `@Validated` is present, Spring asks the validator to check the constraints declared on the object after the binding step. Both binding and validation errors can be recorded in `BindingResult`.

~~~text
HTTP form / query / path variables / compatible headers
                         |
                         v
             @ModelAttribute("registrationForm")
                         |
                         v
           Create or retrieve RegistrationForm
                         |
                         v
     WebDataBinder + ConversionService / Formatter
                         |
          +--------------+---------------+
          |                              |
    Conversion succeeded            Conversion failed
    Assign to object                FieldError typeMismatch
          |                              |
          +--------------+---------------+
                         |
                         v
        @Valid / @Validated → Validator
        Read @NotBlank, @Email, @Min, @Valid...
                         |
                         v
           BindingResult: binding + validation errors
                         |
             +-----------+-----------+
             |                       |
         Has errors               No errors
         return view              execute business logic
         and re-display form      / redirect
~~~

`@ModelAttribute` **does not define constraints by itself**. If the DTO has no validation annotations, custom `Validator`, or suitable Bean Validation provider, `@Valid` does not invent business rules on its own.

In Spring Boot 3, `spring-boot-starter-validation` typically provides a Jakarta Validation provider (such as Hibernate Validator) for the `jakarta.validation.*` APIs. Do not mix legacy `javax.validation.*` from the older ecosystem into Spring Framework 6/Spring Boot 3.

## 2. @Valid vs. @Validated

| Aspect | `@Valid` | `@Validated` |
| --- | --- | --- |
| Package | `jakarta.validation.Valid` | `org.springframework.validation.annotation.Validated` |
| Purpose on `@ModelAttribute` | Triggers Bean Validation for the object | Triggers validation and can select groups |
| When no other group is selected | Checks the `Default` group | Checks the `Default` group in typical configurations |
| Selecting groups at the usage site | Has no group attribute | `@Validated(Group.class)` or `@Validated({A.class,B.class})` |
| Cascading into child objects | `@Valid` on the reference edge | The root is validated; child edges still need `@Valid` |
| Used in plain Jakarta Validation | Yes | No, belongs to Spring |
| On a Spring bean class | Not an AOP method validation marker | Can be used for method validation via Spring AOP |

**Choose `@Valid`** when the same form has fixed rules belonging to the default group. **Choose `@Validated(...)`** when the operation state determines which constraints should run: creating a draft, final submission, manager approval, or updating a profile.

Example:

~~~java
@PostMapping("/draft")
String draft(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    // ...
}

@PostMapping("/final")
String finalSubmit(
        @Validated({Default.class, FinalSubmit.class})
        @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    // ...
}
~~~

This is a **signature snippet**, not a standalone controller yet; `Default` belongs to `jakarta.validation.groups.Default` while `FinalSubmit` is an application-defined marker interface.

There is no need to attach both `@Valid` and `@Validated` to the same argument "just to be safe". Instead, choose the annotation that clearly reflects the desired groups. `@Validated` is Spring's convenient extended variant; it does not make Bean Validation automatically traverse into every object if the cascade marker is missing on the DTO.

### When selecting only one custom group

With the DTO:

~~~java
@NotBlank
private String fullName; // Default group

@NotBlank(groups = FinalSubmit.class)
private String inviteCode; // FinalSubmit group
~~~

`@Validated(FinalSubmit.class)` normally runs only constraints belonging to `FinalSubmit`, so `fullName` in `Default` may be skipped. If the business rule requires both name and invite code to be valid on final submission, write:

~~~java
@Validated({Default.class, FinalSubmit.class})
~~~

Listing multiple groups **does not mean** the groups are checked in the listed order. To actually enforce group ordering and short-circuiting, look into `@GroupSequence`; do not rely on the iteration order of error collections.

## 3. BindingResult immediately follows the validated parameter

This is the controller pattern to remember:

~~~java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration";
    }

    return "redirect:/register/success";
}
~~~

`BindingResult` or `Errors` must be placed **immediately after** the corresponding `@ModelAttribute` parameter. Spring MVC attaches errors to that specific bound/validated object. Inserting a `Model` or `HttpServletRequest` parameter in between is wrong:

~~~java
@PostMapping("/register")
String wrong(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        Model model,
        BindingResult errors) {
    return "registration";
}
~~~

The `wrong` snippet is only an **anti-pattern**; do not put it into a real running controller.

`BindingResult` provides these APIs:

~~~java
boolean invalid = errors.hasErrors();
int count = errors.getErrorCount();
FieldError field = errors.getFieldError("age");
java.util.List<FieldError> ageErrors =
        errors.getFieldErrors("age");
java.util.List<ObjectError> global =
        errors.getGlobalErrors();
Object fieldDisplayValue = errors.getFieldValue("age");
~~~

This is an illustrative snippet assuming the variable `errors` already exists.

- `FieldError` describes an error on a property such as `age`, `email`, or `address.city`.
- `ObjectError` describes a whole-object error, which can come from a class-level constraint or a custom validator comparing multiple fields.
- `getRejectedValue()` holds the invalid value (which can be the input string or the converted object).
- `isBindingFailure()` indicates whether the error occurred during binding/type conversion or during validation.
- `getCodes()` provides the array of codes for lookup in message bundles; `getDefaultMessage()` gives the default text.
- `getFieldValue("age")` is useful for the view because when conversion fails, it can return the rejected string even when the Java property is null.

Two different kinds of errors:

| HTTP input | Java property | Result |
| --- | --- | --- |
| `age=21` | `Integer age` + `@Min(18)` | Converts to 21, valid |
| `age=16` | `Integer age` + `@Min(18)` | Converts to 16, `Min` constraint error |
| `age=abc` | `Integer age` + `@Min(18)` | Conversion failed, `typeMismatch` binding error |
| `email=not-an-email` | `String email` + `@Email` | Bound successfully, `Email` validation error |
| `address.city=` | Nested field with `@NotBlank` | Field error on `address.city` when `@Valid` cascade is declared |

A field can have **multiple** errors, so never assume `getFieldError("age")` is the only error. When you need to pick conversion errors, look for `FieldError::isBindingFailure`.

## 4. Complete example: two validation groups in one form

The sample application uses Java 17+, Spring Boot 3.5.7, Spring MVC, Thymeleaf, Bean Validation, and MockMvc. Users enter full name, email, age, city, and invite code. Save draft applies `Default`; final submit applies `Default` and `FinalSubmit`.

Project structure:

~~~text
mvc-registration/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/registration/
    │   │   ├── RegistrationApplication.java
    │   │   ├── FinalSubmit.java
    │   │   ├── RegistrationForm.java
    │   │   └── RegistrationController.java
    │   └── resources/
    │       ├── templates/registration.html
    │       └── application.properties
    └── test/
        └── java/com/example/registration/
            └── RegistrationControllerTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-registration</artifactId>
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
~~~

`spring-boot-starter-validation` is the dependency required in a typical Spring Boot 3 application to obtain a Jakarta Validation provider. The Spring Boot parent manages dependency versions; in real projects, choose versions according to your organization's support and security update policy.

### 4.2. RegistrationApplication.java

~~~java
package com.example.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationApplication.class, args);
    }
}
~~~

### 4.3. FinalSubmit.java — validation group

~~~java
package com.example.registration;

public interface FinalSubmit {
}
~~~

This is a marker interface used as a type-safe group; the interface itself contains no logic or state.

### 4.4. RegistrationForm.java — DTO and nested validation

~~~java
package com.example.registration;

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

    @NotBlank(groups = FinalSubmit.class)
    private String inviteCode;

    @Valid
    private AddressForm address = new AddressForm();

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

    public String getInviteCode() {
        return inviteCode;
    }

    public void setInviteCode(String inviteCode) {
        this.inviteCode = inviteCode;
    }

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public static class AddressForm {
        @NotBlank
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }
}
~~~

Explanation:

- `fullName`, `email`, and `age` are default constraints. `@Email` needs to be combined with `@NotBlank` because format checking usually lets `null` pass.
- `inviteCode` only has `@NotBlank(groups = FinalSubmit.class)`; saving a draft does not require the code.
- `@Valid` on `address` marks the cascade edge. If omitted, validating `RegistrationForm` will not descend into `AddressForm.city`.
- `AddressForm` has getters/setters and a default object so property binding can process the `address.city` input.
- `@Valid` does not mean `address` must be non-null. When that is required, also place `@NotNull` on the association.
- `Integer age` lets us observe a type conversion error from the string `abc`; using `int` would not represent the same null state when input is missing.

### 4.5. RegistrationController.java

~~~java
package com.example.registration;

import jakarta.validation.Valid;
import jakarta.validation.groups.Default;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "fullName", "email", "age",
                "inviteCode", "address.city");
    }

    @GetMapping
    public String show(Model model) {
        model.addAttribute(
                "registrationForm", new RegistrationForm());
        return "registration";
    }

    @PostMapping("/draft")
    public String saveDraft(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "registration";
        }
        return "redirect:/register/success";
    }

    @PostMapping("/final")
    public String finalSubmit(
            @Validated({Default.class, FinalSubmit.class})
            @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "registration";
        }
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    @ResponseBody
    public String success() {
        return "Accepted";
    }
}
~~~

In `saveDraft`, `@Valid` applies Default constraints (including nested `address.city`). In `finalSubmit`, `@Validated({Default.class, FinalSubmit.class})` additionally checks `inviteCode`. `BindingResult` is placed right next to the form argument in both methods.

`@InitBinder` restricts which properties are allowed to bind, preventing HTTP requests from writing to unintended fields (mass assignment). It is a boundary protection mechanism, **distinct from validation**; do not use `@NotBlank` in place of controlling editable properties.

The handlers do not write to a database: this is a validation demo, so they only redirect to a success endpoint. If the application actually saves a record, it must call the service after `errors.hasErrors() == false` and still verify authorization/domain invariants in the service.

### 4.6. templates/registration.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Registration</title>
  <style>
    .error { color: #b00020; }
    .invalid { border: 1px solid #b00020; }
  </style>
</head>
<body>
<h1>Registration</h1>

<form th:action="@{/register/draft}"
      th:object="${registrationForm}"
      method="post">

  <label>Full name
    <input type="text"
           th:field="*{fullName}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('fullName')}"
     th:errors="*{fullName}"></p>

  <label>Email
    <input type="text"
           th:field="*{email}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('email')}"
     th:errors="*{email}"></p>

  <label>Age
    <input type="text"
           inputmode="numeric"
           th:field="*{age}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('age')}"
     th:errors="*{age}"></p>

  <label>City
    <input type="text"
           th:field="*{address.city}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('address.city')}"
     th:errors="*{address.city}"></p>

  <label>Invite code (required only on final submit)
    <input type="text"
           th:field="*{inviteCode}"
           th:errorclass="invalid">
  </label>
  <p class="error"
     th:if="${#fields.hasErrors('inviteCode')}"
     th:errors="*{inviteCode}"></p>

  <button type="submit">Save draft</button>
  <button type="submit"
          th:formaction="@{/register/final}">Final submit</button>
</form>
</body>
</html>
~~~

Thanks to `th:object="${registrationForm}"` and `th:field="*{...}"`, Thymeleaf reads the Spring binding status, retrieving the bound value **or the rejected value if there is an error**. `th:errors` renders messages next to the field. The nested path `address.city` must match the Java property and input name.

The two buttons target two URLs: the default button submits to `/register/draft`, and the final button uses `formaction` to submit to `/register/final`. Because the two handlers select different groups, an empty invite code can be valid in draft mode but invalid at the final step.

`type="text" inputmode="numeric"` for `age` helps preserve the string `abc` when simulating a conversion error. Browsers may reject or normalize non-numeric values in `<input type="number">`, so the HTML control should be chosen based on UX and actual testing.

### 4.7. application.properties and trying it out

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

Disabling template caching is only for learning/dev environments. Run:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/register`, fill in `fullName=Lan`, `email=lan@example.com`, `age=21`, `address.city=Ha Noi`, and leave `inviteCode` empty.

- Click **Save draft**: Default constraints are valid; `inviteCode` does not belong to Default, so the response is an HTTP **302** redirect to `/register/success`.
- Click **Final submit**: the `FinalSubmit` group is selected; the empty `inviteCode` has a `FieldError`. The controller returns the `registration` view in the same request (this pattern is typically HTTP **200**) and re-displays the input.
- Enter `inviteCode=ABC123` and do a final submit: all demo constraints are valid, switching to an HTTP **302** redirect.
- Try `age=abc`: conversion to `Integer` fails, `BindingResult` contains a `typeMismatch` error and can retain the string `"abc"` for the template.

Spring Boot startup logs do not have identical stdout across machines; do not assume logs must match a single pattern. The evidence for this lesson is the **HTTP behavior and MockMvc assertions** below.

## 5. MockMvc testing for validation and groups

File `src/test/java/com/example/registration/RegistrationControllerTest.java`:

~~~java
package com.example.registration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.servlet.ModelAndView;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getPageCreatesForm() throws Exception {
        mvc.perform(get("/register"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeExists(
                        "registrationForm"));
    }

    @Test
    void draftDoesNotRequireInviteCode() throws Exception {
        mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/register/success"));
    }

    @Test
    void finalRequiresInviteCode() throws Exception {
        var response = mvc.perform(post("/register/final")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "inviteCode"))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult result = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "registrationForm");

        assertNotNull(result);
        FieldError error = result.getFieldError("inviteCode");
        assertNotNull(error);
        assertEquals("NotBlank", error.getCode());
        assertFalse(error.isBindingFailure());
    }

    @Test
    void finalAcceptsCompleteForm() throws Exception {
        mvc.perform(post("/register/final")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", "Ha Noi")
                        .param("inviteCode", "ABC123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/register/success"));
    }

    @Test
    void nestedCityConstraintIsChecked() throws Exception {
        mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "21")
                        .param("address.city", ""))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "address.city"));
    }

    @Test
    void failedAgeConversionKeepsRejectedText()
            throws Exception {

        var response = mvc.perform(post("/register/draft")
                        .param("fullName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "abc")
                        .param("address.city", "Ha Noi"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "registrationForm", "age"))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult result = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "registrationForm");
        assertNotNull(result);

        FieldError mismatch = result.getFieldErrors("age")
                .stream()
                .filter(FieldError::isBindingFailure)
                .findFirst()
                .orElseThrow();

        assertEquals("abc", mismatch.getRejectedValue());
        assertEquals("abc", result.getFieldValue("age"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Six distinct tests: (1) form initialization; (2) `@Valid` runs Default only; (3) `@Validated` combines Default + FinalSubmit; (4) valid final submission; (5) `@Valid` on a nested field; (6) type mismatch and rejected value. Assertions do not depend on `Set<ConstraintViolation>` order.

These tests require a Spring test context with MVC, Thymeleaf, and a Jakarta provider. If the application adds Spring Security, a CSRF token must be added to POST tests according to the actual security configuration, otherwise HTTP 403 may occur **before** controller validation runs.

## 6. Without BindingResult: MethodArgumentNotValidException

Two ways to write the handler signature:

~~~java
// A. With BindingResult: handler renders errors itself
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        BindingResult errors) {
    return errors.hasErrors()
            ? "registration"
            : "redirect:/register/success";
}
~~~

~~~java
// B. Without BindingResult: framework reports the error
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form) {
    return "redirect:/register/success";
}
~~~

These are **two comparison snippets; do not copy both at once** because their URLs collide.

When a `@ModelAttribute` command object is validated on its own without a corresponding `BindingResult`, Spring MVC usually throws `MethodArgumentNotValidException` if binding or validation fails (default handling is typically HTTP 400). Handler B is not executed up to the redirect line.

If the controller has a direct constraint on another method parameter, for example:

~~~java
@PostMapping("/check")
String check(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm form,
        @RequestParam @Min(1) int count) {
    return "ok";
}
~~~

This is an illustrative snippet that needs imports for `@RequestParam` and `@Min`. Since Spring Framework **6.1**, direct constraints like `@Min` can trigger native **method validation** in Spring MVC, including nested constraints on `@Valid`. When method validation encounters errors not handled by a matching `Errors`/`BindingResult`, it usually throws `HandlerMethodValidationException`.

**Note:** `@Valid` by itself is **not a direct constraint**, so it does not automatically trigger method validation for the entire signature. Adding `@NotNull` directly to a method argument can change the validation/exception path. Spring MVC method validation can still work with `BindingResult`: the controller is only invoked if all errors belong to arguments that have a matching `Errors` parameter immediately following them.

If the controller has **class-level `@Validated`**, Spring AOP method validation may run through a proxy. To use Spring 6.1+ native controller method validation, Spring documentation recommends removing class-level `@Validated` where appropriate. `@Validated` **on the form parameter itself** to select groups is a separate use case and does not require `MethodValidationPostProcessor` to work.

## 7. @ModelAttribute and @RequestBody are not synonymous

| Aspect | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Data source | HTML forms, query params, compatible request values | HTTP body via message converter, typically JSON |
| Data conversion | `WebDataBinder`/`ConversionService` for property/constructor | `HttpMessageConverter` deserialization |
| Validation | `@Valid` or `@Validated` on the argument | Also has `@Valid` or `@Validated` |
| Binding errors | `BindingResult`/field errors or exception | May be a parse/converter exception before validation |
| Typical UI | Server-rendered HTML view | REST JSON response/frontend handling |
| Example | `POST application/x-www-form-urlencoded` | `POST application/json` |

Do not attach `@RequestBody` just because you want to use `@Valid`; both annotations support validation. The focus is on **how data is received** and the media type. `@ModelAttribute` on an argument can be inferred when omitted for object types not handled by another resolver, though declaring it explicitly is clearer, especially for native-image/AOT inference.

## 8. Nested objects, groups, and tricky cases

### 8.1. Null and different constraints

`@Valid` on an object edge **does not require the object to exist**. If `address == null`, cascaded validation skips that branch. To require the address to be present:

~~~java
@NotNull
@Valid
private AddressForm address;
~~~

`@Email` checks email syntax, whereas `@NotBlank` checks presence/non-blankness. `@Min(18)` checks the number after successful type conversion; `@NotNull` forbids a missing age. Each constraint addresses a different requirement and should not be conflated.

### 8.2. Collections and container elements

A form with a collection of recipients can be declared as:

~~~java
private java.util.List<@Valid RecipientForm> recipients;
~~~

With `RecipientForm` having `@NotBlank String name`, Jakarta Validation can validate each element when bound and configured with appropriate value extraction. The nested path can be `recipients[0].name`. If an element in the list is null, `@Valid` alone skips null; add `@NotNull` on the type argument when needed.

In real forms, you should determine the item count and limit index/auto-grow behavior to avoid inputs creating overly large structures. This is a data binding/security concern, not solely Bean Validation.

### 8.3. Group conversion

A cascade edge can use `@ConvertGroup`:

~~~java
@Valid
@ConvertGroup(
        from = Default.class,
        to = DetailedChecks.class)
private AddressForm address;
~~~

This snippet needs imports for `jakarta.validation.groups.ConvertGroup`, `Default`, and the `DetailedChecks` interface. Conversion means **when validating the Default group on this edge**, the child is checked under the `DetailedChecks` group; it does not mean "check everything". You must clearly understand why group conversion is applied to avoid overlapping, hard-to-predict configurations.

### 8.4. Custom Spring Validator

In addition to Jakarta Bean Validation, Spring MVC allows attaching an `org.springframework.validation.Validator` via `@InitBinder`:

~~~java
@InitBinder("registrationForm")
void attach(WebDataBinder binder) {
    binder.addValidators(myValidator);
}
~~~

This snippet requires the `myValidator` variable to be provided via dependency injection; it does not compile standalone. A custom validator can record errors into `Errors.rejectValue(...)`, which appear together in `BindingResult`. If using `@Validated` with groups, ensure the custom Spring validator understands validation hints/groups or deliberately separate responsibilities; do not assume every Spring `Validator` interprets Jakarta groups the same way.

## 9. Re-displaying the form, messages, and security

To re-render the form after errors:

~~~java
if (errors.hasErrors()) {
    return "registration";
}
~~~

Do not replace the current object with `new RegistrationForm()` when errors occur; do not redirect to GET without carrying the data and `BindingResult`. The common pattern is **return the same view on error, redirect after success** (Post/Redirect/Get on success).

Thymeleaf Spring integration uses `th:object`, `th:field`, and `th:errors` to re-display both rejected values and messages. For an age field where `"abc"` fails conversion to `Integer`, `RegistrationForm.getAge()` may be null while `BindingResult.getFieldValue("age")` can return `"abc"`.

Spring resolves messages via `FieldError.getCodes()`, combined with `MessageSource` and locale. You can place `src/main/resources/messages.properties`:

~~~properties
NotBlank.registrationForm.fullName=Full name must not be blank
NotBlank.registrationForm.inviteCode=Invite code is required on final submit
Email.registrationForm.email=Invalid email address
Min.registrationForm.age=Age does not meet the minimum requirement
typeMismatch.registrationForm.age=Age must be an integer
~~~

The codes above follow common conventions for the corresponding object name/field; if the project changes `MessageCodesResolver` or the object name, check the actual `FieldError.getCodes()`. For internationalization, use locale-specific bundles such as `messages_vi.properties` and `messages_en.properties`.

Data protection:

- Only bind requests into a **form DTO** containing properties allowed to be received; when property binding is used, consider `setAllowedFields(...)`.
- Validation does not replace authorization, CSRF protection, or domain checks in the service.
- Do not re-display passwords/tokens/OTPs just to "preserve the form", and do not log raw `getRejectedValue()` if it may contain sensitive data.
- Escape output according to the HTML context (for example `th:text`/`th:field`), and do not use `th:utext` with untrusted data.
- When the response is a JSON API instead of an HTML view, design a stable error schema and avoid exposing the entire exception/target object.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@Valid` is attached but no errors appear | Missing Jakarta provider, missing or mismatched constraints | Check dependencies, annotations, and trigger |
| Draft form requires final submit code | Draft handler selected `FinalSubmit` | Use only Default on the draft branch |
| Final submit skips `fullName` | Only `@Validated(FinalSubmit.class)` used | Include `Default.class` as well |
| `address.city` is invalid yet passes | Missing `@Valid` on `address` | Add the cascade marker on the proper edge |
| Handler does not receive errors | `BindingResult` is not adjacent to the object | Fix parameter ordering |
| Input `age=abc` becomes null | Conversion error | Render based on binding status/rejected value |
| Form comes back empty after errors | Redirected or created a new object | Return the same view, keeping model and BindingResult |
| Both `@Valid` and `@Validated` on same parameter | No clear group design | Use one annotation reflecting the groups to run |
| Controller throws unexpected exception | Direct method constraint or class-level AOP present | Check `MethodArgumentNotValidException` and `HandlerMethodValidationException` |
| Wrong field name | HTML input name differs from property | Use `th:field` and proper mapping |
| Registration updates admin fields | Bound entity directly or missing whitelist | Use a form DTO and allowed fields |
| Invalid data is processed further | Missing `errors.hasErrors()` check or swallowed exception | Block business logic on errors |
| Messages are not translated | Message bundle/codes/locale mismatch | Check `getCodes()` and `MessageSource` configuration |

## 11. Self-check questions

**1.** Why is `@ModelAttribute` not enough to ensure a valid email?  
Because it only binds data; to validate content, you must declare `@Email` and trigger validation.

**2.** When should you use `@Validated` instead of `@Valid`?  
When you need to specify different validation groups at the point of receiving the object; for example, saving a draft with Default and final submission with Default + FinalSubmit.

**3.** Why can `@Validated(FinalSubmit.class)` skip `@NotBlank` on `fullName`?  
Because a constraint without an explicit group belongs to `Default`, and that group is not automatically included in a list of custom groups.

**4.** Where does `BindingResult` go?  
Immediately after the `@ModelAttribute` parameter whose binding/validation results it receives in the handler signature.

**5.** If `age=abc`, how can `getAge()` be null while the form still displays `abc`?  
Because `BindingResult` retains the rejected value, and Thymeleaf's `th:field` reads the binding status.

**6.** Does adding `@Valid` to a handler argument automatically trigger native method validation?  
No; it is a marker that triggers bean validation/cascading for the argument. A direct constraint on a method parameter can cause Spring MVC to use method validation.

**7.** What is the effect of removing `@Valid` on `RegistrationForm.address`?  
Constraints on `AddressForm.city` are not traversed through that edge when validating the root form.

**8.** Why should you not bind directly to an entity?  
To avoid mass assignment and keep web input data separate from business/administrative attributes that only the server is allowed to modify.

**Remember:** `@ModelAttribute` binds the request into an object; `@Valid` triggers default validation and cascades through child markers; `@Validated(...)` allows selecting groups; `BindingResult` stores binding + validation errors. Good form design requires getting **annotations, groups, BindingResult placement, templates, dependencies, and tests** all right.

## References

- [Spring Framework 6.2 — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Configuring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — @Validated API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/annotation/Validated.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/BindingResult.html)
- [Jakarta Validation 3.0 specification — Groups, cascade, constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Thymeleaf + Spring 3.1 tutorial — th:field, th:errors](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)
- [Spring Boot 3.5.7 release](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now/)
