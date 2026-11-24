# Collecting Binding Errors and Continuing to Process Other Fields

In Spring Framework, **data binding** maps input data (typically strings from an HTTP form) onto properties of a Java object. A value that fails type conversion does not necessarily halt the entire **property binding** pass: Spring can record that field's error in `BindingResult` while continuing to bind the other valid fields.

This article focuses on the **error-handling flow when binding individual properties** with `DataBinder` / `WebDataBinder` and how a Spring MVC controller receives, inspects, and responds to those errors. The ability to continue applies to ordinary binding errors handled by the binder; it does not mean every exception during request reading, object creation, or application execution is automatically collected.

## 1. Scenario and Expected Outcome

Suppose a registration form submits three fields:

~~~text
name=Lan
age=abc
email=lan@example.com
~~~

The target object has `name: String`, `age: int`, and `email: String`. Spring binds `name`, fails to convert `"abc"` to an integer for `age`, and still binds `email`. After the binding pass:

- `name` contains `"Lan"` and `email` contains `"lan@example.com"`.
- `age` does not receive the invalid value; it keeps the value it held prior to the failed assignment (for example 18 if initialized to 18).
- `BindingResult` contains an error for the `age` field, including the error code, rejected value, and the fact that it is a binding failure.
- **The application must check for errors before using or saving the object**. Partial binding does not mean the data is business-valid.

The benefit is that the user can see *all collected errors* after a single form submission without having to re-enter valid fields. However, continuing to process other fields is not a decision to "ignore errors and save data."

## 2. Processing Flow from Input to BindingResult

~~~text
Input data (Map/property values or HTTP form)
                |
                v
Create or retrieve target object; initialize DataBinder
                |
                v
Iterate over bindable properties
                |
       +--------+---------+
       |                  |
 Convert/assign succeeds  Property conversion/assignment fails
       |                  |
 Update property        Record FieldError in BindingResult
       |                  |
       +--------+---------+
                |
                v
Continue processing remaining properties
                |
                v
(Per configuration) run validation on the object
                |
                v
Inspect BindingResult: binding errors + validation errors
                |
       +--------+---------+
       |                  |
   Has errors          No errors
       |                  |
Display/return errors   Proceed with business logic
Do not persist
invalid data
~~~

**Points to distinguish:**

1. **Binding** converts and assigns data to properties (for example `String` → `int`). Type conversion failures typically produce a `FieldError` with code `typeMismatch`.
2. **Validation** checks constraints after data is populated (for example age ≥ 18, name non-empty). Validators can add errors to the **same** `BindingResult`; `@Valid` / `@Validated` annotations do not replace binding.
3. **Request processing and object creation** are related stages that can raise their own exceptions. Malformed JSON with `@RequestBody` or target instantiation failures do not fall under property binding's "one field fails, subsequent fields still bind" guarantee.
4. "Continuing" applies to properties that can be processed independently. Do not assume assignment order is always fixed, or that setters with side effects will be rolled back when another field fails.

## 3. Key APIs and What Errors Mean

| Component | Responsibility |
|---|---|
| `DataBinder` | Accepts a target and a set of values to bind; coordinates conversion, property assignment, and error collection. |
| `WebDataBinder` | Web-oriented variant used when processing form objects in Spring MVC. |
| `MutablePropertyValues` / `PropertyValues` | Represents property name/value pairs when using the binder directly. |
| `BindingResult` | Result for a target object: holds field errors, global object errors, and binding metadata. |
| `FieldError` | Error details for one field, such as field name, error code, rejected value, and binding-failure flag. |
| `ObjectError` | Object-level error, not necessarily tied to a single field. |
| `Errors` | General error reading/recording interface; `BindingResult` extends it with binding information. |

Common operations:

- `result.hasErrors()`: is there at least one field error or object error?
- `result.getFieldErrors()`: retrieves the list of field errors; a single field can have multiple errors.
- `result.getFieldError("age")`: retrieves the first error for field `age`, or `null`.
- `result.getGlobalErrors()`: object-level errors.
- `result.getAllErrors()`: both field errors and object errors.
- `fieldError.getRejectedValue()`: the rejected input value (must be handled safely when displaying/logging).
- `fieldError.getCode()`: general error code, typically `typeMismatch` for type conversion errors.
- `fieldError.isBindingFailure()`: `true` when the error represents a binding failure; constraint errors created by a validator usually have this flag set to `false`.
- `result.getSuppressedFields()`: fields excluded from binding by allow/disallow rules; **not synonymous with FieldError by default**.

`FieldError.getCodes()` can return multiple codes from most specific to most general (such as codes qualified by object/field down to `typeMismatch`) so `MessageSource` can pick an appropriate message. Do not rely on the full code list or exception message text to drive business logic; prefer declared codes/fields and constraints.

## 4. Java Example: One Field Fails, Other Fields Still Bind

The example below uses **Java 17+** and Spring Framework's `org.springframework.validation.DataBinder` API. Each property is a JavaBean property with getter/setter; `age` is initialized to 18 so it is clear what happens when the new value is rejected.

File **BindingErrorsDemo.java**:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class BindingErrorsDemo {
    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "form");
        binder.setAllowedFields("name", "age", "email");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("age", "abc");
        input.add("email", "lan@example.com");

        // A type conversion error does not stop valid properties from being bound.
        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + form.getName());
        System.out.println("age=" + form.getAge());
        System.out.println("email=" + form.getEmail());
        System.out.println("hasErrors=" + result.hasErrors());

        FieldError ageError = result.getFieldError("age");
        if (ageError != null) {
            System.out.println("field=" + ageError.getField());
            System.out.println("code=" + ageError.getCode());
            System.out.println("rejected=" + ageError.getRejectedValue());
            System.out.println(
                "bindingFailure=" + ageError.isBindingFailure()
            );
        }
    }

    public static final class RegistrationForm {
        private String name;
        private int age = 18;
        private String email;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

**Running the example:** compatible Spring Framework JARs are required, at minimum the `spring-context` module and its required dependencies, inside the `lib/` directory. Since this example uses the Spring library, having only the JDK without the Spring classpath will not compile.

~~~bash
# Linux/macOS: lib/ contains compatible Spring JARs and dependencies
javac -cp "lib/*" BindingErrorsDemo.java
java -cp ".:lib/*" BindingErrorsDemo

# Windows: the classpath entry separator is a semicolon
javac -cp "lib/*" BindingErrorsDemo.java
java -cp ".;lib/*" BindingErrorsDemo
~~~

Standard output of the example with the default converters:

~~~text
name=Lan
age=18
email=lan@example.com
hasErrors=true
field=age
code=typeMismatch
rejected=abc
bindingFailure=true
~~~

**Step-by-step explanation by binding timing:**

1. `name="Lan"` is valid, so it is assigned.
2. `age="abc"` cannot be converted to `int`: Spring collects a `typeMismatch` error and keeps the previous `age=18` value; `"abc"` is stored as the rejected value for error reporting.
3. `email="lan@example.com"` is still processed and assigned to the object.
4. `result.hasErrors()` returns `true`, so the object **must not be treated as valid to save**, even though the other two fields hold valid values.

Detailed messages, specific code lists, and processing order can depend on converter configuration, binder settings, and Spring version; the example relies only on the core values/result types shown above. Do not base business conditions on internal error message strings.

## 5. Spring MVC: Receiving Errors in the Controller While Keeping Valid Field Data

In a Spring MVC application handling forms with `@ModelAttribute`, Spring creates/retrieves the form object, binds parameters, and places errors into `BindingResult`. Place the `BindingResult` parameter **immediately after** the model attribute parameter being checked, with no other parameter in between.

The snippet below is **integration code inside a Spring MVC project**, not a standalone Java file. Assume `RegistrationForm` is a JavaBean with properties `name`, `age`, and `email`, plus Bean Validation constraints as needed, and views `registration/form` and `registration/success` are provided by the application.

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    @InitBinder("form")
    void configureBinder(WebDataBinder binder) {
        // Only fields allowed to be edited through the form.
        binder.setAllowedFields("name", "age", "email");
    }

    @PostMapping
    String submit(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            // Spring MVC keeps the form and BindingResult for the view to display errors.
            return "registration/form";
        }

        // Only proceed to the success branch when there are no binding/validation errors.
        // Real applications also check business conditions before saving.
        return "registration/success";
    }
}
~~~

With form data `name=Lan&age=abc&email=lan%40example.com`, the typical flow is:

- `name` and `email` bind successfully onto the `form` object.
- `age` produces a type conversion error accessible via `errors.getFieldError("age")`.
- If Bean Validation is present, applicable constraints run after binding; they may add errors into `errors`.
- `errors.hasErrors()` is `true`; the controller returns the input view to display errors rather than entering the success branch.
- In the view/template, both entered values and error messages must be displayed safely. For a wrong-type field, the rejected value lives in the error info; do not assume the property on the target became that invalid string.

**The position of `BindingResult` is semantically required**: `BindingResult` corresponds to the `@ModelAttribute` immediately preceding it. If you omit this error-handling parameter, Spring MVC usually routes binding/validation errors through the exception mechanism (e.g., `MethodArgumentNotValidException`); when full method validation applies, the exception type may differ. The controller then will not automatically receive the result to re-render the form via the `errors.hasErrors()` branch above.

## 6. Aggregating Errors and Distinguishing Scenarios

| Input / situation | What typically happens | How to handle |
|---|---|---|
| `age=abc` when `age` is `int` | Conversion/binding error on `age`; other valid properties can still be assigned. | Iterate `getFieldErrors()`, report invalid type on `age`, retain form input. |
| `age=16` converts successfully but age ≥ 18 is required | Binding succeeds; validator can add a `FieldError`. | Do not save; use appropriate validation message. |
| Two fields have invalid types at once | Binder can collect multiple `FieldError`s in one pass. | Display errors per field; do not take only the first error for the whole form. |
| Missing required field | Can become a validation error like `@NotBlank` / `@NotNull`, or a binding error if `setRequiredFields` is configured. | Distinguish which constraint applies; do not assume "missing field" is a type conversion error. |
| Property name does not exist on JavaBean | Depending on `ignoreUnknownFields`, binder may skip it or throw an exception. | Check field names and configuration; do not assume it is recorded as a `FieldError`. |
| Field not in `allowedFields` | Prevented from assignment; may appear in `getSuppressedFields()`. | Handle per input policy; do not treat it as a successfully bound field. |
| Malformed JSON with `@RequestBody` | Read/deserialization error can occur before `@ModelAttribute` property binding. | Handle via HTTP message conversion exception mechanism; do not expect form `BindingResult` to hold per-field errors. |

**A single request can have both binding and validation errors.** For example, `age=abc` causes `typeMismatch`, while `name=""` can cause a `@NotBlank` error. When returning a response, merge messages by field/object for the user; when executing business logic, still distinguish error origins to avoid wrong decisions.

## 7. How to Iterate and Return Error Messages

In a controller, you can inspect the error list instead of only calling `hasErrors()`:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();
        boolean conversionFailed = fieldError.isBindingFailure();

        // Record field name/error code against an allowlist.
        // Map to a display message; do not return raw stack traces.
    }
    return "registration/form";
}
~~~

If building an API that returns JSON responses, return a consistent error structure, for example:

~~~json
{
  "message": "Invalid form data",
  "errors": [
    {
      "field": "age",
      "code": "typeMismatch",
      "message": "Age must be a valid integer"
    }
  ]
}
~~~

This is an **application-designed response format example**, not JSON returned automatically by Spring MVC by default. Messages can be mapped from error codes using `MessageSource` to support multiple languages. Never include exception messages, internal class names, stack traces, or sensitive data (passwords, tokens, personal info) in responses or logs.

Do not call `getFieldError()` once and conclude you have handled all errors: that method returns only the first error. For object-wide constraints such as "end date must be after start date," inspect `getGlobalErrors()` alongside `getFieldErrors()`.

## 8. Limitations and Design Considerations

**No automatic rollback for setters that already succeeded.** The object may be left in a partially populated state. Therefore, never execute business actions, write to the database, publish events, or call external APIs before concluding the form is valid. Bind into a dedicated DTO/form object, validate thoroughly, and only then map onto domain entities in the success branch.

**Only bind permitted fields.** `setAllowedFields(...)` or constructor/DTO design limits the input surface users can control. Avoid binding directly onto entities with sensitive properties like `role`, `isAdmin`, `id`; blocking a field does not guarantee it produces a standard `FieldError`.

**Do not equate binding errors with all exceptions.** During property binding, typical conversion errors are collected; however, constructor instantiation errors, custom converter/validator exceptions, setters with side effects, misconfigured binders, or system errors can still interrupt the flow. An exception not handled by the binder will not automatically turn into a `FieldError` to continue.

**An existing object may hold stale data.** If the `age` field fails to bind, its previous value may remain intact. Therefore, do not inspect the target to infer what the user just entered; use `FieldError.getRejectedValue()` for invalid fields, with appropriate display/logging safeguards.

**Constructor binding has different semantics from property binding.** Spring also supports instantiating objects via constructor; instantiation failures and null targets can affect whether an object exists to continue property binding. The example in section 4 intentionally uses a pre-existing JavaBean to illustrate per-property handling accurately.

**`@Valid` does not automatically permit ignoring errors.** It adds validation; the business branch must still respect `BindingResult` or the corresponding exception mechanism.

## 9. Behavior Tests to Verify

For the `DataBinder` example, a meaningful test should verify **all of the following together**:

1. Input `name="Lan"`, `age="abc"`, `email="lan@example.com"`.
2. After `bind`, `name` and `email` receive the new values; `age` stays 18.
3. `result.hasFieldErrors("age")` returns `true` and the rejected value is `"abc"`.
4. `ageError.isBindingFailure()` returns `true`.
5. No persistence step runs while `result.hasErrors()` is `true`.

With Spring MVC, use `MockMvc` to send `POST /registrations` with `age=abc`, then verify the controller returns the form view, the model contains field error `age`, valid fields remain populated in the form, and no save operation ran. Add cases for `age=20`, `age=16` with validation, two invalid fields at once, and a disallowed field name to verify the boundary between binding, validation, and field suppression.

## 10. Takeaways

- **Bind per field, collect errors, continue processing bindable fields:** that is the goal of a standard property binding flow.
- **`BindingResult` holds errors, the target holds successfully assigned values:** you cannot use the target as proof that the whole form is valid.
- **Check all errors before business logic:** place `BindingResult` immediately after `@ModelAttribute`, show errors per field, and proceed to the success path only when the form is genuinely valid.
- **Distinguish error classes:** type conversion, Bean Validation, field suppression, JSON deserialization, and system errors do not share the same handling mechanism.

### Official References

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Java Bean Validation and DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
