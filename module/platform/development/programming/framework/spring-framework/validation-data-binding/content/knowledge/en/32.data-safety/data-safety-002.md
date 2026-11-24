# Task-Specific DTOs and Allowed Field Lists in Spring MVC

## 1. Why Is Data Binding a Security Boundary?

In Spring MVC, `@ModelAttribute` helps map request parameters onto Java object properties. This is a very convenient feature for building forms, yet it is also where **untrusted data** enters the application.

Suppose an application has a domain object containing:

```java
public class AccountEntity {
    private Long id;
    private String displayName;
    private String email;
    private String role;
    private boolean locked;
    private Long ownerId;

    // Other setters/getters omitted in this illustrative example.
}
```

A hastily written endpoint:

```java
@PostMapping("/accounts/update")
public String update(@ModelAttribute AccountEntity account) {
    accountRepository.save(account);
    return "redirect:/accounts";
}
```

The two snippets above are **anti-pattern illustrations**, not a standalone runnable program; `accountRepository` is an assumed dependency. When Spring binds directly from a request into an entity with many writable properties, a client can attempt to send extra parameters:

```text
displayName=Lan&email=lan@example.org&role=ADMIN&locked=false&ownerId=7
```

If those properties can be bound and the code updates the entity without proper controls, a user who is only allowed to change their display name could attempt to alter **permissions, lock status, or ownership**. This is a form of **mass assignment / over-posting / unsafe data binding**.

**Design principle:** Do not use "which fields exist on the entity" as the criterion for "which fields the client may submit." Field modification rights depend on the **task**, the **caller**, and the **resource**; the input DTO must express that boundary.

This lesson explains two complementary defenses:

1. **Task-specific DTO (task-specific command/input DTO):** each operation accepts only the fields belonging to that operation's contract.
2. **Allowed field list (allowlist):** when using Spring property/setter binding, configure `WebDataBinder#setAllowedFields(...)` to restrict which fields are bound, and inspect `BindingResult#getSuppressedFields()` if a client attempts to send out-of-contract fields.

It also distinguishes **constructor binding**, **property binding**, `setDeclarativeBinding(true)`, JSON `@RequestBody`, validation, and authorization. The goal is not merely to block one specific payload, but to structure the code so that **even if a sensitive property is added to the entity in the future, it is not automatically exposed to clients**.

**Scope:** Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring MVC Servlet stack, Jakarta Validation. The security principles apply more broadly, though specific classes, exceptions, and binding pipelines in WebFlux or other frameworks must be checked separately.

## 2. What Is a Task-Specific DTO?

A **task-specific DTO** is a Java type describing **the data a specific action is permitted to accept**, rather than a full mirror of the database entity.

An account might support three tasks:

| Task | Input DTO | Fields caller may submit | Fields server must manage |
| --- | --- | --- | --- |
| Account registration | `CreateAccountForm` | `displayName`, `email`, `acceptedTerms` | `id`, `role`, `locked`, `ownerId` |
| Change contact info | `ChangeContactForm` | `email`, `phone`, `newsletter` | `id`, `role`, `locked`, `displayName` |
| Grant admin role | `ChangeRoleCommand` | `role` through an authorized admin workflow | Contact fields and other out-of-scope permissions |

These are three distinct contracts. **Do not reuse a single `AccountEntity` with all setters for all three**, relying on clients "not to send fields absent from the UI."

### 2.1. Input DTOs and entities serve different roles

- **Input DTO:** the HTTP data boundary, defining valid fields for a use case along with syntax/format constraints.
- **Domain entity:** business state and invariants; may hold properties that clients must never control.
- **Output DTO:** data allowed to be returned to the user, not necessarily identical to the input or entity.
- **Service command:** a validated/authorized business request; can be modeled separately to avoid coupling to HTTP APIs.

A safer flow:

```text
Untrusted HTTP request
      |
      v
Request mapping + task-specific DTO
      |
      v
Data binding: allowlist / constructor / conversion
      |
      v
Jakarta/Spring validation
      |
      v
Authentication + authorization + business checks
      |
      v
Explicit mapping of valid fields
      |
      v
Domain service / aggregate / database
      |
      v
Response DTO for caller
```

**Important:** DTOs and allowlists **do not replace authorization**. A field may be permitted in a DTO while the caller still **lacks permission to edit that specific account**. For example, a syntactically valid `email` does not mean anyone can change account 42's email.

### 2.2. Why is a single DTO with many nullable fields hard to keep safe?

An "all-purpose" DTO:

```java
public class AccountRequest {
    private String displayName;
    private String email;
    private String phone;
    private String role;
    private Boolean locked;
    private Long ownerId;
    // getters/setters...
}
```

If this type is reused across all endpoints, every endpoint must continually decide which fields are allowed and which are not. When a new property is added, multiple places may accidentally allow editing it or omit validation groups. Smaller task-specific DTOs typically provide:

- Clear responsibility during code review.
- Validation tailored to the specific action.
- Input structures that are easy to document in OpenAPI.
- Lower over-posting risk when the domain entity evolves.
- Less conditional logic like "if operation is CREATE ignore field X, if UPDATE ignore field Y."
- Easier negative testing against a concrete contract.

**Not every endpoint requires a unique class.** Two endpoints with genuinely identical input semantics can share a DTO. Split them when **the allowed field set or data interpretation differs**.

## 3. An Allowlist as an Additional Defense Layer for Property Binding

With `@ModelAttribute`, Spring typically uses `WebDataBinder` to assign request values to writable properties. You can restrict it with:

```java
@InitBinder("createAccount")
void initCreate(WebDataBinder binder) {
    binder.setAllowedFields(
            "displayName", "email", "acceptedTerms");
}
```

Effect: when the binder performs **property binding** for objectName `createAccount`, only property paths matching the allowed patterns are transferred onto the object. Other fields can be **suppressed** (excluded from binding) and recorded via `BindingResult#getSuppressedFields()`.

In Spring 6.x:

- `setAllowedFields("...")` is a **positive allowlist**: naming only the properties that are allowed.
- `setDisallowedFields("...")` is a **denylist**: listing forbidden fields. This is less safe because newly added fields on the class can be overlooked.
- `getSuppressedFields()` returns field names excluded during binding; **it does not mean `hasErrors()` automatically becomes true**.
- Allowlist patterns may include wildcards `*` per Spring's matching rules, so an overly broad pattern can unintentionally permit multiple nested properties.
- Matching of **allowed field patterns is case-sensitive** per Spring 6.x Javadoc; do not assume different casings of a field name are treated identically.
- `@InitBinder("createAccount")` scopes the initializer by **binder objectName**, not Java type, controller method name, or URL path.

This is a control at the **binding phase**, not a database permission check and not a JSON deserialization firewall.

### 3.1. Name the model attribute explicitly

```java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("createAccount")
                CreateAccountForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

Only when the binder is created for the name `createAccount` is the corresponding `@InitBinder("createAccount")` method selected by Spring. The Java variable name `form` does not replace objectName.

Do not rename `@ModelAttribute("createAccount")` to `@ModelAttribute("account")` without updating the initializer; the intended allowlist may silently stop applying.

### 3.2. Place BindingResult immediately after the bound argument

`BindingResult` or `Errors` must appear **immediately after** the command object it describes:

```java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("createAccount") CreateAccountForm form,
        BindingResult result,
        Model model) {
    if (result.hasErrors()) {
        return "form";
    }
    return "done";
}
```

With this signature, the controller can inspect validation/binding errors and `getSuppressedFields()`. If `Model model` is inserted between the form and `BindingResult`, Spring cannot associate the binding result per its convention.

**Remember:** suppressed fields are reported as a separate signal via `getSuppressedFields()`. Checking `result.hasErrors()` **is not enough** to detect that a client submitted disallowed properties.

## 4. How Does a Positive Allowlist Differ from a Denylist and Validation?

| Mechanism | Example | What question does it answer? | What does it NOT solve? |
| --- | --- | --- | --- |
| Task-specific DTO | `ChangeContactForm` lacks `role` | What data shape does the action accept? | Caller's permission on the resource |
| `setAllowedFields` | `"email","phone","newsletter"` | Which fields may be property-bound? | Jackson JSON mapping, constructor args, DB permissions |
| `setDisallowedFields` | `"role","locked"` | Which fields are denied in property binding? | Unknown or future sensitive fields |
| `@Valid` + `@NotBlank` | Email must have content | Does the value meet constraints? | Who is allowed to change the email? |
| `@Email` | String has email syntax | Is the input format valid? | Whether the email is verified or belongs to the caller |
| Authorization | Account owner or admin | Who may perform this action on this resource? | Email or phone format |
| Explicit mapping | `current.role()` preserved when changing email | Which domain properties actually change? | Permission violations if the service picks the wrong resource |
| DB constraints | unique email, FK, optimistic lock | Is the final data consistent? | Access control at the HTTP boundary |

A secure API requires the right layers **working together**. For example, `@NotNull` on `role` does not prevent a client from changing themselves to `ADMIN`; both `MEMBER` and `ADMIN` can satisfy the constraint. This is a matter of **authorization and field ownership**, not just Bean Validation.

### 4.1. Why is a positive allowlist better than "forbidding the role field"?

Suppose you write:

```java
binder.setDisallowedFields("role", "locked");
```

Later the entity adds `billingLimit`, `organizationId`, or `verified`. The old denylist knows nothing about those new fields. An allowlist permitting only `email`/`phone` still keeps the new fields closed. Therefore, when property-binding untrusted data, **prefer an allowlist**.

If a denylist is still used for compatibility reasons, combine it with a positive DTO boundary and tests for new properties. Never treat a denylist as the sole defense.

### 4.2. Why is an overly broad allowlist also unsafe?

For example:

```java
binder.setAllowedFields("*");
```

From a security standpoint, this declaration practically defeats the allowlist: every supported property path can match. Patterns like `"settings*"` or `"addresses*"` also require careful inspection of nested properties.

If editing nested fields is required:

```java
binder.setAllowedFields(
        "displayName",
        "address.city",
        "address.postcode"
);
```

This is a **fragment** for a DTO that actually has an `address` property; it is not part of the runnable project below. This list is narrower than `"address.*"` because it permits only those two attributes.

**Do not "allowlist a parent object" and assume all of its nested properties are safe to expose.** Inspect property path semantics, patterns, and generated setters; also test malicious nested fields.

## 5. Constructor Binding, Property Binding, and declarativeBinding

Per the Spring MVC 6.x documentation, `@ModelAttribute` can use **constructor binding** and **setter/property binding**. Both paths must be distinguished when evaluating an allowlist.

### 5.1. Property binding

With a JavaBean:

```java
public class ContactForm {
    private String email;
    private String phone;

    public ContactForm() {}

    public void setEmail(String email) {
        this.email = email;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }

    // getters...
}
```

Spring can instantiate the object via the no-arg constructor and assign values through setters. With `setAllowedFields("email")`, `phone` in the request is suppressed during the property-binding phase.

### 5.2. Constructor binding and immutable DTOs

With a record:

```java
public record ChangeEmailRequest(
        @NotBlank @Email String email) {
}
```

This is a fragment requiring imports for Jakarta constraints. When an appropriate record is used as `@ModelAttribute`, Spring can use constructor binding to construct the object from input. The record **has no `role`/`locked` setters** because those fields are absent from both the constructor and the type.

Benefits: the input surface is easy to inspect; immutability prevents post-construction field mutation. However:

- **Constructor parameters are still untrusted data** and require validation.
- **`setAllowedFields(...)` primarily governs property binding**, not filtering every constructor parameter.
- If your constructor includes `role` or `ownerId`, using an immutable record **does not make those values safe**. The DTO must *declare only the parameters the request is allowed to supply*.
- When a record/constructor parameter needs an HTTP parameter name different from the Java name, Spring supports `@BindParam` per the docs and corresponding mapping tests.
- A DTO whose constructor accepts every entity field **is not a task-specific DTO merely because it is a record**.

### 5.3. setDeclarativeBinding(true)

Spring provides declarative binding mode:

```java
@ControllerAdvice
public class BinderPolicy {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

This is a **global configuration fragment**, not part of the runnable project below. When `declarativeBinding` is enabled, Spring continues to apply constructor binding, while setter/property binding is **applied only when `allowedFields` are explicitly declared**.

This is useful if a system wants a safer default for property binding. However, it must not be misunderstood as:

- "Disables all data binding" — constructor binding still runs.
- "Makes all constructor inputs automatically safe" — you must still design constructor inputs tightly.
- "Automatically blocks JSON properties" — Jackson has its own pipeline.
- "Eliminates the need for tests" — another `@InitBinder` could still configure `allowedFields` for a form's binder.

When applying globally, run regression tests on legacy forms relying on setters, marker/default fields, nested collections, and constructor-bound handlers. A global change can broadly affect form behavior.

### 5.4. Which approach should you choose?

| Case | Recommended choice |
| --- | --- |
| New API command, few fields, no mutation needed | Record/immutable task DTO, constructor binding or Jackson DTO |
| HTML form currently using setters | Dedicated JavaBean input DTO + explicit `setAllowedFields` |
| System currently binding domain entities directly | Refactor to dedicated DTOs; enforce a tight allowlist during transition |
| Many legacy forms hard to refactor at once | Consider declarative binding and incrementally add allowlists/tests |
| JSON REST using `@RequestBody` | Dedicated DTO/record, controlled Jackson mapping, validation, authorization |
| Field editable only by admins | Dedicated admin endpoint/command + authorization; never just UI show/hide |

## 6. Java 17 Example: Two Tasks, Two DTOs, Two Allowlists

### 6.1. Purpose and observable behavior

A minimal Spring Boot MVC project has two endpoints:

- **`POST /accounts`**: creates an account from `CreateAccountForm` with `displayName`, `email`, and `acceptedTerms`.
- **`POST /accounts/{accountId}/contact`**: updates contact info using `ChangeContactForm` with `email`, `phone`, and `newsletter`.

In the domain, an account also has `id` and `role`. These two fields are **always server-managed** and never appear on the input DTOs. The server assigns `role="MEMBER"` on account creation and preserves the role when changing contact info.

At the same time:

- `@InitBinder("createAccount")` allows property binding only for account creation fields.
- `@InitBinder("contactChange")` allows property binding only for contact change fields.
- `BindingResult#getSuppressedFields()` detects requests attempting to inject `role`, `id`, or `displayName` on endpoints where they are disallowed.
- `@Valid` enforces `@NotBlank`, `@Email`, `@AssertTrue`, `@Pattern`, and `@NotNull`.
- MockMvc sends real form-urlencoded requests through the MVC infrastructure, verifying both happy paths and malicious/invalid payloads.

This is an **in-memory example to observe binding and policy**, not an authorization, persistence, or email-verification system. In production, replace the in-memory map with a repository and add authentication/authorization, transactions, unique constraints, and auditing.

### 6.2. Project structure

```text
task-dto-allowlist/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── TaskDtoApplication.java
    │   ├── CreateAccountForm.java
    │   ├── ChangeContactForm.java
    │   ├── AccountService.java
    │   └── AccountController.java
    └── test/java/demo/
        └── AccountBindingSecurityTest.java
```

### 6.3. pom.xml

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
    <artifactId>task-dto-allowlist</artifactId>
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

The Spring Boot parent manages compatible Spring Framework, Jackson, and Hibernate Validator versions for the starters. `spring-boot-starter-validation` is declared explicitly because `@Valid` needs a real Jakarta Validation provider to enforce constraints.

### 6.4. src/main/java/demo/TaskDtoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaskDtoApplication.class, args);
    }
}
```

The main class and other types share the `demo` package so component scanning detects the controller and service.

### 6.5. src/main/java/demo/CreateAccountForm.java

```java
package demo;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class CreateAccountForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @AssertTrue
    private Boolean acceptedTerms;

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

    public Boolean getAcceptedTerms() {
        return acceptedTerms;
    }

    public void setAcceptedTerms(Boolean acceptedTerms) {
        this.acceptedTerms = acceptedTerms;
    }
}
```

Design notes:

- `displayName` and `email` must be non-blank. `@Email` validates format per the provider; it does not prove the email actually exists or is verified.
- `acceptedTerms` uses `Boolean` with `@NotNull` and `@AssertTrue` to distinguish a missing value from `false`. Terms acceptance typically also requires recording **the terms version and consent timestamp** in the service/DB; this demo omits that.
- There are no setters for `role`, `id`, `locked`, or `ownerId`. This is a **DTO structural decision**, not merely removing fields from an HTML form.

If the domain later adds `creditLimit` or `securityFlags`, `CreateAccountForm` will not automatically expose them.

### 6.6. src/main/java/demo/ChangeContactForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class ChangeContactForm {

    @NotBlank
    @Email
    private String email;

    // Can be left blank by omitting phone;
    // if a value is provided, it must match the demo pattern.
    @Pattern(regexp = "\\+?[0-9]{8,15}")
    private String phone;

    @NotNull
    private Boolean newsletter;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPhone() {
        return phone;
    }

    public void setPhone(String phone) {
        this.phone = phone;
    }

    public Boolean getNewsletter() {
        return newsletter;
    }

    public void setNewsletter(Boolean newsletter) {
        this.newsletter = newsletter;
    }
}
```

This DTO **omits `displayName`, `role`, and `id`** because the task only updates contact information and newsletter preference.

To keep semantics clear in this example, this endpoint is **a contact-replacement command**: `email` and `newsletter` are required, and an absent `phone` sets it to `null` (clears the phone number). It is **not PATCH partial-update semantics**. If PATCH is desired, you must separately distinguish "field absent," "field explicitly null," and "field with value" to avoid unintended overwrites.

`@Pattern` permits null per standard Bean Validation rules, which fits an optional phone design. If an empty string should also mean "no phone," add appropriate normalization/validation rather than assuming `@Pattern` treats all empty strings as null.

### 6.7. src/main/java/demo/AccountService.java

```java
package demo;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class AccountService {

    public record Account(
            long id,
            String displayName,
            String email,
            String phone,
            boolean newsletter,
            String role) {
    }

    private final ConcurrentMap<Long, Account> accounts =
            new ConcurrentHashMap<>();

    private final AtomicLong nextId = new AtomicLong(100);

    public AccountService() {
        // Sample data for testing the change-contact command.
        accounts.put(42L, new Account(
                42L,
                "Lan",
                "lan@example.org",
                "+84911111111",
                false,
                "MEMBER"
        ));
    }

    public Account create(CreateAccountForm form) {
        long id = nextId.incrementAndGet();

        // id and role are determined by the server; never taken from the request.
        Account account = new Account(
                id,
                form.getDisplayName(),
                form.getEmail(),
                null,
                false,
                "MEMBER"
        );

        accounts.put(id, account);
        return account;
    }

    public Optional<Account> changeContact(
            long accountId, ChangeContactForm form) {

        Account updated = accounts.computeIfPresent(
                accountId,
                (id, current) -> new Account(
                        current.id(),
                        current.displayName(),
                        form.getEmail(),
                        form.getPhone(),
                        Boolean.TRUE.equals(form.getNewsletter()),
                        current.role()
                )
        );

        return Optional.ofNullable(updated);
    }
}
```

**Core security points:**

- Account creation: copies only `displayName` and `email` from `CreateAccountForm`. ID comes from the server, and role is `MEMBER`.
- Contact change: preserves `current.id()`, `current.displayName()`, and `current.role()`; copies only the fields belonging to the command.
- Does not invoke reflection or a loosely configured automatic mapper to copy the entire request object onto an entity.
- Does not accept a `Map<String,Object>` from HTTP as a list of properties to mutate the domain.
- Fixture `42L` exists solely to test updates independently; it is not a security ID or a real user account.

**Illustrative limitations:** this `AccountService` **lacks authentication, authorization, transactions, unique email checks, and persistence**. Production must verify that the principal is authorized to act on `accountId` before updating. `ConcurrentHashMap` and `AtomicLong` merely provide a runnable Java example, not a substitute for a database and business concurrency control.

### 6.8. src/main/java/demo/AccountController.java

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    private final AccountService accounts;

    public AccountController(AccountService accounts) {
        this.accounts = accounts;
    }

    @InitBinder("createAccount")
    public void initCreateAccount(WebDataBinder binder) {
        binder.setAllowedFields(
                "displayName", "email", "acceptedTerms");
    }

    @InitBinder("contactChange")
    public void initContactChange(WebDataBinder binder) {
        binder.setAllowedFields(
                "email", "phone", "newsletter");
    }

    @PostMapping(
            path = "/accounts",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("createAccount")
                    CreateAccountForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            return rejectSuppressed(result);
        }
        if (result.hasErrors()) {
            return rejectInvalid(result);
        }

        AccountService.Account created = accounts.create(form);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

    @PostMapping(
            path = "/accounts/{accountId}/contact",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> changeContact(
            @PathVariable long accountId,
            @Valid @ModelAttribute("contactChange")
                    ChangeContactForm form,
            BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            return rejectSuppressed(result);
        }
        if (result.hasErrors()) {
            return rejectInvalid(result);
        }

        // Production: authorization by principal and accountId
        // must be enforced before updating the resource.
        var changed = accounts.changeContact(accountId, form);
        if (changed.isEmpty()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(changed.get());
    }

    private static ResponseEntity<?> rejectSuppressed(
            BindingResult result) {

        List<String> fields = Arrays.stream(
                result.getSuppressedFields())
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(Map.of(
                "code", "DISALLOWED_FIELDS",
                "fields", fields
        ));
    }

    private static ResponseEntity<?> rejectInvalid(
            BindingResult result) {

        List<String> fields = result.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        List<String> bindingFailures = result.getFieldErrors()
                .stream()
                .filter(FieldError::isBindingFailure)
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(Map.of(
                "code", "INPUT_INVALID",
                "fields", fields,
                "bindingFailures", bindingFailures
        ));
    }
}
```

Rationale for this implementation:

1. **Two named `@InitBinder` methods**: allowlist selection is keyed by `@ModelAttribute("createAccount")` and `@ModelAttribute("contactChange")`, not merely by Java class equality or difference.
2. **Input constrained by DTOs**: the controller neither accepts `AccountService.Account` nor an entity with a `role` setter.
3. **Allowlist acts as defense-in-depth**: even if a client sends `role` or `id` in form/query parameters, the binder detects suppressed fields and the controller returns 400 rather than silently continuing.
4. **`BindingResult` placed right after the form object**: binding/validation errors are captured in the controller instead of turning into 500 errors.
5. **Check suppressed fields before `hasErrors()`**: disallowed fields do not necessarily create a `FieldError`; the `DISALLOWED_FIELDS` branch keeps error classification clear.
6. **Distinguish `isBindingFailure()`**: when `newsletter=maybe` cannot be converted to `Boolean`, the offending field is flagged as a type conversion error.
7. **No mass update**: the service uses explicit mapping and leaves `role` untouched.
8. **Do not confuse input validation with authorization**: the example does not resolve the caller's actual permissions; production must add that layer.

**Response note:** the demo returns the domain record so learners can observe that `role` stays unchanged. Production should use an **output DTO** to control which fields are returned per viewer permissions; never serialize every entity field by default, especially PII or secrets.

### 6.9. src/test/java/demo/AccountBindingSecurityTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountBindingSecurityTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder createRequest(
            String displayName, String email, String acceptedTerms) {

        return post("/accounts")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", displayName)
                .param("email", email)
                .param("acceptedTerms", acceptedTerms);
    }

    private MockHttpServletRequestBuilder contactRequest(
            String email, String newsletter) {

        return post("/accounts/42/contact")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", email)
                .param("phone", "+84912345678")
                .param("newsletter", newsletter);
    }

    @Test
    void creationAssignsRoleOnServer() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.displayName").value("Mai"))
                .andExpect(jsonPath("$.role").value("MEMBER"));
    }

    @Test
    void creationRejectsInjectedRole() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void creationRejectsClientChosenId() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "true")
                        .param("id", "999"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("id")));
    }

    @Test
    void invalidEmailDoesNotReachService() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "not-an-email", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields", hasItem("email")));
    }

    @Test
    void falseAcceptedTermsFailsValidation() throws Exception {
        mvc.perform(createRequest(
                        "Mai", "mai@example.org", "false"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("acceptedTerms")));
    }

    @Test
    void contactChangePreservesIdentityAndRole()
            throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.email")
                        .value("new@example.org"))
                .andExpect(jsonPath("$.role").value("MEMBER"))
                .andExpect(jsonPath("$.newsletter").value(true));
    }

    @Test
    void contactChangeRejectsInjectedRole() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields", hasItem("role")));
    }

    @Test
    void contactChangeRejectsDisplayName() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "true")
                        .param("displayName", "Attacker"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.fields",
                        hasItem("displayName")));
    }

    @Test
    void contactChangeRejectsInvalidPhone() throws Exception {
        mvc.perform(post("/accounts/42/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org")
                        .param("newsletter", "true")
                        .param("phone", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields", hasItem("phone")));
    }

    @Test
    void wrongBooleanIsBindingFailure() throws Exception {
        mvc.perform(contactRequest(
                        "new@example.org", "maybe"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.bindingFailures",
                        hasItem("newsletter")));
    }

    @Test
    void missingNewsletterIsNotNullViolation()
            throws Exception {
        mvc.perform(post("/accounts/42/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("newsletter")));
    }

    @Test
    void nonexistentResourceIsNotFound() throws Exception {
        mvc.perform(post("/accounts/999999/contact")
                        .contentType(
                            MediaType.APPLICATION_FORM_URLENCODED)
                        .param("email", "new@example.org")
                        .param("phone", "+84912345678")
                        .param("newsletter", "false"))
                .andExpect(status().isNotFound());
    }
}
```

**The 12-case test suite** covers:

- Valid creation: server assigns role.
- Sending `role=ADMIN` on creation: suppressed.
- Sending `id=999` on creation: suppressed.
- Malformed email on creation: rejected.
- Terms not accepted: violates `@AssertTrue`.
- Valid contact update: ID, displayName, and role are preserved.
- Attempting to change role via contact task: suppressed.
- Attempting to change displayName via contact task: suppressed.
- Malformed phone: violates `@Pattern`.
- Invalid boolean value: type conversion failure.
- Missing `newsletter`: violates `@NotNull`.
- Resource absent from demo store: 404.

**Test independence:** fixture `id=42` has `displayName="Lan"` and `role="MEMBER"`. Contact-change tests may update email/phone on the fixture within the same context, yet no test depends on email ordering from another test; assertions on `role`/`displayName` remain invariant in the service.

### 6.10. Running and checking output

In the project directory, using JDK 17+ and Maven:

```bash
mvn -q clean test
```

**Expected:** 12 tests pass and Maven exits with code 0 when dependencies are cached and the environment matches. No fabricated Maven stdout is shown as observed output because log levels and Surefire/JUnit versions can vary. The assertions verify HTTP status, JSON response codes, field names, and post-mapping domain values.

Start the server:

```bash
mvn spring-boot:run
```

Valid account creation request:

```bash
curl -i -X POST 'http://localhost:8080/accounts' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Mai' \
  --data-urlencode 'email=mai@example.org' \
  --data-urlencode 'acceptedTerms=true'
```

HTTP **201 Created** with illustrative body (new ID generated by the server; example below assumes a freshly started sequence on its first creation):

```json
{
  "id": 101,
  "displayName": "Mai",
  "email": "mai@example.org",
  "phone": null,
  "newsletter": false,
  "role": "MEMBER"
}
```

Attempted role escalation request:

```bash
curl -i -X POST 'http://localhost:8080/accounts' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Mai' \
  --data-urlencode 'email=mai@example.org' \
  --data-urlencode 'acceptedTerms=true' \
  --data-urlencode 'role=ADMIN'
```

HTTP **400 Bad Request** with:

```json
{
  "code": "DISALLOWED_FIELDS",
  "fields": ["role"]
}
```

Contact update request for the fixture:

```bash
curl -i -X POST 'http://localhost:8080/accounts/42/contact' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=contact@example.org' \
  --data-urlencode 'phone=+84912345678' \
  --data-urlencode 'newsletter=true'
```

HTTP **200 OK**, body contains `displayName="Lan"`, `role="MEMBER"`, `email="contact@example.org"`, and `newsletter=true`. Adding `displayName=Attacker` or `role=ADMIN` causes the controller to return `DISALLOWED_FIELDS`.

**Note:** because the example uses a mutable in-memory store and generated IDs, do not assert a fixed new ID across arbitrary environments/test orders. Fix only fixture ID 42 for tests requiring an existing account.

## 7. Limits of setAllowedFields: Not a Jackson JSON Filter

This is a critical distinction.

### 7.1. Form / @ModelAttribute

The runnable example uses:

```java
@Valid @ModelAttribute("createAccount") CreateAccountForm form
```

For `application/x-www-form-urlencoded` requests (or request parameters from sources supported by `@ModelAttribute`), Spring uses the binder for **property binding**. `setAllowedFields("displayName", "email", "acceptedTerms")` governs property names bound via that mechanism.

### 7.2. JSON / @RequestBody

Another endpoint:

```java
@PostMapping("/api/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountJson request) {
    // ...
    return ResponseEntity.ok().build();
}
```

This is a **fragment** requiring a `CreateAccountJson` definition; it is not part of the Maven runnable project above. Jackson (or another HTTP message converter) deserializes JSON into the DTO **before** the validation step. `WebDataBinder#setAllowedFields` **does not filter Jackson JSON properties** the way it filters setter/property binding for `@ModelAttribute`.

For JSON, a safe design typically uses:

- **Task-specific records/classes** containing only the fields the request needs.
- Controlled Jackson property names and deserialization behavior.
- If the API requires **rejecting unknown fields** instead of ignoring them, explicit strict Jackson configuration tested end-to-end.
- Never using a JPA entity as `@RequestBody` if it has sensitive fields.
- Service copying only the fields permitted by the command.
- Authentication/authorization independent of validation.

Example JSON input DTO:

```java
public record CreateAccountJson(
        @NotBlank String displayName,
        @NotBlank @Email String email,
        @NotNull @AssertTrue Boolean acceptedTerms) {
}
```

This fragment requires Jakarta constraint imports. It has neither `role` nor `id`. Still, **do not assume unknown JSON fields are rejected by default**: Jackson/Boot have specific settings for unknown properties and may ignore them by default. What matters is that **unknown fields must never affect the domain**; returning 400 on unknown properties is **a separate contract** that must be configured and tested.

### 7.3. Do @JsonIgnore and @JsonProperty(access=...) replace DTOs?

Jackson annotations can control serialization/deserialization of individual properties, such as marking fields read-only or ignored. They are useful, yet binding **an entire entity** with scattered annotations increases risk when new fields appear or serialization rules change.

Task-specific DTOs are easier to review: fields outside the input contract simply do not exist on the type. Jackson restrictions/strict mode can add defense-in-depth without necessarily replacing the DTO design boundary.

## 8. Scoped @InitBinder and a Multi-Task Controller

In the demo:

```java
@InitBinder("createAccount")
void createBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "displayName", "email", "acceptedTerms");
}

@InitBinder("contactChange")
void contactBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "email", "phone", "newsletter");
}
```

These two methods are **abbreviated fragments** of the runnable controller. If an unnamed `@InitBinder` is used:

```java
@InitBinder
void all(WebDataBinder binder) {
    binder.setAllowedFields("email");
}
```

that initializer can apply broadly across binders in the controller; such a configuration could prevent the account creation form from binding `displayName` or `acceptedTerms`.

**Avoid having multiple initializers call `setAllowedFields` on the same binder** without understanding ordering and "who owns the allowlist." If both a global `@ControllerAdvice` and a local controller call `setAllowedFields(...)`, the last setter call can overwrite the earlier list; do not assume Spring intersects the two allowlists automatically.

### 8.1. Sharing a policy across multiple controllers

Shared configuration can live in `@ControllerAdvice`, provided it is scoped:

```java
@ControllerAdvice(assignableTypes = AccountController.class)
public class AccountBinderAdvice {

    @InitBinder("contactChange")
    void restrict(WebDataBinder binder) {
        binder.setAllowedFields("email", "phone", "newsletter");
    }
}
```

This is an **alternative organization fragment**, omitted from the runnable demo to avoid duplicating the local `@InitBinder`. `assignableTypes` limits which controllers receive the advice; `@InitBinder("contactChange")` restricts the binder to matching `objectName`.

When moving policy from local to global, adjust tests and avoid duplication. Unscoped advice can hit unrelated endpoints that happen to share a model attribute name with different business semantics, causing unintended side effects.

### 8.2. Multiple tasks sharing one Java class can still have distinct policies

When two tasks genuinely share a DTO type yet need different allowlists, two model attribute names can be used:

```java
@ModelAttribute("publicProfile") ProfileForm publicProfile
@ModelAttribute("privateProfile") ProfileForm privateProfile
```

with binders scoped to each name. However, **if the allowed field sets genuinely differ**, consider creating **two task-specific DTOs**; that is easier to review than keeping one type with excessive writable properties and relying solely on binder names.

## 9. Allowed Field Patterns, Nested Objects, Lists, and Maps

`DataBinder#setAllowedFields(...)` accepts **property paths or patterns**, not just top-level field names. Spring documentation illustrates examples such as:

- `"address"`: matches the `address` property.
- `"person.address.city"`: nested property.
- `"addresses[0].city"`: `city` field of the first list/array element.
- `"map[key]"`: specific entry in a Map.
- `"map*"`: wildcard for entries starting with the corresponding map prefix.

Yet **expressive syntax does not mean you should loosen the allowlist**. For sensitive domains, permit only property paths that actually belong to the task.

### 9.1. List of objects

Fragment example with a DTO holding `List<AddressForm> addresses`:

```java
binder.setAllowedFields(
        "addresses[*].city",
        "addresses[*].postcode"
);
```

Spring's `*` wildcard can match indices inside brackets. Test actual property names, cap element counts, and prevent clients from editing `addresses[0].id` or `addresses[0].ownerId` if the endpoint lacks that authority.

Do not write `"addresses*"` when only `city`/`postcode` are needed, as it can match other nested properties as well.

### 9.2. Map keys

With dynamic Map keys:

```java
binder.setAllowedFields(
        "preferences[news]",
        "preferences[offers]"
);
```

This is a fragment. It expresses a finite set of keys. If clients are allowed to edit arbitrary keys, add **key validation**, maximum size, key name checks, value constraints, and contextual authorization; a `"preferences*"` pattern does not replace those checks.

### 9.3. Constructor arguments are a different case

When using record/constructor binding, the request can supply parameters matching constructor arguments. `setAllowedFields` **is not a general allowlist mechanism for constructor arguments**. If a record holds `List<@Valid LineItem> items`, the record design plus constraints and constructor binding determine the accepted shape. Avoid defining a constructor containing `ownerId`, `role`, and `price` and expecting property-binding `allowedFields` to neutralize them.

### 9.4. Protecting collection size and auto-grow

A client may send huge indexed parameters such as `items[999999].name` to stress the binder or collections. Spring provides `DataBinder#setAutoGrowCollectionLimit(...)`, yet you should also configure appropriate limits on request parameter counts, body size, depth, and business-level max item counts.

Do not focus solely on field ownership while overlooking **resource exhaustion** when binding large lists or Maps.

## 10. When to Choose @ModelAttribute(binding=false)?

If a controller needs to **read** a domain object for reference without **binding the request onto it**, you can use:

```java
@ModelAttribute(binding = false) AccountEntity existingAccount
```

This is a fragment; `AccountEntity` must already exist in the model and the controller needs logic to fetch the account by ID. `binding=false` disables request data binding for that attribute at that parameter position.

Architectural example:

```java
@PostMapping("/accounts/{id}/contact")
public String save(
        @Valid @ModelAttribute("contactChange") ChangeContactForm input,
        BindingResult errors,
        @ModelAttribute(binding = false) AccountEntity existing) {
    // Only update existing through the service after authorization checks.
    return "done";
}
```

This is a **fragment**, not a runnable endpoint in the demo. `binding=false` neither loads the entity nor checks permissions on its own; proper model population and service checks are still required. Also prevent clients from replacing the DB-loaded entity via another binding path.

## 11. Validation Differs from Authorization, and Mapping Is Only Safe in the Right Place

A common mistake is believing `@Valid` guarantees a safe update. In reality:

- `@NotBlank` checks for a non-empty string.
- `@Email` checks email-like syntax.
- `@Min` checks a lower numeric bound.
- `@AssertTrue` checks a Boolean condition.
- **None of these annotations determines whether user X is allowed to change account Y's email.**

Authorization must verify at least:

1. **Actor:** is the caller authenticated, and with what roles/scopes?
2. **Action:** create, change contact, change role, lock account, delete account?
3. **Resource:** does the account belong to the caller or their administrative scope?
4. **Allowed transition:** does the current state allow this operation?
5. **Business invariants:** verified email, unique email, lock status, or approvals?

A production service might have a signature like:

```java
public AccountView changeContact(
        AuthenticatedActor actor,
        long accountId,
        ChangeContactCommand command) {

    Account account = repository.findById(accountId)
            .orElseThrow(NotFoundException::new);

    authorization.requireCanEditContact(actor, account);

    account.setEmail(command.email());
    account.setPhone(command.phone());
    account.setNewsletter(command.newsletter());

    repository.save(account);
    return AccountView.from(account);
}
```

This is an **architectural fragment** whose classes/services are undefined; do not treat it as runnable code in the Maven demo. The point is that authorization sits at the service/resource boundary, followed by **updating only the fields permitted by the command**. Never call an unconstrained `BeanUtils.copyProperties(request, account)` when `account` holds sensitive fields.

### Preventing IDOR/BOLA when using accountId in the URL

Even an endpoint whose input DTO omits `role` can be abused if the caller changes `/accounts/42/contact` to `/accounts/43/contact` and the server updates account 43 without ownership checks. That is **Broken Object Level Authorization (BOLA)**, not mass assignment. Both flaws frequently coexist in CRUD systems and must be mitigated independently.

### Concurrency checks

If two requests update contact info concurrently, use transactions/optimistic locking or documented concurrent-write rules as required by the business domain. The demo's `ConcurrentHashMap.computeIfPresent` merely avoids basic unsynchronized map updates; it **does not replace** database transactions or business version conflict handling.

## 12. "Field Absent from DTO" Differs from "Suppressed Field"

A task may choose to:

- **Ignore unknown input:** if the DTO lacks `role` and the framework is configured to ignore unknown fields, the request proceeds without using `role`.
- **Reject unknown input:** if the client sends out-of-contract fields, return 400.
- **Audit unknown input:** block or record an event with redacted details, without logging sensitive values.

In the demo, `setAllowedFields` causes an unauthorized field name (such as `role`) to be suppressed during the property-binding phase. The controller inspects `getSuppressedFields()` and returns **`DISALLOWED_FIELDS`**.

However, **this policy is only demonstrated for the `@ModelAttribute` + property-binding pipeline used here**. With `@RequestBody`, Jackson has different rules for unknown properties; with constructor binding, `allowedFields` does not filter constructor arguments in the same way.

### Why not rely solely on getSuppressedFields()?

An application might ignore `getSuppressedFields()` and still remain safe if the DTO has no sensitive properties and service mapping selects only permitted fields; however, it could silently **accept out-of-contract requests** without error, misleading clients.

If the API must explicitly report "disallowed fields," enforce a clear contract and test extra-field rejection. If the API intentionally ignores unknown fields for client compatibility, document that contract and still guarantee they cannot alter domain state.

**Never infer that zero suppressed fields means authorization passed.** Having no extra input fields says nothing about whether the actor may modify the resource.

### Should you use a raw map for partial updates?

For example:

```java
@PostMapping("/accounts/patch")
public void patch(@RequestBody Map<String, Object> values) {
    // ...
}
```

This is an anti-pattern fragment. If the service loops over `values.entrySet()` and uses reflection to invoke entity setters, the boundary of permitted fields blurs and easily leads to over-posting.

If using JSON Merge Patch or JSON Patch, enforce a **schema, allowed operations/paths list, validation, authorization**, nested path controls, and explicit null semantics. Never assume every property path in a patch body is permitted just because it is valid JSON.

## 13. Testing for Mass Assignment Systematically

A solid test suite must include **negative cases that deliberately send unauthorized fields**. Testing only valid forms with the three intended fields does not prove the allowlist actually works.

### Task-based test matrix

| Task | Extra payload | Expected security outcome |
| --- | --- | --- |
| Create account | `role=ADMIN` | Rejected or ignored per contract; server role stays MEMBER |
| Create account | `id=999` | Client does not choose the ID |
| Create account | `locked=false` | Client does not control lock status |
| Change contact | `displayName=Attacker` | Display name is not modified |
| Change contact | `role=ADMIN` | Role is not changed |
| Change contact | `ownerId=1` | Ownership is not transferred |
| Change contact | `email=invalid` | Email constraint fails |
| Change contact | `newsletter=maybe` | Boolean binding failure |
| Change contact | Missing `newsletter` | Validation detects missing value |
| Change contact | Another user's ID | Authorization rejects before writing |
| Change contact | Nonexistent account | 404 or contract-defined response |
| Admin change role | Non-admin user | 403 (or matching policy response) |
| Nested form | `addresses[0].ownerId=...` | Nested owner field is not mutated |
| JSON command | Extra property `role` | Does not affect domain; rejected/ignored per contract |

**Clear distinction:** in the demo, testing another account's ID, admin permissions, and nested collections are **production test plans**, not implemented test code. The runnable demo covers the 12 input/allowlist cases listed in section 6.

### Preferred assertion styles

- Assert HTTP status and machine-readable error code.
- Assert suppressed fields by name without echoing raw values.
- Assert **post-service-mapping state**: role and ID remain unchanged.
- Assert command DTOs lack out-of-contract setters/properties (via review/API schema).
- Assert validation flags the right fields and classifies type conversion errors.
- Assert unauthorized users cannot affect other resources (integration/security tests).
- Assert adding new properties to the entity **does not expand the input DTO**.

### Do not test by invoking the controller method directly

If you only write:

```java
AccountController controller = new AccountController(service);
// controller.create(new CreateAccountForm(), ...);
```

you have to construct `BindingResult` manually and bypass MVC argument resolution/binding from HTTP requests. Such a unit test proves neither that `@InitBinder` was selected nor that `allowedFields` filtered properties. Use `MockMvc` with a real controller and MVC context for binder assertions.

## 14. Common Mistakes When Designing Task-Specific DTOs

### 14.1. Naming a DTO "AccountDto" while including the entire entity

A DTO is secure by **its field set and semantics**, not by the `Dto` suffix. If `AccountDto` still carries `role`, `ownerId`, `locked`, `accountBalance`, and all setters, over-posting risk persists.

### 14.2. Using a display DTO as an update DTO

An API response may need to return `role` and `createdAt` for UI display. Reusing that response DTO as an update request is a mistake: adding a read field for the UI can turn into a writable server field if mapping is unchecked.

### 14.3. Sharing one DTO between regular users and administrators

An admin may be authorized to change roles, whereas a regular user is not. Separate `ChangeRoleCommand` from `ChangeContactForm` and authorize each action. Never rely solely on hiding the role button in the UI.

### 14.4. Putting @NotNull on role and thinking role is protected

`@NotNull` only requires a non-null value. It does not ensure the server set the role. Protect `role` by **excluding it from task input DTOs** and never updating it in services outside authorized workflows.

### 14.5. Relying on disallowedFields as the only defense

An existing denylist can miss new sensitive fields. Prefer task DTOs + `allowedFields` when using property binding. If a denylist is needed for a specific reason, test new fields and audit changes to the domain model.

### 14.6. Using the wrong objectName on @InitBinder

`@InitBinder("contactChange")` does not automatically apply to a binder named `contactForm`. Name `@ModelAttribute` explicitly and test a request with an extra field to prove the init-binder actually ran.

### 14.7. Configuring allowedFields without checking suppressed fields

The binder can drop unknown fields without producing a `FieldError`. If the contract requires rejecting extra fields, check `BindingResult#getSuppressedFields()` explicitly rather than relying only on `hasErrors()`.

### 14.8. Using @RequestBody JSON and expecting setAllowedFields to apply

Jackson deserializes JSON before Bean Validation; property-binder `allowedFields` is not a JSON key allowlist. Use a dedicated input DTO + Jackson strictness where needed and test the JSON pipeline directly.

### 14.9. Using a record whose constructor includes sensitive fields

An immutable object is not automatically safe when its constructor accepts `role`, `locked`, or `ownerId` from untrusted input. Task DTOs must accept only permitted fields.

### 14.10. Allowing an entire nested object with a wildcard

`setAllowedFields("profile*")` can match unintended properties. Use narrow patterns and test malicious nested fields, especially when the domain model has deep object graphs.

### 14.11. Auto-mapping every property from request to entity

A helper like `BeanUtils.copyProperties(input, entity)` without explicit exclusions/allowlists can expose new fields for mutation as DTOs/entities evolve. Explicit mapping in the service is clearest for sensitive updates.

### 14.12. Trusting validation while forgetting resource ownership

A DTO may have a safe field list while still letting a user modify another account if ownership is unchecked. Enforce object-level authorization in the service rather than trusting client-supplied IDs.

### 14.13. Treating null and absent identically in PATCH

An update command might mean "omitted phone = keep existing" or "omitted phone = clear." Mixing the two semantics risks data loss. Separate full-replacement and partial-update commands, with clear contracts for absent/null/value.

### 14.14. Testing only the UI

Hiding the `role` field in the frontend does not stop requests from sending it. Write HTTP tests sending extra parameters via MockMvc/curl or security tests. Attackers are not constrained by the form you render.

## 15. Dedicated DTOs for PATCH, Commands, and Admin Actions

### 15.1. Changing email differs from changing role

An email-change command might look like:

```java
public record ChangeEmailCommand(
        @NotBlank @Email String newEmail) {
}
```

An administrative command:

```java
public record ChangeRoleCommand(
        @NotNull AccountRole newRole) {
}
```

These are **fragments**; `AccountRole` is a domain enum to be declared in a real application. They carry different semantics: changing roles requires admin privileges, auditing, and possibly re-authentication; never merge them merely because both touch `AccountEntity`.

### 15.2. When partial updates must distinguish absent, null, and value

A JSON PATCH-like request might contain:

```json
{"phone": null}
```

or:

```json
{}
```

These two payloads can mean **clear the phone number** versus **leave the phone number unchanged**. Deserializing both into a DTO with only `String phone` turns both into `null`, losing whether the client sent the field.

Solutions depending on the contract:

- Use HTTP PUT/full replacement with all required fields mandatory.
- Use JSON Merge Patch (RFC 7396) and handle explicit nulls per its semantics.
- Use JSON Patch (RFC 6902) with authorized operations/paths.
- Use a command with a clearly configured presence/marker wrapper (typically requiring serializer support).
- Use a dedicated endpoint `POST /accounts/{id}/clear-phone` instead of a generic patch when appropriate for the domain.

Do not try to solve partial-update semantics with `@NotNull` or `setAllowedFields` alone; it is a question of input representation and operation contract.

### 15.3. DTOs with nested lists/maps

If a task edits a list of addresses, the DTO can hold `List<UpdateAddressItem>`, provided that:

- Each item contains only updatable fields.
- Each item ID is verified to belong to the account/caller.
- Constraints cascade via `@Valid` in the right place.
- Element count and nesting depth are bounded.
- Nested entities with owner/admin fields never become writable.
- If property binding uses indexed paths, the allowlist carefully checks every nested property.
- Addition, deletion, ordering, and duplicate-ID behavior stay well-defined.

Using `List<DomainAddressEntity>` directly just because getters/setters are convenient is a signal to re-examine the input boundary.

## 16. Additional Production Testing Checkpoints

### 16.1. Policy tests in the service layer

Controller validation only filters data coming from HTTP. Services may be invoked by background jobs, message handlers, or internal tests. A secure domain service should enforce **action- and resource-level permissions** independently of controllers or via a unified business authorization boundary.

### 16.2. Concurrency and persistence tests

If a contact-change command executes multiple DB updates, wrap it in an appropriate transaction. If data is versioned, apply optimistic locking or documented conflict rules. Never assume the demo's `ConcurrentHashMap.computeIfPresent` suffices for real persistence.

### 16.3. Strict unknown-fields tests for JSON

If you document that "the server rejects unknown JSON properties," test sending `"role":"ADMIN"`, `"id":999`, or typoed keys and verify a 400 from the JSON handler. Do not treat form-urlencoded test results as proof for JSON.

### 16.4. Form field marker/default tests

Spring's `WebDataBinder` handles unchecked HTML checkboxes via field marker and field default prefixes. If a task DTO has Booleans/checkboxes, test checked, unchecked, and missing states. `acceptedTerms` in the demo is sent explicitly to avoid relying on marker conventions in tests focused on the allowlist.

### 16.5. Model-change tests

Whenever a new field is added to an entity or DTO, review:

- Does it belong to any request contract?
- Does it need new validation?
- Does any allowlist need updating?
- When and by whom may it be mapped into the domain?
- Are there permission, consent, or audit requirements?
- Could an output DTO accidentally expose the new data?

An automated test sending extra fields or a schema snapshot guards against unintended expansion far better than promising "the frontend won't send it."

## 17. Review Checklist When Creating a Data-Bound Endpoint

### Request design

- [ ] Every action has a **task-specific input DTO/command** with matching fields and semantics.
- [ ] No JPA/domain entity with broad setters is used as a request model.
- [ ] Request DTOs are separated from response DTOs and persistence entities.
- [ ] ID/role/owner/locked are never accepted from clients when the server must own them.
- [ ] Full replacement, partial update, creation, and admin mutations are clearly separated.

### Binding and validation

- [ ] `@ModelAttribute("objectName")` is named explicitly for HTML/form requests.
- [ ] For property binding, `setAllowedFields(...)` is configured specifically per task.
- [ ] `@InitBinder("objectName")` is scoped accurately on the controller/advice.
- [ ] `BindingResult` appears immediately after the bound/validated argument.
- [ ] `getSuppressedFields()` is checked when the contract requires rejecting extra fields.
- [ ] `@Valid`/`@Validated` is paired with a real Bean Validation provider.
- [ ] Type conversion errors are distinguished from constraint violations.
- [ ] Allowlists are not relied upon to guard constructor binding or Jackson JSON.
- [ ] If `setDeclarativeBinding(true)` is enabled, legacy forms are regression-tested.
- [ ] Nested collection/Map depth and element counts are bounded.

### Business logic and authorization

- [ ] Actor and permission to perform the action on the resource are verified.
- [ ] Service mapping **updates only permitted fields**.
- [ ] Role, ownerId, status, lock flags, and server-generated IDs are managed separately.
- [ ] DB constraints, transactions, and concurrency are handled when persisting.
- [ ] An audit trail exists for sensitive field changes.
- [ ] Output DTOs expose only fields the caller is authorized to view.

### Testing and operations

- [ ] Valid requests and constraint-invalid values are tested.
- [ ] Extra `role`/`id`/`ownerId`/nested sensitive fields are tested.
- [ ] Domain state is asserted unchanged outside the action's scope.
- [ ] Unauthorized callers targeting another account are tested.
- [ ] JSON inputs are tested separately if the endpoint uses `@RequestBody`.
- [ ] `@InitBinder` is tested as actually applied by Spring MVC, not via direct Java method calls.
- [ ] Sensitive rejected values are not logged.
- [ ] Monitoring distinguishes `DISALLOWED_FIELDS` from `INPUT_INVALID`.
- [ ] Regression tests run when new properties are added to entities/DTOs.

## 18. Conclusion

**Task-specific DTOs** restrict **which data an action has a legitimate reason to accept**. Spring's **allowed field lists** restrict **which property paths can be assigned via property binding**. The two measures complement rather than replace each other.

In Spring MVC:

- Prefer dedicated/immutable input DTOs; never bind JPA/domain entities directly.
- With setter/property binding, use `@InitBinder` + `setAllowedFields(...)` by `objectName` and inspect `getSuppressedFields()` when extra fields must be rejected.
- Remember that constructor binding and `@RequestBody` JSON use separate pipelines and are not protected by `allowedFields` in the same way.
- Add Bean Validation to verify values, **service authorization** to verify actor/action/resource, and **explicit mapping** to ensure only intended domain fields change.
- Write tests that intentionally send sensitive fields and verify post-update state, rather than testing only "UI-compliant" requests.

This design reduces mass-assignment risk even as the domain model evolves over time, while keeping each task's contract clear, testable, and straightforward to security-review.

## References

- [Spring Framework — MVC Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — MVC @ModelAttribute arguments and constructor binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — DataBinder API: setAllowedFields, getSuppressedFields, declarativeBinding](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — @RequestBody JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Core Constructor Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP API Security — Broken Object Property Level Authorization (BOPLA)](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
