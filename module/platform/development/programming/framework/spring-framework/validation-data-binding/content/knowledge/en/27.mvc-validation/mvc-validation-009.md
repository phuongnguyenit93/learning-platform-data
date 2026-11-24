# Combining Errors or BindingResult with Validation Types in Spring MVC

## 1. Goal: one place collecting errors from multiple phases

In Spring MVC, a request can be invalid for many reasons: a string fails conversion to a number, a value violates a Jakarta Validation annotation, a custom Spring validation rule fails, or a business policy is only known after reading the data. When a controller receives a **command/form object** via `@ModelAttribute`, those errors can usually all be recorded into the same `Errors`/`BindingResult`.

Both interfaces live in `org.springframework.validation`:

- **`Errors`**: interface for reading and recording errors on an object; provides `hasErrors()`, `getFieldErrors()`, `getGlobalErrors()`, `rejectValue(...)`, and `reject(...)`.
- **`BindingResult`**: **extends `Errors`** and adds access to data binding results, such as `getTarget()`, `getRawFieldValue(...)`, `getSuppressedFields()`, and `getModel()`.

If you only need to check for errors or add errors, declaring `Errors` is usually enough. If you need to distinguish type conversion errors, inspect suppressed fields, or prepare a model for an HTML form, `BindingResult` is more useful.

**Rule #1:** the `Errors` or `BindingResult` parameter in a controller signature must be placed **immediately after the bound/validated parameter** it describes. Never place another controller parameter in between.

```java
@PostMapping("/signups")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "signup-form";
    }
    return "redirect:/success";
}
```

This is a **fragment** of an MVC controller using views, not a standalone Java program. The sections below explain the mechanism, error categories, a runnable REST form example, and key differences with JSON/Bean Validation methods.

## 2. At which stages do errors appear?

An `application/x-www-form-urlencoded` request processed through `@ModelAttribute` typically follows this flow:

```text
HTTP POST /signups
   Content-Type: application/x-www-form-urlencoded
                   |
                   v
          Create/retrieve command object
                   |
                   v
          Data binding from parameters
                   |
                   +--> conversion error
                   |       e.g. age=abc -> Integer
                   |       record FieldError into BindingResult
                   |
                   v
          @Valid / @Validated
                   |
                   +--> Jakarta Bean Validation
                   |       e.g. @NotBlank, @Min, @Email
                   |
                   +--> Spring Validator registered via @InitBinder
                   |       e.g. reject reserved username
                   |
                   v
          Controller receives object and BindingResult
                   |
                   +--> errors.hasErrors() ?
                   |       |
                   |       +--> yes: render form/HTTP 400
                   |
                   +--> additional business checks (if data is valid enough)
                   |       |
                   |       +--> rejectValue / reject
                   |
                   v
          Execute business logic if no errors remain
```

Not every request goes through the exact same pipeline. For `@RequestBody` JSON, an HTTP message converter constructs the object first; if the body has syntax errors or is non-deserializable, Spring can throw `HttpMessageNotReadableException` **before any object/`BindingResult` is available to the controller**. For controller methods with **direct parameter constraints**, Spring MVC 6.1+ adds a dedicated method validation branch.

### Four important validation groups

| Group | How errors are created | Typical location | Inspectable via `Errors` / `BindingResult`? |
| --- | --- | --- | --- |
| Data binding / type conversion | Cannot convert `"abc"` to `Integer` | `@ModelAttribute` with request parameters | **Yes**, as a `FieldError`, typically `isBindingFailure() == true` |
| Jakarta Bean Validation | `@NotBlank`, `@Min`, `@Email`, custom `@Constraint` | Bound object with `@Valid`/`@Validated` | **Yes**, Spring adapts constraint violations into `FieldError`/`ObjectError` |
| Custom Spring `Validator` | `supports(...)` + `validate(Object, Errors)` | `@InitBinder`, MVC config, or direct invocation | **Yes**, validator calls `rejectValue` and `reject` |
| Business rules | Database checks, duplicate username, cross-field policy | Controller/service at an appropriate point | **Can be**, by explicitly calling `result.rejectValue(...)` / `reject(...)` before returning a response |

Distinction: `BindingResult` is **where errors are recorded**, not an automatic validation engine. It does not evaluate `@Min` by itself without a `Validator` and a validation trigger.

## 3. Comparing Errors and BindingResult

Both live in the Spring Validation package, **not** Jakarta Validation's `jakarta.validation.Validator` or `ConstraintViolation`.

| Method | `Errors` | `BindingResult` | When to use |
| --- | --- | --- | --- |
| `hasErrors()`, `getErrorCount()` | Yes | Yes | Decide whether to halt processing on errors |
| `hasFieldErrors("age")` | Yes | Yes | Check errors on a single property |
| `getFieldErrors()`, `getGlobalErrors()` | Yes | Yes | Separate field errors from object errors |
| `rejectValue("field", "code", "message")` | Yes | Yes | Add a property error |
| `reject("code", "message")` | Yes | Yes | Add an object-level / cross-field error |
| `getFieldValue("age")` | Yes | Yes | Display the user's entered value, including rejected values |
| `getTarget()` | No | Yes | Access the target object of binding |
| `getRawFieldValue("age")` | No | Yes | Query the raw property value on the target |
| `getSuppressedFields()` | No | Yes | Detect properties skipped because binding was disallowed |
| `getModel()` | No | Yes | Build a map containing target and BindingResult for a view |

`BindingResult extends Errors`, so a `BindingResult` argument works anywhere an API expects `Errors`. When you need `getSuppressedFields()`, you cannot call it directly on a variable typed as `Errors` without an actual `BindingResult`.

### FieldError vs. ObjectError

- `FieldError` ties an error to a **property path**, such as `username`, `age`, or `address.zipCode`; provides `getField()`, `getRejectedValue()`, and `isBindingFailure()`.
- `ObjectError` represents a **whole-object or cross-field** error that cannot be assigned to a single field—for example, a locked voucher or an invalid combination of fields.
- `FieldError` is a subtype of `ObjectError`, yet UI rendering typically distinguishes "next to the input box" from "banner message at the top of the form".
- A **single field can have multiple errors**. Never assume each property has at most one `FieldError`.
- A type conversion error can trigger additional validation errors depending on how the binder/validator handles a property left `null`; in tests, check error types and field names rather than relying on exact error counts when exact counts are not required.

## 4. Right and wrong ways to declare controller parameters

### Right: BindingResult immediately after the model

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        BindingResult bindingResult,
        Model model) {
    if (bindingResult.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

### Right: use Errors if only the general API is needed

```java
@PostMapping("/profiles")
public String save(
        @Validated @ModelAttribute("profile") ProfileForm profile,
        Errors errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

### Wrong: another parameter inserted in between

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        Model model,
        BindingResult result) {
    // BindingResult does not immediately follow profile.
    return "profile-form";
}
```

The three code blocks above are **separate illustrative signatures**; do not paste them all at once into one controller. With wrong placement, Spring MVC cannot associate `BindingResult` with `profile` per convention; argument resolution may throw an exception instead of entering the method.

### Two model objects need two separate results

```java
@PostMapping("/combined")
public String save(
        @Valid @ModelAttribute("person") PersonForm person,
        BindingResult personResult,
        @Valid @ModelAttribute("address") AddressForm address,
        BindingResult addressResult) {
    if (personResult.hasErrors() || addressResult.hasErrors()) {
        return "combined-form";
    }
    return "redirect:/done";
}
```

This is a fragment illustrating parameter ordering; form classes are defined separately in the application. Never share a single `BindingResult` across multiple command objects.

**Note:** when there is no `Errors`/`BindingResult` immediately after a validated parameter, Spring may throw a default exception (typically `MethodArgumentNotValidException`), and the controller will not receive the error list to render a view. Proper parameter placement handles errors **locally inside the handler**; it does not mean every possible request error is swallowed.

## 5. Combining error sources: runnable example with Spring Boot 3 and Java 17

The example uses a form endpoint `POST /signups`. We intentionally combine four sources:

1. **Binding error:** `age=abc` cannot convert to `Integer`.
2. **Jakarta Validation:** `@NotBlank`, `@NotNull`, `@Min(18)`, and `@Email`.
3. **Spring `Validator`:** forbids username `admin` and rejects invitation code `BLOCK`.
4. **Business check:** simulates username `taken` already existing; runs only once basic binding/validation errors are absent.

To observe results clearly in tests, the endpoint responds with JSON containing **failing field names** (without echoing raw rejected values), the list of **fields failing type conversion**, and **global error** messages. A pure HTML MVC application can keep the exact same `BindingResult` logic while returning a template instead of JSON.

### 5.1. File layout

```text
mvc-errors-combination/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ValidationTypesApplication.java
    │   ├── SignupForm.java
    │   ├── SignupPolicyValidator.java
    │   └── SignupController.java
    └── test/java/demo/
        └── SignupControllerTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-errors-combination</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

`spring-boot-starter-validation` provides the Jakarta Validation provider for `@Valid` on the controller argument. If you only add annotations to code without a configured provider/validator, do not expect Bean Validation to run like in the example.

### 5.3. ValidationTypesApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationTypesApplication.class, args);
    }
}
```

### 5.4. SignupForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {
    @NotBlank
    private String username;

    @NotNull
    @Min(18)
    private Integer age;

    @NotBlank
    @Email
    private String email;

    private String invitation;

    public String getUsername() {
        return username;
    }
    public void setUsername(String username) {
        this.username = username;
    }

    public Integer getAge() {
        return age;
    }
    public void setAge(Integer age) {
        this.age = age;
    }

    public String getEmail() {
        return email;
    }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getInvitation() {
        return invitation;
    }
    public void setInvitation(String invitation) {
        this.invitation = invitation;
    }
}
```

This model has a Java-provided no-args constructor and public setters suitable for property binding. Using `Integer` distinguishes an omitted value (`null`, rejected by `@NotNull`) from a number below 18 (rejected by `@Min`). `@Min` is not a number parser: `age=abc` is a type conversion error before the age evaluation phase.

### 5.5. SignupPolicyValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "Username is reserved");
        }

        if ("BLOCK".equalsIgnoreCase(form.getInvitation())) {
            errors.reject(
                    "invitation.blocked",
                    "Invitation is blocked");
        }
    }
}
```

`supports(...)` declares which types the validator handles. `validate(...)` records errors on the MVC-provided `Errors` object:

- `rejectValue(...)` creates a **field** error on `username`.
- `reject(...)` creates a **global/object** error on the command object.

Here the validator **does not access a database directly** and does not throw an exception on invalid data; it records errors for the controller to aggregate. Code names `username.reserved` and `invitation.blocked` are **application-defined error codes**, not Jakarta constraint annotations.

### 5.6. SignupController.java

```java
package demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestController
public class SignupController {

    @InitBinder("signup")
    public void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "username", "age", "email", "invitation");
        binder.addValidators(new SignupPolicyValidator());
    }

    @PostMapping(
        path = "/signups",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> signup(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult result) {

        // Binding, type conversion, and @Valid have already occurred before this line.
        // Check business rules only if the form is valid enough to evaluate.
        if (!result.hasErrors()
                && "taken".equalsIgnoreCase(form.getUsername())) {
            result.rejectValue(
                    "username",
                    "username.taken",
                    "Username is already used");
        }

        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(Map.of(
                    "ok", false,
                    "code", "DISALLOWED_FIELDS"
            ));
        }

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> bindingFields = result.getFieldErrors().stream()
                    .filter(FieldError::isBindingFailure)
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> globalMessages = result.getGlobalErrors().stream()
                    .map(ObjectError::getDefaultMessage)
                    .map(m -> Objects.toString(m, "Invalid object"))
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "ok", false,
                    "code", "INVALID_SIGNUP",
                    "fields", fields,
                    "bindingFields", bindingFields,
                    "globalMessages", globalMessages
            ));
        }

        return ResponseEntity.ok(Map.of(
                "ok", true,
                "username", form.getUsername()
        ));
    }
}
```

**Points to observe:**

- `@Valid` triggers Jakarta Bean Validation on `SignupForm`. Spring MVC combines it with `SignupPolicyValidator` added via `@InitBinder("signup")`; the custom validator does not replace the global Bean Validator because `addValidators(...)` is used rather than `setValidator(...)`.
- `BindingResult` sits **immediately after** `@ModelAttribute`, allowing the controller to handle errors inside the method instead of letting MVC throw a default exception.
- `getFieldErrors()` holds field errors from multiple sources. `isBindingFailure()` distinguishes type conversion errors when needed. `getGlobalErrors()` holds errors created via `reject(...)`.
- `result.rejectValue(...)` in the controller demonstrates adding a **business rule**. Because it only runs when `!result.hasErrors()`, we avoid querying/evaluating business rules while input data is still malformed or incomplete.
- `getSuppressedFields()` detects when a client tries to send properties outside the allowlist; suppression itself does not automatically become a `FieldError`. The example proactively returns `DISALLOWED_FIELDS` instead of silently accepting it.
- When returning `fields`, the example reveals only failing field names without returning rejected values; this is appropriate for teaching and reduces personal-data exposure risk.

**Note on Spring validators:** local `@InitBinder` targets the binder named `signup`; if you rename `@ModelAttribute("signup")` without updating `@InitBinder`, the custom validator may not attach to the binder as expected. Choose `addValidators` when you want to **combine** with the global Jakarta Validator; use `setValidator`/`replaceValidators` only when you genuinely want to replace the validator list.

### 5.7. SignupControllerTest.java with MockMvc

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "20")
                        .param("email", "lan@example.org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true))
                .andExpect(jsonPath("$.username").value("lan"));
    }

    @Test
    void jakartaConstraintsAreCollected() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "")
                        .param("age", "16")
                        .param("email", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_SIGNUP"))
                .andExpect(jsonPath("$.fields",
                        hasItems("username", "age", "email")))
                .andExpect(jsonPath("$.bindingFields.length()").value(0));
    }

    @Test
    void typeMismatchIsTrackedSeparately() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "abc")
                        .param("email", "lan@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_SIGNUP"))
                .andExpect(jsonPath("$.bindingFields", hasItems("age")));
    }

    @Test
    void springValidatorCreatesFieldError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "admin")
                        .param("age", "23")
                        .param("email", "admin@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItems("username")));
    }

    @Test
    void springValidatorCreatesGlobalError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "23")
                        .param("email", "lan@example.org")
                        .param("invitation", "BLOCK"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.globalMessages",
                        hasItems("Invitation is blocked")));
    }

    @Test
    void controllerCanAddBusinessFieldError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "taken")
                        .param("age", "23")
                        .param("email", "taken@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItems("username")));
    }

    @Test
    void massAssignmentAttemptIsRejected() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "23")
                        .param("email", "lan@example.org")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"));
    }
}
```

Run with Java 17+ and Maven in the project directory:

```bash
mvn -q test
```

**Expected test result:** all seven tests pass (exit code 0) when Maven has resolved dependencies. Do not enforce specific Maven stdout because Spring/Test/JUnit logs vary by library version and log settings. Assertions check **HTTP status, error code, failing field names, binding failure category, and global errors** instead of depending on default Bean Validation message strings.

Run the application:

```bash
mvn spring-boot:run
```

And submit the form using curl:

```bash
curl -i -X POST http://localhost:8080/signups \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=lan' \
  --data-urlencode 'age=20' \
  --data-urlencode 'email=lan@example.org'

curl -i -X POST http://localhost:8080/signups \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'age=abc' \
  --data-urlencode 'email=bad'
```

The first request returns **200 OK** with `ok=true`; the second returns **400 Bad Request** with code `INVALID_SIGNUP` and `fields`/`bindingFields` lists. Because both a type conversion failure and an annotation constraint can be recorded on a field, the example prints **distinct names** rather than relying on the per-field error count.

## 6. How to inspect each error kind inside BindingResult

### 6.1. Type conversion errors

When `age` receives `"abc"` while the property is `Integer`, the error usually carries a root code like `typeMismatch`. Spring creates a `FieldError` with `isBindingFailure() == true`. We can check:

```java
boolean invalidAgeType = result.getFieldErrors("age")
        .stream()
        .anyMatch(FieldError::isBindingFailure);
```

This is a fragment inside a controller that already has `BindingResult result`. Do not rely on message text `"Failed to convert..."` because messages can be interpolated via `MessageSource` and locale.

### 6.2. Jakarta Validation violations

With `@NotBlank` on `username`, Spring's adapter turns the violation into a `FieldError` that typically has `isBindingFailure() == false`. The constraint code is fed into the message codes mechanism so it can be interpolated/localized. Example:

```java
boolean invalidUsername = result.hasFieldErrors("username");
boolean hasGlobal = result.hasGlobalErrors();
int totalErrors = result.getErrorCount();
```

These checks only inspect **error state**; they do not by themselves identify which source produced the error. If you need reliable business-level categorization, use consistently defined error codes rather than checking only the `isBindingFailure()` flag.

### 6.3. Global / cross-field errors

When a rule does not belong to any single field, use:

```java
result.reject(
    "registration.invalidCombination",
    "The selected values cannot be used together"
);
```

This creates an `ObjectError`, retrieved via `getGlobalErrors()`. Do not force cross-field errors onto an arbitrary property just to return the form: the UI can display them at the top of the form or beneath the related field group.

### 6.4. How do rejectValue and reject differ?

```java
result.rejectValue(
    "username",
    "username.taken",
    "Username is already used"
);

result.reject(
    "invitation.blocked",
    "Invitation is blocked"
);
```

- `rejectValue` takes a **field path**, **error code**, and **default message**, with overloads accepting interpolation arguments.
- `reject` takes an **object-level** code and message.
- Codes can be resolved by `MessageCodesResolver` and `MessageSource`; hence `ObjectError#getCodes()` typically holds multiple keys from specific to general, aiding i18n design.
- If the controller uses nested paths, the field name must match the relative path in that context; avoid calling `rejectValue` for a property absent from the DTO.

### 6.5. When should business checks run?

A defensive pattern:

```java
if (result.hasErrors()) {
    return "signup-form";
}

// Data has passed type conversion and basic validation.
if (userService.existsByUsername(form.getUsername())) {
    result.rejectValue(
        "username", "username.taken", "Username already exists");
}

if (result.hasErrors()) {
    return "signup-form";
}

// Persist data only at this point.
userService.register(form);
return "redirect:/success";
```

This is an **illustrative fragment**, not standalone runnable code: `userService` and `signup-form` are components required in the application. This avoids querying the DB while fields still have invalid types or missing values. Note that checking username existence before inserting is **not enough** to prevent race conditions; data requiring uniqueness still needs a database constraint or suitable consistency mechanism.

## 7. @Valid, @Validated, and multiple validation groups

`jakarta.validation.Valid` triggers Bean Validation and cascades into child objects marked `@Valid`. It is **not** a non-null constraint: to require a field to exist, add `@NotNull` or `@NotBlank` appropriately.

`org.springframework.validation.annotation.Validated` supports choosing validation groups. Example:

```java
public interface UpdateChecks {}

public class ProfileForm {
    @NotBlank(groups = UpdateChecks.class)
    private String displayName;

    // getter/setter...
}

@PostMapping("/profile")
String update(
        @Validated(UpdateChecks.class)
        @ModelAttribute("profile") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profile";
}
```

This is a fragment; classes/forms/controllers must be placed in valid locations with full imports. Placing a constraint only in `UpdateChecks` does **not automatically include it in the Default group**. If `@Valid` without groups is used, custom-group constraints may not run. Carefully verify active groups, group conversion, and whether a custom Spring `Validator` uses validation hints.

**Two notes:**

1. `BindingResult` does not choose groups; it receives errors after the validation engine has run with the active groups.
2. A plain Spring `Validator` only has `validate(Object, Errors)`; it does not know about Jakarta groups unless you implement or configure the corresponding validation-hint mechanism.

## 8. @ModelAttribute vs. @RequestBody and @RequestPart

### 8.1. @ModelAttribute: suited for forms and binding errors

With `application/x-www-form-urlencoded`, `@ModelAttribute` fits binding multiple request parameters into a JavaBean. Field type conversion errors (e.g., numbers) and Bean Validation errors can appear together in the `BindingResult` immediately after the command object.

When the controller renders HTML views, a common pattern is:

```java
@PostMapping("/settings")
public String save(
        @Valid @ModelAttribute("settings") SettingsForm settings,
        BindingResult result) {

    if (result.hasErrors()) {
        return "settings-form";
    }

    return "redirect:/settings";
}
```

This is a fragment of a template-using controller, not a handler in the runnable REST project above. Spring MVC can use errors in the model to render messages next to fields and retain rejected request values, depending on the template engine.

### 8.2. @RequestBody JSON: Errors can receive DTO violations, cannot rescue parse errors

Spring MVC supports `Errors` or `BindingResult` **immediately after a `@Valid @RequestBody` argument**:

```java
@PostMapping("/api/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody AccountRequest request,
        Errors errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_ACCOUNT"));
    }

    return ResponseEntity.ok().build();
}
```

This is a JSON API fragment with `AccountRequest` defined separately, not included in the Maven demo project above.

**Crucial distinction:**

- Valid JSON where Jackson builds `AccountRequest` yet `@NotBlank`/`@Min` fail: Spring can pass DTO errors into `Errors` and let the controller handle them itself.
- Malformed JSON, such as `{"age":,}`, or values unconvertible to Java types: the HTTP message converter usually throws `HttpMessageNotReadableException` **before the controller runs**. There is no object to attach to the `errors` variable.
- A `Content-Type` header unsupported by the endpoint can trigger `HttpMediaTypeNotSupportedException` (415), not a field error in `BindingResult`.
- Without an adjacent `Errors`/`BindingResult` and with standalone DTO validation, errors normally go to `MethodArgumentNotValidException`, defaulting to 400.

Do not use `@RequestBody` assuming an entire HTML form-urlencoded payload is processed like JSON. Spring MVC has a dedicated pipeline for `@ModelAttribute`/`@RequestParam`.

### 8.3. @RequestPart multipart

With multipart requests, a part can be turned into an object by a converter and then checked by Bean Validation; Spring MVC also supports `Errors`/`BindingResult` right after a `@Valid @RequestPart` argument where applicable. However, reading parts, missing parts, multipart parsing, and wrong content-types can still throw exceptions before any binding result exists. Test the exact media types, part names, and handler signatures.

## 9. Method validation in Spring MVC 6.1+: when BindingResult is not enough

Since Spring Framework 6.1, MVC has **built-in method validation** when direct constraints like `@Min`/`@NotBlank` are placed directly on method parameters (or return values). This mechanism can encompass nested `@Valid` and raise `HandlerMethodValidationException`. It differs from individual DTO validation.

Example:

```java
@PostMapping("/search")
public String search(
        @RequestParam @Min(1) int page,
        @Valid @ModelAttribute("filters") FilterForm filters,
        BindingResult filtersResult) {

    if (filtersResult.hasErrors()) {
        return "search-form";
    }
    return "search-results";
}
```

This is a fragment; `FilterForm` and the views must be defined separately. If `page=0`, the error belongs to **the `page` parameter**, not the `filters` object, so `filtersResult` **cannot represent all method errors on its own**.

According to Spring MVC documentation:

1. Individual object validation uses `MethodArgumentNotValidException` when errors are not received through an adjacent `Errors` parameter.
2. Built-in method validation can throw `HandlerMethodValidationException` when errors belong to method parameters lacking an immediately following `Errors` parameter to handle them.
3. MVC can **still invoke the controller** if **all** method validation errors belong to parameters that have an `Errors`/`BindingResult` immediately after them.
4. If **any** error belongs to another parameter without an adjacent `Errors`, Spring throws `HandlerMethodValidationException` instead of simply ignoring that error.
5. `@Valid` **is not a direct constraint**; on its own it does not require MVC method validation, whereas placing `@NotNull` directly on a parameter can change the branch.
6. A controller marked `@Validated` at the **class level** may use Spring AOP proxy validation; if you want Spring 6.1+ built-in method validation, Spring docs recommend removing class-level `@Validated` from controllers.

Do not try to force `HandlerMethodValidationException` into a single DTO's `BindingResult`. It holds `ParameterValidationResult` entries grouped per parameter; handle it via `ResponseEntityExceptionHandler` or an appropriate `@ControllerAdvice`.

### Decision table by controller signature

| Signature / scenario | Common handling behavior |
| --- | --- |
| `@Valid @ModelAttribute Form form, BindingResult br` | Controller handles binding/validation errors via `br` |
| `@Valid @RequestBody Dto dto, Errors errors`; JSON readable | Controller handles validation errors via `errors` |
| `@Valid @RequestBody Dto dto`; JSON readable yet DTO invalid | Typically throws `MethodArgumentNotValidException` |
| `@RequestBody` JSON unreadable | `HttpMessageNotReadableException`, even if an `Errors` parameter follows |
| Controller has direct `@Min` on `@RequestParam` | Can trigger MVC method validation and `HandlerMethodValidationException` |
| Method validation errors only on arguments with adjacent `Errors` | MVC can invoke the controller to handle them |
| Method validation error on an argument without adjacent `Errors` | Throws `HandlerMethodValidationException` |
| Class-level `@Validated` on controller | Can route to AOP method validation; check configuration |

## 10. BindingResult, view model, and error messages

### 10.1. Returning HTML forms

Spring integrates `BindingResult` with model attributes so view engines can display errors. For an object named `signup`, the standard model error key typically has the form:

```text
org.springframework.validation.BindingResult.signup
```

The object + `BindingResult` pair gives the view access to both entered values and field errors. In a controller returning a template name, Spring MVC usually manages the relevant model entries automatically. If you manually build a model map from `BindingResult#getModel()`, preserve the exact object name and binding result key. Avoid accidentally overwriting the model attribute after binding, as the view could lose error details.

JSP/Spring form tags example (illustrative fragment):

```jsp
<form:form modelAttribute="signup" method="post">
    <form:input path="username"/>
    <form:errors path="username"/>

    <form:input path="age"/>
    <form:errors path="age"/>

    <form:errors path="*" />
    <button type="submit">Submit</button>
</form:form>
```

Taglib declarations and matching view resolution are required in the application. Thymeleaf templates can use `th:field`, `#fields.hasErrors(...)`, and `th:errors` for the same purpose. This covers *presenting errors*; validation logic still resides in binders and validators.

### 10.2. Message codes and i18n

Spring's `MessageCodesResolver` usually builds multiple codes from most specific to most general. For example, `rejectValue("age", "typeMismatch")` can correspond to detailed message keys by object/field/type before falling back. Exact keys depend on the message resolver and object name, so avoid hardcoding a single code in tests unless you control the resolver.

You can provide `messages.properties` and `messages_vi.properties` so messages interpolate by locale. For example:

```properties
username.reserved=Username này không được sử dụng
username.taken=Tên đăng nhập đã tồn tại
invitation.blocked=Mã mời này đã bị khóa
```

If an API response needs stable error codes, separate **machine-readable codes** from **localized human messages** rather than forcing clients to parse translated text.

### 10.3. Do not expose sensitive rejected values

`FieldError#getRejectedValue()` can contain passwords, tokens, emails, or identifiers. Dumping the entire `BindingResult` into logs or responses is risky. The runnable example only outputs **field names** and type-conversion failure indicators, never raw values.

## 11. Common mistakes

### 11.1. Placing BindingResult in the wrong position

**Wrong:** `(@Valid Form form, Model model, BindingResult br)`. **Right:** `(@Valid Form form, BindingResult br, Model model)`. With multiple forms, each object must have its own result immediately after it.

### 11.2. Missing @Valid or @Validated

Declaring `@NotBlank` on a DTO alone is not enough for MVC to automatically run DTO validation across all method signatures. Add `@Valid`/`@Validated` at the proper binding site and ensure a Jakarta Validation provider is registered.

### 11.3. Confusing conversion errors with constraint errors

`age=abc` typically produces `typeMismatch`, not `@Min(18)`. Some cases also add `@NotNull` because the field failed conversion and remained `null`. Do not assert a fixed error count if the application logic only needs to detect "age is invalid".

### 11.4. Using setValidator instead of addValidators unintentionally

`setValidator(...)` sets a single validator on the binder; an unintended configuration can overwrite the global Jakarta Validator provided by MVC. Use `addValidators(...)` when combining validators, and test both Jakarta constraints and custom Spring rules.

### 11.5. supports() returning false

Spring `Validator#supports(Class<?>)` must accept the corresponding model class. If declared for the wrong type, Spring should not apply the validator to out-of-scope targets; when attaching via `@InitBinder`, verify the target class and binder name.

### 11.6. Checking only getFieldErrors and ignoring getGlobalErrors

Calling `errors.reject(...)` creates an object-level error that does not appear as a property-specific error. When building API error summaries or rendering forms, handle both groups.

### 11.7. Running business logic despite form conversion errors

If age failed conversion to a number, querying a DB or computing prices based on age can fail or cause unwanted side effects. Check `hasErrors()` before executing business rules that rely on parsed/validated data.

### 11.8. Assuming BindingResult catches malformed JSON

If `@RequestBody` JSON fails inside the converter, the controller never receives an object; an adjacent `BindingResult` does not turn parse errors into `FieldError`s. Use exception handling such as `ResponseEntityExceptionHandler`/`@ControllerAdvice` for `HttpMessageNotReadableException`.

### 11.9. Relying on one object's BindingResult to handle all method parameters

A direct `@Min` on `@RequestParam` can trigger method validation, separate from individual DTO validation. Consult Spring MVC 6.1+ documentation and handle `HandlerMethodValidationException` for parameters lacking an adjacent `Errors`.

### 11.10. Relying on an allowlist without checking suppressed fields

`setAllowedFields(...)` blocks binding outside the list, yet does not necessarily create a validation error in the `hasErrors()` sense. When a security contract requires rejecting malicious requests, inspect `getSuppressedFields()` and actively reject or log appropriately.

## 12. Implementation checklist

- [ ] Pick the right pipeline: `@ModelAttribute` for form parameters, `@RequestBody` for JSON, `@RequestPart` for multipart.
- [ ] Always place `Errors`/`BindingResult` immediately after the parameter it describes.
- [ ] Decide when `@Valid` or `@Validated(group)` should be used.
- [ ] Ensure a Jakarta Validation provider is present when running constraint annotations.
- [ ] Use `@InitBinder` + `addValidators(...)` when combining a custom Spring `Validator` with the global validator.
- [ ] Execute business validation after basic validity checks pass.
- [ ] Distinguish field errors, global errors, binding failures, and suppressed fields.
- [ ] Keep response schemas/API error codes consistent; never expose sensitive rejected values.
- [ ] Handle converter exceptions and MVC method validation outside local `BindingResult` scope.
- [ ] For HTML views, ensure the right model attribute and binding result are returned.
- [ ] Write MockMvc tests for happy path, constraints, type mismatch, custom field errors, global errors, business checks, and mass assignment.
- [ ] Verify the Spring version: built-in controller method validation starts in Spring Framework 6.1; do not treat it as identical to every AOP method validation setup.

## 13. Conclusion

`Errors` is the interface for **receiving and reporting errors**; `BindingResult` is the variant tied to **data binding** that provides extra metadata. When placed immediately after a `@ModelAttribute` or an eligible `@Valid @RequestBody`, they let the controller aggregate and respond to errors itself rather than relying entirely on default exceptions.

Within the same `BindingResult`, you can combine **type conversion errors**, **Jakarta Bean Validation violations**, **Spring `Validator` errors**, and **additional business rules**. However, **unreadable JSON, wrong media types, errors on other method parameters, and infrastructure failures** do not automatically become `FieldError`s on the form object. Respecting each boundary and testing each error category is the way to build consistent, understandable, and maintainable MVC validation.

## References

- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ModelAttribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — Java Bean Validation and Spring Validator](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
