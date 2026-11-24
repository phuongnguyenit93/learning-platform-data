# Multi-Tenancy and Selecting Identity Stores from Controlled Data

> **Context:** Multiple authentication mechanisms in Spring Security Authentication, **Servlet** branch. This lesson focuses on multi-tenant / multi-organization applications that need to select the right identity store, `AuthenticationManager`, or identity provider. Examples run on **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**. Overarching rule: **client-supplied data may propose a login target, but server-managed configuration must determine which stores are permitted; the authentication result must be bound to the right organization.**

## 1. The Problem: Same Username Across Two Organizations

Suppose a system manages two independent organizations:

- **north** has an account `sam`, demo password `north-pass123`, role `ROLE_ANALYST`.
- **south** also has an account `sam`, but demo password `south-pass456`, role `ROLE_VIEWER`.

Identical username strings **do not mean the same principal across the entire system**. The true identity is the logical pair **`(tenantId, userId)`**, such as `(north, sam)` and `(south, sam)`. The two accounts can have different passwords, statuses, roles, IdPs, and MFA policies.

When a client calls:

```http
GET /tenants/north/me HTTP/1.1
Authorization: Basic c2FtOm5vcnRoLXBhc3MxMjM=
```

the server must verify that the credentials belong to the **north** store, rather than searching for the username across every store and taking the first match. If the client changes the URL to `/tenants/south/me` while still sending **north**'s password, the request must be rejected.

**Subtle point:** the string `north` in the path is still **client-controlled data**. We cannot trust that merely because the client chose the `north` URL, the client is a member of north. However, that path can serve as a *candidate routing key* when the server validates it against a **registered tenant list**, picks the corresponding independent manager, and then **authenticates credentials directly inside the chosen store**. Selecting the store and proving identity are two separate steps.

### Which Data Is Trusted?

| Data | Client-controllable? | Safe usage |
| --- | --- | --- |
| `/tenants/north/...` | Yes | Use only as a candidate name to look up against a server-approved registry/route |
| `X-Tenant: south` | Yes | Never dynamically pick a DataSource/manager from the header alone; require an explicit verification policy |
| Username `sam` | Yes | Only a lookup key inside the chosen store; not yet an authenticated identity |
| Password, API key, Bearer token | Yes | Proof must be verified by the corresponding provider/decoder |
| `role=ADMIN`, `authenticated=true` | Yes | **Never grant permissions or authenticated status** from these values |
| `tenantId -> AuthenticationManager` | Server-provisioned | Controlled registry; maps only to configured managers/IdPs |
| Tenant's `userId -> authorities` | Trusted identity source after verification | Apply permissions **scoped to the tenant** |
| JWT `iss` before signature verification | Can be forged | Use only as a lookup key against **allowlisted issuers**; verify token before trusting claims |

Never accept a JDBC URL, IdP hostname, JWK URL, database schema, or connection string directly from a request to construct an authentication store. Doing so can lead to wrong-tenant selection, SSRF, arbitrary database access, or privilege escalation.

## 2. Clearly Separate Three Questions: Routing, Authentication, Authorization

1. **Tenant routing:** Which namespace/organization is the request targeting, and does the server allow that namespace?
2. **Authentication:** Are the request's credentials valid **against the selected tenant's identity store**? Who is the verified identity?
3. **Authorization:** Does that identity have permission to perform the specific action on a **resource belonging to the same tenant**?

Never collapse those three questions into a single `if` statement reading `tenantId`, `role`, and `password` from JSON and returning HTTP 200.

General model example:

```text
Client request
  | path/host/issuer hint (untrusted)
  | credentials (unauthenticated)
  v
Canonical route + server-owned Tenant Registry
  | check whether slug is registered/ACTIVE
  | map slug -> provisioned manager/issuer/store
  | unknown tenant -> reject, no fallback to global store
  v
Designated authentication mechanism
  | HTTP Basic / session login / Bearer / API key ...
  v
Tenant-dedicated AuthenticationManager
  | ProviderManager -> matching AuthenticationProvider
  | -> tenant's UserDetailsService, password hash / decoder / IdP
  | -> check credentials, account flags, issuer, audience...
  v
Verified Authentication
  | principal bound to verified tenant
  | authorities issued by server-side source, not from request
  v
SecurityContextHolder
  v
Authorization + resource ownership checks
  | sufficient permissions and matching tenant -> 200
  | missing/invalid credentials -> 401
  | authenticated but missing permissions -> 403
  | cross-tenant resource -> deny
```

In Spring Security Servlet, `FilterChainProxy` chooses the **first matching `SecurityFilterChain`** based on request matchers and `@Order` precedence. The authentication mechanism inside the chain (for example `BasicAuthenticationFilter`) invokes `AuthenticationManager`; the provider verifies credentials and returns an authenticated `Authentication`; the result is placed in `SecurityContext` for downstream authorization rules to evaluate.

When there are only a few static namespaces, multiple `SecurityFilterChain`s with specific `securityMatcher`s are usually simple and easy to audit. When tenants change dynamically, you need a **provisioned registry** and a more tightly engineered resolver mechanism. Either way, the initial tenant selector must never be treated as proof of login.

### Security Invariants

- **Pick the right store before comparing passwords**; never iterate through all tenants trying the same credentials until one succeeds.
- **One tenant has no right to use another tenant's manager** merely because usernames collide.
- **Verified accounts must bind to the target tenant**; a user signed into north does not automatically gain access to south.
- **Permissions are scoped per tenant**: `ROLE_ANALYST` in north does not automatically mean `ROLE_ANALYST` in south.
- **Nonexistent or disabled tenants must fail closed**; no "default to a public/global manager" shortcut.
- **Business data must filter by tenant at the data access layer**; succeeding at authentication does not automatically guard every repository query.

## 3. Runnable Spring Boot Example with Two Independent Identity Stores

We build two `InMemoryUserDetailsManager` stores to observe isolation clearly. Both hold the same username `sam` with different passwords and roles. Two separate `DaoAuthenticationProvider`s are created; each verifies passwords with `BCryptPasswordEncoder` and reads only its own store.

**Tenant selection via server configuration:** The registry statically maps `north -> northManager` and `south -> southManager`. Two `SecurityFilterChain`s use server-registered paths; clients can pick a URL but cannot inject a third manager or grant themselves roles. Endpoints do not read `X-Tenant`, `X-Role`, or `X-Authenticated`.

### 3.1. Structure

```text
tenant-auth-demo/
├── pom.xml
├── src/main/java/com/example/tenants/TenantAuthApplication.java
└── src/test/java/com/example/tenants/TenantAuthApplicationTests.java
```

**`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>tenant-auth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/tenants/TenantAuthApplication.java`**:

```java
package com.example.tenants;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@SpringBootApplication
public class TenantAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantAuthApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean("northUsers")
    UserDetailsService northUsers(PasswordEncoder encoder) {
        UserDetails sam = User.withUsername("sam")
                .password(encoder.encode("north-pass123"))
                .roles("ANALYST")
                .build();
        return new InMemoryUserDetailsManager(sam);
    }

    @Bean("southUsers")
    UserDetailsService southUsers(PasswordEncoder encoder) {
        UserDetails sam = User.withUsername("sam")
                .password(encoder.encode("south-pass456"))
                .roles("VIEWER")
                .build();
        return new InMemoryUserDetailsManager(sam);
    }

    // Only trusted code/configuration may provision this registry.
    @Bean
    TenantAuthRegistry tenantAuthRegistry(
            @Qualifier("northUsers") UserDetailsService north,
            @Qualifier("southUsers") UserDetailsService south,
            PasswordEncoder encoder) {

        return new TenantAuthRegistry(Map.of(
                "north", managerFor(north, encoder),
                "south", managerFor(south, encoder)
        ));
    }

    private static AuthenticationManager managerFor(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    static final class TenantAuthRegistry {
        private final Map<String, AuthenticationManager> managers;

        TenantAuthRegistry(Map<String, AuthenticationManager> managers) {
            this.managers = Map.copyOf(managers);
        }

        AuthenticationManager requireRegistered(String tenant) {
            AuthenticationManager manager = managers.get(tenant);
            if (manager == null) {
                throw new IllegalArgumentException("Unregistered tenant");
            }
            return manager;
        }
    }

    // Routes are defined by the server; never use a JDBC URL from the client.
    @Bean
    @Order(1)
    SecurityFilterChain northChain(
            HttpSecurity http, TenantAuthRegistry registry) throws Exception {
        return tenantChain(http, "north", registry.requireRegistered("north"));
    }

    @Bean
    @Order(2)
    SecurityFilterChain southChain(
            HttpSecurity http, TenantAuthRegistry registry) throws Exception {
        return tenantChain(http, "south", registry.requireRegistered("south"));
    }

    private static SecurityFilterChain tenantChain(
            HttpSecurity http, String tenant, AuthenticationManager manager)
            throws Exception {

        String base = "/tenants/" + tenant;
        http
            .securityMatcher(base + "/**")
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(base + "/reports").hasRole("ANALYST")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    // Paths outside the two provisioned namespaces must be denied.
    @Bean
    @Order(3)
    SecurityFilterChain denyOtherPaths(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @RestController
    static class TenantController {
        record Profile(String tenant, String username, List<String> authorities) {}

        @GetMapping("/tenants/{tenant}/me")
        Profile me(@PathVariable String tenant, Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new Profile(tenant, authentication.getName(), authorities);
        }

        @GetMapping("/tenants/{tenant}/reports")
        String reports(@PathVariable String tenant) {
            return "reports:" + tenant;
        }
    }
}
```

### 3.2. Explaining Each Layer in the Code

1. `northUsers` and `southUsers` are **two independent user stores**, despite sharing the username `sam`. Each holds its own BCrypt hash and role. This is a demo; real stores can be separate databases, schemas, LDAPs, or IdPs.
2. `TenantAuthRegistry` is built from `Map.of(...)` **server-side**, holding only the two provisioned managers. `Map.copyOf` prevents external mutation. Requests cannot supply manager names, DB addresses, or JDBC sources.
3. `managerFor(...)` constructs a `DaoAuthenticationProvider` backed by the right tenant's `UserDetailsService`. `ProviderManager` calls that provider for `UsernamePasswordAuthenticationToken` coming from the Basic filter.
4. `northChain` with `securityMatcher("/tenants/north/**")` is selected first when the path matches; it uses the **north manager** fetched from the registry. Same for south. The two chains are ordered via `@Order(1)` and `@Order(2)`.
5. `HttpSecurity.authenticationManager(manager)` configures the **chain-specific** manager. `httpBasic()` uses it when `BasicAuthenticationFilter` receives a Basic header.
6. `hasRole("ANALYST")` checks the `ROLE_ANALYST` authority issued by the server store. The north user can access `/tenants/north/reports`; the south user only has `ROLE_VIEWER` and is still rejected after authenticating.
7. `SessionCreationPolicy.STATELESS` prevents the demo from storing logins in sessions. Basic credentials must be resent on every request. The demo routes use GET only; if adding state-changing operations via browsers, evaluate CSRF and automatic credential sending.
8. The final chain uses `denyAll` to close off unregistered paths instead of falling back to a global user store. It returns a 4xx status for unknown tenants; the exact code depends on this chain's entry point/exception handling.

**Ensuring the right namespace:** The controller receives `tenant` from the path, but only runs after the chain dedicated to that tenant has successfully authenticated the call. Because each chain's `securityMatcher` binds tightly to its path, a self-asserted `X-Tenant` cookie/header will not switch managers. This is still only **HTTP-layer protection**; real data-reading APIs must also bind tenants at query/service level as shown in section 6.

## 4. Running and Verifying Isolation Between Tenants

Run inside the folder containing `pom.xml`:

```bash
mvn spring-boot:run
```

Try the following cases with `curl`. The passwords here are for local demo only; use HTTPS for real credentials.

```bash
# 1. North: valid north password -> 200.
curl -i -u sam:north-pass123 http://localhost:8080/tenants/north/me

# 2. South: valid south password -> 200.
curl -i -u sam:south-pass456 http://localhost:8080/tenants/south/me

# 3. Send north credentials to south -> 401.
curl -i -u sam:north-pass123 http://localhost:8080/tenants/south/me

# 4. Send south credentials to north -> 401.
curl -i -u sam:south-pass456 http://localhost:8080/tenants/north/me

# 5. Spoofing tenant and role headers cannot escalate privileges on south -> 403.
curl -i -u sam:south-pass456 \
    -H 'X-Tenant: north' \
    -H 'X-Role: ROLE_ANALYST' \
    http://localhost:8080/tenants/south/reports

# 6. North has ROLE_ANALYST -> allowed to view north reports (200).
curl -i -u sam:north-pass123 http://localhost:8080/tenants/north/reports

# 7. Unknown tenant has no provisioned manager -> rejected (4xx).
curl -i -u sam:north-pass123 http://localhost:8080/tenants/unknown/me
```

Sample JSON for successful responses:

```json
{"tenant":"north","username":"sam","authorities":["ROLE_ANALYST"]}
```

```json
{"tenant":"south","username":"sam","authorities":["ROLE_VIEWER"]}
```

The controller returns JSON with fields ordered by the record. A 401 response may include `WWW-Authenticate: Basic ...`; error bodies vary by server. A 403 error does not mean a wrong password: the user authenticated inside that tenant yet lacks permission for the endpoint. `curl -i` displays status codes and headers for inspection.

### Why Are Scenarios (3) and (4) Important?

They prove **username alone** is not used to look up users globally. If the app used a single shared `UserDetailsService` and searched for `sam` across every tenant, request (3) could accidentally succeed with another tenant's credentials. In this example, south's manager sees only south's hash; north's password fails to match. Someone who belongs to both tenants must verify against **the exact tenant context being accessed**.

## 5. Automated Testing with Spring Security + MockMvc

Create `src/test/java/com/example/tenants/TenantAuthApplicationTests.java`:

```java
package com.example.tenants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantAuthApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void identicalUsernameIsVerifiedAgainstEachTenantStore() throws Exception {
        mvc.perform(get("/tenants/north/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("north"))
                .andExpect(jsonPath("$.username").value("sam"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_ANALYST"));

        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "south-pass456")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenant").value("south"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_VIEWER"));
    }

    @Test
    void credentialsCannotCrossTenantBoundaries() throws Exception {
        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/tenants/north/me")
                    .with(httpBasic("sam", "south-pass456")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void clientHeadersCannotOverrideStoreOrGrantRoles() throws Exception {
        mvc.perform(get("/tenants/south/reports")
                    .with(httpBasic("sam", "south-pass456"))
                    .header("X-Tenant", "north")
                    .header("X-Role", "ROLE_ANALYST")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/tenants/south/me")
                    .with(httpBasic("sam", "north-pass123"))
                    .header("X-Tenant", "north"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/tenants/north/reports")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().isOk())
                .andExpect(content().string("reports:north"));
    }

    @Test
    void unregisteredTenantNeverFallsBackToAnotherStore() throws Exception {
        mvc.perform(get("/tenants/unknown/me")
                    .with(httpBasic("sam", "north-pass123")))
                .andExpect(status().is4xxClientError());
    }
}
```

Run:

```bash
mvn test
```

The tests do more than compare outputs of a custom function: `MockMvc` runs through `FilterChainProxy`, `BasicAuthenticationFilter`, managers/providers, and real authorization rules. They verify two separate stores, non-cross-tenant credentials, spoofed headers failing to switch managers/roles, and rejection of unregistered tenants. Running tests on demo source code is different from modifying permissions or configurations in an existing production application.

## 6. Real-World Design: Registry, Multiple Mechanisms, and Business Data

### 6.1. Tenant Registry Must Remain Under Server Control

Production applications typically maintain a tenant configuration table populated by controlled onboarding/administration workflows. A record may include:

| Field | Meaning |
| --- | --- |
| `tenantId` | Canonical, unique identifier, not arbitrarily changed |
| `status` | Accept only `ACTIVE` tenants; suspended/deleted must be rejected |
| `allowedDomains` / route mapping | System-verified and provisioned domains/paths |
| `identityProviderType` | Approved password store, LDAP, OIDC/JWT issuer, or API key mechanism |
| `identityStoreRef` | Server-managed reference key to secret/config, never a request-supplied JDBC URL |
| `trustedIssuer`, `audience` | Valid issuer/audience list per tenant when using Bearer |
| `policyVersion` | Audited version of permission and authentication policy config |
| `enabledMechanisms` | Permitted mechanisms (Basic, session login, JWT...) per tenant |

When a request carries a tenant slug, the server canonicalizes the slug, queries the registry, checks status, and picks the provisioned manager/provider/decoder. **Never dynamically create managers for every arbitrary new tenant string encountered**. For dynamic onboarding, only authenticated, authorized administrative components may modify the registry; runtime code reads only trusted snapshots, caches under proper keys, and evicts cache entries when configs are revoked.

Never use `X-Database-Url` or `X-Issuer-Url` to open arbitrary connections or fetch JWKs. Doing so risks SSRF, store confusion, or trusting an attacker-chosen IdP.

### 6.2. `AuthenticationManagerResolver<HttpServletRequest>` Can Be Used

When there are many tenants or tenants use **different mechanisms**, you may need a resolver that picks a manager per request. Spring Security provides:

```java
public interface AuthenticationManagerResolver<C> {
    AuthenticationManager resolve(C context);
}
```

This is an **API excerpt to illustrate the concept**, not a standalone runnable file. For Servlet, `C` can be `HttpServletRequest`. The resolver should read a **canonicalized candidate tenant key**, look it up in a trusted registry, and return the registered manager; nonexistent tenants must fail safely.

Algorithm example (intentional pseudocode, **not complete Java**):

```text
resolve(request):
    candidate = canonicalRouteResolver.candidateTenant(request)
    config = trustedTenantRegistry.requireActive(candidate)
    manager = managedAuthManagers.require(config.tenantId)
    return manager  // never create a manager from an arbitrary client-supplied URL
```

Some setups like `oauth2ResourceServer(...).authenticationManagerResolver(...)` accept a resolver directly. For other filters, choose a filter/mechanism that supports it or write a compliant adapter; **merely declaring a resolver bean does not mean** every `httpBasic()` or `formLogin()` automatically uses it.

In the two-static-tenant demo, two `SecurityFilterChain`s with `http.authenticationManager(...)` are clear and sufficient. When moving to a runtime registry, do not keep stale managers for disabled tenants; manage lifecycle, invalidation, and configuration monitoring.

### 6.3. With JWT/OIDC: Select Issuer First, Then Verify Token

A JWT can contain `iss`, `sub`, `tenant`, and `roles`. Before verifying the signature and claims, these strings are **untrusted**. You can use the unverified `iss` as a **provisional lookup key** against a server-allowlisted issuer list, provided you:
1. Accept only issuers present in the registry/trusted-issuers set.
2. Pick the decoder/AuthenticationManager configured for that issuer.
3. Verify signature, allowed algorithm, `iss`, `aud`, `exp`/`nbf`, and required constraints.
4. Bind the verified tenant to the principal, confirm it matches the target resource, and map scopes/roles only after verification.
5. Reject unknown issuers, validly signed tokens with the wrong audience, or tokens from another tenant.

Spring Security includes `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` for multiple trusted issuers. For opaque tokens, configure introspection providers per tenant trust boundary; never infer an arbitrary introspection endpoint from a self-asserted header.

**Important:** a valid `issuer` does not grant a token permission to read another tenant's data; authorization still requires tenant/resource binding. When one issuer serves multiple tenants, verify the tenant claim and membership relationship against a server-confirmed policy.

### 6.4. With Sessions and Multiple Login Flows

If an application supports JSON login, form login, Basic, and Bearer concurrently, analyze:
- **Which mechanism handles this request?** Match by path/endpoint and Authorization scheme; avoid two filters processing against intent.
- **Which tenant is selected?** Base it on a registry-mapped route/host, or a verified claim at the right layer.
- **Which identity was verified?** Include tenant membership and valid issuer; never let a north session cookie implicitly enter south.
- **Is context persisted?** Session logins use `SecurityContextRepository` alongside session-fixation/CSRF protections; stateless Basic/JWT usually re-authenticates on each new request.

If choosing tenants by domain, `Host`, `Forwarded`, and `X-Forwarded-Host` can be spoofed by clients if reverse proxies fail to strip/overwrite them. Rely on hostnames only after a trusted proxy normalizes them and the server maps the hostname to a provisioned tenant. Do not mistake `getServerName()` for proof that the user belongs to the tenant.

### 6.5. Also Bind Data Queries by Tenant

Authentication isolation **is not enough** to protect data rows. If a request reaches `/tenants/north/invoices/42`, the backend must verify:
- The verified `Authentication` belongs to tenant north or holds a special cross-tenant permission granted by server policy.
- Invoice 42 actually belongs to north.
- The repository query includes the tenant key; never run a global `findById(42)` and return immediately.

Illustrative **service/repository snippet**, not a standalone application:

```java
Invoice invoice = invoiceRepository
        .findByTenantIdAndId(authenticatedTenantId, invoiceId)
        .orElseThrow(() -> new ResourceNotFoundException());

authorizationService.requireCanReadInvoice(authentication, invoice);
return invoice;
```

Class and repository method names here represent an application-specific domain design. In systems using row-level security, schema-per-tenant, or database-per-tenant, still set the tenant context in the right place and clear/reset it to avoid leaks across requests, threads, or connection pools.

### 6.6. Caches and Audits Must Also Carry Tenant Identity

Caching solely by `username` can mix up north's `sam` and south's `sam`; use keys like `(tenantId, userId, policyVersion)` where appropriate. Likewise, `UserDetails` caches, sessions, token verification caches, rate limits, and audit events must identify the right tenant while avoiding logging passwords, API keys, or Bearer tokens.

When a tenant is suspended, invalidate authentication paths and active sessions/tokens/cached permissions per policy. For dynamic configurations, audit who modified registries, secret references, issuers, or routes. Modifying tenant configuration requires admin permissions and dedicated authentication.

## 7. Common Security Pitfalls and How to Spot Them

| Design flaw | Why it is wrong | How to fix |
| --- | --- | --- |
| Picking database directly from `X-Database-Url` | Client dictates infrastructure, enabling SSRF or accessing other stores | Use a server-provisioned registry mapping tenant -> secret/config |
| Reading `X-Tenant` and trusting the user belongs there | Header can be spoofed by client | Treat as a hint, pick an allowed manager, **authenticate and verify membership** |
| Searching `username` across all tenants and taking first match | Username collisions mix up organizations | Select the right tenant store before authenticating |
| Global fallback `AuthenticationManager` for unknown tenants | Easy to bypass isolation | Unknown/disabled tenant: fail closed |
| Letting client send `roles`, `authenticated` | Privilege escalation from unverified input | Trust only authorities verified by trusted provider/issuer |
| Parsing JWT `iss` and trusting all claims | Payload is unverified | Allowlist issuer to pick verifier; verify signature, audience, expiry before granting permissions |
| Authenticated in north so allowed to read south | Authentication differs from authorization | Bind principal to tenant and enforce tenant/resource ownership |
| Caching `UserDetails` by username | Two tenants' `sam` accounts overwrite each other | Include tenant and policy metadata in cache key |
| Wrong ordering of security chains | Routes fall into an overly broad chain | Specific `@Order` first, fallback last, test every matcher |
| Protecting only filters while repository queries remain global | Can still read other organizations' data | Scope queries by tenant and enforce object-level authorization |
| Creating a new DataSource per request from input | Exhausts resources, uncontrolled connections | Pre-provisioned pools/managers with server-managed lifecycle and secrets |

### 401, 403, and 404 in a Multi-Tenant Environment

- **401 Unauthorized**: no valid credentials for the manager of the accessed tenant. HTTP Basic typically sends a `WWW-Authenticate` challenge.
- **403 Forbidden**: authenticated, but lacks permission for the tenant or requested operation; e.g., south user with `ROLE_VIEWER` hitting `/reports` which requires `ROLE_ANALYST`.
- **404 Not Found** or generic 4xx: may be used for unregistered or unowned tenants/resources under an information-disclosure-minimization policy. Do not assume one fixed response without knowing the specific entry point/handler. Above all, **never allow access and never fall back to another tenant**.

Do not rely on response status codes alone to prove tenant isolation. Test **A's credentials on B's route**, **same username in A/B**, **insufficient roles**, **nonexistent tenants**, **resources owned by B requested by A**, and **tokens with wrong issuer/audience** when using JWT.

## 8. Roadmap from Demo to Production

1. **Canonical tenant identifier:** choose a stable internal `tenantId`, distinct from display names/domains.
2. **Provisioned registry:** routes/domains/issuers/methods/store references must follow governance workflows, allowlists, ACTIVE status checks, and auditing.
3. **Bind identity:** construct principals holding the tenant and real ID, not just a username; verify tenant membership in the provider/IdP.
4. **Layer mechanisms:** configure chains/resolvers by endpoint group and credential scheme; verify no weak bypasses/fallbacks exist.
5. **Tenant authorization:** derive roles/scopes from server/verified claims, never raw requests; check both action permissions and object ownership.
6. **Maintain data isolation:** enforce per-tenant separation in datasources/schemas/row queries, connection lifecycles, caches, queues, and audits.
7. **Protect credentials:** HTTPS, password hashing, MFA where needed, rate limiting, monitoring, secret rotation, and token expiry.
8. **Adversarial testing:** cross-tenant credentials, spoofed tenant hints, unknown issuers, expired tokens, disabled accounts, wrong chain matches, and unknown tenants.

## 9. Self-Check Questions

1. Why does `tenant=north` in the URL not prove the client belongs to north, yet can still serve as a routing key?
2. How should identical usernames `sam` in north and south be represented internally?
3. Which `AuthenticationManager` and `AuthenticationProvider` verify the password when a request hits `/tenants/south/me`?
4. If north's password is sent to south, why must it return 401?
5. Why can't `X-Role: ROLE_ANALYST` let the south user enter `/tenants/south/reports`?
6. Why is `denyOtherPaths` needed at the end instead of a global fallback manager?
7. With a JWT whose `iss` is unverified, what is allowed before signature verification, and what is strictly forbidden?
8. Once logged into north, why can `findById(invoiceId)` still leak south's data?
9. Why is a cache key containing only the username usually insufficient in multi-tenancy?
10. If an application uses `Host` to select tenants, what must be controlled at the reverse proxy?

**Answer hints:** (1) the path is a client-controlled hint, while the trusted registry/mapping and provider verify membership; (2) `(tenantId, userId)`; (3) south's manager/DAO provider; (4) south's password hash does not match; (5) roles come from the server-side provider; (6) fail closed for unknown tenants; (7) use issuer as an allowlist key to select the verifier, never trust claims before verification; (8) missing tenant-bound query/ownership check; (9) username collisions across tenants; (10) normalize and strip spoofed forwarded headers, mapping hostnames strictly from server config.

## 10. Official References

- Spring Security — Multiple HttpSecurity / SecurityFilterChain: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — OAuth2 Resource Server Multi-tenancy / AuthenticationManagerResolver: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html
- Spring Security — HTTP Basic authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
