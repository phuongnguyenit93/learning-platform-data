# Diagnosing `supports()` Returning `false` and Target-Type Mismatched Validators in Spring

## 1. The Problem: Target-Type Errors Differ from Data Errors

A Spring `org.springframework.validation.Validator` answers two different questions:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(clazz)` indicates whether the validator is **capable of handling the passed class**.
- `validate(target, errors)` checks **values of an object that already has the right type** and records field/global errors.
- `supports() == false` does not mean a business value is invalid. It means **the validator is incompatible with the target type**.
- `validate(...)` returns `void`, not a boolean like `supports`.

For example, `UserFormValidator` specifically validates `UserForm`. Whether the form is valid or has an invalid age, `supports(UserForm.class)` must return `true`. If `UserFormValidator` is registered on a binder holding `OrderForm`, `supports(OrderForm.class)` returns `false`: this is a **configuration or validator-routing bug**, not a `FieldError` that a user can fix.

Spring 6.1/6.2 exhibits typical symptoms:

~~~text
DataBinder.setValidator(...) + incompatible target
    -> IllegalStateException

DataBinder.addValidators(...) + incompatible target
    -> IllegalStateException

ValidationUtils.invokeValidator(...) + incompatible target
    -> IllegalArgumentException

Calling validator.validate(...) directly with wrong target type
    -> Possible ClassCastException or incorrect processing
~~~

Therefore, do not write an exception handler that returns HTTP 400 for every error containing the word `Validator`. A mismatch caused by the server attaching the wrong validator is usually a **server-side bug** that requires fixing configuration/logic and monitoring 5xx safely.

## 2. Distinguishing Type Compatibility from Validation Results

| Scenario | `supports` | `validate`/Errors | Meaning |
| --- | --- | --- | --- |
| `UserForm` with valid name, age 22 | true | No errors | Right type, valid data |
| `UserForm` with empty name | true | Field error on name | Right type, invalid data |
| `UserForm` with age 16 | true | Field error on age | Right type, business rule failed |
| `OrderForm` passed to UserFormValidator | false | Should not call `validate` | Wrong type, fix registration |
| Subclass `PremiumUserForm` | Depends on `supports` contract | If supported, validates as UserForm | Needs inheritance tests |
| Jakarta Bean Validation `@NotBlank` | Not a method of the same name on Jakarta Validator | Produces ConstraintViolation via provider | Different mechanism, integrated into Spring via adapter |

A typical Spring Validator implementation:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return UserForm.class.isAssignableFrom(clazz);
}

@Override
public void validate(Object target, Errors errors) {
    UserForm form = (UserForm) target;

    if (form.getAge() != null && form.getAge() < 18) {
        errors.rejectValue("age", "user.age.minimum");
    }
}
~~~

`supports` inspects only the class. It does **not** read the age, query a database, or throw an exception to report a bad value. `validate` runs only when the target is compatible; it records `Errors` via `rejectValue`/`reject`.

### Why `Class#isAssignableFrom` Is Easily Reversed

When you want to support `UserForm` and its subclasses, the correct formula is:

~~~java
return UserForm.class.isAssignableFrom(clazz);
~~~

Read it as: an instance of `clazz` can be assigned to a `UserForm` variable. For example:

| `clazz` | Expected Result |
| --- | --- |
| `UserForm.class` | true |
| `PremiumUserForm.class` (extends UserForm) | true |
| `OrderForm.class` | false |
| `Object.class` | false |

An easy mistake to write:

~~~java
// WRONG if you want to support UserForm subclasses:
return clazz.isAssignableFrom(UserForm.class);
~~~

With the reversed form, `supports(Object.class)` may return `true`, while `supports(PremiumUserForm.class)` returns `false`. If unit tests only pass `UserForm.class` itself, this bug goes uncaught.

An exact comparison:

~~~java
return clazz == UserForm.class;
~~~

is not necessarily wrong if the design strictly permits **only the exact UserForm class**, disallowing subclasses/proxies. However, when subtypes must be accepted, you must choose `isAssignableFrom` in the right direction. Never turn every validator into `supports(clazz) { return true; }` to dodge errors, because casts and property paths later on can still be invalid.

### Class and Object Name Are Not the Same

~~~java
new DataBinder(new UserForm(), "createUser");
new DataBinder(new UserForm(), "editUser");
~~~

Two binders have different object names but the **same Java class**, so `supports(UserForm.class)` produces the same result.

~~~java
new DataBinder(new UserForm(), "form");
new DataBinder(new OrderForm(), "form");
~~~

These two binders share the same object name but have **different Java classes**. `supports` checks the Java type, not the object name string.

## 3. When Does Spring Detect a Mismatch?

### 3.1. Registering a Validator on a `DataBinder` That Already Has a Target

~~~java
OrderForm order = new OrderForm();
DataBinder binder = new DataBinder(order, "orderForm");

binder.setValidator(new UserFormValidator());
~~~

In Spring 6.1/6.2, when a target already exists, `DataBinder` checks `validator.supports(target.getClass())` at registration time. If it does not match, `setValidator(...)` throws **`IllegalStateException`**. `addValidators(...)` and `replaceValidators(...)` also check support against a non-null target.

JUnit test:

~~~java
var binder = new DataBinder(new OrderForm(), "orderForm");

assertThrows(IllegalStateException.class,
        () -> binder.addValidators(new UserFormValidator()));
~~~

**Do not treat this as a conversion error** or validation error. Registration itself did not succeed; `BindingResult` will not necessarily contain a `FieldError`.

### 3.2. Calling `ValidationUtils.invokeValidator`

~~~java
OrderForm order = new OrderForm();
var errors = new BeanPropertyBindingResult(
        order, "orderForm");

ValidationUtils.invokeValidator(
        new UserFormValidator(), order, errors);
~~~

`ValidationUtils.invokeValidator(...)` first checks `supports(order.getClass())`. An incompatibility throws **`IllegalArgumentException`**. Unit test:

~~~java
assertThrows(IllegalArgumentException.class,
        () -> ValidationUtils.invokeValidator(
                new UserFormValidator(), order, errors));
~~~

This behavior is explicitly documented in the Spring Javadoc; avoid guessing exceptions solely from the word `Validator` in a class name.

### 3.3. Calling `validate` Directly and Failing a Cast

~~~java
// Do not do this:
new UserFormValidator().validate(
        new OrderForm(),
        new BeanPropertyBindingResult(
                new OrderForm(), "orderForm"));
~~~

If the implementation casts `(UserForm) target`, a `ClassCastException` may occur. Calling `validate` directly **bypasses the guard in `ValidationUtils`**. Do not solve this by swallowing `ClassCastException`: it is a type mismatch in code, not a rule-violating input value.

### 3.4. The Binder's Target May Not Be Created Yet

In certain constructor-binding paths, a `DataBinder` can exist with a null target and a configured target type before the object is instantiated. When the target is null, `target.getClass()` cannot be used to check `supports` at registration time. Consequently, a misconfiguration may surface **later** during argument resolution/validation.

Do not conclude a validator is compatible merely because `setValidator` did not throw while the target was null. You must test against a **real endpoint** and the actual object-creation path.

### 3.5. Do Not Rely on `toString()` Content in Exceptions

A binder exception message may include the target or class name. Do not assert a fixed message string across Spring versions. Tests should prioritize the **exception type** and data outcomes. Logs/HTTP responses must not print raw `target.toString()`, the entire `BindingResult`, or rejected values (which may contain passwords, emails, or tokens).

## 4. When Does the Validator Run and Why Are There No Field Errors?

`DataBinder#bind(...)` and `DataBinder#validate()` are two separate steps:

~~~java
DataBinder binder =
        new DataBinder(new UserForm(), "userForm");

binder.setValidator(new UserFormValidator());

binder.bind(new MutablePropertyValues(Map.of(
        "displayName", "",
        "age", "16"
)));

// Only binding ran; custom validation has not run yet.
boolean before = binder.getBindingResult().hasErrors();

binder.validate();

// Only then does custom validation record field errors.
boolean after = binder.getBindingResult().hasErrors();
~~~

With the implementation in Section 8, `before == false` and `after == true`. **This is the outcome of the example when the age string converts to Integer successfully**. If binding receives `age=abc`, Spring may create a `typeMismatch` during the bind step so `before` can be true—a different mechanism.

In Spring MVC, `@Valid`/`@Validated` on an argument triggers validation after binding; `BindingResult` placed immediately after the argument lets the controller receive errors. If the `@Valid` trigger is missing, even if a custom Spring validator is registered, do not assume it will run automatically.

### Reading `getValidator()` or `getValidators()`?

`getValidator()` returns the primary validator if present. `getValidators()` returns the full registered list. Spring 6.1+ provides `getValidatorsToApply()`, reflecting the list after applying the exclusion predicate.

If multiple validators exist, check completely:

~~~java
List<Validator> all = binder.getValidators();
List<Validator> active = binder.getValidatorsToApply();
~~~

This snippet assumes appropriate imports, not a standalone class. `setExcludedValidators(Predicate<Validator>)` is a filter applied when running validators, **not a way to fix a target-mismatched validator that already failed at registration**.

## 5. `setValidator`, `addValidators`, and `replaceValidators`

| API | Effect | Common Mistake |
| --- | --- | --- |
| `setValidator(v)` | Replaces the current validator list with v; `null` can clear it. | Losing the global Jakarta Bean Validation adapter by replacing it. |
| `addValidators(v)` | Appends validator(s) to the existing list. | Attaching a local validator of the wrong type across all forms. |
| `replaceValidators(v1, v2)` | Replaces the list with the listed validators. | One of the validators does not support the target. |
| `getValidators()` | Returns the entire registered list. | Not checking it and missing a second validator. |
| `getValidatorsToApply()` | Active list after predicate exclusion, Spring 6.1+. | Thinking it makes a wrong validator's `supports` return true. |

If the application includes `spring-boot-starter-validation`, Spring MVC usually uses `LocalValidatorFactoryBean` to run Jakarta Bean Validation. When adding a custom Spring validator in `@InitBinder`, the generally appropriate approach is:

~~~java
binder.addValidators(userFormValidator);
~~~

instead of `setValidator(userFormValidator)` if you want to **keep both global Bean Validation and custom rules**. However, `addValidators` itself will also reject a type-mismatched validator when a target already exists.

### `@InitBinder` Scope Issues

Wrong when a controller has multiple target classes:

~~~java
@InitBinder
void initEveryBinder(WebDataBinder binder) {
    binder.addValidators(userFormValidator);
}
~~~

Without specifying an object name, the callback can apply to multiple model attributes. When another handler uses `OrderForm`, `UserFormValidator` is incompatible. Fix:

~~~java
@InitBinder("userForm")
void initUser(WebDataBinder binder) {
    binder.addValidators(userFormValidator);
}

@InitBinder("orderForm")
void initOrder(WebDataBinder binder) {
    binder.addValidators(orderFormValidator);
}
~~~

**Two separate mechanisms must both be right**:

- `@InitBinder("userForm")`: scopes configuration by **object name**.
- `supports(UserForm.class)`: checks the **Java type**.

Do not merely rename `@InitBinder` without checking the actual target type. Also do not catch all exceptions in `@ControllerAdvice` and return HTTP 400, because a mismatch caused by server validator misconfiguration is not a user form error.

## 6. A Fast, Repeatable Diagnostic Workflow

When seeing `Invalid target for Validator` or `Validator ... does not support ...` in logs, check in order:

1. **Timing:** is it happening during `setValidator`/`addValidators`, `ValidationUtils.invokeValidator`, or inside `validate`?
2. **Runtime target:** is `binder.getTarget()` null or already instantiated? If present, what is `getTarget().getClass()`?
3. **Object name:** does `binder.getObjectName()` match the `@ModelAttribute("...")` name?
4. **Supports:** does `customValidator.supports(runtimeClass)` behave as expected? Unit test exact, subtype, unrelated, and `Object.class`.
5. **Registered validators:** are global Bean Validation, custom validators, or a validator replaced by `setValidator` present?
6. **Controller binding lifecycle:** is `@InitBinder` applied too broadly across other forms? Is there a global `@ControllerAdvice`?
7. **Inside validate:** is there an invalid cast or `rejectValue` for a property not belonging to the target?
8. **Validation trigger:** does the MVC handler have `@Valid`/`@Validated`, or is code calling `DataBinder.bind` without calling `validate`?
9. **Pipeline:** is the request `@ModelAttribute`, `@RequestBody` JSON, WebFlux, or a service method? Do not apply one diagnosis to every stack.
10. **Regression tests:** are there tests demonstrating both wrong-type and right-type forms after the fix?

Debug metadata:

~~~java
Object target = binder.getTarget();

Class<?> runtimeType =
        target != null ? target.getClass() : null;

boolean supported = runtimeType != null
        && userFormValidator.supports(runtimeType);
~~~

Do not log the entire target/`BindingResult` as it may expose rejected values. You may log **class name, binder object name, and error category** in a controlled logging system.

## 7. Spring Validator vs. Jakarta Bean Validation

| Spring interface | Jakarta interface |
| --- | --- |
| `org.springframework.validation.Validator` | `jakarta.validation.Validator` |
| Has `supports(Class<?>)` | Has no `supports(Class<?>)` API of the same name |
| `validate(Object, Errors)` records errors into Spring `Errors` | `validate(T, Class<?>... groups)` returns `Set<ConstraintViolation<T>>` |
| Used in `DataBinder#setValidator/addValidators` | Integrated via `LocalValidatorFactoryBean` or Spring adapters |
| Useful for local object/domain rules | Based on `@NotBlank`, `@Min`, `@Email`, and custom constraints |

`org.springframework.validation.SmartValidator` also adds an overload with validation hints:

~~~java
void validate(
        Object target,
        Errors errors,
        Object... validationHints);
~~~

Hints can represent validation groups, depending on the implementation. **Validation hints do not fix a `supports(false)`**. If a validator does not support the runtime target class, registration/type must be fixed even when the right group is passed.

`@Valid` only triggers pipeline validation; it does not invent rules out of thin air. If a DTO has no Jakarta constraints and no compatible Spring Validator attached, `@Valid` may produce zero errors.

## 8. Runnable Example: Java 17+, Spring Boot 3.2+, JUnit 5

The project contains **two distinct models**, two corresponding Spring validators, one controller, and two test classes. Choose Spring Boot 3.2+ (Framework 6.1+) with a patch release matching your organization's security policy. Use Java 17+.

In a Maven project already configured with the Spring Boot parent/BOM, add dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Package: `com.example.validatorchecks`. Main files in `src/main/java/com/example/validatorchecks/`, tests in `src/test/java/com/example/validatorchecks/`.

### 8.1. `ValidatorChecksApplication.java`

~~~java
package com.example.validatorchecks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidatorChecksApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ValidatorChecksApplication.class, args);
    }
}
~~~

### 8.2. `UserForm.java`

~~~java
package com.example.validatorchecks;

public class UserForm {
    private String displayName;
    private Integer age;

    public UserForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer value) {
        this.age = value;
    }
}
~~~

### 8.3. `OrderForm.java`

~~~java
package com.example.validatorchecks;

public class OrderForm {
    private String code;

    public OrderForm() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String value) {
        this.code = value;
    }
}
~~~

`OrderForm` does not extend `UserForm`; this is the test case for `supports == false`.

### 8.4. `UserFormValidator.java`

~~~java
package com.example.validatorchecks;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public final class UserFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return UserForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        UserForm user = (UserForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "displayName", "user.name.required");

        if (user.getAge() == null) {
            errors.rejectValue("age", "user.age.required");
        }
        else if (user.getAge() < 18) {
            errors.rejectValue("age", "user.age.minimum");
        }
    }
}
~~~

`supports` returns true for `UserForm` and subclasses, false for `OrderForm`. `validate` safely casts to `UserForm` and creates a `FieldError` if name/age is invalid. It does not log values, holds no per-request state, and does not query a database.

### 8.5. `OrderFormValidator.java`

~~~java
package com.example.validatorchecks;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public final class OrderFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return OrderForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "code", "order.code.required");
    }
}
~~~

### 8.6. `DiagnosticsController.java`

~~~java
package com.example.validatorchecks;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/diagnostics")
public class DiagnosticsController {

    private final UserFormValidator users;
    private final OrderFormValidator orders;

    public DiagnosticsController(
            UserFormValidator users,
            OrderFormValidator orders) {
        this.users = users;
        this.orders = orders;
    }

    @InitBinder("userForm")
    void configureUser(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
        // Keep the global Bean Validation validator if present.
        binder.addValidators(users);
    }

    @InitBinder("orderForm")
    void configureOrder(WebDataBinder binder) {
        binder.setAllowedFields("code");
        binder.addValidators(orders);
    }

    @PostMapping(path = "/users",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> user(
            @Valid @ModelAttribute("userForm") UserForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("INVALID_USER");
        }

        return ResponseEntity.ok(
                "USER:" + form.getDisplayName()
                + ":" + form.getAge());
    }

    @PostMapping(path = "/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> order(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("INVALID_ORDER");
        }

        return ResponseEntity.ok(
                "ORDER:" + form.getCode());
    }
}
~~~

Design effect: `@InitBinder("userForm")` adds `UserFormValidator` only for the matching attribute name; `@InitBinder("orderForm")` does the same for `OrderFormValidator`. `@Valid` triggers validation; `BindingResult` immediately after the argument receives errors. `setAllowedFields` reduces mass-assignment risk, though it **does not replace `supports` or authorization**.

## 9. Unit Tests: `supports`, Exceptions in the Right Place, and Validation Results

Create `src/test/java/com/example/validatorchecks/ValidatorCompatibilityTest.java`:

~~~java
package com.example.validatorchecks;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ValidatorCompatibilityTest {

    private final UserFormValidator users =
            new UserFormValidator();
    private final OrderFormValidator orders =
            new OrderFormValidator();

    static class PremiumUserForm extends UserForm {
    }

    @Test
    void supportsExactType() {
        assertTrue(users.supports(UserForm.class));
    }

    @Test
    void supportsSubclass() {
        assertTrue(users.supports(PremiumUserForm.class));
    }

    @Test
    void rejectsUnrelatedAndSuperclassTypes() {
        assertFalse(users.supports(OrderForm.class));
        assertFalse(users.supports(Object.class));
        assertFalse(orders.supports(UserForm.class));
    }

    @Test
    void wrongAssignableDirectionWouldRejectSubclass() {
        assertFalse(PremiumUserForm.class
                .isAssignableFrom(UserForm.class));
    }

    @Test
    void mismatchedSetValidatorThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.setValidator(users));
    }

    @Test
    void mismatchedAddValidatorsThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.addValidators(users));
    }

    @Test
    void mismatchedReplaceValidatorsThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.replaceValidators(users));
    }

    @Test
    void validationUtilsMismatchThrowsDifferentException() {
        OrderForm order = new OrderForm();
        var errors = new BeanPropertyBindingResult(
                order, "orderForm");
        assertThrows(IllegalArgumentException.class,
                () -> ValidationUtils.invokeValidator(
                        users, order, errors));
    }

    @Test
    void validationUtilsCorrectTargetCreatesFieldErrors() {
        UserForm user = new UserForm();
        user.setDisplayName("");
        user.setAge(16);
        var errors = new BeanPropertyBindingResult(
                user, "userForm");

        ValidationUtils.invokeValidator(users, user, errors);

        assertTrue(errors.hasFieldErrors("displayName"));
        assertTrue(errors.hasFieldErrors("age"));
    }

    @Test
    void bindAloneDoesNotRunCustomValidation() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");
        binder.setValidator(users);

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "",
                "age", "16")));

        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("displayName"));
        assertTrue(binder.getBindingResult()
                .hasFieldErrors("age"));
    }

    @Test
    void validUserHasNoErrors() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");
        binder.setValidator(users);
        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "age", "22")));
        binder.validate();

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("Lan", user.getDisplayName());
        assertEquals(22, user.getAge());
    }

    @Test
    void orderValidatorRunsOnOrder() {
        OrderForm order = new OrderForm();
        DataBinder binder = new DataBinder(order, "orderForm");
        binder.setValidator(orders);
        binder.bind(new MutablePropertyValues(
                Map.of("code", "")));
        binder.validate();

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("code"));
    }

    @Test
    void setValidatorReplacesPreviousValidator() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");

        Validator noop = new Validator() {
            @Override
            public boolean supports(Class<?> c) {
                return true;
            }
            @Override
            public void validate(Object target, Errors errors) {
            }
        };

        binder.setValidator(noop);
        binder.setValidator(users);

        assertEquals(1, binder.getValidators().size());
        assertSame(users, binder.getValidator());
    }

    @Test
    void addValidatorsKeepsEarlierCompatibleValidator() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");

        Validator noop = new Validator() {
            @Override
            public boolean supports(Class<?> c) {
                return UserForm.class.isAssignableFrom(c);
            }
            @Override
            public void validate(Object target, Errors errors) {
            }
        };

        binder.setValidator(noop);
        binder.addValidators(users);

        assertEquals(2, binder.getValidators().size());
        user.setAge(16);
        binder.validate();
        assertTrue(binder.getBindingResult()
                .hasFieldErrors("age"));
    }

    @Test
    void setValidatorNullClears() {
        DataBinder binder = new DataBinder(
                new UserForm(), "userForm");
        binder.setValidator(users);
        binder.setValidator(null);
        assertEquals(0, binder.getValidators().size());
    }

    @Test
    void excludedValidatorDoesNotRun() {
        UserForm user = new UserForm();
        user.setAge(16);
        DataBinder binder = new DataBinder(user, "userForm");
        binder.addValidators(users);
        binder.setExcludedValidators(
                v -> v instanceof UserFormValidator);

        assertEquals(1, binder.getValidators().size());
        assertEquals(0, binder.getValidatorsToApply().size());

        binder.validate();
        assertFalse(binder.getBindingResult().hasErrors());
    }
}
~~~

**16 unit tests** check: exact type, subtype, unrelated/superclass; all three type-mismatched registration methods throw `IllegalStateException`; type-mismatched `ValidationUtils.invokeValidator` throws `IllegalArgumentException`; bind differs from validate; validation creates field errors; order/semantics of `setValidator`, `addValidators`, `setExcludedValidators`.

Note: these tests rely on `DataBinder` **having a non-null target** on Spring Framework 6.1/6.2. When the target is not created yet or on a different Spring version, failure timing may differ. Do not hardcode exception messages that may include target state.

## 10. MockMvc Integration Tests: Proving `@InitBinder` Is Applied Properly

Create `src/test/java/com/example/validatorchecks/DiagnosticsControllerTest.java`:

~~~java
package com.example.validatorchecks;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticsControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validUser() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "22"))
                .andExpect(status().isOk())
                .andExpect(content().string("USER:Lan:22"));
    }

    @Test
    void blankName() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "")
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void underage() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void missingAge() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void conversionMismatchIsNotSupportsMismatch()
            throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void extraUserPropertyIsSuppressed() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "22")
                    .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void validOrderDoesNotUseUserValidator()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", "O-001"))
                .andExpect(status().isOk())
                .andExpect(content().string("ORDER:O-001"));
    }

    @Test
    void blankOrderCodeUsesOrderValidator()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", ""))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ORDER"));
    }

    @Test
    void extraOrderPropertyIsSuppressed()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", "O-001")
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ORDER"));
    }
}
~~~

**9 MockMvc tests** verify that `@InitBinder("userForm")` and `@InitBinder("orderForm")` match their respective model attributes; `@Valid` actually invokes the right validators; conversion mismatches are not confused with type compatibility; properties outside the allowlist are rejected.

### Running All Tests

~~~bash
./mvnw test -Dtest=ValidatorCompatibilityTest,DiagnosticsControllerTest
~~~

On Windows:

~~~powershell
mvnw.cmd test -Dtest=ValidatorCompatibilityTest,DiagnosticsControllerTest
~~~

If Maven is installed globally, `mvn test` can be used. There are **25 test cases designed to pass** on Spring Boot 3.2+ with the source above, though lesson source code **does not equate to having executed the tests**; run them in the project and verify Surefire/JUnit results.

### Trying the Endpoints with curl

~~~bash
curl -i -X POST "http://localhost:8080/diagnostics/users" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "displayName=Lan&age=22"

curl -i -X POST "http://localhost:8080/diagnostics/users" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "displayName=Lan&age=16"

curl -i -X POST "http://localhost:8080/diagnostics/orders" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=O-001"
~~~

Expected HTTP statuses are **200 / 400 / 200** respectively; corresponding bodies:

~~~text
USER:Lan:22
INVALID_USER
ORDER:O-001
~~~

These are the bodies of **three HTTP requests**, not a single Java program printing three lines to stdout. When Spring Security is present, CSRF/authentication must be configured properly; never disable security in production just to make tests pass.

## 11. Nested Validators: Passing the Right Object to the Child Validator

If `CustomerForm` contains `AddressForm address`, and `AddressValidator` supports only `AddressForm`, you **cannot** pass `CustomerForm` to AddressValidator.

~~~java
@Override
public void validate(Object target, Errors errors) {
    CustomerForm customer = (CustomerForm) target;

    AddressForm address = customer.getAddress();

    if (address == null) {
        errors.rejectValue("address", "address.required");
        return;
    }

    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, address, errors);
    }
    finally {
        errors.popNestedPath();
    }
}
~~~

This is a snippet of `CustomerValidator` with an `addressValidator` field and application-supplied model types, not standalone runnable source. Test:

- `CustomerValidator.supports(CustomerForm.class)` is true.
- `AddressValidator.supports(AddressForm.class)` is true.
- Never call `ValidationUtils.invokeValidator(addressValidator, customer, errors)`.
- When `address==null`, handle null first (the helper requires a non-null target).
- `pushNestedPath("address")`/`popNestedPath()` ensures the child validator rejecting `postalCode` records it as `address.postalCode`.
- `finally` always restores the nested path even if the validator throws an exception.

A validator supporting `CustomerForm` does not automatically mean every nested object is checked. You can use composition as above or Jakarta `@Valid` on the nested property depending on the provider; test the chosen mechanism directly.

## 12. MVC, WebFlux, and Service Validation

**Spring MVC:** `WebDataBinder` extends `DataBinder`. `@InitBinder` from a controller or `@ControllerAdvice` configures validators. When `@Valid @ModelAttribute` is used, data errors normally go into `BindingResult`; a validator registration mismatch is a separate issue.

**Spring `@RequestBody` JSON:** Jackson deserializes JSON, then validation can run; `@InitBinder` can still affect the binder's validators, though `setAllowedFields` is for property binding rather than a JSON deserializer allowlist. A JSON parse failure must not be diagnosed as `supports=false`.

**Spring WebFlux:** uses reactive argument resolution, `WebExchangeBindException`/`HandlerMethodValidationException` depending on the scenario, and `WebTestClient` instead of MockMvc. The principle of using the right validator type still holds. Do not perform blocking JDBC/network calls inside `supports` or `validate` on the reactive event loop.

**Service-layer method validation:** `@Validated`/AOP and Jakarta Bean Validation can throw `ConstraintViolationException`/`MethodValidationException`; these are not the same error as `DataBinder#setValidator`. Do not lump everything into `HTTP 400`. A service invoked from a scheduler or event consumer may have no HTTP client to "fix the input."

## 13. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `IllegalStateException` on `setValidator` | Binder target is not supported. | Check `getTarget().getClass()` and `supports`. |
| `IllegalArgumentException` from `ValidationUtils` | Wrong target passed to helper. | Pass the right child object type or a different validator. |
| `ClassCastException` inside `validate` | Bypassed supports or supports too broad. | Align type checks, casts, and field paths. |
| Subclass is not validated | Used `==` or reversed `isAssignableFrom`. | Test exact/subtype; use the right direction if needed. |
| `Object.class` unexpectedly supported as true | Reversed `clazz.isAssignableFrom(UserForm.class)`. | Use `UserForm.class.isAssignableFrom(clazz)`. |
| OrderForm also gets UserFormValidator | `@InitBinder` applied too broadly. | Scope by object name and test both routes. |
| `@Valid` present yet no custom errors | Validator unregistered, wrong scope, or only `bind` ran. | Check `@InitBinder`, `getValidators()`, and `validate` trigger. |
| `@NotBlank` errors disappear after edit | `setValidator` replaced global Jakarta adapter. | Use `addValidators` to combine them. |
| Errors recorded on nonexistent fields | `rejectValue` wrong property name/target. | Test real target beans and field paths. |
| Error appears late during binding | Target was null at validator registration time. | Test constructor binding/actual MVC lifecycle. |
| Using exclusion to mask mismatch | Registration guard may run before exclusion. | Do not register wrong types. |
| Malformed JSON body treated as supports error | Wrong converter pipeline. | Diagnose Jackson/HttpMessageConverter separately. |
| Returning status 400 for validator registration error | Blaming client for server bug. | Keep server error, alert, and fix configuration. |
| Making `supports` return true for every class | Hides mismatch until cast/property fails. | Restrict to exact types/interfaces. |

## 14. Pre-Merge Diagnostic Checklist

- [ ] Test `supports` with exact type, subtype, unrelated type, and `Object.class`.
- [ ] If supporting subclasses, use `ExpectedType.class.isAssignableFrom(clazz)` in the right direction.
- [ ] `validate` only casts/accesses fields present on all supported types.
- [ ] Do not use `supports` to inspect business values or request state.
- [ ] `@InitBinder` is scoped to the exact `@ModelAttribute` name and does not register validators for other forms.
- [ ] When using `DataBinder` manually, test `bind` and `validate` as two distinct steps.
- [ ] Test `setValidator`, `addValidators`, and `replaceValidators` with an incompatible non-null target.
- [ ] Test `ValidationUtils.invokeValidator` on both compatible and incompatible target types.
- [ ] Test that `BindingResult` receives field errors for invalid data of the right type.
- [ ] If global Bean Validation is active, use `addValidators` when adding custom rules.
- [ ] Inspect `getValidators()` rather than only `getValidator()` if a binder has multiple validators.
- [ ] Do not use `setExcludedValidators` to hide a type mismatch at registration.
- [ ] Check constructor binding when the target starts out null.
- [ ] Write MockMvc/WebTestClient integration tests for all model attributes in the same controller.
- [ ] Do not log targets/rejected values or return stack traces containing internal details.
- [ ] Do not treat validator configuration bugs as 400 errors that clients can fix.
- [ ] Re-run tests after refactoring DTO classes, controller methods, and `@InitBinder` names.

**Conclusion:** `supports() == false` indicates **the validator does not support the target class**, as opposed to invalid data that `validate(...)` records via `Errors`. In Spring, registering an incompatible validator on a binder with a target typically throws `IllegalStateException`; `ValidationUtils.invokeValidator` on the wrong target typically throws `IllegalArgumentException`. Correctly diagnosing **runtime type, `isAssignableFrom` direction, binder scope, and lifecycle**, then testing both registration and execution, prevents these bugs from returning.

## References

- Spring Reference — Validator interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Reference 6.2 — DataBinder and Jakarta Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Reference 6.2 — MVC Validator configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Reference — MVC `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Javadoc 6.2 — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Javadoc 6.2 — `ValidationUtils#invokeValidator`: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/ValidationUtils.html
- Spring Javadoc 6.2 — `SmartValidator`: https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/validation/SmartValidator.html
