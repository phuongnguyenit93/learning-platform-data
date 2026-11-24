# Preserving Rejected Values to Re-render Forms in Spring MVC

## Lesson objectives

When a user fills out a form and clicks **Submit**, if a field is invalid, the application should re-display the exact data the user just typed alongside error messages. This is trickier than it looks: HTTP input is strings, whereas Java properties can be `Integer`, `LocalDate`, or custom domain types. If type conversion fails, the Java object **cannot hold the raw value that was entered**; Spring MVC must preserve it in the binding result so the form can still re-render it.

This lesson is part of the **Binding in MVC** topic. After completing it, you will be able to:

- Explain how `WebDataBinder`, `BindingResult`, `FieldError`, and `rejectedValue` work together.
- Distinguish type conversion errors (`typeMismatch`) from Bean Validation errors (`@NotBlank`, `@Email`, `@Min`).
- Write controllers using `@Valid @ModelAttribute` and place `BindingResult` in the right position to re-render the form without losing user input.
- Use Thymeleaf `th:object`, `th:field`, and `th:errors` to return invalid values without manually reading raw strings from the request.
- Test properly with cases such as `age=abc` when the Java property `age` has type `Integer`.
- Recognize scenarios that lose data: replacing the model object, redirecting on error, mismatched property names, or rendering `getAge()` manually instead of using binding integration.

## 1. Scenario and UX requirement

A registration form has three fields:

~~~text
Full name: Lan
Email: sai-email
Age: abc
[ Submit ]
~~~

The Java application uses a model:

~~~java
private String displayName;
private String email;
private Integer age;
~~~

There are two distinct kinds of problems:

1. `email = "sai-email"` binds into `String` but fails `@Email`. This is a **validation failure**.
2. `age = "abc"` cannot be converted into `Integer`. This is a **binding/conversion failure**, typically with error code `typeMismatch`.

If the controller re-renders the form simply by reading `signupForm.getAge()`, the age value may be `null`: the user would see the age field wiped out even though they just typed `abc`. However, `BindingResult` retains information about the failing field and its rejected value so the view can re-display `abc`.

Desired outcome:

~~~text
Full name: Lan
Email: sai-email
       Invalid email
Age: abc
      Age must be an integer
[ Submit ]
~~~

Error messages may be determined by a message bundle; the illustrative output above does not mean Spring generates those exact sentences automatically. What must be guaranteed is that **input is preserved**, errors are shown next to the corresponding fields, and only valid data proceeds to business processing.

## 2. Where does Spring MVC get the “rejected value”?

An HTTP form sends a request following field naming conventions, for example:

~~~http
POST /signup
Content-Type: application/x-www-form-urlencoded

displayName=Lan&email=sai-email&age=abc
~~~

Initial values from the request are strings. When encountering the `@ModelAttribute("signupForm")` argument, Spring MVC roughly performs:

~~~text
Request parameters: "Lan", "sai-email", "abc"
   |
   v
@ModelAttribute("signupForm")
   |
   v
WebDataBinder
   |-- select properties allowed for binding
   |-- convert types via ConversionService/PropertyEditor
   |-- assign succeeded properties onto SignupForm
   |-- record errors if conversion fails
   |
   v
@Valid / @Validated (if present, at supported point)
   |
   v
BindingResult
   |-- ObjectError and FieldError
   |-- rejectedValue for failed fields
   |-- error codes, arguments, default message
   |
   v
Controller: if hasErrors() then return "signup"
   |
   v
Thymeleaf th:field + th:errors read binding status
   |
   v
Form re-displays inputs and errors
~~~

`WebDataBinder` is responsible for binding source values onto the object and detecting type conversion failures. `BindingResult` is the interface holding both binding and validation results, including values that cannot fit into the Java bean.

A `FieldError` exposes:

~~~java
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
String code = fieldError.getCode();
boolean conversionFailed = fieldError.isBindingFailure();
String defaultMessage = fieldError.getDefaultMessage();
~~~

This is an API snippet assuming an existing `fieldError` variable, **not a standalone Java class**.

- `getField()`: the field name, e.g., `age` or `address.city`.
- `getRejectedValue()`: the rejected value. For `age=abc` in the example, this is typically the string `"abc"`; for `age=17`, which binds successfully but violates `@Min(18)`, the value may be the integer `17`.
- `isBindingFailure()`: `true` for binding errors such as failed type conversion; `false` for errors detected by a validator on already-bound data.
- `getCode()`: primary error code, e.g., `typeMismatch`, `Email`, `Min`; when customizing messages, inspect `getCodes()` (the prioritized list of codes) rather than guessing a single code.
- `getDefaultMessage()`: default message, which may depend on message source/locale.

**Important:** `rejectedValue` does not mean every field always carries its original input there. It is meaningful only in the context of **an error**. For valid fields, read values via the model/binding status as usual.

## 3. How do conversion errors differ from validation errors?

These two branches must be distinguished when testing and rendering:

| Input | Target type | Constraint | Binding result | Validation result |
| --- | --- | --- | --- | --- |
| `age=22` | `Integer` | `@Min(18)` | Succeeded: `22` | Valid |
| `age=17` | `Integer` | `@Min(18)` | Succeeded: `17` | `Min` error |
| `age=abc` | `Integer` | `@Min(18)` | Failed to convert to `Integer` | `typeMismatch` error; may add other errors depending on config |
| `email=not-an-email` | `String` | `@Email` | Succeeded | `Email` error |
| `displayName=""` | `String` | `@NotBlank` | Succeeded: `""` | `NotBlank` error |

If conversion fails, the Java bean may retain `null` or a previous value on the target property; do not assume it holds `"abc"`. For a validation failure, the bound value is normally present in the model, and `FieldError` also holds the rejected value.

A single field can sometimes have more than one error (for example, failed conversion leaves the property `null` and `@NotNull` is also present). Therefore, do not assume a “one FieldError per field” rule; `getFieldErrors("age")` can return multiple items. When looking for a **binding error**, check `isBindingFailure()` rather than grabbing only the first error and assuming it is the only one.

## 4. Runnable Spring Boot 3 + Java 17 example

The example uses Spring MVC, Jakarta Bean Validation, and Thymeleaf. Users visit `GET /signup` and submit `POST /signup`. On error, the controller returns the `signup` view while keeping `BindingResult`. When valid, the application redirects to a sample success page; the example does not persist data to a database.

Directory structure:

~~~text
rejected-values-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/form/
    │   │   ├── FormApplication.java
    │   │   ├── SignupForm.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── templates/signup.html
    │       └── application.properties
    └── test/
        └── java/com/example/form/SignupControllerTest.java
~~~

### 4.1. Maven: pom.xml

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>rejected-values-demo</artifactId>
    <version>1.0.0</version>
    <name>rejected-values-demo</name>

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

Spring Boot 3.3.5 is a pinned example version using the `jakarta.validation.*` namespace and Java 17. In a real project, use your project's managed Spring Boot/BOM version; do not add duplicate validation providers.

### 4.2. Entry point: FormApplication.java

~~~java
package com.example.form;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormApplication.class, args);
    }
}
~~~

### 4.3. Form backing object: SignupForm.java

~~~java
package com.example.form;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
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
~~~

Use a **dedicated DTO for the form** so HTTP requests never write directly onto entity/domain objects. `Integer` clearly surfaces conversion errors (numbers entered as strings) and missing inputs. `@NotNull` checks presence, while `@Min(18)` checks the value after successful conversion.

### 4.4. Controller: SignupController.java

~~~java
package com.example.form;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class SignupController {

    @InitBinder("signupForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "displayName", "email", "age");
    }

    @GetMapping("/signup")
    public String show(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping("/signup")
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "signup";
        }

        // A real application would perform business logic/save data here.
        return "redirect:/signup/success";
    }

    @GetMapping("/signup/success")
    @ResponseBody
    public String success() {
        return "Form accepted";
    }
}
~~~

Key mechanisms:

1. `@ModelAttribute("signupForm")` creates/retrieves the object named `signupForm` and tells Spring to bind matching parameters.
2. `@Valid` triggers Bean Validation after binding.
3. `BindingResult` **must appear immediately after** the `@ModelAttribute` parameter receiving errors. Do not insert `Model`, `HttpServletRequest`, or an unrelated parameter between the two arguments.
4. `bindingResult.hasErrors()` detects both binding errors and validation errors.
5. On error, `return "signup"` renders the same template within **the same POST request**. Spring places the model attribute and its `BindingResult` in the model so the view can display the entered data.
6. Redirect only when there are no errors. The example does not actually persist a user; the `Form accepted` message simply indicates validation passed.
7. `@InitBinder` restricts which properties may be written from the request: `displayName`, `email`, `age`. This reduces mass assignment risk; real projects also need proper DTO design and binding policies.

**Do not do the following in the error branch:**

~~~java
if (bindingResult.hasErrors()) {
    model.addAttribute("signupForm", new SignupForm());
    return "signup";
}
~~~

This is an **incorrect snippet for comparison**, not part of the working controller above. It replaces the newly bound object with an empty one, losing the user's input and potentially desynchronizing the model/`BindingResult` state.

### 4.5. Thymeleaf template: templates/signup.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign Up</title>
    <style>
        .invalid { border: 2px solid #b00020; }
        .error { color: #b00020; }
    </style>
</head>
<body>
<h1>Sign Up</h1>

<form th:action="@{/signup}"
      th:object="${signupForm}"
      method="post">

    <div>
        <label for="displayName">Full name</label>
        <input type="text"
               th:field="*{displayName}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('displayName')}"
           th:errors="*{displayName}"></p>
    </div>

    <div>
        <label for="email">Email</label>
        <input type="text"
               th:field="*{email}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="age">Age</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{age}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('age')}"
           th:errors="*{age}"></p>
    </div>

    <button type="submit">Submit</button>
</form>
</body>
</html>
~~~

Syntax notes:

- `th:object="${signupForm}"` selects the form-backing bean with the exact name `signupForm`.
- `th:field="*{age}"` integrates with Spring binding status: when a `FieldError` exists, it can re-render **the invalid value `"abc"`** even though `form.getAge()` is `null`.
- `th:errors="*{age}"` displays error messages for `age`; `#fields.hasErrors('age')` controls whether the error element is rendered.
- `th:errorclass="invalid"` adds the CSS class when the field has errors.
- `inputmode="numeric"` suggests a numeric keyboard on mobile devices while keeping `type="text"`, avoiding browser rules on `<input type="number">` that discard or normalize a string like `abc`. Server-side validation is still required.
- Spring Thymeleaf escapes content when using `th:field`/`th:errors` under normal template rules. Never render user input with unescaped HTML such as `th:utext`.

The names in `th:object`, `@ModelAttribute`, and the `BindingResult` key must match. When the model object is named `signupForm`, Spring uses the binding result key:

~~~text
org.springframework.validation.BindingResult.signupForm
~~~

The constant `BindingResult.MODEL_KEY_PREFIX` holds this prefix; there is no need to hardcode the key prefix in production code.

### 4.6. application.properties

A minimal configuration file can be used:

~~~properties
spring.thymeleaf.cache=false
server.port=8080
~~~

Disabling the template cache here only makes HTML edits immediately visible during learning/development; do not disable caching by default in production.

### 4.7. Running the example

From the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/signup`. Enter:

~~~text
Full name = Lan
Email     = sai-email
Age       = abc
~~~

Then submit the form. The controller returns the `signup` view, and the form re-displays `Lan`, `sai-email`, and `abc` alongside the corresponding error messages. The response is typically HTTP 200 because the example intentionally re-renders an HTML page; applications may choose another status code if required by a contract.

Next, enter:

~~~text
Full name = Lan
Email     = lan@example.com
Age       = 22
~~~

This time the form has no errors; the controller returns `redirect:/signup/success` (HTTP 302) and the target endpoint returns the text `Form accepted`. The example does not perform persistence.

## 5. Automated testing with MockMvc

In addition to inspecting the form in a browser, verify `BindingResult` directly to catch conversion and validation errors. File `src/test/java/com/example/form/SignupControllerTest.java`:

~~~java
package com.example.form;

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
class SignupControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void initialFormHasBackingObject() throws Exception {
        mockMvc.perform(get("/signup"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeExists("signupForm"));
    }

    @Test
    void typeMismatchKeepsRejectedText() throws Exception {
        var result = mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "sai-email")
                        .param("age", "abc"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "email", "age"))
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);

        Object rawResult = mav.getModel().get(
                BindingResult.MODEL_KEY_PREFIX + "signupForm");

        assertInstanceOf(BindingResult.class, rawResult);
        BindingResult errors = (BindingResult) rawResult;

        FieldError ageError = errors.getFieldError("age");
        assertNotNull(ageError);
        assertTrue(ageError.isBindingFailure());
        assertEquals("abc", ageError.getRejectedValue());
        assertEquals("abc", errors.getFieldValue("age"));

        SignupForm form = (SignupForm)
                mav.getModel().get("signupForm");
        assertNotNull(form);
        assertEquals("Lan", form.getDisplayName());
        assertEquals("sai-email", form.getEmail());
        assertNull(form.getAge());
    }

    @Test
    void minViolationIsNotTypeMismatch() throws Exception {
        var result = mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "17"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "age"))
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);
        BindingResult errors = (BindingResult) mav.getModel()
                .get(BindingResult.MODEL_KEY_PREFIX
                        + "signupForm");

        assertNotNull(errors);
        FieldError ageError = errors.getFieldError("age");
        assertNotNull(ageError);
        assertFalse(ageError.isBindingFailure());
        assertEquals(17, ageError.getRejectedValue());
    }

    @Test
    void validFormRedirects() throws Exception {
        mockMvc.perform(post("/signup")
                        .param("displayName", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "22"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup/success"));
    }
}
~~~

Run command:

~~~bash
mvn test
~~~

Expected assertions:

- `GET /signup` has the `signupForm` model attribute.
- POST with `age=abc` re-renders `signup`, has field errors on `age` and `email`; `FieldError.getRejectedValue()` for `age` holds `"abc"`.
- `BindingResult.getFieldValue("age")` also returns the value the user needs to see when binding fails, whereas `SignupForm.getAge()` is `null` because `"abc"` cannot be assigned to `Integer`.
- POST with `age=17` produces a `@Min(18)` error rather than a type mismatch; the rejected value is the converted integer.
- Valid POST redirects.

The tests inspect the model rather than assuming rendered HTML always keeps the exact same attribute order or CSS. For visual verification, you can add DOM/HTML assertions checking that the input named `age` displays `abc`. For HTML forms, a browser end-to-end test also reveals control-specific behaviors such as number inputs, selects, checkboxes, or JavaScript.

## 6. BindingResult APIs to understand properly

This is essential when debugging in a controller:

~~~java
boolean invalid = bindingResult.hasErrors();

int errorCount = bindingResult.getErrorCount();

FieldError firstAgeError =
        bindingResult.getFieldError("age");

java.util.List<FieldError> ageErrors =
        bindingResult.getFieldErrors("age");

Object displayValue =
        bindingResult.getFieldValue("age");

Object rawProperty =
        bindingResult.getRawFieldValue("age");

String[] suppressed =
        bindingResult.getSuppressedFields();
~~~

This is illustrative code inside a controller where `bindingResult` already exists; it is not a standalone program.

| API | What it returns | When to use |
| --- | --- | --- |
| `hasErrors()` | Whether there is at least one field/global error | Decide whether to re-render the form |
| `getFieldError("age")` | First error for the field or `null` | Quick check for a failing field |
| `getFieldErrors("age")` | List of errors for the field | Display/inspect multiple constraints |
| `getRejectedValue()` | Value rejected by a specific error | Analyze the invalid input cause |
| `isBindingFailure()` | Conversion/binding error vs validation error | Distinguish `typeMismatch` from `Min` |
| `getFieldValue("age")` | Display value for the field: may be the rejected value | Preserve input when conversion fails |
| `getRawFieldValue("age")` | Raw property value on the target without display formatting | Debug target; **do not** substitute for rejected value |
| `getFieldType("age")` | Java type of the property if determinable | Troubleshoot converter errors |
| `getAllErrors()` | Both `FieldError` and `ObjectError` | Display field/global errors |
| `getSuppressedFields()` | Fields suppressed when binder rejects binding | Audit allowed/disallowed field policies |
| `getModel()` | Map containing object and `BindingResult` | When manually building `ModelAndView`/passing binding context to view |

**Key point:** `getRawFieldValue("age")` reflects the target property data, which is typically `null` after conversion failure. `getFieldValue("age")` is designed to return the rejected update on error, making it suitable for showing what the user entered. `FieldError.getRejectedValue()` belongs to an **individual error** and should not be treated as the entire form state.

`BindingResult` is also an `Errors`, offering `rejectValue(...)` to register manual business errors. When adding errors manually, provide appropriate codes and values; manual errors are not automatically binding failures. Only rely on `getRejectedValue()` from errors populated with accurate data.

### 6.1. Model has two related entries

When Spring creates a `BindingResult` for an object named `signupForm`, the view can receive:

~~~text
"signupForm" -> bound SignupForm
"org.springframework.validation.BindingResult.signupForm" -> BindingResult
~~~

Via the API:

~~~java
String errorsKey =
        BindingResult.MODEL_KEY_PREFIX + "signupForm";

Object errors = model.asMap().get(errorsKey);
~~~

This snippet explains the model contract; the main controller example needs no manual manipulation. If custom code constructs a `ModelAndView` manually, it may need to pass both the object and binding result, e.g., using `bindingResult.getModel()`. In the standard `@ModelAttribute + BindingResult` flow, Spring handles this when rendering the view.

## 7. Why does Thymeleaf `th:field` preserve invalid values too?

When a form is bound to an object via `th:object`, `th:field="*{age}"` is not equivalent to simply reading `signupForm.age`. The Thymeleaf/Spring integration checks the field's **binding status**, allowing it to pull the rejected value from `BindingResult` rather than relying solely on the bean getter.

Comparison:

~~~html
<!-- Correct: integrates Spring binding -->
<input type="text" th:field="*{age}">

<!-- May lose "abc" if age is Integer and binding fails -->
<input type="text" th:value="${signupForm.age}">
~~~

These two lines are only a side-by-side comparison inside a template with `th:object`; the second line intentionally illustrates the problematic approach. When `age` has a type mismatch, the Java property may be `null`, leaving `th:value` with nothing to display even though `BindingResult` still holds `"abc"`.

Similarly, with JSP Spring form tags:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form modelAttribute="signupForm" method="post" action="/signup">
    <form:input path="age"/>
    <form:errors path="age" cssClass="error"/>
    <button type="submit">Submit</button>
</form:form>
~~~

This is a **JSP alternative to Thymeleaf**, not part of the Maven Thymeleaf project above. `<form:input>` and `<form:errors>` also rely on the Spring binding context. A separate JSP view resolver configuration is required if using JSP.

Not every template engine uses `BindingResult` automatically. If rendering HTML manually or using an engine without Spring integration, you must explicitly retrieve `getFieldValue()`/`FieldError` and escape content properly for context to preserve rejected input.

## 8. Redirecting when a form is invalid: why data gets lost

The following lines mean very different things:

~~~java
if (bindingResult.hasErrors()) {
    return "signup";
}
~~~

This is what the main example uses: same request, model and `BindingResult` remain available, and the view re-displays inputs and errors.

~~~java
if (bindingResult.hasErrors()) {
    return "redirect:/signup";
}
~~~

This is an **incorrect example when no state-preservation mechanism is present**. A redirect triggers a new GET request; the POST's request-scoped model attributes and `BindingResult` do not carry over automatically. If the GET handler creates `new SignupForm()`, the form becomes blank. This mistake is often misdiagnosed as “Thymeleaf isn't keeping values”.

### 8.1. When PRG is truly needed for the error branch

The **Post/Redirect/Get** pattern is useful after success to avoid form resubmission on refresh. If redirecting on error is strictly required, you must deliberately transfer **both the form object and `BindingResult`** via flash attributes. Illustrative controller snippet:

~~~java
redirectAttributes.addFlashAttribute(
        "signupForm", form);

redirectAttributes.addFlashAttribute(
        BindingResult.MODEL_KEY_PREFIX + "signupForm",
        bindingResult);

return "redirect:/signup";
~~~

This snippet assumes `RedirectAttributes redirectAttributes` is also injected into the handler. The GET endpoint must check whether a model/flash attribute already exists before creating a new object, otherwise it will overwrite the flashed data. Flash attributes generally rely on session/redirect lifecycle; consider sensitive data, object size, serialized state, and concurrency across multiple tabs. For typical form apps, **returning the same view on error and redirecting on success** is easier to control.

### 8.2. Do not preserve form inputs via query strings

Avoid putting invalid user inputs (especially emails, tokens, or sensitive information) into the URL like:

~~~text
/signup?email=sai-email&age=abc
~~~

URLs can end up in browser history, server logs, analytics, and `Referer` headers. If the requirement is merely preserving form inputs after a failed POST, `BindingResult` in a server-rendered view achieves that without putting raw input in the URL.

## 9. Common pitfalls that alter or lose values

### 9.1. Inconsistent model attribute names

If POST uses `@ModelAttribute("registration")` while the view uses `th:object="${signupForm}"`, the template engine does not look at the same object and binding result. Keep the name consistent across GET, POST, template, and `BindingResult.MODEL_KEY_PREFIX + objectName`.

### 9.2. HTML field names not matching Java properties

Spring binds by field name, e.g., `name="displayName"` with `setDisplayName(...)`. `th:field="*{displayName}"` generates matching `name` and `id` attributes. If you manually write `name="full_name"` while the model only has `displayName`, you need custom binding/naming configuration; Spring cannot guess that two names are synonymous.

### 9.3. Input types with browser-specific rules

`<input type="number">` may fail to display a string like `abc` because browsers enforce HTML form control rules. To preserve any invalid text cleanly to demonstrate server errors, `type="text" inputmode="numeric"` is an easily observable choice. Regardless of control type, **the server must still validate** types and bounds.

For `select`, `checkbox`, radio buttons, and multi-selects, preserving state is not as simple as setting a single `value` string. Use proper `th:field` and `th:checked`/selected integration, and test when selections are missing or invalid. Multi-value fields require compatible Java/collection types.

### 9.4. Date, number, and locale formatting

`LocalDate`, `BigDecimal`, currencies, and timestamps use locale-aware conversion/formatting. For example, input `31/02/2026` cannot form a valid date; the model property may remain `null` while `BindingResult` retains the invalid text. Configure `@DateTimeFormat`, `Formatter`, or `Converter` to match business rules, and let the view read values through Spring binding integration.

Do not forcibly reformat every date/number into a fixed format after an error, as that can change its meaning or prevent users from recognizing what they typed. When conversion succeeds but a constraint fails, the view may show a formatted value according to the application's formatter; **this differs** from preserving the raw string from a failed conversion.

### 9.5. Nested properties and collection indexes

If a form has `contact.address.city` or `items[0].quantity`, error paths use the corresponding field names:

~~~text
contact.address.city
items[0].quantity
~~~

For the view to re-display values in the right inputs, Spring binding must recognize the nested path and the template must bind the matching path. Collections may require element initialization, valid indexes, and auto-grow limits; never let HTTP input create unbounded collections. Inspect `FieldError.getField()` to confirm errors attach to the intended index/property.

### 9.6. Do not “fix” errors by clearing FieldErrors

Calling `bindingResult.getFieldErrors().clear()` is not a reliable way to alter results and may not be supported by the returned collection. To normalize inputs such as trimming whitespace, define clear conversion/normalization before validation and test how values display. Do not delete errors simply to hide messages in the template.

## 10. Security and limits of preserving input

The “preserve entered values” UX goal has important exceptions:

- **Passwords, OTPs, tokens, API keys, card numbers:** never automatically echo secret inputs back into HTML input values, error messages, flash sessions, or logs. Design forms so users re-enter sensitive fields.
- **XSS:** render via `th:field` / `th:text` (context-aware escaping), never `th:utext` with untrusted input. Apply proper escaping for attribute/URL/JS contexts per template policy.
- **Mass assignment:** avoid binding HTTP requests directly onto entities containing administrative fields such as `id`, `role`, `approved`. Use a dedicated form DTO; if property binding is enabled, consider `WebDataBinder.setAllowedFields(...)` and inspect `getSuppressedFields()`.
- **Error messages:** avoid placing raw `getRejectedValue()` into exceptions/logs where personal data may appear; prefer concise messages and stable field codes.
- **Multiple tabs/redirects:** reusing flash/session objects across concurrent submissions can cause confusion. Prefer same-request re-rendering on form errors.
- **Server-side trust:** do not assume re-rendered values are valid. Execute business logic only after binding and validation pass, and continue enforcing domain rules at the appropriate layer.

### CSRF when Spring Security is enabled

The demo omits Spring Security to focus on binding. In applications with CSRF protection, POST forms must submit a CSRF token configured per Spring Security/Thymeleaf integration. Never disable CSRF protection because form validation fails. Distinguish CSRF-related 403 errors from `BindingResult.hasErrors()`, as CSRF failures can occur before the controller is invoked.

## 11. Common errors table

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| Invalid POST returns an empty form | Returning `redirect:/signup` without flash, or GET creates a new model | Return the same view on error; keep `BindingResult` |
| `age=abc` turns into a blank input | Rendering `form.getAge()` or `th:value` instead of binding status | Use `th:field`/`getFieldValue("age")` |
| Controller skips `hasErrors()` branch | `BindingResult` not immediately after `@ModelAttribute` or validation not triggered | Fix parameter order; verify `@Valid` and validation starter |
| No error message appears next to field | `th:errors` uses wrong property/object name or missing constraint | Align model name, field name, and binding path |
| `typeMismatch` occurs but bean field stays null | Converter could not assign value, which is expected | Read rejected update from `BindingResult` instead of bean getter |
| Value `17` causes Min error | Conversion succeeded; value is below `@Min(18)` | Re-display `17` with validation message |
| Cannot tell which error occurred | Only checking `getErrorCount()` | Inspect `getFieldErrors()`, `getField()`, `getCodes()`, `isBindingFailure()` |
| Form gets overwritten after POST | Controller replaces `signupForm` with a different object | Keep the bound object for that view |
| Custom formatter swallows bad text | Converter returns an inappropriate default instead of failing | Fix conversion semantics; preserve error details |
| Browser fails to display invalid text for number field | HTML `type="number"` rejects non-numeric text | Use an appropriate control; test in a real browser |
| Secret value appears in HTML | Blindly echoing all fields | Never echo passwords/tokens; design dedicated fields |
| Input preserved but `role`/`admin` changed unintentionally | Direct entity binding or unrestricted allowed fields | Use DTOs and field allowlists |
| Error messages change by locale | `MessageSource`/`Formatter` adjusts display | Test errors across supported locales |

## 12. Troubleshooting checklist when a form “loses data”

When investigating a real issue, check in order:

1. Check what `name=value` pairs the request actually sent in DevTools Network.
2. Verify the controller declares `@ModelAttribute("...")` with `BindingResult` immediately following it.
3. Inspect `bindingResult.hasErrors()`, `getFieldErrors()`, `getFieldError("field").getRejectedValue()`, `isBindingFailure()`, and `getFieldValue("field")`. Do not log sensitive data.
4. Confirm the error branch returns the **view name** directly without an unintended redirect.
5. Verify the rendered model contains the exact object name and `BindingResult.MODEL_KEY_PREFIX + objectName`, especially when using a custom `ModelAndView`.
6. In the template, prefer `th:field` and `th:errors`; check element `name`, field path, HTML input type, and whether custom JavaScript overwrites values after render.
7. Separate conversion errors from Bean Validation errors; test both `age=abc` and `age=17`.
8. After fixing, test both valid and invalid requests, including refresh/redirect behavior and multiple tabs.

## 13. Practice exercises

**Exercise 1 — Analyzing differences:** Submit `age=abc` into an `Integer age` field annotated with `@Min(18)`. Why can the object getter return `null` while `BindingResult.getFieldValue("age")` still returns `"abc"`? Answer based on the two steps of conversion and storing rejected input.

**Exercise 2 — Preserving input:** Change the template from `th:field="*{age}"` to `th:value="${signupForm.age}"` and enter a non-numeric string. Compare the UI and explain why retaining binding status is necessary.

**Exercise 3 — Adding a date field:** Add `birthDate: LocalDate` with appropriate formatting and validation rules. Submit an invalid date, then compare `getRejectedValue()`, `getFieldValue()`, and the value on the object.

**Exercise 4 — Intentional redirect:** Change the error branch to `redirect:/signup` and observe the data disappearing. Explain which two model keys must be carried over if using flash attributes and why GET must not overwrite them.

**Exercise 5 — Nested errors:** Create `AddressForm` with field `city`, annotate the form's `address` field with `@Valid`, and render `th:field="*{address.city}"`. Verify the `FieldError` path is `address.city` and invalid nested input remains visible on re-render.

**Exercise 6 — Security test:** Try adding POST parameter `role=ADMIN` when `SignupForm` has no `role` or `role` is not in allowed fields. Verify the request cannot alter administrative state; never use a sensitive entity directly as a form-backing bean.

### Key takeaway

**Preserving form input is not just keeping the Java object.** If conversion fails, the object cannot hold the text the user typed. `BindingResult` stores rejected values and field errors; `th:field`/Spring form tags read binding status to re-display input in the same request. Controllers use `@Valid @ModelAttribute`, place `BindingResult` immediately after it, **return the view on error**, and redirect only after validation passes. Distinguish conversion failures from validation failures and avoid echoing secret data.

## References

- [Spring Framework Reference — @ModelAttribute in handler methods, BindingResult, and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework API — BindingResult, getFieldValue, getModel, MODEL_KEY_PREFIX](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework API — FieldError and getRejectedValue/isBindingFailure](https://docs.spring.io/spring-framework/docs/6.2.15-SNAPSHOT/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework API — AbstractBindingResult.getFieldValue](https://docs.spring.io/spring-framework/docs/6.2.0-M7/javadoc-api/org/springframework/validation/AbstractBindingResult.html)
- [Thymeleaf + Spring Tutorial — th:field, th:errors, and Spring form integration](https://www.thymeleaf.org/doc/tutorials/3.0/thymeleafspring.html)
- [Spring Framework Reference — Redirect Attributes, Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html)
- [Spring Framework Reference — MVC Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html)
