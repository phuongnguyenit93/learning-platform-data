# AuthorizationManager and the Access Decision Model in Spring Security

> **Topic:** Spring Security – fundamentals → **Authorization**. This document focuses on the mechanism that decides whether a user is allowed to perform an action on a specific resource; how Spring Security makes decisions at HTTP request, method, and object levels; and how to build safe, testable, and extensible rules when needed.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **authentication** (identity verification) from **authorization** (access decision).
2. Describe the flow `Authentication` → `AuthorizationManager` → grant/deny/abstain → execute or reject.
3. Understand the `AuthorizationManager<T>`, `AuthorizationResult`, `AuthorizationDecision`, `Supplier<Authentication>`, and protected object `T` interfaces.
4. Use built-in policies (`permitAll`, `denyAll`, `authenticated`, `hasRole`, `hasAuthority`) and combine rules.
5. Integrate `AuthorizationManager` at the HTTP layer using `authorizeHttpRequests`/`access(...)`; distinguish it from method security (`@PreAuthorize`, `@PostAuthorize`).
6. Design rules around **least privilege**, **default deny**, and owner/tenant boundaries, and test 200/401/403 cases.
7. Recognize API differences across Spring Security 6.x, 7.x, and reactive authorization.

## 2. What Question Does Authorization Answer?

**Authentication** answers: *Who is sending the request?* For example: user `alice` has logged in and carries authorities `ROLE_USER`, `REPORT_READ`.

**Authorization** answers: *Is that person allowed to perform this action on this resource, in the current context?*

Let us model a decision:

~~~text
principal = who is calling?        alice
action    = what do they want?     READ
resource  = which object?          report/2026-Q4
context   = which conditions?      tenant, owner, state, time...
policy    = organization rule?     REPORT_READ and matching tenant
decision  = allow or deny?         GRANTED or DENIED
~~~

In an application, a person can **log in successfully and still be denied** when trying to read a colleague's document. This is normal: "logged in" does not mean "has every permission".

Examples of control levels:

| Level | Policy example | Typical enforcement point |
| --- | --- | --- |
| Endpoint | `GET /reports/**` requires `REPORT_READ` | `SecurityFilterChain`/`AuthorizationFilter` |
| HTTP method | `POST /orders/**` requires `ORDER_WRITE` | `authorizeHttpRequests` with `HttpMethod` |
| Service method | Only accountants may export reports | `@PreAuthorize` or custom method `AuthorizationManager` |
| Record/resource | Only owner or admin may read profile | Check owner/tenant from trusted data source |
| Field/result | View only permitted data fields | Business-layer policy, projection/filter, or suitable post-authorization |

There are three common models:

- **RBAC (Role-Based Access Control):** permissions tied to roles, such as ADMIN, EDITOR. Easy to manage, though too many roles can become hard to maintain.
- **ABAC (Attribute-Based Access Control):** evaluates user, resource, and environment attributes (e.g., department, owner, classification, tenant, state).
- **ReBAC (Relationship-Based Access Control):** evaluates relationships between subject and resource (owner, group member, shared user). An application often combines all three rather than choosing strictly one model.

`AuthorizationManager` is the technical mechanism that receives the information to evaluate and expresses the **decision**. It does not automatically know your business policy unless you configure or implement it.

## 3. Access Decision Flow in Servlet Security

For a Spring MVC / Servlet application using the `authorizeHttpRequests` DSL, the general flow is:

~~~text
HTTP request
    |
    v
SecurityFilterChain (authentication, security context, ...)
    |
    v
AuthorizationFilter
    | creates Supplier<Authentication> (fetches identity only when actually needed)
    | selects rule based on request matcher
    v
AuthorizationManager<RequestAuthorizationContext>
    | policy + authentication + request context
    +------ GRANTED ------> Controller/Service
    |
    +------ DENIED -------> AccessDeniedException
                              |
                              v
                        ExceptionTranslationFilter
                        -> entry point / 401 when unauthenticated
                        -> access denied handler / 403 when authenticated
~~~

This is an illustrative diagram and does not show every filter or every error-handling path. The final HTTP response also depends on how the authentication entry point, access denied handler, and authentication mechanism are configured.

Components to distinguish:

- `SecurityFilterChain`: the set of security filters applied to a request.
- `AuthorizationFilter`: invokes `AuthorizationManager` when `authorizeHttpRequests` is used on the Servlet stack.
- `Authentication`: principal, authorities, and authentication state. `GrantedAuthority` usually holds a string value, e.g., `ROLE_ADMIN`.
- `SecurityContextHolder`: where the security context is obtained on the Servlet stack, defaulting to `ThreadLocal` per request processing.
- `AuthorizationManager`: decides whether an operation on a secure object is permitted.
- `ExceptionTranslationFilter`: translates security exceptions into an entry point or access-denied response depending on context.

Authentication and authorization steps are related yet use different APIs: **`AuthenticationManager` verifies credentials; `AuthorizationManager` decides access.**

### How Does 401 Differ From 403?

- **401 Unauthorized**: typically appears when there is no valid authentication and the endpoint requires the user to log in. The HTTP name is slightly misleading: the practical meaning is *authentication required*.
- **403 Forbidden**: typically means the identity is authenticated yet lacks sufficient permissions for the operation. It can also appear in other cases, such as a rejected CSRF check.
- **200 OK**: the request was permitted and the endpoint succeeded; this does not prove all data layers are properly protected.

Do not test a policy with just one route and one account: on the same endpoint, test anonymous, authorized user, under-privileged user, cross-tenant account, and non-existent resource cases.

## 4. The AuthorizationManager<T> Contract

The `AuthorizationManager<T>` interface receives two key inputs:

1. `Supplier<Authentication> authentication`: enables **lazy** identity lookup. Rules like `permitAll` or `denyAll` may not need to fetch authentication at all.
2. `T object`: the object being protected. For example:
   - `RequestAuthorizationContext` when checking a Servlet HTTP request;
   - `MethodInvocation` when checking before a method call;
   - method-result context for post-authorization mechanisms.

The modern interface can be understood conceptually as:

~~~java
AuthorizationResult authorize(
    Supplier<Authentication> authentication, T object);

default void verify(
    Supplier<Authentication> authentication, T object);
~~~

**Note on versions and signatures:** The lines above are presented to learn the API, not as a standalone Java file. In Spring Security **6.4/6.5**, `authorize(...)` already exists while `check(...)` is the older deprecated API. In Spring Security **7.x**, the primary API is `authorize(...)` (with nullability/type annotations that may vary across versions). Code calling `check(...)` directly or overriding the old signature with `@Override` needs review when upgrading. The runnable examples later use a **lambda via `.access(...)`**, avoiding dependence on an old override signature.

**`AuthorizationResult`** provides `isGranted()`. The common implementation is `AuthorizationDecision`, which can be constructed via:

~~~java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);
~~~

This snippet requires importing `org.springframework.security.authorization.AuthorizationDecision`. `AuthorizationDecision` expresses an allow/deny outcome. A custom manager may also return `null` to **abstain** (make no decision), depending on the contract of the manager and caller. **Abstain is not equivalent to GRANTED** and must never be used to implicitly allow access. When implementing rules, always be explicit about which final component handles an undecided result; at the HTTP level, configuring `anyRequest().denyAll()` is an easy-to-understand safeguard.

`verify(...)` invokes the decision mechanism and throws `AccessDeniedException` on denial. In framework-managed flows, Spring Security calls and interprets the decision for you; never `try/catch` and swallow the exception to return 200.

### Why Use Supplier Instead of Authentication Directly?

Suppose static/public endpoints are very common. When a matcher selects `permitAll`, Spring Security does not need to load `Authentication` from the session just to grant access. Deferring `authentication.get()` until a policy needs it avoids unnecessary work and helps decouple policy from authentication mechanisms.

Avoid calling `authentication.get()` repeatedly in custom logic unnecessarily, and never assume the result is always a logged-in user: rule design must handle missing identity, anonymous tokens, missing authorities, and exceptions from data sources.

## 5. Three States in the Decision Model

| State | Meaning | Example |
| --- | --- | --- |
| **GRANTED** | Policy confirms access is allowed | User with `REPORT_READ` reads a report |
| **DENIED** | Policy confirms access is not allowed | User lacks `REPORT_READ` |
| **ABSTAIN** | Manager makes no decision | Specialized rule lacks facts or does not apply |

Short implementation example illustrating specialized logic, **not a complete endpoint**:

~~~java
AuthorizationManager<RequestAuthorizationContext> onlyReports =
    (authentication, context) -> {
        String path = context.getRequest().getRequestURI();

        if (!path.startsWith("/api/reports/")) {
            return null; // ABSTAIN: this manager does not handle other paths
        }

        Authentication auth = authentication.get();
        boolean allowed = auth != null
            && auth.getAuthorities().stream()
                .anyMatch(a -> "REPORT_READ".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    };
~~~

Requires importing `AuthorizationManager`, `AuthorizationDecision`, `Authentication`, and `RequestAuthorizationContext`. This example only illustrates manager semantics. Never use `startsWith` as a production route-matching mechanism without considering boundaries and path normalization; use Spring Security's standard `requestMatchers`/`RequestMatcher`. If a manager returns `null` and the caller treats that as "not denied", you risk opening unauthorized access. For real HTTP rules, **scope the matcher properly** and return an explicit decision for the matched branch; use `denyAll` for unmatched paths.

Do not confuse these 3 states with the legacy voting model: legacy `AccessDecisionVoter` also had GRANT/DENY/ABSTAIN, yet how they were combined depended on `AccessDecisionManager` (affirmative, unanimous...). Do not assume the exact same combining rules when moving to `AuthorizationManager`.

## 6. Built-In AuthorizationManagers

Spring Security provides common policies and delegation mechanisms:

| Component | Role |
| --- | --- |
| `AuthorityAuthorizationManager<T>` | Checks whether the caller holds the required authority/role |
| `AuthenticatedAuthorizationManager<T>` | Checks authentication state; can distinguish authenticated, fully authenticated, remember-me/anonymous per rule |
| `RequestMatcherDelegatingAuthorizationManager` | Selects the matching manager based on Servlet request matchers |
| `AuthorizationManagers` | Static factory supporting composition of multiple managers such as `allOf`, `anyOf` |
| `AuthorizationManagerBeforeMethodInterceptor` | Applies policy before invoking a method |
| `AuthorizationManagerAfterMethodInterceptor` | Applies policy after invocation, based on the return value |
| Custom `AuthorizationManager<T>` | Business rules such as tenant, owner, document state, or external policy service |

These names describe the **architecture**—you do not instantiate every class manually. For basic rules, Spring Security's DSL constructs the appropriate manager:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
    .anyRequest().denyAll()
);
~~~

This is an illustrative configuration snippet placed **inside a `SecurityFilterChain` bean** having variable `http`. Rules are evaluated in declaration order: a broad matcher must not be placed before a specific matcher, otherwise the specific rule may never be reached.

### hasRole and hasAuthority Are Not the Same

- `hasAuthority("REPORT_READ")` compares against an authority named **literally** `REPORT_READ`.
- `hasRole("ADMIN")`, under the default prefix configuration, looks for authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` also checks the exact string `ROLE_ADMIN`, though readers of the configuration must understand the role prefix meaning.
- Role hierarchy, depending on version/configuration, may allow a higher role to imply a lower role. Never assume `ROLE_ADMIN` has every authority unless explicitly configured.

In OAuth2 Resource Server, scopes are commonly mapped to authorities like `SCOPE_read` or `SCOPE_reports.read` depending on the converter; `hasRole("read")` does not automatically mean "OAuth scope read". Determine how JWT claims are converted into authorities and write rules accordingly.

### Combining With AND/OR

`AuthorizationManagers.allOf(...)` expresses requiring multiple conditions simultaneously; `AuthorizationManagers.anyOf(...)` expresses permitting when at least one condition passes. Business logic example:

~~~text
View sensitive report:
  authenticated
  AND has REPORT_READ
  AND same tenant

Edit document:
  (is owner AND state is DRAFT)
  OR is administrator with DOCUMENT_OVERRIDE
~~~

For components that may `abstain`, the combined outcome also depends on implementation and version; do not extrapolate from naive AND/OR operators while ignoring null cases. For critical policies, write truth-table tests covering GRANT, DENY, ABSTAIN, and exceptions.

**Spring Security 7.x:** Introduces `AuthorizationManagerFactory<T>`/`DefaultAuthorizationManagerFactory<T>` to customize manager creation, role prefixes, and role hierarchies. This is a version-specific feature; **do not drop this API directly into Spring Security 6.5 code**.

## 7. Request Authorization: Selecting Routes and Checking Permissions

Common DSL on the Servlet stack:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/catalog").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("ORDER_READ")
        .requestMatchers(HttpMethod.POST, "/api/orders/**")
            .hasAuthority("ORDER_WRITE")
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

This configuration snippet requires importing `HttpSecurity`, `HttpMethod`, `SecurityFilterChain`, and `Bean` inside a Spring configuration class; authentication is not configured yet. Key points:

1. `requestMatchers(...)` selects which requests the policy evaluates; it can match path, HTTP method, dispatcher type, or custom matchers.
2. `securityMatcher(...)` decides which requests **an entire `SecurityFilterChain`** applies to; it differs from `requestMatchers(...)`, which are rules *inside* the chain.
3. When multiple `SecurityFilterChain` beans exist, verify chain ordering and `securityMatcher` coverage; requests unmatched by any chain can escape the intended policy.
4. Define GET/POST rules explicitly by method; the same path does not imply the same permissions.
5. `anyRequest().denyAll()` acts as default deny, reducing the risk of newly added endpoints being exposed unintentionally.
6. Use `permitAll` for static/public content rather than excluding requests from the security filter chain with `ignoring`, so other protections like security headers remain active.

### Rules for Real Objects

Suppose route `GET /api/orders/{id}`. Checking only `hasAuthority("ORDER_READ")` may be **insufficient**, because a user holding this authority should not read orders belonging to another tenant. Resource-level authorization is needed:

~~~text
canRead(orderId, user):
  order = repository.findById(orderId)
  if order does not exist -> handle 404 per policy
  if user lacks ORDER_READ -> DENY
  if order.tenantId != user.tenantId -> DENY
  if order.private && owner != user && !manager -> DENY
  otherwise -> GRANT
~~~

This is business pseudocode, not runnable Java. Tenant and owner must be fetched from trusted sources, never relying solely on a client-sent `X-Tenant` header or a client-supplied URL variable. Choosing 403 or 404 for someone else's resource must be consistent with policies limiting resource existence disclosure.

## 8. Complete Application Example (Java 17, Spring Boot 3.5.x)

Goal: a small Spring MVC + Security application with four scenarios:

- Public endpoint callable by anyone.
- Reports requiring the `REPORT_READ` authority.
- Illustrative document readable if the owner name on the route equals the caller's name or the caller is admin.
- All other requests denied.

**Environment:** use Spring Initializr to create a Maven project, **Java 17+**, **Spring Boot 3.5.x**, package `com.example.authz`. Select **Spring Web** (`spring-boot-starter-web`) and **Spring Security** (`spring-boot-starter-security`). This lesson intentionally uses the **Servlet/MVC** stack for the runnable example; reactive is clearly distinguished in section 12. With Spring Security 7.x, the ideas still apply, though consult the migration/reference guide for the deployed version.

Files live in `src/main/java/com/example/authz/`.

### File 1 — AuthorizationDemoApplication.java

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

### File 2 — SecurityConfig.java

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> ownerOrAdmin
    ) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.GET, "/api/documents/{owner}")
                    .access(ownerOrAdmin)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> ownerOrAdmin() {
        return (authentication, context) -> {
            Authentication auth = authentication.get();

            boolean loggedIn = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken);

            String owner = context.getVariables().get("owner");

            boolean isOwner = loggedIn
                && owner != null
                && owner.equals(auth.getName());

            boolean isAdmin = loggedIn
                && auth.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

            return new AuthorizationDecision(isOwner || isAdmin);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("learn123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

**Notes on each decision:**

- `ownerOrAdmin` is a bean of type `AuthorizationManager<RequestAuthorizationContext>`. The lambda receives an authentication supplier and a request context, returning an `AuthorizationDecision`. This is a **real custom AuthorizationManager**, plugged into the DSL via `.access(ownerOrAdmin)`.
- `isAuthenticated()` alone is not enough to treat every `Authentication` as a real account: anonymous tokens can carry an authenticated state. Hence the example excludes `AnonymousAuthenticationToken`.
- `context.getVariables().get("owner")` reads the path variable extracted by the matcher. This is a **syntax demo**, not a production ownership policy: clients control the path; for real data you must check the owner from a database record or trusted source.
- User `reader` has `DOCUMENT_READ`, while `admin` has `ROLE_ADMIN` and `REPORT_READ`. The demo owner policy does not require `DOCUMENT_READ` for admin; in production, define the permission matrix clearly.
- Uses `BCryptPasswordEncoder` for in-memory learning passwords; never hardcode users/passwords in production source code.
- Does not disable CSRF globally: the demo only uses GET. For POST/PUT/DELETE, design CSRF properly for session/cookie or token-based APIs and test each case.

### File 3 — ReportService.java

~~~java
package com.example.authz;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String quarterlyReport() {
        return "quarterly-report";
    }
}
~~~

`@EnableMethodSecurity` in `SecurityConfig` activates method security. `@PreAuthorize` on `ReportService` adds enforcement at the business/service layer. When another bean invokes `ReportService.quarterlyReport()` through the Spring proxy, the decision is checked **before** the method executes. This helps protect call paths other than the HTTP controller.

### File 4 — DemoController.java

~~~java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final ReportService reportService;

    public DemoController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/reports")
    public String report() {
        return reportService.quarterlyReport();
    }

    @GetMapping("/documents/{owner}")
    public String document(@PathVariable String owner) {
        return "document-for-" + owner;
    }
}
~~~

To run, go to the project directory and use the Maven Wrapper generated by Spring Initializr:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With default port 8080 and no extra security configuration, test from another terminal:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u reader:learn123 http://localhost:8080/api/reports
curl -i -u admin:admin123 http://localhost:8080/api/reports
curl -i -u reader:learn123 http://localhost:8080/api/documents/reader
curl -i -u reader:learn123 http://localhost:8080/api/documents/alice
curl -i -u admin:admin123 http://localhost:8080/api/documents/alice
~~~

**Expected results per the demo code** (not logs executed in the current environment):

| Request | Expected HTTP | Body on success | Reason |
| --- | --- | --- | --- |
| Anonymous → `/api/public` | 200 | `public` | `permitAll` |
| Anonymous → `/api/reports` | 401 | — | Login required |
| Reader → `/api/reports` | 403 | — | Missing `REPORT_READ` |
| Admin → `/api/reports` | 200 | `quarterly-report` | Has `REPORT_READ` at HTTP and service |
| Reader → `/api/documents/reader` | 200 | `document-for-reader` | Matches owner on route |
| Reader → `/api/documents/alice` | 403 | — | Neither owner nor admin |
| Admin → `/api/documents/alice` | 200 | `document-for-alice` | Has `ROLE_ADMIN` |

Why have two layers for `/api/reports`? The HTTP rule blocks direct unauthorized requests; the service rule protects the logic if the method is called from another part of the application through its proxy. In real authorization, both policies must **align** to avoid broken UX or security gaps. Do not manually copy rules across dozens of places; encapsulate policies in reusable components and write unified tests.

### Difference Between Demo Results and Real Data

Controller `/api/documents/{owner}` only returns a string to make the decision mechanism easy to see. It does not look up a document by ID. In a real application, an endpoint like `GET /api/documents/42` must verify the *real owner of document 42* from the database, along with tenant and permissions, rather than accepting `owner=reader` chosen by the client and granting access to arbitrary data. This is the **IDOR/BOLA** issue (reading others' resources by changing IDs).

## 9. Designing Business-Specific Custom AuthorizationManagers

When `hasRole`/`hasAuthority` is not enough, you can write a custom manager. Before writing it, clarify:

1. **Principal**: which identity, authenticated by which mechanism, how are authorities normalized?
2. **Action**: READ, CREATE, APPROVE, DELETE... different actions may require different policies.
3. **Resource**: which resource, where are owner/tenant/state retrieved from (database or trusted source)?
4. **Context**: timestamp, MFA, data classification, policy version... are they trustworthy?
5. **Failure modes**: resource missing, DB error, policy service timeout, missing identity, abstain result.
6. **Decision**: always return an explicit decision for the policy slice you own; never silently permit when a dependency fails.

Illustrative design model:

~~~text
DocumentPolicy.canRead(authentication, documentId)
  = authenticated
    AND permission includes DOCUMENT_READ
    AND (
         sameTenant AND isOwner
         OR explicit DOCUMENT_ADMIN delegation
        )
    AND document.notDeleted
~~~

Determining `sameTenant` and `isOwner` must use real records. If the DB/policy server does not respond, never auto-grant: the safe rule is **fail closed**, while distinguishing service errors (typically 5xx) from business denial decisions (403/404 per policy). "Fail closed" does not mean disguising every error as HTTP 403.

### When to Write a Dedicated Policy Instead of SpEL?

`@PreAuthorize("hasAuthority('DOCUMENT_READ')")` is very clear. However, long expressions with many owner/tenant/feature-flag branches are hard to audit and unit test. When logic grows complex, use a policy service with clear methods and inject it into a custom manager or method-security expression. Never let the controller, frontend, and database queries each define "what admin can do" differently.

If a decision must call an external policy engine (such as OPA), configure timeouts, policy-versioned caching, error classification, and auditing; do not add expensive blocking calls to every request without measuring performance. Avoid caching grants for too long when permission revocations must take effect quickly. If policies face concurrent update races, consider snapshots/versions or transaction boundaries to reduce TOCTOU.

## 10. Method Security: Pre/Post Invocation Decisions

HTTP policies only protect HTTP entry points. Business methods can be called from scheduled jobs, messaging consumers, or internal components, so combining request and method authorization is common practice.

Enable method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

This is an illustrative fragment; the demo app already has `@EnableMethodSecurity`, so do not create a duplicate config bean just to enable it again. Under the default Spring AOP proxy approach:

- `@PreAuthorize("hasAuthority('REPORT_READ')")`: decides before invoking the method.
- `@PostAuthorize("returnObject.owner == authentication.name")`: inspects the returned value after the method; understand the risks of side effects and data exposure before a denial can happen.
- `@PreFilter` and `@PostFilter`: can filter input/return collections by expression; avoid using casually on very large datasets.
- `@Secured` and `@RolesAllowed` may be supported depending on configuration; they cannot replace cases with complex business conditions.

Note: `@PreAuthorize` and `@PostAuthorize` are rule syntax; underneath, Spring Security uses corresponding interceptors/managers. `AuthorizationManagerBeforeMethodInterceptor` works with managers before invocation; `AuthorizationManagerAfterMethodInterceptor` can inspect the result after invocation.

**Self-invocation warning:** in standard AOP proxying, a call `this.securedMethod()` from inside the same class can bypass the proxy so the annotation is not applied. Call from another bean or structure services cleanly; test the actual call path. Additionally, constructor/non-public method calls or objects not managed by Spring may behave differently than expected due to proxying.

**Pre or post?** For state-changing operations (money transfer, delete, sending email), prefer checking permissions **before side effects**. `@PostAuthorize` makes sense for certain return-value checks, yet cannot "undo" side effects that already occurred prior to a deny decision.

## 11. Testing Policies With a Permission Matrix

Do not test only "admin is allowed". A valuable test suite should cover:

- anonymous / wrong credentials;
- user with the right permission;
- logged-in user lacking the permission;
- owner versus non-owner;
- admin actually carrying the right authority;
- unmatched routes and default deny;
- same-tenant / cross-tenant in multi-organization systems;
- overlapping rules: is matcher order correct;
- method security when called through a service bean;
- revoked permissions or policy-service failures (if applicable).

Add the two test-scope dependencies in `pom.xml` (if not already present):

~~~xml
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
~~~

In `src/test/java/com/example/authz/DemoAuthorizationTests.java`:

~~~java
package com.example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void reportNeedsLogin() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCannotSeeReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCanSeeOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/reader"))
            .andExpect(status().isOk())
            .andExpect(content().string("document-for-reader"));
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCannotSeeOthersDocument() throws Exception {
        mvc.perform(get("/api/documents/alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin",
                  authorities = {"ROLE_ADMIN", "REPORT_READ"})
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

On PowerShell: `.\mvnw.cmd test`. `@WithMockUser` provides a mock principal for the Spring Security test context; this is **not a test of the real HTTP Basic login mechanism**. To test Basic authentication, use `httpBasic(...)` from `spring-security-test` or real HTTP calls. Both test types serve different purposes: policy tests avoid depending on login flows, while integration tests verify the system end-to-end.

The assertions above are the expected outcomes of the stated code and configuration, not test results executed by this document. In real deployments, run Maven tests and verify logs and dependency versions.

## 12. How Servlet and Reactive Use AuthorizationManager

**Do not mix the two API stacks.**

| Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthorizationFilter` and Servlet filters | `WebFilter` and reactive security filters |
| `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` (per reactive API) |
| `SecurityContextHolder`, typically ThreadLocal | `ReactiveSecurityContextHolder` and Reactor Context |
| `authorizeHttpRequests` | `authorizeExchange` |

Illustrative **reactive example**, to be placed only inside a Spring WebFlux configuration with appropriate imports and beans, never alongside the Spring MVC demo app:

~~~java
@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/reports/**").hasAuthority("REPORT_READ")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

When decisions require asynchronous I/O on WebFlux, choose `ReactiveAuthorizationManager` and suitable publishers instead of blocking calls on the event loop. Passing a Servlet `AuthorizationManager<RequestAuthorizationContext>` to `authorizeExchange` just because the names look similar is both the wrong type and the wrong execution model. Authorization and authentication in a reactive chain must use the Reactor Context to preserve identity across async boundaries.

## 13. Important Changes Across Versions

### From AccessDecisionManager/Voter to AuthorizationManager

Previously, many applications used `FilterSecurityInterceptor`, `AccessDecisionManager`, `AccessDecisionVoter`, metadata attributes, and voting strategies. The modern model centers policies around `AuthorizationManager`, integrated at both request and method security. Key changes to remember:

- Use `authorizeHttpRequests` instead of the older `authorizeRequests` configuration to activate the `AuthorizationFilter`-based request authorization path.
- For custom logic, replace or wrap the old voter mechanism with an `AuthorizationManager` that has clear semantics.
- In Spring Security 6.4+, prefer `authorize(...)` over `check(...)`; `check(...)` was deprecated in the 6.5 line.
- Starting with Spring Security 7, the legacy Access API (`AccessDecisionManager`, `AccessDecisionVoter`, etc.) lives in the legacy `spring-security-access` module. New applications should not depend on the legacy API. When migrating, review both dependencies and behavior separately.
- Spring Security 7 adds `AuthorizationManagerFactory` to customize how default managers are built. This is optional if the DSL already expresses your policy completely.

Do not migrate configurations via mechanical renaming and assume 100% identical behavior. When changing models, review matcher ordering, abstain handling, exceptions, method interceptors, role prefixes, and default deny. Read the migration guide for the exact version you are upgrading to.

### When to Use @PreAuthorize vs a Custom AuthorizationManager?

Use `@PreAuthorize` for short, clear authority/parameter-based policies that the whole team can understand easily. Use a custom manager when a policy is applied across multiple places, involves complex domain conditions, needs isolated testing, or wraps an interface to a decision service. A policy service/domain method can still be called from a custom `AuthorizationManager`; the two techniques complement each other.

## 14. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Using only `authenticated()` for sensitive resources | Every logged-in account gets access | Specify concrete authority/action/owner/tenant |
| Placing a broad matcher before a narrow matcher | Narrow rule gets shadowed or skipped | Order from specific to general and test |
| Having no catch-all rule | New endpoints may get unintended open policy | Use `anyRequest().denyAll()` for controlled endpoint sets |
| Believing `hasRole("ADMIN")` implies all permissions | Admin role does not implicitly grant every permission | Define explicit role-authority mappings/hierarchies |
| Using `hasRole("SCOPE_read")` instead of `hasAuthority("SCOPE_read")` | Wrong `ROLE_` prefix | Inspect actual authorities on authentication |
| Trusting client-chosen owner from URL/header | IDOR/BOLA, cross-tenant breach | Query trusted data source by resource ID |
| Calling `authorizationManager.authorize()` manually and ignoring the result | Decision is never enforced | Use framework interceptors or `verify`/handle result per contract |
| Treating `null` (abstain) as `true` | "Nobody denied so allow" vulnerability | Define composition and default deny |
| Catching every `AccessDeniedException` and returning 200 | Erases the security boundary | Let standard handlers process the exception |
| Protecting only the controller while the service is called freely | Bypass via jobs/messaging/other services | Enforce method/domain security when needed |
| Calling `this.securedMethod()` with an AOP proxy | Annotation may not be applied | Invoke through Spring bean proxy, test execution path |
| Using `@PostAuthorize` for operations with side effects | Method already mutated data before denial | Authorize before mutating |
| Not testing anonymous and denied cases | Proves only happy paths | Test 401/403/granted/cross-tenant matrix |
| Using blocking policy lookups on the reactive event loop | Blocks threads, degrades throughput | Reactive manager + non-blocking source or proper scheduler isolation |
| Hardcoding credentials or caching permissions too long | Secret leaks / slow permission revocation | Secret management, appropriate TTL/invalidation |

## 15. Design Principles You Can Apply Immediately

**Least privilege:** grant only the permissions required for the task, avoiding overly broad authorities. In large systems, prefer action-descriptive permission names like `INVOICE_READ`, `INVOICE_APPROVE` over meaningless role names.

**Deny by default:** when a request does not match an allow rule, deny it. When a policy depends on data that is unavailable, avoid auto-permitting; classify service errors clearly.

**Defense in depth:** route authorization and method/domain authorization complement each other. Permission checks remain valid at the point of fetching/modifying resources, especially with multi-tenancy or asynchronous processing.

**Separation of concerns:** authentication manages identity; authorization manages policy; business services execute business logic. Managers should have focused responsibilities and be easy to test.

**Correctness under change:** every new endpoint/permission requires updating policies and tests. Role mappings, tenant changes, policy caches, token scopes, method proxying, and filter/chain order are common bug sources rarely visible in UI reviews.

**Auditability:** on deny decisions, log necessary details (appropriate principal ID, action, resource identifier, policy version, outcome) while avoiding passwords, access tokens, or unnecessary personal data. Spring Security authorization events can help observability; verify publisher configuration and the version in use.

**Do not treat hiding a frontend button as authorization.** UI can guide users away from invalid actions, yet the backend must verify every request. Clients can always send HTTP requests directly without going through the UI.

## 16. Practice Exercises

**Exercise 1 — Decision states.** In a system with three custom managers, manager A returns `null` because it does not manage the path; manager B returns DENIED due to missing permission; manager C returns GRANTED because the user is the owner. Can you conclude the request is allowed from these three isolated results alone? Explain why it depends on composition logic and policy order.

**Exercise 2 — Role prefix.** A token carries authorities `SCOPE_reports.read` and `ROLE_USER`. Predict the results of `hasRole("USER")`, `hasAuthority("SCOPE_reports.read")`, and `hasRole("reports.read")` under the default role prefix.

**Exercise 3 — Protecting resources.** Endpoint `GET /documents/{id}` currently uses `authenticated()`. Design a rule checking `DOCUMENT_READ`, owner, and tenant from the database. Separately state the DB timeout and non-existent resource cases.

**Exercise 4 — Policy order.** If `requestMatchers("/api/**").permitAll()` is placed before `requestMatchers("/api/admin/**").hasRole("ADMIN")`, what happens? Reorder them and write a test asserting anonymous users cannot call the admin URL.

**Exercise 5 — Method security.** A service has `@PreAuthorize` on method `transfer()`, yet another method in the same class calls `this.transfer()`. Why is there a risk of bypassing the annotation when using a Spring proxy? Restructure the beans so a call passes through the proxy or enforce the policy explicitly.

**Exercise 6 — Version migration.** When upgrading from Spring Security 6.5 to 7, identify where custom managers override `check(...)`, where `AccessDecisionManager/Voter` is used, and how abstaining managers are handled. Write regression tests before changing APIs.

**Self-check hints:**

- Exercise 1: insufficient information to conclude; you must know the matchers and combining logic, and never treat abstain as grant.
- Exercise 2: `hasRole("USER")` and `hasAuthority("SCOPE_reports.read")` match; `hasRole("reports.read")` looks for `ROLE_reports.read` by default and usually fails to match.
- Exercise 3: must look up owner/tenant from the real resource, fail closed on errors while distinguishing system errors, and never trust client-declared ID/tenant.
- Exercise 4: the broad matcher can grant access early, skipping the admin rule. Put the specific rule first and include `anyRequest().denyAll()`.
- Exercise 5: self-invocation can bypass the proxy; enforce policies at a trusted boundary.
- Exercise 6: separate API signature changes from access-decision changes; regression tests guard security semantics.

## 17. Summary and Reference Documentation

`AuthorizationManager` is the central mechanism enabling Spring Security to enforce **who can do what, on which resource**. Three core factors to remember:

1. **Right inputs:** trusted `Authentication`/authorities, action, real resource, and context such as tenant/owner.
2. **Right decision:** GRANT, DENY, and ABSTAIN have distinct semantics; specify default-deny and error behavior.
3. **Right enforcement point:** HTTP rules, method interceptors, and domain-level checks complement each other; test the real call path.

Start with the simple DSL, then add custom managers when business policies demand it; never sacrifice clarity and testability for an overly convoluted expression. A correct access decision is only trustworthy when **enforced at the right place**.

Official documentation to cross-check by version:

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — Authorization overview](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/)
- [Spring Security — Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
