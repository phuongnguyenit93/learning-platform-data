# BindException and Completing DataBinder with close

## 1. Lesson Objectives

When using Spring Framework to bind data onto a Java object, the outcome is not merely the successfully assigned values. Binding can encounter type-conversion failures, missing required fields, or errors detected during validation. Spring gathers these errors in a `BindingResult` object. The `DataBinder.close()` method provides a way to **convert the result stored in `BindingResult` into either a success outcome or a `BindException`**.

After this lesson, you will be able to:

- Accurately describe the roles of `DataBinder`, `Errors`, `BindingResult`, and `BindException`.
- Know when `bind()`, `validate()`, `getBindingResult()`, and `close()` are called.
- Explain why `close()` returns a `Map<?, ?>` when no errors exist, yet throws `BindException` when errors are present.
- Distinguish binding errors (type conversion, missing configured required fields) from validation errors registered by a `Validator`.
- Inspect `FieldError`, `ObjectError`, and the model map without relying on string exception messages.
- Use the appropriate APIs in standalone programs and in Spring MVC request-handling flows.

**Most importantly:** the name `close()` here **does not mean closing a connection, releasing resources, calling `AutoCloseable.close()`, or automatically running validation**. It inspects errors already accumulated in `BindingResult` and finalizes the binding flow at the result boundary as decided by the caller.

## 2. Four Components and Their Relationships

| Component | Package | Role |
| --- | --- | --- |
| `DataBinder` | `org.springframework.validation.DataBinder` | Accepts `PropertyValues`, assigns to the target object, converts types, and coordinates validation |
| `Errors` | `org.springframework.validation.Errors` | Contract for recording and querying object/field errors |
| `BindingResult` | `org.springframework.validation.BindingResult` | Extends `Errors` with binding context, e.g., `getTarget()`, `getModel()`, `getSuppressedFields()` |
| `BindException` | `org.springframework.validation.BindException` | Exception used when treating `BindingResult` errors as a failure condition to throw to the caller |

In Spring Framework 6.x, `BindException` is a **checked exception** (extending `Exception`) and implements `BindingResult`. Therefore you can catch it via `catch (BindException ex)` and directly inspect `ex.hasErrors()`, `ex.getFieldErrors()`, or `ex.getErrorCount()`. It wraps an existing `BindingResult`, rather than creating a separate exception per individual error.

Key distinctions:

- **`BindingResult` is structured error data.** It can coexist with the target object and be inspected whether errors exist or not.
- **`BindException` is a control-flow signal.** It is useful when the caller wants to turn collected errors into a failure condition to catch or handle at a boundary.
- **`close()` is the conversion decision.** It does not execute validation constraints; it simply checks `getBindingResult().hasErrors()` at the moment it is called.

The core of `DataBinder.close()`'s contract is:

~~~java
// Pseudocode equivalent to Spring 6.2 public behavior;
// illustrative only, not code to copy into DataBinder.
public Map<?, ?> close() throws BindException {
    if (getBindingResult().hasErrors()) {
        throw new BindException(getBindingResult());
    }
    return getBindingResult().getModel();
}
~~~

Thus `close()` has two clear branches and no implicit `validate()` step.

## 3. Standard Sequence: bind → validate → inspect → close

~~~text
Source data (PropertyValues)
         |
         v
DataBinder.bind(...) ----------> BindingResult receives binding errors
         |                       (required, typeMismatch, ...)
         v
DataBinder.validate() ---------> BindingResult adds validation errors
         |                       (rejectValue, reject, ...)
         v
DataBinder.getBindingResult()
         |
         +--> hasErrors() = false --> close() returns model Map
         |
         +--> hasErrors() = true  --> close() throws BindException
~~~

### 3.1. The bind phase

`binder.bind(propertyValues)` attempts to bind allowed properties onto the target. Errors may be recorded as `FieldError` entries, such as:

- `typeMismatch`: input string cannot convert to the target type (e.g., `"abc"` to `Integer`).
- `required`: missing value for a field registered via `setRequiredFields(...)`.
- `methodInvocation`: an error from a setter or related method call recorded by the binding error processor.

Specific error codes and message code lists can be customized by `BindingErrorProcessor` and `MessageCodesResolver`. A property-assignment failure does not necessarily make `bind()` throw `BindException` immediately; `DataBinder` typically accumulates recoverable errors inside `BindingResult`.

Severe Java errors outside this error-collection mechanism can still throw their own exceptions. Do not assume every exception is deferred until `close()`.

### 3.2. The validate phase

`binder.setValidator(myValidator)` registers a Spring `Validator`; `binder.validate()` asks the validator to run and append errors.

For example, an age of `17` parses to a valid `Integer` during binding, yet fails a minimum-age rule of `18` during validation. The validator can call:

~~~java
errors.rejectValue("age", "age.tooYoung");
~~~

This is a **logic fragment inside `Validator.validate(Object, Errors)`**. It registers a `FieldError` without throwing `BindException` itself.

`setValidator(...)` **does not** mean `bind()` or `close()` runs the validator automatically. Callers using `DataBinder` directly must explicitly call `validate()` at the right time. In Spring MVC, the framework can coordinate validation via `@Valid`/`@Validated` depending on parameters, so do not extrapolate the web lifecycle from a standalone binder example.

### 3.3. Reading errors and choosing how to handle them

`binder.getBindingResult()` lets you inspect errors before deciding to throw:

~~~java
BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    for (FieldError fieldError : result.getFieldErrors()) {
        System.out.println(fieldError.getField());
    }
}
~~~

This snippet requires importing `org.springframework.validation.BindingResult` and `FieldError`. If you prefer returning errors to the user rather than throwing an exception, you can handle `BindingResult` directly without calling `close()`.

## 4. Standalone Java 17 Example: Success, Validation Error, Type-Conversion Error

The following example uses Spring Framework **6.2.0**, Java 17, and Maven, **requiring no Spring Boot, servlet, controller, or Bean Validation provider**. To keep outcomes predictable, the program defines a simple Spring `Validator` and prints the total error count along with `isBindingFailure()`.

Create `pom.xml` in the project directory:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>bind-close-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/BindCloseDemo.java`:

~~~java
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class BindCloseDemo {

    public static class RegistrationForm {
        private String email;
        private Integer age;

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

    public static class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            if (form.getEmail() == null
                    || form.getEmail().isBlank()) {
                errors.rejectValue("email", "email.required");
            }
            if (form.getAge() != null && form.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    private static void runCase(
            String label, String email, String ageInput) {

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registration");
        binder.setAllowedFields("email", "age");
        binder.setValidator(new RegistrationValidator());

        binder.bind(new MutablePropertyValues(Map.of(
            "email", email,
            "age", ageInput
        )));

        BindingResult result = binder.getBindingResult();
        System.out.println("CASE " + label);
        System.out.println("afterBind=" + result.getErrorCount());

        binder.validate();
        System.out.println("afterValidate=" + result.getErrorCount());

        try {
            Map<?, ?> model = binder.close();

            boolean targetKeyPresent =
                model.get("registration") == form;
            boolean resultKeyPresent =
                model.get(
                    BindingResult.MODEL_KEY_PREFIX + "registration"
                ) == result;

            System.out.println("close=OK");
            System.out.println(
                "modelKeysPresent=" +
                (targetKeyPresent && resultKeyPresent)
            );
        } catch (BindException ex) {
            FieldError ageError = ex.getFieldError("age");

            System.out.println("close=BindException");
            System.out.println(
                "caughtErrorCount=" + ex.getErrorCount()
            );
            System.out.println(
                "ageBindingFailure=" +
                (ageError != null && ageError.isBindingFailure())
            );
        }
    }

    public static void main(String[] args) {
        runCase("valid", "lan@example.com", "20");
        runCase("invalid", " ", "17");
        runCase("badAgeType", "lan@example.com", "abc");
    }
}
~~~

Run from the directory containing `pom.xml` (with Java 17+ and Maven installed):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=BindCloseDemo
~~~

Stdout from the program itself (excluding external Maven/environment messages):

~~~text
CASE valid
afterBind=0
afterValidate=0
close=OK
modelKeysPresent=true
CASE invalid
afterBind=0
afterValidate=2
close=BindException
caughtErrorCount=2
ageBindingFailure=false
CASE badAgeType
afterBind=1
afterValidate=1
close=BindException
caughtErrorCount=1
ageBindingFailure=true
~~~

### Exact interpretation of each case

**Case `valid`:** `age="20"` converts to `Integer 20`, email is non-blank, and the validator adds no errors. `close()` returns the model map. Both keys are verified by direct lookup rather than printing map iteration order.

**Case `invalid`:** `age="17"` has a valid type, so `afterBind=0`. The validator catches the whitespace-only email and age under 18; `afterValidate=2`. `close()` sees `hasErrors() == true` and throws `BindException`. The age error is a **validation failure**, not a **binding failure**, so `ageBindingFailure=false`.

**Case `badAgeType`:** `age="abc"` fails to convert to `Integer`. `DataBinder` records a bind-phase `FieldError` with `isBindingFailure()==true`. The sample validator handles null safely and avoids adding an age error when conversion failed, so both before and after `validate()` there is still one error. `close()` throws `BindException` and `ageBindingFailure=true`.

This is **a complete program with `main`**. The `@ModelAttribute` and `@ExceptionHandler` examples in later sections are snippets for a Spring MVC application requiring a separate web project.

## 5. What Does BindException Contain?

`BindException` implements `BindingResult` and exposes the wrapped `BindingResult` via `getBindingResult()`. Inside a catch block you can use:

~~~java
catch (BindException ex) {
    BindingResult result = ex.getBindingResult();

    int total = result.getErrorCount();
    boolean hasAgeError = result.hasFieldErrors("age");

    for (FieldError error : result.getFieldErrors()) {
        String field = error.getField();
        boolean fromBinding = error.isBindingFailure();
        Object rejected = error.getRejectedValue();

        // Decide error code and message appropriate for the caller.
    }
}
~~~

This is a **catch snippet** used inside a method that calls `binder.close()`. The `total` and `hasAgeError` variables assist analysis; `rejected` may contain user-submitted data and you must avoid logging secrets.

Key APIs:

| API | Meaning |
| --- | --- |
| `hasErrors()` | At least one field or object error exists |
| `getErrorCount()` | Total number of errors |
| `getFieldErrors()` / `getFieldError("age")` | Errors attached to specific fields |
| `getGlobalErrors()` | Object-level errors (e.g., cross-field rules) |
| `FieldError.isBindingFailure()` | Distinguishes errors from binding vs. normal validation logic |
| `FieldError.getRejectedValue()` | Value rejected when recording the error; handle safely as it may be sensitive |
| `ObjectError.getCodes()` | Prioritized codes for message lookup via `MessageSource` |
| `getObjectName()` | Target object name, e.g., `registration` |
| `getBindingResult()` | Retrieves the structured holder wrapped by `BindException` |

A `FieldError` is a subtype of `ObjectError` that adds field metadata; errors from `Errors.reject(...)` are typically global errors, while `Errors.rejectValue(...)` records field errors. Error code names, `getCodes()` lists, and final messages are governed by resolvers/message catalogs; avoid asserting on the entire `exception.getMessage()` string since it includes extensive details and can vary across versions.

`BindException` is a **checked exception** in the Spring 6.x example, so Java code calling `close()` must `catch` it or declare `throws BindException` per Java rules. It differs from `ConstraintViolationException` used in certain Jakarta method-validation flows.

## 6. Why Does close() Return a Map and Which Keys Are Included?

On success, `close()` returns the equivalent of `getBindingResult().getModel()`. Given a binder initialized like this:

~~~java
DataBinder binder = new DataBinder(registrationForm, "registration");
~~~

the model contains two key entries:

| Key | Value |
| --- | --- |
| `"registration"` | Target object `registrationForm` |
| `BindingResult.MODEL_KEY_PREFIX + "registration"` | The corresponding `BindingResult` itself |

The constant `BindingResult.MODEL_KEY_PREFIX` equals `"org.springframework.validation.BindingResult."` in Spring Framework; thus the second key is `"org.springframework.validation.BindingResult.registration"`. Having both the target and error result is useful when a view needs to re-display form data alongside validation messages.

Example reading directly without depending on entry order:

~~~java
Map<?, ?> model = binder.close();

Object target = model.get("registration");
Object errors = model.get(
    BindingResult.MODEL_KEY_PREFIX + "registration"
);
~~~

When errors exist, `close()` **does not return a map** and instead throws an exception. If the caller still wants the model to re-render the form despite errors, it can call `binder.getBindingResult().getModel()` directly. `BindingResult.getModel()` creates a new result map on every call; mutating a received map and calling `getModel()` again does not persist changes into the next map.

Do not think of `close()` as a method that writes to a database, commits a transaction, destroys the binder, or makes the target atomic in an "accept only when valid" sense. Binding may already have assigned **part** of the properties onto the target before an error was recorded; throwing `BindException` does not roll back the target to its initial state.

## 7. Misconceptions About the Word "close"

### 7.1. close() does not release resources

`DataBinder` is not used as an `AutoCloseable`. Code like:

~~~java
// WRONG: DataBinder is not AutoCloseable.
try (DataBinder binder = new DataBinder(form, "form")) {
    // ...
}
~~~

will not satisfy the try-with-resources contract, because `DataBinder` does not implement `AutoCloseable`. There is no need to call `close()` in a `finally` block as with streams, connections, or files. If you do not want to convert errors into an exception, simply using `getBindingResult()` is completely valid.

### 7.2. close() does not validate automatically

~~~java
binder.setValidator(myValidator);
binder.bind(values);
binder.close();  // Sees only existing errors; myValidator has not run.
~~~

This is an **illustrative code fragment** with initialized variables. If data binds with valid types yet violates business rules, `close()` may return successfully because `validate()` was never called. The proper sequence when a validator is needed is:

~~~java
binder.setValidator(myValidator);
binder.bind(values);
binder.validate();
Map<?, ?> model = binder.close();
~~~

### 7.3. close() does not throw one exception per field

A single `BindException` carries **the entire** collected set of errors. That is an advantage of `BindingResult`: you can display errors on `email`, `age`, and the object all at once when they occur together.

### 7.4. Not every problem causes close() to fail

Fields disallowed from binding and suppressed are recorded in `getSuppressedFields()`, yet **they are not automatically added to the error list so `hasErrors()` returns true**. Example:

~~~java
binder.setAllowedFields("email", "age");
binder.bind(new MutablePropertyValues(Map.of("role", "ADMIN")));
String[] suppressed = binder.getBindingResult().getSuppressedFields();
~~~

This snippet assumes an initialized binder and matching object name. The `role` field is blocked because it is not in the allowlist; therefore, **never** treat the fact that `close()` did not throw as proof that the request contained no extra or disallowed fields. If your contract requires rejecting suppressed fields, the caller must check `suppressed.length > 0` explicitly and handle it accordingly.

Similarly, `setIgnoreUnknownFields(true)` is the default for property binding and ignores fields that do not match the object instead of raising an error. To protect data, use dedicated DTO/command objects and allowlists of permitted fields; avoid binding directly onto entities with sensitive properties.

## 8. How Required Fields, Type-Conversion Errors, and Validation Errors Differ

`DataBinder`'s default error processor can record a `required` error when you configure required fields for property binding:

~~~java
DataBinder binder = new DataBinder(form, "registration");
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of("age", "20")));
BindingResult errors = binder.getBindingResult();
~~~

This snippet assumes `form` has `email` and `age` properties; `email` is absent from the source data. `errors` will contain a `required` error for `email`. This is a **bind-time check**, not Jakarta `@NotBlank` or a custom Spring validator.

For comparison:

| Error type | Origin | Example | How to observe |
| --- | --- | --- | --- |
| Missing required field | `DataBinder` with `setRequiredFields(...)` | Missing `email` | `FieldError` with code `required` |
| Type mismatch | Converter/PropertyEditor during bind | `age="abc"` for `Integer` | `FieldError` with `isBindingFailure() == true` |
| Field validation | `Validator.validate(...)`/Bean Validation when invoked | `age=17` less than 18 | `FieldError` on field `age` |
| Cross-field validation | Validator checking relationships between fields | `startDate` after `endDate` | `ObjectError` via `reject(...)` or intentional field error |
| Suppressed field | Binding protection allowlist | `role` not allowed to bind | `getSuppressedFields()`; not automatically an error |

In addition to `required` and `typeMismatch`, Spring can produce `methodInvocation` in setter/method contexts. Avoid building message strings tightly coupled to one specific code when the application configures custom `BindingErrorProcessor`/`MessageCodesResolver` strategies.

**Practical takeaway:** When converting age fails, do not both access age as if it were valid and add a validation error under that false assumption. Validators must tolerate null/unset values, or design an explicit invocation order/guard. `close()` does not solve this for you.

## 9. When Is BindException Used in Spring MVC Web Apps?

Two very different situations can occur:

**A. You create `DataBinder` yourself and call `close()`:** this is an explicit programmatic step, just like the standalone example above. You can certainly do this in a service or adapter if desired, then catch `BindException` at the corresponding boundary. However, creating a binder manually inside a controller that already uses MVC's built-in mechanism is usually unnecessary.

**B. Spring MVC automatically binds and validates handler parameters:** the framework coordinates reading requests, converting types, and validating. With `@ModelAttribute`, errors can be passed to an adjacent `BindingResult`/`Errors` parameter immediately following the object. With `@RequestBody` JSON, bodies are normally deserialized by an `HttpMessageConverter` (such as Jackson), so not everything goes through `DataBinder.bind(...)` like form fields.

Example of a **Spring MVC controller method snippet**:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
            errors.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getCode())
                .toList()
        );
    }
    return ResponseEntity.ok("accepted");
}
~~~

This method requires importing `jakarta.validation.Valid`, `org.springframework.validation.BindingResult`, MVC annotations, and `ResponseEntity`; `RegistrationForm` must carry appropriate constraints and the application must have a Bean Validation provider for `@Valid` to take effect. This code is a controller snippet, **not a program with `main`**.

In Spring MVC 6.2, when using `@Valid`/`@Validated` on an object handler parameter without a local `Errors`/`BindingResult`, argument-level validation failures are typically reported via `MethodArgumentNotValidException`. This class extends `BindException` in Spring 6.2 while also implementing the HTTP-specific `ErrorResponse` contract. When constraints sit directly on parameters/methods so method validation applies, Spring MVC 6.1+ can throw `HandlerMethodValidationException`. Body-parsing failures can raise `HttpMessageNotReadableException`.

Do not describe **every** web error as the result of a developer-called `DataBinder.close()`, or assume catching `BindException` handles all cases. `@ControllerAdvice` or `ResponseEntityExceptionHandler` can map each failure type into a consistent response while preserving fields, messages, status codes, and needed metadata.

In Spring WebFlux, binding validation failures can flow through `WebExchangeBindException` and a reactive lifecycle that differs from MVC. When calling `DataBinder` standalone, no default HTTP status is produced by `BindException`: the caller decides how to respond.

## 10. Error Handling: Exception or Returning a Result?

Not every caller should receive a checked exception. Choose according to the application contract:

| Scenario | Reasonable choice |
| --- | --- |
| A CSV batch needs to record errors per row and keep going | Read `getBindingResult()`, store errors per row; avoid exceptions as routine flow |
| An API/form needs to return multiple field errors together | Use the framework/controller `BindingResult`, map errors to a clear response |
| A binding step must fail immediately on invalid input | Call `validate()` when needed, then `close()`, and handle `BindException` at the boundary |
| A service already receives a properly typed DTO, no property binding needed | Use `Validator`/Jakarta Validation directly instead of creating `DataBinder` just to get `BindException` |
| Need to build a model for a form/view | Use `BindingResult.getModel()` or the `close()` return value when error-free |
| Input includes disallowed fields | Inspect `getSuppressedFields()` and apply a dedicated rejection rule; `close()` does not enforce this automatically |

**Security and logging:** errors can hold field names, rejected values, object names, and input strings. Avoid writing sensitive data (passwords, tokens, personal info) into logs or HTTP bodies. Use stable error codes, localized messages via `MessageSource` where appropriate, and clear field/path structures; never return full `BindException.toString()` output to clients.

## 11. Testing the Behavioral Boundaries of close()

A meaningful test suite should verify:

1. **No errors:** call bind, validate, `close()`; assert the model contains the target and `BindingResult.MODEL_KEY_PREFIX + objectName`.
2. **Validation failure:** input converts cleanly yet a custom `Validator` calls `rejectValue(...)`; assert `close()` throws `BindException` with the right error count and `isBindingFailure()==false` for validator errors.
3. **Binding failure:** wrong input type for a property; assert a `FieldError` already exists before `validate()` with `isBindingFailure()==true`.
4. **validate not called:** register a validator then only bind + close; assert `close()` only checks existing errors and does not run `Validator` automatically.
5. **Missing required:** use `setRequiredFields(...)` then omit the field; assert the `required` error is recorded from the bind phase.
6. **Global error:** validator calls `reject("invalidCombination")`; assert `getGlobalErrors()` and `hasErrors()` reflect the object-level error.
7. **Suppressed field:** allowlist blocks a property; inspect `getSuppressedFields()` because it does not necessarily make `close()` throw.
8. **Partially bound target:** trigger `typeMismatch` on one field and valid input on another; assert the exception does not roll back successfully assigned properties.

These checks directly guard the `DataBinder.close()` contract. Tests that assert on the entire `BindException.getMessage()` string or rely on `Map.keySet()` order become brittle when framework internals or message resolvers change.

## 12. Self-Check Questions

**Question 1.** Does `binder.setValidator(v)` followed by `binder.close()` guarantee `v.validate()` ran?  
**Answer:** No. With explicit `DataBinder` usage, you must call `binder.validate()` or another mechanism that actually triggers the validator.

**Question 2.** Where does the error originate when `age="abc"` is supplied for `Integer age`?  
**Answer:** During binding/type conversion, usually recorded as a `typeMismatch` `FieldError`. `close()` can then throw `BindException` because the result already holds an error.

**Question 3.** Why can `close()` fail even though the target object already holds some valid properties?  
**Answer:** Binding is not a transaction. Spring can assign valid properties and record errors on others; `close()` only evaluates the current error set without rolling back.

**Question 4.** When there are two field errors, how many `BindException` instances does `close()` throw?  
**Answer:** One exception wrapping the `BindingResult` that collects the errors, not two separate exceptions.

**Question 5.** When you need to re-render a bound form even with errors, must you call `close()`?  
**Answer:** No. Use `getBindingResult()` and `getModel()` if you want to retain data for error display without turning it into an exception.

**Question 6.** Can you replace `try/catch BindException` with `try-with-resources(DataBinder)`?  
**Answer:** No. `DataBinder` is not `AutoCloseable`.

**Question 7.** Does `close()` automatically flag suppressed fields as validation errors?  
**Answer:** Not by default. Inspect `BindingResult.getSuppressedFields()` and apply your disallowed-field policy.

## 13. Summary of the Processing Flow for Correct Usage

~~~text
Create DataBinder(target, objectName)
    |
    +-- configure allowedFields / requiredFields / conversion / Validator
    |
    +-- bind(PropertyValues)
    |       |
    |       +-- FieldError from binding failures (if any)
    |
    +-- validate()   <-- only when needed, not implicitly called by close()
    |       |
    |       +-- FieldError / ObjectError from validator (if any)
    |
    +-- getBindingResult()
    |       |
    |       +-- has errors?
    |              |
    |              +-- read and return errors (no need for close)
    |              |
    |              +-- close() -> throws BindException if throwing is desired
    |
    +-- no errors -> close() returns Map containing target + BindingResult
~~~

`DataBinder.close()` is **the point that turns the "has errors or not" decision into either a thrown exception or a returned model**. Use it only when that style of handling genuinely fits the caller. For MVC forms and HTTP APIs, prefer the framework's built-in `BindingResult`/exception-handling mechanisms; for services, CLIs, and batch jobs, decide between returning errors or throwing exceptions based on that layer's contract.

## Official Documentation

- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/BindException.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring MVC 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
