# JEE Pre-authentication and Identities Provided by the Servlet Container

> **Scope:** Spring Security **Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+, Jakarta Servlet API). This lesson focuses on Java EE/Jakarta EE **container-managed authentication** used by Spring Security as **pre-authentication**. The key concept is that the **Servlet Container authenticates the user first**, while Spring Security consumes the container-established identity and roles to construct `Authentication`, enforce authorization, and integrate with the application. This lesson does not use WebFlux and does not treat client-sent HTTP headers as trusted identities.

## 1. What Does Pre-authentication Mean?

Normally in Spring Security, the application verifies passwords, Bearer tokens, or another authentication method itself through filters/providers. With **pre-authentication**, another system has **already authenticated** the HTTP request before Spring Security processes it. Spring Security does not re-collect passwords to check; instead, it reads the **principal** and (if available) **roles/authorities** from a trusted source.

In the JEE case, the trusted source is the **Servlet Container / application server** (such as a container configured with a realm, login mechanism, and security constraints), accessed via standard `HttpServletRequest` APIs. Spring Security uses pre-authentication classes to place this information into `SecurityContext`.

A sound example scenario:

1. A user accesses a WAR application deployed to an application server configured with realm/SSO authentication.
2. The container forces the user to authenticate via an administrator-configured mechanism (BASIC, FORM, client certificate, or container-integrated mechanism, depending on the environment).
3. Upon success, the container exposes the principal and roles through `HttpServletRequest`.
4. Spring Security receives the verified identity, maps roles, and checks `hasRole` / `hasAuthority` rules before allowing controller invocation.

**Pre-authenticated does not mean "every request is trustworthy."** If the container did not actually authenticate the request or the application has an access path bypassing the authentication layer, identity data is untrustworthy. Controlling the trust boundary is a prerequisite before using it.

### Which Components Are Responsible?

| Component | Responsibility |
| --- | --- |
| **Servlet Container** | Executes the login mechanism/realm, identifies the user and roles per container configuration. |
| `HttpServletRequest.getUserPrincipal()` | API returning the principal associated with the request from the container; may return `null` if unauthenticated. |
| `HttpServletRequest.getRemoteUser()` | Username authenticated by the container, or `null` if absent. |
| `HttpServletRequest.getAuthType()` | Authentication type established by the container, e.g., `BASIC_AUTH` or `FORM_AUTH`; may be `null`. |
| `HttpServletRequest.isUserInRole(role)` | Checks whether the user holds a role under container configuration. |
| `J2eePreAuthenticatedProcessingFilter` | Spring Security filter reading the container-authenticated principal from the Servlet request and creating a pre-authentication token. |
| `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` | Converts role information from `isUserInRole` into authorities per the configured list of roles. |
| `PreAuthenticatedAuthenticationProvider` | Processes the pre-authentication token inside `AuthenticationManager`, coordinating with the corresponding user-details service. |
| `SecurityContext` / `Authentication` | Represents the principal and granted authorities used by Spring Security components after authentication. |

## 2. Distinguishing Container Authentication from Spring Security Authentication

**Container authentication** answers: *Who did the container authenticate, and which roles does the container say the user belongs to?*

**Spring Security** uses that data to answer: *Which principal owns the current request, which `GrantedAuthority` values do they hold, and are they permitted to access this URL/method?*

~~~text
Browser
  |
  v
Servlet Container (Realm + auth mechanism + security constraints)
  |  success: request has Principal, roles
  v
Servlet Filter Chain
  |
  +-- Spring Security / FilterChainProxy
        |
        +-- J2eePreAuthenticatedProcessingFilter
        |      reads request.getUserPrincipal()
        |      reads role mapping from request.isUserInRole(...)
        |      creates PreAuthenticatedAuthenticationToken
        |
        +-- AuthenticationManager
        |      PreAuthenticatedAuthenticationProvider
        |      UserDetails/GrantedAuthority from trusted details
        |
        +-- SecurityContext holds Authentication
        +-- AuthorizationFilter enforces permissions
        |
        v
      Controller / Service
~~~

Exact filter ordering depends on version and configuration; this is the conceptual flow. Class names still carry the **J2ee** prefix for API history, even though Spring Boot 3.x uses the **`jakarta.servlet.*`** namespace instead of `javax.servlet.*`.

### Why Not Check Passwords in Two Places Simultaneously?

If the container is already responsible for authenticating requests via realm/SSO, additionally configuring Spring form login as a separate authentication source for the **same protected path** can produce two login flows, conflicting redirects, or inconsistent principal/role mappings. Designate clearly which side is the **primary authentication source** and which only enforces authorization. Different regions may have separate security filter chains, provided scopes and trust boundaries are defined explicitly.

## 3. Servlet APIs That Provide Identity

In code running **before Spring Security wraps the request**, container APIs are typically used like this:

~~~java
Principal principal = request.getUserPrincipal();
String username = request.getRemoteUser();
String authType = request.getAuthType();
boolean isUser = request.isUserInRole("USER");
boolean isAdmin = request.isUserInRole("ADMIN");
~~~

Requires importing `java.security.Principal` and `jakarta.servlet.http.HttpServletRequest`; this is an **illustrative snippet inside a filter/controller with a request variable**, not a standalone Java program.

Explanation:

- `getUserPrincipal()` returns a `Principal` or `null`. Do not assume the principal is necessarily a plain string, email, or object from a specific SSO provider.
- `getRemoteUser()` typically gives the container-authenticated username; name formatting depends on the realm.
- `getAuthType()` lets you observe the mechanism reported by the container; it **does not prove** the request is secure if the container or network path is misconfigured.
- `isUserInRole("ADMIN")` asks the container whether the user has role `ADMIN`. These roles must be declared/mapped in the deployment environment; they do not appear automatically from arbitrary LDAP/IdP group names.

**Crucial debugging note:** after passing through Spring Security, `HttpServletRequest` may be wrapped by `SecurityContextHolderAwareRequestWrapper`, causing security methods on the request to reflect **Spring Security's Authentication** rather than the raw container object. Therefore, to verify whether the container actually supplied a principal/role, inspect at the container or in a filter running **before Spring Security**; do not merely call `request.getUserPrincipal()` inside a controller and assume it is the original container object.

In Spring application code, the source for inspecting identity after pre-auth processing is:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String name = authentication.getName();
    boolean admin = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"));
}
~~~

This snippet requires importing `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. It only reads the security context; `isAuthenticated()` must be paired with a policy that does not treat anonymous users as valid users. Inside a controller protected by `.authenticated()`, `Authentication` is handled by Spring Security per the corresponding rule.

## 4. Role of J2eePreAuthenticatedProcessingFilter

`org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter` builds on `AbstractPreAuthenticatedProcessingFilter`. It neither renders a login form, redirects users to an Identity Provider, nor verifies passwords on the container's behalf. It **extracts the principal** supplied by the container, constructs a `PreAuthenticatedAuthenticationToken`, and forwards it into Spring's authentication mechanism.

The pre-authentication mechanism performs two distinct tasks:

1. **Identify principal:** read from `HttpServletRequest.getUserPrincipal()`.
2. **Assign authorities:** read from container role data via the details source or via a trusted `UserDetailsService`, depending on configuration.

`J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` calls `request.isUserInRole(roleName)` for each role in the **mappable roles** list. Matching roles are converted into `GrantedAuthority`; the default mapper typically prefixes `ROLE_` to the role name to match Spring Security's `hasRole("USER")`.

Example:

~~~text
Container authenticated user = alice
isUserInRole("USER")  = true
isUserInRole("ADMIN") = false

Spring Security Authentication:
  principal = alice
  authorities = [ROLE_USER]

Rule hasRole("USER")  -> allowed
Rule hasRole("ADMIN") -> denied
~~~

This is a **hypothetical scenario**, not default stdout or framework log output. Role mapping conditions must match the actual configuration of both container and application.

### Related Classes

`PreAuthenticatedAuthenticationProvider` can use `PreAuthenticatedGrantedAuthoritiesUserDetailsService` to adopt authorities packaged inside authentication details. In custom setups, `UserDetailsByNameServiceWrapper` can fetch extra user information by username. This is **how authorities/user details are enriched in Spring**, not re-verifying a default password.

If a user is disabled in the business system while the container still allows login, the application must explicitly decide how to check business account status before permitting operations; never confuse "container authentication succeeded" with "all business permissions are valid."

## 5. Configuring Spring Security 6 with HttpSecurity.jee

This is a **complete Java configuration** example in a Spring Boot 3.x application with `spring-boot-starter-web` and `spring-boot-starter-security`. It assumes the application is deployed to a **Servlet Container configured with JEE authentication** and roles `USER` and `ADMIN`.

File `JeeSecurityConfig.java` inside a package scanned by Spring Boot:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JeeSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/app/admin/**").hasRole("ADMIN")
                .requestMatchers("/app/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().denyAll()
            )
            .jee(jee -> jee
                .mappableRoles("USER", "ADMIN")
            );

        return http.build();
    }
}
~~~

**Meaning of each part:**

- `.jee(...)` enables **JEE container pre-authentication** integration, adding `J2eePreAuthenticatedProcessingFilter` and its associated provider per Spring Security.
- `mappableRoles("USER", "ADMIN")` declares **which roles to query from the container** and convert into granted authorities. With standard role mapping, the resulting authorities are `ROLE_USER` and `ROLE_ADMIN`.
- `hasRole("ADMIN")` checks authority `ROLE_ADMIN` (by default convention). Do not write `hasRole("ROLE_ADMIN")` when using the default prefixing configuration.
- `requestMatchers("/app/admin/**")` is evaluated before `/app/**` so the broader matcher does not shadow the admin rule; `anyRequest().denyAll()` denies paths outside the specified scope. `/health` is an example health-check endpoint opened at the **Spring layer**, though container constraints can still block it if the container protects the entire app.
- **Do not** call `formLogin()` or `httpBasic()` in this example. Any BASIC/FORM login mechanism is configured by the **Container** in this scenario.
- Never disable CSRF merely because JEE is used. If the web app relies on automatically sent sessions/cookies, analyze CSRF for state-changing HTTP methods; Spring Security enables CSRF protection by default unless disabled.

### What Must Be Configured on the Servlet Container?

Simply adding `.jee(...)` **does not turn** a default embedded Tomcat into a container with a full realm, login mechanism, and security constraints. If `getUserPrincipal()` is `null`, the filter cannot conjure a real identity out of thin air.

For a **WAR deployed to an app server**, security constraints and role names can be declared in `web.xml`, while administrators configure the realm/user store/SSO on the server. That part is the **container's contract**, not configuration generated automatically by Spring Security.

## 6. Example web.xml for Container-Managed Authentication

This is an example **Jakarta Servlet 6.0** descriptor (suited for Jakarta EE 10 when supported by the container). Place it at `src/main/webapp/WEB-INF/web.xml` in a WAR application. The container must have a real configured realm, users, and role mappings; the descriptor does not create accounts itself.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <security-constraint>
        <web-resource-collection>
            <web-resource-name>Protected Application</web-resource-name>
            <url-pattern>/app/*</url-pattern>
        </web-resource-collection>
        <auth-constraint>
            <role-name>USER</role-name>
            <role-name>ADMIN</role-name>
        </auth-constraint>
    </security-constraint>

    <login-config>
        <auth-method>BASIC</auth-method>
        <realm-name>CompanyRealm</realm-name>
    </login-config>

    <security-role>
        <role-name>USER</role-name>
    </security-role>
    <security-role>
        <role-name>ADMIN</role-name>
    </security-role>
</web-app>
~~~

This is a **configuration example**, not a standalone runnable app. Explanation:

1. The container protects URLs under `/app/*` and requires a valid user belonging to either `USER` or `ADMIN`. If a user fails the container constraint, the container can reject the request **before Spring Security**.
2. `<auth-method>BASIC</auth-method>` selects **container-implemented** HTTP Basic. This is not Spring Security's `http.httpBasic()`. Production environments must use HTTPS to avoid exposing credentials and enforce suitable login policies.
3. `CompanyRealm` is an illustrative realm name; the container must be configured with a real realm mapping groups/users to the matching JEE roles. The XML file contains no passwords or default users.
4. Container role `ADMIN` may pass the constraint, while Spring still applies a separate rule: `/app/admin/**` requires `ROLE_ADMIN`.
5. The descriptor's `/app/*` matcher and Spring Security's `/app/**` use **two different pattern systems**; test real URLs, especially servlet mappings, context paths, and nested routes.
6. Descriptor placement/effectiveness can vary by container/deployment. For Boot executable JARs using an embedded server, copying this file alone does not enable container auth; an actual embedded container, realm, and servlet security integration must be configured.

**Key distinction:** the container decides who enters the outer protection layer first, and Spring Security can **tighten rules further** by URL/method roles, yet Spring cannot rescue an application if the container leaves a sensitive path bypassing authentication under a broken application trust model.

## 7. Inspecting Identity in a Spring MVC Controller

In a controller **after Spring Security**, read `Authentication` or `@AuthenticationPrincipal` to obtain the identity Spring actually uses for authorization. Example `IdentityController.java`:

~~~java
package com.example.web;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/app/identity")
    public Map<String, Object> identity(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Map.of(
                "username", authentication.getName(),
                "authorities", authorities
        );
    }
}
~~~

This code requires Spring MVC/Security dependencies to be configured and assumes `/app/identity` passed pre-auth and `hasAnyRole("USER", "ADMIN")`. For a user **alice** with role USER supplied by the container and properly mapped, an example response **could** be:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER"]
}
~~~

The response above is an **illustrative scenario**, not a fixed result across every container: principal names and role lists depend on the realm/provider and custom mapping.

**Security:** this endpoint is only for understanding and testing integration. In production, avoid exposing authorities and unnecessary identity details to clients; if returning details, enforce access control. Never rely on a client-sent field (query param, `X-User` header, JSON body) to build `Authentication`.

### Can Spring Method Security Be Used?

Yes. If the project enables method security and already receives authorities from JEE mapping, annotations like `@PreAuthorize("hasRole('ADMIN')")` can apply alongside URL authorization. `@EnableMethodSecurity` must be present on the relevant config and the method must genuinely be invoked through a Spring proxy; method security does not replace container authentication.

## 8. Role Mapping: Common Cause of 403 Errors

Container roles and Spring Security authorities are not automatically identical strings.

Suppose the container provides:

~~~text
getUserPrincipal().getName() = alice
request.isUserInRole("USER")  = true
request.isUserInRole("ADMIN") = false
~~~

When `jee.mappableRoles("USER", "ADMIN")` aligns, Spring creates `GrantedAuthority("ROLE_USER")` and `hasRole("USER")` succeeds. If the container returns a differently named role, such as `TEAM_MEMBER` instead of `USER`, then `isUserInRole("USER")` evaluates false, Spring lacks `ROLE_USER`, and it returns 403 when accessing a URL requiring USER.

### How to Handle It Properly

- Inspect the **exact role names recognized by the container** in the realm and security role declarations.
- Check `request.isUserInRole(...)` directly at a trusted point before Spring request wrappers.
- Configure `mappableRoles(...)` accordingly; if authorities are already prefixed or must follow a custom convention, consider `mappableAuthorities(...)` or custom mapping with clear understanding of prefixes.
- Verify the difference between `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")` under Spring conventions.
- For multi-tenant/internal-group role mapping, enrich authorities via a trusted service. Never escalate privileges from user-submitted strings/roles.

Never "quick-fix" by switching all of `/app/**` to `permitAll()`; that merely hides mapping bugs and destroys the authorization boundary.

## 9. Once the Container Authenticates, How Are Sessions and Logout Handled?

The **login** responsibility belongs to the container or upstream SSO system; this affects logout, session lifetimes, and principal refreshes.

- **Sessions:** the container may use HTTP sessions, per-request BASIC, SSO cookies, or another mechanism depending on the app server. Spring Security also has `SecurityContext`, persistence policies, and its own session management. Both lifecycles must be understood together; never infer how the container behaves solely from the presence of `JSESSIONID`.
- **Logout:** Spring's `http.logout()` does not guarantee invalidating external SSO sessions or logging out of the container realm. The Servlet API offers `HttpServletRequest.logout()` in supporting environments, though exact behavior depends on the container; sometimes logout must integrate with the IdP/SSO gateway. Never claim global logout without testing it.
- **Role changes during an active session:** container roles may be cached, and Spring Security's context has its own lifecycle. When roles are revoked, plan appropriate refresh or invalidation so stale permissions do not linger too long.
- **CSRF:** if browsers automatically send auth cookies, POST/PUT/PATCH/DELETE requests still face CSRF risks; keep Spring Security's CSRF defenses where appropriate. Container-managed login does not mean CSRF disappears.
- **HTTPS:** use TLS for login, cookies, redirects, and APIs; configure `Secure`, `HttpOnly`, and `SameSite` properly and evaluate proxy/forwarded headers.

Never treat `request.getUserPrincipal() != null` as sufficient proof to allow all sensitive operations: authorization must still verify business roles/permissions, resource ownership, account status, and business rules.

## 10. How Does JEE Pre-auth Differ from Header-Based Pre-auth?

Spring Security also includes `RequestHeaderAuthenticationFilter`, often used when a proxy/SSO gateway forwards usernames via a header (e.g., `SM_USER`). That is **not** the default JEE container authentication mechanism.

| Criterion | JEE container pre-auth | Header-based pre-auth |
| --- | --- | --- |
| Principal source | `HttpServletRequest.getUserPrincipal()` established by the container. | Header supplied by an upstream system, extracted by a separate filter. |
| Role source | `request.isUserInRole(...)` or trusted user-details mapping. | Upstream system/role provider configured by the application. |
| Spring filter | `J2eePreAuthenticatedProcessingFilter`. | `RequestHeaderAuthenticationFilter`. |
| Trust condition | Container authenticated the request and no path bypasses realm/constraints. | Proxy blocks direct clients, strips spoofed headers, and sets trusted header itself. |
| Configuration risk | Container provides no principal or role mapping mismatches. | Attacker injects username header and impersonates users if upstream fails to protect. |

**Never trust `X-Remote-User`, `X-User`, or `X-Authenticated-User` merely because the header name sounds "authenticated."** Clients can send those headers themselves if the proxy is not locked down. If header pre-auth is needed, define network boundaries, TLS/mTLS, header stripping/overwriting at the proxy, and block direct paths bypassing the proxy.

With JEE, what you trust is the **container-guaranteed identity**, not a request attribute/header populated arbitrarily by application code.

## 11. Testing Integration with the Right Mechanism

### 11.1 Live Testing on a Servlet Container

Use a container with a real realm and two accounts: a USER-only user and an ADMIN user. Deploy the WAR with aligned `web.xml` and Spring Security config.

| Scenario | Expectation |
| --- | --- |
| Unauthenticated call to `/app/identity` | Container challenges or rejects per login mechanism; controller is never reached with a valid identity. |
| Alice with role USER accesses `/app/identity` | Container authenticates; Spring receives principal; returns `username` and mapped `ROLE_USER`. |
| Alice (USER only) accesses `/app/admin/report` | Spring `hasRole("ADMIN")` rejects; typically HTTP 403. |
| Bob with ADMIN accesses `/app/admin/report` | Passes authorization checks if container constraint also allows it and endpoint exists. |
| Valid container user yet `isUserInRole("USER")` is false | Spring lacks authority; may return 403 even though container login succeeded. |
| Container emits no principal | Pre-auth has no identity to extract; request is rejected per config without falling back to a valid user. |

Final outcomes depend on the endpoint, container security policy, and method-level rules; these are **test expectations**, not a live run transcript.

When using container BASIC over HTTPS with test accounts, test manually as suited to the environment (browser or HTTP client). Never put real passwords into terminal history or docs. Verify status codes, challenges/redirects, and that the application **does not** execute controllers without sufficient privileges.

### 11.2 Distinguishing MockMvc Unit Tests from Integration Tests

Spring Security Test offers helpers like `with(user("alice").roles("USER"))` to **simulate a Spring Security Authentication** in MockMvc. They are convenient for testing authorization in Controllers/Services, yet **do not prove** the Servlet Container authenticated the user, `isUserInRole` behaves right, or `J2eePreAuthenticatedProcessingFilter` actually received a principal from the container.

To test real JEE pre-auth, run inside a Servlet Container configured with realms/constraints, or write integration tests mocking the container request/pre-auth filter and full role mapping. Never treat a unit test with `@WithMockUser` as proof that production SSO/container integration is right.

## 12. Deployment Diagnostics

| Symptom | Common cause | Diagnostic check |
| --- | --- | --- |
| Every request returns 403 | Container provides no principal, realm/constraints unconfigured, or security chain misaligned. | Inspect container auth before Spring; check filter chain and `request.getUserPrincipal()` at pre-Spring boundary. |
| No login form appears | `.jee()` does not generate a login page; container login method/realm is unconfigured. | Check deployment descriptor and container auth mechanism. |
| User logs in yet `hasRole("ADMIN")` always fails | `isUserInRole("ADMIN")` is false, role names mismatch, or mapping prefixes wrong. | Inspect container roles, `mappableRoles`, and granted authorities. |
| User belongs to IdP group yet lacks Spring role | IdP group not mapped to a JEE role by container, or role absent from mappable list. | Check container realm/role mapper before editing Spring. |
| `/health` demands container login despite Spring `permitAll` | Container constraint protects the URL and runs before Spring. | Inspect `web.xml` and active URL security constraints. |
| Sensitive endpoint bypasses authentication | A URL/method sits outside container constraints or an access path bypasses the trusted gateway. | Audit all entry points, dispatcher types, context paths, and security matchers; close bypasses. |
| Spring logout still allows app access via SSO | Container/IdP session persists; Spring logout does not equal SSO logout. | Design cross-layer logout and test session revocation. |
| Embedded Boot runs yet principal is always null | `http.jee` enabled without configuring an embedded container auth realm. | Configure a real container or choose an appropriate native Spring auth mechanism. |
| Account role changed yet old privileges remain | Caching in realm, session, or SecurityContext. | Configure expiration/invalidation and test role revocation. |
| Principal "appears" in controller yet not from realm | Spring Security wrapper altered how the request exposes principal. | Inspect raw container request before security wrapper and Spring Authentication separately. |

### Safe Debugging Sequence

1. **At the container:** are a real realm and login mechanism configured? Is the URL protected by the container? Does the realm authenticate users and map roles accurately?
2. **Before Spring filters:** what do `getUserPrincipal()`, `getRemoteUser()`, and `isUserInRole(...)` return? Can any request bypass security constraints?
3. **In Spring Security:** does `J2eePreAuthenticatedProcessingFilter` run in the right chain? Does `PreAuthenticatedAuthenticationProvider` produce an `Authentication`? Which authorities are granted?
4. **At authorization:** which matcher matches the URL? Which `ROLE_*` does `hasRole` require? Are method security rules involved?
5. **Lifecycle:** are logout, session timeout, role changes, redirects/proxies, and HTTPS/CSRF synchronized with container/SSO?

When debugging, never log authentication credentials, session IDs, passwords, SSO tickets, or sensitive tokens. Never return the entire security context directly to users outside controlled testing.

## 13. When Should You Choose JEE Pre-auth?

**Appropriate** when deploying a Servlet application to an enterprise container/application server with standardized realm/SSO supplying a trusted principal and roles, and Spring Security needs to leverage that identity for URL authorization, method security, and application components.

**Not the best fit** when a standalone Spring Boot application runs on an embedded server without container auth, or the system primarily uses a JWT Bearer resource server/OIDC login implemented directly by Spring Security. Those mechanisms have their own filter chains and configurations; do not add `.jee()` out of habit if the container does not perform pre-authentication.

**Remember the chain:** **Servlet Container authenticates first → request holds trusted principal/roles → J2eePreAuthenticatedProcessingFilter extracts identity → Spring Security builds Authentication and mapped authorities → authorization enforces per URL/method**. Test both container and Spring boundaries; if the principal source is untrustworthy, every downstream rule rests on a broken foundation.

## Official References

- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html
- Spring Security API — JeeConfigurer: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/config/annotation/web/configurers/JeeConfigurer.html
- Jakarta Servlet API — HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest
