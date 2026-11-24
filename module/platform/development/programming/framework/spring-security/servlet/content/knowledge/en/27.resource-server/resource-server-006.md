# `JwtAuthenticationConverter` and `JwtGrantedAuthoritiesConverter` in Spring Security Servlet

## 1. Goal of the Two Converters

In Spring Security Servlet's **JWT-based OAuth2 Resource Server**, the system receives a bearer access token, verifies the token, and builds an `Authentication` so rules like `hasAuthority(...)`, `hasRole(...)`, and `@PreAuthorize(...)` can decide access rights.

The two classes serve two different transformation layers:

- **`JwtGrantedAuthoritiesConverter`**: reads claims of an already-decoded `Jwt`, converting data such as `scope`/`scp` into `Collection<GrantedAuthority>`. By default each scope is prefixed with **`SCOPE_`**.
- **`JwtAuthenticationConverter`**: converts a `Jwt` into an `AbstractAuthenticationToken` (in practice usually `JwtAuthenticationToken`), attaches authorities from the child converter, and selects a claim as the principal name. By default the principal name comes from the `sub` claim.

This is the **identity and authority mapping step**, not the token signature verification step. Signature verification, expiration, issuer, and other validators belong to `JwtDecoder`/`OAuth2TokenValidator`. Never use a converter to “trust” an unverified JWT.

Example user token:

```json
{
  "iss": "https://auth.example.com/realms/demo",
  "sub": "user-42",
  "preferred_username": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ADMIN", "REVIEWER"],
  "exp": 1893456000
}
```

With the **default** converter, the authority set is typically:

```text
SCOPE_orders.read
SCOPE_orders.write
```

The `roles` claim **does not automatically** become `ROLE_ADMIN` or `ROLE_REVIEWER`. To use `hasRole("ADMIN")`, the application must explicitly map the role claim to `GrantedAuthority("ROLE_ADMIN")`, provided that the claim is issued by a trusted issuer and carries appropriate semantics.

## 2. Where Does the Converter Sit in the Authentication Flow?

A Servlet request to an endpoint configured with `oauth2ResourceServer().jwt()` follows this conceptual flow:

```text
Client -> GET /api/orders
          Authorization: Bearer eyJ...

  Spring Security filter chain (Servlet)
          |
          v
  BearerTokenAuthenticationFilter
          | extracts bearer token from request
          v
  JwtAuthenticationProvider
          |
          +-- JwtDecoder
          |     verifies signature, allowed algorithms, timestamp
          |     claims, and issuer per configuration/validators
          |
          v
  Jwt (verified by decoder)
          |
          v
  JwtAuthenticationConverter
          |
          +-- JwtGrantedAuthoritiesConverter
          |       scope/scp -> SCOPE_...
          |
          v
  JwtAuthenticationToken
          | Jwt principal, name, authorities
          v
  SecurityContext / AuthorizationFilter / method security
          |
          +-- sufficient authorities -> invoke Controller
          +-- missing authority -> 403 (typically)
```

When the bearer token is missing or invalid, Spring Security typically returns `401 Unauthorized` with an appropriate `WWW-Authenticate` header. If the token authenticated successfully but lacks an authority, it typically returns `403 Forbidden`. Final status codes depend on security entry points/handlers and upstream layers, so verify actual responses.

`JwtAuthenticationConverter` **never grants extra permissions** to a token on its own. It merely converts data **provided by the issuer and already validated by the decoder** into a form Spring Security understands. A misconfigured converter can cause valid users to receive `403`, or worse, grant overly broad permissions.

## 3. The Default `JwtGrantedAuthoritiesConverter`

Spring Security 6.x recognizes well-known authority claims such as `scope` and `scp`. The value may be a space-delimited string of scopes:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write"
}
```

Or a collection:

```json
{
  "sub": "alice",
  "scp": ["orders.read", "orders.write"]
}
```

By default, the converter reads **one recognized scope claim** and emits:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Therefore, an endpoint can declare:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders.read")
```

**Do not write `hasRole("orders.read")`** if you are using the default scope mapping: `hasRole` looks for `ROLE_orders.read`, not `SCOPE_orders.read`.

If a JWT contains both `scope` and `scp`, do not assume the framework always merges both. If you need explicit merge or precedence rules, normalize the token at the authorization server or write a suitable custom converter.

If a claim contains a comma-separated string `"orders.read,orders.write"`, the delimiter must be configured accordingly. `setAuthoritiesClaimDelimiter(...)` is available in Spring Security 6.1+; the default matches space-delimited scopes. Do not change the delimiter arbitrarily if the issuer follows the standard OAuth2 scope format.

## 4. Configuring Claim Name, Prefix, and Delimiter

`JwtGrantedAuthoritiesConverter` provides important options:

```java
JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

authorities.setAuthoritiesClaimName("permissions");
authorities.setAuthorityPrefix("PERM_");
```

When the token contains:

```json
{
  "permissions": ["invoices.read", "invoices.approve"]
}
```

The resulting authority set will contain:

```text
PERM_invoices.read
PERM_invoices.approve
```

The setters behave as follows:

| Setter | Purpose | Example |
| --- | --- | --- |
| `setAuthoritiesClaimName("roles")` | Select the **top-level** claim holding permissions | `roles: ["ADMIN"]` |
| `setAuthorityPrefix("ROLE_")` | Prefix prepended to each claim value | `ADMIN` → `ROLE_ADMIN` |
| `setAuthorityPrefix("")` | Keep values as-is, adding no prefix | `ROLE_ADMIN` → `ROLE_ADMIN` |
| `setAuthoritiesClaimDelimiter(",")` | Split rule for a **string** claim when issuer uses commas | `"a,b"` → `"a"`, `"b"` |

A single `JwtGrantedAuthoritiesConverter` reads one configured claim and applies one prefix to the output. If you switch the authorities claim from `scope` to `roles`, **you may drop all default `SCOPE_*` authorities** unless you actively combine both converters. That is one of the most common configuration mistakes.

A claim name like `"realm_access.roles"` **is not automatically interpreted as a JSON path** into a nested object. For nested payloads, write a dedicated converter that extracts the map/collection and accepts only expected data types.

## 5. `JwtAuthenticationConverter`: Authorities and Principal Name

`JwtAuthenticationConverter` lets you customize:

```java
JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(authorities);
authenticationConverter.setPrincipalClaimName("preferred_username");
```

`setJwtGrantedAuthoritiesConverter` controls **authorities**; `setPrincipalClaimName` controls `Authentication#getName()`.

Suppose the JWT contains:

```json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "roles": ["ADMIN"]
}
```

If the authorities converter reads `roles` with prefix `ROLE_`, `hasRole("ADMIN")` will match. If the principal claim is changed to `"preferred_username"`, `getName()` can return `"alice"` instead of `"user-42"`.

However:

- `getName()` is a chosen name for application use; changing the claim name **does not increase token trustworthiness**.
- `Authentication#getPrincipal()` for `JwtAuthenticationToken` is normally the `Jwt` object itself, not a `UserDetails` loaded from a database.
- `preferred_username` may change over time; if you need a stable identifier to link internal users, consider combining `iss + sub`, depending on your identity provider contract.
- If the chosen claim is absent or has an unexpected type, the resulting principal name may not match expectations. Test tokens with missing or mistyped claims.

Never use `preferred_username` or email as proof that a user holds the ADMIN role. Authorities must come from a properly issued authority claim after validating issuer/audience and verifying how the provider manages roles.

## 6. Standalone Java 17+ Example Running Without an Identity Provider

This example deterministically demonstrates the authorities produced by converters. The program **manually constructs a `Jwt` purely to illustrate mapping**—it does not read a real bearer token, verify signatures, or make HTTP requests. It is not a substitute for a production Resource Server configuration.

Create a Gradle project with the following `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.security:spring-security-oauth2-resource-server'
    implementation 'org.springframework.security:spring-security-oauth2-jose'
}

application {
    mainClass = 'demo.jwt.JwtConverterDemo'
}
```

Create `src/main/java/demo/jwt/JwtConverterDemo.java`:

```java
package demo.jwt;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class JwtConverterDemo {
    private JwtConverterDemo() {}

    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");

        // Mock Jwt for mapping illustration, NOT a token with a valid signature.
        Jwt jwt = Jwt.withTokenValue("demo-not-a-real-token")
                .header("alg", "RS256")
                .claim("sub", "user-42")
                .claim("preferred_username", "alice")
                .claim("scope", "orders.read orders.write")
                .claim("roles", List.of("ADMIN", "REVIEWER"))
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plusSeconds(3600))
                .build();

        JwtAuthenticationConverter defaults =
                new JwtAuthenticationConverter();
        AbstractAuthenticationToken defaultAuth = defaults.convert(jwt);

        System.out.println("default.name=" + defaultAuth.getName());
        System.out.println("default.authorities=" + names(defaultAuth));

        // Separate the scope and role sets.
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter combined =
                new JwtAuthenticationConverter();
        combined.setPrincipalClaimName("preferred_username");

        combined.setJwtGrantedAuthoritiesConverter(token -> {
            List<GrantedAuthority> granted = new ArrayList<>();
            granted.addAll(scopes.convert(token));
            granted.addAll(roles.convert(token));
            return granted;
        });

        AbstractAuthenticationToken combinedAuth = combined.convert(jwt);

        System.out.println("combined.name=" + combinedAuth.getName());
        System.out.println("combined.authorities=" + names(combinedAuth));
        System.out.println("canReadOrders=" +
                names(combinedAuth).contains("SCOPE_orders.read"));
        System.out.println("hasAdminRole=" +
                names(combinedAuth).contains("ROLE_ADMIN"));
    }

    private static List<String> names(AbstractAuthenticationToken auth) {
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
    }
}
```

Run from the project directory containing the Gradle wrapper:

```bash
./gradlew run
```

Windows PowerShell:

```powershell
.\gradlew.bat run
```

**Stdout of the Java program** (excluding Gradle lines):

```text
default.name=user-42
default.authorities=[SCOPE_orders.read, SCOPE_orders.write]
combined.name=alice
combined.authorities=[ROLE_ADMIN, ROLE_REVIEWER, SCOPE_orders.read, SCOPE_orders.write]
canReadOrders=true
hasAdminRole=true
```

Explanation: the default converter extracts scopes only; the combined converter extracts scopes **and** roles while changing the principal name to `preferred_username`. `sorted()` ensures deterministic stdout ordering for learning and testing. There is no `JwtDecoder` in this program: building a `Jwt` manually is **a way to test mapping**, not proof that a token is security-valid.

## 7. Configuration in a Spring Boot 3.3.x Resource Server (Servlet)

A real application with Spring MVC and a JWT Resource Server needs these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Illustrative `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/demo
```

This is an **example URI**. In real deployments, `issuer-uri` must point to the exact issuer the API trusts, with metadata/JWK support and matching algorithms/policies. This configuration lets the framework set up `JwtDecoder`, but **does not automatically turn a `roles` claim into `ROLE_*`**.

Create `src/main/java/demo/security/JwtSecurityConfig.java` inside a Spring Boot application that already has a main class and corresponding APIs:

```java
package demo.security;

import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtSecurityConfig {
    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<GrantedAuthority> granted = new ArrayList<>();
            granted.addAll(scopes.convert(jwt));
            granted.addAll(roles.convert(jwt));
            return granted;
        });
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(resource -> resource.jwt(jwt ->
                        jwt.jwtAuthenticationConverter(jwtConverter)))
                .build();
    }
}
```

**Points to understand before applying:**

1. `JwtDecoder` handles token validation; `JwtAuthenticationConverter` only determines principal/authorities after decoding.
2. `scopes` uses the default `scope`/`scp` and `SCOPE_` prefix; `roles` uses the `roles` claim and `ROLE_` prefix.
3. `hasAuthority("SCOPE_orders.read")` matches the exact authority string.
4. `hasRole("ADMIN")` matches `ROLE_ADMIN` per Spring Security's default role prefix.
5. `/api/admin/**` requires `ROLE_ADMIN`, so `roles: ["ADMIN"]` is trusted only if issuer and audience are properly validated.
6. This is **a configuration for a demo application**, not a class to drop alongside existing filter chains or converters without analyzing chain ordering and matchers.
7. The example does not disable CSRF. For a stateless API accepting only bearer tokens in the `Authorization` header, decide session and CSRF policies based on how clients actually send credentials; if cookies/sessions still exist, never disable CSRF indiscriminately.

### A Safe Claim-Reading Endpoint

Create a controller in the application with the Security bean above:

```java
package demo.security;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "subject", jwt.getSubject(),
                "issuer", String.valueOf(jwt.getIssuer()));
    }
}
```

`@AuthenticationPrincipal Jwt` accesses the authenticated `Jwt` in the Resource Server. Avoid returning the entire `getClaims()` map or raw JWT in responses: claims may hold sensitive data. `jwt.getSubject()` must exist if the app uses it as an identity; check the issuer's claim contract.

To make a real HTTP call:

```bash
curl -i https://api.example.com/api/me \
  -H "Authorization: Bearer <access-token-issued-by-idp>"
```

A successful result depends on a real API, issuer, valid JWT, and decoder configuration; since this example has no real token, **no fabricated HTTP output is shown**.

## 8. Controlling Claim Names and Normalizing Roles

There is no OAuth2 standard forcing every issuer to emit a `roles` claim under one exact schema. Some providers emit:

```json
{
  "roles": ["ADMIN", "USER"]
}
```

Others emit:

```json
{
  "realm_access": {
    "roles": ["ADMIN", "USER"]
  }
}
```

Or:

```json
{
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_REVIEWER"]
    }
  }
}
```

`setAuthoritiesClaimName("realm_access.roles")` does not traverse nested JSON along dots. For nested objects, write a custom `Converter<Jwt, Collection<GrantedAuthority>>` to extract the exact path and validate data types.

Illustrative snippet for a nested `realm_access.roles` claim:

```java
// Placed inside a method/config that has a jwt variable of type Jwt.
Map<String, Object> realm = jwt.getClaimAsMap("realm_access");
Object rawRoles = realm == null ? null : realm.get("roles");
List<GrantedAuthority> out = new ArrayList<>();

if (rawRoles instanceof Collection<?> items) {
    for (Object item : items) {
        if (item instanceof String role
                && role.matches("[A-Z][A-Z0-9_]{0,40}")) {
            out.add(new SimpleGrantedAuthority("ROLE_" + role));
        }
    }
}
```

This is an **illustrative snippet, not standalone**. You must import `Map`, `Collection`, `List`, `ArrayList`, `GrantedAuthority`, and `SimpleGrantedAuthority`. The regex is only an example internal format constraint—**it does not replace an allowlist of recognized roles**. With claims from multiple issuers, never assume the same `"ADMIN"` string carries equivalent permissions across issuers. Separate issuer/audience and map into a clearly designed internal permission set.

### Preventing Overly Broad Grants

Suppose a developer writes:

```java
roles.setAuthorityPrefix("");
```

while the rule uses `hasRole("ADMIN")`. The converter produces authority `"ADMIN"`, yet `hasRole("ADMIN")` requires `"ROLE_ADMIN"`; the result is `403`. Conversely, if the token already contains `"ROLE_ADMIN"` and you leave prefix `"ROLE_"`, the authority becomes `"ROLE_ROLE_ADMIN"`.

Pick **one standard contract**: either the token carries `ADMIN` and the converter prepends `ROLE_`, or the token already carries `ROLE_ADMIN` and the converter keeps it unchanged. Do not tweak role prefixes globally just to make one test pass before understanding the issuer's schema.

## 9. Testing Converters Without Real Signed JWTs

Separate testing **mapping** from testing **decoding/validation**. For mapping unit tests, you can construct an in-memory `Jwt` just like the program in section 6.

JUnit 5 example, added to the demo project from section 6:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create `src/test/java/demo/jwt/JwtConverterTest.java`:

```java
package demo.jwt;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtConverterTest {
    private Jwt jwt(String scope, List<String> roles) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue("fake-for-test")
                .header("alg", "RS256")
                .claim("sub", "alice")
                .claim("scope", scope)
                .claim("roles", roles)
                .issuedAt(issued)
                .expiresAt(issued.plusSeconds(600))
                .build();
    }

    @Test
    void defaultMappingAddsScopePrefix() {
        var auth = new JwtAuthenticationConverter()
                .convert(jwt("orders.read orders.write", List.of("ADMIN")));

        assertThat(auth.getAuthorities())
                .extracting("authority")
                .containsExactlyInAnyOrder(
                        "SCOPE_orders.read", "SCOPE_orders.write");
    }

    @Test
    void rolesMappingUsesRolePrefix() {
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(roles);

        var auth = converter.convert(jwt("orders.read", List.of("ADMIN")));
        assertThat(auth.getAuthorities())
                .extracting("authority")
                .containsExactly("ROLE_ADMIN");
    }

    @Test
    void absentRoleClaimDoesNotCreateAdminRole() {
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        Jwt token = Jwt.withTokenValue("fake-for-test")
                .header("alg", "RS256")
                .claim("sub", "bob")
                .claim("scope", "orders.read")
                .issuedAt(issued)
                .expiresAt(issued.plusSeconds(600))
                .build();

        assertThat(roles.convert(token)).isEmpty();
    }
}
```

Run:

```bash
./gradlew test
```

These tests build a `Jwt` in memory purely to prove the converter does not invent authorities absent from claims. They **do not** prove JWT signature validity or that the Spring Security filter chain authorizes HTTP requests properly. Add integration tests with `MockMvc` and Spring Security test support (e.g., JWT post-processor or stub JwtDecoder configuration) and verify `401`/`403`/`200` per endpoint. In real environments, test wrong issuer/audience/signature, expired tokens, missing scopes, and mistyped claims.

## 10. What Happens When a Claim Is Missing or Mistyped?

`JwtGrantedAuthoritiesConverter` is not a general-purpose JWT parser and not a place to coerce arbitrary malformed claims. Cases to test proactively:

| JWT / Configuration | Expected Authority | Consequence |
| --- | --- | --- |
| `scope: "orders.read"` | `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` can match |
| `scp: ["orders.read"]` | `SCOPE_orders.read` (default) | Useful when issuer emits an array |
| `roles: ["ADMIN"]` + `ROLE_` roles converter | `ROLE_ADMIN` | `hasRole("ADMIN")` can match |
| `roles` absent | No `ROLE_ADMIN` from that converter | Does not fabricate roles |
| `roles: ["ROLE_ADMIN"]` + `ROLE_` prefix | `ROLE_ROLE_ADMIN` | Contract mismatch, usually causes 403 |
| Custom converter reads `roles` only | No `SCOPE_orders.read` unless merged | Scope-based rules may fail |
| `realm_access.roles` inside nested object | Not resolved via dotted path | Needs a nested converter |
| `"scope": "orders.read,orders.write"` | Needs matching delimiter if issuer uses commas | Avoids one authority holding the entire string |

With mistyped claims, never silently coerce arbitrary objects into `"ADMIN"` via `toString()` or turn every string into an authority. Fail according to an explicit policy, log redacted diagnostics, and require the provider to emit tokens matching the schema.

## 11. Decoder, Issuer, and Audience Remain the Primary Security Barrier

Suppose an attacker crafts a JWT containing:

```json
{
  "sub": "attacker",
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
```

If an application simply runs the converter on this object without verifying the token, it sees `ROLE_ADMIN`. That **does not prove the attacker is authenticated**. Trust roles/scopes only after the token has passed a decoder with a valid signature, algorithm, timestamps, and issuer, and audience/scopes satisfy API requirements.

Configuring `issuer-uri` helps the framework identify a trusted issuer and use matching JWK/metadata, yet the API must still determine whether the JWT **was meant for this specific API**. Audience (`aud`) validation must be explicitly reviewed and configured per provider and framework version; never assume default issuer configuration automatically enforces your API's audience.

Complete security covers:

1. **Signature/algorithm:** accept only expected algorithms/keys; never trust an input `alg` header in a way that bypasses verification.
2. **Issuer:** token was issued by the right authorization server.
3. **Audience:** token is intended for your Resource Server.
4. **Time:** `exp`, `nbf`, and clock skew, plus optional token lifetime policies.
5. **Scopes/roles:** converter maps claims and `AuthorizationManager` enforces endpoint permissions.
6. **Token handling:** HTTPS only, never log bearer tokens, never forward tokens to downstream services outside the audience.
7. **Revocation:** with self-contained JWTs, revocation immediacy differs from opaque token introspection; design lifetimes and revocation strategies to match requirements.

Never treat `setAuthorityPrefix("ROLE_")` as verifying that a role actually exists in the business system. It merely constructs an authority string from validated JWT data.

## 12. Authorities, Permissions, and Method-Level Checks

In Spring Security, `GrantedAuthority#getAuthority()` is a permission string evaluated by authorization logic.

```java
.hasAuthority("SCOPE_orders.read")
.hasRole("ADMIN")
```

`hasRole("ADMIN")` by default checks for authority `"ROLE_ADMIN"`. `hasAuthority("ADMIN")` checks for exact `"ADMIN"`. The two expressions are not equivalent.

To use method security in Spring Security 6.x, enable it:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

You can then use it in appropriate services/controllers:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order findOrder(String id) {
    // Illustrative business logic; not a standalone method.
    return orderRepository.findById(id).orElseThrow();
}
```

This snippet assumes `Order`, `orderRepository`, and method security configuration already exist. `JwtAuthenticationConverter` supplies authorities to the `Authentication` inspected by method security, but enforcing access still requires object-level authorization: `orders.read` may allow reading the list, yet **does not mean a user can read every order belonging to another tenant**.

For multi-tenant resources, always verify tenant/resource ownership in the business layer. Never infer permissions from URL paths or a bare `"ADMIN"` role when an admin is actually scoped to their own tenant.

## 13. Common Pitfalls and Root-Cause Diagnosis

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Valid JWT yet endpoint returns `403` | Role claim unmapped, missing prefix, or missing scope | Inspect authorities after converter (do not log raw JWT) |
| `hasRole("ADMIN")` always fails | Authority is `"ADMIN"` instead of `"ROLE_ADMIN"`, or `"ROLE_ROLE_ADMIN"` | Inspect exact authority string |
| Has `roles`, lost `SCOPE_*` | Replaced default converter with role-only converter | Merge roles + scopes if the API needs both |
| Token uses `scp` yet converter looks for `permissions` | Wrong claim name | Verify payload schema and configuration |
| Token has nested roles yet converter misses them | `setAuthoritiesClaimName` is not JSONPath | Write a converter for nested structures |
| Authentication name unexpected | `sub` differs from `preferred_username`; missing principal claim | Check `setPrincipalClaimName` and issuer contract |
| `401` before reaching controller | Missing/malformed token, signature, issuer, expiration, Bearer parsing | Check decoder, `WWW-Authenticate`, and safe security debug |
| Has authority yet user still cannot read object | Additional business/tenant authorization | Check resource-level permissions; do not disable checks |
| API accepts tokens from another system | Loose issuer/audience validation | Lock down decoder, issuer, audience, and run negative tests |
| POST returns `403` while GET works | May be CSRF in a cookie-based app, not just roles | Distinguish CSRF from missing authorities |
| Junk authorities appear from claims | Custom converter uses `toString()` or overly broad prefixing | Accept only expected claim types with an authority allowlist |

In production, to diagnose permissions, you can temporarily log **normalized registration/issuer, safe user ID, and a bounded list of authorities** to internal logs with strict access controls. Never log access tokens, raw JWTs, claims containing PII, or private keys.

## 14. Designing Consistent Mapping Across Multiple Issuers

When an API accepts tokens from multiple identity providers, `"ADMIN"` from provider A may mean something different from provider B. Do not collapse both into a global `ROLE_ADMIN` without an explicit contract.

Key architectural questions:

- Which issuers does the API accept, and do they share the same audience?
- Is `scope`, `scp`, `roles`, or nested `resource_access` the standard claim for each provider?
- Are roles **global**, **client-level**, or **tenant-level**?
- Is that issuer authorized to grant this API's `"ADMIN"` role, or only roles within its own system?
- If using a unified internal authority set, who maintains the provider-role → permission mapping table and approves changes?
- Should a token missing key claims be rejected, or treated as authenticated with zero permissions?

Spring Security can use a custom `JwtAuthenticationConverter`, `AuthenticationManagerResolver`, or per-issuer decoders/validators for multi-issuer setups. You must verify that the token belongs to a trusted issuer **before** interpreting roles. Never use an unverified token's `iss` claim to grant elevated rights.

## 15. End-to-End Testing Steps

A practical testing plan for both learning and operations:

1. **Default mapping:** a mock JWT with `"scope": "orders.read"` must yield `SCOPE_orders.read`.
2. **Role mapping:** `"roles": ["ADMIN"]` must yield `ROLE_ADMIN` when defined by the contract.
3. **Combined mapping:** a JWT with both `scope` and `roles` must retain both groups without duplicating or adding unlisted permissions.
4. **Missing/invalid claims:** absent or mistyped roles must not produce `ROLE_ADMIN`.
5. **Principal:** verify `getName()` equals `sub` or the chosen claim; avoid using mutable usernames instead of immutable user IDs when linking data.
6. **HTTP authentication:** missing tokens or tokens with invalid signature/issuer/expiration return authentication errors; valid tokens with the right scope enter the endpoint.
7. **HTTP authorization:** valid tokens lacking `ROLE_ADMIN` cannot call admin APIs, typically returning 403.
8. **Audience:** tokens with valid signatures meant for another API must be rejected by the configured validator.
9. **Method/object security:** high-privilege authorities must still undergo tenant-ownership checks when required by business rules.
10. **Logging:** all tests must avoid leaking bearer tokens and private claims in responses or logs.

You can use `MockMvc` + `spring-security-test` to verify authorization rules, and separately test `JwtDecoder`/JWK with real or stub keys. Note: a test using the `jwt()` post-processor with pre-populated authorities **can bypass the very converter under test**. Unit test the converter directly as in section 9, or write tests that run through the resource server filter/decoder when the goal is verifying the full pipeline.

## 16. Configuration Checklist

Before shipping a custom converter to production, verify:

- `JwtDecoder` verifies signature/issuer, timestamps, and audience per the token contract.
- Scope/role claims originate from a trusted issuer and carry the right semantics for the API.
- `JwtAuthenticationConverter` is wired into the **right** `SecurityFilterChain` and resource server JWT configuration.
- `setAuthoritiesClaimName`, prefix, and delimiter match actual token schemas.
- When adding roles, `SCOPE_*` authorities are not accidentally dropped if rules still rely on scopes.
- `hasRole("X")` and `hasAuthority("ROLE_X")` are used consistently.
- Nested claims use a converter checking types and paths; dots in claim names are not treated as JSONPath.
- Principal names are stable for business logic; usernames/emails are not assumed immutable forever.
- Negative tests exist for unprivileged tokens, wrong issuer/audience, and empty/mistyped claims.
- Raw JWTs and secrets never appear in logs, responses, or metrics.

## Remember

`JwtGrantedAuthoritiesConverter` answers **“Which `GrantedAuthority` instances does this JWT produce?”**. `JwtAuthenticationConverter` answers **“From a verified JWT, how should an `Authentication` with principal and authorities be constructed?”**. By default Spring Security maps `scope`/`scp` to `SCOPE_*` and `sub` to the principal name. For custom roles/permissions, declare claims and prefixes explicitly, combine converters intentionally, and let `JwtDecoder` and authorization rules continue handling real security enforcement.