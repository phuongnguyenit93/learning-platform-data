# DataBinder: validate With or Without Validation Hints

## 1. Understanding the Problem

Spring Framework provides two methods on `org.springframework.validation.DataBinder`:

```java
binder.validate();                 // No hints passed.
binder.validate("strict");         // Custom hint understood by the application.
binder.validate(Publish.class);    // Class hint, commonly used as a validation group.
```

Both overloads request running registered validators on the binder's target and placing errors into `BindingResult`. The difference lies in **how Spring invokes each validator**: passing no hints uses the basic validation method; passing non-empty hints allows Spring to forward them to a `SmartValidator`.

Imagine a registration form: basic rules require a sufficiently long name and a valid email; a publishing mode additionally requires an email address from a corporate domain. The basic checker always runs, while a smart validator can accept the `"strict"` hint to enforce the extra requirement. `DataBinder` itself **does not understand** the business meaning of `"strict"`.

Keep four ideas clear:

1. `DataBinder` **coordinates** binding and validation.
2. A regular `Validator` only has `validate(Object, Errors)`.
3. `SmartValidator` additionally supports `validate(Object, Errors, Object... hints)`.
4. Hints are only extra metadata; their effect depends on the invoked validator.

## 2. Participating Components

`DataBinder` accepts a Java target and object name, manages binding errors, and lets you register one or more Spring validators:

```java
DataBinder binder = new DataBinder(form, "registration");
binder.addValidators(new RegistrationValidator());
binder.validate();
BindingResult result = binder.getBindingResult();
```

This is an illustrative snippet inside a method where `form` and a valid `RegistrationValidator` already exist. `"registration"` is the object name used in `BindingResult`, not necessarily the class name. `DataBinder` can be used outside Spring MVC; `WebDataBinder` in web applications extends this mechanism.

### Regular Validator

`org.springframework.validation.Validator` has the basic contract:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

`supports(Class<?>)` determines which target classes can be validated. `validate(Object, Errors)` evaluates the object and calls `errors.rejectValue(...)` for field errors or `errors.reject(...)` for object-wide errors. It has no hint parameter.

### SmartValidator

`org.springframework.validation.SmartValidator` extends `Validator`, adding an overload:

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

This is the condensed core signature; Spring versions may include additional helper methods. A class implementing `SmartValidator` is still a `Validator` and must also define the basic validation behavior. `Object...` is varargs syntax: callers can pass multiple objects, such as strings, enums, or classes representing validation groups.

### BindingResult

`DataBinder.validate(...)` returns **`void`**, not a boolean or a set of violations. To read the outcome:

```java
BindingResult result = binder.getBindingResult();
boolean invalid = result.hasErrors();
int totalErrors = result.getErrorCount();
int fieldErrors = result.getFieldErrorCount();
int globalErrors = result.getGlobalErrorCount();
```

`BindingResult` can hold data-conversion errors from the binding step as well as errors recorded by validators. `DataBinder`'s result differs from the `Set<ConstraintViolation<T>>` type returned by the Jakarta Validation API; when Spring integrates a Jakarta provider, an adapter translates violations into Spring errors.

## 3. How validate() Without Hints Works

Call:

```java
binder.validate();
```

Spring takes the target and `BindingResult` and iterates over the configured validators. For **every validator**, even classes that implement `SmartValidator`, the `DataBinder.validate()` overload invokes the basic method:

```java
validator.validate(target, bindingResult);
```

This means:

- A regular `Validator` runs all the rules it defines.
- A `SmartValidator` runs the rules in its `validate(Object, Errors)` method.
- No hints are passed to the three-parameter method of `SmartValidator`.
- Every validator writes errors into the shared `BindingResult`; you can inspect `getFieldErrors()` and `getGlobalErrors()`.
- If no validator is registered, calling it does not invent new rules. An annotation on a model also does not execute automatically merely because a binder exists.

**No hint does not mean skipping validation.** `validate()` still runs the default rules of registered validators.

## 4. How validate(Object... hints) Works

Examples:

```java
binder.validate("strict");
binder.validate(Publish.class);
binder.validate(Default.class, Publish.class);
```

`Publish` must be defined by the application; in Jakarta examples, `Default` is `jakarta.validation.groups.Default`.

For Spring Framework 6.1, the overload selection mechanism can be represented by the following pseudocode:

```java
for (Validator validator : validatorsToApply) {
    if (hints.length > 0 && validator instanceof SmartValidator smart) {
        smart.validate(target, bindingResult, hints);
    } else {
        validator.validate(target, bindingResult);
    }
}
```

This is **pseudocode**, not the full source code: Spring's implementation also retrieves the target, checks state, and processes the hints array with internal helpers. The key takeaway is that only **`SmartValidator`** receives non-empty hints; a regular `Validator` is still invoked as usual.

| Call | Regular Validator | SmartValidator |
| --- | --- | --- |
| `binder.validate()` | `validate(target, errors)` | `validate(target, errors)` |
| `binder.validate("strict")` | `validate(target, errors)` | `validate(target, errors, "strict")` |
| `binder.validate(Publish.class)` | `validate(target, errors)` | `validate(target, errors, Publish.class)` |
| `binder.validate(new Object[0])` | `validate(target, errors)` | `validate(target, errors)` because hints are empty |

Why does `validate(new Object[0])` behave like `validate()`? In the varargs overload, Spring only takes the `SmartValidator` branch when the hints array is **non-empty**. Even so, writing `validate()` makes your intent clearer when you do not need hints.

**Core note:** DataBinder does not interpret, filter, or assign default meaning to `"strict"`, `Publish.class`, or any enum. A `SmartValidator` may understand the hint, ignore it, or use it to select a different set of rules. The Javadoc explicitly states that hints may be ignored by the target validator.

## 5. Standalone Java 17 Example: Regular Validator and SmartValidator

This example has two Spring validators and needs no Spring Boot, HTTP server, or Jakarta Validation provider:

- `BasicEmailValidator implements Validator`: checks that the email contains an `@` character.
- `PolicyValidator implements SmartValidator`: always checks that the username is at least three characters long; if `"strict"` is received, it also checks that the email ends with `@example.org`.

We use a **fresh binder each time** to compare both modes without accumulating errors.

Structure:

```text
databinder-hints/
├── pom.xml
└── src/main/java/demo/DataBinderHintsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>databinder-hints</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DataBinderHintsDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.List;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.SmartValidator;
import org.springframework.validation.Validator;

public final class DataBinderHintsDemo {

    public static final class Signup {
        private final String username;
        private final String email;

        public Signup(String username, String email) {
            this.username = username;
            this.email = email;
        }

        public String getUsername() {
            return username;
        }

        public String getEmail() {
            return email;
        }
    }

    // Basic validator: cannot receive validation hints.
    public static final class BasicEmailValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;
            if (form.getEmail() == null
                    || !form.getEmail().contains("@")) {
                errors.rejectValue("email", "email.invalid");
            }
        }
    }

    // SmartValidator with an overload supporting hints.
    public static final class PolicyValidator implements SmartValidator {
        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;
            if (form.getUsername() == null
                    || form.getUsername().length() < 3) {
                errors.rejectValue("username", "username.tooShort");
            }
        }

        @Override
        public void validate(
                Object target, Errors errors, Object... hints) {
            // Explicitly apply basic rules in hint mode.
            validate(target, errors);

            Signup form = (Signup) target;
            boolean strict = Arrays.asList(hints).contains("strict");

            if (strict
                    && (form.getEmail() == null
                        || !form.getEmail().endsWith("@example.org"))) {
                errors.rejectValue("email", "email.domain");
            }
        }
    }

    private static DataBinder newBinder(Signup signup) {
        DataBinder binder = new DataBinder(signup, "signup");
        binder.addValidators(
            new BasicEmailValidator(),
            new PolicyValidator()
        );
        return binder;
    }

    private static void show(String label, BindingResult result) {
        List<String> codes = result.getFieldErrors().stream()
            .map(error -> error.getCode())
            .sorted()
            .toList();
        System.out.println(label + ": " + codes);
    }

    public static void main(String[] args) {
        Signup input = new Signup("Li", "invalid");

        DataBinder normal = newBinder(input);
        normal.validate();
        show("no hints", normal.getBindingResult());

        DataBinder strict = newBinder(input);
        strict.validate("strict");
        show("strict", strict.getBindingResult());

        DataBinder unknown = newBinder(input);
        unknown.validate("unknown");
        show("unknown hint", unknown.getBindingResult());
    }
}
```

Run from the directory containing `pom.xml`, with JDK 17+ and Maven installed:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DataBinderHintsDemo
```

Lines **printed by the program** (excluding any Maven/Spring environment logs):

```text
no hints: [email.invalid, username.tooShort]
strict: [email.domain, email.invalid, username.tooShort]
unknown hint: [email.invalid, username.tooShort]
```

Interpreting each case:

1. `BasicEmailValidator` runs in all three passes, because with or without hints it only implements regular `Validator`. `"invalid"` does not contain `@`, producing `email.invalid`.
2. `PolicyValidator.validate(Object, Errors)` checks that `"Li"` is shorter than three characters and produces `username.tooShort`.
3. `normal.validate()` calls the basic method of `PolicyValidator`, so it does **not** produce `email.domain`.
4. `strict.validate("strict")` calls the `SmartValidator` overload. In the code, the overload **explicitly delegates to the basic method**, then applies the email domain rule and produces `email.domain`.
5. `unknown.validate("unknown")` still passes a hint to `SmartValidator`, but the validator does not recognize it and adds no extra error.
6. `sorted()` sorts error codes alphabetically so the output has a deterministic order. These are error codes recorded in `BindingResult`, not messages interpolated from `MessageSource`.

### A Very Common Bug When Writing Your Own SmartValidator

In the overload:

```java
@Override
public void validate(Object target, Errors errors, Object... hints) {
    validate(target, errors);
    // Additional checks based on hints.
}
```

The call `validate(target, errors)` is **explicitly added by the author**. Spring does not automatically call both the basic method and the hint-accepting method of the same `SmartValidator`. If you want strict mode to **add to** default rules, reuse them as shown above or extract a shared internal helper method. If a hint's purpose is to **switch rule sets**, you can choose different logic; there is no rule that passing hints always yields more errors.

## 6. Validation Hints When Integrating Jakarta Validation Groups

A different scenario from the custom `"strict"` string is **Bean Validation groups** in Jakarta Validation. Spring provides `LocalValidatorFactoryBean` and `SpringValidatorAdapter` to bridge a Jakarta Validation provider with Spring's `SmartValidator`/`BindingResult` model.

Example DTO with group constraints:

```java
import jakarta.validation.constraints.NotBlank;

interface Publish {}

record Article(
    @NotBlank String title,
    @NotBlank(groups = Publish.class) String slug
) {}
```

This is a data-model snippet, not a standalone program. `@NotBlank` on `title` belongs to the `jakarta.validation.groups.Default` group (no groups declared); `@NotBlank` on `slug` belongs only to the `Publish` group.

If a `LocalValidatorFactoryBean` has been initialized, a compatible provider is present, and the binder registers that adapter:

```java
DataBinder binder = new DataBinder(article, "article");
binder.setValidator(localValidatorFactoryBean);

binder.validate();                        // Default.
binder.validate(Publish.class);           // Publish.
binder.validate(
    jakarta.validation.groups.Default.class,
    Publish.class
);                                        // Default + Publish.
```

**This is an API illustration**, assuming `article` and `localValidatorFactoryBean` already exist, separate from the Java SE example in section 5. When comparing calls, create independent binders so results do not accumulate.

The differences:

- `DataBinder.validate()` calls the adapter's basic validation method, corresponding to how the Jakarta provider validates the default group.
- `DataBinder.validate(Publish.class)` forwards the group class hint to the adapter and provider, requesting checks for constraints in `Publish`. Selecting one group **does not automatically include `Default`** merely because default constraints exist on the DTO.
- `DataBinder.validate(Default.class, Publish.class)` explicitly validates both groups at that entry point (or use group inheritance/sequences if designed that way).
- `DataBinder.validate("strict")` in the earlier example was purely a custom convention of `PolicyValidator`. Do not pass arbitrary strings into the Jakarta adapter expecting them to become groups.

The Java SE example in section 5 **does not use a Jakarta provider**, so `"strict"` is interpreted entirely by Java code inside `PolicyValidator`. With Spring Boot 3, the common dependency for Jakarta Validation is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This dependency belongs inside a project with the corresponding Spring Boot parent/BOM. The starter typically provides the Jakarta Validation API and a compatible Hibernate Validator provider; `DataBinder` itself is not that provider.

## 7. How Do Hints Affect Multiple Validators?

Suppose a binder registers:

```java
binder.addValidators(new BasicEmailValidator(), new PolicyValidator());
binder.validate("strict");
```

General sequence:

1. `BasicEmailValidator` is called via `validate(target, errors)`; it has no knowledge of the `"strict"` hint.
2. `PolicyValidator` is called via `validate(target, errors, "strict")` because it is a `SmartValidator`.
3. Both write errors into **the same `BindingResult`**.
4. `binder.getBindingResult().hasErrors()` reflects the total error count, which may include binding errors from earlier.

If you register a `LocalValidatorFactoryBean` for Jakarta groups alongside a regular Spring validator, passing `Publish.class` only affects groups on the adapter; the regular Spring validator **still evaluates its rules**. Thus a group is not an “off switch for all other validators”.

### addValidators and setValidator

- `addValidators(...)` appends validators to the binder's list.
- `setValidator(...)` sets the primary validator, which can replace the previously configured list per Spring's contract.
- Spring checks target compatibility via `supports(Class<?>)` when registering validators. Registering the wrong target type is a configuration error, not a way to filter validators via hints.

If you need to control ordering or validator exclusion, configure the binder/invocation flow according to your Spring version; do not assume hints act as a list of validator names to execute.

## 8. Reusing DataBinder and Accumulating Errors

A common mistake in experiments is calling sequentially:

```java
binder.validate();
binder.validate("strict");
System.out.println(binder.getBindingResult().getErrorCount());
```

The same `BindingResult` can retain errors from both passes. For example, `errors.rejectValue(...)` can add duplicate errors. The final count does not represent strict mode alone. To compare, initialize a fresh binder per case as in the runnable example.

This also applies when **binding/conversion** errors occurred before validation: `validate(...)` does not clear `FieldError` entries caused by failed type conversions. `hasErrors()` and `getErrorCount()` do not count only hint-triggered constraints.

A `DataBinder` must have a valid target to validate. Operations may be rejected if no target is present; if a validator calls `rejectValue("someField", ...)`, the field name must correspond to a property Spring can access. Hints cannot fix an invalid field path, wrong target type, or misconfigured validator.

## 9. Connection to Spring MVC: @Valid and @Validated

In Spring MVC, `WebDataBinder` extends `DataBinder`. When the framework processes an `@ModelAttribute` or `@RequestBody` parameter annotated to trigger validation, Spring can perform validation after binding and populate `BindingResult`.

Example selecting a Jakarta group:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/articles")
String publish(
        @Validated(Publish.class)
        @ModelAttribute("article") ArticleForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "article-form";
    }
    return "article-created";
}
```

This is an **illustrative snippet inside a controller** where `ArticleForm` and `Publish` are defined. It is not a standalone Java program. `BindingResult` must immediately follow the validated parameter so the controller can handle errors inline.

In Spring MVC's Jakarta Validation configuration, `@Validated(Publish.class)` supplies the group hint to the compatible validator. `@Valid` typically requests validation for the default group without specifying a custom business group. When the controller already has validation triggered automatically by the framework, do not call `binder.validate(...)` again just to collect the same errors twice.

Note that **controller argument validation** and **method validation via AOP** are not a single execution path. `@Validated` on a service can participate in method validation via a proxy; calling `DataBinder.validate(...)` manually does not create proxies or validate other method invocations.

## 10. Common Pitfalls and Remedies

| Symptom | Cause to Check | Remedy |
| --- | --- | --- |
| Passed `"strict"` but no new errors | Regular validator ignores hints; SmartValidator did not handle the hint | Check validator type and implemented overload |
| `validate()` still yields errors | Normal behavior when validators are registered | Inspect `BindingResult` and default rules |
| `Publish` group skips default constraints | `Publish` does not implicitly include `Default` | Pass multiple groups or design group inheritance |
| Passed string `"Publish"` instead of `Publish.class` | Jakarta Validation groups use classes | Use actual group class and compatible adapter |
| Hints drop basic rules in SmartValidator | Hint overload does not auto-call basic overload | Reuse shared logic when adding rules |
| Calling validate twice inflates error count | Reusing `BindingResult` on the same binder | Separate binders/test cases per run |
| Annotations present but no errors appear | Provider/adapter/entry point not active | Check dependencies, Bean Validation setup, and call path |
| Spring errors have codes without messages | `MessageSource` or default message not configured | Configure messages for the error codes |
| Expecting `validate(...)` to return boolean | API returns `void` | Check `getBindingResult().hasErrors()` |
| Validation fails when binder has no target | Valid target not initialized | Create target and configure validators before calling |

Useful design rules:

- Need only default rules: prefer basic `Validator` and `binder.validate()`.
- Need context-dependent rules: use `SmartValidator` with a clearly documented hints contract.
- Need standard annotation groups: use Jakarta Validation groups with a compatible provider/adapter and `Class<?>` hints.
- Avoid using hints as an authorization mechanism: validation mode does not replace authorization or business access control.
- When testing modes, verify the set of error codes with a fresh binder per mode instead of merely counting errors on the same binder.

## 11. Self-Check Questions

1. What does `binder.validate("strict")` do if only a regular `Validator` is registered?
2. For a `SmartValidator`, which overload does Spring invoke when calling `binder.validate()`?
3. If the hint-accepting overload does not call the basic logic, why might strict mode lose a rule?
4. How does `validate(new Object[0])` differ from and resemble `validate()`?
5. What is `Publish.class`, and why does it differ from the string `"Publish"` in Jakarta groups?
6. Why does `DataBinder.validate(Publish.class)` not automatically force a regular Spring `Validator` to skip its rules?
7. After validation, how do you retrieve the errors and distinguish binding errors from validation errors?

**Remember:** `validate()` uses the basic validation method; `validate(hints...)` only passes **non-empty** hints to `SmartValidator`, while regular validators still run as before. How far a hint takes effect is the responsibility of the receiving validator. With the Jakarta Validation adapter, class hints typically represent validation groups.

## References

- Spring Framework — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework — SmartValidator Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/SmartValidator.html
- Spring Framework — SpringValidatorAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Jakarta Validation Specification: https://jakarta.ee/specifications/bean-validation/
