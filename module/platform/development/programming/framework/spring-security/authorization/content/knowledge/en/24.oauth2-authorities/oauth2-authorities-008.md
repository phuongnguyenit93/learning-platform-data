# Differences Between OAuth2 Login Authorities and Bearer Token Authorities in Spring Security

## 1. One user, two authentication paths, two authority sources

A Spring Boot system often serves both:
- **A web application signing in via OpenID Connect (OIDC)/OAuth2 Login**: the browser redirects to an Identity Provider (IdP), the app receives an authorization code, exchanges tokens, establishes a login session, and serves `/ui/**` routes.
- **A REST API receiving Bearer access tokens**: mobile apps, other servers, or SPAs call `/api/**` with `Authorization: Bearer ...`; Resource Server validates the token and builds an `Authentication` for that request.

Both paths produce an `Authentication` object and a set of `GrantedAuthority` instances for Spring Security to evaluate. Yet **the two `Authentication` objects differ in origin, purpose, and what information can be trusted**.

Example:

```text
BROWSER FLOW
Browser ── OAuth2 Authorization Code / OIDC ──> IdP
            <─ code ─ token ─
Spring OAuth2 Login
  -> OAuth2User / OidcUser
  -> OAuth2AuthenticationToken
  -> authorities from user / login access token / user mapping
  -> SecurityContext in browser session

BEARER FLOW
HTTP client ── Authorization: Bearer <access-token> ──> API
Spring OAuth2 Resource Server
  -> verify JWT or introspect opaque token
  -> JwtAuthenticationToken or BearerTokenAuthentication
  -> authorities from validated token/introspection + converter
  -> SecurityContext for API request
```

**Very easy pitfall:** OAuth2 Login **can also contain `SCOPE_*`**. Spring Security 6.5's documentation on `Mapping User Authorities` explains that `OAuth2User`/`OidcUser` authorities include scopes from the **access token received during Login**, prefixed with `SCOPE_`. In addition, special authorities like `OAUTH2_USER` or `OIDC_USER` appear. In Resource Server, `SCOPE_*` typically comes from `scope`/`scp` inside the **current Bearer access token**, or from `scope` in an introspection response.

So the distinction is not "Login has only ROLE, Bearer has only SCOPE." Rather:

> **An authority is the output of a specific authentication and mapping pipeline. Identical authority names do not guarantee the same identity, audience, business permissions, or level of trust.**

### Objectives

After this lesson, you can:
1. Distinguish `OAuth2AuthenticationToken`, `JwtAuthenticationToken`, and `BearerTokenAuthentication`.
2. Understand `OAUTH2_USER`, `OIDC_USER`, `SCOPE_reports.read`, `ROLE_ADMIN`, and internal authorities like `APP_REPORT_READ`.
3. Explain why an access token issued to an **OAuth2 client** during Login does not automatically become an API Bearer token sent by another client to a Resource Server.
4. Customize Login via `GrantedAuthoritiesMapper` or `OAuth2UserService`/`OidcUserService`.
5. Customize JWT Bearer via `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter`; know that opaque Bearer uses `OpaqueTokenIntrospector`.
6. Protect domain services when both browser sessions and Bearer tokens exist, preventing one authority string from being misused across both mechanisms.
7. Write integration tests with `MockMvc`, `oauth2Login()`, mocked `JwtDecoder`, and JUnit/Mockito; distinguish converter tests from real IdP/token signature verification.

## 2. What does OAuth2 Login do?

In a server-side web app with `oauth2Login()`:

1. The browser starts sign-in at `/oauth2/authorization/{registrationId}`.
2. Spring Security builds an authorization request with state and redirects to the IdP.
3. After the user consents/authenticates, the IdP redirects to the callback (typically `/login/oauth2/code/{registrationId}`) with an authorization code.
4. Spring Security exchanges the code for tokens, calls OIDC/UserInfo when needed, and constructs an `OAuth2User` or `OidcUser`.
5. Spring Security builds an `OAuth2AuthenticationToken` holding the principal, authorities, and `authorizedClientRegistrationId`.
6. The result is typically stored in the `SecurityContext` bound to the **HTTP session** for subsequent browser requests.

This is **user sign-in into a client application**. It does not turn the app into a Resource Server merely because the IdP issued an OAuth2 access token to the client.

### 2.1. Default authorities you may encounter

| Source | Example authority | Explanation |
|---|---|---|
| OAuth2 Login, OAuth2User | `OAUTH2_USER` | Authority identifying the principal as `OAuth2User` |
| OAuth2 Login, OIDC | `OIDC_USER` | Authority identifying the principal as `OidcUser` |
| OAuth2 Login access token scopes | `SCOPE_openid`, `SCOPE_profile`, or other granted scopes | Represents the scopes of the client's access token from Login |
| OAuth2 Login custom mapping | `APP_REPORT_READ`, `ROLE_EMPLOYEE` | Present only if the team configures mapping from a trusted source |
| OAuth2 Resource Server JWT | `SCOPE_reports.read` | Reads JWT `scope` or `scp` by default after token validation |
| OAuth2 Resource Server opaque | `SCOPE_reports.read` | Reads `scope` from introspection response |
| Resource Server custom converter | `ROLE_SUPPORT`, `PERM_report:approve` | Produced by custom-configured converter/introspector |

**Do not mistake `OIDC_USER` for admin privileges.** It merely indicates the user/principal class, not permission to read private documents or access admin APIs.

**Do not mistake `SCOPE_openid` for `ROLE_USER`.** `openid` is a scope for OpenID Connect authentication, not a business role granting access to all data.

**Never infer `ROLE_ADMIN` from an email domain.** Only grant permissions from reliably configured IdP claims, verified memberships, or an authoritative internal authorization store.

### 2.2. How do `OAuth2User` and `OidcUser` differ?

`OAuth2User` is the OAuth 2.0 login principal with attributes (typically from UserInfo or a provider API); `OidcUser` extends it with an ID token and OIDC claims.

- `OAuth2UserAuthority` holds attributes from OAuth2 UserInfo; typical authority string is `OAUTH2_USER`.
- `OidcUserAuthority` holds `OidcIdToken` and `OidcUserInfo`; typical authority string is `OIDC_USER`.
- Spring Security can add `SCOPE_*` from access token scopes accompanying OAuth2 Login.
- Claims/groups can be mapped to internal `GrantedAuthority` instances via `GrantedAuthoritiesMapper`.
- If a provider API or external role lookup is needed, `OAuth2UserService`/`OidcUserService` handles requests, tokens, and attributes more flexibly than a mapper receiving only authorities.

**Key rule:** an ID token conveys user authentication info to the OIDC Client—it is **not** an API access token. Never send an ID token as a Bearer access token to a Resource Server just because both are JWTs.

## 3. How does Resource Server handle Bearer tokens?

A request:

```http
GET /api/reports/101 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

is not OAuth2 Login. It is a Resource Server **access token authentication** request:

- **JWT Bearer**: `BearerTokenAuthenticationFilter` extracts the token, `JwtDecoder` verifies the signature and required claims; `JwtAuthenticationConverter` builds `JwtAuthenticationToken` with authorities.
- **Opaque Bearer**: Resource Server introspects the token with the Authorization Server; if `active=true` and the request is valid, it typically builds `BearerTokenAuthentication` with `OAuth2AuthenticatedPrincipal` and authorities from introspection.

For a JWT access token:

```json
{
  "iss": "https://idp.example.invalid",
  "sub": "alice",
  "aud": ["report-api"],
  "scope": "reports.read reports.approve",
  "exp": 1893456000
}
```

In a typical Spring Security 6.5 configuration, generated authorities are:

```text
SCOPE_reports.read
SCOPE_reports.approve
```

Another token using an array claim:

```json
{
  "sub": "alice",
  "scp": ["reports.read", "reports.approve"]
}
```

The default `JwtGrantedAuthoritiesConverter` reads scopes from `scope` or `scp` and adds the `SCOPE_` prefix. However, **not every JWT from every IdP uses standard scope claims**; many providers use `roles`, `groups`, `realm_access`, or a custom JSON object. Configure a converter explicitly instead of guessing claim names.

### 3.1. Three mandatory layers before trusting `SCOPE_`

1. **Valid token**: signature, issuer `iss`, lifetime `exp`/`nbf`, key algorithm, and revocation policy are configured and verified.
2. **Right audience**: `aud` must include this exact API/resource server. A token issued for API B must not be accepted at API A. Spring Boot supports `spring.security.oauth2.resourceserver.jwt.audiences`.
3. **Scope/action/object**: `SCOPE_reports.read` authorizes a **defined report action**, not every tenant or every report ID.

If audience or issuer is wrong, **never construct an "authenticated" `Authentication` simply because the JWT has a readable payload**. Base64-decoding a JWT is not token validation.

### 3.2. Opaque tokens are not JWTs

An opaque Bearer token can be an unreadable string; Resource Server queries the introspection endpoint. Spring Security maps `scope` from introspection to `SCOPE_*` by default, but the principal/token type is typically `BearerTokenAuthentication`, not `JwtAuthenticationToken`.

If a policy bean writes `authentication instanceof JwtAuthenticationToken` to allow JWTs, **an opaque Bearer token will be denied** unless a matching branch is added. That is an intentional policy choice; never accidentally treat every Bearer token as a JWT.

## 4. Step-by-step authority comparison

| Aspect | OAuth2 Login | JWT Bearer | Opaque Bearer |
|---|---|---|---|
| HTTP authentication | Authorization Code + browser login | Authorization: Bearer access JWT | Authorization: Bearer opaque |
| Principal | `OAuth2User` or `OidcUser` | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Typical Authentication | `OAuth2AuthenticationToken` | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| SecurityContext | Usually in server session | Usually request-scoped/stateless | Usually request-scoped/stateless |
| Characteristic default authority | `OAUTH2_USER` / `OIDC_USER` | `SCOPE_*` from `scope`/`scp` | `SCOPE_*` from introspection |
| Can it contain `SCOPE_`? | **Yes**, from login access token | **Yes**, from Bearer JWT | **Yes**, from introspection |
| Mapping hook | `GrantedAuthoritiesMapper`, `OAuth2UserService`/`OidcUserService` | `JwtAuthenticationConverter` | `OpaqueTokenIntrospector` / custom token authentication converter |
| Is token verified directly per request? | Browser usually uses session after login; token handled during login flow | JWT sent on that request | Opaque token sent on that request |
| Business role | Requires explicit mapping/lookup | Can map from trusted claims | Can map from trusted introspection |
| Cross-tenant leak defense | Requires server membership/object guard | Requires server membership/object guard | Requires server membership/object guard |
| When token is old/revoked | Session authorities can be stale | JWT can remain valid until `exp` per revocation policy | Introspection can reflect active state, subject to caching/AS |
| Requires OIDC ID token? | When choosing OIDC Login | **No**; API needs access token | **No** |

A login session and a Bearer request **can hold the exact same `SCOPE_reports.read` string**, yet that string alone does not tell you which token carried it, what its audience was, or which business policy granted it.

## 5. How does Spring Security check authority strings?

Spring Security treats `GrantedAuthority.getAuthority()` as a plain string without tagging whether it "came from Login" or "came from Bearer." For example:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report read(...) { ... }
```

checks the string `SCOPE_reports.read` on the current `Authentication`. If Login also carries that string, the expression **will pass** for a user in a browser session. That is consistent with the API, yet **can violate security policy** if developers intended the scope to come strictly from a **Bearer access token issued for `report-api`**.

### 5.1. `hasRole` vs. `hasAuthority`

```java
hasAuthority("SCOPE_reports.read")
hasAuthority("APP_REPORT_READ")
hasRole("REPORT_ADMIN")
```

Three different checks:
- `hasAuthority("SCOPE_reports.read")` matches the exact string.
- `hasAuthority("APP_REPORT_READ")` matches the exact internal permission.
- `hasRole("REPORT_ADMIN")` checks `ROLE_REPORT_ADMIN` under the default prefix.

Do not use `hasRole("SCOPE_reports.read")` to check a scope; it looks for `ROLE_SCOPE_reports.read`. Conversely, `SCOPE_reports.read` never becomes `ROLE_ADMIN` without custom mapping.

### 5.2. Never auto-map OAuth scopes into admin roles

A risky configuration pattern:

```java
// ANTI-PATTERN: turns any "admin" token scope into application admin.
jwtAuthorities.setAuthorityPrefix("ROLE_");
```

Changing the prefix from `SCOPE_` to `ROLE_` **only renames the string**; it does not prove a trusted provider granted the scope for the right action or audience. If an app confuses scopes and roles across multiple clients, this grants overly broad permissions.

If custom authorities from JWTs are needed, validate the token, pin trusted issuer/audience, allow-list values, and add roles with distinct prefixes/namespaces; never map whole unverified claims into `ROLE_ADMIN`.

### 5.3. User permissions vs. application permissions

An OAuth2 access token can represent:
- **End-user delegated access**: a user consented or the IdP delegated permissions to a client.
- A **client credentials token**: a workload/application granted permissions **without an interactive user**.

Never infer from `sub` or `SCOPE_*` that a human user is actively operating in a browser. If a workflow requires user presence, check an appropriate claim/grant type/assurance level and apply principal-type policies. If a workload needs system rights, assign a dedicated service identity rather than impersonating a user.

## 6. Two distinct mapping hooks: picking the right extension point

### 6.1. OAuth2 Login: `GrantedAuthoritiesMapper`

`GrantedAuthoritiesMapper` receives the authorities collected during Login and returns a new collection. This fits when:
- `OidcUserAuthority` or `OAuth2UserAuthority` already carries sufficient claims/attributes to map.
- No external API calls are needed.
- You want to map internal application roles independently of technical scopes.

Example granting `APP_REPORT_READ` only when an **OIDC ID token from an allow-listed issuer** carries a reliably configured app claim:

```java
@Bean
GrantedAuthoritiesMapper loginAuthoritiesMapper() {
    return authorities -> {
        Set<GrantedAuthority> result = new HashSet<>(authorities);
        for (GrantedAuthority a : authorities) {
            if (a instanceof OidcUserAuthority oidc) {
                var claims = oidc.getIdToken().getClaims();
                if ("https://idp.example.invalid".equals(
                        claims.get("iss"))
                    && "viewer".equals(claims.get("report_access"))) {
                    result.add(new SimpleGrantedAuthority(
                        "APP_REPORT_READ"));
                }
            }
        }
        return result;
    };
}
```

This snippet is wired into the demo in Section 8. The `report_access` claim is an **organization-defined convention example**, not a standard OAuth2/OIDC claim. Only trust such a claim if the IdP is configured to emit it from a trusted role source (and the ID token was validated); never trust user-editable profile UI data.

In production, also bind **registration/client**, tenant, trusted issuer, and policy version. Checking the `iss` string inside the mapper **does not replace** ID token validation by the OIDC login stack. If conditions are not met → do not grant `APP_REPORT_READ`.

### 6.2. OAuth2 Login: Delegating `OAuth2UserService`/`OidcUserService`

If permissions live in another IdP API, an internal role service, or project memberships, `GrantedAuthoritiesMapper` may fall short because it sees only authorities. Use `OAuth2UserService<OAuth2UserRequest, OAuth2User>` or `OAuth2UserService<OidcUserRequest, OidcUser>`, delegate to the default service, then **look up trusted roles** using the immutable issuer/subject and appropriate access token.

Sample flow:

```text
OAuth2 Login complete
  -> DefaultOidcUserService load user + ID token/UserInfo
  -> Membership service lookup using trusted (issuer, sub)
  -> Verified application role(s)
  -> return OidcUser with mapped authorities
  -> OAuth2AuthenticationToken in session
```

Never map `email_verified=true` to global admin; emails can change and domains can span multiple organizations. Any network lookup needs timeouts, bounded retries, caching/revocation policies, and **fail-closed** handling if permissions cannot be verified.

### 6.3. JWT Bearer: `JwtGrantedAuthoritiesConverter`

JWT Bearer does not pass through OAuth2 Login's `GrantedAuthoritiesMapper`. Use the resource server converter:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();
// Default: scope or scp -> SCOPE_<scope>

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopes);
```

If a provider uses a custom claim:

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();
custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
```

Illustrative sample: if `permissions` contains `report:read`, the converter emits `PERM_report:read`. Verify schema, delimiter, and claim provenance. To keep both `scope` and `permissions`, **combine** two converters deliberately; merely changing the claim name drops default scope authorities.

### 6.4. Opaque Bearer: `OpaqueTokenIntrospector`

For opaque tokens, `JwtAuthenticationConverter` is **not invoked**. Configure `oauth2ResourceServer(o -> o.opaqueToken(...))` with an introspector; a custom `OpaqueTokenIntrospector` can extract claims, scopes, and verified metadata from the response to construct `OAuth2AuthenticatedPrincipal` with authorities. Never decode opaque tokens as JWTs or trust scopes taken from raw headers.

## 7. Two-security-chain architecture: keeping sessions and API Bearer separate

An application serving:
- `/ui/reports/**`: browser session, OAuth2 Login, app roles `APP_REPORT_READ`/`APP_REPORT_APPROVE`.
- `/api/reports/**`: stateless Bearer JWT, scopes `SCOPE_reports.read`/`SCOPE_reports.approve`.

Each group must have **explicit authentication mechanisms and authority requirements**, never treating an OAuth Login session as a Bearer API credential.

```text
Request
   |
   +-- path /api/** ?
   |     |
   |     +-- @Order(1) API SecurityFilterChain
   |            - OAuth2 Resource Server JWT
   |            - stateless
   |            - require SCOPE_reports.read / approve
   |            - anyRequest denyAll
   |
   +-- otherwise @Order(2) browser SecurityFilterChain
         - OAuth2 Login, HttpSession
         - require APP_REPORT_READ / APPROVE
         - CSRF for mutations
         - other paths denyAll
```

**Order matters:** Spring Security selects the **first matching chain**, not the intersection of all chains. `anyRequest().denyAll()` in the API chain protects only requests entering the API chain; the browser fallback must cover everything else.

For APIs using only Bearer headers (no cookie auth) and no browser-automatic credentials, CSRF may be disabled **only on the API chain** after threat modeling. The browser chain still needs CSRF for POST/PUT/DELETE.

### 7.1. Service-level policies should still check the `Authentication` type

Because `hasAuthority(...)` checks only a string, critical applications should distinguish **authentication mechanisms** at the domain boundary if the same service is reachable from both paths:

```java
if (authentication instanceof OAuth2AuthenticationToken) {
    return has(authentication, "APP_REPORT_READ");
}
if (authentication instanceof JwtAuthenticationToken) {
    return has(authentication, "SCOPE_reports.read");
}
return false; // Unknown authentication kind: deny.
```

This is a logic sketch; the full project uses `ReportPolicy`, adding tenant membership and canonical resource lookup.

This helps if a scheduler, message consumer, or another chain inadvertently calls the same service. **Do not rely solely on authority names to grant access across every `Authentication` type.**

## 8. Java 17 / Spring Boot 3.5.6 project demonstrating both authority pipelines

This example runs a Servlet/MVC Spring Boot app with:
1. Two `SecurityFilterChain` beans and `@Order`.
2. `oauth2Login()` with an OIDC `GrantedAuthoritiesMapper`.
3. `oauth2ResourceServer().jwt()` using `JwtAuthenticationConverter`.
4. `ReportPolicy` accepting **`OAuth2AuthenticationToken` + `APP_*`** or **`JwtAuthenticationToken` + `SCOPE_*`**, rejecting opaque tokens, Basic, or anonymous calls.
5. An in-memory repository holding canonical tenants and memberships.
6. `MockMvc` tests simulating OAuth Login and Bearer claims (without needing a real IdP).

**Important about the environment:** `idp.example.invalid` is an illustrative domain with no real IdP. The project compiles and integration tests verify authorization via mocks; **real OAuth2 redirect logins and real JWT signature verification require your deployment environment's IdP/JWKS/credentials**. Do not mistake the unit tests below for real cryptographic trust verification.

### 8.1. File tree

```text
oauth2-authorities-demo/
  pom.xml
  src/main/resources/application.yml
  src/main/java/com/example/authorities/
    AuthoritiesApplication.java
    SecurityConfiguration.java
    Report.java
    ReportCatalog.java
    ReportPolicy.java
    ReportService.java
    ReportController.java
  src/test/java/com/example/authorities/
    AuthoritiesIntegrationTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>oauth2-authorities-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-oauth2-client` and `spring-boot-starter-oauth2-resource-server` are **two distinct capabilities**. The second provides resource server/JWT validation; login capability is not automatically included with JWT resource server alone.

### 8.3. `application.yml`

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            client-id: example-web-client
            client-secret: development-only-not-real
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
            provider: demo
        provider:
          demo:
            authorization-uri: https://idp.example.invalid/authorize
            token-uri: https://idp.example.invalid/token
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
            jwk-set-uri: https://idp.example.invalid/jwks
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid
          jwk-set-uri: https://idp.example.invalid/jwks
          audiences: report-api
```

These URIs are **configuration scaffolding so the app starts and runs local tests**, not a live service. When connecting a real IdP:
- Register a real OAuth2 Client and redirect URI; protect the client secret via a secret manager or environment variable.
- Verify OIDC ID token issuer, signature, and client audience; provider metadata must match deployment.
- Configure `issuer-uri`, `jwk-set-uri`, and `audiences` for **access tokens meant for `report-api`**; never use an ID token as a Bearer API token.
- Never let browsers/HTTP callers choose `issuer-uri` or `audiences`.
- For multiple issuers, use a reviewed `AuthenticationManagerResolver` or multi-tenant strategy; map `(issuer, subject)` to a stable internal user ID.

### 8.4. Main class

**`src/main/java/com/example/authorities/AuthoritiesApplication.java`**

```java
package com.example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesApplication.class, args);
    }
}
```

### 8.5. `SecurityConfiguration`

**`src/main/java/com/example/authorities/SecurityConfiguration.java`**

```java
package com.example.authorities;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/{id}")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/reports/{id}/approve")
                    .hasAuthority("SCOPE_reports.approve")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // This API authenticates solely via Bearer headers, not cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtConverter)))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http,
            GrantedAuthoritiesMapper loginMapper) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/",
                    "/login/**", "/oauth2/**", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/ui/reports/{id}")
                    .hasAuthority("APP_REPORT_READ")
                .requestMatchers(HttpMethod.POST,
                    "/ui/reports/{id}/approve")
                    .hasAuthority("APP_REPORT_APPROVE")
                .anyRequest().denyAll()
            )
            .oauth2Login(oauth -> oauth.userInfoEndpoint(
                userInfo -> userInfo.userAuthoritiesMapper(loginMapper)))
            .build();
    }

    @Bean
    GrantedAuthoritiesMapper loginAuthoritiesMapper() {
        return authorities -> {
            Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(authorities);

            for (GrantedAuthority authority : authorities) {
                if (authority instanceof OidcUserAuthority oidc) {
                    var claims = oidc.getIdToken().getClaims();
                    boolean trustedIssuer =
                        "https://idp.example.invalid".equals(
                            claims.get("iss"));
                    if (!trustedIssuer) {
                        continue;
                    }
                    String role = String.valueOf(
                        claims.get("report_access"));
                    if ("viewer".equals(role)) {
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                    }
                    if ("approver".equals(role)) {
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_APPROVE"));
                    }
                }
            }
            return mapped;
        };
    }

    @Bean
    JwtAuthenticationConverter jwtConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();
        // Default scope/scp -> SCOPE_*, never automatically becomes ROLE_*.
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
```

**Analysis:**
1. `@Order(1)` API chain matches only `/api/**`, requiring Bearer JWTs and `reports.read`/`reports.approve` scopes. Requests not matching those API operations are denied.
2. `@Order(2)` browser chain is a catch-all for the rest, allowing login/callback URLs and the specified UI GET/POST routes. `oauth2Login` creates a session when the real flow succeeds.
3. Only the API chain disables CSRF because the example API accepts **Bearer headers only**, without browser cookies. The browser chain **retains default CSRF**. Re-evaluate if authentication transport changes.
4. `GrantedAuthoritiesMapper` maps only OIDC ID tokens from an allow-listed issuer with a trusted `report_access` claim. It preserves existing authorities (like `OIDC_USER`, `SCOPE_openid`), **never treating those as report permissions**.
5. `JwtAuthenticationConverter` continues using default `scope`/`scp` → `SCOPE_*`; it never maps Login ID token roles. The API requires the configured audience in `application.yml`.
6. The example mapper **does not assign roles for non-OIDC OAuth2 Logins lacking an ID token**: those providers need another trusted user/group service.
7. Any unapproved path in either chain is denied, including admin paths.
8. The `report_access` claim is a **private convention** of this lesson, not built-in Spring Security or OIDC behavior.

### 8.6. `Report` and `ReportCatalog` — tenant is server-side data

**`src/main/java/com/example/authorities/Report.java`**

```java
package com.example.authorities;

public record Report(
    Long id, String tenant, String owner,
    String title, boolean approved) {}
```

**`src/main/java/com/example/authorities/ReportCatalog.java`**

```java
package com.example.authorities;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class ReportCatalog {
    private final ConcurrentMap<Long, Report> reports =
        new ConcurrentHashMap<>();

    // Demo single trusted IdP: users mapped by sub.
    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob"),
        "t2", Set.of("carol")
    );

    private final AtomicInteger approvals = new AtomicInteger();

    public ReportCatalog() {
        reset();
    }

    public synchronized void reset() {
        reports.clear();
        reports.put(101L, new Report(
            101L, "t1", "alice", "Revenue", false));
        reports.put(102L, new Report(
            102L, "t1", "bob", "Costs", false));
        reports.put(201L, new Report(
            201L, "t2", "carol", "South division", false));
        approvals.set(0);
    }

    public Report find(Long id) {
        return id == null ? null : reports.get(id);
    }

    public boolean isMember(String tenant, String principal) {
        Set<String> inTenant = members.get(tenant);
        return inTenant != null && principal != null
            && inTenant.contains(principal);
    }

    public synchronized Report approve(Long id) {
        Report old = find(id);
        if (old == null) return null;
        Report updated = new Report(
            old.id(), old.tenant(), old.owner(),
            old.title(), true);
        reports.put(id, updated);
        approvals.incrementAndGet();
        return updated;
    }

    public int approvals() {
        return approvals.get();
    }
}
```

In-memory data is a test fixture, not a database. Production needs an authoritative tenant membership store, `issuer+sub` subject mapping, and `UPDATE ... WHERE tenant_id=? AND ...` DML. Never use body-supplied tenant/owner fields to grant permissions.

### 8.7. `ReportPolicy` — distinguishing authentication mechanisms in domain services

**`src/main/java/com/example/authorities/ReportPolicy.java`**

```java
package com.example.authorities;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {
    private final ReportCatalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public ReportPolicy(ReportCatalog catalog) {
        this.catalog = catalog;
    }

    private static boolean has(Authentication auth, String value) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (value.equals(a.getAuthority())) return true;
        }
        return false;
    }

    private boolean trustedMember(Authentication auth, Long reportId) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }
        Report report = catalog.find(reportId);
        return report != null
            && catalog.isMember(report.tenant(), auth.getName());
    }

    public boolean canRead(Authentication auth, Long reportId) {
        if (!trustedMember(auth, reportId)) return false;

        if (auth instanceof OAuth2AuthenticationToken) {
            return has(auth, "APP_REPORT_READ");
        }
        if (auth instanceof JwtAuthenticationToken) {
            return has(auth, "SCOPE_reports.read");
        }
        return false; // Basic, anonymous, opaque, unknown => deny.
    }

    public boolean canApprove(Authentication auth, Long reportId) {
        if (!trustedMember(auth, reportId)) return false;

        if (auth instanceof OAuth2AuthenticationToken) {
            return has(auth, "APP_REPORT_APPROVE");
        }
        if (auth instanceof JwtAuthenticationToken) {
            return has(auth, "SCOPE_reports.approve");
        }
        return false;
    }
}
```

Why branch the policy by `Authentication` type?
- A Login principal that happens to carry `SCOPE_reports.read` from the login client's access token **is not treated as a Bearer access token for `report-api`**.
- A JWT carrying `APP_REPORT_READ` from a different claim mapping also **cannot** enter the browser branch.
- An opaque Bearer token will not enter the JWT branch until the system deliberately approves and implements a controlled `BearerTokenAuthentication` branch.
- Tenant membership is verified **before** evaluating authorities; the demo's usernames/subs come from a single IdP. Production must use an internal ID mapped from `issuer+sub`, not display names or emails.

**Limitation:** checking the runtime type is a defense-in-depth layer in the demo, not a replacement for token validation, issuer/audience checks, session policy, or route isolation via `SecurityFilterChain`.

### 8.8. Service and Controller

**`src/main/java/com/example/authorities/ReportService.java`**

```java
package com.example.authorities;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportCatalog catalog;

    public ReportService(ReportCatalog catalog) {
        this.catalog = catalog;
    }

    @PreAuthorize(
        "@reportPolicy.canRead(authentication, #id)"
    )
    public Report read(@P("id") Long id) {
        return catalog.find(id);
    }

    @PreAuthorize(
        "@reportPolicy.canApprove(authentication, #id)"
    )
    public Report approve(@P("id") Long id) {
        Report changed = catalog.approve(id);
        if (changed == null) {
            throw new AccessDeniedException("Resource changed");
        }
        return changed;
    }
}
```

**`src/main/java/com/example/authorities/ReportController.java`**

```java
package com.example.authorities;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/ui/reports/{id}")
    public Report browserRead(@PathVariable("id") Long id) {
        return service.read(id);
    }

    @PostMapping("/ui/reports/{id}/approve")
    public Report browserApprove(@PathVariable("id") Long id) {
        return service.approve(id);
    }

    @GetMapping("/api/reports/{id}")
    public Report apiRead(@PathVariable("id") Long id) {
        return service.read(id);
    }

    @PostMapping("/api/reports/{id}/approve")
    public Report apiApprove(@PathVariable("id") Long id) {
        return service.approve(id);
    }
}
```

`@EnableMethodSecurity` ensures `@PreAuthorize` executes when the controller invokes the Spring-managed service proxy. Even if called from another job or bean, a disallowed `Authentication` type or missing membership is still denied by the service.

Never use `@PostAuthorize` as the sole gate for `approve` because the side effect runs before the post-check. In production, use guarded DML and transactions/optimistic locking.

## 9. Integration tests: MockMvc distinguishing Login and Bearer

To avoid requiring a live IdP, we:
- Use the `oauth2Login()` test post-processor to create an `OAuth2AuthenticationToken` with test-controlled attributes and authorities.
- Use `@MockitoBean JwtDecoder` and a **real Bearer header in MockMvc** to exercise the Resource Server filter and `JwtAuthenticationConverter`. The mock decoder returns pre-built `Jwt` claims; signatures are not actually verified.
- Test `GrantedAuthoritiesMapper` directly to verify validated OIDC claims map properly; the `oauth2Login()` test post-processor **does not run the mapper like a real login callback**.
- Test denied permissions on both UI and API, not just happy paths.

**`src/test/java/com/example/authorities/AuthoritiesIntegrationTest.java`**

```java
package com.example.authorities;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritiesIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ReportCatalog catalog;
    @Autowired GrantedAuthoritiesMapper loginMapper;
    @Autowired JwtAuthenticationConverter jwtConverter;

    @MockitoBean JwtDecoder jwtDecoder;

    private static Jwt jwt(String token, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("iss", "https://idp.example.invalid")
            .claim("aud", List.of("report-api"))
            .claim("scope", scope)
            .issuedAt(now)
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    private static Jwt jwtWithScp(String token) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("iss", "https://idp.example.invalid")
            .claim("aud", List.of("report-api"))
            .claim("scp", List.of("reports.read"))
            .issuedAt(now)
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    private static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.OAuth2LoginRequestPostProcessor
    login(String... authorities) {
        var granted = java.util.Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toArray(GrantedAuthority[]::new);
        return oauth2Login()
            .attributes(attrs -> attrs.put("sub", "alice"))
            .authorities(granted);
    }

    private static org.springframework.test.web.servlet.request.RequestPostProcessor
    bearer(String token) {
        return request -> {
            request.addHeader(
                HttpHeaders.AUTHORIZATION, "Bearer " + token);
            return request;
        };
    }

    @BeforeEach
    void setup() {
        catalog.reset();

        when(jwtDecoder.decode("api-read"))
            .thenReturn(jwt("api-read", "reports.read"));
        when(jwtDecoder.decode("api-approve"))
            .thenReturn(jwt("api-approve", "reports.approve"));
        when(jwtDecoder.decode("api-both"))
            .thenReturn(jwt("api-both",
                "reports.read reports.approve"));
        when(jwtDecoder.decode("api-oidc-scopes"))
            .thenReturn(jwt("api-oidc-scopes",
                "openid profile"));
        when(jwtDecoder.decode("api-scp"))
            .thenReturn(jwtWithScp("api-scp"));
        when(jwtDecoder.decode("api-invalid"))
            .thenThrow(new BadJwtException("Invalid token"));
    }

    private static boolean has(
            java.util.Collection<? extends GrantedAuthority> values,
            String expected) {
        return values.stream()
            .anyMatch(a -> expected.equals(a.getAuthority()));
    }

    @Test
    void loginWithMappedAppReadCanReadUi() throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("APP_REPORT_READ")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revenue"));
    }

    @Test
    void loginWithoutAppPermissionCannotReadUi() throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("OIDC_USER", "SCOPE_openid")))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginScopeAloneDoesNotReplaceAppReadRole()
            throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("SCOPE_reports.read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void browserAppRoleCannotApproveWithoutApproveRole()
            throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login("APP_REPORT_READ"))
                .with(csrf()))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void browserApproverCanApproveWithCsrf() throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login(
                    "APP_REPORT_READ", "APP_REPORT_APPROVE"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.approved").value(true));
        assertEquals(1, catalog.approvals());
    }

    @Test
    void browserApproverWithoutCsrfIsDenied() throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login(
                    "APP_REPORT_READ", "APP_REPORT_APPROVE")))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void browserUserCannotReadOtherTenant() throws Exception {
        mvc.perform(get("/ui/reports/201")
                .with(login("APP_REPORT_READ")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiWithReadScopeCanRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-read")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void apiWithScpArrayCanRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-scp")))
            .andExpect(status().isOk());
    }

    @Test
    void apiWithOnlyApproveScopeCannotRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-approve")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiOpenidScopesDoNotGrantReportAccess()
            throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-oidc-scopes")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiReadScopeDoesNotGrantApprove() throws Exception {
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-read")))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void apiApproveScopeCanApproveWithoutBrowserCsrf()
            throws Exception {
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-approve")))
            .andExpect(status().isOk());
        assertEquals(1, catalog.approvals());
    }

    @Test
    void apiBothScopesCanReadAndApprove() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-both")))
            .andExpect(status().isOk());
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-both")))
            .andExpect(status().isOk());
    }

    @Test
    void apiMissingBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-invalid")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiCannotReadOtherTenantWithValidScope()
            throws Exception {
        mvc.perform(get("/api/reports/201")
                .with(bearer("api-read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void pathNameAdminDoesNotGrantUnlistedRoute()
            throws Exception {
        mvc.perform(get("/api/admin/diagnostics")
                .with(bearer("api-both")))
            .andExpect(status().isForbidden());
    }

    @Test
    void oidcTrustedClaimMapsAppRead() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://idp.example.invalid",
                   "report_access", "viewer"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertTrue(has(mapped, "APP_REPORT_READ"));
        assertFalse(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void oidcApproverClaimMapsBothAppPermissions() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://idp.example.invalid",
                   "report_access", "approver"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertTrue(has(mapped, "APP_REPORT_READ"));
        assertTrue(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void untrustedIssuerDoesNotMapAppRole() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://unexpected.example.invalid",
                   "report_access", "approver"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertFalse(has(mapped, "APP_REPORT_READ"));
        assertFalse(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void oauthScopeIsNotAutomaticallyBusinessAppRole() {
        var mapped = loginMapper.mapAuthorities(List.of(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("OAUTH2_USER")));
        assertTrue(has(mapped, "SCOPE_reports.read"));
        assertFalse(has(mapped, "APP_REPORT_READ"));
    }

    @Test
    void jwtConverterCreatesScopeAuthorities() {
        var authentication =
            jwtConverter.convert(jwt("unit", "reports.read"));
        assertTrue(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
        assertFalse(has(
            authentication.getAuthorities(), "APP_REPORT_READ"));
    }

    @Test
    void jwtConverterUsesScpClaim() {
        var authentication =
            jwtConverter.convert(jwtWithScp("unit-scp"));
        assertTrue(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
    }

    @Test
    void jwtConverterDoesNotInventRolesFromScopes() {
        var authentication =
            jwtConverter.convert(jwt("unit", "openid profile"));
        assertFalse(has(
            authentication.getAuthorities(), "ROLE_ADMIN"));
        assertFalse(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
    }
}
```

**Important QA note:** `@MockitoBean` is included in Spring Framework 6.2 (used by Boot 3.5). The stub `JwtDecoder` tests verify Bearer routing, the converter, and authorization decisions, **without proving real JWT signature/issuer/audience validation**. The `oauth2Login()` tests simulate an already-logged-in `Authentication`; they **do not** run authorization-code redirects, ID token validators, or the mapper in a real callback. Unit tests on `OidcIdToken`/`GrantedAuthoritiesMapper` verify the role mapping separately.

When integrating a real IdP, add:
- E2E OAuth2 authorization-code + OIDC Login verifying issuer/audience/nonce/state.
- Real JWTs signed with a test IdP's private key, checking JWKS rotation, `iss`, `aud`, `exp`, `nbf`.
- Negative tests sending an ID token as a Bearer access token, wrong audience, wrong issuer, and missing/malformed scopes.
- Session logout/re-authentication, role revocation, and authority cache TTLs.
- Opaque token introspection if the product supports opaque access tokens.

### 9.1. Running tests

```bash
mvn test
```

**Expected outcome:** the JUnit/MockMvc tests above pass on Spring Boot 3.5.6 and Spring Security 6.5.x. They have been authored and reviewed in source, **without Maven execution in this lesson**. Run them in CI and adjust if provider/client libraries or security configurations differ from the demo.

Because there is no live IdP at `idp.example.invalid`, opening a browser and clicking Login in the demo app **cannot complete real authentication** until you replace endpoints/credentials with a working IdP; mock tests can still validate authorization logic.

## 10. Reviewing common misconceptions

### 10.1. "OAuth2 Login never has `SCOPE_`"

False. Per Spring Security 6.5 documentation, `OAuth2User.getAuthorities()` or `OidcUser.getAuthorities()` includes scopes from the login client's access token with the `SCOPE_` prefix. This **does not prove** those scopes are business permissions for another resource server.

### 10.2. "A Bearer token is always a JWT"

False. Bearer is the mechanism carrying a token in a request. The token can be JWT or opaque; Spring Resource Server has two distinct authentication configurations. `JwtAuthenticationConverter` does not run for opaque introspection.

### 10.3. "Two sides holding `SCOPE_reports.read` have the same permissions"

Not always. A scope only has meaning given **issuer, audience, grant, client, and resource**. `reports.read` on a token issued for CRM grants no default permissions in a financial-report API. Resource Server must validate audience, not just match authority strings.

### 10.4. "An ID token is a valid Bearer access token"

No. An OIDC ID token is meant for **a client authenticating a user**. An access token is meant for a resource server. They have different audiences; an API must reject an ID token lacking the right audience/token type even when its signature is valid.

### 10.5. "If UserInfo has `role=admin`, just map `ROLE_ADMIN`"

No, if the claim comes from a user-editable source or an unconfigured provider. You need data provenance, issuer trust, tenant membership, consent, and role assignment policies. Public profile fields are not proof of admin rights.

### 10.6. "`oauth2Login` mapper also changes JWT authorities"

No. `oauth2Login`'s `GrantedAuthoritiesMapper` affects the Login flow; JWT Resource Server uses `JwtAuthenticationConverter` (opaque: introspector). The two hooks are independent.

### 10.7. "Changing the converter prefix from `SCOPE_` to `ROLE_` is enough"

No. Prefixes do not change token assurance, audience, or how roles are granted. Changing the prefix can also break existing `hasAuthority('SCOPE_...')` rules. Any migration requires tests and threat modeling.

### 10.8. "Every browser call to `/ui` sends the access token"

Not necessarily. Server-side OAuth2 Login typically stores `SecurityContext` in the session, and the browser sends a session cookie. The app may store access tokens in `OAuth2AuthorizedClientRepository`/Service for downstream calls, rather than attaching them to every browser request.

### 10.9. "A resource server API can trust a Login session just like Bearer"

Only if intentionally configured and reviewed. In the demo, the API chain accepts only Bearer JWTs with a stateless policy; the browser chain uses sessions. If they shared a chain, an expression `hasAuthority('SCOPE_reports.read')` could pass with a Login `Authentication` carrying that string. Keep authentication sources or routes separated.

### 10.10. "Keeping roles in the session forever is harmless"

No. If a user is removed from a group after Login, session authorities can persist until session refresh or expiration. You need revocation policies, re-authentication, or dynamic server-side checks. Bearer JWTs also have a validity window up to `exp` without revocation/introspection.

## 11. Checklist for designing dual-flow authorization

- [ ] Distinguish `oauth2Login()` from `oauth2ResourceServer().jwt()`/`opaqueToken()`.
- [ ] Enforce `OAuth2AuthenticationToken`, `JwtAuthenticationToken`, and `BearerTokenAuthentication` on the proper routes.
- [ ] Do not assume OAuth2 Login lacks scope authorities.
- [ ] Do not assume identical `SCOPE_*` strings mean identical audience or action.
- [ ] Never use `OIDC_USER`/`OAUTH2_USER` as business data permissions.
- [ ] Keep `hasRole`/`hasAuthority`/prefix conventions consistent.
- [ ] Source Login role mapping from OIDC/UserInfo/trusted memberships, never user-editable profiles.
- [ ] Ensure JWT converter handles `scope`/`scp`/custom claims and namespaces accurately.
- [ ] Customize opaque token introspectors separately; never invoke JWT converters on them.
- [ ] Validate JWT issuer, signature, `exp`/`nbf`, **audience**, and algorithm policy.
- [ ] Never treat ID tokens as API access tokens.
- [ ] Map subjects by `issuer + subject`; never use email/name as global permission keys.
- [ ] Ensure stateless Bearer APIs do not accidentally accept browser sessions.
- [ ] Ensure browser Login enforces session/CSRF/redirect state, login callbacks, and logout properly.
- [ ] Order security chains with `@Order` and `securityMatcher` leaving no gaps.
- [ ] Check tenant/object permissions plus authentication mechanism in domain methods instead of relying on authority strings alone for high-risk actions.
- [ ] Grant read and approve/write permissions separately; read scope must never imply write.
- [ ] Enforce TTL/cache consistency strategies for role grants/revocations in both sessions and tokens.
- [ ] Cover `MockMvc` tests with mocked OAuth2 Login, mocked JWT Bearer decoder, and unit mapper/converter tests.
- [ ] Run contract/E2E tests with a real IdP proving cryptographic validation and authority mapping.
- [ ] Audit decisions by principal issuer/subject, mechanism, policy version, and action/resource; never log raw tokens.

## 12. Self-check questions

**Question 1.** An OAuth2 Login user has `OIDC_USER` and `SCOPE_openid`. Are they allowed to approve a report?

**Answer:** Not from those authorities alone. Explicit business permissions like `APP_REPORT_APPROVE` plus tenant/resource guards are required.

**Question 2.** A JWT Bearer carries `scope="reports.read reports.approve"`. Which authorities does Resource Server create by default?

**Answer:** Typically `SCOPE_reports.read` and `SCOPE_reports.approve` after the JWT is validly verified and the converter reads scopes.

**Question 3.** Can OAuth2 Login ever contain `SCOPE_reports.read`?

**Answer:** Yes. Login receives the client's access token with granted scopes, which Spring may represent as `SCOPE_*`. However, that does not make it the current Bearer token for `report-api`.

**Question 4.** Which hook maps roles from an ID token/UserInfo during OAuth2 Login?

**Answer:** `GrantedAuthoritiesMapper` or `OAuth2UserService`/`OidcUserService`, depending on whether existing claims suffice or extra lookups are needed.

**Question 5.** Which hook is used when a JWT Bearer `permissions` claim needs to produce `PERM_*`?

**Answer:** `JwtGrantedAuthoritiesConverter` configured with `setAuthoritiesClaimName`/`setAuthorityPrefix`, attached to `JwtAuthenticationConverter` in `oauth2ResourceServer().jwt()`.

**Question 6.** Which hook is used when an opaque Bearer token arrives at the resource server?

**Answer:** `OpaqueTokenIntrospector` or an introspection-related converter, not `JwtAuthenticationConverter`.

**Question 7.** Should `sub=alice` be used as a system-wide user key with multiple issuers?

**Answer:** No. Two issuers can reuse the same `sub` for two different users. Use `(issuer, sub)` or map to a verified stable internal principal ID.

**Question 8.** Does `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` force the caller to be JWT Bearer?

**Answer:** No. The expression checks only the authority string; to restrict authentication mechanisms, check the `Authentication` type/provenance or isolate routes by filter chain.

**Question 9.** Does using `@MockitoBean JwtDecoder` in MockMvc verify JWT signatures?

**Answer:** No. The mock decoder returns a pre-parsed token, so tests verify only the conversion/authorization pipeline. Real signed/verified JWT integration tests are still needed.

**Question 10.** An API uses cookies for auth and wants to disable CSRF because "REST." Is that justified?

**Answer:** No. Consider omitting CSRF only on endpoints whose threat model does not rely on automatically sent browser credentials, such as Bearer tokens in `Authorization` headers with proper safeguards. Browser sessions still require CSRF for unsafe methods.

## 13. Official references

- [Spring Security 6.5 — OAuth2 Login: Advanced Configuration / Mapping User Authorities](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): `OAUTH2_USER`, `OIDC_USER`, `SCOPE_*` in Login, `GrantedAuthoritiesMapper`, and delegated `OAuth2UserService`.
- [Spring Security 6.5 — OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): Authorization Code, `ClientRegistration`, redirect callbacks, and Login flow.
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): `JwtAuthenticationToken`, JWT claims validation, `scope`/`scp`, `JwtGrantedAuthoritiesConverter`, audience.
- [Spring Security 6.5 — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, `BearerTokenAuthentication`, `SCOPE_*`, and customization.
- [Spring Security 6.5 — Testing OAuth2 (MockMvc)](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `jwt()`, test authorities, and claims.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, proxies.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth2 client/resource server roles and authorization code.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization` Bearer header, transport, and token handling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, UserInfo, issuer/client ID, and authentication.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT profile and distinction from ID tokens.

**Conclusion:** `OAuth2 Login` creates a login session with `OAuth2AuthenticationToken`, typically holding `OAUTH2_USER`/`OIDC_USER` and **potentially `SCOPE_*`**. `Resource Server` validates the **current request's** Bearer access token using `JwtAuthenticationToken` or `BearerTokenAuthentication` with authorities from validated scopes/introspection. Never rely on the `SCOPE_` prefix alone to infer authority provenance. Separate converters/mappers, verify issuer/audience and canonical tenants, enforce roles/scopes per route and `Authentication` type, and test both allow/deny paths and differing tokens/claims.