# DataBinder: setValidator, addValidators, and replaceValidators

In Spring Framework, **`DataBinder`** manages binding values onto an object and can run **`Validator`** instances to check that object. When a form or API has multiple groups of rules — such as checking required fields, valid age, and business rules — the three methods **`setValidator(...)`**, **`addValidators(...)`**, and **`replaceValidators(...)`** determine **which validators are registered on the binder, their order, and whether an existing list is preserved**.

A key distinction to make upfront: **registering a validator does not mean running validation**. When using `DataBinder` directly, you call `binder.validate()` to execute them. In Spring MVC, after data binding, annotations such as `@Valid` or `@Validated` on eligible parameters can trigger validation according to Spring MVC's mechanism.

This lesson focuses on the `org.springframework.validation.DataBinder` API, how to combine multiple Spring `Validator` instances, how to read `BindingResult`, and how these three methods behave in `WebDataBinder`.

## 1. Where Do DataBinder, Validator, and BindingResult Sit in the Flow?

```text
Target object + input data
             |
             v
          DataBinder
             |
             +-- bind(PropertyValues)
             |      convert types and write properties
             |
             +-- list of registered Validators
             |      setValidator / addValidators / replaceValidators
             |
             +-- validate() when invoked
                    |
                    +-- Validator 1
                    +-- Validator 2
                    +-- ...
                    |
                    v
              BindingResult
             (field errors, global errors)
```

Components:

| API | Function |
| --- | --- |
| `DataBinder` | Binds values onto the object; holds conversion configuration, binding rules, and validators |
| `Validator` | Spring interface with `supports(Class<?>)` and `validate(Object, Errors)` |
| `SmartValidator` | Extends `Validator` to support validation hints when supplied |
| `Errors` | Object used by validators to record field/object errors |
| `BindingResult` | Extends `Errors`, holding both binding and validation errors |
| `WebDataBinder` | Web-environment variant of `DataBinder`, commonly configured by Spring MVC via `@InitBinder` |

Example of a simple `Validator`:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class AgeValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;
        if (form.getAge() != null && form.getAge() < 18) {
            errors.rejectValue("age", "age.tooYoung");
        }
    }
}
```

This is an **illustrative snippet**, assuming a `RegistrationForm` with `getAge()`; the full standalone runnable code is provided in section 5. `supports(...)` describes compatible target types; `validate(...)` inspects the target and adds errors to `Errors` when a rule is not satisfied.

**Note on type names:** `org.springframework.validation.Validator` is different from `jakarta.validation.Validator`. The three `DataBinder` methods discussed here take **Spring's** Validator interface. Spring provides adapters such as `LocalValidatorFactoryBean` to integrate Jakarta Bean Validation with this mechanism.

## 2. Exact Comparison of the Three Methods

Suppose a `DataBinder` currently has this validator list:

```text
[A, B]
```

Where A, B, and C are `org.springframework.validation.Validator` instances.

| Call | List After Call | Explanation |
| --- | --- | --- |
| `binder.setValidator(C)` | `[C]` | Clears the previous list and sets a single validator |
| `binder.addValidators(C)` | `[A, B, C]` | Appends the validator to the list |
| `binder.replaceValidators(C, A)` | `[C, A]` | Clears the previous list and replaces it with the passed validators |
| `binder.setValidator(null)` | `[]` | Clears the configured validator list |
| `binder.replaceValidators()` | `[]` | Replaces with an empty list |

**`setValidator(Validator validator)`** means setting a single validator for the binder. It does not merely replace the first element; it **clears all existing validators** before adding the new one (if the argument is non-`null`). Thus, after adding multiple validators, calling `setValidator(...)` again can wipe out validators already in use.

**`addValidators(Validator... validators)`** takes one or more validators and **appends** them to the existing list. This is the usual choice when you want to keep default or previously configured validators and add module/controller-specific rules.

**`replaceValidators(Validator... validators)`** replaces **the entire list** with the supplied validators in exact order. It fits when you want explicit full control over the validator set and may need more than one new validator. Calling it with no arguments produces an empty list.

All three operations are **configuration**. They do not re-check data automatically, do not clear existing errors in `BindingResult`, and do not automatically invoke `validate()`.

### Registration Order Matters

Suppose:

```java
binder.setValidator(nameValidator);
binder.addValidators(ageValidator, emailValidator);
```

The list is:

```text
[nameValidator, ageValidator, emailValidator]
```

When `binder.validate()` is called, validators are applied in list order (excluding any filtered out via an exclusion configuration, if set). If one validator records an error, that error **does not automatically prevent subsequent validators from running**. Therefore, avoid assuming one validator will "short circuit" others. Rules should be independent or handle invalid values safely.

When you need to change the order, you can use:

```java
binder.replaceValidators(emailValidator, nameValidator, ageValidator);
```

Changing order can affect error ordering and any validators that rely on state checked earlier; ideally, write validators that do not depend on side effects of other validators.

## 3. getValidator(), getValidators(), and getValidatorsToApply()

Configuring multiple validators makes a few APIs easy to misunderstand.

| API | Return Value |
| --- | --- |
| `binder.getValidator()` | The **first** validator in the list, or `null` if none |
| `binder.getValidators()` | Configured list of validators, unmodifiable directly |
| `binder.getValidatorsToApply()` | Validators that will be applied after considering the exclusion predicate, if configured; available since Spring 6.1 |

Example:

```java
binder.setValidator(nameValidator);
binder.addValidators(ageValidator);
System.out.println(binder.getValidator() == nameValidator); // true
System.out.println(binder.getValidators().size());          // 2
```

**`getValidator()` only returns the first validator**, which does not mean only the first validator runs. To inspect the entire registered set, use `getValidators()`. In Spring 6.1+, `setExcludedValidators(Predicate<Validator>)` lets you exclude certain validators from execution; when you need the effective set being applied, `getValidatorsToApply()` is the right method.

Do not mutate the list returned by `getValidators()` with `add(...)` or `clear()`; the returned collection is protected against direct modification. Use the three configuration methods rather than manipulating the internal list.

## 4. Target Type Checking and Supported Scope

When a binder already has a target object, Spring checks whether a registered validator supports that object's class via `supports(Class<?>)`. If a validator does not support the target, registration can throw **`IllegalStateException`** reporting the incompatible type/validator.

```java
@Override
public boolean supports(Class<?> type) {
    return RegistrationForm.class.isAssignableFrom(type);
}
```

Writing with `isAssignableFrom` supports `RegistrationForm` and compatible subclasses. Writing:

```java
return type == RegistrationForm.class;
```

only accepts that exact class. Either can be right depending on intent, but it must match the binder's actual object type.

For a validator that only handles `Address`, do not register it directly on a `DataBinder` whose target is `RegistrationForm` unless that validator truly supports `RegistrationForm`. Instead, have the form's validator invoke the child validator for `Address` and use `Errors.pushNestedPath("address")`/`popNestedPath()` if child error paths are needed. `DataBinder`'s check here operates on **the binder-level target type**, not what field types it contains.

Additional note: a shared `Validator` should avoid holding per-request mutable state. Error state and input data belong to `Errors`/`BindingResult` and the target of each validation pass.

## 5. Runnable Java 17 Example: Observing All Three APIs in Action

This example needs no web server. It uses Spring Framework Core Validation, three independent validators, and **three separate DataBinders** to precisely distinguish the effect of each configuration method without carrying over errors from a prior validation run.

### 5.1. Project Structure

```text
data-binder-validators/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ValidatorRegistryDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'data-binder-validators'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'example.ValidatorRegistryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Use JDK 17+ with a Gradle version compatible with the JDK/Spring; Maven Central access is needed on first dependency download. `spring-context` brings in the Spring dependencies needed for the validation APIs in the example.

### 5.2. Complete Java File

**`src/main/java/example/ValidatorRegistryDemo.java`**

```java
package example;

import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

import java.util.List;

public class ValidatorRegistryDemo {

    public static final class RegistrationForm {
        private final String name;
        private final String email;
        private final Integer age;

        public RegistrationForm(String name, String email, Integer age) {
            this.name = name;
            this.email = email;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public String getEmail() {
            return email;
        }

        public Integer getAge() {
            return age;
        }
    }

    public static final class NameValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");
        }
    }

    public static final class AgeValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;
            if (form.getAge() == null || form.getAge() < 18) {
                errors.rejectValue("age", "age.invalid");
            }
        }
    }

    public static final class EmailValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;
            if (form.getEmail() == null
                    || !form.getEmail().contains("@")) {
                errors.rejectValue("email", "email.invalid");
            }
        }
    }

    private static List<String> validatorNames(DataBinder binder) {
        return binder.getValidators().stream()
                .map(validator -> validator.getClass().getSimpleName())
                .toList();
    }

    private static List<String> errorFields(DataBinder binder) {
        return binder.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .toList();
    }

    public static void main(String[] args) {
        RegistrationForm form =
                new RegistrationForm("   ", "invalid-email", 16);

        Validator byName = new NameValidator();
        Validator byAge = new AgeValidator();
        Validator byEmail = new EmailValidator();

        // Case 1: set one validator, then add another.
        DataBinder additive = new DataBinder(form, "registration");
        additive.setValidator(byName);
        additive.addValidators(byAge);
        System.out.println("setThenAdd=" + validatorNames(additive));
        additive.validate();
        System.out.println("setThenAddErrors=" + errorFields(additive));

        // Case 2: replace clears the previous validators.
        DataBinder replaced = new DataBinder(form, "registration");
        replaced.setValidator(byName);
        replaced.addValidators(byAge);
        replaced.replaceValidators(byEmail, byAge);
        System.out.println("replaced=" + validatorNames(replaced));
        System.out.println("primary="
                + replaced.getValidator().getClass().getSimpleName());
        replaced.validate();
        System.out.println("replacedErrors=" + errorFields(replaced));

        // Case 3: set after add retains only a single validator.
        DataBinder reset = new DataBinder(form, "registration");
        reset.addValidators(byName, byAge);
        reset.setValidator(byEmail);
        System.out.println("setAfterAdd=" + validatorNames(reset));
    }
}
```

`RegistrationForm` here is an immutable class with getters and initialized via its constructor. The example **only illustrates validation** and does not perform `binder.bind(...)` or property binding, so setters are not needed. If you want to bind form data through setters, use a mutable DTO with appropriate setters or configure constructor binding separately.

### 5.3. Run and Verify stdout

From the project directory:

```bash
gradle -q run
```

If a Gradle wrapper is present on Unix/macOS, use `./gradlew -q run`; on Windows, use `gradlew.bat -q run`.

**Expected stdout:**

```text
setThenAdd=[NameValidator, AgeValidator]
setThenAddErrors=[name, age]
replaced=[EmailValidator, AgeValidator]
primary=EmailValidator
replacedErrors=[email, age]
setAfterAdd=[EmailValidator]
```

Line-by-line explanation:

- `setThenAdd` holds two validators because `setValidator(byName)` was followed by `addValidators(byAge)`.
- When running `additive.validate()`, `name` has only whitespace so `name` fails; `age=16` so `age` fails. Email was not registered on this binder.
- `replaceValidators(byEmail, byAge)` replaces the list with `[EmailValidator, AgeValidator]`. `NameValidator` does not run, even though `name` is still all whitespace.
- `getValidator()` returns the first validator in the new list, i.e., `EmailValidator`.
- `replacedErrors` contains `email` and `age` in the order the two validators were invoked. `name` is absent from the error list because the name validator was replaced.
- `setAfterAdd` contains only `EmailValidator`: `setValidator` removed the validators added earlier.

This output demonstrates **the difference between configuring the validator list and validation results**. Separate binders hold distinct `BindingResult` instances, so prior errors never bleed into the example's data.

## 6. Registering Alone Is Not Enough: Trigger validate at the Right Time

Example showing the standard order when using `DataBinder` manually:

```java
RegistrationForm target =
        new RegistrationForm("Lan", "lan@example.org", 25);
DataBinder binder = new DataBinder(target, "registration");

binder.setValidator(new NameValidator());
binder.addValidators(new AgeValidator(), new EmailValidator());

// The object already has data; this is the step that executes validation.
binder.validate();

boolean invalid = binder.getBindingResult().hasErrors();
```

`setValidator` and `addValidators` above only update the list; **`binder.validate()`** actually executes the validators and records errors. If using a mutable JavaBean and transferring data from a request-like map before validating, the general order is:

```java
binder.bind(new MutablePropertyValues(inputValues));
binder.validate();
BindingResult result = binder.getBindingResult();
```

This is an **illustrative pattern**, requiring `inputValues` and the appropriate `org.springframework.beans.MutablePropertyValues` import. `bind(...)` processes values onto fields and may produce type-conversion errors, whereas `validate()` runs registered validators. `BindingResult` can hold both kinds of errors.

**Warning on reusing a binder:** If you call `validate()` multiple times on **the same `DataBinder`**, errors already recorded in `BindingResult` do not automatically disappear just because `setValidator(...)` or `replaceValidators(...)` is called. To compare two validator lists fairly, create a fresh binder with its own error result, as shown in section 5. Do not interpret lingering old errors as proof that a removed validator is still executing.

### Validation hints

When calling `binder.validate(hints...)`, if a validator implements `SmartValidator`, Spring can pass the hints to `validate(target, errors, hints...)`. A plain `Validator` only has `validate(target, errors)` and therefore has no built-in group/hint handling. To apply Jakarta Bean Validation groups, understand the adapter and `@Validated` involved; **the set/add/replace methods do not define groups themselves**.

## 7. Practical Impact in Spring MVC and @InitBinder

In Spring MVC, `WebDataBinder` extends `DataBinder`. A controller can configure the binder for a model attribute via `@InitBinder`:

```java
@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    private final RegistrationBusinessValidator businessValidator;

    public RegistrationController(
            RegistrationBusinessValidator businessValidator) {
        this.businessValidator = businessValidator;
    }

    @InitBinder("registrationForm")
    void configureRegistration(WebDataBinder binder) {
        binder.addValidators(businessValidator);
    }

    @PostMapping
    String submit(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration/form";
        }
        return "registration/success";
    }
}
```

This is **integration illustrative code**, requiring Spring MVC imports, `@Valid`, `WebDataBinder`, and a `RegistrationBusinessValidator` class supporting `RegistrationForm` as well as corresponding views/application setup. This snippet cannot be compiled standalone with `javac` without those dependencies and supporting classes. It shows the right place to add a local validator; `@InitBinder("registrationForm")` scopes the callback to the model attribute named `registrationForm`.

In a Spring MVC application with a Jakarta Bean Validation provider, Spring typically configures a global validator (such as `LocalValidatorFactoryBean`) for `@Valid` or `@Validated`. When you want to **add** form-specific rules while keeping constraints like `@NotBlank`, `@Email`, `@Min`:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.addValidators(new RegistrationBusinessValidator());
}
```

`addValidators` is usually appropriate because it keeps existing validators. Conversely:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.setValidator(new RegistrationBusinessValidator());
}
```

reduces the list to only the specified validator, **potentially replacing the global Bean Validation validator** that Spring MVC had attached to the binder. In that case, do not assume Jakarta Validation annotations will still run via the previous validator.

If the requirement is an intentional replacement of all validators:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.replaceValidators(
            new RegistrationBusinessValidator(),
            new RegistrationCrossFieldValidator());
}
```

This snippet assumes both validators support `RegistrationForm`. `replaceValidators` clearly expresses the intent of using **a new validator set**, whereas `addValidators` expresses the intent of **appending**.

**Identify the trigger mechanism:** `@Valid`/`@Validated` on an eligible model parameter causes Spring MVC to invoke validators after binding. Configuring `@InitBinder` itself does not validate inside the callback; `@InitBinder` primarily prepares the binder for request processing.

## 8. Choosing the Right Method by Goal

| Goal | Consider | Reason |
| --- | --- | --- |
| Only one validator exists; explicitly set list to just that one | `setValidator(v)` | Removes all prior validators then sets `v` |
| Keep global Bean Validation and add controller business rules | `addValidators(v)` | Preserves prior configuration |
| Append two custom rules in order | `addValidators(v1, v2)` | Appends validators sequentially |
| Intentionally replace the entire existing checker set with two validators | `replaceValidators(v1, v2)` | Resulting list is exactly `[v1, v2]` |
| Clear the entire registered list | `replaceValidators()` or `setValidator(null)` | Both leave the list empty |
| Inspect the first validator | `getValidator()` | Returns the first element, possibly `null` |
| Inspect all configured validators | `getValidators()` | Returns the full list |
| Compare error outputs of two validator sets | Create two separate binders | Avoids old errors remaining in the same `BindingResult` |

Sometimes different validation sets are needed per workflow (e.g., create vs. update). Rather than mutating the list arbitrarily mid-validation, configure the binder cleanly before running and use validators suited to the target. If rules only differ by Bean Validation groups, consider `@Validated(Group.class)` or an appropriate `SmartValidator` instead of replacing all validators.

## 9. Common Mistakes

### 9.1. Confusing `setValidator` with `addValidators`

```java
binder.addValidators(requiredFieldsValidator);
binder.setValidator(businessValidator);
```

After these two lines, only `businessValidator` remains in the list. To run both, use:

```java
binder.addValidators(requiredFieldsValidator);
binder.addValidators(businessValidator);
```

or specify the whole list with `replaceValidators(requiredFieldsValidator, businessValidator)`.

### 9.2. Looking Only at `getValidator()` and Assuming Only One Validator Exists

```java
binder.setValidator(first);
binder.addValidators(second);
System.out.println(binder.getValidator() == first); // true
```

The line above does not negate the presence of `second`. Inspect `getValidators()` to see the configured list.

### 9.3. Failing to Call validate After Manual Configuration

```java
DataBinder binder = new DataBinder(target);
binder.addValidators(customValidator);
// Without calling binder.validate(), customValidator has not run yet.
```

This is why an object can contain invalid data while `BindingResult` shows no validator errors; inspect the execution flow, not just the configuration.

### 9.4. Validator Does Not Support the Target Type

```java
@Override
public boolean supports(Class<?> type) {
    return Address.class.isAssignableFrom(type);
}
```

A validator supporting only `Address` normally cannot be registered on a binder whose target is `RegistrationForm` if `RegistrationForm` is not an `Address` subtype. The solution is to create a parent validator for `RegistrationForm` and delegate to the `Address` validator in context, or redesign the validator so `supports` accurately describes the target.

### 9.5. Registering the Same Validator Repeatedly

`addValidators` is a list-append operation, not a deduplication mechanism guaranteeing one instance per type. If the same validator is added multiple times, it can run multiple times and record duplicate errors. Before calling `addValidators` across multiple configuration points, clarify who owns registration and verify the resulting list.

### 9.6. Assuming replace Clears Existing Errors

`replaceValidators(...)` changes the list of **validators for subsequent validation calls**; it is not an API that clears errors in `BindingResult`. Previously recorded errors can remain in the binder, so do not reuse the same binder to compare configurations without managing validation history.

### 9.7. Confusing Spring Validator with Jakarta Validator

`jakarta.validation.Validator` is not a direct input type for `DataBinder.addValidators(...)`. When Jakarta Validation is needed, use Spring's integration (such as the `LocalValidatorFactoryBean` adapter) instead of casting between two incompatible interfaces. With `@Valid`/`@Validated`, inspect the validators Spring MVC has registered.

### 9.8. Validation Is Not a Filter for Which Fields Are Bound

No matter how many validators are registered, whether a client can mutate a property is not solved by validation alone. When binding request input, prefer DTOs containing only permitted fields, use `setAllowedFields(...)` or an appropriate binding mechanism, and avoid *mass assignment* onto domain entities containing sensitive fields like `role` or `approved`.

## 10. How to Verify in Code and Tests

For a binder with a valid target, you can verify these invariants:

1. After `setValidator(a)`, `getValidators()` is exactly `[a]`.
2. After `addValidators(b, c)`, the list becomes `[a, b, c]`, preserving order.
3. After `replaceValidators(c, b)`, the list is `[c, b]`.
4. `getValidator()` is `c`, the leading validator.
5. After `binder.validate()`, errors recorded by `c` and `b` appear; errors produced solely by `a` do not appear **provided `a` was not already validated previously**.
6. `setValidator(null)` or `replaceValidators()` leaves `getValidators()` empty.
7. If a validator does not satisfy `supports(target.getClass())`, adding it must be rejected rather than accepting a rule for the wrong class.

The following check assumes `a`, `b`, `c` are all validators supporting the target:

```java
DataBinder binder = new DataBinder(target, "form");
binder.setValidator(a);
binder.addValidators(b);
assert binder.getValidators().size() == 2;
assert binder.getValidator() == a;

binder.replaceValidators(c, b);
assert binder.getValidators().size() == 2;
assert binder.getValidator() == c;
```

This is an **illustrative snippet** inside a test or method where those variables already exist. Java assertions are disabled by default; when using `assert`, enable `-ea` on the JVM or use JUnit/AssertJ assertions.

In unit tests, create a fresh target/binder per scenario. When testing Spring MVC, check both **field errors** and whether local validator configuration accidentally replaced global Bean Validation; that is where `addValidators` and `setValidator` commonly diverge in practice.

## 11. Takeaways

- **`setValidator(v)`**: configures a single validator `v`; previous validators are removed.
- **`addValidators(v1, v2)`**: appends `v1`, `v2` to the current list.
- **`replaceValidators(v1, v2)`**: replaces the entire list with `v1`, `v2`.
- **`getValidator()`**: returns the first validator; **`getValidators()`**: returns the full list.
- **`binder.validate()`**: executes configured validators; error details are collected in **`BindingResult`**.
- **In `@InitBinder`**, use `addValidators` when you need to preserve global validators and add custom logic. Use `setValidator` or `replaceValidators` when intentionally replacing them.

### Self-Practice Exercise

You have three validators: `RequiredValidator`, `CrossFieldValidator`, and `BusinessValidator`. A `DataBinder` already has `RequiredValidator`. Predict the list after each call:

```java
binder.addValidators(crossFieldValidator);
binder.setValidator(businessValidator);
binder.addValidators(requiredValidator);
binder.replaceValidators(
        crossFieldValidator, requiredValidator);
```

**Answer:** after the first add it is `[RequiredValidator, CrossFieldValidator]`; after set it is `[BusinessValidator]`; after the next add it is `[BusinessValidator, RequiredValidator]`; after the final replace it is `[CrossFieldValidator, RequiredValidator]`. `BusinessValidator` is no longer in the list. This describes configuration only; errors are produced only when validation is triggered.

## Official Documentation

- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/DataBinder.html): the three validator registration methods, querying the list, and executing validation.
- [Spring Framework — Validation via Spring Validator](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): the `Validator` interface, type checking, and recording errors.
- [Spring Framework — Bean Validation Integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): configuring `DataBinder` and combining multiple validators.
- [Spring Framework — Spring MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): global and local validators via `@InitBinder`.
