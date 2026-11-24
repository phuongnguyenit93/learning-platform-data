# getSuppressedFields and tracking excluded fields in Spring DataBinder

## 1. Why track fields blocked during binding?

Suppose an endpoint lets users edit their profile with two updatable properties: `displayName` and `email`. The Java object also happens to have `role` and `internalNote`, attributes that only the system should manage. A request arrives:

```text
displayName=Lan
email=lan@example.org
role=ADMIN
internalNote=overwrite
```

If property binding runs against an object with setters for all four fields without input restrictions, a client can try modifying data not shown in the form. Spring `DataBinder` lets you configure an **allowlist** and/or **denylist** to exclude fields outside the binding policy. Excluded field names are recorded in `BindingResult` and can be read via:

```java
String[] suppressed =
    binder.getBindingResult().getSuppressedFields();
```

This returns the **list of field names rejected during binding**, not the list of rejected values and not validation errors. It is useful for input inspection, detecting mass-assignment attempts, and testing field-binding policies.

This lesson aims to clarify exactly when a field is suppressed, how to read `getSuppressedFields()`, how to decide whether to reject the whole request, and the limits of this mechanism.

## 2. Participating APIs

| API | Role |
| --- | --- |
| `DataBinder.setAllowedFields(String... fields)` | Registers names/patterns **permitted** for property binding. |
| `DataBinder.setDisallowedFields(String... fields)` | Registers names/patterns **forbidden** from property binding. |
| `DataBinder.bind(PropertyValues)` | Binds name/value pairs onto the target, checking allowed/disallowed fields. |
| `DataBinder.getBindingResult()` | Returns the `BindingResult` holding errors and binding metadata. |
| `BindingResult.getSuppressedFields()` | Returns a `String[]` of **field names** blocked from binding. |
| `BindingResult.recordSuppressedField(String field)` | Records an excluded field, normally invoked by the binder when encountering a disallowed field value. |
| `BindingResult.hasErrors()` | Checks binding/validation errors; does not check suppressed fields. |
| `DataBinder.setDeclarativeBinding(true)` | Since Spring 6.1, restricts property binding declaratively alongside constructor binding. |

These interfaces and classes live under `org.springframework.validation.*` and `org.springframework.beans.*`. `BindingResult` extends `Errors`, yet `getSuppressedFields()` is **binding-specific metadata** rather than a `FieldError`.

### Two outcomes that must be checked independently

```java
BindingResult result = binder.getBindingResult();

boolean hasBindingOrValidationErrors = result.hasErrors();
boolean hasSuppressedFields = result.getSuppressedFields().length > 0;
```

Possible combinations:

- `hasErrors() == false` yet `hasSuppressedFields == true`: permitted inputs bound cleanly while the request included extra blocked fields.
- `hasErrors() == true` and `hasSuppressedFields == false`: e.g., `age=abc` could not convert to `int` without violating allowed fields.
- Both `true` or both `false`.

**Never use `hasErrors()` in place of checking `getSuppressedFields()`.** A request carrying extra blocked fields may produce zero `FieldError` or `ObjectError` entries.

## 3. How Spring filters out fields

For **property binding**, visualize the flow as:

```text
PropertyValues from request / form / map
              |
              v
      DataBinder.bind(...)
              |
              v
   Check allowed / disallowed
        |               |
        | allowed       | disallowed
        v               v
 Check required    Exclude from data to bind
 / conversion          |
        |               v
        |       BindingResult.recordSuppressedField(name)
        v
 Assign property
        |
        v
BindingResult: errors + suppressed field names
```

`DataBinder` checks each property name before applying values to the target. If disallowed:

1. The corresponding property value is removed from the set to be bound.
2. The field name is recorded in `BindingResult` via `recordSuppressedField(...)`.
3. That setter/property is not updated with the excluded value.
4. Spring does not automatically turn the request into a validation error solely because a field was suppressed.

Spring processes binding from `MutablePropertyValues` and uses internal helper `checkAllowedFields(...)`. In Spring MVC, `WebDataBinder` inherits this behavior from `DataBinder`.

**Exact scope:** this `setAllowedFields`/`setDisallowedFields` mechanism applies to **property binding via `bind(PropertyValues)`**. It does not directly constrain **constructor binding** parameters via `construct(ValueResolver)`, because constructor binding fetches only values needed for declared constructor parameters. With constructor binding, design DTOs/constructors to accept only values users are allowed to provide.

## 4. Allowlist: binding only declared fields

Example:

```java
DataBinder binder = new DataBinder(profile, "profile");
binder.setAllowedFields("displayName", "email");
binder.bind(propertyValues);
```

Spring permits property binding only to `displayName` and `email`. If the input includes `role` or `internalNote`, both are suppressed. This fits input forms with a well-defined scope.

**By default**, when `allowedFields` is not configured, Spring does not restrict property binding with an allowlist; therefore, proactively configure it on models containing sensitive data or use a dedicated DTO with only permitted fields.

### Patterns in setAllowedFields

Spring supports exact field names and simple wildcards, for example:

```java
binder.setAllowedFields(
    "displayName",
    "email",
    "address.street",
    "address.city",
    "phones[*]"
);
```

This illustrates a model with matching properties. For lists, arrays, and maps, verify which patterns actually match the paths received by the binder, such as `phones[0]` or `map[key]`. The Javadoc describes wildcards of the form `xxx*`, `*xxx`, `*xxx*`, and `xxx*yyy`; do not assume Spring supports full regex or Ant path patterns.

For nested objects, be cautious with overly broad patterns:

```java
binder.setAllowedFields("address.*");
```

This pattern may accept more child properties than expected. If `address` later gains a sensitive setter, an overly broad allowlist can accidentally expose that field to binding. Prefer explicit field names or separate input DTOs.

### Case sensitivity

In Spring Framework 6.1, **allowed field pattern matching is case-sensitive**. For instance, `"email"` does not automatically allow casing variants. Java property names must also match how Spring resolves them, including nested/indexed paths.

## 5. Denylist: blocking only specified fields

Example:

```java
DataBinder binder = new DataBinder(profile, "profile");
binder.setDisallowedFields("role", "internalNote");
binder.bind(propertyValues);
```

`role` and `internalNote` are excluded from property binding while other fields can still be processed. This demonstrates the suppressed-fields mechanism, yet it **easily misses** new sensitive fields added to the object later.

Per the Spring 6.1 Javadoc:

- **Disallowed field pattern matching is case-insensitive**; patterns are canonicalized and lowercased in the default implementation.
- **Allowed field pattern matching is case-sensitive**.
- **Denylist takes precedence**: a name matching a disallowed pattern is blocked even if it also matches an allowed pattern.

Example illustrating precedence:

```java
binder.setAllowedFields("displayName", "role");
binder.setDisallowedFields("role");
```

With input `role=ADMIN`, `role` is still suppressed. There is no "allowlist written later overrides denylist" rule. Keep filtering rules consistent and avoid mixing two complex lists unless genuinely needed.

**Safe guidance:** for client form data, prefer a **specific allowlist** or an input DTO containing only permitted fields. Denylists easily omit new fields. Beyond binding controls, the system still needs service-layer authorization to enforce who may modify which resources.

## 6. Runnable Java 17 example: two suppressed fields

The following program uses **Spring Framework 6.1.14**, without a Spring Boot web server. We deliberately define a form with setters for sensitive attributes to observe `DataBinder` blocking values outside the allowlist.

Structure:

```text
suppressed-fields-demo/
├── pom.xml
└── src/main/java/demo/SuppressedFieldsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>suppressed-fields-demo</artifactId>
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

File `src/main/java/demo/SuppressedFieldsDemo.java`:

```java
package demo;

import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class SuppressedFieldsDemo {

    public static final class ProfileForm {
        private String displayName;
        private String email;
        private String role = "USER";
        private String internalNote = "server-only";

        public String getDisplayName() {
            return displayName;
        }
        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public String getEmail() {
            return email;
        }
        public void setEmail(String email) {
            this.email = email;
        }

        public String getRole() {
            return role;
        }
        public void setRole(String role) {
            this.role = role;
        }

        public String getInternalNote() {
            return internalNote;
        }
        public void setInternalNote(String internalNote) {
            this.internalNote = internalNote;
        }
    }

    private static String suppressed(BindingResult result) {
        String[] fields = result.getSuppressedFields().clone();
        Arrays.sort(fields); // Deterministic ordering for output.
        return Arrays.toString(fields);
    }

    public static void main(String[] args) {
        ProfileForm first = new ProfileForm();
        DataBinder allowBinder = new DataBinder(first, "profile");
        allowBinder.setAllowedFields("displayName", "email");

        MutablePropertyValues incoming = new MutablePropertyValues();
        incoming.add("displayName", "Lan");
        incoming.add("email", "lan@example.org");
        incoming.add("role", "ADMIN");
        incoming.add("internalNote", "overwrite");

        allowBinder.bind(incoming);
        BindingResult firstResult = allowBinder.getBindingResult();

        System.out.println("ALLOWLIST");
        System.out.println("displayName=" + first.getDisplayName());
        System.out.println("email=" + first.getEmail());
        System.out.println("role=" + first.getRole());
        System.out.println("internalNote=" + first.getInternalNote());
        System.out.println("suppressed=" + suppressed(firstResult));
        System.out.println("hasErrors=" + firstResult.hasErrors());

        // A field in the allowlist is still blocked if the denylist forbids it.
        ProfileForm second = new ProfileForm();
        DataBinder bothBinder = new DataBinder(second, "profile");
        bothBinder.setAllowedFields("displayName", "role");
        bothBinder.setDisallowedFields("role");

        MutablePropertyValues secondInput = new MutablePropertyValues();
        secondInput.add("displayName", "Mai");
        secondInput.add("role", "ADMIN");

        bothBinder.bind(secondInput);

        System.out.println("ALLOW_AND_DENY");
        System.out.println("displayName=" + second.getDisplayName());
        System.out.println("role=" + second.getRole());
        System.out.println("suppressed="
                + suppressed(bothBinder.getBindingResult()));
    }
}
```

Inside `suppressed-fields-demo`, run with JDK 17+ and Maven configured:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SuppressedFieldsDemo
```

Lines printed by the program (excluding any Maven/Spring logs):

```text
ALLOWLIST
displayName=Lan
email=lan@example.org
role=USER
internalNote=server-only
suppressed=[internalNote, role]
hasErrors=false
ALLOW_AND_DENY
displayName=Mai
role=USER
suppressed=[role]
```

**Analysis:**

1. Four name/value pairs are sent to the first binder. `displayName` and `email` match the allowlist, so their setters are invoked.
2. `role` and `internalNote` are outside the allowlist, so their data is stripped before writing to the target.
3. The blocked properties keep their server-side initial values: `role=USER` and `internalNote=server-only`.
4. `getSuppressedFields()` provides the two **field names**, not `"ADMIN"` or `"overwrite"`. The program sorts a copy of the array for stable output; business logic should never depend on suppression order.
5. `firstResult.hasErrors()` is `false` because valid fields bound cleanly, and suppression alone does not register a `FieldError`. This is the core takeaway of the lesson.
6. In the second binder, `role` appears in **both** the allowlist and denylist. Denylist wins, so `role` stays `USER` and `getSuppressedFields()` contains `role`.

The example runs no validator; it tests **property binding rules**. If business validation is needed, register a Spring `Validator` or Jakarta Validation adapter and invoke validation or let Spring MVC trigger it.

## 7. How to monitor excluded fields after binding

`BindingResult.getSuppressedFields()` returns a `String[]`. From the API, the simplest check is:

```java
BindingResult result = binder.getBindingResult();
String[] suppressed = result.getSuppressedFields();

if (suppressed.length > 0) {
    // Record signal of input outside the binding policy.
}
```

This illustrates checking after the binder has processed the request. Two common handling approaches exist:

### A. Log and continue processing valid data

With legacy UIs that may submit deprecated fields, a system may need monitoring during a transition period. You can log **field names** and allow valid fields to proceed if the API contract permits. Keep in mind that an unsupported field name can also be a client compatibility bug rather than an attack.

Example:

```java
String[] fields = result.getSuppressedFields();

if (fields.length > 0) {
    logger.warn("Rejected bind field names: {}", Arrays.toString(fields));
}
```

This snippet requires an `SLF4J` logger and `import java.util.Arrays`. In production, use structured logs with route/correlation IDs for investigation, and control log volume.

### B. Reject the entire request when blocked fields appear

For APIs requiring strict input contracts, policy may return **HTTP 400 Bad Request** whenever a request has suppressed fields. Check in the controller before persisting to the database or calling services with side effects.

```java
if (result.getSuppressedFields().length > 0) {
    throw new IllegalArgumentException(
        "Request contains fields that are not bindable"
    );
}
```

The snippet above is plain Java; in Spring MVC, map the exception to an appropriate HTTP response or use `ResponseStatusException`. This code **does not** cause `DataBinder` to throw automatically; the application makes that decision explicitly.

### What should be logged?

- **Log:** excluded field names, endpoint/form name, sanitized request identifier, field count, API version.
- **Avoid logging by default:** raw field values, full request bodies, cookies, tokens, passwords, personal data, or unfiltered content.
- **Be careful:** client-supplied field names are still untrusted input; cap length, strip control characters to prevent log injection, and avoid unbounded log growth.
- **Do not jump to conclusions:** a suppressed field may come from an old client, frontend bug, automation, or probing. Correlate other evidence before declaring an attack.

You can emit suppression counts to internal metrics, yet avoid exposing internal sensitive field names in end-user responses by default.

## 8. Spring MVC: tracking via @InitBinder and BindingResult

In web applications using `@ModelAttribute`, Spring MVC creates a `WebDataBinder` for binding. Configure the allowlist via `@InitBinder`, then inspect suppressed fields from the `BindingResult` parameter.

**Integration example**, assuming `ProfileForm` and a Spring MVC application exist:

```java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.server.ResponseStatusException;

@Controller
class ProfileController {

    @InitBinder("profile")
    void restrictProfileBinding(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping("/profile")
    String updateProfile(
            @ModelAttribute("profile") ProfileForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported profile fields"
            );
        }

        if (errors.hasErrors()) {
            return "profile-form";
        }

        // Call service to update authorized fields.
        return "profile-saved";
    }
}
```

This snippet is **not** the standalone Java file from Section 6. It requires `ProfileForm`, Spring Web MVC dependencies, controller scanning, routing, and a running web app. `BindingResult` appears **immediately after** `@ModelAttribute` to capture that object's binding result.

In this example:

1. `@InitBinder("profile")` configures the allowlist for the model attribute named `profile`.
2. Spring MVC routes form/query parameters to `WebDataBinder` via model-attribute binding.
3. Fields outside the allowlist are suppressed; their names appear in `BindingResult.getSuppressedFields()`.
4. The controller proactively returns a client error if policy forbids ignored fields.
5. If there is no suppression yet binding/validation errors exist, the controller handles the form as usual.
6. When data is valid, the service layer must still verify that the current user is authorized to update the profile.

### Does @RequestBody follow this same path?

Do not infer that unknown JSON keys in `@RequestBody` always show up in `getSuppressedFields()`. For JSON requests, Spring MVC normally uses an `HttpMessageConverter` (like Jackson) to deserialize the body. Unknown JSON properties and JSON binding settings are handled by the converter; they **do not necessarily** pass through `DataBinder.bind(PropertyValues)`. `getSuppressedFields()` applies primarily when using `DataBinder`/`WebDataBinder` **property binding**, such as `@ModelAttribute`.

If your application needs to control and track JSON fields, use DTOs, JSON deserialization settings, and appropriate schema/authorization checks. Do not rely on `getSuppressedFields()` as an all-format unknown-key detector.

## 9. Suppressed fields vs. unknown fields and binding errors

Three distinct phenomena must be kept separate:

| Phenomenon | Example | How Spring normally handles it |
| --- | --- | --- |
| **Suppressed field** | `role` has a setter yet is absent from `setAllowedFields(...)` | Strips property value from binding and records **field name** in `getSuppressedFields()`. |
| **Unknown property** | Input has `obsoleteField` absent from model; not caught earlier by allow/deny filter | Per `setIgnoreUnknownFields(...)`, may be ignored by default; not every unknown property becomes a suppressed field. |
| **Binding/conversion error** | `age=abc` while Java property is `Integer` | Normally emits a `FieldError` with a code like `typeMismatch`; check `hasErrors()` and `getFieldErrors()`. |

Example:

```java
binder.setIgnoreUnknownFields(true); // DataBinder default.
```

This setting **differs** from `setAllowedFields(...)`: it governs properties that do not exist on the model. If a name is blocked by the allowlist, it can be recorded as suppressed before Spring attempts property access. If a name is allowed yet the model lacks that property, handling depends on `ignoreUnknownFields` and the property access mechanism.

Therefore, do not use `getSuppressedFields()` as an exhaustive counter of all unexpected inputs or rejected data.

### Do suppressed fields create a FieldError?

Normally **no**. `DataBinder.checkAllowedFields(...)` removes disallowed property values and adds their names to the suppressed field set. This is **binding metadata**. Errors from validators or conversion are represented by `FieldError`/`ObjectError`. If your application wants to treat suppression as a request error, define your own policy returning 400 or a custom error mechanism.

### Does getSuppressedFields contain rejected values?

No. The method returns **field names**. That makes tracking possible without dumping raw values into logs. Still, field names alone can reveal API structure if returned to clients; weigh response contents carefully.

## 10. Nested paths, collections, and wildcards: keeping scope tight

Spring supports nested property paths, indexed paths, and map keys:

```text
address.city
address.country
items[0].sku
items[1].quantity
preferences[theme]
```

When configuring an allowlist, tie patterns to the exact paths actually permitted, e.g.:

```java
binder.setAllowedFields(
    "displayName",
    "address.city",
    "address.country",
    "items[*].sku"
);
```

This is an illustrative snippet; the model needs matching fields, getters/setters, and collections. Spring wildcards use **simple matching**, not regex. Test patterns against the real nested/indexed inputs your frontend submits.

Things to verify:

- Field names in `getSuppressedFields()` are the property paths recorded by Spring; never assume they are always simple top-level names or ordered identically to the request.
- `address.*` can cover future `address` fields as the model evolves. Be explicit when handling tightly controlled data.
- `items[*].sku` and `items[0].sku` have different coverage; verify wildcards against the Javadoc and tests.
- Map keys and indexed expressions may undergo canonicalization. Compare against the canonicalized names Spring uses rather than guessing from raw request strings.
- For very large inputs or unusual indexes, bound payload size and collection auto-grow; suppression is not a defense against memory exhaustion.
- Never log client-supplied field paths without bounding character lengths and total volume.

## 11. Declarative binding since Spring 6.1

Spring Framework 6.1 provides:

```java
binder.setDeclarativeBinding(true);
```

Per the Javadoc, this setting restricts binding such that:

- **Constructor binding** applies to declared constructor parameters.
- **Property binding** runs only when `allowedFields` is configured.

Example in a controller:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "email");
}
```

This snippet belongs in a controller or `@ControllerAdvice` with appropriate imports. Combining these settings keeps binding rules explicit.

**Monitoring caveat:** if declarative binding disables property binding entirely because no allowlist is configured, do not assume every request key outside the constructor will appear in `getSuppressedFields()`. Suppressed-field recording primarily happens during `checkAllowedFields(...)`; a path that skips that step may not populate suppressed names. Treat `getSuppressedFields()` as an indicator of **fields recorded by the binder as suppressed**, not a complete log of all ignored input.

### Why isn't constructor binding controlled by setAllowedFields?

`construct(ValueResolver)` resolves values needed for constructor parameters; `setAllowedFields(...)` governs **property binding**. If a DTO constructor takes a `role` parameter and the client supplies `role=ADMIN`, setting a property allowlist will not strip that parameter from the constructor signature. Design DTOs with only constructor arguments clients may supply, and assign server-owned roles server-side.

This is also why **constraining data in a DTO** is generally easier to govern than binding straight onto domain/JPA entities full of setters and internal relationships.

## 12. Monitoring in production

A practical policy should explicitly define:

1. **Input scope**: which endpoints use `@ModelAttribute`/property binding vs. JSON converters.
2. **Acceptance policy**: which fields may be edited per use case; prefer dedicated DTOs.
3. **Behavior on suppression**: reject the request, or during a migration window log and warn.
4. **Observability**: route template, correlation ID, count of blocked fields, and bounded/sanitized field names; avoid logging secrets.
5. **Regression testing**: whenever adding a property to a DTO/domain model, submit inputs attempting to mutate it and verify server state stays intact.
6. **Authorization**: verify the user has permission to modify the target record/resource; allowlists do not enforce object-level access control.
7. **Alerting**: spikes in blocked requests can signal frontend bugs or probing, though they do not automatically prove an attack.

Pseudocode at an application layer holding binder/result:

```java
String[] suppressed = result.getSuppressedFields();

if (suppressed.length != 0) {
    // Increment metric for route + reason "field_suppressed".
    // Log bounded, sanitized field names; no raw values.
    // Reject request if the endpoint contract requires strict fields.
}
```

This is pseudocode; metrics and logging depend on your stack. Never use raw client data as unbounded-cardinality metric labels; use route templates or normalized reason codes.

### Which cases should be tested?

| Test case | Expectation |
| --- | --- |
| Send only `displayName` and `email` in allowlist | Binder updates both fields; suppressed is empty. |
| Also send `role` outside allowlist | `role` stays unchanged; `getSuppressedFields()` contains `role`. |
| `role` in both allowlist and denylist | Denylist wins; `role` is still suppressed. |
| Send mistyped value for an allowed field | Appropriate binding error; not necessarily any suppressed field. |
| Send unknown field with no allowlist | Outcome depends on `ignoreUnknownFields`; not treated as suppressed by default. |
| Send nested/indexed field | Verify exact path and permitted pattern. |
| Client sends differently cased key | Verify case-sensitive allowlist and case-insensitive denylist on your Spring version. |
| Using JSON `@RequestBody` | Test Jackson/DTO configuration separately; do not rely on `getSuppressedFields()`. |
| Using constructor binding | Test constructor signature and fields extracted from request. |

## 13. Common misconceptions and mistakes

1. **Checking only `BindingResult.hasErrors()`.** Suppression normally does not emit a validation error; inspect `getSuppressedFields()` separately.
2. **Using `setDisallowedFields("role")` and forgetting new sensitive attributes.** Denylists fall behind as models evolve; prefer allowlists or dedicated DTOs.
3. **Binding directly onto JPA entities.** Entities often expose properties, relations, and setters not meant for clients; use tightly scoped request DTOs.
4. **Assuming `getSuppressedFields()` captures every unexpected input.** Unknown properties, JSON deserialization, constructor binding, and other paths may not appear in this array.
5. **Returning the suppressed field list to end users thoughtlessly.** The API can leak internal property names; return generic errors and keep details in controlled logs.
6. **Logging raw rejected values.** `getSuppressedFields()` returns names, not values; never re-collect entire requests into logs, especially when credentials or PII may be present.
7. **Using overly broad wildcards.** `address.*` or `*` can expose newly added fields not meant to be edited.
8. **Confusing `setIgnoreUnknownFields` with `setAllowedFields`.** One controls unknown properties; the other restricts bindable fields.
9. **Treating suppression as authorization.** It protects the property-binding surface, not whether a user has permission to edit a record or hold a role.
10. **Failing to re-test after extending a model.** Adding a new setter to a class changes the binding surface; allowlist tests prevent regressions.
11. **Asserting suppressed-field array order in tests.** Sort or compare as a set; business logic should not rely on recording order.
12. **Trying to apply property-binding allowlists to constructor parameters.** The two binding modes follow separate paths; constructors must be designed to take only intended fields.

## 14. Self-check questions

1. What type does `BindingResult.getSuppressedFields()` return? Does it contain field names or input values?
2. Why can a request with blocked `role=ADMIN` still cause `BindingResult.hasErrors()` to return `false`?
3. When `role` appears in both `setAllowedFields` and `setDisallowedFields`, what happens?
4. How do `setAllowedFields` and `setDisallowedFields` differ in default field scope and case sensitivity?
5. Does `setIgnoreUnknownFields(true)` guarantee every unknown key appears in `getSuppressedFields()`? Why or why not?
6. When should you return HTTP 400 on suppressed fields, and when might you only monitor during a transition?
7. Why shouldn't you bind directly into an entity with `setRole` or `setBalance` setters?
8. With `@ModelAttribute`, how do you retrieve suppressed fields in a controller and where must `BindingResult` be placed?
9. Why doesn't JSON `@RequestBody` with unknown properties always go through `DataBinder.getSuppressedFields()`?
10. With Spring 6.1 `setDeclarativeBinding(true)`, why can't the suppressed array be treated as a complete record of every client-sent key?

**Key takeaway:** `DataBinder` can block fields outside the **property binding** policy; `BindingResult.getSuppressedFields()` reports the **names of fields recorded as suppressed by the binder**. This result is not automatically a binding error or validation error. To monitor and protect your application, use explicit allowlists/DTOs, inspect suppressed fields independently of `hasErrors()`, and enforce proper handling and logging policies at the entry point.

## References

- Spring Framework 6.1 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.1 — BindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.1 — AbstractBindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/validation/AbstractBindingResult.html
- Spring Framework — Data Binding / Model Design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — Validation, Data Binding and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
