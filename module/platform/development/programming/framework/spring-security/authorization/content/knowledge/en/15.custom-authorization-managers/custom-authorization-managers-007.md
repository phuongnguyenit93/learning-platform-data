# Registering a Manager via access at the HTTP Level

> **Scope:** Spring Security – authorization → **Custom AuthorizationManager**. The focus is registering an `AuthorizationManager<RequestAuthorizationContext>` in `SecurityFilterChain` configuration via `authorizeHttpRequests(...).requestMatchers(...).access(manager)` to decide permissions on **HTTP servlet requests**. Java 17+ examples use Spring Boot 3.x and Spring Security 6.x; notable API changes in Spring Security 7.x are explained separately.

## 1. The Problem: Access Depends on Both User and Resource in the URL

An API has the following routes:

~~~text
GET /api/public/ping           → public
GET /api/documents/101         → requires DOC_READ and owner of document 101
GET /api/documents/202         → requires DOC_READ and owner of document 202
All other requests             → denied by default
~~~

Suppose `alice` owns document `101` and `bob` owns `202`. Using only:

~~~java
.requestMatchers("/api/documents/**").hasAuthority("DOC_READ")
~~~

would let anyone with `DOC_READ` pass the HTTP check for **every** document, even if they are not the owner. To evaluate both `Authentication` and server-stored resource state, we put the logic into a custom authorization manager and register it with `.access(...)`.

Skeleton example:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
);
~~~

This means **a request matching the HTTP method + path is handed to the manager for a decision**. `.access(...)` accepts an object implementing `AuthorizationManager<RequestAuthorizationContext>`; it is not a URL, not a role, and not a bean name written as a SpEL string.

## 2. Components in the Processing Pipeline

~~~text
HTTP request
    |
    v
Spring Security FilterChainProxy
    |
    +-- authentication filters (Basic, Bearer, session, ...)
    |
    v
AuthorizationFilter
    |
    | Supplier<Authentication>, HttpServletRequest
    v
RequestMatcherDelegatingAuthorizationManager
    |
    | try requestMatchers in order
    v
Matching rule: .access(documentReadManager)
    |
    | RequestAuthorizationContext(request, path variables)
    v
documentReadManager
    |
    +-- get Authentication when needed
    +-- get documentId from matched URL
    +-- check permission + data from trusted source
    |
    +-- allow -> proceed to controller
    |
    +-- deny  -> AccessDeniedException
                   |
                   v
            ExceptionTranslationFilter
            -> HTTP 401/403 depending on auth state and entry point
~~~

Concepts to distinguish:

| Component | Function |
| --- | --- |
| `SecurityFilterChain` | Defines the filters protecting requests; built by `HttpSecurity.build()` |
| `authorizeHttpRequests` | Declares authorization rules at the HTTP layer |
| `requestMatchers` | **Selects which requests** a rule applies to, by path, HTTP method, or custom matcher |
| `.access(manager)` | **Selects how decisions are made** for matched requests |
| `AuthorizationManager<RequestAuthorizationContext>` | Function deciding allow or deny |
| `Supplier<Authentication>` | Allows deferring retrieval of user info until needed |
| `RequestAuthorizationContext` | Holds `HttpServletRequest` and path variables extracted by the matcher |
| `AuthorizationDecision` | Object representing the `granted = true/false` decision |
| `AuthorizationFilter` | Applies the result to let the request proceed or block it |

**Distinguish "match" from "authorize":** a request matching `GET /api/documents/{documentId}` only means it enters the manager for that route. Matching the path **does not mean access is granted**.

## 3. Most Important Rules When Declaring `.access(...)`

### 3.1. Write the Manager with the Right Context Type

In Spring Security Servlet:

~~~java
AuthorizationManager<RequestAuthorizationContext> documentReadManager = /* ... */;
~~~

`RequestAuthorizationContext` lives in package:

~~~java
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
~~~

Two commonly used data points:

~~~java
context.getRequest()               // HttpServletRequest
context.getVariables()             // Map<String, String> from request matcher
context.getVariables().get("documentId")
~~~

Do not confuse it with `MethodInvocation` in Method Security or `ServerWebExchange` in WebFlux. Reactive APIs use `ReactiveAuthorizationManager<AuthorizationContext>` and a different DSL; the Servlet snippets in this lesson cannot be applied directly to a WebFlux application.

### 3.2. Rules Are Evaluated in Order; First Match Decides

Wrong example:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
)
~~~

`/api/**` comes first and permits `GET /api/documents/101`, so the custom manager **is never called**. This is a serious authorization flaw even if the manager itself is written accurately.

Put narrower rules before broader rules. If permitting a public path, keep its scope tight:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .access(documentReadManager)
    .anyRequest().denyAll()
)
~~~

`anyRequest().denyAll()` is a safety net for undeclared endpoints. For a service intentionally exposing only a specific set of APIs, it reduces the risk of accidentally exposing endpoints when new controllers are added.

### 3.3. `securityMatcher` Differs from `requestMatchers`

`http.securityMatcher("/api/**")` decides **which requests this entire SecurityFilterChain applies to**. Meanwhile, `requestMatchers("/api/documents/**")` only selects **rules within an already-chosen chain**.

With multiple `SecurityFilterChain`s, Spring Security picks the first chain matching `securityMatcher` according to chain order. If no chain matches, requests may fall outside the authorization gates under review. Therefore, never treat `anyRequest().denyAll()` inside a chain protecting only `/api/**` as a catch-all for the entire application. Check fallback chains and `@Order` as well.

## 4. Building a Complete Spring Boot Example

This example is database-independent: an in-memory repository holds two documents so we can observe the policy. Rule: the request must be authenticated, the caller must have the exact authority `DOC_READ`, and the document must belong to the caller. If the ID is invalid or the document is not found, the manager **denies**.

The example uses **Spring Boot 3.x + Spring Security 6.x**, Java 17+. You need a Gradle Spring Boot project with the `org.springframework.boot` plugin and appropriate dependency management. If using Spring Boot 4/Security 7, review the version section before changing APIs or pinning dependencies.

### 4.1. Declaring Dependencies

In the `build.gradle` of an existing Spring Boot project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

You do not need `@EnableMethodSecurity` to use authorization at the HTTP layer: they are two separate configuration boundaries. `@EnableMethodSecurity` is only needed when using annotations like `@PreAuthorize` on services.

The Java files below use package `demo.httpauth`. Sharing a package lets `@SpringBootApplication` discover beans, controllers, and configurations.

### 4.2. Application

**`src/main/java/demo/httpauth/HttpAuthApplication.java`**

~~~java
package demo.httpauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthApplication.class, args);
    }
}
~~~

### 4.3. Document and Data Store

**`src/main/java/demo/httpauth/Document.java`**

~~~java
package demo.httpauth;

public record Document(long id, String owner, String title) {
}
~~~

**`src/main/java/demo/httpauth/DocumentStore.java`**

~~~java
package demo.httpauth;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101L, "alice", "Alice document"),
        202L, new Document(202L, "bob", "Bob document")
    );

    public Optional<Document> findById(long documentId) {
        return Optional.ofNullable(documents.get(documentId));
    }
}
~~~

Owner data comes from a trusted repository, **not from client-sent query parameters or headers**. In a real project, check by immutable user ID and verified tenant rather than treating usernames as permanent identifiers.

### 4.4. Extracting Business Rules into a Dedicated Class

**`src/main/java/demo/httpauth/DocumentHttpPolicy.java`**

~~~java
package demo.httpauth;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentHttpPolicy {
    private final DocumentStore store;

    public DocumentHttpPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, String rawId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean hasReadAuthority = authentication.getAuthorities().stream()
                .anyMatch(authority -> "DOC_READ".equals(authority.getAuthority()));
        if (!hasReadAuthority || rawId == null) {
            return false;
        }

        final long documentId;
        try {
            documentId = Long.parseLong(rawId);
        } catch (NumberFormatException invalidId) {
            return false;
        }

        return store.findById(documentId)
                .map(document -> document.owner().equals(authentication.getName()))
                .orElse(false);
    }
}
~~~

Here `DocumentHttpPolicy` is a plain Java class returning `boolean`. It accepts `Authentication` and the ID extracted from the URL by the matcher. Its protective steps include:

1. Rejecting anonymous, unauthenticated, and missing authentication.
2. Checking the `DOC_READ` authority **as an exact string**, without confusing it with role `ROLE_DOC_READ`.
3. Handling non-numeric IDs or missing path variables with `false`, avoiding 500 errors from parsing.
4. Looking up the document on the server; if absent, returning `false`.
5. Comparing the document's real owner with the authenticated identity.

In a real application, you must account for tenants, lock states, permission changes, and transactions; this simple example only illustrates HTTP-layer decisions.

### 4.5. Registering `AuthorizationManager` via `@Bean`

**`src/main/java/demo/httpauth/SecurityConfig.java`**

~~~java
package demo.httpauth;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentReadManager(
            DocumentHttpPolicy policy) {

        return (authenticationSupplier, context) -> {
            // Supplier fetches Authentication when the manager actually needs it.
            var authentication = authenticationSupplier.get();
            String rawId = context.getVariables().get("documentId");

            return new AuthorizationDecision(policy.canRead(authentication, rawId));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Qualifier("documentReadManager")
            AuthorizationManager<RequestAuthorizationContext> manager)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
                    .access(manager)
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Key details to understand:

- `@Bean` returns **one instance** of type `AuthorizationManager<RequestAuthorizationContext>`. The `SecurityFilterChain` configuration receives it via dependency injection. `@Qualifier("documentReadManager")` prevents ambiguity if the application later defines multiple authorization managers.
- `.requestMatchers(HttpMethod.GET, ".../{documentId}")` applies this rule only to **GET** requests on matching paths. The `documentId` variable comes from the matcher, not from manually string-splitting `request.getRequestURI()`.
- `.access(manager)` binds the registered manager to the rule. Only that rule calls `DocumentHttpPolicy` logic.
- `.anyRequest().denyAll()` denies undeclared requests; if you want to allow another endpoint, declare its rule explicitly.
- `.httpBasic(...)` is a simple authentication mechanism for trying the example. HTTP Basic must run over HTTPS in real environments; for APIs using JWT/sessions, replace it with the appropriate authentication mechanism while reusing the manager pattern.
- The example does not disable CSRF. GET requests are used for illustration; when adding POST/PUT/DELETE, verify both CSRF policy and authentication type rather than blindly disabling CSRF protection application-wide.

**Why does the example use a lambda?** `AuthorizationManager` is a functional interface, yet its abstract method signature changed across version lines. A lambda with an explicit target type returning `AuthorizationDecision` keeps code concise and more easily compatible across Spring Security 6.5 and 7.x. If you need to inject multiple services, manage controlled caching, or add helper methods, you can implement a separate `@Component` class; section 7 explains the two signature versions.

### 4.6. Controller Serving HTTP Requests

**`src/main/java/demo/httpauth/DocumentController.java`**

~~~java
package demo.httpauth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DocumentController {
    private final DocumentStore store;

    public DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{documentId}")
    public Document read(@PathVariable long documentId) {
        return store.findById(documentId).orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

If the manager denies, execution **never reaches** the body of `read`. If the manager allows yet the document is deleted between check time and controller read time, the controller returns 404 via its own branch. Real systems must close the gap between check and use for sensitive resources; see section 9.

## 5. Testing Real HTTP Through `MockMvc`

To verify that the rule is registered and the manager actually runs, tests must go through the **filter chain**, not merely call `new DocumentHttpPolicy(...)`. Spring Security Test provides `@WithMockUser` to simulate authenticated users for tests.

**`src/test/java/demo/httpauth/DocumentHttpAuthorizationTest.java`**

~~~java
package demo.httpauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = HttpAuthApplication.class)
@AutoConfigureMockMvc
class DocumentHttpAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicPingIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk());
    }

    @Test
    void privateDocumentRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerWithReadAuthorityCanAccessDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void otherOwnerIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void ownerWithoutReadAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void bobCanAccessHisDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(202));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingDocumentIsDeniedByTheManager() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void malformedDocumentIdIsDenied() throws Exception {
        mvc.perform(get("/api/documents/not-a-number"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Result explanation:** with no credentials on an endpoint requiring login, HTTP Basic returns `401 Unauthorized`; when authenticated yet failing the policy, the filter returns `403 Forbidden`. Exact differentiation depends on `AuthenticationEntryPoint`, `AccessDeniedHandler`, and actual authentication configuration; the tests above verify the sample configuration's behavior.

The non-existent ID test expects `403` because the policy is designed to return `false` before the controller runs. Another application may choose 404 for unauthorized resources to avoid leaking existence, yet must do so consistently without letting the controller open a path past the policy.

Run from the Spring Boot-configured Gradle project directory:

~~~text
./gradlew test --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

The sample classes do not call `System.out.println`, so there is no fixed business stdout. The goal is all assertions green and Gradle completing `test`. If another project uses a context path, extra filter chains, or a different authentication mechanism, update tests to match the real setup before drawing conclusions.

## 6. Unit Testing Manager Logic and Fail-Closed Verification

HTTP tests confirm the filter chain enforces the gate; additionally, write unit tests for the policy to exercise every branch quickly:

**`src/test/java/demo/httpauth/DocumentHttpPolicyTest.java`**

~~~java
package demo.httpauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentHttpPolicyTest {
    private final DocumentHttpPolicy policy =
            new DocumentHttpPolicy(new DocumentStore());

    private Authentication user(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "unused",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void requiresOwnershipAndAuthority() {
        assertTrue(policy.canRead(user("alice", "DOC_READ"), "101"));
        assertFalse(policy.canRead(user("bob", "DOC_READ"), "101"));
        assertFalse(policy.canRead(user("alice", "OTHER"), "101"));
    }

    @Test
    void missingOrMalformedResourceIsDenied() {
        assertFalse(policy.canRead(user("alice", "DOC_READ"), "999"));
        assertFalse(policy.canRead(user("alice", "DOC_READ"), "xyz"));
        assertFalse(policy.canRead(user("alice", "DOC_READ"), null));
    }

    @Test
    void absentAuthenticationIsDenied() {
        assertFalse(policy.canRead(null, "101"));
    }
}
~~~

The unit test above instantiates `DocumentHttpPolicy` directly and **cannot verify** whether `SecurityFilterChain` registered the manager; therefore, never drop the `MockMvc` tests.

You can run both test suites:

~~~text
./gradlew test --tests demo.httpauth.DocumentHttpPolicyTest --tests demo.httpauth.DocumentHttpAuthorizationTest
~~~

A safe HTTP policy should cover **non-existent resource**, **malformed ID**, **unauthenticated**, **missing authority**, **non-owner**, and **allowed** cases. If an unexpected branch cannot determine permission, deny explicitly. Never catch all exceptions and return `new AuthorizationDecision(true)` just to "keep the system running."

## 7. `AuthorizationManager` API by Version: `check` and `authorize`

This is an error-prone detail when copying an old Spring Security example into a newer version.

| Spring Security line | Notable contract | Notes |
| --- | --- | --- |
| **6.0–6.3** | `AuthorizationManager` uses `check(Supplier<Authentication>, T)` returning `AuthorizationDecision` or `null` | Implementing classes normally override `check` |
| **6.4–6.5** | Added `authorize(Supplier<Authentication>, T)` returning `AuthorizationResult`; `check` remains yet is marked deprecated | When migrating versions, inspect the interface and prefer the API-recommended form |
| **7.x** | Primary method is `authorize(Supplier<? extends Authentication>, T)` returning `AuthorizationResult`; legacy `check` removed from contract | Custom classes overriding `check` from 6.x cannot be used unchanged |

A custom class written for **Spring Security 6.5** may look like:

~~~java
// Illustrated specifically for 6.5; no need to add to the section 4 example.
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        RequestAuthorizationContext context) {
    // ... check permissions and resource
    return new AuthorizationDecision(false);
}
~~~

In **Spring Security 7.x**, the signature becomes:

~~~java
// Illustrated specifically for 7.x; import AuthorizationResult and matching Supplier type.
@Override
public AuthorizationResult authorize(
        Supplier<? extends Authentication> authentication,
        RequestAuthorizationContext context) {
    // ... check permissions and resource
    return new AuthorizationDecision(false);
}
~~~

These two snippets only show the method placed **inside** a corresponding implementation, not two methods to copy together into one class.

Because `AuthorizationDecision` implements `AuthorizationResult` in newer lines, a properly typed lambda:

~~~java
AuthorizationManager<RequestAuthorizationContext> manager =
        (authentication, context) -> new AuthorizationDecision(false);
~~~

is a concise way to write simple decisions without maintaining different method signatures between the two API lines. Even so, always **compile and run tests against your locked Spring Security version**; do not treat lambda similarity as a guarantee across all framework changes.

If a custom manager returns `null` in an API allowing abstain, that is not `true`. Abstain semantics depend on the caller and composition; at strict enforcement boundaries, return an **explicit allow/deny** result. The section 4 example always returns `AuthorizationDecision(boolean)`.

## 8. When to Use `.access(manager)` Instead of Built-In Rules?

| Requirement | Sensible expression |
| --- | --- |
| Public endpoint | `permitAll()` |
| Only requires a logged-in user | `authenticated()` |
| One fixed authority | `hasAuthority("DOC_READ")` |
| Default role | `hasRole("ADMIN")` matching `ROLE_ADMIN` authority under default prefix |
| Require a set of authorities | A composed manager like `allOf(...)` or version-appropriate config rule |
| Need user + owner + resource state + tenant | `.access(customAuthorizationManager)` |
| Group of URLs calling the same policy engine | Register one shared manager across matching matchers |
| Rule depends on service result/action content | Combine with `@PreAuthorize`/`@PostAuthorize` or enforce at domain/service boundary |

Not every condition needs a custom class. For concise `hasAuthority("DOC_READ")`, built-ins are easier to read. Introduce a dedicated manager only when you need **stateful/resource-aware logic**, lookups, or a policy reused in multiple places.

Example placing a manager on one rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
    .access(documentReadManager)
~~~

You can use a manager on `anyRequest()` when every request in the chain genuinely needs the same policy:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .anyRequest().access(sharedPolicy)
)
~~~

However, `RequestAuthorizationContext.getVariables()` may then **lack the `documentId` variable** because the matcher is `anyRequest()`. If a policy expects a path variable, it must handle missing variables safely; e.g., `DocumentHttpPolicy` returns `false`. **Never blindly reuse a path-ID-dependent manager for every URL.**

For endpoints sharing a path across multiple methods, create dedicated managers for read/write actions or pass structured operations into the policy; never permit all HTTP methods just because they share a path. When relying on `GET`/`POST`/`DELETE`, test each method along with appropriate CSRF/transaction constraints.

## 9. Practical Considerations

### 9.1. Do Not Trust Client-Asserted Owner Data

Conceptually flawed example:

~~~java
// Never treat owner in the request as proof of permission.
String ownerFromQuery = request.getParameter("owner");
boolean allowed = ownerFromQuery.equals(authentication.getName());
~~~

The caller chooses `owner`; it does not prove the document belongs to them. A proper policy extracts `documentId` from the matched URL, fetches the document from the repository, and compares the owner from **trusted data** against the authenticated identity. In multi-tenant apps, the tenant ID must also come from a verified source, never solely from arbitrary headers.

### 9.2. Matcher Path Variables vs. Controller Path Variables

`context.getVariables().get("documentId")` is extracted by Spring Security's request matcher. `@PathVariable("documentId")` in a controller is resolved by Spring MVC when the controller runs. They often use the same URL template, yet happen at **two separate processing stages**.

Do not assume the manager has access to `HandlerMethod` or controller parameter binding results. Inside the filter chain, the MVC handler may not have run yet. If a matcher does not support capturing variables, `getVariables()` may be empty. Use a specific `RequestMatcher` that supports variable extraction, or design the manager without depending on matcher variables.

`context.getRequest()` provides `HttpServletRequest` to read HTTP method, path, headers, or remote address if genuinely required. Be careful with proxies/load balancers when using IPs; never trust `X-Forwarded-For` directly unless infrastructure properly configures forwarded headers and trusted proxies.

### 9.3. Potential Double Data Reads

In the example, the manager queries the repository to verify ownership; then the controller reads the document again to return the response. With a real database:

~~~text
T1: manager reads document 101, owner=alice -> allow
T2: another transaction changes owner or tenant
T3: controller re-reads modified document 101 -> may return unauthorized data
~~~

This is **time-of-check/time-of-use**. For sensitive resources, enforce control via transactions, queries constrained directly by owner/tenant at the data layer, locking/optimistic locking, or unified check-and-fetch/update mechanisms. Filter-level authorization does not guarantee database state stays unchanged throughout request processing.

Additionally, per-request manager checks can cause duplicate/N+1 queries when checking multiple objects per request. Use minimal repository projections, carefully keyed per-user/tenant caches, and measure query counts; never cache "allow" decisions by document ID alone without binding identity and policy version.

### 9.4. HTTP Policies and Method Policies Do Not Replace Each Other

`authorizeHttpRequests(...).access(manager)` protects requests **passing through the web security filter chain**. Yet the same service can be invoked by jobs, message consumers, tests, schedulers, or internal code bypassing HTTP. For sensitive business logic, you also need **gates at the service/domain/data layer**.

`@PreAuthorize` uses Spring Method Security and proxies; `AuthorizationManager<RequestAuthorizationContext>` uses the HTTP request context. You can reuse a **plain Java policy service** across both gates, while never confusing the two generic contexts. For example, `DocumentHttpPolicy` isolates business evaluation and can be adapted to another layer once its parameters are cleanly designed.

### 9.5. HTTP 401, 403, 404 and Controlling Information Disclosure

Typically:

- **401 Unauthorized**: request lacks proper authentication; `AuthenticationEntryPoint` starts authentication (e.g., Basic challenge).
- **403 Forbidden**: caller is authenticated yet lacks permission; `AccessDeniedHandler` responds.
- **404 Not Found**: path/resource does not exist in the application contract; some systems deliberately return 404 for unauthorized resources to avoid revealing existence.

Do not equate `AuthorizationDecision(false)` with a hardcoded HTTP status. Filters and exception handling determine the status based on authentication configuration. Tests must verify the full path. Security logs should record actor ID, resource ID, and outcome safely without logging tokens or sensitive payloads.

### 9.6. Dispatcher Types, Error Dispatches, and Multiple Filter Chains

`AuthorizationFilter` may run for dispatches like `REQUEST`, `FORWARD`, `ERROR`, and `INCLUDE` depending on configuration and environment. When error handling triggers a new `ERROR` dispatch, `anyRequest().denyAll()` can deny that dispatch, preventing error pages from rendering as expected. You can declare deliberately:

~~~java
// Illustrative only if the application genuinely needs forward/error dispatches.
.dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
    .permitAll()
~~~

Evaluate what permitting these dispatcher types means for your application instead of copying mechanically. In apps with multiple servlets or non-default servlet paths, configure matchers accordingly; newer Spring Security docs cover `PathPatternRequestMatcher`.

With multiple `SecurityFilterChain`s, ensure every sensitive endpoint matches **a gated chain**. One chain might have `securityMatcher("/internal/**")` while another covers remaining URLs; set `@Order` properly and test endpoints both inside and outside each chain. `anyRequest().denyAll()` in one chain does not protect paths that chain never matches.

### 9.7. CSRF and Authentication

This lesson uses HTTP Basic and GET without disabling CSRF. When adding state-changing HTTP methods, review `CsrfFilter`, CORS, cookies/sessions, and credential sources. For pure bearer-token apps not relying on cookies, CSRF design may differ. Never add `csrf.disable()` just to make a POST test pass without understanding the threat model.

## 10. Common Pitfalls When Registering a Manager via access

| Symptom | Possible cause | How to check / fix |
| --- | --- | --- |
| Manager is never invoked | Broad `permitAll` rule placed earlier or request misses the chain | Check `requestMatchers` and `securityMatcher` ordering; add real route tests |
| `getVariables().get("documentId")` is null | Matcher does not capture variables, placeholder name differs, or `anyRequest()` used | Match placeholder names and matcher type; deny by default when variable is missing |
| Every ID is permitted | Checked authority only without verifying server-side owner | Verify ID → resource → real owner/tenant |
| 500 when URL contains non-numeric ID | Unhandled `Long.parseLong` | Return explicit deny or use a stricter matcher |
| 403 when expecting 401 or vice versa | Authentication entry point, anonymous config, or another filter chain | Run MockMvc logged out/logged in; inspect entry point |
| New endpoints are open by default | `anyRequest().permitAll()` or overly broad `/api/**` | Use deny-by-default for tightly controlled chains |
| Spring Security 7 errors when overriding `check` | API moved to `authorize` | Update custom class signature or use a target-typed lambda |
| Ambiguous manager bean on injection | Multiple `AuthorizationManager<RequestAuthorizationContext>` beans | Name beans clearly and use `@Qualifier` |
| Manager relies on controller state and cannot find `@PathVariable` | Authorization runs in filter before MVC handler | Use `RequestAuthorizationContext.getVariables()` |
| Policy allows when repository errors | Catch-all returns allow or broad fallback | Fail closed; separate infrastructure errors from authorization decisions |
| HTTP rules work yet a background job reads unauthorized data | Job bypasses web filter chain | Protect the corresponding service/domain/data layer |
| Policy unit tests pass yet URL remains open | Misregistered in `SecurityFilterChain` | Add MockMvc tests traversing the entire filter chain |
| Request routed through another chain skips policy | Multiple chains with overlapping/misordered `securityMatcher` | Check chain selection and integration-test routes |
| Wrong context type in lambda | Mixing `MethodInvocation`/reactive `AuthorizationContext` into Servlet | Use `RequestAuthorizationContext` for `authorizeHttpRequests` |

## 11. Reinforcement Exercises

**Exercise 1 – Prove rule ordering.** Temporarily place `.requestMatchers("/api/**").permitAll()` above the document rule. Run `otherOwnerIsForbidden` and observe that it no longer enforces the gate; restore the order and verify the test passes. Explain why the manager was correct yet the route remained open.

**Exercise 2 – Separate write permission by HTTP method.** Add `PUT /api/documents/{documentId}` requiring `DOC_EDIT` and ownership, with a dedicated manager or `canEdit` policy method. Ensure `GET` does not accidentally grant `PUT`. Write a test confirming a user with `DOC_READ` but missing `DOC_EDIT` cannot edit.

**Exercise 3 – Multi-tenancy.** Add a tenant ID to `Document` and trusted principals. Write a test proving `alice` in tenant A cannot read a document in tenant B even with a matching username. Never accept tenant solely from unverified query parameters.

**Exercise 4 – Missing path variable.** Register a manager expecting `documentId` on `anyRequest()` in a test environment; inspect what `getVariables()` contains and how the policy returns `false`. Redesign the matcher for the right request set.

**Exercise 5 – Upgrade regression check.** Run the full test suite on your pinned Spring Security version, check whether `AuthorizationManager` uses `check` or `authorize` when writing class implementations, and verify code using `.access(manager)` still enforces the gate after upgrading.

**Completion criteria:** declare an `AuthorizationManager<RequestAuthorizationContext>` bean, bind it with `requestMatchers(...).access(manager)`, understand first-match rule evaluation, read path variables safely, return deny-by-default decisions, distinguish HTTP 401/403, and write `MockMvc` tests covering both allowed and blocked paths.

## References

- Spring Security 6.5 – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 – **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security – **Authorization Architecture**, `AuthorizationManager` and `AuthorizationDecision`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security 6.5 API – **AuthorizationManager**: https://docs.spring.io/spring-security/site/docs/6.5.4/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 7.0 API – **AuthorizationManager**: https://docs.spring.io/spring-security/site/docs/7.0.0/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security API – **RequestAuthorizationContext**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html
