# Relationship between DataBinder, BindingResult, and Validator in Spring Framework

## 1. Three components solving three distinct responsibilities

When an application receives external data (for example, form fields), it needs to **populate the data into a Java object**, **check whether the data is valid**, and then **return errors to the caller**. Spring Framework separates those tasks into three roles:

| Component | Primary responsibility | Key thing to remember |
| --- | --- | --- |
| **DataBinder** (`org.springframework.validation.DataBinder`) | Populates input values into a target object, performs type conversion, configures `Validator`s, and manages results | `bind(...)` does not automatically call `validate()` when used manually |
| **Validator** (`org.springframework.validation.Validator`) | Checks validity rules of an object and records violations through the `Errors` interface | Does not convert types itself, does not directly handle HTTP, and does not create `BindingResult` itself |
| **BindingResult** (`org.springframework.validation.BindingResult`) | Holds errors from **binding/type conversion** and **validation**, along with field details and rejected values | `BindingResult` extends `Errors`; allows querying `FieldError`, `ObjectError`, `hasErrors()` |

Thinking in terms of ownership: **DataBinder coordinates binding and validation; Validator evaluates the object; BindingResult accumulates error results from both stages.** `Validator.validate(target, errors)` receives an `Errors` instance supplied by the caller; in the normal `DataBinder` flow, that `Errors` object is the binder's `BindingResult`.

~~~text
Input data (property name -> value)
                 |
                 v
          DataBinder.bind(...)
                 |  - locate property / convert type
                 |  - update target object
                 |  - record binding errors if any
                 v
         Java object (target)
                 |
          DataBinder.validate()  [when called]
                 |
                 v
          Validator.validate(target, Errors)
                 |  - check rules
                 |  - reject(...) / rejectValue(...)
                 v
       DataBinder.getBindingResult()
                 |
                 v
        BindingResult: binding errors + validation errors
                 |
                 v
     Controller / service / form view / API response
~~~

Important point: this diagram shows the **logical flow**, not that every application manually instantiates `DataBinder`. In Spring MVC, the framework uses `WebDataBinder` (which extends `DataBinder`) to perform most of this work.

## 2. What does DataBinder do in each stage?

### 2.1. Binding and type conversion

For a JavaBean object with properties `name` (String) and `age` (Integer), inputs may arrive as `name=Lan` and `age=20` in string form. `DataBinder.bind(PropertyValues)` locates the corresponding property paths, uses the configured conversion mechanism to convert `"20"` to `Integer(20)`, and calls the setter. It can also work with nested paths if the configuration and object model allow it.

If `age=abc`, the conversion error is typically recorded as a `FieldError` with a base code like `typeMismatch`; the target value does not become a valid number. **Binding does not mean validation**: even when type conversion succeeds, `age=-5` can still violate business rules. Moreover, an error on one field does not necessarily prevent other fields from being bound successfully; the object may be partially updated.

In addition to setter assignment (property binding), modern Spring versions also support **constructor binding** to instantiate objects from constructor parameters. Both binding styles share the same core idea: turn input data into an object and record errors in `BindingResult`; object construction and writable properties differ.

### 2.2. Configuring validators and explicitly running validation

When using `DataBinder` directly:

1. Create a binder for the target object: `new DataBinder(target, "objectName")`.
2. Restrict allowed fields when accepting untrusted data: `setAllowedFields(...)`.
3. Configure validators: `setValidator(...)` or `addValidators(...)`.
4. Execute binding: `bind(propertyValues)`.
5. **Explicitly call** `validate()` to run the configured validators.
6. Retrieve the same result object: `getBindingResult()`.

`setValidator(...)` only configures the validator; it does not run validation. Conversely, `validate()` is not responsible for reading requests or converting strings to numbers. A binder can have multiple validators compatible with the target type. Understand each validator's specific rules to avoid recording duplicate errors with the same meaning for a single field.

## 3. Where does Validator record errors?

Spring's `Validator` defines two methods:

- `supports(Class<?> clazz)`: determines whether this validator applies to that target type. You can use `TargetClass.class.isAssignableFrom(clazz)` when subclasses should be supported.
- `validate(Object target, Errors errors)`: applies rules and records errors, e.g., `errors.rejectValue("name", "name.required")` or `errors.reject("order.invalid")`.

`rejectValue` records an error on a specific field; `reject` records an object-level error when a condition involves multiple fields. `ValidationUtils.rejectIfEmptyOrWhitespace` is a utility for checking blank fields. Avoid throwing exceptions for routine input mistakes if the caller expects detailed error reporting via `BindingResult`.

**Errors** is the error recording/reading interface that validators depend on. **BindingResult** extends `Errors` and adds binding-specific details such as the target object, field values, rejected input values, suppressed fields excluded from binding, and form model creation support. Thus, validators normally accept `Errors`, while result-handling code uses `BindingResult`.

Distinguishing two common error groups:

| Situation | Detection source | Representation |
| --- | --- | --- |
| `age=abc` when field is `Integer` | DataBinder / type conversion | `FieldError`, usually carrying code `typeMismatch` |
| `age=16` converted to number successfully, but minimum age is 18 | Validator | `FieldError` via `rejectValue("age", "age.min")` |
| Name omitted or whitespace-only | Validator | `FieldError` via `rejectIfEmptyOrWhitespace` |
| Two fields have an invalid relationship (e.g., start date after end date) | Validator | Can use an object-level error via `reject(...)` |

Both binding errors and validation errors are read from **the same `BindingResult`**. `getFieldErrors("age")` retrieves errors for the field; `getGlobalErrors()` retrieves object-level errors; `hasErrors()` and `getErrorCount()` report overall status. `FieldError.getRejectedValue()` helps show the rejected value when appropriate, though that data may contain sensitive information and should not be logged indiscriminately. Error codes can be resolved into localized messages via `MessageSource`.

## 4. Java 17+ example: binding failure and validation contributing errors together

The following example runs **without a web server**. It simulates a registration form: name must not be blank, age must be at least 18. The input intentionally supplies an invalid type for age and a disallowed property to show all three components' roles.

Create the structure:

~~~text
binding-demo/
  pom.xml
  src/main/java/BindingFlowDemo.java
~~~

**pom.xml** (Spring Framework 6.2.x; in a Spring Boot project managing Spring versions, use Boot's dependency management instead of forcing versions manually):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>binding-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/BindingFlowDemo.java**:

~~~java
import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BindingFlowDemo {

    public static final class RegistrationForm {
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

    public static final class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");

            // If age already failed type conversion, avoid recording an extra age error.
            if (!errors.hasFieldErrors("age")
                    && (form.getAge() == null || form.getAge() < 18)) {
                errors.rejectValue("age", "age.min");
            }
        }
    }

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        binder.setAllowedFields("name", "age");
        binder.setValidator(new RegistrationValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "  ");
        input.add("age", "not-a-number");
        input.add("isAdmin", "true");

        binder.bind(input);     // Convert types/bind properties and record binding errors.
        binder.validate();      // Run RegistrationValidator, record validation errors.

        BindingResult result = binder.getBindingResult();
        System.out.println("nameBlank=" + form.getName().isBlank());
        System.out.println("age=" + form.getAge());
        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());
        System.out.println("nameError=" + result.hasFieldErrors("name"));
        System.out.println("ageError=" + result.hasFieldErrors("age"));
        System.out.println("suppressed="
                + Arrays.toString(result.getSuppressedFields()));
    }
}
~~~

Run from the directory containing `pom.xml` (requires Java 17+ and Maven installed):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=BindingFlowDemo
~~~

Standard output of the program (excluding Maven's own log messages):

~~~text
nameBlank=true
age=null
hasErrors=true
errorCount=2
nameError=true
ageError=true
suppressed=[isAdmin]
~~~

Explanation of **each cause**, rather than just looking at `hasErrors=true`:

1. `name` is bound as a two-space string; `RegistrationValidator`'s rule detects that the name is effectively empty and creates one error.
2. `age` fails to convert from `"not-a-number"` to `Integer`; the binder creates one `typeMismatch` error and the `age` property remains `null`.
3. The validator checks `errors.hasFieldErrors("age")` before evaluating age, so it does not create a duplicate `age.min` error for a value that already failed type conversion. In total there are **two errors**.
4. `isAdmin` is ignored because it is not in `setAllowedFields`. The field name appears in `getSuppressedFields()`; a blocked field does **not automatically** become a `FieldError`. The application can explicitly decide whether to reject the entire request when suppressed fields are encountered.
5. If you replace the input with `name=Lan`, `age=20`, and omit `isAdmin`, then run both `bind()` and `validate()`, the result will have no errors under the example's rules.

The example uses a mutable JavaBean because setter binding makes the binding step easy to observe. With constructor binding, object instantiation differs, yet the same separation of **binding → validation → error result** still applies.

## 5. Relationship in Spring MVC

With `@ModelAttribute`, Spring MVC normally creates or retrieves the model object, uses `WebDataBinder` to populate request data into the object, runs validation when an appropriate trigger is present (such as `@Valid` or `@Validated`), and then provides `BindingResult` to the controller. `WebDataBinder` is the web-specific variant of `DataBinder`, while `BindingResult` and `Validator` retain the same roles.

The snippet below **illustrates inside a controller** (assuming `RegistrationForm` and `RegistrationValidator` are defined classes, along with a form view named `register-form`; this is not a standalone MVC application):

~~~java
@InitBinder("registrationForm")
void configureRegistration(WebDataBinder binder) {
    binder.setAllowedFields("name", "age");
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

Here:

- `@InitBinder` configures the binder for the model attribute: allowlisting fields and adding a validator. In a real application, you may also need to configure `ConversionService`, formatters, or converters so request data converts properly.
- `@Validated` triggers validation on the model attribute after binding in the MVC flow. `@Valid` (Jakarta Validation) is also supported by Spring MVC; Bean Validation execution requires a compatible provider on the classpath. `@Valid` alone does not replace configuring or calling `validate()` when using `DataBinder` manually outside MVC.
- **The `BindingResult` parameter must immediately follow the model attribute it describes.** If `Model`, `HttpServletRequest`, or another parameter is placed in between, Spring will not associate the result as intended.
- If `BindingResult` is not declared to handle errors in the controller, modern Spring MVC typically reports failures via exceptions such as `MethodArgumentNotValidException`; method validation scenarios may use `HandlerMethodValidationException`. Details depend on parameter type and Spring version.
- For JSON `@RequestBody`, reading JSON is typically handled by `HttpMessageConverter`/Jackson first; do not assume it goes through the same form-field binding mechanism as `@ModelAttribute`.

### Spring Validator and Jakarta Bean Validation

These two common validation approaches can complement each other, though they are not the same API:

| Spring Validator | Jakarta Bean Validation |
| --- | --- |
| Write a class implementing `supports(...)` and `validate(Object, Errors)` | Declare constraints like `@NotBlank`, `@Min`, `@Size` on the model |
| Records errors through Spring's `Errors` | Provider (e.g., Hibernate Validator) evaluates constraints; Spring has an adapter integrating errors into the MVC flow |
| Convenient for multi-field rules or custom checks | Convenient for declarative constraints reusable across many places |

In Spring MVC, global validators or validators added via `@InitBinder` can participate together. Avoid running the same rule twice, and remember that type conversion errors may already exist **before** the validator inspects the object.

## 6. Reading BindingResult to respond accurately

Common queries:

~~~java
if (result.hasErrors()) {
    for (var fieldError : result.getFieldErrors()) {
        System.out.println(fieldError.getField()
                + " -> " + fieldError.getCode());
    }
    for (var globalError : result.getGlobalErrors()) {
        System.out.println(globalError.getCode());
    }
}
~~~

This is an **illustrative snippet assuming a `result` variable is already in scope**, not a standalone runnable program. For form views, keep `BindingResult` alongside the model attribute to render field-specific errors. For REST APIs, map `FieldError` and `ObjectError` instances into a clear response structure; avoid sending stack traces or sensitive data. Do not equate `getDefaultMessage()` with a localized message in all cases: Spring has an error-code and `MessageSource` system for resolving messages.

## 7. Common mistakes and safety principles

1. **Calling only `bind()` and assuming it validated:** binding primarily handles value assignment and type conversion. When using the binder manually, call `validate()` if rules need checking.
2. **Calling only the validator while ignoring binding errors:** the object may not have received certain fields due to type conversion errors. Always inspect the full `BindingResult`, and consider `hasFieldErrors(field)` to avoid duplicate errors or faulty logic.
3. **Equating `BindingResult` with `Validator`:** the validator determines violations, BindingResult accumulates violations; calling `getBindingResult()` does not run validation by itself.
4. **Using `@Valid` but placing `BindingResult` in the wrong position:** in Spring MVC, the result must immediately follow the validated parameter if you want to handle errors in the same method.
5. **Binding requests directly onto an entity containing sensitive fields:** setter binding can update unexpected properties (mass assignment). Prefer dedicated DTOs or constructor binding, and restrict `setAllowedFields(...)` when property binding is needed; do not rely on `setDisallowedFields(...)` as the primary defense.
6. **Ignoring blocked fields:** check `getSuppressedFields()` if policy requires rejecting payloads containing fields outside the allowlist; suppressed fields do not automatically make `hasErrors()` true.
7. **Assuming every error comes from a validator:** `typeMismatch` and binding/conversion errors can be produced by the binder. Distinguish the error source when displaying correction hints and writing tests.
8. **Coupling `Validator` tightly to HTTP:** the Spring `Validator` contract needs neither a request nor a controller; validate on objects and `Errors` for reusability and independent testing.

To inspect the flow yourself, place breakpoints sequentially at `bind(...)`, `validate(...)`, and `getBindingResult()`. Observe the object before/after binding and the error list before/after validation; seeing only a `typeMismatch` error right after `bind()` is the clearest evidence of this separation of responsibilities.

## References

- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Configuring a DataBinder: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring MVC — @InitBinder: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
