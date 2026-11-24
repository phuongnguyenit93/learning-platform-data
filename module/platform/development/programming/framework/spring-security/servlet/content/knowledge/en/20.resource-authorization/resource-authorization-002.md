# Matching the Current User Against Record Ownership in Spring Security Servlet

> **Module:** Spring Security - servlet. **Category:** Resource Authorization. **Target:** Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC, Spring Data JPA, H2, and MockMvc. The focus is verifying that an authenticated user is genuinely allowed to read, modify, or delete **a specific record**, rather than only checking login or a general role.

## 1. The Problem: Logging In Is Not Enough to View Someone Else's Data

Alice and Bob are both valid users:

```text
Alice: userId=101
Bob:   userId=202

Documents:
  document 1 -> ownerUserId=101 (Alice)
  document 2 -> ownerUserId=202 (Bob)
```

With Spring Security, it is easy to write an HTTP rule:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").authenticated()
    .anyRequest().denyAll()
)
```

That condition only confirms the request belongs to a logged-in user. If the controller fetches the document directly by ID:

```java
@GetMapping("/api/documents/{id}")
Document get(@PathVariable Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

then Bob only needs to replace `/api/documents/2` with `/api/documents/1` to receive Alice's data. This is **Broken Object Level Authorization (BOLA)**, commonly known as **Insecure Direct Object Reference (IDOR)**.

**Rule:** The ID in the URL only identifies the resource; **it does not prove ownership**. Every request must be checked against the server-verified identity and permissions on the **exact record**.

```text
GET /api/documents/1
       |
       v
Spring Security authenticates actor (Bob)
       |
       v
Application resolves trusted actorId=202
       |
       v
Query document by both id=1 and ownerUserId=202
       |
       +--> No permitted result:
       |      do not return Alice's data
       |
       +--> Permitted result found:
              return only the required DTO
```

Never replace this check with a hard-to-guess UUID, a hidden Edit button on the frontend, or a generic authority like `ROLE_USER`.

## 2. Authentication, URL Authorization, and Ownership Are Three Different Questions

| Layer | Question | Relevant Components |
| --- | --- | --- |
| Authentication | Who is the request from? | `Authentication`, `SecurityContext`, authentication filter |
| HTTP authorization | Which URL categories can the actor enter? | `SecurityFilterChain`, `authorizeHttpRequests` |
| Role/authority | Does the actor have this kind of operational permission? | `hasRole`, `hasAuthority`, `GrantedAuthority` |
| Object authorization | Does the actor have permission on **this record ID**? | Service policy, repository query, `@PreAuthorize` |
| Tenant authorization | Does the record belong to a tenant the actor is allowed in? | Tenant membership + data predicate |
| Business rule | Is modification allowed in the current state? | Domain service, transaction |

A principal with `ROLE_EDITOR` does not mean they can edit every document in the system. A user having `DOCUMENT_READ` also does not prove they can read another tenant's documents.

### Minimal Permission Matrix

| Request | Actor | Owner | Outcome |
| --- | --- | --- | --- |
| GET document A | Alice | Alice | Allow |
| GET document B | Alice | Bob | Deny, do not leak content |
| PATCH document A | Alice | Alice | Allow if record is editable |
| PATCH document B | Alice | Bob | Deny |
| GET document A | Anonymous | Alice | Require login |
| GET non-existent ID | Alice | None | 404 |
| GET document list | Alice | Multiple owners | List only permitted documents |

Whether to return HTTP 403 or 404 when a document exists but is unauthorized is an API policy choice. The non-negotiable rule is that the response must not return private payloads to an unauthorized actor.

## 3. Obtaining the Current User from a Trusted Source

Spring Security Servlet provides an `Authentication` built from the configured authentication flow. In an MVC controller, you can inject:

```java
@GetMapping("/me")
String me(Authentication authentication) {
    return authentication.getName();
}
```

Or a principal matching the authentication mechanism:

```java
@GetMapping("/me")
String me(@AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

These snippets are fragments; import `Authentication`, `AuthenticationPrincipal`, and `UserDetails` when using them. `@AuthenticationPrincipal UserDetails` only works if the principal is actually a `UserDetails`; JWT/OIDC/SSO may supply a different principal type.

In service/background code you can also obtain `Authentication` from `SecurityContextHolder`:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

However, you must handle missing users in the context, anonymous tokens, async/background threads that do not automatically inherit context, and service-to-service identities. For HTTP endpoints already protected by `authenticated()`, injecting the `Authentication` parameter is safer than reading it repeatedly inside business services.

### Do Not Use Client-Declared Actor IDs

This is a security flaw:

```java
// WRONG: letting the request choose the owner used for checking.
Document document = repository.findByIdAndOwnerId(
    id, request.getParameter("ownerId"));
```

The client can modify `ownerId` and impersonate Alice. An `X-User-Id` value in an HTTP header is also not automatically trustworthy unless a gateway authenticates/forwards it with a signature and the backend verifies the trust boundary. Data used as the actor must come from **verified authentication**, then map to an internal ID.

### Username Is Not an Ideal Long-Term Ownership Key

The runnable example later uses `Authentication.getName()` (Alice/Bob) as the owner key for simplicity. **Production should use a stable internal user ID** such as a UUID or database key. Usernames/emails can change, be reassigned, or collide across multiple IdPs.

With OIDC, map **issuer + subject** to an internal user ID, while validating signature, issuer, audience, expiration, and tenant membership. Identical `sub` values from two different issuers do not automatically represent the same user.

## 4. Owner, Creator, Assignee, and Shared Users Can Differ

A business table may include:

```text
document.ownerUserId       // current owner
document.createdByUserId   // original creator
document.assigneeUserId    // assigned user
document.tenantId          // organization/data zone
document.sharedWith        // shared permissions
```

If ownership transfers from Alice to Bob, Alice is no longer the owner just because `createdByUserId` is still Alice. Similarly, an assignee permitted to work on a task does not automatically become the owner of all attached files.

Define clearly:

- Can the owner read, edit, delete, share, export, or transfer ownership?
- Can shared users view, comment, or modify content?
- Can an admin view within their tenant or across tenants?
- Can the owner still edit a locked/approved record?
- When an account loses permissions, how are active sessions and tokens handled?

A helper named `isOwner` should strictly check the owner, without silently accepting `createdBy` unless the business rules require it.

## 5. Implementation Patterns and Risks

| Pattern | Pros | Cons to Control |
| --- | --- | --- |
| Controller loads then compares owner | Easy to see in small endpoints | Easy to forget in other endpoints |
| Service policy | Centralized logic, reusable between REST and jobs | Must control check-then-write races |
| `@PreAuthorize` with policy bean | Declarative rules on service methods | AOP proxy, duplicate queries, parameter naming |
| Repository query with owner predicate | Blocks out-of-scope data right at the DB | Must be used consistently across all read/list/write paths |
| DB Row-Level Security | Defense layer at the database | Requires proper per-request DB identity/tenant context management |

No single annotation automatically secures every resource endpoint. For simple ownership, **queries with an owner predicate** are very easy to test; method security can supplement this when policies have multiple conditions.

## 6. Unsafe Pattern: `findById` After Checking Login Only

```java
@GetMapping("/documents/{id}")
Document get(@PathVariable Long id) {
    return repository.findById(id)
        .orElseThrow();
}
```

If SecurityFilterChain only requires `authenticated()`, any logged-in user can probe IDs one by one. Changing IDs from sequential numbers to UUIDs only makes guessing harder; it does not create authorization.

A manual check can be written as:

```java
Document d = repository.findById(id).orElseThrow();
if (!d.getOwnerUserId().equals(currentUserId)) {
    throw new AccessDeniedException("Forbidden");
}
return toDto(d);
```

This is an illustrative fragment depending on document/actor types and imports. It is better than no check at all, but it still **loads the entity first** before authorizing, risking missed checks in other branches. A query already scoped by owner is usually simpler.

## 7. Putting the Owner Predicate into the Read Query

A Spring Data JPA repository can provide:

```java
Optional<OwnedDocument> findByIdAndOwnerUsername(
    Long id, String ownerUsername);
```

This restricts documents by both ID and trusted actor. In SQL terms:

```sql
SELECT id, owner_username, title
FROM owned_documents
WHERE id = :id
  AND owner_username = :trustedActorUsername;
```

The actual SQL generated by the JPA provider may differ slightly. However, the semantics are that **if no record matches both conditions, no data is returned**.

Similarly, listing a user's documents uses:

```java
List<OwnedDocument> findByOwnerUsernameOrderByIdAsc(
    String ownerUsername);
```

Never call `findAll()` and let the frontend filter or hide rows. If the server already sent Bob's record to Alice's browser, the data has leaked even if the UI does not display it.

In large systems, use `Pageable` and proper indexes, avoiding loading all records into memory and filtering. In multi-tenant setups, add `tenantId` from a trusted tenant context.

## 8. Conditional Mutations to Avoid Checking Permissions Too Early

A check performed prior to the operation can become stale:

```text
t0: Alice checks that document 101 has owner Alice.
t1: Another transaction transfers document 101 to Bob.
t2: Alice still updates document 101 by ID without re-checking the owner.
```

If business rules require the actor to be the owner **at write time**, put the permission predicate directly into the mutation statement:

```java
@Modifying
@Query("""
    update OwnedDocument d
       set d.title = :title
     where d.id = :id
       and d.ownerUsername = :owner
    """)
int renameIfOwner(Long id, String owner, String title);
```

The update succeeds only when the record still satisfies `id AND owner` in the database. Check affected rows: if 0, return 404/403 per policy. Never fall back to `findById` and update with elevated privileges to "rescue" the request.

**JPA limitation:** `@Modifying` bulk JPQL updates can bypass entity callbacks, dirty checking, and automatic optimistic lock/version handling. If the app uses `@Version`, design an explicit version predicate/increment or an appropriate optimistic-lock flow. This is a strategy to reduce TOCTOU, not an absolute guarantee across all transactions and distributed workflows.

## 9. Runnable Example: Spring Boot 3, Java 17, JPA, and H2

The example has two accounts `alice` / `bob`, each owning one document. HTTP requires login, while the service/repository restricts each document by authenticated username. The example uses username for simplicity; production systems should use an internal immutable user ID.

### 9.1. Gradle Dependencies

Create a Spring Boot 3.x Java 17 Gradle project with the Spring Boot plugin and dependency management, then add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 9.2. Database Configuration

File `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:ownershipdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
```

H2 and `create-drop` are strictly for demo/testing. Never use `create-drop` to manage production schemas; use migrations and secure DB credentials.

### 9.3. Complete Application Source

Create `src/main/java/example/ownership/OwnershipApplication.java`:

```java
package example.ownership;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(OwnedDocumentRepository repository) {
        return args -> repository.saveAll(List.of(
            new OwnedDocument("alice", "Alice private note"),
            new OwnedDocument("bob", "Bob private note")
        ));
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filter(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/api/documents", "/api/documents/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            // Browser session: CSRF protection remains enabled.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}

@Entity
@Table(name = "owned_documents")
class OwnedDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected OwnedDocument() { }

    OwnedDocument(String ownerUsername, String title) {
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }
}

interface OwnedDocumentRepository
        extends JpaRepository<OwnedDocument, Long> {

    List<OwnedDocument> findByOwnerUsernameOrderByIdAsc(
        String ownerUsername);

    Optional<OwnedDocument> findByIdAndOwnerUsername(
        Long id, String ownerUsername);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update OwnedDocument d
           set d.title = :title
         where d.id = :id
           and d.ownerUsername = :ownerUsername
        """)
    int renameIfOwner(
        @Param("id") Long id,
        @Param("ownerUsername") String ownerUsername,
        @Param("title") String title);
}

record DocumentView(Long id, String title) {
    static DocumentView from(OwnedDocument d) {
        return new DocumentView(d.getId(), d.getTitle());
    }
}

record RenameDocumentRequest(String title) { }

@Service
class DocumentService {

    private final OwnedDocumentRepository repository;

    DocumentService(OwnedDocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<DocumentView> listMine(String actorUsername) {
        return repository.findByOwnerUsernameOrderByIdAsc(
                actorUsername)
            .stream()
            .map(DocumentView::from)
            .toList();
    }

    @Transactional(readOnly = true)
    public DocumentView readMine(
            Long id, String actorUsername) {
        return repository.findByIdAndOwnerUsername(
                id, actorUsername)
            .map(DocumentView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @Transactional
    public void renameMine(
            Long id, String actorUsername, String title) {
        int changed = repository.renameIfOwner(
            id, actorUsername, title);
        if (changed != 1) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping
    List<DocumentView> list(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/{id}")
    DocumentView read(
            @PathVariable Long id,
            Authentication authentication) {
        return service.readMine(id, authentication.getName());
    }

    @PatchMapping("/{id}")
    ResponseEntity<Void> rename(
            @PathVariable Long id,
            @RequestBody RenameDocumentRequest request,
            Authentication authentication) {

        String title = request.title();
        if (title == null || title.isBlank() ||
                title.length() > 120) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        service.renameMine(
            id, authentication.getName(), title.trim());
        return ResponseEntity.noContent().build();
    }
}
```

With Java 17, having one public top-level class `OwnershipApplication` matching the filename and package-private top-level classes in the same file is valid. Spring Boot scans the `example.ownership` package and picks up the configuration, service, JPA entity/repository, and controller.

### 9.4. Permission Mechanism on Each Path

- `GET /api/documents` queries by `ownerUsername=authentication.getName()`, without using `findAll()`.
- `GET /api/documents/{id}` queries by **both** ID and owner; if there is no match, it returns 404 without confirming that a record exists belonging to Bob.
- `PATCH /api/documents/{id}` accepts a DTO containing only `title`, without binding a full JPA entity from the request body. The client cannot choose the actor.
- `renameIfOwner` runs inside a transaction and includes the owner condition directly on the DB update; 0 affected rows means no authorized record was updated.
- `DocumentView` contains only ID and title, limiting serialization of internal fields.
- Both accounts use a password encoder and are local demo credentials only.
- `formLogin(form -> form.permitAll())` enables the login page/default login processing; protected APIs still require authentication.
- CSRF stays enabled because browser sessions are used. A valid PATCH must include a CSRF token. Never disable CSRF just to make a test turn "green".

**Do not use this code as-is as a production template.** Production requires stable owner IDs, tenant scoping, migrations, rate controls, auditing, data retention, and optional optimistic locking. JPQL bulk updates do not automatically trigger entity callbacks or version checks.

### 9.5. Running the Demo

In a Gradle project with the wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell use `./gradlew.bat bootRun`.

Open `http://localhost:8080/api/documents`, log in as `alice` / `alice-pass`. The **expected** JSON response, with IDs for illustration only:

```json
[
  {
    "id": 1,
    "title": "Alice private note"
  }
]
```

Actual IDs may differ due to `GenerationType.IDENTITY` and data insertion order; never hardcode ID `1` in tests. Alice must not see `Bob private note`; Bob signing in from another browser profile sees only Bob's documents.

If Alice manually replaces the URL ID with Bob's document ID, the query finds no matching record owned by Alice and returns 404. **These results are described based on the code, not actual execution output captured while writing.**

## 10. MockMvc: Negative Tests for Record-Level Authorization Are Mandatory

Testing only "Alice reads Alice successfully" does not catch BOLA. You must test "Bob fails to read/edit Alice" and verify Alice's content remains unchanged.

Create `src/test/java/example/ownership/OwnershipSecurityTest.java`:

```java
package example.ownership;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OwnedDocumentRepository repository;

    @BeforeEach
    void resetDocuments() {
        repository.deleteAll();
        repository.saveAll(List.of(
            new OwnedDocument("alice", "Alice private note"),
            new OwnedDocument("bob", "Bob private note")
        ));
    }

    private Long aliceDocumentId() {
        return repository.findByOwnerUsernameOrderByIdAsc("alice")
            .get(0).getId();
    }

    private Long bobDocumentId() {
        return repository.findByOwnerUsernameOrderByIdAsc("bob")
            .get(0).getId();
    }

    @Test
    void aliceOnlyListsHerDocument() throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("Alice private note"));
    }

    @Test
    void aliceReadsHerOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId())
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void aliceCannotReadBobsDocumentByChangingId()
            throws Exception {
        mvc.perform(get("/api/documents/{id}", bobDocumentId())
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void bobCannotReadAlicesDocumentByChangingId()
            throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId())
                .with(user("bob").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unknownIdDoesNotReturnPrivateData() throws Exception {
        mvc.perform(get("/api/documents/{id}", -1L)
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void aliceCanRenameOnlyHerOwnDocument() throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Alice updated note\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice updated note"));
    }

    @Test
    void bobCannotRenameAlicesDocument() throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("bob").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Hijacked\"}"))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void missingCsrfCannotMutateOwnedDocument()
            throws Exception {
        Long id = aliceDocumentId();

        mvc.perform(patch("/api/documents/{id}", id)
                .with(user("alice").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No Csrf\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/{id}", id)
                .with(user("alice").roles("USER")))
            .andExpect(jsonPath("$.title")
                .value("Alice private note"));
    }

    @Test
    void blankTitleIsRejected() throws Exception {
        mvc.perform(patch("/api/documents/{id}", aliceDocumentId())
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void anonymousCannotListPrivateData() throws Exception {
        mvc.perform(get("/api/documents"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void bobOnlyListsHisDocument() throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("bob").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("Bob private note"));
    }
}
```

Run:

```bash
./gradlew test
```

**Verification level:** the tests and results above are **expected**, not compiled/executed when authoring the lesson. `SecurityMockMvcRequestPostProcessors.user` builds an authenticated principal for authorization testing; it does not perform login/password verification through `UserDetailsService`. Integration tests with real authentication, proxies, and a real database are required before production.

### Analyzing the Test Suite

- The most important test is `bobCannotRenameAlicesDocument`: Bob has an authenticated principal and a valid CSRF token, yet is still denied because he is not the owner.
- Cross-ID read tests in both directions help catch a query that omits the owner check.
- List tests prove the list endpoint does not mix in another user's data.
- The missing-CSRF test checks a mechanism independent of ownership; a CSRF 403 does not mean the owner check ran.
- The DB fixture resets before each test, and IDs are fetched from the repository so they do not depend on the IDENTITY counter.
- The tests do not assume ownership from role names: both Alice and Bob have `ROLE_USER`, yet their permissions on specific documents differ.

## 11. Method Security with `@PreAuthorize` and a Policy Bean

Spring Security can protect service methods using a policy bean, which is helpful when multiple entry points invoke the same business logic.

Example method security configuration (supplementary fragment, does not automatically replace the main application):

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Illustrative policy component:

```java
@Component("documentPolicy")
class DocumentPolicy {

    private final OwnedDocumentRepository repository;

    DocumentPolicy(OwnedDocumentRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Long documentId,
                           Authentication authentication) {
        if (authentication == null ||
            !authentication.isAuthenticated() ||
            authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return repository.existsByIdAndOwnerUsername(
            documentId, authentication.getName());
    }
}
```

The repository needs:

```java
boolean existsByIdAndOwnerUsername(
    Long documentId, String ownerUsername);
```

Then a Spring-managed service can use:

```java
@PreAuthorize("@documentPolicy.isOwner(#documentId, authentication)")
public DocumentView readAllowed(
        @P("documentId") Long documentId) {
    return repository.findByIdAndOwnerUsername(
            documentId, currentUserName())
        .map(DocumentView::from)
        .orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));
}
```

This is an **optional fragment**, not a standalone runnable file: you must define `repository`, `currentUserName()`, Spring imports, bean wiring, and `@P` from `org.springframework.security.core.parameters.P`. `@P` helps SpEL resolve argument names reliably when compiling without Java `-parameters` metadata.

**Important trap:** Spring AOP proxy-based method security may **not run on self-invocation**. If a method inside the service calls `this.readAllowed(...)`, the invocation may bypass the proxy. Place guards at service boundaries called from other beans and test thoroughly.

### Should You Use `@PostAuthorize`?

An expression example:

```java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
```

only illustrates how to inspect the return value if the object has an `ownerUsername` property. It checks **after the method has run**; it is unsuitable for protecting methods that write data, send emails, delete files, or call external services. For sensitive data, placing an owner predicate in the query before fetching reduces the risk of processing unauthorized data.

If you want 403 instead of 404 when a method guard denies access, you can rely on `AccessDeniedException` from method security, but the response policy must remain consistent and avoid leaking existence through other paths.

## 12. Multi-Tenancy: A Valid Owner Can Still Be in the Wrong Tenant

A query filtered by owner alone is insufficient when users belong to multiple organizations or tenants.

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND owner_user_id = :trustedActorId
  AND tenant_id = :trustedTenantId;
```

`trustedTenantId` should not be taken directly from an `X-Tenant-Id` header without verifying membership. If a user switches tenants in the UI, the backend must verify the user is actually allowed to operate in that tenant.

Order of reasoning:

1. Verify authentication.
2. Map the actor to an internal immutable ID.
3. Determine the tenant context via verified membership.
4. Check permission for the operation type (read/edit/delete).
5. Query the record with ID + owner + tenant predicates.
6. Apply business state/locking for sensitive mutations.

A `ROLE_ADMIN` in tenant A does not automatically allow reading all documents in tenant B. Admin overrides must be explicitly designed, audited, and tested across tenants.

### Database Row-Level Security

With databases supporting RLS, you can add row-restricting policies at the DB layer. However, RLS does not automatically know Spring `Authentication`; the application must bind trusted user/tenant context to the DB connection/transaction, clean up the context when connections return to the pool, and avoid using a DB role that bypasses RLS. Treat RLS as a defense-in-depth layer, not a complete replacement for service authorization.

## 13. Create, Transfer, Delete, and Batch Operations

### Create Document

Do not accept a client-declared owner as proof:

```java
// WRONG: client chooses the owner.
new Document(request.ownerUserId(), request.title());
```

The server must obtain the actor from the verified principal and assign ownership per business rules. If creating on behalf of someone else is a supported feature, it needs specific permissions and auditing.

### Delete Document

An owner-only delete can execute a DB statement with `WHERE id=:id AND owner_user_id=:actorId` and inspect the affected row count, rather than a bare `deleteById(id)` after authentication.

### Bulk Delete / Export

For a list of IDs, check **every ID** or use a query with owner+tenant predicates and compare affected rows against policy. If a request includes one Alice document and one Bob document, it must not accidentally delete both. Explicitly define atomic failure vs. partial success, and test it.

### Transfer Ownership

Transferring ownership is a sensitive operation: verify the current actor has transfer rights, the recipient is valid in the tenant, document state allows transfer, consent requirements, auditing, and concurrency. After transfer, caches/search indexes/old share links may need updating or revocation. Never unconditionally set `ownerUserId` from the request.

## 14. 403, 404, and Not Disclosing Resource Existence

| Scenario | Suitable Response |
| --- | --- |
| Not logged in | 401 with an API entry point or 302 to login under form-login |
| Logged in, missing general role/permission | 403 |
| Document does not exist | 404 |
| Document exists but belongs to another user | 403 **or** 404 per policy |
| Mutation missing CSRF | Usually 403 before controller |
| Document is locked | 403/409 depending on business contract |

The JPA example chooses **404 for both "ID does not exist" and "ID belongs to someone else"**, reducing confirmation of private document existence. If choosing 403, still avoid leaking title, owner, tenant, or sensitive fields in the response.

Never return HTTP 200 with private data plus a `canEdit=false` field. View permission and edit permission are distinct conditions; an actor without view permission must not receive content just so the UI can hide an edit button.

## 15. Caching, Search, Files, and Easily Overlooked Bypass Paths

Other access paths can nullify a proper owner check on the main GET endpoint:

- **List/search:** `findAll()` and search indexes without tenant/owner filtering can leak records.
- **Cache:** cache keys using only document ID can serve Alice's cached response to Bob. Cache keys and privacy policies must account for actor/tenant.
- **CDN:** never publicly cache private data under URLs usable by other users.
- **File attachments:** `/documents/{id}/files/{fileId}` must verify the file→document relationship and the document's owner, not just the file ID.
- **Export/download:** CSV/PDF reports must enforce the same authorization policy, never bypassing it due to async processing.
- **WebSocket/SSE:** private events must be sent only to matching user/tenant subscriptions.
- **Background jobs:** require an explicit service identity/delegation policy, rather than running with blanket admin rights and emitting all data.
- **Share links:** signed URLs can act as capability credentials, but must be issued, scope/TTL-limited, and revoked per policy; they are not an excuse to skip checks on remaining APIs.

A test covering only `GET /api/documents/{id}` does not prove attachment thumbnails, version history, or audit trails are protected.

## 16. Concurrency, Revoked Permissions, and Stale Sessions

The owner can change while a request is in flight; roles or tenant memberships can also be revoked. You must define:

- **Read consistency:** DB queries reflect ownership at the appropriate point in time.
- **Write consistency:** DB updates verify owner/tenant validity within the transaction.
- **Optimistic locking:** when using `@Version`, check the version and avoid bypassing it via bulk updates.
- **Retry:** after a conflict, never retry automatically with broader permissions.
- **Revocation:** sessions or JWTs may hold stale role snapshots; for DB-stored ownership, requests must check current state when required by policy.
- **Distributed cache/index:** permission changes on node A must propagate to node B within a defined SLA.
- **In-flight requests:** an operation that passed authorization before revocation may commit afterward; sensitive workflows may need a recheck at commit time.

Do not claim that "logout or owner change cancels all JWTs and transactions" unless mechanisms and integration tests prove it.

## 17. Regression Test Checklist for Resource-Level Authorization

| Test | What Must Be Proven |
| --- | --- |
| Owner reads own record | Succeeds, correct DTO |
| Another user changes URL ID | Cannot read data |
| Another user sends PATCH with valid CSRF | Cannot modify |
| Non-existent ID | Returns valid 404 |
| Anonymous request | Login challenge, no content leaked |
| Client sends forged ownerId | Does not change actor/owner without transfer permission |
| List/search/export | Only in-scope data |
| Another user's file attachment | Cannot access via file ID |
| ROLE_ADMIN in another tenant | Allowed only if policy permits |
| Create record | Owner assigned from trusted principal |
| Ownership transfer during update | No privilege escalation via TOCTOU |
| Token/session with stale role | Complies with SLA and revocation policy |
| Caching by document ID | No data leak across principals |
| Bulk IDs mixing owned/unowned | Does not delete or export out of scope |
| Delete/restore/version endpoints | Consistent owner/tenant rules |

MockMvc is suitable for testing controller/filter/service behavior when fixtures bind identities properly. Real HTTP integration tests with actual authentication, sessions/tokens, network/proxies, and a real DB are needed for requirements beyond mock scope.

## 18. Review Questions with Answers

**Question 1.** Why does `authenticated()` fail to protect a document ID belonging to someone else?

**Answer:** It only ensures the request has a logged-in identity; it does not compare that identity against the specific record's owner.

**Question 2.** Client sends `ownerId=101`. Can the backend treat that as the current user ID?

**Answer:** No. The actor must come from a verified principal or server-side identity mapping.

**Question 3.** Does a UUID replace an owner check?

**Answer:** No. UUIDs reduce guessability but do not prevent IDs from being shared/leaked and do not prove access rights.

**Question 4.** How does `findByIdAndOwnerUsername` help compared to `findById`?

**Answer:** It returns only a record matching both the resource ID and the actor, reducing the risk of accidentally loading someone else's data and forgetting a check.

**Question 5.** Why shouldn't you check ownership and then update with `UPDATE ... WHERE id=:id` at a separate time?

**Answer:** Ownership can change between check and update. An update with an owner predicate/locking/version protects better according to transaction policy.

**Question 6.** Can Bob with a valid CSRF token modify Alice's document?

**Answer:** No. CSRF is only a request-level protection layer; it does not grant object-level permission.

**Question 7.** Does `@PreAuthorize` automatically run when a bean calls its own method?

**Answer:** A Spring AOP proxy may not intercept self-invocation; design proper service boundaries and test them.

**Question 8.** Why is using `@PostAuthorize` on a method that deletes files dangerous?

**Answer:** Authorization is checked after the method executes, when side effects may have already occurred.

**Question 9.** A document owner's email address changes. What must be ensured?

**Answer:** Ownership mapping should rely on an internal stable user ID so changing an email never causes lost or misassigned permissions.

**Question 10.** Is a `ROLE_ADMIN` user allowed by default to read documents in another tenant?

**Answer:** No. Cross-tenant access requires an explicit policy, least privilege, and auditing.

**Question 11.** When a record does not belong to the actor, is returning 404 acceptable?

**Answer:** Yes, it helps avoid revealing resource existence, but must be applied consistently across the API.

**Question 12.** A search endpoint returns Bob's data and the frontend hides the row. Is that safe?

**Answer:** No. The data has already been sent to an unauthorized client.

**Question 13.** Why shouldn't `ownerUserId` and `createdByUserId` be used interchangeably?

**Answer:** They represent different relationships; the creator is not necessarily the current owner.

**Question 14.** Does MockMvc `user("alice")` test Alice's password?

**Answer:** No. That is mock authentication for authorization testing; login testing must be done separately.

## 19. Pre-Production Acceptance Checklist

- [ ] Identify the caller identity and trusted internal user ID from Authentication.
- [ ] Do not accept current user/owner identity from untrusted body/query/headers.
- [ ] Clearly separate owner, creator, assignee, shared access, and tenant boundaries.
- [ ] Apply both HTTP authorization and object authorization.
- [ ] Read/list/search/export use owner/tenant predicates in queries.
- [ ] Update/delete verify permissions at mutation time and inspect affected rows.
- [ ] Never bind a JPA entity directly from client input when it has an owner field.
- [ ] Output DTOs contain only fields the actor is allowed to see.
- [ ] Create operations assign the owner from the trusted principal.
- [ ] Transfer/share/restore/version/attachment/bulk actions have explicit policies.
- [ ] `@PreAuthorize`, if used, executes through a Spring-managed proxy.
- [ ] Do not use `@PostAuthorize` to protect methods with side effects.
- [ ] CSRF remains enforced when browser sessions can automatically send credentials.
- [ ] Clearly define 401/302, 403, and 404 in the API contract.
- [ ] Admin/support overrides are tenant-scoped and audited.
- [ ] Caches, search indexes, CDNs, and event channels do not leak data across owners.
- [ ] Races/locking/versioning are tested on an appropriate database.
- [ ] Test own ID, foreign ID, missing ID, list, update, and invalid CSRF.
- [ ] Test real authentication and token/session revocation matching deployment.
- [ ] Never log raw tokens, private payloads, passwords, or session secrets.

## Conclusion

**Matching the current user against record ownership is object-level authorization**, not an authentication step or a general role check. In Spring Security Servlet, obtain the actor from verified `Authentication`, map to a trusted owner ID, and match against **real data**.

With Spring Data JPA, the clean solution is **reading by ID + owner** and **conditional writing by ID + owner**, adding tenant and business rules where required. The most important test is not "Alice can read Alice", but **"Alice cannot read or modify Bob's document even when logged in and holding a valid CSRF token"**. That is the boundary protecting resources against BOLA/IDOR.
