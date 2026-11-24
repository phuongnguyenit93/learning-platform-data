# Protecting Update Forms with allowedFields and Checking Suppressed Fields

## 1. The Problem: Client Updates Profile While Sneaking in Admin Privileges

A Spring MVC application has a profile update page. Users are allowed to edit their **display name** and **bio**, but are **not** allowed to change their own role (`role`), admin flag (`admin`), or owner (`ownerId`).

Valid form request:

```http
POST /api/profile/update
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java%20developer
```

Request showing signs of **mass assignment / overposting**:

```http
POST /api/profile/update
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java%20developer&role=ADMIN&admin=true&ownerId=999
```

If a controller binds every property directly onto a mutable JavaBean or JPA entity with setters, Spring can assign unauthorized values. This is the **mass assignment** risk: just because a field is not rendered in the UI does not mean an attacker cannot send that field name in an HTTP request.

In Spring MVC, one protective layer during **property binding** is:

```java
@InitBinder("profileForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
```

With that in place, parameters outside the allowlist are not used to populate properties. However, there is a crucial detail:

**Suppressed fields do not automatically become a `FieldError` or HTTP 400.**

You must check explicitly:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

For example, `role`, `admin`, and `ownerId` can appear in `suppressed`. The controller can decide to reject the entire request instead of silently ignoring them. This hands-on lesson uses a **reject-on-suppression** policy: if any disallowed field is detected, apply no updates at all and return a safe HTTP 400 error.

**Learning objectives:**

1. Understand the mass assignment risk when using `@ModelAttribute`/`WebDataBinder`.
2. Use `setAllowedFields` as a closed allowlist.
3. Read `BindingResult#getSuppressedFields` to detect skipped parameters.
4. Distinguish suppressed fields from binding errors and Bean Validation errors.
5. Define a handling strategy: intentional ignore, warning, or rejecting the whole request.
6. Ensure updates modify only business-permitted fields without binding directly to a JPA entity.
7. Write `MockMvc` and `DataBinder` test suites proving no overposting occurs.
8. Understand the boundary: `allowedFields` applies to **property binding**, not Jackson JSON filtering, and does not replace authorization checks.

**Reference environment:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1, Spring MVC Servlet, Jakarta Bean Validation. The demo runs standalone with Gradle and needs no database. An in-memory store is used only to inspect state before/after updates; in real deployments, replace it with a service/repository with proper transactions, identity, and authorization.

## 2. Why “Hiding Fields in HTML” Is Not Security

An HTML form contains only:

```html
<form method="post" action="/api/profile/update">
  <input name="displayName" value="Lan">
  <textarea name="bio">Java developer</textarea>
  <button type="submit">Save</button>
</form>
```

Yet an attacker can use curl, Postman, or an HTTP interception proxy to send:

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java developer' \
  --data-urlencode 'admin=true' \
  --data-urlencode 'role=ADMIN'
```

Spring does not rely on which inputs were rendered on the HTML page. It processes **the actual request parameters**. If the model has matching setters and the controller does not restrict property binding, those property names can be bound.

A common dangerous snippet:

```java
@PostMapping("/update")
public String update(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "redirect:/profile";
}
```

This is a **counterexample**, not part of the runnable project. It has multiple flaws at once: binding directly onto an entity, losing the boundary of client-editable fields, risking unintended ID/role binding, lacking ownership checks, and potentially overwriting existing data.

**Never use the frontend omitting `role` as a security mechanism.** Update permissions must be enforced on the server.

## 3. How DataBinder and allowedFields Work

### 3.1. Default Property Binding

With a JavaBean having setters:

```java
public class LegacyForm {
    private String displayName;
    private String role;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

If you create a `DataBinder` and call `bind(...)` with `displayName=Lan` and `role=ADMIN`, by default the binder can bind **both** properties. There is no protection on `role` unless you design a dedicated DTO or binder policy.

### 3.2. setAllowedFields

```java
binder.setAllowedFields("displayName", "bio");
```

Spring `DataBinder` checks each property name against the allowlist. Properties that do not match are **removed from the property values before binding**.

The flow can be visualized as:

```text
HTTP form parameters
  displayName=Lan
  bio=Java developer
  role=ADMIN
  admin=true
  ownerId=999
         |
         v
WebDataBinder
  allowedFields = [displayName, bio]
         |
         +--> displayName=Lan        -> allowed for setter assignment
         +--> bio=Java developer     -> allowed for setter assignment
         +--> role=ADMIN             -> suppressed
         +--> admin=true             -> suppressed
         +--> ownerId=999            -> suppressed
         |
         v
BindingResult
  getSuppressedFields(): [role, admin, ownerId]
         |
         v
Controller decides:
  - If suppressed is non-empty -> reject the entire request.
  - If binding/validation errors exist -> report corresponding errors.
  - If both are empty -> invoke the update service.
```

**Do not rely on the ordering of `getSuppressedFields()` as an API contract.** When comparing in tests or logging field names, normalize with a `Set` or sort the list.

### 3.3. How the Allowlist Is Matched

The Spring `DataBinder#setAllowedFields` Javadoc states:

- By default, when no allowed fields are configured, the binder allows binding all matching property names.
- Patterns support exact names and `*` wildcards, e.g., `"xxx*"`, `"*xxx"`, `"*xxx*"`.
- Matching of allowed field patterns is generally **case-sensitive**.
- Before checking, the binder canonicalizes the property path. For nested/indexed properties, you must understand the path representation and matching pattern.
- `setAllowedFields` applies to **`bind(PropertyValues)`**, not to filtering constructor parameters via `construct(ValueResolver)`.

Example:

```java
binder.setAllowedFields(
        "displayName",
        "bio",
        "address.city"
);
```

The allowed scope can include only name, bio, and one child field `address.city`.

Do not use an overly broad pattern:

```java
binder.setAllowedFields("*");
```

because it largely defeats the purpose of an allowlist. A pattern like `"address.*"` also needs careful review: it can expose **unintended child fields**. For sensitive data, enumerate exact property paths.

### 3.4. allowedFields vs disallowedFields

`setDisallowedFields("role", "admin")` is a blocklist: any field not in the forbidden list can still be bound. When an entity/DTO gains a new property, blocklists easily miss it.

`setAllowedFields("displayName", "bio")` is an allowlist: new properties are **not allowed automatically**. This is the safer option when mutable property binding must be used.

In Spring Framework 6.1, `disallowedFields` uses case-insensitive matching whereas `allowedFields` is case-sensitive. Do not assume both share the same semantics. In security-sensitive code, prefer an explicit allowlist over relying on blocklist casing behavior.

## 4. BindingResult#getSuppressedFields: An Often-Overlooked Check

### 4.1. Suppressed Is Not a Binding Error

A request submits:

```text
displayName=Lan&bio=Hello&admin=true
```

If `displayName` and `bio` bind with valid types while `admin` is filtered out because it is not in the allowlist, `BindingResult` can have:

```text
bindingResult.hasErrors() == false
bindingResult.getSuppressedFields().length == 1
bindingResult.getSuppressedFields()[0] == "admin"
```

This is an **illustrative result** for that binder setup, not a guarantee of array ordering in all cases. The crucial point is that **`hasErrors()==false` does not mean the request contained no disallowed fields**.

Therefore, writing only:

```java
if (bindingResult.hasErrors()) {
    return badRequest();
}
service.update(form);
```

is insufficient if your security policy requires **rejecting any extra parameters**.

### 4.2. The Reject-on-Suppression Policy

```java
if (bindingResult.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest().body(
            new ApiError(
                    "DISALLOWED_FIELDS",
                    "Request contains fields that cannot be updated",
                    List.of()
            )
    );
}
```

This snippet appears in the runnable controller. It guarantees the update method is never called when the request includes any field outside the allowlist.

**Check ordering also matters:**

1. Detect suppressed fields.
2. If suppressed is non-empty, return an error and **do not call the service**.
3. If nothing is suppressed but binding/validation errors exist, return data validation errors.
4. If neither exists, apply changes through the service.

A request can simultaneously have a suppressed field and an invalid allowed field. This lesson prioritizes returning `DISALLOWED_FIELDS` to avoid partial processing of suspicious payloads; other applications may aggregate errors, provided the policy is consistent.

### 4.3. Should Suppressed Field Names Be Returned to Clients?

In many applications, return a **generic** message:

```json
{
  "code": "DISALLOWED_FIELDS",
  "message": "Request contains fields that cannot be updated",
  "errors": []
}
```

Never echo back `role=ADMIN`, `ownerId=999`, raw rejected values, or stack traces. Suppressed field names may be recorded in audit logs **if policy permits**, while avoiding logging sensitive values. Whether to reveal the list of disallowed field names to the client depends on your API contract and security requirements.

If auditing is desired:

```java
String[] suppressed = bindingResult.getSuppressedFields();
String[] ordered = suppressed.clone();
java.util.Arrays.sort(ordered);

// Log only field names per security logging policy;
// never log raw values/passwords/tokens.
```

This is an illustrative snippet. Do not misuse audit logs to dump full sensitive payloads.

### 4.4. Why Not Rely Solely on suppressedFields?

The suppressed array only reports **property values received by the binder and marked disallowed**. It does not:

- Verify whether the user owns the account being edited.
- Check whether an **allowed field** violates a business rule when changed.
- Protect service methods called directly from jobs or event listeners.
- Protect JSON deserialization going through Jackson instead of the form property binder.
- Replace unique constraints, transactions, or concurrency controls.
- Prevent a client-sent secret from appearing in reverse-proxy access logs.

Thus, **`allowedFields` is one layer in defense-in-depth**, not the entire security model.

## 5. Three Distinct Boundaries: Bind, Validate, and Authorize

### 5.1. Binding Allowlist

Answers the question: **which properties of the form object may the client populate?**

For example: only `displayName` and `bio`.

### 5.2. Input Validation

Answers: **are the values of those allowed properties valid?**

Example:

```java
@NotBlank
@Size(max = 60)
private String displayName;

@Size(max = 280)
private String bio;
```

`@NotBlank`/`@Size` do not decide whether the client may modify `role`. Conversely, `allowedFields` does not check string length or business formatting.

### 5.3. Authorization and Business Mapping

Answers: **which resource may the current user update, and which changes are permitted?**

In production, identity comes from a verified authentication principal/session/JWT—**never trust `ownerId` from a form**. The service must load the resource by authenticated identity/scope and verify permissions. When updating, map only permitted fields explicitly:

```java
account.setDisplayName(form.getDisplayName());
account.setBio(form.getBio());
```

This is an illustrative snippet assuming `account` has already been loaded and ownership verified. Never use `BeanUtils.copyProperties(form, entity)` unconditionally or reflective object mapping that might accidentally copy `role`/`ownerId`.

## 6. Behavior with Constructor Binding, Records, and declarativeBinding

Spring MVC 6.1 supports constructor binding for immutable objects and Java records. Remember that **`setAllowedFields` controls property binding, not constructor parameters**.

### 6.1. Property Binding

```java
public class ProfileForm {
    private String displayName;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

With setter/property binding, the allowlist blocks disallowed properties.

### 6.2. Constructor Binding

```java
public record ImmutableProfileForm(
        String displayName,
        String bio
) {}
```

Spring can instantiate the object via its constructor based on parameter names. Because the constructor requires only these two values and has no `role` setter, designing an immutable input DTO is the preferred direction.

**Limitation:** if the record itself declares `String role` or `Long ownerId` in its constructor, a property-binding allowlist **cannot be assumed to filter those constructor parameters**. Designing the right constructor input shape from the start is essential.

### 6.3. setDeclarativeBinding(true)

Spring Framework 6.1+ enables:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Meaning: constructor binding runs, while property binding runs only when `allowedFields` patterns are configured. To support property binding on a mutable form, declare the corresponding allowlist:

```java
@InitBinder("profileForm")
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
```

In the runnable demo below, the configuration uses only `setAllowedFields` to focus on property binding and `getSuppressedFields`. In production, consider `declarativeBinding` after testing all form flows and DTO structures.

**Do not confuse with `setRequiredFields`:** the required-fields option on `DataBinder` applies to property binding and does not automatically make constructor parameters required. Requiredness on records should be modeled with appropriate validation constraints/boundaries.

## 7. @ModelAttribute vs @RequestBody JSON

Signature:

```java
public ResponseEntity<?> update(
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    ...
}
```

reads form/query parameters through Spring MVC binding; `@InitBinder` can set `allowedFields` on `WebDataBinder`.

Conversely:

```java
public ResponseEntity<?> updateJson(
        @RequestBody ProfileForm form) {
    ...
}
```

reads JSON via `HttpMessageConverter` (typically Jackson). Spring may use `WebDataBinder` **after deserialization for validation**, but `DataBinder#setAllowedFields` **does not filter JSON properties** while Jackson constructs the object. Therefore, never add such a JSON endpoint expecting the form allowlist to protect `role`.

If the API needs JSON:

1. Create a **dedicated JSON input record** containing only `displayName` and `bio`.
2. Use `@Valid @RequestBody ProfileUpdateRequest` for validation.
3. Control unknown JSON properties via `ObjectMapper` policy/API contract if extra fields must be detected.
4. Most importantly: service mapping updates only allowed fields and enforces authorization.
5. If JSON payloads with keys outside the schema must be blocked, configure Jackson's strict unknown-property policy on the input DTO/`ObjectMapper` and test it. That is JSON deserialization's responsibility, not `setAllowedFields`.

**Do not use “Jackson ignores unknown fields” as the sole security boundary.** DTOs can gain new properties over time; ensure `role`/privileged setters are absent from input models and the service mapper never copies the whole entity blindly.

## 8. Runnable Spring Boot Project: Updating a Profile with an Allowlist

The demo uses Java 17 and Spring Boot 3.3.6. There are two endpoints:

- `GET /api/profile`: inspect the current state of the single demo profile.
- `POST /api/profile/update`: update name and bio via `application/x-www-form-urlencoded`, checking allowed fields, suppressed fields, and Bean Validation.

**Security note:** endpoints have no authentication because this is an isolated example for learning data binding, not a production API. The demo profile always has ID=1 and role=USER; in real deployments, add Spring Security/principal handling and service-level authorization.

### 8.1. Directory Structure

```text
profile-allowed-fields-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/profilebinding/
        ProfileBindingApplication.java
        ProfileForm.java
        ProfileView.java
        FieldIssue.java
        ApiError.java
        ProfileService.java
        ProfileController.java
      resources/
        application.properties
    test/
      java/com/example/profilebinding/
        ProfileAllowedFieldsTest.java
```

### 8.2. settings.gradle

```groovy
rootProject.name = 'profile-allowed-fields-demo'
```

### 8.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` supplies the Jakarta Bean Validation provider in typical Spring Boot 3.x setups. `spring-boot-starter-web` provides Spring MVC, `WebDataBinder`, and Jackson for JSON responses.

### 8.4. application.properties

`src/main/resources/application.properties`:

```properties
spring.application.name=profile-allowed-fields-demo
spring.mvc.problemdetails.enabled=false
```

The Problem Details setting simply keeps the demo error response straightforward. In production applications, RFC 9457 `ProblemDetail` can be used, while suppressed-field policy must still be enforced explicitly by the controller/service.

### 8.5. Main Application

`src/main/java/com/example/profilebinding/ProfileBindingApplication.java`:

```java
package com.example.profilebinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ProfileBindingApplication.class, args
        );
    }
}
```

### 8.6. ProfileForm: Demonstrating a Legacy DTO with Extra Setters

`src/main/java/com/example/profilebinding/ProfileForm.java`:

```java
package com.example.profilebinding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ProfileForm {

    @NotBlank
    @Size(max = 60)
    private String displayName;

    @Size(max = 280)
    private String bio;

    // Legacy properties kept intentionally to demonstrate overposting.
    // In new production DTOs, REMOVE these properties.
    private String role;
    private Boolean admin;
    private Long ownerId;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public Boolean getAdmin() {
        return admin;
    }

    public void setAdmin(Boolean admin) {
        this.admin = admin;
    }

    public Long getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(Long ownerId) {
        this.ownerId = ownerId;
    }
}
```

**Why does the demo have `role`/`admin`/`ownerId` on the form?** So the tests can prove they **would be bound without an allowlist**, yet **are suppressed with an allowlist**. This represents a legacy DTO needing protection. In greenfield production code, the right design is a DTO containing only `displayName` and `bio`; the allowlist then acts as an extra defensive layer rather than an excuse to retain sensitive setters.

`@NotBlank` rejects null/empty/whitespace-only strings. `@Size(max=60)` rejects overly long names, `@Size(max=280)` rejects overly long bios; `@Size` normally allows null so `bio` is optional.

### 8.7. ProfileView: Server-Held State

`src/main/java/com/example/profilebinding/ProfileView.java`:

```java
package com.example.profilebinding;

public record ProfileView(
        long id,
        String displayName,
        String bio,
        String role,
        boolean admin
) {}
```

`role` and `admin` may be **displayed** in the read response in the demo, yet cannot be **updated** from the profile form. Read permission does not imply write permission. In real applications, displaying internal metadata also requires appropriate authorization/redaction rules.

### 8.8. FieldIssue and ApiError

`src/main/java/com/example/profilebinding/FieldIssue.java`:

```java
package com.example.profilebinding;

public record FieldIssue(
        String field,
        String code
) {}
```

`src/main/java/com/example/profilebinding/ApiError.java`:

```java
package com.example.profilebinding;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> errors
) {}
```

`DISALLOWED_FIELDS` is the code when the request contains out-of-allowlist inputs. `VALIDATION_ERROR` is the code when allowed fields fail constraints. The public response omits raw `rejectedValue`s and internal property lists.

### 8.9. ProfileService: Applying Only Allowed Fields

`src/main/java/com/example/profilebinding/ProfileService.java`:

```java
package com.example.profilebinding;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final AtomicReference<ProfileView> state =
            new AtomicReference<>(initial());

    public ProfileView current() {
        return state.get();
    }

    public ProfileView update(ProfileForm form) {
        return state.updateAndGet(old -> new ProfileView(
                old.id(),
                form.getDisplayName().trim(),
                form.getBio() == null ? old.bio() : form.getBio(),
                old.role(),
                old.admin()
        ));
    }

    // Used only for test fixtures in the in-memory demo.
    void resetDemoState() {
        state.set(initial());
    }

    private static ProfileView initial() {
        return new ProfileView(
                1L,
                "An",
                "Tiểu sử cũ",
                "USER",
                false
        );
    }
}
```

The service **does not** read `form.getRole()`, `form.getAdmin()`, or `form.getOwnerId()`. Even if another bug allowed those fields to bind, the `update` implementation still maps only `displayName` and `bio`—a second layer of defense.

`AtomicReference#updateAndGet` suits a single-profile demo and does not represent real database transactions/locking. Production typically needs loading entities by authenticated identity, permission checks, versioning/optimistic locking for concurrent updates, invariant validation, and transactional persistence.

`resetDemoState()` is package-private for test fixtures; there is no HTTP endpoint for it. Never expose a data-reset endpoint in a real application.

### 8.10. ProfileController: @InitBinder, suppressedFields, and BindingResult

`src/main/java/com/example/profilebinding/ProfileController.java`:

```java
package com.example.profilebinding;

import jakarta.validation.Valid;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final ProfileService profiles;

    public ProfileController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @InitBinder("profileForm")
    void restrictProfileForm(WebDataBinder binder) {
        // Only these two properties are allowed via form binding.
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping
    public ProfileView current() {
        return profiles.current();
    }

    @PostMapping(
            path = "/update",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> update(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        // Security step that must not be skipped:
        // suppressed fields do NOT automatically make result.hasErrors() == true.
        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "DISALLOWED_FIELDS",
                            "Request contains fields that cannot be updated",
                            List.of()
                    )
            );
        }

        if (result.hasErrors()) {
            List<FieldIssue> issues = result.getAllErrors()
                    .stream()
                    .map(ProfileController::toIssue)
                    .sorted(Comparator.comparing(FieldIssue::field)
                            .thenComparing(FieldIssue::code))
                    .toList();

            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_ERROR",
                            "Profile form is invalid",
                            issues
                    )
            );
        }

        // Execute only when there are no suppressed fields or errors.
        return ResponseEntity.ok(profiles.update(form));
    }

    private static FieldIssue toIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        return new FieldIssue(
                field,
                Objects.toString(error.getCode(), "invalid")
        );
    }
}
```

**Note each condition:**

1. `@InitBinder("profileForm")` configures only the binder for the model attribute named `profileForm`, avoiding affecting other forms with different policies.
2. `setAllowedFields("displayName","bio")` filters setter/property binding.
3. `@Valid` runs Bean Validation after binding when the object is ready to be checked.
4. `BindingResult result` sits **immediately after** the form argument; otherwise, the controller will not receive binding/validation errors as designed.
5. `getSuppressedFields` is checked **before** `hasErrors`. If the payload has forbidden fields, reject the request before updating.
6. `getAllErrors` collects both `FieldError` and `ObjectError`; the list is sorted by field/code instead of relying on provider order.
7. The service update receives the object only after passing all gates and still maps fields explicitly.
8. The controller does not return suppressed field **values** or schema internals to the client.
9. Do not use `BeanUtils.copyProperties` on entities; it can undermine the security contract.

### 8.11. Why Is There No @RestControllerAdvice for Suppressed Fields?

Suppressed fields **do not automatically throw an exception**. An `@ExceptionHandler(MethodArgumentNotValidException.class)` will never catch a client sending `role=ADMIN` if all allowed inputs are valid and the binder simply suppresses `role`.

Therefore, having `BindingResult` right in the controller to read `getSuppressedFields` and reject is the most transparent pattern in the demo. Across many controllers, you can extract a shared helper/policy, provided it is invoked at **every update boundary** that must block overposting.

Never assume “the project already has global validation advice” is enough to protect property binding.

## 9. Running the Application and Observing Responses

In a project with the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If there is no Gradle wrapper yet, use an appropriate installed Gradle and run `gradle bootRun` or generate the wrapper.

### 9.1. Viewing the Initial Profile

```bash
curl -i http://localhost:8080/api/profile
```

Expected HTTP 200, body:

```json
{
  "id": 1,
  "displayName": "An",
  "bio": "Tiểu sử cũ",
  "role": "USER",
  "admin": false
}
```

In-memory state resets whenever the application restarts.

### 9.2. Valid Update

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java developer'
```

Expected HTTP **200 OK**:

```json
{
  "id": 1,
  "displayName": "Lan",
  "bio": "Java developer",
  "role": "USER",
  "admin": false
}
```

`role` and `admin` remain unchanged because they are not editable fields and because the service does not copy them from the form.

### 9.3. Sending Extra Forbidden Fields

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Hacker' \
  --data-urlencode 'bio=Overposted' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'admin=true' \
  --data-urlencode 'ownerId=999'
```

Expected HTTP **400 Bad Request**:

```json
{
  "code": "DISALLOWED_FIELDS",
  "message": "Request contains fields that cannot be updated",
  "errors": []
}
```

Calling GET profile again shows **no changes from this request**, because the controller rejected it before the service ran. If 9.2 was executed beforehand, name remains `Lan` and bio remains `Java developer`.

### 9.4. Blank Name Is a Validation Error, Not a Suppressed Field

```bash
curl -i -X POST http://localhost:8080/api/profile/update \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=   ' \
  --data-urlencode 'bio=Hello'
```

Expected HTTP 400, code `VALIDATION_ERROR`, and a field error on `displayName` with code `NotBlank`. `displayName` is in the allowlist, so it is not suppressed; its **value** is invalid, not its **field-write permission**.

## 10. MockMvc and DataBinder Test Suite

File `src/test/java/com/example/profilebinding/ProfileAllowedFieldsTest.java`:

```java
package com.example.profilebinding;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileAllowedFieldsTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProfileService profiles;

    @BeforeEach
    void resetState() {
        profiles.resetDemoState();
    }

    @Test
    void validFormChangesOnlyEditableProperties() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("bio", "Java developer"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.bio").value("Java developer"))
            .andExpect(jsonPath("$.role").value("USER"))
            .andExpect(jsonPath("$.admin").value(false));

        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void forbiddenAdminIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("bio", "Try privilege change")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
        assertFalse(profiles.current().admin());
    }

    @Test
    void forbiddenRoleIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("USER", profiles.current().role());
    }

    @Test
    void forbiddenOwnerIdIsSuppressedAndRejected()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Eve")
                .param("ownerId", "999"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals(1L, profiles.current().id());
        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void unknownFieldIsSuppressedAndRejected() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("newFeatureFlag", "enabled"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void rejectedRequestDoesNotApplyValidFieldsPartially()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Valid New Name")
                .param("bio", "Valid new bio")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
        assertEquals("Tiểu sử cũ", profiles.current().bio());
    }

    @Test
    void missingNameTriggersValidationError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("bio", "Hello"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void blankNameTriggersValidationError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "  "))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void tooLongNameTriggersSizeError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "x".repeat(61)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("Size"));
    }

    @Test
    void tooLongBioTriggersSizeError() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("bio", "a".repeat(281)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field")
                    .value("bio"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("Size"));
    }

    @Test
    void missingOptionalBioPreservesOldBio() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.bio").value("Tiểu sử cũ"));
    }

    @Test
    void suppressedFieldTakesPrecedenceOverInvalidAllowedData()
            throws Exception {

        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "  ")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"));

        assertEquals("An", profiles.current().displayName());
    }

    @Test
    void wrongContentTypeIsNotFormBinding() throws Exception {
        mvc.perform(post("/api/profile/update")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","role":"ADMIN"}
                        """))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void directBinderSuppressesEveryDisallowedProperty() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "bio");

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "bio", "Hello",
                "role", "ADMIN",
                "admin", "true",
                "ownerId", "999"
        )));

        assertEquals("Lan", form.getDisplayName());
        assertEquals("Hello", form.getBio());
        assertNull(form.getRole());
        assertNull(form.getAdmin());
        assertNull(form.getOwnerId());

        BindingResult result = binder.getBindingResult();

        Set<String> suppressed = new HashSet<>(
                Arrays.asList(result.getSuppressedFields())
        );

        assertEquals(
                Set.of("role", "admin", "ownerId"),
                suppressed
        );
        assertFalse(result.hasErrors());
    }

    @Test
    void directBinderWithoutAllowlistIsUnsafeForLegacyDto() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "role", "ADMIN",
                "admin", "true",
                "ownerId", "999"
        )));

        // Control check: sensitive setters were populated!
        assertEquals("ADMIN", form.getRole());
        assertEquals(Boolean.TRUE, form.getAdmin());
        assertEquals(999L, form.getOwnerId());
        assertEquals(0, binder.getBindingResult()
                .getSuppressedFields().length);
    }

    @Test
    void suppressedDoesNotAutomaticallyBecomeFieldError() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "bio");

        binder.bind(new MutablePropertyValues(
                Map.of("role", "ADMIN")
        ));

        BindingResult result = binder.getBindingResult();

        assertEquals(
                Set.of("role"),
                new HashSet<>(
                        Arrays.asList(result.getSuppressedFields())
                )
        );
        assertFalse(result.hasErrors());
        assertEquals(0, result.getFieldErrorCount());
    }

    @Test
    void allowedFieldPatternIsCaseSensitive() {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName");

        binder.bind(new MutablePropertyValues(
                Map.of("DisplayName", "Lan")
        ));

        assertNull(form.getDisplayName());

        assertEquals(
                Set.of("DisplayName"),
                new HashSet<>(
                        Arrays.asList(
                                binder.getBindingResult()
                                        .getSuppressedFields()
                        )
                )
        );
    }

    @Test
    void rejectedFieldValueIsNotReflectedInErrorJson()
            throws Exception {

        String marker = "SENSITIVE_MARKER_414";

        MvcResult result = mvc.perform(
                post("/api/profile/update")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("role", marker)
        )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DISALLOWED_FIELDS"))
            .andReturn();

        assertFalse(
                result.getResponse().getContentAsString()
                        .contains(marker)
        );
    }
}
```

There are **18 test methods**, grouped as:

- Permitted updates work and leave role/admin/ID unchanged.
- Sending `admin`, `role`, `ownerId`, and unknown properties is rejected.
- No partial update is applied when at least one forbidden field is present.
- Bean Validation checks missing, blank, and oversized name, and oversized bio.
- Optional bio is preserved when omitted by the user.
- When both an invalid allowed value and a suppressed field are present, security policy prioritizes rejection.
- JSON `Content-Type` is not routed to the form handler.
- Direct `DataBinder` checks verify suppressed field names and that setters were not called.
- Control `DataBinder` without allowlist shows legacy sensitive fields getting bound.
- Proves `getSuppressedFields()` does not automatically create a `FieldError`.
- Verifies allowed field name matching is case-sensitive.
- Verifies sensitive values of suppressed fields never appear in HTTP error JSON.

### 10.1. How to Run

From the project directory with Gradle wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project has no wrapper yet, use an installed Gradle to generate the wrapper or run `gradle test`. **Expect 18 tests to PASS** with Java 17 and exact Spring Boot 3.3.6 dependencies.

**Verification note:** the code and expected behavior were statically reviewed; no claim is made that Gradle/JUnit was executed during authoring. When integrating into a real project, run tests against your application's actual Spring/Security/database versions.

### 10.2. Why Test Both DataBinder and MockMvc?

A `DataBinder` test verifies **field filtering mechanics** independently of HTTP:

```java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAllowedFields("displayName", "bio");
binder.bind(values);

String[] suppressed = binder.getBindingResult()
        .getSuppressedFields();
```

Meanwhile, a `MockMvc` test verifies **integration**:

- Whether `@InitBinder("profileForm")` is selected properly.
- Whether `@ModelAttribute` receives request parameters and invokes the binder.
- Whether `BindingResult` sits immediately adjacent to the argument.
- Whether the controller checks suppressed fields **before** updating.
- Whether the service preserves server-owned fields.
- Whether the API error response leaks suppressed data.

Testing `DataBinder` alone does not prove the real controller wired the allowlist; testing only HTTP 400 without checking state does not prove an unwanted update was prevented.

## 11. Advanced Cases to Understand

### 11.1. Indexed and Nested Property Paths

If a form has `address.city` or a list `contacts[0].email`, `allowedFields` uses property path patterns. Example configurations:

```java
binder.setAllowedFields(
        "displayName",
        "bio",
        "address.city",
        "contacts[0].email"
);
```

Each path should have a business purpose. `"contacts* "` with a trailing space is a different pattern; do not copy carelessly. `"contacts*"` can allow many indexed/nested entries, including properties clients were never meant to change. When allowing multiple items, check collection size limits, object graph growth, and per-item authorization.

**Do not assume `setAllowedFields("address")` is always equivalent to allowing all nested fields `address.*`.** Understand how canonical property paths and wildcard matching behave in your current Spring version; write tests for every nested path you intend to support.

### 11.2. WebDataBinder Field Marker/Default Prefixes

Spring `WebDataBinder` supports field marker/default prefixes for inputs such as checkboxes. For instance, markers can represent an unchecked checkbox that does not submit a value directly. Marker preprocessing can transform property value names before filtering.

During security reviews, also test:

- Checkboxes on/off for allowed field names.
- Markers for disallowed field names.
- Repeated parameters and special-character parameter names.
- Canonicalized/nested property names.
- Empty/default values and custom binders.

Never assume testing a single `admin=true` parameter covers every overposting vector in a complex form.

### 11.3. Allowing Only a Subset of a Nested Object

Suppose an update form contains an address with `city`, `postalCode`, and `verified`. If the client may edit only `city`, allow `address.city` specifically and map it explicitly. If the client sends `address.verified=true`, your policy should detect and reject it.

If one user edits **another user's** profile via a user-supplied ID, `allowedFields` cannot solve that. Authorization/ownership checks must rely on verified identity and resource scope.

### 11.4. allowedFields Can Drift from the DTO During Refactoring

Suppose a developer adds `setPreferredCurrency(...)` to the DTO but forgets to update the allowlist. As a result, the new field gets suppressed and requests fail even though the UI added the input. This is **useful fail-closed behavior**: input contract changes should be reviewed and covered by tests. Never fix it by changing the allowlist to `"*"` for convenience.

Conversely, renaming `bio` to `biography` without updating `@InitBinder` will also suppress the new field. Legitimate-update tests must catch this regression.

### 11.5. Silent Ignore or Reject?

There are two valid policies depending on the product:

| Policy | Description | Pros / Cons |
| --- | --- | --- |
| Ignore | Skip forbidden fields, proceed updating allowed fields | More compatible with older clients, but easily hides anomalous payloads |
| Reject | If suppressed is non-empty, reject the whole request | Clearly detects overposting, avoids partial updates; can break legacy clients sending extra fields |

The demo chooses **Reject** because the exercise focuses on detecting suppressed fields. Whichever policy you choose, never quietly treat suppressed fields as proof that clients did not attempt to send dangerous data.

### 11.6. Update Idempotency and Concurrency

`allowedFields` does not solve the problem of two requests concurrently updating name/bio from a stale read. With a real database, you may need:

- Entity versioning via `@Version` (optimistic locking).
- Conditional requests such as `If-Match` and ETags.
- Explicit transactions and merge policies.
- Audit trails for permitted modifications.
- Authorization checks close to the write operation.
- Never updating the entire entity from out-of-allowlist client data.

This runs parallel to overposting. An update containing only allowed fields can still lose data under concurrent writes without an appropriate strategy.

### 11.7. Multipart, JSON Parts, and Other Input Sources

`@ModelAttribute` can bind form data, including matching multipart form fields. However, a `@RequestPart` containing JSON may be read by a message converter; the form binder's `allowedFields` does not filter individual JSON properties before deserialization. File uploads also require separate checks on size, media type, filename, storage path, and authorization.

Do not mechanically apply form-urlencoded policies to every content type.

## 12. Common Pitfalls

**1. Binding requests directly to a JPA entity with sensitive setters.** Prone to overposting; create a dedicated input DTO and explicit mapping.

**2. Only hiding admin/role in HTML.** Clients can send parameters that do not appear on the page.

**3. Omitting `setAllowedFields` when property binding must be used.** By default the binder can populate any property with a setter.

**4. Using `setDisallowedFields` as the sole protection layer.** Blocklists easily miss new properties; allowlists are clearer.

**5. Checking only `bindingResult.hasErrors()`.** Suppressed fields may not produce a `FieldError`.

**6. Never calling `getSuppressedFields()`.** Fails to detect fields the client sent that the binder stripped out.

**7. Checking suppressed fields after calling `service.update`.** Too late; reject before mutating state.

**8. Allowing partial updates when forbidden fields are present without an explicit policy.** Leads to unpredictable behavior and weak audit clarity.

**9. Using overly broad wildcards like `"*"` or `"address*"`.** Can inadvertently open binding paths to future fields.

**10. Assuming `allowedFields` applies to Jackson JSON `@RequestBody`.** Wrong mechanism: JSON deserialization has its own boundary.

**11. Assuming `allowedFields` filters constructor parameters.** Javadoc restricts it to property binding; input constructors must be designed properly.

**12. Thinking `setDeclarativeBinding(true)` automatically blocks dangerous constructor arguments.** Constructor binding still accepts parameters declared in the constructor.

**13. Configuring `@InitBinder` with the wrong attribute name.** The policy will not apply to the form you meant to protect.

**14. Scoping `@InitBinder` too broadly across all forms.** Can suppress legitimate fields on other endpoints; scope appropriately.

**15. Placing `BindingResult` non-adjacently to the `@ModelAttribute` argument.** The controller will not receive errors as expected.

**16. Returning raw `rejectedValue` or suppressed field values in JSON.** Can leak emails, tokens, or private data.

**17. Lacking server-side authorization.** `allowedFields` restricts properties only; it does not decide which resources a user may edit.

**18. Assuming role won't change just because the service ignores it.** Service mapping is vital, yet binder policy/tests also help detect anomalous payloads.

**19. Testing only HTTP response outcomes without checking state.** A request might return 400 after state was already mutated.

**20. Testing only valid forms.** Fails to detect overposting of `admin`, `role`, `ownerId`.

**21. Asserting the array order of `getSuppressedFields`.** Ordering is not an API contract; compare names as a set or sort them.

**22. Keeping a DTO with privileged setters “because we have an allowlist anyway”.** New DTOs should omit those fields completely; allowlists are defense-in-depth.

**23. Merging suppressed fields into business validation errors without distinction.** Easily obscures security events; use dedicated codes/tracking.

**24. Testing only HTTP forms and ignoring JSON/multipart/other writers.** Other input paths may bypass that binder.

**25. Expanding the allowlist on errors without reviewing domain rules.** A suppressed field may indicate a client sending disallowed data rather than a UI bug.

## 13. Testing and Code Review Checklist

1. Is the controller using `@ModelAttribute` property binding or `@RequestBody` JSON?
2. If using a mutable form, is there a dedicated DTO instead of an entity?
3. Is `@InitBinder` scoped to the exact attribute name?
4. Does `setAllowedFields` list the **exact** updatable fields?
5. If wildcards are used, are they narrow and tested for nested/indexed paths?
6. Have you avoided using `setDisallowedFields` as the sole security policy?
7. Does the controller read `BindingResult#getSuppressedFields()` **before calling the service**?
8. Is there an explicit decision to reject or ignore suppressed fields?
9. If rejecting, does the response use a stable code without exposing raw values?
10. If ignoring, is there appropriate audit/security monitoring without treating the payload as clean?
11. Are Bean Validation/binding errors checked separately from suppressed fields?
12. Is `BindingResult` placed immediately after `@ModelAttribute`?
13. Are tests verifying that allowed name/bio updates succeed?
14. Are there tests with `admin=true`, `role=ADMIN`, `ownerId=999`, and unknown fields?
15. Is there a test proving **the entire request is rejected with no state change**?
16. Is there a direct `DataBinder` test verifying `getSuppressedFields` and that setters were not called?
17. Is there a control binder test without allowlist demonstrating the mass assignment risk?
18. Are tests verifying case-sensitivity of `allowedField` patterns and nested inputs where present?
19. Are there tests for inputs with valid field names but invalid values/formats?
20. Does the service map only allowed fields and preserve server-owned fields?
21. Are identity and ownership taken from the authentication context rather than request fields?
22. When updating a database, are transactions, concurrency, and versioning handled properly?
23. Are JSON endpoints tested separately without mistaking `allowedFields` for a Jackson filter?
24. Are collection growth, upload size, and binding complexity bounded?
25. Are logs verified not to contain suppressed field data?
26. Are integration tests re-run when upgrading Spring Boot/Spring Framework?
27. Does renaming a DTO field trigger a review of the allowlist and tests?
28. Are HTTP 400/422 behavior and error codes documented clearly in the API contract?

**Conclusion:** With Spring MVC property binding, `WebDataBinder#setAllowedFields(...)` acts as a barrier stopping HTTP forms from setting properties outside the allowlist. However, **filtering a field does not automatically turn the request into an error**: read `BindingResult#getSuppressedFields()` and apply an intentional reject or ignore policy. To protect data updates, combine a **dedicated input DTO, allowlist, validation, suppressed-field checks before calling the service, explicit per-field mapping, and authorization**. Your test suite must prove both sides: valid data updates cleanly, while `role`/`admin`/`ownerId` parameters are rejected and cause zero unauthorized changes.

## 14. Official References

- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `setAllowedFields`, `setDeclarativeBinding`, property binding, and constructor binding.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): input model design, allowlist, nested property paths, and mass assignment risk.
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): form binding, constructor/property binding, `BindingResult`.
- [Spring Framework 6.1 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html): `setAllowedFields`, `checkAllowedFields`, patterns, case sensitivity, and constructor-binding limitations.
- [Spring Framework 6.1 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/validation/BindingResult.html): `recordSuppressedField`, `getSuppressedFields`, and binding error metadata.
- [Spring Framework — Data Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): DataBinder, BindingResult, and type conversion.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, argument validation, method validation.
- [Spring Boot 3.3 — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): Jakarta Bean Validation auto-configuration.
