# Rejected Value, Field Value, and Field Type in Spring Errors

When Spring Framework binds input data to a Java object, **the value the user just submitted may differ from the value currently stored in the object**. This is especially important when type conversion fails: a form submits `age=abc`, the Java property `age` has type `Integer` and previously held `21`. Spring cannot assign the string `"abc"` to this property, yet it still needs to remember what the user entered in order to display errors.

The `org.springframework.validation.Errors` API group lets you access **the field value** and **field type**; `FieldError` stores **the rejected value** attached to a specific error. Combining them with `BindingResult` lets you handle messages properly, preserve form input, and avoid mistakenly using an invalid value in business logic.

This article focuses on these methods:

- `Errors.getFieldValue(String field)`: a value suitable for the field's error-reporting/form context; it may be the rejected value instead of the value bound onto the object.
- `Errors.getFieldType(String field)`: the Java type of the field as determined by Spring; returns `Class<?>` or `null`.
- `FieldError.getRejectedValue()`: the rejected value for **a specific field error**.
- `FieldError.isBindingFailure()`: whether the error relates to binding (such as a type mismatch) or validation.
- `BindingResult.getRawFieldValue(String field)`: the current raw field value on the target object, in common binding implementations.

## 1. Three Things to Distinguish

Suppose the initial Java object is:

~~~java
public class ProfileForm {
    private Integer age = 21;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

The user submits the text value `age=abc`. A `DataBinder` using bean-property binding attempts to convert `"abc"` to `Integer` and fails. Information after a typical binding pass:

| Question | API / location | Result in example |
|---|---|---|
| What did the user enter that failed to convert? | `getFieldError("age").getRejectedValue()` | `"abc"` (`String`) |
| What value should be put back into the form field on error? | `errors.getFieldValue("age")` | `"abc"` |
| What actual value is currently in the Java property? | `form.getAge()` | `21` |
| What raw value does `BindingResult` read from the target? | `result.getRawFieldValue("age")` | `21` |
| What is the declared type for property `age`? | `errors.getFieldType("age")` | `Integer.class` |
| Is this a binding error? | `fieldError.isBindingFailure()` | `true` |
| Are there errors for this field? | `errors.hasFieldErrors("age")` | `true` |

**Core takeaway:** `"abc"` is the string the user submitted that could not convert to `Integer`; it never becomes the target's `age` value. `getFieldType("age")` describes **the target field's type**, not the runtime type of the rejected value. Likewise, `getRawFieldValue` is not another name for "HTTP raw input".

## 2. What Does Each API Return?

### 2.1. `Errors.getFieldValue(field)`

Conceptual API call:

~~~java
Object value = errors.getFieldValue("age");
~~~

Under the `Errors` contract, this method returns the current value associated with the field: either the bean property value, or a submitted value rejected during a binding pass. That allows a form to re-display what the user entered even when a `typeMismatch` occurs.

Keep in mind:

- If there is **no binding error** on the field, the value usually comes from the bound property. For some types and `PropertyEditor`/`Formatter` configurations, the value may already be formatted for display.
- If a `FieldError` exists due to a binding failure, Spring can prioritize the rejected value to preserve the unparsed input.
- The return type is `Object`, with no guarantee it is always a `String`, `Integer`, or any specific type. Check the value's type or use a suitable formatter before processing it.
- A nonexistent field, an uninstantiated target, or an empty value can yield `null` depending on the implementation/context. Never infer "no errors" solely from `getFieldValue(field) == null`.

`getFieldValue` is a **state-observation API for error reporting and form input**, not a promise that the returned value has passed all validation.

### 2.2. `Errors.getFieldType(field)`

~~~java
Class<?> type = errors.getFieldType("age");
~~~

This API attempts to determine **the property's Java type**, such as `Integer.class`, `String.class`, `LocalDate.class`, `BigDecimal.class`, or `int.class`, depending on the declaration. In bean-property binding, Spring can usually read the property type from getters/setters and metadata even when the current value is `null`.

Example:

~~~java
Class<?> ageType = errors.getFieldType("age");
if (ageType != null) {
    System.out.println(ageType.getName()); // java.lang.Integer
}
~~~

Essential notes:

- `Integer.class` is the expected type of field `age`; it does not turn `"abc"` into an `Integer`.
- For a field declared as `int`, the result can be `int.class` and `getName()` is `"int"`, not `"java.lang.Integer"`.
- A `null` from `getFieldType` means **Spring could not determine the type**, not that the field has type `null`.
- Different `Errors` implementations vary in their type-inference support; do not assume every `Errors` is backed by a JavaBean with full type descriptors.
- Never rely on a client-supplied Java type name to decide parsing or authorization. Type names from server metadata are supporting info, not an input-validation guarantee.

### 2.3. `FieldError.getRejectedValue()`

~~~java
FieldError ageError = errors.getFieldError("age");
if (ageError != null) {
    Object rejected = ageError.getRejectedValue();
}
~~~

`FieldError` represents **a single error on a single field**. It holds the field name (`getField()`), error codes (`getCode()` / `getCodes()`), message (`getDefaultMessage()`), rejected value, and binding-failure flag.

The rejected value **is not necessarily the original HTTP string**:

- For a type-conversion failure from `age=abc` to `Integer`, the rejected value is typically `"abc"` (the unconvertible string).
- For a validation error "minimum age is 18" after `age=16` already converted to `Integer`, the rejected value can be `Integer.valueOf(16)` itself.
- When a field is missing or an empty value is converted to `null`, `getRejectedValue()` can be `null`. That **does not by itself distinguish** a missing field, an explicit null, or a rule violation.
- A field can have multiple `FieldError` records; `getFieldError("age")` returns only the first. To handle all of them, use `getFieldErrors("age")`.

The `isBindingFailure()` flag distinguishes the error kind:

~~~java
if (ageError.isBindingFailure()) {
    // Example: conversion or property-assignment failure.
} else {
    // Example: validator rejected a successfully converted value.
}
~~~

Do not assume every `FieldError` is a type-conversion error, and do not assume `getRejectedValue()` is only present when `isBindingFailure() == true`.

### 2.4. `BindingResult.getRawFieldValue(field)`

`BindingResult` extends `Errors` and exposes richer binding details:

~~~java
BindingResult result = binder.getBindingResult();
Object rawTargetValue = result.getRawFieldValue("age");
~~~

This method fetches **the raw field value according to the binding result**, typically reading the property currently held on the target directly without formatting for form display. Therefore, when `age=abc` fails to bind and the target still holds 21, `getRawFieldValue("age")` returns 21 in the JavaBean example below.

The word "raw" here **does not mean** "verbatim HTTP request bytes". If you need to inspect the original request, rely on web-layer data and appropriate processing rules; never use `getRawFieldValue` as proof of what the client just sent.

## 3. Flow When Binding Fails vs. When Validation Fails

~~~text
                  Input data
                      |
                      v
              Spring DataBinder
                      |
             Attempt type conversion
                      |
        +-------------+--------------+
        |                            |
     Success                      Failure
        |                            |
  Assign to target            Cannot assign
        |                            |
  Can validate               Record FieldError
        |                            |
  Validator may               rejectedValue = input
  rejectValue(...)                   |
        |                            |
  FieldError usually          bindingFailure = true
  bindingFailure = false             |
        |                            |
        +-------------+--------------+
                      |
                      v
           Errors / BindingResult
                      |
       +--------------+---------------+
       |              |               |
 getFieldValue  getFieldType   getFieldError
 form display   expected type  rejectedValue
~~~

In a typical property-binding pass, a type-conversion failure is handled by Spring as a `FieldError` so the application can report it. Other fields may still bind successfully. However, **a partially bound target is not valid data for persistence**.

Validation runs after bindable values are placed on the object, depending on how the controller or binder is configured. A validation error's rejected value is **the successfully converted value**. This differs from catching a mistyped value before assignment.

## 4. Runnable Example with Java 17 and Spring Framework

The following example runs two separate binding passes for comparison:

1. `age="abc"`: cannot convert to `Integer`, producing a binding error.
2. `age="16"`: converts to `Integer.valueOf(16)` successfully but is rejected by a minimum-age rule via `rejectValue`.

The small project uses Maven to fetch consistent Spring dependencies. Layout:

~~~text
field-errors-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FieldValuesDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>field-errors-demo</artifactId>
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
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the validation/binding APIs in this example along with required transitive dependencies. No Spring Boot, HTTP server, or database is needed to run this program.

**File `src/main/java/demo/FieldValuesDemo.java`:**

~~~java
package demo;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;

public final class FieldValuesDemo {

    public static final class ProfileForm {
        private String name;
        private Integer age = 21;
        private String city;
        private String nickname;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getNickname() {
            return nickname;
        }

        public void setNickname(String nickname) {
            this.nickname = nickname;
        }
    }

    public static void main(String[] args) {
        conversionFailure();
        validationFailure();
    }

    private static void conversionFailure() {
        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profile");
        binder.setAllowedFields("name", "age", "city", "nickname");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("age", "abc");
        input.add("city", "Hue");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        Errors errors = result;

        FieldError error = result.getFieldError("age");
        if (error == null) {
            throw new AssertionError("Expected a type mismatch for age");
        }

        System.out.println("target.name=" + target.getName());
        System.out.println("target.age=" + target.getAge());
        System.out.println("target.city=" + target.getCity());
        System.out.println("age.hasError=" + errors.hasFieldErrors("age"));
        System.out.println("age.code=" + error.getCode());
        System.out.println("age.rejected=" + error.getRejectedValue());
        System.out.println("age.bindingFailure=" + error.isBindingFailure());
        System.out.println("age.fieldValue=" + errors.getFieldValue("age"));
        System.out.println("age.fieldType="
                + errors.getFieldType("age").getName());
        System.out.println("age.rawTargetValue="
                + result.getRawFieldValue("age"));
        System.out.println("city.fieldValue=" + errors.getFieldValue("city"));
        System.out.println("nickname.fieldValue="
                + errors.getFieldValue("nickname"));
        System.out.println("nickname.fieldType="
                + errors.getFieldType("nickname").getName());
    }

    private static void validationFailure() {
        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profile");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("age", "16");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        if (target.getAge() != null && target.getAge() < 18) {
            // Simulate an application validation rule.
            result.rejectValue("age", "age.minimum",
                    "Age must be at least 18");
        }

        FieldError error = result.getFieldError("age");
        if (error == null) {
            throw new AssertionError("Expected validation error for age");
        }

        System.out.println("validated.targetAge=" + target.getAge());
        System.out.println("validated.rejected=" + error.getRejectedValue());
        System.out.println("validated.rejectedType="
                + error.getRejectedValue().getClass().getName());
        System.out.println("validated.bindingFailure="
                + error.isBindingFailure());
        System.out.println("validated.fieldType="
                + result.getFieldType("age").getName());
    }
}
~~~

**Run with JDK 17+ and Maven 3.9+:**

~~~bash
cd field-errors-demo
mvn -q compile exec:java -Dexec.mainClass=demo.FieldValuesDemo
~~~

**Program stdout** with Spring Framework 6.2.12 and default binder configuration:

~~~text
target.name=Lan
target.age=21
target.city=Hue
age.hasError=true
age.code=typeMismatch
age.rejected=abc
age.bindingFailure=true
age.fieldValue=abc
age.fieldType=java.lang.Integer
age.rawTargetValue=21
city.fieldValue=Hue
nickname.fieldValue=null
nickname.fieldType=java.lang.String
validated.targetAge=16
validated.rejected=16
validated.rejectedType=java.lang.Integer
validated.bindingFailure=false
validated.fieldType=java.lang.Integer
~~~

Maven `-q` reduces build logs; the listing above shows **lines printed by the Java code**, without promising every environment suppresses extra Maven/JVM output.

**Explaining the binding failure:** `age="abc"` produces a `FieldError` with code `typeMismatch`. Because the setter never received a valid value, `target.age` remains 21. `Errors.getFieldValue("age")` preserves `"abc"` for re-rendering in the form, while `BindingResult.getRawFieldValue("age")` shows the actual target value 21. `getFieldType("age")` remains `Integer.class`. Fields `name` and `city` bind successfully.

**Explaining the validation failure:** the string `"16"` is converted to `Integer(16)` and assigned successfully. The minimum-age rule then calls `rejectValue`; `FieldError` has rejected value `Integer(16)` and `isBindingFailure() == false`. Therefore, you cannot conclude "the rejected value is always an unconvertible string".

**Note:** the `age.minimum` code in the example is an application-defined code; `typeMismatch` comes from Spring's standard conversion-error reporting. Do not assume all error codes or message contents stay fixed when changing converters, validators, or message-code configuration.

## 5. When a Field Has No Error, Has an Error, or Has No Value

Depending on the binding mechanism and formatters, `getFieldValue(field)` and `getRejectedValue()` may differ or represent the same value. Look at these cases:

| Input and condition | Target after binding | `getFieldValue` | `getRejectedValue` |
|---|---|---|---|
| `name=Lan`, valid | `"Lan"` | Usually `"Lan"` | No `FieldError` to call |
| `age=abc`, property `Integer age=21` | Still `21` | Usually `"abc"` | `"abc"` on the binding error |
| `age=16` then validator rejects age under 18 | `16` | Usually value `16` (possibly formatted) | `Integer(16)` on the validation error |
| `nickname` omitted, property `String nickname=null` | `null` | Usually `null` | No error if not required |
| Invalid value while initial target was also `null` | May stay `null` | May be the rejected input | Depends on value recorded on the error |

With many formatters or editors, `getFieldValue` serves a representation different from the property's stored value. For example, monetary or date values can be formatted per locale; **do not rely on `String.valueOf(getFieldValue(...))` to reconstruct a canonical value for database storage**.

A frequent source of confusion: **having no `FieldError`** and **`FieldError.getRejectedValue() == null`** are not the same. Before reading a rejected value, check that the `FieldError` object actually exists.

## 6. Spring MVC: Reading Values from BindingResult

In a controller handling forms or query parameters with `@ModelAttribute`, Spring MVC binds into the object and collects errors in `BindingResult`. Below is **integration code inside a Spring MVC project**, not a standalone runnable class; it assumes `ProfileForm` has the declared properties and a view named `profile/form` exists.

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class ProfileController {

    @PostMapping("/profiles")
    String submit(
            @Valid @ModelAttribute("profile") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            Errors errors = result;
            FieldError ageError = errors.getFieldError("age");

            if (ageError != null) {
                Object entered = errors.getFieldValue("age");
                Object rejected = ageError.getRejectedValue();
                Class<?> expectedType = errors.getFieldType("age");

                // Convert errors into safe messages for the view.
                // Never print raw rejected values into logs or HTML.
            }

            return "profile/form";
        }

        // Only run business logic when no binding/validation errors remain.
        return "profile/success";
    }
}
~~~

Place `BindingResult` **immediately after** the `@ModelAttribute` object it describes. With `@Valid`, Bean Validation can add errors into the same result. The form object may contain several fields that bound successfully, so always check `result.hasErrors()` before saving or invoking state-changing logic.

**Mechanism distinction:** For JSON `@RequestBody`, Spring uses an `HttpMessageConverter` (typically Jackson-based) to read data. Malformed or undeserializable JSON can raise an exception before a `BindingResult` exists in the style above. Never assume every JSON conversion failure becomes a `@ModelAttribute` `FieldError`; handle HTTP message conversion exceptions with an appropriate mechanism such as `@RestControllerAdvice`.

### Safely rendering form data

The goal is usually to preserve what the user entered after an error:

~~~text
Age: abc
Error: Age must be a valid integer.
Name: Lan
City: Hue
~~~

Do not blindly take `form.getAge()` (which may still be 21) to overwrite the invalid input when re-rendering the form. Spring-integrated view libraries can use `BindingResult` to pick the appropriate value. If building HTML/JSON manually, map explicitly, escape content for the output context, and return only information the caller is authorized to see.

## 7. Iterating Errors and Avoiding Confusion with Multiple Errors on One Field

Use `getFieldError("age")` when you only need the first error; use `getFieldErrors("age")` if you want to handle every error on `age`:

~~~java
for (FieldError error : result.getFieldErrors("age")) {
    String field = error.getField();
    String code = error.getCode();
    boolean bindingFailure = error.isBindingFailure();

    // These values help choose an application-defined message.
    // error.getRejectedValue() may be null or sensitive data.
}
~~~

Error codes can be passed to `MessageSource` to produce locale-appropriate text:

- `typeMismatch`: "Value is not in the required format."
- `age.minimum`: "Age must be at least 18."
- `NotNull`: "Please enter a value."
- More specific codes such as `typeMismatch.profile.age` may appear in the code list generated by `MessageCodesResolver`, depending on configuration.

**The messages above are application-defined examples**, not fixed translations Spring generates across all setups. `FieldError.getCode()` is typically the most general code; `getCodes()` provides the candidate list for message resolution. Never parse exception message strings to drive business decisions.

If a field has multiple errors, do not assume the first error is always the most important one. Choose a clear message-priority policy (for example, when type conversion fails, do not ask the user to satisfy additional numeric bounds on the unparsed value). The validation flow should also avoid adding noisy messages to a field already suffering from a binding failure.

## 8. Nested Fields, Primitives, and Null Values

### 8.1. Nested field paths

Spring uses field names like `address.zipCode` or `items[0].price` depending on structure and binding configuration:

~~~java
FieldError nestedError = result.getFieldError("address.zipCode");
if (nestedError != null) {
    Object rejected = nestedError.getRejectedValue();
    Class<?> expected = result.getFieldType("address.zipCode");
}
~~~

Type resolution depends on whether Spring can access the metadata/property path. For invalid paths, nonexistent properties, or unreadable nested structures, the result can be `null` or fail depending on context; there is no guarantee `getFieldType` resolves every arbitrary path.

### 8.2. `int` vs `Integer`

~~~java
private int primitiveAge;
private Integer boxedAge;
~~~

`primitiveAge` defaults to 0; `boxedAge` can be `null`. `getFieldType("primitiveAge")` can return `int.class`, while `getFieldType("boxedAge")` returns `Integer.class`. Both can reject `"abc"`, yet the target state when assignment fails differs.

Do not use a default 0 to conclude the client definitely submitted 0. When validation needs to distinguish missing input from 0, `Integer` with `@NotNull` is commonly used on request DTOs.

### 8.3. A field with a null value can still have a type

If `nickname == null` while the property is declared `String nickname`, bean-property binding can still return `String.class` via metadata. Hence:

~~~java
Object value = result.getFieldValue("nickname");       // may be null
Class<?> type = result.getFieldType("nickname");       // may be String.class
~~~

`value == null` does not imply `type == null`. When building messages, also distinguish a rejected `null` value from having no field error at all.

## 9. Common Mistakes

**Mistake 1 — using the rejected value as validated data.** `getRejectedValue()` is stored to explain errors, not to bypass type conversion. Use data only after binding, validation, and business checks all succeed.

**Mistake 2 — assuming `getFieldValue` always calls the entity's getter directly.** When a binding failure exists, the API may return the rejected input for form rendering. Read the target via getters or `getRawFieldValue` if you genuinely want the current bean state.

**Mistake 3 — assuming `getRawFieldValue` is the original request value.** It is an API that reads the raw field value per the binding result; in a type-mismatch case it may simply be the target's old value.

**Mistake 4 — casting `getFieldValue("age")` to `Integer`.** When `age=abc`, the method can return a `String`. `(Integer) result.getFieldValue("age")` will then throw `ClassCastException`. Rely on `getFieldType` to know the target type, not to prove the returned value already has that type.

**Mistake 5 — reading `getRejectedValue()` without checking that `FieldError` exists.** For a valid field, `getFieldError(field)` will be `null`; always check first.

**Mistake 6 — confusing a validation error with a conversion error.** When a value converted to the target type yet failed `@Min`, `@NotBlank`, or a custom validator, the rejected value can still be a type-valid Java value. Use `isBindingFailure()` and error codes to classify.

**Mistake 7 — writing the entire rejected value to logs or responses.** A sensitive field may hold passwords, tokens, IDs, or personal info; arrays/objects can also clutter output. Only use allowlisted field names and controlled error messages; restrict logging, apply masking/redaction, and escape on display.

**Mistake 8 — using `@ModelAttribute` directly on an entity and allowing all properties to bind.** This increases the risk of binding properties the user is not permitted to modify. Bind into dedicated form/DTO objects, define allowed fields, and enforce authorization in services. Where needed, configure `DataBinder.setAllowedFields(...)` for property binding.

**Mistake 9 — equating field suppression with `FieldError`.** A field blocked by `allowedFields` can appear in `BindingResult.getSuppressedFields()` without creating a conversion error. Therefore, do not check only `getFieldErrors()` when you need to detect attempts to modify disallowed fields.

## 10. Scenarios to Test

You can write unit tests for `DataBinder` and integration tests with Spring MVC:

| Case | Key expectations |
|---|---|
| `age="abc"`, initial target 21 | `typeMismatch` present; rejected `"abc"`; target stays 21; field type `Integer.class` |
| `age="16"` and validator requires ≥ 18 | Target becomes `Integer(16)`; error `bindingFailure=false` |
| `age="21"` and all constraints valid | No `FieldError` for `age` |
| `nickname=null`, property type `String` | Field value may be null; field type can still be `String.class` |
| Two different fields fail together | Errors retrieved per field; never confuse one field's error for another |
| Field blocked from binding | Not assigned; check `getSuppressedFields()` separately |
| Input contains sensitive data | Responses/logs do not accidentally leak rejected values |
| Controller receives mistyped form | `BindingResult` present to re-display input; persistence branch skipped |

In tests, avoid matching entire exception message strings verbatim because messages vary by locale, converter, Spring version, and message-code resolution. Assert on field name, error kind, rejected value, and target state.

## 11. Choosing the Right Method in Practice

When you need to **re-display the input box the user just submitted**, prefer Spring's form-binding mechanism or `getFieldValue(field)` with safe escaping/formatting.

When you need to **explain a specific field error**, get the `FieldError`, inspect `getField()`, `getCode()` / `getCodes()`, `isBindingFailure()`, and read `getRejectedValue()` only when genuinely needed. Never embed rejected values arbitrarily into messages.

When you need to **know the Java type the target expects**, call `getFieldType(field)`, handle `null`, and remember this type does not necessarily match the runtime type of the rejected input.

When you need to **inspect the value actually held inside the target**, use the form/DTO getter or `BindingResult.getRawFieldValue(field)` per implementation semantics. And whenever binding/validation errors exist, do not use target values for business execution until the entire request meets requirements.

### Official References

- [Spring Framework Javadoc — Errors](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework Javadoc — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework Javadoc — FieldError](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework Javadoc — AbstractBindingResult](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/AbstractBindingResult.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
