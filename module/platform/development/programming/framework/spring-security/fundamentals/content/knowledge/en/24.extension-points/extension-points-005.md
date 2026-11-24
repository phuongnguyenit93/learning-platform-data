# Building Custom Permission Policies with AuthorizationManager

## 1. Why Is a Custom Authorization Policy Needed?

A system often starts with a few simple rules: anyone logged in can view a profile, and users with the `ADMIN` role can open the admin page. Spring Security supports these rules via `authenticated()`, `hasRole(...)`, and `hasAuthority(...)`. However, permissions in real business logic often depend **simultaneously on the requester, the specific resource, and the context of the action**.

For example: a user may only view a document when the document belongs to the same organization (**tenant**) and the user is the **owner**; an administrator may view every document **within their own tenant**, without crossing into another tenant. This rule is difficult to express with `hasRole("USER")` alone, because a role cannot answer "who owns this document?" or "does the document's tenant match the requester's tenant?".

**`AuthorizationManager<T>`** is the standard extension point in Spring Security for writing an authorization decision based on business information. In this learning example, we build an `AuthorizationManager<RequestAuthorizationContext>` for each HTTP Servlet request. It receives information about the authenticated account and the current request, checks the policy, and returns **allow** or **deny**.

The policy question:

> "For user **U**, document **D**, and action **A**, is this request allowed?"

Sample rule:

```text
ALLOW when:
  a valid identity is present
  AND the document exists
  AND user's tenant == document's tenant
  AND (user is owner OR has role ADMIN)

DENY in all other cases.
```

This is **attribute-based access control (ABAC)** combined with roles (RBAC) and per-object permissions. `ADMIN` **does not automatically cross tenant boundaries**. The tenant check must happen **before** granting access by role.

## 2. Where AuthorizationManager Fits in Spring Security

For modern Servlet Spring Security:

1. The request passes through the configured `SecurityFilterChain`.
2. Authentication filters (e.g., HTTP Basic, form login, Bearer token) identify the account and produce an `Authentication` if credentials are valid.
3. `AuthorizationFilter` receives a `Supplier<Authentication>` and calls the authorization mechanism configured by `authorizeHttpRequests(...)`.
4. For a URL matching a `requestMatchers(...)` with `access(customAuthorizationManager)`, Spring Security invokes **the `AuthorizationManager` we wrote**, passing the account and `RequestAuthorizationContext`.
5. An `AuthorizationDecision(true)` result allows continuing to the controller; `AuthorizationDecision(false)` leads to denial and handling by the security exception mechanism.
6. Unauthenticated callers are normally prompted to authenticate (e.g., HTTP Basic returns **401**); authenticated callers lacking permissions normally receive **403**. Exact behavior depends on `AuthenticationEntryPoint`, `AccessDeniedHandler`, and the configured authentication filters.

`AuthorizationManager` only **makes a permission decision**. It should not write JSON/HTML directly, issue redirects, process passwords, or invoke controllers. Separating responsibilities makes policies easier to read, test, and reuse.

### Related Types

| Component | Role |
| --- | --- |
| `Authentication` | Identity from the authentication system; `getName()`, `getAuthorities()`, and principal type. |
| `Supplier<Authentication>` | Supplies `Authentication` when needed. Can defer fetching the identity for rules that do not require it. |
| `RequestAuthorizationContext` | HTTP context, including `getRequest()` and `getVariables()` to retrieve path parameters extracted by the matcher. |
| `AuthorizationDecision` | Result with `isGranted()` indicating allow or deny. |
| `AuthorizationManager<RequestAuthorizationContext>` | Custom policy attached via `.access(manager)` at the HTTP request level. |
| `AuthorizationFilter` | Invokes the authorization mechanism inside the filter chain. |
| `ExceptionTranslationFilter` | Translates access-denied exceptions to the corresponding entry point or handler when the exception occurs in the filter-managed flow. |

**Do not assume `Authentication.isAuthenticated()` is enough to know it is a real user.** With anonymous authentication, Spring Security may place an `AnonymousAuthenticationToken` whose `isAuthenticated()` flag is `true`. The sample policy must explicitly identify and reject anonymous callers.

### API Versions to Note

In **Spring Security 6.0–6.3**, the core method of the interface is:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);
```

Starting in **Spring Security 6.4**, `check(...)` is deprecated and an `authorize(...)` method returning `AuthorizationResult` is introduced to prepare for newer versions. In Spring Security **7.x**, class-based implementations typically need the `authorize(...)` signature matching the running version.

The example below uses a **lambda** as `AuthorizationManager<RequestAuthorizationContext>` and returns `new AuthorizationDecision(...)`. This relies on the *functional interface*, avoiding overriding `check`/`authorize` by name in the policy example. When copying into a project, verify the exact Spring Security version in your dependency tree; do not arbitrarily mix 6.x and 7.x APIs.

## 3. Designing the Policy Before Coding

Suppose the application has three documents:

| ID | Tenant | Owner | Content |
| --- | --- | --- | --- |
| `doc-a` | `acme` | `alice` | Document A |
| `doc-b` | `acme` | `bob` | Document B |
| `doc-c` | `globex` | `carol` | Document C |

Accounts with tenant memberships:

| Account | Valid tenant | Authority |
| --- | --- | --- |
| `alice` | `acme` | `ROLE_USER` |
| `bob` | `acme` | `ROLE_USER` |
| `carol` | `globex` | `ROLE_USER` |
| `admin` | `acme` | `ROLE_ADMIN` |

Learning requirement: `GET /api/documents/{documentId}` is allowed only when **the document exists**, the user **belongs to the same tenant**, and the user **is the document owner or an ADMIN in that tenant**.

Examples:

- `alice` views `doc-a` → **ALLOW**, same tenant and is the owner.
- `bob` views `doc-a` → **DENY**, same tenant but neither owner nor admin.
- `admin` views `doc-a` → **ALLOW**, same tenant and has `ROLE_ADMIN`.
- `admin` views `doc-c` → **DENY**, different tenant even though admin.
- `carol` views `doc-c` → **ALLOW**, same tenant and is the owner.
- Caller without credentials → **DENY**, HTTP Basic prompts for login.
- A non-existent ID → **DENY** immediately in the sample policy to avoid accidentally leaking document existence; representing 403/404 in real products requires a consistent dedicated policy.

We will keep data in memory to observe results. Real applications must fetch documents and tenant relationships from a database or trusted service, and **never trust a tenant ID self-declared by the client in a query parameter or header**.

## 4. Java 17+ Example: Writing an AuthorizationManager for Documents

This example targets **Spring Boot 3.x / Spring Security 6.x, Servlet application**. Create a project via Spring Initializr with **Spring Web** and **Spring Security** dependencies, using Java 17 or higher. Put **all code** in this exact file:

```text
src/main/java/demo/authz/DocumentPolicyApplication.java
```

This is a standalone Spring Boot program **inside a project that has the corresponding Spring libraries**. Bare `javac` lacks the classpath to compile it. No external database or authorization server is needed for the example.

```java
package demo.authz;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DocumentPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentPolicyApplication.class, args);
    }

    public record Doc(
        String id,
        String tenantId,
        String owner,
        String body
    ) {}

    static final class DocumentStore {
        private final Map<String, Doc> documents = Map.of(
            "doc-a",
            new Doc("doc-a", "acme", "alice", "Tai lieu A"),
            "doc-b",
            new Doc("doc-b", "acme", "bob", "Tai lieu B"),
            "doc-c",
            new Doc("doc-c", "globex", "carol", "Tai lieu C")
        );

        Doc find(String id) {
            return documents.get(id);
        }
    }

    static final class TenantDirectory {
        private final Map<String, String> tenants = Map.of(
            "alice", "acme",
            "bob", "acme",
            "carol", "globex",
            "admin", "acme"
        );

        String tenantOf(String username) {
            return tenants.get(username);
        }
    }

    @Bean
    DocumentStore documentStore() {
        return new DocumentStore();
    }

    @Bean
    TenantDirectory tenantDirectory() {
        return new TenantDirectory();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentPolicy(
            DocumentStore documents,
            TenantDirectory tenants) {

        return (authenticationSupplier, context) -> {
            Authentication auth = authenticationSupplier.get();

            // Unauthenticated or anonymous user.
            if (auth == null
                    || !auth.isAuthenticated()
                    || auth instanceof AnonymousAuthenticationToken) {
                return new AuthorizationDecision(false);
            }

            // Value extracted from the matched path.
            String id = context.getVariables().get("documentId");
            Doc doc = documents.find(id);
            if (doc == null) {
                return new AuthorizationDecision(false);
            }

            // Tenant must come from trusted server-side data.
            String userTenant = tenants.tenantOf(auth.getName());
            if (userTenant == null
                    || !userTenant.equals(doc.tenantId())) {
                return new AuthorizationDecision(false);
            }

            boolean owner = doc.owner().equals(auth.getName());
            boolean tenantAdmin = auth.getAuthorities().stream()
                .anyMatch(authority ->
                    "ROLE_ADMIN".equals(authority.getAuthority())
                );

            return new AuthorizationDecision(owner || tenantAdmin);
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> documentPolicy)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/documents/{documentId}"
                ).access(documentPolicy)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    static final class DocumentController {
        private final DocumentStore documents;

        DocumentController(DocumentStore documents) {
            this.documents = documents;
        }

        @GetMapping("/api/documents/{documentId}")
        public Doc getDocument(@PathVariable String documentId) {
            // Reached only after the manager grants access.
            // The map is immutable, so the checked document still exists
            // in this example.
            return documents.find(documentId);
        }
    }
}
```

### Code Explanation by Processing Flow

**1. `DocumentStore` and `TenantDirectory` simulate trusted data.** `DocumentStore` returns a document by ID. `TenantDirectory` maps an authenticated username to a tenant. When building a real system, replace these two classes with repositories or services with proper queries. The example intentionally avoids reading tenant IDs from client-supplied queries or headers.

**2. `documentPolicy(...)` is a Bean of type `AuthorizationManager<RequestAuthorizationContext>`.** The lambda's first parameter is `Supplier<Authentication>`; the second holds the HTTP request and path variables. The policy extracts the ID via:

```java
String id = context.getVariables().get("documentId");
```

The `documentId` variable comes directly from the `"/api/documents/{documentId}"` pattern registered in `requestMatchers(...)`. If you rename the variable in the matcher, you must update the key read from the context; otherwise `id` will be `null` and the policy will deny access.

**3. Check for anonymous before evaluating permissions.** Beyond `null` and the `isAuthenticated()` flag, the policy detects `AnonymousAuthenticationToken`. This prevents unauthenticated callers from slipping past the check simply because an anonymous token is marked "authenticated" at the Java object level.

**4. Check tenant before letting ADMIN pass.** This is a critical security boundary: a user with `ROLE_ADMIN` may only view documents belonging to their own tenant. Writing `owner || tenantAdmin` *after* the tenant check avoids this bug:

```java
// Wrong if ADMIN must not have cross-tenant privileges:
boolean allowed = isAdmin || (sameTenant && isOwner);

// Right for the example policy:
boolean allowed = sameTenant && (isAdmin || isOwner);
```

The snippet above only illustrates the logic; `isAdmin`, `sameTenant`, and `isOwner` are hypothetical variables, not additions to paste into the runnable program above.

**5. `hasRole("ADMIN")` and `ROLE_ADMIN` are related but not identical input strings.** `.roles("ADMIN")` creates the `ROLE_ADMIN` authority by default convention. The policy checks `"ROLE_ADMIN".equals(authority.getAuthority())`. Do not mistakenly check `"ADMIN"` when the actual authority carries the `ROLE_` prefix.

**6. Attach the policy with `.access(documentPolicy)`.** Here every `GET /api/documents/{documentId}` is decided by the custom policy; `.anyRequest().denyAll()` denies all remaining URLs or methods. Rules are evaluated in order, so specific rules must come before fallbacks.

**7. `httpBasic(...)` handles authentication, not the policy.** On each API call with username/password, Basic authentication identifies the user. Without credentials, the Basic result is typically **401** with `WWW-Authenticate`. When authenticated but denied by `AuthorizationManager`, the result is typically **403**. The example keeps Spring Security's default CSRF; the tests only use HTTP GET, so no CSRF changes are needed.

## 5. Running and Verifying the Policy

Start inside the generated Gradle project directory:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

If using Maven, run via the project's corresponding command (e.g., `./mvnw spring-boot:run`). Ensure a matching JDK is installed and the Spring Security dependency is present. When running from Windows PowerShell, use `curl.exe` if you want curl syntax, because the `curl` alias in some PowerShell versions points to a different tool.

Test each command:

```bash
curl -i http://localhost:8080/api/documents/doc-a

curl -i -u alice:alice123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u bob:bob123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u admin:admin123 \
  http://localhost:8080/api/documents/doc-a

curl -i -u admin:admin123 \
  http://localhost:8080/api/documents/doc-c

curl -i -u carol:carol123 \
  http://localhost:8080/api/documents/doc-c
```

Trailing `\` is the line-continuation symbol for Bash-style shells. In PowerShell, write each command on **a single line** and replace `curl` with `curl.exe`.

Verification table:

| Caller | Resource | Expected status | Reason |
| --- | --- | --- | --- |
| Anonymous | `doc-a` | **401** with HTTP Basic | No accepted identity yet |
| `alice` | `doc-a` | **200** | Same tenant, valid owner |
| `bob` | `doc-a` | **403** | Same tenant but neither owner nor admin |
| `admin` | `doc-a` | **200** | Admin belonging to tenant `acme` |
| `admin` | `doc-c` | **403** | Wrong tenant; ADMIN role does not unlock other tenants |
| `carol` | `doc-c` | **200** | Same tenant, valid owner |
| `alice` | `doc-missing` | **403** in the example | ID does not exist so the policy denies |
| `alice` | `POST /api/documents/doc-a` | **403** or configured denial handling | Method not allowed by the GET rule; if adding POST, check CSRF and dedicated handlers |

When `alice` successfully accesses `doc-a`, the JSON body is data-equivalent to:

```json
{
  "id": "doc-a",
  "tenantId": "acme",
  "owner": "alice",
  "body": "Tai lieu A"
}
```

Property order, headers, dates, and server-generated security headers may vary. What must be verified is the **HTTP status code** along with the data and correct access scope. Do not confuse "HTTP 200 with JSON content" with "the policy is definitely right"; test denied cases as well, especially **cross-tenant admin**.

### Why Does a Non-existent ID Return 403 Instead of 404?

In this lesson, `AuthorizationManager` denies immediately when `DocumentStore` does not find the ID, so the controller is never called. This approach can help limit resource enumeration via error messages, though not every product needs to return 403 for non-existent resources. An API may be designed to return 404 uniformly for both "does not exist" and "not allowed to know it exists", or return 403 for missing permissions and 404 for not found, depending on its information-disclosure policy.

**Do not resolve 403/404 by turning every error into `200` with a message in the body.** When changing the policy, keep consistency across endpoints and ensure resource existence is not leaked across tenants via status codes, response times, or error payloads.

## 6. Evaluation Rules and Common Pitfalls

### 6.1. "Deny by default" and returning explicit decisions

The policy returns `new AuthorizationDecision(false)` on every invalid branch: unauthenticated, missing document, unmapped tenant, wrong tenant, or lacking owner/admin permission. It returns `true` only when all required conditions hold.

`AuthorizationManager` can return **null** in certain APIs/versions when a manager abstains from deciding. Do not use `null` to express "block access" in business policies: how an abstention is interpreted can depend on coordinating components. For a decisive policy like the one in this lesson, return **allow or deny** explicitly.

### 6.2. Do not trust client-supplied data

Wrong:

```java
// WRONG ILLUSTRATION: tenant chosen by caller.
String userTenant = request.getHeader("X-Tenant-Id");
boolean allowed = userTenant.equals(document.tenantId());
```

A client can set `X-Tenant-Id` to another tenant. The tenant condition in this lesson comes from a mapping bound to the **authenticated identity**; in real systems, this mapping can come from a tenant-membership table, verified token claims, or another trusted identity mechanism. If an account belongs to multiple tenants, there must be an **active tenant** verified against the list of tenants the account actually belongs to.

Similarly, avoid taking `owner` from a request body as the sole basis for allowing a document update. Ownership must come from server-stored records or a trusted source.

### 6.3. Do not let ADMIN privileges exceed their defined scope

It is easy to mistakenly write:

```java
// Wrong: ROLE_ADMIN becomes a system-wide privilege.
return new AuthorizationDecision(
    hasAdminRole || (sameTenant && isOwner)
);
```

If an administrator manages only a single tenant, the right expression must be:

```java
return new AuthorizationDecision(
    sameTenant && (hasAdminRole || isOwner)
);
```

These two snippets are short logic examples with meaningful variables; they do not replace the complete code in section 4. The rule "can admin cross tenants?" must be defined in the permission model from the start, not inferred from the role name.

### 6.4. Do not rely solely on URL-level authorization for every operation

For the **read-only** API in the example, `AuthorizationManager<RequestAuthorizationContext>` can inspect the document by ID before the controller runs. In real applications, when adding **PUT/POST/DELETE**, pay special attention:

- Rules may depend on actual action data: the owner can read but cannot approve; only a team lead can approve a pending document.
- The document object may change after the filter check runs (**time-of-check/time-of-use**, TOCTOU risk).
- Operations inside services, background jobs, message listeners, or internal methods do not necessarily pass through the configured URL.

For critical state changes, check permissions at the **business/service boundary** against the appropriate record and transaction; you can use **method security** with `@EnableMethodSecurity` and `@PreAuthorize` or a matching `AuthorizationManager<MethodInvocation>`/interceptor. Do not assume an `AuthorizationManager<RequestAuthorizationContext>` for HTTP requests applies directly to every method invocation, because the context types differ.

### 6.5. Do not mix authentication, authorization, and error handling

- **Authentication** answers "who is this?": HTTP Basic, form login, Bearer token, etc.
- **Authorization** answers "what is allowed on which resource?": AuthorizationManager.
- **Error response handling** answers "return 401/403 as JSON, HTML, or redirect?": entry point and access-denied handler.

If you want the API to return Problem Details JSON for 401/403, configure `AuthenticationEntryPoint` and `AccessDeniedHandler` accordingly. Do not write `response.getWriter()` directly inside `AuthorizationManager` and do not set HTTP status 403 inside each policy branch.

### 6.6. Do not assume every 403 comes from the manager denying access

With POST/PUT/DELETE methods on an application with CSRF protection, requests missing a token may be blocked by `CsrfFilter` **before** the controller, even when the role is right. To test write-operation policies, manage the corresponding CSRF mechanism too. Avoid disabling CSRF protection globally to "make 403 go away"; even HTTP Basic can have credentials sent automatically by browsers and requires evaluating CSRF risk.

### 6.7. Performance, dependency failures, and data re-verification

An `AuthorizationManager` may query a database or policy service repeatedly. Issues to handle:

- **Per-request cost**: avoid N+1 queries, index by resource ID and tenant, and fetch only attributes needed for authorization.
- **Dependent system errors**: when a policy service is down, never allow by default just "so the app stays up". Design **fail-closed** behavior or a verified fallback mechanism.
- **Permission caching**: if caching is used, keys must include identity, tenant, resource, action, and policy version when needed; invalidation must exist when permissions or document state change.
- **Auditing**: record caller, action, resource ID, and decision per system requirements, without logging tokens, passwords, cookies, or secrets.
- **Data consistency**: check permissions against the exact record and state at the moment of mutation, especially under concurrent writes or permission changes.

## 7. Ways to Extend AuthorizationManager

### 7.1. Choosing rules by URL, method, and permissions

The sample policy uses:

```java
.requestMatchers(
    HttpMethod.GET,
    "/api/documents/{documentId}"
).access(documentPolicy)
```

If you add an update operation, you can build another `AuthorizationManager<RequestAuthorizationContext>` for `PUT`, or determine the **action** from the HTTP method and evaluate it inside the same policy service. Never assume `GET` and `DELETE` share equal permissions.

Conceptual example:

| Action | Authorized caller | Additional condition |
| --- | --- | --- |
| Read document | Owner or tenant admin | Same tenant |
| Edit content | Owner | Same tenant, status still editable |
| Approve document | Caller with `DOC_APPROVER` authority | Same tenant, document pending approval |
| Delete | Tenant admin | Same tenant and satisfies data-retention rules |

This is an **extension model**, not yet implemented in the GET program in section 4. When implementing, define the source of truth for roles, authorities, statuses, and actions.

### 7.2. Extracting policies into a testable check service

In larger systems, instead of putting all queries inside the manager, you can place business logic in a service such as `DocumentPermissionService`:

```java
// Signature illustration, not a standalone compilable class:
boolean canRead(Authentication auth, String documentId);
boolean canEdit(Authentication auth, String documentId);
```

`AuthorizationManager` becomes the glue: extract `Authentication`, extract `documentId` from the context, call `permissionService.canRead(...)`, and turn the boolean into a decision. The policy service can be tested with concrete data without mocking a full Servlet request.

However, do not treat a boolean-returning method as an automatic enforcement point. **Only where a manager/interceptor is attached, or where callers actively invoke the service and block on false, is the policy actually enforced.**

### 7.3. Combining conditions instead of using one overly broad role

Spring Security provides built-in `AuthorizationManager` implementations for authorities, authentication state, composite conditions, and request/method authorization. A custom policy is useful when **business attributes** cannot be expressed by a single role.

Multiple layers can be combined: require `authenticated()` for one group of endpoints, require a specific authority for another, attach `access(customManager)` on URLs needing fine-grained rules, and invoke business checks inside services when needed. The order of `requestMatchers(...)` decides which rule is chosen: **the first matching rule** is applied; consecutive rules must not be treated as a logical AND unless you explicitly configure composition inside the manager.

Buggy example:

```java
// Does NOT mean "both USER and satisfies customPolicy".
.requestMatchers("/api/documents/**").hasRole("USER")
.requestMatchers("/api/documents/{documentId}").access(documentPolicy)
```

Because `/api/documents/**` may match first, the custom rule is never evaluated for that URL. Attach the custom policy to the **specific rule first** or build a manager that checks all required conditions. The tenant condition in the sample policy **cannot** be replaced by a role.

### 7.4. Calling an external policy engine

In multi-service architectures, `AuthorizationManager` can also act as an adapter calling a policy decision point such as an internal service or policy engine. It sends the verified identity, action, resource, and required attributes, then translates the decision into allow/deny. This helps when policies are centrally governed, but requires handling inter-service authentication, timeouts, bounded retries, safe logging, caching/invalidation, and policy-engine outages.

Never forward the entire HTTP request containing credentials/tokens to an external service solely to check permissions; pass only the minimal verified attributes required by the security contract.

## 8. Testing the Policy with a Permission Matrix

A single test "Alice can view her own document" is not enough. Policies must test **both allowed and denied paths**, especially edge cases that risk cross-tenant data leaks.

| Test case | Expected result |
| --- | --- |
| No credentials calling `doc-a` | 401 (with HTTP Basic configured) |
| `alice` calling `doc-a` | 200 |
| `alice` calling `doc-b` | 403, same tenant but wrong owner |
| `bob` calling `doc-b` | 200 |
| `admin` calling `doc-a` and `doc-b` | 200, same tenant |
| `admin` calling `doc-c` | 403, different tenant |
| `carol` calling `doc-a` | 403, different tenant |
| Valid account without tenant mapping | 403, policy denies |
| Non-existent document | Denied per chosen contract; 403 in this example |
| POST to a GET-only endpoint | Disallowed by the GET policy; CSRF and fallback must be evaluated separately |

To test at the logic level, pass a `Supplier<Authentication>` and a `RequestAuthorizationContext` with controlled request/variables into the manager, then assert `AuthorizationDecision.isGranted()` for each case. For Servlet integration tests, use `MockMvc` with Spring Security Test or an appropriate HTTP client to verify the **actual status**. If `@PreAuthorize` is added on services, test method invocations and transactional behavior separately.

A test suite should catch at least three bugs:

1. **Role bypasses tenant**: an admin of tenant A can view tenant B's document.
2. **Inverted AND/OR condition**: a user in the same tenant who is not the owner can read merely because they are logged in.
3. **Mistaking anonymous for authenticated**: anonymous callers slip through because only `isAuthenticated()` was checked.

## 9. Checklist for Real Projects

1. Write the policy in business language first: who, which resource, which action, under what conditions and exceptions.
2. Identify trusted sources for `Authentication`, tenant, owner, role, and document status; clarify whether a user can belong to multiple tenants.
3. Pick enforcement points: URL with `AuthorizationManager<RequestAuthorizationContext>`, service with method security, or deliberate combination.
4. Deny by default when identity is missing, permissions are absent, data is ambiguous, or the policy service cannot return a trusted decision.
5. Bind the policy to the right matcher, HTTP method, and order; test both matching and non-matching requests.
6. Ensure admin rights do not cross tenants unless the model allows it; use actual authorities rather than assuming role names.
7. For write operations, re-check permissions against current state and transaction boundaries to prevent TOCTOU.
8. Standardize 401/403/404 per the API contract without leaking sensitive documents or tenants.
9. Include negative cases, cross-tenant cases, revoked-permission accounts, and mutating data in tests.
10. Monitor performance, auditing, and dependency failures; check the `AuthorizationManager` API version when upgrading Spring Security.

**Core takeaway:** `AuthorizationManager` is where **a business policy becomes an access decision**. Policy quality lies in verifying the right identity, right resource, right tenant, and right action, and denying when evidence is insufficient; attaching `.access(...)` is simply the step that plugs that decision into the Spring Security pipeline.

### Official Documentation

- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.3 — RequestAuthorizationContext API](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
