# SmartValidator and Passing Validation Hints in Spring Framework

## 1. Why Is `SmartValidator` Needed?

`org.springframework.validation.Validator` defines `supports(Class<?>)` and `validate(Object, Errors)`: the validator identifies supported object types and validates data, recording errors in `Errors`. However, one object sometimes needs **different rule sets depending on context**. For example, on the same `RegistrationForm`, saving a draft only requires a valid email, whereas submitting a final registration also requires a phone number. That is when validation hints are needed.

`org.springframework.validation.SmartValidator` extends `Validator`, adding the ability to accept hints: `validate(Object target, Errors errors, Object... validationHints)`. In modern Spring applications, `SmartValidator` also includes an overload for `validateValue` to validate a single property value in certain contexts; the focus of this article is `validate` with hints.

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

This is a simplified core signature for conceptual learning; the actual interface declaration may include additional default methods depending on the Spring Framework version. `Object...` is varargs, so callers can pass 0, 1, or many hints. Hints are **not** a list of errors and do not automatically become rules: the validator implementation decides how to interpret them.

| Aspect | `Validator` | `SmartValidator` |
| --- | --- | --- |
| Type support check | `supports(Class<?>)` | Inherits `supports` |
| Default validation | `validate(Object, Errors)` | Inherited and must remain implemented |
| Context-aware validation | No hint parameter in the base interface | `validate(Object, Errors, Object...)` |
| Jakarta Bean Validation integration | Hand-written validator possible | Spring's `LocalValidatorFactoryBean`/adapter can translate hints into validation groups |
| Error management | `Errors`/`BindingResult` | Still `Errors`/`BindingResult`; hints do not alter the error-recording contract |

## 2. What Are Validation Hints?

A validation hint is a token passed by the caller to select rules or rule groups. Hints can be `Class<?>` objects representing a **Jakarta Bean Validation group**, or other objects understood by an application's custom `SmartValidator`. There is no universal rule requiring every hint to be a class.

Example processing flow:

```text
Save-draft request
    -> @Validated(Draft.class)
    -> SmartValidator.validate(form, errors, Draft.class)
    -> Run rules belonging to Draft

Final-submit request
    -> @Validated(Submit.class)
    -> SmartValidator.validate(form, errors, Submit.class)
    -> Run rules belonging to Submit
```

This is a conceptual diagram: how Spring forwards hints depends on the validation path, annotations, binder, and actual configured validator. Spring's `@Validated` supports declaring validation groups; Jakarta's `@Valid` triggers default validation and **does not directly carry a group list like `@Validated`**.

## 3. Custom `SmartValidator` Example in Java 17+

To observe the mechanism clearly without a Jakarta Bean Validation provider, the example below implements `SmartValidator` directly and uses marker interfaces as hints. File `SmartValidatorDemo.java`:

```java
import java.util.Arrays;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.SmartValidator;
import org.springframework.validation.ValidationUtils;

public class SmartValidatorDemo {
    interface Draft {}
    interface Submit {}

    public static class RegistrationForm {
        private String email;
        private String phone;

        public RegistrationForm(String email, String phone) {
            this.email = email;
            this.phone = phone;
        }

        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
        public String getPhone() { return phone; }
        public void setPhone(String phone) { this.phone = phone; }
    }

    public static class RegistrationValidator implements SmartValidator {
        @Override
        public boolean supports(Class<?> clazz) {
            return RegistrationForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            validate(target, errors, Draft.class);
        }

        @Override
        public void validate(Object target, Errors errors, Object... hints) {
            RegistrationForm form = (RegistrationForm) target;
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "email.required");
            boolean submit = Arrays.asList(hints).contains(Submit.class);
            if (submit && (form.getPhone() == null
                    || form.getPhone().isBlank())) {
                errors.rejectValue("phone", "phone.required");
            }
        }
    }

    private static void run(String label, Object... hints) {
        RegistrationForm form = new RegistrationForm("user@example.com", "");
        var errors = new BeanPropertyBindingResult(form, "registrationForm");
        SmartValidator validator = new RegistrationValidator();
        validator.validate(form, errors, hints);
        System.out.println(label + ": " + errors.getErrorCount());
        System.out.println("phone error: " + errors.hasFieldErrors("phone"));
    }

    public static void main(String[] args) {
        run("draft", Draft.class);
        run("submit", Submit.class);
    }
}
```

Stdout output:

```text
draft: 0
phone error: false
submit: 1
phone error: true
```

Explanation: `supports` identifies the form type; the basic `validate` method delegates to a default `Draft` policy. The hints overload always checks email, and checks phone only when `Submit.class` is present. When `Draft.class` is passed, email is valid and phone is optional. When `Submit.class` is passed, empty phone produces one field error.

This code is independent of Spring MVC and Spring Boot, though it **requires Spring Framework JARs**. You can compile and run it on Java 17+ if your project declares `spring-context` or modules containing `org.springframework.validation` with matching dependencies. For example, with a resolved dependency classpath in `SPRING_CP` on Linux/macOS:

```bash
javac -cp "$SPRING_CP" SmartValidatorDemo.java
java -cp ".:$SPRING_CP" SmartValidatorDemo
```

On Windows use `;` as the classpath separator. It will not run with bare `javac SmartValidatorDemo.java` when Spring JARs are absent.

**Design note:** `SmartValidator` is a contract, so implementations can choose different defaults. The example intentionally treats `validate(target, errors)` as the `Draft` policy; in real applications, define and document this default clearly so constraints are not accidentally skipped when callers pass no hints.

## 4. Validation Groups with Jakarta Bean Validation

In many applications, hints are marker classes representing Jakarta Bean Validation groups (`jakarta.validation.groups.Default`, or user-defined interfaces). Constraint annotations select which groups apply.

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

interface Draft {}
interface Submit {}

public class RegistrationRequest {
    @NotBlank(groups = {Draft.class, Submit.class})
    @Email(groups = {Draft.class, Submit.class})
    private String email;

    @NotBlank(groups = Submit.class)
    private String phone;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
}
```

This snippet declares the model and groups; compiling it requires the Jakarta Validation API dependency. To **enforce constraints**, a provider such as Hibernate Validator must be configured. Spring Boot typically supplies this infrastructure when the application declares the validation starter, for example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Here `@Email` constrains email format according to provider/constraint semantics; `@NotBlank` ensures non-whitespace content. A constraint without explicit `groups` belongs to `Default`; it does **not automatically** belong to `Draft` or `Submit`. The example declares groups explicitly so checks run as intended.

### 4.1. Using `@Validated` with Spring MVC

```java
import org.springframework.http.HttpStatus;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RegistrationController {
    @PostMapping("/registrations/draft")
    @ResponseStatus(HttpStatus.CREATED)
    String draft(@Validated(Draft.class) @ModelAttribute RegistrationRequest form,
                 BindingResult result) {
        return result.hasErrors() ? "Invalid draft" : "Draft accepted";
    }

    @PostMapping("/registrations/submit")
    String submit(@Validated(Submit.class) @ModelAttribute RegistrationRequest form,
                  BindingResult result) {
        return result.hasErrors() ? "Invalid submission" : "Submitted";
    }
}
```

This is a **controller inside an already-configured Spring MVC application**, not a standalone `main` program. When the binder uses a Jakarta Bean Validation-compatible `SmartValidator`, Spring extracts validation hints from `@Validated` to request the corresponding groups. `BindingResult` must immediately follow the `@ModelAttribute` parameter so the handler can read binding/validation errors. `@ResponseStatus(CREATED)` in the example applies to the draft branch even when returning the error string, so if you need HTTP 400 on invalid input, return `ResponseEntity` or define a separate error-handling mechanism; do not mistake the `"Invalid draft"` string for an HTTP status.

Example flow with a valid email and empty phone:

| Request | Group | Validation Result |
| --- | --- | --- |
| `POST /registrations/draft` | `Draft` | Passes because phone is not required |
| `POST /registrations/submit` | `Submit` | Fails on `phone`, because `@NotBlank` belongs to `Submit` |

`@Validated` integrates with Spring's validation mechanism and can be used in various contexts. In Spring MVC, exact outcomes also depend on parameter type (`@ModelAttribute`, `@RequestBody`, method validation), validator, and framework version. Do not assume every case produces the exact same exception or HTTP status.

### 4.2. Calling `SmartValidator` Directly with Groups

In an application with a configured `LocalValidatorFactoryBean` (the adapter connecting a Jakarta Validation provider), you can call:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.SmartValidator;

// validator is a SmartValidator instance configured by Spring.
// form is an instantiated and populated RegistrationRequest.
var errors = new BeanPropertyBindingResult(form, "registrationRequest");
validator.validate(form, errors, Submit.class);
boolean invalid = errors.hasErrors();
```

This is an illustrative snippet inside a method where `form` and `validator` exist; it is not a standalone program. With a proper Bean Validation adapter, `Submit.class` is interpreted as a group. Passing an arbitrary object that the implementation does not recognize may cause it to be ignored or handled differently; **there is no general rule** that every hint object is a Bean Validation group.

## 5. `@Valid`, `@Validated`, `Default`, and Multiple Hints

| Case | Meaning |
| --- | --- |
| Jakarta `@Valid` | Triggers validation under the default group in supported contexts; also used for cascaded validation on nested properties |
| `@Validated` without value | Triggers validation with the default group in applicable contexts |
| `@Validated(Draft.class)` | Specifies the `Draft` group as the validation hint |
| `@Validated({Draft.class, Submit.class})` | Requests validation against multiple groups in one pass per Bean Validation semantics |
| Constraint without `groups` | Belongs to Bean Validation's `Default` group |

Validating only the `Submit` group will not necessarily run constraints belonging to `Default`. To include default constraints as well, declare the appropriate group, use group inheritance, or use a group sequence as needed. Passing multiple groups **does not impose a mandatory evaluation order**; if you need ordered validation that stops on group failures, use `@GroupSequence` from Jakarta Bean Validation while accounting for group-sequence limitations.

Example:

```java
interface Draft {}
interface Submit extends Draft {}
```

With group inheritance above, validating the `Submit` group under Jakarta Bean Validation includes constraints declared for the super-group `Draft` in addition to `Submit` constraints (per group inheritance rules). This is an explicit way to model policies; placing two interfaces near each other does not make the framework infer a relationship.

### 5.1. Validation Hints vs. Validation Data

Suppose two requests share the same class but have different ages. `supports(RegistrationRequest.class)` gives the same answer; `@Validated(Submit.class)` selects the **constraint set**; `validate` inspects the **actual values** to decide errors. Do not put per-value checks into `supports`, and do not use hints to pass business payload data meant for binding.

## 6. How Do Hints Flow Through Spring `DataBinder`?

`DataBinder` lets you register one or more validators and trigger validation. For `SmartValidator`, the binder can forward hints to the matching overload.

```java
import org.springframework.validation.DataBinder;
import org.springframework.validation.SmartValidator;

// `form` and `smartValidator` are already initialized; snippet inside a method.
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setValidator(smartValidator);
binder.validate(Submit.class);
boolean hasErrors = binder.getBindingResult().hasErrors();
```

Calling `binder.validate(Submit.class)` forwards the hints to registered `SmartValidator` instances. For validators implementing only the plain `Validator` interface, there is no hints overload; the binder may invoke the standard method without applying hints the way a custom `SmartValidator` would expect. Always inspect the actual implementations and configuration.

**Registration is not invocation:** `binder.setValidator(...)` or `binder.addValidators(...)` configures the validator; validation runs only when code, binder, or handler triggers it. In controllers, annotations like `@Validated` instruct the binder to perform that step. When creating a `DataBinder` manually, explicitly call `validate`.

### 6.1. `@InitBinder` and Registration Scope

```java
import org.springframework.validation.SmartValidator;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Inside a controller with an injected smartValidator field:
@InitBinder("registrationRequest")
void initBinder(WebDataBinder binder) {
    binder.addValidators(smartValidator);
}
```

`@InitBinder("registrationRequest")` limits the binder by model attribute name, preventing narrow validators from being registered for incompatible objects. When using `@Validated(Submit.class)` on a matching model parameter, the framework can invoke `SmartValidator` with the group hint. If a registered validator does not `supports` the target type, Spring may reject it when adding or selecting validators depending on the API and execution path; ensure supported types match the model.

## 7. Error Handling, Testing, and Group Design

### 7.1. Common Mistakes

- **Implementing only `Validator` and expecting hints:** you need `SmartValidator` (or a supporting adapter) to receive contextual groups via the overload.
- **Forgetting to implement the parent `validate(Object, Errors)` method:** a custom `SmartValidator` still needs a clear default policy for that method.
- **Confusing `supports` with hints:** `supports` checks types; hints select policies/rule sets.
- **Unintentionally omitting `Default`:** constraints without explicit `groups` belong to `Default` and may be skipped when validating another group alone.
- **Using `@Validated` without a provider:** annotations do not execute constraints when no matching validator/provider is configured.
- **Misplacing `BindingResult`:** for model binding/validation, it must immediately follow the corresponding parameter.
- **Assuming multiple groups run sequentially:** when strict ordering is required, use Bean Validation's group sequences.
- **Attaching a narrow validator to every binder:** register it only for the right target or verify `supports` before execution.
- **Mixing conversion errors and constraint errors:** a request with `age=xyz` can raise `typeMismatch` before group validation checks age rules; distinguish the two error kinds.

### 7.2. Tests Worth Writing

1. For the same form, validating with `Draft` passes while `Submit` fails on fields required only upon submission.
2. Validating with no hints: verify the default group behavior defined by your custom `SmartValidator`.
3. Validating with multiple hints: confirm which rules run, especially with Jakarta Bean Validation groups.
4. Validating an unsupported target: test `supports` and registration rather than calling the method and relying on `ClassCastException`.
5. Test Spring MVC for both `@ModelAttribute` and `@RequestBody` if the application supports both; check `BindingResult`, exceptions, and HTTP statuses as appropriate.
6. Test nested constraints and group inheritance/sequences if your problem genuinely requires them.

### 7.3. Group Design Guidelines

Name groups after **business contexts** (such as `Draft`, `Submit`) rather than arbitrary UI screens. Avoid creating too many overlapping groups that obscure which constraints apply. Treat group configuration as part of your API contract: changing a group annotation can alter request validity even when Java fields remain unchanged.

## 8. Summary

`SmartValidator` adds `Object... validationHints` support to Spring `Validator`, enabling context-dependent validation of a data model. Custom validators can define their own hint semantics, while combining `LocalValidatorFactoryBean` with Jakarta Bean Validation typically treats `Class<?>` hints as validation groups. In Spring MVC, `@Validated` carries groups from the request entry point into the validation flow; `DataBinder` and `Errors` continue handling execution and error recording. To keep the system reliable, clearly define default groups, validator scope, `BindingResult` placement, and binding error handling.
