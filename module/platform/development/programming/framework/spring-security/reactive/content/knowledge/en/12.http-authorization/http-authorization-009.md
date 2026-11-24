# Resource Ownership Authorization and Preventing IDOR

## 1. The Core Problem: Being Allowed to Call an API Does Not Mean Accessing Every Resource

In Spring Security reactive/WebFlux, an authenticated request can pass `authenticated()` or `hasRole("USER")` and still lack permission to read, modify, or delete a specific record. A common mistake is a controller accepting a client-sent ID, calling `repository.findById(id)`, and returning data without checking the **owner** or a valid sharing grant.

**IDOR (Insecure Direct Object Reference)** occurs when a client swaps a resource ID and accesses another user's data or operations because object-level authorization is missing. In OWASP API Security, the corresponding issue is typically called **BOLA (Broken Object Level Authorization)**.

~~~text
GET /api/docs/doc-101 + Alice authenticated ──► 200: Alice's document
GET /api/docs/doc-102 + Alice authenticated ──► 200: Bob's document
                                           ↑ IDOR VULNERABILITY
The app only asks "Is Alice logged in / has ROLE_USER?"
without asking "Does Alice have permission on doc-102?".
~~~

With proper authorization, the second request must **not be allowed to read Bob's document**, even though Alice is permitted to call the same endpoint type to read her own document. Depending on product policy, the response can be 403 or 404; in this lesson, the example chooses 404 for documents the user cannot view to limit disclosing resource existence.

### Learning Objectives

1. Distinguish authentication, URL access permissions, and object-level authorization.
2. Explain why random IDs, `hasRole`, and `hasAuthority` alone are insufficient against IDOR.
3. Obtain actor/tenant from a trusted `SecurityContext` rather than trusting `ownerId`/`tenantId` from paths, queries, headers, or JSON.
4. Protect GET, LIST, SEARCH, PUT/PATCH/DELETE, and child resources, even when a user swaps IDs.
5. Enforce owner/tenant conditions directly inside data queries and within the same UPDATE statement to avoid TOCTOU.
6. Design HTTP 401/403/404 flows, support/admin scopes, and sharing permissions.
7. Build a complete Java 17+ Spring Boot WebFlux example with unit/integration tests using `WebTestClient`.

## 2. Three Decision Layers That Must Not Be Confused

~~~text
HTTP GET /api/docs/doc-102
           │
           ▼
Spring Security: Authentication
  Alice verified password/token? ── No ─► 401 / entry point
           │ Yes
           ▼
HTTP Authorization (authorizeExchange)
  GET /api/docs/* has "doc:read"? ───── No ─► 403
           │ Yes
           ▼
DocumentService / Repository
  doc-102 belongs to the same tenant?
  Alice is owner / has share grant / explicit override?
        │ Yes                        │ No
        ▼                             ▼
  Safe data DTO                  404 or 403
        │
       200
~~~

| Layer | Question | Common API | Limitation |
| --- | --- | --- | --- |
| Authentication | Who is sending the request? | `ReactiveAuthenticationManager`, `Authentication`, `SecurityContext` | Does not know who owns a document |
| HTTP authorization | Can the user use this feature? | `authorizeExchange`, `hasRole`, `hasAuthority` | Does not look up each record's `ownerId` automatically |
| Resource authorization | Does the user have permission on this exact ID? | Service policy, repository predicates, ACLs | Must be enforced on every data access path |
| Database enforcement | Can data be filtered/written by owner+tenant directly in DB? | Conditional SQL, RLS, reactive repositories | Requires trusted actor/tenant |
| Response shaping | Which fields are safe to expose? | DTO allowlists | Does not replace permission checks |

For example, Alice and Bob both have `ROLE_USER` and `doc:read`. If you only use `hasRole("USER")`, both pass the HTTP rule; nothing in that rule checks `doc-102.ownerId == Bob.id`. Resource-level checks must be added.

### 2.1. Role, Permission, Owner, and Tenant

- **Role:** responsibility group, e.g., `ROLE_USER`, `ROLE_SUPPORT`.
- **Permission:** operational capability, e.g., `doc:read`, `doc:write`, `doc:read:any`.
- **Owner:** identifier of the account that owns the record.
- **Tenant:** organizational/customer isolation boundary in multi-tenant applications.
- **Share grant / ACL:** permission shared by the owner or an authorized administrator with another user, with clear action scopes and expiration.

A `hasAuthority("doc:read")` rule does not automatically grant access to all documents. Even `doc:read:any` must be scoped by tenant, organizational boundary, purpose, and policy auditing—never implying system-wide access.

## 3. Forms of IDOR/BOLA to Recognize

### 3.1. Path Variable

~~~http
GET /api/docs/doc-102 HTTP/1.1
Authorization: Basic <Alices-credentials>
~~~

The ID is client-chosen data. If the controller returns `findById("doc-102")` without filtering owner/tenant, Bob's document is exposed. Prior login checks do not solve this.

### 3.2. Query Strings and List Filters

~~~text
GET /api/docs?ownerId=u-200
GET /api/orders?customerId=999
GET /api/reports?tenantId=t-other
~~~

When an endpoint means "mine", the owner must be derived from server-side identity. Client query parameters are merely **selection preferences**, not proof of permission. Search/list endpoints must apply ACLs **before** calculating counts, sorting, paginating, and streaming data; filtering on the frontend or after pagination is insufficient.

### 3.3. JSON Body and Mass Assignment

~~~json
{
  "documentId": "doc-102",
  "ownerId": "u-100",
  "tenantId": "t-1",
  "title": "Change ownership"
}
~~~

Clients can spoof owner/tenant if the backend binds JSON directly onto an entity and saves all fields. For a rename API, the DTO should contain only editable fields:

~~~java
public record RenameRequest(String title) {}
~~~

Permission checks rely on verified identity and current repository data, **never on an `ownerId` self-declared by the client**.

### 3.4. Upload, Download, Attachments, Exports, Batch, GraphQL

- `GET /docs/{docId}/files/{fileId}` must verify the file belongs to a document the user may view, not merely that `fileId` exists.
- `GET /exports/{jobId}` must verify job ownership and object storage keys, not just unguessable links.
- `POST /docs/batch` must authorize every ID in the batch, avoiding "one permitted ID" validating the whole list.
- GraphQL resolvers fetching `node(id)` must also perform object-level checks, not only authorize the root operation.
- WebSockets/SSE and background jobs must enforce policies appropriate when streaming/emitting data, never treating past HTTP authentication as permanent permission.

### 3.5. UUIDs Do Not Replace Authorization

Hard-to-guess UUIDs/ULIDs hinder sequential ID guessing, yet IDs can still leak via email, share links, logs, referrers, other APIs, or bugs. An attacker who knows a valid UUID must still be denied if unauthorized. Never rely on ID secrecy as your sole access control.

## 4. Obtaining a Trusted Actor from Reactive SecurityContext

In Spring WebFlux, security flows through the subscription's **Reactor Context**:

~~~java
Mono<Authentication> authenticatedActor =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Here:
- `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`.
- `Authentication.getName()` may return username, subject, or identifier depending on the login mechanism.
- `Authentication.getPrincipal()` may be `UserDetails`, `Jwt`, or a custom principal.
- `getAuthorities()` returns permissions granted by a trusted manager/identity provider, never arbitrary roles sent by clients.

**Never** extract `ownerId` from `X-User-Id`, a `userId` parameter, or JSON body and treat it as identity. In large applications, keep an **immutable accountId** and **verified tenantId** in the principal/claims or backend directory. Usernames/emails/displayNames can change and should not serve as permanent security keys by default.

In the demo project, Spring Security creates `UserDetails` and the backend maps the **authenticated** username to account ID/tenant from a trusted store. This model is concise for learning; multi-realm/mutable-username products should use principals containing immutable IDs.

Never use Servlet-style ThreadLocal `SecurityContextHolder` assuming it works across all reactive branches. Never call `block()` or manually `subscribe()` to check permissions inside a WebFlux handler.

## 5. Concrete Policy: Alice, Bob, Carol, and Support

Demo dataset design:

| User | Account ID | Tenant | Authorities |
| --- | --- | --- | --- |
| Alice | `u-100` | `t-1` | `ROLE_USER`, `doc:read`, `doc:write` |
| Bob | `u-200` | `t-1` | `ROLE_USER`, `doc:read`, `doc:write` |
| Carol | `u-300` | `t-2` | `ROLE_USER`, `doc:read`, `doc:write` |
| Support | `u-900` | `t-1` | `ROLE_SUPPORT`, `doc:read`, `doc:read:any` |

Documents:

| ID | Tenant | Owner | Initial Title |
| --- | --- | --- | --- |
| `doc-101` | `t-1` | Alice | Alice private plan |
| `doc-102` | `t-1` | Bob | Bob private plan |
| `doc-201` | `t-2` | Carol | Carol private plan |

Rules:

- **GET by ID:** has `doc:read` at HTTP, document matches tenant, and (actor is owner **or** actor holds `doc:read:any` in that tenant).
- **LIST:** same read conditions, filtering **every document**; never return all documents and rely on the client to hide them.
- **PUT rename:** has `doc:write` at HTTP, document matches tenant **and actor itself is the owner**. Support, despite broad read access, cannot write.
- **Unknown ID / unauthorized view:** both return 404 per demo policy.
- **Anonymous:** 401 with HTTP Basic; authenticated user missing operation permission: 403.
- **Wrong tenant:** denied even for users carrying support permissions.

Expected matrix:

| Request | Result |
| --- | --- |
| Alice GET `doc-101` | 200 |
| Alice GET `doc-102` | 404 |
| Bob GET `doc-102` | 200 |
| Alice GET `doc-201` | 404 |
| Support GET `doc-102` | 200 |
| Support GET `doc-201` | 404 |
| Alice PUT `doc-101` (valid CSRF) | 200 |
| Alice PUT `doc-102` (valid CSRF) | 404 |
| Support PUT `doc-102` (valid CSRF) | 403 |
| Anonymous GET `doc-101` | 401 |

Support overrides stay confined within the same tenant, never serving as a shortcut to view every customer. Real applications with private data require proper approval workflows and auditing for such permissions.

## 6. HTTP Authorization via `authorizeExchange`

Typical route-level configuration:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/docs", "/api/docs/*")
            .hasAuthority("doc:read")
        .pathMatchers(HttpMethod.PUT, "/api/docs/*")
            .hasAuthority("doc:write")
        .anyExchange().denyAll()
    )
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

**This is an excerpt**, not a standalone Java file. The project in Section 8 includes all dependencies/imports/beans.

In Spring Security:
1. Filters authenticate the user and build a trusted `Authentication`.
2. `AuthorizationWebFilter` applies `authorizeExchange` rules in order.
3. Document GET requires `doc:read`; PUT requires `doc:write`.
4. Passing the HTTP layer **does not** guarantee the ID belongs to the user. Controller/service/repository must enforce resource ownership.
5. `anyExchange().denyAll()` prevents newly added routes missing policies from opening accidentally.

**Distinction:** `hasRole("USER")` checks `ROLE_USER` by default, while `hasAuthority("doc:read")` checks the exact string `doc:read`. Both check coarse authorities without querying records.

### 6.1. Can Ownership Be Checked Directly in an HTTP Rule?

Yes. A `ReactiveAuthorizationManager<AuthorizationContext>` passed to `.access(...)` can use `Mono<Authentication>` and the request context, where `AuthorizationContext.getVariables()` provides extracted URI matcher variables.

Example **API illustration, not part of the runnable project**:

~~~java
ReactiveAuthorizationManager<AuthorizationContext> ownerManager =
    (authentication, context) -> {
        Object rawId = context.getVariables().get("id");
        if (!(rawId instanceof String documentId)) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .flatMap(auth ->
                trustedAccounts.findByUsername(auth.getName()))
            .flatMap(actor ->
                documentRepository.existsByIdAndTenantIdAndOwnerId(
                    documentId, actor.tenantId(), actor.id()))
            .map(AuthorizationDecision::new)
            .defaultIfEmpty(new AuthorizationDecision(false));
    };

// Example corresponding rule:
.pathMatchers(HttpMethod.GET, "/api/docs/{id}")
    .access(ownerManager)
~~~

Methods `trustedAccounts.findByUsername(...)` and `documentRepository.existsByIdAndTenantIdAndOwnerId(...)` are **hypothetical application-defined APIs**. This illustrates Spring Security 6.3's reactive contract, where `check(Mono<Authentication>, AuthorizationContext)` returns `Mono<AuthorizationDecision>`; it is not a standalone application.

**Practical considerations:**
- The illustrative manager allows only owners and **does not** handle Support permissions; applying it to the demo would alter the policy. Extend it according to approved grants/tenants.
- An access denial in the filter for an authenticated user normally returns **403**, differing from the 404 policy in the resource service; unify your contract.
- Checking at HTTP and then running `findById`/`UPDATE ... WHERE id` downstream can still leak data if the service is called elsewhere or under a TOCTOU race.
- Therefore, for data operations, **owner/tenant predicates inside queries and write statements** remain the strongest defense.

### 6.2. Does Reactive Method Security Help?

You can use `@EnableReactiveMethodSecurity` and `@PreAuthorize`/custom authorizers in business services to protect across multiple ingresses (REST, GraphQL, message jobs). Still, `@PreAuthorize("hasAuthority('doc:read')")` does not check ownership by itself. When calling a reactive repository inside an authorizer, use proper reactive methods instead of `block()` inside SpEL. Test both method security and repository constraints.

## 7. Protecting Data at Query Time and Update Time

### 7.1. Fetching by ID Alone Is Insufficient

**Risky pattern:**

~~~java
Mono<Document> find(String id) {
    return repository.findById(id);
}
~~~

Returning the result directly to any logged-in user causes IDOR.

**Scoped query pattern:**

~~~java
Mono<Document> findOwned(
        String id, String tenantId, String ownerId) {

    return repository.findByIdAndTenantIdAndOwnerId(
        id, tenantId, ownerId);
}
~~~

The repository method name in the example is **application-defined**, not a built-in method on every `ReactiveCrudRepository`. The point is that the database query filters simultaneously by ID, tenant, and owner. For shared data, add valid ACL/grant conditions rather than dropping the tenant filter.

For LIST/SEARCH, enforce permissions inside the SQL/search query **before count/pagination**. Never load an entire table and filter in Java (leaks metadata, poor performance, wrong page counts).

### 7.2. Preventing TOCTOU: Check Ownership and Write in the Same Operation

A dangerous sequence:

~~~text
T1: SELECT doc-101 → owner Alice
T2: Backend transfers owner from Alice to Bob
T3: UPDATE doc-101 SET title = ... using only WHERE id = doc-101
    → Alice can still overwrite after losing permission.
~~~

This is a **time-of-check to time-of-use** race. A proper update statement for private documents must constrain owner+tenant at write time:

~~~sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedAccountId
  AND version = :expectedVersion;
~~~

- `rowsUpdated = 1`: success.
- `rowsUpdated = 0`: nonexistent, unauthorized, or version changed; handle safely per contract (404 / 409 / 412 when distinguishing safely).
- Never run an ID-only UPDATE after checking ownership in a separate SELECT.
- Apply similar conditions to DELETE. For nested files/subresources, verify parent relationships.
- Never infer write permission from a read share grant.

A SQL statement combining permission predicates, optimistic locking, and an appropriate transaction provides far stronger protection than checking in a controller before an unconstrained write.

### 7.3. 403 or 404 When Unauthorized on a Record?

- **403 Forbidden**: caller is authenticated but forbidden from performing the action; suitable when the caller is allowed to know the resource exists.
- **404 Not Found**: used for both nonexistent resources and resources the caller may not view, reducing ID enumeration.
- **401 Unauthorized**: no valid authentication yet (in the HTTP Basic demo).

The demo chooses 404 in the service to hide personal documents and 403 in the filter for missing functional permissions. Keep error messages/headers consistent and avoid bodies revealing "document belongs to Bob". Note 404 does not completely eliminate timing or log side channels, so monitoring and enumeration controls remain necessary.

## 8. Complete Java 17+ Project: Protecting GET/LIST/PUT Documents

The demo uses **Spring Boot 3.3.13**, Gradle 8.x, Spring Security WebFlux, and JDK 17+. Versions are pinned for API illustration, not as a production recommendation for an unsupported Boot release.

Data lives in RAM so the code runs standalone without an external database; production should use R2DBC, owner+tenant queries, and conditional updates.

### 8.1. Structure and Gradle

~~~text
webflux-idor-defense/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── IdorDefenseApplication.java
    │   ├── DemoStore.java
    │   ├── SecurityConfig.java
    │   └── DocumentController.java
    └── test/java/demo/
        └── OwnershipTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-idor-defense'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add `spring-boot-starter-web` in this example: Spring WebFlux uses `ServerHttpSecurity`/`WebFilter`, not `HttpSecurity`/Servlet `Filter`.

### 8.2. Entry Class

`src/main/java/demo/IdorDefenseApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdorDefenseApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdorDefenseApplication.class, args);
    }
}
~~~

### 8.3. Store: Trusted Accounts and Filtered Operations

`src/main/java/demo/DemoStore.java`:

~~~java
package demo;

import java.util.Comparator;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class DemoStore {

    record Account(
        String id,
        String tenantId,
        String username,
        String passwordHash,
        Set<String> authorities
    ) {}

    // Internal stored entity, DO NOT serialize directly to HTTP.
    record StoredDocument(
        String id,
        String tenantId,
        String ownerId,
        String title,
        long version
    ) {}

    private final Map<String, Account> accountsByUsername;
    private final ConcurrentHashMap<String, StoredDocument> documents =
        new ConcurrentHashMap<>();

    DemoStore(PasswordEncoder encoder) {
        Account alice = new Account(
            "u-100", "t-1", "alice",
            encoder.encode("alice-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account bob = new Account(
            "u-200", "t-1", "bob",
            encoder.encode("bob-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account carol = new Account(
            "u-300", "t-2", "carol",
            encoder.encode("carol-pass"),
            Set.of("ROLE_USER", "doc:read", "doc:write")
        );
        Account support = new Account(
            "u-900", "t-1", "support",
            encoder.encode("support-pass"),
            Set.of("ROLE_SUPPORT", "doc:read", "doc:read:any")
        );

        accountsByUsername = Map.of(
            alice.username(), alice,
            bob.username(), bob,
            carol.username(), carol,
            support.username(), support
        );

        documents.put("doc-101", new StoredDocument(
            "doc-101", "t-1", "u-100", "Alice private plan", 1));
        documents.put("doc-102", new StoredDocument(
            "doc-102", "t-1", "u-200", "Bob private plan", 1));
        documents.put("doc-201", new StoredDocument(
            "doc-201", "t-2", "u-300", "Carol private plan", 1));
    }

    Mono<Account> findAccountByUsername(String username) {
        return Mono.justOrEmpty(accountsByUsername.get(username));
    }

    private boolean sameTenant(
            StoredDocument doc, Account caller) {
        return doc.tenantId().equals(caller.tenantId());
    }

    private boolean mayRead(
            StoredDocument doc, Account caller) {
        return sameTenant(doc, caller)
            && (doc.ownerId().equals(caller.id())
                || caller.authorities().contains("doc:read:any"));
    }

    private boolean mayWrite(
            StoredDocument doc, Account caller) {
        return sameTenant(doc, caller)
            && doc.ownerId().equals(caller.id());
    }

    Mono<StoredDocument> findReadable(
            String id, Account caller) {
        return Mono.justOrEmpty(documents.get(id))
            .filter(doc -> mayRead(doc, caller));
    }

    Flux<StoredDocument> listReadable(Account caller) {
        return Flux.fromIterable(documents.values())
            .filter(doc -> mayRead(doc, caller))
            .sort(Comparator.comparing(StoredDocument::id));
    }

    Mono<StoredDocument> renameOwned(
            String id, Account caller, String newTitle) {

        return Mono.defer(() -> {
            AtomicReference<StoredDocument> updated =
                new AtomicReference<>();

            // Atomic for ONE key in JVM Map:
            // ownership check and update happen inside the same computeIfPresent.
            documents.computeIfPresent(id, (key, original) -> {
                if (!mayWrite(original, caller)) {
                    return original;
                }

                StoredDocument changed = new StoredDocument(
                    original.id(), original.tenantId(),
                    original.ownerId(), newTitle, original.version() + 1);

                updated.set(changed);
                return changed;
            });

            return Mono.justOrEmpty(updated.get());
        });
    }
}
~~~

Analysis:
- `Account.id` and `tenantId` are assigned by the backend; clients cannot choose or override them.
- `findReadable` returns `Mono.empty()` when the document does not exist **or** permission is insufficient; the caller cannot tell why.
- `listReadable` applies the same policy to LIST. In production, translate this predicate into a SQL/search filter to avoid loading the entire dataset.
- `mayRead` allows tenant `t-1` Support to read Bob's document, but not Carol's tenant `t-2` document.
- `mayWrite` **does not** allow Support to update on someone's behalf; only the owner in the same tenant may do so.
- `renameOwned` checks owner and updates **atomically inside `ConcurrentHashMap.computeIfPresent`** for a single key. When moving to a DB, use a conditional UPDATE checking row count, optionally adding version/transaction.
- `AtomicReference` exists only locally per subscription to extract the result from the map lambda; it is not shared cross-request state.
- `StoredDocument` is an internal entity holding owner/tenant, not a response DTO.

The in-memory store is illustrative, not a production/cluster solution, and does not persist state across restarts.

### 8.4. Spring Security: Authorizing Operations by URL

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(DemoStore store) {
        return username -> store.findAccountByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash())
                .authorities(account.authorities().toArray(String[]::new))
                .build());
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/docs", "/api/docs/*")
                    .hasAuthority("doc:read")
                .pathMatchers(HttpMethod.PUT, "/api/docs/*")
                    .hasAuthority("doc:write")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // KEEP CSRF ENABLED: PUT requires a valid token.
            .build();
    }
}
~~~

- Passwords in `DemoStore` are BCrypt-hashed, and `UserDetailsRepositoryReactiveAuthenticationManager` verifies raw passwords using `PasswordEncoder`.
- Authorities are managed by the backend, never read directly from the request.
- `httpBasic` is for the simple demo running locally over HTTP; production requires HTTPS and an appropriate authentication solution.
- GET requires `doc:read`, PUT requires `doc:write`; `anyExchange().denyAll()` blocks other routes.
- CSRF protection stays enabled by default because browsers can send Basic/cookie credentials automatically. PUT tests must supply a CSRF token. Do not disable CSRF simply for HTTP Basic without assessing risks.
- HTTP authorization **does not know** the `ownerId` in the database; `DemoStore` enforces object-level checks.

### 8.5. Controller: Never Allow Clients to Write ownerId or tenantId

`src/main/java/demo/DocumentController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class DocumentController {

    public record DocumentView(
        String id, String title, long version) {}

    public record RenameRequest(String title) {}

    private final DemoStore store;

    DocumentController(DemoStore store) {
        this.store = store;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/docs")
    Flux<DocumentView> list() {
        return currentAccount()
            .flatMapMany(store::listReadable)
            .map(this::toView);
    }

    @GetMapping("/api/docs/{id}")
    Mono<DocumentView> get(@PathVariable String id) {
        return currentAccount()
            .flatMap(actor -> store.findReadable(id, actor))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)))
            .map(this::toView);
    }

    @PutMapping("/api/docs/{id}")
    Mono<DocumentView> rename(
            @PathVariable String id,
            @RequestBody Mono<RenameRequest> input) {

        return input
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.BAD_REQUEST)))
            .flatMap(command -> {
                if (command.title() == null
                    || command.title().isBlank()
                    || command.title().length() > 100) {

                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid title"));
                }

                return currentAccount()
                    .flatMap(actor -> store.renameOwned(
                        id, actor, command.title().trim()))
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                    .map(this::toView);
            });
    }

    private Mono<DemoStore.Account> currentAccount() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .flatMap(this::loadTrustedAccount)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
    }

    private Mono<DemoStore.Account> loadTrustedAccount(
            Authentication authentication) {
        return store.findAccountByUsername(authentication.getName());
    }

    private DocumentView toView(DemoStore.StoredDocument doc) {
        return new DocumentView(
            doc.id(), doc.title(), doc.version());
    }
}
~~~

Key protections:
1. `id` in the URL only identifies the target object to read/modify, never serving as proof of permission.
2. `currentAccount()` extracts authentication from the Reactor Context and maps it to a trusted account. There are no `ownerId`/`tenantId` parameters in the controller.
3. GET/LIST/PUT call owner/tenant-constrained operations on `DemoStore`, never returning `findById` directly.
4. The update request contains only `title`; internal entities are never mass-bound from JSON. Blank and >100-character inputs are rejected.
5. `DocumentView` contains only `id`, `title`, and `version`; it never returns `ownerId`, `tenantId`, or `passwordHash`.
6. Unauthorized and nonexistent records both return `NOT_FOUND` in the object service.
7. The code preserves `Mono`/`Flux` pipelines without calling `block()` or `subscribe()`.

In real deployments, obtain the immutable account ID directly from the verified identity (or a realm-scoped trusted account directory) and execute conditional R2DBC queries. The controller must never be the sole line of defense if the service is invoked via queues, scheduled jobs, or GraphQL.

## 9. Running with curl: Changing IDs Cannot Escalate Permissions

From the project directory, requires JDK 17+ and compatible Gradle:

~~~bash
gradle bootRun
~~~

Or use `./gradlew bootRun` (Unix/macOS) / `gradlew.bat bootRun` (Windows) if a wrapper is present.

In bash/Git Bash:

~~~bash
# Anonymous: 401.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-101

# Alice owns doc-101: 200.
curl -s -u alice:alice-pass \
  http://localhost:8080/api/docs/doc-101

# Alice guesses Bob's doc-102 ID: 404.
curl -s -u alice:alice-pass -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-102

# Bob reads Bob's document: 200.
curl -s -u bob:bob-pass \
  http://localhost:8080/api/docs/doc-102

# Support t-1 reads Bob's document: 200.
curl -s -u support:support-pass \
  http://localhost:8080/api/docs/doc-102

# Support t-1 cannot read Carol's t-2 document: 404.
curl -s -u support:support-pass -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/docs/doc-201

# Alice only lists documents within her permitted scope.
curl -s -u alice:alice-pass \
  http://localhost:8080/api/docs
~~~

GET `doc-101` response before editing:

~~~json
{
  "id": "doc-101",
  "title": "Alice private plan",
  "version": 1
}
~~~

Alice's LIST response:

~~~json
[
  {
    "id": "doc-101",
    "title": "Alice private plan",
    "version": 1
  }
]
~~~

Warning: `curl -u` in examples is only for local use; over the Internet HTTPS is mandatory and secrets must never be stored in logs/scripts. On PowerShell, use `curl.exe` and replace `/dev/null` with `NUL`.

### 9.1. PUT Without CSRF May Return 403 Before Checking Owner

A `curl -X PUT` without a CSRF token is usually rejected by `CsrfWebFilter` because the demo keeps CSRF enabled by default. This is **not** proof that object-level authorization works: tests must send a valid token so requests reach functional permission and ownership checks.

Never disable CSRF globally in browser systems using cookie/Basic credentials. Pure Bearer-token apps with different credential transport need their own CSRF risk evaluation. The next section uses `WebTestClient.mutateWith(csrf())` in test scope to simulate a valid token without disabling production CSRF.

## 10. Integration Testing with `WebTestClient`

`src/test/java/demo/OwnershipTests.java`:

~~~java
package demo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OwnershipTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousCannotReadProtectedDocument() {
        client.get().uri("/api/docs/doc-101")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadOwnDocumentButNotInternalOwnerFields() {
        client.get().uri("/api/docs/doc-101")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-101")
            .jsonPath("$.ownerId").doesNotExist()
            .jsonPath("$.tenantId").doesNotExist();
    }

    @Test
    void aliceCannotReadBobsDocumentByChangingId() {
        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isNotFound();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-102");
    }

    @Test
    void supportReadOverrideNeverCrossesTenant() {
        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/docs/doc-201")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void listContainsOnlyReadableDocuments() {
        client.get().uri("/api/docs")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("doc-101")
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void ownerMayRenameWithValidCsrf() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-101")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Alice updated"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Alice updated");
    }

    @Test
    void aliceCannotRenameBobsDocumentEvenWithDocWrite() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Illegal takeover"))
            .exchange()
            .expectStatus().isNotFound();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Bob private plan");
    }

    @Test
    void supportCannotWriteBecausePermissionIsMissing() {
        client.mutateWith(csrf()).put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("support", "support-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Not allowed"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingCsrfCannotModifyDocument() {
        client.put().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "No csrf"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/docs/doc-102")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Bob private plan");
    }
}
~~~

The tests cover **nine** scenarios: anonymous 401, owner 200, cross-ID 404, tenant-bounded Support override, scoped list, owner PUT 200, PUT on Bob's document despite `doc:write` returning 404, Support lacking write 403, and PUT missing CSRF 403 without modifying data.

**Important:** do not assert only HTTP status on denied updates; re-read the document under the owner's account to confirm the data was not modified. The test editing `doc-101` does not affect assertions on `doc-102`, so this does not depend on test execution order. With database tests, isolate fixtures/transactions per test.

Run:

~~~bash
gradle test
~~~

Or use the corresponding wrapper if present. Tests are designed to run on the WebFlux context, though actual outcomes must be verified by compiling/running in your project environment rather than treating Gradle stdout as a fixed string.

## 11. Scenarios a Single Authorization Layer Easily Misses

### 11.1. List, Search, and Pagination

If GET by ID checks owner yet `GET /api/docs?page=0` returns every document, the API still has BOLA. Permission conditions must reside in the data query **before count, sort, limit, and offset**. Caching total counts or facet/search filters can also disclose the existence of other documents.

### 11.2. Nested Objects and File Downloads

`GET /api/docs/{docId}/attachments/{fileId}` must verify that the file genuinely belongs to an authorized `docId` in the same tenant. Pre-signed object storage URLs have TTLs but do not check ownership on issuance; issue URLs only after authorizing the file, and account for expiration, sharing, and revocation.

### 11.3. Multi-Tenant and Support/Admin

`ROLE_ADMIN` in tenant A does not automatically grant access to tenant B. Never read the active tenant from a client-sent header without verifying membership/roles in that tenant. Support/override permissions should specify tenant scope, action, expiry, purpose, and auditing.

### 11.4. Caching/CDN/ETag

Never place private documents in a public CDN cache keyed solely by URL. Consider `Cache-Control: private, no-store` for sensitive data or caches partitioned by principal/tenant/policy. Remember 304/ETag, error bodies, and CDN rules can also leak data/metadata.

### 11.5. Background Jobs and Permission Revocation Timing

A request might authorize an export at 10:00, while the worker exports the file at 10:20 after permission was revoked. Define policies for when permissions are checked, time-limited delegations, cancellation, and auditing. Never push raw session cookies/passwords/tokens onto queues.

### 11.6. ID Enumeration and Side Channels

Use consistent 404s to reduce resource existence leaks, yet also maintain:
- Rate limiting and alerts on high volumes of invalid IDs.
- Avoiding messages like "belongs to Bob" in public bodies/logs.
- Watching for differences in latency, headers, body sizes, and metadata.
- Checking URL-encoded ID variants, aliases, nested resources, sort/search, and secondary APIs.
- Never substituting rate limits or random IDs for object-level authorization.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| `authenticated()` as the sole condition | Any logged-in user reads any ID | Check owner/tenant/grant per object |
| Using `hasRole("USER")` without checking ID | Broad role does not protect private data | Add object-level authorization |
| Trusting `ownerId`/`tenantId` in JSON | Client spoofs or transfers ownership | Take identity from trusted authentication |
| Returning `findById(id)` directly | IDOR on GET | Query with owner+tenant or ACL |
| Checking owner then `UPDATE WHERE id` | TOCTOU when owner changes | Conditional UPDATE with owner/tenant/version |
| Filtering lists only on the frontend | Backend already leaked data | Filter in database/service before response |
| Hiding IDs with UUIDs alone | Exploitable once ID leaks | UUIDs only assist; always check permissions |
| Assuming SUPPORT accesses every tenant | Cross-tenant data leak | Explicitly scope tenant and action, with audit |
| Checking owner in controller while service is public | GraphQL/queue bypass | Protect service/repository |
| Deserializing JSON into entity with owner | Mass assignment | DTO with only editable fields |
| Returning entity with sensitive metadata | Leaks owner, tenant, state | Response DTO allowlist |
| 403/404 bodies revealing denial reason | Leaks valid IDs and owners | Consistent error policy |
| Using `block()` inside WebFlux authorizer | Blocks event loop | Reactive pipeline, R2DBC |
| Calling `subscribe()` to check permissions | Response may leave before check completes | Compose with `flatMap` |
| Removing CSRF just to make demo PUT run easily | Forged browser requests | Keep CSRF matching credential model |
| Testing only cross-tenant, skipping same-tenant users | Misses horizontal IDOR | Test Alice ↔ Bob with same `ROLE_USER` |
| Checking only 404 status, skipping DB check after write | Data may still have been mutated | Assert data remained unchanged |
| Caching personal documents without user partitioning | Cross-user leak from CDN/cache | `no-store`/`private` or policy-aware cache |

## 13. Check Questions

1. **What is IDOR?** A user accesses/manipulates an unauthorized object by swapping ID references when the backend lacks object-level authorization.
2. **How does BOLA differ?** OWASP's term emphasizing broken authorization at the object level; IDOR is the direct-ID exploitation pattern.
3. **Alice has `doc:read`; can she read Bob's doc?** No. Functional permission does not satisfy ownership/tenant conditions.
4. **Does `hasRole("USER")` automatically check `ownerId`?** No; it checks role authority.
5. **Can UUIDs replace authorization?** No. IDs can leak.
6. **Where do `ownerId`/`tenantId` come from?** Verified identity and backend records, never trusting client body/query/headers.
7. **Why filter LIST at the data source?** Avoids leaking records/counts and wrong pagination counts.
8. **Why use conditional UPDATE?** Guarantees permission still holds at write time, preventing TOCTOU.
9. **What does `rowsUpdated=0` mean?** Either nonexistent, unauthorized, or version changed; handle safely per contract.
10. **Can tenant `t-1` Support read Carol's `t-2` doc?** No, even with `doc:read:any` in tenant `t-1`.
11. **Does READ permission automatically grant WRITE?** No; each action needs its own policy.
12. **403 or 404 for unauthorized documents?** Depends on policy; 404 commonly reduces existence disclosure for private objects.
13. **Why must denied PUT tests re-read the record?** To prove the operation did not actually alter data.
14. **If HTTP filter checks ownership, can service checks be skipped?** No: services have other callers and races between check and update.
15. **Does a PUT missing CSRF returning 403 prove owner authorization works?** No; CSRF can block before ownership checks.
16. **How is `ReactiveSecurityContextHolder` used?** Reads `Mono<SecurityContext>` from Reactor Context to obtain `Authentication` and identify the actor.
17. **What should shared-document checks inspect?** Active grant, grantee, action, tenant, expiry, and revocation status.
18. **What risk arises if owner changes between check and update?** TOCTOU; enforce permissions directly inside UPDATE/transaction.
19. **Does Tenant A Admin automatically control Tenant B?** No; explicit scope/delegation is required.
20. **Why not return the full `StoredDocument` object?** Can leak owner/tenant/metadata; use an allowed DTO and still verify permissions.

## 14. Production Implementation Checklist

- [ ] Inventory all APIs referencing IDs: GET, UPDATE, DELETE, LIST, SEARCH, exports, files, batch, GraphQL, jobs.
- [ ] Clearly define owner, tenant, and share permissions; separate coarse roles from action permissions.
- [ ] Actor ID/tenant must come from verified sources using immutable realm-scoped keys.
- [ ] `authorizeExchange` enforces functional permissions; new routes deny by default.
- [ ] Repository GET/LIST/SEARCH queries include owner/tenant/ACL predicates; filter before count/page.
- [ ] UPDATE/DELETE enforce permissions inside the write operation or a consistent transaction.
- [ ] Handle races, optimistic locking/versions, ownership transfers, and grant revocations.
- [ ] Request DTOs do not accept unauthorized owner/tenant fields; response DTOs expose only needed fields.
- [ ] Standardize 401/403/404 without disclosing sensitive resource existence.
- [ ] Cross-tenant and support overrides have explicit policies, scopes, and audits.
- [ ] Never use hard-to-guess IDs, hidden frontend buttons, or rate limits as access control.
- [ ] Caches, pre-signed URLs, background jobs, and WebSockets/SSE cannot bypass object policies.
- [ ] Test at least two accounts with the same role and tenant, plus one in another tenant.
- [ ] Test rejected writes leave records unchanged; check multipart/nested/list and alias routes.
- [ ] No blocking database I/O or detached `subscribe()` in reactive authorization.
- [ ] Keep CSRF when browsers attach credentials automatically, protect cookies/tokens, and use HTTPS.
- [ ] Monitor enumeration, horizontal probing, and support activity without logging raw credentials.

## 15. References

- OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP — IDOR Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Spring Security 6.3 — Reactive HTTP Authorization: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 API — `ReactiveAuthorizationManager`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Spring Security API — `AuthorizationContext`: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security — WebFlux Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html

**Key Takeaway:** An ID in a URL identifies the target resource, **not a license to access it**. Preventing IDOR/BOLA in Spring Security reactive requires combining **trusted authentication + HTTP method permissions + owner/tenant/grant checks where data is read/written**, and testing ID swaps between accounts sharing the same role. For PUT/PATCH/DELETE, enforce ownership directly in the write statement to prevent TOCTOU.
