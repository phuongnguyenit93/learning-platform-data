# Checking Permissions for Read, Edit, Delete, and Export as Separate Operations

> **Scope:** Spring Security on **Spring Boot MVC / Servlet**, Java 17+, focusing on **Data Protection**. This lesson treats READ, UPDATE, DELETE, and EXPORT as **four actions requiring independent authorization decisions**, while also checking **the exact record, owner, tenant, business state, and actual returned data**. Never stop at checking only that a user is "logged in" or holds a general role.

## 1. The Problem: A User May View Data Without Being Allowed to Edit, Delete, or Export It

Imagine an application storing business documents. A user may be allowed to open a document in the UI, yet must not be allowed to:

- **Edit:** alter the title/content or modify sensitive fields.
- **Delete:** remove data, which can impact reconciliation and traceability.
- **Export:** generate CSV/XLSX/PDF files containing batches of records, moving data outside normal access controls.
- **Read other records:** even when knowing a valid ID or URL, the user still has no right to view documents outside their organization/tenant.

These are two authorization dimensions that must be combined:

1. **Function-level permission:** is the user allowed to perform the READ, EDIT, DELETE, or EXPORT action in general?
2. **Object-level permission:** on **which specific record**, in which tenant, and under what role/ownership/state is the user allowed to act?

Conceptual formula:

```text
ALLOW(subject, action, resource, context)
    = authenticated(subject)
    AND hasCapability(subject, action)
    AND belongsToAllowedScope(subject, resource)
    AND businessRulesAllow(subject, action, resource, context)
```

All of the conditions above must be checked **on the server** before data is disclosed or modified. A hidden button, disabled frontend route, or hard-to-guess UUID cannot replace these checks.

### Sample Permission Matrix

| Sample user | Read record in same tenant | Edit own record | Delete own record | Export list in same tenant |
| --- | --- | --- | --- | --- |
| Alice, authorities `DOC_READ` + `DOC_EDIT` + `DOC_DELETE` | Yes | Yes | Yes | **No**, lacks `DOC_EXPORT` |
| Bob, authorities `DOC_READ` + `DOC_EXPORT` | Yes | No | No | Yes, within permitted tenant |
| Carol, read/edit/delete/export authorities, different tenant | Only Carol's tenant | Per permission and ownership | Per permission and ownership | Only Carol's tenant |
| Unauthenticated user | No | No | No | No |

This is an **illustrative policy** to demonstrate the principle. A real application may specify "only department managers may DELETE", "EXPORT requires approval", or "locked records cannot be UPDATED". The key point is **never inferring EXPORT from READ, DELETE from EDIT, or object permissions from menu access**.

## 2. Distinguishing Authentication, Authorization, and Data Controls

- **Authentication:** establishes who the caller is (session, Basic, Bearer token, OAuth2, etc.). Spring Security's `Authentication` represents the principal and authorities in the security context.
- **Request authorization:** blocks or allows URL/method patterns in `SecurityFilterChain`, e.g., only authenticated users may call `/api/documents/**`.
- **Method authorization:** applies conditions to service calls via `@EnableMethodSecurity` and `@PreAuthorize`; very useful when decisions need the record ID.
- **Data authorization:** restricts **which records are queried, updated, deleted, or exported**, filtering by tenant/owner and business rules right where data is accessed.
- **Data minimization:** even when READ is allowed, a user may only be allowed to see certain fields; use DTOs/query projections instead of exposing the full entity.
- **Audit and monitoring:** log who performed which action, when, and on which resource; never write raw sensitive content into logs.

Spring Security lets you configure permissions at both request and method levels; `@EnableMethodSecurity` **is not enabled merely by adding the security starter**. Once enabled, `@PreAuthorize` is enforced via Spring AOP proxies for Spring-managed beans.

### Required Verification Pipeline

```text
HTTP request
    |
    v
SecurityFilterChain: is the caller authenticated?
    |
    v
Controller: parse and validate input data
    |
    v
DocumentService: @PreAuthorize(action, documentId)
    |
    v
DocumentPolicy: capability + tenant + owner + business state
    |
    v
DocumentRepository: query/operate within valid scope
    |
    v
Data-minimized DTO or CSV
    |
    v
HTTP response
```

**Do not check permissions only in the controller.** A service can also be invoked from jobs, event listeners, batches, or other endpoints; if a rule lives only on one route, another call path can bypass it. Even with `@PreAuthorize`, watch out for performance and race conditions between checking and DB execution (section 10).

## 3. Defining Each Action and Target Resource

### 3.1. READ: Permission to View Records

READ covers viewing details, searching/listing, previews, fetching attachments, viewing history, and any endpoint returning data fields. Securing detail GETs while forgetting search/list is a common bug.

Example `GET /api/documents/a-1`:

1. Authenticate the caller.
2. Check `DOC_READ`.
3. Determine the tenant from a trusted identity; **never blindly trust a client-supplied tenant**.
4. Verify record `a-1` actually belongs to the permitted tenant.
5. Return only the fields the caller needs.

READ does not mean "allowed to view every column in the table". You may need separate `READ_METADATA`, `READ_CONTENT`, `READ_PII`, or field masking when data is sensitive.

### 3.2. UPDATE: Permission to Modify Records and Fields

UPDATE usually requires stronger permissions than READ. Verify:

- `DOC_EDIT` (functional permission);
- record owner or a role allowed to edit on someone's behalf;
- same tenant/project scope;
- record state allows editing (not locked, not already approved if business rules forbid it);
- **which fields may be modified** (reject ownerId, tenantId, role, approvedBy unless an explicit rule permits them);
- concurrency/versioning to avoid overwriting another user's changes.

Never use `BeanUtils.copyProperties(request, entity)` or bind DTOs directly onto entities containing sensitive fields without an allowlist. DTOs should declare only fields the client is allowed to edit.

### 3.3. DELETE: Permission to Remove Data and Its Consequences

DELETE typically requires a **separate** authority (`DOC_DELETE`); even someone with EDIT may not be allowed to delete. Consider:

- soft delete vs. hard delete, retention/legal hold;
- whether deleting a document cascades to attachments/caches/search indexes;
- whether approval or re-confirmation is required for critical data;
- idempotency and handling nonexistent IDs;
- audit events to record who performed the deletion.

Even when an API uses `DELETE /api/documents/{id}`, **the HTTP method does not grant permission by itself**. Rules must verify both the action **and the specific record**.

### 3.4. EXPORT: Permission to "Take Data Out" Independently of READ

EXPORT carries different risks from fetching a single record with GET: one request can download thousands of rows, expose PII, include wrongly filtered records, contain malicious spreadsheet formulas, use unsafe filenames, or leave shareable links active after permissions are revoked.

Minimum checks:

1. **Separate `DOC_EXPORT` authority**; never inherit it implicitly from `DOC_READ`.
2. Tenant/project scope and read permissions applied to **every row and row group**.
3. Limits on filters, row count, payload size, processing time, rate, and concurrent exports.
4. Export only approved columns; never export password hashes, access tokens, secrets, or internal fields outside the contract.
5. Audit requester, data type, scope, timestamp, and job status (avoid logging file contents).
6. If export generates a persisted file or runs asynchronously: verify permissions **at request time, generation time, and download time**, with appropriate file retention/link TTLs.
7. Properly encode CSV and mitigate **formula injection** (detailed in section 9).

**A paginated list endpoint must not be "stretched" into a full export via `?pageSize=100000000`.** Define a dedicated EXPORT use case with its own contract, limits, and authorization.

## 4. Designing Endpoints and Status Codes

| Illustrative HTTP endpoint | Action | Required checks |
| --- | --- | --- |
| `GET /api/documents/{id}` | READ | `DOC_READ` + record scope |
| `PUT /api/documents/{id}` | UPDATE | `DOC_EDIT` + owner/tenant + field allowlist |
| `DELETE /api/documents/{id}` | DELETE | `DOC_DELETE` + owner/tenant + deletion policy |
| `GET /api/documents/export` | EXPORT | `DOC_EXPORT` + `DOC_READ` + tenant + row/column filtering |

**Status codes so clients behave properly:**

- **401 Unauthorized:** request lacks valid authentication per API scheme.
- **403 Forbidden:** authenticated, but lacks permission for the action or data; CSRF failures can also produce 403.
- **404 Not Found:** resource does not exist, or the application **deliberately hides whether the resource exists** when policy requires it.
- **400 Bad Request:** invalid payload; do not return 400 for every authorization failure.
- **409 Conflict:** state/version conflict where business rules warrant it.
- **204 No Content:** DELETE succeeded with no response body.

Do not mechanically hardcode every permission failure to 404 or 403. Choose a policy that prevents disclosing record existence, document the contract, and test consistently. In the demo below, the policy denies operations on nonexistent IDs with 403 because `@PreAuthorize` executes before the service loads the entity; that is an **illustrative decision**, not a universal HTTP rule.

## 5. Runnable Demo: One Authority per Action, Plus Tenant and Owner

Example using Spring Boot 3.x, Java 17+, Spring Security 6.x, Spring MVC, Spring Data JPA, and H2. Users and tenants are **initialized server-side** for learning convenience; never take a client-sent `X-Tenant-ID` as the source of truth. This example is for local permission testing only and lacks production provisioning, password management, or production auditing.

Structure:

```text
document-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.yml
    │   └── java/com/example/docsecurity/
    │       ├── DocumentSecurityApplication.java
    │       ├── SecurityConfig.java
    │       ├── TenantDirectory.java
    │       ├── DocumentEntity.java
    │       ├── DocumentRepository.java
    │       ├── DocumentPolicy.java
    │       ├── UpdateDocumentRequest.java
    │       ├── DocumentView.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/java/com/example/docsecurity/
        └── DocumentAuthorizationTest.java
```

### 5.1. Gradle Build and H2 Configuration

File `settings.gradle`:

```groovy
rootProject.name = 'document-security-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:docsecurity;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false

server:
  error:
    include-message: never
```

Plugin versions are **pinned so the example is reproducible on environments supporting Gradle/Java 17**, not as a recommendation to deploy an older Spring Boot release to production. When working in an existing repository, use the project's approved versions and dependency management, keeping security patches up to date.

### 5.2. Main Class — `DocumentSecurityApplication.java`

```java
package com.example.docsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DocumentSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentSecurityApplication.class, args);
    }
}
```

### 5.3. Entity — `DocumentEntity.java`

```java
package com.example.docsecurity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "business_documents")
public class DocumentEntity {

    @Id
    private String id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false, length = 120)
    private String title;

    @Version
    private Long version;

    protected DocumentEntity() {
    }

    public DocumentEntity(
            String id, String tenantId, String ownerUsername, String title) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void changeTitle(String newTitle) {
        this.title = newTitle;
    }
}
```

Only `title` is updated through a business method; clients have no setter API for `tenantId` or `ownerUsername`. `@Version` enables **optimistic locking** when the entity is updated via JPA, though adding the annotation alone does not provide a complete conditional-update/ETag API; the client also needs a version contract if UI conflict detection is desired.

### 5.4. Repository — `DocumentRepository.java`

```java
package com.example.docsecurity;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<DocumentEntity, String> {
    List<DocumentEntity> findByTenantIdOrderByIdAsc(String tenantId);
}
```

`findByTenantIdOrderByIdAsc(...)` is important for the export example: the query already includes the **tenant condition in SQL**, rather than reading the entire table and filtering in Java. On large datasets, paginate or stream within resource limits; returning a `List` is only suitable for small demo data.

### 5.5. Server-Side Tenant Directory — `TenantDirectory.java`

```java
package com.example.docsecurity;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> tenants = Map.of(
        "alice", "tenant-alpha",
        "bob", "tenant-alpha",
        "carol", "tenant-beta"
    );

    public String tenantFor(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return null;
        }
        return tenants.get(authentication.getName());
    }
}
```

In production, this directory must be replaced with verified tenant claims/identifiers from an identity provider or a managed server-side lookup. **Never** take a tenant from query/header or form body and treat it as ownership. A user may belong to multiple tenants; in that case, the model must verify the selected tenant belongs to the user's permitted set and check every resource against that tenant.

### 5.6. Users, Authorities, and SecurityFilterChain — `SecurityConfig.java`

```java
package com.example.docsecurity;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf").permitAll()
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Keep default CSRF for HTTP requests that may use browser credentials.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EDIT", "DOC_DELETE")
            .build();

        var bob = User.withUsername("bob")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EXPORT")
            .build();

        var carol = User.withUsername("carol")
            .password(encoder.encode("demo-password"))
            .authorities("DOC_READ", "DOC_EDIT",
                         "DOC_DELETE", "DOC_EXPORT")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.saveAll(List.of(
                    new DocumentEntity(
                        "a-1", "tenant-alpha", "alice", "Budget Alpha"),
                    new DocumentEntity(
                        "a-2", "tenant-alpha", "bob", "Delivery Notes"),
                    new DocumentEntity(
                        "b-1", "tenant-beta", "carol", "Budget Beta")
                ));
            }
        };
    }
}
```

This is a **demo using HTTP Basic** for easy invocation and testing; demo passwords and in-memory H2 are **not suitable for production**. When using `curl -u`, watch out for shell history and process lists; in real systems, never pass sensitive passwords directly on the command line. Real applications should use TLS, proper identity systems, credential management, and operational policies.

Here the URL guard only requires authentication; **READ/EDIT/DELETE/EXPORT permissions live on the service methods**. `@EnableMethodSecurity` is what makes `@PreAuthorize` take effect. If you omit this annotation, method checks are not enabled automatically just by having `spring-boot-starter-security`.

### 5.7. Policy: Checking Capability, Tenant, and Owner — `DocumentPolicy.java`

```java
package com.example.docsecurity;

import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;
    private final TenantDirectory tenants;

    public DocumentPolicy(
            DocumentRepository repository, TenantDirectory tenants) {
        this.repository = repository;
        this.tenants = tenants;
    }

    public boolean canRead(Authentication auth, String documentId) {
        return repository.findById(documentId)
            .map(doc -> canReadDocument(auth, doc))
            .orElse(false);
    }

    public boolean canEdit(Authentication auth, String documentId) {
        if (!has(auth, "DOC_EDIT")) {
            return false;
        }
        return repository.findById(documentId)
            .map(doc -> sameTenant(auth, doc) && (
                Objects.equals(doc.getOwnerUsername(), auth.getName())
                || has(auth, "DOC_ADMIN")
            ))
            .orElse(false);
    }

    public boolean canDelete(Authentication auth, String documentId) {
        if (!has(auth, "DOC_DELETE")) {
            return false;
        }
        return repository.findById(documentId)
            .map(doc -> sameTenant(auth, doc) && (
                Objects.equals(doc.getOwnerUsername(), auth.getName())
                || has(auth, "DOC_ADMIN")
            ))
            .orElse(false);
    }

    public boolean canExport(Authentication auth) {
        return has(auth, "DOC_EXPORT")
            && has(auth, "DOC_READ")
            && tenants.tenantFor(auth) != null;
    }

    public boolean canReadDocument(
            Authentication auth, DocumentEntity document) {
        return has(auth, "DOC_READ") && sameTenant(auth, document);
    }

    private boolean sameTenant(Authentication auth, DocumentEntity doc) {
        String userTenant = tenants.tenantFor(auth);
        return userTenant != null
            && Objects.equals(userTenant, doc.getTenantId());
    }

    private boolean has(Authentication auth, String authority) {
        return auth != null
            && auth.isAuthenticated()
            && auth.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
```

Detailed explanation:

- `canRead`: requires `DOC_READ` **and** matching tenant. Thus Carol, despite having READ authority, cannot read `a-1` in tenant-alpha.
- `canEdit`: requires `DOC_EDIT`, same tenant, **and** either being the owner or holding `DOC_ADMIN`. Alice cannot edit Bob's `a-2` even in the same tenant.
- `canDelete`: checks `DOC_DELETE` **separately** rather than reusing `canEdit`. In real products, DELETE may also be blocked if the record is locked.
- `canExport`: requires **both** `DOC_EXPORT` and `DOC_READ`, plus a server-resolved tenant. Alice, even though she can read/edit/delete, still cannot export.
- `canReadDocument` is reused when generating the file to prevent exporting records outside read scope. The export query also filters by tenant to reduce data volume.
- `DOC_ADMIN` in this example is only an **owner exception within the same tenant**; it does not cross tenants and does not replace `DOC_EDIT`/`DOC_DELETE` authorities. If you want a cross-tenant superadmin, define and audit **a new explicit rule**, never "silently assume admin can do anything".

Signs that permissions are properly separated: changing `DOC_EXPORT` does not alter READ/EDIT/DELETE capabilities. Changing `DOC_DELETE` does not grant edit or view access.

### 5.8. Input/Output DTOs — `UpdateDocumentRequest.java`, `DocumentView.java`

File `UpdateDocumentRequest.java`:

```java
package com.example.docsecurity;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
    @NotBlank @Size(max = 120) String title
) {}
```

File `DocumentView.java`:

```java
package com.example.docsecurity;

public record DocumentView(String id, String title) {}
```

Only allow the client to modify `title`: no `tenantId`, `ownerUsername`, `version`, or `authorities` in the request body. Output returns only `id` and `title`. If more fields are needed, each field must have a business reason and appropriate read/write policy.

### 5.9. Service Enforcing Per-Action Permissions — `DocumentService.java`

```java
package com.example.docsecurity;

import java.util.Objects;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentPolicy policy;
    private final TenantDirectory tenants;

    public DocumentService(
            DocumentRepository repository,
            DocumentPolicy policy,
            TenantDirectory tenants) {
        this.repository = repository;
        this.policy = policy;
        this.tenants = tenants;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    @Transactional(readOnly = true)
    public DocumentView read(String id) {
        return toView(requireDocument(id));
    }

    @PreAuthorize("@documentPolicy.canEdit(authentication, #p0)")
    @Transactional
    public DocumentView edit(String id, UpdateDocumentRequest request) {
        DocumentEntity doc = requireDocument(id);
        doc.changeTitle(request.title());
        return toView(doc);
    }

    @PreAuthorize("@documentPolicy.canDelete(authentication, #p0)")
    @Transactional
    public void delete(String id) {
        DocumentEntity doc = requireDocument(id);
        repository.delete(doc);
    }

    @PreAuthorize("@documentPolicy.canExport(authentication)")
    @Transactional(readOnly = true)
    public String exportCsv() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        String tenant = Objects.requireNonNull(tenants.tenantFor(auth));

        StringBuilder csv = new StringBuilder("id,title\r\n");
        repository.findByTenantIdOrderByIdAsc(tenant).stream()
            .filter(doc -> policy.canReadDocument(auth, doc))
            .forEach(doc -> csv
                .append(csvCell(doc.getId()))
                .append(',')
                .append(csvCell(doc.getTitle()))
                .append("\r\n"));

        return csv.toString();
    }

    private DocumentEntity requireDocument(String id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new IllegalStateException("Document not found after check"));
    }

    private DocumentView toView(DocumentEntity doc) {
        return new DocumentView(doc.getId(), doc.getTitle());
    }

    private String csvCell(String raw) {
        String normalized = raw == null ? "" :
            raw.replace("\r", " ").replace("\n", " ");
        String leading = normalized.stripLeading();

        // Mitigate some common CSV formula injection patterns.
        if (!leading.isEmpty() && "=+-@".indexOf(leading.charAt(0)) >= 0) {
            normalized = "'" + normalized;
        }
        return "\"" + normalized.replace("\"", "\"\"") + "\"";
    }
}
```

**Why `#p0`?** In `@PreAuthorize` expressions, `#p0` refers to the first method parameter, which is `id` here. This does not depend on Java parameter names being preserved in bytecode via the `-parameters` compiler flag. The annotation invokes the `documentPolicy` bean, passing `authentication` from the security expression root and the target ID.

**When is authorization checked?** The Spring AOP proxy intercepts the method call before the service body runs. If the policy denies access, the service neither reads results to return to the client nor modifies data. In real apps, note that `@PreAuthorize` queries the repository to inspect the object before the business transaction opens; transactions, isolation, and races must be designed consistently (section 10).

**Why not return the entity?** The entity also carries tenant, owner, version, and potentially PII added later. The `DocumentView` DTO forms a narrower contract, reducing data-exposure risk as the DB schema evolves.

**Why two tenant checks during export?** `findByTenantIdOrderByIdAsc(tenant)` filters directly in the DB; `canReadDocument` double-checks per-record read permission. For complex policies, the query itself must express the scope so unauthorized data is not loaded into memory; this example uses two layers for illustration and does not endorse filtering millions of rows in Java.

**Demo code limitations:** `exportCsv` builds the entire file in RAM; use it only for small datasets. In production, paginate/stream properly, cap rows/bytes, enforce quotas, and handle downloads safely. Prepending a single quote to cells starting like formulas **mitigates only certain CSV injection cases** and does not guarantee complete safety across all spreadsheet programs; see section 9.

`requireDocument` throws if the record disappears between the permission check and the DB operation. This intentionally highlights the **check–use** gap; production code must map missing/race cases to proper responses without leaking stack traces. `@Version` helps detect update conflicts via optimistic locking, but does not by itself solve all authorization races.

### 5.10. HTTP Controller — `DocumentController.java`

```java
package com.example.docsecurity;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/csrf")
    public CsrfToken csrf(HttpServletRequest request) {
        return (CsrfToken) request.getAttribute(CsrfToken.class.getName());
    }

    @GetMapping("/documents/{id}")
    public DocumentView read(@PathVariable String id) {
        return documents.read(id);
    }

    @PutMapping("/documents/{id}")
    public DocumentView update(
            @PathVariable String id,
            @Valid @RequestBody UpdateDocumentRequest request) {
        return documents.edit(id, request);
    }

    @DeleteMapping("/documents/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        documents.delete(id);
    }

    @GetMapping(value = "/documents/export", produces = "text/csv")
    public ResponseEntity<byte[]> export() {
        byte[] data = documents.exportCsv().getBytes(StandardCharsets.UTF_8);
        return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"documents.csv\"")
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
            .body(data);
    }
}
```

**Checkpoint:** the controller invokes the **service bean** through the Spring proxy so `@PreAuthorize` takes effect. The controller only receives DTOs and returns HTTP responses. Never place core authorization logic inside an `if (id.equals(...))` in the controller while the service can be called from other places.

At `GET /api/csrf`, Spring Security exposes `CsrfToken` as a request attribute when the CSRF filter runs and a token is generated. This illustrates how a client can obtain a token before calling PUT/DELETE with browser/cookie flows. The API uses HTTP Basic as a demo, yet **keeps CSRF enabled** to avoid showing an anti-pattern of disabling protection for browser credentials. In production, configure CSRF according to your actual authentication method.

### 5.11. Running the Program

In the directory containing the project, use a compatible Gradle installation (or the wrapper if generated):

```bash
./gradlew test
./gradlew bootRun
```

If a newly created project lacks `gradlew`, you can run `gradle test` and `gradle bootRun` with a compatible Gradle installed. These sample classes **are not standalone files to run with `javac`/`java` without dependencies**; Gradle prepares the classpath, and Spring Boot starts the application context and H2 database. There is no fixed stdout output; startup logs depend on the environment, and demo data lives in in-memory H2.

In development, send read requests with Basic Authentication:

```bash
# Alice reads document a-1 (tenant-alpha): expect 200.
curl -i -u alice:demo-password \
  http://localhost:8080/api/documents/a-1

# Carol in tenant-beta tries reading a-1: expect 403.
curl -i -u carol:demo-password \
  http://localhost:8080/api/documents/a-1

# Alice has READ but not EXPORT: expect 403.
curl -i -u alice:demo-password \
  http://localhost:8080/api/documents/export

# Bob has DOC_EXPORT and DOC_READ in tenant-alpha: expect 200 CSV.
curl -i -u bob:demo-password \
  http://localhost:8080/api/documents/export
```

When Bob exports, the content includes only readable documents in tenant-alpha, namely `a-1` and `a-2`. Tenant-beta's `b-1` is absent. The filename returned is `documents.csv` with header `Cache-Control: no-store`. That header only helps control HTTP caching; it does not replace protecting the file after a user downloads it to their device.

To test PUT/DELETE with CSRF, use a cookie jar and the token returned from `/api/csrf`. Bash with `curl` and `jq`:

```bash
# Step 1: fetch token, keeping the same cookie jar.
CSRF=$(curl -sS -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

# Step 2: Alice updates her own a-1: expect 200.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X PUT http://localhost:8080/api/documents/a-1 \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"title":"Budget Alpha (Updated)"}'

# Step 3: Alice tries updating Bob's a-2: expect 403.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X PUT http://localhost:8080/api/documents/a-2 \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"title":"Unauthorized change"}'

# Step 4: Alice deletes her own a-1: expect 204.
curl -i -u alice:demo-password \
  -b cookies.txt -c cookies.txt \
  -X DELETE http://localhost:8080/api/documents/a-1 \
  -H "X-CSRF-TOKEN: $CSRF"
```

These commands can **modify demo data**, so run them against the local app seeded with test data—never indiscriminately against a real service. Once step 4 runs, record `a-1` is gone from the current session's H2 database; to repeat from scratch, restart the app in this in-memory H2 setup.

**Do not confuse 403 missing permission with 403 missing CSRF:** if you omit the token, `CsrfFilter` can reject the request before the service ever checks `DOC_EDIT` or `DOC_DELETE`. To test business authorization, supply a valid CSRF token.

## 6. Tests Proving the 4 Actions Are Independent

File `src/test/java/com/example/docsecurity/DocumentAuthorizationTest.java`. Uses the Spring Boot integration context, `MockMvc`, and `spring-security-test`. `@Transactional` on the test rolls back mutations on synchronous MockMvc request threads so one test does not pollute seed data for another.

```java
package com.example.docsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@Rollback
class DocumentAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/documents/a-1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadButCannotExport() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("a-1"));

        mvc.perform(get("/api/documents/export")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadAndExportButCannotEditOrDelete() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("bob", "demo-password")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/export")
                .with(httpBasic("bob", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(content().contentTypeCompatibleWith("text/csv"))
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("a-1")));

        mvc.perform(put("/api/documents/a-2")
                .with(httpBasic("bob", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Changed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(delete("/api/documents/a-2")
                .with(httpBasic("bob", "demo-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanEditOwnDocumentButNotAnotherOwners() throws Exception {
        mvc.perform(put("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Updated by Alice\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Updated by Alice"));

        mvc.perform(put("/api/documents/a-2")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Illegal update\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotReadAcrossTenantEvenWithReadAuthority() throws Exception {
        mvc.perform(get("/api/documents/a-1")
                .with(httpBasic("carol", "demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/b-1")
                .with(httpBasic("carol", "demo-password")))
            .andExpect(status().isOk());
    }

    @Test
    void aliceCanDeleteOwnDocument() throws Exception {
        mvc.perform(delete("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingCsrfRejectsMutationBeforeBusinessAuthorization() throws Exception {
        mvc.perform(put("/api/documents/a-1")
                .with(httpBasic("alice", "demo-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No csrf\"}"))
            .andExpect(status().isForbidden());
    }
}
```

**Why test each operation?** Testing only "Alice can call GET" proves nothing about UPDATE/DELETE/EXPORT safety. The test suite covers **both the horizontal axis (actions) and the vertical axis (owner/tenant)**.

**A note on test status codes:** this example uses Spring Security method authorization, so missing `DOC_*` returns 403 for authenticated callers. If your team chooses 404 to hide resource existence, change the response mechanism consistently and update the assertions.

**Additional tests for real products:** also test GET list/search, pagination, client-chosen filter IDs, batch edit/delete, attachments/previews, permissions across GraphQL/WebSockets/jobs, verifying exported columns/rows, and re-downloading exported files after permission revocation.

## 7. Why URL Checks Alone Are Not Enough

Consider a configuration like:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("DOC_READ")
    .requestMatchers(HttpMethod.PUT, "/api/documents/**")
        .hasAuthority("DOC_EDIT")
    .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
        .hasAuthority("DOC_DELETE")
    .anyRequest().denyAll()
);
```

The snippet above is a **request-level illustration**, requiring `HttpMethod` and `HttpSecurity` imports if placed in a full config class. It has two problems:

1. An overly broad `GET /api/documents/**` rule also matches `GET /api/documents/export`. Unless a **specific EXPORT rule is placed before the general GET rule**, someone with only READ could pass the URL check. The service-level `DOC_EXPORT` check can still protect it if retained.
2. Path/method rules **do not know** that document `a-2` belongs to Bob or `b-1` belongs to another tenant, so they cannot decide whether the caller may read/edit/delete that document.

When you want to block early at the URL layer, declare specific paths explicitly:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/export")
        .hasAuthority("DOC_EXPORT")
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("DOC_READ")
    .requestMatchers(HttpMethod.PUT, "/api/documents/**")
        .hasAuthority("DOC_EDIT")
    .requestMatchers(HttpMethod.DELETE, "/api/documents/**")
        .hasAuthority("DOC_DELETE")
    .anyRequest().denyAll()
)
```

This is an **alternative request guard option in the example**, not meant to be combined ambiguously with the other `authorizeHttpRequests` snippet. To ensure `DOC_EXPORT` also requires `DOC_READ`, use an appropriate expression/manager at the request layer or have `@PreAuthorize` on the service verify **both** as in the demo. **Never remove service-level checks** after adding URL rules.

Matcher order matters because Spring Security selects the first matching rule in declaration order. More specific rules like `/export` must precede broader `/**` rules. URL-level checks are distinct from object-level checks after resolving the ID in the DB.

## 8. Real-World Security Flaws Related to the Four Operations

### 8.1. IDOR / BOLA: Swapping IDs in the URL

Alice opens `/api/documents/a-1`, then changes the URL to `/api/documents/b-1`. If the server only checks login or `DOC_READ` without checking tenant/owner, data may be exposed. This is **Broken Object Level Authorization (BOLA)**, prominent in the OWASP API Security Top 10.

Any read, edit, delete, or export path accepting an object ID from the client needs the same rule: **an object identifier is not proof of permission**. Never trust auto-increment IDs, UUIDs, slugs, or signed IDs if the policy does not validate current authorization.

### 8.2. BFLA: One Access Permission Reused Across Multiple Functions

For example, the frontend hides the "Export" button, while `GET /export` only checks `authenticated()`; a user can call the API directly. That is **Broken Function Level Authorization**. Avoid rules like "anyone with an account can download everything".

### 8.3. Mass Assignment and Field-Level Security

Suppose a client sends:

```json
{
  "title": "Updated",
  "tenantId": "tenant-beta",
  "ownerUsername": "attacker",
  "approved": true
}
```

If the backend binds the payload directly onto a JPA entity and persists it, someone with permission to EDIT `title` can change tenant/owner or approval status. DTOs with a strict **field allowlist** prevent this class of bugs. Likewise, READ endpoints must restrict output fields to prevent excessive data exposure.

### 8.4. Export Bypassing Pagination/Filters or Read Policies

A classic mistake is showing only 20 documents in the UI while export calls `repository.findAll()` and downloads tens of thousands of rows. Apply the same business scope to export queries, cap record counts, and check `DOC_EXPORT`. If export allows filtering by ID/status, those filters **may only narrow** the permitted scope, never widen it outside the tenant.

### 8.5. Soft Deletes and Data Stored Outside the DB

If DELETE is implemented via `deleted = true`, READ and EXPORT queries must exclude deleted records when policy requires it. If attachments live in object storage, users must not be able to fetch them via lingering public URLs after permissions are revoked. Checking permissions on metadata is insufficient if the download link bypasses authorization.

### 8.6. Export Continuing After Permissions Are Revoked

If a user is authorized to export at 10:00 and has permissions revoked at 10:01, a 30-minute export job might still finish generating a file. Design job snapshots, permission re-checks, file TTLs, and download-endpoint checks; exact behavior depends on business requirements. A **signed URL** with a TTL is not a complete substitute for user authorization if it can be forwarded to others.

## 9. Handling CSV, XLSX, PDF, and Protecting Exported Data

### 9.1. Right Scope and Columns Before Generating Files

Export decisions should have two separate layers:

- **Eligibility:** who may **request an export**, which export type, which tenant, and what row limit.
- **Content authorization:** which individual rows/columns go into the file. Having `DOC_EXPORT` does not automatically grant access to another tenant's data or private fields the caller cannot READ.

When exporting multiple related entities—such as orders + buyers + payments—never blindly join and pull buyer PII if the contract only permits exporting order numbers.

### 9.2. CSV Escaping Differs from Formula Injection

Syntactically valid CSV requires quoting, escaping `"` as `""`, and handling newlines. Yet **CSV quoting alone does not stop spreadsheets from interpreting a cell as a formula**. If a cell begins with `=`, `+`, `-`, `@`, or app-specific prefixes, spreadsheet software may execute a formula when the file is opened.

`csvCell(...)` in the demo replaces CR/LF with spaces, prepends `'` to certain cells starting with formula characters after whitespace, and CSV-quotes every value. It is only an **illustrative risk-reduction measure**, not a universal solution across every spreadsheet app or re-save/re-open workflow. Test with the actual applications your users open files in, consult OWASP guidance, and prefer **XLSX with cells explicitly typed as Text** when stricter type control is needed.

Never treat stripping a single formula character as a complete fix; attackers can use tabs/spaces, Unicode, delimiters, or application-specific spreadsheet features.

### 9.3. Export File Lifecycle

- Return `Content-Disposition: attachment` with a safe filename; never place unvalidated client input into headers.
- Set `Cache-Control` appropriately for sensitive data and enforce HTTPS.
- Cap row counts, byte sizes, and concurrent exports; use streaming/async jobs for large datasets.
- Store exports in private storage tied to creator/tenant/scope, with TTLs and audits; delete upon expiration.
- Re-check permissions on download; if using pre-signed URLs, keep TTLs short and control issuance.
- Avoid logging PII or raw CSV in access logs, error logs, or internal notifications/emails.
- For PDF/XLSX, remember metadata, hidden sheets/columns, external links, and hidden data also require authorization.

## 10. Combining Authorization with Data Transactions

### 10.1. Race Conditions Between Policy Check and Operation

`@PreAuthorize` runs before the service body. If another operation can change the record's tenant/owner/state right after the check and before the update/delete, a decision based on the old snapshot may no longer hold. Example:

```text
T1: Alice has permission to edit document a-1.
T1: canEdit(a-1) = true.
T2: System transfers a-1 to Bob or locks the document.
T1: UPDATE a-1 based on stale decision -> violates new policy.
```

Common production techniques:

1. Enforce tenant/owner/state constraints **inside the same conditional UPDATE/DELETE query** and verify the affected row count.
2. Use appropriate transaction isolation or row-level locking when business rules require it.
3. Use `@Version`/optimistic locking to detect concurrent edits; return a conflict error or perform controlled retries—**never automatically retry after permissions have changed**.
4. Ensure authorization-relevant fields cannot be altered outside controlled use cases.
5. For strict multi-tenant systems, consider **database row-level security** as an extra layer if supported by the DB; the tenant context passed to the DB must come from a trusted source and be safely reset between requests.

Illustrative SQL concept when only the owner may edit:

```sql
UPDATE business_documents
SET title = :title
WHERE id = :id
  AND tenant_id = :authorized_tenant
  AND owner_username = :authenticated_user
  AND state = 'DRAFT';
```

This snippet **illustrates a scope-constrained query** and does not run directly against the demo entity because the demo has no `state` column. Real code must inspect the affected row count and handle optimistic versioning and state transitions properly rather than assuming "no exception thrown" means success.

### 10.2. Self-Invocation Can Bypass Method Security

`@PreAuthorize` relies on Spring AOP proxies. If `DocumentService` had an internal method:

```java
public void unsafeInternalCall(String id) {
    this.delete(id);  // Review carefully: calling within the same object can bypass the proxy
}
```

This is only a **warning pattern**, not added to the demo. Calling `this.delete(...)` on the same instance does not pass through the proxy the way a controller calling a service bean does, so annotations on the target method **may not execute on the self-invocation path**. Separate service/use-case boundaries or invoke through a properly proxied bean, and still enforce safety predicates at the data-access layer.

### 10.3. Never Rely on a Prior "Read" Action

Permission to read yesterday does not prove permission to delete today. Even if the UI sends a flag saying "user already viewed the document" or the client previously succeeded on GET, the backend must verify UPDATE/DELETE/EXPORT permissions **at action time**. With time-limited grants, approval states, or changing tenant memberships, fresh checks are mandatory.

## 11. Asynchronous Exports and Batch Operations

Large applications may generate reports asynchronously:

```text
POST /api/exports
   -> authenticate + DOC_EXPORT + valid filter + quota
   -> create ExportJob {requester, tenant, filter, permissions-context}

Background worker
   -> pick up job, verify scope is still valid per policy
   -> read via tenant-scoped query, filter rows/columns
   -> generate private file, scan content/format if needed
   -> write audit log, status COMPLETED/FAILED

GET /api/exports/{jobId}
   -> only requester or appropriate privileged role may view status

GET /api/exports/{jobId}/download
   -> re-verify DOC_EXPORT, requester, tenant, TTL, and file access permission
   -> stream file/short-lived URL with issuance controls
```

This is a **reference architecture**, not code implemented in the demo. Background workers do not inherit `SecurityContextHolder` from the request thread automatically or safely. Persist **verified requester identity, scope, and policy context**; the worker must evaluate permissions according to policy at execution/download time. Never push long-lived raw bearer tokens or serialized `Authentication` objects onto a queue for arbitrary reuse.

For bulk UPDATE/DELETE, never check permission on only the first ID. Validate **every** ID, define all-or-nothing vs. partial-success semantics explicitly, cap batch sizes, and use appropriate transactions. A single out-of-tenant record slipping into a batch operation is a breach.

## 12. Security Test Matrix to Cover

A complete matrix should test not only all 4 HTTP methods, but also different target objects:

| Caller / resource | READ | UPDATE | DELETE | EXPORT |
| --- | --- | --- | --- | --- |
| Unauthenticated | Blocked | Blocked | Blocked | Blocked |
| User with READ in tenant | Allowed on matching records | Blocked if missing EDIT | Blocked if missing DELETE | Blocked if missing EXPORT |
| User with READ+EDIT, non-owner | Readable per policy | Blocked from editing non-owned record | Separate | Separate |
| User with DELETE but no EDIT | Evaluated independently by READ | Blocked if missing EDIT | Allowed to DELETE only scoped objects | Separate |
| User with EXPORT but no READ | No | No | No | Blocked if policy requires both |
| User in another tenant | Sees no content | Cannot alter data | Cannot delete | Contains no rows from other tenant |
| User with authorities, record locked | Per READ policy | Typically blocked | Per retention policy | Per dedicated export policy |
| Caller with invalid CSRF | Read GET may succeed per auth | 403 before reaching service | 403 before reaching service | GET uses no CSRF but export checks still apply |

Other critical tests:

- Nonexistent ID vs. existing unauthorized ID: consistent 403/404 behavior without leaking content.
- UPDATE containing forbidden fields `ownerUsername`, `tenantId`, `approved`: ignored or rejected per contract, **never modifying** DB values.
- EXPORT with filters attempting cross-tenant IDs, huge `pageSize`, or CSV formula-injection characters.
- Requests containing multiple IDs: never use authorization on one ID to authorize the rest.
- After permission revocation, export files with TTL longer than policy cannot be downloaded.
- Concurrent update/delete requests: test races, version conflicts, and transaction semantics.
- Direct service bean calls in integration tests: verify `@PreAuthorize` still applies outside controllers.
- Test alternative routes returning the same documents: search, preview, attachments, history, "download original", "print", GraphQL, audit, and admin APIs.
- For multi-tenant setups, test cross-tenant READ, EDIT, DELETE, and EXPORT using valid IDs/UUIDs.

**Do not stop at checking status codes.** For rejected UPDATE/DELETE requests, verify the DB truly **did not change**; for EXPORT, inspect the file to verify **no forbidden rows/columns are present**, because an endpoint returning 200 can still leak data in the body.

## 13. Common Implementation Mistakes

1. **Lumping everything into `hasRole("USER")`:** a generic role only indicates the user exists in the system, not which operations they may run.
2. **Granting EXPORT alongside READ:** bulk downloads carry distinct risks and require a separate policy.
3. **Only hiding buttons in the frontend:** clients can call APIs directly with curl/Postman/scripts.
4. **Letting `GET /export` match a broad `GET /**` rule:** use an explicit matcher or independent service policy, and order matchers properly.
5. **Checking only that an ID exists:** an ID does not grant permission; verify tenant/owner/business rules.
6. **Returning JPA entities directly:** entities can expose tenant IDs, internal flags, or future secret columns.
7. **Using the request body to switch tenant/owner arbitrarily:** leads to mass assignment/privilege escalation.
8. **Calling `repository.findAll()` and filtering a subset before export:** leaks data easily and wastes resources; scope the query in the DB.
9. **Reusing one `canEdit` method for DELETE:** accidentally turns EDIT capability into delete permission.
10. **Forgetting to re-check on export file download:** permissions may have been revoked after the job started.
11. **Ignoring CSV formula injection:** "data-only" files can still be interpreted as formulas by spreadsheets.
12. **Relying solely on `@PreAuthorize` on methods called via `this.***`:** self-invocation can bypass the proxy.
13. **Overlooking races between check and write:** permissions/state can change; use transactions and DB predicates.
14. **Assuming `@EnableMethodSecurity` alone is enough:** you still need accurate business rules; annotations do not know tenant/owner on their own.
15. **Returning 401 when an authenticated user lacks permission:** confuses authentication with authorization; clients may uselessly re-prompt for login.
16. **Disabling CSRF to make DELETE tests easier:** when browsers send cookies automatically, that increases CSRF risk; pass valid tokens in tests instead.
17. **Using a single "admin" user across all tenants without auditing:** privileged exceptions need explicit scope, justification, and audit trails.
18. **Logging raw titles/bodies/CSV exports:** audit logs should capture operation metadata and identifiers without dumping sensitive payloads into logs.

## 14. Checklist Before Launching a New Data Feature

- [ ] Separate READ, UPDATE, DELETE, and EXPORT explicitly, defining authorities and role policies for each.
- [ ] Identify resource ID, tenant, owner, state, and business rules as decision inputs.
- [ ] Enforce permissions in the service/use case and DB query scope rather than only in the UI/URL layer.
- [ ] Enable `@EnableMethodSecurity` when using `@PreAuthorize`; test invocation through Spring proxies.
- [ ] Design output DTOs and input field allowlists; never bind sensitive system fields.
- [ ] Scope list/search READs, previews, and attachments too—not only detail GETs.
- [ ] Ensure UPDATEs handle transactions, versioning/concurrency, and field/state protection.
- [ ] Ensure DELETEs account for retention/soft-delete/attachment lifecycles, separate permissions, and auditing.
- [ ] Ensure EXPORTs require a separate authority, scoped queries, allowed columns, limits, and auditing.
- [ ] Check CSV/XLSX/PDF exports for injection, metadata leaks, and post-download protection.
- [ ] Re-verify caller, tenant, TTL, and current permissions on export job download endpoints.
- [ ] Test the full action × user × tenant × owner × state matrix, inspecting actual returned/stored data.
- [ ] Verify 401/403/404/409 behavior, CSRF, logs, and returned payloads.

### Self-Check Questions

1. Why does a user with `DOC_READ` not automatically get `DOC_EXPORT`?
2. Alice has `DOC_EDIT` and knows the ID of a document in tenant-beta. What additional conditions are missing before allowing UPDATE?
3. Why can a `GET /api/documents/**` rule cause trouble for `GET /api/documents/export`?
4. What is the difference between request authorization in `SecurityFilterChain` and object-level checks in `@PreAuthorize`?
5. Why must tests for a blocked UPDATE verify the DB is **unchanged**, not only HTTP 403?
6. What risk arises if an API returns `DocumentEntity` directly when a private field is later added to the DB?
7. An export job was created before a user's permissions were revoked; what design ensures the download link does not keep leaking data?
8. What risk exists with `@PreAuthorize` on a method invoked via `this.method()`?
9. Why is prepending `'` in `csvCell` only a mitigation rather than an absolute guarantee?
10. What goes wrong if authorization uses a client-supplied `tenantId` without verifying identity?
11. Why does `@Version` not replace checking authorization against record state?
12. When is an `UPDATE ... WHERE tenant_id = ... AND owner = ...` query safer than checking first and updating afterward?

**Answer hints:** (1) export is bulk exfiltration requiring separate functional authority and read scope; (2) tenant, owner, and state; (3) broad matcher can swallow the export route; (4) one checks the request path, the other evaluates with the ID and data policy; (5) prevents handlers from returning an error status after a mutation already ran; (6) overexposure; (7) re-check at download time, TTL/file ACL; (8) bypasses the AOP proxy; (9) spreadsheet apps parse CSV differently; (10) attacker chooses their own tenant; (11) optimistic locking does not verify who is authorized; (12) narrows the check–use window and enforces scope in the DB.

## Official Documentation

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- OWASP API Security Top 10 — API1 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 — API3 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP — CSV Injection: https://owasp.org/www-community/attacks/CSV_Injection
- Spring Data JPA — Repositories: https://docs.spring.io/spring-data/jpa/reference/repositories.html
