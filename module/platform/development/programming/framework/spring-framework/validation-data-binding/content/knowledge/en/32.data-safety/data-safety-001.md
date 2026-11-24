# Mass Assignment Risks When Binding Directly to Entities in Spring MVC

## 1. The Security Problem: Which Properties Is a Request Allowed to Modify?

When a user updates their profile, the UI may display only two fields: `displayName` and `email`. However, the Java entity persisted in the database also contains sensitive fields such as `role`, `verified`, `tenantId`, `accountBalance`, or `ownerId`.

If the controller binds HTTP data directly to that entity, a request sender can **inject parameters that do not appear in the UI**:

```text
POST /accounts/1
Content-Type: application/x-www-form-urlencoded

displayName=Alice&email=alice@example.test&role=ADMIN&verified=true
```

If the entity has corresponding writable properties, the binding mechanism can write `role=ADMIN` and `verified=true` into the entity, even though regular users are not allowed to modify these two fields.

That is **mass assignment** (also known as *over-posting* or *autobinding vulnerability*): client-controlled data is mapped onto more object properties than are actually authorized. OWASP classifies this vulnerability category under CWE-915 — *Improperly Controlled Modification of Dynamically-Determined Object Attributes*.

**Fundamental principle:** Being *bindable* does not mean the caller is *authorized to modify* a field. A model/domain entity should not become the HTTP API input contract merely because the framework can automatically assign properties.

This lesson focuses on **Spring MVC data binding**, specifically when form/query parameters are bound via `@ModelAttribute` onto a **JPA entity**. Differences with `@RequestBody` JSON, constructor binding, validation, authorization, and dirty checking are also covered to avoid defending at the wrong layer.

## 2. How Does Mass Assignment Happen in Spring MVC?

### 2.1. @ModelAttribute and property binding

A controller can be written very concisely:

```java
@PostMapping("/accounts/{id}")
public String update(@ModelAttribute Account account) {
    repository.save(account);
    return "ok";
}
```

This is a **dangerous illustration**, not a recommended approach and not a standalone Java file. If `Account` is a JPA entity containing setters for role, verified, balance, or owner, the API is accepting input in the shape of the entire entity rather than only the fields allowed for update.

By standard mechanism, `@ModelAttribute` uses `WebDataBinder` to extract data from the request and apply constructor binding or property binding. With property binding, request parameter names can match Java property names.

For example:

```text
request parameter       Java bean property
--------------------    ---------------------------
displayName=Alice    -> account.setDisplayName("Alice")
email=a@example.org  -> account.setEmail("a@example.org")
role=ADMIN           -> account.setRole(Role.ADMIN)
verified=true        -> account.setVerified(true)
```

The data does not need to be present in the HTML form. A client can craft the request via curl, a modified browser, or an API client.

### 2.2. An Entity Already Loaded in the Model Is Even More Dangerous

Spring supports loading a model object before the controller handler executes:

```java
@ModelAttribute("account")
public Account load(@PathVariable("id") long id) {
    return repository.findById(id).orElseThrow();
}

@PostMapping("/accounts/{id}")
public String update(
        @ModelAttribute("account") Account account) {

    repository.save(account);
    return "saved";
}
```

This is an illustrative snippet requiring imports, a class, and a repository. The first `@ModelAttribute("account")` method places the entity into the Model, and then the handler's `@ModelAttribute("account")` argument can retrieve that exact object and bind request parameters onto it.

Because the entity already holds values from the database, sensitive setters can be invoked before business update code even begins. If the entity is still **managed** in a transaction's JPA persistence context, dirty checking can even detect and flush changes that the code did not intentionally make.

In another scenario, the entity is detached, yet `repository.save(entity)` can merge and persist the values modified by binding. **Do not assume every form binding automatically persists**: you must inspect the entity lifecycle, transaction boundaries, and actual `save`/flush calls.

### 2.3. Nested property paths widen the attack surface

If the form object has nested properties and accessors/collections support binding, parameter names can look like:

```text
shippingAddress.city=Hanoi
owner.id=99
items[0].unitPrice=0
permissions[0].enabled=true
```

These are **hypothetical paths** and do not imply every entity can bind them. Feasibility depends on the object graph, writable properties, auto-grow, converters, collections, and binder configuration.

Nevertheless, it demonstrates that the risk is not limited to a single flat column. When binding an entity with JPA associations, data about owner, tenant, permissions, or pricing may lie deep in the object graph. Using a flat, purpose-built DTO and mapping only approved fields is an effective way to reduce the attack surface.

## 3. Why Can't Spring Automatically Know Which Fields Are Editable?

Spring can know:

- Property `role` exists and its type is `Role`.
- String `ADMIN` can be converted to enum `Role.ADMIN`.
- Setter `setRole(Role)` permits writing.
- Bean Validation can evaluate constraints on the property.

From those facts alone, however, the framework **does not know** whether the caller is a guest, the account owner, a support agent, or an administrator; nor does it know whether this request is only permitted to change the email or is allowed to change the role.

This is the boundary between **binding capability** and **authorization policy**.

| Mechanism | What does it decide? | Does it block mass assignment on its own? |
| --- | --- | --- |
| Java setter | Whether a property can be changed from Java code | No |
| `@ModelAttribute` | Transfers request values onto an object | No, if the object is too broad |
| `@Valid` / `@Validated` | Whether values satisfy constraints | Does not decide what the caller may edit |
| `@NotNull`, `@Email` | Structure or conditions on values | No |
| `@Column(updatable=false)` | Affects JPA SQL update for one column | Not a complete authorization boundary |
| `@JsonIgnore` | Jackson JSON serialization/deserialization behavior | Does not protect `@ModelAttribute` property binding |
| Dedicated input DTO | Narrows properties receivable from HTTP | Strongly helpful, but still needs authorization |
| `WebDataBinder#setAllowedFields` | Restricts property names in property binding | Helpful for the configured binder |
| Service authorization | Whether the caller can edit the specific resource and fields | Essential |
| Database constraints | Enforces certain persisted invariants | Complementary, does not replace authorization |

A role `ADMIN` is valid in terms of type and enum value, yet completely **unauthorized** if supplied by the user themselves. Validation only detects invalid structure or declared constraints; it does not resolve the legitimacy of an operation on its own.

## 4. Four Primary Defenses in Priority Order

### 4.1. Prefer input DTOs; do not use JPA entities as form objects

If a request is only allowed to edit `displayName` and `email`, create a DTO with only those two fields:

```java
public class ProfileUpdateForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    // Default constructor and getters/setters for these two properties.
}
```

The DTO **does not have** `role`, `verified`, `tenantId`, `accountBalance`, or `ownerId`. A `role` parameter sent by the client has no matching property in the DTO to map onto.

The service loads the entity by ID and updates only the permitted attributes:

```java
@Transactional
public void updateProfile(long accountId, ProfileUpdateForm form) {
    Account account = repository.findById(accountId)
        .orElseThrow();

    // Verify that the caller has permission to update accountId here.
    account.setDisplayName(form.getDisplayName());
    account.setEmail(form.getEmail());
}
```

This is an integration fragment requiring appropriate dependencies and context access. Do not rely on `BeanUtils.copyProperties(form, account)` as a security guarantee if source/target can grow unchecked; **explicit assignment** makes the list of allowed fields clear during code review.

### 4.2. Use allowedFields when property binding is still required

Register a local `@InitBinder`:

```java
@InitBinder("profile")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}
```

And the corresponding model attribute:

```java
@PostMapping("/accounts/{id}")
public String update(
        @Valid @ModelAttribute("profile") ProfileUpdateForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

These are two fragments of a controller. `@InitBinder("profile")` restricts the binder for the model attribute named `profile`. `setAllowedFields` provides an **allowlist** for property binding; disallowed input fields can be recorded in `BindingResult#getSuppressedFields()`.

For example:

```java
if (errors.getSuppressedFields().length > 0) {
    // Explicitly reject requests with disallowed properties.
}
```

**You must explicitly return an error** when suppressed fields exist if the API intends to reject over-posting. Spring can silently ignore fields outside the allowlist; do not assume every suppressed field produces a `FieldError` or HTTP 400.

An allowlist is better than a denylist because adding a new sensitive property to the entity will **not automatically open it for binding**. Conversely, if you only block `role` with `setDisallowedFields("role")`, a later addition of `verified` or `adminComment` could easily be missed.

### 4.3. Constructor-only binding when appropriate

Spring Framework 6.1+ supports declarative binding mode:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

According to the MVC documentation, when this flag is enabled:

- Constructor binding is still used according to the model object's design.
- Property binding is not performed unless explicit `allowedFields` are configured.
- With an immutable DTO/record whose constructor accepts only valid fields, this adds a useful layer of defense.

An input record:

```java
public record ProfileInput(
    @NotBlank String displayName,
    @NotBlank @Email String email
) {}
```

Carries neither `role` nor `verified` in its constructor. However, **constructor binding does not by itself make an entity safe to use as a DTO**: if the entity's constructor accepts sensitive fields, those fields can still be populated from the request. It is the design of the **input type** that determines safety.

`setAllowedFields` primarily restricts **property binding**, not every argument passed into a primary constructor. Do not apply an allowlist as a blanket shield for an entity whose constructor accepts privileged data.

### 4.4. Authorization and safe mapping in the service layer

After binding, the server must:

- Determine the **true identity** from the authentication context, not from a client-supplied `userId` or `tenantId` parameter.
- Verify the caller is authorized to update that **specific entity ID**.
- Verify permission to edit **each group of attributes** if different roles exist.
- Update only approved attributes and use an appropriate transaction.
- Enforce database constraints, optimistic locking, audit logs, or other policies as required by the system.

**DTOs and allowlists do not replace object-level access control** (IDOR/BOLA). A user can submit a completely valid DTO while targeting someone else's `/accounts/2`. That is a separate authorization vulnerability and must be blocked independently.

## 5. Distinguishing @ModelAttribute Form Binding from @RequestBody JSON

A common mistake is configuring `setAllowedFields(...)` in `@InitBinder` and assuming it blocks JSON properties. In reality:

| Request format | Primary mechanism | Core defense |
| --- | --- | --- |
| `application/x-www-form-urlencoded` with `@ModelAttribute` | `WebDataBinder` and conversion service | DTO + allowedFields/declarativeBinding |
| Query parameters into `@ModelAttribute` | `WebDataBinder` | DTO + allowedFields |
| `@RequestBody SomeEntity` with JSON | `HttpMessageConverter`/Jackson deserialization | Input DTO/Jackson rules + service mapping |
| `@RequestPart` JSON | HTTP message converter for the body part | Dedicated DTO and validation |
| Direct `@RequestParam Long id` | Argument resolver | Type conversion + validation + authorization |
| Server fetches entity from repository | JPA/repository | Check permissions before updating, do not bind arbitrarily |

With JSON:

```java
@PostMapping("/accounts/{id}")
public ResponseEntity<?> update(
        @PathVariable long id,
        @Valid @RequestBody ProfileUpdateRequest body) {
    // Only map allowed fields from the body.
    return ResponseEntity.noContent().build();
}
```

This is a fragment requiring a DTO and imports. When Jackson deserializes JSON directly into an entity that has a `setRole` setter, mass assignment **can still occur**, but through the **JSON deserialization** path rather than the `@ModelAttribute` property binder.

### Annotations that protect at the wrong layer

- `@JsonIgnore` or `@JsonProperty(access = READ_ONLY)` affects Jackson, not the property binding mechanism of `@ModelAttribute`.
- `@Column(updatable = false)` can restrict a column when JPA generates SQL UPDATE, but does not prevent in-memory object mutation, other side effects, or other sensitive columns.
- `@Transient` is a persistence mapping concept, not an allowlist of fields HTTP is permitted to update.
- `@Valid` checks constraints; `role=ADMIN` can still be a valid enum value.
- Simply omitting a field from the HTML form or hiding an input is not a defense. Clients are not forced to follow the UI.

To accept JSON safely, use an input DTO/record with a minimal set of fields, validation, and explicit service mapping. If you want to reject JSON containing unknown fields, configure Jackson to fail on unknown properties as part of a separate contract; this behavior differs from `BindingResult#getSuppressedFields()` in the MVC form binder.

## 6. JPA: Why Do Mistakes Also Lead to Persisted Changes?

### 6.1. Persistence context and dirty checking

When an entity is **managed** within a JPA persistence context, calling setters alters its state. When the transaction commits or flushes, the JPA provider can detect changes and execute SQL UPDATEs.

Therefore, the risk is not limited to an explicit `repository.save(...)` call. If a managed entity was bound earlier in a request/transaction flow, controlling updates becomes harder to reason about. You should not rely on "this code doesn't call save" to conclude an entity will never be persisted.

**However:** whether an entity is managed or detached depends on transaction boundaries, `OpenEntityManagerInView`, repository methods, and how the entity was loaded. A request does not automatically flush every modified object. Analyze the exact persistence flow before asserting impact.

### 6.2. Associations and tenant boundaries

An entity might contain:

```java
@ManyToOne
private Organization owner;

@Enumerated(EnumType.STRING)
private Role role;

private boolean approved;
```

This is a JPA fragment. Allowing clients to bind properties directly across the object graph can introduce risks of changing ownership relationships or approval state depending on mapping and binder configuration.

Do not take `ownerId`/`tenantId` from the request and trust it as the authorization context. Derive the tenant from the principal/server-side context, scope every lookup by tenant, and permit only valid associations.

### 6.3. Invariants and concurrency

Even a DTO with the exact right fields still needs protection for invariants such as server-calculated totals, unique constraints, inventory limits, and state transitions. Checks like `@Min(0)` only validate a single value, not against double-spend or stale writes. Use transactions, optimistic locking, database constraints, or domain methods as needed.

## 7. Hands-On Lab: Java 17 + Spring Boot 3.5.6 + JPA/H2

The goal is to observe **directly** the difference between dangerous entity binding and a controlled DTO. The application uses an in-memory H2 database and seeds a demo account:

```text
id=1
displayName=Alice
email=alice@example.test
role=USER
verified=false
```

There are three endpoints:

1. `GET /lab/accounts/1` — reads account state via a response DTO to observe effects.
2. `POST /lab/accounts/1` — **the safer approach**, accepts `ProfileUpdateForm` and updates only `displayName`/`email`; extra properties are rejected.
3. `POST /lab/unsafe/accounts/1` — **an intentionally unsafe lab path**, binds the request directly onto the loaded entity to reproduce the vulnerability. Never deploy this endpoint in a real application.

To reduce the chance of accidental deployment, the controllers are annotated with `@Profile("lab")`, the server binds only to loopback `127.0.0.1`, and data uses in-memory H2. There is no authentication/authorization in this lab, so **even the DTO demo endpoint is not yet a complete production application**.

### 7.1. File structure

```text
mass-assignment-lab/
├── pom.xml
└── src/main/
    ├── java/demo/massassign/
    │   ├── MassAssignmentApplication.java
    │   ├── Account.java
    │   ├── AccountRepository.java
    │   ├── ProfileUpdateForm.java
    │   ├── AccountView.java
    │   ├── ProfileService.java
    │   ├── SafeAccountController.java
    │   └── UnsafeAccountController.java
    └── resources/
        └── application.properties
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>mass-assignment-lab</artifactId>
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
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
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

Each starter serves a distinct role: MVC/web, Bean Validation, and JPA. H2 is an embedded test database requiring no external database installation.

### 7.3. application.properties

```properties
# Run the lab on loopback only; do not expose it to the network.
server.address=127.0.0.1
server.port=8080

spring.datasource.url=jdbc:h2:mem:massassignment;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`ddl-auto=create-drop` is only suitable for demos/tests. It drops data when the context closes; never copy this setting for a production database. `open-in-view=false` avoids keeping the persistence context open across the entire HTTP request, though it does not replace DTOs or authorization.

### 7.4. MassAssignmentApplication.java

```java
package demo.massassign;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MassAssignmentApplication {

    public static void main(String[] args) {
        SpringApplication.run(MassAssignmentApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(AccountRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.save(new Account(
                    "Alice",
                    "alice@example.test",
                    Account.Role.USER,
                    false
                ));
            }
        };
    }
}
```

With a fresh H2 database and no other records, the first record typically receives ID `1`. If a real project already has other data, you must use the actual ID; the commands below assume a clean lab environment.

### 7.5. Account.java — entity with sensitive fields

```java
package demo.massassign;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {

    public enum Role {
        USER, ADMIN
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    private String email;

    @Enumerated(EnumType.STRING)
    @Column(name = "access_role", nullable = false)
    private Role role;

    private boolean verified;

    protected Account() {
    }

    public Account(
            String displayName,
            String email,
            Role role,
            boolean verified) {

        this.displayName = displayName;
        this.email = email;
        this.role = role;
        this.verified = verified;
    }

    public Long getId() {
        return id;
    }

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

    public Role getRole() {
        return role;
    }

    // This setter may be needed for an admin workflow, but that does not mean
    // a user's profile update request should be allowed to invoke it.
    public void setRole(Role role) {
        this.role = role;
    }

    public boolean isVerified() {
        return verified;
    }

    public void setVerified(boolean verified) {
        this.verified = verified;
    }
}
```

The entity intentionally includes setters for `role` and `verified` to reproduce mass assignment. In a real system, you can restrict public setters, use domain methods that enforce authorization, and ensure privileged changes go through a dedicated service. Still, **removing setters is not a standalone defense plan**: constructor binding, field access, or other JSON paths may still exist. You must still control the input boundary.

### 7.6. AccountRepository.java

```java
package demo.massassign;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
```

Spring Data JPA generates the implementation for this repository when the application context starts.

### 7.7. ProfileUpdateForm.java — input DTO with only two fields

```java
package demo.massassign;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class ProfileUpdateForm {

    @NotBlank
    private String displayName;

    @NotBlank
    @Email
    private String email;

    public ProfileUpdateForm() {
    }

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
}
```

**The key takeaway of this demo:** This DTO **does not contain** `role` or `verified`. Those fields have no valid path through the profile update form.

`@NotBlank` and `@Email` enforce basic input structure. They do not replace checking whether the caller has permission to update this account.

### 7.8. AccountView.java — response DTO

```java
package demo.massassign;

public record AccountView(
        long id,
        String displayName,
        String email,
        String role,
        boolean verified) {

    public static AccountView from(Account account) {
        return new AccountView(
            account.getId(),
            account.getDisplayName(),
            account.getEmail(),
            account.getRole().name(),
            account.isVerified()
        );
    }
}
```

A dedicated response DTO helps the application control which fields are exposed. The lab intentionally exposes `role`/`verified` for test observation; a real public API should decide independently which details may be disclosed.

### 7.9. ProfileService.java — intentional attribute updates

```java
package demo.massassign;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProfileService {

    private final AccountRepository repository;

    public ProfileService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AccountView read(long id) {
        return AccountView.from(load(id));
    }

    @Transactional
    public AccountView update(long id, ProfileUpdateForm form) {
        Account account = load(id);

        // In production, verify principal/tenant/owner here
        // before modifying properties.
        account.setDisplayName(form.getDisplayName());
        account.setEmail(form.getEmail());

        // Managed entity is dirty-checked by JPA when the transaction commits.
        return AccountView.from(account);
    }

    private Account load(long id) {
        return repository.findById(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
    }
}
```

The service invokes only two setters for a profile update. Because it runs inside a transaction, the entity loaded via the repository is managed within that transaction; JPA flushes the changes on commit. It does not copy the entire DTO/entity via reflection, nor does it update role/verified from the form.

**Demo limitation:** the comment about the principal is not an executed authorization step. The application runs locally solely to illustrate mass assignment; production must add Spring Security and ownership/tenant checks before updating.

### 7.10. SafeAccountController.java — form DTO + allowlist

```java
package demo.massassign;

import jakarta.validation.Valid;

import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("lab")
@RestController
@RequestMapping("/lab/accounts")
public class SafeAccountController {

    private final ProfileService service;

    public SafeAccountController(ProfileService service) {
        this.service = service;
    }

    @InitBinder("form")
    void configureForm(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @GetMapping("/{id}")
    public AccountView read(@PathVariable("id") long id) {
        return service.read(id);
    }

    @PostMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> update(
            @PathVariable("id") long id,
            @Valid @ModelAttribute("form") ProfileUpdateForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body("REJECTED_FIELDS");
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("INVALID_PROFILE");
        }

        return ResponseEntity.ok(service.update(id, form));
    }
}
```

**Three distinct layers of defense:**

1. `ProfileUpdateForm` exposes only the properties allowed to be edited; it has no role/verified.
2. `binder.setAllowedFields("displayName","email")` proactively restricts property binding. Extra HTTP parameters are suppressed, and the handler rejects the request with status 400.
3. The service copies only the two fields from the DTO to the entity; this is where authorization and tenant checks for the actual user must be added.

`BindingResult` must be placed **immediately after** `@ModelAttribute("form") ProfileUpdateForm form`. If another parameter is inserted in between, form error-binding rules no longer work properly. `@Valid` runs Jakarta Bean Validation, while `getSuppressedFields()` checks for fields disallowed by the binder.

**Never rely on a DTO "that has all fields plus @Valid" instead of an allowlist.** A property like `role` may be completely valid by type while still being off-limits to the caller.

### 7.11. UnsafeAccountController.java — intentionally flawed endpoint

```java
package demo.massassign;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@Profile("lab")
@RestController
@RequestMapping("/lab/unsafe/accounts")
public class UnsafeAccountController {

    private final AccountRepository repository;

    public UnsafeAccountController(AccountRepository repository) {
        this.repository = repository;
    }

    @ModelAttribute("account")
    public Account load(@PathVariable("id") long id) {
        return repository.findById(id).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Account not found"));
    }

    @PostMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public AccountView update(
            @ModelAttribute("account") Account account) {

        // UNSAFE: the entity has been property-bound directly.
        // The user may have already overwritten role / verified before reaching here.
        Account saved = repository.save(account);
        return AccountView.from(saved);
    }
}
```

This is an **intentionally vulnerable test fixture**: present only when running the `lab` profile, with no policy/allowlist and no input DTO. `@ModelAttribute("account")` creates/loads the model attribute from the repository; Spring MVC can bind request parameters onto that object before the `update` handler calls `save`.

If the request sends `role=ADMIN`, Spring has built-in enum conversion and `setRole` alters the value. `verified=true` is converted to boolean. `repository.save(account)` can persist those unauthorized values.

**Do not deploy or expose network access to this endpoint.** Its sole purpose is to demonstrate why HTTP must never bind directly to a domain entity.

### 7.12. Running the lab

Requires Java 17+ and Maven 3.x. In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run -Dspring-boot.run.profiles=lab
```

The application listens on `127.0.0.1:8080` per `application.properties`. With a fresh H2 database, the seed creates account ID 1 with role `USER` and `verified=false`.

**Run the steps in the order below** so the demonstration results are not affected by the intentionally unsafe action at the end.

#### Step A — check initial state

```bash
curl -s 'http://127.0.0.1:8080/lab/accounts/1'
```

The body contains these key values:

```json
{
  "id": 1,
  "displayName": "Alice",
  "email": "alice@example.test",
  "role": "USER",
  "verified": false
}
```

The fields above represent the logical data of the JSON response; property order and whitespace may vary depending on the Jackson serializer.

#### Step B — send role/verified to the safe endpoint

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice' \
  --data-urlencode 'email=alice@example.test' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'verified=true'
```

HTTP status **400 Bad Request**. The exact body explicitly returned by the handler is:

```text
REJECTED_FIELDS
```

Because `role` and `verified` are not in the binder's allowlist, they are suppressed; the handler checks `getSuppressedFields()` and rejects the entire request. It **does not** call `service.update`.

Run `GET /lab/accounts/1` again: `role` is still `USER` and `verified` is still `false`. This demonstrates the safe handling.

#### Step C — update profile per contract

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice Nguyen' \
  --data-urlencode 'email=alice.nguyen@example.test'
```

HTTP **200 OK**. The JSON response contains:

```json
{
  "id": 1,
  "displayName": "Alice Nguyen",
  "email": "alice.nguyen@example.test",
  "role": "USER",
  "verified": false
}
```

The service updated the two permitted properties, while `role` and `verified` remained unchanged from the database. JSON properties may be ordered differently depending on the serializer.

#### Step D — intentionally demonstrate the unsafe entity-binding path

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/unsafe/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice Nguyen' \
  --data-urlencode 'email=alice.nguyen@example.test' \
  --data-urlencode 'role=ADMIN' \
  --data-urlencode 'verified=true'
```

HTTP **200 OK**, yet this is a **dangerous** outcome, not a security success. The response shows:

```json
{
  "id": 1,
  "displayName": "Alice Nguyen",
  "email": "alice.nguyen@example.test",
  "role": "ADMIN",
  "verified": true
}
```

Because the data was bound directly onto the entity itself before calling `repository.save`, `role` and `verified` changed. This is textbook over-posting.

#### Step E — verify persisted state

```bash
curl -s 'http://127.0.0.1:8080/lab/accounts/1'
```

The response now reflects `role` as `ADMIN` and `verified=true`. That proves the data was not merely mutated transiently in the response object; the unsafe handler's `repository.save` persisted the change.

**Stopping and restarting the application** resets the in-memory H2 schema in the lab via `create-drop`, allowing you to retry from the initial account state.

#### Step F — invalid data validation

```bash
curl -i -X POST 'http://127.0.0.1:8080/lab/accounts/1' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=' \
  --data-urlencode 'email=not-an-email'
```

HTTP **400 Bad Request**, body:

```text
INVALID_PROFILE
```

This error comes from `@NotBlank`/`@Email` on the DTO. It differs from the case with suppressed fields, and both differ from account ownership checks.

The `curl -i` commands display headers and body; the JSON blocks illustrate key fields without asserting exact order or whitespace. When you have not yet verified at runtime, run the steps sequentially and verify HTTP status codes and database state against these expectations.

## 8. Comparing the Two APIs After the Lab

| Criterion | `POST /lab/unsafe/accounts/{id}` | `POST /lab/accounts/{id}` |
| --- | --- | --- |
| Request-receiving object | JPA `Account` | `ProfileUpdateForm` |
| Entity loaded before binding | Yes, via `@ModelAttribute` method | No; entity is loaded after validation in the service |
| `role`/`verified` present on input type | Setters exist on entity | Not present on DTO |
| Allowed fields | None | `displayName`, `email` |
| Over-posting handling | Undetected | Checks suppressed fields and returns 400 |
| Validation | No explicit DTO validation | `@Valid` on DTO |
| Mapping before persistence | Saves the bound entity | Explicit setters in service |
| Demo authorization | No | No, must be added before production |
| Result when client sends `role=ADMIN` | Can persist role ADMIN | Rejected, no update |
| Suitable for production | **No** | Better foundation, but still lacks authentication/authorization |

The lesson is not that every `@ModelAttribute` is dangerous. It becomes dangerous when **the binding target has more writable fields than the request is authorized to update**. A dedicated, well-scoped DTO that is properly validated and authorized is the right choice.

## 9. When You Truly Must Bind an Entity

Some legacy systems use entities directly in server-side forms. If you cannot refactor immediately, at minimum you must:

1. Create an `@InitBinder("account")` with `setAllowedFields(...)` listing **only approved fields**.
2. Use `setDeclarativeBinding(true)` where appropriate; inspect constructor properties separately.
3. Check `BindingResult#getSuppressedFields()` and reject invalid requests.
4. Keep `BindingResult` immediately after the form object to handle binding/type conversion errors.
5. Verify permissions on the ID/tenant from the server-side context.
6. Do not save/flush the entity if validation or authorization fails.
7. Write over-posting integration tests for every endpoint.
8. Plan a migration to DTOs, since a binder field allowlist does not cover every interaction path with an entity.

Legacy safeguard example:

```java
@InitBinder("account")
void restrict(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email");
}

@PostMapping("/accounts/{id}")
public ResponseEntity<?> update(
        @Valid @ModelAttribute("account") Account account,
        BindingResult errors) {

    if (errors.getSuppressedFields().length > 0) {
        return ResponseEntity.badRequest().build();
    }
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    // Still requires authorization and safe persistence mapping.
    return ResponseEntity.noContent().build();
}
```

This is a **conditional defensive fragment** for legacy code, not part of the complete runnable lab. If an `@ModelAttribute("account")` method loads the entity before the handler, note that the entity can be mutated **during binding**, before your code checks suppressed fields. It is better not to expose the entity to the binder at all.

If you need an entity reference for a view or domain operation and **do not want binding**:

```java
@ModelAttribute(binding = false) Account account
```

A handler can use a separate form DTO alongside an entity loaded from the model with `binding=false` to avoid binding the request onto that entity. Even then, ensure the model attribute is available, the ID source is trusted, and resource access permissions are verified.

## 10. @InitBinder, Scope, and Configuration Override Risks

`@InitBinder` inside a controller typically has local scope. `@ControllerAdvice` can apply binder rules across multiple controllers. However:

- `@InitBinder("profile")` runs only for the binder of the model attribute named `profile`.
- An unnamed `@InitBinder` applies more broadly and can easily affect unintended DTOs.
- Global configuration from `@ControllerAdvice` typically applies before local `@InitBinder` methods.
- `setAllowedFields(...)` is a **setter**; it does not automatically intersect with a previously set allowlist.
- A local setter running afterward can widen allowed fields and break the expectations of a global security policy.

Dangerous example:

```java
// Global advice restricted:
binder.setAllowedFields("displayName", "email");

// Local controller runs later and accidentally widens:
binder.setAllowedFields("displayName", "email", "role");
```

This is an illustrative fragment. Do not treat a global advice allowlist as an immutable policy if downstream binder customizations can still modify it.

It is best to place critical binding policies in configuration with clear ownership, scope them per DTO, and maintain regression tests ensuring sensitive fields can never be bound.

## 11. Solutions That Create a False Sense of Security

### 11.1. "Just add @Valid"

Incorrect. `@Valid` evaluates declared constraints; it does not know whether the user is allowed to escalate their role. For instance, an enum value `Role.ADMIN` is completely valid by type even if the request sender is not allowed to change it.

A DTO with a `role` field, `@NotNull`, and `@Valid` is still vulnerable to over-posting if the server trusts that role without authorization.

### 11.2. "Blocking role with disallowedFields is enough"

Not recommended. When the team adds `approved`, `verified`, or `tenantId` properties, the old denylist does not update itself. Both OWASP and Spring recommend preferring an **allowlist** whenever property binding is used.

### 11.3. "If there's no input in the HTML, nobody can send it"

Incorrect. The server does not receive an immutable copy of the UI form. Clients can construct arbitrary HTTP requests regardless of whether HTML controls are omitted, hidden, `readonly`, or `disabled`.

### 11.4. "Using @JsonIgnore alone is safe"

Insufficient. `@JsonIgnore` works with Jackson; form binding via `@ModelAttribute` does not use Jackson for property resolution. Even with JSON, you must check both serialization and deserialization settings alongside business authorization.

### 11.5. "We have @Column(updatable=false), so it's fine"

Incorrect. This JPA annotation only affects persistence SQL for the configured column. The object in memory can still change; other code may rely on that in-memory value, and other sensitive attributes still update.

### 11.6. "Removing setters solves everything"

Restricting setters reduces the property-binding surface, yet Java objects can still receive data through constructors, reflection/field access by serializers, mappers, or other paths. Use input DTOs/authorization and test the boundary.

### 11.7. "With a safe DTO, we don't need owner checks"

False. A DTO stops clients from injecting extra fields; it does not stop them from changing the ID in the URL to edit someone else's account. Ownership/tenant authorization is a separate mandatory mechanism.

### 11.8. "Repo.save() is the first place the entity changes"

Not necessarily. If binding runs on an entity already present in the Model, setters have already executed before the handler starts. When managed, dirty checking can even persist those changes upon transaction flush.

## 12. Testing to Prevent Mass Assignment

A system should have **negative tests** for cases where extra properties are deliberately sent.

| Scenario | Expectation |
| --- | --- |
| Send only valid `displayName`/`email` | Update succeeds, sensitive fields unchanged |
| Also send `role=ADMIN` | 4xx or intentional ignore, **do not update role** |
| Also send `verified=true` | Do not update verified |
| Send `ownerId` or `tenantId` | Do not change tenant/owner |
| Send nested `owner.id` | Do not alter ownership association |
| Send `status=APPROVED` or `balance=0` | Do not alter status/financial state |
| Send unparseable number to a property | Return type conversion error, no partial persistence |
| DTO invalid per `@NotBlank`/`@Email` | 4xx, no update |
| Use user A to send update for user B's ID | 403/404 per contract, do not update B |
| Edit fields not allowed for current role | Rejected even if the DTO contains the field |
| Same API accepting JSON `@RequestBody` | DTO and Jackson mapping accept only approved fields |
| Refactor entity by adding a new setter | Input binding does not automatically grant update access to the new field |

### 12.1. Unit tests are not enough

A unit test calling directly:

```java
new SafeAccountController(service).update(id, form, errors);
```

does not trigger Spring MVC's `WebDataBinder`, `@InitBinder`, conversion, or validation. It can verify the service/controller code as written, but **does not** prove over-posting is prevented.

Use `MockMvc` or HTTP integration tests through the Spring context to verify:

- `getSuppressedFields()` is populated for inputs outside the allowlist.
- `@Valid` runs and `BindingResult` is positioned properly.
- The entity in the database preserves `role`/`verified` after a rejected request.
- No endpoint binds untrusted input directly onto an entity.
- Every update enforces ownership/tenant checks from a trusted identity.

### 12.2. MockMvc test example (optional fragment)

If you add the `spring-boot-starter-test` dependency and an appropriate test class, you can test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProfileBindingSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void overPostingIsRejected() throws Exception {
        mvc.perform(post("/lab/accounts/1")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Alice")
                .param("email", "alice@example.test")
                .param("role", "ADMIN"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("REJECTED_FIELDS"));
    }
}
```

This is a **test fragment** requiring imports, the `lab` profile enabled, an application context, and the test dependency; it is not part of the 8 main example Java source files. In production tests, beyond checking the HTTP status, also assert the database state to catch bugs where an endpoint mutates/persists an entity yet still returns 400.

### 12.3. JSON tests are also needed separately

Do not use a form-binding test to conclude that `@RequestBody Account` is safe. Send JSON containing extra `role`, `verified`, or nested fields to the actual JSON endpoint, observe how DTO/Jackson deserialization behaves, and confirm persisted values remain unchanged.

If strict unknown-fields handling is configured, verify the 400 response and safe error message. If the API intentionally ignores unknown fields, add tests proving the server does not map them onto the entity.

## 13. Additional Defenses in Real-World Architecture

### 13.1. Split use cases instead of one generic entity update

Instead of a single `PATCH /accounts/{id}` endpoint accepting all fields, consider separating:

- `PUT /accounts/{id}/profile` for display name/email.
- `POST /accounts/{id}/verify` for a separately verified authentication flow.
- `POST /admin/accounts/{id}/role` for role changes after admin authentication.
- `POST /accounts/{id}/transfer-owner` if the domain allows it with dedicated authorization.

Each endpoint has its own input DTO and service method, making policies clearer. These paths are design patterns only and do not exist in the demo.

### 13.2. Domain-meaningful service methods

A well-designed service exposes operations like `changeEmail(...)`, `verifyIdentity(...)`, and `grantRole(...)` rather than a generic `updateEntity(Map<String,Object> changes)`. That way, code reviews clearly see the required fields and permissions per use case.

### 13.3. Database safeguards

Database constraints and optimistic locking help prevent data corruption, duplicates, and lost updates. However, they do not understand "this user cannot promote their own role" if the update is schema-valid. Authorization and input mapping must still live in the application or an appropriate policy layer.

### 13.4. Auditing and observability

Log attempts to submit disallowed fields at a level sufficient to detect abuse, while avoiding logging entire request bodies or sensitive rejected values. For admin-initiated `role`/`verified` updates, record audit events capturing identity, resource, action, timestamp, and reason per system policy.

### 13.5. Mapping libraries and code generation

Mappers like MapStruct can assist in converting DTOs to entities, yet mappings still need review. If an "update entity from DTO" mapper uses an automatic null/unmapped policy, a newly added field on the DTO/entity might be copied unintentionally. Explicit mapping configuration or domain methods are safer than implicitly copying every property.

### 13.6. Interaction with the frontend

Frontend form validation and disabled controls only improve UX. The backend must still validate and authorize every field. Never treat hidden inputs like `role=USER` or `price=100` as trusted sources; pricing, tenant, and permissions must be computed or decided on the server.

## 14. Spotting Risks During Code Review

When reading Spring MVC controllers, watch out for these patterns:

```java
public void update(@ModelAttribute UserEntity user) { ... }
```

```java
public void save(@RequestBody AccountEntity account) { ... }
```

```java
repository.save(entityBoundFromClient);
```

```java
BeanUtils.copyProperties(request, entity);
```

These are **review red flags**, not automatic proof of a vulnerability. You must examine setters, input mapping, validation, allowlists, authorization, serialization, and persistence. If a request DTO contains only permitted fields, access control is explicit, and the mapper is exact, automated mapping can be reasonable; otherwise, convenient binding/copying can unintentionally alter privileged state.

Code review checklist:

1. Which entities are exposed as request models?
2. Do writable properties include sensitive fields?
3. Is the model attribute loaded from the database before binding?
4. Which binders set `setAllowedFields` / `setDeclarativeBinding`?
5. Could global and local binder configurations override each other?
6. Does the DTO include privileged properties that ordinary users cannot modify?
7. Does service-layer mapping use explicit assignment?
8. Where do ID, owner, and tenant come from, and how are they verified against the principal?
9. Is there a separate JSON endpoint exposing the same object?
10. After validation/authorization failures, is database state guaranteed unchanged?
11. Do regression tests send extra/nested fields?
12. Does the code leak rejected values/PII in error messages or logs?

## 15. Summary

**Mass assignment occurs when a request can modify more object properties than the user is authorized to change.** In Spring MVC, binding `@ModelAttribute` directly onto a JPA entity with writable properties like `role`, `verified`, `owner`, or `balance` easily introduces over-posting risks. When the entity is persisted via `save`/dirty checking, unauthorized changes can reach the database.

The top defenses are **dedicated input DTOs per use case**, **explicit mapping** onto the entity after **authorization** succeeds, and **allowlist property binding** via `WebDataBinder#setAllowedFields` when property binding is still used. Where appropriate, `setDeclarativeBinding(true)` and immutable DTOs shrink the property-mutation surface; do not confuse them with authorization. For JSON, use DTOs and Jackson configuration because `@RequestBody` is not restricted by the form binder's `setAllowedFields`.

Perform real HTTP tests with deliberately added fields such as `role=ADMIN` and confirm that **persistent state remains unchanged**. That is far stronger evidence than merely observing that a request was rejected.

## References

- Spring Framework 6.2 — `@ModelAttribute` controller arguments and security considerations: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@InitBinder`, allowlist, constructor binding, and `setDeclarativeBinding`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 — `@ModelAttribute` methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html
- Spring Framework 6.2 — `@RequestBody` and message converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 — `DataBinder` Javadoc (allowed fields, suppressed fields, declarative binding): https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/validation/DataBinder.html
- OWASP Cheat Sheet Series — Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- CWE-915 — Improperly Controlled Modification of Dynamically-Determined Object Attributes: https://cwe.mitre.org/data/definitions/915.html
- OWASP API Security Top 10 — Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/