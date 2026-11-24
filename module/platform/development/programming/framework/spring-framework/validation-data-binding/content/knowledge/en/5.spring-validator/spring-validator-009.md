# Direct Validation with `validateObject` Since Spring Framework 6.1

When you already have a Java object in memory and simply want to run a **Spring `Validator`**'s rules on it, you no longer need to create a `DataBinder` or instantiate `Errors` yourself. Since **Spring Framework 6.1**, the `org.springframework.validation.Validator` interface includes a default method:

~~~java
Errors validateObject(Object target);
~~~

Core usage:

~~~java
Errors errors = validator.validateObject(input);
if (errors.hasErrors()) {
    // Reject the input and handle the recorded errors.
}
~~~

This method calls the existing validation logic, creates, and returns a new `Errors` instance so you can read the results immediately. It is a concise option for **validating a standalone object after it has been constructed**, such as before executing a use case. It does not bind requests, does not convert strings into numbers, and does not replace the full Spring MVC validation lifecycle.

## 1. Before and After Spring 6.1: What Changed?

Spring's `Validator` interface originally had two primary methods:

~~~java
boolean supports(Class<?> clazz);
void validate(Object target, Errors errors);
~~~

- `supports(Class<?>)` indicates which object types the validator is meant for.
- `validate(Object, Errors)` inspects the object and calls `errors.rejectValue(...)` for field errors or `errors.reject(...)` for object-wide errors.

Before Spring 6.1, directly validating an object outside binding typically required creating an `Errors` instance yourself:

~~~java
// Traditional approach: create the error collector manually.
Errors errors = new BeanPropertyBindingResult(input, "input");
validator.validate(input, errors);

if (errors.hasErrors()) {
    // Handle errors.
}
~~~

Since Spring 6.1, the shorter form is:

~~~java
// Spring Framework 6.1+.
Errors errors = validator.validateObject(input);

if (errors.hasErrors()) {
    // Handle errors.
}
~~~

No changes are needed in how validators are written: implementing `validate(Object, Errors)` remains the foundation. `validateObject` is a **default method on Spring's `Validator` itself**, so existing validators can use it directly when running on a compatible version, provided the validator logic works with the simple `Errors` implementation that the method creates.

Conceptually, Spring 6.1's default logic is equivalent to:

~~~java
default Errors validateObject(Object target) {
    Errors errors = new SimpleErrors(target);
    validate(target, errors);
    return errors;
}
~~~

This snippet illustrates the delegation documented in the Spring API, not a method you need to copy into your project. `SimpleErrors` manages an error list for a single top-level object. **Each call to `validateObject` creates a fresh `Errors`** and re-runs the validator.

One crucial detail: the default method **does not automatically call `supports(target.getClass())`** before forwarding the object to `validate(target, errors)`. The caller must still choose a validator compatible with the object type, or use a validator with built-in type checks.

## 2. Complete Runnable Example with Java 17 and Spring 6.1

We validate a meeting room booking with three properties:

- `title` must contain non-whitespace characters;
- `startHour` between 0 and 23, `endHour` between 1 and 24;
- `startHour` must be less than `endHour`.

Two rule groups will generate a **field error** and a **global error**. The example uses the `Validator.forInstanceOf(...)` factory (also introduced in Spring 6.1) to write a strongly typed validator without a separate implementation class.

Project structure:

~~~text
spring-direct-validation/
├── pom.xml
└── src/main/java/demo/DirectValidationDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-direct-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
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
                <configuration>
                    <mainClass>demo.DirectValidationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/demo/DirectValidationDemo.java`:

~~~java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class DirectValidationDemo {

    public static final class MeetingSlot {
        private final String title;
        private final int startHour;
        private final int endHour;

        public MeetingSlot(String title, int startHour, int endHour) {
            this.title = title;
            this.startHour = startHour;
            this.endHour = endHour;
        }

        public String getTitle() {
            return title;
        }

        public int getStartHour() {
            return startHour;
        }

        public int getEndHour() {
            return endHour;
        }
    }

    private static final Validator SLOT_VALIDATOR =
            Validator.forInstanceOf(MeetingSlot.class, (slot, errors) -> {
                if (slot.getTitle() == null || slot.getTitle().isBlank()) {
                    errors.rejectValue(
                            "title", "title.required",
                            "Title must not be blank");
                }

                if (slot.getStartHour() < 0 || slot.getStartHour() > 23) {
                    errors.rejectValue(
                            "startHour", "startHour.range",
                            "Start hour must be from 0 to 23");
                }

                if (slot.getEndHour() < 1 || slot.getEndHour() > 24) {
                    errors.rejectValue(
                            "endHour", "endHour.range",
                            "End hour must be from 1 to 24");
                }

                if (slot.getStartHour() >= slot.getEndHour()) {
                    errors.reject(
                            "time.order",
                            "End hour must be after start hour");
                }
            });

    private static void report(String label, MeetingSlot slot) {
        Errors errors = SLOT_VALIDATOR.validateObject(slot);
        System.out.println(label + ": errors=" + errors.getErrorCount());

        errors.getFieldErrors().forEach(error ->
                System.out.println(
                        "FIELD " + error.getField() + ": "
                                + error.getDefaultMessage()));

        errors.getGlobalErrors().forEach(error ->
                System.out.println(
                        "GLOBAL " + error.getCode() + ": "
                                + error.getDefaultMessage()));
    }

    public static void main(String[] args) {
        report("OK", new MeetingSlot("Team meeting", 9, 10));
        report("BAD", new MeetingSlot(" ", 11, 10));

        try {
            SLOT_VALIDATOR
                    .validateObject(new MeetingSlot(" ", 11, 10))
                    .failOnError(IllegalArgumentException::new);
        } catch (IllegalArgumentException exception) {
            System.out.println("THROWN: "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

In the project directory, with **JDK 17+** and Maven, run:

~~~bash
mvn -q compile exec:java
~~~

Expected output:

~~~text
OK: errors=0
BAD: errors=2
FIELD title: Title must not be blank
GLOBAL time.order: End hour must be after start hour
THROWN: IllegalArgumentException
~~~

In the first case, the 9–10 meeting slot has a valid title, so no errors occur. In the second case, `title` consists only of whitespace and the end hour is earlier than the start hour; the validator records **one property error** and **one object-wide error**, so `getErrorCount()` equals 2. Finally, `failOnError(...)` turns the invalid result into an exception. The program prints only the exception class name; the detailed message depends on how `Errors` formats its summary.

The example uses a validator created via `Validator.forInstanceOf`. If your project already has traditional classes implementing `Validator`, you can call `validateObject` on them the same way without using the factory. `forInstanceOf` simply shortens declaring the validator and checking the supported target type.

## 3. Reading the Result Returned by `validateObject`

`validateObject` returns **`org.springframework.validation.Errors`**, Spring's API for inspecting and recording errors. Do not cast the result to `BindingResult`, because the default implementation uses `SimpleErrors`, not a binder result.

| Method | When to Use |
| --- | --- |
| `hasErrors()` | Quick check for any errors; decides whether to halt the flow. |
| `getErrorCount()` | Total count of field + global errors, e.g., in tests or reports. |
| `getFieldErrors()` | Errors tied to property names, convenient for per-input error reporting. |
| `getFieldError("title")` | First error specifically for `title`, which may be `null`. |
| `getGlobalErrors()` | Errors not tied to a single property, such as the start/end rule. |
| `getAllErrors()` | All errors as `ObjectError` and `FieldError` instances. |
| `getObjectName()` | Name of the object the result describes. |
| `failOnError(IllegalArgumentException::new)` | Does nothing if valid; if errors exist, throws an exception created from the error summary string. |

Inspecting a `FieldError`:

~~~java
Errors errors = SLOT_VALIDATOR.validateObject(
        new MeetingSlot(" ", 11, 10));

errors.getFieldErrors().forEach(error -> {
    String field = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
    // Put field/code/message into an appropriate response structure.
});
~~~

`getCode()` is the error code for programmatic handling or message lookup; `getDefaultMessage()` is the fallback message, which may be `null` if the validator did not supply one. User-facing presentation can use `MessageSource` to localize by error code. Do not use translated message strings directly in business branching conditions.

When you need to **throw immediately** instead of branching manually:

~~~java
SLOT_VALIDATOR.validateObject(slot)
        .failOnError(IllegalArgumentException::new);
~~~

`failOnError` is a default method on `Errors`, also introduced in Spring Framework 6.1. The supplied function receives an error summary string and creates an exception. You can pass `IllegalStateException::new` or an application-specific exception factory if that is how the calling layer manages errors. Avoid throwing exceptions at boundaries that need to collect **multiple errors for simultaneous display** unless a matching handler translates them.

### Why Does `supports(Class<?>)` Still Exist?

`supports` remains an important Spring `Validator` contract: it tells orchestrating components which types a validator handles. In a manually implemented class:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return MeetingSlot.class.isAssignableFrom(clazz);
}
~~~

Remember that the default `validateObject(target)` method simply creates `SimpleErrors` and calls `validate(target, errors)`; by itself it **does not invoke `supports` as a mandatory filter**. Passing the wrong object type to a validator that casts directly can trigger a `ClassCastException`. In direct-call code, select the right validator for the type, or use typed factories like `forInstanceOf`/`forType` with appropriate type-support semantics.

## 4. Important Limitations of `SimpleErrors`

`validateObject`'s convenience comes from Spring creating a `SimpleErrors` automatically. However, **`SimpleErrors` is designed for a single top-level object**, with limitations compared to `BeanPropertyBindingResult` or `DataBinder`.

### 4.1. No Nested-Path Navigation Support

For example, an `Order` validator needs to invoke an `Address` validator like this:

~~~java
// Illustrates a nested validator fragment (not a standalone runnable example).
try {
    errors.pushNestedPath("address");
    addressValidator.validate(order.getAddress(), errors);
} finally {
    errors.popNestedPath();
}
~~~

The `pushNestedPath("address")`/`popNestedPath()` flow requires an `Errors` implementation that supports nested-path context switching. `SimpleErrors` does not support this operation; calling it can throw `UnsupportedOperationException`. Therefore, **do not use `validateObject` directly for validators that rely on nested paths**.

If nested-object validation is needed, create an `Errors` instance capable of property binding/navigation:

~~~java
// Use the appropriate Spring imports; snippet inside an application.
Errors errors = new BeanPropertyBindingResult(order, "order");
orderValidator.validate(order, errors);
~~~

Afterward, `errors.hasErrors()` and `getFieldErrors()` work as usual. For real HTTP requests that also involve binding and conversion, use `DataBinder`/`WebDataBinder` or standard Spring MVC integration.

Do not assume every validator written for `BeanPropertyBindingResult` is automatically compatible with `SimpleErrors`. Check whether it uses `pushNestedPath`, `setNestedPath`, or relies on binding-related state.

### 4.2. Does Not Perform Data Binding, Type Conversion, or Binding Error Recording

`validateObject` only **validates an existing object**; if a user types `"abc"` into a numeric field, this method does not parse the string into a number and does not record `typeMismatch` errors the way `DataBinder` can. Binding errors must be collected during a separate binding step.

Comparing the two flows:

~~~text
A. Already-constructed Java object:
   object -> validator.validateObject(object) -> Errors
                    |
             read errors / failOnError

B. Web/form data needing binding:
   request/raw values -> DataBinder/WebDataBinder
                      -> conversion + binding errors
                      -> validation
                      -> BindingResult
                      -> handle errors or proceed
~~~

In case B, a direct programmatic flow with `DataBinder` looks like:

~~~java
// Snippet; target and properties are prepared by the application.
DataBinder binder = new DataBinder(target, "target");
binder.setValidator(validator);
binder.bind(properties);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Includes both binding errors and registered validation errors.
}
~~~

`DataBinder.validate()` and `Validator.validateObject(...)` **are not two names for the same process**. The former operates within the binder context and reports through `BindingResult`; the latter creates a standalone `SimpleErrors` for a single check.

### 4.3. Does Not Run Jakarta Bean Validation Automatically for Every Object

`org.springframework.validation.Validator` is a Spring API, distinct from `jakarta.validation.Validator`. Do not confuse:

~~~java
// Spring Validator: returns Errors.
org.springframework.validation.Errors errors =
        springValidator.validateObject(input);
~~~

with:

~~~java
// Jakarta Bean Validation: returns Set<ConstraintViolation<T>>.
// Snippet; requires a configured jakarta.validation.Validator.
var violations = jakartaValidator.validate(input);
~~~

If you only create `Validator.forInstanceOf(...)` as in the example, `@NotNull`/`@Size` annotations on a DTO **will not execute automatically**; you must write validator logic or configure a proper Bean Validation provider/adapter. Conversely, Spring integrates Bean Validation via `LocalValidatorFactoryBean`/MVC mechanisms when configured, but that is one specific validator implementation, not the default behavior of every `Validator`.

### 4.4. Does Not Replace Business Decisions

If `errors.hasErrors()` is `false`, it only means *the rules executed by that validator produced no errors*. It does not guarantee the caller has permission, the resource still exists, a value remains unique in the DB, or transactional conditions hold. Essential checks must still live in the appropriate service, domain, or transaction boundary.

Pattern before performing side effects:

~~~java
// Application service snippet.
Errors errors = bookingValidator.validateObject(request);
if (errors.hasErrors()) {
    return BookingResult.invalid(errors.getAllErrors());
}

return bookingService.reserve(request);
~~~

Here `BookingResult` and `bookingService` are illustrative application components. The key point is **rejecting invalid input before executing the reservation operation**.

## 5. When Should You Choose `validateObject`?

| Situation | Appropriate Choice | Reason |
| --- | --- | --- |
| Java object already built and needs simple validator execution in a service | `validator.validateObject(object)` | Minimal boilerplate; creates `Errors` automatically for the check. |
| Need to quickly throw an exception if the object is invalid | `validator.validateObject(object).failOnError(...)` | Single clear statement using Spring's standard error mechanism. |
| Validator needs `pushNestedPath`/`popNestedPath` for child objects | `validator.validate(object, new BeanPropertyBindingResult(...))` | Requires an `Errors` implementation supporting nested paths. |
| Need to bind raw form values into a DTO and capture conversion errors | `DataBinder`/`WebDataBinder` | Provides binding context and `BindingResult`. |
| Handling `@Valid @ModelAttribute` or `@Valid @RequestBody` in Spring MVC | MVC validation mechanism + `BindingResult`/exception handler | Spring manages resolvers, binding, validation, and HTTP responses. |
| Using constraint annotations like `@NotNull`, `@Min`, `@Pattern` | Appropriate Jakarta Bean Validation provider/adapter | Annotation-based validation is a separate mechanism requiring configuration. |

There is no requirement to “upgrade all code to `validateObject`” starting in Spring 6.1. If a validator relies on a binder or nested paths, the classic pattern remains right. The new method shines in **direct validation** scenarios with compatible validators.

## 6. Writing Tests for Both Branches and Support Limits

With `validateObject`, tests should verify actual validator behavior, not merely that an `Errors` object is returned.

**Valid case:**

~~~java
// Snippet suitable for a configured JUnit 5 test.
Errors result = SLOT_VALIDATOR.validateObject(
        new MeetingSlot("Review", 8, 9));

assertFalse(result.hasErrors());
assertEquals(0, result.getErrorCount());
~~~

**Case with both field and global errors:**

~~~java
Errors result = SLOT_VALIDATOR.validateObject(
        new MeetingSlot("", 11, 10));

assertTrue(result.hasErrors());
assertTrue(result.hasFieldErrors("title"));
assertTrue(result.hasGlobalErrors());
assertEquals(2, result.getErrorCount());
~~~

**Exception case:**

~~~java
assertThrows(IllegalArgumentException.class,
        () -> SLOT_VALIDATOR
                .validateObject(new MeetingSlot("", 11, 10))
                .failOnError(IllegalArgumentException::new));
~~~

These tests are **snippets for a test class** and should not be pasted into section 2's demo file without adding JUnit dependencies, static imports, and appropriate visibility. If testing from another class, give the validator suitable access scope.

If a project has nested validators, test the `pushNestedPath` path separately with `BeanPropertyBindingResult`. Do not force `SimpleErrors` to perform behavior its API explicitly does not support.

## 7. Common Mistakes When Using the New API

1. **Casting `Errors` to `BindingResult`**: `validateObject` returns `SimpleErrors` by default; casting to `BindingResult` can throw `ClassCastException`.
2. **Assuming `validateObject` bound web data**: it does not read raw requests or catch type conversion errors; bind earlier in the right layer.
3. **Calling with the wrong object type**: the default method does not check `supports(...)` automatically; select the proper validator and avoid blind casts.
4. **Passing a nested-path-dependent validator to `validateObject`**: `SimpleErrors` lacks nested-path navigation; use an `Errors` implementation that supports it.
5. **Throwing and then ignoring the exception**: `failOnError` throws on errors. A handler or caller must surface the failure per contract rather than letting persistence continue.
6. **Assuming Spring validators run all Jakarta annotations automatically**: a Bean Validation provider/adapter is required for constraint annotations.
7. **Using display messages as business codes**: `getDefaultMessage()` can vary by language or configuration; rely on explicit error codes.
8. **Failing to check errors before side effects**: `validateObject` only helps if errors actually abort the flow before DB writes or event publishing.
9. **Reusing `Errors` across objects or threads**: `validateObject` returns a new result each call; keep each result tied to its target object. `Errors` is not designed for concurrent multi-threaded access.

## 8. Project Adoption Checklist

When direct validation is needed in Spring 6.1+, follow this sequence:

1. Select the right `org.springframework.validation.Validator` for your object's class; verify `supports(...)` if validator selection is dynamic.
2. Confirm the validator does not rely on nested-path navigation or binding context absent in `SimpleErrors`.
3. Call `Errors errors = validator.validateObject(object)`.
4. Use `hasErrors()` to branch, `getFieldErrors()`/`getGlobalErrors()` to build a response, or `failOnError(...)` to raise a deliberate exception.
5. Proceed to business operations only after input is valid and authorization, state, and invariant checks pass.
6. Test valid cases, multi-field failures, global errors, exception throwing, and the binder path separately if your app accepts raw requests.

Minimal pattern to remember:

~~~java
Errors result = validator.validateObject(input);
result.failOnError(IllegalArgumentException::new);
// Execution reaches this line only if the validator recorded no errors.
~~~

### Official Spring Documentation

- [Spring Framework — Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/6.1/core/validation/validator.html)
- [Spring 6.1 — `Validator.validateObject(Object)` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Validator.html)
- [Spring 6.1 — `SimpleErrors` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/SimpleErrors.html)
- [Spring 6.1 — `Errors.failOnError(...)` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Errors.html)
- [Spring 6.1 — `BeanPropertyBindingResult` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html)
