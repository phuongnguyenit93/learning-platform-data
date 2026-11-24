# HTTP 401, 403, 404 and Non-Disclosure Policy for Data Existence

> Scope: handling denied requests in APIs using Spring Security **Servlet**. This lesson distinguishes authentication errors, authorization errors, and non-existent resources; then applies a policy of returning 404 so callers cannot infer whether someone else's data exists. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x.

## 1. Objectives and Principles

After this lesson, you should be able to answer: (1) when to send 401, 403, 404; (2) how Spring Security translates authentication/authorization errors into HTTP responses; (3) when 403 can be replaced by 404; (4) how to design queries and tests so IDs, tenants, owners, or data states are not leaked.

**Authentication** answers "who is the caller?". **Authorization** answers "what is that caller allowed to do with which object, in what context?". An HTTP status is only a message sent to the client; it **does not replace** server-side permission checks. In APIs with private data, sometimes even the answer "this resource exists" is sensitive information.

For example, suppose an API has `GET /api/documents/10`. If document 10 belongs to Alice, Bob must not read it. When Bob guesses the number 10, the system can intentionally return the same response as for a non-existent ID so Bob cannot determine whether Alice has that document.

## 2. Exact HTTP Semantics

| HTTP | Standard Meaning | Common Scenarios | What the Client Should Understand |
|---|---|---|---|
| `401 Unauthorized` | Missing valid authentication credentials for the target resource | Not logged in, missing token, expired/invalid token | Need to provide or refresh appropriate credentials |
| `403 Forbidden` | Server understood the request but refuses to authorize it | Authenticated, missing role/scope/operation permission; another policy forbids it | Should not automatically resend with the same permissions expecting success |
| `404 Not Found` | Current representation not found **or** server does not wish to disclose that the resource exists | Wrong ID, deleted, or resource hidden by policy | Cannot conclude from the status alone that the object actually does not exist |

Important notes:

- The name `401 Unauthorized` is misleading: in practice it relates to **authentication**. Per RFC 9110, a 401 response **must** include at least one appropriate `WWW-Authenticate` challenge, such as `WWW-Authenticate: Basic realm="api"` or `WWW-Authenticate: Bearer realm="api"`. Writing status 401 without handling the challenge lacks proper HTTP semantics.
- `403` does not mean "not logged in". An authenticated caller lacking permissions is the common case. Policies such as blocking based on account status can also lead to 403.
- Per RFC 9110, a server is **permitted** to send `404` instead of `403` when it wants to hide the existence of a forbidden resource. This is an intentional design decision, not a rule that "every 403 case must be turned into 404".
- `404` may be heuristically cached in HTTP. For results related to private data, control `Cache-Control` and reverse proxy/CDN configurations to prevent sharing or retaining responses across user permissions.

### Three Axes to Separate

1. **Who is calling?** Missing valid credentials → 401 path at protected endpoints.
2. **Is that caller allowed to see the object's existence?** No permission to know the ID/object → typically return 404 identically to a non-existent ID.
3. **If allowed to know the object, do they have permission to perform the operation?** Knows the object exists, but not allowed to edit/delete/view a report → may return 403.

Do not call 404 "more secure" in an absolute sense. 404 only hides existence through **one response channel**; if the response body, latency, size, cache, list endpoints, public logs, or side notifications still leak information, the policy has not met its goal.

## 3. Decision Table for a Protected Endpoint

| Caller and Object State | Recommended Status | Reason |
|---|---:|---|
| Unauthenticated, calling `GET /api/documents/10` | 401 | Require login before evaluating the ID |
| Credentials provided but authentication fails | 401 | Invalid credentials |
| Alice has permission to read Alice's document 10 | 200 | Allowed, return data |
| Alice accesses non-existent ID 999 | 404 | No visible resource |
| Bob accesses Alice's ID 10, existence must remain secret | 404 | Resource is not visible to Bob |
| Alice knows her document 10, but her role cannot delete | 403 | Document is visible, operation is forbidden |
| Alice calls known admin endpoint `/api/admin/report` without role | 403 | Global operation forbidden, no private ID to hide |
| Calling a mistyped, non-existent route | 404 (typically) | No matching endpoint; filter order and security policy can affect the actual result |

This is **one sample policy** for a personal document API, not a rule applied identically to every system. If a resource's identity is public while its content is private, 403 may fit better than 404. If the resource's very existence is secret, fix a 404 choice for both non-existent IDs and non-visible IDs.

### Decision Flow

```text
Request enters protected endpoint
  ├─ Missing credentials / credential authentication failed?
  │    └─ 401 + appropriate WWW-Authenticate
  └─ Authenticated
       ├─ Object does not exist within the scope VISIBLE to the caller?
       │    └─ Common 404 for "does not exist" and "not visible"
       └─ Object is visible to the caller
            ├─ Not allowed to perform requested operation? → 403
            └─ Allowed? → proceed with business logic (200/201/204/... per operation)
```

It is not necessary to query the entire object first and check ownership afterward. A query constrained directly by the caller avoids accidentally bringing out-of-scope records into controllers, DTOs, public audits, or caches.

## 4. How Does Spring Security Servlet Actually Handle Denials?

High-level flow with `authorizeHttpRequests` and HTTP Basic/Bearer authentication:

```text
HTTP request
  → SecurityFilterChain
  → authentication filter (e.g., BasicAuthenticationFilter, BearerTokenAuthenticationFilter)
  → ExceptionTranslationFilter wrapping downstream filters
  → AuthorizationFilter / subsequent processing steps
  → DispatcherServlet → controller → service/repository
```

- `AuthorizationFilter` retrieves `Authentication` and uses `AuthorizationManager` to evaluate rules. When disallowed, it throws `AccessDeniedException` (or a subclass).
- `ExceptionTranslationFilter` does not make authorization decisions itself. It catches `AuthenticationException` and `AccessDeniedException` from downstream processing to route to a response mechanism.
- If authentication is required or an anonymous user is denied, `ExceptionTranslationFilter` invokes `AuthenticationEntryPoint`. HTTP Basic typically returns 401 with a challenge; form login apps may return **302 redirecting to the login page**, so do not assume every Spring Security system always returns 401.
- If an authenticated user is denied, it invokes `AccessDeniedHandler`; the typical behavior is 403.
- Authentication errors occurring directly inside an authentication filter can be routed by that filter straight to a failure handler/entry point. Not every 401 passes through the same `ExceptionTranslationFilter` branch.
- Method-layer checks (`@PreAuthorize`, `@PostAuthorize`) can also generate denials. For servlet requests passing through the Security filter chain, they can be translated into responses by the mechanism above; however, filter ordering, MVC exception handlers, and how you catch exceptions can change what is observed.

**Key point:** `AuthenticationEntryPoint` handles the authentication-needed branch; `AccessDeniedHandler` handles the permission-denied branch. The "someone else's resource → 404" policy usually has to occur in **business logic/object queries**; you should not force every `AccessDeniedException` across the entire application to become 404.

## 5. Runnable Example: How 401 / 403 / 404 Differ

Build a small application using **Spring Boot 3.3.x, Java 17, Spring Security 6.x**, and HTTP Basic to clearly observe the statuses. Data is in memory for learning only; real applications replace it with a repository scoped by tenant/owner and a secure authentication system.

Structure:

```text
build.gradle
src/main/java/demo/DenialDemoApplication.java
src/main/java/demo/SecurityConfig.java
src/main/java/demo/DocumentController.java
src/test/java/demo/DenialDemoApplicationTests.java
```

`build.gradle` (specific example versions; update patches appropriately for real use):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/java/demo/DenialDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DenialDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DenialDemoApplication.class, args);
    }
}
```

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alicepass")
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password("{noop}bobpass")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build()
        );
    }
}
```

Here `authenticated()` only requires the caller to have a valid identity; it **does not yet decide** whether Alice may read Bob's specific document. `hasRole("ADMIN")` is equivalent to checking the `ROLE_ADMIN` authority. `{noop}` storing plaintext passwords is **for demo purposes only**; never use it with real users.

`src/main/java/demo/DocumentController.java`:

```java
package demo;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final Map<Long, Document> documents = Map.of(
        10L, new Document(10L, "alice", "Alice's private document"),
        20L, new Document(20L, "bob", "Bob's private document")
    );

    @GetMapping("/api/documents/{id}")
    public ResponseEntity<DocumentResponse> read(
            @PathVariable long id, Authentication authentication) {

        // In-memory demo. With a DB, query directly by id + owner/tenant.
        return documents.values().stream()
            .filter(doc -> doc.id() == id
                && doc.owner().equals(authentication.getName()))
            .findFirst()
            .map(doc -> ResponseEntity.ok(
                new DocumentResponse(doc.id(), doc.title())))
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "Admin report";
    }

    private record Document(long id, String owner, String title) {}

    public record DocumentResponse(long id, String title) {}
}
```

Both **ID 10 not existing** and **ID 10 existing but Bob not allowed to see it** end with `ResponseEntity.notFound().build()`. The controller does not disclose any difference in the response body, nor does it return the owner/title of unauthorized documents. The admin endpoint illustrates 403 at the `AuthorizationFilter` layer.

### Running and Manual Verification

In a Gradle project with the wrapper and JDK 17+, run `./gradlew bootRun` (on Windows use `gradlew.bat bootRun`). With `curl`, print only the HTTP status:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/documents/10
# 401: missing credentials

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/documents/10
# 200: Alice sees her document

curl -s -o /dev/null -w '%{http_code}\n' -u bob:bobpass http://localhost:8080/api/documents/10
# 404: Bob is not allowed to see Alice's document

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/documents/999
# 404: ID does not exist for Alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:alicepass http://localhost:8080/api/admin/report
# 403: Alice does not have role ADMIN

curl -s -o /dev/null -w '%{http_code}\n' -u admin:adminpass http://localhost:8080/api/admin/report
# 200: admin has permission
```

The lines starting with `#` above are **expected outcomes**, not output captured from a running server. To inspect the challenge, run `curl -i http://localhost:8080/api/documents/10` and look for `WWW-Authenticate` in the 401 response. The default Basic configuration typically sends a `Basic` challenge. Do not store or print real credentials in logs/shell history.

### Regression Testing with MockMvc

`src/test/java/demo/DenialDemoApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DenialDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanRead() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void hiddenDocumentLooksMissing() throws Exception {
        mvc.perform(get("/api/documents/10"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingDocumentLooksMissing() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void knownAdminOperationIsForbidden() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }
}
```

Run `./gradlew test`. This is a test suite for **status decisions**. In a real system, add comparisons of JSON errors, headers, and cache policies for the "non-existent ID / hidden ID" pair; test tenant isolation, read/write permissions, disabled users, and each real authentication scheme.

## 6. Designing Existence Hiding in Business Logic

### 6.1. Query Within the Visible Scope

**Less secure pattern:**

```java
// Illustrative snippet, not a standalone Java program.
Document doc = repository.findById(id)
    .orElseThrow(() -> new NotFoundException("not found"));
if (!doc.getOwnerId().equals(currentUserId)) {
    throw new AccessDeniedException("document " + id + " belongs to another user");
}
return toDto(doc);
```

The snippet above distinguishes a non-existent ID from someone else's ID through 404/403 exception types. If the policy requires protecting existence, that difference is a signal enabling ID enumeration.

**Recommended pattern when owner/tenant determines visibility:**

```java
// Illustrative Spring Data JPA snippet; use entity/repository matching your project.
interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {
    Optional<DocumentEntity> findByIdAndTenantIdAndOwnerId(
        Long id, String tenantId, String ownerId);
}

// tenantId and ownerId must come from the authenticated principal/claims;
// do not trust values sent by the client if the client is allowed to spoof them.
return repository.findByIdAndTenantIdAndOwnerId(id, tenantId, ownerId)
    .map(this::toDto)
    .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
```

For both never-existing IDs and IDs outside the caller's scope, the repository returns `Optional.empty()`, so the API can produce **one** uniform 404 response. Do not query another tenant's record just to check "does it exist?". For lists, apply the owner/tenant filter in paginated queries and total counts; do not fetch everything and filter in the UI.

**Complex permission cases:** ownership is not the only condition (sharing, groups, ACLs, projects, delegated access). In that case, define a comprehensive "visible to principal" predicate, push it down to the query/policy layer, and then separately check operation permissions on the visible object. Avoid relying on a single role name to replace object-level checks.

### 6.2. Defining a Consistent Policy

Example record management product:

- **Visibility:** Alice sees her own records; project members granted `read` permission can see shared records.
- **Capability:** Someone with only `read` can GET, while PUT/DELETE return 403 since existence is already allowed to be known.
- **Non-visibility:** Users outside the project receive 404 at the specific record URL, identical to a non-existent ID.
- **General endpoints:** Admin APIs deny with 403 if a role is missing; do not hide everything as 404.
- **Not logged in:** Protected APIs return 401/challenge before looking up IDs, so no data is disclosed to anonymous callers.

If a resource has states like `deleted`, `archived`, or `suspended`, deciding whether those states are visible is also part of the visibility policy. Do not return 410 to someone not allowed to know the object ever existed; 410 confirms it "used to exist and is gone".

### 6.3. How to Avoid Leaks Through Other Channels

1. **Same status, body, and public metadata:** The "does not exist" / "not visible" pair should share a common body like `{"title":"Not Found","status":404}` or an empty body, with a message mentioning neither owner, tenant, "permission denied", nor internal IDs. Watch `Content-Length`, custom headers, and redirects too.
2. **Consistent reasonable execution paths:** Repeated latency differences can become an oracle. Scoped queries and proper indexes usually help reduce differences. Do not claim "constant time" without measurement evidence; compare latency distributions under representative load when risk is high.
3. **Prevent scanning:** Apply appropriate rate limits, monitor abnormal 404 rates, sequential ID guessing, and repeated errors. Random UUIDs reduce ID predictability but **do not replace permission checks**.
4. **Be careful with caching:** If a response depends on user, tenant, or token, do not let a CDN share that response. For private data APIs, consider `Cache-Control: private, no-store` per policy and verify actual headers across every gateway. Do not rely solely on framework defaults.
5. **No leaks from secondary endpoints:** GET, HEAD, download URLs, previews, exports, search, autocomplete, total counts, batch lookups, GraphQL, WebSockets, and attachment links must apply the same visibility policy. Do not let GET return 404 while HEAD returns 403 or export leaks filenames.
6. **Separate internal logs from public responses:** The server can audit the true reason (`missing`/`out_of_scope`/`forbidden`), authenticated principal/tenant, correlation ID, and applied rule. Do not log bearer tokens, passwords, sensitive content, or public logs revealing an object's owner.
7. **Do not turn every exception into 404:** DB errors, timeouts, mapping bugs, `NullPointerException`, or configuration errors are not "resource not found". Swallowing system errors into 404 distorts observability, hides bugs, and can create other leak channels.

## 7. Cases Easily Chosen Wrongly

### 401 vs. 403 in Bearer Tokens

With OAuth 2.0 Resource Server, Spring Security supports `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`:

- Missing token accessing a protected endpoint: 401 with `WWW-Authenticate: Bearer` (details need not be disclosed).
- Expired/invalid token: typically 401; Bearer challenge may include `error="invalid_token"` per RFC 6750.
- Valid token lacking scope to perform the operation: typically 403; Bearer challenge may include `error="insufficient_scope"`. Only disclose scope names when consistent with the information disclosure policy.

Do not use a custom `AccessDeniedHandler` to force every response into JSON 403 if it accidentally strips `WWW-Authenticate` or breaks how Spring Security handles Bearer errors. When replacing entry points/handlers, re-verify status, challenges, body, and error codes.

### 302 Is Not a 401 Error in Form Login

Web applications using `formLogin` may redirect anonymous users to the login page (302). That is intentional behavior for browsers, unlike JSON/Basic/Bearer APIs. Set test expectations according to each `SecurityFilterChain`'s actual authentication scheme.

### 403 Does Not Always Need to Be Changed to 404

If a user sees a ticket within the same team but cannot close the ticket, 403 clearly reflects "knows the ticket, not allowed to perform the action". If the user must not know the ticket exists, 404 is more appropriate. The choice lies in the product's **visibility policy**.

### Be Careful with Custom ExceptionHandlers

A `@ControllerAdvice` catching all `Exception` or all `AccessDeniedException` instances can produce responses different from `AuthenticationEntryPoint` / `AccessDeniedHandler` or expose `exception.getMessage()`. Only map well-defined business exceptions, let Spring Security handle security errors at the proper layer, and test real requests passing through filters.

### Route 404 and Object 404 Are Two Different Branches

A non-existent route may be rejected early by filters (especially with `anyRequest().authenticated()` or `denyAll()`). Do not infer from the status of an unknown URL that the controller ran. In real APIs, configure routing, security matching, and fallback handlers consistently with application requirements.

## 8. Design and Testing Checklist

| Check Question | What Must Be Achieved |
|---|---|
| Anonymous calls protected endpoint? | 401 + valid challenge for Basic/Bearer; or redirect matching form login contract |
| Wrong/expired credentials? | Rejected before business logic, no data accessed |
| Authenticated but not allowed to know resource? | Responds identically to a non-existent resource in public information |
| Allowed to know resource, but lacks operation permission? | Returns 403 consistent with policy |
| Are permissions checked directly on the object? | Query/policy constrains owner, tenant, ACL; not based solely on path roles |
| Do list, HEAD, search, export, download, and count share the same policy? | No secondary path leaks names/IDs/statuses/counts |
| Could 404 be cached wrongly across users? | Cache policy and CDN verified |
| Are there real tests through SecurityFilterChain? | Covers 401, 403, 404 hidden, 404 missing, 200 allowed, and related headers/bodies |
| Are logs/audits useful without leaking secrets? | Distinguishes internal reasons without disclosing them to unauthorized clients |

**Rule to remember:** `401` requires valid authentication; `403` says the request is forbidden; `404` can mean not found **or not allowed to know it exists**. A non-disclosure policy is only effective when applied across queries, related endpoints, bodies, headers, caches, and tests—not just by changing a single HTTP status code.

## 9. Standards and Official References

- [RFC 9110 – HTTP Semantics, sections 15.5.2–15.5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2): definitions of 401, 403, 404; permits 404 to hide existence.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage, section 3](https://www.rfc-editor.org/rfc/rfc6750.html#section-3): `WWW-Authenticate` and `invalid_token`, `insufficient_scope` errors.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `ExceptionTranslationFilter` and security filters.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` and `AuthorizationManager`.
- [Spring Security – Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): handling 401 and challenges in HTTP Basic.
- [Spring Security – Bearer Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): handling token failures.