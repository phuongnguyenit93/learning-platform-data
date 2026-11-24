# Distinguishing Authenticated Identity from Granted Authorities

> **Module:** Spring Security - fundamentals  
> **Knowledge group:** Authorization  
> **Central question:** Does a user who has successfully logged in automatically get permission to perform every operation? **No.** The system needs to know *who is requesting* and *what that user is allowed to do in the specific context*.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **authentication (identity verification)** from **authorization (access decision)** within a request lifecycle.
- Correctly read the two groups of information coexisting inside Spring Security's `Authentication` object: principal/identity information and the set of `GrantedAuthority`/granted permissions.
- Explain why `Authentication.isAuthenticated() == true` **does not mean** the user holds any required authority.
- Distinguish role, authority, permission, and scope; know how `hasRole` and `hasAuthority` match authority strings.
- Recognize the special case of `AnonymousAuthenticationToken`, distinguishing authentication state from tokens marked `authenticated`.
- Design permission checks at the URL, method, and specific resource levels; avoid confusing “logged in” with “allowed to view/edit this document”.

## 2. Two Different Security Questions

**Authentication: “Who are you, and is your proof of identity valid?”**

For example, Alice sends a username/password; the system verifies the login credentials. Or a client sends a bearer token; the resource server checks the signature, expiration, issuer, and token acceptance conditions. After successful authentication, Spring Security typically has an `Authentication` object representing the trusted principal for the scope of the request or session.

**Authorization: “Is this known identity allowed to perform the requested action on this resource?”**

For example, Alice is validly identified but only has permission to view invoices; deleting an invoice requires a different permission. Logging in successfully does not grant delete permission.

~~~text
Client sends request
       |
       v
[Authentication] Check credentials / token / session
       |
       +-- Fails: requires authentication or deny
       |
       v
[Authentication] Principal and GrantedAuthorities identified
       |
       v
[Authorization] Action + resource + applicable rules
       |
       +-- Fails: access denied
       |
       v
Business logic allowed to execute
~~~

In HTTP APIs, systems typically use **401 Unauthorized** when a request lacks valid authentication information and **403 Forbidden** when the identity is recognized but lacks permission. This is a common convention, not the only inference from status codes: an app using form login may redirect to a login page; CSRF, other filters, or custom entry points can also produce different outcomes.

### Scenario Matrix

Suppose a document management application has three permissions: `document:read`, `document:write`, and `document:delete`.

| User | Authentication | Granted authorities | View | Edit | Delete |
| --- | --- | --- | --- | --- | --- |
| Alice | Succeeded | `document:read` | Yes | No | No |
| Bob | Succeeded | `document:read`, `document:write` | Yes | Yes | No |
| Carol | Succeeded | `document:delete` | No | No | Yes per action permission check |
| Unauthenticated guest | No trusted identity | None of the above permissions | No | No | No |

The table only simulates **action-based permission checks**; in practice, the system may also require read permission before deleting or document ownership. What matters is that **with the same “authenticated” state, the set of permissions can be completely different**.

## 3. What Does an `Authentication` Object Contain?

Spring Security defines `org.springframework.security.core.Authentication`. After valid authentication completes, it typically contains:

| API / data | Used to answer | Example | Do not infer |
| --- | --- | --- | --- |
| `getPrincipal()` | Who is the subject? | `UserDetails`, `Jwt`, `OAuth2User`, or username | Principal is not the list of permissions |
| `getName()` | Identifier name provided by the implementation | `alice`, token subject | Display name is not always a unique key across tenants |
| `getCredentials()` | Proof used during authentication | Password/token, usually erased after authentication | Do not log or include credentials in responses |
| `getAuthorities()` | What permissions does the subject carry? | `ROLE_ADMIN`, `document:read`, `SCOPE_reports.read` | Not the final conclusion for every resource |
| `isAuthenticated()` | Is this token marked authenticated according to the implementation's semantics? | `true`/`false` | Does not mean having `ROLE_ADMIN` or access to any document |
| `getDetails()` (when supported by the implementation) | Additional metadata about the authentication | Request details | Not by default a source of permissions or security proof |

`SecurityContext` holds `Authentication`. In Servlet applications, Spring Security typically accesses the security context via `SecurityContextHolder`; in WebFlux, it uses `ReactiveSecurityContextHolder` inside the reactive publisher. **How the security context is propagated differs**, but the separation between identity and authorities remains the same.

### Warning About `isAuthenticated()`

A username/password login request before being authenticated can be represented by a token with `isAuthenticated() == false`. After `AuthenticationManager` or `AuthenticationProvider` accepts the credentials, the resulting object may return `true`. However, Spring Security also has **anonymous authentication**: `AnonymousAuthenticationToken` is typically marked `isAuthenticated() == true` to conveniently represent an anonymous user in the security context.

Therefore, a manual check:

~~~java
// NOT sufficient to decide that the request is a genuinely logged-in user.
boolean loggedIn = authentication != null && authentication.isAuthenticated();
~~~

is not a safe substitute for `authenticated()` in the DSL or `AuthenticationTrustResolver`. Spring Security's authorization mechanism distinguishes anonymous, remember-me, and fully authenticated when needed; for example, `AuthenticationTrustResolver.isAnonymous(authentication)` identifies anonymous tokens.

## 4. `GrantedAuthority` Is a “Granted Permission”, Not an “Identity”

`Authentication.getAuthorities()` returns a collection of `GrantedAuthority`. This interface has the method `String getAuthority()`. A common implementation is `SimpleGrantedAuthority`, which holds the authority string for matching.

Example:

~~~text
Authentication:
  principal: "alice"
  authenticated: true
  authorities:
    - "ROLE_EMPLOYEE"
    - "document:read"
~~~

In the example above:

- `alice` indicates who the principal is.
- `ROLE_EMPLOYEE` describes the role assigned by the system to the principal.
- `document:read` describes a specific capability.
- Without `document:delete`, a rule requiring `document:delete` must deny Alice even though Alice has a valid identity.

**An authority is an input fact for making an authorization decision.** The decision may also depend on the HTTP method, path, resource data in the database, tenant, time, owner–resource relationship, or business policy.

### Role, Permission, Scope: Naming and Semantics

| Concept | Example | Intended meaning |
| --- | --- | --- |
| **Role** | `ADMIN`, `EDITOR` | Group of user responsibilities/functions |
| **Role authority** | `ROLE_ADMIN` | Authority string commonly used by Spring Security to represent a role |
| **Permission / operation authority** | `document:read`, `invoice:approve` | Permission granted per operation |
| **OAuth2 scope** | `reports.read` → commonly mapped to `SCOPE_reports.read` | Scope authorized by the token, per resource server mapping configuration |
| **Object-level policy** | “Alice may only view documents in Alice's department” | Rule combining subject, action, resource, and context |

Spring Security does not automatically understand that a `ROLE_ADMIN` string implies all `document:*`. The relationship “ADMIN may read/delete” must exist in authority mapping or the application's authorization policy. Similarly, a `roles` claim inside a JWT **does not automatically become** `ROLE_ADMIN` if no configured converter maps it.

### How `hasRole` Differs from `hasAuthority`

By default convention, `hasRole("ADMIN")` checks the authority with the `ROLE_` prefix, equivalent to requiring `ROLE_ADMIN`. `hasAuthority("ROLE_ADMIN")` requires that **exact string**; `hasAuthority("ADMIN")` checks the string `ADMIN` without prepending `ROLE_`. The role prefix can be customized via corresponding configuration.

~~~text
Current authorities: ["ROLE_ADMIN", "document:read"]

hasRole("ADMIN")                 -> true  (matches ROLE_ADMIN by default)
hasAuthority("ROLE_ADMIN")       -> true
hasAuthority("ADMIN")            -> false
hasAuthority("document:read")    -> true
hasAuthority("document:write")   -> false
~~~

Do not manually add `ROLE_` to a `hasRole` call when using default semantics; avoid expecting a matched string that differs from the actual granted data. Authority names are case-sensitive strings; keep casing and separator conventions consistent between the issuer and the check site.

## 5. Java 17+ Practice: Same Identity, Different Authority Sets

The following example runs standalone as a console application using `spring-security-core`. It only simulates constructed `Authentication` objects to observe the data, **not a login program or proof of a valid password**.

Project structure:

~~~text
identity-authorities-demo/
├── build.gradle
└── src/main/java/demo/IdentityAuthoritiesDemo.java
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.IdentityAuthoritiesDemo'
}
~~~

File `src/main/java/demo/IdentityAuthoritiesDemo.java`:

~~~java
package demo;

import java.util.List;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class IdentityAuthoritiesDemo {

    private static void check(Authentication authentication, String authority) {
        boolean granted = authentication.getAuthorities().stream()
            .anyMatch(item -> authority.equals(item.getAuthority()));

        System.out.printf(
            "%s | tokenFlag=%s | %s=%s%n",
            authentication.getName(),
            authentication.isAuthenticated(),
            authority,
            granted
        );
    }

    public static void main(String[] args) {
        Authentication aliceReader =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(
                    new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                    new SimpleGrantedAuthority("document:read")
                )
            );

        Authentication aliceEditor =
            UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(
                    new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                    new SimpleGrantedAuthority("document:read"),
                    new SimpleGrantedAuthority("document:write")
                )
            );

        Authentication bobAdmin =
            UsernamePasswordAuthenticationToken.authenticated(
                "bob",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            );

        Authentication loginAttempt =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice",
                "not-a-real-password"
            );

        Authentication anonymous = new AnonymousAuthenticationToken(
            "demo-key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );

        AuthenticationTrustResolver resolver =
            new AuthenticationTrustResolverImpl();

        check(aliceReader, "document:write");
        check(aliceEditor, "document:write");
        check(bobAdmin, "document:read");
        System.out.println("loginAttempt | tokenFlag="
            + loginAttempt.isAuthenticated());
        System.out.println("anonymous | tokenFlag="
            + anonymous.isAuthenticated()
            + " | isAnonymous=" + resolver.isAnonymous(anonymous));
    }
}
~~~

Run with JDK 17+ and Gradle 8.x:

~~~bash
gradle run --quiet
~~~

Stdout output:

~~~text
alice | tokenFlag=true | document:write=false
alice | tokenFlag=true | document:write=true
bob | tokenFlag=true | document:read=false
loginAttempt | tokenFlag=false
anonymous | tokenFlag=true | isAnonymous=true
~~~

**Result analysis:**

1. For the same principal name `alice`, the two authentication objects in the test have different authority sets. Identity **is not enough** to infer the permissions of a specific session or token.
2. `bob` has `ROLE_ADMIN` but **does not have** `document:read`. The `check` method compares exact authority strings so it returns `false`. The program does not define a rule “ROLE_ADMIN equals document:read”.
3. `loginAttempt` has not passed authentication so it has `tokenFlag=false`. The password here is only test data; no `AuthenticationManager` verifies it.
4. `anonymous` has `tokenFlag=true`, yet `AuthenticationTrustResolver` still recognizes it as anonymous. Relying solely on the raw flag leads to incorrect conclusions.
5. The `authenticated(...)` constructor/factory is used **only to build fixtures**. In a real system, a trusted object must be produced by a valid authentication mechanism; never arbitrarily construct an authenticated token from a client-supplied username.

The `check` program is a direct permission check for learning purposes. It **does not** replace `AuthorizationManager`, method security, or resource access policies in a Spring application.

## 6. How Does Spring Security Carry Identity and Authorities Through a Request?

In the typical case, the flow looks like this:

~~~text
Credentials / session / bearer token
          |
          v
AuthenticationManager + AuthenticationProvider
(or equivalent authentication component of the active mechanism)
          |
          v
Successful authentication:
  - principal
  - authenticated state
  - GrantedAuthority[]
          |
          v
Request/security-execution scoped SecurityContext
          |
          v
AuthorizationManager:
  - what does the endpoint/method require?
  - do the granted authorities match the policy?
  - if checking at domain level, is the resource permitted for access?
          |
          +-- deny when unmet
          |
          v
Allow business logic execution
~~~

The authentication step may load authorities via `UserDetailsService` for username/password login; or convert token scopes/claims into authorities via a converter for OAuth2 Resource Server; or through a custom mechanism. **The source of authorities and how they are mapped depend on configuration**—do not guess from usernames, database role names, or raw JWT content.

For Servlet, `Authentication` is typically placed in `SecurityContext`, with `SecurityContextHolder` providing the access API. For WebFlux, Spring Security maintains this context in the Reactor Context and reads it via `ReactiveSecurityContextHolder`; the identity–authority comparison logic remains similar.

## 7. URL Permission Checks Differ from “Logged In Is Enough”

Example configuration for a Spring Security Servlet application (Spring Security 6.x), placed in a `@Configuration` class of an application using Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/documents/**")
                .hasAuthority("document:write")
            .requestMatchers(HttpMethod.DELETE, "/documents/**")
                .hasAuthority("document:delete")
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Required imports: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`, and `org.springframework.http.HttpMethod`. This is a configuration snippet **integrated into a Spring application**, not a standalone Java file; the application still needs actual configuration of the authentication mechanism.

**Meaning of each check type:**

- `permitAll()`: public URL, no identity required.
- `authenticated()`: requires a principal recognized by the system as authenticated per Spring Security; requires no specific business authority.
- `hasAuthority("document:read")`: requires the exact read permission, whether the principal is Alice or Bob.
- `hasRole("ADMIN")`: with the default role prefix, requires `ROLE_ADMIN`.
- `denyAll()`: rejects unlisted requests — a safe default strategy when intentionally exposing only a small set of APIs.

Matcher order matters: Spring Security applies the first matching rule for a request in `authorizeHttpRequests`. Therefore, do not place `/documents/**.authenticated()` before `GET /documents/**.hasAuthority("document:read")` if you intend to protect GET with the read permission: the broader matcher would capture the request first.

**An independent note:** With Spring Security Servlet CSRF protection enabled, a `POST` or `DELETE` request from a browser can be rejected for a missing/invalid CSRF token even when the authority is correct. This is a different protection mechanism from authority checks. Do not disable CSRF just to make an authority example “work” without evaluating the application model.

### Example Requirements for `hasRole` and `hasAuthority`

If `Authentication.getAuthorities()` currently contains:

~~~text
["ROLE_EDITOR", "document:read"]
~~~

then:

| Rule | Result | Why |
| --- | --- | --- |
| `authenticated()` | Passes the authentication state check if the token is recognized | Only requires authenticated |
| `hasRole("EDITOR")` | Passes | Matches `ROLE_EDITOR` by default |
| `hasAuthority("ROLE_EDITOR")` | Passes | Exact string match |
| `hasAuthority("document:write")` | Fails | This permission was not granted |
| `hasRole("ADMIN")` | Fails | Missing `ROLE_ADMIN` |

The results above assume a genuinely recognized principal, not an anonymous token; other request protection mechanisms are excluded.

## 8. Permission Checks at Methods and Specific Resources

Permissions attached only to URLs are often insufficient. A service can be invoked via REST, an internal job, or elsewhere; and the same `document:read` permission does not necessarily allow viewing **every** document.

To enable method security checks with Spring Security, declare `@EnableMethodSecurity` on a configuration class; Spring Boot Starter Security does not enable all method authorization automatically. Illustrative example:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

In a Spring-managed service:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document loadDocument(long id) {
    return documentRepository.findById(id).orElseThrow();
}
~~~

The two snippets above are **integration illustration code**, not a self-running Java program: `Document`, `documentRepository`, and the Spring-managed service are defined by the specific application. `@PreAuthorize` requires method security to actually be enabled, usually applied through a Spring proxy when calls go through a bean; self-invocation inside the same instance can bypass proxy advice.

The condition above only checks *general read permission*. If the system requires users to view only their own documents, a resource-level policy based on trusted data must be added:

~~~text
Subject:     alice
Action:      document:read
Resource:    document #42, owner=bob
Authority:   alice has document:read
Policy:      document owner must match subject

Result:      DENY even though authentication is valid and authority is present
~~~

Place ownership/tenant checks inside the policy/service, retrieving the true owner from server-side data instead of trusting a client-sent `ownerId`; avoid inferring permission solely from an `id` in the URL. You can combine `@PreAuthorize` with a policy bean, such as the conceptual `@documentPolicy.canRead(authentication, #id)`, where the policy actually queries ownership/relationship with the resource before returning a result. Do not treat that expression as an ownership check if the bean has not been implemented.

### Authentication Is Not an Authorization Decision

Example manual check:

~~~java
// API illustration only; this is not a complete authorization policy.
Authentication auth = SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
boolean hasRead = auth.getAuthorities().stream()
    .anyMatch(a -> "document:read".equals(a.getAuthority()));
~~~

Here `username` gives the identity and `hasRead` tells whether one authority is present, but it has not yet answered **is Alice allowed to view document #42 in tenant Y today?**. A proper answer requires a policy with sufficient attributes about the resource and context.

## 9. Different Authorization Layers Have Different Responsibilities

| Layer | Typical decision | Risk if missing |
| --- | --- | --- |
| Request/endpoint | `GET /documents/**` requires `document:read` | External access to sensitive endpoints |
| Method/service | `approveInvoice()` requires `invoice:approve` | An internal call path bypasses controller checks |
| Object/domain | Who can view a document with `ownerId=...`? | IDOR/BOLA: changing IDs to read another user's object |
| Data/query | Restrict queries by true tenant/owner | Returning out-of-scope data even through a valid endpoint |

Do not treat the `ADMIN` role as an implicit bypass for every tenant check, privacy rule, or business rule. If a group of users needs cross-tenant permissions, describe and control that exception with an explicit, audited policy rather than inferring it automatically from the role name.

## 10. Permissions Change Over Time and Context

The same principal can have different sets of authorities because:

1. A user belongs to multiple tenants/departments; permissions in tenant A are not necessarily valid in tenant B.
2. Roles are changed after login, while the current session/JWT still carries old claims or authorities until refreshed, expired, or invalidated by design.
3. A token is issued with a narrow read-only scope even though the user has a broader role in another system.
4. A user has read authority, but the resource is locked, sharing was revoked, or it belongs to someone else.

**Effective permissions = system-trusted identity + active grants + policy by action/resource/context.** Do not copy all roles from the database into a token and assume they will always reflect the latest state; design refresh/revocation cycles appropriate to the risk level.

Do not use `getName()` as a unique identifier if the same name can appear across multiple identity sources or tenants. Prefer a verified stable user ID/subject combined with proper tenant boundaries; never trust a principal or authority self-declared by the client without verification.

## 11. Common Mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| “Logged in means allowed to edit data” | Conflates authentication with authorization | Use `hasAuthority`/action-specific policies |
| Using `isAuthenticated()` as proof of non-anonymous | Anonymous tokens can return `true` | Use `authenticated()`/`AuthenticationTrustResolver` |
| Granting `ROLE_ADMIN` but calling `hasAuthority("ADMIN")` | Authority string mismatch | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Seeing claim `scope=read` and requiring `hasAuthority("read")` | Resource server may map it to `SCOPE_read` | Inspect the converter and actual authority strings |
| Checking `document:read` then returning any document ID | Missing object-level authorization | Check owner/tenant against server-side data |
| Trusting permissions sent in unverified body/header | Client privilege escalation | Authorities must come only from verified/controlled sources |
| Manually building an authenticated token from request data | Bypasses valid authentication | Let `AuthenticationProvider`/trusted mechanism verify |
| Testing only with default `@WithMockUser` and concluding permissions work | Mock may carry different authorities than production | Test both valid/invalid authorities and real mapping paths |
| Logging the entire `Authentication` | May leak sensitive information | Log only minimal user ID and required audit decision |
| Reading `SecurityContextHolder` in WebFlux like Servlet | Reactive context has different semantics from thread-local | Use `ReactiveSecurityContextHolder` in the pipeline |

## 12. Testing the Identity and Permission Boundary Properly

A good test suite should separate scenarios along two axes: **authentication state** and **granted authorities**. For example, for a document read endpoint whose policy requires `document:read` and matching owner:

| Case | Expectation |
| --- | --- |
| Unauthenticated / invalid token | Blocked at authentication/entry point |
| Authenticated, lacking `document:read` | Denied at authorization |
| Authenticated, has `document:read`, matching owner | Allowed if all other conditions hold |
| Authenticated, has `document:read`, wrong owner | Denied by resource-level policy |
| Authenticated, only `ROLE_ADMIN`, no read permission mapping | Follows specific authority rule, not implicitly allowed |
| Same user with a new token having different grants than the old token | Decision must reflect the currently effective grants |

With `spring-security-test`, `@WithMockUser(username = "alice", authorities = "document:read")` simulates identity and authority for method/HTTP layer tests; `@WithMockUser(roles = "ADMIN")` creates a prefixed role authority. Such mock tests verify **authorization**, not that real login/token validation works. To test JWT scope/role mapping and real credentials, add integration tests for the corresponding authentication path.

Verify both the unauthorized response and that business data logic **is not executed** when denied. For multi-tenant systems, testing cross-tenant access using the same document ID is especially valuable.

## 13. Self-Check

**Question 1.** Alice logs in successfully and `isAuthenticated()` returns `true`. Is Alice allowed to call an endpoint requiring `hasAuthority("invoice:approve")`?

**Answer:** Only if `Authentication` carries the `invoice:approve` authority and other policies also permit it. Authentication status alone is not enough.

**Question 2.** Under Spring Security defaults, why can `hasRole("AUDITOR")` and `hasAuthority("AUDITOR")` return different results?

**Answer:** `hasRole("AUDITOR")` checks the string `ROLE_AUDITOR` using the default prefix, whereas `hasAuthority("AUDITOR")` checks the exact string `AUDITOR`. The result depends on the granted authorities and prefix configuration.

**Question 3.** Why should `authentication.isAuthenticated()` not be used as the sole test to distinguish anonymous guests from logged-in users?

**Answer:** `AnonymousAuthenticationToken` can carry `isAuthenticated() == true` even though it represents an anonymous principal. Spring Security's authorization and trust resolver mechanisms distinguish this token type.

**Question 4.** If Alice has `document:read`, does Alice have permission to view a document belonging to Bob?

**Answer:** Insufficient information. General read permission is not permission for every object. If the policy requires the owner to match the principal or belong to the same tenant, that policy must be checked against server-controlled data.

**Question 5.** A JWT has the claim `roles=["ADMIN"]`. Why might `hasRole("ADMIN")` still fail?

**Answer:** A role claim is only useful for Spring Security authorization if a converter is configured to map it into the appropriate `GrantedAuthority` (usually `ROLE_ADMIN`). Reading a raw JWT claim does not mean the authority has been granted in `Authentication`.

## 14. Conclusion and Further Reading

**Authentication establishes a trusted subject; authorization evaluates grants and policies against the specific operation and resource.** In Spring Security, both sets of data can reside in `Authentication`, yet they answer two distinct questions. Understanding this helps you choose the right APIs—`getName`, `getAuthorities`, `hasAuthority`, `hasRole`—and avoid granting access merely because a user logged in.

Official documentation:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
