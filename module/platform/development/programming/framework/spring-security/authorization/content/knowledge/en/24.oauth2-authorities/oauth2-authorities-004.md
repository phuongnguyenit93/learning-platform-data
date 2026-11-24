# `hasAuthority` for Scopes and `hasRole` for Normalized Roles

## 1. The problem: OAuth2 scopes do not automatically become Spring Security roles

A valid OAuth2 access token may contain:

```json
{
  "iss": "https://idp.example.org",
  "sub": "alice",
  "aud": ["api://documents"],
  "scope": "documents.read documents.write",
  "app_roles": ["USER"]
}
```

With Spring Security Resource Server, scopes in a JWT are mapped by default into `GrantedAuthority` instances prefixed with `SCOPE_`. Accordingly, a token with `scope="documents.read documents.write"` typically produces:

```text
SCOPE_documents.read
SCOPE_documents.write
```

However, the `app_roles` claim in this example does **not automatically** become `ROLE_USER`. The Resource Server cannot know what `roles` or `app_roles` means across every identity provider. The application must configure role mapping according to the issuer contract.

Therefore, the two expressions:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
@PreAuthorize("hasRole('ADMIN')")
```

are not interchangeable. The first looks for the exact authority `SCOPE_documents.read`; the second, under the default role prefix, looks for `ROLE_ADMIN`. Both inspect `Authentication.getAuthorities()`, rather than inspecting raw JSON inside the JWT each time a method is invoked.

**Lesson objectives:** understand the difference between scopes, roles, and authorities; normalize roles safely; configure mapping for both `SCOPE_` and `ROLE_`; use `hasAuthority` and `hasRole` in HTTP/method security; test that roles and scopes are not mixed up; and avoid granting unintended privileges when a JWT carries untrusted claims.

## 2. Distinguishing scope, role, and GrantedAuthority

| Term | Example | Purpose |
| --- | --- | --- |
| OAuth2 scope | `documents.read` | Permission/capability granted to the access token for the API |
| Scope authority | `SCOPE_documents.read` | Form Spring Security typically creates from `scope`/`scp` |
| Application role | `ADMIN`, `AUDITOR` | Business responsibility group or entitlement |
| Role authority | `ROLE_ADMIN` | Form Spring Security expects by default with `hasRole('ADMIN')` |
| Object permission | Alice can READ Document 42 | Requires owner, ACL, tenant, state, or ABAC |
| Principal | `iss` + `sub` or internal identity | Who is being authenticated |
| Authentication | `JwtAuthenticationToken` | Principal, authentication state, and authorities |
| GrantedAuthority | `SimpleGrantedAuthority("ROLE_ADMIN")` | A concrete authority after authentication/mapping |

OAuth2 does not mandate that every token carry a `roles` claim. An IdP may use `groups`, `realm_access.roles`, `resource_access`, or a custom claim. Conversely, a client-credentials token can hold broad scopes while **carrying no end-user roles**. The application must clearly identify whether a role belongs to a user, client, tenant, or organization.

For example, an authentication has:

```text
Authentication.name = alice
Authentication.authorities =
    SCOPE_documents.read
    SCOPE_reports.export
    ROLE_USER
```

Here `hasAuthority('SCOPE_documents.read')` is true, `hasRole('USER')` is true, and `hasRole('ADMIN')` is false. Merely seeing `app_roles=["ADMIN"]` in the token does not make `hasRole('ADMIN')` true if the converter does not grant `ROLE_ADMIN`.

## 3. `hasAuthority` checks an exact authority

`hasAuthority(String)` checks whether the caller holds the exact matching `GrantedAuthority`. It **does not automatically prepend `SCOPE_` or `ROLE_`** to the input string.

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public DocumentView readDocument(String id) {
    return service.read(id);
}
```

With authorities `[SCOPE_documents.read, ROLE_USER]`:

| Expression | Default result |
| --- | --- |
| `hasAuthority('SCOPE_documents.read')` | true |
| `hasAuthority('documents.read')` | false |
| `hasAuthority('SCOPE_documents.write')` | false |
| `hasAuthority('ROLE_USER')` | true |
| `hasAuthority('USER')` | false |
| `hasAuthority('ROLE_ADMIN')` | false |

Use `hasAuthority('SCOPE_x')` for OAuth2 scopes when the converter uses defaults. If a project intentionally calls `JwtGrantedAuthoritiesConverter#setAuthorityPrefix("")`, authorities will lack `SCOPE_`, and every expression must align with that converter. With multiple authority kinds, keeping separate namespaces makes auditing easier.

### `hasAnyAuthority` and all-of checks

```java
@PreAuthorize(
    "hasAnyAuthority('SCOPE_documents.read','SCOPE_documents.audit')")
```

allows access when the caller holds **at least one** of the listed authorities. If business logic requires both scopes simultaneously, write an AND condition or use an API supporting all-of in your Spring Security version. Do not assume `documents.write` always implies `documents.read` based solely on its name: the OAuth2 issuer and API policy define that relationship.

## 4. `hasRole` adds the default role prefix

With the standard `ROLE_` prefix, the expression:

```java
@PreAuthorize("hasRole('ADMIN')")
```

looks for authority `ROLE_ADMIN`. It typically corresponds to:

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
```

when both use the same role hierarchy and no other customizations exist. However:

```java
@PreAuthorize("hasRole('documents.read')")
```

is **not equivalent** to `hasAuthority('SCOPE_documents.read')`; it targets `ROLE_documents.read` in the default configuration.

| Held authority | hasRole('ADMIN') | hasAuthority('ROLE_ADMIN') |
| --- | --- | --- |
| `ROLE_ADMIN` | true | true |
| `SCOPE_ADMIN` | false | false |
| `ADMIN` | false | false |
| `ROLE_ROLE_ADMIN` | false | false |
| `SCOPE_documents.read` | false | false |

Table assumes no role hierarchy or custom prefix.

In the Java request DSL, write `.hasRole("ADMIN")`, **not** `.hasRole("ROLE_ADMIN")`. Some request authorization implementations reject role strings that already start with `ROLE_`. To match `ROLE_ADMIN` literally, use `.hasAuthority("ROLE_ADMIN")`. In SpEL method security, `hasRole('ADMIN')` remains the most readable form.

### The role prefix can be customized

Spring Security supports `GrantedAuthorityDefaults`, and Spring Security 7.x provides `AuthorizationManagerFactory` to configure the role prefix for corresponding managers. If you change the prefix to `APP_ROLE_`, the converter must emit matching authorities; never change only one side and assume all HTTP/method expressions automatically align. Most projects do not need to change the default `ROLE_`.

## 5. How are JWT scopes converted to `SCOPE_` by default?

Per Spring Security Resource Server documentation, JWTs with a `scope` or `scp` claim are typically converted into `GrantedAuthority` instances with the `SCOPE_` prefix. For example:

```json
{
  "sub": "alice",
  "scope": "documents.read reports.export"
}
```

produces:

```text
SCOPE_documents.read
SCOPE_reports.export
```

Another issuer might use:

```json
{
  "sub": "bob",
  "scp": ["documents.read", "documents.write"]
}
```

and produce:

```text
SCOPE_documents.read
SCOPE_documents.write
```

Spring Security provides `JwtGrantedAuthoritiesConverter` for scope mapping and `JwtAuthenticationConverter` to build an `Authentication` from the decoded and validated token.

**Important:** a valid JWT means the token has been **verified** before trusting claims. Base64-decoding a token and reading `scope`/`roles` is insufficient; an attacker can craft an arbitrary payload.

Processing pipeline:

```text
Authorization: Bearer access-token
       |
       v
JwtDecoder
 - verify signature, key, algorithm
 - issuer and timestamps validation
 - audience/token purpose per API configuration
       |
       v
JwtAuthenticationConverter
 - JwtGrantedAuthoritiesConverter: scope/scp -> SCOPE_...
 - application role converter: issuer-controlled roles -> ROLE_...
       |
       v
JwtAuthenticationToken
 - principal / name
 - GrantedAuthorities
       |
       v
HTTP hasAuthority/hasRole
method @PreAuthorize
       |
       v
object/tenant policy before data access
```

Issuer and audience are two critical boundaries: a token with a valid signature issued for **another API** must not be accepted at this Resource Server. Spring Boot provides `issuer-uri` and `audiences` properties in supported versions, but you must still verify the exact schema and token type.

## 6. Role claims do not automatically become `ROLE_ADMIN`

Suppose a token contains:

```json
{
  "sub": "alice",
  "scope": "documents.read",
  "app_roles": ["ADMIN", "USER"]
}
```

The Resource Server's default scope converter does not treat `app_roles` as a role source. If the system wants `hasRole('ADMIN')`, it must add deliberate mapping.

Good design:

```text
scope / scp
  "documents.read"  -> "SCOPE_documents.read"

trusted app_roles
  "ADMIN"           -> "ROLE_ADMIN"
  "USER"            -> "ROLE_USER"
```

Do not write a single line like:

```java
JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();
scopes.setAuthorityPrefix("ROLE_");
```

to "make `hasRole` work." That line **changes the scope namespace** into `ROLE_documents.read` instead of adding a separate converter for roles; as a result, `hasAuthority('SCOPE_documents.read')` will fail. Worse, if the token has a scope named `ADMIN`, this misconfiguration creates `ROLE_ADMIN` unintentionally.

### What does a normalized role mean?

Before creating `ROLE_...`, satisfy these steps:

1. Token/identity is verified by a trusted issuer.
2. Role claim is in the expected location, with the right audience and token purpose.
3. Claim has the agreed data type, e.g., a list of strings.
4. Role names are checked against a **vocabulary and allow-list**.
5. Legacy/group names are mapped using an approved lookup table.
6. Distinguish platform roles from tenant-local roles.
7. Prepend `ROLE_` strictly once.
8. If the claim is missing/malformed/unknown, **grant no role**.
9. Write tests for revoked roles, new issuers, and tampered tokens.
10. Never read roles from client-supplied headers, request bodies, or cookies.

Examples from two issuers:

| Source | Raw role | Mapping |
| --- | --- | --- |
| IdP A, trusted claim | `ADMIN` | `ROLE_ADMIN` |
| IdP B, trusted group `/documents/admins` | group needs a dedicated mapper | Possibly `ROLE_ADMIN` per contract |
| Tenant alpha membership | `OWNER` | OWNER permission within **alpha**, not default global ADMIN |
| Client `X-Role` | `ADMIN` | Untrusted |
| Raw claim `ROLE_ADMIN` when contract expects `ADMIN` | invalid format | Grant no authority |

Do not simply call `toUpperCase()` and accept arbitrary strings; unknown roles must never be "normalized into validity."

## 7. Truth table: scopes and roles are independent conditions

Suppose only two authorities are used: `SCOPE_documents.read` and `ROLE_ADMIN`:

| Token after mapping | hasAuthority('SCOPE_documents.read') | hasRole('ADMIN') |
| --- | --- | --- |
| `[SCOPE_documents.read]` | true | false |
| `[ROLE_ADMIN]` | false | true |
| `[SCOPE_documents.read, ROLE_ADMIN]` | true | true |
| `[SCOPE_ADMIN]` | false | false |
| `[ROLE_USER]` | false | false |
| `[]` | false | false |

For an admin document export endpoint:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_documents.export') and hasRole('ADMIN')")
```

this expression requires **both the export scope and the ADMIN role**. A token carrying only the ADMIN role cannot bypass client scopes. Conversely, the export scope alone does not turn the caller into an admin.

An example requiring only one of the two grants:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.read') or hasRole('AUDITOR')")
```

is valid only when business logic **explicitly approves** AUDITOR bypassing the scope. Never use OR merely to paper over a 403 caused by broken mapping.

## 8. Dependency-free Java 17: simulating semantics with stdout

To see the exact distinction, start with a standalone Java 17 program. It simulates authority matching (it is not Spring Security's implementation and **does not verify JWTs**).

File `ScopeRoleSemanticsLab.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class ScopeRoleSemanticsLab {

    record Principal(String subject, Set<String> authorities) {}

    private static Principal mapped(
            String subject,
            List<String> scopes,
            List<String> trustedCanonicalRoles) {

        Set<String> allowlisted = Set.of("USER", "AUDITOR", "ADMIN");
        Set<String> result = new LinkedHashSet<>();

        for (String scope : scopes) {
            if (scope != null && !scope.isBlank()) {
                result.add("SCOPE_" + scope);
            }
        }
        for (String role : trustedCanonicalRoles) {
            if (allowlisted.contains(role)) {
                result.add("ROLE_" + role);
            }
        }
        return new Principal(subject, Set.copyOf(result));
    }

    static boolean hasAuthority(Principal principal, String exact) {
        return principal.authorities().contains(exact);
    }

    static boolean hasRole(Principal principal, String role) {
        return hasAuthority(principal, "ROLE_" + role);
    }

    private static void show(String label, Principal principal) {
        System.out.println(label
                + ": read=" + hasAuthority(
                    principal, "SCOPE_documents.read")
                + ", admin=" + hasRole(principal, "ADMIN")
                + ", bare=" + hasAuthority(
                    principal, "documents.read"));
    }

    public static void main(String[] args) {
        show("alice", mapped("alice",
                List.of("documents.read"), List.of("USER")));
        show("bob", mapped("bob",
                List.of("documents.read"), List.of("ADMIN")));
        show("bot", mapped("bot",
                List.of("ADMIN"), List.of()));
        show("unknown", mapped("eve",
                List.of("documents.read"),
                List.of("ROLE_ADMIN", "OTHER")));
    }
}
```

Run:

```bash
javac ScopeRoleSemanticsLab.java
java ScopeRoleSemanticsLab
```

Expected stdout:

```text
alice: read=true, admin=false, bare=false
bob: read=true, admin=true, bare=false
bot: read=false, admin=false, bare=false
unknown: read=true, admin=false, bare=false
```

- Alice has the read scope, but not the ADMIN role.
- Bob has the read scope and the canonical ADMIN role, so both checks succeed.
- Bot has a **scope named ADMIN**, but not `ROLE_ADMIN`.
- A role claim `ROLE_ADMIN` fails canonical vocabulary validation, neither producing `ROLE_ROLE_ADMIN` nor getting "fixed" into admin.
- The `mapped` function is strictly educational. Production code must never accept unverified scopes/roles from clients and pass them here; all values must come from a trusted authentication/authorization boundary.

## 9. Spring Security converter: keeping scopes and roles in separate namespaces

Spring Security 6.x provides `JwtGrantedAuthoritiesConverter`, `DelegatingJwtGrantedAuthoritiesConverter`, and `JwtAuthenticationConverter`. We use a default converter for scopes and a dedicated converter for normalized role claims.

File `JwtAuthorityConfiguration.java`:

```java
package example.auth;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityConfiguration {

    private static final Set<String> ALLOWED_ROLES =
            Set.of("USER", "AUDITOR", "ADMIN");

    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        // Do not change prefix: JWT scope/scp -> SCOPE_...
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> roles =
                JwtAuthorityConfiguration::rolesFromTrustedClaim;

        DelegatingJwtGrantedAuthoritiesConverter combined =
                new DelegatingJwtGrantedAuthoritiesConverter(
                        scopes, roles);

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }

    private static Collection<GrantedAuthority>
            rolesFromTrustedClaim(Jwt jwt) {

        Object raw = jwt.getClaims().get("app_roles");
        if (!(raw instanceof List<?> values)) {
            return List.of();
        }

        Set<GrantedAuthority> authorities =
                new LinkedHashSet<>();

        for (Object item : values) {
            if (item instanceof String role
                    && ALLOWED_ROLES.contains(role)) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return List.copyOf(authorities);
    }
}
```

This is a **complete Java configuration file**, assuming the Resource Server's `JwtDecoder` has already validated the token. `ALLOWED_ROLES` validates only **role names**, not the signature or authoritativeness of the issuer. The `app_roles` claim must be issuer-governed, not user-editable metadata or a client-set header.

Key behaviors:

- `scope="documents.read"` → `SCOPE_documents.read`.
- `app_roles=["ADMIN"]` → `ROLE_ADMIN`.
- `scope="ADMIN"` → `SCOPE_ADMIN`, never automatically `ROLE_ADMIN`.
- `app_roles=["ROLE_ADMIN"]` → **does not grant ADMIN** because it is not in the unprefixed allow-list.
- `app_roles=["admin"]` → **not granted** if the contract requires uppercase.
- Missing/wrongly typed `app_roles` → grants no roles.
- A single token can carry **both** scope authorities and role authorities.
- Unknown roles are ignored, though ignoring them is never proof of cryptographic token validity.

### Nested role claims

If the IdP uses:

```json
{
  "realm_access": {
    "roles": ["administrator", "reader"]
  }
}
```

do not assume `setAuthoritiesClaimName("realm_access.roles")` understands nested JSON paths across all versions. Write a type-checking converter:

```java
Object root = jwt.getClaims().get("realm_access");
if (root instanceof java.util.Map<?, ?> data) {
    Object roles = data.get("roles");
    if (roles instanceof List<?> values) {
        // Validate issuer contract + role allowlist.
    }
}
```

This is an integration snippet. Across multiple issuers or clients, a role like `administrator` can mean different things; mapping must honor the exact trusted issuer/audience and resource server.

## 10. Configuring `HttpSecurity`: roles in HTTP, scopes at the method layer

File `ApiSecurityConfiguration.java`:

```java
package example.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    public SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                        HttpMethod.GET, "/api/http/admin")
                .hasRole("ADMIN")
                .requestMatchers(
                        HttpMethod.GET, "/api/**")
                .authenticated()
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                        converter)));

        return http.build();
    }
}
```

With this configuration:

- `GET /api/http/admin` is directly protected by HTTP `hasRole("ADMIN")`.
- Other GET `/api/**` routes require only `authenticated()` at the HTTP layer, so 403 tests on service `@PreAuthorize` prove **method security** actually enforces rules.
- `@EnableMethodSecurity` enables method-level annotations on Spring-managed beans.
- `JwtAuthenticationConverter` is injected into Resource Server so tokens pass through the scope and role mappers.
- Matcher order matters; specific rules must precede `/api/**`.
- `anyRequest().denyAll()` blocks any HTTP routes without an explicit policy.

The example config protects only GET endpoints and has no browser-cookie workflow. If adding POST/PUT/DELETE or session/cookie authentication, design appropriate CSRF and session policies. Never turn "REST API" into an excuse to disable CSRF in every architecture.

## 11. Method security: read scope and admin role

Services for the learning example:

```java
@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public String read(String documentId) {
        return "doc:" + documentId;
    }
}

@Service
class AdminService {

    @PreAuthorize("hasRole('ADMIN')")
    public String status() {
        return "admin-ok";
    }
}
```

This source belongs in `DemoController.java` in the project below; do not create a second file with duplicate classes when copying the project.

For services using `@PreAuthorize`, calls must pass through the Spring AOP proxy. If a method inside the same bean calls `this.protectedMethod()`, advice can be bypassed. If a controller calls `new DocumentService()`, that instance is not Spring-proxied.

**Do not substitute `hasRole('ADMIN')` for the read scope to "let admins read" unless business policy explicitly permits bypassing client-scoped permissions.** A user with the ADMIN role whose token lacks `SCOPE_documents.read` must still be blocked by scope policy.

Also, this method returns illustrative text only. Production code must check document owner/tenant/ACL and query with tenant predicates; `SCOPE_documents.read` only proves the token is allowed to **invoke the read capability**.

## 12. Maven Java 17 project testing both the converter and HTTP/method guards

The project uses Spring Boot 3.5.16 (BOM-managed Spring Security 6.x), Java 17, Spring MVC Servlet Resource Server, and JUnit 5. Release 3.5.16 is real, though that Boot branch has reached end of OSS support; new production systems should use a currently supported branch. The project is an **educational example**, not production deployment code.

Structure:

```text
oauth-scope-role-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/auth/
    │   │   ├── ScopeRoleLabApplication.java
    │   │   ├── JwtAuthorityConfiguration.java
    │   │   ├── ApiSecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/
        └── java/example/auth/
            └── ScopeRoleLabTest.java
```

`JwtAuthorityConfiguration.java` and `ApiSecurityConfiguration.java` were presented in full in Sections 9–10. Do not create duplicate copies of those two classes.

### 12.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>oauth-scope-role-lab</artifactId>
    <version>1.0.0</version>

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
</project>
```

### 12.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/documents
          audiences:
            - api://documents
```

The URI/issuer/audience are **example values**, not a real IdP. To run a real server, replace them with a real issuer, configure keys/JWKS, audience, time validators, and the scope claim contract. In the integration tests below, a test-only `JwtDecoder` is created to test the converter/guards without network access; it **does not verify real JWT signatures**.

### 12.3. `ScopeRoleLabApplication.java`

```java
package example.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeRoleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScopeRoleLabApplication.class, args);
    }
}
```

### 12.4. `DemoController.java`

```java
package example.auth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final DocumentService documents;
    private final AdminService admins;

    public DemoController(
            DocumentService documents,
            AdminService admins) {
        this.documents = documents;
        this.admins = admins;
    }

    @GetMapping("/documents/{id}")
    public String document(@PathVariable String id) {
        return documents.read(id);
    }

    @GetMapping("/method/admin")
    public String methodAdmin() {
        return admins.status();
    }

    @GetMapping("/http/admin")
    public String httpAdmin() {
        return "http-admin-ok";
    }
}

@Service
class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public String read(String id) {
        return "doc:" + id;
    }
}

@Service
class AdminService {

    @PreAuthorize("hasRole('ADMIN')")
    public String status() {
        return "admin-ok";
    }
}
```

Services are Spring-managed beans constructor-injected into the controller, so `@PreAuthorize` is enforced via AOP proxies. Route `/api/http/admin` uses HTTP `hasRole("ADMIN")`, while `/api/method/admin` requires only `authenticated()` at HTTP and relies on method security to reject missing roles.

### 12.5. `ScopeRoleLabTest.java`

```java
package example.auth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(ScopeRoleLabTest.StubJwtDecoderConfig.class)
class ScopeRoleLabTest {

    @Autowired MockMvc mvc;
    @Autowired JwtAuthenticationConverter converter;

    @Test
    void scopeReaderCanRead() throws Exception {
        mvc.perform(get("/api/documents/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer reader"))
           .andExpect(status().isOk())
           .andExpect(content().string("doc:42"));
    }

    @Test
    void adminWithoutReadScopeCannotRead() throws Exception {
        mvc.perform(get("/api/documents/42")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isForbidden());
    }

    @Test
    void scopeReaderIsNotAdmin() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer reader"))
           .andExpect(status().isForbidden());
    }

    @Test
    void canonicalAdminCanUseMethodGuard() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isOk())
           .andExpect(content().string("admin-ok"));
    }

    @Test
    void canonicalAdminCanUseHttpGuard() throws Exception {
        mvc.perform(get("/api/http/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
           .andExpect(status().isOk())
           .andExpect(content().string("http-admin-ok"));
    }

    @Test
    void scopeNamedAdminIsNotAdminRole() throws Exception {
        mvc.perform(get("/api/http/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer scope-admin"))
           .andExpect(status().isForbidden());
    }

    @Test
    void wrongRoleVocabularyCannotEscalate() throws Exception {
        mvc.perform(get("/api/method/admin")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer bad-role"))
           .andExpect(status().isForbidden());
    }

    @Test
    void missingTokenIsUnauthenticated() throws Exception {
        mvc.perform(get("/api/documents/42"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void converterDoesNotMixNamespaces() {
        Jwt jwt = StubJwtDecoderConfig.jwt(
                "unit", "alice", "documents.read",
                List.of("ADMIN", "UNLISTED", "ROLE_ADMIN"));

        Set<String> values = converter.convert(jwt)
                .getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

        assertTrue(values.contains("SCOPE_documents.read"));
        assertTrue(values.contains("ROLE_ADMIN"));
        assertFalse(values.contains("SCOPE_ADMIN"));
        assertFalse(values.contains("ROLE_ROLE_ADMIN"));
        assertFalse(values.contains("ROLE_UNLISTED"));
    }

    @TestConfiguration
    static class StubJwtDecoderConfig {

        @Bean
        @Primary
        JwtDecoder stubDecoder() {
            return token -> switch (token) {
                case "reader" -> jwt(
                        token, "alice", "documents.read",
                        List.of("USER"));
                case "admin" -> jwt(
                        token, "alice", null,
                        List.of("ADMIN"));
                case "scope-admin" -> jwt(
                        token, "alice", "ADMIN",
                        List.of());
                case "bad-role" -> jwt(
                        token, "alice", "documents.read",
                        List.of("ROLE_ADMIN", "UNLISTED"));
                default -> throw new BadJwtException(
                        "Unknown test token");
            };
        }

        static Jwt jwt(String token, String subject,
                       String scope, List<String> roles) {
            Jwt.Builder builder = Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .claim("sub", subject)
                    .claim("app_roles", roles);
            if (scope != null) {
                builder.claim("scope", scope);
            }
            return builder.build();
        }
    }
}
```

**Why use a stub `JwtDecoder`?** So real HTTP requests pass through `BearerTokenAuthenticationFilter`, `JwtAuthenticationConverter`, and method/HTTP guards without calling an external IdP. The stub token `"reader"` is not a signed JWT; it is accepted only in the test context. **Never copy a stub decoder to production.** Real tests for signature/issuer/audience require a dedicated suite with real signing and a real `JwtDecoder`.

Run:

```bash
java -version
mvn -version
mvn -q clean test
```

Expected are **nine JUnit 5 tests**: scope reader can read; admin role cannot replace read scope; scope cannot replace role; method/HTTP `hasRole` agrees when `ROLE_ADMIN` is present; scope `ADMIN` does not become a role; invalid raw roles cannot escalate; unauthenticated request receives 401; converter emits exact authorities. Maven output depends on the environment, so do not fabricate Maven stdout.

**Limitations of the example:** does not yet implement a data repository/tenant layer, does not test cryptographic JWT validation, and does not demonstrate an authorization server. Use it solely as a foundation for learning authority mapping and checking.

## 13. Why test the converter separately alongside HTTP tests?

There are several ways to create mock authentication in tests, and not all of them invoke the real converter.

```java
mvc.perform(get("/api/documents/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
   .andExpect(status().isOk());
```

This is a **Spring Security Test snippet**. The `jwt()` request post-processor typically creates a test authentication that can bypass the configured Resource Server `JwtDecoder` and converter. It is great for testing HTTP authorization, but **does not prove issuer-token role mapping**.

Similarly, `@WithMockUser(roles = "ADMIN")` creates `ROLE_ADMIN` for a test without proving that a real JWT carrying the ADMIN role will be converted into that authority. You need four layers:

1. **Converter unit tests:** given `Jwt` test objects, assert exact scope/role authorities.
2. **Filter/method integration tests:** with a test decoder, assert 200/403/401 across real requests.
3. **Decoder cryptography tests:** with signed JWTs and test keys, wrong signature/issuer/audience/expiry must be rejected.
4. **Object authorization tests:** even with valid scopes/roles, callers must not read resources owned by other owners/tenants.

In DENY test branches, assert not only the HTTP status but also **zero side effects** on write APIs; returning HTTP 403 after mutating the database is insecure.

## 14. Tenant-scoped roles are not global `ROLE_ADMIN`

A user with `OWNER` permission in tenant `alpha` does not automatically hold `ADMIN` permission across the entire platform.

```json
{
  "sub": "alice",
  "scope": "documents.read",
  "tenant": "alpha",
  "tenant_role": "OWNER"
}
```

If the app maps `tenant_role=OWNER` into an unscoped global authority `ROLE_ADMIN`, the caller can exceed boundaries when accessing `beta`.

A fuller policy:

```text
ALLOW document READ
  = authenticated
  AND hasAuthority("SCOPE_documents.read")
  AND activeMembership(subject, authorizedTenant)
  AND resource.tenantId == authorizedTenant
  AND (isOwner(subject, resource) OR isShared(subject, resource))
```

If tenant-specific admin is needed, use a service policy `tenantPolicy.isAdmin(auth, tenant)` or canonical tenant-bound authorities checked against the resource's tenant, rather than global `hasRole('ADMIN')`.

SQL must bind the tenant:

```sql
SELECT id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant;
```

`hasAuthority('SCOPE_documents.read')` only authorizes the read capability per token; it **does not add a WHERE clause** and does not prove record 42 belongs to tenant `alpha`. This is the separation between function-level and object-level authorization.

## 15. OAuth2 Client, OIDC login, and opaque tokens differ from JWT Resource Server

Different Spring Security components construct `Authentication` differently:

| Scenario | Mechanism | What to check |
| --- | --- | --- |
| JWT Resource Server | `JwtDecoder`, `JwtAuthenticationConverter` | Scopes usually become `SCOPE_`; roles require mapping |
| Opaque Resource Server | Introspection + authenticated principal | Introspection scopes usually become `SCOPE_`; role mapping depends on policy |
| OAuth2 Login | `OAuth2AuthenticationToken`/`OAuth2User` | Authorities may include `OAUTH2_USER` plus mapped authorities |
| OIDC Login | `OidcUser` / authentication | Do not assume every ID token role is an API bearer authority |
| In-memory user | `UserDetailsService` | `roles("ADMIN")` creates `ROLE_ADMIN`, but proves nothing about JWT converters |
| Mock principal in tests | `@WithMockUser` | Authorities are manually set by the test |

Do not assume an OIDC-logged-in user automatically has the same `SCOPE_...` and `ROLE_...` authorities as a JWT resource server request. If a project combines OAuth2 client and resource server, verify the request filter chain and `Authentication` type before writing expressions.

For opaque tokens, introspection must target a trusted endpoint and scope/role mapping must follow a clear contract. When introspection times out, the system must fail closed rather than issuing fake scopes/roles.

## 16. WebFlux: same concepts, different security DSL

WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`, reactive authentication, and `ReactiveSecurityContextHolder`. However, authority names can still be `SCOPE_documents.read` and `ROLE_ADMIN`.

Reactive HTTP configuration pattern:

```java
@Bean
SecurityWebFilterChain reactiveSecurity(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/documents/**")
            .hasAuthority("SCOPE_documents.read")
            .pathMatchers(HttpMethod.GET, "/api/admin/**")
            .hasRole("ADMIN")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
```

This is an **integration snippet**, not part of the MVC project above. It requires reactive Spring Security, Reactor, and `Converter` imports. You can use `ReactiveJwtAuthenticationConverterAdapter` to wrap a synchronous `JwtAuthenticationConverter` for WebFlux, or write a reactive converter directly.

Reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodConfig {
}

@Service
class ReactiveDocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public Mono<String> read(String id) {
        return Mono.just("doc:" + id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

Spring-managed beans and Reactor Context must be wired properly. Never read thread-local `SecurityContextHolder` expecting the current identity on worker threads; never call `block()` on an event-loop thread to "check roles first."

## 17. `hasAnyRole`, role hierarchy, and changing the prefix

`hasAnyRole('AUDITOR','ADMIN')` checks for one of the listed roles; `hasAnyAuthority('SCOPE_a','SCOPE_b')` checks for one of the listed authorities. Both serve business policies, and **choosing OR vs. AND is a security decision**, not a syntax detail.

Example:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export') " +
    "and hasAnyRole('ADMIN','AUDITOR')")
```

The token must carry the export scope and at least one of the two roles. With only the READ scope, export is denied. With the ADMIN role alone and no export scope, export is also denied.

Spring Security supports `RoleHierarchy`, such as `ROLE_ADMIN > ROLE_AUDITOR`. When wired into the appropriate manager/expression handler, `ADMIN` satisfies `AUDITOR`. However, a hierarchy **does not automatically expand `ROLE_ADMIN` into every `SCOPE_*`**; bypassing scopes requires an explicitly approved policy.

Example `GrantedAuthorityDefaults`:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("ROLE_");
}
```

This bean illustrates the default role prefix in method security. Changing `ROLE_` to another string requires updating the converter at the same time and testing both HTTP and method authorization managers. In Spring Security 7.x, some managers use `AuthorizationManagerFactory` to configure role prefixes; do not assume one customization affects every layer or version uniformly.

## 18. Multiple issuers and clients: preventing role collisions

The same `app_roles=["ADMIN"]` claim can appear across multiple issuers:

- Issuer A: `ADMIN` means docs platform administrator.
- Issuer B: `ADMIN` means a partner's private portal administrator.
- Client credentials token: carries `ADMIN` in metadata without representing an end user.

Without binding issuer/audience/client trust, the app may grant `ROLE_ADMIN` to an out-of-scope caller. For multi-issuer setups:

1. Accept only issuers on an explicit allow-list.
2. Verify the real issuer via an appropriate JWT decoder before reading roles.
3. Verify this API's audience.
4. Maintain separate role mappings per trusted issuer/application.
5. Namespace `(issuer, subject)` when resolving internal principals.
6. Never map tenant-local permissions to global roles.
7. Set expiry/revocation SLAs for roles and memberships.
8. Write tests with identical `sub` values from two different issuers.

Never use `X-Tenant-Id`, `X-Role`, or query parameters to elevate permissions. Even in a validly signed token, user-editable profile roles from an IdP may not qualify as strong authorities; claim sources must have appropriate governance.

## 19. Common errors and fixes

| Issue | Cause | Fix |
| --- | --- | --- |
| JWT scope READ, `hasRole` READ returns 403 | `hasRole` looks for `ROLE_READ` | Use `hasAuthority('SCOPE_documents.read')` |
| JWT scope READ, `hasAuthority` bare read returns 403 | Converter prepended `SCOPE_` | Use the full authority name |
| JWT `app_roles` ADMIN, `hasRole` ADMIN returns 403 | Role claim not mapped yet | Configure a trusted role converter |
| Role becomes `ROLE_ROLE_ADMIN` | Double prefix | Canonical role input must contain only `ADMIN` |
| Scope becomes `ROLE_documents.read` | Scope converter prefix was altered | Keep `SCOPE_`, build a separate role converter |
| JWT has `SCOPE_ADMIN`, `hasRole` ADMIN still false | Scope differs from role | Intended behavior; do not escalate |
| HTTP allows, method returns 403 | Method guard requires another scope/role | Test each layer |
| Converter test green, real token returns 401 | JWT signature/issuer/audience failed | Check decoder/token |
| `@WithMockUser` ADMIN test green, JWT ADMIN fails | Mock bypassed converter | Unit test JWT converter + integration test |
| Tenant alpha admin reads beta | Global role lacks tenant isolation | Enforce membership/resource tenant policy |
| Missing token scope | No `scope`/`scp` matching contract | Check issuer schema |
| Nested claim token roles | Converter does not read nested maps | Write a type-safe converter |
| Unknown role becomes admin | Fuzzy mapping, auto-uppercase | Allow-list and formal mapping table |
| Recently revoked token still holds role | JWT/cache unexpired | Short TTL, introspection, entitlement revision |

To diagnose a 403, check in order: Was the token authenticated? Does the token have the right audience? What is the `Authentication` type? What does `getAuthorities()` actually contain? Does the converter use the right claim name and prefix? Which HTTP or method guard denied access? Is an additional object/tenant policy denying it?

Never fix a 403 by adding `permitAll()`, `or hasRole('ADMIN')`, or removing `@PreAuthorize` without first determining why the authority was missing.

## 20. Recommended test suite

| Scenario | Expected outcome |
| --- | --- |
| JWT scope `documents.read` | `SCOPE_documents.read` granted |
| JWT scope `documents.write` | Does not imply read scope |
| JWT `app_roles` ADMIN | `ROLE_ADMIN` granted per contract |
| ADMIN role without read scope | Document read DENIED |
| Read scope without ADMIN role | Admin method DENIED |
| Token scope named `ADMIN` | Does not grant `ROLE_ADMIN` |
| `app_roles` contains `ROLE_ADMIN` (raw prefix) | Does not grant `ROLE_ROLE_ADMIN` |
| Unknown `app_roles` | No unknown role granted |
| Wrongly typed/null `app_roles` | No role granted |
| Token with no scope/role | Protected route/method DENIED |
| Unauthenticated | 401 |
| Invalid token signature | 401/invalid token |
| Wrong token issuer | 401 |
| Wrong token audience | 401 |
| Expired token | 401 |
| Trusted role outside tenant | Object/tenant policy DENIES |
| READ scope for another owner's document | Object policy DENIES |
| Role hierarchy `ADMIN>AUDITOR` | Verified on the configured manager |
| User has role, method called via self-invocation | Test catches proxy bypass |
| Two issuers where ADMIN means different things | No privilege collision |
| Cached authority after revocation | Within revocation SLA |

Note that tests in the sample project cover only the scope/role mapper and HTTP/method guards. You must add decoder cryptography tests with signed test JWTs, database tenant/object tests, and regression tests after upgrading Spring Security/BOM.

## 21. Adoption checklist

- [ ] Distinguish OAuth2 scopes, business roles, `GrantedAuthority`, and object permissions.
- [ ] `JwtDecoder` verifies signature, issuer, audience, expiry/`nbf`, and token purpose.
- [ ] Scopes use the `SCOPE_` prefix by default; expressions use exact authority names.
- [ ] Roles come from **issuer-controlled claims** per contract, never from client input.
- [ ] Role mapper enforces a clear allow-list/normalization and adds `ROLE_` strictly once.
- [ ] Never apply a `ROLE_` converter prefix to OAuth scopes if preserving the scope namespace.
- [ ] Use `hasRole('ADMIN')` only for normalized roles with clear semantics.
- [ ] Use `hasAuthority('SCOPE_x')` for OAuth2 scopes, never `hasRole('x')` as a substitute.
- [ ] AND/OR between scopes and roles reflects deliberate policy, not a 403 workaround.
- [ ] Enable and separately test both HTTP `SecurityFilterChain` and method security.
- [ ] Verify `RoleHierarchy`/custom prefixes against the exact managers and version in use.
- [ ] Enforce tenant/owner/ACL/resource state in services and repositories.
- [ ] Never use global `ROLE_ADMIN` for roles scoped to a single tenant.
- [ ] Positive authorization caches have bounded TTLs and revocation/invalidation strategies.
- [ ] Maintain full converter unit tests, negative HTTP/method tests, and signed JWT decoder tests.
- [ ] Never use mock authorities in tests as proof of cryptographic validation.
- [ ] Ensure error/audit logs omit raw JWTs, client secrets, and unnecessary PII.

**Conclusion:** Both `hasAuthority` and `hasRole` inspect `GrantedAuthorities`, yet they represent two distinct permission sources. With default Spring Security OAuth2 Resource Server, the `documents.read` scope becomes `SCOPE_documents.read` and is checked via `hasAuthority('SCOPE_documents.read')`. An application role `ADMIN` must be **verified, normalized, and mapped** to `ROLE_ADMIN` before `hasRole('ADMIN')` is meaningful. Never turn scopes into roles automatically, never let roles bypass client scopes, and never treat either as sufficient to skip tenant/object authorization.

## Official references

- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtAuthenticationConverter JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security — GrantedAuthorityDefaults JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
