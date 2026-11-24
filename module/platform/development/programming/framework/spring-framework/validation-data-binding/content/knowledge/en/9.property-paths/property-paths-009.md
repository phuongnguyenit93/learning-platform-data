# Distinguishing Invalid Fields from Unknown Fields in Spring DataBinder

When Spring binds external data onto a Java object by **property path**, not every error carries the same meaning. Two easily confused terms in the `DataBinder` API are **unknown field** and **invalid field**:

- **Unknown field**: the field name from the input data **does not correspond to a bindable property** on the target object. For example, a `Profile` object only has `age` and `address`, yet the request sends `nickname`.
- **Invalid field (unreachable path)**: the path points to a property that exists in the object model, yet **cannot be reached in the current object graph**. For example, `address.city` is structurally valid, yet `profile.address == null` and binding does not auto-create `Address`.

In `DataBinder#setIgnoreInvalidFields` terminology, *invalid* **does not mean** "the value violates `@NotBlank` or `@Min`," nor does it mean "failed to convert a string to a number." Those failures must be categorized separately.

This lesson applies primarily to **property binding with `DataBinder.bind(PropertyValues)`** in Spring Framework 6.x, with Java 17 examples. It also explains how it relates to Spring MVC `@ModelAttribute`, configuration flags, and testing.

## 1. First, understand property paths

Spring uses input key names to locate where to bind on a Java object:

```text
Profile
├── age: Integer
└── address: Address
    └── city: String

"age"           -> Profile.age
"address.city"  -> Profile.address.city
"nickname"      -> no matching property
```

In default mode, `DataBinder` binds properties per JavaBean conventions: setters like `setAge(...)` and `setAddress(...)`, getters to traverse nested objects, and convertible types. The dot in `address.city` denotes accessing a property of a child object, not a single Java field name.

Separate three questions:

1. **Does the property name exist and is it writable?** If not, it is an *unknown field* candidate.
2. **Can the path traverse all intermediate objects?** If a `null` branch is not auto-created, it is an *invalid field* in the sense of "unreachable path."
3. **Can the value convert to the target type and satisfy rules?** If not, it may be a conversion failure or validation failure, with separate handling.

A path like `address.city` can be "structurally valid" yet "untraversable at bind time." That is the most important distinction between the two concepts in this lesson.

## 2. Quick comparison table

| Scenario | Matching property exists? | Actual issue | Related mechanism |
| --- | --- | --- | --- |
| `nickname=Lan` while `Profile` lacks `nickname` | No | **Unknown field** | `setIgnoreUnknownFields(...)` |
| `address.city=Hanoi`, `address == null`, auto-grow off | Yes | **Invalid field** due to unreachable intermediate branch | `setIgnoreInvalidFields(...)`; `setAutoGrowNestedPaths(...)` |
| `age=abc` with `age: Integer` | Yes; reachable | **Type mismatch**: conversion failed | Conversion mechanism and `BindingResult` |
| `age=16` with minimum age 18 rule | Yes; convertible | **Validation failure**: rule violated | `Validator`/`validate()` or Bean Validation |
| `role=ADMIN` while `setAllowedFields("age")` | `role` may exist on bean | **Suppressed/disallowed field**: intentionally blocked from binding | `setAllowedFields(...)`; `getSuppressedFields()` |

The first column **is not** a security check result. A field recognized and bound by Spring may still be off-limits for business modification. Use dedicated DTOs and restrict which fields can be bound externally.

## 3. Unknown field: a field name with no target to bind

Suppose:

```java
public class Profile {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Input with key `age` finds a matching setter. Input with key `nickname` has no matching property on `Profile`. This is an unknown field. The Java snippet above only illustrates bean structure; a complete runnable example is in section 7.

### 3.1. setIgnoreUnknownFields defaults to true

On a standard `DataBinder`:

```java
binder.setIgnoreUnknownFields(true);
```

This is the **default**. When binding `nickname=Lan`, the binder **ignores the unrecognized field**. It does not invent `nickname` on the bean, nor does it turn it into a `Validator` error automatically. Depending on API requirements, ignoring is convenient for forms carrying extra helper fields, yet it can hide client typos.

For example, a client sends `ag=20` instead of `age=20`: if `ag` is absent on the bean, Spring ignores it by default, leaving `age` at its prior value or `null`. Therefore do not treat `bind()` completing without exceptions as proof that every client key was applied.

### 3.2. setIgnoreUnknownFields(false) to require matching properties

To catch unrecognized names at the property binding step:

```java
binder.setIgnoreUnknownFields(false);
```

Then calling `bind(...)` with an unmatched key can throw `NotWritablePropertyException` (a kind of `InvalidPropertyException` in Spring Beans). In the `nickname` example, this is a **property accessibility** failure, not a length or format validation constraint.

**Do not assume** strict mode creates a `FieldError` inside `BindingResult` like `age=abc` does. Unknown/invalid cases can be ignored or throw exceptions depending on configuration; test the corresponding exception handling branch explicitly.

The scope of this flag is property binding with `bind(PropertyValues)`. It does not mean every lookup via `BindingResult`, every constructor-based object creation, or every JSON request obeys the exact same flag.

## 4. Invalid field: an existing path that cannot be reached

Suppose `Profile` has property `address: Address` and `Address` has `city: String`. Submitted data:

```text
address.city=Hanoi
```

The path name is **correct**. However, if `profile.getAddress() == null`, the binder must cross a non-existent branch to call `setCity("Hanoi")`.

### 4.1. Why does auto-grow change the outcome?

`DataBinder` enables by default:

```java
binder.setAutoGrowNestedPaths(true);
```

If the nested object type can be instantiated in a way Spring supports (such as `Address` having a public no-arg constructor), the binder can create an `Address` and set `city`. Because **no null branch blocks traversal**, `address.city` binds cleanly.

To observe an *invalid field*, an educational example explicitly disables this feature:

```java
binder.setAutoGrowNestedPaths(false);
```

If `address` remains `null`, accessing `address.city` encounters an untraversable path. This typically raises `NullValueInNestedPathException`, a subclass of `InvalidPropertyException`.

Do not confuse with unknown field: `city` exists on `Address`. The problem is that **the `Address` instance does not yet exist at the intermediate step**.

### 4.2. setIgnoreInvalidFields defaults to false

By default:

```java
binder.setIgnoreInvalidFields(false);
```

The binder does not silently skip paths that exist in the model yet are currently unreachable. When encountering a `null` branch it cannot instantiate, binding can throw an exception. Enabling:

```java
binder.setIgnoreInvalidFields(true);
```

lets the binder **ignore parameters targeting non-existent branches of the object graph**, such as `address.city` when `address == null` and auto-grow is disabled.

**Key takeaway:** this is not a "skip every invalid value" flag. It does not replace conversion, validation, authorization, input limits, or handling other exceptions.

### 4.3. Effect matrix of the flags in a concrete scenario

Suppose `Profile.address == null`, `Address` is a JavaBean with a default constructor, and the request contains `address.city=Hanoi`:

| autoGrowNestedPaths | ignoreInvalidFields | Expected result |
| --- | --- | --- |
| `true` (default) | `false` (default) | Spring auto-creates `Address` and sets `city` if instantiable |
| `false` | `false` | Path is unreachable; typically throws `NullValueInNestedPathException` |
| `false` | `true` | Skips value targeting non-existent branch; `address` remains `null` |

If `Address` cannot be instantiated, or the property path has another issue, a different error can occur. Check the exact runtime exception rather than generalizing that every nested path auto-creates cleanly.

## 5. Do not equate invalid fields with invalid values

The word "invalid" in validation docs sometimes means "bad value." However, `setIgnoreInvalidFields(...)` refers to **path reachability during binding**.

### 5.1. Correctly named field that fails conversion

With `age: Integer`, `age=abc` targets a real, reachable property. The failure is that `"abc"` cannot convert to `Integer`. In standard binding, Spring records a `FieldError`, typically with base code `typeMismatch`, in `BindingResult`.

```java
BindingResult result = binder.getBindingResult();
for (FieldError error : result.getFieldErrors()) {
    System.out.println(error.getField()
            + " -> bindingFailure=" + error.isBindingFailure());
}
```

`FieldError.isBindingFailure()` helps identify errors coming from binding; tests for error codes should not depend on exact wording from a specific Spring version.

Setting `setIgnoreUnknownFields(true)` or `setIgnoreInvalidFields(true)` **does not turn `age=abc` into a valid age**, nor should those flags be used to hide conversion errors.

### 5.2. Correctly typed field that fails a business rule

The string `age=16` converts to `Integer 16`. If the application rule is "age at least 18," only after running a Spring `Validator` or Bean Validation does a constraint error appear.

```java
@Override
public void validate(Object target, Errors errors) {
    Profile profile = (Profile) target;
    if (profile.getAge() != null && profile.getAge() < 18) {
        errors.rejectValue("age", "age.min", "Age must be at least 18");
    }
}
```

This snippet is part of an `org.springframework.validation.Validator` implementation; the complete example shows the class, imports, and registration. Errors added by `errors.rejectValue(...)` normally have `isBindingFailure() == false`.

**Four distinct outcomes, not one:**

- Unknown: binder finds no matching property.
- Invalid path: binder knows the property yet cannot reach it.
- Type mismatch: binder finds and reaches the property yet cannot convert the value to the Java type.
- Validation failure: the Java value exists yet violates a constraint.

## 6. Are unknown, invalid, and suppressed fields the same?

**No.** `BindingResult.getSuppressedFields()` identifies fields excluded from binding by allowed/disallowed field policies. For example:

```java
binder.setAllowedFields("age", "address.city");
```

If the real object also has a `role` property and the client sends `role=ADMIN`, the binder skips `role` because it is absent from the allowlist. After binding, `getSuppressedFields()` can report that `role` was blocked.

This **differs** from `nickname` not existing on the bean at all. Unknown fields ignored by default do not automatically become suppressed fields. Nor should `getSuppressedFields()` be treated as a complete list of all binding errors; it specifically represents values rejected by the binding allow/disallow policy.

For data protection, **merely disabling unknown-field ignoring is insufficient**. A sensitive field like `role` *genuinely exists* and has a setter; it will not be treated as unknown. For external inputs, prefer DTOs containing only needed fields, constructor binding where appropriate, and an allowlist for property binding.

## 7. Runnable Java 17 example: observing each error type

This example uses **Spring Framework 6.2** directly with no HTTP server. Each scenario uses a fresh `Profile` and `DataBinder` so results do not leak across scenarios.

Directory structure:

```text
spring-field-paths/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/paths/FieldPathDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-field-paths'
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
    mainClass = 'demo.paths.FieldPathDemo'
}
```

`spring-context` brings in the dependencies needed to use `DataBinder`, `MutablePropertyValues`, and `Validator`. In a Spring Boot application with dependency management, let Boot manage the Spring component versions rather than copying this pinned version.

Create `src/main/java/demo/paths/FieldPathDemo.java` with:

```java
package demo.paths;

import org.springframework.beans.InvalidPropertyException;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;

public class FieldPathDemo {

    // Child bean: has a no-arg constructor so Spring can auto-grow.
    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Profile {
        private Integer age;
        private Address address;

        public Profile() {
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class ProfileValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Profile.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Profile profile = (Profile) target;
            if (profile.getAge() != null && profile.getAge() < 18) {
                errors.rejectValue(
                        "age", "age.min", "Age must be at least 18");
            }
        }
    }

    private static void bindCase(
            String label,
            String field,
            String inputValue,
            boolean ignoreUnknown,
            boolean ignoreInvalid,
            boolean autoGrow) {

        Profile profile = new Profile();
        DataBinder binder = new DataBinder(profile, "profile");
        binder.setIgnoreUnknownFields(ignoreUnknown);
        binder.setIgnoreInvalidFields(ignoreInvalid);
        binder.setAutoGrowNestedPaths(autoGrow);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add(field, inputValue);

        try {
            binder.bind(values);
            BindingResult result = binder.getBindingResult();
            String city = profile.getAddress() == null
                    ? "null" : profile.getAddress().getCity();

            System.out.println(label
                    + ": OK; errors=" + result.getErrorCount()
                    + "; city=" + city
                    + "; age=" + profile.getAge());

            for (FieldError error : result.getFieldErrors()) {
                System.out.println("  " + error.getField()
                        + ": bindingFailure=" + error.isBindingFailure());
            }
        } catch (InvalidPropertyException exception) {
            // Catch strict property path errors rather than treating them
            // as regular FieldErrors in BindingResult.
            System.out.println(
                    label + ": " + exception.getClass().getSimpleName());
        }
    }

    private static void validationCase() {
        Profile profile = new Profile();
        DataBinder binder = new DataBinder(profile, "profile");
        binder.setValidator(new ProfileValidator());

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("age", "16");

        binder.bind(values);
        System.out.println("rule-before-validate: errors="
                + binder.getBindingResult().getErrorCount());

        binder.validate();
        FieldError error =
                binder.getBindingResult().getFieldError("age");

        System.out.println("rule-after-validate: errors="
                + binder.getBindingResult().getErrorCount()
                + "; bindingFailure=" + error.isBindingFailure());
    }

    public static void main(String[] args) {
        // Field does not exist on Profile.
        bindCase("unknown-ignored",
                "nickname", "Lan", true, false, false);
        bindCase("unknown-strict",
                "nickname", "Lan", false, false, false);

        // Field exists, yet Profile.address is null.
        bindCase("invalid-strict",
                "address.city", "Hanoi", true, false, false);
        bindCase("invalid-ignored",
                "address.city", "Hanoi", true, true, false);
        bindCase("invalid-auto-grow",
                "address.city", "Hanoi", true, false, true);

        // Property is reachable, yet value has the wrong type.
        bindCase("type-mismatch",
                "age", "abc", true, false, false);

        // Property has the right type, yet value violates a rule.
        validationCase();
    }
}
```

With Gradle installed, run from the project directory:

```bash
gradle -q run
```

If the project has a Gradle Wrapper, substitute `./gradlew -q run` (Unix/macOS) or `gradlew.bat -q run` (Windows). Once Gradle downloads dependencies, the expected output from `main` is:

```text
unknown-ignored: OK; errors=0; city=null; age=null
unknown-strict: NotWritablePropertyException
invalid-strict: NullValueInNestedPathException
invalid-ignored: OK; errors=0; city=null; age=null
invalid-auto-grow: OK; errors=0; city=Hanoi; age=null
type-mismatch: OK; errors=1; city=null; age=null
  age: bindingFailure=true
rule-before-validate: errors=0
rule-after-validate: errors=1; bindingFailure=false
```

The exception classes in this example are typical for the chosen paths in Spring 6.2. Changing field access mode, instantiation capability, or converters can alter outcomes; when testing, verify exact exception types and bean state directly.

### 7.1. Analyzing the six binding runs

- **`unknown-ignored`:** `nickname` does not exist on `Profile`. With `ignoreUnknownFields=true`, Spring skips it; no property is added and no validation error appears.
- **`unknown-strict`:** same key, yet `ignoreUnknownFields=false`. Spring rejects it for lacking a writable property and throws `NotWritablePropertyException`.
- **`invalid-strict`:** `address.city` has valid structure, yet `address=null` and `autoGrowNestedPaths=false`. Because `ignoreInvalidFields=false`, the binder does not skip the path and raises `NullValueInNestedPathException`.
- **`invalid-ignored`:** same null path, yet `ignoreInvalidFields=true`. Spring skips the assignment; `address` stays `null`.
- **`invalid-auto-grow`:** with `autoGrowNestedPaths=true`, Spring instantiates `Address` via its default constructor and sets `city="Hanoi"`.
- **`type-mismatch`:** `age` exists and is reachable, yet `"abc"` cannot convert to `Integer`. The binder records a conversion error; `age` on the new bean stays `null`.

`validationCase()` is separated to demonstrate that `16` converts to `Integer 16`. After `bind()` there are 0 errors; after `validate()` there is 1 error from `ProfileValidator`, with `isBindingFailure=false`.

Notably, both *unknown-ignored* and *invalid-ignored* produce zero `FieldError` entries. Ignoring an input value can leave a bean **missing data without any error**. Never call `result.hasErrors()` alone and assume every client-submitted field was received.

## 8. When changing settings, what exactly should you check?

| Setting | DataBinder default | Primary effect |
| --- | --- | --- |
| `setIgnoreUnknownFields(boolean)` | `true` | Ignores or rejects keys lacking a matching property |
| `setIgnoreInvalidFields(boolean)` | `false` | Ignores or rejects paths that are currently unreachable |
| `setAutoGrowNestedPaths(boolean)` | `true` | Can auto-create null nested objects during property binding |
| `setAllowedFields(String...)` | All fields considered | Permits only listed paths / valid patterns |
| `setRequiredFields(String...)` | No required fields | Checks field presence during the binding phase |
| `setValidator(...)` or `addValidators(...)` | No custom validator by default | Registers constraint validators invoked by `validate()` |

The first three flags **do not have the same effect** and should not be toggled arbitrarily just to "let requests pass." For example, if you turn off ignore-unknown to catch typos, the app needs exception handling and an HTTP error contract; toggling the flag alone does not generate a structured 400 response.

**Scope:** these flags describe setter/field binding with `bind(PropertyValues)`. They do not apply identically to constructor binding (`DataBinder.construct(...)`), which resolves values via constructor parameters. Consult the API docs for your Spring version when mixing binding strategies.

## 9. Relationship to @ModelAttribute and @RequestBody

### 9.1. Form/query with @ModelAttribute

In Spring MVC, `WebDataBinder` processes eligible request data to bind onto `@ModelAttribute` objects. This is where property path rules and binder settings directly apply.

Illustrative snippet in a controller where beans are already defined:

```java
@InitBinder("profile")
void configureProfile(WebDataBinder binder) {
    binder.setAllowedFields("age", "address.city");
    binder.setIgnoreUnknownFields(false);
    binder.setIgnoreInvalidFields(false);
}
```

The code above is **part of a controller**, not a standalone program. If an endpoint declares `@ModelAttribute("profile") Profile profile`, ensure `Profile` is bindable and nested object instantiation fits. The name `profile` in `@InitBinder` must match the object name used by the binder.

Do not assume every exception thrown from an unknown/invalid path automatically becomes a `BindingResult` with a `FieldError`: some strict property-path errors can escape as exceptions. For API design, decide explicitly whether to ignore unknown keys, return errors, or accept only an allowlisted set of fields.

### 9.2. JSON with @RequestBody

With `@RequestBody` receiving JSON, Spring normally uses an `HttpMessageConverter` (e.g., Jackson) to build the DTO. Unrecognized JSON properties obey **JSON deserializer/Jackson** configuration rules, not `DataBinder#setIgnoreUnknownFields`. If JSON has a nested `address` object, constructing the nested DTO also belongs to that deserialization mechanism.

Therefore, **do not extrapolate `DataBinder.bind(PropertyValues)` ignore-unknown/invalid behavior to JSON**. Verify each ingestion path: forms/queries, constructor binding, JSON bodies, and specific framework configurations.

### 9.3. BindingResult and HTTP responses

In a form controller, a `BindingResult` placed immediately after the `@ModelAttribute` parameter captures conversion and validation errors. However, unknown/invalid paths in strict mode can throw exceptions during binding and must be handled properly. Do not use `getSuppressedFields()` to infer every unrecognized field.

At the HTTP layer, never return internal exception class names, secret values, or stack traces to clients. Design public error messages such as "unsupported field," "cannot bind property path," or "invalid data type" per error category, and test with real requests.

## 10. Edge cases to know

### 10.1. Nested paths with non-instantiable types

`autoGrowNestedPaths=true` enables auto-creating eligible branches, **not a guarantee** every type can be created. Missing constructors, blocked properties, complex collections, or insufficient type metadata can still throw exceptions. Do not treat `ignoreInvalidFields=true` as a catch-all workaround for instantiation failures.

### 10.2. Typos midway through a path

If a client sends `address.ctiy` instead of `address.city`, once the path reaches `Address`, the leaf property name `ctiy` does not exist. That situation involves an **unknown property**, distinct from `address.city` being spelled right while `address == null` with auto-grow off. In complex graphs, which segment fails first depends on object state and accessor implementation, so test against real DTOs.

### 10.3. Read-only properties

Having a getter without a matching setter in JavaBean property binding means the property is unwritable. A client-sent field can trigger `NotWritablePropertyException` in strict mode. Never assume "having a getter" is enough to make a path bindable.

### 10.4. Collection indices and auto-grow limits

Paths like `items[0].name` also depend on whether the collection holds the element or can expand. `DataBinder` enforces an auto-grow collection limit to prevent runaway allocation. For untrusted inputs, cap element counts, depth, and bindable fields; a huge index is not merely an "unknown field."

### 10.5. Disallowed fields may still exist on the bean

If `role` genuinely has a setter, `setIgnoreUnknownFields(false)` will **not block it simply because it is dangerous**. Use a DTO restricting writable properties and an allowlist aligned with the input contract. Restricting allowed paths is especially vital when binding nested properties from requests.

### 10.6. Invalid field vs. validation failure on nested objects

An instantiated `Address` with `city=""` is a **reachable path**. To reject blank city names, enforce a rule (Spring `Validator` or Bean Validation). Setting `setIgnoreInvalidFields(false)` will not automatically reject an empty string.

## 11. Valuable test strategies

Plan tests that separate each case; avoid relying solely on a single `hasErrors()` boolean.

| Test | Verification target |
| --- | --- |
| Default unknown | Does not create unknown property; `bind()` can finish with no `FieldError` |
| Strict unknown | `setIgnoreUnknownFields(false)` rejects unknown key; verify exception |
| Invalid with auto-grow off | `address == null`, submitting `address.city` makes path unreachable |
| Ignored invalid | `setIgnoreInvalidFields(true)` skips matching branch; confirm bean untouched |
| Auto-grow active | Instantiates `Address` with suitable constructor and sets `city` |
| Type mismatch | `age=abc` creates conversion error with `isBindingFailure() == true` |
| Validation failure | `age=16` binds; after `validate()`, rule error is recorded |
| Disallowed field | `setAllowedFields(...)` blocks field; `getSuppressedFields()` reflects it |
| Spring MVC form | Returns appropriate error status for binding errors or strict path errors |
| JSON body | Unknown JSON property behavior tested via deserializer config, not inferred from DataBinder |

In console tests, create a fresh bean and binder per case. In web MVC, use `MockMvc` to simulate forms/queries, asserting response status and ensuring internal details are not leaked. If your app maps exceptions to API error payloads, test that branch too.

## 12. Common misconceptions

1. **"Invalid field means age 16 is invalid:"** in `setIgnoreInvalidFields`, it means an unreachable path. Age 16 is a validation failure if a minimum age rule exists.
2. **"Setting `ignoreInvalidFields=true` skips all type mismatches:"** false; conversion errors use a separate mechanism and usually appear in `BindingResult`.
3. **"Assuming unknown fields always produce a `FieldError`:"** Spring ignores them by default; strict mode can throw `NotWritablePropertyException`.
4. **"Assuming nested paths with `null` always error:"** `autoGrowNestedPaths=true` can auto-create branches and bind cleanly.
5. **"Assuming `address.city` and `address.ctiy` are the same error:"** one can be a valid path that is null; the other is a non-existent property name.
6. **"Relying on `getSuppressedFields()` to detect unknown fields:"** suppressed generally reports fields blocked by allowed/disallowed field policies.
7. **"Disabling `ignoreUnknownFields` prevents mass assignment:"** sensitive properties that actually exist can still bind; use DTOs and allowlists.
8. **"Assuming Spring MVC JSON uses these flags like forms:"** `@RequestBody` goes through message converters and deserializers.
9. **"Flipping the defaults mentally:"** `ignoreUnknownFields=true`, `ignoreInvalidFields=false`, `autoGrowNestedPaths=true` on a standard `DataBinder`.
10. **"Not separating exceptions from accumulated errors:"** mistyped inputs like `age=abc` normally create `FieldError`; unknown/invalid paths in strict mode can throw exceptions that must be handled explicitly.

## 13. Self-practice

**Scenario A:** `Profile` has `address`, currently `null`. The client sends `address.city=Da Nang`. Predict the outcome when toggling `autoGrowNestedPaths` and `ignoreInvalidFields`; explain why changing these flags does not make `city` an "unknown" property.

**Scenario B:** The client sends `address.ciy=Da Nang`. Explain how to verify `ciy` is a misspelled name and distinguish it from `address.city` when `address` lacks an instance.

**Scenario C:** The client sends `age=abc` and `age=16` to a bean with `Integer age`. Distinguish the order of binding, conversion, and validation; explain when `FieldError.isBindingFailure()` is `true` and when it is `false`.

**Scenario D:** A form bean has a `role` property, yet only `age` and `address.city` should be editable. Why does `setIgnoreUnknownFields(false)` fail to solve this? Identify the roles of `setAllowedFields(...)` and an input DTO.

You have mastered this lesson when you can distinguish: **unknown = no matching property to bind; invalid = property path exists yet cannot be reached; type mismatch = value cannot convert; validation failure = value exists yet fails a rule.**

## References

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html).
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html).
- [Spring Framework — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html).
- [Spring Framework — NullValueInNestedPathException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html).
