# Authentication, Principal, and the GrantedAuthority Collection Used in Authorization Checks

> **Module:** Spring Security - authorization  
> **Knowledge group:** Authorities and roles  
> **Learning goal:** Understand how Spring Security carries the authenticated identity and general permissions into an authorization decision; distinguish `Authentication`, `principal`, `GrantedAuthority`, `role`, and `scope`; know how to read, use, test, and handle cases prone to privilege escalation.

## 1. When the system checks permissions, what information is it reading?

Suppose Alice logs in successfully and is assigned the following authorities:

```text
principal = alice
authorities = [
  "ROLE_EDITOR",
  "document:read",
  "document:edit"
]
```

Alice sends `GET /api/documents/42`. A `hasAuthority("document:read")` check can allow it through at the HTTP layer because Alice's authority collection contains the exact string `document:read`. If Alice sends `DELETE /api/documents/42` while the application requires `document:delete`, the corresponding check will deny it if that authority is missing.

What about whether Alice is allowed to edit **document 42**? `document:edit` only proves a general functional permission; if the document belongs to another tenant, is locked, or Alice is not the owner/assigned editor, it must still be denied according to business policy. That is why three questions must be separated:

1. **Authentication:** who is the caller, and have they been authenticated by a trusted mechanism?
2. **Authority/role:** what general permissions have been granted by the system to that identity?
3. **Resource authorization:** for the specific resource and context, does the business rule permit performing this action?

In Spring Security, the central object connecting questions 1 and 2 to the authorization decision step is `Authentication`. It holds the principal and the collection of `GrantedAuthority` instances; many `AuthorizationManager` implementations read these authorities to make decisions.

## 2. Five concepts not to confuse

| Concept | Role | Example |
| --- | --- | --- |
| `SecurityContextHolder` | Entry point to the current security context in a Servlet application | Retrieve the `SecurityContext` of the currently executing thread |
| `SecurityContext` | Holds the current `Authentication` | `context.getAuthentication()` |
| `Authentication` | Represents an authentication request or the currently authenticated identity | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken` |
| `principal` | Entity identifying the caller, stored as a property inside `Authentication` | `UserDetails`, `Jwt`, `OidcUser`, custom principal |
| `GrantedAuthority` | A permission/role/scope granted to the principal | `ROLE_ADMIN`, `document:read`, `SCOPE_files.read` |

`Authentication` is an interface extending `java.security.Principal` and provides key methods such as `getName()`, `getPrincipal()`, `getCredentials()`, `getDetails()`, `getAuthorities()`, and `isAuthenticated()`. **`getPrincipal()` returns `Object`**, with no guarantee that it is always a `String` or `UserDetails`.

One way to visualize it:

```text
SecurityContextHolder
  └── SecurityContext
       └── Authentication
            ├── principal: identity
            ├── authorities: Collection<? extends GrantedAuthority>
            ├── credentials: authentication proof; usually erased once authenticated
            ├── details: mechanism-specific metadata
            └── authenticated: status depending on Authentication type

AuthorizationManager
  ├── reads Authentication, when the rule needs identity/permissions
  ├── matches authority/role or runs custom policy
  └── ALLOW / DENY depending on the decision type of the version in use
```

**Key takeaway:** principal answers "who", while authority answers "what general permissions are granted". Both are **inputs** to authorization; they do not by themselves decide permissions on individual business objects.

## 3. Authentication has two lifecycles: unauthenticated and authenticated

`Authentication` can be used at two different points in time:

**Before authentication:** a filter reads credentials from the request and creates an `Authentication` requesting authentication. For example, a token containing username + password usually starts in an unauthenticated state. It is passed to `AuthenticationManager`, typically implemented by `ProviderManager` coordinating with one or more `AuthenticationProvider` instances.

**After authentication:** the provider verifies the proof, determines the trusted principal and authorities, and returns an `Authentication` representing the authenticated identity. Depending on the mechanism, it is stored in `SecurityContext` for authorization interceptors to use during the current request. With sessions, the context may be loaded/saved via `SecurityContextRepository`. With bearer tokens, token authentication typically happens per request.

```text
HTTP request
   |
   v
Authentication filter
   |
   | credentials/token from request
   v
AuthenticationManager / AuthenticationProvider
   |
   | verify credential/token and load permissions from trusted source
   v
Authenticated Authentication
   |
   v
SecurityContext
   |
   v
Authorization filter / method interceptor
   |
   | use getAuthorities(), getName(), principal, resource...
   v
ALLOW or DENY
```

Practical example: a user having `ROLE_ADMIN` in the database does not mean a client can self-send an `X-Role: ADMIN` header to obtain that authority. A server-trusted provider or converter must verify the source, map it, and grant the authority onto `Authentication`.

**Do not manually set `isAuthenticated=true`** on unverified request data. That value is an internal token state, not cryptographic proof or a guarantee that permissions came from a trusted source. Issuing an authenticated token must belong to valid authentication infrastructure.

## 4. Inside Authentication: what is each field used for?

| Component | Function | Notes for authorization |
| --- | --- | --- |
| `getPrincipal()` | Returns the principal object | May be `UserDetails`, `Jwt`, an OIDC principal, or a custom type; determine the type before casting |
| `getName()` | Returns the identifier name per implementation | May be username or `sub` claim; do not assume it is a DB/tenant ID |
| `getAuthorities()` | Returns the set of general permissions as a collection | Check exact authority string values or use an appropriate manager/policy |
| `getCredentials()` | Authentication proof, such as password/token | Do not use as a permission source, do not log; may have been erased after authentication |
| `getDetails()` | Metadata related to the authentication process | May include IP address, session ID depending on mechanism; do not assume it is trusted fact for domain policy |
| `isAuthenticated()` | State of the token per implementation | **Not sufficient** to determine that a request is a real user rather than anonymous |
| `getName()` via `Principal` | Name representing the identity | Not an authorization model or ACL |

The following Servlet example **only illustrates how to read** in code running under Spring Security; the endpoint must be protected before access. It is not a standalone Java file:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.List;
import java.util.Objects;

class CurrentAuthenticationView {
    static void inspectCurrentAuthentication() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null) {
            return; // No Authentication in this context yet.
        }

        String name = authentication.getName();
        Object principal = authentication.getPrincipal();
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        // Use in controlled internal processing.
        // Do not log credentials/tokens or the entire principal.
    }
}
```

`SecurityContextHolder` uses `ThreadLocal` as the default strategy on Servlet. Spring Security provides mechanisms to set and clear the context in the filter chain. Do not keep a reference to `Authentication` in a `static` variable shared across requests, and do not assume a task running on another thread automatically has the right context.

## 5. Principal is not always a username

The principal type changes depending on how the application authenticates:

| Authentication mechanism | Common principal | What you should know |
| --- | --- | --- |
| Form login / username-password | `UserDetails` or custom principal | Can read `getUsername()`, or internal identifier from a custom type |
| HTTP Basic with `UserDetailsService` | Usually `UserDetails` | May be an object from the service or another wrapper depending on configuration |
| OAuth2 Resource Server JWT | Usually `Jwt` inside `JwtAuthenticationToken` | `getName()` usually reads the `sub` claim with the default converter |
| OAuth2 Login / OIDC | `OAuth2User` / `OidcUser` | Has attributes/claims; type and name mapping depend on the provider |
| Anonymous authentication | `anonymousUser` or configured value | Does not represent a real logged-in identity |
| Custom system | Application-designed principal | Define a stable contract and check it at the adapter |

In Spring MVC you can conveniently obtain the principal using `@AuthenticationPrincipal`:

```java
// Only makes sense when the authentication mechanism actually uses UserDetails.
@GetMapping("/api/my-username")
public String myUsername(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

For a JWT resource server, a `UserDetails` parameter like above is usually unsuitable; use the `Jwt` type if the converter has been confirmed:

```java
// MVC snippet with bearer JWT, used when the principal is actually Jwt.
@GetMapping("/api/my-subject")
public String mySubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
```

These snippets are controller methods with corresponding imports/beans, **not** standalone Java programs to run with `javac`. In a controller you can accept `Authentication` directly or use `@CurrentSecurityContext` when you need the whole context. Do not cast `(UserDetails) authentication.getPrincipal()` everywhere; JWT/OIDC/anonymous can cause `ClassCastException`.

### Business identifiers should be normalized

`authentication.getName()` is often useful for representing the subject, but multi-tenant applications need clear rules:
- Which issuer does the immutable/stable subject ID belong to?
- If two identity providers both issue `sub="123"`, could they collide? When needed, key the identity by issuer + subject.
- Can users change their email/username? If so, do not use display email as a long-term permission key.
- Does the tenant being accessed truly belong to that identity?
- If a user has a personal account but is acting on behalf of an organization, where is the organizational context verified?

An adapter such as `AuthenticatedActorResolver` can turn a verified `Authentication` into a trusted `Actor(userId, tenantId, memberships)`. Business policies receive `Actor` instead of coupling all logic directly to JWT/UserDetails structure.

## 6. How does GrantedAuthority work?

The `GrantedAuthority` interface has one primary method:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

The most common form is `SimpleGrantedAuthority`, holding a string such as `ROLE_EDITOR` or `document:read`. A `hasAuthority("document:read")` check requires a `GrantedAuthority#getAuthority()` equal to that exact string; it does not infer it from a role name and does not analyze owner/tenant relationships.

There are complex `GrantedAuthority` types where `getAuthority()` returns `null` because they cannot be represented concisely as a single string. In that case, ordinary string-based managers will not understand this complex permission; a custom `AuthorizationManager` that knows how to handle that authority type is required.

For example, suppose an `Authentication` has exactly three authorities:

```text
ROLE_EDITOR
document:read
SCOPE_documents.write
```

| Check | Typical result | Reason |
| --- | --- | --- |
| `hasAuthority("ROLE_EDITOR")` | ALLOW | Matches authority string |
| `hasRole("EDITOR")` | ALLOW | Looks for `ROLE_EDITOR` by default |
| `hasAuthority("EDITOR")` | DENY | No `EDITOR` string present |
| `hasRole("ROLE_EDITOR")` | Should not be written | `hasRole` already applies the prefix convention; DSL APIs may reject this argument |
| `hasAuthority("document:read")` | ALLOW | Exact match |
| `hasAuthority("document:write")` | DENY | Lacks this permission |
| `hasAuthority("SCOPE_documents.write")` | ALLOW | Matches converted scope string |
| `hasAuthority("documents.write")` | DENY | Missing `SCOPE_` |
| `hasRole("ADMIN")` | DENY | No `ROLE_ADMIN` present |

The results above assume a valid authenticated flow and Spring Security's default conventions, with no custom prefix or custom manager. The policy must define which authorities are functional permissions, which are roles, and which reflect scopes from external systems.

## 7. How does a role actually relate to GrantedAuthority?

In Spring Security, **a role is typically an authority with a prefix** `ROLE_`. Under default configuration:

```text
hasRole("ADMIN")            ~= hasAuthority("ROLE_ADMIN")
hasRole("EDITOR")           ~= hasAuthority("ROLE_EDITOR")
hasAuthority("document:edit")  = exact match for string "document:edit"
```

The `~=` symbol means equivalent in authority requirement in common scenarios, though not every custom `AuthorizationManager` behaves identically. The default prefix can be customized via `GrantedAuthorityDefaults` or related configuration. When changing the prefix, it must stay consistent with how authorities are built, HTTP checks, method security, tests, legacy data, and JWT converters.

A role can represent multiple permissions in an application's domain design, but Spring Security **does not automatically know** that "EDITOR implicitly has `document:read` and `document:edit`" solely from the name `ROLE_EDITOR`. If a policy checks `hasAuthority("document:edit")`, you must actually grant the `document:edit` authority or use an explicit role → permission resolution rule.

Example:

```text
Alice:
  GrantedAuthority("ROLE_EDITOR")

Policy A: hasRole("EDITOR")             -> allowed
Policy B: hasAuthority("document:edit") -> denied
```

If the team wants the EDITOR role to include document editing permission, that role can be mapped into a set of authorities at login time or via an explicit policy service. Do not expect the two check styles to align automatically.

For naming, you should:
- Use `ROLE_*` for roles following the default convention.
- Use consistent codes such as `document:read`, `document:edit` for general permissions.
- Use `SCOPE_*` when authorities are mapped from OAuth2 scopes following resource server conventions.
- Verify case sensitivity: `ROLE_ADMIN` differs from `ROLE_admin`.
- Do not create a separate authority for each of millions of records as a substitute for ACLs/per-resource policies.

## 8. Standalone Java 17+ example: permission data and matching

The goal of this example is to simulate **how authority strings are matched**. This is not Spring Security internal code, performs no login, and must not be used as an authentication layer; assigning `AuthSnapshot` in the demo represents data **already issued and verified by the server**.

Save as `AuthorityCheckDemo.java`:

```java
import java.util.List;

public class AuthorityCheckDemo {

    record AuthSnapshot(String subjectId, List<String> authorities) {}

    static boolean hasAuthority(AuthSnapshot auth, String required) {
        return auth.authorities().contains(required);
    }

    static boolean hasRole(AuthSnapshot auth, String role) {
        return hasAuthority(auth, "ROLE_" + role);
    }

    static boolean mayEditDocument(
        AuthSnapshot auth, String documentOwnerId
    ) {
        return hasAuthority(auth, "document:edit")
            && auth.subjectId().equals(documentOwnerId);
    }

    public static void main(String[] args) {
        AuthSnapshot alice = new AuthSnapshot("alice", List.of(
            "ROLE_EDITOR",
            "document:read",
            "document:edit"
        ));

        AuthSnapshot bob = new AuthSnapshot("bob", List.of(
            "ROLE_VIEWER",
            "document:read"
        ));

        System.out.println("Alice hasRole EDITOR: "
            + hasRole(alice, "EDITOR"));
        System.out.println("Alice hasAuthority EDITOR: "
            + hasAuthority(alice, "EDITOR"));
        System.out.println("Alice hasAuthority ROLE_EDITOR: "
            + hasAuthority(alice, "ROLE_EDITOR"));
        System.out.println("Bob read: "
            + hasAuthority(bob, "document:read"));
        System.out.println("Bob edit: "
            + hasAuthority(bob, "document:edit"));
        System.out.println("Alice edits own doc: "
            + mayEditDocument(alice, "alice"));
        System.out.println("Alice edits Bob's doc: "
            + mayEditDocument(alice, "bob"));
    }
}
```

Run with JDK 17 or higher:

```bash
javac AuthorityCheckDemo.java
java AuthorityCheckDemo
```

Exact output:

```text
Alice hasRole EDITOR: true
Alice hasAuthority EDITOR: false
Alice hasAuthority ROLE_EDITOR: true
Bob read: true
Bob edit: false
Alice edits own doc: true
Alice edits Bob's doc: false
```

Observations:

1. `hasRole("EDITOR")` looks up `ROLE_EDITOR` by convention; checking plain authority `EDITOR` does not match.
2. Bob has read permission but not edit permission.
3. Alice has `document:edit` yet is still not allowed to edit Bob's document in the simulated policy because the owner condition is not met.
4. Real applications must also check tenant, status, database facts, delegated permissions, and transaction safeguards.
5. The plain Java snippet does not represent `AuthenticationTrustResolver`, anonymous users, token validation, or the full `AuthorizationManager`. It intentionally focuses only on authority lookup.

## 9. HTTP configuration: how are authorities used?

A **partial** Servlet configuration example for Spring Boot 3 / Spring Security 6.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/public/**")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/**")
                .hasAuthority("document:edit")
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/me")
                .authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

This snippet defines **authorization rules** without configuring login infrastructure, sessions, token decoders, or CSRF; this class alone cannot be treated as a complete runnable application.

Interpretation:

- `GET /api/documents/42` requires `document:read` in `Authentication#getAuthorities()`.
- `PATCH /api/documents/42` requires `document:edit`, but still needs policy checks on record 42 after loading from a trusted source.
- `/api/admin/**` requires the `ROLE_ADMIN` authority by default.
- `GET /api/me` requires an identity recognized as validly authenticated.
- Requests not matching a specific rule are blocked by `denyAll`.

**Matcher order matters:** rules are evaluated in declaration order, and the first matching rule decides. Therefore, a broad matcher like `/api/**.permitAll()` placed before specific matchers can nullify the protection intended by later rules.

For endpoints using sessions/cookies to perform PATCH/POST/DELETE, CSRF must be configured and tested according to the architecture; do not disable CSRF just to make requests pass. The authorization layer does not replace authentication, CORS/CSRF, or business policies.

## 10. Method security reads the same Authentication

HTTP security is the enforcement point at the request boundary; method security is the enforcement point on Spring bean methods. Enable it with `@EnableMethodSecurity` and then use `@PreAuthorize`:

```java
// Service snippet; repository, document, and policy types are application-defined.
@Service
class DocumentService {
    private final DocumentRepository repository;
    private final DocumentPolicy documentPolicy;

    DocumentService(DocumentRepository repository,
                    DocumentPolicy documentPolicy) {
        this.repository = repository;
        this.documentPolicy = documentPolicy;
    }

    @PreAuthorize("hasAuthority('document:edit')")
    @Transactional
    public void rename(long id, String newTitle, Actor actor) {
        Document document = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(DocumentNotFoundException::new);

        if (!documentPolicy.mayRename(actor, document)) {
            throw new AccessDeniedException("No permission to rename");
        }

        document.rename(newTitle);
    }
}
```

The snippet above illustrates integration, not a standalone Java file: repository, entity, Actor, and exception are application-defined business types; Spring annotations/exceptions must be imported accordingly.

The `@PreAuthorize` layer asks "does the caller have `document:edit`?"; the policy service asks "on this record, in this tenant and this state, is this person allowed to rename it?".

**Important condition:** `Actor` must be mapped by the server from a trusted `Authentication`, never accepting `Actor`/`tenantId`/`role` intact from a client-declared body. When a service has multiple entry points (HTTP, job, listener), you must not rely solely on HTTP matchers.

Method security typically goes through an AOP proxy. Calling `this.rename(...)` from another method of the same object can bypass the `@PreAuthorize` interceptor. If a use case requires protection across every call path, design a policy guard inside the service or ensure calls go through the proper bean/proxy.

## 11. Accessing Authentication and principal in controllers/services

Three common approaches in Servlet:

**Approach A — Receive `Authentication` in a Spring MVC controller:** on a properly protected endpoint, Spring MVC can pass the authenticated principal into the method.

```java
@GetMapping("/api/me")
public String currentName(Authentication authentication) {
    return authentication.getName();
}
```

**Approach B — Read from context when running on the same thread:**

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String subject = authentication.getName();
}
```

This is only a read operation, not a complete "logged in" check. An existing `Authentication` could be anonymous. In shared singleton components, avoid caching usernames in fields. For logic needing permission checks, use Spring Security authorization APIs instead of repeatedly hand-writing `if (authentication != null)`.

**Approach C — Retrieve the configured principal type with `@AuthenticationPrincipal`:** suitable when you are certain the principal is `UserDetails` or `Jwt`. If you want to read the whole context, use `@CurrentSecurityContext`.

| API | What do you receive? | Points to watch |
| --- | --- | --- |
| `@AuthenticationPrincipal` | `Authentication#getPrincipal()` | Type depends on the authentication mechanism |
| `Authentication` parameter in MVC | Authentication object representing the request principal | For anonymous, MVC's resolution from the Servlet principal may return null |
| `@CurrentSecurityContext` | `SecurityContext` | Retrieves the contained authentication, including anonymous types depending on filters |
| `SecurityContextHolder.getContext()` | Current context per holder strategy | Bound to the Servlet thread by default |
| `authentication.getAuthorities()` | Authority collection | Should not be logged in full if it contains sensitive internal permission info |

When passing identity deeper into the domain, map it to the application's `Actor` at the boundary and pass it explicitly, so the domain does not depend on `SecurityContextHolder` or token types.

## 12. Anonymous authentication and the isAuthenticated() trap

Spring Security supports `AnonymousAuthenticationToken`. If a request has no real logged-in user, `AnonymousAuthenticationFilter` can place an authentication representing an anonymous guest into `SecurityContext`. This helps the system handle anonymous flows consistently.

Trap:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

// DO NOT use this condition to conclude a real user is logged in:
if (auth != null && auth.isAuthenticated()) {
    // May contain an AnonymousAuthenticationToken.
}
```

Some `AnonymousAuthenticationToken` instances are marked authenticated by implementation, even though the caller is still an anonymous guest in the security sense. Therefore:

- A token's `isAuthenticated()` **does not mean** "a real user has proven their identity".
- The `.authenticated()` DSL and the `isAuthenticated()` expression in Spring Security check points apply proper anonymous/trust resolution differentiation.
- `permitAll` grants public access per configuration; it does not mark the client as having business permissions.
- If you need to distinguish anonymous/remember-me/fully authenticated, use the capabilities provided by the framework (for example `fullyAuthenticated()`) with clear authentication contracts.
- Avoid assigning sensitive permissions like `ROLE_ADMIN` to an anonymous token or using `ROLE_ANONYMOUS` as an indicator of a real user permission.

For anonymous requests in MVC, an `Authentication` parameter resolved from the Servlet principal may be `null` even if `SecurityContext` holds `AnonymousAuthenticationToken`. If you need to inspect anonymous auth directly, use `@CurrentSecurityContext`.

## 13. Where does the authority collection come from?

The authorities collection is typically created/mapped during authentication, for example:

| Source | How authorities are formed | What to control |
| --- | --- | --- |
| Username/password + `UserDetailsService` | `UserDetails#getAuthorities()` from user/role store | Permissions loaded from trusted DB/config; understand refresh timing |
| LDAP/AD | Authentication provider mapper | Distinguish actual groups from internal permissions |
| HTTP Basic | After verifying credentials, uses principal's authorities | Basic is only a credential transport, not a permission source |
| OAuth2 Resource Server JWT | Converter turns verified claims/scopes into authorities | Validate signature, expiry, issuer, audience per deployment requirements; explicit claim mapping |
| OAuth2 Login/OIDC | User authority/claims mapper | Distinguish identity claims from actually granted permissions |
| Custom SSO/token | Custom `AuthenticationProvider`/converter | Do not accept self-declared authorities from the client |

Spring Security Resource Server JWT by default typically reads scopes from the `scope`/`scp` claim and maps them to authorities prefixed with `SCOPE_`. For example, a scope claim `documents.read` can yield:

```text
JWT scope: "documents.read"
    |
    v
GrantedAuthority("SCOPE_documents.read")
    |
    v
hasAuthority("SCOPE_documents.read") -> ALLOW
```

This **does not automatically create** `ROLE_ADMIN` nor `document:read`. To use `hasRole("ADMIN")` or `hasAuthority("document:read")`, the application must have an explicit, tested mapping from trusted claims/permission sources. When customizing `JwtGrantedAuthoritiesConverter`, the claim name and prefix can change.

**Note on JWT:** the `sub` claim identifies the subject; `scope` describes the token's scope; `roles` if present is data per the agreed issuer, not automatically application roles. Tokens must have their signature, valid algorithm, validity period, issuer/audience, and corresponding system requirements verified. Never take permissions from a JWT payload not accepted by a trusted verifier.

**Note on sessions:** authorities attached to an `Authentication` stored in a session may reflect a snapshot at login time. If roles change in the database but the session is not refreshed/invalidated, old permissions can remain active. You must design revocation, context updates, session invalidation, or re-query policy at the time sensitive actions are processed.

## 14. An Authentication holding an authority does not mean owner of every object

Suppose Bob and Alice both have `ROLE_EDITOR`, but only Alice is the owner of document 42.

```text
Authentication(Alice)
  principal = alice
  authorities = ["ROLE_EDITOR", "document:edit"]

Authentication(Bob)
  principal = bob
  authorities = ["ROLE_EDITOR", "document:edit"]

Document 42:
  owner = alice
  tenant = org-a
  status = DRAFT
```

Both can pass `hasAuthority("document:edit")` when calling the same API. But when checking `policy.canEdit(actor, document)`:
- Alice is allowed to edit if the tenant matches and the status permits.
- Bob is denied if the policy requires owner or a specific grant and Bob lacks the corresponding permission.

Therefore, a complete design can look like:

```text
ALLOW when
   isAuthenticatedByTrustedMechanism
AND hasAuthority("document:edit")
AND actor.tenantId == document.tenantId
AND (actor.id == document.ownerId OR hasResourceGrant(actor, document, WRITE))
AND document.status == DRAFT
```

Do not mechanically use `principal.name` for owner comparisons if the domain stores immutable IDs, tenants, and different issuers. The relationship between principal and entity must be confirmed through a trusted mapper.

**Do not stuff a separate authority per document** such as `DOCUMENT_42_EDITOR` into identities for millions of records. Per-object permissions should generally live in ACLs, policy services, or actor-scoped queries, rather than bloating authorities in sessions/tokens.

## 15. Check rules can combine multiple authorities

Depending on the API/DSL and version, there can be several decision styles:

- `hasAuthority("document:read")`: requires one exact authority.
- `hasAnyAuthority("document:read", "document:admin")`: satisfies **at least one** authority.
- `hasRole("ADMIN")`: checks role by convention.
- `hasAnyRole("EDITOR", "ADMIN")`: accepts one of the listed roles.
- Combined checks using a custom policy: has the appropriate role **and** belongs to the tenant **and** is operating on an allowed resource type.
- `@PreAuthorize("hasAuthority('document:edit') and ...")`: expresses conditional logic in method security, though long SpEL expressions hard to audit should be avoided.
- Custom `AuthorizationManager`: used when reusable complex rules or data from services/domain are needed.

For a requirement of "having both READ and WRITE", do not use `hasAnyAuthority("READ", "WRITE")` thinking it is an AND operation. You must build a rule that genuinely requires both or use a policy service. Similarly, if `ROLE_ADMIN` must still pass a tenant check, do not write an OR branch for ADMIN that accidentally bypasses the entire tenant condition.

In authority-based configurations, authorization should not be scattered into inconsistent manual checks across controllers, services, event listeners, and queries. A unified policy, invoked at appropriate entry points, is easier to test.

## 16. Servlet runtime, other threads, and WebFlux

In a **Servlet** application, `SecurityContextHolder` uses `ThreadLocal` by default. Code on the same request thread can read the context. But when you spawn a new thread, use `@Async`, an executor, or a scheduler, do not assume the request context is safely propagated.

Mechanisms like `DelegatingSecurityContextRunnable` or `DelegatingSecurityContextExecutor` can help propagate context in Servlet tasks when justified. Lifecycle must be controlled: do not keep an old user beyond the task scope, and do not use `MODE_GLOBAL` in a multi-user web app.

In a **Reactive WebFlux** application, context is attached to the Reactor sequence via `ReactiveSecurityContextHolder`; you cannot assume reading via Servlet-style `SecurityContextHolder` in a reactive flow is correct. The `SecurityContextHolder` snippets in this article are for **Servlet**.

A background job running under a service account needs an explicit identity/capability and appropriate authorization applied; do not arbitrarily pick up the last user left on a thread or use implicit admin permissions.

## 17. Error outcomes: authentication and authorization are two distinct branches

Common scenarios:

| Situation | Primary outcome | Common HTTP status |
| --- | --- | --- |
| No valid credentials for an endpoint requiring login | Initiates authentication or rejects | 401 for APIs, possibly 302 to login for web forms |
| Logged in but missing `document:read` | Authorization deny | Usually 403 |
| Has `document:read` but lacks permission to view object 42 | Resource authorization deny | 403 or 404 depending on existence-hiding strategy |
| Has permission but object does not exist | Resource not found | 404 |
| Has permission but object is already APPROVED, cannot edit | Business condition rejects operation | Appropriate domain error code, e.g. 409 |

Note that exact responses also depend on `AuthenticationEntryPoint`, `AccessDeniedHandler`, application exception handling, and login mechanisms. Do not assume that whenever `auth != null` it must return 403; an anonymous request may hold a technical authentication object yet still needs to be prompted to authenticate.

Avoid logging credentials, raw bearer tokens, passwords, sensitive claim contents, or the entire `principal`. For diagnosing authorization, log request/correlation ID, normalized actor ID, action, resource ID, decision, and a safe reason per audit policy.

## 18. Testing authority grants and enforcement points properly

A simple matrix for testing:

| Principal and authorities | Requirement | Expected result |
| --- | --- | --- |
| Alice: `ROLE_EDITOR`, `document:read` | `hasRole("EDITOR")` | ALLOW |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("EDITOR")` | DENY |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("ROLE_EDITOR")` | ALLOW |
| Alice: `ROLE_EDITOR`, `document:read` | `hasAuthority("document:edit")` | DENY |
| Bob: `SCOPE_documents.read` | `hasAuthority("SCOPE_documents.read")` | ALLOW |
| Bob: `SCOPE_documents.read` | `hasAuthority("document:read")` | DENY if unmapped |
| Anonymous | `authenticated()` | DENY |
| Alice has `document:edit` but lacks permission on object 42 | Object policy | DENY |
| Alice has `document:edit` and is owner of object 42 in same tenant DRAFT | Object policy | ALLOW |

You can use Spring Security Test to mock identity at the method or HTTP layer:

```java
// Test snippet; requires spring-security-test and an appropriate test environment.
@Test
@WithMockUser(username = "alice", authorities = {"document:read"})
void readerCanRead() {
    // Call endpoint/service requiring document:read; assert 200/allow.
}

@Test
@WithMockUser(username = "alice", roles = {"EDITOR"})
void editorHasRole() {
    // Call endpoint/service requiring hasRole("EDITOR").
}
```

`@WithMockUser(roles={"EDITOR"})` creates authority `ROLE_EDITOR` by convention; `authorities={"document:read"}` creates authorities as literal strings. **Do not assume** the mock user also has `document:read` simply because it has `ROLE_EDITOR`. If configuration requires both role and permission, pass the full authorities explicitly in the fixture or provide a custom security context.

Key testing levels:

1. **Unit:** permissions are mapped accurately from user/role data; helpers/policies cover ALLOW, DENY, missing authority, and other cases.
2. **Method security:** enable `@EnableMethodSecurity`, ensure annotations actually run through proxies, and test self-invocation/alternate paths per architecture.
3. **HTTP:** test GET/PATCH/DELETE matchers, missing/sufficient permissions, anonymous/authenticated, 401/403, and CSRF per configuration.
4. **JWT integration:** use tested tokens/decoders to verify role/scope converters, issuer/audience, expiry, renamed claims, and that permissions do not appear automatically.
5. **Domain policy:** vary only object owner/tenant/status to prove access or denial on records, not just checking roles at the boundary.
6. **Revocation:** change roles, lock accounts, remove groups, then retry via old session/cache/token according to expiration/current-permission contracts.

**Test trap:** a POST/PATCH returning 403 due to a missing CSRF token does not prove `hasAuthority` is blocking it. Tests must eliminate confounding causes, establish proper authentication and a valid request, and then vary **only** the authority set or resource condition to verify the conclusion.

## 19. Mistakes that cause vulnerabilities or break permissions

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Casting every principal to `UserDetails` | Fails with JWT/OIDC/anonymous | Check actual principal type or use a mapping adapter |
| Treating `getName()` as always a DB user ID | Permissions assigned to wrong user, tenant/issuer confusion | Normalize a stable ID from a trusted source |
| Checking only `auth != null && auth.isAuthenticated()` | May mistake anonymous for real user | Use standard `authenticated()` DSL / trust resolver |
| Treating `hasRole("EDITOR")` as `hasAuthority("EDITOR")` | Unexpected deny | Understand the default `ROLE_` prefix |
| Passing `ROLE_ADMIN` into `hasRole` | Misuses API convention, may cause config error | Call `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Assuming a JWT with `scope` grants `document:read` | Endpoint denied or rule checks wrong permission | Configure converter and test `SCOPE_` |
| Trusting header/body `role=admin` | Privilege escalation | Authorities are issued only by authentication infrastructure |
| Checking only general permissions at the URL | IDOR/BOLA on individual documents | Add tenant/object policies |
| Stuffing every object permission into authorities | Bloated token/session, hard to revoke | ACLs/resource policies/scoped queries |
| Storing `Authentication` in a static variable | Cross-request identity leakage | Keep context within proper scope and lifecycle |
| Using Servlet-style `SecurityContextHolder` in WebFlux | Wrong/lost reactive context | Use `ReactiveSecurityContextHolder` |
| Using `@PreAuthorize` then calling within same bean via `this` | May bypass method interceptor | Route calls through proxy / guard inside use case |
| Changing roles only in the database | Old session/token/cache still holds permissions | Design refresh/revoke/invalidation |
| Logging full principal/credentials | Leaks secrets/user info | Minimal, controlled auditing |

## 20. Checklist when adding an authorization rule

1. **Identity:** what is the actual principal type? How does `getName()` map to the domain actor ID and tenant?
2. **Permission source:** are authorities created in `UserDetailsService`, provider, JWT converter, or custom mapper? Is it trusted?
3. **Permission naming:** using `ROLE_*`, `SCOPE_*`, or permission codes like `document:read`? Is the prefix customized?
4. **Rule:** need one authority, multiple authorities with OR/AND, or an object/context-based policy?
5. **Enforcement points:** which HTTP matchers, methods, service use cases, background jobs, lists/exports/downloads need protection?
6. **Domain boundaries:** are tenant, owner, group, status, delegation, and transaction checks applied after general permissions?
7. **Special identities:** how are anonymous, remember-me, tokens from other issuers, stale sessions, and requests missing context handled?
8. **Revocation:** when do role/scope changes take effect across sessions/JWTs/caches?
9. **Testing:** are there cases for ALLOW/DENY, missing permissions, prefixes, JWT claims, alternate entry points, CSRF, and cross-tenant objects?
10. **Observability:** are authentication/authorization/domain errors and audits clearly distinguished without leaking data?

**Self-check:**

- Alice has `ROLE_EDITOR` but only `document:read`. Does an API using `hasAuthority("document:edit")` allow her through? → **No**. Role EDITOR does not automatically generate edit permission if not mapped.
- A JWT has scope `documents.read`; what authority does the default converter map it to? → Typically `SCOPE_documents.read`; `hasAuthority("documents.read")` does not match.
- A controller calls `authentication.getPrincipal()` and casts it to `UserDetails`; what happens when switching to Resource Server JWT? → The principal is usually `Jwt`, so the cast can fail; the adapter or reading approach must change.
- An `AnonymousAuthenticationToken` has `isAuthenticated() == true`. Should it be treated as a logged-in user? → **No**; use the trust resolver / Spring Security's authenticated check mechanism.
- Bob has `document:edit` but the document belongs to Alice's tenant. Can he edit it? → **No**, if the policy requires the same tenant and no valid delegation exists.

**Main point:** `Authentication` represents the identity in the security context, `principal` is the identifying information inside it, and `GrantedAuthority` is the set of general permissions granted by a trusted authentication/authorization source. Spring Security can match roles/authorities with `hasRole`/`hasAuthority`, but permissions on **individual business objects** must still be thoroughly checked by the application.

## References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/anonymous.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
