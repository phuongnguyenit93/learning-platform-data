# bindingFailure: Distinguishing Type-Conversion Errors from Validation Errors in Spring

When a Spring application receives data from a request, there are two distinct questions:

1. **Can binding convert and assign the data to the Java object?** For example, the string `"abc"` cannot be converted to `Integer` for property `age`.
2. **Does the bound value satisfy validation rules?** For example, `age=16` converts to an integer successfully yet violates a minimum-age requirement of 18.

Both can be stored as `FieldError` entries in `Errors`/`BindingResult`. The `FieldError.isBindingFailure()` property distinguishes **errors originating in the binding step** from **errors originating in the validation step** when handling Spring's standard error objects.

## 1. Two Phases: Type Conversion First, Constraint Checks Second

Given a model with field `Integer age`, requests send data as strings; the binder must convert to Java types before checking rules like minimum age.

~~~text
Incoming data ("age")
              |
              v
       DataBinder / WebDataBinder
              |
       Convert type and assign field
           /          \
          /            \
    "abc" -> error    "16" -> 16
        |                  |
   FieldError               v
   bindingFailure=true   Validator / Bean Validation
   code=typeMismatch        |
                        16 < 18
                            |
                        FieldError
                        bindingFailure=false
                        code=age.tooYoung / Min
          \                  /
           \                /
            BindingResult (Errors)
                      |
              hasErrors(), getFieldErrors()
                      |
                view / API response
~~~

Distinguish carefully: **binding errors are not synonymous with every form error**. Spring can also generate binding errors when a field configured as required is missing (`required`) or when a setter fails during assignment (`methodInvocation`), depending on binder configuration. `typeMismatch` is the most common and easily observed case.

| Criterion | Type-conversion / binding error | Validation error |
| --- | --- | --- |
| Detection phase | When the binder reads and assigns data to Java properties | After binding, when applying validation rules |
| Example | `age="abc"` for `Integer age` | `age="16"` became `Integer 16` but is under 18 |
| Standard Spring error | `FieldError`, typically with general code `typeMismatch` | `FieldError` or `ObjectError`, potentially with code `Min`, `NotBlank`, or custom code |
| `FieldError.isBindingFailure()` | `true` | `false` for normal validation errors |
| Value assigned successfully? | Failing field may remain unassigned | Target type was usually converted and assigned |
| Action needed | Fix input format/type, or conversion logic | Fix value to meet constraints/business rules |

Note that `isBindingFailure()` is a method on **`FieldError`**, not on every `ObjectError`. Object-level validation errors, such as start date after end date, may simply be `ObjectError` instances created by `errors.reject(...)`.

## 2. APIs to Read in `Errors` and `BindingResult`

`org.springframework.validation.Errors` lets you check whether errors exist and inspect details:

~~~java
if (errors.hasErrors()) {
    int total = errors.getErrorCount();
    for (FieldError fieldError : errors.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();
        boolean bindingFailed = fieldError.isBindingFailure();
        // Use this data to classify errors or build a response.
    }
}
~~~

This snippet illustrates code inside a scope that already has an `Errors errors` variable and imports `org.springframework.validation.FieldError`.

Useful methods:

| API | Meaning |
| --- | --- |
| `hasErrors()` / `getErrorCount()` | Whether any error exists or total error count |
| `hasFieldErrors("age")` / `getFieldErrors("age")` | Check or retrieve **all** errors for field `age` |
| `getFieldError("age")` | Get the first field error (may miss additional errors) |
| `getFieldErrors()` | Get errors attached to fields |
| `getGlobalErrors()` | Get object-level errors |
| `getAllErrors()` | Get both `FieldError` and `ObjectError` |
| `FieldError.getField()` | Failing field name |
| `FieldError.getRejectedValue()` | Rejected value, possibly the raw string when binding failed |
| `FieldError.getCode()` | Default/most general code, i.e., the **last** code in the codes list |
| `FieldError.getCodes()` | Message keys tried in order, from specific to general |
| `FieldError.isBindingFailure()` | Flag distinguishing binding failures from validation errors |

`BindingResult` extends `Errors` and is used by Spring MVC/`DataBinder` to carry extra binding context. A single `BindingResult` can hold **multiple kinds of errors at once**. Hence:

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError fieldError) {
        if (fieldError.isBindingFailure()) {
            // Error from the binding step (e.g., typeMismatch).
        } else {
            // Validation error attached to a field.
        }
    } else {
        // Object-level ObjectError: has no isBindingFailure().
    }
}
~~~

The snippet above requires importing `org.springframework.validation.ObjectError` and `FieldError`; `result` is an already-provided `BindingResult`. Never cast every element of `getAllErrors()` directly to `(FieldError) error`, because object-level errors are not `FieldError` instances.

**Important:** `isBindingFailure()` only describes **the origin of that error object**, not whether the request is valid for business processing. A form can have a type-conversion error on `age` and a validation error on `name` simultaneously. To decide whether the form can proceed, use `result.hasErrors()`.

## 3. How Does Spring Produce `typeMismatch` Errors?

Given a JavaBean:

~~~java
public class RegistrationForm {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

If the binder receives `age=abc`, default converters cannot turn letters into an integer. Typically, Spring records a `FieldError` with:

~~~text
objectName          = registrationForm
field               = age
rejectedValue       = "abc"
bindingFailure      = true
code (getCode())    = typeMismatch
~~~

Under a common `DefaultMessageCodesResolver` setup, `getCodes()` contains candidates such as:

~~~text
typeMismatch.registrationForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

The exact list depends on object name, field type, nested path, and resolver configuration. `getCode()` returns the **last** code in the list (e.g., `typeMismatch`); `getCodes()` holds candidates for contextual message translation. Do not treat `getCode()` as the first specific code.

With `age=16`, conversion to `Integer 16` succeeds. When `@Min(18)` or a custom validator rejects the value, the corresponding `FieldError` has `bindingFailure=false`. Calling `Errors.rejectValue("age", "age.tooYoung")` sets the final general code to `age.tooYoung`; Bean Validation `@Min` usually uses general code `Min`. Validation codes reflect **rules**, whereas binding codes reflect **difficulty converting/assigning data**.

Not every malformed input creates a `FieldError` here. For instance, malformed JSON payloads or Jackson deserialization failures may trigger `HttpMessageNotReadableException` in Spring MVC **before any target object is formed for validation**. Errors on `@RequestParam Integer age` also have their own conversion/exception path. When designing handlers, know each endpoint's parameter types.

## 4. Runnable Example: `DataBinder` Producing Both Kinds of `FieldError`

The following example uses **Java 17+ and Spring Framework 6.x**. `DataBinder` lets us reproduce the binding + validation flow without an HTTP server.

Complete code for `src/main/java/BindingFailureDemo.java` in a Maven project with `spring-context`:

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public final class BindingFailureDemo {

    public static class RegistrationForm {
        private Integer age;

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static class AgeValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            // If age already failed type conversion, do not add an age rule error.
            boolean conversionFailed = errors.getFieldErrors("age")
                    .stream()
                    .anyMatch(FieldError::isBindingFailure);
            if (conversionFailed) {
                return;
            }

            RegistrationForm form = (RegistrationForm) target;
            Integer age = form.getAge();
            if (age != null && age < 18) {
                errors.rejectValue(
                        "age",
                        "age.tooYoung",
                        "Age must be at least 18.");
            }
        }
    }

    private static void inspect(String rawAge) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("age");
        binder.addValidators(new AgeValidator());

        MutablePropertyValues properties = new MutablePropertyValues();
        properties.add("age", rawAge);

        binder.bind(properties);      // 1. Convert type and assign age.
        binder.validate();            // 2. Run AgeValidator.

        BindingResult result = binder.getBindingResult();

        System.out.println("input=" + rawAge);
        System.out.println("boundAge=" + form.getAge());
        System.out.println("errors=" + result.getErrorCount());

        for (FieldError error : result.getFieldErrors()) {
            System.out.println(error.getField()
                    + " | " + error.getCode()
                    + " | bindingFailure=" + error.isBindingFailure());
        }
    }

    public static void main(String[] args) {
        inspect("abc"); // Cannot convert to Integer.
        inspect("16");  // Converts to Integer but < 18.
        inspect("20");  // Both binding and validation succeed.
    }
}
~~~

In Maven, `spring-context` pulls in the relevant Spring modules, including `spring-beans` and `spring-core`. Example dependency:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>6.2.0</version>
</dependency>
~~~

Once you have a `pom.xml` configured for Java 17+ and the dependency above, place the file at the proper path and run:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=BindingFailureDemo
~~~

Output printed by the program:

~~~text
input=abc
boundAge=null
errors=1
age | typeMismatch | bindingFailure=true
input=16
boundAge=16
errors=1
age | age.tooYoung | bindingFailure=false
input=20
boundAge=20
errors=0
~~~

**Why does each case produce that output?**

1. **`"abc"`:** `binder.bind(...)` cannot assign to `Integer age`, so it adds a `FieldError` with `bindingFailure=true`. The field remains `null` on the new form. `AgeValidator` sees a conversion failure on that field and skips adding a spurious minimum-age error.
2. **`"16"`:** the binder converts to `Integer 16` with no binding error. `AgeValidator` sees `age < 18`, calls `errors.rejectValue(...)`, and creates a `FieldError` with `bindingFailure=false`.
3. **`"20"`:** the binder converts to `Integer 20` and the validator finds no violation; `getErrorCount()==0`.

Setting `binder.setAllowedFields("age")` ensures the example binds only the intended field; in web applications, restricting bindable properties is an important safeguard when using model binding. In this program, **`binder.bind(...)` creates the type-conversion error, while `binder.validate()` runs the custom validator**. If you merely construct a `BeanPropertyBindingResult` and call `validate()` without a failing bind pass, you will not naturally get a `typeMismatch`.

The example intentionally skips the minimum-age validation error when `age` already has a conversion error. Spring **does not guarantee that every custom validator automatically skips unbound fields**; `binder.validate()` still executes registered validators. Validator authors must account for `null`, prior binding errors, and the risk of emitting two confusing messages for the same input.

## 5. Classifying Errors Without Relying on Message Text

In the UI or API layer, classify using metadata instead of comparing error message text:

~~~java
for (FieldError error : result.getFieldErrors()) {
    String kind = error.isBindingFailure()
            ? "BINDING"
            : "VALIDATION";

    System.out.println(kind + ": "
            + error.getField() + " - " + error.getCode());
}
~~~

For example, an API can normalize the two groups into:

~~~json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "age",
      "kind": "BINDING",
      "code": "typeMismatch",
      "message": "Age must be an integer."
    }
  ]
}
~~~

This is an **application-designed response**, not an auto-serialized `BindingResult` format. When another request sends `age=16`, the API can keep the same structure while using `kind="VALIDATION"`, `code="age.tooYoung"`, and a message requiring age 18 or older.

If business requirements call for stable public error codes over time, build an explicit mapping layer from Spring codes to API codes. Spring's `getCode()` is helpful for handling, yet codes can shift if validators, resolvers, or rules change. Never let clients depend on localized Vietnamese/English strings from `getDefaultMessage()`.

### Do not rely solely on checking `typeMismatch` text

You can often recognize common type-conversion errors via `"typeMismatch"` or the `getCodes()` list. Still, to distinguish **the binding vs. validation origin of a `FieldError`**, prefer `isBindingFailure()`. Codes set by configuration or developers can change; a custom validator could even reuse a binding-like code name for a validation failure. **The error code expresses the violation type; the `bindingFailure` flag records Spring's error origin.**

### Rejected values mean different things

`FieldError.getRejectedValue()` can contain:

- `"abc"` (the unconvertible string) in the `age=abc` case.
- The Java value `Integer 16` when binding succeeded but validation failed.

Do not hastily treat `getRejectedValue()` as the value stored on the bean: when conversion fails, the bean property may remain `null` or keep its previous value. Also avoid logging or returning rejected values automatically if fields contain passwords, tokens, personal data, or sensitive content.

## 6. Using `BindingResult` in Spring MVC

For forms using `@ModelAttribute`, Spring MVC performs data binding, checks constraints when requested, and provides `BindingResult`. The snippet below assumes `RegistrationForm` and `AgeValidator` are beans/classes integrated into a Spring MVC application with appropriate imports:

~~~java
@Controller
class RegistrationController {

    private final AgeValidator ageValidator;

    RegistrationController(AgeValidator ageValidator) {
        this.ageValidator = ageValidator;
    }

    @InitBinder("registrationForm")
    void initBinder(WebDataBinder binder) {
        binder.setAllowedFields("age");
        binder.addValidators(ageValidator);
    }

    @PostMapping("/registrations")
    String register(
            @Validated @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result,
            Model model) {

        if (result.hasErrors()) {
            model.addAttribute("fieldErrors", result.getFieldErrors());
            return "registration-form";
        }

        return "redirect:/registrations/success";
    }
}
~~~

The annotations and types belong to Spring MVC/Spring Validation: `@Controller`, `@InitBinder`, `@PostMapping`, `@Validated`, `@ModelAttribute`, `WebDataBinder`, `BindingResult`, and `Model`. `AgeValidator` must be registered as a bean (or supplied via another mechanism) for injection. This is a **view/template integration snippet**, not a complete single-file runnable app.

Key points:

- `BindingResult result` must sit **immediately after** the bound/validated model parameter in the handler signature. Without a properly placed `BindingResult`, Spring MVC may route errors into exceptions through another path.
- `@Validated` (or `@Valid` where appropriate) tells Spring to run validation. `@InitBinder` only registers/configures the binder; registration alone is not enough to trigger validators automatically in every scenario.
- When a form request sends `age=abc`, `result.getFieldErrors("age")` usually contains a binding error with `isBindingFailure()==true`; sending `age=16` yields a corresponding validation error with `false`.
- `BindingResult` can hold both conversion errors and validation errors across different fields. Controllers should rely on `hasErrors()` to reject processing and present all relevant errors.
- When handling multiple fields, you do not have to abort all validation just because one field failed binding; let validators check fields that converted cleanly while avoiding duplicate errors on broken fields.

JSON request bodies follow a different path. Example:

~~~http
POST /registrations
Content-Type: application/json

{"age":"abc"}
~~~

If Jackson fails to convert `"abc"` to `Integer` while deserializing `@RequestBody`, Spring may throw `HttpMessageNotReadableException` before running model validators. **Do not assume** this exception creates a `FieldError.isBindingFailure()==true` inside a `BindingResult` like `@ModelAttribute`. With `@RequestBody @Valid`, constraint errors on an already-deserialized object typically go through `MethodArgumentNotValidException`. APIs need separate exception handlers for unreadable JSON, field constraints, and URL parameter conversion failures as needed.

## 7. Turning Errors into Locale-Friendly Messages

`FieldError` holds machine-readable codes and implements `MessageSourceResolvable`. It can be passed directly to `MessageSource` to pick a message based on `Locale` and the candidate code list:

~~~java
for (FieldError fieldError : result.getFieldErrors()) {
    String translated = messageSource.getMessage(fieldError, locale);
    // Attach translated text to the view or API response.
}
~~~

Assuming object name `registrationForm`:

~~~properties
# messages_vi.properties
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
typeMismatch=Giá trị nhập không đúng kiểu.
age.tooYoung.registrationForm.age=Bạn phải từ 18 tuổi trở lên.
age.tooYoung=Giá trị không đạt yêu cầu tuổi tối thiểu.
~~~

When `age=abc`, the message source can pick `typeMismatch.registrationForm.age`; when `age=16`, it can pick `age.tooYoung.registrationForm.age`. `getCodes()` reveals the exact candidate list. Maintain a default bundle (e.g., `messages.properties`) alongside translations for supported locales. Do not rely solely on `getDefaultMessage()` for binding errors: it can sometimes contain technical converter/exception text.

The request's `Locale` can come from a locale resolver or the `Accept-Language` header per Spring MVC configuration. **The message language never changes `isBindingFailure()`, error codes, or validation rules.** If the project needs dedicated API codes, standardize them alongside localized display text.

## 8. Simultaneous Errors and Precautions

A single request can cause multiple errors to coexist:

- `age=abc` fails type conversion → `FieldError(age, typeMismatch, true)`.
- `email=""` binds as a string but violates `@NotBlank` → `FieldError(email, NotBlank, false)`.
- `startDate > endDate` violates a combined rule → potentially an `ObjectError` created by `reject(...)`.

Therefore, do not label the entire request as "BINDING" merely because one conversion error appears. **Classify per error**, then use `result.hasErrors()` for the overall decision. A web app can choose HTTP 400 for any invalid input, while error packaging, HTTP status, and public codes are part of the application's API contract.

A custom validator must guard against secondary errors:

~~~java
@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;

    boolean conversionFailed = errors.getFieldErrors("age")
            .stream()
            .anyMatch(FieldError::isBindingFailure);

    if (!conversionFailed && form.getAge() != null
            && form.getAge() < 18) {
        errors.rejectValue("age", "age.tooYoung");
    }
}
~~~

If required checks include `@NotNull`, consider whether a missing-input error should appear alongside an unparseable-input error. Duplicate-suppression rules should be designed explicitly so you do not hide another helpful error from the user.

**Distinguish from suppressed fields:** `BindingResult.getSuppressedFields()` reflects fields blocked by the binder (e.g., outside the allowlist). That is separate security/binding-policy metadata, not a list of `FieldError` instances with `bindingFailure=true`. Never use `isBindingFailure()` to infer whether fields were suppressed or a request was rejected for mass assignment.

## 9. How to Test

For the program in Section 4, testing the three inputs `"abc"`, `"16"`, and `"20"` verifies both behavior layers together. Key assertions:

~~~java
// Type mismatch case after binder.bind("age" = "abc"):
FieldError mismatch = bindingResult.getFieldError("age");
assert mismatch != null;
assert mismatch.isBindingFailure();
assert "typeMismatch".equals(mismatch.getCode());

// Case where "16" binds, then is rejected by AgeValidator:
FieldError invalidAge = validationResult.getFieldError("age");
assert invalidAge != null;
assert !invalidAge.isBindingFailure();
assert "age.tooYoung".equals(invalidAge.getCode());
~~~

These are **illustrative test assertions**, assuming two `BindingResult` instances produced by the corresponding test cases. If using Java `assert`, remember to enable `-ea` at runtime. In real projects, JUnit `assertNotNull`/`assertTrue`/`assertFalse` are more convenient because they always evaluate.

Scenario matrix for endpoint testing:

| Input and entry path | Expectation |
| --- | --- |
| Form `age=abc` → `@ModelAttribute` | `BindingResult` has `typeMismatch`, `bindingFailure=true` |
| Form `age=16` → `@ModelAttribute` + validator | `bindingFailure=false`, rule code `age.tooYoung` |
| Form `age=20` | No errors on field `age` |
| Multi-field form, one conversion error and one constraint error | Keeps all errors; classifies each `FieldError` separately |
| Undeserializable JSON | Handler for parse/deserialization exceptions; do not assume the same `BindingResult` |
| Object-level error | Read `getGlobalErrors()`; do not cast to `FieldError` |
| Missing specific message key | Show suitable fallback message; never leak stack traces or internal messages |

## 10. Common Misconceptions

1. **Using `errors.hasErrors()` to conclude all errors came from validation.** This conflates conversion and rules; inspect `FieldError.isBindingFailure()` per field error.
2. **Checking `error.getCode().equals("typeMismatch")` is enough for all binding errors.** `typeMismatch` is common, yet `required`, `methodInvocation`, and custom codes also exist; check `isBindingFailure()` too.
3. **Assuming validation only runs when binding completely succeeds.** `DataBinder.validate()` is a separate call; registered validators can still run when `BindingResult` already holds errors. Custom validators must guard against `null` and failed bindings.
4. **Displaying `getRejectedValue()` directly to users.** It can hold raw unparsed input and sensitive values; turn it into friendly messages and controlled logs.
5. **Confusing `getCode()` with the first specific candidate.** `getCode()` is the last/most general code; use `getCodes()` or `MessageSource.getMessage(error, locale)` to leverage lookup order.
6. **Casting all of `getAllErrors()` to `FieldError`.** Object-level errors live there too; use `instanceof FieldError`.
7. **Applying form-binding logic to JSON bodies and query parameters.** They can raise different exceptions; design handlers per parameter type and error source.
8. **Recording duplicate errors on an unconvertible field.** If a field already has `bindingFailure=true`, a business validator should not infer from `null` and add "age too young". Choose an explicit error policy.

## 11. Guiding Principle

When explaining or returning input errors, keep processing boundaries clear: **the binder converts types and records binding errors, the validator checks rules and records validation errors, and `BindingResult` collects both**. Inspect each `FieldError` with `isBindingFailure()`; check the whole `BindingResult` with `hasErrors()`; and build display messages only from error codes and locale-appropriate information.

Official API sources: [`FieldError` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html), [`DataBinder` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html), [`DefaultMessageSourceResolvable` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultMessageSourceResolvable.html).
