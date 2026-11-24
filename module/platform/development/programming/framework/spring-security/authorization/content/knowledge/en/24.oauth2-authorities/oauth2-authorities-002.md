# Mapping Scopes to `SCOPE_` Authorities in Spring Security OAuth2 Resource Server

## 1. The problem: the access token has `docs:read`, so why check `SCOPE_docs:read`?

A system uses an **OAuth 2.0 Resource Server** to protect a documents API. The Authorization Server issues an **access token** with the `docs:read` scope:

```json
{
  "iss": "https://issuer.example.test/training",
  "sub": "alice",
  "aud": ["docs-api"],
  "scope": "docs:read docs:export",
  "exp": 1799999999
}
```

This is an **illustrative payload**, not a complete JWT, not a signed access token, and must not be used as an actual credential.

After the JWT is verified and converted into an `Authentication`, Spring Security Resource Server **by default** maps scopes into `GrantedAuthority` instances prefixed with `SCOPE_`:

```text
JWT claim:
  scope = "docs:read docs:export"

JwtGrantedAuthoritiesConverter:
  "docs:read"   -> "SCOPE_docs:read"
  "docs:export" -> "SCOPE_docs:export"

Authentication.getAuthorities():
  [SCOPE_docs:read, SCOPE_docs:export]
```

Therefore the API can write:

```java
.requestMatchers(HttpMethod.GET, "/api/docs/**")
    .hasAuthority("SCOPE_docs:read")
```

or with method security:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public DocumentView read(long documentId) {
    // Method body after passing the authority check.
}
```

If you write `hasAuthority("docs:read")`, it will **not match** by default, because the actual authority in `Authentication` is `SCOPE_docs:read`, not the raw scope string.

This lesson belongs to the **Authorities from OAuth2** group, topic **Mapping scopes to `SCOPE_` authorities in Resource Server** of the **Spring Security – authorization** module.

Objectives after this lesson:

1. Understand the difference between an **OAuth2 scope**, a **JWT claim**, a **Spring Security `GrantedAuthority`**, and a **role**.
2. Trace the path of a Bearer token through JWT validation to `JwtAuthenticationToken`.
3. Know which authorities `scope`/`scp` are converted into by default.
4. Use `hasAuthority("SCOPE_...")`, `@PreAuthorize`, or `OAuth2AuthorizationManagers.hasScope(...)` properly.
5. Configure a Spring Boot 3.5.x Resource Server, `issuer-uri`, `audiences`, and a JWT converter.
6. Customize claims/prefixes using `JwtGrantedAuthoritiesConverter` without accidentally escalating privileges.
7. Distinguish self-contained JWTs from opaque token introspection, along with scope mapping behavior.
8. Build a Java 17 / Spring Boot 3.5.8 / Spring Security 6.5.x example with Gradle code and integration tests.
9. Test the **actual Bearer -> JwtDecoder -> JwtAuthenticationConverter path** rather than only assigning authorities manually in tests.
10. Recognize that scopes grant only **functional** permissions, not permissions on tenants, owners, or individual objects.
11. Handle 401/403 errors, wrong audience/issuer tokens, insufficient scopes, revocation, and safe debugging practices.
12. Avoid confusing **ID tokens**, access tokens, client scopes, roles, and data permissions.

**Core message:** `SCOPE_` is **Spring Security's authority naming convention after reading scopes from a verified access token**. It is not a required claim inside the JWT, not a prefix to send to the Authorization Server, and not a substitute for tenant/ACL checks in the service.

---

## 2. Concepts: scope, role, authority, permission, tenant

| Concept | Example | Where it lives / who decides |
| --- | --- | --- |
| OAuth2 scope | `docs:read` | Authorization Server grants it to the access token per grant/policy |
| JWT claim `scope` | `"docs:read docs:write"` | Payload of the access token |
| JWT claim `scp` | `["docs:read", "docs:write"]` | Claim style commonly used by some providers |
| Spring `GrantedAuthority` | `SCOPE_docs:read` | Resource Server creates it in `Authentication` |
| Application role | `ROLE_ADMIN` | Application's role source and mapping rules |
| Object permission | `READ document#11` | Domain ACL/owner/share/ABAC |
| Tenant membership | Alice belongs to `T1` | Verified membership/directory |
| Token audience | `docs-api` | Resource Server must verify the token is meant for its API |
| Subject | `iss` + `sub` | Stable principal ID within the issuer scope |

**An access token with scope `docs:read` does not automatically mean** the bearer can view every document across every tenant. It usually only indicates that the client/principal has been granted the capability to invoke the **read operations group** on the corresponding Resource Server. To view Document#11, you may still need:

```text
allowRead(actor, document) =
    validAccessTokenForThisApi
    AND authorityContains("SCOPE_docs:read")
    AND actorIsMemberOf(document.tenantId)
    AND ownerOrAclAllows(actor, document)
```

Scopes are typically the **coarse-grained** layer; object/tenant authorization is the **fine-grained** layer. Do not confuse `"SCOPE_admin"` appearing in a token with `ROLE_ADMIN`, nor confuse a role with system-wide superuser privilege.

### 2.1. An access token is not an ID token

In OpenID Connect (OIDC), an **ID token** primarily conveys the user authentication event to the **client**, whereas an **access token** is issued to call a resource/API. A Resource Server should process an **access token** with the audience and constraints suited to the API, not use an ID token meant for another client as an API bearer token.

An ID token may contain `email`, `preferred_username`, `name`, or even role claims, but seeing those fields does **not** prove it is a valid access token for `docs-api`.

### 2.2. Requested scopes differ from granted scopes

A client may request:

```text
scope=docs:read docs:write
```

The Authorization Server may still grant only:

```text
scope=docs:read
```

The Resource Server must rely on the **verified actual token**, not on the authorization request query, frontend settings, or the list of scopes the client *wanted*.

---

## 3. Path from Bearer token to `SCOPE_`

When the API receives:

```http
GET /api/docs/11 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
```

the typical flow in a Spring Security Servlet JWT Resource Server is:

```text
HTTP Authorization: Bearer <access-token>
          |
          v
BearerTokenAuthenticationFilter
          |
          v
JwtAuthenticationProvider
          |
          v
JwtDecoder / NimbusJwtDecoder
  - parses token as JWT format
  - verifies signature and matching key
  - validates exp / nbf / iss per decoder
  - validates aud when configured
          |
          v
Jwt (claims that passed decoder validation)
          |
          v
JwtAuthenticationConverter
          |
          +--> JwtGrantedAuthoritiesConverter
          |      scope/scp -> SCOPE_...
          |
          v
JwtAuthenticationToken
  Authentication.getPrincipal() = Jwt
  Authentication.getName()      = sub (default)
  Authentication.getAuthorities() = GrantedAuthority list
          |
          v
SecurityContextHolder + AuthorizationFilter
          |
          +--> HTTP hasAuthority / hasScope
          +--> Method Security @PreAuthorize
          |
          v
Controller -> Service -> Domain & Repository ACL
```

This is a logical diagram; it does not depict every internal invocation or every filter in exact order across all configurations.

**Key point:** Parsing the `scope` claim is not equivalent to verifying the token. The converter only maps **claims already accepted by `JwtDecoder`**. If an application manually calls `Base64.decode(payload)` and reads scopes **without verifying signature/issuer/audience**, an attacker can craft a fake JSON scope and grant themselves permissions.

### 3.1. Self-contained JWT: required checks

A production JWT Resource Server must enforce:

- **Signature/algorithm/key:** accept only trusted algorithms and keys from the configured issuer; never trust an arbitrary `alg` or `jku` chosen by the token without controls.
- **Issuer (`iss`):** matches the trusted Authorization Server.
- **Validity window (`exp`, `nbf`):** reject expired or not-yet-valid tokens.
- **Audience (`aud`):** intended for this API itself, not an access token for another API.
- **Tenant/organization context:** matches the trust boundary in a multi-tenant system.
- **Grant/revocation and policy updates:** decisions on invalidating unexpired tokens, cache TTLs, and freshness requirements.

Spring Security includes default validators based on configuration; using an issuer URI **is no reason to skip audience validation**. With Spring Boot 3.5 you can configure `spring.security.oauth2.resourceserver.jwt.audiences`.

### 3.2. 401 and 403 errors

| Scenario | Typical result |
| --- | --- |
| Missing Bearer token when endpoint requires auth | `401 Unauthorized` |
| Bearer cannot be decoded/verified | `401 Unauthorized` |
| JWT expired or wrong issuer | `401 Unauthorized` |
| Valid JWT, missing `SCOPE_docs:read` | `403 Forbidden` |
| JWT has `SCOPE_docs:read`, missing ACL/tenant permission | Usually `403` or `404` per contract |
| Public endpoint, no token needed | Allowed by `permitAll` unless rejected by another filter |

Exact statuses depend on the entry point, exception handler, filter order, and per-application configuration. When returning `403`, you do not need to disclose that an object in another tenant exists.

---

## 4. Default rule: `scope` or `scp` -> `SCOPE_`

Spring Security JWT Resource Server typically uses `JwtAuthenticationConverter` together with `JwtGrantedAuthoritiesConverter`.

### 4.1. `scope` claim as a space-delimited string

Example:

```json
{
  "sub": "alice",
  "scope": "docs:read docs:write docs:export"
}
```

Generated authorities:

```text
SCOPE_docs:read
SCOPE_docs:write
SCOPE_docs:export
```

**It does not automatically create** `ROLE_ADMIN`, unprefixed `docs:read`, or `SCOPE_docs` if the token only has `docs:read`.

### 4.2. `scp` claim as a list

Some Authorization Servers use:

```json
{
  "sub": "alice",
  "scp": ["docs:read", "docs:write"]
}
```

By default, the converter also supports reading the scope list from `scp` and produces:

```text
SCOPE_docs:read
SCOPE_docs:write
```

Some providers send the `scp` claim as a string. Spring Security's converter handles `String` values using the configured delimiter and `Collection` values element by element.

### 4.3. Case with no scope

For example, a valid token for the API, but:

```json
{
  "sub": "alice",
  "aud": ["docs-api"]
}
```

With only the default converter, `SCOPE_docs:read` is **not generated**. The caller may be authenticated, but an endpoint requiring `hasAuthority("SCOPE_docs:read")` must deny access.

This is the distinction:

```text
authenticated()  !=  hasAuthority("SCOPE_docs:read")
```

Do not try to "fix" a missing scope error by changing the whole documents API to `.anyRequest().authenticated()`, because doing so opens actions beyond the caller's functional permissions.

### 4.4. What if both `scope` and `scp` are present?

In Spring Security 6.5's default converter, finding the well-known authorities claim uses a **list of recognized names**, with no contract to "merge every claim by union." Therefore, **do not assume** scopes from both `scope` and `scp` will be combined.

When an IdP might send both claims simultaneously, standardize the contract with the IdP or **explicitly configure `setAuthoritiesClaimName(...)`**, and test real payloads and security regressions. Never union claims from sources that do not share the same trust level.

### 4.5. Claims named `permissions` or `roles` do not become scopes automatically

A JWT containing:

```json
{
  "permissions": ["docs:read"],
  "roles": ["ADMIN"]
}
```

will **not automatically** be mapped to `SCOPE_docs:read` or `ROLE_ADMIN` by the default `JwtGrantedAuthoritiesConverter` reading `scope`/`scp`. To use custom claims, you need an explicit converter with allow-listing/validation; avoid turning roles not guaranteed by the issuer into system roles.

---

## 5. How to check authorities in HTTP Security

### 5.1. Using `hasAuthority("SCOPE_...")`

In Spring Security Servlet:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/docs/**")
        .hasAuthority("SCOPE_docs:read")
    .requestMatchers(HttpMethod.POST, "/api/docs")
        .hasAuthority("SCOPE_docs:write")
    .anyRequest().denyAll()
);
```

- `GET /api/docs/11` requires the exact authority `SCOPE_docs:read`.
- `POST /api/docs` requires `SCOPE_docs:write`.
- A user with only read scope does **not** automatically have write scope.
- For `DELETE`, `PATCH`, and `PUT`, matching rules/permissions must exist if supported by the business logic.
- `anyRequest().denyAll()` ensures new endpoints are not left open without review.

Order narrow and method-specific matchers properly. An overly broad `"/api/docs/**".authenticated()` rule placed before the POST/write rule can bypass the write restriction.

### 5.2. Using OAuth2 `hasScope(...)`

Spring Security 6.5 also provides a helper:

```java
import static org.springframework.security.oauth2.core.authorization.OAuth2AuthorizationManagers.hasScope;
```

And:

```java
.requestMatchers(HttpMethod.GET, "/api/docs/**")
    .access(hasScope("docs:read"))
```

**Code snippet**, assuming `HttpSecurity` is configured inside a `SecurityFilterChain` bean. `hasScope("docs:read")` expresses the token's read scope, corresponding to the `SCOPE_docs:read` authority model when using the standard mapping. Do not pass `"SCOPE_"` into `hasScope` if this API expects the raw scope name.

If you customize the prefix away from `SCOPE_`, review how `hasScope(...)` and `hasAuthority(...)` interact per your version's contract rather than assuming the two are always equivalent.

### 5.3. `hasRole("ADMIN")` is a different concept

| Expression | What does it check by default? |
| --- | --- |
| `.hasAuthority("SCOPE_docs:read")` | Has authority `SCOPE_docs:read` |
| `.hasAuthority("docs:read")` | Has raw authority `docs:read` |
| `.hasRole("ADMIN")` | Has authority `ROLE_ADMIN` |
| `.hasAuthority("ROLE_ADMIN")` | Has authority `ROLE_ADMIN` |
| `.access(hasScope("docs:read"))` | Has OAuth2 scope `docs:read` per manager |
| `.authenticated()` | Only requires authentication, no specific scope |

**Do not use `.hasRole("docs:read")`** to check an OAuth scope: `hasRole` prepends `ROLE_` by default and will look for `ROLE_docs:read`, not `SCOPE_docs:read`.

### 5.4. `@PreAuthorize` at the service layer

```java
@PreAuthorize("hasAuthority('SCOPE_docs:write')")
public String create() {
    return "CREATED";
}
```

For the annotation to be enforced in a Spring MVC/Servlet app, enable:

```java
@EnableMethodSecurity
```

The method must be invoked through a **Spring-managed proxy**. If another method in the same bean calls `this.create()`, Spring AOP may bypass the interceptor on self-invocation. For defense in depth, place critical checks at the service/domain boundary and test them through the real Spring context.

---

## 6. Full example: Spring Boot 3.5.8 JWT Resource Server

This Java 17 project demonstrates:

- Mapping JWT claims `scope` and `scp` into `SCOPE_...`.
- Requiring different scopes for HTTP GET and POST.
- Re-checking authorities with Method Security in the service layer.
- Enforcing tenant isolation via a server-side directory after authenticating the subject.
- Real tests sending the Bearer header through `MockMvc`, using a **test-only** `JwtDecoder` to produce decoded JWTs.
- Dedicated unit tests for `JwtGrantedAuthoritiesConverter`.
- Production `issuer-uri` and audience configuration, without confusing a fake test decoder with real JWT cryptographic verification.

**Important:** The main configuration targets a Resource Server with a **real Authorization Server** in production. The integration tests that run independently of an IdP using a fake `JwtDecoder` **exist only in test sources** and do not prove JWT cryptographic verification.

### 6.1. Project structure

```text
scope-authority-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ScopeAuthorityApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── ScopeResourceServerTest.java
        └── JwtScopeConverterTest.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'scope-authority-resource-server'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` brings in Spring Security Resource Server and Boot-managed JWT/Jose dependencies. You do not need `spring-boot-starter-oauth2-client` if the application **acts solely as a Bearer-accepting API Resource Server** and does not perform OAuth2 login/authorization code flows itself.

### 6.4. `application.yml`: issuer and audience

**`src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/training
          audiences:
            - docs-api
```

`https://issuer.example.test/training` is an **illustrative URL**, not a live IdP. To run the real API, replace it with your Authorization Server's issuer URI and your API's exact audience. The tests in Section 7 use a fake decoder so they **do not require a running issuer**.

Production policy:

- `issuer-uri` must be a **trusted** issuer, never taken from caller-supplied headers or queries.
- `audiences` must be the real resource server audience, never an arbitrary OAuth client's audience.
- If also configuring a JWK Set URI, understand how it interacts with issuer validation and key rotation.
- Never disable signature verification or allow `"alg":"none"` tokens.
- Never rely on an access token **having** a `"scope"` claim if decoder/issuer validation is bypassed.

In Spring Boot 3.5, `spring.security.oauth2.resourceserver.jwt.audiences` configures audience validation for the Resource Server.

### 6.5. Application: `ScopeAuthorityApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeAuthorityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ScopeAuthorityApplication.class, args
        );
    }
}
```

### 6.6. Security configuration: `SecurityConfig.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        // Do not set claim name/prefix: keep default
        // "scope" or "scp" and "SCOPE_".
        JwtAuthenticationConverter auth =
            new JwtAuthenticationConverter();

        auth.setJwtGrantedAuthoritiesConverter(scopes);
        return auth;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter authConverter)
            throws Exception {

        return http
            // Suitable only when the API is strictly bearer-only,
            // stateless, and does not rely on browser cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping"
                ).permitAll()

                .requestMatchers(
                    HttpMethod.GET, "/api/me/authorities"
                ).authenticated()

                .requestMatchers(
                    HttpMethod.GET, "/api/docs/**"
                ).hasAuthority("SCOPE_docs:read")

                .requestMatchers(
                    HttpMethod.POST, "/api/docs"
                ).hasAuthority("SCOPE_docs:write")

                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(jwt ->
                    jwt.jwtAuthenticationConverter(authConverter)
                )
            )
            .build();
    }
}
```

**Technical explanation:**

- `JwtGrantedAuthoritiesConverter` defaults to the `scope`/`scp` claim and the `SCOPE_` prefix.
- `JwtAuthenticationConverter` builds `JwtAuthenticationToken` from the JWT and its authorities.
- `@EnableMethodSecurity` activates `@PreAuthorize` in `DocumentService`.
- `GET /api/docs/**` requires read scope; `POST /api/docs` requires write scope.
- `GET /api/me/authorities` requires authentication, purely to observe authority mapping in the demo. **Do not ship a similar debug endpoint to production** without justification and access controls.
- `anyRequest().denyAll()` rejects unreviewed paths/methods.
- `.csrf(AbstractHttpConfigurer::disable)` is **acceptable in this example only** because the API is designed purely around Bearer headers without cookie-based sessions or implicit credentials. If your application uses browser cookies/sessions, re-evaluate and enable CSRF appropriately. Do not blindly copy disabling CSRF across every API.
- JWT decoding/verification is never disabled in main sources. With a real `issuer-uri`, Spring Security constructs `JwtDecoder` per configuration and validates tokens before the converter runs.

### 6.7. Service: functional scope + tenant-scoped access

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

record Document(long id, String tenantId, String title) {
}

@Service
public class DocumentService {

    private final Map<Long, Document> docs = Map.of(
        11L, new Document(11L, "T1", "Alpha"),
        12L, new Document(12L, "T1", "Beta"),
        21L, new Document(21L, "T2", "Gamma")
    );

    // Simulates a trusted server-side directory, NOT a
    // self-asserted client JWT claim.
    private final Map<String, String> actorTenants = Map.of(
        "alice", "T1",
        "bob", "T2"
    );

    @PreAuthorize("hasAuthority('SCOPE_docs:read')")
    public String read(long id) {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()) {
            throw new AccessDeniedException(
                "Authenticated actor required");
        }

        String trustedTenant =
            actorTenants.get(auth.getName());

        if (trustedTenant == null) {
            throw new AccessDeniedException(
                "Trusted tenant mapping required");
        }

        Document document = docs.get(id);

        if (document == null
                || !trustedTenant.equals(document.tenantId())) {
            // Do not disclose that an object in another tenant exists.
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document unavailable"
            );
        }

        return document.title();
    }

    @PreAuthorize("hasAuthority('SCOPE_docs:write')")
    public String create() {
        // Demo only illustrates authorization; does not mutate DB.
        return "CREATED";
    }
}
```

Because this is a **Spring MVC/Servlet** app, reading `SecurityContextHolder` on the request thread is the right imperative model. This lesson is **not** Reactive WebFlux; on a reactive stack, read authentication via `ReactiveSecurityContextHolder` and use `SecurityWebFilterChain`.

`actorTenants` is a simulated directory. In production:

- Use a stable `issuer + subject`/internal user ID instead of assuming `sub` is unique across all issuers.
- Verify membership/tenant status from an authoritative source.
- For DB-backed data, filter `WHERE id = :id AND tenant_id = :trustedTenant` **in the repository SQL**, rather than fetching other tenants' rows and filtering in memory.
- For write operations, check owner/ACL/state/version inside a transaction or conditional DML.
- The `SCOPE_docs:read` scope is **only one condition** for reading an object.

In the demo, `read` uses a small in-memory map; in a real product this is **not a sufficient data isolation mechanism**.

### 6.8. Controller: `DocumentController.java`

```java
package demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/api/docs/{id}")
    public String read(@PathVariable long id) {
        return service.read(id);
    }

    @PostMapping("/api/docs")
    public String create() {
        return service.create();
    }

    @GetMapping("/api/me/authorities")
    public List<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .sorted()
            .toList();
    }
}
```

The controller **does not** accept `userId`/`tenant` from the request to grant permissions. `DocumentService` obtains the identity from the verified Spring Security context, checks the scope via Method Security, and enforces tenant isolation afterward.

The debug API `GET /api/me/authorities` exposes only the mapped **authority names**, without printing raw access tokens; still, it should not be enabled for production users unless needed.

---

## 7. Real integration tests on the HTTP Bearer authentication flow

### 7.1. Why not rely solely on the `jwt()` test helper?

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.jwt()` and allows assigning arbitrary authorities:

```java
// TEST SNIPPET: easy to write, but has limitations.
mvc.perform(get("/api/docs/11")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_docs:read")
    ))
);
```

This is very useful for testing **HTTP/method policies**, but the authority is **manually injected** by the test. If you use only this, tests can pass even when the production `JwtGrantedAuthoritiesConverter` has the wrong claim or prefix.

To verify the exact goal of this lesson, we send `Authorization: Bearer ...` with a **test-only fake `JwtDecoder` in the test context**. The real filter/provider/`JwtAuthenticationConverter` will receive the `Jwt` and map `scope` or `scp` to authorities. The fake decoder only replaces cryptographic token verification; **never** use this in production.

### 7.2. `ScopeResourceServerTest.java`

**`src/test/java/demo/ScopeResourceServerTest.java`:**

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(ScopeResourceServerTest.FakeDecoderConfig.class)
class ScopeResourceServerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeDecoderConfig {

        @Bean
        @Primary
        JwtDecoder jwtDecoder() {
            return raw -> switch (raw) {
                case "read-alice" -> token(
                    raw, "alice", "scope", "docs:read");

                case "write-alice" -> token(
                    raw, "alice", "scope", "docs:write");

                case "both-alice" -> token(
                    raw, "alice", "scope",
                    "docs:read docs:write");

                case "read-bob" -> token(
                    raw, "bob", "scope", "docs:read");

                case "scp-alice" -> token(
                    raw, "alice", "scp",
                    List.of("docs:read"));

                case "empty-alice" -> token(
                    raw, "alice", "scope", "");

                case "role-alice" -> token(
                    raw, "alice", "scope", "admin");

                default -> throw new BadJwtException(
                    "Invalid test Bearer token");
            };
        }

        private static Jwt token(
                String raw,
                String subject,
                String claimName,
                Object claimValue) {

            return Jwt.withTokenValue(raw)
                .header("alg", "RS256")
                .claim("sub", subject)
                .claim(
                    "iss",
                    "https://issuer.example.test/training"
                )
                .claim("aud", List.of("docs-api"))
                .claim(claimName, claimValue)
                .build();
        }
    }

    private static String bearer(String raw) {
        return "Bearer " + raw;
    }

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("PONG"));
    }

    @Test
    void scopeReadMapsToAuthorityAndAllowsRead()
            throws Exception {

        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_docs:read")
            );

        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Alpha"));
    }

    @Test
    void scpArrayAlsoMapsToScopeAuthority()
            throws Exception {

        mvc.perform(get("/api/docs/12")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("scp-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Beta"));
    }

    @Test
    void readScopeCannotWrite() throws Exception {
        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCannotRead() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("write-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPost() throws Exception {
        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("write-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("CREATED"));
    }

    @Test
    void multipleScopesProduceMultipleAuthorities()
            throws Exception {

        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_docs:read")
            )
            .andExpect(
                jsonPath("$[1]")
                    .value("SCOPE_docs:write")
            );

        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isOk());
    }

    @Test
    void noScopeCannotRead() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("empty-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void scopeAdminIsNotRoleAdmin() throws Exception {
        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("role-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_admin")
            );

        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("role-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void knownIdInOtherTenantIsNotVisible()
            throws Exception {

        mvc.perform(get("/api/docs/21")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/docs/21")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-bob")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Gamma"));
    }

    @Test
    void invalidBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("not-valid")
                ))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/docs/11"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedMethodIsDenied() throws Exception {
        mvc.perform(post("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isForbidden());
    }
}
```

**Explanation of test reliability:**

- `MockMvc` passes through `SecurityFilterChain`; the Bearer token is extracted by the Resource Server authentication flow.
- The test-only `JwtDecoder` returns a `Jwt` with matching claims based on simulated token names. **Do not** put this decoder into `src/main` or use it in production/staging with real data.
- The **real** `JwtAuthenticationConverter` reads `scope`/`scp` and creates `SCOPE_...` in `Authentication`.
- `@EnableMethodSecurity` still executes through the Spring proxy of `DocumentService`.
- Negative tests cover missing scope, wrong scope, invalid JWT, missing token, and cross-tenant IDs.
- `@AutoConfigureMockMvc` does not disable Spring Security; requests flow through the configured filters.

**Explicit limitation:** This tests **authorization mapping and routing**, not RSA/JWK signatures or issuer/audience validators. The fake `JwtDecoder` accepts defined payloads without cryptographic verification. Add integration tests using an Authorization Server/JWK test fixture and expired/incorrect-issuer/wrong-audience JWTs on a real `NimbusJwtDecoder` before production deployment.

### 7.3. Converter unit tests: `JwtScopeConverterTest.java`

**`src/test/java/demo/JwtScopeConverterTest.java`:**

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class JwtScopeConverterTest {

    private static Jwt jwt(String claim, Object value) {
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim(claim, value)
            .build();
    }

    private static Set<String> authorities(
            JwtGrantedAuthoritiesConverter converter,
            Jwt jwt) {

        return converter.convert(jwt).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void spaceDelimitedScopeBecomesPrefixedAuthorities() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_docs:read", "SCOPE_docs:write"),
            authorities(
                converter,
                jwt("scope", "docs:read docs:write")
            )
        );
    }

    @Test
    void scpArrayAlsoBecomesPrefixedAuthorities() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_docs:read", "SCOPE_docs:export"),
            authorities(
                converter,
                jwt(
                    "scp",
                    List.of("docs:read", "docs:export")
                )
            )
        );
    }

    @Test
    void missingScopeDoesNotGrantRead() {
        var converter = new JwtGrantedAuthoritiesConverter();

        Set<String> granted = authorities(
            converter,
            Jwt.withTokenValue("no-scope")
                .header("alg", "RS256")
                .claim("sub", "alice")
                .build()
        );

        assertFalse(granted.contains("SCOPE_docs:read"));
        assertEquals(Set.of(), granted);
    }

    @Test
    void scopeDoesNotAutomaticallyBecomeRole() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_admin"),
            authorities(converter, jwt("scope", "admin"))
        );
    }

    @Test
    void customClaimAndPrefixMustBeExplicit() {
        var converter = new JwtGrantedAuthoritiesConverter();

        converter.setAuthoritiesClaimName("permissions");
        converter.setAuthorityPrefix("PERM_");

        assertEquals(
            Set.of("PERM_docs:read"),
            authorities(
                converter,
                jwt(
                    "permissions",
                    List.of("docs:read")
                )
            )
        );

        assertEquals(
            Set.of(),
            authorities(
                converter,
                jwt("scope", "docs:read")
            )
        );
    }
}
```

These tests **target the converter directly**, isolating **claim mapping** issues from **JWT verification** and HTTP filter issues. If the mapping unit test passes while HTTP returns 403, the issue may lie in converter wiring, matcher ordering, method security, or the JWT decoder. If an HTTP test with manually assigned `jwt()` authorities passes while the converter test fails, fix the **converter**, not the test authorities.

### 7.4. Running tests

When the Gradle Wrapper is present:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

If there is no wrapper yet, use an installed compatible Gradle version to generate it (`gradle wrapper`), then run. The test suite is designed to run **without connecting to an IdP**, because nested `FakeDecoderConfig` exists only in tests.

**Expected result:** 13 HTTP integration tests and 5 converter tests, all passing in a compatible dependency environment. This is an **expectation based on the authored source code**, not a claim of having compiled or executed tests in the current environment.

### 7.5. Running the real app requires an Authorization Server

```bash
./gradlew bootRun
```

The production build **does not** include `FakeDecoderConfig`. To call the real API, configure an accessible `issuer-uri` and obtain a valid JWT from that IdP with audience `docs-api` and the matching scopes.

Example request syntax, where `<ACCESS_TOKEN>` must be a **valid access token issued by the IdP**:

```bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/docs/11
```

Do not Base64-encode the illustrative JSON from the beginning of this lesson to use as an access token: JWTs require valid signatures, format, and validations. Do not pass test token strings like `"read-alice"` or `"both-alice"` to the real app; a production Resource Server must reject them.

---

## 8. Customizing the converter: claim, prefix, and principal name

Defaults work well if the IdP issues standard scopes. If the IdP uses a different structure, **explicitly declare** the mapping and write regression tests.

### 8.1. Custom claim: `permissions`

For example, the IdP issues:

```json
{
  "sub": "alice",
  "permissions": ["docs:read", "docs:write"]
}
```

You can configure:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("permissions");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
```

**This is an alternative bean replacing the one in `SecurityConfig.java`**; do not add two beans with the same name simultaneously to the demo project.

With this configuration, the converter uses the `permissions` claim instead of the default `scope`/`scp`; authorities still have the `SCOPE_` prefix unless you change the prefix. This **does not automatically mean every value in `permissions` is a valid OAuth2 scope**: the application and issuer must specify the mapping policy.

### 8.2. Custom prefix

If you want authorities like `"PERM_docs:read"`:

```java
JwtGrantedAuthoritiesConverter granted =
    new JwtGrantedAuthoritiesConverter();

granted.setAuthoritiesClaimName("permissions");
granted.setAuthorityPrefix("PERM_");
```

Then you must use:

```java
.hasAuthority("PERM_docs:read")
```

rather than continuing to require `SCOPE_docs:read` and expecting it to match.

Spring Security also allows an empty prefix:

```java
granted.setAuthorityPrefix("");
```

However, removing the prefix makes it easy to confuse scopes with roles or custom authorities. For APIs with multiple authority sources, maintain clear namespaces (`SCOPE_`, `ROLE_`, `PERM_`) and review the semantics of each namespace.

### 8.3. Custom delimiter

For an IdP sending a string claim with a custom separator, Spring Security 6.5 provides:

```java
granted.setAuthoritiesClaimDelimiter(",");
```

This is a **regex** applied to a String claim, not a way to split arbitrary Collection types. Only change the delimiter when the actual token contract is **guaranteed by the issuer**; include tests for spaces, empty values, and malformed data.

### 8.4. Custom principal claim

If you have a use case where `Authentication.getName()` should use a different claim:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
```

However, the `sub` subject is generally better suited as a stable identity. `preferred_username`/email can change or collide across tenants; **do not** use them as security keys unless the IdP guarantees uniqueness and immutability.

### 8.5. Keeping scopes and roles separate

Some tokens contain both `scope` and a `realm_access.roles` claim. If you need to turn issuer roles into `ROLE_...`, use a **composite converter with a trusted source and allow-list** rather than converting all scopes to `ROLE_` via:

```java
granted.setAuthorityPrefix("ROLE_");
```

because that could cause a scope named `ADMIN` to be interpreted as a system role. When designing a custom converter:

- Scopes use the `SCOPE_` namespace.
- Issuer-asserted, app-accepted roles use the `ROLE_` namespace.
- Internal permissions use a separate namespace if needed.
- Verify issuer/audience/tenant/role source before granting authorities.
- Never union token fields from multiple clients/issuers lacking the same trust level.
- Write negative tests: a token from another issuer must not become admin.

---

## 9. Opaque tokens also map scopes -> `SCOPE_`, but the source of facts differs

JWT is only **one access token format**. With an opaque token, the Resource Server does not decode claims locally with a JWT parser, but queries an **introspection endpoint**:

```text
Authorization: Bearer opaque-value
          |
          v
OpaqueTokenIntrospector
          |
          v
Authorization Server introspection endpoint
          |
          v
active=true, scope="docs:read docs:write", sub="alice"
          |
          v
BearerTokenAuthentication
          |
          v
GrantedAuthority:
   SCOPE_docs:read
   SCOPE_docs:write
```

Spring Security opaque-token support also maps scopes with the `SCOPE_` prefix by default.

Outline configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.test/introspect
          client-id: docs-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

And the security DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

This is an **alternative configuration replacing the JWT resource server**; do not paste both `.jwt(...)` and `.opaqueToken(...)` together into the demo without an explicit requirement.

**Differences:**

| JWT Resource Server | Opaque Resource Server |
| --- | --- |
| Decodes and verifies JWT via `JwtDecoder` | Introspects token via `OpaqueTokenIntrospector` |
| `JwtAuthenticationToken` is the typical Authentication | `BearerTokenAuthentication` is the typical Authentication |
| Claims come from the verified JWT | Attributes come from the introspection response |
| Default scope converter reads `scope`/`scp` | Default scope mapping reads response `scope` |
| Can verify offline using JWK | Depends on introspection service availability |
| Pre-expiry revocation requires policy/blacklist/introspection | Introspection typically queries current active status, subject to caching |

Do not use `JwtGrantedAuthoritiesConverter` expecting it to configure **opaque introspection** mapping; if an opaque provider uses custom permission fields, you typically need a custom `OpaqueTokenIntrospector`/principal-authority mapping.

---

## 10. SCOPE_ does not automatically solve multi-tenancy and object-level authorization

Suppose:

| Document | Tenant | Owner |
| ---: | --- | --- |
| 11 | T1 | Alice |
| 12 | T1 | Bob |
| 21 | T2 | Carol |

Alice has a valid JWT:

```json
{
  "sub": "alice",
  "aud": ["docs-api"],
  "scope": "docs:read"
}
```

If the service only writes:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
```

then Alice can read T2's document 21 simply by guessing the ID. **This is an object-level authorization bug**, not a scope converter bug.

Conceptually right approach:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public DocumentView read(long id) {
    Actor actor = actorDirectory.requireFromAuthentication();

    return repository.findByIdAndTenantId(
        id, actor.trustedTenantId()
    ).map(DocumentView::from)
     .orElseThrow(() -> new ResponseStatusException(
         HttpStatus.NOT_FOUND, "Document unavailable"
     ));
}
```

**Code snippet**, requiring other types/services to be defined. The key point is that `trustedTenantId` comes from a verified directory/membership, not directly from a `?tenantId=T2` query parameter.

For READ requiring ACLs or row ownership, add those conditions as well. For UPDATE/DELETE, guard tenant/owner/state/version **directly in SQL DML** to prevent TOCTOU. In the UI, never treat the presence of a "Delete" button as authorization.

### 10.1. Client credentials differ from user delegation

An access token issued via the **client credentials grant** may represent a **client/application** without an end-user having the same semantics as authorization code. A service account's `docs:write` scope does not allow it to impersonate Alice.

Distinguish clearly:

- Does `sub` represent a user or a client identity per the IdP contract?
- Does the token have the audience for this Resource Server?
- Which tenants is the client allowed to operate on?
- Are separate service-to-service identity and auditing needed?
- Does `scope` only constrain the action while business approval/tenant scope are still required?

Do not blindly treat `Authentication.getName()` as a user ID if the API accepts both user tokens and machine tokens.

### 10.2. Scopes bound delegation, not the entire policy

A typical policy:

```text
ALLOW =
    tokenValid
    AND aud == docs-api
    AND grantedAuthorityContains(SCOPE_docs:read)
    AND membershipAllows(issuer, subject, tenant)
    AND objectAclAllows(subject, doc)
    AND dataStateAllows(action)
```

If any required condition lacks trustworthy data, **deny**—never open access based on scope alone.

---

## 11. Debugging `SCOPE_` safely

When someone says "the token has the scope but the API still returns 403," check **each layer in order**.

### 11.1. Diagnostic checklist

1. Confirm the token is a Resource-Server-accepted **access token**, not an ID token sent by the client.
2. Inspect `Authorization: Bearer <token>` on the actual request.
3. Verify the token passed validation; JWT decoder failures typically return `401`, not an authority error.
4. Verify `iss`, `aud`, `exp`, `nbf` on the server per policy, not just by eyeballing a decoded payload in a debug tool.
5. Check whether the provider uses `scope`, `scp`, or another claim name.
6. Check whether the claim is a space-delimited String, a Collection, or uses a non-standard delimiter.
7. Check whether a custom `JwtAuthenticationConverter` or `JwtGrantedAuthoritiesConverter` is registered.
8. Check whether the active prefix is `SCOPE_` or was changed to `ROLE_`, `PERM_`, or an empty string.
9. Check `hasAuthority`/`hasRole`/`hasScope` in both HTTP Security and Method Security.
10. Identify the first matcher rule that actually applies to the path and HTTP method.
11. Check whether the domain service (tenant, owner, ACL, state) is denying at a later layer.
12. Add a converter unit test + real Bearer integration test passing through the filter before changing production policy.

### 11.2. Never log raw tokens

Avoid:

```java
// FORBIDDEN in real applications:
log.info("Authorization header = {}", authorizationHeader);
```

because logs could retain usable Bearer tokens for accessing the API. Instead, log bounded metadata with appropriate retention:

```text
requestId, issuerIdentifier, subjectHash,
audienceResult, authorityNames, decision,
policyVersion, requestPathTemplate, responseStatus
```

Avoid logging tokens, refresh tokens, secrets, full JWT payloads containing PII, or sensitive group details. In production, even logging authority/role lists needs an appropriate logging policy.

### 11.3. Common errors

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| JWT scope `docs:read`, API `hasAuthority('docs:read')` returns 403 | Missing `SCOPE_` prefix | Require `SCOPE_docs:read` |
| Using `hasRole('docs:read')` | `hasRole` looks for `ROLE_docs:read` | Use `hasAuthority` or `hasScope` |
| JWT has only `scp`, custom converter reads only `scope` | Wrong claim name | Align `scp`/converter contract |
| `permissions` claim produces no authorities | Default reads only well-known scope claims | Custom claim converter |
| Token has right scope but returns 401 | Signature/issuer/audience/expiry failed decoder | Check trust config; do not bypass validators |
| Token has right scope but returns 403 | HTTP/method/domain policy not satisfied | Identify which rule denied |
| Read token fails on POST | Read scope differs from write scope | Issue proper write scope via AS |
| Role `ADMIN` in token but no `ROLE_ADMIN` | No role mapping configured | Custom role converter with allow-list |
| Custom prefix changed to `PERM_`, rule still uses `SCOPE_` | Misaligned configuration | Update policy and tests |
| Test `.with(jwt().authorities(...))` passes, prod fails | Test injects authorities, skips converter | Send Bearer header with test decoder + converter |
| Access token for API A works on API B | Missing `aud` validation | Configure audiences and test cross-audience tokens |
| User with scope reads another tenant's data | Missing object-level guard | Tenant-scoped repository + ACL |
| Old access token still works after revocation | JWT unexpired/cached | Token lifetime, introspection/revocation strategy |
| Opaque token custom fields unmapped | Default introspection maps only standard scope | Custom introspector |
| Client credentials treated as user token | Confused principal/client semantics | Separate machine identity policy |
| Broad `authenticated` rule placed before read rules | Matcher order permits early | Specific rules first, fallback deny |
| Copying `{noop}` test password into prod | Weakens credential security | Password hashing/OIDC/OAuth2 |
| Disabling CSRF on cookie/session app | CSRF risk | Design CSRF per actual authentication transport |

---

## 12. Security considerations: issuer, audience, replay, and revocation

### 12.1. Trust only the right Authorization Server

A Resource Server must never accept an arbitrary `"iss"` claim and fetch JWKs from a token-supplied issuer without a trusted issuer allow-list and SSRF/key-confusion protections.

In production, a tenant may have its own issuer. When supporting **multi-issuer/multi-tenant**, design an `issuer -> decoder` allow-list, audience validation, and tenant binding. A scope named `docs:read` from issuer A does not necessarily carry the same permissions as the same scope name from issuer B. Avoid combining authorities from tokens across different issuers without normalization and a trust policy.

### 12.2. Audience confusion

A user holds a valid access token for `billing-api` with `docs:read`. If `docs-api` verifies only the signature/issuer without verifying audience, it may accept a token **not meant for it**.

Configure audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/training
          audiences:
            - docs-api
```

Ensure real tokens carry the appropriate audience, and review behavior when `aud` is a string vs. a list depending on spec/provider.

### 12.3. What if a scope has been revoked?

With self-contained JWTs, a Resource Server can verify offline. This means an unexpired valid token can continue carrying `SCOPE_docs:read` **until expiration** unless additional revocation/denylist/token-version/introspection mechanisms are in place.

Depending on system requirements:

- Keep access token TTLs reasonable.
- Protect refresh tokens and enforce revocation policies.
- Use token revocation events + denylist/token epoch with cache invalidation.
- Use introspection when high freshness is required, trading off latency/availability.
- Re-check permissions/tenant/ACL in the DB at request and mutation time.
- For sensitive writes, use transactions/conditional UPDATEs to block changes to owner/grant/state between check and use.

**Do not treat an `ALLOW` from `SCOPE_docs:write` in a JWT as an immutable guarantee across an entire transaction lifecycle.**

### 12.4. OAuth scope names are a contract

Names like `docs:read`, `docs:write`, and `docs:export` are **application-defined examples**. The Authorization Server and Resource Server must agree on:

- Scope names and the meaning of each name.
- Permitted resources and actions.
- Who can be granted each scope and under which OAuth flow.
- Default deny when a token lacks a scope.
- Whether there is any hierarchy across read/write/admin.
- How roles, tenants, or project-specific permissions are mapped.
- Policy versioning and regression testing when semantics change.

Do not invent the rule "`docs:write` includes `docs:read`" unless it is an explicit policy enforced at the Authorization Server or converter/service; in Spring's default authorities model, they are two distinct strings.

---

## 13. Permission and status matrix

Assume the token has been accepted by the Resource Server (unless noted otherwise).

| Actor / JWT scope | Request | Result |
| --- | --- | --- |
| Anonymous, no token | `GET /public/ping` | `200` |
| Alice `docs:read` | `GET /api/docs/11` (T1) | `200`, `"Alpha"` |
| Alice `docs:read` | `GET /api/docs/21` (T2) | `404` per tenant scope |
| Bob `docs:read` | `GET /api/docs/21` (T2) | `200`, `"Gamma"` |
| Alice `docs:read` | `POST /api/docs` | `403`, missing write |
| Alice `docs:write` | `GET /api/docs/11` | `403`, missing read |
| Alice `docs:write` | `POST /api/docs` | `200`, `"CREATED"` (demo does not write DB) |
| Alice `docs:read docs:write` | Matching GET and POST | `200` |
| Alice `scp=["docs:read"]` | `GET /api/docs/12` | `200`, `"Beta"` |
| Alice `scope=""` | `GET /api/docs/11` | `403` |
| Alice `scope="admin"` | `GET /api/docs/11` | `403`, authority is `SCOPE_admin` |
| Undecodable token | `GET /api/docs/11` | `401` |
| No token | `GET /api/docs/11` | `401` |
| Valid token, unlisted POST path | `POST /api/docs/11` | `403`, fallback deny |

This is the **expected matrix for the demo**, not test results executed at the time of writing.

---

## 14. Practice exercises

### Exercise 1: predict the authorities

JWT payload:

```json
{
  "sub": "u1",
  "scope": "orders:read orders:write"
}
```

What does the Resource Server map by default?

**Answer:** `SCOPE_orders:read`, `SCOPE_orders:write`.

### Exercise 2: wrong `hasAuthority`?

```java
.hasAuthority("orders:read")
```

The token has `"scope":"orders:read"`, yet the API returns 403. Why?

**Answer:** Default authorities carry the `SCOPE_` prefix, so you must check `hasAuthority("SCOPE_orders:read")` or `hasScope("orders:read")` per the corresponding API.

### Exercise 3: `scp` as an array

```json
{
  "sub": "u1",
  "scp": ["orders:read", "orders:refund"]
}
```

Which authorities?

**Answer:** `SCOPE_orders:read`, `SCOPE_orders:refund` under the default converter.

### Exercise 4: missing scope

A JWT has a valid signature and right audience, but no `scope`/`scp`. A GET endpoint requires `SCOPE_orders:read`.

**Answer:** Typically 403 because the caller is authenticated but lacks the authority. Do not allow access merely because the token is properly signed.

### Exercise 5: scope vs. role

A JWT has `scope: "ADMIN"`. Does it automatically satisfy `.hasRole("ADMIN")`?

**Answer:** No. The default converter produces `SCOPE_ADMIN`, while `hasRole` looks for `ROLE_ADMIN` by default.

### Exercise 6: custom prefix

The converter uses `setAuthorityPrefix("PERM_")`. The HTTP rule still checks `SCOPE_orders:read`.

**Answer:** Does not match. Align the rule with the mapping or keep the default prefix.

### Exercise 7: `permissions` claim

A JWT has `permissions: ["orders:read"]` and no `scope`/`scp`. Does the default converter grant `SCOPE_orders:read`?

**Answer:** No. Requires a custom claim mapping agreed upon by the IdP and resource server.

### Exercise 8: JWT from another API

A token has a valid `iss` and `docs:read` scope, but `aud` contains only `billing-api`. What should the `docs-api` Resource Server do?

**Answer:** Reject the token at **authentication** due to wrong audience; do not treat the scope as sufficient.

### Exercise 9: object-level authorization

Alice in T1 has `SCOPE_docs:read`; ID 21 is in T2. Is `@PreAuthorize("hasAuthority('SCOPE_docs:read')")` alone enough?

**Answer:** No. The repository must query using trusted tenant and object permissions.

### Exercise 10: Test using only `jwt().authorities(...)`

A test with `.with(jwt().authorities(SCOPE_docs:read))` passes, yet production fails to map `scp`. Why did the test miss it?

**Answer:** The test injects the authority directly into `Authentication`, bypassing the real JWT claims converter. You need converter unit tests and Bearer integration tests with a test decoder.

### Exercise 11: 401 or 403?

Unverified token: `401` is typical. Valid token missing scope: `403` is typical. Why the difference?

**Answer:** In the first case authentication failed; in the second case authentication succeeded, but authorization denied the operation.

### Exercise 12: JWT expires after role revocation

The JWT is unexpired, while the scope was revoked in the directory. Does the server automatically strip the scope from the already-issued token?

**Answer:** Not automatically. You need a revocation strategy, short TTL, introspection, or re-checking changed permissions at the policy/domain boundary.

### Exercise 13: opaque token

An opaque introspection response has `"scope":"orders:read orders:write"`. Can it produce `SCOPE_...`?

**Answer:** Yes, under the default opaque Resource Server scope mapping; no JWT parser is needed. However, custom claims require custom mapping.

### Exercise 14: client credentials

A token issued to a service account has scope `docs:write`. Can the backend by default write on behalf of any user/tenant?

**Answer:** No. Requires a principal/client identity policy, tenant scope, auditing, and object-specific permissions.

---

## 15. Resource Server implementation checklist

1. Verify the incoming token is an **access token** intended for this Resource Server.
2. Configure `issuer-uri` from a trusted Authorization Server.
3. Configure audience (`spring.security.oauth2.resourceserver.jwt.audiences`) for the real API.
4. Use JWT/JWK signature verification and validators; never parse payloads manually to grant access.
5. Check whether the IdP emits `scope` or `scp`, and whether its type is String or Collection.
6. Understand the default `SCOPE_` prefix and write exact authority names in policies.
7. Separate scopes and roles: `SCOPE_` does not automatically become `ROLE_`.
8. Apply `hasAuthority("SCOPE_...")` or OAuth2 `hasScope(...)` in the right places.
9. Enable `@EnableMethodSecurity` if protecting service methods.
10. Never use `.authenticated()` alone for permission-sensitive endpoints.
11. Place specific HTTP method/path rules first, with fallback deny afterward.
12. For tenant/object access, use a directory + tenant-scoped repository and ACLs.
13. For writes, check grant/owner/state/version close to the mutation inside a transaction.
14. If customizing claim/prefix, centralize the converter in one place and add negative tests.
15. Test the converter independently + HTTP Bearer integration through the filter/decoder.
16. Test invalid signature/issuer/audience/expired JWTs with a real decoder whenever possible.
17. Never let a test fake decoder leak into production runtime.
18. Never log raw access tokens, secrets, or full sensitive JWT claims.
19. Deliberately design token TTL/revocation, JWK rotation, and timeout/availability behavior.
20. Verify OAuth client credentials vs. user tokens, stable principal identities, and multi-issuer trust.
21. Review CSRF risk before disabling it, based on how the API actually receives credentials.
22. Test 401, 403, 404, and data immutability after denials per API contract.

---

## 16. Official references

1. [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): Bearer JWT verification, `scope`/`scp` mapping, `SCOPE_`, and custom `JwtAuthenticationConverter`.
2. [Spring Security 6.5 – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, scope mapping, and custom introspectors.
3. [Spring Security – JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): setters for claim, prefix, and delimiter.
4. [Spring Security – JwtAuthenticationConverter API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): JWT -> Authentication, principal claim, and authorities.
5. [Spring Security – JWT Authentication Token](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html): principal, name, and granted authorities.
6. [Spring Security – Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): GrantedAuthority, roles, and authorization decisions.
7. [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and AOP.
8. [Spring Security – Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `jwt()`/`opaqueToken()` test helpers and custom authorities.
9. [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.security.oauth2.resourceserver.jwt.audiences`.
10. [Spring Boot – OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): issuer/JWT resource server autoconfiguration.
11. [OAuth 2.0 Framework – RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): scope semantics and OAuth2 roles.
12. [OAuth2 Bearer Token Usage – RFC 6750](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer header and token errors.
13. [JWT – RFC 7519](https://www.rfc-editor.org/rfc/rfc7519): claims, registered claim names, and JWT structure.
14. [OAuth 2.0 JWT Access Token Profile – RFC 9068](https://www.rfc-editor.org/rfc/rfc9068): JWT access token guidance and resource server validation.
15. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and object-level checks.

**Conclusion:** In Spring Security OAuth2 Resource Server, access token **`scope` or `scp`** claims are converted by the default `JwtGrantedAuthoritiesConverter` into `GrantedAuthority` instances prefixed with **`SCOPE_`**. Write **`hasAuthority("SCOPE_docs:read")`** to require the `docs:read` scope, rather than confusing it with `hasRole("ADMIN")`. When an IdP uses different claims, configure a converter and test against the verified token schema; never disable signature/issuer/audience validation. Scopes are a functional authorization layer and **do not protect tenant/ACL/object ownership on their own**, so always combine them with repository/domain guards and verify both ALLOW and DENY cases.