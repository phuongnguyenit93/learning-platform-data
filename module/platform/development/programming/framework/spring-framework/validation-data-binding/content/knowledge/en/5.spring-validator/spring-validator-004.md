# ValidationUtils.rejectIfEmpty and rejectIfEmptyOrWhitespace in Spring Validator

When writing an `org.springframework.validation.Validator`, we often need to report an error if the user leaves a required field empty. Spring Framework provides two `static` utility methods in `org.springframework.validation.ValidationUtils`:

- `ValidationUtils.rejectIfEmpty(...)`: rejects `null` values or empty strings `""`.
- `ValidationUtils.rejectIfEmptyOrWhitespace(...)`: additionally rejects strings containing **only whitespace characters**, such as `"   "`, tabs, or newlines.

Both methods record an error for **a single field** into an `Errors` object; they do not return a `boolean`, do not throw a validation exception, do not alter data, and do not replace the full object validation workflow. They are simple yet very handy helpers for writing required-input rules in a Spring `Validator`.

## 1. Distinguishing the Two Methods Precisely

Suppose a form has a `String` field `name`. The table below evaluates the **exact same value** with each method:

| Value of `name` | Does `rejectIfEmpty` reject? | Does `rejectIfEmptyOrWhitespace` reject? | Reason |
| --- | :---: | :---: | --- |
| `null` | Yes | Yes | No value present |
| `""` | Yes | Yes | Zero-length string |
| `" "` | No | Yes | Has length, but only whitespace |
| `"   "` | No | Yes | Contains no content characters |
| `"\t\n"` | No | Yes | Only tab and newline |
| `" An "` | No | No | Contains letter characters |
| `"0"` | No | No | String contains character `0` |

**Quick choice:** if a text field must carry real content, usually use `rejectIfEmptyOrWhitespace`. `rejectIfEmpty` fits when you only want to forbid `null`/`""`, while whitespace-containing values have specific domain meaning or will be processed in another step.

With both helpers, the value `" An "` **is not trimmed**: they only check and register errors, without calling `strip()` or `trim()` to write back to the object.

### Internal Comparison Mechanism

Conceptually, the behavior is equivalent to:

~~~java
// Illustrates the condition; not the complete Spring source code.
Object value = errors.getFieldValue(field);

boolean empty = value == null
        || !org.springframework.util.StringUtils.hasLength(value.toString());

boolean emptyOrWhitespace = value == null
        || !org.springframework.util.StringUtils.hasText(value.toString());
~~~

- `hasLength` checks whether there is **at least one character**; `"   "` still has length.
- `hasText` checks whether there is **at least one non-whitespace character**.
- `Errors#getFieldValue(field)` retrieves the value through the binding/object metadata managed by `Errors`. Thus you only pass `Errors` and the field name; there is no need to pass the target object a second time.

In the actual implementation, when the condition fails, Spring calls `errors.rejectValue(field, errorCode, errorArgs, defaultMessage)`. Whitespace detection follows Java's `StringUtils.hasText` / `Character.isWhitespace` behavior; certain special Unicode characters such as **non-breaking space** are not necessarily treated as whitespace. If international data requires strict sanitization rules, define and test a dedicated Unicode policy.

## 2. Parameters and Overloads

Both method groups share the same primary overload signatures:

~~~java
ValidationUtils.rejectIfEmpty(errors, field, errorCode);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, defaultMessage);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, errorArgs);
ValidationUtils.rejectIfEmpty(errors, field, errorCode, errorArgs, defaultMessage);

ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, defaultMessage);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, errorArgs);
ValidationUtils.rejectIfEmptyOrWhitespace(errors, field, errorCode, errorArgs, defaultMessage);
~~~

These are **illustrative call forms**, where `errors` is `Errors`, `field` and `errorCode` are `String`, `defaultMessage` is `String`, and `errorArgs` is `Object[]`. They are not a complete Java program.

| Parameter | Purpose | Example |
| --- | --- | --- |
| `Errors errors` | Where Spring records field errors | `errors` passed into `Validator#validate` |
| `String field` | Property name to check, following the object's field path | `"name"`, `"address.street"` |
| `String errorCode` | Error code for categorization or message lookup | `"required"`, `"name.blank"` |
| `Object[] errorArgs` | Arguments for formatted messages | `new Object[]{"Full name"}` |
| `String defaultMessage` | Fallback message if the error code is not resolved | `"Full name must not be blank"` |

Example of two practical calls inside `validate`:

~~~java
ValidationUtils.rejectIfEmpty(
        errors, "referenceCode", "referenceCode.empty");

ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "displayName", "displayName.required",
        "Display name must not be blank");
~~~

**Note on overloads:** the fourth parameter has both `String` and `Object[]` variants. Writing `rejectIfEmpty(errors, "name", "required", null)` can trigger an **ambiguous method call** error in Java because `null` matches both overloads. Omit the fourth argument, cast explicitly, or use the five-argument overload if truly needed.

`errorCode` is not directly the user-facing message string. Spring can expand this code into more specific codes based on object/field names and look them up via `MessageSource`; `defaultMessage` is merely a fallback.

## 3. Runnable Java 17+ Example: Same Value, Two Different Outcomes

The following example uses **plain Spring Framework**, requiring neither Spring Boot nor a web server. We define a JavaBean `InputForm` with two fields:

- `referenceCode` uses `rejectIfEmpty`, allowing whitespace-only strings.
- `displayName` uses `rejectIfEmptyOrWhitespace`, requiring at least one content character.

To reproduce the difference clearly, each check assigns **the exact same test value** to both fields.

### 3.1. Maven Dependency

Create a Maven project with `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>validation-utils-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
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

Version `6.2.5` is **pinned for reproducibility**, without implying it is the latest Spring release. `spring-context` includes the needed validation classes and pulls in transitive Spring dependencies. The example does not need `jakarta.validation-api` or Hibernate Validator because it uses the plain `org.springframework.validation.Validator` interface.

### 3.2. Program Code

Save at the exact path `src/main/java/example/ValidationUtilsDemo.java`:

~~~java
package example;

import java.util.stream.Collectors;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationUtilsDemo {

    // JavaBean: BeanPropertyBindingResult reads values via getters.
    public static class InputForm {
        private String referenceCode;
        private String displayName;

        public InputForm(String referenceCode, String displayName) {
            this.referenceCode = referenceCode;
            this.displayName = displayName;
        }

        public String getReferenceCode() {
            return referenceCode;
        }

        public void setReferenceCode(String referenceCode) {
            this.referenceCode = referenceCode;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }

    public static class InputFormValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return InputForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmpty(
                    errors, "referenceCode", "referenceCode.empty");

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "displayName", "displayName.blank");
        }
    }

    private static void check(String label, String value) {
        InputForm form = new InputForm(value, value);
        BindingResult errors =
                new BeanPropertyBindingResult(form, "inputForm");

        new InputFormValidator().validate(form, errors);

        String errorSummary = errors.getFieldErrors().stream()
                .map(error -> error.getField() + "=" + error.getCode())
                .collect(Collectors.joining(", "));

        System.out.println(label + " -> " +
                (errorSummary.isEmpty() ? "OK" : errorSummary));
    }

    public static void main(String[] args) {
        check("null", null);
        check("empty", "");
        check("spaces", " \t ");
        check("text", " An ");
    }
}
~~~

`FieldError` is created and held by Spring in `BindingResult`; here `getCode()` returns the original error code passed to `rejectValue`. The `target` parameter in `validate` is the object to inspect; the helpers read property values through `Errors`, so there is no need to cast `target` yourself for those two checks.

**Directory structure:**

~~~text
validation-utils-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ValidationUtilsDemo.java
~~~

### 3.3. Compile and Run

Install JDK 17+ and Maven, then in the directory containing `pom.xml` run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.ValidationUtilsDemo
~~~

**Stdout printed by the program**, when the program and dependencies run normally:

~~~text
null -> referenceCode=referenceCode.empty, displayName=displayName.blank
empty -> referenceCode=referenceCode.empty, displayName=displayName.blank
spaces -> displayName=displayName.blank
text -> OK
~~~

Case-by-case explanation:

1. `null`: neither field has a value, so both helpers register errors.
2. `""`: zero-length string, so both helpers register errors.
3. `" \t "`: the string has characters (length > 0), so `rejectIfEmpty` does **not** report an error; all characters are spaces/tabs, so `rejectIfEmptyOrWhitespace` reports an error for `displayName`.
4. `" An "`: the string contains letters, so both helpers accept it; they **do not** trim leading or trailing whitespace.

If running on Windows, the Maven command is still `mvn -q compile exec:java -Dexec.mainClass=example.ValidationUtilsDemo` in Command Prompt/PowerShell once Maven is on PATH. Maven logging output may vary; the four lines above are the output produced by `System.out.println`.

## 4. Why Are Errors and BindingResult Needed?

`ValidationUtils` **does not know** which object you want to inspect from just a field name. The `Errors` object already holds the context, object name, and property access capability.

In the example:

~~~java
InputForm form = new InputForm("", "  ");
BindingResult errors = new BeanPropertyBindingResult(form, "inputForm");
new InputFormValidator().validate(form, errors);

boolean failed = errors.hasErrors(); // true
int fieldErrorCount = errors.getFieldErrorCount(); // 2
~~~

`BeanPropertyBindingResult` works for objects following JavaBean conventions with readable properties. `BindingResult` extends `Errors` and adds binding-specific metadata. The `Errors` interface provides essential operations:

- `errors.rejectValue("name", "required")`: directly registers an error on a field.
- `errors.reject("form.invalid")`: registers an error at the object-wide level.
- `errors.hasErrors()`: checks whether any error exists.
- `errors.getFieldErrors()` / `getFieldError("name")`: inspects errors per field.
- `errors.getFieldValue("name")`: reads the field value within the binding context.

Both helpers act much like an `if` statement followed by `errors.rejectValue(...)`. They **do not return errors** to the caller; the caller reads them from `Errors`/`BindingResult` afterward.

### Field Errors vs. Object Errors

If `name` is left blank, the error should be attached to the `name` field so the UI displays it next to the input box. If a condition involves **multiple fields at once**, such as `startDate` must precede `endDate`, you can use `errors.reject(...)` to create an object-wide error or choose an appropriate field to attach it to. Do not force complex business rules into these two emptiness helpers.

## 5. Using Them in a Spring Validator

Common pattern:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "email", "email.required");

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "fullName", "fullName.required");

        RegistrationForm form = (RegistrationForm) target;

        // Only validate format when email actually has content.
        if (form.getEmail() != null
                && !form.getEmail().isBlank()
                && !form.getEmail().contains("@")) {
            errors.rejectValue("email", "email.invalid");
        }
    }
}
~~~

This is an **illustrative code snippet in a Spring application**, requiring a `RegistrationForm` class with `email` and `fullName` properties along with the appropriate imports/dependencies. It cannot run standalone like the program in section 3.

`supports(Class<?>)` declares which object types the validator handles; `validate(Object, Errors)` applies rules and records errors. The `contains("@")` check above only illustrates how to **avoid reporting duplicate format errors when a field is already empty**, not a complete email validation algorithm.

The benefit of extracting a `RegistrationValidator`: controllers and services can reuse rules, test without HTTP, and avoid repeating `if (name == null || ...)` checks across multiple places.

### Integrating with Spring MVC

When using Spring MVC, a controller can register a custom validator via `@InitBinder` and request validation when binding a `@ModelAttribute`:

~~~java
// Snippet inside a @Controller; requires RegistrationForm,
// RegistrationValidator, annotation imports, and MVC configuration.
@InitBinder("registrationForm")
void initRegistrationBinder(WebDataBinder binder) {
    binder.addValidators(new RegistrationValidator());
}

@PostMapping("/register")
String register(
        @Validated @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

In Spring MVC, `@Validated` (or an appropriate validation annotation) signals the binder to execute configured validation; `BindingResult` is placed **immediately after** the model attribute to read errors. `ValidationUtils` runs only when the code inside the custom validator is actually invoked. Simply having a class implementing `Validator` in the source **does not mean** every request will be validated automatically.

Distinguish clearly:

1. **Data binding:** transferring HTTP parameters into Java objects.
2. **Spring Validator:** validating the object, e.g., with the two `ValidationUtils` methods.
3. **Displaying errors:** reading `BindingResult` and informing the user.

A type conversion error during binding can also be stored in `BindingResult`. Do not confuse that kind of error with “required/blank” errors created by `ValidationUtils`.

## 6. Customizing errorCode, Messages, and Internationalization

Both helpers accept `errorCode` to **classify the error**, not to print raw text directly. Example:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "fullName", "required",
        new Object[]{"Full name"},
        "{0} must not be blank");
~~~

Here `"required"` is the error code; `errorArgs` supplies values to interpolate via `MessageFormat`; `defaultMessage` is the fallback string. When using `MessageSource` in Spring MVC, you can provide a `messages.properties` file such as:

~~~properties
required.registrationForm.fullName=Please enter your full name
required.fullName=Full name is required
required=This field must not be blank
~~~

These keys are examples of **message codes** that can be generated from code `required`, object name `registrationForm`, and field name `fullName` by Spring's `MessageCodesResolver`. Priority and exact generated codes depend on resolver configuration; `messages.properties` is not read directly by `ValidationUtils` on its own. The presentation layer or `MessageSource` looks up the error codes to determine the message text.

Use consistent error codes (`required`, `invalid.email`, `range.exceeded`...), reserve prose for user-facing messages, and avoid using display text as business error codes.

## 7. Nested Fields and Nested Paths

Given a JavaBean:

~~~text
Customer
  ├── name
  └── address
       └── street
~~~

If `Customer` has `Address`, you can check the nested property name:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "address.street", "street.required");
~~~

Spring can read this field path if the property chain is compatible and the nested value is accessible.

When reusing an `AddressValidator`, you can manage the nested path:

~~~java
errors.pushNestedPath("address");
try {
    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "street", "street.required");
} finally {
    errors.popNestedPath();
}
~~~

Then the error is attached to field `address.street`; the `finally` block ensures the context is restored even if validation fails. **The property path must exist**, and the nested object may need to be initialized or supported by the binder. If `address` is `null` and the configuration cannot traverse child fields, the helpers will not unconditionally instantiate the entire object tree.

To check the `address == null` condition as a whole, you can use `errors.rejectValue("address", "address.required")` or a more appropriate validation rule.

## 8. Do Not Confuse with @NotEmpty, @NotBlank, and jakarta.validation

In projects using Jakarta Bean Validation and a provider like Hibernate Validator, the annotations are:

- `@NotNull`: disallows `null`, but still accepts `""` for strings.
- `@NotEmpty`: disallows `null` or empty strings/collections/arrays/maps; for `String`, `"   "` is still accepted.
- `@NotBlank`: applies to `CharSequence`, requiring non-whitespace content; closest to `rejectIfEmptyOrWhitespace` for text fields.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;

public class RegistrationForm {
    @NotBlank
    private String fullName;
    // Getters, setters, and other fields...
}
~~~

This is an **incomplete class skeleton**; a Jakarta Validation provider is required for constraints to be enforced in an integrated runtime.

| Need | Commonly Suitable Choice |
| --- | --- |
| Plain Spring custom validator, string field must not be `null`/`""` | `ValidationUtils.rejectIfEmpty` |
| Plain Spring custom validator, field must contain non-whitespace text | `ValidationUtils.rejectIfEmptyOrWhitespace` |
| DTO using Jakarta Bean Validation to declare constraints | `@NotBlank` or `@NotEmpty`, depending on type and rule |
| List must contain elements | `@NotEmpty` or dedicated collection validation |
| Number must be greater than 0 | `@Positive`, `@Min(1)`, or numeric range validator |
| Cross-field conditions | Custom `Validator`, custom constraint, or business validation |

Key difference: `ValidationUtils` uses **Spring `Errors`** and works independently of any Jakarta Bean Validation provider; annotations like `@NotBlank` must be executed by a suitable validation system. Within the same application, both approaches can coexist.

## 9. Common Mistakes and Edge Cases

### Confusing “empty” with “blank”

~~~java
ValidationUtils.rejectIfEmpty(errors, "name", "required");
~~~

If `name = "   "`, this statement **does not report an error**. When data represents names, titles, addresses, or passwords where whitespace-only values must be prevented, consider `rejectIfEmptyOrWhitespace` with an appropriate normalization policy.

### Assuming the Helpers Trim Data Automatically

With `name = " Lan "`, both helpers accept it, and the object still retains `" Lan "`. If business rules require stripping whitespace, define a **separate normalization step** (for example on the DTO, binder, or in a service) and decide clearly when normalization occurs. Avoid arbitrarily trimming passwords or fields where spaces are meaningful.

### Applying to Numbers, Booleans, Lists, or Arrays

Both helpers call `value.toString()` for non-null values. For example:

- `Integer.valueOf(0)` -> `"0"`: **not** considered empty.
- `Boolean.FALSE` -> `"false"`: **not** considered empty.
- `new ArrayList<>()` -> `"[]"`: **not** considered empty.

Therefore, they are primarily useful for **text fields**. To verify a list/array/map is non-empty, inspect the structure directly or use `@NotEmpty`; to validate numbers, use range constraints or validators. With primitives like `int`, the default value `0` also cannot represent `null`.

### Incorrect Property Path

If a DTO only has `getFullName()` while you check `"name"`, `Errors` may fail to access the property and throw an exception when reading the field. Ensure field names match JavaBean conventions or the configured binding mechanism; do not expect the helpers to map differing JSON property names automatically.

### Recording Errors and Continuing as If Valid

The helpers return `void`. After running the validator, you must inspect `errors.hasErrors()` or `result.hasFieldErrors("name")` and decide to return the form, respond with 400, or halt business processing. Ignoring `BindingResult` leaves the service unprotected against invalid input even though errors were recorded.

### Invoking Validation Multiple Times

Each time the emptiness condition holds and the helper is called, it can **register another** `FieldError`. Do not assume Spring deduplicates errors automatically; design your flow to avoid redundant validation passes and avoid checking the same condition in multiple places without reason.

### Unicode Whitespace and Normalization

`StringUtils.hasText` uses Java's whitespace definition. Characters that “look like spaces” do not always behave identically to ASCII spaces or tabs, and Unicode normalization differences can matter for international data. Add dedicated tests for special characters if business rules require it; do not claim the helpers catch every invisible character.

### Treating errorCode as the Final Message

`"name.blank"` is a programmatic error code. If an API needs to return Vietnamese or other localized messages, integrate `MessageSource` and process `FieldError` in the presentation layer; do not assume `getCode()` is user-ready text.

## 10. Project Usage Checklist

1. Confirm the field is a **string**, and whether the rule forbids `null`/empty or whitespace-only as well.
2. Specify the exact property name in `field`, matching getters or binder configuration.
3. Choose stable `errorCode` values for easy message mapping and testing.
4. Implement `Validator#supports` and `validate` for the right target; actually call the validator or register it with the binder.
5. After validation, handle `BindingResult`/`Errors`; in MVC, place `BindingResult` right after the corresponding model attribute.
6. Test `null`, `""`, `" "`, `"\t"`, `"a"`, `" a "`, and business-relevant Unicode characters.
7. Do not use these two helpers to replace length, format, numeric, collection, or authorization checks.

### Self-Check Questions

1. Why does `rejectIfEmpty` allow `"   "` while `rejectIfEmptyOrWhitespace` rejects it?
2. Inside `validate(Object, Errors)`, why do the helpers not need a `target` parameter?
3. For `InputForm(referenceCode=" ", displayName=" ")`, how many errors do the two helpers in the example produce, and on which fields?
4. If you call `ValidationUtils.rejectIfEmpty(errors, "age", "required")` when `age` is an `int` equal to `0`, what happens and what should you use instead?
5. How do you display a Vietnamese message when you only have the error code `"displayName.blank"`?

**Key takeaway:** `rejectIfEmpty` checks for **no characters**; `rejectIfEmptyOrWhitespace` checks for **no non-whitespace characters**. Both are concise ways to add a `FieldError` to Spring `Errors`, while error-handling logic remains the responsibility of the validator/controller.

## Official Documentation

- Spring Framework Reference — Validation using Spring's Validator Interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Javadoc — ValidationUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ValidationUtils.html
- Spring Framework Javadoc — Errors: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html
- Spring Framework Javadoc — BeanPropertyBindingResult: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html
- Spring Framework Javadoc — StringUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/StringUtils.html
- Spring Framework source — ValidationUtils.java: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/validation/ValidationUtils.java