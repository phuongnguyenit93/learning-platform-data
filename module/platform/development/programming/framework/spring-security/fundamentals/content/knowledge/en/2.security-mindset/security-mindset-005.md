# Server-Side Authorization on Every Request and Sensitive Action

> **Principle:** Every time a user or system requests to **read, modify, export, or manage a resource**, the server must determine who the subject truly is and **whether that subject is permitted to perform that specific action on that specific object in its current state**. A hidden button in the UI, a guarded SPA route, or a client saying "I am admin" never replaces a server-side authorization decision.

This lesson belongs to the **Security Mindset** group of Spring Security. Illustrative examples target Spring MVC/Servlet applications using Java 17+ and Spring Security; the authorization design principles still apply to APIs, batch jobs, message consumers, and other protocols.

## 1. Expected Outcomes

After studying this lesson, you can:

1. Explain why **authentication** differs from **authorization**, and why checking roles only at the URL level is insufficient.
2. Design authorization policies for **every request** and individual operations such as viewing, editing, approving, exporting data, transitioning state, and changing others' permissions.
3. Place checks appropriately across request filters, services, and data access layers; handle objects owned by other users or tenants.
4. Use Spring Security's `SecurityFilterChain` and method security to enforce part of the policy.
5. Test both allowed and **must-deny** scenarios, including swapped IDs, swapped HTTP methods, missing CSRF tokens, repeated calls, or concurrent calls.

## 2. Why Frontend Checks Have No Value as a Security Boundary

Suppose the UI only renders an "Approve Invoice" button if `isManager === true`. Someone does not need to click that button: they can call `POST /api/invoices/42/approve` directly with curl, Postman, a script, or by modifying the request in DevTools. Similarly, a logged-in user can change `/documents/10` to `/documents/20`.

**Any data controlled by the client must never be treated as proof of authorization**, including:

- Resource IDs, `ownerId`, `tenantId`, `userId`, `role` parameters, `isAdmin` fields, permissions encoded in JSON, or IDs inside routes.
- Self-declared headers such as `X-User-Id`, `X-Tenant`, or `X-Role` if an Internet-facing path can set or alter those headers.
- The frontend hiding menus, disabling buttons, blocking navigation, or checking "logged in" in local storage.
- A token that looks like a JWT whose signature, issuer, audience, expiration, and token type have not yet been properly verified by the server per its trust contract.

The frontend still needs checks for good user experience and preventing accidental mistakes. However, **the server decides**, based on verified identity/claims, business policies, and trustworthy data state.

```text
Client                  Spring Security                 Domain/service
  | POST /documents/10/publish      |                            |
  |-------------------------------->|                            |
  |                                  | authenticate credential    |
  |                                  | authorize HTTP action      |
  |                                  |--------------------------->|
  |                                  |     check document owner   |
  |                                  |     check current state    |
  |                                  |     perform atomic update  |
  |                                  |<---------------------------|
  |<---------------------------------| result / reject            |
```

The decision must be repeated on **every request**; a previously allowed request does not create a "permanent pass" for subsequent requests. For still-valid sessions/credentials, permission info may be cached and vary by policy, yet the system must clearly define how permission revocation and token validity windows are handled.

## 3. Complete Policy: Who, Doing What, on What, Under Which Conditions?

The easiest model for business review is:

```text
Decision = allow(
  actor       = authenticated identity,
  action      = READ | EDIT | PUBLISH | EXPORT | DELETE | GRANT_PERMISSION,
  resource    = object and real owner/tenant in the system,
  context     = state, relationship, expiration, additional authentication requirement
)
```

| Component | Example | Trusted Source |
| --- | --- | --- |
| Actor | Alice, Bob, accounting staff | `Authentication` from security context, verified token |
| Action | `DOCUMENT_READ`, `DOCUMENT_PUBLISH` | The actual operation the endpoint/service executes |
| Resource | Document 10 with `owner=alice` | Database/repository, never raw owner from the request |
| Context | `status=DRAFT`, tenant, effective date | Data state and server policy |

Example permission matrix:

| Subject | Document | Action | Condition | Outcome |
| --- | --- | --- | --- | --- |
| Alice with `DOC_READ` | Alice's | READ | Document exists | Allow |
| Alice with `DOC_READ` | Bob's | READ | Different owner | Deny |
| Alice with `DOC_PUBLISH` | Alice's | PUBLISH | Currently `DRAFT` | Allow |
| Alice with `DOC_PUBLISH` | Alice's | PUBLISH | Already `PUBLISHED` | Deny due to state |
| Bob with only `DOC_READ` | Bob's | PUBLISH | Lacks publish permission | Deny |
| Anonymous | Any | READ/PUBLISH | Unauthenticated | Deny |

**Distinguish three permission levels:**

- **Function-level:** is this person allowed to invoke the publish operation?
- **Object-level:** is this person allowed to publish **document #10**?
- **Property/field-level:** is this person allowed to edit `ownerId`, `status`, `limit` fields or view columns containing secrets?

Checking only functions easily leads to **BFLA** (Broken Function Level Authorization) if admin endpoints are exposed; checking only login while ignoring owner/tenant leads to **BOLA/IDOR** (Broken Object Level Authorization). Binding a request body directly to an entity for updates can cause **mass assignment/overposting**; even when users may edit their own documents, they do not automatically have rights to edit `status` or `ownerId`.

## 4. Placing Authorization Checks Across Multiple Boundaries

### 4.1. HTTP Request: Filtering Callable Operations

Define paths and HTTP methods following **deny by default**: undeclared endpoints must be rejected, and newly introduced methods must be reviewed. Example:

```java
// Partial configuration illustration; full application class is in Section 6.
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/api/documents/*/publish")
            .hasAuthority("DOC_PUBLISH")
        .requestMatchers(HttpMethod.GET, "/api/documents/*")
            .hasAuthority("DOC_READ")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults()).build();
}
```

`authorizeHttpRequests` rules are evaluated **in order**; the first matching rule wins. Therefore, place narrow rules before broad ones. For an application with multiple `SecurityFilterChain` beans, verify both **which chain is selected** by `securityMatcher` and the rules inside each chain; avoid letting requests slip outside all chains. Path-specific rules must also account for dispatcher types, servlet paths, and endpoints outside Spring MVC (if any).

Spring Security provides `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `denyAll`, and custom `AuthorizationManager` implementations. Default roles like `hasRole("ADMIN")` match the `ROLE_ADMIN` authority; when using permissions like `DOC_PUBLISH`, `hasAuthority("DOC_PUBLISH")` is clearer.

**Limitation:** URL filters know path, method, authentication, and request metadata; they do not automatically know document 10 belongs to Alice and is currently `DRAFT`. Service/domain checks remain mandatory.

### 4.2. Service/Domain: Resource Permissions and State Transitions

Place rules right alongside critical business behavior so all callers undergo the policy, not just one controller:

- Before **reading**: does the resource exist? Can the actor view it within this tenant/owner? Does the response contain secret fields?
- Before **updating**: which resources can the actor edit? Which fields are editable? Does the change violate business invariants?
- Before **approving/publishing/refunding/deleting/granting permissions**: does the actor hold the specific permission for this action? Are state preconditions met? Is dual approval or re-authentication required?
- For **list/search/export**: filter directly in the query by user/tenant; do not protect only the detail endpoint. For batch operations, check **each item**, preventing one invalid ID from leaking other data exports.
- For **sensitive actions** like changing MFA, creating API keys, raising limits, or assigning roles: consider step-up authentication, maker-checker separation, rate limits, full auditing, and recovery procedures.

In Spring Security, `@EnableMethodSecurity` enables `@PreAuthorize` on methods. This is a useful barrier, though you must understand **proxy interception**: calls from another bean into a public method are generally checked; calling `this.publish(...)` from within the same bean can bypass the interceptor. Unannotated or non-proxied methods still need explicit policies in the architecture. Avoid placing checks solely in controllers when business logic is also invoked by message handlers, scheduled jobs, or internal flows.

### 4.3. Data Layer: Filter Properly by Owner/Tenant, Avoid Scattered Checks

A plain ID query like `findById(id)` is insufficient for private data. For user-owned documents, a scoped query is safer:

```java
// Illustrative Spring Data code; requires actual entity/repository to compile.
Optional<DocumentEntity> findByIdAndOwnerIdAndTenantId(
    Long id, Long ownerId, Long tenantId);
```

For state updates, consider a **conditional update inside a transaction** instead of "SELECT to check, wait briefly, then UPDATE":

```sql
-- Business logic illustration; table/column names must match real schema.
UPDATE document
SET status = 'PUBLISHED'
WHERE id = :id
  AND owner_id = :trustedActorId
  AND tenant_id = :trustedTenantId
  AND status = 'DRAFT';
```

Treat the operation as successful only if the updated row count equals **1**; 0 means nonexistent, wrong owner/tenant, or invalid state. If business logic must distinguish errors, do so without leaking out-of-scope data existence. For money transfers, inventory, concurrent approvals, or multi-table updates, use transactions, optimistic/pessimistic locks, idempotency, and appropriate execution limits; an authorization annotation alone does not solve race conditions.

## 5. Why "Every Request" Includes Multiple Entry Points

A system may expose the same business operation via:

- Web UI, REST endpoints, and mobile APIs.
- Export endpoints, file downloads, previews, reports, webhooks.
- Schedulers, queue consumers, asynchronous jobs, workflows, listeners, or admin commands.
- GraphQL mutations/resolvers, WebSocket messages, gRPC, service-to-service APIs.

An HTTP `SecurityFilterChain` controls only requests passing through that filter chain. It does **not** automatically apply the same URL rules to a message queue or an internally invoked service method. Each entry point must authenticate the caller and pass a trusted actor/service identity to the **same business policy**, while granting only least privilege to service accounts.

In particular, `GET /api/orders` might be checked properly, yet a newly added `GET /api/orders/export` endpoint could dump the entire table if filtered only by HTTP role. Data-emitting paths (downloads, exports, searches, logs, caches) are also resources needing authorization.

## 6. Runnable Spring Boot Example: Read Permission and Publish Permission

Let's build a small API with two documents: ID 10 belongs to Alice, ID 20 belongs to Bob. Alice can read/publish her own document; Bob only has permission to read his own document. A publisher must not transition someone else's document to `PUBLISHED`. Requests without a CSRF token are also rejected by default on POST.

The example uses **Java 17, Spring Boot 3.5.16 (Spring Security 6.x)** to demonstrate the APIs and testing approach. This is a frozen 3.x reference for the lesson; when starting a production project in 2026, use a supported Spring Boot line and apply current patches.

### 6.1. Structure

```text
authorize-every-action/
├── pom.xml
└── src/
    ├── main/java/demo/authorization/AuthorizationApplication.java
    └── test/java/demo/authorization/AuthorizationApplicationTests.java
```

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>authorize-every-action</artifactId>
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
```

### 6.2. Application and Policy

Create `src/main/java/demo/authorization/AuthorizationApplication.java`:

```java
package demo.authorization;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Allow container to render 404/409 errors via ERROR dispatch.
                // Does not open permissions for direct requests from clients.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.POST, "/api/documents/*/publish")
                    .hasAuthority("DOC_PUBLISH")
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAuthority("DOC_READ")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF remains enabled by default, including for POST in this example.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("DOC_READ", "DOC_PUBLISH")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-pass"))
                .authorities("DOC_READ")
                .build()
        );
    }
}

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable long id) {
        return service.read(id);
    }

    @PostMapping("/{id}/publish")
    DocumentView publish(@PathVariable long id) {
        return service.publish(id);
    }
}

@Service
class DocumentService {
    private final ConcurrentMap<Long, Document> documents =
        new ConcurrentHashMap<>(Map.of(
            10L, new Document(10L, "alice", "Alice draft", State.DRAFT),
            20L, new Document(20L, "bob", "Bob draft", State.DRAFT)
        ));

    @PreAuthorize("hasAuthority('DOC_READ')")
    public DocumentView read(long id) {
        return toView(ownedDocument(id));
    }

    @PreAuthorize("hasAuthority('DOC_PUBLISH')")
    public synchronized DocumentView publish(long id) {
        // In-memory demo: a single lock protects check + update.
        Document doc = ownedDocument(id);
        if (doc.state() != State.DRAFT) {
            throw new ResponseStatusException(HttpStatus.CONFLICT);
        }

        Document published = new Document(
            doc.id(), doc.owner(), doc.title(), State.PUBLISHED);
        documents.put(id, published);
        return toView(published);
    }

    private Document ownedDocument(long id) {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Document doc = documents.get(id);
        // Same response for "not found" and "not owned".
        if (doc == null || !doc.owner().equals(auth.getName())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return doc;
    }

    private static DocumentView toView(Document doc) {
        // Do not expose owner or internal entity by default.
        return new DocumentView(
            doc.id(), doc.title(), doc.state().name());
    }
}

enum State {
    DRAFT, PUBLISHED
}

record Document(long id, String owner, String title, State state) {}

record DocumentView(long id, String title, String status) {}
```

**Explanation of each boundary:**

1. **Request authorization:** URL and HTTP method must have matching permissions; all other paths hit `denyAll`. There is no case where `GET` being allowed implicitly allows `POST`.
2. **Method authorization:** `@PreAuthorize` preserves a check if service logic is called from another bean. `@EnableMethodSecurity` is required for the annotation to work in this config.
3. **Object authorization:** `ownedDocument(id)` compares the owner from the data store with the username in `SecurityContextHolder`; the server **never takes owner from request body/query**. Even with `DOC_PUBLISH`, Alice cannot publish Bob's document.
4. **State authorization:** having publish permission does not mean repeated publishing is allowed; only `DRAFT` transitions to `PUBLISHED`.
5. **Data minimization:** the response only contains `id/title/status`; never serialize the entire internal entity directly when it may hold internal data.
6. **Concurrency:** `synchronized` keeps the state check and update in one critical section **inside a single-JVM demo**. Real apps with multiple instances and a database must use transactions + conditional updates/locking; `synchronized` does not protect across nodes.
7. **CSRF:** because POST uses HTTP Basic where browsers can resend credentials automatically, the example keeps default Servlet CSRF protection. If deploying a true Bearer-token API that does not rely on auto-sent cookies/credentials, evaluate the threat model and configure appropriately; never use `csrf.disable()` out of habit.
8. **Sample accounts:** `InMemoryUserDetailsManager` and password `demo-pass` are for local testing only. Production needs a real identity system, HTTPS, password/MFA policies, and roles assigned from a trusted source.

A note on `404`: in this example, the response for "ID does not exist" and "not the owner" is identical to avoid leaking existence. In production, weigh `403`/`404` conventions, internal logging, and UX; what matters is leaking no data.

### 6.3. Testing Every Allowed and Denied Branch

Create `src/test/java/demo/authorization/AuthorizationApplicationTests.java`:

```java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationApplicationTests {

    @Autowired
    MockMvc mvc;

    private static RequestPostProcessor alice() {
        return user("alice").authorities(
            new SimpleGrantedAuthority("DOC_READ"),
            new SimpleGrantedAuthority("DOC_PUBLISH")
        );
    }

    private static RequestPostProcessor bob() {
        return user("bob").authorities(
            new SimpleGrantedAuthority("DOC_READ")
        );
    }

    @Test
    void everyRequestAndSensitiveActionIsChecked() throws Exception {
        // 1. Unauthenticated -> HTTP Basic returns 401.
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isUnauthorized());

        // 2. Alice reads the exact document she owns.
        mvc.perform(get("/api/documents/10").with(alice()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Alice draft"));

        // 3. Alice swaps ID to Bob's document -> denied.
        mvc.perform(get("/api/documents/20").with(alice()))
            .andExpect(status().isNotFound());

        // 4. Send POST without CSRF token -> 403.
        mvc.perform(post("/api/documents/10/publish").with(alice()))
            .andExpect(status().isForbidden());

        // 5. Bob owns 20 but lacks DOC_PUBLISH -> 403.
        mvc.perform(post("/api/documents/20/publish")
                .with(bob()).with(csrf()))
            .andExpect(status().isForbidden());

        // 6. Alice has publish permission but document 20 belongs to Bob -> 404.
        mvc.perform(post("/api/documents/20/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isNotFound());

        // 7. Alice publishes document 10 in DRAFT state -> 200.
        mvc.perform(post("/api/documents/10/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PUBLISHED"));

        // 8. Repeat same action in PUBLISHED state -> 409.
        mvc.perform(post("/api/documents/10/publish")
                .with(alice()).with(csrf()))
            .andExpect(status().isConflict());

        // 9. Undeclared path, even when logged in -> 403.
        mvc.perform(get("/api/unknown").with(alice()))
            .andExpect(status().isForbidden());
    }
}
```

In the project directory, run with **JDK 17+ and Maven 3.6.3+**:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` runs an integration test covering nine scenarios; when all satisfy the contract above, Maven reports a successful build. The lesson does not rely on guessing log counts or stdout output from the server.

When running the local server, `GET` with Basic Auth can be tested with:

```bash
curl -i http://localhost:8080/api/documents/10
curl -i -u alice:demo-pass http://localhost:8080/api/documents/10
curl -i -u alice:demo-pass http://localhost:8080/api/documents/20
```

For `POST`, do not bypass CSRF just to make curl "succeed easily"; use the `MockMvc` test with `csrf()` above. If you want to send POST via browser/curl, issue a token matching the session/CSRF configuration and send both the token and matching credentials. All Basic credentials in production must travel over HTTPS.

**Testing note:** `user(...)` in `spring-security-test` creates a mock principal for the request; it tests authorization, **not the real password/token authentication path**. Write separate tests for login, signatures, and token claims when production uses those mechanisms. With `ConcurrentHashMap` data, a single test executes state steps sequentially; production tests should have independent database fixtures between tests.

## 7. Preventing Bugs in Actions Even More Sensitive Than Publish

### 7.1. Approvals, Refunds, Transfers, Payments

These actions check not only roles but also **amount limits, state, owner/tenant, approver identity, and repetition limits**. Example refund approval policy:

- `REFUND_REQUEST` allows creating a refund request, scoped by order owner.
- `REFUND_APPROVE` allows approving within the assigned amount threshold and department.
- The requester must not self-approve if separation of duties is required.
- Inside a transaction, verify the order/payment is still eligible and transition state once.
- Use an idempotency key so retried requests do not refund twice.
- Audit who, when, what action, which object, and result; avoid logging full card numbers, passwords, or bearer tokens.

"Having approval permission" is only **one condition**. Rules like "pending approval," "not yet refunded," "no self-approval," and "within limit" must also be enforced by the server.

### 7.2. Role Assignment, Ownership Transfer, and Policy Changes

Never allow directly updating sensitive fields from a generic DTO like:

```json
{
  "displayName": "Alice",
  "role": "ADMIN",
  "ownerId": "bob",
  "tenantId": "finance"
}
```

If `PUT /users/me` accepts `UserEntity` directly and saves all fields, clients can attempt privilege escalation. Design direction:

- Define separate DTOs per task; `UpdateProfileRequest` contains only fields the user may edit.
- Create dedicated endpoints for changing roles, owners, limits, or policies; require specialized permissions, business conditions, auditing, and re-authentication when necessary.
- In the service, check the actor against the target and role hierarchy; never let a lower-privileged user grant higher privileges.
- Permissions and identity must come from verified server-side data; never trust submitted `role`, `isAdmin`, or `actorId` values.

### 7.3. Exports, Lists, and Background Tasks

An export endpoint may be functionally valid yet leak an entire table. Filter data directly in the query by owner/tenant/allowed scope, cap row counts and allowed columns, and control download link expiration. For asynchronous jobs, store the verified scope and decide when to re-check permissions (at enqueue time, execution time, and download time) per business requirements. Never blindly copy a browser's authentication into a background job without checking expiration and trust boundaries.

## 8. Common Mistakes When Designing Authorization

### Mistake 1 — Protecting Only the UI

**Symptom:** the admin menu is hidden, yet `POST /api/admin/users/1/role` is still reachable if someone knows the URL.

**Fix:** enforce server-side checks for endpoints and services; test requests directly without going through the frontend.

### Mistake 2 — Calling Only `authenticated()`

**Symptom:** Alice logs in and downloads Bob's document simply by changing the ID number.

**Fix:** check actor + action + resource; filter owner/tenant in the database and exclude out-of-scope data from responses.

### Mistake 3 — Checking Permissions Only at the Start of a Flow

**Symptom:** permissions were revoked, yet previously issued download links or delayed jobs keep using the old privileges forever.

**Fix:** define policies for session/token TTL, revocation, short-lived grants, and re-check points before sensitive tasks. Never assume an earlier UI verification step authorizes all subsequent steps.

### Mistake 4 — Giving Every HTTP Method the Same Permission

**Symptom:** `GET /api/documents/10` is allowed, so `POST /api/documents/10/publish` or `DELETE /api/documents/10` also slips through an overly broad wildcard.

**Fix:** authorize per specific HTTP method and path/action; place narrow matchers first and `denyAll` for unknown paths. Never use GET to perform state changes.

### Mistake 5 — Relying on Service Checks That Bypass the Proxy

**Symptom:** `@PreAuthorize` is on the method, yet code in the same bean calls `this.method()`, or the annotation was added while forgetting `@EnableMethodSecurity`.

**Fix:** place policies at service boundaries called from other beans and test real method interception; for business invariants, verify directly where data is updated. Never treat annotations as an automatic safety net for every invocation.

### Mistake 6 — Reading Permissions from Unverified Input

**Symptom:** the backend trusts `X-User-Id` or `role=ADMIN` on Internet requests, or trusts JWTs without verifying all claims/signatures.

**Fix:** obtain the actor solely from trusted authentication; explicitly configure claim mapping and proxy/header trust boundaries. Never let the frontend decide the actor.

### Mistake 7 — Check-Then-Act Race Conditions

**Symptom:** two requests both observe `status=PENDING`, and both approve or both refund.

**Fix:** bind checks to transactions and atomic/conditional updates; use optimistic or row locks when needed, and ensure idempotency at the write source. Authorization can be correct while state handling still fails if checks are separated from writes.

### Mistake 8 — Returning an HTTP Denial After Causing Side Effects

**Symptom:** the service performs an update or publishes a message and only then calls `@PostAuthorize` to decide if it was allowed.

**Fix:** decide permissions and preconditions **before executing side effects**. `@PostAuthorize` can fit certain data-reading cases but should not be the sole gate for already-executed mutations.

### Mistake 9 — Inconsistency in Multi-Tenant Systems

**Symptom:** the detail screen filters by tenant, while list, export, cache, search index, or background consumers do not.

**Fix:** policy and tenant scope must be consistent across all access paths and cache keys; test cross-tenant access with identical or guessable IDs.

## 9. Recommended Test Suite Before Release

| Scenario | What Must Be Proven |
| --- | --- |
| Anonymous calls private endpoint | Rejected / appropriately challenged for auth |
| User with right permission and owner | Allowed and returns only permitted data |
| User with right role but different owner/tenant | No access, no unauthorized existence confirmation |
| User is owner but lacks action permission | Cannot publish/delete/export/grant permissions |
| Switch `GET` to `POST`/`DELETE` | Does not inherit read permission |
| Send forged `role`/`ownerId`, mass assignment | No privilege escalation or ownership transfer |
| Repeat request after state transition | Does not execute action a second time against policy |
| Two concurrent requests | No duplicate processing or invariant violation |
| Missing/invalid CSRF token when CSRF applies | Rejected before mutation |
| Expired token, wrong issuer/audience | Not authenticated, not authorized |
| Revoked permission | Meets revocation and cache SLA/policy |
| Non-HTTP paths: job/queue/service call | Still subject to policy at the proper boundary |
| Multi-tenant export/list/download | Leaks no out-of-scope records or fields |
| Undeclared new route | Blocked by deny-by-default |
| Error occurred | Logs no secrets/PII and causes no side effects before deny |

Use Spring Security Test + MockMvc for request authorization; test method authorization through real beans/proxies; use datasets with at least two subjects and two tenants for owner/tenant checks; use a real database or production-like environment for concurrency/transactions. For sensitive decisions, testing **DENY** branches usually catches more critical bugs than testing only the happy path.

## 10. Checklist for Every New Endpoint

Before merging code for an endpoint or mutation, self-check:

1. **Who is calling?** Is authentication derived from verified credentials or self-declared client headers/bodies?
2. **What action?** How does GET/list/detail differ from EDIT/PUBLISH/DELETE/EXPORT/GRANT_PERMISSION?
3. **On which data?** Where do owner, tenant, ACL, project scope, and current state come from?
4. **Where is it checked?** Do URL, service, query/update transaction, background worker, and file download share the same policy?
5. **What about concurrency/retries?** Are checks and updates atomic, with idempotency limits and appropriate auditing?
6. **What is the default when policy is missing?** Is a new request denied or let through?
7. **Are there negative tests?** Are there at least anonymous, wrong role, wrong object, wrong tenant, invalid state, wrong HTTP method, and token/CSRF cases?

For high-risk operations (refunds, MFA changes, granting permissions, locking accounts, deleting data), add limit checks, re-authentication, dual approval, least-privilege admin access, and detection/recovery capabilities.

## 11. Key Takeaways

- **Every request must be authenticated and authorized according to its own policy.** Public requests must be marked public intentionally.
- **Every sensitive action must be checked where it executes:** sufficient permissions, right owner/tenant, right state, and business conditions.
- **Never trust clients when they declare their own privileges.** Rely only on server-verified identity/claims and trustworthy resource data.
- **Permission to call an endpoint does not mean ownership of the object.** HTTP, service/domain, and data-scoping layers must reinforce each other.
- **Deny by default + least privilege + negative testing** form a practical triad to prevent data leaks and unauthorized execution.

## References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP API Security Top 10 — 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
