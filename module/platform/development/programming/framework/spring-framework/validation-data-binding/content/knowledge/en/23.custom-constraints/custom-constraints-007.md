# Mapping Object-Level Errors to a Field Path in Spring Validation

## 1. Problem statement and desired outcome

A rule checking **relationships across multiple properties** is usually placed at the object level (class-level): for example, `password` must equal `confirmPassword`, end date must be after start date, or `minPrice` must not exceed `maxPrice`. If a class-level constraint emits its default error, the violation property path points to the object itself; in Spring MVC the error usually becomes an `ObjectError`, whereas UIs wanting to render an error right beneath a specific input box typically need a `FieldError`.

**Goal:** keep validating the cross-field rule, but attach the message to the path of the field responsible for fixing the error, such as `confirmPassword`. With Jakarta Bean Validation, do this **directly inside `ConstraintValidator`** using `ConstraintValidatorContext.addPropertyNode(...)`. With manual validation in Spring, use `Errors.rejectValue(...)` or `BindingResult.rejectValue(...)` to register a field error.

Example when the two passwords differ:

| Recording approach | Path / error type | Typical presentation |
| --- | --- | --- |
| Default class-level violation | Empty property path at root; Spring receives `ObjectError` | General form-level message |
| Class-level violation + `addPropertyNode("confirmPassword")` | Property path `confirmPassword`; Spring receives `FieldError` | Message next to the confirm password input |
| Spring `errors.reject("password.mismatch", ...)` | `ObjectError` | General message |
| Spring `errors.rejectValue("confirmPassword", ...)` | `FieldError` | Message next to the confirm password input |

You neither need to nor should try to "convert the type" of an `ObjectError` after it has been created. Emit the error with the **right path directly at the validation source**.

## 2. Mapping mechanism from Bean Validation to Spring

1. `@Valid` on a model parameter instructs Bean Validation to validate the object, provided a validation provider is configured.
2. The class-level constraint executes `ConstraintValidator<Annotation, Form>.isValid(form, context)`.
3. If it returns `false` without adjusting `context`, the violation sits on the root object; the path is typically an empty string.
4. Calling `context.disableDefaultConstraintViolation()` and building a violation with `addPropertyNode("confirmPassword")` gives the new violation the property path `confirmPassword`.
5. Spring's integration layer converts violations with field paths into field errors on `BindingResult`; Thymeleaf or API handlers can access them via `getFieldErrors("confirmPassword")`.

**Two mandatory details:** after `buildConstraintViolationWithTemplate(...)` you must finish with `addConstraintViolation()`; if you disable the default violation, you must create at least one new violation when returning `false`. Do not call `addBeanNode()` if you want a property path.

## 3. Complete example: matching passwords, message on `confirmPassword`

The example uses Java 17, Spring Boot 3.5.7, Spring MVC, and Jakarta Validation (`jakarta.validation.*` packages). Each class below is in package `com.example.demo`. Main structure:

~~~text
pom.xml
src/main/java/com/example/demo/
  DemoApplication.java
  RegistrationForm.java
  MatchingPasswords.java
  MatchingPasswordsValidator.java
  RegistrationController.java
src/main/resources/templates/register.html
src/test/java/com/example/demo/RegistrationValidationTest.java
~~~

### 3.1. Maven dependencies

~~~xml
<!-- pom.xml -->
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
    <artifactId>validation-field-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

`spring-boot-starter-validation` supplies the Bean Validation provider; having only `jakarta.validation-api` without a provider is insufficient to run the example. For Spring Framework 5 / Boot 2, the corresponding imports belong to `javax.validation.*`; do not mix the two namespaces.

### 3.2. Object to validate

~~~java
// src/main/java/com/example/demo/RegistrationForm.java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

@MatchingPasswords
public class RegistrationForm {
    @NotBlank(message = "Please enter a password")
    private String password;

    @NotBlank(message = "Please confirm your password")
    private String confirmPassword;

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getConfirmPassword() {
        return confirmPassword;
    }

    public void setConfirmPassword(String confirmPassword) {
        this.confirmPassword = confirmPassword;
    }
}
~~~

`@MatchingPasswords` is attached at the **class** level because it needs to inspect both values. `@NotBlank` still checks each field independently; the cross-field validator avoids producing duplicate errors for blank values.

### 3.3. Declaring the class-level constraint

~~~java
// src/main/java/com/example/demo/MatchingPasswords.java
package com.example.demo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = MatchingPasswordsValidator.class)
public @interface MatchingPasswords {
    String message() default "Confirmation password does not match";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

`message`, `groups`, and `payload` are the standard elements of a Bean Validation constraint annotation. `@Target(TYPE)` lets the rule run on the entire `RegistrationForm`.

### 3.4. Attaching the object-level error to a specific field

~~~java
// src/main/java/com/example/demo/MatchingPasswordsValidator.java
package com.example.demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.Objects;

public final class MatchingPasswordsValidator
        implements ConstraintValidator<MatchingPasswords, RegistrationForm> {

    @Override
    public boolean isValid(
            RegistrationForm form,
            ConstraintValidatorContext context) {

        if (form == null) {
            return true; // Use @NotNull separately if the object must be present.
        }

        String password = form.getPassword();
        String confirmation = form.getConfirmPassword();

        if (password == null || confirmation == null
                || password.isBlank() || confirmation.isBlank()) {
            return true; // Let @NotBlank handle each blank field.
        }

        if (Objects.equals(password, confirmation)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                    context.getDefaultConstraintMessageTemplate())
                .addPropertyNode("confirmPassword")
                .addConstraintViolation();

        return false;
    }
}
~~~

How to read the key section:

- `disableDefaultConstraintViolation()` removes the default object-level violation, preventing both a general error and a field error from appearing for the same mismatch.
- `getDefaultConstraintMessageTemplate()` reuses the message declared on the annotation; it can be replaced with another template/key.
- `addPropertyNode("confirmPassword")` **appends the property name to the violation path**, without mutating the validated object or reassigning field values.
- `addConstraintViolation()` actually registers the new violation; `return false` reports the invalid result.

With `password="abc123"` and `confirmPassword="xyz456"`, the violation's `getPropertyPath().toString()` equals **`confirmPassword`**. If you omit `addPropertyNode(...)` and leave the default, the path stays at root.

### 3.5. Connecting Spring MVC and Thymeleaf

~~~java
// src/main/java/com/example/demo/DemoApplication.java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

~~~java
// src/main/java/com/example/demo/RegistrationController.java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
@RequestMapping("/register")
public class RegistrationController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("registrationForm", new RegistrationForm());
        return "register";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "register";
        }
        return "redirect:/register/success";
    }

    @GetMapping("/success")
    @ResponseBody
    public String success() {
        return "Registration valid";
    }
}
~~~

`BindingResult` must sit **immediately after** its corresponding `@Valid @ModelAttribute` parameter so Spring supplies binding/validation errors for that model. If placed in the wrong position, error handling may change or controller invocation may fail.

~~~html
<!-- src/main/resources/templates/register.html -->
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Register</title></head>
<body>
<form method="post" th:action="@{/register}"
      th:object="${registrationForm}">
    <label for="password">Password</label>
    <input id="password" type="password" th:field="*{password}">
    <p th:if="${#fields.hasErrors('password')}"
       th:errors="*{password}"></p>

    <label for="confirmPassword">Confirm password</label>
    <input id="confirmPassword" type="password"
           th:field="*{confirmPassword}">
    <p th:if="${#fields.hasErrors('confirmPassword')}"
       th:errors="*{confirmPassword}"></p>

    <button type="submit">Register</button>
</form>
</body>
</html>
~~~

Submitting two different values returns the `register` view. Because the error is attached to `confirmPassword`, `#fields.hasErrors('confirmPassword')` is `true` and `th:errors="*{confirmPassword}"` displays "Confirmation password does not match" next to the second input box. No manual error-transfer code is needed in the controller.

### 3.6. Verifying the property path with JUnit

~~~java
// src/test/java/com/example/demo/RegistrationValidationTest.java
package com.example.demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class RegistrationValidationTest {

    @Autowired
    Validator validator;

    @Test
    void mismatchIsReportedOnConfirmationField() {
        RegistrationForm form = new RegistrationForm();
        form.setPassword("abc123");
        form.setConfirmPassword("xyz456");

        Set<ConstraintViolation<RegistrationForm>> violations =
                validator.validate(form);

        assertEquals(1, violations.size());
        ConstraintViolation<RegistrationForm> error =
                violations.iterator().next();

        assertEquals("confirmPassword",
                error.getPropertyPath().toString());
        assertEquals("Confirmation password does not match",
                error.getMessage());
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Expected verification results: the test passes; opening `http://localhost:8080/register` in a browser, entering two differing passwords, and submitting displays the message next to the `confirmPassword` field. Do not predict exact Maven log lines because they depend on the environment. In Spring MVC, you can equivalently verify `bindingResult.getFieldError("confirmPassword") != null` and that `bindingResult.getGlobalErrors()` contains no error from this constraint.

## 4. Alternative: emitting `FieldError` directly with Spring `Errors`

When the cross-field rule lives in a custom `org.springframework.validation.Validator`, or you validate manually inside a controller, you can register a field error directly:

~~~java
// Illustrative snippet inside a controller/validator with form and errors:
if (form.getPassword() != null
        && form.getConfirmPassword() != null
        && !java.util.Objects.equals(
                form.getPassword(), form.getConfirmPassword())) {
    errors.rejectValue(
            "confirmPassword",
            "password.mismatch",
            "Confirmation password does not match");
}
~~~

`errors` here can be `BindingResult` or the `Errors` interface; `rejectValue(field, errorCode, defaultMessage)` records a `FieldError`. `password.mismatch` is the **error code** looked up by the messages/i18n system, while the last string is the fallback message. Unlike `errors.reject("password.mismatch", ...)`, which creates an **`ObjectError`**.

Note: the snippet above is an **alternative** to `@MatchingPasswords`; do not run both checks for the same rule because users may see duplicate messages. When form structure and rules are stable, building the property path directly inside `ConstraintValidator` is usually easier to reuse across MVC, services, and `jakarta.validation.Validator` checks.

**Do not call `rejectValue("", ...)` or pass `null` when targeting a specific field.** On a root object, an empty field can become a global error; provide the exact field name.

## 5. Nested paths, multiple fields, and lists

### A nested field

If a class-level constraint inspects the entire `OrderForm` but needs to point to `shippingAddress.postalCode`, build the path node by node:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
            "Postal code does not match the shipping country")
        .addPropertyNode("shippingAddress")
        .addPropertyNode("postalCode")
        .addConstraintViolation();
return false;
~~~

Spring sees the field name as `shippingAddress.postalCode` when the object structure and path align. With Spring `Errors` at the root, you can use `errors.rejectValue("shippingAddress.postalCode", ...)`; when `Errors` already has a nested path set, field names are relative to the current nested path.

### Reporting errors on two fields

A rule like "`startDate <= endDate`" is often helpful when shown on `endDate`; if the UI genuinely needs to show it on **both** fields, create **two** separate custom violations before returning `false`:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate("Invalid date range")
        .addPropertyNode("startDate")
        .addConstraintViolation();
context.buildConstraintViolationWithTemplate("Invalid date range")
        .addPropertyNode("endDate")
        .addConstraintViolation();
return false;
~~~

Do this only if UX has a clear reason, because Spring will store two separate errors. For collections (`items[2].price`) or maps, Jakarta Validation provides the `inIterable().atIndex(...)` / `atKey(...)` API to represent elements accurately; do not stuff bracketed strings into a single property node name when the API supports structured nodes.

## 6. Distinguishing error objects and handling approaches

| Concept | Meaning | Verification example |
| --- | --- | --- |
| `ConstraintViolation#getPropertyPath()` | Path generated by Jakarta Bean Validation | `confirmPassword` |
| `ObjectError` | Error attached to the entire object in Spring | `errors.getGlobalErrors()` |
| `FieldError` | Error attached to a single field in Spring | `errors.getFieldErrors("confirmPassword")` |
| `BindingResult` | Collection of binding and validation errors for a model | `errors.hasFieldErrors("confirmPassword")` |
| `reject(...)` | Adds a global error | Rule not belonging to a specific field |
| `rejectValue(...)` | Adds a field error | Points directly to where the user needs to fix input |

**When an object-level error already exists:** calling `rejectValue` only **adds** a field error; it does not automatically delete the old object-wide error. With a class-level constraint, the right fix is changing violation emission as in section 3.4; with a custom Spring `Validator`, call `rejectValue` from the start. If re-shaping errors from an external system, construct a controlled output error model instead of mutating `BindingResult`'s error list directly.

## 7. Common pitfalls

1. **Forgetting `disableDefaultConstraintViolation()`:** you may receive both a global error and a field error for one rule. If you intend to report only on a field, disable the default before adding the custom violation.
2. **Forgetting `addConstraintViolation()`:** the builder chain has not registered the new error; when the default is disabled, returning `false` is an invalid violation state.
3. **Wrong property name:** `"confirm_password"` differs from `"confirmPassword"`. The property path must point to an actual property of the validated object; nested names must reflect the real structure.
4. **Placing `@MatchingPasswords` on a single field:** `ConstraintValidator` in the example accepts the entire `RegistrationForm`, so the annotation belongs at the class level. Field-level constraints already have that field as their base path.
5. **Placing `BindingResult` in the wrong position:** in Spring MVC, the `BindingResult`/`Errors` parameter must immediately follow the model parameter whose errors it receives.
6. **Missing validation provider or mixing `javax`/`jakarta`:** Spring Boot 3 uses Jakarta; you need a validation dependency with a provider. `@Valid` alone does nothing if validation is not configured.
7. **Duplicate checks when fields are empty:** when combining `@NotBlank` with password matching, decide clearly whether both errors should appear. The example skips matching when a field is blank.
8. **Exposing entire errors as JSON:** `FieldError` can carry the rejected value; never return or log raw sensitive values like passwords. Provide only the field, error code, and appropriate message to clients.
9. **Assuming class-level constraints are always global:** class-level describes *the scope of data inspected*; property path describes *where the message is attached*. These two decisions are independent when using custom violations.

## 8. Practical checklist

- Clearly identify which field the user should fix; prefer an actionable field.
- If using Jakarta Bean Validation, put the constraint on the class when multiple values are needed; inside the validator, disable default and add `addPropertyNode(...).addConstraintViolation()`.
- If using Spring `Validator` or manual checks, use `rejectValue` to emit a `FieldError` from the outset.
- Ensure field/path names really exist, nested data is handled properly, and forms pair `@Valid` with `BindingResult` in the right parameter order.
- Test valid, invalid, null/empty cases, UI messages next to the field, and verify there are no duplicate errors or leaked sensitive values.

## References

- Jakarta Validation `ConstraintValidatorContext` and adding property nodes: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/constraintvalidatorcontext
- Hibernate Validator Reference Guide, custom property paths section: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-custom-property-paths
- Spring `Errors`/`BindingResult` and `rejectValue`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html
