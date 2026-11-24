# `ReactiveAuthorizationManager` with `AuthorizationContext` in Spring Security WebFlux

## 1. The problem and goal

When protecting a reactive HTTP API, the rule "must be logged in to call" is rarely enough. Consider these endpoints:

```http
GET /api/tenants/TENANT_A/documents/42
DELETE /api/tenants/TENANT_A/documents/42
```

To decide whether to allow or deny, the application must simultaneously know **who is calling**, the **HTTP method**, the **tenant in the path**, the **document ID**, **functional permissions**, and the **document's business metadata**. In Spring Security for WebFlux, a strongly typed way to write this policy is `ReactiveAuthorizationManager<AuthorizationContext>` inside `ServerHttpSecurity.authorizeExchange(...).access(...)`.

This guide belongs to the **HTTP on WebFlux** section of the Spring Security Authorization module. After completing it, you will be able to:

1. Distinguish `ReactiveAuthorizationManager<AuthorizationContext>` (HTTP authorization in WebFlux) from `AuthorizationManager<RequestAuthorizationContext>` (Servlet) and reactive method-security authorization.
2. Understand what `Mono<Authentication>` and `AuthorizationContext` contain, and why you must **never use `block()`** or imperative `SecurityContextHolder` on the authorization path.
3. Access `context.getExchange()` and `context.getVariables()`, read path variables safely, and handle malformed IDs.
4. Wire a custom manager using `.pathMatchers(HttpMethod.GET, ...).access(manager)`, combining `permitAll`, `hasAuthority`, `denyAll`, and matcher ordering.
5. Combine READ/DELETE permissions with tenant membership, ownership, document state, and a policy source returning `Mono<Boolean>`.
6. Handle **anonymous** callers, missing authentication, policy source errors, missing path variables, and missing records in a **deny-by-default** manner.
7. Test with `WebTestClient` and `spring-security-test`, verifying 200/204/401/403 status codes, CSRF, and **that the method body does not execute when denied**.
8. Understand production boundaries: HTTP authorization differs from service-layer object authorization, a path tenant variable is not a trusted identity, race conditions, reactive data access, caching, multi-tenancy, and side effects.

**Illustrative versions:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux, and Reactor. Examples follow the 6.5 branch conventions. Since Spring Security 6.4, `ReactiveAuthorizationManager.check(...)` has been marked deprecated in favor of `authorize(...)`; this guide notes that clearly so APIs are not blindly carried over to 7.x.

## 2. Architecture: request, manager, decision `Mono`, and handler

```text
HTTP GET /api/tenants/TENANT_A/documents/42
  |
  v
SecurityWebFilterChain
  |
  v
WebFlux exchange matcher
  pathMatchers(GET, "/api/tenants/{tenantId}/documents/{docId}")
  |
  v
ReactiveAuthorizationManager<AuthorizationContext>
  |  Mono<Authentication>             -> actor/authorities
  |  AuthorizationContext.variables  -> tenantId, docId
  |  AuthorizationContext.exchange   -> HTTP method/request
  |
  +-- missing auth/permission/tenant/doc/state --> AuthorizationDecision(false)
  |
  +-- policy source (Mono<Boolean>)
        |
        +-- true  --> AuthorizationDecision(true)
        +-- false --> AuthorizationDecision(false)
        +-- error --> deny/fail closed per policy
  |
  v
AuthorizationWebFilter / ExceptionTranslation
  |  401 when authentication is needed
  |  403 when authenticated but not permitted
  |
  +-- ALLOW -> WebFlux handler/controller -> Mono<ResponseEntity<...>>
  +-- DENY  -> handler body is not invoked
```

Spring Security provides authentication as a publisher automatically. The manager **does not need to construct a new `SecurityContext`** and should not rely on the request thread's `ThreadLocal`: in Reactor, a pipeline can hop threads while retaining the Reactor Context.

### 2.1. Key interfaces and classes

| Component | Primary package | Responsibility |
| --- | --- | --- |
| `ReactiveAuthorizationManager<T>` | `org.springframework.security.authorization` | Makes a reactive authorization decision for target `T` |
| `AuthorizationContext` | `org.springframework.security.web.server.authorization` | Holds `ServerWebExchange` and URI template variables |
| `AuthorizationDecision` | `org.springframework.security.authorization` | Result indicating granted or denied |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Configures WebFlux HTTP security |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Security `WebFilter` chain |
| `Authentication` | `org.springframework.security.core` | Identity and authorities verified by the framework |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Accesses `SecurityContext` via Reactor Context |
| `WebTestClient` | `org.springframework.test.web.reactive.server` | Tests WebFlux HTTP endpoints |
| `SecurityMockServerConfigurers` | `org.springframework.security.test.web.reactive.server` | Simulates authentication/CSRF in reactive tests |

**Do not confuse with Servlet:** Servlet uses `HttpSecurity.authorizeHttpRequests` and `AuthorizationManager<RequestAuthorizationContext>`; WebFlux uses `ServerHttpSecurity.authorizeExchange` and `ReactiveAuthorizationManager<AuthorizationContext>`. Do not mistakenly import `HttpServletRequest` or `RequestAuthorizationContext` in a WebFlux project.

## 3. Structure of `ReactiveAuthorizationManager<AuthorizationContext>`

### 3.1. Signature in Spring Security 6.5

```java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

public class SampleManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return authentication
            .map(auth -> new AuthorizationDecision(
                auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> "DOC_READ".equals(a.getAuthority()))))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
```

This is a **syntactically standalone Java class** when Spring Security and Reactor dependencies are present, yet it only checks an authority without checking tenant/resource/owner, and `auth.isAuthenticated()` **is not enough to exclude an anonymous token**. The complete example in section 8 adds those checks.

**Version compatibility details:**

- In Spring Security 6.5, `check(Mono<Authentication>, T)` returning `Mono<AuthorizationDecision>` is still the common way to implement the interface; it is marked deprecated.
- The interface also defines `authorize(Mono<Authentication>, T)`, returning `Mono<AuthorizationResult>`, which is recommended for new APIs. `AuthorizationDecision` implements the corresponding authorization result model.
- Since signatures and override semantics can change between 6.5 and 7.x, check the Javadoc for your exact version. Examples here target **6.5.x** specifically; do not treat `@SuppressWarnings("deprecation")` as a universal migration strategy across versions.
- `Mono.empty()` can represent abstain/no decision in some managers; how the system handles abstain depends on composition. For sensitive policies, these examples **return an explicit deny** for every ineligible case to avoid ambiguity.

### 3.2. `Mono<Authentication>` is not `Authentication`

In WebFlux, the first parameter is a **publisher**, not a synchronous authentication object:

```java
return authentication
    .filter(auth -> auth.isAuthenticated())
    .flatMap(auth -> reactivePolicy.canRead(auth)
        .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

`reactivePolicy.canRead(auth)` is assumed to return `Mono<Boolean>`. This is only a **fragment**. Never call:

```java
// ANTI-PATTERN: can block the Netty event loop.
Authentication auth = authentication.block();

// ANTI-PATTERN: ThreadLocal is not the primary source of reactive context.
Authentication auth2 = SecurityContextHolder
    .getContext().getAuthentication();
```

Calling `block()` in WebFlux can stall the event loop, degrade throughput, or throw an exception in non-blocking environments. If the current data source uses blocking JDBC/JPA, migrate to R2DBC/reactive services or offload cleanly onto an appropriate scheduler; never hide a blocking call inside `Mono.just(repository.findById(...))` and pretend it is reactive.

### 3.3. `AuthorizationContext`: exchange and variables

```java
ServerWebExchange exchange = context.getExchange();
HttpMethod method = exchange.getRequest().getMethod();

Object tenantValue = context.getVariables().get("tenantId");
Object documentValue = context.getVariables().get("docId");
```

These variables come from `pathMatchers("/api/tenants/{tenantId}/documents/{docId}")`. In the 6.5 API, `getVariables()` returns `Map<String,Object>`; do not cast every entry to `String` before checking. `getExchange()` exposes the HTTP method, request headers, path, query params, attributes, remote address, and more, yet **data from an HTTP request never becomes trustworthy by itself**.

For instance, a client can send `/api/tenants/TENANT_B/documents/42`, so the manager must verify the caller is actually allowed to access `TENANT_B`. Do not read `X-Tenant-Id` and assume it is the principal's tenant. Similarly, `docId="hello"` or a value overflowing `long` should be denied or handled cleanly rather than causing an accidental 500.

### 3.4. `AuthorizationDecision(true/false)`, missing auth, and errors

Common result scenarios:

| Case | Example policy | Typical HTTP result |
| --- | --- | --- |
| Authenticated, valid authority + valid tenant + valid resource | Allow | Handler runs, 2xx or 404 depending on data |
| Authenticated, missing authority | Deny | 403 Forbidden |
| Authenticated, different tenant | Deny | 403 (or 404 if the API hides resource existence) |
| Authenticated, resource does not exist | Deny | 403 in the example |
| Anonymous / unauthenticated | Deny / authentication required | 401 when HTTP Basic entry point is configured |
| Invalid path variable | Explicit deny | 403 in the example |
| Policy backend error | Fail closed | 403 in the example; production may use 503 when safe and non-leaking |

**Do not conflate 401/403 with resource hiding:** if you want to return 404 to avoid leaking IDs across tenants, design response and exception handling consistently. The manager only produces a decision; the final HTTP status also depends on the authentication entry point, access-denied handler, CSRF filter, and WebFlux exception mapping.

## 4. Configuring `ServerHttpSecurity.authorizeExchange(...)`

### 4.1. Wiring a custom manager

```java
@Bean
SecurityWebFilterChain filterChain(
        ServerHttpSecurity http,
        DocumentAuthorizationManager manager) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/ping").permitAll()
            .pathMatchers(HttpMethod.GET,
                "/api/tenants/{tenantId}/documents/{docId}")
                .access(manager)
            .pathMatchers(HttpMethod.DELETE,
                "/api/tenants/{tenantId}/documents/{docId}")
                .access(manager)
            .anyExchange().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is a **bean fragment**; `DocumentAuthorizationManager` and imports appear in the complete project in section 8. Matcher order matters: put specific routes before `anyExchange`; if `anyExchange().permitAll()` appears in the wrong place, subsequent routes may not be protected as intended.

### 4.2. When to use `.hasAuthority(...)` instead of `.access(manager)`?

Use the built-in DSL when rules are simple:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("REPORT_READ")
    .anyExchange().authenticated()
)
```

Use `.access(manager)` when you need custom logic over path variables, tenant membership, ownership, document state, reactive lookups, or PDP decisions. **Do not overcomplicate every route:** routes needing only authentication or a role can use built-in managers so they remain easy to read and test.

### 4.3. CSRF and HTTP methods

In WebFlux, CSRF protection is typically enabled by default. For `DELETE`, `POST`, `PUT`, and `PATCH` under session/cookie authentication, requests must carry a valid CSRF token. That is why the DELETE test in this guide uses:

```java
webTestClient
    .mutateWith(mockUser("alice").authorities(
        new SimpleGrantedAuthority("DOC_DELETE")))
    .mutateWith(csrf())
    .delete()
    .uri("/api/tenants/TENANT_A/documents/42")
    .exchange()
    .expectStatus().isNoContent();
```

This is a **test fragment**. Without a CSRF token, a request allowed by the custom manager can still get **403 from `CsrfWebFilter`**, which does not prove the manager denied it. Never disable CSRF application-wide just to make tests pass easily; for stateless bearer-token APIs, base the CSRF decision on the authentication threat model and whether browsers send credentials automatically.

### 4.4. Router functions and `pathMatchers`

WebFlux supports both annotated controllers and functional `RouterFunction`s. HTTP authorization runs in a `WebFilter` and can protect both. However, template variables from `AuthorizationContext` must match the **security matcher** that selected the rule; do not rely on variable names from a controller or `RouterFunction` if the security matcher did not extract them. When URI path matching becomes complex, test `context.getVariables()` directly alongside real HTTP routes.

## 5. Policy example: tenant + document + method

Suppose the database contains:

| Tenant | ID | Owner | State | Body |
| --- | ---: | --- | --- | --- |
| TENANT_A | 42 | alice | DRAFT | A private 42 |
| TENANT_B | 42 | bob | DRAFT | B private 42 |
| TENANT_A | 43 | bob | PUBLISHED | A public 43 |
| TENANT_B | 44 | bob | PUBLISHED | B public 44 |

**Server-side membership**:

- `alice` belongs to TENANT_A, and may be granted `DOC_READ` and `DOC_DELETE`.
- `bob` belongs to TENANT_B, and may be granted `DOC_READ` and `DOC_DELETE`.
- `reviewer` belongs to both TENANT_A and TENANT_B, but in the demo only uses `DOC_READ`.
- Unknown users without membership are denied even if they pass a valid tenant in the URL.

**Business rule**:

```text
canRead(actor, tenant, document)
  = authenticated
    AND hasAuthority("DOC_READ")
    AND actor is allowed to use tenant
    AND document.tenant = tenant
    AND (document.state = PUBLISHED OR document.owner = actor.username)

canDelete(actor, tenant, document)
  = authenticated
    AND hasAuthority("DOC_DELETE")
    AND actor is allowed to use tenant
    AND document.tenant = tenant
    AND document.state = DRAFT
    AND document.owner = actor.username
```

Using username for owner here is **only to keep tests concise**. In systems with multiple identity providers, use a stable `issuer + subject` or internal user ID; identical usernames across two tenants must never be treated as the same identity. The manager still checks the actor's tenant, the path tenant, and the resource's tenant via the repository.

### 5.1. Allow/deny matrix

| Request | Auth/authority | Expected | Why? |
| --- | --- | --- | --- |
| GET A/42 | alice + DOC_READ | 200, A private 42 | Owner and member of A |
| GET B/42 | bob + DOC_READ | 200, B private 42 | Owner and member of B |
| GET B/42 | alice + DOC_READ | 403 | Alice does not belong to B |
| GET A/42 | bob + DOC_READ | 403 | Bob does not belong to A |
| GET A/43 | reviewer + DOC_READ | 200 | PUBLISHED, member of A |
| GET A/42 | reviewer + DOC_READ | 403 | Alice's DRAFT |
| GET A/42 | alice with DOC_DELETE only | 403 | DELETE permission does not grant READ |
| DELETE A/42 | alice + DOC_DELETE + CSRF | 204 | Owner, DRAFT |
| DELETE B/42 | bob + DOC_DELETE + CSRF | 204 | Owner, DRAFT |
| DELETE A/43 | alice + DOC_DELETE + CSRF | 403 | PUBLISHED and not owner |
| DELETE A/42 | reviewer with DOC_READ only + CSRF | 403 | Missing DELETE |
| DELETE A/42 | alice + DOC_DELETE, missing CSRF | 403 | Blocked by CSRF filter |
| GET A/999 | alice + DOC_READ | 403 | Document missing |
| GET A/not-a-number | alice + DOC_READ | 403 | Invalid path variable |
| GET A/42 | unauthenticated | 401 | Authentication required |
| GET /public/ping | unauthenticated | 200 | Public route |
| POST A/42 | authenticated | 403 | Route not configured |

**Distinction:** a 403 from the custom manager and a 403 from CSRF come from different sources. Tests must include DELETE **with** a CSRF token to actually reach the authorization manager.

## 6. Reactive pipeline: do it right rather than merely "using Mono"

### 6.1. Return the publisher; never subscribe manually

The manager should return `Mono<AuthorizationDecision>` and let Spring Security manage the subscription. Do not call `.subscribe()` inside `check()`, because the decision escapes the request pipeline and exceptions or context can be mishandled.

```java
return authentication
    .flatMap(auth ->
        policy.canRead(auth, tenant, id)
            .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

`policy.canRead(...)` is an application-defined reactive method fragment. Results are produced only when the pipeline is subscribed to. Avoid uncontrolled side effects at **assembly** time and avoid blocking remote calls on the Netty event loop.

### 6.2. Fail closed when lookups fail

```java
return policy.isAllowed(user, tenant, id, action)
    .map(AuthorizationDecision::new)
    .onErrorReturn(new AuthorizationDecision(false))
    .defaultIfEmpty(new AuthorizationDecision(false));
```

This pattern intentionally turns policy backend errors into deny. Production may differentiate `AccessDenied` from `ServiceUnavailable` to return 503 and alert, yet **never fall back to ALLOW**. Monitor errors so a PDP outage is not hidden behind a wave of hard-to-diagnose 403s.

If the policy returns `Mono.empty()` because no document exists, `defaultIfEmpty(false)` should emit an explicit deny; avoid mixing `empty = missing data` with the framework's `empty = abstain`.

### 6.3. Never read the actor from request headers

```java
// ANTI-PATTERN: the client controls this value.
String actor = context.getExchange().getRequest()
    .getHeaders().getFirst("X-User");

// ANTI-PATTERN: a client-supplied tenant does not prove membership.
String tenant = context.getExchange().getRequest()
    .getHeaders().getFirst("X-Tenant");
```

The manager must obtain identity from the `Mono<Authentication>` produced by security filters after authentication, and membership from a **verified** directory or claims. If an actor can switch tenants, the server must verify membership before using the tenant from the path.

### 6.4. Do not use Servlet APIs

The following types belong to Servlet and are invalid with reactive `AuthorizationContext`:

```java
// Wrong WebFlux context:
// HttpServletRequest
// RequestAuthorizationContext
// HttpSecurity.authorizeHttpRequests(...)
```

Use `ServerWebExchange`, `AuthorizationContext`, and `ServerHttpSecurity.authorizeExchange(...)`. If Spring Boot has both `spring-boot-starter-web` and `spring-boot-starter-webflux` on the classpath, Boot normally prefers MVC; check `spring.main.web-application-type=reactive` and dependencies when running WebFlux tests.

## 7. Relationship among HTTP security, reactive method security, and RLS

### 7.1. HTTP WebFilter is the first layer, not the whole authorization model

An HTTP `ReactiveAuthorizationManager<AuthorizationContext>` checks only requests passing through the WebFlux security chain. A business method may be called from scheduled jobs, message consumers, reactive listeners, or other services **bypassing HTTP security**. For critical data, enforce checks at the service or repository layer too.

When enabling reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
    // Mono/Flux methods can use @PreAuthorize.
}
```

This is a configuration fragment, not required in the HTTP demo in section 8. `@EnableReactiveMethodSecurity` is for **reactive method security** and uses Reactor Context. Do not equate it with Servlet/imperative-method `@EnableMethodSecurity`.

### 7.2. `AuthorizationContext` is an HTTP context, not a domain ACL

`AuthorizationContext` holds the exchange and path variables; it does not automatically hold ACEs, owners, or document states. Reading the document must be done by a reactive policy/data source. If a complex policy uses blocking JDBC `Spring Security ACL`, account for I/O and schedulers or redesign data access—never run blocking JDBC queries directly inside an authorization manager on the event loop.

### 7.3. TOCTOU

A `DELETE` might be permitted because at check time the document is Alice's DRAFT. Before the DELETE statement executes, another transaction could transition it to APPROVED. Therefore, inside the body/service you **must re-check owner and state at deletion time** via conditional update/delete or optimistic locking, rather than assuming pre-authorization froze the record.

For reactive databases, conceptual SQL:

```sql
DELETE FROM documents
WHERE tenant_id = :tenant
  AND document_id = :id
  AND owner_id = :authenticatedSubject
  AND status = 'DRAFT';
```

Verify affected rows equal 1 before treating the deletion as succeeded. `@PreAuthorize` does not replace transactions or locking. The in-memory demo checks owner/state inside `ConcurrentHashMap.computeIfPresent` to highlight the principle; it **does not simulate database transactions**.

## 8. Java 17+ project with `WebTestClient` and real Spring Security

The project below uses real WebFlux HTTP Security, a **non-blocking in-memory** store to keep focus on the manager, and 22 JUnit tests. It requires no Docker/database and is not a production multi-node service. The Spring Boot test context creates real WebFlux routes and the security chain; `WebTestClient` binds to the `ApplicationContext` and applies `springSecurity()` from `spring-security-test`.

### 8.1. File layout

```text
reactive-authz-context-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ReactiveAuthorizationContextTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-authz-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

The project puts all Java under `src/test/java`, so only `testImplementation` is needed. When moving into an application, switch the WebFlux/Security starters to `implementation`. Because only the WebFlux starter is present, the demo does not depend on Servlet `MockMvc`.

### 8.2. A complete Java test file

Create `src/test/java/demo/ReactiveAuthorizationContextTest.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    classes = ReactiveAuthorizationContextTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "spring.main.web-application-type=reactive"
)
public class ReactiveAuthorizationContextTest {

    public record Key(String tenant, long id) {}

    public record Document(
        String tenant, long id, String owner,
        String state, String body
    ) {}

    public record DocumentView(
        String tenant, long id, String body
    ) {}

    public static class TenantDirectory {
        private final Map<String, Set<String>> memberships = Map.of(
            "alice", Set.of("TENANT_A"),
            "bob", Set.of("TENANT_B"),
            "reviewer", Set.of("TENANT_A", "TENANT_B")
        );

        public boolean belongs(String actor, String tenant) {
            return memberships.getOrDefault(actor, Set.of())
                .contains(tenant);
        }
    }

    public static class ReactiveDocumentStore {
        private final Map<Key, Document> rows =
            new ConcurrentHashMap<>();
        private final AtomicInteger lookups = new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);

        public void reset() {
            rows.clear();
            rows.put(new Key("TENANT_A", 42L),
                new Document("TENANT_A", 42L,
                    "alice", "DRAFT", "A private 42"));
            rows.put(new Key("TENANT_B", 42L),
                new Document("TENANT_B", 42L,
                    "bob", "DRAFT", "B private 42"));
            rows.put(new Key("TENANT_A", 43L),
                new Document("TENANT_A", 43L,
                    "bob", "PUBLISHED", "A public 43"));
            rows.put(new Key("TENANT_B", 44L),
                new Document("TENANT_B", 44L,
                    "bob", "PUBLISHED", "B public 44"));
            lookups.set(0);
            available.set(true);
        }

        public Mono<Document> find(String tenant, long id) {
            return Mono.defer(() -> {
                lookups.incrementAndGet();
                if (!available.get()) {
                    return Mono.error(new IllegalStateException(
                        "Simulated policy source outage"));
                }
                return Mono.justOrEmpty(
                    rows.get(new Key(tenant, id)));
            });
        }

        // Domain re-check: do not trust an earlier precheck.
        public Mono<Boolean> deleteDraftOwnedBy(
                String tenant, long id, String actor) {
            return Mono.fromSupplier(() -> {
                Key key = new Key(tenant, id);
                AtomicBoolean deleted = new AtomicBoolean();
                rows.computeIfPresent(key, (k, doc) -> {
                    if ("DRAFT".equals(doc.state())
                            && actor.equals(doc.owner())) {
                        deleted.set(true);
                        return null;
                    }
                    return doc;
                });
                return deleted.get();
            });
        }

        public String rawBody(String tenant, long id) {
            Document d = rows.get(new Key(tenant, id));
            return d == null ? null : d.body();
        }

        public boolean exists(String tenant, long id) {
            return rows.containsKey(new Key(tenant, id));
        }

        public int lookups() {
            return lookups.get();
        }

        public void setAvailable(boolean state) {
            available.set(state);
        }
    }

    public static class DocumentPolicy {
        private final ReactiveDocumentStore store;

        public DocumentPolicy(ReactiveDocumentStore store) {
            this.store = store;
        }

        public Mono<Boolean> isAllowed(
                String actor, String tenant,
                long id, String action) {
            return store.find(tenant, id)
                .map(doc -> {
                    if ("READ".equals(action)) {
                        return "PUBLISHED".equals(doc.state())
                            || actor.equals(doc.owner());
                    }
                    if ("DELETE".equals(action)) {
                        return "DRAFT".equals(doc.state())
                            && actor.equals(doc.owner());
                    }
                    return false;
                })
                .defaultIfEmpty(false);
        }
    }

    public static class DocumentAuthorizationManager
            implements ReactiveAuthorizationManager<AuthorizationContext> {

        private final TenantDirectory directory;
        private final DocumentPolicy policy;
        private final AtomicInteger checks = new AtomicInteger();

        public DocumentAuthorizationManager(
                TenantDirectory directory, DocumentPolicy policy) {
            this.directory = directory;
            this.policy = policy;
        }

        @Override
        @SuppressWarnings("deprecation")
        public Mono<AuthorizationDecision> check(
                Mono<Authentication> authentication,
                AuthorizationContext context) {

            return Mono.defer(() -> {
                checks.incrementAndGet();

                Object rawTenant =
                    context.getVariables().get("tenantId");
                Object rawId =
                    context.getVariables().get("docId");

                if (!(rawTenant instanceof String tenant)
                        || tenant.isBlank()
                        || !(rawId instanceof String idText)) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                final long id;
                try {
                    id = Long.parseLong(idText);
                    if (id <= 0L) {
                        return Mono.just(new AuthorizationDecision(false));
                    }
                } catch (NumberFormatException invalidId) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                HttpMethod method =
                    context.getExchange().getRequest().getMethod();

                String action = HttpMethod.GET.equals(method)
                    ? "READ"
                    : HttpMethod.DELETE.equals(method)
                        ? "DELETE" : null;

                if (action == null) {
                    return Mono.just(new AuthorizationDecision(false));
                }

                String authority = "DOC_" + action;

                return authentication
                    .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                    .flatMap(auth -> {
                        boolean hasAuthority = auth.getAuthorities()
                            .stream()
                            .anyMatch(granted -> authority.equals(
                                granted.getAuthority()));

                        if (!hasAuthority
                                || !directory.belongs(
                                    auth.getName(), tenant)) {
                            return Mono.just(
                                new AuthorizationDecision(false));
                        }

                        return policy.isAllowed(
                                auth.getName(), tenant, id, action)
                            .map(AuthorizationDecision::new)
                            .defaultIfEmpty(
                                new AuthorizationDecision(false))
                            .onErrorReturn(
                                new AuthorizationDecision(false));
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
            });
        }

        public int checks() {
            return checks.get();
        }

        public void reset() {
            checks.set(0);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger deletes = new AtomicInteger();

        public void read() {
            reads.incrementAndGet();
        }

        public void delete() {
            deletes.incrementAndGet();
        }

        public int reads() {
            return reads.get();
        }

        public int deletes() {
            return deletes.get();
        }

        public void reset() {
            reads.set(0);
            deletes.set(0);
        }
    }

    @RestController
    @RequestMapping("/api/tenants/{tenantId}/documents")
    public static class DocumentController {
        private final ReactiveDocumentStore store;
        private final Probe probe;

        public DocumentController(
                ReactiveDocumentStore store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @GetMapping("/{docId}")
        public Mono<ResponseEntity<DocumentView>> get(
                @PathVariable("tenantId") String tenant,
                @PathVariable("docId") long id) {
            probe.read();

            return store.find(tenant, id)
                .map(doc -> ResponseEntity.ok(new DocumentView(
                    doc.tenant(), doc.id(), doc.body())))
                .defaultIfEmpty(
                    ResponseEntity.notFound().build());
        }

        @DeleteMapping("/{docId}")
        public Mono<ResponseEntity<Void>> delete(
                @PathVariable("tenantId") String tenant,
                @PathVariable("docId") long id) {
            probe.delete();

            return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .flatMap(actor ->
                    store.deleteDraftOwnedBy(tenant, id, actor))
                .map(deleted -> deleted
                    ? ResponseEntity.noContent().<Void>build()
                    : ResponseEntity.status(
                        HttpStatus.CONFLICT).<Void>build());
        }
    }

    @RestController
    public static class PublicController {
        @GetMapping("/public/ping")
        public Mono<String> ping() {
            return Mono.just("pong");
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebFluxSecurity
    public static class Config {

        @Bean TenantDirectory tenantDirectory() {
            return new TenantDirectory();
        }

        @Bean ReactiveDocumentStore documentStore() {
            return new ReactiveDocumentStore();
        }

        @Bean DocumentPolicy documentPolicy(
                ReactiveDocumentStore store) {
            return new DocumentPolicy(store);
        }

        @Bean DocumentAuthorizationManager documentManager(
                TenantDirectory directory, DocumentPolicy policy) {
            return new DocumentAuthorizationManager(directory, policy);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentController documentController(
                ReactiveDocumentStore store, Probe probe) {
            return new DocumentController(store, probe);
        }

        @Bean PublicController publicController() {
            return new PublicController();
        }

        @Bean MapReactiveUserDetailsService testUsers() {
            // Demo only. HTTP tests inject mockUser; do not use
            // {noop} passwords in production.
            UserDetails user = User.withUsername("test-login")
                .password("{noop}test-only")
                .authorities("DOC_READ")
                .build();
            return new MapReactiveUserDetailsService(user);
        }

        @Bean SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http,
                DocumentAuthorizationManager manager) {
            return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/ping").permitAll()
                    .pathMatchers(HttpMethod.GET,
                        "/api/tenants/{tenantId}/documents/{docId}")
                        .access(manager)
                    .pathMatchers(HttpMethod.DELETE,
                        "/api/tenants/{tenantId}/documents/{docId}")
                        .access(manager)
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Keep CSRF at its default: DELETE must include token.
                .build();
        }
    }

    @Autowired ApplicationContext applicationContext;
    @Autowired ReactiveDocumentStore store;
    @Autowired DocumentAuthorizationManager manager;
    @Autowired Probe probe;

    private WebTestClient web;

    @BeforeEach
    void setUp() {
        store.reset();
        manager.reset();
        probe.reset();

        web = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient actor(
            String username, String authority) {
        return web.mutateWith(
            mockUser(username).authorities(
                new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicPingWorksWithoutAuthentication() {
        web.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentReadIsUnauthorized() {
        web.get()
            .uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isUnauthorized();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void aliceReadsHerTenantADraft() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("A private 42")
            .jsonPath("$.tenant").isEqualTo("TENANT_A");

        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobReadsSameIdInTenantBWithoutSeeingA() {
        actor("bob", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("B private 42")
            .jsonPath("$.tenant").isEqualTo("TENANT_B");
    }

    @Test
    void aliceCannotReadTenantBLocalId42() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotReadTenantALocalId42() {
        actor("bob", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void reviewerReadsPublishedDocumentInTenantA() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("A public 43");
    }

    @Test
    void reviewerReadsPublishedDocumentInTenantB() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_B/documents/44")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.body").isEqualTo("B public 44");
    }

    @Test
    void reviewerCannotReadOtherPersonsDraft() {
        actor("reviewer", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void deleteAuthorityDoesNotImplyReadAuthority() {
        actor("alice", "DOC_DELETE")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void genericRoleDoesNotImplyDocRead() {
        actor("alice", "ROLE_ADMIN")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownUsernameIsNotMemberOfPathTenant() {
        actor("unknown", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingDocumentIsDeniedBeforeHandler() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/999")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void malformedDocIdIsDeniedInAuthorizationManager() {
        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/not-a-number")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void overflowingDocIdIsDeniedInAuthorizationManager() {
        actor("alice", "DOC_READ")
            .get().uri(
                "/api/tenants/TENANT_A/documents/999999999999999999999")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void aliceCanDeleteHerOwnDraftWithCsrf() {
        actor("alice", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isNoContent();

        assertThat(store.exists("TENANT_A", 42L)).isFalse();
        assertThat(store.rawBody("TENANT_B", 42L))
            .isEqualTo("B private 42");
        assertThat(probe.deletes()).isEqualTo(1);
    }

    @Test
    void bobCanDeleteHisOwnDraftWithoutDeletingTenantA() {
        actor("bob", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_B/documents/42")
            .exchange()
            .expectStatus().isNoContent();

        assertThat(store.exists("TENANT_B", 42L)).isFalse();
        assertThat(store.rawBody("TENANT_A", 42L))
            .isEqualTo("A private 42");
    }

    @Test
    void aliceCannotDeletePublishedDocument() {
        actor("alice", "DOC_DELETE")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/43")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 43L)).isTrue();
    }

    @Test
    void readAuthorityDoesNotImplyDelete() {
        actor("reviewer", "DOC_READ")
            .mutateWith(csrf())
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 42L)).isTrue();
    }

    @Test
    void missingCsrfTokenBlocksEvenAuthorizedDelete() {
        actor("alice", "DOC_DELETE")
            .delete().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.deletes()).isZero();
        assertThat(store.exists("TENANT_A", 42L)).isTrue();
    }

    @Test
    void policySourceErrorFailsClosed() {
        store.setAvailable(false);

        actor("alice", "DOC_READ")
            .get().uri("/api/tenants/TENANT_A/documents/42")
            .exchange()
            .expectStatus().isForbidden();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void unknownRouteIsDeniedByAnyExchange() {
        actor("alice", "DOC_READ")
            .get().uri("/internal/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

### 8.3. Why does this example test the HTTP manager properly?

**`DocumentAuthorizationManager`** is registered in `SecurityWebFilterChain` with `.access(manager)` for both HTTP methods. It receives a `Mono<Authentication>` from the framework, extracts `tenantId` and `docId` from `AuthorizationContext.getVariables()`, checks the method from `getExchange()`, and calls `DocumentPolicy.isAllowed(...)` returning `Mono<Boolean>`, mapping it to `AuthorizationDecision`.

**`WebTestClient` binds to `ApplicationContext`** via `bindToApplicationContext(...).apply(springSecurity())`, so `mockUser(...)` and `csrf()` participate in the real reactive security filter chain without starting an actual HTTP server. This is context-bound HTTP testing, **different** from a unit test that invokes `manager.check(...)` directly.

**`Probe`** increments its counters only inside the controller handler. When 403 occurs via the manager or CSRF, the counters stay zero; thus negative tests verify not only status codes, but also that the protected method body never ran.

**`ReactiveDocumentStore`** uses a `ConcurrentHashMap` to illustrate a non-blocking source via `Mono.defer`. It has no DB or network I/O, so it does not replace R2DBC/database production tests. `deleteDraftOwnedBy` still re-checks owner/state at mutation time to illustrate TOCTOU defense, though without distributed transactions.

**`TenantDirectory`** holds server-side membership in the example. Production requires verifying issuer/subject, role/tenant scope, token revocation, and tenant switching. Never let users dictate membership via URL or HTTP headers alone.

### 8.4. Running and expected results

In the `reactive-authz-context-demo` directory:

```bash
gradle test --tests demo.ReactiveAuthorizationContextTest
```

If the project already has a Gradle Wrapper, use `./gradlew test --tests demo.ReactiveAuthorizationContextTest` on Linux/macOS or `gradlew.bat test --tests demo.ReactiveAuthorizationContextTest` on Windows.

**Expected:** **22 JUnit tests** pass and Gradle finishes with `BUILD SUCCESSFUL`, provided the Java/Gradle/dependency environment matches. This is an **expected outcome**, not a log from an actual execution. HTML report: `build/reports/tests/test/index.html`.

| Test group | What to confirm |
| --- | --- |
| Public, anonymous | `permitAll` route runs; protected route requires authentication |
| Alice/Bob sharing local ID 42 | Returns the body belonging to the respective tenant |
| Cross-tenant | `AuthorizationContext` path variables + membership block access |
| Reviewer | Can read PUBLISHED in valid tenants, cannot read others' DRAFTs |
| Function-level permissions | `DOC_DELETE` does not grant `DOC_READ`; generic role does not unlock documents |
| Missing/malformed IDs | Explicit deny without entering controller |
| DELETE with CSRF | Deletes matching DRAFT/owner while leaving the other tenant untouched |
| DELETE without CSRF | 403 from CSRF, even though custom manager would allow |
| Policy source outage | No fallback to ALLOW |
| Unmatched URL | `anyExchange().denyAll()` takes effect |
| Probe | Denied requests do not invoke the method body |

### 8.5. When tests fail: check in order

1. **401 instead of 403:** did you inject `mockUser` into the Spring Security-wrapped `WebTestClient`? Is the authentication entry point active?
2. **All DELETEs return 403:** did you send `csrf()` in authorized DELETE tests? Otherwise CSRF blocks before the manager runs.
3. **403 even on valid GETs:** check that `getVariables()` receives `tenantId`/`docId` with the exact template names. If the map is empty, check the security matcher and version.
4. **404 instead of 200:** verify the controller `@Bean` is registered, annotated with `@RestController`, and mapped to the right path.
5. **Denied yet handler still ran:** did you invoke tests through `WebTestClient`/real `WebFilterChain` or instantiate the controller with `new`?
6. **Method Security not running:** this is an HTTP security demo; enabling method annotations separately requires `@EnableReactiveMethodSecurity` and Publisher-returning services.
7. **Different behavior after adding MVC starter:** Boot may start a Servlet app; check web application type and classpath.
8. **Blocking errors:** look for `.block()` or blocking JDBC/JPA in the manager; use a reactive data source or offload I/O onto a bounded scheduler if immediate replacement isn't possible.

## 9. Applying to production services and data

### 9.1. URI parameters do not replace object checks

The manager is invoked because the path matcher matched, yet `AuthorizationContext` does not itself prove an ID belongs to the tenant. **Load the object by tenant + ID from the data source**:

```java
// Reactive repository fragment provided by the application:
Mono<Document> findByTenantAndId(String tenant, long id);

// Policy fragment:
return repository.findByTenantAndId(tenant, id)
    .map(doc -> documentOwnerPolicyAllows(actor, doc, action))
    .defaultIfEmpty(false);
```

Do not write `repository.findById(id)` and assume the URL tenant is safe enough. With blocking JPA/JDBC, never run it directly on the Netty event loop. With R2DBC, use `DatabaseClient`/reactive repositories and proper transactions.

### 9.2. Domain authorization must cover non-HTTP paths too

A message consumer or scheduler never passes through `SecurityWebFilterChain`. For sensitive data, put critical rules in the **service/repository** alongside the HTTP manager; avoid relying solely on an HTTP layer that internal calls can bypass. Do not assume the HTTP manager handles reactive method security; the two mechanisms have different contexts and targets.

### 9.3. Caching decisions and latency

If a policy queries a DB or PDP on every request, you can consider short-lived `ALLOW`/`DENY` caching keyed by **tenant + actor identity + action + resource + policy revision**. Invalidate when ACLs/roles/tenants/resources change, monitor stale grants, and never cache a READ decision for DELETE. For sensitive mutations, pre-authorization caches are only an optimization; re-checking inside the transaction remains essential.

### 9.4. Multiple identity sources

`Authentication.getName()` is not guaranteed globally unique. Two users in tenants A and B might share a username or come from different IdPs. Use a stable `issuer + subject` or internal user ID and verify tenant membership—never trust user-supplied headers. The demo uses username for ownership solely to keep code compact; change this before multi-tenant production use.

### 9.5. Multiple authentication mechanisms

If your application uses OAuth2 Resource Server JWT, HTTP Basic, sessions, mTLS, or an authenticating gateway, **never** treat an `X-User` header as `Authentication`. Configure the appropriate authentication filter and entry point. Use a `ReactiveAuthenticationManager` or JWT converter to populate authorities on `Authentication`; the authorization manager decides only after authentication has succeeded.

### 9.6. Interaction with WebSockets, SSE, and streaming

HTTP authorization checks the handshake/request, yet on long-lived streams or WebSockets, permissions may be revoked while data is still flowing. For sensitive data, add periodic re-checks or termination policies matching your TTL/revocation SLA and protocol. Never treat a single `ALLOW` at stream open as a permanent license.

## 10. Common mistakes

| Mistake | Consequence | Detection / fix |
| --- | --- | --- |
| Using `AuthorizationManager<RequestAuthorizationContext>` in WebFlux | Wrong Servlet API | Use `ReactiveAuthorizationManager<AuthorizationContext>` |
| Using `SecurityContextHolder.getContext()` in a reactive pipeline | Wrong context on thread switch | Use `Mono<Authentication>` / `ReactiveSecurityContextHolder` |
| Calling `block()` during permission checks | Blocks event loop, hurts throughput | Return `Mono<AuthorizationDecision>` |
| Ignoring `getVariables()` and reading only body/query params | Fails to bind the real resource | Test the security path matcher with URI templates |
| Changing tenant in the URL to gain access | IDOR / cross-tenant access | Verify membership and resource tenant server-side |
| Having READ grants DELETE | Missing action separation | Test `GET` vs `DELETE` and distinct authorities |
| Using Servlet `@PreAuthorize` for WebFlux HTTP | Wrong security layer | `authorizeExchange` protects HTTP; `@EnableReactiveMethodSecurity` protects methods |
| Treating `Mono.empty()` as ALLOW | Ambiguous abstain semantics | Return explicit `AuthorizationDecision(false)` on missing data |
| Catching PDP error and falling back to `true` | Fail-open | `onErrorReturn(deny)` + alert |
| Concluding DELETE 403 came from the custom manager | Might be CSRF | Test DELETE with `csrf()` |
| Overly broad `anyExchange().permitAll()` | Exposes unintended routes | Specific rules first, default `denyAll` |
| Checking ownership only before calling DELETE | Race condition / TOCTOU | Conditional DELETE on owner/state/version |
| Caching permissions by lone `id` | ID collisions across tenants/actions | Key by tenant, actor, action, resource, revision |
| Unit testing manager with `new` without filter chain | Misses integration bugs | Use `WebTestClient` + `springSecurity` |
| Policy returns 403 while internal endpoint still reads data | HTTP manager doesn't cover jobs | Protect service/repository layers too |
| Using `JdbcTemplate` directly inside `flatMap` | Blocking I/O on reactive thread | Use R2DBC/reactive APIs or a controlled scheduler |

## 11. Acceptance checklist

- [ ] WebFlux project uses `ServerHttpSecurity.authorizeExchange(...)`, not Servlet `HttpSecurity`.
- [ ] `ReactiveAuthorizationManager<AuthorizationContext>` uses `Mono<Authentication>`, never `block()`/`subscribe()`.
- [ ] `getExchange()`/`getVariables()` use the exact variable names from the security matcher; malformed/missing IDs are checked.
- [ ] Anonymous callers, missing authorities, or invalid tenant memberships receive explicit deny.
- [ ] `READ`/`DELETE` permissions are separated; record owner/state/tenant are verified by a trusted policy source.
- [ ] Data-layer queries still enforce tenant/ID scoping rather than relying solely on the path.
- [ ] HTTP routes are ordered properly; unknown paths/methods are denied per policy.
- [ ] `WebTestClient` tests use real security support and distinguish 401/403/200/204.
- [ ] CSRF is tested properly for DELETE/POST under browser credential mechanisms.
- [ ] Negative tests cover non-existent IDs, malformed IDs, overflow, wrong tenant, source outage, and missing auth/authority.
- [ ] Tests verify the method body does not execute when denied; side effects perform conditional re-checks.
- [ ] Display username is not used as a global owner identity across multiple tenants/issuers.
- [ ] Blocking I/O is never placed on the event loop; reactive transactions and error handling are verified.
- [ ] For newer versions, deprecated `check` vs `authorize` signatures are verified and migration-tested.

## 12. Extended exercises

**Exercise A — POST and CSRF:** Add `POST /api/tenants/{tenantId}/documents` with `DOC_CREATE`, having the server assign tenant/owner from the trusted identity. Write tests with and without `csrf()` and verify documents cannot be created in another tenant.

**Exercise B — Multiple authorities:** Give `reviewer` permission to read PUBLISHED documents in both tenants, but grant `DOC_DELETE` only for documents they created; do not treat `ROLE_REVIEWER` as permission to delete any object.

**Exercise C — Data policy:** Replace the map with an R2DBC repository storing `tenant_id` and `doc_id`, tested with Testcontainers PostgreSQL. If using RLS, ensure the DB role has no bypass and the tenant context is scoped to the transaction.

**Exercise D — Invalid URIs:** Try `/documents/0`, `/documents/-1`, IDs exceeding `Long.MAX_VALUE`, and paths with special encoding. None may produce 500 or side effects from parsing.

**Exercise E — URI variables:** Change the security path matcher to `/workspaces/{workspaceId}/documents/{docId}` without updating the manager. Observe how missing `tenantId` triggers deny; fix the contract or manager.

**Exercise F — Direct manager testing:** Use `MockServerWebExchange`, `AuthorizationContext` with simulated variables, `StepVerifier`, and `Mono<Authentication>` to test authorization branches in isolation; keep `WebTestClient` integration tests afterward.

**Exercise G — Outage:** Have a reactive PDP return `Mono.error`; return 403/503 per policy without ever falling back to allow, and add metrics and trace IDs.

**Exercise H — Self-approve / self-delete:** Add an `APPROVE` policy with maker-checker rules; test method actions + owner/state and conditional writes to guard against TOCTOU.

## 13. Conclusion

`ReactiveAuthorizationManager<AuthorizationContext>` is the extension point for **HTTP authorization in Spring Security WebFlux**. It combines **reactive `Authentication`** with **`ServerWebExchange` and URI template variables**, letting you check authorities, HTTP methods, tenants, resources, and business policies without blocking the Reactor event loop.

Core structure:

```java
// WebFlux HTTP:
.pathMatchers(HttpMethod.GET, "/api/tenants/{tenantId}/documents/{docId}")
    .access(documentAuthorizationManager)

// Spring Security 6.5 Manager:
Mono<AuthorizationDecision> check(
    Mono<Authentication> authentication,
    AuthorizationContext context)
```

Safety rules: **deny explicitly when conditions are missing**, distinguish 401/403 from CSRF, never treat path tenant as a trusted identity, separate the HTTP gate from transaction/domain authorization, and test both allow and deny cases with `WebTestClient`. Remember to check Javadoc when upgrading from 6.5 to 7.x because `check(...)` is deprecated in 6.5.

## Official references

- Spring Security 6.5 — WebFlux HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 API — `ReactiveAuthorizationManager`, `check` and `authorize`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationContext`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Spring Security 6.5 API — `ServerHttpSecurity.AuthorizeExchangeSpec.Access.access`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security 6.5 — Reactive Method Security (distinct from HTTP manager): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Reactive WebTestClient authentication test: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — Reactive testing CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5 — Testing Spring Boot Applications and WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
