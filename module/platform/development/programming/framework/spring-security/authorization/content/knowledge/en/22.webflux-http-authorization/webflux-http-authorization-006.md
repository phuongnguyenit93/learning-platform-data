# `AuthorityReactiveAuthorizationManager` and Checking Roles and Authorities

## 1. Lesson goals

In a **Spring WebFlux** application, Spring Security must decide which requests may proceed based on the authenticated identity and the caller's `GrantedAuthority` values. `AuthorityReactiveAuthorizationManager<T>` is a built-in implementation of `ReactiveAuthorizationManager<T>` dedicated to checking that an `Authentication` holds one or more required authorities.

After this lesson, you will be able to:
- Distinguish **role** from **authority** and understand the default `ROLE_` prefix.
- Choose correctly among `hasAuthority(...)`, `hasAnyAuthority(...)`, `hasRole(...)`, and `hasAnyRole(...)`.
- Attach rules to WebFlux `ServerHttpSecurity.authorizeExchange(...)` and `SecurityWebFilterChain`.
- Understand `Mono<Authentication>`, authorization results, and API differences between Spring Security 6.5 and 7.x.
- Inspect authorities produced from `UserDetails`, JWT scopes, or converters without confusing raw claims with mapped authorities.
- Combine HTTP authorization with reactive method security, tenant checks, and object-level authorization.
- Avoid mistaking **`hasAny`'s OR** for **AND**, mistaking a tenant-A role for a global role, and accidentally leaving routes unprotected.
- Test using an authority matrix and `WebTestClient`; recognize 401/403 responses and unauthenticated cases.

The parent context is **HTTP on WebFlux**: this is not a guide for Spring MVC/Servlet. Names to distinguish:
- WebFlux: `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange`, `ReactiveAuthorizationManager`, `Mono`.
- Servlet: `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests`, `AuthorizationManager`, `Supplier<Authentication>`.

Misusing Servlet APIs in a WebFlux configuration typically causes compilation errors or a filter chain that fails to protect the active web stack.

## 2. What does `AuthorityReactiveAuthorizationManager` do?

Full class name:

~~~text
org.springframework.security.authorization.AuthorityReactiveAuthorizationManager<T>
~~~

It implements:

~~~text
org.springframework.security.authorization.ReactiveAuthorizationManager<T>
~~~

Conceptually, the manager receives **an authentication stream** and **a secured object being authorized**:

~~~text
Mono<Authentication> ───────┐
                             ├── AuthorityReactiveAuthorizationManager
T securedObject ────────────┘            │
                                         v
                           AuthorizationResult / Decision
                                ALLOW or DENY
~~~

The manager reads `Authentication.getAuthorities()` and checks the specified authorities. It does **not by itself**:
- Verify passwords or JWT signatures.
- Read a document's database owner or ACL by ID.
- Prove a role is valid in the target tenant.
- Check request body data, balances, lock state, or business deadlines.
- Make decisions from the contents of `T object` when using only the built-in authority factories.

Its strength is fast, clear **functional/coarse-grained permission checks**. When rules depend on objects or context, you need a custom `ReactiveAuthorizationManager`, service policy, or scoped query.

### Relationship with reactive execution

In WebFlux, authorization integrates with Reactor publishers. `Mono<Authentication>` represents authentication that may not yet be resolved when assembling the pipeline; the framework controls subscription and evaluation per request.

Never call `block()` on the Netty event loop to fetch authentication or wait on an ACL service. When checks need I/O, compose with `Mono`/`Flux`, bounded client timeouts, and appropriate fail-closed behavior.

## 3. `GrantedAuthority`, roles, and actual string values

`Authentication` holds a `Collection<? extends GrantedAuthority>`; each `GrantedAuthority` typically returns a string from `getAuthority()`.

Example data:

~~~text
Authentication.getAuthorities() =
  "ROLE_ADMIN"
  "SCOPE_documents.read"
  "documents:write"
~~~

Read each string literally. `AuthorityReactiveAuthorizationManager.hasAuthority("documents:write")` looks for **exactly** `documents:write`. It does not add a prefix or translate it into `ROLE_...`.

A **role** in Spring Security is commonly represented as an authority prefixed with `ROLE_`. For instance, `ADMIN` is the readable role name, while the actual authority string may be `ROLE_ADMIN`.

Reference table:

| Call | Required authority | When appropriate? |
|---|---|---|
| `hasAuthority("ROLE_ADMIN")` | Exact `ROLE_ADMIN` | When you know the full mapped role string |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | When using the default role convention |
| `hasAuthority("ADMIN")` | Exact `ADMIN` | Only when raw `ADMIN` was actually granted |
| `hasAuthority("SCOPE_documents.read")` | Exact `SCOPE_documents.read` | When JWT resource server maps OAuth scopes this way |
| `hasAuthority("documents:write")` | Exact `documents:write` | Business authority granted verbatim |
| `hasRole("EDITOR")` | `ROLE_EDITOR` | When user/issuer converter creates the prefixed role |

**Important:** `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")` normally check the same authority; `hasAuthority("ADMIN")` is a different condition.

For `AuthorityReactiveAuthorizationManager` itself, the Javadoc states that `hasRole` adds the **`ROLE_`** prefix; do not assume a role-prefix bean configured for method expressions will automatically change this static factory's behavior. If your deployment uses a different naming scheme, use `hasAuthority("TENANT_ADMIN")` or build a custom manager with tested conventions.

## 4. Four primary static factories

In Spring Security 6.5 and 7.x, the documented factories are:

~~~java
AuthorityReactiveAuthorizationManager.hasAuthority("documents:read");
AuthorityReactiveAuthorizationManager.hasAnyAuthority(
        "documents:read", "documents:write");
AuthorityReactiveAuthorizationManager.hasRole("ADMIN");
AuthorityReactiveAuthorizationManager.hasAnyRole("ADMIN", "SUPPORT");
~~~

**These are manager-creation snippets**, not standalone Java files: you need Spring Security classes, imports, and a concrete generic type `T`.

| Factory | Condition | Logical relation |
|---|---|---|
| `hasAuthority(a)` | Actor has exact authority `a` | Single condition |
| `hasAnyAuthority(a,b,...)` | Actor has **at least one** authority in the set | OR |
| `hasRole(r)` | Actor has `ROLE_r` | Single prefixed condition |
| `hasAnyRole(r1,r2,...)` | Actor has at least one `ROLE_r*` | OR |

**"Any" does not mean "all".**

For an actor with only `documents:read`:
- `hasAnyAuthority("documents:read","documents:write")` → ALLOW.
- Requiring **both** read and write simultaneously → this actor must be DENIED.

If a policy requires **AND**, do not substitute `hasAnyAuthority`. You can combine a coarse HTTP gate with additional checks in a service method, or write a custom reactive manager with a defined contract. Some newer Spring Security versions add a factory for all-of authorities, but **do not assume it exists across every version** of `AuthorityReactiveAuthorizationManager`.

### Order and case sensitivity

Authorities are strings; do not expect `ROLE_admin` to automatically equal `ROLE_ADMIN`. Never uppercase client input to grant permissions unless the policy defines normalization. Roles and authorities must originate from trusted identity mapping with consistent naming conventions and case-exact tests.

## 5. Basic role/authority matching matrix

Assume these authentications:

| Principal | GrantedAuthorities |
|---|---|
| An | `ROLE_ADMIN`, `documents:read` |
| Binh | `ROLE_EDITOR`, `documents:write` |
| Chi | `ROLE_VIEWER`, `SCOPE_documents.read` |
| Dung | `ADMIN` (without `ROLE_`) |
| Unauthenticated guest | No valid authentication |

Expected outcomes:

| Policy | An | Binh | Chi | Dung |
|---|---:|---:|---:|---:|
| `hasRole("ADMIN")` | ALLOW | DENY | DENY | DENY |
| `hasAuthority("ROLE_ADMIN")` | ALLOW | DENY | DENY | DENY |
| `hasAuthority("ADMIN")` | DENY | DENY | DENY | ALLOW |
| `hasAnyRole("ADMIN","EDITOR")` | ALLOW | ALLOW | DENY | DENY |
| `hasAuthority("documents:write")` | DENY | ALLOW | DENY | DENY |
| `hasAnyAuthority("documents:read","SCOPE_documents.read")` | ALLOW | DENY | ALLOW | DENY |

The matrix shows that **actual authorities matter more than an "admin" label elsewhere**. Merely placing a `role: ADMIN` claim in a JWT does not guarantee Spring produces `ROLE_ADMIN`. An auth converter or `UserDetails` must translate claims into the proper `GrantedAuthority` instances.

In the HTTP stack, unauthenticated callers are typically handled by an authentication entry point returning 401/challenge or a redirect. Do not treat an "unauthenticated guest" row as equivalent to manually constructing an empty authentication with arbitrary authorities.

## 6. Version differences: `check` and `authorize`

This is a frequent source of compile errors when learning from older examples.

### Spring Security 6.5

Spring Security 6.5 Javadoc for `AuthorityReactiveAuthorizationManager<T>` lists:

~~~java
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication, T object);
~~~

In `ReactiveAuthorizationManager<T>` 6.5, `check(...)` is marked deprecated; `authorize(...)` is a **default** method introduced in 6.4 returning `Mono<AuthorizationResult>`. Still, the concrete 6.5 class implements `check(...)`, so do not assume `check` was already removed in 6.5.

### Spring Security 7.x

Spring Security 7.1 Javadoc lists:

~~~java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);
~~~

In the 7.x interface, `authorize(...)` is the method to implement; `check(...)` is no longer in the current Javadoc API. Code calling `manager.check(...)` from older blogs or docs may **fail to compile** on 7.x.

| Aspect | 6.5 | 7.x |
|---|---|---|
| Interface | `ReactiveAuthorizationManager<T>` | `ReactiveAuthorizationManager<T>` |
| Primary contract | `check` abstract/deprecated, `authorize` default | `authorize` abstract |
| Concrete class return | `Mono<AuthorizationDecision>` from `check` | `Mono<AuthorizationResult>` from `authorize` |
| `hasRole/hasAuthority` static factories | Present | Present |
| `verify(...)` | Present | Present |

**Do not confuse reactive with non-reactive:** Servlet `AuthorizationManager<T>` takes `Supplier<Authentication>`, whereas reactive takes `Mono<Authentication>`. Never copy classes or method signatures between the two worlds.

Version references:
- [AuthorityReactiveAuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html).
- [ReactiveAuthorizationManager 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html).
- [AuthorityReactiveAuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html).
- [ReactiveAuthorizationManager 7.x](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html).

**Upgrade rule:** check the actual Spring Security dependency version running—do not infer it from Java 17 or an unverified Spring Boot version; compile and test custom managers and `.check/.authorize` calls against the exact target version.

## 7. `Mono<AuthorizationResult>` and DENY/empty semantics

A reactive authorization publisher has distinct outcomes:

~~~text
Mono.just(AuthorizationResult granted)  -> ALLOW
Mono.just(AuthorizationResult denied)   -> DENY
Mono.empty()                            -> no decision / abstain
Mono.error(...)                         -> evaluation error
~~~

In Spring Security 6.5, the older signature still uses `AuthorizationDecision`, which exposes its result via `isGranted()`. Spring Security 7.x uses `AuthorizationResult` for the primary method, with `isGranted()`.

**An empty `Mono` does not automatically mean ALLOW.** The Javadoc states it indicates no decision was made. For mandatory policies, design composition/adapters so no-decision **never opens access**. Similarly, a timeout calling a remote policy backend is never a reason to allow.

The `verify(...)` method on `ReactiveAuthorizationManager` defines a contract where the publisher completes normally when granted and emits an error when denied. Even then, if a custom manager has abstain semantics, never write a PEP that defaults to `true` on an empty result.

A snippet using the 7.x API to evaluate explicitly (integration snippet):

~~~java
Mono<AuthorizationResult> result =
        AuthorityReactiveAuthorizationManager
            .<String>hasAuthority("documents:read")
            .authorize(authenticationMono, "document:42");
~~~

Here `"document:42"` is merely an illustrative generic secured object; the authority factory **does not read the document's owner from that string**. Real document authorization needs a custom policy beyond a plain authority check.

## 8. WebFlux `SecurityWebFilterChain`: standard route-based example

A Spring WebFlux configuration using HTTP Basic **solely to demonstrate granting roles/authorities**:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class WebFluxSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAnyAuthority("SCOPE_reports.read", "ROLE_AUDITOR")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .build();
    }
}
~~~

This is a **Spring configuration class**; running it requires Spring Boot WebFlux + Spring Security dependencies, an authentication user store/provider, controllers, and matching config. It is not a program runnable with `javac` alone.

Explanation:
1. `ServerHttpSecurity` configures WebFlux HTTP security.
2. `SecurityWebFilterChain` is the WebFlux filter chain, distinct from Servlet's `SecurityFilterChain`.
3. `authorizeExchange(...)` defines matchers in order.
4. Public routes are permitted before restricted rules.
5. GET reports requires **either** the READ scope or the AUDITOR role.
6. POST reports requires exact `SCOPE_reports.write`.
7. All admin paths require authority `ROLE_ADMIN` because `hasRole("ADMIN")` adds the prefix.
8. Remaining exchanges are denied via `denyAll`, curbing accidental exposure of new routes.
9. `httpBasic(withDefaults())` is a demo authentication mechanism; it does not automatically create users or JWTs.

**CSRF warning:** WebFlux Spring Security normally enables CSRF protection as appropriate. For POST requests using HTTP Basic/session/browsers, POST may fail with 403 due to a missing CSRF token **even with the right authority**. Do not disable CSRF indiscriminately just to make quick tests pass; if the app is a stateless bearer-token API, establish its threat model and configure CSRF to fit the architecture.

### Matchers decide first, authorities decide second

A rule applies only when a request matches its matcher. A `GET /api/reports/3` enters the GET reports rule; it does not continue trying the admin rule after being denied by the GET rule.

Order matters. Writing:
~~~java
.authorizeExchange(ex -> ex
    .anyExchange().authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
)
~~~

is a **misconfigured intent** because the broad fallback matcher appears first; depending on the DSL version, it may reject configuring matchers after `anyExchange`. Put specific rules before the fallback, choosing `denyAll` or an intentional `authenticated` fallback deliberately.

## 9. Path matchers, method matchers, and evaluation order

Suppose:

~~~text
GET    /api/reports/5         -> requires read scope or auditor
POST   /api/reports/5         -> requires write scope
DELETE /api/reports/5         -> denyAll if no rule matches
GET    /api/admin/status      -> requires ROLE_ADMIN
GET    /public/version        -> permitAll
~~~

This avoids a common bug: writing `.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")` for **all methods**, allowing POST/DELETE with only the READ scope.

In WebFlux, combine `pathMatchers(HttpMethod.GET,...)`, `pathMatchers(HttpMethod.POST,...)`, and additional matchers. Never assume the URL path alone describes the action when an API supports multiple HTTP methods.

**Resource boundary:** `hasAuthority("SCOPE_reports.read")` checks only functional authority; it **does not check which tenant report #5 belongs to**. Services and repositories must still apply ID + tenant + owner/ACL predicates in data access.

### Writing multiple `SecurityWebFilterChain`s

WebFlux can have multiple chains with `securityMatcher(...)` and priority ordering. Each request enters a matching chain, so not all rules have to live in one chain. Test thoroughly:
- Public and protected paths.
- Actuator and internal endpoints.
- Similar paths, trailing slashes, and encoded paths.
- Different authentication across routes when using multiple chains.
- Each chain's default rule.

Never accidentally add a chain with a broad matcher and `permitAll` ahead of a chain protecting sensitive APIs.

## 10. Creating `GrantedAuthority` from in-memory users in demos

For HTTP Basic demos, Spring Security can load authentication from `ReactiveUserDetailsService`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;

@Configuration
public class DemoUsersConfiguration {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo-password")
                .roles("ADMIN")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password("{noop}demo-password")
                .authorities("ROLE_AUDITOR", "SCOPE_reports.read")
                .build();

        UserDetails writer = User.withUsername("writer")
                .password("{noop}demo-password")
                .authorities("SCOPE_reports.write")
                .build();

        return new MapReactiveUserDetailsService(admin, auditor, writer);
    }
}
~~~

**Local/demo only:** `{noop}` is a non-hashing password encoder, **never for production**. Use a proper `PasswordEncoder`, store credentials/secrets securely, and never hardcode them.

Key details:
- `.roles("ADMIN")` generates an authority of the form `ROLE_ADMIN`.
- `.authorities("ROLE_AUDITOR", "SCOPE_reports.read")` sets the **exact strings declared**.
- `.authorities("SCOPE_reports.write")` does not create `ROLE_WRITER`.
- The `admin` user in the example **does not have** `SCOPE_reports.write` merely by being ADMIN.
- `hasAnyAuthority("SCOPE_reports.read","ROLE_AUDITOR")` grants access to `auditor`; `writer` needs another rule for GET if the business wants writers to read as well.

Do not think `hasRole("ADMIN")` reads a column named `role` from a user database. It inspects the `GrantedAuthority` list on the `Authentication` produced by the authentication provider.

## 11. Roles do not automatically imply other permissions

In the matrix above, `admin` has `ROLE_ADMIN` without automatically having `SCOPE_reports.read` or `SCOPE_reports.write`. Spring Security does not by default treat "ADMIN" as having every custom authority string you invent.

If policy requires admins to WRITE reports, declare it explicitly:

~~~java
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.write", "ROLE_ADMIN")
~~~

This is an **OR** between the write scope and the admin role. Yet you must ask:
- Which admin: system-wide or single-tenant only?
- Do roles from the JWT/user store carry the right scope?
- Does POST also need object-level permissions or business state checks?
- Are audit, MFA, or approval constraints required when an admin acts?

Never tack `ROLE_ADMIN` onto every rule just to make tests pass. That can grant cross-tenant power or create bypasses around business restrictions.

If READ+WRITE are required simultaneously, use an explicit AND policy. `hasAnyAuthority(a,b)` does **not** satisfy that requirement.

## 12. When AND or complex policies are needed

Basic authority managers excel at checking **one** or **one of many** authorities. For a rule like:

~~~text
ALLOW only if:
    has authority ROLE_APPROVER
    AND has authority SCOPE_invoices.approve
    AND tenant membership active
    AND invoice is not locked
~~~

multiple layers must collaborate.

One approach in reactive method security:

~~~java
@PreAuthorize(
    "hasAuthority('ROLE_APPROVER') and " +
    "hasAuthority('SCOPE_invoices.approve')"
)
public Mono<InvoiceView> approve(String tenantId, Long invoiceId) {
    return invoiceService.approveInScope(tenantId, invoiceId);
}
~~~

This is a **Spring Reactive Method Security integration snippet**; the method is intercepted by a Spring AOP proxy before the Publisher executes per method-security support. Even then, those two authorities still do **not** check the tenant or invoice. `approveInScope` must check tenant membership, object owner/ACL, status, and transactional consistency before mutating.

Another option is a custom `ReactiveAuthorizationManager<AuthorizationContext>` using the appropriate version's API and querying policy data from reactive services. When a policy bean returns `Mono<Boolean>`, never call `.block()` to force a result on the event loop.

### Conceptual example for a custom reactive manager on 7.x

~~~java
ReactiveAuthorizationManager<AuthorizationContext> manager =
    (authentication, context) ->
        authentication
            .map(auth -> auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> a.getAuthority().equals("ROLE_APPROVER"))
                    && auth.getAuthorities().stream()
                       .anyMatch(a -> a.getAuthority()
                           .equals("SCOPE_invoices.approve")))
            .map(granted -> (AuthorizationResult)
                    new AuthorizationDecision(granted));
~~~

This is a **7.x API snippet**, requiring imports for `ReactiveAuthorizationManager`, `AuthorizationContext`, `AuthorizationResult`, `AuthorizationDecision`, and `Authentication`, plus WebFlux dependencies. It expresses AND of two authorities without tenant/resource policies, and can emit `Mono.empty()` if no authentication is present. When used in request authorization, ensure anonymous/empty callers are blocked by global rules or `switchIfEmpty(Mono.just(new AuthorizationDecision(false)))` per the version contract, never treating empty as ALLOW.

**On 6.5**, custom interfaces still require the abstract/deprecated `check(...)` method, so do not copy a 7.x lambda signature expecting it to run on 6.5 without checking; isolate version-specific adapters or use built-in DSL rules when compatibility is needed.

## 13. JWT Resource Server: scopes usually become `SCOPE_`

For a WebFlux OAuth 2.0 Resource Server, a JWT might contain:

~~~json
{
  "iss": "https://identity.example/issuer",
  "sub": "user-72",
  "scope": "reports.read reports.write"
}
~~~

Once the resource server **verifies the JWT**, the default mapping from scopes to authorities is typically:

~~~text
SCOPE_reports.read
SCOPE_reports.write
~~~

Then:

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("SCOPE_reports.read")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("SCOPE_reports.write")
~~~

matches those two scopes. However, `hasRole("reports.read")` looks for `ROLE_reports.read`, **not** `SCOPE_reports.read`, and therefore usually DENIES.

Do not confuse:
- `scope`/`scp` in the token is the raw claim.
- `SCOPE_...` is the `GrantedAuthority` produced by the converter.
- `ROLE_...` is the role convention.
- `hasAuthority(...)` inspects the `GrantedAuthority` list **after conversion**, not raw claims directly.

WebFlux resource server config (integration snippet):

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

This snippet requires Spring Security OAuth2 Resource Server/Jose dependencies, issuer/JWK token config, and imports. Example Spring Boot config:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example/issuer
~~~

The URI is illustrative; replace it with a real issuer and verify `iss`, signature, `exp`, `nbf`, audience, token purpose, and product security requirements.

## 14. JWT roles do not automatically become `ROLE_`

A JWT might contain:

~~~json
{
  "sub": "user-72",
  "roles": ["ADMIN", "AUDITOR"]
}
~~~

Do not assume Spring reactive resource server automatically turns `roles` into `ROLE_ADMIN` and `ROLE_AUDITOR`. Standard default mapping focuses on `scope`/`scp`. If your authorization server emits roles in a custom claim, configure a trusted converter to map them into `Authentication.getAuthorities()`.

In Spring Security, components such as `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter`, and `ReactiveJwtAuthenticationConverterAdapter` wire conversion in a reactive resource server according to your version. When customizing, enforce these checks:
- Accept only verified issuers; never take roles from a JSON body or header.
- Ensure claim names/structures match the issuer and tenant.
- Never grant a global role if a token holds a role scoped to another tenant.
- When combining scopes and custom roles, avoid accidentally **dropping** scope authorities.
- Never trust unvalidated role strings not on an allowlist or normalized by policy.
- Check JWT expiration/revocation per SLA; stale roles can persist until token expiry.

**Critical debugging skill:** once the JWT is validated, inspect (in a controlled test environment) the exact authorities created by the converter. Never log raw tokens or full `Authentication` objects in production.

## 15. `ReactiveSecurityContextHolder` instead of assuming `ThreadLocal`

In Spring WebFlux, the security context of a reactive flow travels in the **Reactor Context**. When accessing authentication in a reactive component, one pattern is:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

This is an **integration snippet** without a wrapper class; inside a Spring/WebFlux component it must tie into the request lifecycle. It may return `Mono.empty()` when no security context is present; when business logic requires authentication, deny on missing identity rather than inventing a default user.

Never store authentication in a custom `ThreadLocal` assuming it propagates automatically across `publishOn`, async boundaries, or other threads. When calling blocking DBs/APIs in a reactive chain, design threading carefully without blocking the Netty event loop or leaking context across requests.

A custom reactive authorization check usually does not need to read `ReactiveSecurityContextHolder` itself; the framework passes `Mono<Authentication>` directly to the manager. Use that parameter instead of pulling identity from an unreliable thread-local.

## 16. HTTP checks differ from reactive method security

HTTP authorization via `authorizeExchange` intercepts by path/method before controllers or services run. Method authorization protects **use cases** and remains reusable whether the service is invoked from HTTP or another adapter.

Method security config:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
~~~

Some older docs/versions used `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` to opt into the newer infrastructure. Verify the right option for your project's Spring Security version.

Service:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<ReportView> readReport(String tenantId, Long reportId) {
        return findReportWithVerifiedScope(tenantId, reportId);
    }
}
~~~

This code is a **Spring integration snippet**, requiring implementations for `ReportView` and `findReportWithVerifiedScope`. The method is gated by the authority. Yet if `findReportWithVerifiedScope` runs an unscoped `repository.findById(reportId)`, an actor with the READ scope can still view someone else's report. Enforce tenant, owner/ACL, and status checks at the data-access boundary.

In reactive method security, return types should be `Publisher` (such as `Mono`/`Flux`) or a type supported by your version so it integrates with Reactor Context. Calls go through a Spring proxy in proxy mode; self-invocation `this.readReport(...)` can bypass the interceptor.

## 17. Role hierarchy: do not infer ADMIN automatically has every permission

A policy might intend:
~~~text
ADMIN > EDITOR > VIEWER
~~~

Yet an authentication holding only `ROLE_ADMIN` **does not automatically contain** `ROLE_EDITOR`, `ROLE_VIEWER`, or `SCOPE_reports.read`. Spring Security offers role hierarchy features in specific contexts and versions; never assume static `hasAuthority("SCOPE_reports.read")` automatically infers an arbitrary hierarchy.

Options:
1. Grant all required authorities when building `Authentication` from a trusted data source.
2. Use a supported role hierarchy mechanism explicitly configured for your Spring Security version and authorization path.
3. Build a policy service encoding hierarchy and domain action mappings, backed by integration tests.

**Never test only `hasRole("ADMIN")` and conclude that admin also passes every `hasAuthority` route.**

Role hierarchies can be helpful, yet if misconfigured, an ADMIN role from one tenant could apply in another tenant. Roles must have verified scope, not merely exist as strings.

## 18. Tenant, owner, ACL: limits of `AuthorityReactiveAuthorizationManager`

Consider user An:
~~~text
tenant north: ROLE_EDITOR
tenant south: ROLE_VIEWER
document 42: tenant south, owner Binh, share READ
~~~

If `Authentication` merges all of An's roles into a global `ROLE_EDITOR` and a WebFlux route uses:
~~~java
.pathMatchers("/tenants/**/documents/**").hasRole("EDITOR")
~~~

then `ROLE_EDITOR` from north can unlock requests to south. That is an **authority modeling flaw**, not a bug in `AuthorityReactiveAuthorizationManager`: the class faithfully checked the authority the app granted, because the authority lacked tenant scoping.

A sound decision requires:
~~~text
authenticated(actor)
AND verifiedMembership(actor, requestedTenant)
AND roleAllows(actor, requestedTenant, action)
AND resource.tenant == requestedTenant
AND (owner OR validGrant OR verifiedProjectScope)
AND resourceStateAllows(action)
~~~

A typical clean design:
- HTTP WebFlux gate checks coarse scope/action with `hasAuthority`.
- Service resolver loads verified actor and tenant membership.
- Repository queries `id AND tenant AND (owner OR ACL...)`.
- Writes use guarded transactions, expected version, and revocation checks.

Never let users submit `tenantId` or `isAdmin` as proof. A READ grant on a document does not imply DELETE. If a policy requires cross-tenant support, design a dedicated audited capability instead of dropping tenant filters.

## 19. Using `hasAnyRole` for multiple allowed groups

Example:
~~~java
.pathMatchers("/api/operations/**")
    .hasAnyRole("OPERATOR", "SUPPORT")
~~~

This condition is:
~~~text
hasAuthority("ROLE_OPERATOR")
OR hasAuthority("ROLE_SUPPORT")
~~~

It does not require both. A user with `ROLE_SUPPORT` and without `ROLE_OPERATOR` is still allowed.

Another example:
~~~java
.pathMatchers("/api/invoices/**")
    .hasAnyAuthority("SCOPE_invoices.read", "ROLE_AUDITOR")
~~~

Allows an actor holding at least one of those two authorities. If business rules require auditor **and** scope, never use `hasAnyAuthority`. In particular, if a DELETE endpoint mistakenly uses `hasAnyRole("VIEWER","ADMIN")`, viewers can DELETE—a severe **least privilege** violation.

## 20. Deny-by-default and unauthenticated access

A safe design:
~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

This is an illustrative configuration. Consider `authenticated()` as an API fallback carefully: it allows any authenticated user onto newly added API routes, so if you want to block every undeclared route, use `denyAll()`.

Again, rule order matters: `/api/admin/**` must precede `/api/**` when the latter is broader. GET/POST/DELETE routes on the same path should be guarded by action.

Distinctions:
- `permitAll()`: requires no authorization for this matcher; other filters/protections may still run per config.
- `authenticated()`: requires valid authentication.
- `hasAuthority(...)`: requires a specific authority in `Authentication`.
- `hasRole(...)`: requires authority `ROLE_<role>`.
- `denyAll()`: always denies for the matching rule.

Never use `permitAll()` to work around an authority mapping bug; fix authentication conversion and route configuration instead.

## 21. 401, 403, and their different causes

When a request is blocked:
- **401 / challenge**: no valid authentication in an API using HTTP Basic/Bearer, or an invalid token. Form login may redirect instead of returning 401 directly.
- **403**: authenticated, yet lacking the required authority/role or denied by policy.
- **403 due to CSRF**: POST/DELETE using cookies or HTTP Basic with CSRF enabled and a missing CSRF token; not always `hasAuthority`.
- **404**: resource does not exist within the viewable set (when services apply scoped queries and policies choose 404 to prevent enumeration).
- **5xx**: authz backend/DB unavailable or misconfigured; must never fail open.

Never return the full list of authorities or token claims to clients to "explain missing roles." Never treat an authentication failure as proof a user lacks object permissions. In audit logs, record appropriate reason codes without logging raw tokens or owners/ACLs of unauthorized resources.

## 22. Why avoid `block()` during WebFlux authorization?

A custom policy may need a reactive repository or remote PDP:

~~~text
Mono<Authentication>
      |
      v
fetch verified membership (reactive DB)
      |
      v
fetch resource metadata/ACL
      |
      v
Mono<AuthorizationResult>
~~~

Calling `.block()` on a reactive request thread can stall the Netty event loop, inflating latency and causing timeouts under load.

Best practices:
- Compose using `flatMap`/`map` and proper publisher return types.
- Never return `Mono.just(true)` when a remote policy times out.
- Use timeouts and circuit breakers distinguishing DENY from ERROR; neither grants access.
- Never construct a side-effecting publisher and subscribe manually inside the authorization function; the framework is the subscriber.
- Ensure the authentication's Reactor Context is not lost across custom async/task boundaries.
- Test errors and cancellations, not just happy paths.

Example snippet:
~~~java
return membershipService.hasRole(actor, tenant, "EDITOR")
    .flatMap(roleOk -> roleOk
        ? resourcePolicy.canWrite(actor, tenant, documentId)
        : Mono.just(false))
    .map(granted -> (AuthorizationResult)
        new AuthorizationDecision(granted));
~~~

This code is **only an integration pipeline snippet**; `actor` must come from verified authentication, services must return `Mono<Boolean>`, and full code must match your Spring version. Functional authority checks still do not replace current resource state; writes need transactions/guards against TOCTOU.

## 23. Notes on writing custom managers and upgrading Spring Security

When you only need role/authority checks, built-in factories are simpler and less error-prone than a custom manager. Write a custom manager when:
- Policy requires owner/tenant/ACL/object state.
- Complex business AND/OR conditions are needed.
- You integrate a remote PDP or relationship authorization.
- Decisions depend on request method, verified headers, and domain context.
- You need PEP/PDP separation and reason codes.

If writing one:
1. Check your Spring Security version **before** choosing `check` or `authorize`.
2. Verify generic `T`: `AuthorizationContext` for WebFlux HTTP, or another secured object type.
3. Return a lazy publisher; never force `block()`.
4. On missing auth/input, choose explicit DENY/ERROR rather than accidental abstain.
5. Handle timeouts, cancellations, and exceptions so they never become ALLOW.
6. Never call `getAuthorities()` on a null authentication.
7. Bind decisions to verified actions, resources, and tenants.
8. Never log raw `Authentication`, JWTs, or resource payloads.
9. Separate technical errors from business DENYs in observability.
10. Test routes, method security, policy reloads, and concurrency when permissions change.

**On the `ROLE_` convention:** this class's static `hasRole` factory is documented to prepend `ROLE_`. When a system uses different role naming or method security uses a custom prefix, use the exact mapped authority and integration tests rather than assuming every layer reads the same prefix config.

## 24. Standalone Java 17: demonstrating exact role and authority matching

This example is **pure Java 17, without Spring**. It models the string-matching logic of the factories, illustrating the difference between `hasRole`, `hasAuthority`, `hasAnyRole`, and `hasAnyAuthority` before wiring WebFlux.

Create `AuthorityMatchDemo.java`:

~~~java
import java.util.Set;

public class AuthorityMatchDemo {
    static boolean hasAuthority(Set<String> granted, String required) {
        return granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String role) {
        return granted.contains("ROLE_" + role);
    }

    static boolean hasAnyAuthority(
            Set<String> granted, String... options) {
        for (String authority : options) {
            if (granted.contains(authority)) {
                return true;
            }
        }
        return false;
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        for (String role : roles) {
            if (granted.contains("ROLE_" + role)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        Set<String> an = Set.of(
                "ROLE_ADMIN", "SCOPE_reports.read");
        Set<String> binh = Set.of(
                "ROLE_EDITOR", "SCOPE_reports.write");
        Set<String> chi = Set.of("ADMIN");

        System.out.println("an-role-admin="
                + hasRole(an, "ADMIN"));
        System.out.println("an-authority-admin="
                + hasAuthority(an, "ADMIN"));
        System.out.println("an-exact-role-authority="
                + hasAuthority(an, "ROLE_ADMIN"));
        System.out.println("an-report-read="
                + hasAuthority(an, "SCOPE_reports.read"));
        System.out.println("binh-any-role="
                + hasAnyRole(binh, "ADMIN", "EDITOR"));
        System.out.println("binh-any-authority="
                + hasAnyAuthority(
                    binh, "SCOPE_reports.read", "SCOPE_reports.write"));
        System.out.println("binh-read-only="
                + hasAuthority(binh, "SCOPE_reports.read"));
        System.out.println("chi-has-role-admin="
                + hasRole(chi, "ADMIN"));
        System.out.println("chi-has-authority-admin="
                + hasAuthority(chi, "ADMIN"));
        System.out.println("empty-no-role="
                + hasAnyRole(Set.of(), "ADMIN", "EDITOR"));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac AuthorityMatchDemo.java
java AuthorityMatchDemo
~~~

Exact stdout:

~~~text
an-role-admin=true
an-authority-admin=false
an-exact-role-authority=true
an-report-read=true
binh-any-role=true
binh-any-authority=true
binh-read-only=false
chi-has-role-admin=false
chi-has-authority-admin=true
empty-no-role=false
~~~

Explanation:
- `ROLE_ADMIN` satisfies `hasRole("ADMIN")`, yet does **not** satisfy `hasAuthority("ADMIN")`.
- `hasAuthority("ROLE_ADMIN")` requires the exact string, so An succeeds.
- Binh passes one-of-two roles and one-of-two scopes, despite lacking the READ scope.
- Chi has raw `ADMIN` without `ROLE_ADMIN`.
- An empty authority set cannot satisfy any role in this model.

**Scope limit:** this program has no `Mono`, authentication providers, bearer tokens, filter chains, or object-level permissions. It models **factory string matching**, not every runtime/anonymous detail of Spring Security. The integration test section below proves matchers and authentication work in real WebFlux.

## 25. Integration testing with `WebTestClient`

Spring Security Test supports `WebTestClient` in the reactive stack. Example testing an admin GET:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxAuthorizationTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void adminRoleCanAccessAdminPath() {
        webTestClient
            .mutateWith(mockUser().roles("ADMIN"))
            .get().uri("/api/admin/status")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rawAdminAuthorityDoesNotSatisfyHasRole() {
        webTestClient
            .mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("ADMIN")))
            .get().uri("/api/admin/status")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Test integration snippet**: requires Spring Boot WebFlux Test/Spring Security Test/JUnit, a real `GET /api/admin/status` endpoint returning 200 when permitted, a chain configured with `hasRole("ADMIN")`, and `WebTestClient` wired with security test support. Without those conditions configured in the test app, the snippet is not a standalone runnable test file.

Different Boot/Security versions may require binding `WebTestClient` with `springSecurity()` in standalone tests; check the matching WebFlux test docs. With real HTTP Basic requests, testing CSRF/401/403 differs from a mock-user security context.

### Matrix to verify in integration tests

| Request | GrantedAuthority | Expected from illustrative rules |
|---|---|---|
| GET `/api/admin/status` | `ROLE_ADMIN` | Allowed |
| GET `/api/admin/status` | `ADMIN` | 403 when authenticated |
| GET `/api/admin/status` | `ROLE_EDITOR` | 403 |
| GET `/api/reports/7` | `SCOPE_reports.read` | Allowed |
| GET `/api/reports/7` | `ROLE_AUDITOR` | Allowed |
| GET `/api/reports/7` | `SCOPE_reports.write` | 403 per illustrative GET rule |
| POST `/api/reports/7` | `SCOPE_reports.write` + valid CSRF | Reaches handler; HTTP result per handler |
| POST `/api/reports/7` | `SCOPE_reports.read` | 403 |
| DELETE `/api/reports/7` | Any | `denyAll` if no DELETE rule exists |
| GET `/public/version` | Unauthenticated | Allowed via `permitAll` |
| GET `/api/admin/status` | Unauthenticated | Challenge/401 or redirect per authentication config |

Do not check only status codes: ensure denied requests **never invoke data-mutating services**, and handlers return proper statuses without leaking unauthorized resources or owners.

## 26. Mocking user roles vs mocking user authorities

In tests:
~~~java
mockUser().roles("ADMIN")
~~~

normally creates authority `ROLE_ADMIN`, just like user builder `.roles("ADMIN")`.

Meanwhile:
~~~java
mockUser().authorities(
    new SimpleGrantedAuthority("ADMIN"))
~~~

creates the literal authority `ADMIN`. If your tests use `roles` while your production JWT converter emits raw `ADMIN`, tests can PASS while production fails with 403.

Conversely, test fixtures granting overly broad authorities like `ROLE_ADMIN` + `SCOPE_reports.write` can mask missing mappings in the real provider. Test at least one path through the real authentication provider or a validated JWT test fixture matching your real claims and converter.

Never construct role/scope fixtures from client-supplied JSON and treat that as an authentication security integration test.

## 27. Unit testing the manager directly for the target version

To test the manager itself rather than HTTP routes, using a test-constructed authentication:
~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "an", "unused",
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

In Spring Security **6.5**, you can call (in a library-integrated test):

~~~java
Mono<AuthorizationDecision> decision =
    AuthorityReactiveAuthorizationManager
        .<String>hasRole("ADMIN")
        .check(Mono.just(authentication), "securedObject");
~~~

In Spring Security **7.x**:

~~~java
Mono<AuthorizationResult> decision =
    AuthorityReactiveAuthorizationManager
        .<String>hasRole("ADMIN")
        .authorize(Mono.just(authentication), "securedObject");
~~~

These are version-specific snippets requiring imports and dependencies. Use `StepVerifier` or a Reactor test subscriber to assert `decision.isGranted()`. **Never call `.block()` in WebFlux runtime code**; standalone tests may use test utilities as appropriate.

In particular, assert:
- Exact `GrantedAuthority` yields ALLOW.
- Missing authority yields DENY.
- Wrong role prefix yields DENY.
- `Any` factories apply OR, not AND.
- An authentication publisher with no principal or with an error never turns into "default allow."
- Custom manager errors/abstains are never converted to ALLOW by your adapter.

## 28. Common mistakes and fixes

**1. Using `hasRole("ROLE_ADMIN")`.** The factory already prepends `ROLE_`; do not pass an already-prefixed name thinking it is "safer." Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`.

**2. Using `hasAuthority("ADMIN")` when the user builder sets `.roles("ADMIN")`.** The user holds `ROLE_ADMIN`, not raw `ADMIN`. Align the exact strings.

**3. Using `hasRole("reports.read")` for a JWT scope.** JWT scopes typically map to `SCOPE_reports.read`. Use `hasAuthority("SCOPE_reports.read")` or a dedicated scope manager if appropriate.

**4. Assuming `hasAnyAuthority(a,b)` requires both a and b.** It requires only one. For AND, use a tested composite policy.

**5. Assuming `ADMIN` automatically holds every authority.** No such inference exists unless configured. Grant explicit authorities or a proper role hierarchy policy.

**6. Putting a broad matcher before a narrow matcher.** Admin routes can fall into `authenticated()` or the wrong rule. Place specific rules before the fallback.

**7. Forgetting the HTTP method.** A READ rule covering all verbs can accidentally guard DELETE with read permission. Separate method-level actions.

**8. Using `HttpSecurity` in a WebFlux project.** Wrong stack. For WebFlux use `ServerHttpSecurity` and `SecurityWebFilterChain`.

**9. Calling `check(...)` in a Spring Security 7.x codebase.** Current API uses `authorize(...)`. Verify Javadoc for your exact version.

**10. Assuming a JWT `roles` claim means `ROLE_ADMIN` exists.** A converter is needed to produce actual `GrantedAuthority` instances.

**11. Testing with mock roles while the production converter emits different authorities.** Test the claim/provider mapping path as well as routes, not just `@WithMockUser`.

**12. Using global roles on multi-tenant URLs.** A north role can open south resources. Add membership and resource tenant guards.

**13. Treating an authority as proof of owner/ACL.** `SCOPE_documents.read` does not verify rights on document #42; enforce object-level checks.

**14. Calling `block()` when policy requires I/O.** Can stall the event loop. Compose non-blocking publishers.

**15. Treating `Mono.empty()` as ALLOW.** Empty means no decision per contract, not granted.

**16. Disabling CSRF to fix every 403.** Can strip an essential defense. Identify the root cause and evaluate against the session/cookie/bearer threat model.

**17. Protecting only HTTP and forgetting methods/workers.** Sensitive services can be invoked via messages or schedulers. Place policies at shared boundaries.

**18. Catching a PDP exception and returning `true`.** Fail-open. On backend failure, deny the action and emit observability signals.

## 29. Pre-merge checklist for WebFlux authorization code

- [ ] Confirm the project uses WebFlux (not the Servlet stack).
- [ ] Use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `authorizeExchange` properly.
- [ ] Order matchers from narrow to broad, with an appropriate deny fallback.
- [ ] Verify GET/POST/PUT/PATCH/DELETE per the required action.
- [ ] Understand `hasRole("R")` matches `ROLE_R`; `hasAuthority("X")` matches exact `X`.
- [ ] Never use `hasAnyRole`/`hasAnyAuthority` to express AND.
- [ ] Keep role/authority naming conventions and letter casing consistent.
- [ ] Explicitly map JWT scopes and custom roles to `GrantedAuthority`.
- [ ] Validate JWTs before trusting claims; check issuer/audience/expiry and tenant scope.
- [ ] Never merge a subject's roles across multiple tenants into unintended global permissions.
- [ ] Verify object/resource tenant, owner, and ACL separately from functional roles.
- [ ] Enable reactive method security where needed and ensure it executes through proxies.
- [ ] Never block the event loop or manually subscribe inside authorization rules.
- [ ] Ensure no-decision, error, and timeout states never become ALLOW.
- [ ] Test valid/invalid role prefixes, missing authorities, JWT scopes, matcher ordering, and HTTP verbs.
- [ ] Test 401/403/CSRF and confirm mutations do not execute when denied.
- [ ] Verify custom managers and `check`/`authorize` match your **Spring Security version**.
- [ ] Ensure multiple `SecurityWebFilterChain`s do not route protected endpoints into a permissive chain.
- [ ] When upgrading versions, review Javadoc and run security integration tests before release.

**Conclusion:** `AuthorityReactiveAuthorizationManager` is the **GrantedAuthority** checking tool in WebFlux: `hasAuthority` matches exact strings, `hasRole` uses the `ROLE_` prefix, and `hasAny...` factories use OR logic. Place them properly inside `authorizeExchange`, standardize how credentials/JWTs produce authorities, and always guard data in services/repositories when permissions depend on tenants or objects. For custom reactive authorization, follow your exact API version and maintain fail-closed behavior.

## Official references

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain`, `ServerHttpSecurity.authorizeExchange`, matcher ordering.
- [Spring Security 6.5 — AuthorityReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html): factories and `check(...)` in 6.5.
- [Spring Security 6.5 — ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): default `authorize` since 6.4, `check` deprecated.
- [Spring Security 7.x — AuthorityReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html): factories and `authorize(...)`.
- [Spring Security 7.x — ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): reactive contract and `verify`.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, Reactor Context.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT verification, mapping scopes to `SCOPE_`, and WebFlux setup.
- [Spring Security — WebFlux Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient`, authentication mocks, and security testing.
