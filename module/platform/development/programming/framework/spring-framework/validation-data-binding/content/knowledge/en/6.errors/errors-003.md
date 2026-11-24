# ObjectError and FieldError in Spring Framework

## 1. Roles of the Two Error Types

When Spring performs **data binding** (mapping request data onto a Java object) or **validation** (checking whether data satisfies rules), the result can contain multiple errors. Spring represents them with two classes in the `org.springframework.validation` package:

- **`ObjectError`:** describes an error concerning the **entire object** (global/object-level error), such as a business rule that evaluates multiple properties together.
- **`FieldError`:** describes an error on a **specific property** (field-level error), such as `age` failing to convert to a number or `email` failing `@Email`.

An important point about inheritance:

```text
org.springframework.context.support.DefaultMessageSourceResolvable
              |
              v
org.springframework.validation.ObjectError
              |
              v
org.springframework.validation.FieldError
```

**`FieldError extends ObjectError`.** Therefore, every `FieldError` is also an `ObjectError` in terms of **Java type**, though it carries additional information about the failing field. When referring to a *global error* in `BindingResult`, Spring means an error **not attached to a field**; do not assume every element typed as `ObjectError` is a global error.

Example order form:

```text
productCode = ""
quantity    = "abc"
currency    = "USD"
country     = "VN"
```

- `productCode` is blank, violating `@NotBlank` → typically produces a `FieldError` for `productCode`.
- `quantity=abc` cannot be converted to `Integer` → produces a `FieldError` for `quantity` with `bindingFailure=true`.
- The order as a whole fails a coordination rule, such as "this order type cannot be used with that country" → the validator can register a global `ObjectError`.

A rule spanning multiple fields is not **required** to be a global error: the validator author can deliberately attach the violation to a chosen field. How the error appears depends on where the validator reports it.

## 2. Comparing Structure and APIs

| Property/Method | `ObjectError` | `FieldError` |
| --- | --- | --- |
| Package | `org.springframework.validation` | `org.springframework.validation` |
| Target | Overall object/model | A specific field/property path |
| Inheritance | `DefaultMessageSourceResolvable` | `ObjectError` |
| `getObjectName()` | Yes | Yes (inherited) |
| `getCodes()`, `getCode()` | Yes | Yes (inherited) |
| `getArguments()`, `getDefaultMessage()` | Yes | Yes (inherited) |
| `getField()` | No | Yes |
| `getRejectedValue()` | No | Yes |
| `isBindingFailure()` | No | Yes |
| Typical origin | `errors.reject(...)` or object-level constraint | `errors.rejectValue(...)`, type mismatch, field constraint |
| Convenient retrieval | `errors.getGlobalErrors()` | `errors.getFieldErrors()` |

### Meaning of each data field

**`objectName`** is the name of the object being validated/bound, e.g. `"registration"`; it does not have to match the Java class name. In MVC, it usually comes from the model attribute name; in `new DataBinder(target, "registration")`, the developer passes the name directly.

**`codes`** is a prioritized list of message keys used to look up a translation or suitable message. **`defaultMessage`** is the fallback message if no matching key is found; it is not guaranteed to be translated into the user's language.

**`field`** is the name of the failing property, such as `"age"`, `"address.zipCode"`, or `"items[0].quantity"`. **`rejectedValue`** is the value rejected in the binding/validation context; this value may contain sensitive data, so never print it verbatim to logs or public APIs.

**`bindingFailure`** distinguishes a binding/conversion failure (`true`) from a normal validation failure (`false`). You need to know *which field failed* and *why kind of error occurred* rather than looking only at the message text.

### Basic methods

```java
ObjectError objectError = ...; // Obtained from BindingResult.getGlobalError()
String objectName = objectError.getObjectName();
String[] messageCodes = objectError.getCodes();
String defaultMessage = objectError.getDefaultMessage();

FieldError fieldError = ...; // Obtained from BindingResult.getFieldError("age")
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
boolean conversionOrBindingFailed = fieldError.isBindingFailure();
```

This snippet illustrates usage once you already have two non-`null` error variables, **not a standalone Java file**. `getGlobalError()` and `getFieldError(...)` can return `null`; real code must check before calling methods on them.

## 3. Where Errors Are Stored: `Errors` and `BindingResult`

`ObjectError`/`FieldError` are **error records**. The objects holding the error collection in Spring's flow are the `Errors` interface and its subinterface `BindingResult`:

```text
HTTP form/query
      |
      v
WebDataBinder / DataBinder
      |
      +--> conversion or assignment fails ------> FieldError (binding failure)
      |
      +--> run Validator / Bean Validation
                 |
                 +--> property error ---------> FieldError
                 |
                 +--> object-wide error ------> ObjectError
      |
      v
BindingResult extends Errors
      |
      +--> getFieldErrors()  : List<FieldError>
      +--> getGlobalErrors() : List<ObjectError> (global only)
      +--> getAllErrors()    : List<ObjectError> (both types)
```

In MVC programming, controllers typically declare `BindingResult` immediately after the `@ModelAttribute` or `@RequestBody` argument to be validated. When writing a standalone validator, the parameter usually uses the `Errors` interface. When you need field values, binding metadata, suppressed fields, or `getModel()`, `BindingResult` provides those additional methods.

Key retrieval methods:

| API on `Errors` / `BindingResult` | Result |
| --- | --- |
| `hasErrors()` | At least one error of any kind exists |
| `hasGlobalErrors()` | At least one global error exists |
| `hasFieldErrors()` | At least one field error exists |
| `hasFieldErrors("email")` | At least one error exists on field `email` |
| `getErrorCount()` | Total number of error records |
| `getGlobalErrorCount()` | Number of global errors |
| `getFieldErrorCount()` | Number of field errors |
| `getGlobalError()` | First global error or `null` |
| `getFieldError("email")` | First field error for `email` or `null` |
| `getGlobalErrors()` | List of global errors |
| `getFieldErrors()` | List of field errors |
| `getFieldErrors("email")` | List of all errors for `email` |
| `getAllErrors()` | Both global errors and field errors |
| `getFieldValue("email")` | Field value for re-rendering, possibly the rejected value |
| `getSuppressedFields()` | Names of fields blocked during binding (`BindingResult` API) |

**A single field can have multiple errors**, so `getFieldErrorCount()` counts **error records**, not distinct field names. For example, the same field may violate two constraints. Do not use `getFieldError("email")` if the requirement is to display **all** errors for that field; use `getFieldErrors("email")`.

Important: `getAllErrors()` has the declared return type `List<ObjectError>`, because `FieldError` extends `ObjectError`. To group items when iterating that list, check `instanceof FieldError` or use `getFieldErrors()` / `getGlobalErrors()` separately.

## 4. Creating Errors with `reject` and `rejectValue`

Spring provides two direct operations through `Errors` and `BindingResult`:

```java
// Error concerning the whole object:
errors.reject("order.inconsistent",
              "Order information is inconsistent");

// Error concerning a specific field:
errors.rejectValue("quantity",
                   "quantity.invalid",
                   "Invalid quantity");
```

These are two calls **inside a method that already has a valid `errors` variable**. Calling `reject(...)` adds a global error; calling `rejectValue("quantity",...)` adds a field error. Other overloads accept `Object[] errorArgs` for parameterized messages.

Example of a multi-property rule:

```java
// Inside Validator.validate(Object target, Errors errors):
OrderForm form = (OrderForm) target;

if ("INTERNATIONAL".equals(form.getShippingMethod())
        && "DOMESTIC_ONLY".equals(form.getProductType())) {
    errors.reject("shipping.product.conflict",
                  "Product does not support this shipping method");
}

if (form.getQuantity() != null && form.getQuantity() <= 0) {
    errors.rejectValue("quantity", "quantity.positive",
                       "Quantity must be greater than 0");
}
```

The snippet above illustrates an application-defined `OrderForm` class and must be placed inside a suitable `validate` method. In the example, the first error is object-level because it describes a relationship between two properties; the second is attached to `quantity` so the UI can render it right next to the input box.

### Errors do not come only from validators

`DataBinder` automatically records several binding errors without requiring a call to `rejectValue(...)`:

- `typeMismatch`: fails to convert a string to the target type, e.g. `"abc"` → `Integer`.
- `required`: missing a field configured on the binder as required via `setRequiredFields(...)`.
- `methodInvocation`: failure invoking a setter/property under the binder's error-processing mechanism.

These codes are common error codes produced by `DefaultBindingErrorProcessor`; other versions or configurations may use different strategies. Distinguish binding errors occurring during **data conversion/assignment** from validation errors occurring during **rule evaluation**. `@NotBlank`, `@Size`, `@Min`, or a Spring `Validator` typically add validation errors after binding when triggered.

## 5. Complete Java 17+ Example: Inspecting All Three Errors

The example below runs outside a web server using Spring Framework 6.2.x and Maven. The goal is to demonstrate how `DataBinder` creates a `FieldError` for a type-conversion failure, how to add a validation `FieldError`, and how to add a global `ObjectError`. This example does not need a Jakarta Bean Validation provider because we register two errors manually.

Create `pom.xml` in the Maven project directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-errors-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/demo/ErrorsDemo.java`:

```java
package demo;

import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class ErrorsDemo {

    public static class Signup {
        private String username;
        private Integer age;

        public Signup() {}

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public Integer getAge() { return age; }
        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static void main(String[] args) {
        Signup signup = new Signup();
        DataBinder binder = new DataBinder(signup, "signup");
        binder.setAllowedFields("username", "age");

        // Input data consists of strings. "abc" cannot convert to Integer.
        binder.bind(new MutablePropertyValues(
                Map.of("username", "A", "age", "abc")));

        BindingResult errors = binder.getBindingResult();

        // Simulate one field validation error and one object-wide error.
        errors.rejectValue("username",
                "username.tooShort", "Username is too short");
        errors.reject("signup.blocked",
                "Cannot create account");

        FieldError ageError = errors.getFieldError("age");
        FieldError usernameError = errors.getFieldError("username");
        ObjectError globalError = errors.getGlobalError();

        System.out.println("total=" + errors.getErrorCount());
        System.out.println("global=" + errors.getGlobalErrorCount());
        System.out.println("field=" + errors.getFieldErrorCount());
        System.out.println("age.field=" + ageError.getField());
        System.out.println("age.rejected=" + ageError.getRejectedValue());
        System.out.println("age.bindingFailure="
                + ageError.isBindingFailure());
        System.out.println("username.rejected="
                + usernameError.getRejectedValue());
        System.out.println("username.bindingFailure="
                + usernameError.isBindingFailure());
        System.out.println("global.object="
                + globalError.getObjectName());
        System.out.println("global.defaultMessage="
                + globalError.getDefaultMessage());
    }
}
```

Run with Java 17+ and Maven installed:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.ErrorsDemo
```

Stdout produced by `main` (excluding Maven logs):

```text
total=3
global=1
field=2
age.field=age
age.rejected=abc
age.bindingFailure=true
username.rejected=A
username.bindingFailure=false
global.object=signup
global.defaultMessage=Cannot create account
```

Explanation:

1. `Map.of("username","A","age","abc")` holds **strings** like a form submission. `DataBinder` assigns `username=A` successfully.
2. The `Integer` property `age` cannot accept `"abc"`, so the binder creates a `FieldError` with `isBindingFailure() == true` and rejected value `"abc"`.
3. `rejectValue("username",...)` adds a field error, but because it is a manual validation rule, `isBindingFailure() == false`.
4. `reject("signup.blocked",...)` adds a global `ObjectError`. `getObjectName()` is `"signup"`, the name passed to `DataBinder`.
5. The total of three errors consists of two field errors and one global error. The fact that `Map.of` does not guarantee iteration order does not affect the outcome because we query fields by name rather than relying on list order.

The Java code above **compiles as a standalone class in a Maven project with the declared dependency**; no web server or database connection is required.

## 6. Reading Errors Properly in a Spring MVC Controller

In a form-receiving controller, place `BindingResult` **immediately after** the argument being bound/validated:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

// Methods live inside an appropriate @Controller or @RestController class.
@PostMapping("/signup")
public ResponseEntity<String> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (form.getPassword() != null
            && form.getPassword().equals(form.getUsername())) {
        errors.reject("signup.passwordSameAsUsername",
                "Password must not match username");
    }

    if (errors.hasErrors()) {
        for (FieldError error : errors.getFieldErrors()) {
            // Map field + code + message to UI/API as needed.
            // Avoid logging rejectedValue directly for sensitive fields.
        }
        for (ObjectError error : errors.getGlobalErrors()) {
            // Display form-wide error once.
        }
        return ResponseEntity.badRequest().body("INVALID_SIGNUP");
    }

    return ResponseEntity.ok("ACCEPTED");
}
```

This is an **illustrative method snippet**, not a standalone file: the application must define `SignupForm` with getters, corresponding validators/constraints, and have Spring MVC + a Bean Validation provider configured. `@Valid` is `jakarta.validation.Valid` in Spring Framework 6 / Spring Boot 3; `BindingResult` remains Spring's interface. With JSON `@RequestBody`, validation handling can also use `BindingResult` or an exception handler depending on the method signature.

Whether errors are recorded by the framework or added via `errors.reject(...)`, they appear together in `BindingResult`. A response can contain **multiple** errors; the controller should return the full relevant list rather than checking only the first error if the UI needs to guide the user to fix multiple fields.

### When `BindingResult` is not declared

In MVC, validation failures on `@Valid @RequestBody`/`@Valid @ModelAttribute` parameters are typically handled via exceptions (such as `MethodArgumentNotValidException` in the corresponding cases). Modern Spring MVC also supports **method validation** with `HandlerMethodValidationException` for signatures carrying constraints directly on parameters/methods. Do not assume all validation errors pass through the same exception; however, when a matching `BindingResult` is present, reading `getFieldErrors()` and `getGlobalErrors()` still follows this model.

For Spring WebFlux, reactive-specific exception types and flows apply, such as `WebExchangeBindException`; do not copy MVC handlers verbatim into reactive applications.

## 7. Building API Responses and Displaying Errors to Users

An API can return a structure like the following (this is an **application design**, not a default JSON format guaranteed by Spring):

```json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "age",
      "code": "typeMismatch",
      "message": "Age must be a valid number"
    },
    {
      "field": "username",
      "code": "username.tooShort",
      "message": "Username is too short"
    }
  ],
  "globalErrors": [
    {
      "code": "signup.blocked",
      "message": "Cannot create account"
    }
  ]
}
```

The short `code` fields in the example above can be business codes the application **chooses to publish**. Inside `ObjectError`/`FieldError`, `getCodes()` typically holds **Spring-expanded message codes** incorporating object name, field name, and data type. Therefore, do not assume `error.getCode()` equals the exact string passed to `errors.reject(...)`; when a stable API contract is required, define a dedicated set of public error codes.

Implementation tips:

- Form UI: display `FieldError` next to the input with the matching `field`; display `ObjectError` in a general message area.
- API: return safe messages, optionally with `field` and a stable error code. Returning multiple errors lets clients fix all issues in one round trip.
- Logging: logging field names/error codes is fine; avoid writing `rejectedValue` containing passwords, tokens, personal data, or oversized payloads into logs or responses.
- Security: even field names deserve consideration if they expose internal structure; use public DTOs as the boundary between requests and business models.

**Never rely on `ObjectError`/`FieldError.toString()` itself as a response format**: it is not a JSON contract meant for client applications, and it may expose details that should stay private.

### Accessing elements in `getAllErrors()`

```java
for (ObjectError error : errors.getAllErrors()) {
    if (error instanceof FieldError fieldError) {
        System.out.println("field=" + fieldError.getField());
    } else {
        System.out.println("global=" + error.getObjectName());
    }
}
```

This snippet belongs inside a method with an `errors` variable of type `Errors` or `BindingResult`. Pattern matching `instanceof` has been supported since Java 16 (works well with Java 17+). In applications handling real input, `System.out.println` is purely illustrative; avoid printing sensitive values.

## 8. Message Codes, `MessageSource`, and Localization

`ObjectError` implements `MessageSourceResolvable` via its superclass, so it can be passed directly into a Spring `MessageSource` to resolve messages for a `Locale`.

Suppose the code is:

```java
errors.reject("order.invalidTotal", "Order total is invalid");
errors.rejectValue("quantity", "quantity.nonPositive",
                   "Quantity must be greater than 0");
```

With `objectName="order"` and `field="quantity"` of type `Integer`, `DefaultMessageCodesResolver` **typically** generates the priority list:

```text
Global error:
  order.invalidTotal.order
  order.invalidTotal

Field error:
  quantity.nonPositive.order.quantity
  quantity.nonPositive.quantity
  quantity.nonPositive.java.lang.Integer
  quantity.nonPositive
```

The ordering can be affected by the configured `MessageCodesResolver` strategy, especially when using a prefix or a different formatter. For collection/map properties, the resolver can also generate codes for both the indexed element and the general field.

Example resource `src/main/resources/messages_vi.properties`:

```properties
order.invalidTotal.order=Tổng đơn hàng không nhất quán.
quantity.nonPositive.order.quantity=Số lượng phải lớn hơn 0.
typeMismatch.order.quantity=Số lượng phải là số.
```

In an application with an appropriate message bundle configured (e.g., Spring Boot configuring `spring.messages.basename=messages`), you can resolve the message:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.validation.FieldError;

FieldError error = errors.getFieldError("quantity");
if (error != null) {
    String message = messageSource.getMessage(
            error, Locale.forLanguageTag("vi"));
    System.out.println(message);
}
```

This snippet assumes `errors` and `messageSource` (injected by Spring) are already available in the method and is not a standalone class. Spring searches message keys from `error.getCodes()` in order and falls back to `defaultMessage` if no key matches. Which language the UI renders should come from the locale appropriate to the request/user, not a hardcoded `Locale` in a multilingual product.

**Distinguish `getDefaultMessage()` from a resolved message.** `getDefaultMessage()` does not consult `messages_vi.properties`. If you display it directly, configured translation keys are bypassed.

## 9. Common Practical Pitfalls

### 9.1. A single field with two errors

If a field both requires `@NotBlank` and must match a format, multiple messages can appear on the same field. `getFieldError("email")` retrieves only the first error. Use `getFieldErrors("email")` to receive all of them. Do not assume there is always exactly one error per field or that message ordering is fixed across providers/validators.

### 9.2. Type-conversion errors and rule errors mean different things

- Input `quantity=abc` on `Integer quantity`: this is a binding error; `isBindingFailure()` is typically `true` and the entered value is preserved in `getRejectedValue()`.
- Input `quantity=-2`, with `@Min(1)`: type conversion succeeded, but validation failed; `isBindingFailure()` is typically `false`.
- Input `quantity=5` but fields conflict with each other: the validator can record an `ObjectError` using `reject(...)` or a class-level Bean Validation constraint.

**Do not continue running business checks on a field that failed to bind cleanly** without checking errors or handling null/default values.

### 9.3. Nested field paths

For `address.zipCode`, `FieldError.getField()` can carry a path like `"address.zipCode"`. On forms with collections, the field may be `"lines[0].quantity"`. This name helps connect messages to inputs, but it must be mapped according to the UI contract—never interpolated directly into SQL or unchecked expressions.

Spring `Errors` also offers `pushNestedPath(...)`/`popNestedPath()` so child validators can create contextual errors. When writing a custom `Validator`, always restore the nested path in a `finally` block so subsequent errors do not inherit the wrong prefix.

### 9.4. Bean Validation does not only produce `FieldError`

Constraints placed on fields/properties usually lead to field errors. Class-level constraints can lead to global errors; custom validators can also route class-level constraint violations to a property by configuring the violation path. Therefore, rely on the **returned API lists** (`getFieldErrors()`/`getGlobalErrors()`) when rendering, rather than making rigid assumptions from the annotation type.

### 9.5. `FieldError` does not always hold a String rejected value

`getRejectedValue()` returns `Object`. For a form type mismatch, it may be the raw string; with Bean Validation, it may be the already-converted Java value (e.g., `Integer -2`); it can also be `null`. Handling code must not cast it to `String` without checking.

### 9.6. `BindingResult` must be in the right position

In an MVC controller:

```java
public String submit(
        @Valid @ModelAttribute("order") OrderForm form,
        BindingResult result) {
    // ...
}
```

This is the correct parameter order for the validated object. Inserting an unrelated parameter in between can prevent Spring from binding the corresponding `BindingResult`. This example shows only the method signature; it must be placed in a controller with a fully defined `OrderForm`.

### 9.7. Global errors and field errors are not HTTP statuses

`ObjectError` and `FieldError` **do not automatically decide** HTTP 400, 422, or any other status. They carry validation/binding details. The controller or exception handler decides how to translate the error collection into a response per the application's contract. Likewise, `@Valid` does not attach business semantics to a public error code by itself.

## 10. Testing and Debugging Errors

### Testing directly with `BindingResult`

A unit test using Spring APIs can construct `BeanPropertyBindingResult` to test a validator without starting a web server:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;

OrderForm form = new OrderForm(); // Project-defined DTO
BindingResult result =
        new BeanPropertyBindingResult(form, "order");

result.rejectValue("quantity", "quantity.positive",
                   "Quantity must be greater than 0");
result.reject("order.inconsistent",
              "Order is inconsistent");

// Corresponding assertions could be:
// result.hasErrors() == true
// result.getErrorCount() == 2
// result.getFieldErrorCount() == 1
// result.getGlobalErrorCount() == 1
```

This is a **snippet to place inside a test method**, requiring the project's `OrderForm` class. `DataBinder` is unnecessary if you only want to test error-registration logic; if you want to test `typeMismatch`, test through `DataBinder.bind(...)` as shown in the complete example in Section 5.

### Verification checklist

1. With invalid-type input, check that `getFieldError("quantity").isBindingFailure()` is `true` and the entered value is preserved.
2. With constraint errors, verify `FieldError` has the right field name and expected codes/message.
3. With cross-field rules, verify the error appears in `getGlobalErrors()` or on the specific field as decided by the validator.
4. Verify `getErrorCount() == getFieldErrorCount() + getGlobalErrorCount()` on the same `Errors` instance.
5. Test fields with multiple errors so the UI does not drop records after the first error.
6. Test localization via `MessageSource` with at least two `Locale` values if the application is multilingual.
7. Test the real MVC path with valid requests, failing field constraints, type-conversion errors, and global errors; confirm status/JSON matches the project's API.
8. Test logs and responses to ensure `getRejectedValue()` of passwords/tokens or protected data is never exposed.

In a debugger, inspect `errors.getAllErrors()` and expand each element to check its runtime type (`FieldError` vs `ObjectError`), `codes`, `defaultMessage`, `field`, `rejectedValue`, and `bindingFailure`. You do not have to guess the error source from the displayed message alone.

## 11. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `getAllErrors()` and treating every element as a global error | Field errors get misclassified | Use `getGlobalErrors()` and `getFieldErrors()` separately or `instanceof` |
| Using only `getFieldError()` | Drops remaining errors on the field | Use `getFieldErrors()` |
| Displaying only `getDefaultMessage()` | Bypasses locale translations | Resolve via `MessageSource` |
| Assuming `getRejectedValue()` is always a `String` | Invalid cast or data leak | Handle as `Object` and filter sensitive data |
| Interpreting `isBindingFailure() == false` as "no error" | Ignores validation errors | Still check `hasErrors()` and the error lists |
| Ignoring `getGlobalErrors()` | Users never see form-wide rule violations | Display general errors in a prominent spot |
| Placing `BindingResult` non-adjacent to the bound parameter | Binding/validation does not populate the result as expected | Order signature parameters properly |
| Assuming every `ObjectError` has no field | Overlooks the `FieldError` subclass | Keep the inheritance hierarchy in mind |
| Returning raw error objects in API responses | Couples to Spring internals and risks leaking data | Map to a public error DTO with stable codes |
| Handling all validation via `MethodArgumentNotValidException` | Misses method validation or WebFlux paths | Categorize by signature and actual stack |

## 12. Technical Summary

- **`ObjectError`** describes an object-level problem; it carries `objectName`, message codes, arguments, and a default message.
- **`FieldError`** extends `ObjectError` and adds `field`, `rejectedValue`, and `bindingFailure`; it targets a specific field.
- **`BindingResult`/`Errors`** holds and categorizes the error collection. `getGlobalErrors()` returns only object-level errors; `getFieldErrors()` returns only field-level errors; `getAllErrors()` returns both.
- **`reject(...)`** registers a global error; **`rejectValue(...)`** registers a field error; `DataBinder` can also automatically create field errors when binding fails.
- **`MessageSource`** resolves error codes into localized messages; `defaultMessage` is only a fallback, and public APIs should expose dedicated error codes.
- When handling real requests, check both global and field errors, guard against sensitive data in rejected values, and test both binding and validation.

## Official References

- [Spring Framework API — ObjectError](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework API — FieldError](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework API — Errors](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework API — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework API — DefaultMessageCodesResolver](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework Reference — Validation and Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation.html)
- [Spring Framework Reference — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
