# Mapping Claims or Scopes to `GrantedAuthority` in Bearer Tokens

## 1. Lesson Objectives

When a Spring Security API receives `Authorization: Bearer <access-token>`, **token authentication** answers "Is this token valid and issued for this API?", while **authorization** needs to know what the token or server-side data permits. The bridge between these two steps is the set of `GrantedAuthority` objects inside the `Authentication`.

This lesson guides you through:

1. Understanding the relationship between `scope`/`scp`, custom claims (`roles`, `authorities`, `realm_access`), and `GrantedAuthority`.
2. Using `JwtGrantedAuthoritiesConverter` and `JwtAuthenticationConverter` to convert JWT claims into authorities.
3. Distinguishing `SCOPE_messages:read`, `ROLE_ADMIN`, `hasAuthority(...)`, `hasRole(...)`, and business permissions.
4. Combining scopes with roles in a controlled way, handling nested claims and wrong data types, and preventing unintended privilege escalation.
5. Customizing authorities for opaque tokens via `OpaqueTokenIntrospector`; recognizing differences in WebFlux.
6. Building Spring Boot 3.x / Spring Security 6.x configurations and Java 17+ unit tests, distinguishing converter tests from real token verification tests.

**Context:** OAuth 2.0 Resource Server in Spring Security Servlet; WebFlux and version differences appear at the end. Both JWTs and opaque tokens can use `Bearer`, yet **how information is read and customized differs**.

## 2. From Access Token to `Authentication`

`GrantedAuthority` is Spring Security's small Java contract:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

The common implementation is `SimpleGrantedAuthority`, holding a string such as `SCOPE_orders:read` or `ROLE_OPERATOR`.

**Illustrative** JWT access token payload (signature and timestamp fields omitted for readability):

```json
{
  "iss": "https://idp.example.org/realms/training",
  "sub": "user-7392",
  "aud": ["api://training"],
  "scope": "messages:read messages:write",
  "roles": ["OPERATOR"]
}
```

Only **after the JWT has been verified and validated by `JwtDecoder`**, a converter can produce:

```text
Authentication type: JwtAuthenticationToken
Authentication name: user-7392
Granted authorities:
  SCOPE_messages:read
  SCOPE_messages:write
  ROLE_OPERATOR
```

The `SCOPE_` and `ROLE_` strings are **Spring Security** conventions, not mandatory JWT fields or OAuth 2.0 permission statements. A converter can change prefixes, but authorization rules must match the converted values.

Typical Servlet flow:

```text
HTTP Authorization: Bearer eyJ...
             |
             v
BearerTokenAuthenticationFilter
             |
             v
AuthenticationManager / JwtAuthenticationProvider
             |
             +--> JwtDecoder:
             |    verifies signature, issuer, lifetime, audience per config
             |
             +--> JwtAuthenticationConverter:
                  JwtGrantedAuthoritiesConverter and custom mapping
             |
             v
Authenticated JwtAuthenticationToken
  principal = Jwt
  authorities = [...]
             |
             v
SecurityContextHolder -> AuthorizationFilter / @PreAuthorize
```

**Principle:** a converter is not a cryptographic verification layer. A manually decoded JSON payload or a `Jwt` constructed from text **is not** proof of authorization; signature/algorithm/issuer/audience/time/tenant checks must happen before trusting claims.

## 3. Spring Security Defaults: `scope` and `scp`

`JwtGrantedAuthoritiesConverter` (package `org.springframework.security.oauth2.server.resource.authentication`) reads one of the well-known authority claims, typically:

- `scope`: usually a **space-delimited string of scopes**, e.g., `"messages:read messages:write"`.
- `scp`: may be a collection of strings, e.g., `["messages:read", "messages:write"]`, depending on the authorization server.

Each scope is converted into a `SimpleGrantedAuthority` prefixed with **`SCOPE_`**.

| Received Claim | Default Mapping | Notes |
| --- | --- | --- |
| `"scope": "profile email"` | `SCOPE_profile`, `SCOPE_email` | Two independent scopes |
| `"scp": ["orders:read", "orders:write"]` | `SCOPE_orders:read`, `SCOPE_orders:write` | Collection |
| `"scope": "orders:read"` | `SCOPE_orders:read` | Does not create `ROLE_...` |
| `"roles": ["ADMIN"]` | Does not create `ROLE_ADMIN` automatically | Custom claim needs a custom converter |
| Neither `scope` nor `scp` | No scope-derived authorities | Token may be valid yet lack permissions |
| Both `scope` and `scp` present | Default converter picks one claim per well-known logic | Does **not** merge both fields automatically |

Scope and authority names are **case-sensitive**: `SCOPE_Orders:Read` and `SCOPE_orders:read` differ. Do not arbitrarily call `toUpperCase()` or `toLowerCase()` without an explicit issuer contract.

In the application:

```java
.requestMatchers("/api/messages/**")
.hasAuthority("SCOPE_messages:read")
```

or in method security:

```java
@PreAuthorize("hasAuthority('SCOPE_messages:read')")
```

both check the **mapped authority string**, not the raw `scope` JSON field directly. An endpoint requiring write access must check `SCOPE_messages:write` rather than inferring it from `messages:read`.

### `hasAuthority` vs. `hasRole`

| API | Actual Check | Used With |
| --- | --- | --- |
| `hasAuthority("SCOPE_messages:read")` | Has exact authority string `SCOPE_messages:read` | OAuth2 scope |
| `hasAuthority("ROLE_OPERATOR")` | Has exact authority string `ROLE_OPERATOR` | Mapped role |
| `hasRole("OPERATOR")` | With default role prefix, requires `ROLE_OPERATOR` | Spring-style role |
| `hasRole("SCOPE_messages:read")` | With default prefix, checks `ROLE_SCOPE_messages:read` | Inappropriate for scopes |
| `authenticated()` | Authentication is authenticated | Requires no specific scope/role |

Therefore, **a successfully authenticated JWT does not imply endpoint access**. A resource server may return **401** when the token is missing/invalid/expired and **403** when the token is valid yet lacks the authority; exact status also depends on entry point and filter chain configuration.

## 4. Configuring Spring Boot 3.x to Receive and Validate JWTs

For a Spring Boot 3.x Gradle project on Java 17+, minimum dependencies for a Servlet API resource server:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The resource server starter brings in bearer token handling and compatible JWT verification libraries (`spring-security-oauth2-jose`). You do not need `spring-boot-starter-oauth2-client` just because the API accepts Bearer tokens.

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/training
          audiences: api://training
```

- `issuer-uri` configures `JwtDecoder` to discover metadata/JWKs of the trusted issuer and validate `iss`.
- `audiences` (supported in corresponding Spring Boot 3.x versions) checks that `aud` includes this resource server. Reject access tokens issued for other APIs.
- The resource server also validates signatures, `exp`/`nbf` timestamps, and actual validator conditions. For multiple issuers/tenants or custom JWK URLs, define the `JwtDecoder` and validations explicitly.
- The `idp.example.org` URL is **illustrative**. A real issuer and a valid token minted for audience `api://training` are required before requests succeed.

Never commit tokens, private keys, or credentials to Git. Mock tokens in the unit tests below only test the converter; they do not pass through `JwtDecoder`.

## 5. Using Default Mapping in `SecurityFilterChain`

For a JWT containing `scope=messages:read`, a simple configuration is:

```java
package example.authority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class DefaultJwtSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .requestMatchers(HttpMethod.POST, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
        return http.build();
    }
}
```

This is a **standalone Spring Security Servlet configuration** when placed in a Spring Boot project with controllers, dependencies, and decoder properties above. Do not register both the `SecurityFilterChain` bean in this section and the one in section 7 simultaneously unless they have `securityMatcher`/`@Order` for unambiguous routing: **pick one variant** for the application.

The example assumes the app has matching endpoints. If a public health check is needed, declare its `permitAll()` matcher before `anyRequest().denyAll()`.

For APIs using only header-based Bearer tokens, consider a `STATELESS` session policy and CSRF matching the real architecture. Never disable CSRF globally if browser cookie/session login also exists; CSRF and token validation are separate concerns.

## 6. Customizing Claim Name, Prefix, and Delimiter

Key configuration methods on `JwtGrantedAuthoritiesConverter`:

| API | Purpose | Scope |
| --- | --- | --- |
| `setAuthoritiesClaimName("permissions")` | Read `permissions` claim instead of well-known `scope`/`scp` | One chosen claim |
| `setAuthorityPrefix("ROLE_")` | Change prefix on generated authorities | Must match authorization rules |
| `setAuthorityPrefix("")` | Add no prefix | Use only when rules are explicitly designed for it |
| `setAuthoritiesClaimDelimiter(",")` | Regex delimiter splitting string claim, e.g., `read,write` | Available since Spring Security **6.1** |
| `JwtAuthenticationConverter#setJwtGrantedAuthoritiesConverter(...)` | Plug converter into JWT authentication | Servlet resource server |
| `JwtAuthenticationConverter#setPrincipalClaimName("preferred_username")` | Change claim used for Authentication's name | Does **not** alter permissions |

For example, if the `permissions` claim is a comma-separated string:

```json
{
  "permissions": "orders:read,orders:write"
}
```

**Spring Security 6.1+** configuration:

```java
JwtGrantedAuthoritiesConverter permissions = new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
permissions.setAuthoritiesClaimDelimiter(",");

JwtAuthenticationConverter authentication = new JwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(permissions);
```

Result:

```text
PERMISSION_orders:read
PERMISSION_orders:write
```

This is a **snippet inside a Java method** with imports:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
```

`setAuthoritiesClaimName` **replaces** the default claim; if you need both `scope` **and** `roles`, combine converters explicitly as in section 7. Avoid turning all scopes into `ROLE_`: `SCOPE_` represents OAuth2 delegated permissions, whereas roles are typically application-managed business permissions.

## 7. Complete Example: Merging `scope` and `roles` Claim

An IdP may issue:

```json
{
  "scope": "messages:read messages:write",
  "roles": ["OPERATOR"]
}
```

Business requirements:
- `scope` maps to `SCOPE_messages:read` / `SCOPE_messages:write`.
- `roles` maps to `ROLE_OPERATOR`.
- Grant no role if the token lacks `roles`, and never promote `SCOPE_...` to a role.
- Avoid duplicate authorities if a token contains repeated values.

### 7.1. Compilable Java 17+ Security Config

`src/main/java/example/authority/MappedJwtSecurityConfig.java`:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MappedJwtSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        // Keep default mapping: scope/scp -> SCOPE_...
        JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();

        // roles claim defined by an issuer authorized to mint it.
        JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        Converter<Jwt, Collection<GrantedAuthority>> merged = jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();
            authorities.addAll(scopes.convert(jwt));
            authorities.addAll(roles.convert(jwt));
            return authorities;
        };

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(merged);
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .requestMatchers(HttpMethod.POST, "/api/messages/**")
                    .hasAuthority("SCOPE_messages:write")
                .requestMatchers("/api/operations/**")
                    .hasRole("OPERATOR")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter)));
        return http.build();
    }
}
```

`LinkedHashSet` deduplicates identical `GrantedAuthority` strings while preserving deterministic order. The merged authority set is computed for a single JWT evaluation; the code **does not** modify the JWT payload or reissue an access token.

**Trust note:** this example lets `roles` influence permissions because **it assumes a trusted IdP issues this claim for this API's audience**. If the issuer does not guarantee the semantics/provenance of `roles`, or the token carries roles meant for another application, do not map it directly. Apply allowlists, check client/tenant/audience, or look up permissions in the application. An access token from an external partner cannot elevate itself to administrator simply by containing `"roles":["OPERATOR"]`.

### 7.2. Controllers to Observe Authorization

File `src/main/java/example/authority/MessagesController.java`:

```java
package example.authority;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/messages")
public class MessagesController {

    @GetMapping
    public String list() {
        return "messages:read accepted";
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public String create() {
        return "messages:write accepted";
    }
}
```

File `src/main/java/example/authority/OperationsController.java`:

```java
package example.authority;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/operations")
public class OperationsController {

    @GetMapping
    public String status() {
        return "operator accepted";
    }
}
```

File `src/main/java/example/authority/AuthorityDemoApplication.java`:

```java
package example.authority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}
```

Include **only** `MappedJwtSecurityConfig` or the simple config from section 5 in the same demo to avoid duplicate filter chain beans.

Run in a Spring Boot project connected to a real IdP:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. Requests succeed only when the caller holds an access token signed by the **real issuer**, valid for the API's audience, and containing the required scope/role.

Example API call in a test environment with a valid token stored in `ACCESS_TOKEN`:

```bash
curl -i -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  https://api.example.org/api/messages
```

Do not use the fake token JSON above to call a real API. Without a running API over HTTPS and a real token, deterministic live stdout/HTTP responses cannot be shown.

## 8. Mapping Nested Claims, e.g., `realm_access.roles`

Some authorization servers place roles inside a nested object:

```json
{
  "realm_access": {
    "roles": ["REPORT_VIEWER", "OPERATOR"]
  }
}
```

`setAuthoritiesClaimName("realm_access.roles")` **is not a JSON path evaluator**: the default converter looks for a **top-level** claim literally named `realm_access.roles`, so it normally finds nothing.

To extract nested claims, write a type-safe converter. Example inside a utility class, taking a verified `Jwt` in Java 17:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RealmRoleMapper {
    private static final Set<String> ALLOWED =
        Set.of("REPORT_VIEWER", "OPERATOR");

    private RealmRoleMapper() {}

    public static Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();
        Object rawRealm = jwt.getClaim("realm_access");

        if (!(rawRealm instanceof Map<?, ?> realm)) {
            return result;
        }

        Object rawRoles = realm.get("roles");
        if (!(rawRoles instanceof Collection<?> roles)) {
            return result;
        }

        for (Object value : roles) {
            if (value instanceof String role && ALLOWED.contains(role)) {
                result.add(new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
        return result;
    }
}
```

Integrate with the scope converter inside `jwtAuthenticationConverter()`:

```java
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
Converter<Jwt, Collection<GrantedAuthority>> merged = jwt -> {
    Set<GrantedAuthority> result = new LinkedHashSet<>(scopes.convert(jwt));
    result.addAll(RealmRoleMapper.convert(jwt));
    return result;
};
JwtAuthenticationConverter authentication = new JwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(merged);
```

Imports for `Jwt`, `GrantedAuthority`, `LinkedHashSet`, `Set`, `Collection`, `Converter`, `JwtAuthenticationConverter`, and `JwtGrantedAuthoritiesConverter` are the same as in section 7. This is a **snippet inside a configuration class**, not a standalone program.

In this example, only the two roles in `ALLOWED` are imported. Unknown roles are ignored (fail closed for unrecognized roles). Check **issuer/tenant/audience/target app** before trusting `realm_access`; across multiple IdPs, the same `OPERATOR` string can carry different meanings. If an invalid role represents a protocol error that should reject the entire token rather than be ignored, enforce that policy in validation and test it.

## 9. Principal Name vs. Authorities

In a JWT, `sub` is the default for `Authentication#getName()`; a display identity may come from `preferred_username`, `email`, or another field. `JwtAuthenticationConverter` supports:

```java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
```

This line only picks the **principal name**; it does not grant `ROLE_...`, alter scopes, or change how `JwtDecoder` verifies the token. If keeping the merged converter, configure both properties on **the same** `JwtAuthenticationConverter` bean rather than creating two separate beans and expecting Spring to merge them.

In multi-tenant systems, use a stable identity key such as `(issuer, sub)` to link accounts. Emails and usernames can change or collide across issuers; never use display names as the sole key for high-risk authorization.

## 10. Opaque Bearer Tokens: Authorities Come from Introspection

With an **opaque token**, the API does not decode a JWT payload itself. Instead, it calls the authorization server's introspection endpoint, verifies the token's status (`active`), and uses the attributes returned by the trusted server.

```text
Authorization: Bearer <opaque-token>
             |
             v
BearerTokenAuthenticationFilter
             |
             v
OpaqueTokenAuthenticationProvider
             |
             v
OpaqueTokenIntrospector.introspect(token)
   -> verifies active and returns OAuth2AuthenticatedPrincipal
   -> attributes + authorities (typically scope -> SCOPE_...)
             |
             v
BearerTokenAuthentication -> SecurityContext
```

By default, Spring Security maps scopes in the introspection response to `SCOPE_...`. This is a **different** pipeline from `JwtGrantedAuthoritiesConverter`; if the API is configured with `.opaqueToken(...)`, registering a `JwtAuthenticationConverter` alone **does not alter** opaque token authorities.

Spring Boot 3.x configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

In a Servlet application using opaque tokens, select:

```java
http.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()));
```

Import `withDefaults()` from `org.springframework.security.config.Customizer`. This **replaces** `.jwt(...)` when verifying tokens via introspection. A JWT can also be verified via introspection instead of JWK signatures if that is the Resource Server's policy, though the resulting authentication follows the **opaque path**.

### 10.1. Customizing Opaque Authorities via an Introspector Wrapper

Example adding role `OPERATOR` only if the trusted issuer's introspection response contains it in `roles`, while preserving all scope authorities loaded by Spring Security. File `src/main/java/example/authority/OpaqueAuthorityConfig.java`:

```java
package example.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class OpaqueAuthorityConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}") String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}") String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}") String secret) {

        OpaqueTokenIntrospector delegate = SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(secret)
            .build();

        return token -> {
            OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(principal.getAuthorities());

            Object rawRoles = principal.getAttribute("roles");
            if (rawRoles instanceof Collection<?> roles) {
                for (Object value : roles) {
                    if ("OPERATOR".equals(value)) {
                        authorities.add(new SimpleGrantedAuthority("ROLE_OPERATOR"));
                    }
                }
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(), principal.getAttributes(), authorities);
        };
    }
}
```

Notes:

- The example assumes `roles` is a collection; each IdP may return a different type. Never cast blindly or treat an arbitrary string as a permission group.
- `delegate.introspect(token)` must run **before** assigning authorities; if the token is inactive or credentials fail, introspection throws and no trusted principal is created.
- The code keeps scope authorities from `principal.getAuthorities()` and adds only the allowlisted role. If the authorization server returns claims that do not represent app roles, look up permissions from an API-side policy store.
- `client-secret` is a server secret used for introspection; load it from a secret manager/environment, never commit it.
- Enable `OpaqueAuthorityConfig` only in the profile using **opaque tokens**; with a JWT profile and multiple `SecurityFilterChain` beans, isolate beans/matchers explicitly. This code is not a custom JWT converter.

## 11. Testing the Converter with JUnit 5 (No Real Access Token Needed)

File `src/test/java/example/authority/JwtAuthorityMappingTest.java`. This is a **claim-mapping unit test**; `Jwt.withTokenValue(...)` constructs an in-memory fixture and does not verify signatures:

```java
package example.authority;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class JwtAuthorityMappingTest {

    private static Jwt fixture() {
        return Jwt.withTokenValue("fixture-only")
            .header("alg", "RS256")
            .claim("sub", "user-7392")
            .claim("scope", "messages:read messages:write")
            .claim("roles", List.of("OPERATOR"))
            .build();
    }

    private static Set<String> names(
            java.util.Collection<? extends GrantedAuthority> authorities) {
        return authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void defaultConverterAddsScopePrefixOnly() {
        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_messages:read", "SCOPE_messages:write"),
            names(converter.convert(fixture()))
        );
    }

    @Test
    void customConverterCombinesScopeAndRoles() {
        JwtAuthenticationConverter converter =
            new MappedJwtSecurityConfig().jwtAuthenticationConverter();

        var auth = converter.convert(fixture());
        assertNotNull(auth);
        assertEquals("user-7392", auth.getName());
        assertEquals(
            Set.of(
                "SCOPE_messages:read",
                "SCOPE_messages:write",
                "ROLE_OPERATOR"
            ),
            names(auth.getAuthorities())
        );
    }

    @Test
    void absentScopeMeansNoDefaultScopeAuthority() {
        Jwt withoutScope = Jwt.withTokenValue("fixture-without-scope")
            .header("alg", "RS256")
            .claim("sub", "user-2")
            .claim("roles", List.of("OPERATOR"))
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();
        assertEquals(Set.of(), names(converter.convert(withoutScope)));
    }
}
```

Run:

```bash
./gradlew test --tests example.authority.JwtAuthorityMappingTest
```

With compatible dependencies and a properly configured Gradle project, all **3 tests** should pass. There is no fixed application stdout: Gradle output depends on project and version. The second test verifies `ROLE_OPERATOR` mapping from the config class in section 7 without network access or real access tokens.

### 11.1. Distinguishing Converter Tests from Security Integration Tests

`spring-security-test` provides the `jwt()` request post-processor for MockMvc. Example:

```java
mvc.perform(get("/api/messages")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_messages:read")
        )))
   .andExpect(status().isOk());
```

This snippet belongs in a `@Test` with `MockMvc mvc`, static imports `SecurityMockMvcRequestPostProcessors.jwt`, `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status`, and import `SimpleGrantedAuthority`. `jwt()` creates a **mock authenticated Authentication** for authorization testing; it **does not** check JWT signatures or run your real converter if you supply authorities explicitly.

To test the `JwtDecoder → JwtAuthenticationConverter` path, use a `@MockBean`/test decoder bean in compatible Spring Boot versions or a suitable test IdP/JWKs server and send Bearer tokens over HTTP. Separate these test layers:

| Test | What It Verifies |
| --- | --- |
| `JwtGrantedAuthoritiesConverter` unit test | Conversion of `scope`, `scp`, `roles`, missing/wrong-type claims |
| Custom mapping unit test | Allowlists, prefixes, merging, and deduplication |
| MockMvc with `jwt()` | Authorization rules requiring specific authorities |
| Integration test with real JWT | Signature/JWK, issuer, audience, expiration, decoder, and mapping |
| Integration test with opaque introspection | `active`, scopes, timeouts, introspector, mapping, and permissions |

Never treat MockMvc `jwt()` as proof that production signature verification is configured properly.

## 12. Common Errors

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| Valid token yet HTTP 403 | Endpoint requires `ROLE_ADMIN`, token only produces `SCOPE_...` | Inspect `Authentication.getAuthorities()` and matchers; choose right policy |
| `hasRole("messages:read")` fails | `hasRole` adds `ROLE_`, whereas scopes use `SCOPE_` | Use `hasAuthority("SCOPE_messages:read")` |
| JWT has `"roles"` yet app sees no role | Default converter reads only well-known scope claims | Configure custom claim converter/merge |
| Scopes disappear after switching to `roles` | `setAuthoritiesClaimName("roles")` **replaces** previous claim source | Create converters for both scope and roles and merge them |
| Both `scope` and `scp` exist, only one set appears | Default converter does not merge two claims at once | Define claim contract with issuer, map explicitly if needed |
| `realm_access.roles` always empty | Nested claim name passed as a flat claim name | Read `Map<?, ?>` and validate the inner collection |
| Roles changed yet old JWT keeps access | Self-contained JWT is unexpired; does not see account updates immediately | Reasonable TTL, revocation/introspection, or server-side permission lookup |
| Login ID token accepted by API | API missing audience/token-type validation | Resource server must trust only **access tokens** for the API, check aud/iss |
| `401 invalid_token` | Bad JWT signature/issuer/audience/expiration or malformed token | Check decoder, JWKS/clocks; never edit converter to bypass validation |
| Wrong type in `roles` causes `ClassCastException` | Unchecked cast to `List<String>` | Check `instanceof`, reject or drop permission per policy |
| Case mismatch (`read`/`READ`) causes 403 | Authority strings match case-sensitively | Standardize contract at IdP and verify rules |
| Opaque token ignores `JwtGrantedAuthoritiesConverter` | Goes through introspection, not `JwtAuthenticationConverter` | Customize `OpaqueTokenIntrospector` or opaque authentication converter per version |
| `@PreAuthorize` has no effect | Method security not enabled or self-invocation bypassed proxy | Enable `@EnableMethodSecurity`, invoke through managed bean |
| `jwt()` test passes yet real token fails | Mock test bypassed decoder/converter | Add integration tests with real tokens and a test IdP |

Report errors safely: return standard 401/403 responses, and in internal logs record only request correlation ID, error category, and required authority. Avoid logging raw Bearer tokens or full claims containing personal data.

## 13. Claims and Authorities Do Not Replace Security Policy

A production system must agree on **who issues** tokens, **who tokens are for**, and **which authority sources are trusted**:

1. **Issuer:** restrict `iss` and trusted JWKs. Avoid decoders accepting `alg=none`, token-embedded keys, or arbitrary issuers.
2. **Audience:** verify `aud` includes this API; a token from the same issuer minted for a frontend or another API must not be accepted.
3. **Token type:** distinguish access tokens from ID tokens; OAuth 2.0 Bearer Resource Servers use access tokens.
4. **Tenant/client boundaries:** `ADMIN` role in tenant A or client X is not automatically valid in tenant B or API Y.
5. **Source of authority:** scopes are granted by the authorization server per consent/client policy; business roles may need allowlists, principal lookups, or server-side entitlement stores.
6. **Time bounds:** check `exp`, `nbf`, clock skew, and key rotation; if fast revocation is required, consider short token TTLs or introspection.
7. **Never derive permissions from request input:** clients must not supply `roles` via query params, HTTP headers, or unverified JWTs.
8. **Avoid confusing identity with permissions:** `preferred_username`, `email`, and `sub` are identity claims; never synthesize `ROLE_...` just because a string matches a keyword.
9. **Test negative cases:** missing scope, extra scope lacking role, wrong-type role, different issuer, wrong audience, wrong tenant, revoked/expired tokens.

Converting claims into authorities is an **intentional policy step**, executed after data is verified and before authorization. The same `roles` claim across two token issuers can mean entirely different things; keep the mapping at the resource server boundary with tests ensuring no privilege escalation.

## 14. Servlet, WebFlux, and Version Differences

### Servlet

In Spring MVC/Servlet, `JwtAuthenticationConverter` implements `Converter<Jwt, AbstractAuthenticationToken>` and is registered via:

```java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter)));
```

`SecurityContextHolder` manages Authentication per Servlet request context; application rules evaluate `Authentication.getAuthorities()`.

### WebFlux

WebFlux does not use `HttpSecurity` or Servlet `SecurityFilterChain`. It uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive authentication. If you already have a synchronous claim-mapping converter:

```java
package example.authority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveAuthoritySecurityConfig {

    @Bean
    SecurityWebFilterChain webFluxChain(
            ServerHttpSecurity http,
            JwtAuthenticationConverter converter) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/api/messages/**")
                    .hasAuthority("SCOPE_messages:read")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt
                .jwtAuthenticationConverter(
                    new ReactiveJwtAuthenticationConverterAdapter(converter)
                )))
            .build();
    }
}
```

This is a **variant specifically for a Spring WebFlux application** having the converter bean from section 7. `ReactiveJwtAuthenticationConverterAdapter` adapts a synchronous converter to the reactive interface; it does not mean you can use `HttpSecurity` in WebFlux. If mapping needs asynchronous DB/network lookups, implement a non-blocking reactive converter rather than calling `.block()` inside the reactive chain.

### Versions

| Spring Security Line | Key Notes |
| --- | --- |
| **5.2+** | `JwtGrantedAuthoritiesConverter` included in Resource Server JWT; default scope → `SCOPE_...` |
| **5.7–5.8** | `WebSecurityConfigurerAdapter` deprecated; migrate configuration to `SecurityFilterChain` beans |
| **6.0+** | Requires Java 17 and Jakarta APIs for Servlet; uses lambda DSL and beans |
| **6.1+** | `setAuthoritiesClaimDelimiter(...)` supports splitting string claims with custom regex |
| **6.x / Boot 3.x** | `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, and `jwtAuthenticationConverter(...)` remain standard |
| **7.x / Boot 4.x** | Check DSL, OAuth2 authorization helpers, and dependency baselines in migration guides; JWT/opaque authority mapping remains separate |

Some Spring Security 7.x documentation also mentions authorities marking **authentication factors** such as `FACTOR_BEARER`. That represents information about the authentication mechanism, **not** a business permission like `ROLE_ADMIN` or scope `SCOPE_messages:read`. Do not treat it as an endpoint permission.

## 15. Hands-On Exercises and Completion Criteria

**Exercise 1:** A JWT has:

```json
{"scp":["invoices:read","invoices:approve"],"roles":["FINANCE"]}
```

Using the default JWT converter, the scope authorities are:

```text
SCOPE_invoices:read
SCOPE_invoices:approve
```

`ROLE_FINANCE` appears only after declaring an appropriate converter and confirming the issuer is authorized to issue that role.

**Exercise 2:** Endpoint `POST /invoices/approve` requires both the approval scope and the finance role. `hasAuthority("SCOPE_invoices:approve")` alone is not enough; combine policies, e.g., in Spring method security:

```java
@PreAuthorize("hasAuthority('SCOPE_invoices:approve') and hasRole('FINANCE')")
```

Remember to enable `@EnableMethodSecurity`. A token missing either authority must be rejected even if it holds the other.

**Exercise 3:** An API switches from JWT to opaque tokens while keeping `hasAuthority("SCOPE_invoices:read")`. Test that the introspection response has `scope`, `active=true`, the right issuer endpoint, and that the opaque mapper produces `SCOPE_invoices:read`. Do not leave a JWT converter around assuming it is still invoked.

An implementation meets requirements when: invalid tokens are rejected by decoder/introspector; valid tokens with proper permissions gain access; valid tokens missing scope/role receive 403; mappings never grant permissions from claims lacking a clear contract; and unit and integration tests accurately reflect those cases.

## 16. References

- Spring Security 6.5 — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth 2.0 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security API — `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
