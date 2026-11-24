# Preventing Unauthorized Changes to Server-Managed id, role, owner, and status

## Objective

In Spring MVC, data binding and JSON deserialization convert HTTP requests into Java objects. If you accept an entity directly that contains attributes such as `id`, `role`, `ownerId`, and `status`, a client can inject parameters outside the UI to request modifications to server-managed properties. This is **mass assignment / over-posting** (CWE-915). A related vulnerability is **IDOR/BOLA**: the sender alters the ID in the URL to affect someone else's resource.

This lesson belongs to the **Data Safety** series and focuses on four principles:

1. Accept only **editable attributes** into the input DTO.
2. With Spring MVC `@ModelAttribute`, restrict binding via `WebDataBinder` when needed; with JSON `@RequestBody`, control Jackson separately.
3. Identify the authenticated principal and verify ownership/tenant and permissions in the service, regardless of what the body sends.
4. Preserve `id`, `role`, `owner`, and `status` from current server state and modify them only through dedicated workflows with proper authorization, auditing, and transactions.

You will build a Java 17+ / Spring Boot 3.5.7 example featuring both form and JSON endpoints, Spring Security, `@Valid`, `setAllowedFields`, `setDeclarativeBinding`, principal-based ID checks, and a MockMvc test suite verifying that protected data remains unchanged.

## 1. How Does a Mass Assignment Attack Happen?

The frontend renders only two input fields:

~~~text
Display name: [Alice]
Bio:          [Developer]
                  [Save]
~~~

Yet the entity on the server has:

~~~java
public class AccountEntity {
    private Long id;
    private String ownerUsername;
    private String role;
    private String status;
    private String displayName;
    private String bio;

    // getters, setters, associations, and other logic...
}
~~~

If the controller binds the entity directly:

~~~java
@PostMapping("/accounts/edit")
String edit(@ModelAttribute AccountEntity account) {
    repository.save(account);
    return "redirect:/accounts";
}
~~~

then a client can submit:

~~~http
POST /accounts/edit
Content-Type: application/x-www-form-urlencoded

id=202&ownerUsername=bob&role=ADMIN&status=ACTIVE&displayName=Alice&bio=Hello
~~~

`@ModelAttribute` with property binding can assign request parameter names matching JavaBean properties, even for fields absent from the HTML. If the server then saves without policy checks, it may accidentally allow changing the ID, owner, role, or status.

The same applies to JSON:

~~~http
PUT /api/accounts/101
Content-Type: application/json

{
  "displayName": "Alice",
  "bio": "Hello",
  "id": 202,
  "role": "ADMIN",
  "ownerUsername": "bob",
  "status": "ACTIVE"
}
~~~

If `@RequestBody` deserializes into a broad entity and the service copies all fields, that is over-posting. **The UI is not a security boundary:** hidden/disabled fields, frontend validation, or "there is no edit-role button" will never stop a crafted HTTP request.

### Four server-determined properties

| Field | Meaning | Source of truth | Risk if client can modify arbitrarily |
| --- | --- | --- | --- |
| `id` | Record identity | Database or authorized ID in URL | Record swapping, unintended update, identity confusion |
| `role` | Permissions or membership | Security store / admin workflow | Self-escalation to ADMIN |
| `ownerId` / `ownerUsername` | Owner/tenant | Authenticated principal and domain data | Account takeover, transferring resources to another user |
| `status` | Lifecycle state | Domain state machine | Self-approval, unlocking, bypassing workflows |

An attribute may be modifiable in another endpoint—for example, `role` via an admin operation or `status` via an approval workflow. What must be prevented is **modifying it without authorization or outside the permitted command**, not prohibiting every change altogether.

## 2. Distinguishing Binding, Validation, and Authorization

Three questions are not the same:

- **Binding:** "Can the request assign a value to this property?"
- **Bean Validation:** "Does the value satisfy type/length/format rules?"
- **Authorization:** "Is this caller allowed to perform that action on that record?"

Example:

~~~java
class ProfileRequest {
    @NotBlank
    String displayName;

    @NotNull
    Role role;
}
~~~

JSON `{"displayName":"Alice","role":"ADMIN"}` can **pass** `@NotBlank` and `@NotNull`, even though the sender has no right whatsoever to choose a role. Therefore, **`@Valid` is not authorization**.

Logical chain of responsibility:

~~~text
Client-controlled HTTP input
       |
       +-- @ModelAttribute → WebDataBinder
       |                    (form/query/path/header)
       |
       +-- @RequestBody    → Jackson
       |                    (JSON)
       v
DTO containing only editable fields
       |
       v
@Valid / @Validated: syntax, size, format
       |
       v
Authenticated Principal / SecurityContext
       |
       v
Service: check resource owner / tenant / action
       |
       v
Domain: check current status and transition
       |
       v
Update only designated fields
       |
       v
Transaction / concurrency / audit
~~~

In practice, security filters typically authenticate before MVC reads the body. This diagram illustrates **responsibilities**, not a rigid middleware order.

## 3. Separate Inputs and Separate Outputs

### 3.1. Use DTOs containing only editable fields

Instead of accepting `AccountEntity`, define:

~~~java
public record EditProfileRequest(
        @NotBlank String displayName,
        @Size(max = 200) String bio) {
}
~~~

This is a snippet using `jakarta.validation.constraints.*`. The DTO **lacks** `id`, `role`, `ownerUsername`, and `status`.

You can define distinct commands for distinct use cases:

~~~text
RegisterAccountRequest:    email, password, displayName
EditOwnProfileRequest:     displayName, bio
ChangePasswordRequest:     oldPassword, newPassword
AdminChangeRoleRequest:    targetId, newRole, reason
ApproveApplicationCommand: applicationId, decision, justification
~~~

These should not be merged merely to avoid creating another class. The input contract expresses **write permissions** for each endpoint; the response model expresses **what may be read**.

### 3.2. Having a field in the response does not mean input can edit it

A user's own response might look like:

~~~json
{
  "id": 101,
  "ownerUsername": "alice",
  "role": "USER",
  "status": "ACTIVE",
  "displayName": "Alice"
}
~~~

Meanwhile the server may accept only this input:

~~~json
{
  "displayName": "Alice Updated",
  "bio": "New bio"
}
~~~

Never share one class with full getters/setters for both input and output just because the JSON shapes look similar.

### 3.3. Why can a mutable DTO still be safe?

A mutable DTO with only `setDisplayName` and `setBio` offers no sensitive properties for the framework to write. As the API evolves, reviewing new DTO changes is part of security review: **adding a new setter widens the input surface**.

Record/immutable constructor binding is even more helpful when the constructor accepts only editable fields. However, **never** put `role` or `owner` into a request record's constructor and assume constructor binding enforces permissions on its own.

## 4. Spring MVC: setAllowedFields and declarativeBinding

### 4.1. @ModelAttribute uses WebDataBinder

In MVC, `@ModelAttribute` typically binds form/query data into an object via `WebDataBinder`. To restrict property binding:

~~~java
@InitBinder("editForm")
void configureBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
~~~

`@InitBinder("editForm")` applies to the model attribute named `editForm` in the controller. Remember to match the name with `@ModelAttribute("editForm")` on the handler.

`setAllowedFields` is an **allowlist**: fields absent from the list are not accepted by setter/property binding. By contrast, `setDisallowedFields("id","role","owner","status")` is a **blocklist**: later, if the entity gains `isAdmin` or `approvedAt`, the old list easily misses it. Both Spring and OWASP recommend dedicated DTOs or an explicit allowlist rather than relying solely on disallowed fields.

### 4.2. setDeclarativeBinding(true) since Spring 6.1

Spring Framework 6.1+ supports:

~~~java
binder.setDeclarativeBinding(true);
~~~

When enabled, constructor binding continues to operate on declared constructor parameters, while setter/property binding activates only when `allowedFields` is configured. With a mutable form DTO:

~~~java
@InitBinder("editForm")
void configureBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "bio");
}
~~~

This helps prevent unintended property binding. Still, if the DTO constructor declares `role` or `ownerId`, those constructor parameters **remain** an input path: designing the input object properly is the core defense.

In Spring 5.x/6.0, the `setDeclarativeBinding` API does not exist: use dedicated DTOs and `setAllowedFields` for your version, or upgrade to a version that supports it.

### 4.3. Detecting suppressed fields

`BindingResult.getSuppressedFields()` returns field names rejected by the binder because they did not match the allowlist:

~~~java
@PostMapping("/me/form")
ResponseEntity<?> submit(
        @Valid @ModelAttribute("editForm") EditAccountInput form,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "UNEXPECTED_FIELD"));
    }

    // Check errors.hasErrors() and ownership in the service.
}
~~~

This is an abbreviated snippet; full code appears in section 8. You may choose to reject requests carrying extra fields to catch over-posting probes. Never log sensitive values from suppressed fields; if auditing is required, store the field name and request/correlation ID after sanitization.

**Note:** `getSuppressedFields()` belongs to Spring's data binder. It does not inspect unknown JSON properties parsed by Jackson.

### 4.4. Nested paths and wildcards

Allowed fields support property paths:

~~~java
binder.setAllowedFields(
        "displayName",
        "contact.city",
        "contact.postalCode");
~~~

With nested objects, avoid broad wildcards such as `"members[*].*"` if child objects contain `role`, `ownerId`, or `approved`. Input could attempt:

~~~text
members[0].role=ADMIN
contact.ownerId=202
flags[approved]=true
~~~

Nested collections/maps must likewise be modeled as DTOs containing only writable fields. If a map allows arbitrary keys, the domain service must constrain key names and value types per business rules.

## 5. JSON @RequestBody Needs Its Own Mechanism

`@RequestBody` typically uses Jackson's `HttpMessageConverter`, **not** `@ModelAttribute`'s WebDataBinder setter filtering. Thus, adding `@InitBinder` will not automatically stop JSON like `{"role":"ADMIN"}` if you still bind into an object that has a `role` field.

With a DTO containing only `displayName`/`bio`, you can tell Jackson to reject unknown keys:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

In the Spring Boot 3.5 example, Jackson raises an error if a client sends extra `id`, `role`, `ownerUsername`, or `status`, since no matching properties exist on the DTO. `HttpMessageNotReadableException` typically maps to HTTP 400.

This property applies to the Boot-configured Jackson mapper and may affect other JSON endpoints; evaluate scope and backwards compatibility in production. If you choose to ignore unknown keys instead of rejecting them, **still ensure there is no path copying unknown fields onto the entity**.

`@JsonIgnore` or `@JsonProperty(access = READ_ONLY)` can help govern JSON serialization/deserialization, yet they do not replace DTOs, Spring MVC binder policies, authorization, or domain rules. Adding a new setter to an input DTO can make a field no longer "unknown."

## 6. IDOR and Ownership Must Be Checked in the Service

### 6.1. An ID in the URL carries no permission

~~~http
PUT /api/accounts/202
Authorization: Bearer <verified-token>
Content-Type: application/json

{"displayName":"Changed","bio":"Text"}
~~~

Suppose the sender is `alice` and account `202` belongs to `bob`. The DTO body is completely valid and contains no sensitive fields, **yet the request must still be blocked**. That is why input DTOs alone cannot prevent IDOR/BOLA.

The controller should pass the user identity from Spring Security:

~~~java
service.updateOwn(
        idFromPath,
        principal.getName(),
        input);
~~~

The service checks:

~~~java
Account account = repository.findById(id)
        .orElseThrow(AccountNotFoundException::new);

if (!account.getOwnerUsername()
        .equals(authenticatedUsername)) {
    throw new AccountNotFoundException();
}
~~~

This snippet requires repository/domain classes and is not standalone. Returning HTTP 404 for resources not owned by the caller can reduce ID enumeration; some APIs return 403 per contract. What matters is **never updating a resource without authorization**.

### 6.2. The principal must come from a trusted source

Never trust `ownerUsername` from a request body, query string, hidden form input, or self-asserted header like `X-User-Id`. The principal must be the identity verified by the security layer (session, HTTP Basic, JWT with validated signature/issuer/audience/expiration, etc.).

To avoid gaps across different entry points, enforce ownership/tenant authorization at the service/domain boundary before writing, not only in controllers. If using method security `@PreAuthorize`, still scope the target object rather than checking only that the user holds some generic role.

### 6.3. Multi-tenant

In multi-tenant systems, verify both the ID and the authenticated tenant context:

~~~java
Optional<AccountEntity> findByIdAndTenantId(
        Long id, Long trustedTenantId);
~~~

This is an illustrative Spring Data derived query signature. If `tenantId` appears in the URL or JSON, it remains untrusted input that must be checked against server-side membership. Never let clients pick an arbitrary tenant and immediately read or write that tenant's data.

## 7. Status and Role Are Separate Workflows

### 7.1. Never let profile edit alter status

A `SUSPENDED` account cannot submit `{"status":"ACTIVE"}` to unlock itself. Even with a valid request containing only `displayName`, the service must still check the current status and reject edits if the account is not allowed to be modified.

### 7.2. State machine

Example:

~~~text
DRAFT --submit--> PENDING
PENDING --approve--> APPROVED
PENDING --reject--> REJECTED
APPROVED --archive--> ARCHIVED
~~~

Transitioning `PENDING → APPROVED` is a **domain action**, not an arbitrary property update. The approval endpoint must verify reviewer permissions, initial state, justification, transaction, and auditing.

### 7.3. Changing roles through an admin workflow

If admins are permitted to change roles, create a dedicated endpoint/command:

~~~java
record AdminChangeRoleRequest(
        String newRole,
        String reason) {
}
~~~

Then verify admin authority from the security store, permissions on the tenant/target, policies against self-escalation or removing the last admin if needed, write an audit record, and refresh session/authority caches. Never add `role` to `EditOwnProfileRequest` simply because code reuse seems convenient.

### 7.4. Avoid blanket copyProperties

Do not write:

~~~java
BeanUtils.copyProperties(request, entity);
repository.save(entity);
~~~

when the request is broad or property mapping is unconstrained. Prefer explicit mapping:

~~~java
entity.setDisplayName(input.displayName());
entity.setBio(input.bio());
// Do not call setId, setRole, setOwner, or setStatus.
~~~

Similarly with MapStruct, a mapping with an explicit field list and ignored-by-default targets is far easier to review than an open mapping. No mapper replaces authorization.

## 8. Runnable Example: Spring Boot 3.5.7 / Java 17 / Spring MVC

The demo application provides two ways to edit the same profile:

- `PUT /api/accounts/{id}` accepts JSON into `EditAccountInput`.
- `POST /api/accounts/me/form` accepts a form into `@ModelAttribute("editForm")` with an allowlist.
- `GET /api/accounts/{id}` reads only the matching principal's account.

The domain holds four server-managed fields (`id`, `ownerUsername`, `role`, `status`) and two editable fields (`displayName`, `bio`). Account `charlie` starts as `SUSPENDED`. Data lives in a `ConcurrentHashMap` so the example requires no database; production should use a repository and transactions.

### 8.1. Project structure

~~~text
safe-account-edit/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/safeedit/
    │   │   ├── Application.java
    │   │   ├── SecurityConfig.java
    │   │   ├── EditAccountInput.java
    │   │   ├── AccountView.java
    │   │   ├── AccountService.java
    │   │   ├── AccountNotFoundException.java
    │   │   ├── AccountLockedException.java
    │   │   ├── AccountController.java
    │   │   └── ApiErrors.java
    │   └── resources/application.properties
    └── test/java/com/example/safeedit/
        └── AccountSecurityTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>safe-account-edit</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

The Spring Boot parent manages dependency versions; Spring Security test provides `@WithMockUser` and `csrf()` for MockMvc. Spring MVC/Servlet is chosen because `WebDataBinder` with `@InitBinder` is demonstrated here.

### 8.3. Application.java

~~~java
package com.example.safeedit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

~~~java
package com.example.safeedit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());

        // Keep CSRF enabled by default.
        return http.build();
    }
}
~~~

Authentication is necessary; the service must still verify resource ownership and state. HTTP Basic is used here only to illustrate protecting endpoints. Production requires a proper identity provider/user store, HTTPS, token/session policies, security headers, and auditing. Never construct `Principal` from a username in the request body.

### 8.5. EditAccountInput.java

~~~java
package com.example.safeedit;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class EditAccountInput {

    @NotBlank
    @Size(max = 80)
    private String displayName;

    @Size(max = 200)
    private String bio;

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
}
~~~

The default no-arg constructor suffices for Jackson and the form binder to instantiate the object. Notably: **there are no setters for id, role, owner, or status**. `@NotBlank` and `@Size` validate only the accepted data, not authorization rules.

### 8.6. AccountView.java

~~~java
package com.example.safeedit;

public record AccountView(
        long id,
        String ownerUsername,
        String role,
        String status,
        String displayName,
        String bio) {
}
~~~

This is the response DTO. Readable fields in an API response do not automatically belong in the input DTO.

### 8.7. AccountService.java

~~~java
package com.example.safeedit;

import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class AccountService {

    private record StoredAccount(
            long id,
            String ownerUsername,
            String role,
            String status,
            String displayName,
            String bio) {
    }

    private final Map<Long, StoredAccount> accounts =
            new ConcurrentHashMap<>();

    private final Map<String, Long> primaryIds = Map.of(
            "alice", 101L,
            "bob", 202L,
            "charlie", 303L);

    public AccountService() {
        accounts.put(101L, new StoredAccount(
                101L, "alice", "USER", "ACTIVE",
                "Alice", "Developer"));

        accounts.put(202L, new StoredAccount(
                202L, "bob", "USER", "ACTIVE",
                "Bob", "Designer"));

        accounts.put(303L, new StoredAccount(
                303L, "charlie", "USER", "SUSPENDED",
                "Charlie", "Editor"));
    }

    public AccountView getOwn(
            long id, String authenticatedUsername) {

        StoredAccount stored = accounts.get(id);

        if (stored == null
                || !stored.ownerUsername()
                        .equals(authenticatedUsername)) {
            throw new AccountNotFoundException();
        }

        return view(stored);
    }

    public AccountView updateOwn(
            long id,
            String authenticatedUsername,
            EditAccountInput input) {

        StoredAccount next = accounts.compute(
                id, (key, stored) -> {
                    if (stored == null
                            || !stored.ownerUsername()
                                    .equals(authenticatedUsername)) {
                        throw new AccountNotFoundException();
                    }

                    if (!stored.status().equals("ACTIVE")) {
                        throw new AccountLockedException();
                    }

                    return new StoredAccount(
                            stored.id(),
                            stored.ownerUsername(),
                            stored.role(),
                            stored.status(),
                            input.getDisplayName().trim(),
                            input.getBio());
                });

        return view(next);
    }

    public AccountView updateMyPrimary(
            String authenticatedUsername,
            EditAccountInput input) {

        Long id = primaryIds.get(authenticatedUsername);
        if (id == null) {
            throw new AccountNotFoundException();
        }

        return updateOwn(id, authenticatedUsername, input);
    }

    private static AccountView view(StoredAccount stored) {
        return new AccountView(
                stored.id(),
                stored.ownerUsername(),
                stored.role(),
                stored.status(),
                stored.displayName(),
                stored.bio());
    }
}
~~~

Four security points:

- `id` comes from the URL or internal lookup, never from the input DTO.
- `authenticatedUsername` comes from the Spring Security principal, never from the body.
- The service matches ownership before editing and rejects non-`ACTIVE` accounts.
- When building the updated record, the four server-managed fields are **copied intact** from existing state; only the two editable fields are updated.

`ConcurrentHashMap.compute` provides atomic per-key updates in the demo. The `primaryIds` map is sample fixture data, not a real-world account lookup mechanism: use a trusted database mapping and verify tenant/permissions. Account `role` is server-managed metadata; authority sources used for access control in production must be protected by the security subsystem, never taken from DTOs.

### 8.8. AccountNotFoundException.java

~~~java
package com.example.safeedit;

public final class AccountNotFoundException
        extends RuntimeException {
}
~~~

### 8.9. AccountLockedException.java

~~~java
package com.example.safeedit;

public final class AccountLockedException
        extends RuntimeException {
}
~~~

### 8.10. AccountController.java

~~~java
package com.example.safeedit;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.security.Principal;
import java.util.Map;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @InitBinder("editForm")
    void initBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("displayName", "bio");
    }

    @GetMapping("/{id}")
    public AccountView get(
            @PathVariable long id,
            Principal principal) {

        return service.getOwn(id, principal.getName());
    }

    @PutMapping(
            path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public AccountView updateJson(
            @PathVariable long id,
            @Valid @RequestBody EditAccountInput input,
            Principal principal) {

        return service.updateOwn(
                id, principal.getName(), input);
    }

    @PostMapping(
            path = "/me/form",
            consumes =
                    MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updateForm(
            @Valid @ModelAttribute("editForm")
            EditAccountInput input,
            BindingResult errors,
            Principal principal) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(
                    Map.of("code", "UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    Map.of("code", "VALIDATION_FAILED"));
        }

        return ResponseEntity.ok(
                service.updateMyPrimary(
                        principal.getName(), input));
    }
}
~~~

**Important:** `@InitBinder` governs only the `@ModelAttribute` path. JSON `@RequestBody` uses Jackson with the DTO and strict unknown fields. The form handler places `BindingResult` immediately after `@ModelAttribute` and returns 400 if the binder suppresses any input outside the allowlist.

The form route is `/me/form`, so **no path variable** enters the bound request values. The server resolves the principal's account. For form endpoints with an `id` path variable, inspect carefully how MVC exposes URI variables to the binder and `getSuppressedFields()` so valid requests are not accidentally rejected.

### 8.11. ApiErrors.java

~~~java
package com.example.safeedit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(AccountNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Account not found");
        p.setProperty("code", "ACCOUNT_NOT_FOUND");
        return ResponseEntity.status(
                HttpStatus.NOT_FOUND).body(p);
    }

    @ExceptionHandler(AccountLockedException.class)
    ResponseEntity<ProblemDetail> locked() {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Account cannot be edited in its current state");
        p.setProperty("code", "ACCOUNT_STATE_CONFLICT");
        return ResponseEntity.status(
                HttpStatus.CONFLICT).body(p);
    }
}
~~~

Not-found/unauthorized errors return 404 per the demo policy, and locked-state errors return 409. The handler never echoes internal exception details. Invalid JSON/form responses are handled by MVC or the controller with HTTP 400.

### 8.12. application.properties

~~~properties
server.port=8080
spring.jackson.deserialization.fail-on-unknown-properties=true
server.error.include-message=never
~~~

Do not hardcode `spring.security.*` passwords in project source. To reproduce with `alice`/`bob`/`charlie` principals, use `@WithMockUser` in the MockMvc tests below; when running the server manually, configure a real authentication provider and credentials for your environment.

Run:

~~~bash
mvn test
mvn spring-boot:run
~~~

A successful response after updating profile info looks like:

~~~json
{
  "id": 101,
  "ownerUsername": "alice",
  "role": "USER",
  "status": "ACTIVE",
  "displayName": "Alice Updated",
  "bio": "New bio"
}
~~~

The four server-managed fields stay intact while the client is only allowed to send two editable fields.

## 9. MockMvc Testing Both HTTP Responses and Final State

File `src/test/java/com/example/safeedit/AccountSecurityTest.java`:

~~~java
package com.example.safeedit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(username = "alice", roles = "USER")
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AccountSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerReadsOwnAccount() throws Exception {
        mvc.perform(get("/api/accounts/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void validJsonChangesOnlyEditableFields()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Alice Updated",
                                  "bio":"New bio"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andExpect(jsonPath("$.displayName").value(
                        "Alice Updated"));
    }

    @Test
    void forgedJsonRoleAndOwnerAreRejected()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Changed",
                                  "bio":"Text",
                                  "role":"ADMIN",
                                  "ownerUsername":"bob"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.role").value("USER"))
                .andExpect(jsonPath("$.ownerUsername").value(
                        "alice"))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    void forgedJsonIdIsRejected() throws Exception {
        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "id":202,
                                  "displayName":"Changed",
                                  "bio":"Text"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    void validFormUpdatesOwnFields() throws Exception {
        mvc.perform(post("/api/accounts/me/form")
                        .with(csrf())
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Alice Form")
                        .param("bio", "Updated by form"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value(
                        "Alice Form"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void forgedFormFieldsAreSuppressedAndRejected()
            throws Exception {

        mvc.perform(post("/api/accounts/me/form")
                        .with(csrf())
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Attacker")
                        .param("bio", "Text")
                        .param("id", "202")
                        .param("role", "ADMIN")
                        .param("ownerUsername", "bob")
                        .param("status", "ACTIVE"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "UNEXPECTED_FIELD"));

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.displayName").value("Alice"))
                .andExpect(jsonPath("$.role").value("USER"));
    }

    @Test
    void pathIdCannotAccessOtherOwner()
            throws Exception {

        mvc.perform(put("/api/accounts/202")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"Not Bob",
                                  "bio":"No permission"
                                }
                                """))
                .andExpect(status().isNotFound());

        mvc.perform(get("/api/accounts/202"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "charlie", roles = "USER")
    void suspendedAccountCannotEdit() throws Exception {
        mvc.perform(put("/api/accounts/303")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"New Charlie",
                                  "bio":"Edit attempt"
                                }
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(
                        "ACCOUNT_STATE_CONFLICT"));

        mvc.perform(get("/api/accounts/303"))
                .andExpect(jsonPath("$.status").value("SUSPENDED"))
                .andExpect(jsonPath("$.displayName").value(
                        "Charlie"));
    }

    @Test
    void invalidDisplayNameDoesNotChangeAccount()
            throws Exception {

        mvc.perform(put("/api/accounts/101")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName":"",
                                  "bio":"Text"
                                }
                                """))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/api/accounts/101"))
                .andExpect(jsonPath("$.displayName").value("Alice"));
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAccount() throws Exception {
        mvc.perform(get("/api/accounts/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/accounts/me/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "No CSRF")
                        .param("bio", "Text"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The suite of **11 tests** verifies: owner read access; valid JSON modifying only two fields; forged JSON role/owner/id rejected with state preserved; valid form update; form with fields outside the allowlist suppressed and rejected; changing URL ID to another user's account blocked; `SUSPENDED` state cannot be bypassed; Bean Validation; 401 authentication; and 403 CSRF.

`@DirtiesContext` recreates the application context after each test so map entries are not mutated across tests. In larger systems with databases, consider transactional rollback or fixture resets for speed while maintaining test isolation.

**QA scope:** the code and APIs in the demo target Java 17 / Spring Boot 3.5.7; `mvn test` is the provided execution command. This document does not claim Maven was executed in the authoring environment.

## 10. JPA/Transactions and Server State

In production, replace the in-memory map with entities and repositories. A safer update approach:

~~~java
@Transactional
public AccountView edit(
        long id,
        String authenticatedUsername,
        EditAccountRequest input) {

    AccountEntity entity =
            repository.findByIdAndOwnerUsername(
                    id, authenticatedUsername)
                .orElseThrow(AccountNotFoundException::new);

    if (entity.getStatus() != AccountStatus.ACTIVE) {
        throw new AccountLockedException();
    }

    entity.setDisplayName(input.displayName());
    entity.setBio(input.bio());

    return toView(entity);
}
~~~

This is an **architectural snippet** requiring real entity/repository/DTO definitions, not part of the runnable project above. Never invoke setters for id/role/owner/status. In JPA, managed entities are dirty-checked when the transaction completes; avoid copying the HTTP body directly onto the entity.

With optimistic locking:

~~~java
@Entity
class AccountEntity {
    @Id
    private Long id;

    @Version
    private long version;
}
~~~

This is an incomplete JPA snippet missing imports/mapping. `@Version` helps detect certain lost updates when two requests edit concurrently; it does not prove the caller is authorized.

When atomic authorization and state checks are needed directly in the database, a conditional update can be used:

~~~sql
UPDATE accounts
SET display_name = :displayName,
    bio = :bio
WHERE id = :accountId
  AND owner_username = :trustedUsername
  AND status = 'ACTIVE'
  AND version = :expectedVersion;
~~~

Check the affected row count and advance `version` according to DB/ORM policy. In multi-tenant systems, add a tenant predicate. Never use an arbitrary `userId` or `tenantId` from the request body as a trusted predicate.

## 11. PATCH, Nested Fields, and Other Write Paths

### 11.1. JSON Patch

A payload such as:

~~~json
[
  {"op":"replace","path":"/displayName","value":"Alice"},
  {"op":"replace","path":"/role","value":"ADMIN"}
]
~~~

must never be applied directly to an entity. With JSON Patch/Merge Patch, enforce an **allowlist of paths** (such as `/displayName`, `/bio`), validate operation/type, distinguish absent fields from null, and authorize on the resource.

### 11.2. Nested input

~~~json
{
  "displayName":"Alice",
  "team":{
    "ownerId":202,
    "members":[{"role":"ADMIN"}]
  }
}
~~~

If a DTO embeds a broad nested `team` object, clients can attempt to modify `role`/`owner` via the child graph. Separate nested DTOs containing only permitted fields, with appropriate constraints and size limits. Never apply wildcards across an entire object graph when it contains server-managed fields.

### 11.3. Bulk / batch updates

When an API accepts a list of IDs, check authorization on **every** object or use a query enforcing the same scope. Never validate only the first ID and apply the update to the whole batch without checking the rest. For partially failing batches, define transaction/atomicity boundaries and error response contracts clearly.

### 11.4. Auditing and observability

Record:

~~~text
principal=alice
action=EDIT_OWN_PROFILE
resourceType=Account
resourceId=101
changedFields=[displayName,bio]
result=SUCCESS
~~~

This is an example log entry, not demo stdout. If an attempt to submit `role` or `ownerUsername` is caught, you can log the field name and request ID after sanitization—**never** log raw bodies, rejected values, tokens, or sensitive PII.

## 12. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| User sends `role=ADMIN` and server accepts it | Entity is bound directly | Small DTO, allowedFields, authorization |
| Using only `setDisallowedFields("role")` | Later `isAdmin` or other aliases are missed | Prefer allowlist/DTO |
| `@Valid` still accepts `role=ADMIN` | Valid enum value, yet unauthorized | Authorization and exclude `role` from input |
| Client modifies `ownerId` in body | Trusting body instead of principal | Use identity from `SecurityContext` |
| DTO has only editable fields, yet edits another account | IDOR via URL `/{id}` | Service checks authorization on resource ID |
| Form rejected when extra field is added | Binder suppresses field outside allowlist | Explicit 400 or controlled ignore policy |
| JSON has extra fields and `@InitBinder` does not block them | JSON is handled by Jackson | DTO + Jackson unknown-field policy |
| Declarative binding enabled, yet constructor takes `role` | Constructor remains a binding source | Constructor accepts only editable params |
| `status=ACTIVE` unlocks account | Input copied onto entity | Domain state check and separate workflow |
| PATCH edits `/members/0/role` | Unbounded paths | Patch allowlist/nested DTO |
| Form sends hidden `ownerId` | Hidden inputs are untrusted | Exclude `owner` from form inputs |
| Test asserts only 400 without checking DB | State may have changed before throwing | Assert state post-request, transaction/rollback |
| Missing CSRF tests | Testing controller directly bypasses security filters | Full MockMvc Security + `csrf()` |
| Ownership checked only in controller | Other service callers can bypass | Enforce at service/domain boundary |
| Concurrent update overwrites newer status | Race condition/lost update | Transaction, version/state predicate |
| Logging raw rejected field value | Leaks tokens/PII | Log minimal key/context, never values |
| JSON response exposes internal exception | Returning raw exception | Safe error codes and messages |
| Older Spring versions lack `setDeclarativeBinding` | API added in Spring 6.1 | DTO + allowedFields, or upgrade version |

A real-world security note: Spring advisory **CVE-2025-22233** documented cases where `disallowedFields` checks could be bypassed in certain versions. Listed fixed versions include 6.2.7 and 6.1.20. Apply appropriate patches while still preferring DTO/allowlist design over denylists.

## 13. Checklist for Reviewing an Update Endpoint

1. Does the controller accept an entity directly from body or form?
2. Does the input DTO contain only fields permitted for editing?
3. Could any nested DTO/collection/map expose `owner`/`role`/`status`?
4. For forms, does `@InitBinder` match the model attribute name and configure `allowedFields` accurately?
5. For JSON, are extra fields tested under the active Jackson policy?
6. Is the URL ID authorized against the true principal/tenant?
7. Is `SecurityContext` populated from a trusted authentication source rather than self-asserted headers/bodies?
8. Do `role`/`status` have separate workflows and precondition checks?
9. Does the service manually map only editable fields?
10. Do database transactions, versioning, or conditional updates protect against race conditions?
11. Are there tests for JSON role/owner/id, form role/owner/id, URL IDOR, and suspended states?
12. Do tests verify final state still preserves `id`/`role`/`owner`/`status`?
13. Are CSRF, method security, and auditing in place where needed?
14. When upgrading Spring versions, have binder APIs and security advisories been reviewed?
15. When a request is rejected, do responses and logs avoid leaking secrets and user data?

## 14. Practice Exercises

**1.** Build an anti-pattern controller accepting `AccountEntity` and try sending `role=ADMIN`. Explain exactly which layer allows writing the field and why this code must not be used.

**2.** Switch to an input DTO with `displayName` and `bio`; write a test for JSON with extra `role` and `ownerUsername`. Explicitly specify 400 vs. ignore behavior.

**3.** For the form endpoint, add `@InitBinder("editForm")` and `setAllowedFields`, then inspect `BindingResult.getSuppressedFields()`. Why does suppressing `ownerUsername` not mean authorization is complete?

**4.** Enable `setDeclarativeBinding(true)` on Spring 6.1+ and test a DTO constructor containing only editable fields. Explain why a broad constructor remains dangerous.

**5.** Authenticate as `alice` and attempt `PUT /api/accounts/202` belonging to `bob`. Why must a payload without `role`/`owner` still be rejected?

**6.** For account `charlie` in `SUSPENDED` state, send a valid bio update request. What happens, and under which policy should 403 vs. 409 be returned?

**7.** Design an admin-only command to change roles with permission checks, reason, and auditing. Distinguish the requested role in the body from the caller's authority.

**8.** Add `tenantId` to accounts. Update the repository query to verify ID, owner, and tenant within the same safe predicate.

**9.** Add `@Version` to the JPA entity. Design a test for two concurrent updates and explain why optimistic locking does not replace authorization.

**10.** Add a nested `ContactInput` with street/city. Prove clients cannot inject `contact.ownerId` or `members[0].role` through the binder or JSON.

## Conclusion

~~~text
HTTP form / JSON / PATCH: UNTRUSTED
       |
       v
Input DTO with editable fields only
       |
       +-- MVC form: allowedFields + declarativeBinding
       +-- JSON: Jackson DTO + unknown-field strategy
       +-- PATCH: allowlist operations/paths
       |
       v
Format and constraint validation
       |
       v
Authenticated principal + resource-level authorization
       |
       v
Server-side state checks and workflow rules
       |
       v
Explicit updates ONLY for editable fields
       |
       v
Transaction / concurrency / audit
~~~

**Never allow id, role, owner, or status to become client-writable data merely because a setter or JSON property exists.** Separate input from domain models, authorize against the target object, retain server-owned fields from trusted state, and test both HTTP responses and post-update data. `@Valid`, UI hiding, and denylists cannot replace those boundaries.

## References

- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [Spring Framework 6.2 — MVC Data Binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Security — CVE-2025-22233 DataBinder advisory](https://spring.io/security/cve-2025-22233/)
- [Spring Boot 3.5 — Jackson application properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Security — MockMvc with @WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
