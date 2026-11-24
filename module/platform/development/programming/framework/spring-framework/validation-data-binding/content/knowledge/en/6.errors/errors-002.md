# BindingResult Extends Errors with Binding Context in Spring Framework

## 1. Purpose and Context

In Spring, receiving input data typically goes through two related but distinct steps:

1. **Data binding**: reading source data (such as HTTP parameter strings) and assigning/converting it to properties of a Java object.
2. **Validation**: checking whether the object or its values satisfy declared rules.

Consider a registration form with an `age` field of type `Integer` and an `email` field of type `String`:

```text
age=abc
email=not-an-email
admin=true
```

- `age=abc` fails to convert from `String` to `Integer`: a **binding/type conversion** error.
- `email=not-an-email` converts to `String` successfully but violates an email rule: a **validation** error if a suitable validator is configured.
- `admin=true` is not in the allowed property set: the data can be **suppressed** (prevented from binding). A suppressed field does not automatically become a `FieldError`.

Spring provides `org.springframework.validation.Errors` for recording and reading errors per object/field. `org.springframework.validation.BindingResult` **extends `Errors`**, keeping all of that capability and adding information about the data-binding process: the bound target object, raw property values, conversion metadata, suppressed fields, and a model map for re-rendering the form.

The core takeaway: **`Errors` is the error-management contract; `BindingResult` is the binding result with error-management capabilities and binding-context lookup.** This is an interface inheritance relationship, not two independent error systems.

## 2. Inheritance Relationship and Position in the Processing Flow

```text
                  Errors (interface)
                  ├─ reject(...), rejectValue(...)
                  ├─ hasErrors(), getErrorCount()
                  ├─ getGlobalErrors(), getFieldErrors()
                  ├─ getFieldValue(...), getFieldType(...)
                  └─ getObjectName(), nested path, ...
                         ^
                         | extends
                         |
               BindingResult (interface)
                  ├─ getTarget()
                  ├─ getModel()
                  ├─ getRawFieldValue(...)
                  ├─ findEditor(...)
                  ├─ resolveMessageCodes(...)
                  ├─ getSuppressedFields()
                  ├─ addError(...)
                  └─ recordFieldValue(...), ...
                         ^
                         | implements
                         |
            AbstractBindingResult (base class)
                         ^
                         |
             BeanPropertyBindingResult
             DirectFieldBindingResult
             MapBindingResult
             ... (ways of storing/accessing target)
```

`BindingResult extends Errors` has two direct consequences:

- A variable of type `BindingResult` **can use every method of `Errors`**, such as `result.hasErrors()`, `result.rejectValue(...)`, or `result.getFieldErrors()`.
- A method that only needs to check or register errors can accept `Errors`. When it needs the target, raw values, suppressed fields, or model, declare `BindingResult`.

Simplified signature example:

```java
// API excerpt, not a standalone program:
public interface BindingResult extends Errors {
    Object getTarget();
    java.util.Map<String, Object> getModel();
    Object getRawFieldValue(String field);
    String[] getSuppressedFields();
    // Other methods omitted.
}
```

Depending on the version and nullability annotations, the actual Javadoc signature includes additional annotations or default method declarations. The key is understanding the `extends Errors` relationship and the responsibility of each API group.

## 3. What Does Errors Provide?

`Errors` does not perform binding itself. It defines how to **record and query** errors for an object. Representative APIs:

| `Errors` API | Meaning | Example |
| --- | --- | --- |
| `getObjectName()` | Name of the object being checked | `"signupForm"` |
| `hasErrors()`, `getErrorCount()` | Whether errors exist, total count | `true`, `2` |
| `reject(code, ...)` | Records an object-level error | `"registrationClosed"` |
| `rejectValue(field, code, ...)` | Records a property-level error | `rejectValue("email", "invalidEmail")` |
| `getGlobalErrors()` | List of object-level errors | Errors not tied to a specific field |
| `getFieldErrors()` | List of field-level errors | Errors for `age`, `email` |
| `getFieldError("age")` | First error for the field | One `FieldError` or `null` |
| `getFieldValue("age")` | Field value retained/displayed in error context | May be the rejected input string |
| `getFieldType("age")` | Field type if determinable | `Integer.class` |
| `setNestedPath(...)`, `pushNestedPath(...)`, `popNestedPath()` | Supports errors on nested objects | `address.zipCode` |

**Two types of error objects:**

- `ObjectError` describes an object-level error, typically not tied to a specific property.
- `FieldError extends ObjectError` describes a field-level error, adding `getField()`, `getRejectedValue()`, and `isBindingFailure()`.

For example, `@NotBlank` on `email` usually creates a field error; a rule like "start date must be before end date" can use an object-level error when the rule spans multiple fields.

**`Errors` is not synonymous with Bean Validation.** A `Validator` can receive `Errors` and call `rejectValue`. `@Valid`/`@Validated` are mechanisms that trigger validation in the right context; `Errors` itself is only the store/query interface for errors.

## 4. What Does BindingResult Add Beyond Errors?

### 4.1. `getTarget()`: the bound object

`getTarget()` returns the target object associated with the binding result, if present. The target may be a JavaBean, a `Map`, or another structure depending on the implementation. When constructor binding fails in certain flows, do not assume a target is always obtainable.

You can inspect it via:

```java
Object boundObject = result.getTarget();
```

In MVC, a controller typically already has the `@ModelAttribute SignupForm form` parameter, so calling `getTarget()` just to reach the same object is unnecessary. This API is especially useful when working directly with `DataBinder` or generic utilities that receive binding results.

### 4.2. `getRawFieldValue(field)`: the raw property value

`getRawFieldValue("age")` returns the field's value in the target object in the raw form accessible by the implementation, or `null` if indeterminable. It differs from `Errors.getFieldValue("age")`: the `Errors` method may return the **rejected value** for re-rendering on a form when conversion fails.

For example, when a client sends `age=abc` and the target type is `Integer`:

- Conversion fails, so `form.getAge()` may remain `null`.
- `result.getRawFieldValue("age")` may be `null` because that is the actual property value.
- `result.getFieldValue("age")` may return `"abc"` because Spring retains the rejected value for displaying messages on the form.
- `result.getFieldError("age").getRejectedValue()` contains `"abc"`; `isBindingFailure()` is `true`.

Do not confuse "raw field value" with "original HTTP string". For type-conversion errors, the rejected input typically lives in `FieldError`. Availability of the raw field value depends on the target type and implementation.

### 4.3. `getModel()` and `MODEL_KEY_PREFIX`: data for re-rendering the form

`BindingResult.getModel()` creates a `Map<String, Object>` with **two core entries**:

1. `objectName` → the bound target object itself.
2. `BindingResult.MODEL_KEY_PREFIX + objectName` → the `BindingResult` instance.

The value of `BindingResult.MODEL_KEY_PREFIX` is:

```text
org.springframework.validation.BindingResult.
```

If the object name is `signupForm`, the two keys are:

```text
signupForm
org.springframework.validation.BindingResult.signupForm
```

Frameworks and view templates can use this pair to render both form contents and corresponding errors. `getModel()` **creates a new map on every call**; mutating the returned map and calling `getModel()` again will not preserve those mutations. In normal Spring MVC usage, Spring already manages the model and `BindingResult` for model attributes; you rarely need to construct these two keys manually.

### 4.4. `getSuppressedFields()`: fields blocked from binding

When `DataBinder` is configured with `setAllowedFields(...)` or a corresponding field policy, names of disallowed fields can be recorded in `BindingResult`. `getSuppressedFields()` returns the list of suppressed field names.

Example:

```java
binder.setAllowedFields("age", "email");
// Request also contains admin=true.
String[] fields = binder.getBindingResult().getSuppressedFields();
```

If `admin` is suppressed, the array above may contain `"admin"`. **Do not infer `hasErrors() == true` just because suppressed fields exist**: blocking a field does not automatically create a `FieldError`. If application policy requires rejecting the entire request when fields outside the allowlist are sent, check this array and return an appropriate error. This is important extra information that `BindingResult` provides alongside `Errors`.

### 4.5. Other extended APIs

| `BindingResult` API | When it is useful |
| --- | --- |
| `findEditor(field, valueType)` | Looks up a registered `PropertyEditor` by field/type if provided by the implementation |
| `getPropertyEditorRegistry()` | Accesses the editor registry if present; may be `null` |
| `resolveMessageCodes(code)` | Resolves message codes for an object-level error |
| `resolveMessageCodes(code, field)` | Resolves specific message codes by object/field/type; useful for i18n |
| `addError(ObjectError)` | Appends an `ObjectError`/`FieldError` when an error-handling strategy needs it |
| `recordFieldValue(field, type, value)` | Retains field metadata in cases such as target instantiation failure |
| `recordSuppressedField(field)` | Records a field rejected during binding |

Most application code only needs `hasErrors`, `getFieldErrors`, `getSuppressedFields`, and occasionally `getModel`. The editor and message-code APIs are mainly useful when building binding infrastructure, formatters, or form UIs.

## 5. How Spring DataBinder Creates and Uses BindingResult

```text
Data source (HTTP parameters / MutablePropertyValues)
                         |
                         v
                    DataBinder
               +-------------------+
               | check allowedFields|
               | resolve property   |
               | conversion         |
               | setter/field access|
               +-------------------+
                         |
             +-----------+-----------+
             |                       |
          success              conversion fails
             |                       |
      target assigned        FieldError(typeMismatch,
                              bindingFailure=true,
                              rejectedValue="abc")
             |                       |
             +-----------+-----------+
                         |
                 Validator / @Valid
                   (if triggered)
                         |
                FieldError/ObjectError
                for validation rules
                         |
                         v
                 BindingResult
                 = Errors API
                 + binding metadata
                         |
           controller / view / API response
```

Key points to distinguish:

- `DataBinder` is the **component that executes binding**, whereas `BindingResult` is the **result** collected after binding. In code, retrieve it via `binder.getBindingResult()`.
- Type conversion can use `ConversionService`, `Converter`/`Formatter`, or `PropertyEditor` depending on configuration.
- Conversion errors typically carry a base code like `typeMismatch`; validator errors carry codes defined by the validation rules, such as `invalidEmail`.
- Validators run **when invoked or configured to trigger**, not merely by obtaining `BindingResult`. With standalone `DataBinder`, call `binder.validate()`; with Spring MVC, use `@Valid` and a Bean Validation provider.
- When binding fails for one field, other fields may still be assigned successfully. Therefore, the target object may contain partially valid state; do not proceed with business logic if the result has errors.
- Do not treat a suppressed field as "the entire request has been safely validated". It is a signal for applying your controller's policy.

## 6. Standalone Java 17+ Example with Spring Framework 6.2

This example runs on **JDK 17** and Maven, requiring no web server or database. It creates a `SignupForm`, passes three inputs `age=abc`, `email=not-an-email`, and `admin=true` to `DataBinder`, and then runs a custom `Validator`.

We expect to see:

- One `FieldError` from failing to convert `age` to `Integer`.
- One `FieldError` because `email` does not contain `@`.
- `admin` in suppressed fields because it is not in the allowlist.
- The model containing keys for both the object and `BindingResult`.

### 6.1. File layout

```text
binding-result-demo/
├── pom.xml
└── src/main/java/demo/BindingResultDemo.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>binding-result-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BindingResultDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` pulls in the core Spring modules needed for `DataBinder` and `Validator`. The example does not need a Jakarta Bean Validation dependency because it uses `org.springframework.validation.Validator` directly.

### 6.3. `src/main/java/demo/BindingResultDemo.java`

```java
package demo;

import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public final class BindingResultDemo {

    public static final class SignupForm {
        private Integer age;
        private String email;

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }

    static final class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return SignupForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            SignupForm form = (SignupForm) target;
            if (form.getEmail() == null ||
                    !form.getEmail().contains("@")) {
                errors.rejectValue(
                        "email", "invalidEmail", "Email must contain @");
            }
        }
    }

    public static void main(String[] args) {
        SignupForm form = new SignupForm();

        DataBinder binder = new DataBinder(form, "signupForm");
        binder.setAllowedFields("age", "email");
        binder.setValidator(new SignupValidator());

        MutablePropertyValues incoming = new MutablePropertyValues();
        incoming.add("age", "abc");
        incoming.add("email", "not-an-email");
        incoming.add("admin", "true");

        binder.bind(incoming);
        binder.validate();

        BindingResult result = binder.getBindingResult();
        FieldError ageError = result.getFieldError("age");
        FieldError emailError = result.getFieldError("email");

        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());

        System.out.println("age.code=" + ageError.getCode());
        System.out.println("age.rejected=" + ageError.getRejectedValue());
        System.out.println("age.bindingFailure=" +
                ageError.isBindingFailure());

        System.out.println("email.code=" + emailError.getCode());
        System.out.println("email.bindingFailure=" +
                emailError.isBindingFailure());

        System.out.println("age.fieldValue=" +
                result.getFieldValue("age"));
        System.out.println("age.rawFieldValue=" +
                result.getRawFieldValue("age"));
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));

        Map<String, Object> model = result.getModel();
        System.out.println("sameTarget=" +
                (result.getTarget() == form));
        System.out.println("model.hasForm=" +
                model.containsKey("signupForm"));
        System.out.println("model.hasBindingResult=" +
                model.containsKey(
                        BindingResult.MODEL_KEY_PREFIX + "signupForm"));
    }
}
```

Notable lines explained:

1. `DataBinder(form, "signupForm")` creates a binder for the JavaBean object and object name. That name appears in message code paths and model keys.
2. `setAllowedFields("age", "email")` restricts property binding. The `admin` field is suppressed even though the source data sent it.
3. `binder.bind(incoming)` attempts to convert `age` to `Integer`. The string `"abc"` triggers a `typeMismatch` error; no value is assigned to `form.age`.
4. `binder.validate()` runs `SignupValidator`. The validator accepts the **`Errors` parameter type** so it does not depend on `BindingResult`-specific APIs, yet its recorded errors still appear in the same final `BindingResult`.
5. `FieldError.isBindingFailure()` distinguishes conversion failures from rule errors created by the validator. `getFieldValue` preserves the user-submitted value for re-rendering the form; `getRawFieldValue` reads the current value of the target property.
6. `getModel()` shows that `BindingResult` carries the additional responsibility of building model data, which `Errors` does not define.

### 6.4. Run command and expected stdout

From the `binding-result-demo` directory:

```bash
mvn -q compile exec:java
```

**Program stdout:**

```text
hasErrors=true
errorCount=2
age.code=typeMismatch
age.rejected=abc
age.bindingFailure=true
email.code=invalidEmail
email.bindingFailure=false
age.fieldValue=abc
age.rawFieldValue=null
suppressed=[admin]
sameTarget=true
model.hasForm=true
model.hasBindingResult=true
```

This is the exact output of `main`; the example prints logical values to avoid depending on Spring's verbose default message formatting. `getFieldValue("age")` returns the rejected value because conversion failed, whereas `getRawFieldValue("age")` returns `null` because `Integer age` was never assigned. Spring can generate multiple detailed message codes for a single error, though the example only prints the base codes `typeMismatch` and `invalidEmail`.

If you replace `age=abc` with `age=21`, the binding error on `age` disappears. If you replace `email=not-an-email` with `email=user@example.com`, the validation error disappears. However, **`admin` remains suppressed** and `getSuppressedFields()` will still contain that name; the error count from `Errors` does not automatically increase because of a suppressed field.

## 7. Using BindingResult in Spring MVC

### 7.1. Parameter placement is critical

When a controller uses `@ModelAttribute` and triggers validation, `BindingResult` (or `Errors`) must be placed **immediately after** the corresponding model attribute parameter if you want to handle errors inside the controller method.

```java
// Spring MVC controller snippet, not a standalone file.
// Assumes a SignupService bean and a signup/form view exist.
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "signup/form";
    }

    signupService.register(form);
    return "redirect:/signup/success";
}
```

Here `@Valid` is `jakarta.validation.Valid`, while `@ModelAttribute` belongs to `org.springframework.web.bind.annotation`. A real Spring MVC application requires a configured validation provider (e.g., `spring-boot-starter-validation`) and corresponding beans/views.

Incorrect placement:

```java
// Incorrect BindingResult placement for signupForm:
public String submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        Model model,
        BindingResult result) {
    // ...
}
```

The incorrect example above places `Model` between the form and `BindingResult`; Spring MVC cannot treat that result parameter as the error result for the preceding model attribute under the controller contract. Without a properly placed `BindingResult`, validation/binding failures are normally routed to the framework's exception mechanism instead of being passed directly to the controller via this parameter.

**A controller with multiple form objects** can declare two adjacent pairs, each `BindingResult` belonging to the form immediately preceding it. Using explicit `@ModelAttribute("...")` names helps map views and error messages to the right object.

### 7.2. Rendering form errors

Common handling in view-returning applications:

- `result.hasErrors()` decides whether to return to the form.
- `result.getFieldErrors()` displays errors per input such as `email` or `age`.
- `result.getGlobalErrors()` handles errors involving multiple fields or object state.
- `FieldError.getRejectedValue()`/`getFieldValue()` helps retain the user's submitted input, even when conversion failed.
- View engines or Spring form tags can use the model keys tied to `BindingResult`. In normal MVC flows, the framework automatically supplies the result under the model attribute name.

Do not expose raw `FieldError` or `BindingResult` objects in public JSON without filtering: rejected values may contain sensitive data, long strings, or client-controlled input. For APIs, construct a structured error response (field, safe code, chosen message) and escape values when rendering into HTML.

### 7.3. Does BindingResult apply to @RequestBody JSON?

`@RequestBody` usually goes through an `HttpMessageConverter` (such as Jackson), whereas `@ModelAttribute` uses MVC's property/constructor data-binding mechanism. With `@Valid @RequestBody`, Bean Validation errors can be routed through MVC's error mechanism and in some signatures controllers can declare `Errors`/`BindingResult`. **However, do not assume every JSON error lands in `BindingResult`**: malformed JSON, unreadable bodies, or severe deserialization failures can raise an exception before any model object exists to validate, such as `HttpMessageNotReadableException`.

When building REST APIs, establish a unified error strategy via `@ControllerAdvice` and `@ExceptionHandler`, distinguishing unreadable JSON, Bean Validation errors, and business errors. Do not rely on `DataBinder.setAllowedFields` assuming it restricts every property Jackson deserializes from JSON; that boundary must be enforced via DTOs and JSON configuration.

## 8. Distinguishing Binding Errors, Validation Errors, and Suppressed Fields

| Case | Detection phase | Typical details | `hasErrors()` |
| --- | --- | --- | --- |
| `age=abc` when `age` is `Integer` | Type conversion during data binding | `FieldError("age")`, `code="typeMismatch"`, `bindingFailure=true`, `rejectedValue="abc"` | `true` |
| `email=not-an-email` rejected by validator | Validation after binding | `FieldError("email")`, validator-supplied code, `bindingFailure=false` | `true` |
| Two individual fields valid, invalid relationship | Object-level validation | `ObjectError` from `reject(...)` | `true` |
| `admin=true` blocked by `allowedFields` | Suppression during data binding | `getSuppressedFields()` contains `"admin"` | Does not automatically become `true` |
| Valid data and no validator errors | Bind + validation succeed | No `ObjectError`/`FieldError` | `false` |

A field can accumulate multiple errors (multiple failing constraints). `getFieldError("email")` only returns the first recorded error, whereas `getFieldErrors("email")` returns the full list. If you need one message per issue type, inspect the list and apply an explicit selection policy rather than relying on incidental ordering.

Information from `getSuppressedFields()` must be handled separately. Many applications want to return HTTP 400 when a request includes out-of-contract fields, but Spring does not do that automatically from `hasErrors()` alone.

## 9. Role of Message Codes and Internationalization

An `ObjectError` or `FieldError` can carry:

- `objectName` and (for field errors) `field`.
- `codes`: a list of message codes ordered from specific to general.
- `arguments`: parameters for message interpolation.
- `defaultMessage`: a fallback message.
- For `FieldError`: `rejectedValue` and `bindingFailure`.

For example, a `typeMismatch` error on field `age` of `signupForm` may resolve to variants such as:

```text
typeMismatch.signupForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

This is **an example of how `DefaultMessageCodesResolver` builds code sequences**, not a guarantee that every `BindingResult` uses the exact same strategy or configuration. `BindingResult.resolveMessageCodes("typeMismatch", "age")` produces the appropriate codes; `MessageSource` picks the localized message from those codes and the locale. `FieldError.getCode()` only gives the base error code, while `getCodes()` returns all candidate codes.

For example, an application might define messages:

```properties
typeMismatch.signupForm.age=Please enter age as an integer.
invalidEmail.signupForm.email=Email address is invalid.
```

Never expose raw exception names or stack-trace details in user-facing messages. For server errors, message filtering and localization must stay consistent with the project's API/view error-handling conventions.

## 10. Things to Keep in Mind When Working with BindingResult

### 10.1. A binding result is not a validator

`DataBinder.bind(...)` records data conversion and assignment. `binder.validate()` invokes configured validators. `@Valid` and `@Validated` instruct Spring MVC to trigger validation under appropriate conditions. Do not assume `BindingResult` contains validation errors if no validation step actually ran.

### 10.2. A FieldError is not necessarily a binding failure

`FieldError.isBindingFailure()` returns `true` for binding-time failures such as type mismatch; validator-recorded field errors usually create a `FieldError` with `bindingFailure=false`. This distinction is essential if an API needs to differentiate "could not parse value" from "value parsed but is invalid".

### 10.3. getFieldValue() is not identical to getRawFieldValue()

Binding errors can store a rejected value that differs from the target property value. When re-rendering a form, you need to preserve the string the user submitted; therefore, do not substitute the raw target value for the rejected value in all situations.

### 10.4. The target may have been partially updated

Some fields can still bind successfully even when another field fails. Whenever `hasErrors()` is true, never automatically persist the entity or execute sensitive business logic on the partially populated target. Use dedicated DTOs/form objects, validate thoroughly, and then map to business commands.

### 10.5. Be careful with nested field names

Error field names can be `address.zipCode` or `items[0].quantity`. `Errors` provides nested-path APIs, and `BindingResult` follows the corresponding property-access style. Do not manually parse dots or brackets as plain strings if you need structured error access.

### 10.6. Do not confuse suppressed fields with errors

Data outside the allowlist is not assigned, yet it does not automatically increment `getErrorCount()`. To prevent overposting, inspect `getSuppressedFields()` and respond with an error or log appropriately without leaking sensitive values.

### 10.7. Watch out for user data inside rejected values

`FieldError.getRejectedValue()` can contain client-supplied input. Avoid echoing unescaped HTML and avoid writing passwords, tokens, or sensitive data into logs; limit length and map to friendly message codes in API responses.

### 10.8. BindingResult is tied to an object name

In MVC, the model key pattern is `org.springframework.validation.BindingResult.<objectName>`. Using the wrong object/attribute name when constructing a model manually or carrying errors across steps can prevent views from displaying errors or mix up results between forms. Object names must match consistently.

### 10.9. Do not overuse BindingResult in the business layer

Domain services can return business errors via dedicated result types, exceptions, or explicitly designed error structures. `BindingResult` is an abstraction of Spring's binding/validation layer; it does not need to be threaded through services and repositories.

## 11. Practical Scenarios: Troubleshooting and Testing

### Scenario A: Form has a type error but still re-displays what the user typed

The client sends `age=abc`. `form.getAge()` is `null`, while `result.getFieldValue("age")` can be `"abc"` and `FieldError.getRejectedValue()` is also `"abc"`. Views should use Spring's binding mechanism to re-display the value rather than writing "null" back into the input and erasing what the user typed.

### Scenario B: Email format is wrong even though type conversion succeeded

The string `email=not-an-email` is a valid `String` at the binding level. A validator can call `errors.rejectValue("email", "invalidEmail")` to report the error; `FieldError.isBindingFailure()` distinguishes it as a validation error.

### Scenario C: Request tries to inject a privilege field

The client sends `admin=true`, while the binder only allows `age` and `email`. `getSuppressedFields()` provides the signal to inspect. This does not mean the server "validated" the request and declared it safe; rejecting unexpected fields is a controller/API policy decision.

### Scenario D: Form has multiple errors

Call `hasErrors()` to halt business execution when errors exist, then use `getFieldErrors()` and `getGlobalErrors()` to build the message set. For fields with multiple errors, never assume every field has at most one `FieldError`. For APIs, sorting results and attaching stable error codes makes client handling easier.

### Testing checklist

1. Valid input: `hasErrors=false`, target values accurate, suppressed fields empty.
2. Type mismatch (number/date): `FieldError.isBindingFailure=true`, `getRejectedValue` preserves the invalid value.
3. Validation failure: `FieldError.isBindingFailure=false`, error code matches validator output.
4. Two invalid fields together: `getErrorCount` reflects error count, per-field queries are accurate.
5. Field outside allowlist: target unchanged, `getSuppressedFields` contains field name.
6. Nested fields: field path and nested error accurate.
7. Model attribute names: `getModel` contains both expected keys for the object name.
8. In MVC: `BindingResult` sits immediately after the form object, and the view sees field errors and rejected values.
9. Error messages: no secrets, no dangerous markup reflection, locale support verified where needed.

## 12. Knowledge Self-Check

**Question 1:** If a method only needs to call `rejectValue` and `hasErrors`, which parameter type should it accept?

**Answer:** `Errors` is usually sufficient. It still accepts a `BindingResult` instance because that interface extends `Errors`.

**Question 2:** What should you use to retrieve the list of fields blocked by `allowedFields`?

**Answer:** `BindingResult.getSuppressedFields()`.

**Question 3:** Does `getFieldValue("age")` always equal `getRawFieldValue("age")`?

**Answer:** No. When conversion fails, `getFieldValue` can prioritize the rejected value for display, whereas `getRawFieldValue` reflects the target property's actual value.

**Question 4:** Is a `FieldError` always a binding error?

**Answer:** No. Validators also create field-level errors. Use `isBindingFailure()` and the error code to distinguish the context.

**Question 5:** How many key entries of importance does `BindingResult.getModel()` add?

**Answer:** One key for the target object and one key `BindingResult.MODEL_KEY_PREFIX + objectName` for the binding result itself.

**Question 6:** Does `getSuppressedFields().length > 0` automatically make `hasErrors()` return `true`?

**Answer:** No. Suppressed fields must be checked explicitly under the application's input-protection policy.

## 13. Official Documentation

- [Spring Framework Javadoc — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/BindingResult.html): additional APIs, `MODEL_KEY_PREFIX`, extends `Errors`.
- [Spring Framework Javadoc — Errors](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/Errors.html): `reject`, `rejectValue`, object/field errors, and query APIs.
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/DataBinder.html): `bind`, `validate`, `getBindingResult`, `setAllowedFields`.
- [Spring Framework — Validator](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html): implementing `Validator` and using `Errors`.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): placing `BindingResult` immediately after the form parameter and handling errors in controllers.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, and error-handling paths.