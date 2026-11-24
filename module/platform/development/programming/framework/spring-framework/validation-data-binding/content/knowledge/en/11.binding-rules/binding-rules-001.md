# `setAllowedFields`: restricting fields allowed for data binding in Spring

## 1. Why do we need an allowlist of bindable fields?

When Spring binds input data into a Java object using `DataBinder` or `WebDataBinder`, property names from the data source can determine which setter or property gets updated. If the input comes from an HTTP request, the client can easily craft extra parameters that the UI does not display. Binding every property can accidentally allow modification of sensitive fields such as `admin`, `approved`, `ownerId`, `balance`, or `role` — this is the **mass assignment / over-posting** risk.

`DataBinder#setAllowedFields(String... allowedFields)` defines an **allowlist**: the property names permitted to participate in *property binding*. Any field outside the allowlist is excluded from the assignment step, even if the DTO has a valid setter.

```text
HTTP form / PropertyValues
  displayName = "An"
  email       = "an@example.com"
  admin       = "true"
              |
              v
DataBinder with allowedFields = ["displayName", "email"]
              |
              +-- displayName -> assigned
              +-- email       -> assigned
              +-- admin       -> suppressed
              |
              v
BindingResult.getSuppressedFields() -> ["admin"]
```

Key point: `setAllowedFields` is a policy for **property binding**, not an end-user authorization mechanism; it does not replace validation and does not prevent the application from calling setters outside the binder.

## 2. Syntax and when to apply it

Basic API:

```java
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(target, "profile");
binder.setAllowedFields("displayName", "email");
```

In this example, `target` is an already-created object with the corresponding properties. The binder will apply this list when processing `bind(PropertyValues)`.

**Configure the allowlist before binding.** If you set it after `bind`, setters that were already invoked are not automatically rolled back. In Spring MVC, this configuration is typically placed inside `@InitBinder` so the framework applies it before binding the model attribute.

Do not call `setAllowedFields()` with an empty list thinking it will "disable binding": allowlist configuration semantics should not be inferred this way. To block property binding completely for a binder, Spring provides dedicated options such as `setDeclarativeBinding(true)` in supported versions, or you can use a DTO/handler designed strictly for constructor binding. Always check your Framework version and write tests for your security goals.

## 3. Complete Java 17+ example

Create `AllowedFieldsDemo.java` in a project with the appropriate Spring Framework modules:

```java
import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class AllowedFieldsDemo {
    public static class ProfileForm {
        private String displayName;
        private String email;
        private boolean admin;

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }
    }

    public static void main(String[] args) {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "email");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("displayName", "An");
        input.add("email", "an@example.com");
        input.add("admin", "true");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println(form.getDisplayName());
        System.out.println(form.getEmail());
        System.out.println(form.isAdmin());
        System.out.println(result.hasErrors());
        System.out.println(Arrays.toString(result.getSuppressedFields()));
    }
}
```

Output:

```text
An
an@example.com
false
false
[admin]
```

Line-by-line explanation:

1. `displayName` and `email` match the allowlist, so they are assigned.
2. `admin`, despite having a setter, is **not assigned**; the default value of `boolean` remains `false`.
3. A suppressed field is not recorded as a `FieldError` by default, so `result.hasErrors()` returns `false` in this example.
4. `getSuppressedFields()` returns the rejected input field names; this is a very useful signal for **detecting requests that attempt to update out-of-contract fields**.

With Java 17+ and a classpath containing `spring-context` or the relevant Spring modules along with compatible dependencies, you can compile and run it using the following Linux/macOS commands if `SPRING_CP` already contains all required JARs:

```bash
javac -cp "$SPRING_CP" AllowedFieldsDemo.java
java -cp ".:$SPRING_CP" AllowedFieldsDemo
```

On Windows, the classpath separator is `;`. A plain `javac AllowedFieldsDemo.java` command will not work without the Spring JARs. The example has a standalone `main` method independent of an HTTP server.

## 4. `setAllowedFields` and Spring MVC `@InitBinder`

In Spring MVC, `WebDataBinder` is created by the framework for a model attribute and can be configured via `@InitBinder`:

```java
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @InitBinder("profileForm")
    void restrictProfileFields(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping("/profile")
    String update(@ModelAttribute("profileForm") AllowedFieldsDemo.ProfileForm form,
                  BindingResult result) {
        if (result.getSuppressedFields().length != 0) {
            return "Unsupported fields";
        }
        if (result.hasErrors()) {
            return "Invalid profile";
        }
        return "Updated: " + form.getDisplayName();
    }
}
```

This is a controller snippet inside a configured Spring MVC application, not a complete Java file with `main`. With a request like `displayName=An&email=an@example.com`, the properties are bound according to the allowlist. If the client appends `admin=true`, that field is suppressed, and the example controller proactively detects and rejects it.

**Note on HTTP status:** the strings `"Unsupported fields"` and `"Invalid profile"` in the example do not automatically turn into HTTP 4xx responses. A production application should return `ResponseEntity.badRequest()` or use an exception handler to explicitly define the HTTP status and response schema.

`@InitBinder("profileForm")` uses the model attribute name to scope the configuration. The name must match `@ModelAttribute("profileForm")`; if you use `@InitBinder` without scoping by name, the policy can apply to many different objects and drop required fields.

## 5. Exact field names, patterns, and nested paths

The allowlist is applied based on the **property path names** seen by the binder:

```java
binder.setAllowedFields("name", "address.city", "address.postalCode");
```

When the input contains `name` and `address.city`, they can be assigned if the JavaBean structure is valid. If the client sends `address.country` or `address.internalCode`, they fall outside the allowlist.

Spring supports pattern matching in allowed field names according to `DataBinder`/`PatternMatchUtils` semantics, such as `address.*` or `items[*].name` in appropriate cases. Be careful: `address.*` is a broad policy that can allow **new properties** added to `Address` in the future. Do not use broad wildcards merely to reduce maintenance effort when the data is client-controlled.

| Allowlist | Input property | Policy outcome |
| --- | --- | --- |
| `name` | `name` | Allowed |
| `address.city` | `address.city` | Allowed |
| `address.city` | `address.country` | Suppressed |
| `address.*` | `address.city` | May match by pattern |
| `address.*` | `address.internalFlag` | May also match; scope-expansion risk |

Do not confuse dot-separated property paths with JSON paths or database column names. With `@ModelAttribute`, Spring can use the `address.city` path directly; with `@RequestBody` JSON, deserialization is handled by a message converter (usually Jackson), so **DataBinder's allowlist does not automatically block JSON fields**.

## 6. What is `getSuppressedFields()`?

After `bind`, `BindingResult.getSuppressedFields()` reports the property names that were excluded by the binding field filtering mechanism. For example:

```java
String[] suppressed = binder.getBindingResult().getSuppressedFields();
if (suppressed.length > 0) {
    throw new IllegalArgumentException(
            "Unexpected fields: " + String.join(", ", suppressed));
}
```

This is a snippet inside a method that already has a `binder` variable. This fail-fast policy treats a request attempting to write out-of-contract fields as an input error rather than silently ignoring it.

However, you should not log raw field names or sensitive rejected values to public logs. If malicious input is detected, return a safe message to the client and record an audit log according to the appropriate policy. Do not use `getSuppressedFields()` as a substitute for checking whether the caller is authorized to update the record.

### `suppressed field` vs. `field error`

| Scenario | Status | Observable API |
| --- | --- | --- |
| Client sends `admin=true` outside the allowlist | Field is suppressed | `getSuppressedFields()` |
| Client sends `age=abc` when `age` is allowed and target is `int` | Type conversion error | `hasFieldErrors("age")`, `getFieldError("age")` |
| Client sends valid `email` type, but validator finds business rule violation | Validation error | `hasFieldErrors("email")` |
| Client omits `name`, but binder requires `name` | Missing required field | `BindingResult` per required-fields policy |

A suppressed field does not mean the entire operation automatically fails. To reject it, you must check and respond explicitly.

## 7. `setAllowedFields`, `setDisallowedFields`, and `setRequiredFields`

These three API groups answer three different questions:

- `setAllowedFields`: which fields **is the client allowed to send for binding?**
- `setDisallowedFields`: which fields **are forbidden from binding?**
- `setRequiredFields`: which fields **must be present in the input property values?**

```java
binder.setAllowedFields("name", "email");
binder.setRequiredFields("name");
```

Allowing `name` and `email` to bind does not mean they are mandatory; `setRequiredFields("name")` is what adds the required constraint at the binding layer. Distinguish this from Jakarta Bean Validation's `@NotBlank`/`@NotNull`, because validation inspects **object values after binding** and has different semantics from missing input.

You can combine allowed and disallowed fields, but prefer an **explicit allowlist**. A denylist risks missing newly added properties, such as `role` or `creditLimit`, if a developer adds a field later and forgets to update the blocklist. When combining them, understand the filtering order and write tests for special paths.

## 8. Limitation: constructor binding is not the same as property binding

In Spring Framework versions supporting constructor binding, an object can be instantiated from constructor arguments before properties are bound. `setAllowedFields` controls **property binding**; you should not assume it acts as an allowlist for constructor parameters. A record with an `admin` constructor parameter can still receive the corresponding input through the constructor binding path if the model and resolver permit it.

The safe design approach is a **request DTO containing only public fields**; avoid using a domain entity with administrative attributes as the request target. On Spring versions supporting `setDeclarativeBinding(true)`, you can declare a strategy strictly for constructor binding with explicitly controlled property binding, though you must still determine which constructor parameters are safe.

DTO example:

```java
public record UpdateProfileRequest(String displayName, String email) {}
```

This type of DTO has no `admin` constructor parameter for the client to request setting under the API contract. When mapping to the entity, the service must still verify permissions and selectively copy the fields to be updated.

## 9. Testing the allowlist

For unit tests on `DataBinder`, at a minimum verify:

1. Valid fields only: bound to the right values, no suppressed fields.
2. Out-of-allowlist fields present: those properties remain unchanged, and `getSuppressedFields()` contains the exact names.
3. Disallowed nested path names: suppressed without creating or expanding the object graph unexpectedly.
4. Wildcards if used: test both valid names and similarly named sensitive fields.
5. Allowed fields with invalid types: produce conversion/binding errors according to policy.
6. Missing required fields: produce the expected response per required/validation rules.
7. Both Spring MVC and plain Java unit tests: verify `@InitBinder` actually applies to the chosen model name.

JUnit 5 snippet (using the `ProfileForm` class from the main example):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

class AllowedFieldsTest {
    @Test
    void disallowsAdminProperty() {
        var form = new AllowedFieldsDemo.ProfileForm();
        var binder = new DataBinder(form);
        binder.setAllowedFields("displayName", "email");
        binder.bind(new MutablePropertyValues(java.util.Map.of(
                "displayName", "An", "admin", "true")));

        assertEquals("An", form.getDisplayName());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields());
    }
}
```

This test snippet requires Spring and JUnit dependencies on the classpath; it is not a standalone `main` program. In real projects, test the actual sensitive fields of your system, not just the illustrative `admin` field.

## 10. Common mistakes

- **Only hiding fields on the HTML form:** provides zero server-side security, since clients can submit parameters manually.
- **Using an entity directly as the request model:** easily exposes sensitive properties to accidental writes; separate out a request DTO.
- **Relying only on `setDisallowedFields("admin")`:** can miss sensitive fields added later; an allowlist is safer.
- **Setting allowed fields after binding:** too late to stop setters that have already been called.
- **Ignoring suppressed fields:** the application silently drops unauthorized modification attempts without detecting them.
- **Using overly broad patterns:** wildcards may permit unintended nested properties.
- **Assuming allowed fields equals validation:** it only controls bindability, not whether an email is valid or an age meets requirements.
- **Assuming it protects `@RequestBody` JSON in all cases:** JSON binding is typically handled by `HttpMessageConverter`, not `DataBinder` property binding.
- **Assuming it blocks all constructor parameters:** design your constructors and DTOs separately.
- **Skipping authorization checks in the service layer:** an allowlist does not replace checking who is permitted to edit a record and which fields they may change.

## 11. Safe adoption checklist

1. Create small input DTOs containing only the fields the client needs to edit.
2. For property binding, configure `setAllowedFields` before any bind call.
3. In Spring MVC, use `@InitBinder` scoped to the exact model name.
4. Do not allow broad wildcards without testing all related nested properties.
5. Inspect both `BindingResult.hasErrors()` **and** `getSuppressedFields()`.
6. Reject suppressed fields if the API contract forbids clients from sending them.
7. Continue running conversion, validation, and modification-permission checks at the business layer.
8. Add tests whenever the DTO changes, especially when adding new properties or expanding constructors.

**Key takeaway:** `setAllowedFields` helps prevent over-posting by allowing Spring to bind only the explicitly listed property paths. Combining minimal DTOs, suppressed-field checks, validation, and authorization creates a reliable input data boundary.
