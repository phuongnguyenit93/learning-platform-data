# Distinguishing bind from validate: Two Separate Operations in Spring DataBinder

A form can be **successfully bound** onto a Java object and still contain data that is invalid under application rules. Conversely, a field that fails to convert from a string to a number produces an error right during data binding, before rules such as “age must be at least 18” are ever applied.

In Spring Framework, **binding (`bind`)** and **validation (`validate`)** are two operations with distinct responsibilities:

- **Bind**: reads input values, selects target properties, converts types when needed, and attempts to assign values onto the object.
- **Validate**: inspects the object and evaluates validity rules, recording any violations.

`org.springframework.validation.DataBinder` lets you invoke these two operations **separately**: `binder.bind(propertyValues)` and then `binder.validate()`. Both binding errors and validation errors are collected in the binder's **`BindingResult`**.

## 1. The Big Picture

```text
Raw data (form/query parameters or PropertyValues)
          |
          v
   binder.bind(values)
          |
          +-- Select fields allowed to be bound
          +-- Convert type: "20" -> Integer(20)
          +-- Call setter / update target object
          +-- Record binding error if conversion/assignment fails
          |
          v
Java object populated with convertible values
          |
          v
     binder.validate()
          |
          +-- Invoke registered Spring Validators
          +-- Check rules on the current Java values
          +-- Record validation errors if rules are violated
          |
          v
   binder.getBindingResult()
          |
          +-- FieldErrors from binding
          +-- FieldErrors/ObjectErrors from validation
          |
          v
Application handles results, returns errors, or continues business flow
```

The core point is that **`bind()` does not invoke `validate()` by default**, and **`validate()` does not re-read or re-bind raw input data**. When using `DataBinder` directly in Java code, the developer decides when to call each operation. Spring MVC can coordinate both steps automatically depending on argument types and annotations, yet the two responsibilities remain distinct.

### Very Short Example

Suppose `RegistrationForm` has two properties: `name: String` and `age: Integer`.

| Input | After `bind` | After `validate` |
| --- | --- | --- |
| `name=Lan`, `age=20` | `name="Lan"`, `age=20`; no conversion errors | No errors if name is required and minimum age is 18 |
| `name="  "`, `age=17` | Both values bind cleanly; no constraint errors yet | Blank-name error and under-18 age error |
| `name=Lan`, `age=abc` | Converting `abc` to `Integer` fails; binding error on `age` | Binding error remains; validator may inspect already-bound fields |
| `name=Lan`, missing `age` | `age` may remain `null` unless “required fields” is configured | Validator must declare required rule if age is required |

In the table above, “name required” and “age at least 18” are illustrative validation rules. They do not appear automatically just by declaring Java properties.

## 2. What Exactly Does bind Do?

### 2.1. Data Source and Target Object

`DataBinder` takes a **target object** and name–value pairs as `PropertyValues`. `MutablePropertyValues` is a common way to build input programmatically or in tests:

```java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registration");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Lan");
values.add("age", "20");

binder.bind(values);
```

This is a **snippet**; the `RegistrationForm` class, imports, and complete project are shown in the example below. During property binding, Spring finds the matching JavaBean properties, converts `"20"` to `Integer`, and assigns it to `age` via its setter.

`DataBinder` supports nested property paths such as `address.city`, along with settings for allowed fields, required fields, and type conversion. In Spring Framework 6.x, in addition to property binding there is constructor binding via `construct(...)`. This lesson uses **property binding via `bind(...)`** to highlight the two operations clearly.

### 2.2. Type Conversion Is Part of Binding

Over HTTP, `age=20` typically arrives as a string. For an `Integer` property, Spring's conversion mechanism attempts to produce a numeric value. For `age=abc`, conversion fails. `DataBinder` normally records a `FieldError` with base code `typeMismatch` in `BindingResult` instead of treating `abc` as a valid age.

Depending on context, conversion can use a configured `PropertyEditor`, `ConversionService`, or `Formatter`. A manually created `DataBinder` in a console program does not automatically have the same set of formatters as a `WebDataBinder` in a configured Spring MVC application.

Distinguish two questions:

- “Can `abc` convert to `Integer`?” is a **binding/type-conversion question**.
- “Does `17` satisfy the minimum age of 18?” is a **validation question**.

### 2.3. BindingResult Is Already Useful Before validate

Right after `bind(...)`, you can call:

```java
BindingResult result = binder.getBindingResult();
boolean hadBindingProblem = result.hasErrors();
```

`BindingResult` may already hold type-conversion errors or binder-configured required-field errors. Therefore, `hasErrors()` **does not equate to** “Bean Validation has run”. To tell whether a field error originated from binding, `FieldError` provides `isBindingFailure()`.

If you need to specify which external field names are allowed, use `binder.setAllowedFields("name", "age")` or use constructor binding/an appropriate input DTO. Binding untrusted input directly onto an entity with sensitive properties like `role`, `status`, or `id` can lead to unintended mass assignment.

## 3. What Exactly Does validate Do?

### 3.1. Validator Inspects an Existing Java Object

With Spring's `org.springframework.validation.Validator` interface:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

This is a **condensed signature for explanation**. `supports` declares which types can be checked; `validate` evaluates conditions and records errors into `Errors`. Common ways to record errors include:

- `errors.rejectValue("age", "age.min", "Age must be at least 18")`: field-level violation, creating a `FieldError`.
- `errors.reject("registration.invalid", "Registration is invalid")`: object-level violation, creating a global error.
- `ValidationUtils.rejectIfEmptyOrWhitespace(errors, "name", ...)`: helper checking empty or whitespace-only values.

When using `DataBinder` directly, you must register the validator via `binder.setValidator(...)`, `binder.addValidators(...)`, or an equivalent configuration mechanism, **and then** call `binder.validate()`. Until `validate()` is called, custom validator constraints have not executed.

### 3.2. Validate Does Not Fix or Convert Values

`validate()` does not turn `age=abc` into a valid number, does not replace `name="  "` with a valid name, and does not re-read `MutablePropertyValues`. A validator normally records errors; it is not responsible for normalizing or repairing data.

If binding failed on a field, that field may retain its prior value or `null` depending on previous state and binder setup. A validator should not assume all properties were definitely bound successfully; check for `null` appropriately and distinguish binding errors from rule errors to avoid misleading duplicate reports.

### 3.3. How Do Spring Validator and Jakarta Bean Validation Relate?

`DataBinder` supports Spring `Validator`. A Bean Validation provider such as Hibernate Validator can be bridged via `LocalValidatorFactoryBean`, which adapts `jakarta.validation.Validator` to Spring's `Validator`. Annotations such as `@NotBlank`, `@Min`, and `@Email` together with `@Valid`/`@Validated` can then participate in the **validation** step.

Crucially, **constraint annotations do not change `bind()`'s responsibility**. `@Min(18)` checks the value after it has been converted to a number; it does not turn `"abc"` into a number. In Spring 6 and Boot 3, those annotations live in the `jakarta.validation.*` namespace.

## 4. Complete Practical Example: Observing Both Phases

The Java 17 example below demonstrates three cases on **Spring Framework 6.2**, run from the command line without Spring Boot, a web server, or a Jakarta Bean Validation provider. It uses a hand-written Spring `Validator` to keep responsibilities cleanly separated.

Project structure:

```text
bind-vs-validate/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binder/BindVsValidateDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'bind-vs-validate'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.binder.BindVsValidateDemo'
}
```

The `spring-context` dependency pulls in the Spring modules needed for `DataBinder`, `Validator`, and `MutablePropertyValues`. When integrating into an existing Spring Boot project, rely on Boot's Spring version management rather than pinning library versions manually as in this console project.

File `src/main/java/demo/binder/BindVsValidateDemo.java`:

```java
package demo.binder;

import java.util.Comparator;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BindVsValidateDemo {

    // Target object with JavaBean getters/setters.
    public static class RegistrationForm {
        private String name;
        private Integer age;

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
    }

    // Only checks validity rules on Java values.
    public static class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required",
                    "Name is required");

            Integer age = form.getAge();
            if (age != null && age < 18) {
                errors.rejectValue("age", "age.min",
                        "Age must be at least 18");
            }
        }
    }

    private static void show(String scenario, String name, String age) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registration");

        // Only these two fields are bound from input data.
        binder.setAllowedFields("name", "age");
        binder.setValidator(new RegistrationValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", name);
        input.add("age", age);

        // STEP 1: binding + conversion, Validator NOT called yet.
        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println(scenario);
        System.out.println("  bind: age=" + form.getAge()
                + ", errors=" + result.getErrorCount());

        // STEP 2: run Validator on the bound object.
        binder.validate();

        System.out.println("  validate: errors="
                + result.getErrorCount());

        // Classify errors via isBindingFailure(), not by guessing from messages.
        result.getFieldErrors().stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .forEach(error -> System.out.println(
                        "    " + error.getField() + " ("
                        + (error.isBindingFailure()
                                ? "binding" : "validation")
                        + ")"));
    }

    public static void main(String[] args) {
        show("valid", "Lan", "20");
        show("rule-invalid", "  ", "17");
        show("conversion-invalid", "Lan", "abc");
    }
}
```

Run from the project directory using an installed Gradle:

```bash
gradle -q run
```

If the project includes a Gradle Wrapper, the equivalent commands are `./gradlew -q run` (Unix/macOS) or `gradlew.bat -q run` (Windows). Expected **stdout from `main`**:

```text
valid
  bind: age=20, errors=0
  validate: errors=0
rule-invalid
  bind: age=17, errors=0
  validate: errors=2
    age (validation)
    name (validation)
conversion-invalid
  bind: age=null, errors=1
  validate: errors=1
    age (binding)
```

Explaining each case:

1. **`valid`**: `"20"` converts to `Integer 20`, and `name` has content. Neither `bind()` nor `validate()` produces errors.
2. **`rule-invalid`**: `"17"` converts cleanly to `Integer 17`, and `name` receives the two-space string. Right after `bind()`, there are zero errors. Only when `validate()` is called do the age and name rules record **two validation errors**. This is direct proof that successful binding does not guarantee valid data.
3. **`conversion-invalid`**: `"abc"` cannot convert to `Integer`. `bind()` immediately records **one binding error**, and the new object's `age` property remains `null`. Because the example validator only checks the age threshold when `age != null`, it does not fabricate a spurious age error; after `validate()`, the result still holds one binding error.

**Design decision in the example:** the validator did not apply an “age required” rule for `null` so that the difference between conversion errors and threshold errors stands out clearly. In a real application, if `age` is required, add a `null` check, while deciding how to display results when the same field already has a conversion error. Do not assume `null` is inherently a valid age.

## 5. One BindingResult, Two Error Sources

`BindingResult` extends `Errors` and holds inspection results attached to a target object. When the same binder runs `bind(...)` and `validate()`, errors accumulate into the same result object:

```java
binder.bind(input);
BindingResult result = binder.getBindingResult();
int errorsAfterBind = result.getErrorCount();

binder.validate();
int errorsAfterValidate = result.getErrorCount();
```

| Information | How to Read | Interpretation |
| --- | --- | --- |
| Any errors present | `result.hasErrors()` | Includes recorded binding and validation errors |
| Total error count | `result.getErrorCount()` | Includes both `FieldError` and global errors |
| List of field errors | `result.getFieldErrors()` | Contains field path, error code, message |
| Error on one field | `result.getFieldError("age")` | May be a conversion or constraint error |
| Object-level errors | `result.getGlobalErrors()` | Used for rules spanning the whole object |
| Distinguish origin | `fieldError.isBindingFailure()` | `true` usually indicates a binding failure; `false` indicates `rejectValue`/validator |

For example, a type-error `FieldError` typically has a family of codes based on `typeMismatch` (expandable with object name, field name, and Java type). A manual `rejectValue("age", "age.min", ...)` has codes derived from `age.min`. When displaying to users, those codes can be resolved via `MessageSource`; avoid exposing stack traces directly or forcing clients to parse default English messages.

`BindingResult` may retain rejected values. For `age=abc`, the error can keep the raw string entered by the user to re-render a form. Avoid casually logging or returning `rejectedValue` when it could be a password, token, or sensitive data.

**Note:** calling `binder.validate()` multiple times does not mean “a completely fresh check”. Validators can re-add errors onto the same `BindingResult`, creating duplicates. Each request handling pass should have a clear flow and its own result instance.

## 6. Binder Settings Easily Confused with validate

`DataBinder` can check certain conditions **during binding itself**. That does not collapse the two operations into one.

### 6.1. Binder-Level Required Fields

You can configure:

```java
binder.setRequiredFields("name", "age");
```

During binding, the binder checks required fields and can record an error with base code `required` if a field is omitted or lacks a required value per binder policy. This is a **field-presence check at bind time**, not validation of domain rules like minimum age, name length, or email validity.

Do not confuse `setRequiredFields` with Jakarta `@NotNull` or Spring `ValidationUtils.rejectIfEmptyOrWhitespace`. They execute at different points and can differ in how they handle empty/whitespace strings. Design the contract clearly to avoid generating duplicate error messages for a single condition.

### 6.2. Allowed and Suppressed Fields

`setAllowedFields(...)` restricts which field names are permitted to be bound. Unbound data can be inspected via `result.getSuppressedFields()`. This is a **decision about binding scope and object protection**, not a “valid value” rule.

In public APIs, use input DTOs with only the fields clients are allowed to send, specify bindable fields when needed, and let the service decide how to map onto the domain model. Never allow clients to write `role`, `accountStatus`, or identifiers simply because an entity has setters.

### 6.3. Converters, Formatters, and Validators

- `Converter<String, Integer>` or standard type conversion answers whether input can convert to the needed type.
- `Formatter` handles parsing/formatting locale-sensitive types, such as localized dates or numbers.
- `Validator` answers whether the post-conversion object satisfies input rules.

A converter should not “silently fix” a non-numeric string to `0` just to avoid an error. Likewise, a validator should not be responsible for parsing raw input strings.

## 7. Does Spring MVC Run Both Automatically?

**Potentially yes**, depending on parameter types and annotations; underneath, they remain two separate responsibilities.

For forms using `@ModelAttribute`, Spring MVC creates or retrieves the object, uses `WebDataBinder` to bind appropriate parameters, and can invoke validation when `@Valid`/`@Validated` is present. The controller can accept `BindingResult` right after the object to decide how to return errors.

The following is an **MVC integration illustration**, assuming `RegistrationForm` is a bean with getters/setters as in the example and `RegistrationValidator` is Spring-managed or injected into the controller:

```java
@InitBinder("registration")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age");
    binder.addValidators(registrationValidator);
}

@PostMapping(path = "/registrations",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> submit(
        @Validated @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(FieldError::getField)
                        .distinct()
                        .toList());
    }

    return ResponseEntity.ok().body("accepted");
}
```

To place this snippet in a full controller, declare the controller, inject `registrationValidator`, and add the corresponding imports (`WebDataBinder`, `@InitBinder`, `@PostMapping`, `MediaType`, `@Validated`, `@ModelAttribute`, `BindingResult`, `ResponseEntity`, `FieldError`). This is not a standalone Java file. `@Validated` tells Spring MVC the object should be validated after binding, while `@InitBinder` configures the binder specifically for object name `registration`.

**Important rule:** the `BindingResult` parameter must sit **immediately after** the bound/validated parameter it describes. The controller can then receive and surface both binding and validation errors. Without `BindingResult` or with another exception handler, Spring MVC may translate errors into an exception/HTTP 400 depending on handler type and configuration.

### 7.1. Is @RequestBody JSON the Same as DataBinder.bind?

Do not equate the two pipelines:

- `@ModelAttribute` typically binds query/form parameter pairs onto an object via the WebDataBinder mechanism.
- `@RequestBody` uses an `HttpMessageConverter`, usually Jackson for JSON, to **read and deserialize the body into an object**. This process is not simply calling `DataBinder.bind(MutablePropertyValues)` on each JSON field.
- Once the object is constructed, Spring MVC can apply validation via `@Valid`/`@Validated`. Malformed JSON or values unconvertible into DTO types can fail **before** validation with a message-reading error such as `HttpMessageNotReadableException`.
- Constraint violations on an `@Valid @RequestBody` DTO are normally surfaced via `MethodArgumentNotValidException` and HTTP 400 in standard Spring MVC; for direct method validation on parameters, the handling path may differ.

So when saying “binding first, validation second”, understand it as **the logical relationship between constructing/populating data and evaluating constraints**; technical mechanics depend on the data source and controller argument type.

## 8. When Should You Validate After a Failed Binding?

An application may want to return multiple errors at once so the user can fix them in one go. However, you cannot assume all properties have valid types if the binder recorded conversion errors.

A cautious way to organize this:

1. Bind data and retrieve `BindingResult`.
2. Inspect conversion errors and note which fields lack valid values.
3. If the validator can safely inspect the bound portion (checking for `null`, never assuming every field bound), run validation and collect errors.
4. If validation depends strictly on a property that failed conversion, skip that dependent rule or report the binding error first.
5. Only proceed to create/save domain objects when no blocking errors remain and authentication, authorization, and business checks all pass.

For example, `age=abc` should receive a type error. If the validator omits a `null` check and calls `form.getAge() < 18`, the code can throw `NullPointerException` when unboxing `Integer`. Checking `age != null` in the main example avoids turning an input error into a server error.

Do not use `result.hasErrors()` **before** `validate()` as proof that data is valid: that is only post-binding status. Similarly, returning HTTP success right after `bind()` skips registered constraints.

## 9. Designing Tests to Prove Both Steps Are Independent

A test suite should split inputs into distinct groups rather than testing only one “happy path” request:

| Case | Check Right After bind | Check After validate |
| --- | --- | --- |
| `age=20`, valid name | `age == 20`, no binding errors | No errors |
| `age=17`, valid name | `age == 17`, no binding errors | `age.min` error |
| `age=abc`, valid name | Type error on `age` | Binding error still visible, no validator exception |
| `name="  "`, `age=20` | Name is still whitespace string | Blank-name error |
| Missing `age` with required rule | `age` may be `null` or binder records `required` if configured | Check `null` when validation policy requires it |
| Input has `role=ADMIN` while only `name` and `age` allowed | `role` is not bound; may appear in `getSuppressedFields()` | Validation does not replace field allowlist policy |

For unit tests without HTTP, create `DataBinder` and `MutablePropertyValues` as in the example to assert errors appear at the exact expected stage. For MVC integration tests, use `MockMvc` to send form/query/JSON requests and verify both HTTP status and the API's promised error payload.

In tests, do not depend on `FieldError` ordering unless the application explicitly sorts them. When asserting error origin, use `FieldError.isBindingFailure()` and appropriate error codes rather than comparing exact default library message text.

## 10. Common Mistakes

1. **Assuming `bind()` runs all constraints automatically:** `DataBinder.bind(...)` primarily binds and converts types. To run registered Spring `Validator` instances in manual code, call `validate()`.
2. **Assuming `validate()` fixes unconvertible data:** validators check the current object; type conversion belongs to binding/body deserialization.
3. **Checking `hasErrors()` right after binding and returning success:** can skip blank-name, under-age, and other rule errors.
4. **Confusing `typeMismatch` with `@Min`:** a non-numeric string and a number below the threshold are distinct cases, usually needing distinct messages.
5. **Skipping `null` checks after failed conversion:** validators may throw exceptions instead of recording clear errors.
6. **Assuming every error in `BindingResult` comes from `@Valid`:** binding can produce errors even without a Bean Validation provider or calling `validate()`.
7. **Mixing up `setRequiredFields` and `@NotNull`:** bind-time required fields and value constraints belong to two different mechanisms.
8. **Allowing binding to every setter on an entity:** external input can alter unexposed fields; use DTOs and allowed-field controls.
9. **Calling `validate()` repeatedly on the same binder assuming errors reset:** risks accumulating duplicate errors; manage result lifecycle explicitly.
10. **Placing `BindingResult` in the wrong position in MVC signatures:** Spring requires it immediately after the bound/validated parameter.
11. **Using `@RequestBody` and assuming Jackson calls `DataBinder.bind(...)`:** JSON goes through a message converter; decoding failures can happen before Bean Validation.
12. **Assuming an error-free DTO is cleared for persistence:** the service/domain layer must still check business rules, system state, and permissions.

## 11. Self-Check Exercises

**Exercise 1:** Given input `age="x"` and a validator checking only `age >= 18`, explain what error appears at the bind step, why you should not compare `form.getAge() < 18` directly, and which layer is responsible for reporting to the user.

**Exercise 2:** Add an `age != null` constraint to `RegistrationValidator`, then re-run all three scenarios. When `age=abc` causes a binding error, decide whether to also show an “age required” error or only the type conversion error; explain your choice.

**Exercise 3:** Call `binder.bind(input)` but remove the `binder.validate()` line. Compare error counts across all three scenarios with the original output. Then restore `validate()` and verify the two errors in `rule-invalid` reappear.

**Exercise 4:** Add a `role` field with a setter to the form while keeping `setAllowedFields("name", "age")`. Submit `role=ADMIN` in `MutablePropertyValues`, verify that the property is not bound, and observe `getSuppressedFields()`.

**Exercise 5:** Design an `@ModelAttribute` form endpoint with `BindingResult` that separates type conversion errors and validation errors into two message categories while still returning a unified response.

If you can explain why **`"17"` binds successfully yet fails validation**, whereas **`"abc"` fails right at binding**, you have mastered the most important boundary of `DataBinder`.

## Official References

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Java Bean Validation and Configuring DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
