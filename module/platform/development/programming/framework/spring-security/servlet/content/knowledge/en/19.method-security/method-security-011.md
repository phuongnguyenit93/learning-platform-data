# Ordering with @Transactional and the Impact of Post-Execution Denial

> **Context:** Spring Security **Servlet**, Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring transaction management (typically JPA). The focus is the interaction between **method security** (`@PreAuthorize`, `@PostAuthorize`) and **transaction advice** (`@Transactional`): default AOP ordering, when transactions begin/commit/rollback, why returning HTTP **403 after a method runs does not prove data was rolled back**, how to design safe write operations, and how to test against a real database. Boot snippets require a project with matching dependencies; the standalone Java SE section at the end runs independently with JDK 17.

## 1. The Tricky Scenario: "It returned 403—why did the database still change?"

Consider the following business method (this is an **intentionally unsafe illustrative snippet**, not a real write API):

~~~java
@Transactional
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity changeThenCheck(Long id, String text) {
    DocumentEntity document = repository.findById(id).orElseThrow();
    document.setBody(text);     // Writes change in the persistence context.
    return document;           // Checked only after the method returns.
}
~~~

Suppose the document belongs to `alice`; user `bob` authenticates legitimately and calls an update on that document. What happens?

1. The method is invoked through a **Spring proxy**, and JPA loads the record.
2. The method modifies the document body and returns the entity.
3. The transaction advisor can **flush and commit** the data when the method completes.
4. `@PostAuthorize` then compares `returnObject.ownerName` with `authentication.name`.
5. The comparison is false; Spring Security throws an access denial, and HTTP may return **403**.
6. **Yet the database change may have already committed beforehand.**

Under common default advice ordering, this is a real scenario you must test for. **You cannot reason backwards that "403 = no side effect."** Blocking the HTTP response via a security check and rolling back a database transaction are two separate conditions.

If the method sends an email, publishes an event to a broker, calls a payment API, or writes to another system **before `@PostAuthorize` denies it**, JPA's transaction cannot automatically undo external side effects either. That is the fundamental reason *post-execution* checks must never serve as the primary barrier for critical write operations.

### Two security goals must be separated

- **Preventing data disclosure to unauthorized callers.** A `@PostAuthorize` on a read method can block returning an object when the object's properties are only known after querying.
- **Preventing unauthorized writes from executing.** This condition must be checked **before side effects** (and, when needed, re-verified inside the transaction at data-use time).

The two goals are related, yet **not identical**. A result blocked after computation does not revert the computation's prior state changes.

## 2. Method security and transactions are two AOP layers

Spring uses proxies/advisors/interceptors to apply multiple declarative behaviors around the same method call.

| Annotation / mechanism | Primary goal | Critical timing |
| --- | --- | --- |
| `@PreAuthorize` | Evaluates access conditions **before** the method body runs. | Before invoking the method. |
| `@PostAuthorize` | Evaluates an expression with `returnObject` **after** the method returns. | After the body, before the caller receives the result. |
| `@PreFilter` | Filters collection/array/map arguments before invocation when applicable. | Before the body; **not** a transaction guard. |
| `@PostFilter` | Filters elements of the result after the call. | After the body; does not roll back side effects. |
| `@Transactional` | Establishes transaction scope, committing or rolling back per rules. | Around the invocation within the advisor scope. |
| Spring MVC / servlet filters | Translates a denial exception into an HTTP response. | After the error propagates from the service up to the HTTP layer. |

**Java methods do not execute annotations in source-file line order.** Writing `@PreAuthorize`, `@Transactional`, and `@PostAuthorize` in one order vs. another in the source file **does not determine** interceptor ordering. Actual ordering depends on **advisor order**, the proxy chain, how method security and transactions are enabled, and compatible versions.

Therefore, simply changing:

~~~java
@PreAuthorize("hasAuthority('EDIT')")
@Transactional
public void edit(...) { ... }
~~~

to:

~~~java
@Transactional
@PreAuthorize("hasAuthority('EDIT')")
public void edit(...) { ... }
~~~

**does NOT mean "moving the transaction outside."** Both snippets above are merely illustrative fragments requiring a real method body and bean. To adjust nesting, you must configure Spring AOP advisor ordering explicitly or redesign method/transaction boundaries.

## 3. Common default advice ordering

When enabling modern Spring Security method security with `@EnableMethodSecurity`, interceptors are assigned order values to run checks at distinct points. Under the defaults published in the Spring Security 6 line, common milestones include:

~~~text
@PreFilter     around 100
@PreAuthorize  around 200
@Secured       around 300 (if enabled)
@RolesAllowed  around 400 (if JSR-250 enabled)
@PostAuthorize around 500
@PostFilter    around 600

Default transaction advisor:
  @EnableTransactionManagement(order = LOWEST_PRECEDENCE)
  meaning very low precedence priority
~~~

**Version and configuration note:** This diagram helps explain default advice ordering in Spring Security 6.x releases, **not a permanent rule** across every release. Offsets, additional advisors, proxy chains, order overrides, or multiple proxies can alter behavior. Whenever transaction outcomes form a security boundary, **verify your application's actual advisor order** rather than trusting a static table.

In Spring AOP, an advisor with **higher precedence (a smaller numeric order)** generally wraps outside an advisor with lower precedence (a larger numeric order). Going into the method, the outer advisor runs first; coming out, the outer advisor's "after method" logic runs **last**.

With those defaults, a common call flow looks like:

~~~text
Request / Controller
  |
  v
[PreAuthorize advisor, order ~200]          <- checks permission first
  |
  v
[PostAuthorize advisor, order ~500]         <- wraps outside tx
  |
  v
[TransactionInterceptor, LOWEST_PRECEDENCE]
  | BEGIN transaction
  |      |
  |      v
  |   Target service method
  |      |
  |   JPA modifies entity
  |      |
  | COMMIT transaction
  v
[PostAuthorize checks returnObject]         <- can deny AFTER commit
  |
  v
Caller / Controller / Servlet exception handling
~~~

Conclusion: **A post-method denial decision can occur *outside* a transaction scope that has already committed.**

### Why does this happen?

The transaction advisor sits **inside** the `@PostAuthorize` advice. The transaction interceptor receives the method result, commits the transaction, and returns the result to the outer interceptor. Only then does post-authorization inspect `returnObject` and potentially deny access. Because the exception is thrown **after** the transaction interceptor has already completed successfully, it has no active transaction left to roll back.

Conversely, `@PreAuthorize` typically runs before the transaction advisor when placed outside it: if permission is missing, the method body is never called, and the write transaction **is not even started** by the inner advisor. That is the desired behavior for a coarse access gate.

### Do not confuse "outer advisor" with "outer transaction"

When we say **outer transaction**, we mean the transaction interceptor wraps outside `@PostAuthorize`, illustrated logically as:

~~~text
TransactionInterceptor
  BEGIN
    PostAuthorize interceptor
      Target method modifies data
      PostAuthorize checks result -> DENY, throws runtime exception
  ROLLBACK as exception exits the transaction boundary
~~~

In this diagram, a `RuntimeException`/`AccessDeniedException` passing through the transaction interceptor can trigger a **rollback under default rules**. However, that requires **a different ordering configuration**; you must never assume an app runs that way by default.

## 4. @Transactional rollback rules do not mean "every error rolls back"

Default Spring transaction management typically **rolls back on `RuntimeException` and `Error`**, not automatically on every checked exception. Custom rollback rules, catching/suppressing exceptions, nested transactions, or propagation settings change the outcome.

| Event | Rollback behavior |
| --- | --- |
| `RuntimeException` exits the method while the transaction has **not committed** | Rolls back that transaction by default. |
| Checked exception exits without `rollbackFor` | Does not roll back by default in standard configuration. |
| Exception is caught and the method returns normally | Transaction advisor may commit unless marked rollback-only. |
| Exception is thrown **after the transaction has committed** | Cannot roll back an already completed transaction. |
| `@Transactional(noRollbackFor=...)` matches the exception | Can commit despite the exception when configured that way. |
| `REQUIRES_NEW` already committed in another call | Not automatically rolled back by an outer transaction later. |
| Email/HTTP call/event sent outside the transaction | Not undone by database rollback. |
| DB changes remain in persistence context and have not flushed/committed | Can roll back if the error happens **inside** an appropriate transaction. |

In Spring Security 6, missing-permission failures typically surface as `AccessDeniedException` or a specialized subclass inheriting from it. This is a runtime exception, yet **it only triggers rollback if it passes through an active transaction advisor** with matching rollback rules.

**There is no equivalence** between "the request returned status 403" and "Spring called `transaction.rollback()`." HTTP exception translation handles the **protocol**; the transaction manager handles **data**.

### Flush is not commit

With JPA:

- `entity.setBody(...)` on a managed entity usually marks it dirty in the persistence context; a SQL UPDATE may execute on flush.
- `flush()` sends changes down to JDBC within the transaction, but **does not mean the transaction has committed**. If the right transaction rolls back, flushed updates can still be undone by the DB.
- `commit()` finalizes the transaction; once committed successfully, a post-authorize denial **cannot "rewind" that commit**.
- External side effects or separate transactions are another matter; even a successful JPA rollback cannot unsent an already-sent email.

Therefore, do not conclude "the database was permanently written" solely because a SQL UPDATE appeared in logs. You must **re-read the state in a fresh transaction** after the request completes, as shown in the integration tests in Section 9.

## 5. @PreAuthorize and @PostAuthorize: using each for its intended purpose

### @PreAuthorize: blocking before the method body

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
@Transactional
public void updateDocument(Long id, String body) {
    // Write data...
}
~~~

This is a **code fragment** and will not compile standalone without its class/imports/method body. For a user lacking `DOCUMENT_WRITE`, Spring Security blocks execution before the write method runs, provided the call goes through the security proxy.

Drawback to watch for: `hasAuthority("DOCUMENT_WRITE")` is a **coarse functional permission**—it does not check *whether this user may modify this specific document ID*. Someone with write authority still might not be allowed to modify documents in another tenant. You must add server-side resource-level authorization without treating client-sent IDs as "verified."

### @PostAuthorize: checking returnObject after the method runs

~~~java
@Transactional(readOnly = true)
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity readOwnedDocument(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Using a **read-only method** to load a document and then verify the owner of the returned object can fit certain flows. However:

- The method and inner interceptors have already executed before the result is denied.
- `readOnly=true` is a read-only transaction hint/management setting and **should not be treated as an automatic security wall**: buggy code can still produce side effects (emit events, call APIs, update caches).
- With JPA lazy loading, if `@PostAuthorize` runs after the transaction ends and the entity is detached, accessing an unloaded association can fail. Use a DTO containing the checked fields or fetch required properties inside the transaction.
- If the method writes sensitive logs/audits before the check, denying the return value **does not erase the logs**.

**Do not use `@PostAuthorize` as the primary condition for side-effecting POST/PUT/PATCH/DELETE operations.** Use it mainly to **restrict return values** in pure read flows specifically designed to have no side effects.

### @PostFilter is not an undo mechanism

`@PostFilter` filters elements of the result after the method has run. It cannot undo prior changes, and post-filtering can heavily impact performance/memory. If a query returns too much data before filtering, all that data has already been loaded into server memory. For large or sensitive datasets, prefer **filtering directly in the query** by principal/tenant where appropriate.

## 6. "Before execution" and "right before write" are also distinct boundaries

Suppose `@PreAuthorize("@policy.canEdit(authentication, #id)")` queries the owner table before the method's transaction starts. Between **check** and **use**, another process could change ownership/permissions or move the document to a different tenant. This is a form of **TOCTOU (time-of-check to time-of-use)**.

Three layers of protection are commonly used:

1. **Coarse permission gate before the method** via `@PreAuthorize`, such as requiring `DOCUMENT_WRITE`.
2. **Re-verifying permissions against real data** inside the transaction, close to entity mutation—e.g., after loading the document from the DB, comparing the trusted owner/tenant before setting fields.
3. For critical race conditions, using **optimistic locking `@Version`, pessimistic locking, conditional SQL UPDATEs on owner/tenant, or appropriate isolation** to bind the decision to the exact state at write time. A transaction by itself does not guarantee absence of TOCTOU at all isolation levels.

**Rule:** policy must be enforced before irreversible side effects and against trusted source data. Never check ownership from a client JSON `owner` field and treat that as sufficient, because attackers can tamper with the request body.

## 7. Demonstration project: one unsafe method, two proper gates

The Spring Boot 3 example with H2/JPA aims to **demonstrate observable differences**:

- Endpoint `POST /docs/{id}/post-only`: intentionally uses `@PostAuthorize` **after modifying the entity**, showing that 403 can accompany a **commit**. This is a demo vulnerability—**do not use in production**.
- Endpoint `POST /docs/{id}/guarded`: uses `@PreAuthorize` to check `DOCUMENT_WRITE` before the method and verifies the owner **before modifying** inside the transaction.
- Endpoint `GET /docs/{id}/own`: uses `@PostAuthorize` on a **read-only method** to illustrate checking ownership of the result with no business side effects.
- MockMvc tests a user missing permissions, a non-owner user, and a valid user. Tests use a **real** in-memory H2 database and re-read the DB after each request.

### Dependencies and version scope

Java 17+ project with:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-aop
spring-boot-starter-data-jpa
com.h2database:h2             (runtime)
spring-boot-starter-test      (test)
spring-security-test          (test)
~~~

`spring-boot-starter-aop` is declared explicitly to avoid implicit dependency surprises across projects. Spring Security 6's `@EnableMethodSecurity` uses proxy/interceptor infrastructure; `@Transactional` requires a transaction manager, auto-configured by Boot/JPA in this example.

Files live under package `com.example.txsecurity`:

~~~text
src/main/java/com/example/txsecurity/
  TxSecurityApplication.java
  SecurityConfig.java
  DocumentEntity.java
  DocumentRepository.java
  DocumentService.java
  DocumentController.java
src/main/resources/
  application.properties
src/test/java/com/example/txsecurity/
  MethodSecurityTransactionTest.java
~~~

This demo does not use existing services, security configs, or repositories from a real system. All credentials are **dummy values for localhost testing**—never copy them to production.

### 7.1. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:txlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 is an in-memory learning DB; `create-drop` drops/creates the schema on app start/stop and must **not** be used in production. `open-in-view=false` reduces coupling between the JPA session and the HTTP request, making transaction boundaries clearer in this lesson.

### 7.2. DocumentEntity.java

~~~java
package com.example.txsecurity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_name", nullable = false)
    private String ownerName;

    @Column(name = "body", nullable = false)
    private String body;

    protected DocumentEntity() {
        // JPA requires a no-argument constructor.
    }

    public DocumentEntity(String ownerName, String body) {
        this.ownerName = ownerName;
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }
}
~~~

The entity uses getter `getOwnerName()` so the `returnObject.ownerName` expression can read the `ownerName` property per JavaBean conventions. It never takes the owner from the client during updates; instead, it reads it from the DB record.

In production, you need length validation, concurrency/versioning, tenancy, auditing, and valid update policies. In this demo, we only want to highlight **ordering and rollback**.

### 7.3. DocumentRepository.java

~~~java
package com.example.txsecurity;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {
}
~~~

Spring Data JPA generates the implementation automatically because the interface resides in a package scanned by Boot. Both `save` and `findById` go through the Spring Data repository; inside a service with a longer transaction, dirty checking flushes when the transaction commits.

### 7.4. SecurityConfig.java

~~~java
package com.example.txsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement // Uses default order.
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("DOCUMENT_WRITE", "DOCUMENT_READ")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-bob"))
            .authorities("DOCUMENT_WRITE")
            .build();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .authorities("DOCUMENT_READ")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, reader);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/docs/**")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/docs/**")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // CSRF is enabled by default for POST; tests must send a valid token.
        return http.build();
    }
}
~~~

**Read carefully:**

- `@EnableMethodSecurity` enables `@PreAuthorize` and `@PostAuthorize` processing. Without it, method-security annotations may have no effect.
- `@EnableTransactionManagement` illustrates enabling the transaction proxy with the **default order**, without explicitly altering ordering to "force a rollback."
- The HTTP rule only requires **authenticated**; `DOCUMENT_WRITE` and ownership checks are enforced at the service. If `@EnableMethodSecurity` is missing or a call bypasses the proxy, routes can become dangerous. Production should combine HTTP policy checks with defense-in-depth service/resource policies.
- `httpBasic` is a demo choice. Real-world HTTP Basic is only appropriate over TLS and per your threat model.
- Both `alice` and `bob` hold `DOCUMENT_WRITE`, yet only Alice owns the fixture document. `reader` only holds `DOCUMENT_READ` to demonstrate the pre-authorize gate blocking a caller lacking coarse write authority.
- CSRF is not disabled, so a POST lacking a token is blocked before reaching the service; do not confuse a missing-CSRF 403 with a service rollback.

### 7.5. DocumentService.java — the most critical code

~~~java
package com.example.txsecurity;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    // INTENTIONALLY UNSAFE: checks only after mutating.
    // Used to prove 403 can still accompany a commit.
    @Transactional
    @PostAuthorize("returnObject.ownerName == authentication.name")
    public DocumentEntity editPostOnly(Long id, String newBody) {
        DocumentEntity doc = repository.findById(id).orElseThrow();
        doc.setBody(newBody);
        return doc;
    }

    // Better approach: block coarse permission before the method runs.
    @Transactional
    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    public DocumentEntity editGuarded(Long id, String newBody) {
        DocumentEntity doc = repository.findById(id).orElseThrow();

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        // Check owner/tenant from the server-side record BEFORE modifying.
        if (auth == null || !doc.getOwnerName().equals(auth.getName())) {
            throw new AccessDeniedException(
                    "Access denied for this document");
        }

        doc.setBody(newBody);
        return doc;
    }

    // A more reasonable use case for PostAuthorize: reading, not mutating.
    @Transactional(readOnly = true)
    @PostAuthorize("returnObject.ownerName == authentication.name")
    public DocumentEntity readOwn(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

**Method-by-method breakdown:**

**`editPostOnly`:** Has no `@PreAuthorize` and performs no owner check before modifying data. The transaction interceptor can commit the change, and only then does `@PostAuthorize` reject access upon seeing `returnObject.ownerName != authentication.name`. This is an intentional bug for learning—**never expose it to production traffic**.

**`editGuarded`:** A user lacking `DOCUMENT_WRITE` is blocked before the method runs. A user with `DOCUMENT_WRITE` who is not the owner enters the method, loads the record, checks ownership inside the transaction, and throws `AccessDeniedException` **before `setBody`**. Even if data were changed before the exception, a runtime exception could still mark the transaction for rollback; what matters most is avoiding any side effect in the first place.

**`readOwn`:** Uses `@PostAuthorize` after loading the record in a read-only transaction. The method only reads the DB and modifies no contents. If Bob reads Alice's document, the result is denied before the HTTP controller returns the content. This check does not replace SQL/tenant-level read authorization; for highly sensitive data or large queries, filter directly at query time.

**Do not take identity from body or query parameters:** `SecurityContextHolder.getContext().getAuthentication()` comes from Spring Security, unlike a client-supplied `request.getParameter("username")`. Ensure your app's authentication provider verifies credentials properly and never derives authorities from client input.

**Do not assume every query inside a transaction is race-free:** If ownership changes concurrently after loading the record, isolation/locking/optimistic versioning governs the result. In critical flows, you may need a conditional SQL UPDATE checking `owner_id` and `tenant_id`, locking, or optimistic concurrency control.

### 7.6. DocumentController.java

~~~java
package com.example.txsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @PostMapping("/docs/{id}/post-only")
    public String unsafeUpdate(
            @PathVariable Long id,
            @RequestParam("text") String body) {
        return service.editPostOnly(id, body).getBody();
    }

    @PostMapping("/docs/{id}/guarded")
    public String guardedUpdate(
            @PathVariable Long id,
            @RequestParam("text") String body) {
        return service.editGuarded(id, body).getBody();
    }

    @GetMapping("/docs/{id}/own")
    public String readOwn(@PathVariable Long id) {
        return service.readOwn(id).getBody();
    }
}
~~~

**The `/post-only` route is intentionally unsafe for testing only.** Even when the HTTP response returns 403, committed side effects can occur. In a real app, **remove this endpoint** and only expose paths that enforce policy before writing.

The controller only calls **public methods on another service bean**, ensuring calls go through the Spring AOP proxy. If the controller calls `new DocumentService(...)` or the service calls `this.editGuarded(...)` internally on itself, proxy interception can be bypassed.

### 7.7. TxSecurityApplication.java

~~~java
package com.example.txsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxSecurityApplication.class, args);
    }
}
~~~

Place the main class in a parent package of your components. In a project that already has a main class, do not add a second one outside the scope of a standalone demo.

## 8. Timeline of the three scenarios

### 8.1. Alice is the owner and allowed to write

~~~text
HTTP POST /docs/123/guarded + valid CSRF
  |
  | HTTP authentication: alice
  |
  v
@PreAuthorize: has DOCUMENT_WRITE -> PASS
  |
  v
Transaction: BEGIN
  |
  | Load document #123, ownerName=alice
  | ownerName == authentication.name -> PASS
  | setBody("allowed")
  |
  v
Transaction: FLUSH + COMMIT
  |
  v
HTTP 200, body "allowed"
~~~

### 8.2. Reader lacks functional permission

~~~text
HTTP POST /docs/123/guarded + valid CSRF
  |
  | HTTP authentication: reader
  |
  v
@PreAuthorize: missing DOCUMENT_WRITE -> DENY
  |
  x Method body does not run
  x No setBody
  x No document change committed
  |
  v
Typically HTTP 403
DB body remains "original"
~~~

### 8.3. Bob has functional permission but is not the owner — post-check is too late

~~~text
HTTP POST /docs/123/post-only + valid CSRF
  |
  | HTTP authentication: bob
  |
  v
PostAuthorize advisor (will check AFTER)
  |
  v
Transaction: BEGIN
  |
  | Load #123: ownerName=alice
  | setBody("unauthorized-change")
  |
  v
Transaction: COMMIT
  |
  v
@PostAuthorize:
  returnObject.ownerName == authentication.name ?
  "alice" == "bob" -> FALSE
  |
  v
AccessDeniedException -> HTTP 403
  |
  v
Re-read DB: body is still "unauthorized-change"
~~~

The crux of the failure: **the denied response is generated after the DB commit**, because the advisors are nested in that order. This is not a database rollback bug, but **placing the permission check at the wrong point in the write lifecycle**.

## 9. MockMvc + H2 integration tests: observing both HTTP and DB

Create `src/test/java/com/example/txsecurity/MethodSecurityTransactionTest.java`:

~~~java
package com.example.txsecurity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityTransactionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository repository;

    private Long documentId;

    @BeforeEach
    void resetDatabase() {
        // Repository operations are committed before each test.
        repository.deleteAll();
        documentId = repository.saveAndFlush(
                new DocumentEntity("alice", "original")).getId();
    }

    private String databaseBody() {
        // Query repository after the request has completed.
        return repository.findById(documentId)
                .orElseThrow().getBody();
    }

    @Test
    void postAuthorizeCanDenyAfterTransactionCommitted()
            throws Exception {
        mvc.perform(post("/docs/{id}/post-only", documentId)
                .with(csrf())
                .with(httpBasic("bob", "demo-bob"))
                .param("text", "unauthorized-change"))
            .andExpect(status().isForbidden());

        // Point to prove: 403 did NOT prevent the prior commit.
        assertEquals("unauthorized-change", databaseBody());
    }

    @Test
    void preAuthorizeStopsUserWithoutWritePermission()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("reader", "demo-reader"))
                .param("text", "should-not-write"))
            .andExpect(status().isForbidden());

        assertEquals("original", databaseBody());
    }

    @Test
    void inTransactionOwnerCheckStopsNonOwner()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("bob", "demo-bob"))
                .param("text", "should-not-write"))
            .andExpect(status().isForbidden());

        assertEquals("original", databaseBody());
    }

    @Test
    void ownerWithWritePermissionMayUpdate()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("alice", "demo-alice"))
                .param("text", "allowed"))
            .andExpect(status().isOk())
            .andExpect(content().string("allowed"));

        assertEquals("allowed", databaseBody());
    }

    @Test
    void postAuthorizeIsUsefulForReadOnlyResult()
            throws Exception {
        mvc.perform(get("/docs/{id}/own", documentId)
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/docs/{id}/own", documentId)
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("original"));

        assertEquals("original", databaseBody());
    }

    @Test
    void csrfDeniedBeforeServiceIsDifferentFailure()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(httpBasic("alice", "demo-alice"))
                .param("text", "not-saved"))
            .andExpect(status().isForbidden());

        // 403 may be due to missing CSRF rather than method security.
        assertEquals("original", databaseBody());
    }
}
~~~

### Understanding each test

- `postAuthorizeCanDenyAfterTransactionCommitted` is the most important test: **HTTP 403 yet the DB holds the modified value** under the default advisor order. Assertions looking only at 403 will miss this security vulnerability.
- `preAuthorizeStopsUserWithoutWritePermission` proves a caller lacking `DOCUMENT_WRITE` is denied **before the service body runs**.
- `inTransactionOwnerCheckStopsNonOwner` proves a user with coarse permissions who does not own the object is still denied before mutation; the transaction ends without saving any update.
- `ownerWithWritePermissionMayUpdate` is the positive case to guard against overly strict config rejecting all requests with 403.
- `postAuthorizeIsUsefulForReadOnlyResult` checks object-level authorization when reading only; Bob is denied while Alice receives the content.
- `csrfDeniedBeforeServiceIsDifferentFailure` shows a 403 originating in `CsrfFilter`, not from the transaction or method annotation. When testing POST method security, include `csrf()` if CSRF is enabled on the web chain.

**Very important:** the test class above **is not** annotated with `@Transactional`. Putting `@Transactional` on the test can cause the test and service to unintentionally share the same transaction/thread in a way that does not represent HTTP runtime, **hiding the commit boundary** this lesson needs to observe. After the request, the test uses a separate repository operation to re-read the DB and prove whether changes committed.

Run with Maven Wrapper:

~~~bash
./mvnw test
~~~

These tests and expectations are reproducible when the app uses matching dependencies, default transaction advisor order, and compatible Spring Boot 3/Security 6 versions. **This does not claim execution across every minor release.** If the "403 yet committed" test does not reproduce, first check interceptor/advisor ordering, whether method security is enabled, whether calls go through the proxy, whether an outer test transaction is active, JPA transaction/flush settings, and any custom rollback rules.

### Testing beyond MockMvc

MockMvc traverses the Servlet filter chain, but it does not simulate all production behaviors of connection pools, distributed transactions, queues, browsers, or proxies. For payment/refund actions, you need integration tests covering races, transaction propagation, external side effects, and audit/idempotency.

## 10. What if we change the order so the transaction wraps outside @PostAuthorize?

You can adjust the transaction advisor's order. An illustrative application-wide configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(order = 0)
class TransactionAdvisorPriorityExample {
}
~~~

**This is an ALTERNATIVE approach/experiment**—do not blindly add it alongside the existing `@EnableTransactionManagement` in `SecurityConfig` from Section 7 and expect no conflict. This setting alters the **transaction advisor order across the entire application**, not just one method, and can cause transactions to start earlier (even before pre-authorization) or affect interactions with caching/retry/audit advisors.

If the transaction order is `0` (higher precedence than positive-order method-security advisors in corresponding configurations), the transaction can wrap outside `@PostAuthorize`:

~~~text
Transaction: BEGIN
  |
  v
PreAuthorize check
  |
  v
Target method writes data
  |
  v
PostAuthorize check:
  DENY -> RuntimeException
  |
  v
Transaction: ROLLBACK per rollback rules
~~~

As a result, the denial exception crosses **through** the transaction boundary before commit, allowing database writes to roll back. However, this is **neither the only solution nor the best one** for keeping an "edit first, check later" flaw:

1. The transaction opens before pre-authorization, widening transaction scope and impacting performance/locks.
2. `@Transactional(noRollbackFor = AccessDeniedException.class)`, different rollback configurations, caught exceptions, or inner `REQUIRES_NEW` calls can still allow DB commits.
3. Emails, externally published messages, or remote API calls **cannot be rolled back**.
4. Multiple proxies, additional advisors, or unintercepted call paths may bypass transaction interception.
5. Changing global order alone does not prove owner policies were enforced **before side effects**.
6. If returning an object with lazy associations, an outer transaction might aid evaluation, yet it also changes lazy-loading timing and performance and must be tested explicitly.

**Primary recommendation:** for writes, check permissions before mutation; treat transaction ordering as a **measured/tested engineering option** for cases requiring rollback if post-checks fail, never as an excuse to mutate data before authorization checks.

## 11. Self-invocation inside the same bean: the proxy does not run

Spring method security and transactions typically use AOP proxies. An external call into a public bean method can be intercepted; an internal call within the same object via `this.method()` normally **does not go through the proxy**.

~~~java
@Service
public class ExampleService {

    public void entry(Long id) {
        this.protectedAction(id); // BYPASSES common proxy interception.
    }

    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    @Transactional
    public void protectedAction(Long id) {
        // Mutating operation...
    }
}
~~~

This is an **illustrative fragment**, not standalone: it requires imports for `@Service`, `@PreAuthorize`, `@Transactional`, and a real method body. When Spring uses proxy-based AOP, `this.protectedAction` does not trigger advice for that internal call. The result can **bypass both method security and transactions** even though the annotations are placed correctly on the method.

Safer ways to structure it:

- Have callers in other beans invoke a public service method through the Spring bean/proxy.
- Extract unannotated internal logic into a helper method (within the same bean) while exposing only **a single protected entry point**.
- When nested operations need a distinct transaction, create a separate bean with a clear contract and call through the managed bean; do not treat self-injection as a default cure without understanding proxies.
- Do not rely on private/final methods or direct object instantiation for interceptor protection; support varies by proxy type, visibility, and version. Always test that advice actually runs.

### Two transactions do not merge merely for sharing a request

A service method calling a bean annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` can start an independent transaction. If the inner method has already committed, an outer transaction rolling back when `@PostAuthorize` denies access **does not undo the inner commit**. Operations such as sending email, push notifications, RPCs, or calling a payment gateway also sit outside the database transaction.

For critical side effects, prefer: **authorize first**, conditional DB writes, **transactional outbox** when publishing messages after commit, and idempotency/compensation for external systems. Never assume a JPA transaction acts as "undo everything."

## 12. Common issues and how to analyze them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| POST returns 403 yet DB changed | `@PostAuthorize` wraps outside transaction advice; commit precedes denial. | Re-read DB after request in a new transaction; check advisor order. |
| `@PreAuthorize` does not block | `@EnableMethodSecurity` not enabled, self-invocation, manually `new`-ed object, or unproxied method. | Test the service bean from another caller; verify proxy. |
| `@Transactional` present yet rollback did not happen | Exception outside tx/after commit, exception caught, modified rollback rules, or separate transaction committed. | Inspect tx boundaries and rollback rules. |
| Reordering annotations does not fix it | Annotation order in source does not dictate advice order. | Inspect advisor orders and proxy chain. |
| Only unit tests mocking repository look safe | Mocks have no real flush/commit. | Use H2/Testcontainers and assert DB state after HTTP request. |
| Test behavior affected by test transaction | Outer `@Transactional` on the test defers commits. | Avoid `@Transactional` on tests observing commits, or separate execution threads/transactions. |
| GET denied after `@PostAuthorize` | Result owner differs from authentication. | For read methods, inspect fixture data/SpEL and resource permissions. |
| POST without CSRF returns 403 | `CsrfFilter` rejects before reaching the method. | Include `csrf()` when testing method security independently. |
| User with `DOCUMENT_WRITE` modifies another tenant's record | Checked only functional authority without owner/tenant check. | Verify object state inside transaction and use conditional updates. |
| Service writes DB then sends email before denial | External side effects do not roll back. | Move authorization earlier; use outbox and idempotency. |
| Adding transaction order 0 slows down the system | Transactions open earlier around security checks. | Measure locks/duration/latency; consider redesigning call graph. |
| Owner changes in a race after pre-check | TOCTOU between check and update. | Locking, versioning, conditional updates, and tenant policy. |
| `@PostAuthorize` throws `LazyInitializationException` | Expression accesses lazy association after tx ends. | Appropriate fetch/DTO/tx boundaries without disabling security. |

### Five questions to confirm when debugging

1. **Is method security actually enabled?** Is `@EnableMethodSecurity` present, and are policy annotations intercepted?
2. **Does the call go through the proxy?** Controller → Spring bean service, or `this.method()`/`new`?
3. **What is the actual advisor order?** Does transaction advice wrap outside or inside `@PostAuthorize`?
4. **Which transaction boundaries does the exception cross?** Is the `RuntimeException` thrown before commit, caught anywhere, or crossing nested/`REQUIRES_NEW`?
5. **Did the DB actually persist the change after the request?** Verify in a fresh transaction rather than inferring from HTTP status or SQL flush logs.

If you merely reorder annotations and test a single HTTP 403 case, you have not answered questions 3–5.

## 13. Standalone Java 17: simulating outer/inner advisors and rollback outcomes

The following program only **simulates ordering**; it does not use Spring, JDBC, or Spring AOP. Its goal is to contrast cleanly between "post-check runs after commit" and "post-check runs inside the transaction."

Create `TransactionOrderDemo.java`:

~~~java
public final class TransactionOrderDemo {

    private static final class State {
        String persisted = "original";
    }

    private static void transactionInnerThenDeny(State db) {
        System.out.println("CASE 1: transaction inner");
        System.out.println("BEGIN");
        db.persisted = "changed";
        System.out.println("COMMIT");
        // Post-check now denies; it is too late to roll back.
        System.out.println("DENY after commit");
        System.out.println("db=" + db.persisted);
    }

    private static void transactionOuterAndDeny(State db) {
        System.out.println("CASE 2: transaction outer");
        System.out.println("BEGIN");
        String before = db.persisted;
        db.persisted = "changed";
        System.out.println("DENY before commit");
        // Simulate ROLLBACK when the transaction wraps outside post-check.
        db.persisted = before;
        System.out.println("ROLLBACK");
        System.out.println("db=" + db.persisted);
    }

    public static void main(String[] args) {
        transactionInnerThenDeny(new State());
        transactionOuterAndDeny(new State());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac TransactionOrderDemo.java
java TransactionOrderDemo
~~~

**Exact** stdout:

~~~text
CASE 1: transaction inner
BEGIN
COMMIT
DENY after commit
db=changed
CASE 2: transaction outer
BEGIN
DENY before commit
ROLLBACK
db=original
~~~

**Do not misunderstand:** This program only manipulates an in-memory field to simulate transactions; it has no DB engine, JPA dirty checking, or Spring `@PostAuthorize`. It does not prove advisor behavior for any specific Spring Boot version. The MockMvc + H2 tests in Section 9 are what directly verify **how rules run with Spring Security / JPA** in the demo.

## 14. If access control depends on returnObject, how do you make it safe?

There are cases where an object's owner cannot be known before querying. Reasonable options include:

**A. Read-only: query then check afterwards, avoiding side effects.**

~~~java
@Transactional(readOnly = true)
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity readOne(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Suitable when you want to block returning the object to the caller. Ensure read logic does not emit data elsewhere before the post-check and handles lazy loading properly.

**B. Write: load object + check before mutation within the same transaction.**

~~~java
@Transactional
@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
public void updateOne(Long id, String text) {
    var doc = repository.findById(id).orElseThrow();
    if (!doc.getOwnerName().equals(
            SecurityContextHolder.getContext()
                .getAuthentication().getName())) {
        throw new AccessDeniedException("Forbidden");
    }
    doc.setBody(text);
}
~~~

This is a code fragment using the repository and imports from the service defined earlier. It never uses a client-supplied owner. When transaction isolation alone does not guarantee ownership cannot change concurrently, add optimistic locking or a conditional update.

**C. Conditional database UPDATE by user/tenant.**

SQL concept:

~~~sql
UPDATE documents
   SET body = :new_body
 WHERE id = :id
   AND owner_name = :authenticated_actor;
~~~

The `:authenticated_actor` value must come from server-side verified authentication, never from client query/body parameters. If affected rows = 0, treat it as not found/forbidden per your existence-leak prevention policy. This is an SQL concept—named parameter syntax depends on the JDBC/JPA adapter; real applications need transactions/repositories, versioning/concurrency, tenancy, and data validation.

**D. Authorization policy bean with `@PreAuthorize`, plus re-verification at use time.**

~~~java
@PreAuthorize(
    "hasAuthority('DOCUMENT_WRITE') and " +
    "@documentPolicy.mayEdit(authentication, #id)")
@Transactional
public void edit(Long id, String text) {
    // Query, check state/tenant once more if needed,
    // then update...
}
~~~

This is an illustrative method fragment; `documentPolicy` must be a trusted Spring bean. By default, pre-checks can occur **before the method's transaction**, creating TOCTOU; do not rely on an out-of-transaction DB pre-check as permanent proof when permissions/ownership can change.

**E. What if you still need `@PostAuthorize` for a mutation?**

Only with a rigorously reviewed design justification—you must verify advisor nesting, transaction rollback, exception propagation, side effects, queuing, retries, child transactions, and test coverage. Treat this as a **hard-to-prove-safe exception**, never the default choice for write endpoints.

## 15. HTTP 403, AccessDeniedException, and transaction events are three distinct signals

In Spring Security Servlet:

~~~text
Controller calls service
  |
  v
Method security denial
  |
  v
AccessDeniedException / AuthorizationDeniedException
  |
  v
ExceptionTranslationFilter / AccessDeniedHandler
  |
  v
HTTP 403 (typically for authenticated users)
~~~

In this path, the HTTP 403 response occurs **after** or **during** the service call stack depending on when the exception fires. Once a transaction has committed, `ExceptionTranslationFilter` has no capability to "undo a JPA transaction."

On the other hand:

~~~text
HTTP POST missing CSRF
  |
  v
CsrfFilter -> 403
  |
  x Controller does not run
  x Service @PreAuthorize/@PostAuthorize does not execute
  x No mutation occurs in this service
~~~

Therefore, merely seeing 403 in access logs does not prove "method security ran" or "the transaction rolled back." You must separate **authentication failure**, **CSRF failure**, **authorization denied**, **transaction commit/rollback**, and **business audit**. Observability systems can correlate events, metrics, traces, and proper database audits without logging raw tokens/passwords/cookies.

### Testing to refute false conclusions

A strong security test suite includes:

- **Positive write:** valid user, valid permission, valid owner → 200, DB updated.
- **Negative write before method:** missing coarse permission → 403, DB unchanged.
- **Negative write inside transaction:** has general permission but is not owner → 403, DB unchanged.
- **Negative post-only intentionally unsafe:** denied after write → 403, DB **already changed** (to detect the anti-pattern).
- **Negative CSRF:** POST without token → 403, service did not run.
- **Read-only post-check:** non-owner user → 403, no mutation.
- **Race/concurrency:** document ownership/tenant/version changes across two competing requests.
- **External side effect:** emails/messages/payments are never dispatched for denied requests.

Once the pipeline removes the unsafe method, do **not** keep a production test expecting 403 alongside a commit as desired behavior. Keep it as an educational/anti-pattern test in a separate module, or replace it with a regression test asserting **denial without side effects**.

## 16. Self-check questions

**Q1. Does the order of annotations in a source file determine whether `@Transactional` runs before `@PostAuthorize`?** No. Spring AOP advisor order and the proxy chain decide.

**Q2. Why is `@PostAuthorize` dangerous for write methods?** Because the check runs after the method body and potentially after an inner transaction has already committed; 403 cannot undo a commit.

**Q3. What does `@PreAuthorize` solve?** It blocks callers lacking permissions before the method runs. For object-level permissions, you still need trusted owner/tenant checks and concurrency handling on writes.

**Q4. Does `@Transactional` roll back when HTTP returns 403 or when an exception crosses the transaction interceptor?** When the transaction interceptor catches a failure matching rollback rules **before commit**; HTTP status by itself does not trigger rollback.

**Q5. If you move the transaction advisor outside `@PostAuthorize`, are all side effects guaranteed to roll back?** No. Only transactional resources within matching scope roll back; `REQUIRES_NEW`, email/RPCs, exception rules, and proxy bypasses can still leave side effects intact.

**Q6. Should `@PostAuthorize` be used for read-only queries?** It can be valuable for restricting returned objects if the query causes no side effects and lazy loading is handled properly. For highly sensitive or large datasets, filtering at query time is better.

**Q7. Does a POST test receiving 403 prove `@PreAuthorize` denied it?** No. `CsrfFilter` could have returned 403 before the service ran. With CSRF enabled, send a valid token to test authorization.

**Q8. Why should tests avoid `@Transactional` when checking real commits?** It can make the test and service share a single transaction unlike a real request, deferring commits and hiding persisted mutations.

**Q9. Does a flushed transaction mean it committed?** No. Flush pushes SQL inside the transaction; rollback can still undo changes prior to commit.

**Q10. Does calling `this.securedMethod()` inside the same service run the method-security proxy?** With Spring proxy-based AOP, generally **no**. Route calls through a Spring bean/proxy or refactor entry points.

**Q11. What is needed if document permissions can change while a request is running?** Re-verify near mutation time, using transactions and concurrency mechanisms (optimistic locking, pessimistic locking, conditional `UPDATE`) appropriate to system requirements.

**Q12. If the database is unchanged after a denial, is the app definitely safe?** Not yet. Emails, messages, RPCs, or separate transactions might still have fired; verify all side effects.

## 17. Code review and release checklist

- [ ] `@EnableMethodSecurity` is enabled, and protected methods are genuinely intercepted by Spring proxies.
- [ ] Tests prove unauthorized callers do not execute mutations.
- [ ] Distinguish `@PreAuthorize` (before) from `@PostAuthorize` (after).
- [ ] Do not use `@PostAuthorize` as the primary guard for side-effecting methods.
- [ ] When checking owner/tenant, use server-side data and never trust client-supplied owners.
- [ ] Permission checks run **before** database updates, message publishing, emails, or remote calls.
- [ ] For concurrent state transitions, use appropriate locking/versioning/conditional `UPDATE`s.
- [ ] Understand actual advisor ordering between method security and `@Transactional` in your target version.
- [ ] Do not reorder annotations in source code and assume nesting changed.
- [ ] Do not blindly add `@EnableTransactionManagement(order=0)` without evaluating application-wide impact.
- [ ] Rollback rules do not unintentionally exclude access denials.
- [ ] Inspect whether `REQUIRES_NEW` propagation or nested transactions commit prior to denial.
- [ ] Avoid self-invocation, private methods, manually `new`-ed objects, or proxy bypasses that drop security advice.
- [ ] Never treat "403" as proof of transaction rollback; assert DB state from a fresh transaction.
- [ ] POST tests include a CSRF token when testing method security, alongside separate missing-token tests.
- [ ] Never sprinkle `@Transactional` onto tests in ways that mask real commit boundaries.
- [ ] Test ownership, tenant isolation, idempotency, and external side effects per your threat model.
- [ ] Emit audits/metrics distinguishing authorization denials, transaction rollbacks, and side-effect executions.
- [ ] Never log raw credentials, tokens, session cookies, sensitive payloads, or denied user data.

**Conclusion:** `@Transactional` and `@PreAuthorize`/`@PostAuthorize` are both **AOP advices** and do not automatically coordinate into "denied means definitely rolled back." Under common default advisor ordering, `@PostAuthorize` can run **after the transaction has already committed**. Use **`@PreAuthorize` and object checks before writing** as your primary gate, keep `@PostAuthorize` mainly for restricting **read results**, and verify safety with tests covering **HTTP + transactions + database state + side effects**, not just a 403 status.
