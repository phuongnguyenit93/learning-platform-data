# Errors and Collecting Validation Results

When submitting a form in Spring Framework, a value may **fail to convert to a Java type**, or it may convert and bind successfully yet **violate a validation rule**. Spring provides the `org.springframework.validation.Errors` interface to collect these errors per **validated object**, rather than forcing the application to know only "success/failure".

This article explains how to record, read, and handle errors with `Errors`; its relationship with `Validator`, `DataBinder`, and `BindingResult`; the difference between field-level errors and object-level (global) errors; how error codes become user-facing messages; and how to apply them in Spring MVC. The main examples use Java 17+ with Spring Framework 6.2.x.

## 1. Where Does Errors Fit in the Processing Flow?

Consider a registration form submitting these values:

```text
username = "   "
age      = "16"
password = "abc"
confirm  = "xyz"
```

The target object (`target`) has `username: String`, `age: int`, `password: String`, and `confirm: String`. Spring can bind all four values successfully, but subsequent validation detects a blank username, an age below the required minimum, and a mismatched confirmation password.

```text
Input data (strings)
          |
          v
   DataBinder / WebDataBinder -----> ConversionService / Formatter
          |                                   |
          +-------- type conversion, bind <---+
          |
          +---- binding error: e.g., age="abc" -----------+
          |                                               |
          v                                               v
     Java Object                                     BindingResult
          |                                          (extends Errors)
          v                                               ^
  Validator / Bean Validation                             |
          |                                               |
          +---- rejectValue(...) / reject(...) -----------+
          |
          v
  hasErrors(), getFieldErrors(), getGlobalErrors()
          |
          v
  Display per-field errors / form-wide error / API response
```

**Note:** `DataBinder.bind(...)` primarily performs binding and can collect binding errors; when using the `DataBinder` API directly, you need to call `binder.validate()` to run configured validators. In Spring MVC, the framework can trigger validation when the appropriate parameter carries `@Valid` or `@Validated` and the corresponding provider/validator is integrated. Do not assume every bind automatically validates all constraints.

In the example above, if `age="abc"`, converting to `int` fails; that is a **binding error**. If `age="16"`, converting to 16 succeeds, but the minimum age 18 rule fails; that is a **validation error**. Both can be queried through the same `Errors`/`BindingResult` surface.

## 2. What Is Errors and How Does It Differ from BindingResult?

`Errors` is the **contract for recording and querying errors** for a named target (`objectName`). It is not an exception, not a single message string, and it does not perform validation itself. A `Validator` receives `Errors` to **register** errors; classes in the handling layer receive `Errors` to **read** errors.

`BindingResult` **extends `Errors`**, adding data tied to the binding process such as the target, raw field values, and integration with the Spring MVC model. Common implementations include `BeanPropertyBindingResult` and `DirectFieldBindingResult`; when using `DataBinder`, access the result via `binder.getBindingResult()`.

| Component | Role | Example API |
| --- | --- | --- |
| `Validator` | Validation rules, recording errors | `validate(Object, Errors)` |
| `Errors` | Recording/querying per-field and object-wide errors | `rejectValue`, `reject`, `getAllErrors` |
| `BindingResult` | `Errors` with additional data-binding context | `getTarget`, `getFieldErrors`, `getModel` |
| `FieldError` | Represents a property-level error | `getField`, `getRejectedValue`, `isBindingFailure` |
| `ObjectError` | Represents a general error; also the superclass of `FieldError` | `getObjectName`, `getCodes`, `getDefaultMessage` |
| `DataBinder` | Binds input, coordinates type conversion and validators | `bind`, `validate`, `getBindingResult` |
| `MessageSource` | Resolves error codes to localized messages | `getMessage(MessageSourceResolvable, Locale)` |

**Inheritance hierarchy to remember:**

```text
Errors (interface)
  └── BindingResult (interface)

ObjectError
  └── FieldError
```

Because `FieldError extends ObjectError`, `getAllErrors()` returns a list of `ObjectError` that may contain elements that are actually `FieldError` instances. To display messages next to each input, use `getFieldErrors()`/`getFieldErrors("field")`; to display form-wide warnings, use `getGlobalErrors()`.

Each `Errors` instance is tied to the target object name, for example `"signup"`. That name participates in generating message codes and putting the result into the model. Generally, you should not share an `Errors` instance across multiple requests or threads; the API is designed for the validation lifecycle of one object in a single execution flow.

## 3. Two Kinds of Errors: Field and Global

### 3.1. Field error

A **field error** is attached to a specific property, for example:

- `username` is left blank;
- `age` is less than 18;
- `age="abc"` cannot be converted to a number;
- `address.city` is invalid;
- `items[0].quantity` has an out-of-range value.

In a `Validator`, record a field error using `errors.rejectValue(...)`:

```java
errors.rejectValue("age", "age.min", new Object[] {18},
                   "Minimum age is 18");
```

The parameters are, in order: **field name**, **error code** for message lookup, **arguments for the message**, and fallback **default message**. `"age.min"` is an application-defined code; it is not yet the final translated text.

A `FieldError` typically contains:

| Property | Meaning |
| --- | --- |
| `getObjectName()` | Object/form being validated |
| `getField()` | Property path that caused the error |
| `getRejectedValue()` | Rejected value; may be the raw string when binding fails |
| `getCode()` | Most general error code, e.g. `age.min` or `typeMismatch` |
| `getCodes()` | Candidate codes from specific to general for message lookup |
| `getArguments()` | Arguments used for the message template |
| `getDefaultMessage()` | Fallback message (may be null) |
| `isBindingFailure()` | `true` if it is a binding error, usually `false` for validator-created errors |

Do not assume `getRejectedValue()` is always the value stored in the Java object. When binding `age="abc"` to `int` fails, the target may still retain its old/default value; `FieldError` preserves the rejected input for messaging or re-rendering the form.

### 3.2. Global error

A **global error** relates to the object or a rule spanning multiple fields, not necessarily attributable to a single property. For example:

- `password` and `confirm` do not match;
- `startDate` must not be after `endDate`;
- the sum of item percentages does not equal 100.

Register it with `errors.reject(...)`:

```java
errors.reject("password.mismatch",
              "Confirmation password does not match");
```

The result is an `ObjectError` in `getGlobalErrors()`. If the UI wants to display the error next to a single field (e.g., next to `confirm`), you can choose `rejectValue("confirm", ...)`. Choose field or global based on **user experience and the semantics of the rule**, not habit.

**Do not confuse "global error" with a global application error.** In `Errors`, global simply means an error at the **bound object** level, not a production system failure, HTTP 500, or application-wide exception.

## 4. Most Frequently Used Errors Methods

| Group | Method | How to understand it |
| --- | --- | --- |
| Identify target | `getObjectName()` | Target name of the error set |
| Record object-wide error | `reject(code, ...)` | Adds an `ObjectError` |
| Record property error | `rejectValue(field, code, ...)` | Adds a `FieldError` |
| Are there any errors? | `hasErrors()` | `true` if there is at least one error |
| Total count | `getErrorCount()` | Total field + global errors |
| Full list | `getAllErrors()` | Returns both `ObjectError` and `FieldError` |
| Field errors | `hasFieldErrors()`, `getFieldErrorCount()` | Queries errors belonging to fields |
| Errors for one field | `hasFieldErrors("age")`, `getFieldError("age")`, `getFieldErrors("age")` | `getFieldError` only gets the **first** error |
| Global errors | `hasGlobalErrors()`, `getGlobalErrorCount()`, `getGlobalErrors()` | Queries object-wide errors |
| Field value for rendering | `getFieldValue("age")` | May return the rejected value or the property value |
| Field type | `getFieldType("age")` | Field type if determinable |
| Nested path | `pushNestedPath("address")`, `popNestedPath()` | Creates context for validating a subtree |

Some easily overlooked details:

- `getFieldError("age")` only returns a single error or `null`; if a field violates multiple constraints, use `getFieldErrors("age")` so none are missed.
- `getAllErrors()` is a **collection**; do not cast every element to `FieldError`.
- `hasErrors()` indicates there are errors in the validated object; it does not mean data was rolled back or a transaction ended.
- The API does not automatically send an HTTP response, build a JSON error envelope, or auto-correct values.
- `Errors` can hold multiple errors for a single field. Do not treat `getErrorCount()` as "the number of invalid fields".

## 5. How Does Validator Record Errors?

With `org.springframework.validation.Validator`, the two main methods are:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

`supports` answers which target types the validator supports; `validate` checks and records errors. This is a **simplified shape** of the interface for explanation, not a standalone compilable file.

Example form logic:

```java
@Override
public void validate(Object target, Errors errors) {
    Signup form = (Signup) target;

    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "username", "username.required",
            "Username is required");

    if (!errors.hasFieldErrors("age") && form.getAge() < 18) {
        errors.rejectValue("age", "age.min", new Object[]{18},
                "Minimum age is 18");
    }

    if (form.getPassword() != null
            && !form.getPassword().equals(form.getConfirm())) {
        errors.reject("password.mismatch",
                "Confirmation password does not match");
    }
}
```

This is a **snippet inside a class implementing `Validator`**; the `Signup` class and imports are shown in the complete example below.

Why check `!errors.hasFieldErrors("age")`? If the input `age="abc"` cannot be converted to `int`, the primitive target `age` may remain 0. If you only check `age < 18`, the validator would add a low-age error even though the user actually entered **invalid syntax**. Skipping the age check when a binding error already exists for the field helps report the true root cause. This is a useful validation policy; other rules may require different policies.

`ValidationUtils.rejectIfEmptyOrWhitespace(...)` handles null, empty strings, or whitespace-only strings. It **records an error in `Errors`**; it does not mutate the field, throw an exception, or display a message by itself.

## 6. Complete Java 17+ Example: Collecting Both Binding and Validation Errors

This example uses **Spring Framework 6.2.12** via Maven, running as a console program. It demonstrates two cases:

1. Data binds successfully, then the validator creates 2 field errors and 1 object-wide error.
2. `age="abc"` cannot be bound, creating a `typeMismatch` error; the validator avoids adding a meaningless age error.

Structure:

```text
errors-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ErrorsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>errors-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/ErrorsDemo.java`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ErrorsDemo {
    public static class Signup {
        private String username;
        private int age;
        private String password;
        private String confirm;

        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }

        public String getConfirm() { return confirm; }
        public void setConfirm(String confirm) { this.confirm = confirm; }
    }

    public static class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return Signup.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "username", "username.required",
                    "Username is required");

            // Do not add an age error if binding the age field already failed.
            if (!errors.hasFieldErrors("age") && form.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", new Object[]{18},
                        "Minimum age is 18");
            }

            // A cross-field rule is recorded as a global error.
            if (form.getPassword() != null
                    && !form.getPassword().equals(form.getConfirm())) {
                errors.reject("password.mismatch",
                        "Confirmation password does not match");
            }
        }
    }

    private static BindingResult check(
            String username, String age, String password, String confirm) {
        Signup target = new Signup();
        DataBinder binder = new DataBinder(target, "signup");
        binder.setValidator(new SignupValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("username", username);
        input.add("age", age);
        input.add("password", password);
        input.add("confirm", confirm);

        binder.bind(input);    // Collect binding/conversion errors.
        binder.validate();     // Collect Validator errors.
        return binder.getBindingResult();
    }

    private static void printResult(String label, BindingResult result) {
        System.out.println("case=" + label);
        System.out.println("total=" + result.getErrorCount());
        System.out.println("field=" + result.getFieldErrorCount());
        System.out.println("global=" + result.getGlobalErrorCount());

        for (FieldError error : result.getFieldErrors()) {
            System.out.println("FIELD " + error.getField() + " "
                    + error.getCode() + " binding=" + error.isBindingFailure());
        }

        for (ObjectError error : result.getGlobalErrors()) {
            System.out.println("GLOBAL " + error.getCode());
        }
    }

    public static void main(String[] args) {
        BindingResult validation = check("   ", "16", "abc", "xyz");
        printResult("validation", validation);

        BindingResult conversion = check("An", "abc", "same", "same");
        printResult("conversion", conversion);
    }
}
```

Run from the `errors-demo` directory using JDK 17+ and Maven (the first run downloads dependencies):

```bash
mvn -q compile exec:java -Dexec.mainClass=ErrorsDemo
```

The `System.out.println` statements in the program produce:

```text
case=validation
total=3
field=2
global=1
FIELD username username.required binding=false
FIELD age age.min binding=false
GLOBAL password.mismatch
case=conversion
total=1
field=1
global=0
FIELD age typeMismatch binding=true
```

**Reading the output:**

- In the `validation` case, values bind, but `username` contains only whitespace; `age=16` is under 18; `password` differs from `confirm`. There are 3 errors: 2 field and 1 global.
- `FieldError.isBindingFailure()` is `false` for errors registered by the validator, because the data bound successfully and violated a rule.
- In the `conversion` case, `age="abc"` cannot become an `int`. `DataBinder` by default turns the type-conversion failure into a `FieldError` (general code `typeMismatch`) with `isBindingFailure()=true`.
- The validator checks `hasFieldErrors("age")` so it does not add a spurious `age.min` error on the default value 0.
- `result.getErrorCount()` equals `getFieldErrors().size() + getGlobalErrors().size()`.

To inspect the rejected input in the type-conversion failure case (use only in safe debugging), you can read:

```java
FieldError error = conversion.getFieldError("age");
if (error != null) {
    System.out.println(error.getRejectedValue()); // abc
}
```

This snippet continues from the `conversion` variable in `main`; it was not added to stdout above. **Do not log rejected values that contain passwords, tokens, personal data, or unsanitized content**, because `FieldError` can hold the exact sensitive value the user entered.

## 7. Collecting and Querying Errors by Purpose

### 7.1. Only needing to know whether to proceed

```java
if (errors.hasErrors()) {
    // Return the form, or build a failed validation result.
    return;
}
```

This is a logic snippet placed inside a method with an `Errors errors` variable and an appropriate return type. Checking early prevents business logic from running with invalid input.

### 7.2. Displaying errors for each field

```java
for (FieldError fieldError : errors.getFieldErrors()) {
    String field = fieldError.getField();
    String code = fieldError.getCode();
    String fallback = fieldError.getDefaultMessage();
    // Use field/code to attach the message to the corresponding control.
}
```

If the UI only displays one error per field, `getFieldError("age")` returns the first error. If you need all of them, use `getFieldErrors("age")` and sort/group according to UI needs. Avoid displaying raw `FieldError.toString()` to users because it contains internal metadata and may include the rejected value.

### 7.3. Displaying errors for the entire form

```java
for (ObjectError error : errors.getGlobalErrors()) {
    // A message for a cross-field or object-wide rule.
}
```

In complex forms, there is typically a "General Errors" area and message areas directly below each input box. `getAllErrors()` is suitable for a summary section, though you must distinguish `FieldError` instances if you want to display them next to the right controls.

### 7.4. Counting accurately

```java
int total = errors.getErrorCount();
int fieldCount = errors.getFieldErrorCount();
int globalCount = errors.getGlobalErrorCount();

assert total == fieldCount + globalCount;
```

This invariant holds for the error structure tracked by Spring; Java `assert` only executes when `-ea` is enabled and does not replace framework-based testing. For example, a `password` field violating two rules can produce two `FieldError` instances, so `fieldCount` is the number of **errors**, not the number of distinct fields.

## 8. Error Codes, defaultMessage, and i18n

`errors.rejectValue("age", "age.min", ...)` stores an **error code**; this code can be expanded into multiple more-specific candidates by `MessageCodesResolver`. For object `signup` and field `age` of type `int`, common candidates look like:

```text
age.min.signup.age
age.min.age
age.min.int
age.min
```

The exact code list/details depend on the resolver implementation/configuration; `getCodes()` is the source of truth to inspect. Spring uses `MessageSource` with those codes and arguments to resolve a localized message; `getDefaultMessage()` is the fallback when no message is configured for those keys.

Example Vietnamese message file:

```properties
username.required.signup.username=Vui lòng nhập tên đăng nhập.
age.min.signup.age=Tuổi phải từ {0} trở lên.
password.mismatch.signup=Mật khẩu và xác nhận không khớp.
typeMismatch.signup.age=Tuổi phải là một số nguyên.
```

In `MessageSource`, `{0}` is replaced by the first argument if the message configuration/source supports it. For example, `age.min` passes `new Object[]{18}` to produce "Tuổi phải từ 18 trở lên.". Typically, applications declare `messages*.properties` bundles and configure a message source matching `Locale`. Choosing to return `error.getDefaultMessage()` directly in an API is just a simple fallback and **does not guarantee localization** or ensure messages are safe for a public API.

Steps for good message design:

1. Use stable error codes, such as `age.min` or `registration.age.min`, decoupled from wording.
2. Use field/object-specific keys when a rule needs different messages depending on context.
3. Provide a clear `defaultMessage` for cases where a key is missing.
4. Pass arguments for variable values (`18`, size limits, etc.) instead of manual string concatenation.
5. Never include stack traces or exception class names in end-user messages.

**Messages and error codes have different lifecycles:** the same `typeMismatch` code can produce "Vui lòng nhập tuổi hợp lệ" on a Vietnamese UI and "Enter a valid age" on an English UI.

## 9. Errors in a Spring MVC Controller

For forms using `@ModelAttribute`, Spring MVC supports a `BindingResult` parameter **immediately after** the form parameter so the controller receives errors:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

class RegisterForm {
    @NotBlank
    private String username;

    @Min(18)
    private int age;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}

@Controller
class RegisterController {
    @PostMapping("/register")
    String register(
            @Valid @ModelAttribute("form") RegisterForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "register-form";
        }

        // Only process a form valid according to the executed constraints.
        return "register-success";
    }
}
```

This is a **Spring MVC integration snippet**, requiring a project configured with a view resolver and a Bean Validation provider (in Spring Boot, typically adding `spring-boot-starter-validation`). View names are illustrative only; this snippet is not a standalone Spring Boot application.

Four points to remember:

- **Parameter order matters:** `BindingResult` (or `Errors`) must immediately follow the `@ModelAttribute` it accompanies. If another parameter is inserted in between, MVC will not apply the error result to the expected object.
- **`@Valid`/`@Validated` triggers validation** in the appropriate configuration. Accepting `BindingResult` without triggering validation may still capture binding errors, but it will not automatically run business constraints.
- **When `BindingResult` is present**, the controller can decide to return the form instead of letting certain errors be handled via exceptions. How exceptions are raised without this parameter depends on the binding/validation type, such as `MethodArgumentNotValidException` for validating an argument or `HandlerMethodValidationException` when method validation is applied.
- **`@RequestBody` differs from form binding:** JSON is usually read by an HTTP message converter (typically Jackson), then validated; malformed JSON or deserialization failures can raise `HttpMessageNotReadableException` before any `BindingResult` exists in the MVC form style. Do not assume a single handling flow applies blindly across both data sources.

If you use a custom Spring `Validator` instead of Jakarta Bean Validation constraints, you must **register the validator with the MVC binder** (e.g., via `@InitBinder` or MVC configuration) or invoke validation explicitly. `@Valid` does not automatically discover and run every `Validator` class in the application just because it exists.

### Example: Registering a Validator for a Specific Model

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("signup")
void configureSignupBinder(WebDataBinder binder) {
    binder.addValidators(new SignupValidator());
}
```

This is an **illustrative controller method** when the model attribute is named `signup` and `SignupValidator` supports the target type. `addValidators(...)` keeps existing validators; `setValidator(...)` sets a primary validator according to the corresponding configuration. Do not invoke a validator on a target not accepted by `supports(...)`.

## 10. How Is Jakarta Bean Validation Adapted into Errors?

With `jakarta.validation`, annotations like `@NotBlank`, `@Min`, `@Size`, and `@Email` declare constraints directly on the bean. When Spring MVC triggers Bean Validation, matching violations are adapted into errors queryable via `BindingResult`, just as when a Spring `Validator` calls `errors.rejectValue(...)`.

Example:

```java
public class ProfileForm {
    @jakarta.validation.constraints.NotBlank
    private String displayName;

    @jakarta.validation.constraints.Size(max = 120)
    private String bio;

    // Getters/setters required for the chosen property binding mode.
}
```

This is a model excerpt for reading constraints, not a complete Java file. If `displayName` is blank or `bio` exceeds 120 characters, the provider returns constraint violations, and Spring places them into `BindingResult` if validation was triggered. Error codes typically relate to annotation names like `NotBlank` or `Size`; inspect `getCodes()` in your concrete situation rather than guessing the full key strings.

**Distinguishing the flow:**

| Step | Who is responsible | Example |
| --- | --- | --- |
| Read input | MVC argument resolution / message conversion | `age="abc"` |
| Convert type and bind | `DataBinder` / converter | `"20" -> int 20` |
| Check constraints | Spring Validator / Jakarta Bean Validation | `@Min(18)` |
| Collect errors | `Errors` / `BindingResult` | `typeMismatch`, `Min` |
| Resolve codes to messages | `MessageSource` and view/API layer | "Minimum age is 18" |
| Decide next action | Controller/service | Re-render form or proceed |

Some business rules require cross-checking multiple fields or querying a database; place such rules in the appropriate application layer, considering query cost and consistency. `Errors` records errors, but **does not replace** authentication, authorization, transactions, or domain invariants.

## 11. Nested Fields and Nested Paths

If the target contains an `address` object with a `city` field, you can record directly:

```java
errors.rejectValue("address.city", "city.required",
                   "City is required");
```

A dedicated validator for `Address` sometimes uses a nested path to reuse logic:

```java
errors.pushNestedPath("address");
try {
    // Here "city" is interpreted as "address.city".
    errors.rejectValue("city", "city.required",
                       "City is required");
} finally {
    errors.popNestedPath();
}
```

This snippet illustrates validating a parent object with an `address` property; ensure the target and path exist according to the implementation's access mechanism. `try/finally` restores the nested path even if an exception occurs; forgetting `popNestedPath()` can cause errors in subsequent steps to be attached to the wrong path. You can use `ValidationUtils.invokeValidator(...)` to invoke a child validator with `Errors` prepared for the right context.

In nested collections, paths like `items[0].quantity` can appear in `FieldError.getField()`. When rendering in the UI, match the field path to its position in the form, especially when rows are added, removed, or reordered.

## 12. Keeping Errors with Form Data and Displaying Safely

When MVC returns a template, the model attribute's `BindingResult` has a special key formed by `BindingResult.MODEL_KEY_PREFIX` and the attribute name. For a form named `form`, the key usually looks like:

```text
org.springframework.validation.BindingResult.form
```

The framework helps templates/views access these errors through the form-binding mechanism. In Thymeleaf, you can use `th:field` and `th:errors` to display field-bound errors, as in this snippet inside a form that already declares `th:object`:

```html
<input type="text" th:field="*{username}" />
<span th:errors="*{username}"></span>

<input type="text" th:field="*{age}" />
<span th:errors="*{age}"></span>
```

This is a **template excerpt**, not a complete HTML page; the project needs Spring/Thymeleaf integration and matching model attributes. If building a JSON response manually, map error codes/messages into a dedicated DTO per your API contract—such as `field`, `code`, `message`—instead of serializing the entire `BindingResult` directly.

**Especially with sensitive inputs:** binding errors can carry the verbatim `rejectedValue` (passwords, card numbers, tokens). Do not return or log the full `BindingResult`, `FieldError.toString()`, or rejected values without carefully evaluating data-exposure risks. Return only the information needed for the user to correct the input; avoid echoing secrets.

## 13. Testing and Verifying Accurate Results

A test suite for a validator class should separate **binding error** cases from **rule error** cases. Minimum cases for the `Signup` example:

| Input | Expected | Reason |
| --- | --- | --- |
| username `"An"`, age `"20"`, password = confirm | 0 errors | Both binding and rules pass |
| username all whitespace | Field error `username.required` | Semantically blank |
| age `"16"` | Field error `age.min` | Converted to `int` but fails constraint |
| age `"abc"` | Field error `typeMismatch`, `isBindingFailure()=true` | Wrong type; avoid adding false `age.min` |
| password differs from confirm | Global error `password.mismatch` | Cross-field rule |
| Multiple errors at once | `getAllErrors()` contains all errors | Do not lose errors by checking only the first |

When testing with JUnit, assert on **error code + field + bindingFailure flag** rather than comparing translated strings verbatim, because UI text can change with `Locale`. Example check on an existing `BindingResult`:

```java
FieldError ageError = result.getFieldError("age");
org.junit.jupiter.api.Assertions.assertNotNull(ageError);
org.junit.jupiter.api.Assertions.assertEquals("typeMismatch", ageError.getCode());
org.junit.jupiter.api.Assertions.assertTrue(ageError.isBindingFailure());
```

This test snippet expects `result` to contain a type-conversion error on `age` and the project to have the JUnit Jupiter dependency. With MVC, you can use `MockMvc` to submit form requests and inspect model errors; when switching to JSON, add separate tests for deserialization and validation errors.

### Self-debugging when the error count differs from expectations

1. Inspect the raw input and the target's **property type**; confirm whether the failure happened during bind or validate.
2. Verify `binder.bind(...)` ran and `binder.validate()` was called or triggered equivalently in MVC.
3. Check whether the validator supports the target class and is registered on the right binder.
4. Use `getAllErrors()`, `getFieldErrors()`, and `getGlobalErrors()` to break down the error counts.
5. Use `isBindingFailure()` and `getCodes()` to identify type-conversion vs. rule errors.
6. If the UI is missing a message, check `MessageSource` keys, `Locale`, and how the template/API renders errors.
7. If an error is attached to the wrong property, review `nestedPath` or the client-side field name.
8. If a field reports two unhelpful errors, review the guard condition that skips validation on fields that failed binding.

## 14. Common Design Mistakes

| Mistake | Consequence | Appropriate approach |
| --- | --- | --- |
| Calling `binder.bind` and assuming the validator already ran | Rule-violating data leaves `Errors` empty | Call `binder.validate()` or use an MVC flow with validation |
| Mixing `reject` and `rejectValue` | UI does not know which field to attach the message to | Use `rejectValue` for field-specific; `reject` for object-wide rules |
| Checking `getFieldError()` only once | Misses other fields or global errors | Use `getAllErrors()` or the respective collections |
| Treating `getErrorCount()` as the number of invalid fields | Wrong count when one field has multiple errors | Count distinct field names if you truly need field count |
| Converting all errors to `RuntimeException` manually | Hard to report multiple form errors at once | Collect via `Errors` for user-correctable input issues |
| Validator runs rules on unbound values | Adds misleading errors like "age too low" after `"abc"` | Check `hasFieldErrors("age")` before the related rule |
| Hardcoding messages in controllers | Hard to internationalize and reuse | Use error codes + `MessageSource` |
| Placing `BindingResult` non-adjacent to the form parameter | MVC does not handle errors as expected | Place immediately after `@ModelAttribute` or the matching argument |
| Treating `@Valid` as a security control | Valid data can still be bound to unauthorized properties | Use DTOs, allowlists, and backend authorization checks |
| Logging raw `rejectedValue` | Leaks sensitive information | Log selected error codes/fields and mask sensitive data |
| Sharing `Errors` across threads | Corrupted state, errors mixed across requests | Create results scoped to the request/target lifecycle |

## 15. Review Questions

**Question 1.** `age="abc"` is submitted to property `int age`. Is the validator's `age.min` the primary important error?  
No. The primary error is **type conversion**, typically with code `typeMismatch` and `isBindingFailure()=true`. The validator should avoid concluding that age is too low from the default primitive value.

**Question 2.** `startDate > endDate`; should you use `reject` or `rejectValue`?  
Both can be valid depending on the UI. If the error concerns the **relationship between two fields**, `reject` creating a global error is a natural choice; if you want the user to edit `endDate` directly, you can attach `rejectValue("endDate", ...)`.

**Question 3.** There are 3 `FieldError` instances on the same field and 1 object-wide `ObjectError`. What is `getErrorCount()`?  
4. The number of distinct invalid fields is only 1; error count does not equal field count.

**Question 4.** How does `Errors` differ from `BindingResult`?  
`Errors` declares error recording and querying operations; `BindingResult` extends it to provide binding context and model integration. `DataBinder.getBindingResult()` returns a `BindingResult`, which can be passed as `Errors` when a validator needs to record errors.

**Question 5.** Is `getFieldError("username")` enough to get all username errors?  
No. It only returns the first error or `null`. Use `getFieldErrors("username")` if you need the full list.

**Question 6.** When a controller has `@Valid @ModelAttribute("form")`, where do you place `BindingResult`?  
Immediately after that parameter in the method signature; handle `hasErrors()` before invoking business logic.

**Question 7.** Why should you avoid returning `BindingResult` directly as JSON?  
It is an internal binding/validation structure that can contain metadata and sensitive input values. Map it to an error DTO matching your API contract, using selected codes and messages.

**Remember:** `Validator` **determines rule errors**; `DataBinder` **collects binding errors**; `Errors` **is the contract for storing/querying errors**; `BindingResult` **is the result with extra binding info**; `FieldError` **attaches to a field**, `ObjectError` **attaches to the object**; `MessageSource` **resolves error codes into locale-appropriate messages**.

## Official References

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ValidationUtils API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
