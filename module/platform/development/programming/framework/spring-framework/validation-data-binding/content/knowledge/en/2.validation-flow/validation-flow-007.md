# Triggering Validators After the Binding Step in Spring MVC

## 1. Why Is Validation Needed After Binding?

When receiving an HTTP request, Spring MVC can take string data from form/query/path/header, convert types, and assign them into a Java object. That stage is called **data binding**. Binding answers the question "Can the data from the request be placed into this object?", whereas **validation** answers "Once populated, does the object satisfy the rules?"

For example, a form submits `age=17`: converting the string `"17"` to `Integer` succeeds, but the business rule "age 18 or older" fails. Conversely, `age=abc` can cause a type conversion error during binding, before the `@Min(18)` rule is even evaluated. Both categories of errors can be stored in `BindingResult` for the controller layer to handle.

The crux is that **registering a validator** and **triggering a validator** are two separate actions. `@InitBinder` configures `WebDataBinder` (including attaching validators) **before binding**; `@Valid`, `@Validated`, or calling `binder.validate()` requests validation **after data has been bound**.

## 2. Where Validation Sits in the Request Lifecycle

For an `@ModelAttribute` parameter in Spring MVC, the basic flow can be pictured as:

~~~text
HTTP request
    │
    ▼
Spring MVC selects handler/controller
    │
    ▼
Create or fetch model attribute; create WebDataBinder
    │
    ├── Run @InitBinder to configure converters, allowedFields, validators...
    │
    ▼
Bind request values into the object
    ├── Convert types, assign constructor/properties
    └── Record binding errors (e.g., typeMismatch) into BindingResult
    │
    ▼
Is @Valid / @Validated present on the parameter?
    ├── Yes → invoke matching validators, add validation errors
    └── No  → do not automatically run Bean Validation for that parameter
    │
    ▼
BindingResult holds binding + validation results
    ├── BindingResult/Errors immediately after parameter → controller handles it
    └── Absent → Spring may translate errors into an exception
~~~

Points to distinguish:

1. **Binding always precedes object validation** in the standard `@ModelAttribute` flow; validators receive an object that has already gone through type conversion/data assignment.
2. `@InitBinder` runs during **binder preparation**, not as a "post-binding" callback. Put `binder.addValidators(...)` inside it to declare validators that will be used later.
3. `BindingResult` aggregates `FieldError`/`ObjectError`, including both conversion errors and rule errors; call `hasErrors()` to decide whether to proceed.
4. Spring creates a separate binder per object/request processing pass as needed; do not retain `WebDataBinder` as shared state across requests.

## 3. Common Pattern: `@Valid` After `@ModelAttribute` Binding

The example below targets **Spring Framework 6.x / Spring Boot 3.x, Java 17+**, using Jakarta Bean Validation. In a Spring Boot MVC project, both the MVC starter and a validation provider are required:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

If using standalone Spring MVC instead of Boot, configure a corresponding Bean Validation provider. When Bean Validation is on the classpath, Spring MVC typically registers `LocalValidatorFactoryBean` as the default validator backing `@Valid` and `@Validated`.

**DTO receiving form data**, file `RegistrationForm.java`:

~~~java
package com.example.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank(message = "Username must not be blank")
        String username,

        @NotBlank @Email
        String email,

        @NotNull @Min(18)
        Integer age
) {}
~~~

Records work with constructor binding supported in Spring MVC 6.x. You can substitute a JavaBean with a no-arg constructor and getters/setters when using property binding. Note that `@Min(18)` alone does not forbid `null`, so `@NotNull` is also required if the age field is mandatory.

**Controller**, file `RegistrationController.java`:

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.BindingResult;

import java.util.Map;

@RestController
public class RegistrationController {

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var details = errors.getFieldErrors().stream()
                    .map(e -> e.getField() + ": " + e.getDefaultMessage())
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", details));
        }

        return ResponseEntity.ok(Map.of("status", "accepted"));
    }
}
~~~

Here, Spring reads `username`, `email`, and `age` from the form, binds them into `RegistrationForm`, sees `@Valid`, and invokes Bean Validation. `BindingResult errors` **must sit immediately after** the validated parameter so the controller receives errors for that exact object. If errors exist, the controller returns HTTP 400 itself; if valid, it returns HTTP 200. The snippet assumes the Boot application already has a `@SpringBootApplication` class to launch it.

Test an invalid request:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "username=&email=bad-email&age=17"
~~~

The expected result is **400 Bad Request**, with errors related to blank username, malformed email, and age under 18. **Do not depend on error ordering or exact message wording** as they are influenced by the Bean Validation provider and message/locale configuration. A valid request such as the following will receive a response containing `{"status":"accepted"}`:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "username=linh&email=linh%40example.com&age=22"
~~~

What triggers the validator to run? Placing `@Valid` on the **handler parameter**. Simply adding `@NotBlank`, `@Email` to the DTO without `@Valid`/`@Validated` at the request-handling point does not guarantee DTO validation will run automatically.

## 4. `@Validated` and Validation Groups

Spring's `@Validated` also triggers validation when placed on an `@ModelAttribute` parameter, and additionally lets you pass **validation groups**. For example, when creating a new account, username is required:

~~~java
package com.example.demo;

public interface OnCreate {}
~~~

~~~java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

public record AccountForm(
        @NotBlank(groups = OnCreate.class) String username
) {}
~~~

~~~java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Validated(OnCreate.class) @ModelAttribute AccountForm form,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid information");
    }
    return ResponseEntity.ok("created");
}
~~~

This handler snippet is an **excerpt** inside a controller that already imports `org.springframework.validation.annotation.Validated`, `BindingResult`, and related MVC annotations. `@Validated(OnCreate.class)` selects the `OnCreate` group. Constraints belonging only to the `Default` group are not automatically checked in a call specifying only `OnCreate`; to check multiple groups, specify them explicitly or design group inheritance accordingly.

At the controller level, avoid confusing `@Validated` on a **DTO parameter** with `@Validated` on the **controller class** (which triggers AOP-based method validation in certain configurations/versions). Starting in Spring MVC 6.1+, the framework also supports direct method validation for constraints placed on method parameters, so the exception mechanism may differ from single-DTO validation.

## 5. Combining Bean Validation with a Custom Spring `Validator`

When a rule is difficult to express with built-in annotations, you can implement `org.springframework.validation.Validator`. For example, disallowing the username "admin". File `UsernameRuleValidator.java`:

~~~java
package com.example.demo;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;
        if ("admin".equalsIgnoreCase(form.username())) {
            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "This username is reserved"
            );
        }
    }
}
~~~

Register it in `RegistrationController` using constructor injection and an `@InitBinder` method:

~~~java
private final UsernameRuleValidator usernameRuleValidator;

public RegistrationController(UsernameRuleValidator usernameRuleValidator) {
    this.usernameRuleValidator = usernameRuleValidator;
}

@InitBinder("form")
void configureBinder(WebDataBinder binder) {
    binder.addValidators(usernameRuleValidator);
}
~~~

This is also an **addition inside the controller**, with imports `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. Because the handler declared `@ModelAttribute("form")`, `@InitBinder("form")` applies to that attribute's binder.

Upon receiving the form, Spring will:

- create/configure the binder and add `UsernameRuleValidator`;
- bind the request data;
- encounter `@Valid` and run the relevant validators (Bean Validation validator and added validators);
- collect errors into the same `BindingResult`. With `username=admin`, the error code `username.reserved` is attached to the `username` field.

Prefer `addValidators(...)` when adding rules, because `setValidator(...)` replaces the existing validator on the binder and can drop annotation-based constraints unless intentionally reconfigured. `supports(Class<?>)` must return `true` for the target object type; registering a validator that does not support the data type can cause the binder to reject the configuration.

If a rule is shared across multiple controllers, consider `@ControllerAdvice` with `@InitBinder`; if you need to replace the default MVC-wide validator, configure `WebMvcConfigurer#getValidator()`. Choose the narrowest scope that meets the requirement.

## 6. Seeing the Sequence Clearly with Plain Spring `DataBinder`

Outside MVC, `DataBinder` also demonstrates clearly that **binding does not automatically mean validating**. The complete example below uses Spring `spring-context`/`spring-beans` available on the project classpath:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class DataBinderSequenceDemo {

    public static class Order {
        private int quantity;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    public static class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getQuantity() <= 0) {
                errors.rejectValue(
                        "quantity", "quantity.positive",
                        "Quantity must be greater than 0"
                );
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order();
        DataBinder binder = new DataBinder(order);
        binder.addValidators(new OrderValidator());

        binder.bind(new MutablePropertyValues(Map.of("quantity", "0")));
        System.out.println("After binding: " +
                binder.getBindingResult().getErrorCount());

        binder.validate();
        System.out.println("After validation: " +
                binder.getBindingResult().getErrorCount());
        System.out.println(
                binder.getBindingResult()
                        .getFieldError("quantity")
                        .getDefaultMessage()
        );
    }
}
~~~

When running `main` in a Java 17+ project with the Spring libraries listed above, stdout is:

~~~text
After binding: 0
After validation: 1
Quantity must be greater than 0
~~~

Here, `quantity="0"` converted to `int 0` successfully so it produced no binding error; `validate()` is what produced the business error. The example calls `binder.validate()` explicitly because there is no MVC controller or annotation to trigger it automatically. In MVC when `@Valid` is already used, you normally **do not need to call validate a second time**.

## 7. Differences When Using `@RequestBody` (JSON)

With form/query + `@ModelAttribute`, Spring binds into a model attribute via `WebDataBinder`. With JSON + `@RequestBody`, `HttpMessageConverter` (usually Jackson) **deserializes** JSON into an object first; afterward Spring can still use a binder/validator to check the object if the parameter has `@Valid` or `@Validated`.

~~~java
@PostMapping(path = "/api/registrations",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> registerJson(
        @Valid @RequestBody RegistrationForm request
) {
    return ResponseEntity.ok(Map.of("status", "accepted"));
}
~~~

This is a handler snippet extracted from a controller, reusing the DTO and appropriate imports. If the JSON is syntactically valid but violates DTO constraints, Spring MVC typically raises `MethodArgumentNotValidException` when no `BindingResult` parameter handles it locally. If the JSON is malformed or cannot be deserialized, the error happens at the **body-reading step**, typically `HttpMessageNotReadableException`; this is not yet a `@Min`/`@Email` validation error.

With Spring MVC 6.1+, if the handler has Jakarta constraints directly on method parameters (for example `@Min` on `@RequestParam`), **method validation** may apply and raise `HandlerMethodValidationException`. When building centralized API error handling, account for both exception types; do not assume every error is `MethodArgumentNotValidException`.

## 8. Proper Error Handling and Operational Notes

| Situation | Where it occurs / how to handle |
| --- | --- |
| `age=abc` when target is `Integer` | Conversion/binding error, usually with code `typeMismatch`; check `BindingResult`. |
| `age=17` with `@Min(18)` | Binding succeeds; validator adds a constraint error. |
| `@Valid @ModelAttribute ... , BindingResult errors` | Validation is triggered; controller receives errors because `BindingResult` sits immediately after. |
| `@Valid` without an immediately following `BindingResult` | Validation failure is typically translated into an MVC exception, which may default to a 400 response. |
| Spring `Validator` in `@InitBinder` without `@Valid`/`@Validated` | Validator is registered, **not yet requested to run** for that parameter. |
| `@RequestBody` containing broken JSON | Body read/deserialization error occurs before Bean Validation runs. |

To handle errors cleanly:

1. On MVC forms that need to return the view with messages, place `BindingResult` immediately after the object and use `hasFieldErrors(...)`, `getFieldErrors()`, or `getAllErrors()`.
2. On REST APIs, either handle errors locally with `BindingResult` (when the method signature supports it), or use `@RestControllerAdvice` to convert exceptions into a consistent error body.
3. Distinguish error codes (`typeMismatch`, `NotBlank`, custom codes) from display messages; messages can vary by locale and `MessageSource`.
4. Use dedicated DTOs for HTTP input and allow only intended fields to bind. Validation checks values, **it does not replace** field allowlisting or authorization checks.
5. Never handle errors by just calling `errors.clear()` or ignoring `hasErrors()`: post-binding data may not be valid to pass to the business layer.

## 9. Common Mistakes and How to Self-Check

**Wrong ordering:** Writing validation logic inside `@InitBinder` and expecting the form to already hold data. `@InitBinder` is mainly for preparing converters, allowed fields, and validators; actual validation runs after the bind step when triggered.

**Missing provider:** Using `@Valid` and constraint annotations without a Jakarta Bean Validation provider. On Spring Boot 3, check the `spring-boot-starter-validation` dependency and `jakarta.validation.*` imports; older examples using `javax.validation.*` belong to prior Spring/Boot generations.

**Misplacing `BindingResult`:** `BindingResult` must sit right after the parameter it describes, with no unrelated parameter placed between them. If multiple objects are bound/validated, each `BindingResult` must sit next to its own object.

**Forgetting the trigger:** Adding `@InitBinder` or a `Validator` alone is not enough; on the handler, use `@Valid`/`@Validated`. When using `DataBinder` manually, call `validate()` after `bind(...)`.

**Wrong validation group:** `@Validated(Create.class)` does not automatically check all constraints in the `Default` group. Design groups carefully and test both valid and invalid requests.

**Confusing binding errors with validation errors:** If an input value fails type conversion, check `FieldError#isBindingFailure()` and the error code before concluding the validator is misbehaving. A single `BindingResult` can hold both groups of errors at once.

You can test with `MockMvc`: submit a valid form and assert HTTP 200; send `age=17`, `username=admin` and assert 400; send `age=abc` to verify conversion errors; removing `@Valid` in an isolated experiment will show that Bean Validation rules stop running automatically on the parameter. With the `@InitBinder` example, verify that `username=admin` reaches `UsernameRuleValidator` after binding.

## 10. Takeaways

In Spring MVC, **binding builds the object from the request, and validation checks that object**. `@InitBinder` registers configuration and validators before binding; `@Valid`/`@Validated` is the usual signal to run validators after binding; `BindingResult` is where you read the accumulated errors. Mastering these three roles helps distinguish type conversion errors, rule violations, and request-reading failures, while avoiding skipped or duplicate validation.

Official documentation for further reference:

- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — Validator Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
