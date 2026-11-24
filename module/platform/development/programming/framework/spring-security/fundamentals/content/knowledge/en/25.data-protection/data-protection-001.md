# Ownership-Based Authorization to Prevent Unauthorized Direct Object Access

> **Context:** Spring Security — fundamentals / Data Protection. This lesson focuses on **object-level authorization** (checking permissions on **individual data objects**) in Java 17+, Spring Boot 3.x, and Spring Security 6.x (Servlet) applications. Ownership-based authorization prevents **IDOR** (*Insecure Direct Object References*) and **BOLA** (*Broken Object Level Authorization*) when a client alters an ID to view, modify, or delete someone else's data.

## 1. The Problem: An Authenticated User Can Still Read Someone Else's Data

Suppose an application stores private documents:

| Document ID | Owner | Content |
|---|---|---|
| `101` | `alice` | Alice's private notes |
| `202` | `bob` | Bob's private notes |

Alice is logged in and allowed to call `GET /api/documents/101`. If the backend code only checks "is logged in" and queries by `id`, Alice can change the URL to `GET /api/documents/202` and receive Bob's document.

**Vulnerable** code example:

~~~java
// Wrong: only checks that the request is authenticated in SecurityFilterChain.
@GetMapping("/api/documents/{id}")
DocumentEntity get(@PathVariable Long id) {
    return documentRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));
}
~~~

If the route only has `.authenticated()`, Spring Security knows **who is calling** but has not verified **which records they are allowed to access**. Role-based authorization policies such as `hasRole("USER")` are not enough either: both Alice and Bob can hold `ROLE_USER`.

**BOLA** occurs when an API lets a user invoke a valid function without checking permissions on the **specific object** being referenced. **IDOR** is a common manifestation of this flaw when an ID or path allows direct access to an unauthorized resource. The reference can be an auto-incrementing number, UUID, slug, filename, object-storage key, ID in JSON, query string, header, or nested relationship.

Example:

~~~http
GET /api/documents/202 HTTP/1.1
Authorization: Basic <credentials-of-alice>
~~~

An attacker **does not necessarily need to break authentication**. A legitimate user can guess or obtain an ID from logs, URLs, accidental shares, other APIs, or displayed output and try to access another resource.

**Core principle:** the server must verify `authenticated caller + actual object + requested action + data scope (e.g., tenant)` on **every** read and write path. Never treat the client's knowledge of an ID as proof of authorization.

## 2. How Do Authentication, Authorization, and Ownership Differ?

- **Authentication:** Alice provided valid credentials; `SecurityContext` holds a trusted `Authentication`, for example `authentication.getName() == "alice"`.
- **Route/function authorization:** which types of endpoints a logged-in user or user with a suitable role may call; for example, `GET /api/documents/{id}` requires `authenticated()`.
- **Object-level authorization:** for the specific document `id=202`, is Alice allowed to **read** or **edit** it? Permissions may depend on owner, tenant, sharing grants, membership, ACLs, project role, resource state, etc.
- **Data access:** the repository/query returns only records within the allowed scope. This is an effective defense because both retrieval and result filtering respect the policy.

Decision table in an "owner-only read" application:

| Caller | URL | Result | Reason |
|---|---|---|---|
| Unauthenticated | `GET /api/documents/101` | `401` with Basic API demo | No valid identity |
| `alice` | `GET /api/documents/101` | `200` | Alice owns the document |
| `alice` | `GET /api/documents/202` | `404` in demo | No document **permitted to be seen** with that ID |
| `bob` | `GET /api/documents/202` | `200` | Bob owns the document |
| `bob` | `GET /api/documents/101` | `404` in demo | Bob cannot see Alice's document |
| `alice` | `GET /api/documents/999` | `404` | Document does not exist |

`403 Forbidden` can also be appropriate when policy allows users to know a resource exists but forbids the requested action. **`404 Not Found` is a deliberate choice** to avoid disclosing the existence of another user's resource; use it consistently for "does not exist" and "not within accessible scope". The status choice must align with the API contract and information-disclosure goals.

Both `101` and a UUID are merely **identifiers**, not capability tokens that automatically grant permission. Switching sequential IDs to UUIDs makes guessing harder, but **does not fix** the vulnerability if the backend still lets anyone who knows the ID read the content.

## 3. Ownership-Based Data Protection Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant A as Controller
    participant V as Service
    participant R as Repository/DB
    C->>S: GET /api/documents/202 + Alice's credentials
    S->>S: Authentication = Alice
    S->>A: Allow calling authenticated endpoint
    A->>V: getOwned(202)
    V->>S: Retrieve verified principal from SecurityContext
    S-->>V: alice
    V->>R: findByIdAndOwnerUsername(202, "alice")
    R-->>V: No results within Alice's scope
    V-->>A: 404
    A-->>C: 404 (does not return Bob's document)
~~~

There are **two layers of control** in this example:

1. Spring Security blocks unauthenticated requests via `SecurityFilterChain` configuration and `@PreAuthorize("isAuthenticated()")`.
2. The service/repository only reads records whose **requested ID and owner match the authenticated identity**. That is the object-level anti-BOLA check.

Data query expression:

~~~sql
-- Wrong: checks the ID, ignores the owner.
SELECT id, owner_username, title, content
FROM documents
WHERE id = :requestedId;

-- Correct in the "owner-only" model:
SELECT id, owner_username, title, content
FROM documents
WHERE id = :requestedId
  AND owner_username = :authenticatedUsername;
~~~

`:requestedId` is URL input and is **untrusted for authorization**. `:authenticatedUsername` must come from a verified `Authentication` or a trusted server source; never take it from `?owner=alice`, a self-asserted `X-User` header, or an `ownerId` field in client JSON.

A more complex policy can replace the owner condition with `owner OR shared_access OR authorized_project_membership`, but it **must still bind the specific action and resource**.

## 4. Runnable Example with Spring Boot, Spring Security, and H2

The following example creates a GET API to list and read individual documents. H2 is an **in-memory** database for standalone execution without an external DB server. There are two sample accounts, `alice` and `bob`, each with one record. `/api/documents/{id}` looks up by both `id` and owner.

**Environment:** JDK 17+, Maven 3.9+, Spring Boot **3.5.0** (Spring Security 6.x, Jakarta Servlet). Credentials in the demo are for local study only. The sample only exposes `GET` endpoints to keep **default CSRF protection** enabled; update/delete endpoints are covered separately in section 7.

Project structure:

~~~text
ownership-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/ownership/
│   ├── OwnershipDemoApplication.java
│   ├── SecurityConfig.java
│   ├── DocumentEntity.java
│   ├── DocumentRepository.java
│   ├── DocumentService.java
│   └── DocumentController.java
└── src/test/java/com/example/ownership/
    └── OwnershipAuthorizationTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

### 4.2. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:ownership;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

`create-drop` recreates sample data according to the application lifecycle; do not use it carelessly with databases containing real data. `open-in-view=false` forces the service to finish reading data inside the transaction rather than relying on a JPA session left open into the HTTP layer.

### 4.3. OwnershipDemoApplication.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OwnershipDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                new DocumentEntity(
                    101L, "alice", "Alice private", "Only Alice sees this"),
                new DocumentEntity(
                    202L, "bob", "Bob private", "Only Bob sees this")
            ));
        };
    }
}
~~~

Two records have fixed IDs for easy reproduction of test cases. `saveAll` runs only when the demo starts; the in-memory H2 database is rebuilt each time the app runs.

### 4.4. SecurityConfig.java

~~~java
package com.example.ownership;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(
                    "/api/documents", "/api/documents/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alice123")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}bob123")
                .roles("USER")
                .build()
        );
    }
}
~~~

Explanation:

- `authenticated()` only verifies that the request carries a logged-in identity. This condition **does not prove** the user owns the document.
- `@EnableMethodSecurity` enables `@PreAuthorize` on the service. Spring Boot Starter Security does not enable method security automatically.
- `SessionCreationPolicy.STATELESS` fits independent HTTP Basic requests in the demo.
- `DispatcherType.ERROR` and `FORWARD` are permitted so Spring MVC's 404 error handling is not blocked by `anyRequest().denyAll()` during internal dispatches. No additional public data APIs are exposed.
- `{noop}` stores plaintext passwords **in this demo only**. Production systems require a secure password encoder, proper secret management, and HTTPS.
- There is no `csrf().disable()`: all sample requests here are `GET`. For data-writing APIs, evaluate CSRF according to the authentication mechanism and client type before deciding on configuration.

### 4.5. DocumentEntity.java

~~~java
package com.example.ownership;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String content;

    protected DocumentEntity() {
        // JPA requires a no-argument constructor.
    }

    public DocumentEntity(
            Long id, String ownerUsername, String title, String content) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
        this.content = content;
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

    public String getContent() {
        return content;
    }
}
~~~

This is the database record. `ownerUsername` is assigned server-side when seeding demo data. In real systems, use an **immutable principal ID**, such as a user ID from the identity provider, because usernames/emails can change. For multi-tenant systems, add `tenantId` to the model and constrain queries by tenant.

### 4.6. DocumentRepository.java

~~~java
package com.example.ownership;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);

    List<DocumentEntity> findAllByOwnerUsernameOrderByIdAsc(
            String ownerUsername);
}
~~~

**This is the most important safeguard in the example.** The repository requires **both conditions**: the ID the client wants to read and the owner identity verified by the backend. `findAllByOwnerUsernameOrderByIdAsc` also protects the **list endpoint**, avoiding the pitfall where the detail API is safe but the list API returns everyone's data.

If the document exists but belongs to another user, `findByIdAndOwnerUsername` returns `Optional.empty()`, just like a nonexistent ID within that user's scope.

### 4.7. DocumentService.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public DocumentView getOwned(Long documentId) {
        String username = currentUsername();

        DocumentEntity document = repository
            .findByIdAndOwnerUsername(documentId, username)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        return toView(document);
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public List<DocumentView> listOwned() {
        String username = currentUsername();

        return repository
            .findAllByOwnerUsernameOrderByIdAsc(username)
            .stream()
            .map(DocumentService::toView)
            .toList();
    }

    private static String currentUsername() {
        return SecurityContextHolder.getContext()
            .getAuthentication()
            .getName();
    }

    private static DocumentView toView(DocumentEntity document) {
        return new DocumentView(
            document.getId(),
            document.getTitle(),
            document.getContent());
    }

    public record DocumentView(
            Long id,
            String title,
            String content) {
    }
}
~~~

Notes:

1. `@PreAuthorize("isAuthenticated()")` ensures only authenticated users can invoke **public service methods** through the Spring proxy. `Authentication` in `SecurityContextHolder` is populated by Spring Security after authentication; in this demo its username matches `ownerUsername`.
2. `currentUsername()` reads the identity at the **service layer**, avoiding accepting an arbitrary `ownerUsername` parameter passed by the controller or caller. Do not expose any parameter allowing the client to override the identity used for filtering.
3. The call `findByIdAndOwnerUsername(documentId, username)` is what enforces object-level authorization. `@PreAuthorize("isAuthenticated()")` **alone is not sufficient** to protect ownership.
4. `DocumentView` is the DTO returned over HTTP; do not serialize the entire entity directly. That prevents accidentally exposing internal or sensitive fields as the entity evolves.
5. `@Transactional(readOnly = true)` defines the transaction lifecycle for the JPA read operation. Entity-to-DTO mapping happens right inside the service.
6. Methods annotated with `@PreAuthorize` must be called through the **Spring bean proxy**. Self-invoking `this.getOwned(...)` from another method in the same class can bypass the method interceptor; in such cases ensure the policy is still enforced in service/repository logic.
7. In multi-tenant designs, `ownerUsername` alone does not guarantee tenant isolation if identities/IDs are not globally unique; add a `tenantId` key obtained from a trusted context to the query.

### 4.8. DocumentController.java

~~~java
package com.example.ownership;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping
    public List<DocumentService.DocumentView> list() {
        return service.listOwned();
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView get(@PathVariable Long id) {
        return service.getOwned(id);
    }
}
~~~

The controller only accepts `id` and delegates to the service. The controller **never decides ownership itself**, never takes `owner` from a query string, and never returns an entity fetched directly via `findById(id)`.

### 4.9. Automated Testing: OwnershipAuthorizationTest.java

~~~java
package com.example.ownership;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void aliceCanReadHerDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.title").value("Alice private"));
    }

    @Test
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void bobCannotReadAlicesDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void nonExistingIdIsNotFound() throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOnlyListsHerDocuments() throws Exception {
        mvc.perform(get("/api/documents")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(101));
    }

    @Test
    void bobOnlyListsHisDocuments() throws Exception {
        mvc.perform(get("/api/documents")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(202));
    }
}
~~~

Tests cover **authorized caller**, **different owner**, **anonymous**, **nonexistent ID**, and **list API** together; never test only "Alice can view Alice's record".

### 4.10. Running and Observing the App

In the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` needs to download Maven dependencies the first time (if not cached). With `mvn spring-boot:run`, the server listens on `http://localhost:8080` by default if the port is free and no other config overrides it.

In another terminal, try:

~~~bash
# Alice reads her own document
curl -i -u alice:alice123 http://localhost:8080/api/documents/101

# Alice tries changing the ID to Bob's document
curl -i -u alice:alice123 http://localhost:8080/api/documents/202

# Bob reads his own document
curl -i -u bob:bob123 http://localhost:8080/api/documents/202

# Unauthenticated
curl -i http://localhost:8080/api/documents/101

# Alice lists documents (must contain only ID 101)
curl -i -u alice:alice123 http://localhost:8080/api/documents

# Bob lists documents (must contain only ID 202)
curl -i -u bob:bob123 http://localhost:8080/api/documents
~~~

On PowerShell, if `curl` is an alias for `Invoke-WebRequest`, use `curl.exe` with the same arguments.

Expected results to verify:

| Request | Expected HTTP status | Allowed response data |
|---|---|---|
| Alice → `/api/documents/101` | `200` | `id=101`, title `Alice private`, content `Only Alice sees this` |
| Alice → `/api/documents/202` | `404` | **Must not return Bob's content** |
| Bob → `/api/documents/202` | `200` | `id=202`, title `Bob private`, content `Only Bob sees this` |
| Anonymous → `/api/documents/101` | `401` | No document; Basic challenge |
| Alice → `/api/documents` | `200` | List contains only document `101` |
| Bob → `/api/documents` | `200` | List contains only document `202` |
| Alice → `/api/documents/999` | `404` | Indistinguishable from another user's ID |

The JSON returned when Alice successfully reads her document is:

~~~json
{
  "id": 101,
  "title": "Alice private",
  "content": "Only Alice sees this"
}
~~~

JSON field ordering, default HTTP headers, and error JSON generated by Spring Boot/the Servlet container may vary; **do not assert tests against default error body strings**. In this example, QA focuses on status codes and ensuring no data from other owners leaks.

## 5. Why Filter Directly at the Query and Service Layers?

A simple "patch" is calling `findById(id)` and then checking:

~~~java
DocumentEntity document = repository.findById(documentId)
    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

if (!document.getOwnerUsername().equals(authenticatedUsername)) {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND);
}
return toView(document);
~~~

This snippet **can prevent unauthorized reads when applied thoroughly on every call path**, but it carries risks of forgetting checks, duplicating logic, exposing data before the check, being awkward for list APIs, and separating check-then-write into two distinct steps.

In the owner-only model, push the authorization condition into the query:

~~~java
repository.findByIdAndOwnerUsername(documentId, authenticatedUsername)
~~~

Then the query searches only **within the user's allowed scope**. For list APIs, use `findAllByOwnerUsername...` directly at the database level instead of fetching everything and filtering with `stream().filter(...)` in memory. Post-query filtering increases the risk of leaking data through logs, caches, pagination, total counts, exports, or joined queries.

**There is not always just a single `owner_username` column.** Real-world projects may have group owners, project members, shared recipients, action-based permissions, and tenants. Policies should be expressed explicitly (query predicates, policy services, ACL/permission evaluators, database row-level security, or a combination) and applied to every query/write path.

Spring Security protects endpoints and services using constructs such as `authorizeHttpRequests`, `@PreAuthorize`, and `@PostAuthorize`. However, the framework cannot guess the domain relationship "Alice may read document 101 but not document 202"; your domain must supply the condition or policy check.

### @PreAuthorize for Object-Level Permissions

If you want to express policy via method security, an **illustrative** option is:

~~~java
@PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
public DocumentView loadDocument(Long documentId) {
    // Only runs when the policy bean allows it.
}
~~~

This snippet is **not standalone**: it requires `@EnableMethodSecurity`, a bean named `documentPolicy` with a `canRead(...)` method, a Spring-managed service bean, and actual data-access logic. `@PreAuthorize("hasRole('USER')")` only checks a general role; it does not verify ownership. If using `@PostAuthorize("returnObject.ownerId == authentication.name")`, the object has already been loaded before the permission decision, so weigh the risks of sensitive data in memory/side effects and how 403 responses are handled. In the runnable example, owner-scoped queries naturally yield 404.

## 6. Authorization Must Apply to *Actions*, Not Just GET

Anti-BOLA protection covers every path that takes an ID:

- **Read:** `GET /api/documents/{id}`, attachment downloads, file previews, status retrieval.
- **Modify:** `PATCH/PUT /api/documents/{id}`, changing title/content/visibility.
- **Delete:** `DELETE /api/documents/{id}`.
- **Add relationships:** sharing a document, moving a document to a project, attaching files, changing owner.
- **Bulk operations:** bulk delete/export/update with a list of IDs; validate every ID or apply the permission filter inside the bulk statement.
- **Listing/searching:** paging, search, filter, count, export, reporting; always scope data at the source.

Example for a **database-level** write (illustrative extension, not part of the runnable GET API in section 4):

~~~java
// Add to DocumentRepository; requires @Modifying, @Query, @Param imports.
@Modifying
@Query("update DocumentEntity d set d.title = :title " +
       "where d.id = :id and d.ownerUsername = :owner")
int renameIfOwned(
    @Param("id") Long id,
    @Param("owner") String owner,
    @Param("title") String title);

// Add to DocumentService; requires @Transactional and a trusted principal.
@PreAuthorize("isAuthenticated()")
@Transactional
public void renameOwned(Long id, String title) {
    String username = currentUsername();
    int modified = repository.renameIfOwned(id, username, title);
    if (modified == 0) {
        throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found");
    }
}
~~~

The snippets above are **extension fragments** for the two classes introduced earlier; when integrating them, add the corresponding imports, place the methods in the right classes, add input validation, and expose an appropriate endpoint. `UPDATE ... WHERE id = ? AND owner = ?` checks ownership **and performs the mutation in a single statement**. If instead you use separate "read by ID → check owner → update by ID" steps, watch out for concurrent ownership/permission changes (TOCTOU: *time of check to time of use*). With optimistic locking/versioning, the expected version check can also be included in the update predicate.

For `DELETE`, apply the same pattern:

~~~sql
DELETE FROM documents
WHERE id = :requestedId
  AND owner_username = :authenticatedUsername;
~~~

Check the affected row count to decide on `404` or the corresponding result. Never call `deleteById(requestedId)` solely because the route is `authenticated()`.

**For data-modifying APIs, CSRF is a separate topic that must be handled properly:** the runnable sample uses HTTP Basic and keeps default CSRF protection enabled because browsers can automatically attach Basic credentials. If you add `PATCH/DELETE`, support CSRF tokens for cookie/browser clients, or establish a stateless model and credential transport that browsers do not automatically attach before reconsidering CSRF settings. Never "fix a 403 error" by blindly disabling CSRF.

## 7. Distinguishing 401, 403, and 404 in Object Protection

| Status | Practical meaning | When to apply |
|---|---|---|
| `401 Unauthorized` | Client lacks valid credentials for the scheme | Anonymous or invalid HTTP Basic/token; usually needs an appropriate challenge |
| `403 Forbidden` | Caller is identified but not allowed to perform the action | E.g., user knows the document exists or has read access via sharing, but cannot edit it |
| `404 Not Found` | Resource is not within the **accessible scope** | E.g., another user's document or nonexistent ID, when avoiding existence disclosure |

Do not apply one rigid status code formula to every mechanism. For private-document read APIs, returning the same 404 for nonexistent IDs and other users' IDs is a clear choice. By contrast, a collaborative API may intentionally tell the user "you can see this document but cannot edit it" and return 403 on PATCH.

Also watch out for **side channels**: even when both cases return 404, response bodies, headers, processing times, cache keys, or client-visible logs can inadvertently differ and leak resource existence. Never include owner names, document titles, or internal explanations in error responses to unauthorized callers.

A correctly filtered endpoint that returns `200` with a `null` body for someone else's ID is not necessarily a security bypass, but it can make the API contract ambiguous. Define response behavior clearly, write tests for it, and keep it consistent.

## 8. Ownership Cases More Complex Than a Single Username

### 8.1. Multiple Tenants or Organizations

In SaaS applications, a document may have both `tenant_id` and `owner_user_id`. Both must be constrained:

~~~sql
SELECT id, title, content
FROM documents
WHERE id = :documentId
  AND tenant_id = :currentTenantId
  AND owner_user_id = :currentUserId;
~~~

`currentTenantId` and `currentUserId` must be derived from a verified server context; never trust a self-asserted `X-Tenant-ID` header without a mechanism to map and validate tenant access. When a user switches tenants, the backend must determine the active tenant and corresponding membership/permissions. Always test **cross-tenant access**, even when document IDs are hard-to-guess UUIDs.

### 8.2. Owners, Shared Recipients, and Action-Specific Permissions

Sometimes a shared user has `READ` permission but not `WRITE`. An illustrative policy:

~~~text
canRead(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasShareGrant(user, doc, READ))

canEdit(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasShareGrant(user, doc, WRITE))

canDelete(user, doc) =
    sameTenant(user, doc)
    AND (isOwner(user, doc) OR hasProjectAdminPermission(user, doc))
~~~

`hasRole("ADMIN")` does not automatically mean permission to read documents across **all tenants**. If support staff need "break glass" access, enforce a dedicated policy, audit logging, and strict scoping. Never interpret `ROLE_USER` as "can read all documents".

### 8.3. Parent-Child Relationships / Nested IDs

For `/api/projects/{projectId}/documents/{documentId}`, do not check permission on `projectId` alone and then load an arbitrary `documentId`. The record must actually belong to that project **and** the caller must have permission on the project/document.

~~~sql
SELECT d.*
FROM documents d
JOIN project_members m ON m.project_id = d.project_id
WHERE d.id = :documentId
  AND d.project_id = :projectId
  AND m.user_id = :authenticatedUserId
  AND m.can_read = TRUE;
~~~

This SQL illustrates the concept and must be adapted to actual column names, joins, and policies. Some permissions require both project membership and document-level ACLs; express the full policy rather than assuming the illustrative query fits every system.

### 8.4. File Downloads and External Paths

If a controller verifies permissions and then generates a **signed URL** to download a file, that URL must restrict the target object, expiration time, and allowed action. Avoid returning permanent public storage keys/URLs or letting `/download/{fileId}` bypass the parent document's policy. For background jobs, message queues, GraphQL resolvers, WebSockets, scheduled exports, and batch processors, propagate a trusted principal/tenant context or service identity with a defined policy; never assume HTTP requests are the only entry point.

## 9. Anti-Patterns and Fixes

### 9.1. Checking Authentication Only

~~~java
// Insufficient: any user can fetch any ID.
.requestMatchers("/api/documents/**").authenticated()
~~~

This is only the **entry gate**; add resource checks in the service/repository.

### 9.2. Trusting Client-Supplied ownerId

~~~json
{
  "title": "My secret",
  "ownerUsername": "bob"
}
~~~

If the server trusts `ownerUsername` when creating or updating a record, a user can impersonate another owner or transfer ownership without authorization. Use DTOs that only accept permitted fields and assign the owner server-side from the principal; if the product supports ownership transfer, expose a dedicated endpoint with stricter policy.

### 9.3. Fetching Everything and Filtering in Java

~~~java
// Wrong for list APIs: out-of-scope data has already been loaded into memory.
return repository.findAll().stream()
    .filter(doc -> doc.getOwnerUsername().equals(username))
    .toList();
~~~

Beyond data-leak risks, post-DB filtering breaks **paging, count, and sorting**. Query with authorization predicates from the start; pagination and counts must operate on the same scope.

### 9.4. Checking Ownership Once and Reusing Data Elsewhere

For example, GET uses `findByIdAndOwnerUsername` while DELETE calls `deleteById`, or export calls `findAll`. Policies must be enforced on **every operation**. To avoid omissions, prefer repository/service method names that reflect scoping such as `findOwned`, `updateOwned`, and `deleteOwned`, test with a multi-user matrix, and review sensitive `findById` or bulk calls.

### 9.5. Relying on UUIDs or Hidden Edit Buttons as Primary Controls

Hiding buttons in the frontend only improves UX. An attacker can still send HTTP requests directly; UUIDs do not block access once leaked. The **backend** must enforce authorization.

### 9.6. Caching by Document ID Alone

If `GET /api/documents/101` is cached solely by ID without user/tenant/policy context, a response cached for an authorized user can be served to an unauthorized user. Verify permissions before serving cached entries, use appropriate cache keys/scopes, and design invalidation when ownership or ACLs change. CDNs and reverse proxies must also not share private responses across principals; consider `Cache-Control: private, no-store` according to product requirements.

### 9.7. Method Security Not Enabled or Self-Invoked Within the Same Bean

`@PreAuthorize` requires `@EnableMethodSecurity` and typically operates through a Spring AOP proxy. If you forget to enable it, the annotation does not protect anything; self-calling `this.someSecuredMethod()` can bypass the interceptor. Place core policies in services/repositories invoked properly through proxies, combined with request- and service-level tests.

### 9.8. Checking Only One ID in a Batch

For a request containing `[101, 202]`, never infer that the entire list is valid just because the user owns `101`. Only return or modify records allowed by the documented policy; if the contract requires **all** IDs to be valid, validate all of them and reject the entire request when any ID is unauthorized. Pay attention to transactions to avoid unintended partial commits.

## 10. Anti-BOLA/IDOR Testing Matrix

When testing ownership, include at least **two distinct accounts**, each owning a resource, plus an anonymous request. Include these test cases:

| Test case | Expected outcome to guarantee |
|---|---|
| Alice reads Alice's ID | Succeeds; data is accurate and within permissions |
| Alice changes ID to Bob's document | Rejected; does not reveal Bob's data |
| Bob tries Alice's ID | Rejected under the same policy |
| Alice tries a nonexistent ID | Result does not disclose existence of forbidden IDs |
| Anonymous tries a valid ID | Receives no data |
| Alice calls list/search/pagination | Receives only resources within allowed scope |
| Alice tries PATCH/DELETE on Bob's document | Data unchanged; DB state remains intact |
| Alice tries a batch containing both Alice's and Bob's IDs | Cannot read or modify Bob's portion |
| User alters owner/tenant/role in body/header | Server ignores self-asserted values for privilege escalation |
| User in tenant A tries tenant B's ID | Cannot cross tenant boundary |
| User with READ permission tries WRITE/DELETE | Not granted write access merely because read is allowed |

With MockMvc you can use `httpBasic` as shown in the example or `@WithMockUser`/JWT test support depending on your auth mechanism. For real systems, include **integration tests against the repository/database** to prove the query enforces data scoping rather than only mocking a policy to return `true/false`. Write tests must re-check the database after the HTTP response, because returning `403` after a side effect has already occurred is still a serious flaw.

The JUnit example in section 4 proves that Alice and Bob are both validly authenticated yet cannot view each other's documents, and the list endpoint does not expose other records. That is a property that tests checking only `401` for anonymous requests cannot detect.

## 11. Pre-Production Design Checklist

1. **Resources:** Which endpoints accept IDs? Are there nested ID fields in payloads, child relationships, attachments, exports, or batch operations?
2. **Subjects:** Obtain user ID, tenant ID, roles, and grants from a verified `Authentication`/session/token, never from client-asserted values.
3. **Policies:** Who can READ, CREATE, UPDATE, DELETE, and SHARE? Can ownership change, and are there delegates, groups, or proxy permissions?
4. **Enforcement:** Check in the service layer and constrain queries/mutations by principal, tenant, and action; do not protect only the controller.
5. **Responses:** Define when to return `401`, `403`, and `404`; do not leak data or existence outside the allowed scope.
6. **Concurrency and caching:** Handle check-then-act, transactions, versioning, invalidation, and per-user/per-tenant caches.
7. **Testing:** Use at least two principals and multiple records; cover list, read, mutation, bulk, file access, nested-resource IDs, and multi-tenant cases.
8. **Operations:** Audit denied accesses at an appropriate level, alert on ID enumeration attempts, minimize sensitive data in logs, and apply rate limiting; logging does not replace authorization.
9. **Data protection:** Use DTOs to avoid exposing internal fields, classify data, enforce HTTPS, prevent leaks via search/indexes/logs/debug endpoints, and apply least privilege to service accounts.

**Remember:** object-level authorization is a business rule enforced on the backend for **every object and every action**. Authentication tells you "who is calling"; ownership/ACL/tenant policy tells you "what that caller is allowed to do with this record".

## 12. Self-Check Questions

1. Alice has `ROLE_USER` and is logged in. Why is `.hasRole("USER")` not enough to protect `/api/documents/202`?
2. Why can an unguessable UUID still not replace `WHERE owner_username = :principal`?
3. If `findByIdAndOwnerUsername(202, "alice")` returns empty, why does the demo return 404? When is 403 more appropriate?
4. Why must list APIs filter by owner directly in the database rather than protecting only the detail API?
5. For `PATCH /api/documents/202`, how do you ensure **checking ownership and updating** are not separated when permissions can change concurrently?
6. If a document is shared with Bob for read access but not edit access, how should the policy differ between those two actions?
7. Why cannot a `tenantId` parameter from a header or JSON become a trusted scope on its own?
8. If a Spring MVC controller checks ownership but a background job queries the repository directly by ID, which path risks a bypass?
9. In the demo, what does `@PreAuthorize("isAuthenticated()")` protect, and what does `findByIdAndOwnerUsername` protect?
10. What test would you write to prove DELETE returns an error **and does not remove** Bob's document?

## References

- [OWASP API Security Top 10 2023 — API1 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html)
- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
