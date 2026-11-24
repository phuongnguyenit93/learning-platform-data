# DefaultBindingErrorProcessor and the required, typeMismatch, and methodInvocation error codes

In Spring Framework, a **data binding** operation does more than copy input values into a Java object. It can also detect missing required fields, values that cannot be converted to the target type, or failing setter invocations. `DefaultBindingErrorProcessor` is the default component that turns those situations into structured errors inside `BindingResult`.

Three core error codes:

- `required` — a field declared as required by `DataBinder` was not provided according to the input-field check rules.
- `typeMismatch` — a value was supplied for a property, yet could not be converted/coerced to the target Java type.
- `methodInvocation` — invoking the property accessor method, typically a JavaBean setter, threw an exception during binding.

These are **binding-step error codes**, not by default errors from `@NotNull`, `@Min`, or a custom `Validator`. This lesson explains the error processor's role, what triggers each code, how to read `FieldError`, how to map codes to messages, how to customize behavior, and includes a command-line Java 17 example.

## 1. Context: how does DataBinder record errors?

In JavaBean property-binding mode, `DataBinder` receives a target object along with incoming `PropertyValues`. A string value like `"25"` can convert to `Integer 25`, whereas `"abc"` cannot.

```text
Input data (MutablePropertyValues)
                  |
                  v
           DataBinder.bind(...)
                  |
            check required
               fields
                  |
                  +-- missing required field
                  |       |
                  |       v
                  | DefaultBindingErrorProcessor
                  | processMissingFieldError(...)
                  |       |
                  |       +--> FieldError: required
                  |
                  v
     assign properties / convert types
                  |
                  +-- TypeMismatchException
                  |       |
                  |       +--> processPropertyAccessException(...)
                  |               +--> FieldError: typeMismatch
                  |
                  +-- MethodInvocationException
                  |       |
                  |       +--> processPropertyAccessException(...)
                  |               +--> FieldError: methodInvocation
                  |
                  v
      binder.getBindingResult()
                  |
                  +--> FieldError / ObjectError
                  |
                  v
      (optional) binder.validate()
                  |
                  +--> errors from Validator rule checks
```

**Division of responsibilities:**

| Component | Responsibility |
| --- | --- |
| `DataBinder` | Orchestrates property binding; manages required fields, allowed fields, conversion, and error collection. |
| `BindingErrorProcessor` | Strategy interface converting binding failures into errors on `BindingResult`. |
| `DefaultBindingErrorProcessor` | Default implementation using the codes `required`, `typeMismatch`, and `methodInvocation`. |
| `PropertyAccessException` | Exception family for property access/assignment failures, including `TypeMismatchException` and `MethodInvocationException`. |
| `BindingResult` | Holds errors, error codes, field paths, and rejected values; shared across both binding and validation. |
| `MessageCodesResolver` | Expands a base code and field name into a candidate list of more specific codes for message lookup. |
| `MessageSource` | Resolves error codes into locale-appropriate messages. |
| `Validator` | Checks rules on the populated object; if never invoked, it adds no validation errors. |

`DefaultBindingErrorProcessor` does not decide whether all data is valid. It only converts **binding error events forwarded by `DataBinder`** into error structures understood by the rest of Spring.

## 2. Two extension points on BindingErrorProcessor

The `org.springframework.validation.BindingErrorProcessor` interface has two key methods:

```java
void processMissingFieldError(
        String missingField,
        BindingResult bindingResult);

void processPropertyAccessException(
        PropertyAccessException ex,
        BindingResult bindingResult);
```

This is a **condensed API signature**, not a standalone runnable class.

### 2.1. processMissingFieldError(...)

`DataBinder` calls this strategy when a required field is missing from the incoming `PropertyValues`. The default implementation creates a `FieldError` with base code `required` and registers it on `BindingResult`.

Remember: `required` here means **presence required during binding**, e.g. from calling `binder.setRequiredFields("name")`. It is not synonymous with Jakarta `@NotNull` or Spring `ValidationUtils.rejectIfEmptyOrWhitespace`. Those belong to the validation layer.

### 2.2. processPropertyAccessException(...)

`DataBinder` calls this strategy for a `PropertyAccessException` thrown while assigning a property. The default implementation uses:

```java
String baseErrorCode = ex.getErrorCode();
```

For common subclasses:

- `TypeMismatchException#getErrorCode()` yields `typeMismatch`.
- `MethodInvocationException#getErrorCode()` yields `methodInvocation`.

`DefaultBindingErrorProcessor` constructs a `FieldError` based on the error type and offending property name, then calls `BindingResult.resolveMessageCodes(...)` to build candidate codes for message rendering.

**Do not assume every binding exception is converted into a `FieldError` by this processor.** For instance, a completely non-existent property when `setIgnoreUnknownFields(false)` is enabled, or an unreachable nested path, can throw another exception without becoming `typeMismatch` or `methodInvocation`.

## 3. The required code: an input field required by the binder is missing

Suppose `AccountForm` has `name` and `age`, and the server requires `name` to be present during binding:

```java
DataBinder binder = new DataBinder(form, "account");
binder.setRequiredFields("name");
```

If `PropertyValues` supplies only `age=20` with no `name` key, binding records a `FieldError` for `name` with base code `required`.

Key notes:

1. `required` is not automatically generated for every `null` Java property. The binder (or equivalent logic) must be configured to require that field during binding.
2. `setRequiredFields(...)` inspects data participating in the **current binding pass**, not merely the bean's final value. A bean pre-populated with a value can still trigger a missing-field error if the request omits the field required by the binder.
3. When a required field is missing or blank, `DataBinder` can also strip that property value from subsequent application to avoid redundant processing.
4. Empty or whitespace-only strings can be treated as failing the binder's required check; when actual name content constraints are needed, add explicit validation rules.
5. Required fields in property binding differ from constructor parameter requirements and from Spring MVC's `@RequestParam(required = true)`.

Example:

```text
PropertyValues: age = "20"
Required fields: name
       |
       v
No name in data to bind
       |
       v
processMissingFieldError("name", bindingResult)
       |
       v
FieldError(field="name", baseCode="required")
```

Never conclude `required` automatically equals HTTP 400 in every context. `DataBinder` can run in console apps; in MVC, the HTTP response still depends on the handler, `BindingResult`, and exception handling.

## 4. The typeMismatch code: value cannot convert to target type

Suppose a bean declares:

```java
private Integer age;

public void setAge(Integer age) {
    this.age = age;
}
```

When a client sends `age=20`, Spring converts `"20"` to `Integer 20`. When a client sends `age=abc`, conversion fails and a `TypeMismatchException` is created during property assignment.

`DefaultBindingErrorProcessor` receives that exception via `processPropertyAccessException(...)` and records a `FieldError` with base code `typeMismatch`.

```text
age = "abc"  (String)
      |
      v
Convert to java.lang.Integer
      |
      +-- conversion fails
               |
               v
     TypeMismatchException
               |
               v
     DefaultBindingErrorProcessor
               |
               v
     FieldError("age", "typeMismatch")
```

The `typeMismatch` code is **not** `@Min`, `@Max`, or a custom validator. `age=16` still binds successfully because it is a valid integer; only invoking validation with an "age at least 18" rule raises a rule error.

The rejected input is typically retained in `FieldError#getRejectedValue()` so forms can re-display it. Avoid echoing it verbatim to clients or writing it to logs if the field may contain secrets.

## 5. The methodInvocation code: setter/getter throws an exception

Consider a setter:

```java
public void setStatus(String status) {
    if ("LOCKED".equals(status)) {
        throw new IllegalArgumentException(
                "Status cannot be set to LOCKED through this form");
    }
    this.status = status;
}
```

`status=LOCKED` **already has the right `String` type**. The failure is not in type conversion. The problem occurs when Spring invokes the setter and the setter throws an exception. During property binding via JavaBean accessors, this situation is wrapped as a `MethodInvocationException` and translated by `DefaultBindingErrorProcessor` into a `FieldError` with base code `methodInvocation`.

```text
status = "LOCKED" (String, valid type)
       |
       v
  setStatus("LOCKED")
       |
       +-- IllegalArgumentException from setter
                    |
                    v
          MethodInvocationException
                    |
                    v
          DefaultBindingErrorProcessor
                    |
                    v
          FieldError("status", "methodInvocation")
```

Distinctions to keep clear:

- **`typeMismatch`**: failed to produce a value of the right type to assign to the property.
- **`methodInvocation`**: invoking the bean accessor failed during value assignment, usually the setter.
- **Validation error**: a separate validator recorded an error after inspecting the object's state.

Be cautious when throwing exceptions from setters. Setters containing complex business conditions make binding unpredictable and harder to test. In DTO/API designs, keep setters simple and place significant business rules in the appropriate validator, service, or domain layer. The throwing setter example here exists **strictly to demonstrate the `methodInvocation` code**, not as a recommendation to put business logic in setters.

## 6. Runnable example with Java 17 and Spring Framework 6.2

The console project below triggers `required`, `typeMismatch`, and `methodInvocation` in turn. Each scenario uses **a fresh `DataBinder`** so prior errors do not pollute later results. Afterward, a separate validation scenario clarifies that rule error codes are not binding error codes.

Structure:

```text
binding-error-codes/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/binding/BindingErrorCodesDemo.java
```

### 6.1. Gradle configuration

File `settings.gradle`:

```groovy
rootProject.name = 'binding-error-codes'
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
    mainClass = 'demo.binding.BindingErrorCodesDemo'
}
```

`spring-context` brings in the dependencies `DataBinder` and `Validator` need for this example. In an existing Spring Boot project, let Spring Boot manage compatible Spring module versions rather than hardcoding an independent Spring version outside dependency management.

### 6.2. Complete Java code

File `src/main/java/demo/binding/BindingErrorCodesDemo.java`:

```java
package demo.binding;

import java.util.Comparator;
import java.util.List;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class BindingErrorCodesDemo {

    public static class AccountForm {
        private String name;
        private Integer age;
        private String status;

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

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            if ("LOCKED".equals(status)) {
                throw new IllegalArgumentException(
                        "Status cannot be set to LOCKED through this form");
            }
            this.status = status;
        }
    }

    // This Validator illustrates rule errors, NOT the three binding codes.
    public static class AccountValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return AccountForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            AccountForm form = (AccountForm) target;
            if (form.getAge() != null && form.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", "Age must be at least 18");
            }
        }
    }

    private static MutablePropertyValues values(String... pairs) {
        if (pairs.length % 2 != 0) {
            throw new IllegalArgumentException("Expected key/value pairs");
        }

        MutablePropertyValues input = new MutablePropertyValues();
        for (int i = 0; i < pairs.length; i += 2) {
            input.add(pairs[i], pairs[i + 1]);
        }
        return input;
    }

    // With DefaultMessageCodesResolver, the last code is the base code.
    private static String baseCode(FieldError error) {
        String[] codes = error.getCodes();
        if (codes == null || codes.length == 0) {
            return "(none)";
        }
        return codes[codes.length - 1];
    }

    private static void printErrors(BindingResult result) {
        List<FieldError> fieldErrors = result.getFieldErrors()
                .stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .toList();

        for (FieldError error : fieldErrors) {
            System.out.println("  " + error.getField()
                    + " -> " + baseCode(error)
                    + ", bindingFailure=" + error.isBindingFailure());
        }
    }

    private static void bindingCase(
            String label, MutablePropertyValues input) {

        AccountForm form = new AccountForm();
        DataBinder binder = new DataBinder(form, "account");

        // Specify that name must be present in the bound input data.
        binder.setRequiredFields("name");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println(label + ": "
                + result.getErrorCount() + " error(s)");
        printErrors(result);
    }

    private static void validationCase() {
        AccountForm form = new AccountForm();
        DataBinder binder = new DataBinder(form, "account");
        binder.setRequiredFields("name");
        binder.setValidator(new AccountValidator());

        binder.bind(values(
                "name", "Lan", "age", "16", "status", "ACTIVE"));

        System.out.println("validation-before: "
                + binder.getBindingResult().getErrorCount()
                + " error(s)");

        binder.validate();

        BindingResult result = binder.getBindingResult();
        System.out.println("validation-after: "
                + result.getErrorCount() + " error(s)");
        printErrors(result);
    }

    public static void main(String[] args) {
        bindingCase("missing-required",
                values("age", "20"));

        bindingCase("type-mismatch",
                values("name", "Lan", "age", "abc"));

        bindingCase("setter-throws",
                values("name", "Lan", "status", "LOCKED"));

        bindingCase("valid",
                values("name", "Lan", "age", "20", "status", "ACTIVE"));

        validationCase();
    }
}
```

To run, from the project root using an installed Gradle:

```bash
gradle -q run
```

If using the Gradle Wrapper, run `./gradlew -q run` on Unix/macOS or `gradlew.bat -q run` on Windows. Output printed by `main` under Spring 6.2 defaults:

```text
missing-required: 1 error(s)
  name -> required, bindingFailure=true
type-mismatch: 1 error(s)
  age -> typeMismatch, bindingFailure=true
setter-throws: 1 error(s)
  status -> methodInvocation, bindingFailure=true
valid: 0 error(s)
validation-before: 0 error(s)
validation-after: 1 error(s)
  age -> age.min, bindingFailure=false
```

Gradle may print its own tool messages if `-q` is omitted; the block above shows only the lines from the Java program.

### 6.3. Why do the results differ?

**`missing-required`:** `name` was declared via `setRequiredFields("name")` yet omitted from `MutablePropertyValues`. `processMissingFieldError` creates the `required` error. Even though an `AccountForm` bean can exist with `name == null`, this is a missing-field error in *binding input*, not a result from `AccountValidator`.

**`type-mismatch`:** `name` was submitted validly. `age="abc"` fails conversion to `Integer`, producing `typeMismatch`. Because `binder.validate()` was never called, this error must originate from binding.

**`setter-throws`:** `name` is present and `status` has the right string type, yet the setter throws an exception on `"LOCKED"`. `DefaultBindingErrorProcessor` translates the method invocation failure into `methodInvocation`. No `AccountValidator` is needed to observe this code.

**`valid`:** all fields are present and bind cleanly. No validator was invoked; there are zero binding errors. This **does not prove** the data satisfies every business rule.

**`validation-before/after`:** `age=16` converts cleanly to `Integer`, so before `validate()` there are zero errors. `AccountValidator` records `age.min` afterward. `FieldError.isBindingFailure()` returns `false`, reflecting the error's origin.

## 7. How does the base code differ from the FieldError code list?

A `FieldError` does not carry only the bare string `"typeMismatch"`. `DefaultBindingErrorProcessor` typically calls:

```java
bindingResult.resolveMessageCodes(baseErrorCode, fieldName)
```

Spring's `DefaultMessageCodesResolver` builds a **list of codes from most specific to most general** so you can customize messages per field while keeping fallbacks.

For example, with object name `account`, field name `age`, type `java.lang.Integer`, and base code `typeMismatch`, the list typically looks like:

```text
typeMismatch.account.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
```

For missing `name`, base code `required` can produce:

```text
required.account.name
required.name
required.java.lang.String
required
```

For `status` failing in its setter, base code `methodInvocation` can produce:

```text
methodInvocation.account.status
methodInvocation.status
methodInvocation.java.lang.String
methodInvocation
```

These sample lists assume **`DefaultMessageCodesResolver`, JavaBean property binding mode, and the exact field types shown**. A custom `MessageCodesResolver`, different field type resolution, or indexed/collection paths can yield different codes.

Distinguish these APIs:

- `FieldError.getCodes()`: returns **all candidate codes** usable for message lookup.
- `FieldError.getCode()`: the first code per `MessageSourceResolvable` (typically the most specific, e.g. `typeMismatch.account.age`), **not necessarily the base code**.
- `BindingResult.resolveMessageCodes("typeMismatch", "age")`: generates the candidate code list from a base code and field.
- `MessageSource.getMessage(fieldError, locale)`: searches codes in priority order; if no translation matches, falls back to default message or `MessageSource` handling.

In Section 6's example, `baseCode(...)` reads the **last element** of `getCodes()` solely to print the base code under the default resolver. If you swap resolvers, do not rely on picking the last element to categorize errors.

## 8. Mapping required, typeMismatch, and methodInvocation to messages

Technical error codes should be translated into clear messages. Example `messages.properties` bundle:

```properties
required.account.name=Vui lòng nhập tên
required=Trường bắt buộc chưa được cung cấp

typeMismatch.account.age=Tuổi phải là một số nguyên
typeMismatch=Giá trị không đúng kiểu dữ liệu

methodInvocation.account.status=Trạng thái đã chọn không thể áp dụng
methodInvocation=Không thể gán giá trị cho trường
```

In a Spring application managing a `MessageSource` bean, you can declare (Spring Framework Java config example):

```java
@Configuration
public class MessagesConfiguration {
    @Bean
    public MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");
        return source;
    }
}
```

This is a **configuration snippet**, requiring imports for `org.springframework.context.annotation.*`, `org.springframework.context.MessageSource`, and `org.springframework.context.support.ResourceBundleMessageSource`, plus `messages.properties` on the classpath. It is not a standalone program with `main`. In Spring Boot, you can use the auto-configured `messages.properties` and `messageSource` bean when appropriate; avoid declaring duplicate beans unnecessarily.

Suppose you have `BindingResult result` and `MessageSource source`:

```java
for (FieldError error : result.getFieldErrors()) {
    String userMessage =
            source.getMessage(error, Locale.forLanguageTag("vi"));
    System.out.println(error.getField() + ": " + userMessage);
}
```

This integration snippet needs `FieldError` and `Locale` imports. `FieldError` holds the prioritized code list: specific `typeMismatch.account.age` is checked before generic `typeMismatch`. For public APIs, also return a stable API error code for frontend branching; localized display messages should never be used as client logic keys.

### 8.1. Are codes and default messages the same thing?

No. An **error code** is a machine-readable identifier such as `required`. **Message codes** are one or more variants expanded by `MessageCodesResolver`. A **user message** is the resolved text from `MessageSource`, such as "Vui lòng nhập tên". Meanwhile, **default message** on `FieldError` is a fallback string attached to the error; it is not necessarily the same as the localized message.

When building standard APIs, keep these separate internally and avoid leaking sensitive details from exceptions or rejected values.

## 9. Customizing BindingErrorProcessor: when and how?

`DataBinder` allows replacing the default strategy:

```java
binder.setBindingErrorProcessor(customProcessor);
```

This helps when you want to change error codes, fallback messages, or how binding errors are represented. Still, most applications only need to configure `MessageSource`, `MessageCodesResolver`, or an API error mapper **without** replacing the binding error processor.

A minimal customization is changing only the missing-field error code while keeping type mismatch and method invocation handling by extending `DefaultBindingErrorProcessor`:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.DefaultBindingErrorProcessor;
import org.springframework.validation.FieldError;

public final class FriendlyBindingErrorProcessor
        extends DefaultBindingErrorProcessor {

    @Override
    public void processMissingFieldError(
            String missingField, BindingResult result) {

        String[] codes =
                result.resolveMessageCodes("input.required", missingField);

        FieldError error = new FieldError(
                result.getObjectName(),
                missingField,
                null,
                true,
                codes,
                null,
                "Missing required input");

        result.addError(error);
    }
}
```

This is a **structurally standalone Java class** to be placed in a project source set with Spring dependencies. It has no `main`. Once registered via `setBindingErrorProcessor(new FriendlyBindingErrorProcessor())`, missing fields use base code `input.required` instead of `required`, while property access errors continue using the inherited default implementation.

In the `FieldError` constructor above:

- `result.getObjectName()` preserves the binder's object name.
- `missingField` preserves the field path.
- `null` is the illustrative rejected value for the unprovided field.
- `true` marks a **binding failure**; avoid calling `result.rejectValue(...)` casually in a custom binding error processor and losing this classification.
- `codes` is the list expanded via `MessageCodesResolver`.
- `null` is the message arguments in this example; if your formatter/message source expects the field name as an argument, pass the appropriate array.
- The final string is the fallback default message.

When subclassing and overriding a single method, test all three error groups: changing `required` handling must not break or alter `typeMismatch` or `methodInvocation`.

### 9.1. Do not confuse setBindingErrorProcessor and setMessageCodesResolver

| Configuration point | What does it change? | Example |
| --- | --- | --- |
| `setBindingErrorProcessor(...)` | How binding error events become `FieldError`, base codes, and error metadata | Change `required` to `input.required` |
| `setMessageCodesResolver(...)` | How candidate codes are built from base code + object/field/type | Change order/format of `typeMismatch.account.age` |
| `MessageSource` | Text/locale content corresponding to codes | `typeMismatch.account.age=Age must be a number` |
| `setValidator(...)` / `addValidators(...)` | Post-binding value/object validation rules | `age.min` for age under 18 |
| `setRequiredFields(...)` | Which fields must appear in property binding input | Require the `name` key to be present |

Use the lowest-impact customization that meets your goal. If you only want friendlier wording, start with `MessageSource`; do not write a custom `BindingErrorProcessor` just to reword text.

## 10. Boundaries and edge cases

### 10.1. Required fields apply only to property binding

`setRequiredFields(...)` is built for `DataBinder.bind(PropertyValues)`. Constructor binding via `construct(...)` is a separate path that selects values needed to instantiate the object. Do not mechanically apply property-binding missing-field semantics to constructor binding.

Also distinguish `required` from `DefaultBindingErrorProcessor` from Jakarta Bean Validation's `@NotNull`/`@NotBlank`: a request may trigger multiple checks, yet their base codes and timing differ.

### 10.2. Throwing exceptions from setters is not an ideal validation strategy

Some setters accept input and throw `IllegalArgumentException` to guard invariants. That can yield `methodInvocation` in property binding, yet overusing it gives clients confusing errors and makes beans harder to reuse. Input DTOs should mostly hold and receive data; clear validation rules belong in Spring/Jakarta Validators or the service/domain layer depending on their nature.

Not every setter exception turns into `methodInvocation`: if an exception occurs outside property binding, or before reaching the setter due to an invalid path, it follows the actual failure path.

### 10.3. Unknown/invalid paths differ from the three main codes

When input contains a non-existent property name, `DataBinder` may ignore it by default or throw `NotWritablePropertyException` in strict mode. When a nested path cannot traverse a null segment, `NullValueInNestedPathException` can occur. These **do not automatically** turn into `typeMismatch` or `methodInvocation`.

Therefore, do not design your API error pipeline assuming `DefaultBindingErrorProcessor` handles every exception raised while ingesting external data.

### 10.4. Distinguishing binding errors from validation errors

If you invoke:

```java
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();

binder.validate();
```

errors from before and after validation coexist inside `BindingResult`. A `FieldError` with `isBindingFailure() == true` typically came from binding; an error recorded via a validator's `Errors.rejectValue(...)` typically has `isBindingFailure() == false`. If your system uses a custom `BindingErrorProcessor`, test this flag instead of assuming.

Note that `BindingResult` is not shared state across requests. Create a fresh binder/result per bind pass and avoid running validators repeatedly on the same result, which would duplicate errors.

### 10.5. JSON @RequestBody differs from property binding

In Spring MVC, `@ModelAttribute` typically flows through `WebDataBinder` to bind query/form parameters. `@RequestBody`, by contrast, is handled by an `HttpMessageConverter` such as Jackson to decode JSON into objects. JSON type errors can happen during message conversion before validation and **do not necessarily** produce a `DefaultBindingErrorProcessor` `FieldError` with `typeMismatch`.

Do not cite a `DataBinder.bind(MutablePropertyValues)` example as proof that all JSON errors flow through `DefaultBindingErrorProcessor`. Test each endpoint style directly.

## 11. Combining with Spring MVC and BindingResult

In Spring MVC forms, a controller can place `BindingResult` right after the `@ModelAttribute` argument to render error feedback:

```java
@PostMapping("/accounts")
public String submit(
        @ModelAttribute("account") AccountForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "account-form";
    }

    return "account-success";
}
```

This is a **controller snippet** assuming MVC imports, not a standalone console program. With property binding, `required`, `typeMismatch`, or `methodInvocation` errors (if generated during binding) appear in `result`. Whether the controller also runs Bean Validation or a Spring Validator depends on `@Valid`/`@Validated`, `@InitBinder`, and MVC configuration.

To require `name` during binding, configure the binder in the controller:

```java
@InitBinder("account")
void configure(WebDataBinder binder) {
    binder.setRequiredFields("name");
    binder.setAllowedFields("name", "age", "status");
}
```

This is likewise **a single method inside a controller**, with no `main`. `setAllowedFields` limits which fields clients may write; avoid binding directly onto full entities containing sensitive attributes such as `role`, `approved`, or `accountId`.

To return stable JSON error responses, extract field paths, error code lists, and resolved messages from `BindingResult`. Never return raw `FieldError#getRejectedValue()` or internal exception messages when data could be sensitive.

## 12. Thoroughly testing all three binding codes

A solid test suite verifies the **base code**, **`bindingFailure` flag**, **post-bind bean state**, and **timing of when errors appear**.

| Test | Input / configuration | Expected result |
| --- | --- | --- |
| Missing required | `setRequiredFields("name")`, omit `name` | `FieldError` on `name`, base code `required` |
| Required present | Send `name=Lan` | No `required` error |
| Type mismatch | `age=abc` with `Integer age` | `FieldError` on `age`, code `typeMismatch` |
| Numeric age | `age=20` | Binds cleanly, no type error |
| Setter failure | `status=LOCKED` and setter throws | `FieldError` on `status`, code `methodInvocation` |
| Setter success | `status=ACTIVE` | No setter invocation error |
| Validation failure | `age=16` and `validate()` with rule `age >= 18` | `FieldError` code `age.min`, `isBindingFailure=false` |
| Message resolution | Bundle has `typeMismatch.account.age` | Resolves field-specific message |
| Custom processor | `FriendlyBindingErrorProcessor` registered | Missing field uses `input.required`; both property access failures still work |
| API form | Spring MVC `@ModelAttribute` + `BindingResult` | UI/API returns structured errors without leaking internals |

### 12.1. Testing by code

To assert a base code from `FieldError` under the default resolver:

```java
FieldError error = result.getFieldError("age");
if (error == null) {
    throw new AssertionError("Expected an age error");
}

String[] codes = error.getCodes();
boolean typeMismatch = codes != null
        && java.util.Arrays.asList(codes).contains("typeMismatch");

if (!typeMismatch || !error.isBindingFailure()) {
    throw new AssertionError("Expected typeMismatch binding error");
}
```

This snippet assumes `result` already exists from binding `age=abc`. It is not a standalone file. Asserting on codes rather than comparing full default message strings keeps tests resilient across locales and versions.

### 12.2. Should you unit test DefaultBindingErrorProcessor directly?

Yes, when writing a custom processor or verifying custom codes. You can create a `BindingResult` and invoke `processMissingFieldError(...)` to inspect the `FieldError`, or pass a constructed exception to `processPropertyAccessException(...)`. Still, to verify **real integration**, passing data through `DataBinder.bind(...)` as in the example is clearest because it checks both error origin and default dispatch.

In Spring MVC, add separate tests using `MockMvc` or an equivalent HTTP client, since different input styles (`@ModelAttribute`/`@RequestBody`) go through different deserialization paths.

## 13. Common mistakes

1. **Assuming `required` is an `@NotNull` error:** `required` here comes from the binder's required-fields policy. `@NotNull` is Bean Validation and runs under a separate validation lifecycle.
2. **Assuming every invalid value is `typeMismatch`:** `"16"` converts cleanly to `Integer 16`; failing an age threshold is a validation failure.
3. **Thinking `methodInvocation` means "controller method failed":** this code refers to a property accessor during bean property binding, usually a setter.
4. **Reading `FieldError.getCode()` expecting it to always equal `typeMismatch`:** under the default resolver, the first code can be `typeMismatch.account.age`; inspect `getCodes()` as well.
5. **Catching every `PropertyAccessException` and returning HTTP 500:** collectible exceptions caught by the binder become input `FieldError`s; other exceptions need separate classification.
6. **Enabling `setIgnoreUnknownFields(false)` expecting field-name typos to become `typeMismatch`:** unknown properties follow a different path.
7. **Configuring only `MessageSource` thinking it changes when `FieldError` is created:** a message source changes display text, not error detection.
8. **Writing a custom `BindingErrorProcessor` just to reword messages:** message bundles and code resolution usually solve this without replacing the strategy.
9. **Using `rejectValue(...)` when customizing binding errors and losing the origin flag:** `rejectValue` typically does not mark `bindingFailure=true`; construct a `FieldError` directly when accuracy matters.
10. **Declaring `setRequiredFields` without reviewing other binding policies:** required fields, allowed fields, formatters, and conversions interact; test key inputs together.
11. **Returning raw exception messages when a setter throws:** messages may contain internal details or leak sensitive info. Map them to safe client messages.
12. **Applying property-binding conclusions to JSON deserialization:** `@RequestBody` uses a different conversion pipeline and does not necessarily go through `DefaultBindingErrorProcessor`.

## 14. Practice exercises

**Exercise 1.** With `setRequiredFields("name")`, submit only `age=20`. Inspect `FieldError.getField()`, the base code, and `isBindingFailure()`. Then add `name=Lan` and check whether the error disappears.

**Exercise 2.** Bind `age=abc` and `age=16` in turn onto a bean with `Integer age`. Explain why the first yields `typeMismatch`, while the second produces a rule error only once a validator is registered and invoked.

**Exercise 3.** Change `setStatus` to throw `IllegalArgumentException` on `"LOCKED"`. Explain why `methodInvocation` appears during binding even though `status` already has the valid `String` type.

**Exercise 4.** Create `messages.properties` containing `typeMismatch.account.age` and `typeMismatch`. Given `age=abc`, trace the lookup order and fallback if the field-specific key is missing.

**Exercise 5.** Register `FriendlyBindingErrorProcessor`, verify `input.required`, and confirm `typeMismatch` and `methodInvocation` still work. Explain why `bindingFailure=true` should be preserved for binding errors.

**Exercise 6.** Design an `@ModelAttribute` endpoint returning HTTP 400 with stable error codes on invalid input without leaking sensitive rejected values. Contrast tests for form/query input versus JSON `@RequestBody`.

**Summary:** `DefaultBindingErrorProcessor` turns **missing required fields** into `required` and **binding property-access exceptions** into the corresponding `PropertyAccessException` code: `typeMismatch` or `methodInvocation`. `BindingResult` stores the outcome; `MessageCodesResolver` generates prioritized codes; `MessageSource` turns them into messages; `Validator` checks custom rules afterward when invoked.

## Official references

- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — DefaultBindingErrorProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [Spring Framework — BindingErrorProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingErrorProcessor.html)
- [Spring Framework — DefaultMessageCodesResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework — MethodInvocationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/MethodInvocationException.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
