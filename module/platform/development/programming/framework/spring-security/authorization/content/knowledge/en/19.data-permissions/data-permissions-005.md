# Preventing `ownerId`, `tenantId`, and Sensitive Field Tampering via Mass Assignment in Spring Security

## 1. The Problem: User Can Only Edit Title, Yet Sends `ownerId` Too

Suppose the system stores a document:

```json
{
  "id": 11,
  "ownerId": "u-alice",
  "tenantId": "T1",
  "title": "Quarterly plan",
  "description": "Draft",
  "state": "DRAFT",
  "sensitivity": "RESTRICTED",
  "version": 1
}
```

The **Edit Content** feature allows `alice` to update strictly two fields: `title` and `description`. However, a client could submit:

```json
{
  "title": "Updated plan",
  "description": "Valid content",
  "ownerId": "u-bob",
  "tenantId": "T2",
  "state": "APPROVED",
  "sensitivity": "INTERNAL",
  "version": 999,
  "isAdmin": true
}
```

If the controller deserializes the entire JSON into an entity and calls `repository.save(...)` or an overly broad `BeanUtils.copyProperties(...)`, **disallowed properties can be overwritten**. Consequences include ownership transfer, tenant transfer, self-approval, lowering data sensitivity, forging audit info, or privilege escalation.

This vulnerability is called **mass assignment**, **over-posting**, or **unsafe object binding**: the framework automatically maps untrusted input onto internal object properties without scoping to the use case.

This lesson belongs to the **Data Permissions** group of Spring Security authorization, focusing on **blocking tampering with `ownerId`, `tenantId`, and sensitive fields**. We will progress from the attack model, input restriction, and secure service design to a Spring Boot/Java 17 example with real HTTP tests via `MockMvc`.

After this lesson, you will be able to:

1. Explain why authentication and authorities **do not automatically prevent mass assignment**.
2. Classify **client-editable** vs **server-managed** fields.
3. Design **allowlist DTOs** and explicit mapping instead of entity binding.
4. Understand the difference between JSON `@RequestBody` (Jackson) and form `@ModelAttribute` (`WebDataBinder`).
5. Place `ownerId`, `tenantId`, state, and permission checks in the **service**, using trusted identity.
6. Configure unknown JSON field rejection to detect payloads deliberately injecting extra fields.
7. Run a Java 17+ / Spring Boot 3.5.x demo and integration tests covering allow, deny, cross-tenant, unknown fields, approved state, and CSRF.
8. Protect owner transfer, tenant transfer, approval, admin, and PATCH workflows separately.
9. Avoid nested binding, generic mapper, ORM merge, caching, and concurrency flaws.

**Foundational rule:** Clients may only send **data the use case intentionally allows editing**. Owner, tenant, permissions, approval state, audit fields, and version come from **trusted server sources**, changed only through workflows with dedicated policies.

## 2. Mass Assignment Differs from BOLA/IDOR, Yet Often Co-Occurs

**Mass assignment:** the client sends extra fields and object binding writes them into internal state.

**BOLA/IDOR (Broken Object Level Authorization):** the client alters an ID in the URL/request to access or edit **an object they do not own/have permission on**.

Both bugs can combine:

```text
PUT /api/documents/11
Authorization: Bob's token

{
  "title": "Hijacked",
  "ownerId": "u-bob",
  "tenantId": "T1"
}
```

If you only check `hasAuthority('document:edit')` and **bind the payload into the entity before checking the owner**, Bob could turn Alice's record into his own. Even if `ownerId` in the payload is ignored, you still must check whether Bob **has permission to edit document 11**.

| Control Layer | Question | Example |
| --- | --- | --- |
| Authentication | Who is calling? | Verified JWT/session/Basic |
| Function-level authorization | Does the caller have document editing capability? | `document:edit` |
| Object-level authorization | Can they edit **this specific document**? | User, tenant, owner, ACL, and state |
| Field-level write authorization | **Which properties** of the document may be edited? | `title`, `description` |
| State transition policy | Can they change state/owner/tenant? | `DRAFT -> APPROVED`, ownership transfer |
| Data integrity | Is the data still valid at write time? | Validation, version, conditional UPDATE |

**No single layer replaces all the others.** `@PreAuthorize("hasRole('USER')")` does not stop JSON containing `tenantId` if code still copies every field. Conversely, a DTO allowlist does not prevent Bob from editing Alice's document via another ID.

## 3. Classifying Fields by Write Permission

A useful practice is creating a **write-policy matrix** per endpoint/use case:

| Field | Content Edit API | Authoritative Value Source | Valid Way to Change |
| --- | --- | --- | --- |
| `title` | Allowed | Validated JSON | `updateContent` |
| `description` | Allowed | Validated JSON | `updateContent` |
| `id` | Disallowed | Identifier from URL, DB lookup | Immutable after creation |
| `ownerId` | Disallowed | DB + actor/policy | Dedicated `transferOwnership` |
| `tenantId` | Disallowed | DB + server identity | Dedicated tenant transfer workflow |
| `state` | Disallowed | Server workflow | Dedicated `approve`/`reject` |
| `sensitivity` | Disallowed | Data classification policy | Dedicated `changeClassification` |
| `role`, `authorities`, `isAdmin` | Disallowed | Identity/permission management | Dedicated identity administration |
| `createdBy`, `createdAt` | Disallowed | Server auditing | Written once on creation |
| `updatedBy`, `updatedAt` | Disallowed | Server auditing | Written automatically on update |
| `version` | Not arbitrarily editable | DB/optimistic locking | Incremented by DB or checked as precondition |
| `balance`, `approvedAmount`, `price` | Depends on use case | Business rules, approved source | Dedicated API/domain command |

Note that `version` may be **sent by the client as a precondition** (`If-Match`/expectedVersion) to prevent lost updates, but it **must never be assigned directly** onto the entity. `expectedVersion` in a request differs from permission to **set** version.

Similarly, a business feature may let a manager change `ownerId`. That does not make `ownerId` editable in **every** API. Separate the function and use a dedicated permission.

### 3.1. Warning About Future Fields Added Later

Suppose today the entity only has `title` and `description`, and next month `publicAccess` or `reviewedBy` is added. If the controller binds **the full entity** or a mapper copies all properties by default, the new field silently becomes client-editable without anyone intentionally designing permissions for it.

With **a DTO containing only allowed fields**, adding fields to the entity **does not automatically widen the write API**. This is why allowlists are far more durable than blacklists.

## 4. Insecure Code Pattern: Binding the Entity Directly

```java
// INTENTIONALLY INSECURE SNIPPET; do not use in production.

@PutMapping("/api/documents/{id}")
public Document update(
        @PathVariable Long id,
        @RequestBody Document incoming) {

    Document existing = repository.findById(id).orElseThrow();

    // Depending on mapper/config, this can overwrite sensitive fields too.
    BeanUtils.copyProperties(incoming, existing);

    return repository.save(existing);
}
```

If `Document` has setters for `ownerId`, `tenantId`, `state`, `sensitivity`, or `isAdmin`, copying without an allowlist can overwrite them. This is a **vulnerability illustration snippet**, not a runnable program.

Another dangerous variant:

```java
// INSECURE: JSON can control multiple entity fields.
@PutMapping("/api/documents/{id}")
public Document replace(
        @PathVariable Long id,
        @RequestBody Document document) {

    return repository.save(document);
}
```

It can also skip comparing the URL ID against the JSON ID, or turn `save` into an unintended create/update. Even if JPA/Hibernate has `@Column(updatable=false)` on some fields, **never treat that as object-level or field-level authorization**.

### 4.1. Easily Overlooked Entry Points

Mass assignment can occur via:

- JSON API `@RequestBody` deserialized via Jackson into an entity.
- Form-urlencoded/multipart and query strings using `@ModelAttribute`.
- `Map<String,Object>` followed by `ObjectMapper.convertValue(...)` to an entity.
- Generic update services, `BeanUtils.copyProperties`, or reflection mappers.
- JSON Merge Patch / JSON Patch allowing arbitrary path modifications.
- GraphQL input types reusing entities; message/event consumers accepting payloads across trust boundaries.
- Nested properties such as `document.owner.id`, `user.roles[0]`, `account.isAdmin`, `organization.tenantId`.
- ORM update/merge of an entire detached entity received from the client.

The root cause is not any single annotation; the root cause is **allowing untrusted data to dictate properties that belong to server authority**.

## 5. Safe Architecture: Allowlist DTO -> Service Policy -> Controlled Update

```text
Client JSON
    |
    v
@RestController
    |
    +--> Jackson deserializes into UpdateDocumentRequest
    |       title, description
    |       No ownerId/tenantId/state/role
    |
    +--> @Valid / structural validation
    |
    v
DocumentService (Spring-managed bean)
    |
    +--> @PreAuthorize("hasAuthority('document:edit')")
    +--> Get trusted Authentication from SecurityContext
    +--> Resolve userId/tenantId from server directory
    +--> Load real record by id
    +--> Check tenant + owner + state
    |
    v
DocumentStore / DB update
    |
    +--> Set strictly title, description
    +--> PRESERVE ownerId, tenantId, state, sensitivity
    +--> Server increments version/audit
    |
    v
Response DTO (only permitted output fields)
```

**Two distinct allowlist layers:**

1. **Request structure allowlist:** only lets the client declare valid fields of the command. It prevents the API from silently becoming a universal entity updater.
2. **Service business allowlist:** assigns only fields defined in the contract. Even if a mapper is configured differently or another endpoint calls the service, the rule still holds.

**Server-determined subject and tenant values:** Never pass `actorUserId` or `trustedTenant` from JSON and treat it as identity. For JWT/OIDC, verify signature/issuer/audience and map `sub` to user/tenant per policy.

### 5.1. Using an Immutable Request DTO

```java
public record UpdateDocumentRequest(
    @NotBlank @Size(max = 120) String title,
    @NotBlank @Size(max = 1000) String description
) {}
```

The DTO has no `ownerId`, `tenantId`, `state`, `sensitivity`, `role`, or `isAdmin`. A Java record has a constructor declaring exactly the accepted data and no setters for the client to affect anything else.

**Using a DTO alone is not enough.** If the service takes `id` without checking, a caller can still edit someone else's object; hence object-level authorization is required.

### 5.2. Explicit Mapping onto an Existing Entity

```java
// Service idea, assuming permissions and existing record were checked.
Document changed = new Document(
    before.id(),            // Keep ID
    before.ownerId(),       // Keep owner from DB
    before.tenantId(),      // Keep tenant from DB
    before.state(),         // Keep state
    before.sensitivity(),   // Keep sensitivity
    request.title(),        // ONLY client-editable data
    request.description(),  // ONLY client-editable data
    before.version() + 1    // Server increments version
);
```

This is an illustrative snippet; the full program is in section 7. Constructing the new object from old state plus the two permitted fields makes write-permission boundaries **obvious in code review**.

In JPA, load the managed entity and call **only permitted setters** after authorization. Never `merge` a client-built detached entity if it carries more fields than the use case permits.

## 6. Spring MVC: `@RequestBody` Differs from `@ModelAttribute`

This section is crucial to avoid applying the wrong protection mechanism.

### 6.1. JSON `@RequestBody` Uses Jackson

Example:

```java
@PutMapping("/api/documents/{id}")
public UpdateDocumentResponse replace(
        @PathVariable long id,
        @Valid @RequestBody UpdateDocumentRequest request) {
    return service.update(id, request);
}
```

Spring uses `HttpMessageConverter`/Jackson to deserialize JSON into a DTO, then validates it. **`WebDataBinder.setAllowedFields(...)` is not an allowlist mechanism for JSON `@RequestBody`**; it primarily controls property binding for `@ModelAttribute`/forms.

For JSON, use a dedicated DTO, Jackson annotations where appropriate, and **map only permitted fields** in the service.

### 6.2. Form/Query `@ModelAttribute` Uses `WebDataBinder`

For form binding, Spring Framework recommends designing dedicated input objects, using constructor binding, or restricting property binding with `allowedFields`.

```java
// Controller SNIPPET for @ModelAttribute forms, do NOT use to
// protect JSON @RequestBody requests.
@InitBinder("documentForm")
void allowOnlyFormFields(WebDataBinder binder) {
    binder.setAllowedFields("title", "description");
}
```

When you need to detect payloads containing suppressed fields, inspect `BindingResult.getSuppressedFields()` and reject/log per policy. If you only suppress without erroring, users may get a success response while sensitive fields are silently dropped; this is safer than overwriting, yet harder to diagnose.

`DataBinder#setDisallowedFields` uses a **blacklist** that easily misses new fields or nested paths; Spring Framework recommends preferring `allowedFields`/constructor binding. Specifically, `@ModelAttribute` supports property paths like `address.city`, `items[0].name`, `map[key]`; be careful with wildcards unless you intend to expose nested fields.

### 6.3. Validation Does Not Replace Authorization

`@NotBlank`, `@Size`, `@Positive`, enum checks, etc. only confirm data is structurally valid. They **do not answer whether the client has permission to change `ownerId`**. A `tenantId = "T2"` can be completely valid in format yet still be a forbidden modification.

Similarly, JSON Schema can check unknown fields and data types; you still need a service policy if a field is editable by **one group of users but not another**.

### 6.4. Rejecting Unknown JSON Fields as a Supporting Layer

In Spring Boot 3.x, Jackson ignores undeclared JSON fields under Boot's default configuration. So this demo API **immediately catches** fields like `ownerId` and `tenantId`, enable:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

Then JSON sending a field absent from the DTO can trigger **HTTP 400** due to deserialization failure. This is good defense-in-depth to catch over-posting, though:

- **It cannot fix a poorly designed DTO.** If `ownerId` is declared in the DTO and code assigns it, it is not an *unknown field*; the flag cannot save it.
- If `@JsonAnySetter`, aliases, or custom ignore rules exist, evaluate the actual mapper configuration outcome.
- API compatibility matters: rejecting unknown fields can break old/new clients. For sensitive actions, strict contracts are beneficial, with clear versioning and tests.
- Never rely on this flag as the **sole security layer**. Service mapping must still allowlist even if lenient JSON parsing is enabled on another endpoint.

### 6.5. `@JsonProperty(READ_ONLY)`, `@JsonIgnore`, and ORM Annotations

You can use Jackson `@JsonProperty(access = JsonProperty.Access.READ_ONLY)` to restrict deserializing a property, or `@JsonIgnore` to exclude a property from JSON binding. Yet these are **serialization/deserialization behaviors**, not business authorization policies: they can be bypassed when updating via another service, mapper, form binding, or repository.

JPA's `@Column(updatable=false)` only affects how the ORM generates UPDATE statements for a column; it does not block all data update paths and can hinder legitimate ownership transfer workflows. `@CreatedBy`/`@LastModifiedBy` are auditing, not authorization themselves. Use them as contextual defense-in-depth, never as replacements for DTOs and service policies.

## 7. Complete Java 17+/Spring Boot 3.5.8 Demo

The demo builds an HTTP endpoint `PUT /api/documents/{id}` allowing updates only to `title` and `description`. `ownerId`, `tenantId`, `state`, `sensitivity`, and `version` remain server-controlled.

**Security specification:**

- User must be authenticated and hold authority `document:edit`.
- A user/tenant record must exist in a trusted server-managed directory.
- Only the owner **in the same tenant** may edit a document in `DRAFT` state.
- Request DTO contains only `title`, `description` and is validated.
- Unknown JSON fields are rejected with HTTP 400.
- Even if a client attempts to send `ownerId`, `tenantId`, `state`, `sensitivity`, `version`, those fields are never copied to the entity.
- Return a response DTO containing only appropriate fields; never accidentally serialize the entire entity.
- Spring Security CSRF protection **remains enabled**; tests pass a CSRF token.
- `ConcurrentHashMap.compute` keeps updating a single demo entry atomic. Production needs DB transactions and concurrency policies.

### 7.1. File Structure

```text
safe-document-update/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SafeDocumentApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── Document.java
    │   │   ├── UpdateDocumentRequest.java
    │   │   ├── UpdateDocumentResponse.java
    │   │   ├── TrustedUserDirectory.java
    │   │   ├── DocumentStore.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── DocumentApiSecurityTest.java
```

### 7.2. Gradle and Configuration

**`settings.gradle`:**

```groovy
rootProject.name = 'safe-document-update'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

In Boot 3.5.x, this key controls the corresponding Jackson deserialization feature. It helps the API **reject** unknown fields, rather than attaching permission policies to fields already present in the DTO.

### 7.3. Spring Boot and Method Security

**`src/main/java/demo/SafeDocumentApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SafeDocumentApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeDocumentApplication.class, args);
    }
}
```

`@EnableMethodSecurity` is required for `@PreAuthorize` on services to take effect. Adding `spring-boot-starter-security` alone **does not enable method-level security**.

### 7.4. HTTP Security: Authentication and CSRF

**`src/main/java/demo/SecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.PUT, "/api/documents/*")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This demo includes **HTTP Basic** so the Spring Security filter chain has an authentication mechanism. Real users for manual deployment are not defined here; tests use `@WithMockUser`. For production, replace with JWT/OIDC/session as required, and never hardcode passwords in code.

**Do not disable CSRF just to make testing easier.** For cookie/session applications, CSRF protection is vital. MockMvc tests use `.with(csrf())` for PUT, and include a test proving missing tokens are rejected. A stateless bearer-only API has a different CSRF threat model, which must be explicitly evaluated before changing defaults.

### 7.5. Domain Object with Protected Fields

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(
        long id,
        String ownerId,
        String tenantId,
        State state,
        Sensitivity sensitivity,
        String title,
        String description,
        long version) {

    public enum State {
        DRAFT, APPROVED
    }

    public enum Sensitivity {
        INTERNAL, RESTRICTED
    }
}
```

An immutable record avoids general setters. However, **immutability does not automatically eliminate mass assignment** if you deserialize JSON directly into a record entity with all eight constructor parameters. That is why a two-field request DTO is still required.

### 7.6. Request DTO for Content Editing Only

**`src/main/java/demo/UpdateDocumentRequest.java`:**

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 1000) String description) {
}
```

**`src/main/java/demo/UpdateDocumentResponse.java`:**

```java
package demo;

public record UpdateDocumentResponse(
        long id,
        String title,
        String description,
        long version) {
}
```

Request and response **do not have to mirror the entity**. The response contains only the fields the caller needs. Never let Jackson serialize an entity containing sensitive fields and hope an endpoint filter redacts them.

### 7.7. Server-Side Trusted Directory

**`src/main/java/demo/TrustedUserDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId) {
}

@Component
public class TrustedUserDirectory {

    private final Map<String, Actor> accounts = Map.of(
        "alice", new Actor("u-alice", "T1"),
        "bob",   new Actor("u-bob", "T1"),
        "carol", new Actor("u-carol", "T2")
    );

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    public Actor require(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || resolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted identity");
        }

        Actor actor = accounts.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("Unknown actor");
        }
        return actor;
    }
}
```

`Actor` is a server-internal identity, not a client-filled DTO. `getName()` in the example maps to a unique account; in OIDC/JWT production, use a stable `sub` along with issuer/tenant per your real identity model.

A user with `document:edit` does not automatically gain permission to switch tenants or edit every document. That authority is only the first condition.

### 7.8. In-Memory Repository Updating Only Permitted Fields

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentStore {

    private final Map<Long, Document> data = new ConcurrentHashMap<>();

    public DocumentStore() {
        data.put(11L, new Document(
            11L, "u-alice", "T1",
            Document.State.DRAFT, Document.Sensitivity.RESTRICTED,
            "Alpha", "Alice draft", 1L
        ));
        data.put(12L, new Document(
            12L, "u-bob", "T1",
            Document.State.DRAFT, Document.Sensitivity.INTERNAL,
            "Beta", "Bob draft", 1L
        ));
        data.put(13L, new Document(
            13L, "u-carol", "T2",
            Document.State.DRAFT, Document.Sensitivity.RESTRICTED,
            "Gamma", "Carol draft", 1L
        ));
        data.put(14L, new Document(
            14L, "u-alice", "T1",
            Document.State.APPROVED, Document.Sensitivity.RESTRICTED,
            "Approved", "Locked content", 1L
        ));
    }

    public Document snapshot(long id) {
        return data.get(id);
    }

    public Document updateContent(
            long id,
            Actor actor,
            UpdateDocumentRequest request) {

        return data.compute(id, (key, before) -> {
            if (before == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document missing"
                );
            }

            if (!before.ownerId().equals(actor.userId())
                    || !before.tenantId().equals(actor.tenantId())) {
                throw new AccessDeniedException(
                    "Not owner or wrong tenant"
                );
            }

            if (before.state() != Document.State.DRAFT) {
                throw new AccessDeniedException(
                    "Only DRAFT can be edited"
                );
            }

            // Critical allowlist: preserve ALL sensitive fields
            // from the server record, update only the two content fields.
            return new Document(
                before.id(),
                before.ownerId(),
                before.tenantId(),
                before.state(),
                before.sensitivity(),
                request.title(),
                request.description(),
                before.version() + 1
            );
        });
    }
}
```

In the demo, `ConcurrentHashMap.compute` performs the check and update **for the same key** in one atomic operation, useful for avoiding simple races between two edits. It is **not** a multi-table database transaction; when moving to JPA/SQL, use proper transactions, optimistic locking, and conditional updates.

**Key observation:** There is no `request.ownerId()`, `request.tenantId()`, `request.state()`, `request.sensitivity()`, or `request.version()` because the request DTO **does not have** those properties. All of them are preserved from `before` (the server record).

### 7.9. Service with Functional Authority and Identity Checks

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentStore store;
    private final TrustedUserDirectory directory;

    public DocumentService(
            DocumentStore store,
            TrustedUserDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    @PreAuthorize("hasAuthority('document:edit')")
    public UpdateDocumentResponse update(
            long id,
            UpdateDocumentRequest request) {

        var authentication = SecurityContextHolder.getContext()
            .getAuthentication();

        Actor actor = directory.require(authentication);
        Document saved = store.updateContent(id, actor, request);

        return new UpdateDocumentResponse(
            saved.id(), saved.title(),
            saved.description(), saved.version()
        );
    }
}
```

`@PreAuthorize` checks authority **before running the body** when the service is called through a Spring proxy. `directory.require` verifies trusted identity; `DocumentStore` enforces object-level authorization and updates only two fields. All three mechanisms reinforce one another.

In production, place owner/tenant/state rules in a domain service or authorization policy suited to your repository and test every call path, rather than treating an in-memory `DocumentStore` as the sole security boundary.

### 7.10. Controller Accepting Only the Command DTO

**`src/main/java/demo/DocumentController.java`:**

```java
package demo;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @PutMapping("/{id}")
    public UpdateDocumentResponse replace(
            @PathVariable long id,
            @Valid @RequestBody UpdateDocumentRequest request) {
        return service.update(id, request);
    }
}
```

The controller **does not accept** a `Document` entity as `@RequestBody`, has no generic `saveEverything` API, and copies no unknown fields. Users wanting to change ownership must use a separate permission-checked workflow; `ownerId` cannot be smuggled into this API.

## 8. HTTP Testing with `MockMvc`: Verifying Multi-Layer Security

**`src/test/java/demo/DocumentApiSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DocumentApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentStore store;

    private static final String SAFE_JSON =
        "{\"title\":\"Updated\",\"description\":\"Allowed body\"}";

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void onlyEditableFieldsChange() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(11))
            .andExpect(jsonPath("$.title").value("Updated"))
            .andExpect(jsonPath("$.version").value(2))
            .andExpect(jsonPath("$.ownerId").doesNotExist())
            .andExpect(jsonPath("$.tenantId").doesNotExist());

        Document after = store.snapshot(11L);

        assertEquals(before.ownerId(), after.ownerId());
        assertEquals(before.tenantId(), after.tenantId());
        assertEquals(before.state(), after.state());
        assertEquals(before.sensitivity(), after.sensitivity());
        assertEquals(2L, after.version());
        assertEquals("Updated", after.title());
        assertEquals("Allowed body", after.description());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void rejectsOverpostingOfOwnerTenantAndSensitiveFields()
            throws Exception {

        Document before = store.snapshot(11L);

        String malicious = """
            {
              "title": "Attacker title",
              "description": "Modified by attacker",
              "ownerId": "u-bob",
              "tenantId": "T2",
              "state": "APPROVED",
              "sensitivity": "INTERNAL",
              "version": 999,
              "isAdmin": true
            }
            """;

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(malicious))
            .andExpect(status().isBadRequest());

        // Deserialization rejected it; no update occurred.
        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:edit")
    void rejectsEditingSomebodyElsesDocument() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:edit")
    void rejectsCrossTenantEdit() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void requiresEditAuthority() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void rejectsEditAfterApproval() throws Exception {
        Document before = store.snapshot(14L);

        mvc.perform(put("/api/documents/14")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(14L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:edit")
    void csrfProtectionStillApplies() throws Exception {
        Document before = store.snapshot(11L);

        mvc.perform(put("/api/documents/11")
                .contentType(MediaType.APPLICATION_JSON)
                .content(SAFE_JSON))
            .andExpect(status().isForbidden());

        assertEquals(before, store.snapshot(11L));
    }
}
```

Run in the project directory:

```bash
./gradlew test
```

On Windows PowerShell:

```bash
.\gradlew.bat test
```

If there is no Wrapper yet, generate one with a compatible Gradle version or use an installed `gradle test`. With the demo configuration, **all seven test cases are expected to pass**, each with a fresh ApplicationContext after the previous test is marked dirty. Do not fabricate millisecond timings or fake Gradle stdout since actual builds depend on the environment.

### 8.1. Expected HTTP Outcome Matrix

| User / Condition | Request | Expected HTTP | Record Modified? |
| --- | --- | ---: | --- |
| Alice has `document:edit` and is T1 owner | Only `title`, `description` | `200` | Only two fields; version increments |
| Alice has `document:edit` | Also sends `ownerId`, `tenantId`, `state`, `sensitivity`, `isAdmin` | `400` | No |
| Bob has `document:edit` | Edits Alice's document | `403` | No |
| Carol has `document:edit` but belongs to T2 | Edits Alice's T1 document | `403` | No |
| Alice only has `document:read` | Edits her own document | `403` | No |
| Alice has `document:edit` | Edits a record already `APPROVED` | `403` | No |
| Alice has `document:edit` | PUT without CSRF token | `403` | No |

Note that HTTP statuses for authentication errors in real systems also depend on entry point mechanisms (Basic/Bearer/session), exception handling, and avoiding object existence leaks. The demo uses `403` for policy deny and `400` for JSON requests with fields outside the DTO.

### 8.2. Results More Important Than HTTP Status Codes

After a request attempting to set `ownerId = u-bob` and `tenantId = T2`, what must be verified is that **the actual stored data** still has:

```text
document 11:
  ownerId     = u-alice
  tenantId    = T1
  state       = DRAFT
  sensitivity = RESTRICTED
  version     = 1
```

In the valid request case, only `title` and `description` change, while `ownerId`, `tenantId`, `state`, and `sensitivity` remain unchanged and `version` is incremented by the server to `2`.

**Do not assert only `HTTP 403`/`HTTP 400`.** If the system mutates the DB first and throws an exception afterward, you still have a vulnerability. Always read back the record's state, including after validation errors, policy denials, and transaction rollbacks.

## 9. Why This Works Even When Jackson Ignores Unknown Fields

Two independent mechanisms:

- **DTO allowlist**: the request lacks `ownerId` and `tenantId` properties, and the service has no way to read them from the DTO. Even if the JSON parser ignores unknowns, those values never enter the domain update.
- **Strict unknown-field handling**: in the demo, the parser fails with `400` immediately when JSON declares a field outside the contract, surfacing attacks/bugs with zero updates.

Suppose another endpoint does not enable `FAIL_ON_UNKNOWN_PROPERTIES`: the DTO and service mapping still block assigning fields outside the allowlist. Conversely, an endpoint deserializing an entity with an `ownerId` setter is **not helped** by strict-unknown because the field is already defined. Hence **DTO + service policy is the primary defense**; strict parsing is complementary.

### Payloads You Should Test

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "ownerId": "u-attacker"
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "tenantId": "other-tenant",
  "state": "APPROVED"
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "role": "ADMIN",
  "authorities": ["ROLE_ADMIN"],
  "isAdmin": true
}
```

```json
{
  "title": "Allowed",
  "description": "Allowed",
  "audit": {
    "createdBy": "attacker",
    "approvedBy": "attacker"
  }
}
```

On a strict endpoint, all four payloads must be rejected due to unknown fields. On a lenient endpoint, all unknown fields must still **never be persisted**. Nested objects need separate tests if the request DTO contains nested structures.

## 10. How to Handle Legitimate Owner or Tenant Transfers

Do not expand a generic `UpdateDocumentRequest` into:

```java
// DESIGN TO AVOID:
record UpdateDocumentRequest(
    String title,
    String description,
    String ownerId,
    String tenantId,
    String state
) {}
```

Replace with **dedicated use cases**, for example:

```text
PUT  /api/documents/{id}            -> edit title/description
POST /api/documents/{id}/transfer    -> transfer owner, document:transfer permission
POST /api/documents/{id}/approve     -> approve, document:approve permission
POST /api/documents/{id}/classify    -> change sensitivity, document:classify permission
```

### 10.1. Ownership Transfer Command

Dedicated command:

```java
public record TransferOwnershipRequest(String newOwnerId) {
}
```

Service fragment:

```java
// DESIGN SNIPPET, assumes repository/policy/transaction exist.
@PreAuthorize("hasAuthority('document:transfer')")
@Transactional
public void transferOwner(
        long documentId,
        TransferOwnershipRequest request) {

    Document before = documentRepository.requireForUpdate(documentId);
    var actor = trustedDirectory.currentActor();

    transferPolicy.requireCanTransfer(
        actor, before, request.newOwnerId()
    );

    // Policy verifies the new owner exists and belongs to a valid tenant.
    documentRepository.transferOwner(
        documentId, before.tenantId(), request.newOwnerId()
    );

    audit.recordOwnershipTransfer(
        actor.userId(), documentId,
        before.ownerId(), request.newOwnerId()
    );
}
```

This is **not a runnable demo file**; `documentRepository`, `trustedDirectory`, `transferPolicy`, `audit`, transactions, and these methods are components to build in the product.

**The `document:transfer` authority is insufficient without checking the target object.** Business policy must evaluate actor, current owner, tenant, state, target owner, maker–checker restrictions, and audit. If the new owner is in another tenant, a dedicated migration workflow may be required rather than just swapping `ownerId`.

### 10.2. Tenant Transfer Is Even More Sensitive Than Owner Transfer

`tenantId` is usually a **security boundary and data partition**. Changing tenants can affect:

- User memberships and authorities.
- `ACL`/SID/object identities, cache keys, and document shares.
- Encryption keys, data residency, and file storage buckets.
- Foreign keys and relations to projects/customers in the old tenant.
- Indexes/unique constraints, audit trails, and billing.
- Search indexes, events, analytics, and replicas.

Therefore, **never** allow changing `tenantId` via a setter in a generic update. Use a verified migration/transfer workflow, transaction, or saga and preserve tenant invariants after each step.

### 10.3. Self-Approval by Setting State

In approval systems, `state = APPROVED` is not a normal "field edit". It is a **business transition** requiring `document:approve`, prior-state checks, maker–checker, idempotency, auditing, and transactional conditions. Use a method like `approveDocument(id)` instead of putting `state` into the content-editing DTO.

## 11. PATCH and JSON Merge Patch: Another Attack Surface

A PATCH API can receive client-controlled **paths**:

```json
[
  {"op": "replace", "path": "/title", "value": "New title"},
  {"op": "replace", "path": "/ownerId", "value": "u-attacker"}
]
```

With JSON Patch (RFC 6902), never apply the entire patch directly to an entity and save. Check **the list of permitted paths** and valid operations before applying.

Design fragment example:

```java
private static final Set<String> EDITABLE_PATHS =
    Set.of("/title", "/description");

// ILLUSTRATIVE SNIPPET; validate op/value, JSON Pointer,
// duplicates, and nested paths per your actual patch library.
if (!EDITABLE_PATHS.contains(operation.getPath())) {
    throw new AccessDeniedException(
        "Forbidden patch path"
    );
}
```

Watch out for JSON Pointer escaping `~0` and `~1`, Unicode, array indexes, and path nesting; do not merely check `startsWith("/title")` as it might expose unintended fields. Parse/normalize paths with a vetted library, whitelist **exact paths**, and apply to a command DTO rather than mutating sensitive entities.

With JSON Merge Patch (RFC 7396), `null` can mean **remove property**. Explicitly define whether `null` means "keep", "delete", or "invalid" per field. Never let nested payloads like `{"owner":{"id":"..."}}` silently create a new owner relation.

## 12. ORM/JPA, MapStruct, and Defense-in-Depth Mechanisms

### 12.1. JPA Entities Are Not Input Contracts

In JPA/Hibernate, use:

```java
// SNIPPET: after loading managed entity and authorizing.
entity.setTitle(request.title());
entity.setDescription(request.description());
```

Never call `entityManager.merge(detachedFromRequest)` when the detached object comes straight from JSON and contains fields the client may not edit. Merging can inject unwanted state into the managed entity.

### 12.2. `BeanUtils` and Generic Mappers

`BeanUtils.copyProperties(source, target)` by default copies properties with matching names and compatible types. If an input DTO accidentally gains `ownerId`, an automatic copy can update the owner without anyone touching service code.

You can allowlist via mapper:

```java
// Mapper design SNIPPET: assign only permitted fields.
target.setTitle(request.title());
target.setDescription(request.description());
```

MapStruct can be configured with `@BeanMapping(ignoreByDefault = true)` and explicit `@Mapping` only for permitted fields, though you must inspect generated code and test when models change. Generic reflection mappers must never replace field-level policies.

### 12.3. Sensitive Fields Inside Nested Objects

Even when a DTO lacks top-level `ownerId`, a nested DTO like `ProjectUpdateRequest { User owner; }` or `DocumentUpdateRequest { Organization tenant; }` can open a path to alter IDs via nested binding. Keep nested input DTOs strictly **allowlisted**, limiting depth, collection sizes, and property paths.

For `@ModelAttribute`, `setAllowedFields("title","description")` does not cover JSON; for JSON, dedicated request DTOs and server mapping remain central.

### 12.4. Database Constraints and Auditing

Supporting mechanisms:

- `NOT NULL`, foreign keys, CHECK, and unique constraints for data validity.
- ORM `@Version`/optimistic locking to prevent lost updates—**does not grant permissions**.
- DB Row-level security (RLS) where appropriate to limit the blast radius of tenant query bugs.
- Triggers/audit logs for changes to sensitive fields.
- Least-privilege DB accounts; separate privileges for altering ACLs, owners, and tenants.
- Database policies/conditional UPDATEs to bind owner/tenant at write time.

**Database constraints check validity; they do not replace business authorization.** `ownerId = "u-attacker"` may point to a valid existing user yet still be an unauthorized privilege transfer.

## 13. Multi-Tenancy, Caching, and TOCTOU

### 13.1. Tenant Must Come from Verified Identity

Never take:

```java
// UNTRUSTED if tenant is self-declared by the client.
String tenant = request.getHeader("X-Tenant");
```

and use it to select the entire access scope. A header may be verified in a specific gateway architecture, but **never trust it by default**. If the application lets users choose their active workspace tenant, verify the user holds membership/role in the chosen tenant.

In the demo, `TrustedUserDirectory` maps the authentication name to a server-owned Actor and tenant. `DocumentStore` compares against the real record's tenant before updating.

### 13.2. Concurrent Database Writes

Suppose:

```text
T1: alice is allowed to edit document #11 when owner=u-alice, tenant=T1
T2: admin transfers document #11 to bob
T1: overwrites content using the stale permission decision
```

This is **TOCTOU**. In a relational DB, one solution is a conditional UPDATE:

```sql
UPDATE documents
SET title = :newTitle,
    description = :newDescription,
    version = version + 1
WHERE id = :id
  AND owner_id = :trustedActorId
  AND tenant_id = :trustedTenantId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

This is **illustrative SQL**; bind parameters safely via your DB driver. Check the updated row count: 1 = success, 0 = state, permission, or version no longer matches. Do not distinguish the exact cause in a way that automatically discloses object existence to unauthorized users.

Transaction isolation, row locks, optimistic locking, and outboxes may be required when invariants span multiple tables or services. `@Transactional` alone does not guarantee all checks run in a workflow-safe snapshot.

### 13.3. Permission-Aware Caching

Never cache `canEdit(documentId)=true` globally across users. The decision depends on:

```text
(principalId, tenantId, documentId, action, policyVersion)
```

When owner/tenant/ACL/role/state changes, invalidate caches appropriately. If a response cache keys only by URL without identity/authorization scope, another user may receive updated data or metadata they are not permitted to see.

A simple rule: **do not cache write-authorization decisions for long without guaranteeing revocation and owner-transfer invalidation**.

## 14. Common Bugs and Detection Signs

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Client sends `ownerId` and DB changes owner | Entity binding / copying all properties | Request DTO allowlist, explicit server mapping |
| `tenantId` changes when editing title | Generic update / unrestricted JSON Patch | Server-derived tenant, omit tenant from update DTO |
| `@PreAuthorize` exists yet role/state still changes | Checking functional authority only | Field-level policy + separate sensitive endpoints |
| DTO lacks owner but service accepts `Map<String,Object>` | Secondary mapping bypasses DTO | Ban generic entity binding in services |
| Form update exploited via `profile.roles[0]` | Overly broad `@ModelAttribute` binder | Dedicated form DTO / `allowedFields` |
| `@InitBinder` set yet JSON still binds sensitive fields | Confusing form binder with `@RequestBody` Jackson | JSON DTO + Jackson policy |
| Jackson ignores unknown `ownerId` and returns 200 | Unknown fields being ignored | Optionally enable strict unknown fields; keep DTO allowlist |
| Strict unknown enabled yet owner still changes | DTO/entity still declares `ownerId` | Shrink DTO and mapping, don't rely solely on strict mode |
| `@JsonIgnore` set yet a job still changes owner | Annotation only applies to JSON binding | Service/domain authorization |
| `@Column(updatable=false)` yet another query changes tenant | Another DB/ORM layer still has access | Policy + DB permissions/constraints |
| User with same role edits another tenant's record | Missing object/tenant policy | Check owner + tenant on DB record |
| Legitimate owner transfer blocked everywhere | No dedicated transfer workflow | Endpoint/command with `transfer` permission and audit |
| `@PostAuthorize` checks after update | Side effects occur before deny | Pre-method check and DB guard |
| PATCH modifies `/role` or `/ownerId` | Patch applied straight to entity | Whitelist normalized paths/actions |
| Mass assignment via nested properties | Overly broad nested DTOs | Allowlists on nested DTOs/collections too |
| `403` test passes yet owner still changed | Mutation happened before throwing exception | Assert DB state unchanged after error |
| Revoked permission can still update | Stale cache / TOCTOU | Invalidate and use conditional DB updates |
| Self-invocation skips `@PreAuthorize` | Spring AOP proxy bypassed | Separate secured bean, test through proxy |

### Code Review Checklist

1. Does the endpoint accept a JPA entity/model directly as `@RequestBody` or `@ModelAttribute`?
2. Does the request DTO contain any field the client is not allowed to modify, including nested DTOs and collections?
3. Does the mapper use `copyProperties`, `merge`, reflection, generic JSON patch, or `Map<String,Object>`?
4. Does the service load the real record itself and check owner/tenant/state before updating?
5. Are actor and tenant taken from verified `Authentication`/directory rather than an untrusted request?
6. Is `@EnableMethodSecurity` enabled, do callers go through the proxy, and does the policy check object-level authorization?
7. Do owner transfers, tenant transfers, approval transitions, roles, and classifications have dedicated workflows/authorities?
8. After a rejected request, is DB state **guaranteed unchanged**?
9. Could a newly added entity field accidentally appear in the input contract?
10. Are there races between permission checks and UPDATEs? Could permission caches go stale after owner transfer?
11. Are validation, CSRF, error handling, request size limits, and auditing appropriate for the API?
12. Are negative tests present for malformed JSON, unknown fields, missing authority, cross-tenant, wrong owner, and approved state?

## 15. Exercises and Self-Assessment Questions

1. **How does mass assignment differ from a client trying to send a non-existent JSON field?**  
   Mass assignment is dangerous when a field is **bound and used to update state** despite the use case disallowing it. An unknown JSON field is merely a probing attempt; if ignored, no mutation occurs.

2. **With `@PreAuthorize("hasAuthority('document:edit')")` present, why is a DTO still needed?**  
   Because functional authority does not specify which fields a user may edit; the DTO allowlist restricts the input contract.

3. **Why not accept `ownerId` from the client in the title-editing API?**  
   Ownership transfer is a distinct sensitive operation requiring authorization, auditing, and recipient verification.

4. **Does `@InitBinder#setAllowedFields` block JSON in `@RequestBody`?**  
   No. It protects form/`@ModelAttribute` property binding; JSON requires DTOs, Jackson configuration, and service mapping.

5. **Is enabling `FAIL_ON_UNKNOWN_PROPERTIES` enough to prevent mass assignment?**  
   No. If the DTO declares a sensitive property, it is no longer unknown. You must shrink the DTO and mapping.

6. **What if the request carries `tenantId="T2"` while the JWT shows the user belongs to T1?**  
   Never trust a request-declared tenant. The content-edit API should not accept tenant; verify the authenticated tenant against the server record.

7. **Does `@Column(updatable=false)` replace field authorization?**  
   No. It only affects one ORM write path and does not protect all update routes or entity mapping.

8. **Why should the URL `id` and payload `id` not be allowed to differ arbitrarily?**  
   It can easily update the wrong object, cause IDOR, or create duplicate identity ambiguity. Ideally the content-edit payload carries no ID; the service looks up by path ID and authorizes that record.

9. **Can a user with content-edit permission change `state` to `APPROVED` via JSON?**  
   No. They must call the approval use case with its own permission and state-transition policy.

10. **If a test receives 403 yet the data already changed owner before the error, is it safe?**  
    No. You must read back state, confirm zero mutation, and check transaction rollback/ordering.

11. **What if the owner changes right after the check but before the DB write?**  
    That is TOCTOU. Use appropriate conditional UPDATEs, locks, versions, and transactions, and check affected row counts.

12. **Why test allow cases too?**  
    Testing only denies does not prove legitimate updates work or that strictly those two fields change; both allow and deny cases are necessary.

13. **Is a mapper with `ignoreByDefault=true` sufficient on its own?**  
    It helps enforce mapping allowlists, but you still need object-level permission checks for the caller and separate guards for sensitive workflows.

14. **Can the `version` field be sent by the client?**  
    It can be sent as `expectedVersion` for concurrency checks, but never let clients arbitrarily set `entity.version`.

15. **Is a form containing `owner.address.city` safe if top-level only allows `owner`?**  
    Never assume so. Property paths/nested binding need granular allowlists; best practice is a dedicated input DTO without an owner relation if editing it is not required.

## 16. Official References

- [Spring Framework — Web MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): risks of binding untrusted objects, dedicated objects, constructor binding, `allowedFields`, and declarative binding.
- [Spring Framework — `@ModelAttribute` binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): form binding, constructor/field mapping, and limits of property binding.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserializing HTTP bodies via message converters and validation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, service proxies, and expression-based authorization.
- [Spring Boot 3.5 — Spring Security](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): Boot security defaults and enabling method security.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF tokens for state-changing requests.
- [Spring Security — Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): security testing and MockMvc integration.
- [OWASP — API Security: Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/): property-level authorization and mass assignment.
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): allowlists, input DTOs, and defense strategies.

**Conclusion:** Preventing mass assignment is not just hiding one field with Jackson or adding a generic `@PreAuthorize`. You need a combination of **request DTO allowlists**, **explicit field mapping**, **functional and record-level permissions**, **server-side identity/tenant**, **dedicated workflows for sensitive fields**, **post-error state testing**, and **consistent DB write constraints**. Content-editing APIs should edit only content; `ownerId`, `tenantId`, state, permissions, and audit fields must only change through explicitly authorized use cases.