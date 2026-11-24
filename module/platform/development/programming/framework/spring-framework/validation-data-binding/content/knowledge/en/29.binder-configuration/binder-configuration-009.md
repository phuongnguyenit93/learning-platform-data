# Replacing or Adding Validators Without Accidentally Losing Defaults in Spring MVC

## 1. The Problem: Adding a Small Rule Drops `@NotBlank`

You have a signup form validated by Jakarta Validation in Spring MVC:

```java
public class SignupForm {
    @NotBlank
    private String username;

    @Email
    private String email;

    // getters/setters...
}
```

Now the business requires forbidding `admin` and `root`. You write a Spring `Validator`:

```java
public final class ReservedUsernameValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())
                || "root".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                    "username", "username.reserved", "This username is reserved");
        }
    }
}
```

This is an illustrative snippet requiring imports for `org.springframework.validation.Validator`, `Errors`, and a complete `SignupForm` class. If you register it in the controller using:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setValidator(new ReservedUsernameValidator());
}
```

you can accidentally **replace** the global Bean Validation validator attached to the binder by the framework. Then your custom rule runs, yet `@NotBlank`, `@Email`, and other constraints are no longer evaluated by that binder.

In a typical Spring MVC application, when you want to **add** a local Spring `Validator` alongside the default validator, use:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.addValidators(new ReservedUsernameValidator());
}
```

**Core principle:** `addValidators(...)` is an **additive** operation; `setValidator(...)` and `replaceValidators(...)` **reset the list**. To truly replace validators, do so intentionally, understand the consequences, and test all constraints that must still be preserved.

This lesson targets Spring Framework 6.2.x / Spring Boot 3.5.x, Java 17+, and the **Spring MVC Servlet stack**. `DataBinder` exists elsewhere as well, but `@InitBinder` application flow, argument resolvers, and exceptions differ in WebFlux. Do not conflate this with AOP method validation.

## 2. Three Layers to Distinguish Up Front

A form request arriving at a controller typically passes through these steps:

```text
HTTP form/query parameters
           |
           v
Spring MVC argument resolver
           |
           v
WebDataBinder created for model attribute
           |
           +-- global Validator (if MVC configured one)
           |
           +-- @InitBinder in ControllerAdvice
           |
           +-- @InitBinder in Controller
           |
           v
bind / convert request fields into DTO
           |
           v
@Valid / @Validated requests validation
           |
           +-- invoke active validators
           |
           v
BindingResult (FieldError/ObjectError)
           |
           +-- BindingResult immediately after DTO -> handler handles it
           |
           +-- absent -> MVC may throw
               MethodArgumentNotValidException
```

This diagram is a conceptual model and does not claim every argument resolver always builds a binder with the exact same target. Recognize three concepts:

1. **Jakarta Bean Validation provider:** reads `jakarta.validation.constraints.*` annotations such as `@NotBlank`, `@Email`, `@Min`, `@Valid`, and groups.
2. **Spring `org.springframework.validation.Validator`:** contract consisting of `supports(Class<?>)` and `validate(Object, Errors)`, suited for custom rules and recording errors into `BindingResult`.
3. **Spring `DataBinder` / `WebDataBinder`:** holds the list of validators to run when a validation trigger fires; the list can be configured globally and extended locally.

Spring's `LocalValidatorFactoryBean` is the key **bridge**: it implements both `jakarta.validation.Validator` and `org.springframework.validation.Validator` (plus validation hints), translating Jakarta `ConstraintViolation` instances into Spring `FieldError`/`ObjectError` entries.

Thus, the "default validator" in **MVC request binding** is usually the `LocalValidatorFactoryBean` Bean Validation adapter, rather than a custom algorithm hardcoded in the controller.

## 3. When Does Spring Have a Default Validator?

When a Bean Validation provider is present and integrated into MVC configuration, Spring MVC by default registers `LocalValidatorFactoryBean` as the global `Validator` for `@Valid`/`@Validated` on controller arguments.

With Spring Boot 3.x, the standard dependency setup is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

- `spring-boot-starter-web` provides Spring MVC Servlet.
- `spring-boot-starter-validation` provides the Jakarta Validation provider, typically Hibernate Validator and related integration.
- Spring Boot auto-configures a `LocalValidatorFactoryBean` when conditions match; a project that manually configures validators may alter this behavior.
- If no matching provider is on the classpath, **never assume** that simply putting `@NotBlank` on a DTO will automatically validate requests.

**Do not confuse:** Spring Boot having a global bean in the application context does not prove every binder is using that bean. Controller `@InitBinder`, `WebMvcConfigurer#getValidator()`, `@ControllerAdvice`, or XML configuration can alter the list attached to a specific binder.

Whenever you change configuration, always verify **actual runtime behavior** with tests: pass invalid data for both constraint annotations and custom rules. Never check only that the application context starts.

## 4. Validator Configuration APIs on `DataBinder`

Spring `DataBinder` provides these key methods:

| API | Effect on List | When to Use |
| --- | --- | --- |
| `setValidator(Validator validator)` | **Clears existing validators**, then sets the given validator (if non-null) | Intentionally want only a single validator in the list |
| `addValidators(Validator... validators)` | **Appends** validators to the current list | Adding local rules while keeping defaults |
| `replaceValidators(Validator... validators)` | **Clears the existing list** and replaces it with the exact given validators | Explicitly controlling the entire set of validators |
| `getValidator()` | Returns the **first** validator in the list, or `null` | Inspecting the primary validator; does not represent all validators |
| `getValidators()` | Returns the list of configured validators | Inspecting members and order |
| `setExcludedValidators(Predicate<Validator>)` | Sets a predicate filtering validators excluded from the **active** set | Special cases needing to suppress a validator; available since Spring 6.1 |
| `getValidatorsToApply()` | Returns the list after applying the exclude predicate | Debugging which validators actually run; available since Spring 6.1 |
| `validate()` / `validate(hints...)` | **Executes** applicable validator(s), recording errors into `BindingResult` | Programmatic validation or MVC execution when triggered |

### 4.1. Easy-to-Remember State Table

Suppose a binder starts with:

```text
[BeanValidationAdapter]
```

And you have `LocalBusinessValidator`:

| Call | Resulting List |
| --- | --- |
| `binder.addValidators(local)` | `[BeanValidationAdapter, LocalBusinessValidator]` |
| `binder.setValidator(local)` | `[LocalBusinessValidator]` |
| `binder.replaceValidators(local)` | `[LocalBusinessValidator]` |
| `binder.replaceValidators(defaultValidator, local)` | `[BeanValidationAdapter, LocalBusinessValidator]` |
| `binder.setValidator(null)` | `[]` |

This assumes the binder actually started with `BeanValidationAdapter` and no other validators. Do not assume Spring automatically attaches the adapter to a `new DataBinder(target)` you construct by hand: with programmatic binders, you usually configure validators directly.

### 4.2. Be Careful with `getValidator()`

`binder.getValidator()` returns only the **first validator**, not a "combined list" and not guaranteed to always be the Bean Validation adapter:

```java
Validator primary = binder.getValidator();
List<Validator> configured = binder.getValidators();
```

This illustrative snippet uses `org.springframework.validation.Validator` and `java.util.List`. With multiple validators, inspect `getValidators()` to see the full list; in Spring 6.1+, also check `getValidatorsToApply()` to observe exclude predicates.

Do not mutate the list returned by `getValidators()` directly; Spring returns an unmodifiable view. Use the `addValidators`/`replaceValidators` APIs properly.

## 5. Safe Default Pattern: `binder.addValidators(...)`

Suppose `SignupForm` has Jakarta constraints and `ReservedUsernameValidator` is a custom Spring `Validator`.

```java
@RestController
@RequestMapping("/signups")
public class SignupController {

    private final ReservedUsernameValidator usernameValidator;

    public SignupController(ReservedUsernameValidator usernameValidator) {
        this.usernameValidator = usernameValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.addValidators(usernameValidator);
    }

    @PostMapping("/form")
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {
        // ...
    }
}
```

This is an illustrative pattern; the full compilable project is in section 10.

Meaning:
- `@InitBinder("signupForm")` selects only binders with object name `signupForm`.
- `binder.addValidators(usernameValidator)` **does not remove** validators already added by global MVC configuration.
- `@Valid` on `@ModelAttribute` triggers Bean Validation and Spring validators in standard argument validation.
- `BindingResult` stands **immediately after** the DTO and collects errors from both sources.
- If you omit `@Valid`/`@Validated` on the argument without calling `binder.validate()` elsewhere, do not assume the custom validator runs automatically just because it was registered.

This is also the pattern Spring Framework recommends when adding a controller-level custom validator while preserving the global Bean Validation adapter.

### 5.1. Why Scope `@InitBinder` by Name?

With:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.addValidators(usernameValidator);
}
```

a controller with multiple DTOs may create a binder for a type other than `SignupForm`. Because the custom validator's `supports()` accepts only `SignupForm`, it is incompatible with other targets. `DataBinder` checks target support upon registration; in mismatch cases it can throw `IllegalStateException` instead of silently skipping the rule.

Solutions:
- Scope with `@InitBinder("signupForm")` when targeting a single model attribute.
- Or check target/targetType before adding if there is a shared configuration reason.
- Make local validators support **only the exact type**, rather than returning `true` for every class just to dodge the error.

Never work around an "unsupported target" validator by calling `setValidator(null)`: that can wipe out the default validator you still need.

## 6. Why `setValidator(...)` Is Dangerous Inside `@InitBinder`

`setValidator` does not mean "set an auxiliary validator" or "enable validation." It **replaces the entire existing list** with the passed validator.

Mistake:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setValidator(usernameValidator);
}
```

Suppose the global `LocalValidatorFactoryBean` originally checked `@NotBlank`, `@Email`, and `@Min`. After the statement above, that validator is removed from this binder's list, leaving only the custom rule. When a user sends `email="bad"` with a non-reserved username, the request may be **accepted** even though `@Email` would fail in a real Bean Validation pass.

Fix:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.addValidators(usernameValidator);
}
```

Use `setValidator(...)` only when you **deliberately want complete replacement**—for example, a special object needing an exclusive validator where you have verified annotation constraints are no longer relied upon on that binding path.

### 6.1. Pitfall of `setValidator(null)`

```java
binder.setValidator(null);
```

This statement can **empty the binder's validator list**, not merely "reset our custom validator." If the goal is disabling a local rule, refactor registration scope, split controllers/DTOs, or use a controlled exclusion policy. Never use this call as a hack to silence test failures without understanding the cause.

### 6.2. Pitfall in `@ControllerAdvice`

If a `@ControllerAdvice` uses:

```java
@ControllerAdvice
public class GlobalBinderAdvice {

    @InitBinder
    void init(WebDataBinder binder) {
        binder.setValidator(someCustomValidator);
    }
}
```

every binder affected by the advice risks having its global validator replaced by the custom rule. Afterwards, a controller calling `binder.addValidators(...)` appends only to the **already altered** list; it cannot recover the lost default simply by "adding again" unless it holds a direct reference to that default validator.

Consequently, global policies require even more careful design and testing than local ones. When only one special form needs a rule, prefer controller-level `@InitBinder("formName")` or a narrowly scoped advice.

## 7. `replaceValidators(...)`: Use Only When the Full Set Is Known

`replaceValidators(Validator... validators)` is useful when you want to **specify the exact validators** that should apply to a binder.

Example intentionally keeping both default and custom:

```java
Validator defaultValidator = /* verified reference */;
Validator localValidator = new ReservedUsernameValidator();

binder.replaceValidators(defaultValidator, localValidator);
```

This is an illustrative fragment; a comment cannot fabricate `defaultValidator`. Do not assume `binder.getValidator()` is always the default adapter if a `@ControllerAdvice` or earlier config step already replaced the list.

When a binder already holds the desired defaults, **`addValidators` is simpler and less risky**. When `replaceValidators` is truly needed:
1. Identify the exact validators that must be preserved.
2. Obtain references from a trusted configuration source.
3. Ensure all of them support the target.
4. Check ordering and whether duplicates exist.
5. Test violations for **each** rule that must remain active after replacement.

### 7.1. Do Not Drop the Prior List Without Knowing Its Origin

```java
List<Validator> before = binder.getValidators();
binder.replaceValidators(localValidator);
```

Here you saved the list only to inspect/log it and failed to include its elements in the replacement: the prior validators are lost. If you genuinely want to keep everything, `addValidators(localValidator)` expresses that intent cleanly.

If you need to replace one specific validator, build a fresh list from verified components and call `replaceValidators(...)`, accounting for ordering, duplicates, and exclusions. Do not write convoluted code to do what `addValidators` already provides.

### 7.2. `setExcludedValidators` and the Applied List

Since Spring Framework 6.1, you have:

```java
binder.setExcludedValidators(
        validator -> validator instanceof LegacyValidator);
```

`LegacyValidator` here is an illustrative type, not a built-in Spring class. The predicate excludes matching validators from the **set actually executed**; it does not remove objects from `getValidators()`. Use `getValidatorsToApply()` to debug the effective list.

**Risk:** an overly broad predicate can accidentally exclude `LocalValidatorFactoryBean` itself, causing Bean Validation constraints to be skipped even though `getValidators()` still shows it configured.

Unless specifically required, you do not need `setExcludedValidators`. This API is intended for well-tested integration or suppression scenarios.

## 8. How Does Spring `Validator` Differ from Jakarta `Validator`?

In a Spring Boot 3+ project, the name `Validator` appears in **two different packages**:

```java
org.springframework.validation.Validator
jakarta.validation.Validator
```

They do not share the same signature.

### 8.1. Spring `Validator`

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- Validates an object and records errors into `org.springframework.validation.Errors`.
- Typically uses `errors.reject(...)` or `errors.rejectValue("field", "code")`.
- Can be registered via `WebDataBinder#addValidators`.
- Easy to customize per controller or form.

### 8.2. Jakarta `Validator`

```java
jakarta.validation.Validator validator = ...;

Set<ConstraintViolation<SignupForm>> violations =
        validator.validate(form);
```

- Processes annotation constraints, groups, and `@Valid` cascades.
- Returns `Set<ConstraintViolation<T>>`; does not write directly to `BindingResult`.
- Cannot pass `jakarta.validation.Validator` directly to `binder.addValidators(...)`; that method expects a Spring `Validator`.

### 8.3. The `LocalValidatorFactoryBean` Bridge

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` implements **both** APIs. When used as a Spring `Validator`, it executes Jakarta Bean Validation and translates violations into corresponding Spring errors.

Diagram:

```text
@Valid @ModelAttribute SignupForm
             |
             v
Spring WebDataBinder.validate()
             |
             +--> LocalValidatorFactoryBean
             |       |
             |       +--> Jakarta provider: @NotBlank, @Email, @Min
             |       |
             |       +--> Spring FieldError / ObjectError
             |
             +--> ReservedUsernameValidator
                     |
                     +--> errors.rejectValue(...)
             |
             v
       BindingResult merges errors
```

**Never create a new `LocalValidatorFactoryBean` per request**: bootstrapping the provider is expensive and has its own lifecycle. Use a Spring-managed bean, or let Spring MVC's global configuration supply it automatically.

## 9. `SmartValidator`, Validation Hints, and Groups

Spring's `SmartValidator` extends Spring `Validator`:

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

`LocalValidatorFactoryBean` implements `SmartValidator` to support hints such as validation groups. When a handler uses `@Validated(Publish.class)`, group metadata is forwarded to hint-aware validators.

Example:

```java
public interface Publish {}

public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank(groups = Publish.class)
    private String approvalCode;
}
```

This is an **illustrative fragment**, different from the DTO in section 10. If a handler uses:

```java
public ResponseEntity<?> publish(
        @Validated(Publish.class)
        @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

then only constraints in the `Publish` group are evaluated per Jakarta Validation rules (`Default` is not automatically included). If you want both, use `@Validated({Default.class, Publish.class})` with `import jakarta.validation.groups.Default`.

**Important nuance:** A custom Spring `Validator` implementing only `validate(Object, Errors)` still runs when validation hints are present; it simply **does not understand groups**. If business logic must depend on groups, implement `SmartValidator` and handle hints explicitly, or write a custom Jakarta `@Constraint` supporting `groups`.

Do not assume `addValidators` magically "converts" every custom rule into a group-aware Jakarta constraint.

## 10. Complete Project: Java 17 + Spring Boot 3.5.6

We build a signup form API with:
- `@NotBlank` on `username` and `email`.
- `@Email` for valid email format.
- `@NotNull` + `@Min(18)` on age.
- Custom rule forbidding usernames `admin`/`root`.
- `@InitBinder("signupForm")` calling **`addValidators`**, not replacing the global validator.
- `BindingResult` returning a sorted list of fields + stable error codes.
- MockMvc tests ensuring both Jakarta and custom rules still run.
- Dedicated `DataBinder` unit/integration tests proving the difference among `addValidators`, `setValidator`, and `replaceValidators`.

We use Java 17, Spring MVC Servlet, and Spring Boot **3.5.6** as a pinned illustrative release, without implying it is the latest Boot release. Every file below is complete within the shown structure; do not copy unrelated fragments into the project.

### 10.1. Structure

```text
binder-validators-demo/
├── pom.xml
├── src/main/java/demo/validation/
│   ├── BinderValidationApplication.java
│   ├── SignupForm.java
│   ├── OtherForm.java
│   ├── ReservedUsernameValidator.java
│   └── SignupController.java
└── src/test/java/demo/validation/
    ├── SignupControllerTest.java
    └── BinderCompositionTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>binder-validators-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Do not manually add a second Bean Validation provider to `pom.xml` when the starter already manages it. Keeping one compatible provider avoids configuration conflicts between `javax.validation` and `jakarta.validation`.

### 10.3. `BinderValidationApplication.java`

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderValidationApplication.class, args);
    }
}
```

### 10.4. `SignupForm.java`

```java
package demo.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank(message = "username.required")
    private String username;

    @NotBlank(message = "email.required")
    @Email(message = "email.invalid")
    private String email;

    @NotNull(message = "age.required")
    @Min(value = 18, message = "age.min")
    private Integer age;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Uses `Integer` + `@NotNull` to distinguish missing age (`null`) from age `0`. `@Min` by itself treats `null` as valid; `@NotNull` ensures a value is present.

### 10.5. `OtherForm.java`

```java
package demo.validation;

public class OtherForm {

    private String username;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }
}
```

This is strictly a **control** form demonstrating the scope of `@InitBinder("signupForm")`. That `OtherForm` skips the rule in this demo does not imply real-world APIs should allow reserved usernames.

### 10.6. `ReservedUsernameValidator.java`

```java
package demo.validation;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class ReservedUsernameValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String username = form.getUsername();

        if (username != null
                && ("admin".equalsIgnoreCase(username)
                    || "root".equalsIgnoreCase(username))) {

            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "This username is reserved");
        }
    }
}
```

- `supports()` restricts the validator to `SignupForm` and subclasses, if any.
- `validate()` checks only the reserved-username list without reimplementing `@NotBlank`/`@Email`/`@Min`.
- `errors.rejectValue(...)` appends a `FieldError` to the same `BindingResult` MVC is processing.
- The validator performs no I/O, does not mutate the target, and holds no request state.

This **separation of responsibilities** makes losing Bean Validation easy to spot: if only the custom validator remains, an invalid email will not be caught by the custom rule.

### 10.7. `SignupController.java`

```java
package demo.validation;

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

import java.util.Map;

@RestController
@RequestMapping("/signups")
public class SignupController {

    private final ReservedUsernameValidator reserved;

    public SignupController(ReservedUsernameValidator reserved) {
        this.reserved = reserved;
    }

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        // ADD, DO NOT REPLACE: preserve existing Bean Validation.
        binder.addValidators(reserved);
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> form(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var entries = errors.getFieldErrors().stream()
                    .map(error -> {
                        String[] codes = error.getCodes();
                        // Pick the last generic code instead of object-prefixed ones.
                        String code = codes != null && codes.length > 0
                                ? codes[codes.length - 1]
                                : "unknown";
                        return error.getField() + ":" + code;
                    })
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "status", "invalid",
                    "errors", entries));
        }

        return ResponseEntity.ok(Map.of(
                "status", "created",
                "username", form.getUsername()));
    }

    @PostMapping(path = "/other",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, String> other(
            @ModelAttribute("otherForm") OtherForm form) {

        return Map.of("username", form.getUsername());
    }
}
```

**Why use the last code from `FieldError.getCodes()`?** `DefaultMessageCodesResolver` generates error codes from most specific to most general—for example, `NotBlank.signupForm.username`, `NotBlank.username`, `NotBlank.java.lang.String`, `NotBlank`. Taking the last element lets the demo return `username:NotBlank` independent of object name. This is a simple response format for the lesson; production apps may use a dedicated error-code mapping table and localization.

**Note on `Map.of`:** The success endpoint uses only `username`, which passed `@NotBlank`, so it is non-null on the valid path. The `OtherForm` endpoint is called in tests with a non-null username; passing `null` into `Map.of` would throw. A production API should handle nulls explicitly or use a response DTO.

### 10.8. `SignupControllerTest.java` — Tests Going Through Spring MVC

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            signup(String username, String email, String age) {

        return post("/signups/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", username)
                .param("email", email)
                .param("age", age);
    }

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.username").value("Lan"));
    }

    @Test
    void jakartaNotBlankIsStillActive() throws Exception {
        mvc.perform(signup("", "lan@example.com", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:NotBlank")));
    }

    @Test
    void jakartaEmailIsStillActive() throws Exception {
        mvc.perform(signup("Lan", "bad-email", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("email:Email")));
    }

    @Test
    void jakartaMinIsStillActive() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:Min")));
    }

    @Test
    void jakartaNotNullIsStillActive() throws Exception {
        mvc.perform(post("/signups/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "Lan")
                        .param("email", "lan@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:NotNull")));
    }

    @Test
    void localReservedRuleIsActive() throws Exception {
        mvc.perform(signup("admin", "lan@example.com", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:username.reserved")));
    }

    @Test
    void jakartaAndLocalErrorsAppearTogether() throws Exception {
        mvc.perform(signup("root", "wrong", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:username.reserved")))
                .andExpect(jsonPath("$.errors", hasItem("email:Email")))
                .andExpect(jsonPath("$.errors", hasItem("age:Min")));
    }

    @Test
    void conversionErrorIsNotBeanValidation() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:typeMismatch")));
    }

    @Test
    void binderScopeDoesNotAffectOtherForm() throws Exception {
        mvc.perform(post("/signups/other")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "root"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("root"));
    }
}
```

There are **9 MVC tests**:
- Positive test with valid inputs.
- Four tests confirming individual Jakarta constraints still run (`@NotBlank`, `@Email`, `@Min`, `@NotNull`).
- Reserved-username test proving the custom rule was appended.
- Combined test proving **both** sets report errors together.
- Type-mismatch test distinguishing binding from validation.
- Separate-form test checking `@InitBinder("signupForm")` scope.

If someone changes `binder.addValidators(reserved)` to `binder.setValidator(reserved)` in the controller, `jakartaNotBlankIsStillActive`, `jakartaEmailIsStillActive`, `jakartaMinIsStillActive`, and `jakartaNotNullIsStillActive` will catch the regression. That is why this suite is far more valuable than testing only `username=admin`.

### 10.9. `BinderCompositionTest.java` — Dedicated Tests for `DataBinder`

This test clearly demonstrates the difference **without sending HTTP requests**. We instantiate `DataBinder` explicitly in the test and supply the default adapter, because plain `new DataBinder(...)` **does not automatically acquire MVC's global validator**.

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.validation.DataBinder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BinderCompositionTest {

    @Autowired
    LocalValidatorFactoryBean beanValidationAdapter;

    @Autowired
    ReservedUsernameValidator localValidator;

    private SignupForm invalidInput() {
        SignupForm form = new SignupForm();
        form.setUsername("admin");
        form.setEmail("bad-email");
        form.setAge(16);
        return form;
    }

    private DataBinder newBinder() {
        return new DataBinder(invalidInput(), "signupForm");
    }

    @Test
    void addValidatorsPreservesDefaultAndCustom() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);
        binder.addValidators(localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertTrue(errors.hasFieldErrors("email"));
        assertTrue(errors.hasFieldErrors("age"));
        assertEquals(2, binder.getValidators().size());
    }

    @Test
    void setValidatorReplacesThePreviouslyConfiguredOne() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);

        // Intentionally WRONG in this control test.
        binder.setValidator(localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertFalse(errors.hasFieldErrors("email"));
        assertFalse(errors.hasFieldErrors("age"));
        assertEquals(1, binder.getValidators().size());
    }

    @Test
    void replaceValidatorsCanExplicitlyPreserveBoth() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);

        // When replacement is truly needed, list both explicitly.
        binder.replaceValidators(beanValidationAdapter, localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertTrue(errors.hasFieldErrors("email"));
        assertTrue(errors.hasFieldErrors("age"));
        assertEquals(2, binder.getValidators().size());
    }
}
```

**Do not misinterpret the control test:** `setValidatorReplacesThePreviouslyConfiguredOne()` **passes** when confirming Bean Validation was lost, because the test's goal is proving `setValidator`'s destructive behavior. Production code must still use `addValidators` or a replacement retaining the full required list.

The test injects `LocalValidatorFactoryBean` supplied by Spring Boot's Validation auto-configuration in this demo setup. In a customized project with multiple validator beans or no default adapter, injection needs `@Qualifier`/`@Primary` and the test should confirm it uses the application's actual Bean Validation adapter.

### 10.10. Running Tests

In `binder-validators-demo` with JDK 17+ and Maven able to download dependencies:

```bash
mvn test
```

Expected: **12 tests** total (9 MockMvc + 3 DataBinder). The code produces no fixed business stdout; Maven/Surefire reports test counts per environment. Tests use assertions on status, field codes, validator counts, and constraint preservation/loss.

To run the application:

```bash
mvn spring-boot:run
```

In this example, there is no need to manually create a `MethodValidationPostProcessor`; the topic is **MVC binder validation**, not AOP method validation.

## 11. Trying with `curl`: Seeing Both Rule Sets Run Together

### 11.1. Valid Form

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Lan' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=20'
```

Expected HTTP **200** and JSON equivalent to:

```json
{"status":"created","username":"Lan"}
```

### 11.2. Failing a Jakarta Rule

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Lan' \
  --data-urlencode 'email=bad-email' \
  --data-urlencode 'age=20'
```

Expected HTTP **400**, body containing error code `email:Email`. If you change `addValidators` to `setValidator` leaving only the custom validator, this exact request can be erroneously accepted.

### 11.3. Failing the Local Rule

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=20'
```

Expected HTTP **400**, body containing `username:username.reserved`. If you accidentally omit `addValidators` while keeping the default provider, this request will not be blocked.

### 11.4. Both Error Sources Together

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=root' \
  --data-urlencode 'email=wrong' \
  --data-urlencode 'age=16'
```

Expected HTTP **400**; the `errors` list contains:

```json
{
  "status": "invalid",
  "errors": [
    "age:Min",
    "email:Email",
    "username:username.reserved"
  ]
}
```

This list is `sorted()` in the controller so example ordering is deterministic. Never rely on validator execution order or `ConstraintViolation` iteration order to enforce business priorities.

## 12. Verifying Actual Validator Configuration

### 12.1. Do Not Look Only at `getValidator()`

Inside `@InitBinder`, for debugging when needed:

```java
@InitBinder("signupForm")
void inspect(WebDataBinder binder) {
    var before = binder.getValidators();
    binder.addValidators(reserved);
    var after = binder.getValidators();

    // Use before/after for controlled debugging in test environments.
}
```

This illustrative fragment **replaces** `configure(...)` in the project rather than being registered alongside it. Its purpose is inspecting the member list. `getValidator()` returns only the primary entry, whereas `getValidators()` returns the configured list.

Never log the entire target object or raw request because they may hold passwords or personal data. For instrumentation, log class names and validator counts, or assert directly in integration tests.

### 12.2. What Happens with Excluded Validators?

A configuration might include:

```java
binder.setExcludedValidators(
        v -> v.getClass().getSimpleName().contains("Legacy"));
```

This is an API illustration, **not a reliable production filter** because it relies on class names. The predicate creates a difference between `getValidators()` and `getValidatorsToApply()`. If the exclusion accidentally matches the Bean Validation adapter, Jakarta constraints are omitted from binder validation even though the configured list looks complete.

When debugging "a validator is in the list yet doesn't run," check **the applied list** and exclusion predicates, not just the configured list.

### 12.3. `supports(Class<?>)` Is Not Optional

`DataBinder` checks whether a validator supports the target type when adding/setting validators. A `ReservedUsernameValidator` built solely for `SignupForm` must not be attached indiscriminately to binders for `PaymentForm`, `AddressForm`, or the entire application context.

If you want shared logic across multiple classes, you can:
- Define a shared supported interface, such as `HasUsername`, and have the validator support real implementations.
- Use a custom Jakarta constraint on the target field, enabling reuse across DTOs.
- Choose the exact object name/target type when registering the validator.

Never change `supports` to `return true` if the validator still casts `(SignupForm) target`: when a different target type arrives, you will hit a `ClassCastException` at runtime.

## 13. Coordinating `@ControllerAdvice` and Local Validators

Spring MVC allows placing `@InitBinder` inside `@ControllerAdvice`. Example:

```java
@ControllerAdvice(assignableTypes = SignupController.class)
public class SignupAdvice {

    private final CommonSignupValidator common;

    public SignupAdvice(CommonSignupValidator common) {
        this.common = common;
    }

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        binder.addValidators(common);
    }
}
```

This is an illustrative snippet requiring `CommonSignupValidator` and Spring imports; **it is not part of the runnable project** in section 10.

If the controller also has its own `@InitBinder`, both the advice and the controller can affect the same binder. If one place calls `setValidator(...)` after another called `addValidators(...)`, the final list may diverge from intent. **Configuration application order matters**, yet in application code prefer additive APIs over relying on fragile ordering.

A sound organization pattern:
- Configure global Bean Validation at the MVC infrastructure layer.
- Scope common validators cleanly in advice.
- Add form-specific validators in the controller.
- Avoid `setValidator`/`replaceValidators` unless intentionally replacing the validator set.
- Test the combined behavior at the actual handler rather than only unit-testing individual validators in isolation.

## 14. Customizing the Global Validator Is Not Adding a Local Validator

When you need to replace the validator for **all of Spring MVC**, you can configure `WebMvcConfigurer#getValidator()`:

```java
@Configuration
public class MvcValidationConfig implements WebMvcConfigurer {

    @Override
    public Validator getValidator() {
        return customGlobalValidator;
    }
}
```

This is an **architectural illustration** requiring `customGlobalValidator` and imports; it is not in the section 10 runnable project.

This tells MVC to **use the supplied validator as the global validator**, not merely append a rule. Returning a Spring `Validator` that checks only usernames without running Bean Validation can replace MVC's default integration everywhere. That decision has a far wider blast radius than `@InitBinder("signupForm")`.

If your goal is simply to:
- Forbid a username in one form → `@InitBinder` + `addValidators`.
- Share a rule across multiple DTOs → custom Jakarta `@Constraint` or an appropriate Spring `Validator`.
- Customize global Bean Validation messages/constraint factory/interpolator → customize `LocalValidatorFactoryBean`/Boot validation configuration while preserving the Jakarta provider role.
- Choose an entirely different global `Validator` → do so only when deliberately changing validation architecture with full regression tests.

Never "temporarily wire" a global `getValidator()` just to silence validation errors on one endpoint.

## 15. When You Truly Must Replace: Two Safe Strategies

### 15.1. Replace with an Adapter That Calls Both Jakarta and Custom Rules

You can build a **composite Spring `Validator`** executing both rule sources. When doing so, you must:
- Manage execution order and duplicates yourself.
- Preserve validation groups/hints if needed; implement `SmartValidator` where appropriate.
- Translate Jakarta provider violations into Spring `Errors` via an adapter.
- Handle target types and exceptions consistently.

Write a composite only when your architecture explicitly requires a shared abstraction; in ordinary cases, `binder.addValidators(...)` already provides composition.

### 15.2. Use `replaceValidators` with the Full List

Programmatic illustration:

```java
DataBinder binder = new DataBinder(form, "signupForm");

binder.replaceValidators(beanValidationAdapter, customValidator);
binder.validate();

BindingResult result = binder.getBindingResult();
```

This assumes `form`, `beanValidationAdapter`, and `customValidator` are already instantiated and support the target. Unlike `new DataBinder(...); replaceValidators(customValidator)`, this approach **deliberately retains** the Jakarta adapter.

Do not use `replaceValidators` to "auto-fix" a misconfigured binder without knowing its initial state. Any replacement on a production HTTP path needs integration tests covering both baseline constraints and business rules.

## 16. `@RequestBody`, `@ModelAttribute`, and Method Validation

### 16.1. Form / `@ModelAttribute` Is the Clear Case

```java
@PostMapping("/form")
public ResponseEntity<?> register(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

In this context, `WebDataBinder` participates in binding and validation. `@InitBinder("signupForm")` appends the local Spring `Validator`. This is the primary context of the runnable project in section 10.

### 16.2. JSON / `@RequestBody` Also Validates, Through a Different Binding Channel

```java
@PostMapping("/json")
public ResponseEntity<?> register(
        @Valid @RequestBody SignupForm form) {
    // ...
}
```

JSON objects are normally deserialized by `HttpMessageConverter`/Jackson. Spring MVC may still create a binder for post-deserialization validation, and `@InitBinder` can affect the validator list depending on object name and infrastructure. However, **property-binding rules** like `setAllowedFields(...)` cannot block Jackson from populating fields during JSON decoding.

Do not claim `@InitBinder` "never runs" for JSON; likewise, do not rely on setter-binding allowlists to protect deserialization. If a JSON property must be forbidden, use a dedicated input DTO and enforce authorization in the service layer.

### 16.3. Direct Method Constraints Have Their Own Branch

As of Spring Framework 6.1, when a controller handler has `@Min`, `@NotBlank`, etc. **directly** on method parameters or return values, MVC provides built-in method validation. It can supersede standalone argument validation and throw `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`.

Example:

```java
@PostMapping("/mixed")
public String mixed(
        @RequestParam("n") @Min(1) int n,
        @Valid @ModelAttribute("signupForm") SignupForm form) {
    // ...
}
```

This is an illustrative fragment, absent from the runnable project in section 10. **The validator scope of an MVC argument binder and method validation** do not always match; if a handler switches to method validation due to direct constraints, re-test where custom Spring `Validator` instances are invoked. In particular, a local `org.springframework.validation.Validator` does not automatically become a Jakarta `ConstraintValidator` for executable validation.

Because this lesson focuses on avoiding losing the default binder validator, the main runnable example **places no direct method constraints** on handlers. That keeps tests cleanly exercising the binder/`BindingResult` branch.

### 16.4. Service `@Validated` via AOP Is Also Different

`@Service @Validated` plus `MethodValidationPostProcessor` checks method parameters/returns when invocations pass through a Spring proxy. It does not inherit the validator list of a specific `WebDataBinder` used in a web request. Never expect a rule added via controller `@InitBinder` to automatically guard every service call.

When the same rule is needed across HTTP forms and services, implement shared constraint/domain validation at the appropriate layer.

## 17. Validation and Conversion/Binding Errors Are Independent Sources

A form submitting `age=abc` when `age` is an `Integer` fails **before** Bean Validation. Spring records `typeMismatch` in `BindingResult` even when the bean validator is intact.

Conversely:
- `age=16` converts to an integer but violates `@Min(18)`.
- Omitting `age` leaves `null` and violates `@NotNull`.
- `username=admin` is valid in type and non-blank, yet violates the custom rule.
- `email=bad-email` binds as a `String` yet violates `@Email`.
- `username=""` violates `@NotBlank`, and is not necessarily flagged by the custom reserved-name rule.

Seeing a handler return 400 does not tell you whether all validators ran. Inspect **error codes** or the `FieldError` source to verify which branch executed.

Never write a catch-all exception handler returning 400 for every `ValidationException`: some provider/configuration errors are server-side bugs, not bad client requests.

## 18. Pre-Merge Checklist for Binder Changes

1. **Clarify intent:** are you **adding** or **replacing** a `Validator`?
2. If adding, use **`addValidators`**, not `setValidator` just because the name looks familiar.
3. Verify Spring Boot has `spring-boot-starter-validation` and the global Jakarta adapter.
4. Check the exact package: `org.springframework.validation.Validator` vs. `jakarta.validation.Validator`.
5. For custom Spring `Validator`s, ensure `supports(Class<?>)` matches the DTO.
6. Scope `@InitBinder("objectName")` to the form needing the rule; avoid affecting other DTOs.
7. When using `@ControllerAdvice`, check whether binder callbacks overlap.
8. Avoid casually overriding `WebMvcConfigurer#getValidator()`, as it alters global configuration.
9. If using `replaceValidators`, pass **all** validators to preserve, not just the new one.
10. Inspect `getValidators()` and `getValidatorsToApply()` (Spring 6.1+) when exclusion policies exist.
11. Test invalid inputs for **every important Jakarta rule**: `@NotBlank`, `@Email`, `@NotNull`, `@Min`, etc.
12. Test invalid inputs for the **custom rule**; do not test only defaults.
13. Test **multiple errors simultaneously** and confirm all appear in `BindingResult`.
14. Test missing, blank, null, wrong-type, and valid-type out-of-range inputs.
15. Confirm `@Valid`/`@Validated` is on the matching argument; registering a validator does not trigger validation by itself.
16. If using groups, distinguish Spring `SmartValidator` from plain `Validator` and test hint handling.
17. If a controller switches to MVC built-in method validation due to direct constraints, re-test custom-rule execution.
18. Test via `MockMvc` rather than calling controller Java methods directly, proving the MVC binder factory ran.
19. Never allow arbitrary binding of admin/role/security-sensitive properties; validation is not authorization.
20. Log only error metadata, never raw sensitive values.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `binder.setValidator(local)` to "add" a custom rule | Drops existing validators | `binder.addValidators(local)` |
| `binder.replaceValidators(local)` without passing default | Drops Jakarta Bean Validation adapter | Replace only with the full list to preserve |
| `binder.setValidator(null)` to "reset rules" | Empties all validators on the binder | Redesign scope or use controlled exclusion config |
| Using `getValidator()` to claim only one validator exists | Misses additional validators | Inspect `getValidators()` |
| Overlooking `setExcludedValidators` | Validator is in list yet doesn't execute | Inspect `getValidatorsToApply()` |
| Adding a `SignupForm`-only validator to all binders | May throw `IllegalStateException` or cause cast errors | Use `@InitBinder("signupForm")` / check type |
| Creating a `jakarta.validation.Validator` bean and passing it to `addValidators` | Wrong Spring API interface | Use Spring `Validator` or `LocalValidatorFactoryBean` adapter |
| `@Valid` present with no provider | Constraints may not execute as expected | Configure starter/provider and test invalid input |
| Forgetting `@Valid` on the request argument | Validators registered but never triggered | Add the appropriate annotation/trigger |
| Testing only `username=admin` | Custom rule works while missing `@Email` goes unnoticed | Test both default and custom rules |
| Using `@Validated(Publish.class)` assuming `Default` still runs | May skip the `Default` group | Specify groups accurately |
| Plain Spring `Validator` ignores hints yet expected to vary by group | Runs unintended rules | Implement `SmartValidator` or group-aware Jakarta constraint |
| Confusing `typeMismatch` with `@Min` | Misdiagnosing error source | Distinguish binding errors from validation errors |
| Attaching rules in global `@ControllerAdvice` without targeting | Affects unrelated forms | Narrow advice or specify object name |
| Putting class-level `@Validated` on controller just to run a validator | Can switch to AOP validation | Use `@Valid` or parameter-level groups with built-in MVC validation |
| Treating Bean Validation as authorization | Requests can still alter privileges on poorly designed DTOs | Dedicated DTOs + service/security policies |

## 20. Practice Exercises

1. Change `binder.addValidators(reserved)` to `binder.setValidator(reserved)` in the project. Run the tests and identify which Jakarta tests lose protection.
2. Use `binder.replaceValidators(defaultValidator, reserved)` in a programmatic test; contrast its result with `replaceValidators(reserved)`.
3. Submit `username=root`, `email=wrong`, and `age=16` together. Why do all three error codes appear?
4. Remove `@Valid` from `@ModelAttribute SignupForm` while keeping `@InitBinder`. Predict which invalid-input tests change behavior.
5. Add `@Size(min=4)` on `username` and write a test proving the new Jakarta constraint still works alongside the added custom rule.
6. Add a second validator checking an internal email domain. Use `addValidators` and test both custom rules coexisting with the Jakarta adapter.
7. Remove `"signupForm"` from `@InitBinder` and test `/signups/other`. Explain the roles of `supports()` and object name.
8. Create a `Publish` group and `@Validated({Default.class, Publish.class})` on the argument; check whether the custom Spring `Validator` runs and inspects hints.
9. Try `setExcludedValidators(...)` with a predicate excluding one validator and compare `getValidators()` with `getValidatorsToApply()`.
10. Create a record DTO using constructor binding; compare validation with a mutable form and setter binding, taking care not to confuse binding policy with the validator list.
11. Replace error reporting in `SignupController` with an error DTO containing `field`, `code`, and `message`, without returning raw rejected values.
12. Extend tests to guarantee a change in `@ControllerAdvice` does not drop the default validator of another controller.

**Summary:** When configuring binders in Spring MVC, distinguish **add** (appending rules), **set/replace** (replacing the whole list), and **exclude** (filtering at execution time). To add a custom validator without losing default Jakarta Bean Validation, typically use `@InitBinder("formName")` + `binder.addValidators(custom)`, keep `@Valid`/`@Validated` in place, and write regression tests for both error sources.

## 21. Official Documentation

- [Spring Framework 6.2 — Spring MVC Validator configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — `DataBinder` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — Java Bean Validation and `LocalValidatorFactoryBean`](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MVC argument/method validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — `BindingResult` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5 — MockMvc testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)