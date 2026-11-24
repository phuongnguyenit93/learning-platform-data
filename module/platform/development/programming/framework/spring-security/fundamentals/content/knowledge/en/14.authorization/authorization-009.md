# HTTP, Method, and Data Authorization Complement One Another

> **Scope:** Spring Security fundamentals → Authorization. This lesson explains how to combine three control levels: **HTTP/request → business method → permissions on specific data**. Each layer addresses different risks and must remain consistent with a single business policy.

## 1. Why Is One Authorization Layer Not Enough?

A document management API has endpoint `GET /api/documents/42`. Suppose the system authenticates Alice and Alice has the `DOC_READ` permission. That is **not enough** to conclude Alice may read document 42: the document might belong to Bob or another tenant.

Three separate questions must be answered:

1. **HTTP:** Is the caller allowed to enter this group of endpoints? For example, `/api/**` requires login, and administrative routes require admin privileges.
2. **Business method:** Is this identity allowed to perform the *action* “read document”, “approve order”, or “refund payment”, even when invoked from another controller, a job, or a message listener?
3. **Data:** Among records of the same type, **which records, in which tenant, in which state** may this user act upon, and which fields may they view or edit?

Someone with general permission to read documents still does not have permission to read **every document**. Likewise, a repository filtering records by owner does not replace the rule “only someone with approval permission may approve”. Layers must complement one another, stay consistent, and be tested together.

### Example Decision Matrix

| Request | HTTP | Method | Data | Desired outcome |
|---|---|---|---|---|
| Anonymous GET private document | Blocked as unauthenticated | Never enters business logic | Not queried | 401 with the HTTP Basic configuration in the example |
| Alice, has `DOC_READ`, reads Alice's document | Allowed | Read action allowed | Record belongs to tenant and Alice | 200 |
| Alice, has `DOC_READ`, reads Bob's document | Allowed | Read action allowed | Not within scope | 404 per the example policy |
| Logged-in user lacking `DOC_READ` | Allowed | Denied | Query does not run | 403 |
| User with `DOC_READ` attempts POST to edit data | Blocked by HTTP or method rule respectively | No edit permission granted | No update executed | 403 or 405 depending on declared endpoints |

**Note:** 401, 403, and 404 depend on the authentication mechanism/entry point, route mapping, and policies avoiding resource existence disclosure. With form login, unauthenticated users may be redirected instead of receiving 401. Never promise one status code across every Spring Security configuration.

## 2. Processing Path and Responsibilities of Each Layer

```text
Client / token / session
        |
        v
[HTTP security filter chain]
  - Authenticate credentials
  - Request matcher, method, path, dispatcher type
  - Access policy by URL group
        |
        v
[Controller / handler]
  - Validate input format
  - Delegate to use case/service
        |
        v
[Method security at service]
  - Permission to perform business action
  - State rules or context-dependent policies
        |
        v
[Data authorization in query / domain]
  - tenant_id, owner, membership, ACL, status
  - Which data fields may be read/edited
        |
        v
[Repository/DB] → permitted DTO → HTTP response
```

Not every application needs 100% expressions at every layer. For public endpoints, HTTP can use `permitAll`; for a protected operation, sufficient checks are normally needed at the right places. What matters is that **each rule has a clear owner** and no call path accidentally bypasses it.

| Layer | Familiar tools in Servlet Spring Security | Limitations to understand |
|---|---|---|
| HTTP | `SecurityFilterChain`, `HttpSecurity`, `authorizeHttpRequests`, `requestMatchers`, `AuthorizationManager` | Sees request/path/method, does not automatically know who record 42 belongs to |
| Method | `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, or authorization service | Applies only when invocations actually pass through the interceptor/proxy |
| Data/object | Queries with scope predicates; permission service; ACL; DB RLS; projection DTOs | Must be applied across **every** read/list/update/delete/export/stream, not just get-by-id |

**Combined rule:** An operation executes only if all relevant checks permit it. Typically you need **authenticate → authorize action → authorize resource → execute → return scoped data**. Never rely on a UI check or an HTTP role check while skipping ownership checks.

## 3. HTTP Authorization: Guarding the Front Gate

### 3.1. Declaring Explicit Route Policies

With Spring MVC/Servlet, Spring Security plugs into the Servlet filter chain via `FilterChainProxy` and `SecurityFilterChain` beans. You can use `requestMatchers` with HTTP methods/paths to describe request groups.

Conceptually standalone configuration snippet, **not a complete application**:

```java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .authenticated()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Key imports: `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `HttpMethod`. Not a complete Java class. `GET /api/documents/42` requires an authenticated identity, after which **the service must still check `DOC_READ`** and data must still belong to the caller's scope. `hasRole("ADMIN")` checks authority `ROLE_ADMIN` under the default prefix; `hasAuthority("DOC_READ")` checks the exact authority `DOC_READ`. Do not confuse roles with permissions.

### 3.2. Matcher and Filter Chain Mistakes

- Matchers are evaluated in registration order: a broad rule placed earlier can swallow narrow rules. For instance, `/api/**` = `permitAll` before `/api/admin/**` is a severe bug.
- `anyRequest().authenticated()` checks login only; it does not grant access to all resources. `anyRequest().denyAll()` helps reject paths without an intentional policy.
- With multiple `SecurityFilterChain` beans, `securityMatcher` decides which chain handles a request; only the **first matching chain** is used. If no chain matches, the request may go unprotected by Spring Security. Verify `@Order`, matchers, and fallbacks.
- Distinguish URL-level protection from method-level protection. If another path calls the same service, an HTTP matcher on the first controller does not protect that other path.
- `ERROR`/`FORWARD` dispatches can alter error statuses if all dispatch types are blocked. Configure appropriately for your app; never overly broaden permissions on business endpoints.
- Never rely on hiding UI buttons, CORS, or API gateway authentication alone instead of service authorization.

### 3.3. Authentication, 401/403, CSRF

Authentication answers “who is calling?”. Authorization answers “what is this person allowed to do with this resource?”. With Basic or bearer resource servers, anonymous callers usually get 401; logged-in users lacking permissions usually get 403. Some data policies return 404 for out-of-scope records to avoid leaking metadata, though this must be consistent and status changes are never a sole security measure.

CSRF is a separate risk from authorization: when browsers **automatically attach** cookies/sessions (or automatic credential mechanisms), a malicious site can cause the browser to send state-changing requests. With REST APIs using only bearer headers explicitly sent by the application, CSRF analysis can differ. **Never disable CSRF just because “the API has a token”**; inspect how credentials are actually sent. Use `GET` only for safe operations that do not mutate state.

## 4. Method Authorization: Protecting Use Cases

HTTP guards protect entry points; method security protects **business capabilities** regardless of which controller invokes the service. On Spring Security 6 for the imperative model:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

On a `@Service` bean:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public DocumentDto readDocument(long id) {
    return repository.load(id);
}

@PreAuthorize("hasAuthority('DOC_APPROVE')")
public void approveDocument(long id) {
    // Check state + resource scope before mutating
}
```

The snippets above illustrate annotation placement; `DocumentDto`, `repository`, and method bodies are project components, **not a standalone runnable class**. `@EnableMethodSecurity` must be enabled. By default it supports `@PreAuthorize`/`@PostAuthorize`; other annotations have separate activation options depending on kind.

**Place them on services with business meaning**, such as `approveInvoice`, `refundPayment`, `inviteMember`. Controllers can change, whereas the rule for “who may approve” belongs with the use case and is reused across web, message consumers, and tasks with an appropriate principal. Do not duplicate an expression unnecessarily across 20 controllers and forget to update one.

### 4.1. When to Use `@PreAuthorize` vs `@PostAuthorize`?

- `@PreAuthorize` checks **before** invoking the method. Use it for action permissions, trusted input conditions, and calling policy beans like `@documentPolicy.canEdit(#id, authentication)`.
- `@PostAuthorize` evaluates the return value **after** the method runs. It is useful for certain read operations, yet cannot undo side effects already caused, does not automatically roll back transactions in all cases, and may have loaded out-of-scope data into memory.
- `@PreFilter` / `@PostFilter` can filter collections, yet are not the default choice for millions of records: filtering after loading can leak counts, break pagination, and hurt performance and caching. For large lists, constrain scope directly in the DB query.

Policy bean example, illustrative snippet:

```java
@PreAuthorize("@documentPolicy.canEdit(#documentId, authentication)")
public void renameDocument(long documentId, String newTitle) {
    repository.rename(documentId, newTitle);
}
```

`documentPolicy` is a Spring bean with a real permission-checking method; parameter names in expressions must be resolvable by Spring Security, using `@P("documentId")` or compiler parameter-name retention if needed. Even with a correct pre-check, update operations should still include scope conditions in SQL to reduce the window where permissions change between check and write.

### 4.2. Method Security Pitfalls

Proxy-based method security typically applies when **calls pass through a Spring-managed proxy**. One method in the same class calling a `@PreAuthorize`-annotated method via `this.method()` can bypass the interceptor. Objects instantiated manually with `new`, private/non-proxyable methods, or misconfigured proxies can also skip advice. Never trust an annotation just because the code compiles; write integration tests calling through the real bean.

In addition, protecting methods called by jobs/consumers requires defining a clear **service identity** and permissions. Never assume HTTP authentication remains present on worker, scheduler, or message-listener threads.

## 5. Data Authorization: Preventing IDOR/BOLA and Cross-Tenant Access

IDOR (Insecure Direct Object Reference) or Broken Object Level Authorization happens when a caller swaps a resource ID in the URL/body and receives a record they have no right to. For example, Alice can read document 1, yet changes `/api/documents/1` to `/api/documents/2` to read Bob's document. Both requests are authenticated and Alice may hold `DOC_READ`; the vulnerability lies in **object-level authorization**.

### 5.1. Enforcing Scope Directly in the Query

**Unsafe:**

```sql
SELECT id, title
FROM documents
WHERE id = ?;
```

Checking `hasAuthority("DOC_READ")` afterward is insufficient. When the system requires tenant + owner, predicates must include both:

```sql
SELECT id, title
FROM documents
WHERE id = ?
  AND tenant_id = ?
  AND owner_username = ?;
```

`?` placeholders must be bound via prepared statements/JDBC templates, never string-concatenated into SQL. `tenant_id` and `owner_username` come from the **system-authenticated identity/membership**, never blindly trusting an `X-Tenant-Id` header, `?tenant=T2` query parameter, or client-sent owner. If users are allowed to pick a tenant, the backend must verify they actually belong to that tenant before using it.

When the query finds no document in scope, returning 404 (even if the record exists out of scope) avoids confirming someone else's ID exists. Switching 403 to 404 does not replace DB conditions and must also consider audit/UX requirements.

### 5.2. Lists, Counts, Search, Exports, and Updates

Scope must be applied **consistently across every data path**:

- `GET /documents/{id}`: look up record matching `id + tenant + owner/ACL`.
- `GET /documents`: filter scope in SQL **before** `ORDER BY`, `LIMIT/OFFSET`; `count` must also count only visible records.
- Search, CSV export, batch read, and cache: share the same scope; avoid export files or cache keys omitting `tenant_id`/caller.
- `PATCH/DELETE`: in addition to action permissions, constrain scope **inside the write statement itself** and check affected rows, avoiding a race window between check and update.
- Return DTOs with only permitted fields; being allowed to read a document does not implicitly grant access to secrets, internal flags, or others' identifying data.

Example conditional update SQL:

```sql
UPDATE documents
SET title = ?
WHERE id = ?
  AND tenant_id = ?
  AND owner_username = ?;
```

If 0 rows are updated, the ID either does not exist or is out of scope; decide the response and audit per the business contract. If an extra condition like “edit only documents in DRAFT state” is required, add `AND status = 'DRAFT'` or appropriate concurrency control/locking in the same transaction. **Checking and writing in two separate statements does not always guarantee atomicity.**

### 5.3. Permission Relationships Beyond Ownership

Ownership is only one model. Applications may need group memberships, tenant roles, relationship-based access (ReBAC), attribute-based access (ABAC), access control lists (ACLs), document state, delegated permissions, and time-based policies. Place reusable logic in a domain authorization service and push matching predicates down to queries. Balance readability, performance, explainability of denials, and auditing.

With PostgreSQL, Row-Level Security (RLS) can be considered as an extra DB layer. RLS must be configured with trusted session/transaction identity, accurate policies, and connection pooling that cannot leak context. RLS does not excuse skipping action-level checks in services or hiding sensitive fields.

## 6. End-to-End Example: HTTP + Method + Data Protecting One API

This example creates **one Spring Boot 3.x, Java 17+ application** using Servlet MVC, Spring Security 6, JDBC, and in-memory H2. The goal is not production architecture, but running a transparent scenario verifying all three layers. Demo accounts use `{noop}` passwords for learning **in local environments only**, never in real systems.

Data and permissions:

| User | Server-determined tenant | Authorities | Owned records |
|---|---|---|---|
| `alice` | `T1` | `DOC_READ` | 1, 3 |
| `bob` | `T2` | `DOC_READ` | 2 |
| `visitor` | No tenant | `DASHBOARD_READ` | None |

### 6.1. Dependencies

From Spring Initializr, generate a **Gradle Spring Boot 3.x, Java 17+** project, then ensure `build.gradle` contains these dependencies (this snippet is only the **dependencies block** of a Boot project, not the entire build file):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Use only the Web MVC starter in this example; do not add `spring-boot-starter-webflux`. By default Spring Boot runs `schema.sql`/`data.sql` against embedded H2.

### 6.2. Creating Sample Tables

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_username VARCHAR(80) NOT NULL,
    title VARCHAR(200) NOT NULL
);

CREATE INDEX idx_documents_scope
    ON documents (tenant_id, owner_username, id);
```

File `src/main/resources/data.sql`:

```sql
INSERT INTO documents (id, tenant_id, owner_username, title)
VALUES
    (1, 'T1', 'alice', 'Alice private'),
    (2, 'T2', 'bob',   'Bob private'),
    (3, 'T1', 'alice', 'Alice notes');
```

### 6.3. Complete Java Code

Place in **one file** `src/main/java/example/authz/AuthorizationApplication.java`. In real projects, split configuration, controller, service, repository, and policy into separate files/packages; they are combined here so the sample is easy to run.

```java
package example.authz;

import jakarta.servlet.DispatcherType;
import java.util.List;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // ERROR dispatch does not accidentally turn app errors into 403.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .authorities("DOC_READ")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}demo123")
            .authorities("DOC_READ")
            .build();
        UserDetails visitor = User.withUsername("visitor")
            .password("{noop}demo123")
            .authorities("DASHBOARD_READ")
            .build();
        return new InMemoryUserDetailsManager(alice, bob, visitor);
    }
}

record DocumentView(long id, String title) {}

@RestController
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    ResponseEntity<DocumentView> getDocument(
            @PathVariable long id, Authentication authentication) {
        return service.findOneForCaller(id, authentication)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}

@Service
class DocumentService {
    private final DocumentRepository repository;
    private final TenantDirectory tenantDirectory;

    DocumentService(DocumentRepository repository,
                    TenantDirectory tenantDirectory) {
        this.repository = repository;
        this.tenantDirectory = tenantDirectory;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Optional<DocumentView> findOneForCaller(
            long id, Authentication authentication) {
        String caller = authentication.getName();
        String tenant = tenantDirectory.requiredTenant(caller);
        return repository.findVisible(id, tenant, caller);
    }
}

@Component
class TenantDirectory {
    String requiredTenant(String username) {
        // Simulates server-managed membership.
        return switch (username) {
            case "alice" -> "T1";
            case "bob" -> "T2";
            default -> throw new AccessDeniedException(
                "Caller has no tenant membership");
        };
    }
}

@Repository
class DocumentRepository {
    private final JdbcTemplate jdbc;

    DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    Optional<DocumentView> findVisible(long id, String tenant,
                                       String caller) {
        List<DocumentView> rows = jdbc.query(
            """
            SELECT id, title
            FROM documents
            WHERE id = ? AND tenant_id = ? AND owner_username = ?
            """,
            (rs, rowNum) -> new DocumentView(
                rs.getLong("id"), rs.getString("title")),
            id, tenant, caller);
        return rows.stream().findFirst();
    }
}
```

Explanation of each defense line:

1. **HTTP:** only `/public/ping` is public; `GET /api/documents/*` requires authentication; remaining undeclared routes get `denyAll`.
2. **Method:** `DocumentService.findOneForCaller` requires the `DOC_READ` authority. `visitor` logs in successfully yet is denied before touching the DB.
3. **Data:** `TenantDirectory` resolves tenant from the server-authenticated identity; SQL restricts `id + tenant + owner`. Alice holding `DOC_READ` still cannot view Bob's data.
4. **Output:** DTO `DocumentView` returns only `id` and `title`; tenant/owner are not leaked unintentionally. DTOs filter fields—they do not replace query scoping.

In real products, replace the hardcoded `TenantDirectory` with verified membership/claims data supporting multi-tenancy/hierarchies; replace demo users/passwords with real authentication, proper password hashing, TLS, and credential management. Never take tenant from an unverified header.

### 6.4. Run and Verify Results

Run inside the project directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. By default the service runs at `http://localhost:8080` unless configured otherwise. Test with:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/1
curl -i -u visitor:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/1
curl -i -u alice:demo123 http://localhost:8080/api/documents/2
curl -i -u bob:demo123 http://localhost:8080/api/documents/2
```

| Request | Expected HTTP | Why |
|---|---:|---|
| Public ping | 200, body `ok` | HTTP `permitAll` |
| Anonymous GET document 1 | 401 | HTTP requires login, Basic entry point |
| Visitor GET document 1 | 403 | Passes HTTP, denied by `@PreAuthorize` |
| Alice GET document 1 | 200, JSON `{"id":1,"title":"Alice private"}` | Sufficient permission + matching tenant + owner |
| Alice GET document 2 | 404 | Has `DOC_READ`, but SQL scope hides Bob's document |
| Bob GET document 2 | 200, JSON `{"id":2,"title":"Bob private"}` | Sufficient permission + matching scope |

A high-value test scenario is **swapping the ID** of another user's document in an authenticated request. With HTTP+method checks alone, Alice→ID2 would slip through. With proper query scoping, it returns empty.

### 6.5. Integration Test Verifying All Three Layers

Create `src/test/java/example/authz/AuthorizationLayersTest.java`:

```java
package example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationLayersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void httpMethodAndDataScopeWorkTogether() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("visitor", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice private"));

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Bob private"));
    }
}
```

Run `./gradlew test` (Windows: `gradlew.bat test`). This is an **integration test using a real Spring context and security filters**, unlike unit tests that mock the service and merely assert controller mapping. Assumptions to keep: Spring Boot 3.x with matching dependency versions and H2 loading `schema.sql`/`data.sql` at startup. If a real application has multiple datasources, migration tools, or custom SQL initialization, adjust test fixtures accordingly.

## 7. Leave No “Gaps” Between the Three Layers

### 7.1. Object Access and Multi-Tenancy

Suppose tenants T1 and T2 share a table. Role `ROLE_MANAGER` only says “manager”, **not** which tenant they manage. Resolve tenant membership/permissions in the service and bind the tenant into read/write queries. A tenant-selection header is **untrusted input** until the user↔tenant relationship is verified.

A common design:

```text
Authenticated principal
  -> validated tenant membership (server-side)
  -> action permission for that tenant
  -> object relationship/status constraints
  -> scoped SELECT / UPDATE / DELETE
  -> field-filtered DTO
```

Cross-tenant admin privileges may exist, but must be declared with explicit policies, audits, and tests. **Never turn every admin into an unintended bypass of all business rules.**

### 7.2. Where to Authenticate, Where to Authorize?

In a bearer JWT resource server, Security validates the token per issuer, signature, expiry, and audience policies where appropriate; then converts scopes/roles into authorities. Never use client-entered usernames or tenants instead of verified claims/membership. A valid token only proves trusted claims per configuration; it does not mean any arbitrary resource ID is valid.

In the service, use a structured authorizer for complex rules instead of overly long SpEL expressions. For example, `canApprove(user, invoice)` can check role, tenant, non-self-approval, and pending state. The repository must use conditional updates or transactions/locking to guarantee state does not change between check and commit.

### 7.3. Field-Level Authorization

A user permitted to view an order may see `id, status, total` while being barred from `cardToken, internalNotes`. Scoped queries are necessary but insufficient: add projections/DTOs/serializer policies matching sensitivity levels. Avoid returning full JPA entities expecting the frontend to hide fields.

For mutations, never bind full request JSON directly into an entity containing `ownerId`, `tenantId`, or `approved` that a client could tamper with. Create an allowlist of updatable fields, take owner/tenant from the server-side security context, and govern transitions with business rules.

### 7.4. Caches, Background Jobs, and Message Consumers

Cache keys for scoped data should include the necessary scope identifiers (tenant, user, or permission scope) and a version when permissions change; data cached by Alice must never be served to Bob just because `documentId` matches. Background jobs and consumers must have a service principal, explicit permissions, or verified business context; never assume `SecurityContextHolder` automatically propagates across async threads/tasks.

### 7.5. 403, 404, and Information Disclosure

Some systems prefer 403 when a user lacks permission on a known object; others prefer 404 to limit object enumeration. Both are product/security choices depending on the contract. What is mandatory is never returning out-of-scope content, nor leaking via lists/counts/exports, latency/error details, or misdirected audit logs. Record full internal audits while sending only appropriate error details to clients.

## 8. Servlet and WebFlux Differ in Tools, Not Principles

This lesson uses Spring MVC for illustration. With WebFlux, the three-layer model still applies, though security integration differs:

| Aspect | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| HTTP | `SecurityFilterChain`, `HttpSecurity`, `authorizeHttpRequests` | `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange` |
| Method | `@EnableMethodSecurity` with imperative methods | `@EnableReactiveMethodSecurity` with suitable reactive methods |
| Context | `SecurityContextHolder`, typically thread-bound | `ReactiveSecurityContextHolder` on Reactor Context |
| Data | Imperative scoped JDBC/JPA queries/transactions | R2DBC/reactive repositories with reactive scope and transactions |
| Test | `MockMvc`, `spring-security-test` | `WebTestClient`, reactive security test helpers |

Illustrative WebFlux snippet (**not a runnable class**):

```java
@Bean
SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/documents/**").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

In a reactive service, obtain the context properly via the Reactor Context, verify actions using reactive method security/policies, and perform non-blocking queries with tenant/owner predicates—conceptually `repository.findByIdAndTenantIdAndOwnerUsername(id, tenant, username)` returning `Mono`. Never call blocking JPA on the event loop, never pull identity from an arbitrary `ThreadLocal`, and never call `block()` to dodge reactive structure.

## 9. Common Misconceptions and Vulnerabilities

| Practice / assumption | Problem | How to handle |
|---|---|---|
| “`authenticated()` at HTTP is enough.” | Any logged-in user can probe anyone's IDs. | Add action authorization and object/tenant scope. |
| “Having `ROLE_ADMIN` opens all tenants.” | Roles do not express tenant boundaries. | Explicit cross-tenant policies, tests/audits. |
| “`@PreAuthorize` on the controller is enough.” | Jobs, listeners, or other controllers still call the service. | Put rules on the service/use case; test all call paths. |
| “Having the annotation guarantees it runs.” | Self-invocation or non-proxied methods can skip the interceptor. | Spring-managed beans, external invocation, integration tests. |
| “`@PostFilter` handles all lists.” | Loads entire DB into RAM, breaks pagination/counts, risks leaks. | Scope in SQL/queries. |
| “Querying by ID is fine because IDs are hard to guess.” | IDs can leak or be guessed; missing object authorization. | Always query in scope or check trusted ACLs. |
| “Take tenant from a request header.” | Users change the header to access other tenants. | Verify membership and bind the validated tenant. |
| “Check role then UPDATE by ID.” | Row-level updates can cross scope or hit races. | UPDATE with scope/status predicates; check row count. |
| “Returning a DTO protects the object.” | DTOs only restrict fields, not who receives the record. | Data scope first, DTO second. |
| “Hiding the menu locks the feature.” | Hand-crafted HTTP requests still call the API. | Enforce on server across HTTP + service + data. |
| “Testing HTTP 200 is enough.” | Misses unauthorized, cross-tenant, or under-privileged cases. | Negative tests across all three layers. |
| “Cache auth by document ID.” | May serve Alice's data to Bob. | Cache by scope; invalidate when membership changes. |

## 10. Designing an Authorization Test Suite Before Deployment

For each use case, build a matrix of **actor × action × resource scope × state × entry point**. For example, “view document” includes actors anonymous, visitor, alice, bob; resources own, same tenant but not own, other tenant, deleted; entry points HTTP, direct service call, export/list.

Essential tests:

1. **Authentication:** anonymous callers and bad credentials cannot enter private resources; verify the right entry point for Basic/form/bearer.
2. **HTTP:** routes outside policy are denied; broad/narrow matchers and multiple filter chains never open unintended URLs; disallowed HTTP verbs cannot bypass rules.
3. **Method:** authenticated user lacking `DOC_READ` gets 403; invoke methods via real Spring beans, testing self-invocation if the design carries that risk; business role/state rules work.
4. **Object & tenant:** Alice cannot read/edit Bob's document even knowing its ID; a user with the same role in another tenant cannot access it; list/count/export queries share the same scope.
5. **Writes:** updates affect only valid rows; 0 affected rows are handled properly; clients cannot modify owner/tenant/approved; test races/transactions for sensitive workflows.
6. **Fields:** responses never expose secret/private fields; logs/error payloads never reveal out-of-scope records.
7. **Async/caching:** no principal/tenant leaks across threads, schedulers, reactor contexts, or caches; role/membership changes take effect properly.
8. **Browser:** POST/PUT/PATCH/DELETE with cookies/sessions have proper CSRF protection; test authorized requests succeeding with valid CSRF tokens and unauthorized requests failing.
9. **Failure modes:** DB timeouts, retries, exceptions, and concurrency never bypass authorization or turn responses into leaks.

For policy-heavy systems, centralize logic in an **independently testable permission service/authorization manager**, and add integration tests covering HTTP→service→DB and negative cases. Controller unit tests that mock the service only verify mapping/responses; they **do not prove** method interceptors or SQL scoping actually run.

## 11. Endpoint Review Checklist Before Release

- [ ] Enumerate actors, action permissions, tenant/owner/ACL scope, states, and visible fields.
- [ ] HTTP matchers cover exact URL/verb, order, and filter chain; unintended endpoints are denied.
- [ ] Controller never treats client-declared data as verified identity or tenant.
- [ ] Service/use case is protected by method security or suitable policy; not bypassed by self-invocation.
- [ ] Read/list/count/export queries are properly scoped **before** pagination and before building responses.
- [ ] UPDATE/DELETE include scope + business state predicates; affected rows/transactions are handled consistently.
- [ ] DTO/serialization emits only permitted fields; cache keys include scope.
- [ ] Negative tests exist: anonymous, missing permission, different owner, different tenant, invalid verb.
- [ ] CSRF/session/token, 401/403/404, auditing, and async context propagation are reviewed.
- [ ] Any admin/cross-tenant or out-of-scope service account privileges are explicitly documented, never implicit bypasses.
- [ ] Clear policy ownership exists whenever a new endpoint/service/consumer is introduced.

**Conclusion:** HTTP authorization decides **who can enter the route**, method authorization decides **who can execute the business action**, and data authorization decides **which records and fields that action applies to**. Using all three within their proper scopes, sharing trusted policies, scoping queries, and testing denied cases substantially reduces IDOR/BOLA, cross-tenant breaches, and use-case bypasses.

## 12. Official References

- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matchers, rule order, `AuthorizationManager`, filter chains.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, proxies/interceptors.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): sessions/cookies, state-changing operations, protection options.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context and reactive method authorization.
- [Spring Security — Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain` and `ServerHttpSecurity`.
- [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction context and data operation guards.

**When applying:** Cross-check documentation for your application's exact Spring Boot/Spring Security version; the fixed samples use Boot 3.x / Security 6 and local accounts, not a default production configuration.
