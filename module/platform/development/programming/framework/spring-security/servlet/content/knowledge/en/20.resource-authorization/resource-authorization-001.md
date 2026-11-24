# Resource Ownership and the Risk of IDOR When Only Checking Roles

## Lesson Objectives

In Spring Security Servlet, a request can be **validly authenticated** and the sender can have a **valid role**, yet still **not have permission for the specific resource** they are requesting. For example, Alice has ROLE_USER and is allowed to use the document viewing feature; however, document 102 belongs to Bob. If the application only checks hasRole("USER") and then fetches the record by the ID in the URL, Alice can change /documents/101 to /documents/102 to read Bob's data. This is an object-level access control flaw, commonly called **Insecure Direct Object Reference (IDOR)** or classified under **Broken Object Level Authorization (BOLA)**.

This lesson focuses on the question: **"Who does the requested object belong to, what permissions does the caller have on that specific object, and is that check applied on every access path?"**. RBAC, HTTP request matching, and authentication are only parts of the answer.

After completing this lesson, you will be able to:

1. Distinguish between authentication, role-based authorization (RBAC), ownership authorization, and tenant isolation.
2. Identify IDOR/BOLA in URLs, request bodies, queries, file downloads, exports, list/search endpoints, and state-changing APIs.
3. Explain why an API with .authenticated() or hasRole("USER") can still leak data.
4. Design appropriate owner / admin / share / tenant policies and avoid trusting owner fields sent by the client.
5. Protect resources at the Spring Security Servlet HTTP layer and service layer, especially using @EnableMethodSecurity and @PreAuthorize.
6. Combine permission checks with database queries scoped by owner/tenant, rather than relying solely on a prior check.
7. Build and run a Java 17, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA, and H2 example with Alice/Bob data and negative tests.
8. Test tricky cases: ADMIN, anonymous requests, non-existent objects, concurrent owner changes, multi-tenant setups, mass assignment, and paths that bypass controllers.
9. Build a prevention and testing checklist for IDOR on a real API.

The scope is **Spring Security Servlet + Spring MVC**. Object protection issues also apply to GraphQL, messaging, or other APIs, but the runnable example below uses HTTP Basic to make testing requests easy; the demo credentials and in-memory H2 **are not for production use**.

## 1. Right Role Does Not Mean Right Owner

Consider a document management system:

| Resource | Owner | Content |
| --- | --- | --- |
| document 101 | alice | Alice's private notes |
| document 102 | bob | Bob's private plans |
| document 103 | alice | Alice's invoice |

Both Alice and Bob have ROLE_USER. The HTTP rule is:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").hasRole("USER")
        .anyRequest().denyAll());
~~~

This only proves the sender has the USER role when the URL matches the rule; **it does not automatically ask who document 102 belongs to**. If the controller then calls repository.findById(102), Alice can receive Bob's document even though Spring Security succeeded in authenticating and checking the role.

Four independent questions:

| Question | Example Mechanism | What Is Still Unresolved? |
| --- | --- | --- |
| Who are you? | AuthenticationManager, session, Basic, OAuth2 Resource Server | Does not yet know whether you have permission to act |
| What role do you belong to? | hasRole, hasAuthority, RoleHierarchy | Does not yet know who owns the record |
| Which resource is being accessed? | URI path/query/body → database lookup | Does not yet know permissions on that record |
| Are you allowed to perform this action on that resource? | Ownership/tenant/ACL/policy, constrained queries | Must be evaluated for the specific resource and action |

**Authentication is a necessary condition, not ownership.** The documentId field sent in a request is a **client-controlled reference**, whether it is a sequential number or a hard-to-guess UUID.

### How Does an IDOR Attack Work?

~~~text
Step 1: Alice logs in validly => Authentication(name="alice", ROLE_USER)

Step 2: Alice calls GET /api/documents/101
        -> Spring Security: ROLE_USER? Yes
        -> Controller: repository.findById(101)
        -> returns alice's document 101

Step 3: Alice changes one digit: GET /api/documents/102
        -> Spring Security: ROLE_USER? Still yes
        -> Controller: repository.findById(102)
        -> returns bob's document 102  <-- data leak
~~~

This is not a password-guessing bug, login bypass, or token forgery. The attacker typically has a valid account and **simply swaps the object reference**. Therefore, reporting that "authentication works" does not prove the API is protected against IDOR.

### Are IDOR and BOLA Identical?

- **IDOR** usually describes directly accessing an object using an identifier without checking the caller's permissions on that object.
- **BOLA** emphasizes missing or broken object-level authorization in an API, which can occur even when identifiers are not obviously exposed or access paths are complex.
- The two terms overlap significantly; in technical analysis, what matters more are the **action, data source, identity, and authorization conditions**.

Do not use the IDOR label to conclude that a sequential ID by itself is a vulnerability. The vulnerability is the **missing authorization check**, not the ID format itself.

## 2. Real-World Scenarios: Attacks Do Not Stop at GET /{id}

### 2.1. Reading Someone Else's Record

~~~text
GET /api/orders/7001    -> Alice's order
GET /api/orders/7002    -> Bob's order
~~~

If both pass through .authenticated() and then repository.findById(orderId), another user can retrieve Bob's order, shipping address, or payment details.

### 2.2. Modifying or Deleting Records

~~~text
PUT /api/documents/102
{"title":"Modified"}

DELETE /api/documents/102
~~~

An API with only hasRole('USER') can allow a user to delete or edit someone else's document. This is an **integrity violation** in addition to the eavesdropping risk. Permissions must be checked per **action**: canRead does not imply canEdit, and canEdit does not imply canDelete.

### 2.3. File Download or Private Image Endpoints

~~~text
GET /api/files/f-102/download
GET /api/users/42/private-avatar
~~~

Even when files are stored in S3/MinIO or local storage, the service must still know which owner/tenant the file belongs to before granting access. If returning a presigned URL, its expiration, object scope, and issuance conditions must be restricted; never treat a long object name as an authentication mechanism.

### 2.4. List, Search, and Export

~~~text
GET /api/documents?page=1
GET /api/documents?owner=bob
POST /api/reports/export
{"documentIds":[101,102,103]}
~~~

IDOR does not only occur with a single resource ID in the path. A query like owner=bob or a list of IDs is also chosen by the client. If the backend only checks the role and queries all records, Alice can receive batches of other users' data. A batch request must **filter/check every object or query with an owner/tenant condition across the entire set**, not just check permission on the first record.

### 2.5. Nested References

~~~text
GET /api/projects/5/tasks/900
~~~

Even if Alice is allowed to view project 5, task 900 might belong to project 6 or another tenant. You must verify the **actual parent-child relationship in the database**: task.project_id == projectId and the caller has permission on the task/project, rather than inferring it from two values placed in the URL by the client.

### 2.6. Assigning Permissions via Request Body (Mass Assignment)

~~~json
{
  "title": "New invoice",
  "ownerUsername": "admin",
  "tenantId": "another-tenant"
}
~~~

If a controller binds a DTO/body directly into a JPA entity and saves it, the client can change the owner/tenant or an isAdmin field on their own. That is a form of **mass assignment / broken object property level authorization**, related to access control though not completely identical to IDOR. Editable DTOs must contain only allowed fields; owner/tenant must come from the verified identity and trusted server data, not from the request body.

## 3. Designing an Object-Based Access Policy

An easy-to-understand policy for the demo application:

- **Alice** can read and edit documents owned by Alice.
- **Bob** can read and edit documents owned by Bob.
- **ADMIN** can read any document if the product policy genuinely allows it, **but is not allowed by default to edit someone else's document**.
- **Anonymous** users cannot read or edit.
- **Non-existent documents** must not return data and must not be marked as "access granted".
- **Objects belonging to another tenant** always require a separate tenant policy, even when usernames match.

Written as predicates:

~~~text
canRead(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND (doc.ownerId == caller.id OR caller.hasPermission("document:read:any"))

canEdit(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND doc.ownerId == caller.id
    AND doc.state allows edit

canDelete(caller, doc) =
    caller.authenticated
    AND doc.exists
    AND policy-specific permission to delete
~~~

In the demo, we use username from Authentication as the owner identifier because accounts are created within the same application and usernames are fixed. **Production should prefer an immutable user ID**, combined with a tenant ID and sharing/ACL/ABAC permissions if needed.

A role like ROLE_ADMIN does not mean automatic full access to sensitive data. Only add an admin branch if the product requirement explicitly states it, with tests and auditing. When a user is suspended or permissions are revoked, you must review revalidation policies and Authentication/cache data.

### RBAC, ABAC, and ReBAC

| Model | Checks | Examples |
| --- | --- | --- |
| RBAC | Caller's role/authority | ROLE_ACCOUNTANT can open the reports screen |
| ABAC | Attributes of caller, resource, action, context | ownerId, tenantId, status, time, department |
| ReBAC | Relationships between entities | user is a project member, document is shared with user |
| Simple Ownership | Resource belongs to the caller | doc.ownerUserId == caller.userId |

In practice, these models are often combined. RBAC can decide **who can use a feature**, while ownership or ReBAC decides **which records they can use the feature on**.

## 4. Trusted Information Sources: Identity and Owner

Two data sources must be clearly distinguished:

1. **Caller identity:** Authentication verified by Spring Security through the security chain (HTTP Basic in the demo). Accessible via SecurityContextHolder or by passing the framework-provided Authentication.
2. **Actual owner:** the ownerId/tenantId field stored in the resource's database record, or a trusted authorization management source.

Values that are **not trustworthy** on their own:

- ID in the path: /api/documents/102.
- Username/ownerId in the query: ?owner=bob.
- Self-declared headers: X-User: alice or X-Tenant: t-02.
- Body: {"ownerId":"alice"}.
- Client-specified cache key.
- Client-supplied filename/storage path.

Identity can be obtained via principal claims from JWT/OIDC after the token is verified, but **Authentication.getName() is not always the username**. With many identity providers, it may be sub, email, or a configurable claim. Before comparing against the owner in the database, map it properly to the internal user ID.

Do not compare two client-supplied values and call it authorization:

~~~java
// Insecure if both owner and username come from the request:
if (requestOwner.equals(requestUsername)) {
    return documentRepository.findById(documentId);
}
~~~

Here the attacker only needs to set both to alice or bob. A proper policy must link the **verified caller** to the **actual owner of the record**.

### Do UUIDs or Random IDs Prevent IDOR?

Hard-to-guess UUIDs reduce random guessing, but do not replace authorization. IDs can still leak through URLs, logs, emails, browser history, analytics, or shared content. **Skipping ownership checks because an ID is long** is an access control vulnerability.

## 5. Where Should Permission Checks Be Placed?

A Servlet request passes through these layers:

~~~text
HTTP client
    |
FilterChainProxy / SecurityFilterChain
    |-- Authentication (who is calling?)
    |-- authorizeHttpRequests (what does the endpoint/method require?)
    |
DispatcherServlet
    |
DocumentController
    |
DocumentService
    |-- method security + policy on resource
    |
DocumentRepository
    |-- query scoped by owner/tenant, never fetching unauthorized data
    |
Database
~~~

HTTP authorization can reject unauthenticated requests or callers lacking a functional role early. However, a user with the same role can still be unauthorized to read another user's record; therefore, we check **the specific resource and action in the service**.

Main options:

- **Manual service logic:** obtain the caller from Authentication and query the record by owner/tenant; simple and clear for straightforward use cases.
- **Method security:** @EnableMethodSecurity + @PreAuthorize("@documentPermission.canRead(#id, authentication)") before executing the service.
- **Method security on controllers:** helpful, but insufficient if the service is called from jobs, consumers, or other controllers.
- **Repository query scoping:** findByIdAndOwnerUsername or WHERE owner_user_id = :callerId; prevents returning the wrong record and mitigates TOCTOU.
- **Database row-level security:** adds a defense layer when the DBMS supports it, but requires configuring the principal/tenant context properly and testing every query path.
- **Central policy/ACL engine:** suitable for complex systems with document sharing, hierarchies, organizations, and project memberships.

Different protection layers provide **defense in depth**, not a reason to duplicate three inconsistent copies of authorization logic. Business policy should be defined in one place and used consistently across entry points, while repository queries enforce data boundaries.

### Why Is HTTP-Only Insufficient for All Paths?

The same DocumentService.read(id) can be invoked by a REST controller, a GraphQL resolver, a message consumer, or another service. A requestMatchers("/api/**") rule only evaluates HTTP requests entering that chain and does not run when a scheduled job calls a Java method. With a service method protected via a Spring AOP proxy, the policy sits closer to business logic; however, self-invocation or a controller calling a repository directly can still bypass it, so sound architecture and tests are required.

## 6. Common Technical Mistakes Before Hands-On Practice

### 6.1. Using Only hasRole('USER')

~~~java
@PreAuthorize("hasRole('USER')")
public DocumentDto read(Long documentId) {
    return mapper.toDto(repository.findById(documentId).orElseThrow());
}
~~~

If both Alice and Bob have ROLE_USER, both can read any document ID. This annotation only expresses a general role and does not constrain the owner.

### 6.2. Only Comparing the Path User with Authentication

~~~java
@PreAuthorize("#username == authentication.name")
public DocumentDto read(String username, Long documentId) {
    return mapper.toDto(repository.findById(documentId).orElseThrow());
}
~~~

Even if username matches Authentication, documentId could belong to someone else. The username parameter **does not prove** that document 102 belongs to that username. You must tie documentId to the record in the database.

### 6.3. Reading and Returning Data First, Checking Only on the Client

~~~javascript
// Wrong: the frontend hides others' documents merely by hiding the button.
// Once the backend sends the data, an information leak has already occurred.
if (loggedInUser !== document.ownerUsername) {
    hideDownloadButton();
}
~~~

Frontend permissions are useful for UX but are not a security boundary. The backend must deny access **before sending any body, file, or signed URL**.

### 6.4. Using findById Instead of an Owner-Scoped Query

~~~java
repository.findById(documentId);
~~~

Not every findById call is wrong, but if a service serves regular users without a guaranteed owner check, it easily becomes an IDOR source.

You can use:

~~~java
repository.findByIdAndOwnerUsername(
        documentId, authentication.getName());
~~~

Or with a tenant:

~~~sql
SELECT id, owner_user_id, tenant_id, title
FROM documents
WHERE id = :document_id
  AND owner_user_id = :authenticated_user_id
  AND tenant_id = :authenticated_tenant_id;
~~~

The authenticated_* parameters must come from the verified identity and server-determined scope, never directly from the request.

## 7. Complete Example: Spring Boot, Spring Security, and H2

Let's build a simple document API:

- GET /api/documents/{id}: requires an authenticated user at the HTTP layer; the service allows only the owner or ADMIN to read the record.
- PUT /api/documents/{id}: requires an authenticated user; the service allows **only the owner** to change the title—even ADMIN has no edit privilege in this demo.
- Seed data: document 101 owned by Alice and document 102 owned by Bob.
- The USER role is not sufficient to access another user's record.
- Method security verifies ownership via Spring Data JPA.
- Repository queries scope by owner on regular user read/edit paths.
- Tests cover both HTTP/CSRF and direct calls to the Spring-managed service bean.

The application uses **Java 17**, **Spring Boot 3.3.5**, **Spring Security 6.x via Boot dependency management**, Spring Data JPA, and in-memory H2. HTTP Basic is used for a UI-free demo; production must use HTTPS and appropriate user/credential management.

### 7.1. Structure

~~~text
resource-ownership-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (Gradle Wrapper if present)
  src/main/java/dev/example/ownership/
    OwnershipApplication.java
    SecurityConfig.java
    DocumentEntity.java
    DocumentRepository.java
    DocumentPermission.java
    DocumentService.java
    DocumentController.java
  src/test/java/dev/example/ownership/
    DocumentOwnershipIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'resource-ownership-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot starters manage compatible dependency versions. If you use Boot 4 or another Spring Security version, consult that specific version's documentation as APIs/default configs may change. Do not manually mix spring-security-* versions.

### 7.2. Main Application and Data Seeding

File src/main/java/dev/example/ownership/OwnershipApplication.java:

~~~java
package dev.example.ownership;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(DocumentRepository documents) {
        return args -> {
            if (!documents.existsById(101L)) {
                documents.save(new DocumentEntity(
                        101L, "alice", "Alice private notes"));
            }
            if (!documents.existsById(102L)) {
                documents.save(new DocumentEntity(
                        102L, "bob", "Bob private plans"));
            }
        };
    }
}
~~~

Fixed IDs make it easy to reproduce IDOR attacks and write tests with clear expectations. In-memory H2 is created by Boot for the application lifecycle; this is demo data, not a production database. Tests will clean and re-seed data before each test to avoid order dependency.

### 7.3. Entity: Owner Lives in the Database, Not Decided by the Client

File src/main/java/dev/example/ownership/DocumentEntity.java:

~~~java
package dev.example.ownership;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "demo_documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false, updatable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected DocumentEntity() {
    }

    public DocumentEntity(
            Long id, String ownerUsername, String title) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

Using @Column(updatable = false) on ownerUsername in the demo shows that changing the title does not accidentally change the owner. In a real system, ownership transfer is a **separate use case** with strict authorization checks, transactions, and auditing; you should not rely solely on this annotation as an absolute security mechanism.

Never accept DocumentEntity directly as a @RequestBody for renaming: the client could submit disallowed properties. Create a request DTO containing only title as shown below.

### 7.4. Repository

File src/main/java/dev/example/ownership/DocumentRepository.java:

~~~java
package dev.example.ownership;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    boolean existsByIdAndOwnerUsername(
            Long id, String ownerUsername);

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);
}
~~~

Spring Data JPA derives queries from method names matching entity properties. OwnerUsername comes from Authentication on the server; **do not** pass an unverified ownerUsername request parameter here.

### 7.5. SecurityConfig: Two Layers—HTTP and Method Security

File src/main/java/dev/example/ownership/SecurityConfig.java:

~~~java
package dev.example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents/*")
                        .authenticated()
                        .requestMatchers(
                                HttpMethod.PUT, "/api/documents/*")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

In the demo, the HTTP rule intentionally requires only authenticated() for GET/PUT. This makes it clear that **the HTTP layer alone cannot decide permissions on a document ID**; that is the service's responsibility. anyRequest().denyAll() protects all undeclared routes/methods.

@EnableMethodSecurity enables evaluation of annotations like @PreAuthorize on Spring-managed beans; it does not auto-generate owner checks. Never use web.ignoring() to bypass Spring Security for business endpoints.

The demo code does not disable CSRF. Therefore, PUT must send a valid CSRF token in tests; if you try PUT with curl using only HTTP Basic and no token, CsrfFilter may return 403 **before** the service gets a chance to check ownership. Do not confuse "blocked by CSRF" with "IDOR is prevented".

### 7.6. DocumentPermission: Owner/Admin Policy Using Real Data

File src/main/java/dev/example/ownership/DocumentPermission.java:

~~~java
package dev.example.ownership;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPermission")
public class DocumentPermission {

    private final DocumentRepository documents;

    public DocumentPermission(DocumentRepository documents) {
        this.documents = documents;
    }

    public boolean canRead(Long id, Authentication authentication) {
        if (id == null || !isAuthenticatedUser(authentication)) {
            return false;
        }
        if (isAdmin(authentication)) {
            return documents.existsById(id);
        }
        return documents.existsByIdAndOwnerUsername(
                id, authentication.getName());
    }

    public boolean canEdit(Long id, Authentication authentication) {
        return id != null
                && isAuthenticatedUser(authentication)
                && documents.existsByIdAndOwnerUsername(
                        id, authentication.getName());
    }

    public boolean isAdmin(Authentication authentication) {
        return isAuthenticatedUser(authentication)
                && authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));
    }

    private boolean isAuthenticatedUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Because the policy checks the actual document ID from the repository, a ROLE_USER user is not granted access to an ID they do not own. ADMIN is granted read access according to the example policy; canEdit has no ADMIN branch.

An important note on anonymous users: AnonymousAuthenticationToken can return isAuthenticated() as true by implementation, yet it does not represent a real user. The policy excludes anonymous tokens and rejects null IDs. If your environment uses other authentication types, define what constitutes a trusted authenticated principal.

### 7.7. DocumentService: Never Return Data Outside Owner Scope

File src/main/java/dev/example/ownership/DocumentService.java:

~~~java
package dev.example.ownership;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;
    private final DocumentPermission permission;

    public DocumentService(
            DocumentRepository documents,
            DocumentPermission permission) {
        this.documents = documents;
        this.permission = permission;
    }

    @PreAuthorize(
            "@documentPermission.canRead(#id, authentication)")
    @Transactional(readOnly = true)
    public DocumentView read(@P("id") Long id) {
        Authentication caller =
                SecurityContextHolder.getContext().getAuthentication();

        DocumentEntity entity;
        if (permission.isAdmin(caller)) {
            entity = documents.findById(id)
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        } else {
            entity = documents.findByIdAndOwnerUsername(
                            id, caller.getName())
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        }

        return DocumentView.from(entity);
    }

    @PreAuthorize(
            "@documentPermission.canEdit(#id, authentication)")
    @Transactional
    public DocumentView rename(
            @P("id") Long id, String newTitle) {

        if (newTitle == null
                || newTitle.isBlank()
                || newTitle.length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication caller =
                SecurityContextHolder.getContext().getAuthentication();

        if (caller == null) {
            throw new AccessDeniedException("No caller");
        }

        DocumentEntity entity =
                documents.findByIdAndOwnerUsername(
                        id, caller.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));

        entity.rename(newTitle.trim());
        return DocumentView.from(entity);
    }

    public record DocumentView(
            Long id, String ownerUsername, String title) {
        static DocumentView from(DocumentEntity entity) {
            return new DocumentView(
                    entity.getId(),
                    entity.getOwnerUsername(),
                    entity.getTitle());
        }
    }
}
~~~

Key takeaways:

- **@PreAuthorize** ensures the policy runs when the method is called **through a Spring proxy**, before the body executes.
- **@P("id")** keeps the parameter name consistent for the #id expression even across different compiler parameter-name settings.
- **DocumentPermission** reads the owner from the database, not from the request body.
- **DocumentService.read** also uses an owner-scoped query for regular users. This is an extra layer of defense if owner data changes or an unsafe code path exists; ADMIN takes a separate branch per policy.
- **DocumentService.rename** fetches only a record owned by the caller, never implicitly letting an admin modify someone else's record.
- **@Transactional** ensures JPA manages the entity within a transaction; the title change is flushed/dirty-checked by Hibernate on commit.
- **DocumentView** is the DTO returned to the client, avoiding returning a JPA entity with unintended object graphs.
- **AccessDeniedException** for documents not owned by the user prevents data leakage. A product may choose 404 to hide resource existence, but must be consistent and never leak owner details in error messages.

One production nuance to analyze: the existsBy... policy check happens before the method body runs and may execute outside the method's transaction depending on advisor ordering. If owner/tenant changes concurrently between check and use, **TOCTOU** can still occur. Thus the pattern also executes an owner-conditioned query inside the service; sensitive operations need appropriate isolation, locking, or conditional updates for the domain.

### 7.8. Controller Accepts Only the ID and Allowed Editable Fields

File src/main/java/dev/example/ownership/DocumentController.java:

~~~java
package dev.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
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

    @GetMapping("/{id}")
    public DocumentService.DocumentView read(
            @PathVariable("id") Long id) {
        return service.read(id);
    }

    @PutMapping("/{id}")
    public DocumentService.DocumentView rename(
            @PathVariable("id") Long id,
            @RequestBody RenameDocumentRequest request) {
        return service.rename(id, request.title());
    }

    public record RenameDocumentRequest(String title) {
    }
}
~~~

The controller does not accept ownerUsername in RenameDocumentRequest, so the client cannot change the owner via this endpoint. If JSON includes extra undefined fields, Jackson configuration may ignore or reject them depending on settings; **either way, DocumentService ignores that value**. If the API must reject unknown properties, configure validation/deserialization explicitly and test it.

Do not add a @PostMapping that assigns ownerUsername from the request to "let users send documents to others" before designing a proper ownership transfer use case.

### 7.9. Running with Gradle

In a project with Gradle Wrapper, run:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use:

~~~powershell
.\gradlew.bat bootRun
~~~

Use curl with Basic auth only on localhost for the demo:

~~~bash
curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/102

curl -i -u bob:bob-demo-pass \
  http://localhost:8080/api/documents/102

curl -i -u admin:admin-demo-pass \
  http://localhost:8080/api/documents/102

curl -i http://localhost:8080/api/documents/101
~~~

Expected logical results:

| Request | Result |
| --- | --- |
| Alice reads document 101 | 200, JSON with id=101, ownerUsername=alice |
| Alice reads document 102 | 403, does not return Bob's title |
| Bob reads document 102 | 200, JSON with id=102, ownerUsername=bob |
| ADMIN reads document 102 | 200, per canRead exception |
| Anonymous reads document 101 | 401 with WWW-Authenticate per HTTP Basic |
| Bob edits document 101 with valid CSRF | 403, title unchanged |
| Bob edits document 102 with valid CSRF | 200, title updated |
| ADMIN edits document 102 with valid CSRF | 403 in the example policy |

**Never use HTTP Basic over plain public HTTP**: Base64 does not encrypt credentials. Localhost is for illustration only; production requires HTTPS and a proper account lifecycle mechanism.

### 7.10. Integration Testing: Catching IDOR at Both HTTP and Service Layers

File src/test/java/dev/example/ownership/DocumentOwnershipIntegrationTest.java:

~~~java
package dev.example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentOwnershipIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository documents;

    @Autowired
    DocumentService service;

    @BeforeEach
    void resetData() {
        documents.deleteAll();
        documents.save(new DocumentEntity(
                101L, "alice", "Alice private notes"));
        documents.save(new DocumentEntity(
                102L, "bob", "Bob private plans"));
    }

    @Test
    void ownerCanReadByHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.ownerUsername").value("alice"));
    }

    @Test
    void changingIdCannotRevealOtherUsersDocument()
            throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void adminReadExceptionIsExplicit() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(102));
    }

    @Test
    void anonymousRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void otherUserCannotRenameAndDataDoesNotChange()
            throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Illegal change\"}"))
                .andExpect(status().isForbidden());

        assertThat(documents.findById(101L).orElseThrow()
                .getTitle()).isEqualTo("Alice private notes");
    }

    @Test
    void ownerCanRenameWithCsrf() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated title"));

        assertThat(documents.findById(101L).orElseThrow()
                .getTitle()).isEqualTo("Updated title");
    }

    @Test
    void missingCsrfIsRejectedIndependentlyOfOwner()
            throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .contentType("application/json")
                        .content("{\"title\":\"No csrf\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCannotRenameWithoutExplicitPermission()
            throws Exception {
        mvc.perform(put("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Admin modified\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceCallStillRejectsBobDocument() {
        assertThatThrownBy(() -> service.read(102L))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void directServiceCallAllowsOwner() {
        assertThat(service.read(102L).ownerUsername())
                .isEqualTo("bob");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directServiceCallRejectsUnauthorizedEdit() {
        assertThatThrownBy(() ->
                service.rename(102L, "Must not change"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

This test suite checks **both responses and actual data**: changing an ID to someone else's document must return 403; an unauthorized PUT must not silently modify the database; the owner can edit with valid CSRF; ADMIN cannot edit if the policy does not grant it.

Testing DocumentService directly with @WithMockUser proves that method security applies when invoked via a **Spring-managed proxy**, not only when requests go through HTTP's SecurityFilterChain. If you only test the controller with a mocked service, you can miss the most important authorization layer.

@BeforeEach resets the data before each test, avoiding test-order dependencies from title updates. This test uses in-memory H2 and does not replace locking/concurrency testing against a production database.

## 8. Where Should @PreAuthorize Be Placed?

### On the Controller

~~~java
@PreAuthorize("hasRole('USER')")
@GetMapping("/api/documents/{id}")
public DocumentView read(@PathVariable Long id) {
    return documentService.read(id);
}
~~~

This condition only checks a general role, **not ownership**. Furthermore, if the service is invoked from a new controller, job, or consumer, the annotation on the old controller will not protect that call path.

### On the Service Boundary

~~~java
@PreAuthorize(
        "@documentPermission.canRead(#id, authentication)")
public DocumentView read(@P("id") Long id) {
    // ...
}
~~~

This keeps the policy closer to business logic when every entry point calls the same service bean via its proxy. However, if a controller calls a repository directly, or another method in the same bean calls the protected method via this.read(...), the AOP interceptor may not run. Therefore, clean architecture is required, not just annotations.

### What Is Spring AOP Self-Invocation?

~~~java
@Service
public class UnsafeDemoService {

    public void exportMany(Long id) {
        readSensitive(id); // internal call via this, usually bypasses proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void readSensitive(Long id) {
        // sensitive operation
    }
}
~~~

If exportMany is called from outside the bean without a policy, the call to readSensitive within the same object can bypass @PreAuthorize. Solution: protect the real public entry point, or extract the protected operation into a separate bean that is injected and called through a proxy. Never put the sole policy on a private/final method expecting Spring AOP to intercept every call.

### @PreAuthorize or @PostAuthorize?

- **@PreAuthorize:** decides before execution, appropriate when the policy can be evaluated from parameters and a safe authorization query.
- **@PostAuthorize:** can inspect returnObject after the method runs; use with caution if the method has side effects or loads large amounts of data.
- **@PostFilter:** can filter a collection after loading, but is usually less efficient than a database query already filtered by owner/tenant, and carries risk if data is logged/cached before filtering.
- **Custom AuthorizationManager/policy service:** useful when conditions are complex and need reuse across multiple endpoints and methods.

An example where @PostAuthorize must not be used as the sole control for data modification:

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentView rename(Long id, String title) {
    // May have already updated the database before the policy runs.
}
~~~

The method may have already produced side effects before being denied. Throwing an exception does not automatically revert external side effects (messages, emails, external APIs), and transaction rollback behavior also depends on advisor/transaction configuration.

## 9. Preventing TOCTOU: Time of Check vs. Time of Use

Suppose the policy reads the owner from the database:

~~~text
T1: canRead(101, alice) -> true because 101's owner is alice
T2: another transaction transfers 101's owner to bob
T3: service reads record 101 via findById(101)
~~~

If T3 lacks an owner condition, Alice can read data after ownership changed. This is a **time-of-check to time-of-use (TOCTOU)** situation. Placing @PreAuthorize and @Transactional near each other **does not automatically guarantee an atomic check and query**; AOP advisor ordering and transaction isolation can affect behavior.

Mitigations:

1. For reads, **include owner/tenant in the fetching query**, such as findByIdAndOwnerUsername, so rows belonging to others are never returned at query time.
2. For writes, consider a **conditional UPDATE** by id, owner, and state, and check affected rows.
3. When transferring ownership or resource state, use transactions and locking/versioning per domain rules.
4. For sharing permissions or tenant membership, verify validity at execution time rather than trusting stale caches.
5. Never treat an existsBy... check before a transaction as permanent proof for all subsequent actions.

Illustrative SQL example:

~~~sql
UPDATE demo_documents
SET title = :new_title
WHERE id = :document_id
  AND owner_username = :authenticated_username;
~~~

If update count = 0, do not treat the operation as authorized or successful. In production, the query may also need tenant_id, DRAFT status, and a version/lock column. This illustrative SQL is not a guarantee that all race conditions are solved if isolation or other conditions are missing.

### Be Careful with Permissions in Caches

A cache keyed by documentId storing DocumentView without considering tenant/owner can accidentally serve another user's data. Cache data scoped by security boundaries or cache internal records and always perform authorization when returning to the caller. Never cache "hasAccess = true" indefinitely when roles or ownership can change.

## 10. Multi-Tenancy: Username Is Not a Strong Enough Boundary

In SaaS, two users named "alice" can exist in tenants T1 and T2, or one user can have permissions across multiple tenants. A policy comparing only ownerUsername can misassign access if data does not identify the tenant.

A safer model:

~~~text
Caller: userId=U101, activeTenantId=T1
Document 101: ownerId=U101, tenantId=T1  -> may be allowed
Document 102: ownerId=U101, tenantId=T2  -> must verify membership/permissions in T2
Document 103: ownerId=U202, tenantId=T1  -> requires explicit sharing/role
~~~

Use the identity provider/database to verify userId and tenant memberships. If a request sends X-Tenant or /tenants/{tenantId}, that is only the **requested tenant**, not proof that the user has access in that tenant. The service must verify membership and tenant-scoped authorities using a trusted data source.

A typical query:

~~~sql
SELECT id, owner_user_id, tenant_id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND (
      owner_user_id = :authenticated_user_id
      OR EXISTS (
          SELECT 1
          FROM document_shares
          WHERE document_shares.document_id = documents.id
            AND document_shares.grantee_user_id =
                :authenticated_user_id
      )
  );
~~~

This is **illustrative design SQL**; the document_shares schema and corresponding classes do not exist in the demo project. Do not copy this into the H2 demo without the table. Production requires indexes, query plans, constraints, and sharing permission reviews.

### Do Not Confuse "Tenant Admin" with "System-Wide Admin"

Someone with ROLE_ADMIN in tenant A is not automatically allowed to read tenant B's documents. Design principals/authorities to reflect permission scope, such as tenant roles, resource permissions, or ACLs. Do not use global hasRole("ADMIN") as a shortcut in a multi-tenant application when admin rights are strictly local.

## 11. When a Resource Does Not Exist or Access Is Denied: 403 or 404?

Two common response patterns:

- **403 Forbidden:** indicates the caller is authenticated but lacks permission for the object. Easy to diagnose with clear semantics.
- **404 Not Found:** can be used to avoid revealing whether an object exists to an unauthorized user; especially useful in private document APIs.

Both can be valid depending on product requirements. What matters: **never return a body containing the title/owner, stack trace, file metadata, or other messages that leak document details** when denying access.

Do not rely on 404 as a security measure if another search/export/preview endpoint still leaks data. Never replace AccessDeniedException with 404 while skipping permission checks.

When the policy must verify access before allowing retrieval, you can use a single owner-scoped query: if nothing is found within the caller's scope, return a uniform response without confirming whether the record exists.

### Enumeration Risk

If IDs are sequential and the API responds noticeably differently between real and non-existent IDs (status code, timing, response size), an attacker can enumerate the document list. Define a consistent response contract along with appropriate rate limiting/monitoring. However, anti-enumeration measures **cannot replace object authorization**.

## 12. Enforcing Permissions in Non-HTTP Tasks

HTTP authorization only runs when a request enters a SecurityFilterChain with a matching rule. A service can be called directly from:

- Scheduled jobs;
- Message consumers;
- Batch processors;
- GraphQL resolvers or gRPC handlers with separate authentication;
- Background event listeners;
- Other services in the same JVM.

@PreAuthorize on a Spring-managed service bean intercepts calls **through a proxy**, but requires a clear Authentication in SecurityContext. For system jobs without a browser session, never pre-populate an all-powerful Authentication just to bypass policies. Instead, create a **service identity** with least privilege, a clear use case, and auditability, or a dedicated system API with its own policy.

SecurityContextHolder is usually thread-bound; @Async or executors may not inherit the context. You can use DelegatingSecurityContextAsyncTaskExecutor or an appropriate context propagation mechanism, while clearly defining who is delegated and the context lifetime. Missing Authentication should **fail closed**, rather than trusting background code and skipping authorization.

If a controller or consumer calls a repository directly without going through a protected service, method security cannot save you. Enforce module boundaries in architecture and test every entry point.

## 13. Anti-IDOR/BOLA Test Matrix for Real Applications

A test suite containing only "alice accesses document 101 successfully" is not enough. Aim to catch legitimate users escalating privileges across objects:

| Actor | Action | Resource | Expected Outcome |
| --- | --- | --- | --- |
| anonymous | GET | Alice doc 101 | 401/challenge |
| alice | GET | Alice doc 101 | Allowed |
| alice | GET | Bob doc 102 | Denied |
| bob | GET | Bob doc 102 | Allowed |
| bob | PUT | Alice doc 101 | Denied and DB unchanged |
| admin | GET | Alice doc 101 | Allowed only if defined by policy |
| admin | PUT | Alice doc 101 | Denied if policy does not grant edit |
| alice | GET | Non-existent ID | No data leaked |
| alice | GET | Existing ID in another tenant | Denied, do not reveal tenant |
| alice | GET list/search | owner=bob | Cannot see Bob's data |
| alice | POST bulk export | IDs from both Alice and Bob | Does not export Bob's data |
| alice | GET download | Bob's file | Does not return file/presigned URL |
| alice | PUT body | owner=admin | Cannot self-transfer owner |
| alice | GET | Differently formatted/encoded ID string | Does not bypass route/policy |
| alice | direct service call | Bob doc 102 | AccessDeniedException |

Effective testing practices:

1. **Positive case**: authorized user actually succeeds.
2. **Negative cross-user case**: user with the same ROLE_USER but different owner is blocked.
3. **Integrity check**: after a denied PUT/DELETE, the database remains unchanged.
4. **Tenant boundary**: same username in a different tenant cannot access the resource.
5. **Bulk list/export**: no item outside the permitted scope leaks through.
6. **Alternate endpoints**: preview, download, export, thumbnail, soft-delete, version history, comments, attachments.
7. **Direct service test**: method security rejects calls independently of HTTP rules.
8. **Concurrent ownership change**: verify locking/transactions/queries prevent critical race conditions.
9. **Logging/monitoring**: denied attempts do not leak raw tokens or private data.

When you need to test production database semantics, use integration tests with a containerized DB (such as Testcontainers) and concurrent transactions. H2 is only a lightweight base to demonstrate Spring MVC/Spring Security/JPA and does not fully prove isolation/concurrency for production databases.

## 14. Common Real-World Pitfalls

### Pitfall 1 — Having hasRole("USER") and Assuming All Documents Are Safe

ROLE_USER checks general group permissions, not Bob's ownership of document 102. Add an owner/tenant object policy and test a user with the same role accessing another user's ID.

### Pitfall 2 — Comparing the Owner in the URL with the Logged-In Username

With a URL like /users/alice/documents/102, an attacker can keep alice in the path while passing Bob's documentId=102. Always look up the document-owner relationship in the database; never trust a path user as truth about the record.

### Pitfall 3 — Using Request Body ownerUsername to Grant Access

The client can send ownerUsername=alice. Comparing this field against authentication.name still does not verify the record's real owner. Only obtain the owner from a trusted repository/ACL.

### Pitfall 4 — Randomizing IDs and Treating IDOR as Fixed

Hard-to-guess UUIDs do not replace object-level authorization. IDs can leak via links, logs, or other APIs. Object authorization is still mandatory.

### Pitfall 5 — Checking Only One Item and Exporting the Whole List

A bulk request contains IDs [101,102]. If code checks the owner of 101 and then calls repository.findAllById(...) for both, Bob's document can be exported. Apply the predicate to **every document**, or query the list directly scoped by owner/tenant.

### Pitfall 6 — Testing Only GET and Forgetting PUT/DELETE

RBAC might inadvertently apply the same read permission to delete actions. You need method/action-specific policies and must test not only status codes but also database state.

### Pitfall 7 — Controller Bypassing DocumentService

Even if @PreAuthorize sits on the service, a controller calling repository.findById and returning the entity bypasses the service. Block direct repository access from controllers and review dependency graphs/use cases.

### Pitfall 8 — Spring AOP Self-Invocation

A service calling this.readSensitive() inside the same class can bypass the @PreAuthorize proxy. Protect the public entry point or extract the protected method into a separate bean, and add tests.

### Pitfall 9 — Mistaking AnonymousAuthenticationToken for a Real Login

An anonymous token's isAuthenticated() can return true depending on implementation. Custom policies must distinguish anonymous tokens from real authenticated users; you can use the isAuthenticated() SpEL expression or check the token type explicitly.

### Pitfall 10 — Missing CSRF Mistaken for a Successful Owner Check

A POST/PUT with a browser cookie may be blocked with 403 by CsrfFilter before reaching the service. Ownership tests on unsafe HTTP methods must include a valid CSRF token to prove the right layer denied the request.

### Pitfall 11 — Global Admin in a Multi-Tenant SaaS

hasRole('ADMIN') without tenant scoping allows a T1 admin to view T2. Use tenant-specific permissions, tenant memberships, and data scoping.

### Pitfall 12 — Ownership Changing Between Policy Check and Query

existsByIdAndOwner... before a transaction is not permanent proof. Use owner-scoped queries, conditional updates, and domain-appropriate versioning/locking.

### Pitfall 13 — Returning 403 While Logging Someone Else's Record

Never log full DocumentEntity objects, attachments, customer PII, or JWTs in an access denied handler. Audit only necessary metadata with restricted log access.

### Pitfall 14 — Reading the Wrong Principal Name After Changing Identity Providers

JWT getName may return sub instead of username. If the database stores username and the policy compares against a different subject, valid users may be rejected or mis-mapped. Use an internal stable user ID.

### Pitfall 15 — Client Supplying an Arbitrary tenantId

An X-Tenant header or /tenants/T2 path is only the requested tenant. You must verify the caller's membership and scope in the database; never treat a client-set header as authority.

### Pitfall 16 — Relying Only on @PostAuthorize After Side Effects Occur

If a method modifies data or calls external systems before evaluating returnObject.owner, denial may come too late. Prefer checking before the operation alongside proper DB/transaction constraints.

## 15. Production Implementation Checklist

1. **Identify all sensitive resource types:** documents, invoices, orders, files, messages, images, comments, exports.
2. **Enumerate all actions:** read, create, update, delete, download, share, transfer, approve, export.
3. **Define object policies:** owner, tenant, status, share permissions, and admin scope per exact requirements.
4. **Authenticate callers from trusted sources:** SecurityContext/validated claims; never trust self-declared userId/roles from requests.
5. **Use immutable userId and tenantId** in real systems; avoid comparing mutable or non-globally-unique usernames.
6. **Protect the HTTP layer:** authentication, method/path matchers, deny-by-default, and CSRF when credentials rely on cookies.
7. **Protect service use cases:** @EnableMethodSecurity + @PreAuthorize or policy services, not just the USER role.
8. **Enforce repository query scoping** by owner/tenant; avoid fetching records first and filtering on the frontend.
9. **Prevent mass assignment** on owner/tenant/admin/sensitive state via update DTOs.
10. **Combine locking/versioning/isolation** for permission changes and sensitive data modifications.
11. **Protect every access path:** detail, list, export, download, thumbnails, attachments, search, GraphQL, batch.
12. **Design safe API responses:** consistent 403/404 without leaking owner/title/existence of unauthorized documents.
13. **Test cross-user/cross-tenant** access with the same role, not only positive tests.
14. **Verify data remains unmodified** after 403 requests rather than checking status codes alone.
15. **Test services through Spring proxies** and prevent self-invocation/repository bypasses.
16. **Ensure admin exceptions are intentional**, audited, and scoped to tenant/organization.
17. **Test permission revocation, ownership transfer, and concurrency**; do not cache access grants indefinitely.
18. **Monitor ID enumeration attempts** with appropriate rate limiting and anomaly detection, without replacing object authorization.
19. **Protect logs/caches/backups** so sensitive documents do not leak through less protected channels than the main API.
20. **Review policies whenever adding new endpoints or schemas**, treating them as security changes requiring regression tests.

## 16. Self-Check Questions

**Question 1.** Alice and Bob both have ROLE_USER. If SecurityFilterChain uses hasRole("USER"), is Alice guaranteed to be blocked when accessing Bob's document?

**Answer:** No. The USER role permits using the feature; it does not verify the record's owner. The service/repository must check permissions on the object.

**Question 2.** Why can changing /api/documents/101 to /api/documents/102 cause IDOR even when Alice is validly logged in?

**Answer:** Both requests carry the same Authentication. If the backend only reads the ID and calls repository.findById without verifying who owns record 102, Bob's data can be returned to Alice.

**Question 3.** Is using UUIDs instead of sequential IDs enough?

**Answer:** No. UUIDs reduce guessability but do not replace authorization; IDs can be leaked or shared unintentionally.

**Question 4.** Can ownerUsername sent by the client in JSON be used to check permissions?

**Answer:** Not as the sole proof. The client can forge it; the real owner must come from the database/ACL, and the caller from the verified Authentication.

**Question 5.** Should ADMIN automatically be allowed to edit every document?

**Answer:** Not by default. Each product needs an explicit policy; for example, this lesson lets ADMIN read but not edit someone else's document.

**Question 6.** Why is @PreAuthorize on a service more useful than placing it only on a controller?

**Answer:** Multiple entry points can invoke the same service through its Spring proxy. Putting the policy on the service is closer to business logic and does not depend solely on a single URL.

**Question 7.** If a service calls a protected method in the same bean using this.method(), will the policy always run?

**Answer:** No. With a Spring AOP proxy, self-invocation usually bypasses the interceptor; protect the public entry point or extract a separate bean.

**Question 8.** When Alice sends a PUT to Bob's document and gets 403, does that prove there is no IDOR?

**Answer:** Not necessarily, if the 403 came from a missing CSRF token. You must send a valid CSRF token when testing service permissions and verify the database did not change.

**Question 9.** When canRead checks the owner at T1, but another transaction at T2 transfers ownership before the read executes, what should you do?

**Answer:** Mitigate TOCTOU by scoping the fetch query by owner/tenant at retrieval time, using transactions/locking, or using conditional updates suited to the use case.

**Question 10.** Why is GET /api/documents?owner=bob still dangerous if only roles are checked?

**Answer:** The owner query parameter is chosen by the client. The backend must filter by the verified caller/tenant rather than trusting the owner query parameter as authorization.

**Question 11.** A multi-tenant app has a user "alice" in both T1 and T2. Is comparing only ownerUsername sufficient?

**Answer:** No. You need an internal userId and explicit tenantId/membership to prevent cross-tenant access.

**Question 12.** What must be checked in a bulk export containing both Alice's and Bob's IDs?

**Answer:** Every exported item must be within the caller's authorized scope, not just the first item. Never silently include Bob's data if the caller is only allowed to view Alice's.

## Conclusion

**Roles indicate which permission group a user belongs to; ownership indicates which specific records a user has rights on.** When an API only checks ROLE_USER or authenticated() and then accesses documents by a client-chosen ID, IDOR/BOLA flaws can occur even when login and Spring Security HTTP rules work properly.

To prevent this, place **object-level authorization** in the service/policy, get the caller from the verified Authentication, get owner/tenant from the database, and constrain actual queries to the permitted scope. Never treat secret IDs, self-declared headers, frontend checks, or CSRF-induced 403s as proof of ownership.

Test **users with the same role but different owners**, write/delete actions, lists/exports/downloads, tenant boundaries, direct service calls, and concurrent updates. An effective security mechanism must reject the wrong caller **before any private data is returned or modified**.