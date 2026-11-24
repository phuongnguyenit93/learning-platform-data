# Integrating OAuth2 Login and Mapping OIDC Users to Internal Roles in Spring Security Reactive

## 1. Goals and Context

In a **Spring WebFlux** application, logging in with OpenID Connect (OIDC) authenticates users against an Identity Provider (IdP), while **internal authorization** decides what they are allowed to do inside the application. These two steps must be wired properly: a successful login does not automatically grant administrative privileges, and an external claim is not automatically an internal role.

After this lab, you will be able to:

- Configure OAuth2 Login/OIDC with **Authorization Code** in Spring Boot WebFlux.
- Distinguish **ID Token**, **Access Token**, **OAuth2 scope**, **OIDC claims**, **`GrantedAuthority`**, and **internal roles**.
- Use the stable OIDC identity **(issuer, subject)** to look up a user/membership and roles in your system.
- Map authorities **asynchronously** via `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` and `OidcReactiveOAuth2UserService`.
- Apply `hasRole` and `hasAuthority` to routes and reactive methods; avoid privilege escalation via unapproved emails, groups, or claims.
- Unit-test the mapper with JUnit and test WebFlux authorization with `WebTestClient` + `mockOidcLogin()`, while knowing what still requires testing against a real login flow.

**Context:** Spring Security - reactive module, **Integrated Practice** topic. Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x, `Mono`, and `SecurityWebFilterChain`. `HttpSecurity`, `SecurityFilterChain`, synchronous `OidcUserService`, and `MockMvc` belong to **Servlet**; do not mistakenly use them for WebFlux.

## 2. How OIDC Login Differs from Application Authorization

**OAuth 2.0** is an authorization framework. **OpenID Connect 1.0** adds a user authentication layer, including the ID Token and validation rules. Spring Security OAuth2 Login uses the Authorization Code flow; the `openid` scope triggers OIDC processing.

| Concept | Source | Purpose | Do not assume |
| --- | --- | --- | --- |
| `authorization_code` | Redirect callback after IdP login | Exchanged once at the token endpoint for tokens | Neither an access token nor a user session |
| **ID Token** (JWT) | IdP, intended for the OAuth client | Proves the authentication event and carries claims like `iss`, `sub`, `aud`, `exp` | Not the default token for calling protected APIs |
| **Access Token** | IdP/Authorization Server | Authorizes calling APIs for granted scopes | Having a scope does not imply having an internal role |
| `scope=openid profile email` | OAuth client requesting from IdP | Permission/ability to receive identity attributes | Not equivalent to `ROLE_ADMIN` |
| `sub` | Validated ID Token | Subject identifier within the corresponding issuer | Not an email, and not guaranteed globally unique across the Internet |
| `email`, `email_verified` | ID Token/UserInfo depending on provider | Contact info; verified reflects the IdP's email verification policy | Does not prove internal role assignment |
| `groups`, `roles` IdP-specific claims | Provider-configured claims | Can serve as mapping input if the trust policy is explicit | Neither standard OIDC role claims nor guaranteed to generate `ROLE_*` by default |
| `GrantedAuthority` | Spring Security | System permission string used for checks | Not necessarily identical to raw claim contents |
| `ROLE_ADMIN` | Application policy | `hasRole("ADMIN")` checks this authority | Does not appear automatically upon OIDC login success |

In WebFlux, a successful OIDC login typically produces an `OAuth2AuthenticationToken` whose principal is an `OidcUser`. Default authorities may include authorities such as **`OIDC_USER`** and **`SCOPE_...`**; internal roles require explicit mapping configuration. `OAuth2AuthenticationToken.getAuthorities()` is what drives `hasRole/hasAuthority` decisions.

Distinguish **OAuth2 Login** (interactive browser user logging in and keeping a session) from **OAuth2 Resource Server** (an API receiving a Bearer token on every request). Although both relate to OAuth2/OIDC, they have different entry points, principals, tokens, and authorization models.

## 3. OIDC Login Flow in a WebFlux Application

~~~text
Browser                       WebFlux App                     IdP
    | GET /oauth2/authorization/corp   |                         |
    |--------------------------------->|                         |
    |                                  | builds OAuth2 request   |
    |                                  | state, redirect URI     |
    | 302 to authorization endpoint    |                         |
    |<---------------------------------|                         |
    |------------------------------ authorization/login -------->|
    |                                  |                         |
    | callback ?code=...&state=...     |<------------------------|
    |--------------------------------->|                         |
    |                                  | exchanges code at token endpoint
    |                                  | receives & validates ID Token
    |                                  | loads OIDC user/UserInfo
    |                                  | extracts (iss, sub)     |
    |                                  | looks up internal roles (reactive)
    |                                  | builds authorities      |
    | session/cookie + redirect        |                         |
    |<---------------------------------|                         |
    | GET /admin/dashboard             |                         |
    |--------------------------------->| hasRole("ADMIN")        |
    |           200 / 403              |                         |
    |<---------------------------------|                         |
~~~

Specifically:

1. The user initiates login at **`/oauth2/authorization/{registrationId}`**, e.g., `/oauth2/authorization/corp`.
2. Spring creates the authorization request and binds `state` to the browser session for callback verification; in appropriate OIDC configurations, nonce checks also apply. For public clients or configs requiring PKCE, ensure **PKCE** is properly enabled per client type.
3. The IdP authenticates the user and redirects the browser back to **`/login/oauth2/code/{registrationId}`** with `code` and `state`. This endpoint is the default callback and must match the redirect URI registered at the IdP.
4. Spring's OAuth2 client exchanges the code, validates parameters/tokens according to provider/OIDC rules, and creates an `OidcUser`. Rely on the official library mechanisms to enforce issuer, audience, signature, token lifetime, and state/nonce; never manually parse an ID Token and trust its contents.
5. **After the OIDC identity is authenticated**, the application maps `(iss, sub)` to an internal account and roles. The resulting authority set is attached to the `Authentication` when login finishes.
6. `SecurityWebFilterChain` and/or reactive method security evaluates those authorities to allow or deny endpoint access.

**For browser login**, an unauthenticated request to a protected resource typically receives a **302 redirect** to the login page; an authenticated user lacking permissions typically receives **403**. For a separate Bearer API, a missing token typically returns **401**. Do not force both modes into a single status matrix while ignoring which entry point is configured.

## 4. Designing the Identity and Role Model Before Writing Code

Keep at least two distinct data areas:

- **Linked OIDC identity:** `issuer`, `subject`, `internal_user_id`, `status`, and controlled profile fields.
- **Internal permissions:** `internal_user_id`, `tenant_id` if multi-tenant, `role_code`, `enabled`, and version or modification timestamp.

Conceptual schema example:

~~~text
app_user
  id              UUID / bigint
  oidc_issuer     VARCHAR (NOT NULL)
  oidc_subject    VARCHAR (NOT NULL)
  status          ACTIVE | DISABLED
  UNIQUE(oidc_issuer, oidc_subject)

app_user_role
  app_user_id
  tenant_id       (if the system is multi-tenant)
  role_code       USER | AUDITOR | ADMIN
  enabled
~~~

**The linking key should be `(iss, sub)`.** Across two different issuers, the same `sub` can refer to two completely different users. Email addresses can change, be recycled, or be absent; never auto-merge two accounts just because their emails match. With certain pairwise subject configurations, `sub` can differ across OAuth clients; when linking multiple clients, follow an explicit account-linking policy.

**Authoritative role source:** in this lab, the **internal database/role service** decides who holds `USER`, `AUDITOR`, and `ADMIN`. A `groups` claim from the IdP may be used once an organization defines trusted issuers, specific group IDs, an allowlist mapping, and a revocation workflow. Never blindly map `ROLE_` + every external group string; external IdP groups and internal roles can carry very different semantics.

Minimum rules:

1. **Deny by default:** a new OIDC user or one without membership receives neither `ADMIN` nor any sensitive role.
2. **Explicit allowlist:** only role codes recognized by the application are converted to `ROLE_*`.
3. **Fail closed:** a failed role lookup must never silently `onErrorReturn(Set.of("ADMIN"))` or grant access. Decide explicitly between failing login or granting empty roles; when the permission service is unavailable, failing login is safer than elevating privileges.
4. **Tenant isolation:** do not check only `hasRole("ADMIN")` if a role is tenant-scoped; verify tenant/resource ownership in business logic.
5. **Refresh timing choice:** mapping at login creates a permission snapshot in the session, which may not immediately reflect revocations on subsequent requests.

## 5. Configuring Spring Boot 3.x + WebFlux OAuth2 Login

### 5.1. Dependencies

A Gradle project that already includes the Spring Boot plugin and dependency management needs the following dependencies (this is a **`build.gradle` snippet**, not a standalone file):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

test {
    useJUnitPlatform()
}
~~~

For reactive PostgreSQL role lookups, a real deployment can add `spring-boot-starter-data-r2dbc` and its driver; the main example isolates the role service behind an interface so login configuration is decoupled from database queries.

### 5.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.test/realms/training
~~~

This is a **sample configuration**; replace `issuer-uri` with the real URL published by your IdP, and register the OAuth client and exact redirect URI at the IdP. `OIDC_CLIENT_SECRET` comes from an environment variable or secret manager—**never commit it** to Git or expose it to a frontend. The sample assumes a **confidential server-side client**; public clients follow different PKCE and client authentication policies.

`issuer-uri` enables Spring/Boot to discover OIDC metadata and endpoints as supported by the IdP. Network access and valid TLS configuration are required. Behind a reverse proxy, ensure `baseUrl`/scheme/host reflect the **public HTTPS URL** from a trusted proxy; do not allow arbitrary clients to spoof forwarded headers and generate arbitrary redirects. The callback URI must match scheme, host, path, and `registrationId`.

In development environments, you may need test IdP accounts, a local callback URL, and HTTPS/tunnels according to provider rules. Do not use a real IdP for pure unit tests of mapping logic.

## 6. Implementation Example: OIDC Identity → Internal Roles → WebFlux Authorization

This example includes the application entry point, security config, role service, and controller inside package `demo.oidc`. The role service uses **fixed illustrative data** to demonstrate the mechanism; production must replace it with a real DB/API backed by provisioning and revocation workflows.

### 6.1. Application Entry Point

File `src/main/java/demo/oidc/OidcRoleDemoApplication.java`:

~~~java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcRoleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcRoleDemoApplication.class, args);
    }
}
~~~

### 6.2. Role Lookup Interface by Issuer + Subject

File `src/main/java/demo/oidc/InternalRoleService.java`:

~~~java
package demo.oidc;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface InternalRoleService {

    // Must emit a Set (possibly empty), or onError when lookup fails.
    // Never return Mono.empty() to "pretend success".
    Mono<Set<String>> rolesFor(String issuer, String subject);
}
~~~

File `src/main/java/demo/oidc/DemoInternalRoleService.java`:

~~~java
package demo.oidc;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DemoInternalRoleService implements InternalRoleService {

    private record UserKey(String issuer, String subject) {
    }

    // Intentional fixture; DO NOT use as real role storage.
    private static final Map<UserKey, Set<String>> ROLES = Map.of(
        new UserKey(
            "https://idp.example.test/realms/training", "alice-sub"),
            Set.of("USER", "ADMIN"),
        new UserKey(
            "https://idp.example.test/realms/training", "bob-sub"),
            Set.of("USER")
    );

    @Override
    public Mono<Set<String>> rolesFor(String issuer, String subject) {
        return Mono.just(ROLES.getOrDefault(
            new UserKey(issuer, subject), Set.of()));
    }
}
~~~

The example assumes a test IdP issues ID Tokens whose `sub` matches the fixture entries. With a real IdP, subjects usually cannot be chosen arbitrarily; **sync the linked user record** from an authenticated IdP and assign roles through an administrative workflow rather than relying on email or guessing `sub`. An unprovisioned account receives an empty role set.

### 6.3. SecurityWebFilterChain and Reactive OIDC User Service

File `src/main/java/demo/oidc/OidcSecurityConfig.java`:

~~~java
package demo.oidc;

import java.util.Collection;
import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo
        .OidcReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo
        .ReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo
        .OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user
        .DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user
        .OidcUser;
import org.springframework.security.oauth2.core.oidc.user
        .OidcUserAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class OidcSecurityConfig {

    private static final Set<String> KNOWN_ROLES =
            Set.of("USER", "AUDITOR", "ADMIN");

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .pathMatchers("/reports/**").hasAnyRole("USER", "ADMIN")
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveOAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            InternalRoleService roleService) {

        OidcReactiveOAuth2UserService delegate =
                new OidcReactiveOAuth2UserService();

        return request -> delegate.loadUser(request)
            .flatMap(user -> {
                // Only use after the OIDC token has been validated.
                String issuer = user.getIdToken().getIssuer().toString();
                String subject = user.getIdToken().getSubject();

                return roleService.rolesFor(issuer, subject)
                    .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                            "Role service returned empty publisher")))
                    .map(roles -> (OidcUser) new DefaultOidcUser(
                        mapAuthorities(user.getAuthorities(), roles),
                        user.getIdToken(),
                        user.getUserInfo()));
            });
    }

    // Package-private so mapping logic can be unit-tested.
    static Set<GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> providerAuthorities,
            Set<String> internalRoles) {

        Set<GrantedAuthority> result = new HashSet<>();

        // Keep OIDC identity and OAuth scopes; drop any external ROLE_*.
        // Internal ROLEs come solely from the trusted role service.
        for (GrantedAuthority authority : providerAuthorities) {
            String name = authority.getAuthority();
            if (authority instanceof OidcUserAuthority
                    || (name != null && name.startsWith("SCOPE_"))) {
                result.add(authority);
            }
        }

        for (String role : internalRoles) {
            if (KNOWN_ROLES.contains(role)) {
                result.add(new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return Set.copyOf(result);
    }
}
~~~

**How each part works:**

1. `.oauth2Login(Customizer.withDefaults())` enables the browser/OIDC login flow for WebFlux. A `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` bean is the extension point for customizing the user after OIDC login; registering this bean is documented in Spring Security Reactive.
2. `delegate.loadUser(request)` handles the default OIDC user before `.flatMap(...)` looks up roles. This is a **reactive** lookup; never `.block()` inside the request/login flow.
3. `user.getIdToken().getIssuer()` and `.getSubject()` define the link. Do not use email as the account key.
4. `roleService.rolesFor(...)` must return a `Mono` emitting **a Set**, or `onError`. Lookup failures remain login failures rather than falling back to granting permissions. `switchIfEmpty` guards against implementations returning `Mono.empty()`.
5. `mapAuthorities(...)` retains only the OIDC identity authority and `SCOPE_...` from the provider, **discarding any external `ROLE_...`**. Only the three allowlisted internal roles produce `ROLE_USER`, `ROLE_AUDITOR`, `ROLE_ADMIN`.
6. `new DefaultOidcUser(...)` builds a new principal carrying the original loaded ID Token and UserInfo while holding the application's authorities. Spring uses these authorities in the post-login `Authentication`.
7. `.hasRole("ADMIN")` checks for **`ROLE_ADMIN`**, while `.hasAuthority("SCOPE_reports.read")` checks the exact `SCOPE_reports.read` string; `hasRole("ROLE_ADMIN")` is usually a mistake because the prefix is applied automatically.

If a provider requires a name attribute other than `sub`, Spring provides `DefaultOidcUser(authorities, idToken, userInfo, userNameAttributeName)`; choose only an attribute verified by the IdP and present in the claims. This example keeps the default `sub`, matching the linking key.

**Security boundary:** the mapping does not grant roles from raw `"roles"` or `"groups"` claims. If an organization wants IdP groups to assign roles directly, map only **approved group IDs** from a trusted issuer with testing and revocation processes. Users must never supply `groups` via request headers/bodies to influence permissions.

### 6.4. Controller Receiving the Post-Login Principal

File `src/main/java/demo/oidc/DemoController.java`:

~~~java
package demo.oidc;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Login: /oauth2/authorization/corp");
    }

    @GetMapping("/me")
    public Mono<String> me(@AuthenticationPrincipal OidcUser user) {
        // Expose only the currently logged-in user's sub.
        return Mono.just("subject=" + user.getIdToken().getSubject());
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @GetMapping("/admin/dashboard")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
~~~

`@AuthenticationPrincipal OidcUser` is the proper type for OIDC Login. A Resource Server route validating JWT Bearer tokens can create a `JwtAuthenticationToken` and does not necessarily have an `OidcUser`; do not force one controller to assume both principal types without a unified design.

With a real IdP client, a registered callback, and valid `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET`, run:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Visit `/`, then `/oauth2/authorization/corp` to start login. If the IdP returns an identity whose `issuer`/`subject` matches Alice in the fixture: `/me` returns `subject=alice-sub`; `/reports` returns `reports-ok`; `/admin/dashboard` returns `admin-ok`. If it matches Bob: `/reports` succeeds while `/admin/dashboard` returns HTTP 403. If the role service finds no user, neither `ROLE_USER` nor `ROLE_ADMIN` is present, so role-protected endpoints return 403. These are **conditional outcomes based on the fixture and IdP configuration**, not hardcoded Java stdout or a promise that the illustrative provider URL is live.

## 7. Real Role Lookup with a Reactive Data Store

In production, replace `DemoInternalRoleService` with a real repository/API service. With Spring Data R2DBC, a query pattern (an **implementation snippet**, requiring a real schema and dependencies):

~~~java
public Mono<Set<String>> rolesFor(String issuer, String subject) {
    return databaseClient.sql("""
            SELECT r.role_code
            FROM app_user u
            JOIN app_user_role r ON r.app_user_id = u.id
            WHERE u.oidc_issuer = :issuer
              AND u.oidc_subject = :subject
              AND u.status = 'ACTIVE'
              AND r.enabled = TRUE
            """)
        .bind("issuer", issuer)
        .bind("subject", subject)
        .map((row, meta) -> row.get("role_code", String.class))
        .all()
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
}
~~~

`databaseClient` is an injected `org.springframework.r2dbc.core.DatabaseClient`; you also need `spring-boot-starter-data-r2dbc`, a DB driver, and appropriate tables/constraints/migrations. SQL parameters are **bound**, never concatenated into SQL strings. `collect(...)` with zero rows emits an empty `Set.of()`; connection errors emit `onError` rather than silently granting permissions.

In a multi-tenant system, the query above is **not enough** to grant tenant-scoped `ROLE_ADMIN`: add tenant to the lookup key, parameters, and policy, and validate the tenant specified by the request against the user's real membership. When roles are tenant-scoped, consider authorities like `PERM_REPORT_APPROVE` paired with tenant/resource checks, or use a `ReactiveAuthorizationManager` with explicit verification. Never let an ADMIN role in tenant A become app-wide admin privileges.

### First-Time Account Provisioning

Choose an explicit strategy:

- **Pre-provisioning**: only users already assigned internal roles receive permissions; a new OIDC login may create an empty profile but grants no business access.
- **Just-in-time provisioning**: after verifying `(iss,sub)`, create an internal account with minimal approved permissions. Use a unique constraint and handle concurrent logins to avoid duplicate user records.
- **Invite/linking flow**: link users only after an invitation or out-of-band confirmation. Never auto-link by `email`, because matching email or `email_verified=true` does not imply identical current permissions.

If an account is disabled, the role service must reject login or return no roles per policy; avoid leaking account existence through external error messages.

## 8. Role of GrantedAuthoritiesMapper and Choosing the Extension Point

Spring Security Reactive provides two common approaches:

| Strategy | API kind | When to use | Limitations |
| --- | --- | --- | --- |
| `GrantedAuthoritiesMapper` bean | Synchronous mapping from `Collection<GrantedAuthority>` | Roles derive from already-present claims with a simple allowlist and no I/O | Unsuitable for reactive DB/HTTP calls inside the mapper |
| `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` bean | Reactive `Mono`, receives request and token/user | Need to query membership/roles from DB/HTTP and build a new `OidcUser` | Must preserve errors and proper logout/session semantics |
| Resource Server converter | JWT/Opaque token → `Authentication` | Bearer token APIs, not browser OIDC Login | Does not replace OIDC login sessions |

Example **code snippet** for a mapper based on an approved IdP group:

~~~java
@Bean
GrantedAuthoritiesMapper userAuthoritiesMapper() {
    return input -> {
        Set<GrantedAuthority> result = new HashSet<>();
        for (GrantedAuthority authority : input) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object groups = oidc.getIdToken()
                    .getClaims().get("groups");

                if (groups instanceof java.util.Collection<?> values
                        && values.contains("corp-report-admins")) {
                    result.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                }
            }
        }
        return result;
    };
}
~~~

This is an **alternative** to the database role mapping in the main example—do not copy both at once without defining authority precedence. `groups` is an **IdP-specific claim**; use it only if the issuer/client is trusted and claim issuance is controlled. In a real mapper, preserve needed authorities (`OIDC_USER`, `SCOPE_...`) if your policy uses them; the snippet intentionally highlights only the group ID allowlist. Never use an unconditional `map(group -> "ROLE_" + group)`.

If mapping from claims located in UserInfo, note that ID Token and UserInfo do not necessarily share identical claims. Spring's `OidcUserAuthority` exposes both ID Token and UserInfo, and `OidcUser` provides corresponding getters. Whenever UserInfo could ever differ on `subject`, verify subject/issuer consistency and the OIDC provider's trust contract; never merge attributes from two different subjects.

## 9. Unit-Testing Mapping Logic with JUnit 5

File `src/test/java/demo/oidc/OidcRoleMappingTest.java`:

~~~java
package demo.oidc;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcRoleMappingTest {

    @Test
    void discardsExternalRoleAndUsesOnlyApprovedLocalRole() {
        List<GrantedAuthority> external = List.of(
            new SimpleGrantedAuthority("ROLE_ADMIN"),
            new SimpleGrantedAuthority("SCOPE_openid"),
            new SimpleGrantedAuthority("EXTERNAL_POWER"));

        Set<GrantedAuthority> mapped =
            OidcSecurityConfig.mapAuthorities(external,
                Set.of("USER", "SUPER_ADMIN"));

        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("ROLE_USER")));
        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("SCOPE_openid")));

        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("ROLE_ADMIN")));
        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("ROLE_SUPER_ADMIN")));
        assertFalse(mapped.contains(
            new SimpleGrantedAuthority("EXTERNAL_POWER")));
    }

    @Test
    void missingInternalMembershipGivesNoInternalRole() {
        Set<GrantedAuthority> mapped =
            OidcSecurityConfig.mapAuthorities(
                List.of(new SimpleGrantedAuthority("SCOPE_profile")),
                Set.of());

        assertTrue(mapped.contains(
            new SimpleGrantedAuthority("SCOPE_profile")));
        assertFalse(mapped.stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(name -> name.startsWith("ROLE_")));
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.oidc.OidcRoleMappingTest
~~~

These two tests confirm **external authorities do not become internal roles** and users without membership receive no role. No IdP or network is needed for this pure mapping unit test. The code has no predetermined stdout; JUnit reports PASS/FAIL.

## 10. Testing WebFlux Authorization Rules with mockOidcLogin()

`SecurityMockServerConfigurers.mockOidcLogin()` simulates an OIDC principal/`Authentication` when handling a request. It is great for testing `hasRole`, `@AuthenticationPrincipal`, and controllers, yet it **does not go through authorization-code redirects, token exchange, ID Token signature validation, or the real role-mapping user service**.

File `src/test/java/demo/oidc/OidcAuthorizationTest.java` demonstrates testing rules against a WebFlux context independent of an IdP:

~~~java
package demo.oidc;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.EnableWebFlux;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OidcAuthorizationTest.TestConfig.class)
class OidcAuthorizationTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void oidcPrincipalWithoutInternalAdminRoleIsForbidden() {
        client.mutateWith(mockOidcLogin()
                .authorities(new SimpleGrantedAuthority("SCOPE_read")))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void untrustedRolesClaimIsNotEnoughForAuthorization() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token.claim(
                    "roles", java.util.List.of("ADMIN"))))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void explicitInternalAdminAuthorityIsAcceptedByRule() {
        client.mutateWith(mockOidcLogin()
                .authorities(new SimpleGrantedAuthority("ROLE_ADMIN")))
            .get().uri("/admin/dashboard")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void principalSubjectComesFromOidcIdToken() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token.claim("sub", "alice-sub")))
            .get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice-sub");
    }

    @Configuration
    @EnableWebFlux
    @EnableWebFluxSecurity
    static class TestConfig {

        @Bean
        SecurityWebFilterChain rules(ServerHttpSecurity http) {
            return http.authorizeExchange(ex -> ex
                    .pathMatchers("/admin/dashboard").hasRole("ADMIN")
                    .pathMatchers("/me").authenticated()
                    .anyExchange().denyAll())
                .build();
        }

        @Bean
        TestEndpoints testEndpoints() {
            return new TestEndpoints();
        }
    }

    @RestController
    static class TestEndpoints {

        @GetMapping("/admin/dashboard")
        public Mono<String> admin() {
            return Mono.just("admin-ok");
        }

        @GetMapping("/me")
        public Mono<String> me(@AuthenticationPrincipal OidcUser user) {
            return Mono.just(user.getIdToken().getSubject());
        }
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.oidc.OidcAuthorizationTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests demo.oidc.OidcAuthorizationTest
~~~

**Expected result:** 4 tests PASS if dependencies and the WebFlux test context match the example. These tests verify that an unmapped `"roles": ["ADMIN"]` claim **does not automatically become `ROLE_ADMIN`**, whereas an explicit `ROLE_ADMIN` authority in the mock passes the rule. The fourth test verifies that `OidcUser` in the controller receives the supplied `sub`.

These are **authorization rule** tests and do not exercise `OidcReactiveOAuth2UserService` from section 6. To test the real mapping pipeline, test the service separately with a fake dependency or run an integration test with a simulated OIDC provider.

## 11. End-to-End Testing: What Mocks Cannot Prove

### Test Layers to Distinguish

| Layer | Tools | What it verifies |
| --- | --- | --- |
| Pure mapping | JUnit calling `mapAuthorities` | External roles dropped, internal roles match whitelist |
| WebFlux authorization | `WebTestClient` + `mockOidcLogin` | 200/403 by authorities, principal injected into handler |
| Reactive user service | Fake/mock role service, OAuth2 user service delegate test double | `(iss,sub)` lookup accuracy, errors preserved, new `DefaultOidcUser` preserves token/UserInfo |
| OAuth2/OIDC login flow | Test IdP (e.g., test Keycloak instance / protocol mock server) | `state`/`nonce`, redirects, token exchange, ID Token validation, UserInfo, session cookie |
| Production security behavior | Staging environment with real IdP and test role DB | Logout, role updates, tenant isolation, HTTPS proxy, observability |

Key scenarios:

1. **Successful login, internal user has USER:** `/reports` allowed; `/admin/dashboard` returns 403.
2. **Successful login, internal user has ADMIN:** `/admin/dashboard` allowed.
3. **Successful login but no provisioned permissions:** profile page may render (if policy allows), while sensitive data pages return 403.
4. **IdP group claim intentionally set to ADMIN:** denied unless the internal role service grants `ROLE_ADMIN`.
5. **Role lookup DB/HTTP timeout:** login fails per policy, never auto-granting USER/ADMIN; log safe metadata only.
6. **Wrong issuer or subject:** never maps to an account from another issuer or a matching email.
7. **Account disabled or membership revoked:** enforce revocation policy and session invalidation/revalidation.
8. **Two tenants:** an ADMIN of tenant A has no admin access to tenant B.
9. **State mismatch/forged redirect, invalid token signature/audience/expiry:** rejected by OIDC validation, never bypassed by mocks.
10. **Multiple concurrent first-time logins:** no duplicate user/role links created, no wrong default roles assigned.

If the app uses `@PreAuthorize("hasRole('ADMIN')")`, enable `@EnableReactiveMethodSecurity`, invoke methods through Spring bean/proxies, and return `Mono`/`Flux` so the context propagates properly. Test both route-level and method-level security; passing a filter does not guarantee resource-level permissions were checked.

### Wiring the Role Service into Tests

In service tests, stub role lookup to return `Mono.just(Set.of("USER"))` for a known `(iss,sub)` and `Mono.error(new RuntimeException(...))` for infrastructure failures. Verify the service **does not** use `.onErrorReturn(...)` to elevate permissions. With the OIDC delegate, use a test double or protocol test IdP because `OidcReactiveOAuth2UserService` may call the HTTP UserInfo endpoint by default.

Be careful never to use `mockOidcLogin().authorities(ROLE_ADMIN)` as proof that the system maps roles from the database: that test pre-supplies the authority and bypasses the mapper itself.

## 12. Login Sessions, Role Changes, and Revocation

An important point: mapping at **login time** populates authorities on the `Authentication`. In an application using a **web session**, those authorities can persist until the session is updated, invalidated, or the user logs in again.

~~~text
t0  Alice logs in: DB roles = USER, ADMIN -> session holds ROLE_ADMIN
t1  Administrator revokes ADMIN in DB
t2  Alice reuses old session: Authentication may still hold ROLE_ADMIN
t3  Only after session invalidation/recheck are permissions downgraded
~~~

To support rapid revocation:

- Define a **role freshness** SLA and session lifetime; consider invalidating sessions on permission changes or using push invalidation.
- For sensitive operations, evaluate authorization at **action time** against an authoritative DB/policy service rather than relying solely on the login-time `hasRole` snapshot.
- Attach a permission version to the user/session and compare against DB or a short-TTL cache per policy, avoiding unnecessary lookups on every harmless request.
- Distinguish **local logout** (clearing the app session) from **OIDC RP-initiated logout** at the IdP and revoking OAuth authorized clients/tokens. Local logout does not automatically close all IdP SSO sessions.
- When scaling across multiple instances, store sessions safely (per architecture) and synchronize invalidation; do not rely on node-local caches when cluster-wide revocation is required.

Do not confuse internal roles with OAuth access token `scope`: updated DB roles do not mutate an existing ID Token, and a fresh login does not necessarily terminate sessions in other applications.

## 13. Protecting the Login Flow and Identity Data

- Use HTTPS, exact registered redirect URIs, and trusted reverse proxy settings.
- Let Spring Security enforce **state, nonce, ID Token signature, issuer, audience, and token lifetime**. Never disable validators or accept `alg=none` in production.
- Never display or log raw authorization codes, ID Tokens, access tokens, refresh tokens, client secrets, session cookies, or sensitive claims.
- Keep **CSRF protection** enabled for session/cookie-based browser interactions, especially state-changing requests. Never disable CSRF just to make OAuth login “work.”
- Separate web login endpoints (cookie session) from Bearer APIs when both coexist; partition with distinct `SecurityWebFilterChain` beans and explicit matchers if needed.
- When loading user data via `WebClient`, send access tokens only to **trusted** endpoints that require them; never forward ID Tokens arbitrarily to APIs or user-supplied URLs.
- Minimize scopes/permissions on the OAuth client registered with the IdP; keep client secrets in a secret manager; avoid overly broad access token scopes.
- Never accept roles from `?role=ADMIN` query parameters, arbitrary client headers, or directly from `email`.
- Profile attributes like email/displayName are **data to protect**, not authorization keys. `email_verified` only reflects provider email verification policy, not internal membership or roles.
- For multi-tenancy, check `tenant_id` from an authoritative membership/ACL rather than trusting request paths or self-declared claims.

## 14. Common Errors and Fixes

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `/oauth2/authorization/corp` fails | Missing registration or misconfigured issuer/client | Check provider metadata, client registration, and secret |
| Callback reports redirect mismatch | Behind-proxy URI differs from registered URI | Configure HTTPS public base URL and trusted forwarded headers |
| Login succeeds yet `/admin` always returns 403 | `OIDC_USER`/`SCOPE_...` is not `ROLE_ADMIN` | Inspect role service and `ROLE_ADMIN` authority |
| Claim `"roles":["ADMIN"]` present yet still 403 | Spring does not auto-map custom claims to internal roles | Implement allowlist mapping or internal role lookup |
| User from issuer B receives issuer A's roles | Lookup keyed only by `sub` or email | Key by `(iss, sub)` and verify provider |
| Revoked user still has access | `Authentication` cached role snapshot in old session | Invalidate/revalidate per freshness requirements |
| Role DB downtime breaks logins | Mapping service fails closed | Monitor errors, use bounded retry/circuit breaker for safe reads; never fallback ALLOW |
| Role mapper “runs” yet permissions mismatch | Mixing `GrantedAuthoritiesMapper` and `ReactiveOAuth2UserService` with conflicting logic | Pick one clear authority source and inspect post-login `Authentication` |
| `block()` makes WebFlux slow or hang | Calling blocking lookup on the event loop | Use reactive R2DBC/WebClient or offload blocking calls properly |
| `mockOidcLogin` passes while real login fails | Mock bypasses redirects, token validation, and user service | Add real IdP integration test or protocol test server |
| Using `HttpSecurity`/`MockMvc` in WebFlux | Mixing Servlet stack APIs | Switch to `ServerHttpSecurity` and `WebTestClient` |

Never write `hasRole("ROLE_ADMIN")` with default configuration; `hasRole("ADMIN")` already checks the `ROLE_` prefix. For custom authorities without a prefix, use `hasAuthority("EXACT_CODE")` instead of guessing.

## 15. Knowledge Self-Check

1. **Does a successful OIDC login automatically grant `ADMIN` privileges?** No. Login proves identity; internal roles must be granted by an explicit policy.
2. **Why use `(iss, sub)` instead of email?** `sub` is only meaningful within an issuer; email is unstable, can change or be reassigned, and does not represent membership.
3. **What does `hasRole("ADMIN")` match?** `ROLE_ADMIN` in the default `GrantedAuthorities`.
4. **When should you use `GrantedAuthoritiesMapper` vs. `ReactiveOAuth2UserService`?** Mapper for synchronous derivation from existing claims/authorities; service when you need `userRequest`, UserInfo, and reactive I/O for role lookup.
5. **If the roles DB does not find a new user, should it default to `ADMIN` to avoid blocking them?** Absolutely not. Grant empty roles or reject login per policy.
6. **Does `mockOidcLogin().authorities(ROLE_ADMIN)` test the internal DB lookup?** No; it pre-populates authorities and bypasses the real user service.
7. **Does revoking `ADMIN` in the DB immediately remove it from an active session?** Not guaranteed; invalidation/revalidation is needed.
8. **Can an ID Token be used as an access token to call arbitrary APIs?** No. An ID Token authenticates the OAuth client and has its own audience/semantics; APIs must validate proper access tokens.
9. **Why shouldn't a `groups` claim be freely mapped to `ROLE_*`?** Group names and trust contracts are IdP-specific; only explicitly approved groups should map to internal roles.
10. **Why might an unauthenticated web endpoint return 302 instead of 401?** OAuth2 browser login uses a redirecting authentication entry point; Bearer APIs use a different entry point.

## 16. Official References

- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced Configuration (authority mapping and OIDC user service): https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — Reactive OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Security — Reactive OAuth2 Testing (`mockOidcLogin`): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

Key mechanism to remember: **IdP authenticates identity → application links via issuer + subject → role service grants internal roles → Spring Security enforces authorities**. Testing authorization with mocks and testing the OIDC flow with an IdP are two complementary verification layers.