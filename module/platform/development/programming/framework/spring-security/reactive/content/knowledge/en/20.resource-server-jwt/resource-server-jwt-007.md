# Mapping Scopes to SCOPE_ Authorities and Customizing JwtGrantedAuthoritiesConverter

**Module:** Spring Security – reactive (WebFlux)  
**Section:** Resource Server JWT  
**Focus:** How Spring Security converts scopes from a JWT access token into `GrantedAuthority` instances prefixed with `SCOPE_`; how to change the source claim, prefix, and delimiter using `JwtGrantedAuthoritiesConverter`; how to bridge a synchronous converter into the reactive flow via `ReactiveJwtAuthenticationConverterAdapter`; properly testing the distinction between Bearer authentication and 401/403 authorization.

**Summary:** In Spring Security Resource Server JWT, the `scope` claim (usually a space-delimited string) or `scp` claim (usually an array of strings) is converted into authorities shaped like `SCOPE_xxx`. For example, `scope="reports.read reports.write"` produces `SCOPE_reports.read` and `SCOPE_reports.write`. A rule like `hasAuthority("SCOPE_reports.read")` grants access when the JWT is valid **and** contains that scope. `JwtGrantedAuthoritiesConverter` lets you change the claim read, prefix, and delimiter regex. In WebFlux, wrapping a `JwtAuthenticationConverter` (synchronous, non-blocking) in a `ReactiveJwtAuthenticationConverterAdapter` and wiring it into `oauth2ResourceServer().jwt()` attaches those authorities to the resulting reactive `Authentication`.

Important: **Authority mapping does not verify the JWT signature.** `ReactiveJwtDecoder` must validate the token (signature, issuer, expiry/not-before, and audience if required by the API) before the converter reads claims; `SecurityWebFilterChain` then checks authorities. Never take an unverified JWT and trust `scope`/`roles` in its payload.

## 1. Pipeline Overview from Authorization Header to Permission Decision

```text
HTTP GET /api/reports
Authorization: Bearer <signed-access-token>
             |
             v
Spring Security WebFlux / bearer-token authentication
             |
             v
ReactiveJwtDecoder
  - verify JWS signature/key/allowed algorithm
  - check iss, exp, nbf; aud per API validation
  - reject if JWT invalid
             |
             v
Verified Jwt
    claims: sub="alice"
            scope="reports.read reports.write"
            permissions="catalog.read,catalog.write"
             |
             v
Default JwtGrantedAuthoritiesConverter
   scope -> SCOPE_reports.read
            SCOPE_reports.write
             |
             +-- custom converter (if configured)
             |   permissions -> PERM_catalog.read
             |                  PERM_catalog.write
             v
JwtAuthenticationConverter
  -> JwtAuthenticationToken with Jwt as Principal
  -> Authentication.getAuthorities()
             |
             v
ReactiveJwtAuthenticationConverterAdapter
  -> Mono<AbstractAuthenticationToken>
             |
             v
ServerHttpSecurity.authorizeExchange()
   hasAuthority("SCOPE_reports.read")
          |
          +-- missing/malformed token -> 401
          +-- good token, missing permission -> 403
          +-- good token, sufficient permission -> controller Mono/Flux
```

The diagram only illustrates logical responsibilities; reactive publishers emit signals upon subscription. Authority conversion is an in-memory operation—there is no reason to make blocking database calls inside a converter. If permissions require asynchronous lookups, use a dedicated reactive authorization design and perform principal/tenant queries at the appropriate layer.

### 1.1. Four Layers Not to Mix

| Layer | Question | Typical API/mechanism |
| --- | --- | --- |
| Bearer extraction | Does the request have `Authorization: Bearer ...`? | Spring Security Bearer authentication filter/converter |
| JWT validation | Does the token have a trusted signature and claims? | `ReactiveJwtDecoder` + `OAuth2TokenValidator<Jwt>` |
| Authority mapping | How are claims turned into Spring authorities? | `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter` |
| Authorization | Does the current request have access to the route/resource? | `authorizeExchange`, `hasAuthority`, `@PreAuthorize` with reactive method security |

**401 Unauthorized:** Missing valid Bearer token or token rejected during authentication. With a standard Resource Server, responses typically include `WWW-Authenticate: Bearer` or error details per RFC 6750.

**403 Forbidden:** Valid JWT was authenticated, but lacks the required authority or fails policy. Never turn `403` into `401` or drop permission checks just because a test failed.

### 1.2. Default scope and scp Behavior

Spring Security recognizes common claim names, defaulting to `scope` and `scp`. Input data:

```json
{
  "iss": "https://idp.example.invalid",
  "sub": "alice",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write"
}
```

After default mapping, `Authentication.getAuthorities()` contains:

```text
SCOPE_reports.read
SCOPE_reports.write
```

If the provider emits:

```json
{
  "scp": ["reports.read", "reports.write"]
}
```

then the default converter maps those two scopes as well. `JwtGrantedAuthoritiesConverter` normally picks the first present claim from its list of known names, **which does not mean it always merges `scope` and `scp`** if both exist simultaneously. Avoid an AS emitting conflicting claims; agree on a stable claim contract and test when both appear.

### 1.3. Authority Matching Rules Must Match Exactly

| JWT scope / input data | Authority after mapping | Valid rule |
| --- | --- | --- |
| `scope="messages.read"` | `SCOPE_messages.read` | `hasAuthority("SCOPE_messages.read")` |
| `scope="reports.read reports.write"` | `SCOPE_reports.read`, `SCOPE_reports.write` | `hasAuthority("SCOPE_reports.write")` |
| `scp=["catalog.read"]` | `SCOPE_catalog.read` | `hasAuthority("SCOPE_catalog.read")` |
| No scope/scp | Usually empty with default converter | Do not treat authenticated as having all permissions |
| `scope="admin"` | `SCOPE_admin` | Does **not** satisfy `hasRole("ADMIN")` |
| `permissions="catalog.read,catalog.write"` | **Not read** by default | Requires `setAuthoritiesClaimName("permissions")` |

By Spring Security convention, `hasRole("ADMIN")` looks for the authority `ROLE_ADMIN`, which **differs** from `SCOPE_admin` or `SCOPE_ADMIN`. Scopes represent OAuth2 delegation from the AS to an API, whereas roles may represent a domain/application permission model; do not treat them as synonymous.

## 2. JwtGrantedAuthoritiesConverter: Three Key Customization Points

Class:

```java
import org.springframework.security.oauth2.server.resource.authentication
    .JwtGrantedAuthoritiesConverter;
```

The import above is line-wrapped for readability in documentation; in actual Java source, write it on **one line**:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
```

`JwtGrantedAuthoritiesConverter` is a synchronous `Converter<Jwt, Collection<GrantedAuthority>>` with no I/O. Key setters:

| API | Default | When to use |
| --- | --- | --- |
| `setAuthoritiesClaimName(String)` | Looks for well-known `scope` or `scp` | Provider uses `permissions`, `authorities`, or another fixed claim |
| `setAuthorityPrefix(String)` | `SCOPE_` | Want a namespace like `PERM_`; be careful with `ROLE_` |
| `setAuthoritiesClaimDelimiter(String)` | Whitespace-splitting regex for string claims | Provider emits comma/semicolon-delimited strings; available since Spring Security 6.1 |
| `convert(Jwt)` | Extracts scopes/authorities from claim | Test mapping logic directly without network |

### 2.1. Customizing the Claim Name

An organization's provider emits `permissions` instead of `scope`:

```json
{
  "sub": "alice",
  "permissions": ["report.read", "report.export"]
}
```

Configuration:

```java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

converter.setAuthoritiesClaimName("permissions");
// Without changing prefix:
// ["SCOPE_report.read", "SCOPE_report.export"]
```

This is a **fragment**, not a standalone Java program. Changing the claim in the converter **does not modify the JWT**, only which claim is read. **When calling the setter on a single converter, default mapping from `scope`/`scp` is not automatically merged in**; to keep both, combine two converters as shown in Section 3.

### 2.2. Changing the Prefix: SCOPE_, PERM_, and ROLE_

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();

custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
```

With `permissions=["catalog.read"]`, the authority is `PERM_catalog.read`, so use `hasAuthority("PERM_catalog.read")`. Remember to update matchers and tests when changing the prefix.

You can pass `setAuthorityPrefix("")` for no prefix, though namespace collisions must be evaluated. You may use `ROLE_` if the claim **genuinely represents trusted roles** after validating issuer, audience, tenant, and role values; do **not** automatically map every `scope` to an admin role.

Semantically wrong example:

```java
JwtGrantedAuthoritiesConverter danger =
    new JwtGrantedAuthoritiesConverter();
danger.setAuthorityPrefix("ROLE_");
// Now scope "ADMIN" can become ROLE_ADMIN.
// This is NOT a safe default mapping.
```

To map roles from a custom claim, design an explicit allowlist and authorization policy rather than simple string concatenation. Always distinguish claims signed by a trusted AS from user-supplied headers or inputs.

### 2.3. Comma-Delimited Claim Strings

If a token carries:

```json
{
  "permissions": "catalog.read, catalog.write,report.export"
}
```

a non-whitespace delimiter is required:

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();

custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
custom.setAuthoritiesClaimDelimiter("\\s*,\\s*");
```

`setAuthoritiesClaimDelimiter` accepts a **regex**. In a Java literal, `"\\s*,\\s*"` creates a regex matching commas with optional surrounding whitespace. Never use a bare comma if the provider puts spaces after commas and you do not trim; the authority would become `PERM_ catalog.write` (leading space), causing matchers to fail even when things look right at a glance.

If the claim is a **JSON array of strings**, the converter iterates the collection directly without regex splitting. Never feed arbitrary nested objects or serialized JSON strings expecting deep parsing; agree on and test the claim type from the issuer.

## 3. Keeping Default Scopes and Adding Custom Permissions Together

This is a common production scenario: an upstream Authorization Server emits `scope` for the OAuth2 protocol alongside a `permissions` claim for fine-grained permissions.

To map:

```json
{
  "scope": "reports.read reports.write",
  "permissions": "catalog.read,catalog.write"
}
```

to:

```text
SCOPE_reports.read
SCOPE_reports.write
PERM_catalog.read
PERM_catalog.write
```

you **cannot** just create one converter and call `setAuthoritiesClaimName("permissions")`, because that drops the two default scopes. Instead, use **two `JwtGrantedAuthoritiesConverter` instances** and merge their results:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");
permissions.setAuthoritiesClaimDelimiter("\\s*,\\s*");

JwtAuthenticationConverter jwtAuthenticationConverter =
    new JwtAuthenticationConverter();

jwtAuthenticationConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Set<GrantedAuthority> merged = new LinkedHashSet<>();
    merged.addAll(scopes.convert(jwt));       // SCOPE_...
    merged.addAll(permissions.convert(jwt));  // PERM_...
    return merged;
});
```

This is a **fragment** needing imports; the complete code appears in `SecurityConfig.java` in Section 6. `LinkedHashSet` deduplicates authorities without altering permission semantics and performs no blocking I/O. `setJwtGrantedAuthoritiesConverter` **replaces** `JwtAuthenticationConverter`'s default converter, so merging inside the lambda must be explicit.

### 3.1. Why Not Map Everything to ROLE_?

`ROLE_ADMIN` typically represents an internal application role, whereas `SCOPE_reports.read` represents an OAuth2 access token's scope. If an AS issues `scope=admin`, mapping it to `ROLE_ADMIN` could accidentally grant the token internal admin-user privileges. Even with a trusted AS, authorization must consider **audience**, identity/tenant, claims, and business policy.

**Safe naming approach:** Keep `SCOPE_` for OAuth2 scopes; choose `PERM_` for business permission claims agreed upon with the issuer; only add `ROLE_` from reviewed/allowlisted role claims with clear tenant boundaries. Avoid mapping roles from emails, query parameters, or user-controlled custom HTTP headers.

### 3.2. Scopes Do Not Automatically Filter Resources by Owner

`hasAuthority("SCOPE_reports.read")` checks that the token was granted that *type of operation*. It does **not** prove Alice may view Bob's or another tenant's report. Repositories and services still need object-level/tenant checks, reading the principal from `ReactiveSecurityContextHolder` and querying by the validated token's user/tenant.

## 4. ReactiveJwtAuthenticationConverterAdapter and Native Reactive Converters

**WebFlux difference:** `ServerHttpSecurity.OAuth2ResourceServerSpec.JwtSpec.jwtAuthenticationConverter(...)` expects a `Converter<Jwt, Mono<AbstractAuthenticationToken>>`. Meanwhile, the classic `JwtAuthenticationConverter` is a **synchronous** converter from `Jwt` to `Authentication`. Spring provides:

```java
new ReactiveJwtAuthenticationConverterAdapter(
    jwtAuthenticationConverter);
```

The adapter lifts pure in-memory non-blocking logic to a reactive return type; **it does not mean you can run blocking database calls on an executor**. Never put JDBC lookups, `block()`, or blocking HTTP I/O into the converter. If permissions genuinely require reactive APIs/data stores, consider `ReactiveAuthorizationManager` at the authorization layer or design a reactive converter with a clear contract.

### 4.1. WebFlux Signature

```java
Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
    new ReactiveJwtAuthenticationConverterAdapter(
        jwtAuthenticationConverter);
```

In configuration:

```java
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/api/reports")
            .hasAuthority("SCOPE_reports.read")
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth -> oauth
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
    .build();
```

This is a fragment; the full security config below also configures distinct GET/POST permissions, the decoder, Bearer-only settings, and CSRF scope. Never pass a `JwtGrantedAuthoritiesConverter` directly (it returns `Collection<GrantedAuthority>`) into an API expecting a converter returning `Mono<AbstractAuthenticationToken>`; use **`JwtAuthenticationConverter` + adapter** or a suitable `ReactiveJwtAuthenticationConverter`.

### 4.2. Alternative: ReactiveJwtAuthenticationConverter

`ReactiveJwtAuthenticationConverter` takes a `Converter<Jwt, Flux<GrantedAuthority>>` and returns `Mono<AbstractAuthenticationToken>`. You can adapt a collection converter via `Flux.fromIterable`:

```java
ReactiveJwtAuthenticationConverter reactive =
    new ReactiveJwtAuthenticationConverter();

reactive.setJwtGrantedAuthoritiesConverter(
    jwt -> Flux.fromIterable(scopes.convert(jwt)));
```

This is a fragment where `scopes` is an already-declared `JwtGrantedAuthoritiesConverter`. Do not confuse this setter API with `JwtAuthenticationConverter`, which takes `Converter<Jwt, Collection<GrantedAuthority>>`. When reusing existing synchronous converters, the adapter lets you share configuration cleanly while satisfying the WebFlux contract.

### 4.3. Changing Authentication.getName Differs from Changing Authorities

By default, the principal name of `JwtAuthenticationToken` is the `sub` claim. `JwtAuthenticationConverter.setPrincipalClaimName("preferred_username")` changes the name returned by `Authentication.getName()` when that claim is present:

```java
JwtAuthenticationConverter c = new JwtAuthenticationConverter();
c.setPrincipalClaimName("preferred_username");
```

This changes only the **principal name**, **not** scopes or roles. If using username/email for display, know which claim is stable versus mutable; in multi-issuer setups, use `iss + sub` as the reliable identity key. Never alter the subject key solely for UX display convenience.

## 5. Standalone Java 17: Observing the Prefix with Fixed Stdout

To help learners separate **text-mapping logic** from JWT cryptography, you can run a plain Java program. It is **not the real implementation of Spring Security's JwtGrantedAuthoritiesConverter**: it verifies no JWT, handles no `scp` array, and ignores empty/other claims; it merely illustrates the prefix.

Save `ScopePrefixDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class ScopePrefixDemo {

    static List<String> authorities(String scopeClaim) {
        return Arrays.stream(scopeClaim.trim().split("\\s+"))
            .filter(s -> !s.isEmpty())
            .map(s -> "SCOPE_" + s)
            .sorted()
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(authorities(
            "reports.write reports.read"));
        System.out.println(authorities("catalog.read"));
        System.out.println(
            authorities("reports.read").contains("ROLE_ADMIN"));
    }
}
```

Run on JDK 17+:

```bash
javac ScopePrefixDemo.java
java ScopePrefixDemo
```

**Exact stdout:**

```text
[SCOPE_reports.read, SCOPE_reports.write]
[SCOPE_catalog.read]
false
```

Explanation: The prefix is part of the authority string; `SCOPE_reports.read` is not `ROLE_ADMIN`. In a real application, only run the mapper **after the decoder has verified the JWT**.

## 6. Spring Boot WebFlux Project with Real Signed JWTs to Test Scope Mapping

We build a **Bearer-only** Resource Server as a hands-on lab:

| Route | HTTP method | Required authority | Result |
| --- | --- | --- | --- |
| `/public` | GET | Public | `200 public` |
| `/api/reports` | GET | `SCOPE_reports.read` | `200 report-visible` if valid token |
| `/api/reports` | POST | `SCOPE_reports.write` | `200 report-created` if sufficient scope |
| `/api/catalog` | GET | `PERM_catalog.read` | `200 catalog-visible` if custom claim suffices |
| `/api/admin` | GET | `ROLE_ADMIN` | `403` if token only has scope `admin` |
| `/api/inspect` | GET | Authenticated | JSON with principal name and authority list, no token |

Uses **Spring Boot 3.5.7 / Java 17+** as a consistent baseline for the examples. Tests use a **demo HMAC key** to sign JWTs in tests, and the decoder verifies the real signature when requests enter WebFlux. No online IdP is needed. **Hardcoded keys are strictly for localhost tutorials**: production should use an IdP/JWK Set over HTTPS, asymmetric signatures, audience/issuer validation, key rotation, and secret protection.

### 6.1. Directory Structure

```text
webflux-jwt-authorities/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwtauth/
    │   │   ├── JwtAuthoritiesApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/jwtauth/
        └── JwtAuthoritiesTests.java
```

Do not mix Servlet `spring-boot-starter-web` into WebFlux. `spring-boot-starter-oauth2-resource-server` provides the required JWT/JOSE resource server classes.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-jwt-authorities</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-jwt-authorities
server.port=8080
```

Because the demo defines a `@Bean ReactiveJwtDecoder` using a local HMAC key, it **does not need** `issuer-uri` in properties; the decoder and validators are declared in Java. Never deploy the signing key in this code to a real production server.

### 6.2. Application Class

`src/main/java/demo/jwtauth/JwtAuthoritiesApplication.java`:

```java
package demo.jwtauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtAuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtAuthoritiesApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: Decoder, Merged Converter, and Route Policy

`src/main/java/demo/jwtauth/SecurityConfig.java`:

```java
package demo.jwtauth;

import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    static final String ISSUER = "https://idp.example.invalid";
    static final String AUDIENCE = "reports-api";

    // DEMO/TEST ONLY. Never hardcode keys in production.
    static SecretKey demoKey() {
        String value =
            "only-local-demo-hs256-key-keep-out-of-production";
        return new SecretKeySpec(
            value.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(demoKey())
                .macAlgorithm(MacAlgorithm.HS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Missing required audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));
        return decoder;
    }

    static JwtGrantedAuthoritiesConverter scopeAuthorities() {
        // Default: scope/scp -> SCOPE_...
        return new JwtGrantedAuthoritiesConverter();
    }

    static JwtGrantedAuthoritiesConverter permissionAuthorities() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERM_");
        permissions.setAuthoritiesClaimDelimiter("\\s*,\\s*");
        return permissions;
    }

    static Converter<Jwt, Mono<AbstractAuthenticationToken>>
            jwtAuthenticationConverter() {

        JwtGrantedAuthoritiesConverter scopes =
            scopeAuthorities();
        JwtGrantedAuthoritiesConverter permissions =
            permissionAuthorities();

        JwtAuthenticationConverter imperative =
            new JwtAuthenticationConverter();

        imperative.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> merged = new LinkedHashSet<>();
            merged.addAll(scopes.convert(jwt));
            merged.addAll(permissions.convert(jwt));
            return merged;
        });

        // Adapter bridges to Mono<AbstractAuthenticationToken>
        return new ReactiveJwtAuthenticationConverterAdapter(
            imperative);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .pathMatchers(HttpMethod.GET, "/api/catalog")
                    .hasAuthority("PERM_catalog.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/inspect")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter())))
            // Bearer JWT as the only credential; no cookie/form/Basic.
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Detailed explanation:**

1. `ReactiveJwtDecoder` verifies the JWT; tokens are HS256-signed with the demo key. The validator combines issuer, default expiry/not-before, and **audience `reports-api`**. If audience is missing/wrong, the token is rejected before extracting scopes. In production, verify tokens using API-defined issuer/JWKS/algorithm and audience, never a demo private secret.
2. `scopeAuthorities()` keeps the standard `scope`/`scp` → `SCOPE_...` mapping.
3. `permissionAuthorities()` reads `permissions` with a comma regex delimiter and `PERM_` prefix. JSON array claims are also supported.
4. `LinkedHashSet` merges both authority sources without mixing `PERM_` with `SCOPE_` or `ROLE_`. Scope-only tokens still work for `SCOPE_...` rules; permission-only tokens can still access the catalog endpoint.
5. `JwtAuthenticationConverter` builds `JwtAuthenticationToken` with the authority list; `ReactiveJwtAuthenticationConverterAdapter` adapts the result to WebFlux's reactive contract.
6. Specific matchers come before `anyExchange().denyAll()`. GET reports and POST reports require different scopes; do not confuse `POST` with GET.
7. `/api/admin` uses `hasRole("ADMIN")` to prove `scope="admin"` does **not** become `ROLE_ADMIN`. If a product needs roles, establish a trusted role source and separate mapping.
8. `NoOpServerSecurityContextRepository` avoids saving/loading Authentication from `WebSession` in the demo Resource Server. `formLogin`/`httpBasic` are disabled; only valid Bearer tokens are accepted.
9. `csrf.disable()` is used only in this **Bearer-header-only** demo accepting no cookies/sessions/Basic as credentials. If the API later accepts cookie-carried JWTs or browser login fallbacks, re-evaluate/re-enable CSRF for mutations.

**Never call `setAuthorityPrefix("ROLE_")` on the scope claim just to make an admin test green.** Prove your domain/tenant permission model actually supports role issuance and that the ID token/JWT is validated before mapping.

### 6.4. Controller: Exposing Observable Authorities Without Leaking Tokens

`src/main/java/demo/jwtauth/DemoController.java`:

```java
package demo.jwtauth;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record AuthView(
        String name, List<String> authorities) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> reports() {
        return Mono.just("report-visible");
    }

    @PostMapping(value = "/api/reports",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> createReport() {
        // Simulation only; does not write to DB or perform real side effects.
        return Mono.just("report-created");
    }

    @GetMapping(value = "/api/catalog",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> catalog() {
        return Mono.just("catalog-visible");
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-visible");
    }

    @GetMapping(value = "/api/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<AuthView> inspect() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> {
                Authentication auth = context.getAuthentication();
                List<String> values = auth.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
                return new AuthView(auth.getName(), values);
            });
    }
}
```

`/api/inspect` is for **learning/testing only**. It deliberately does **not** send raw tokens, full JWT claims, client secrets, or the `Authorization` header; even authorities and principal names can be sensitive in production, so never expose this debug endpoint publicly in production.

Do not call `block()` inside the controller. `ReactiveSecurityContextHolder` retrieves `Authentication` from the request's Reactor Context rather than `ThreadLocal`. Handlers return `Mono` so WebFlux subscribes automatically; converters in `SecurityConfig` never need to call `subscribe()`.

## 7. Testing Real Signed JWTs Over HTTP with WebTestClient

This is a critical point: `spring-security-test`'s `mockJwt()` is great for **testing authorization policies**, but it injects a mock `Authentication` directly and therefore **does not prove** that production `ReactiveJwtDecoder`/converters run on real Bearer JWTs. This lesson uses **real HS256-signed JWTs with the demo key** in tests, sending `Authorization: Bearer ...` through the WebFlux server to traverse:

1. Bearer authentication filter;
2. `NimbusReactiveJwtDecoder` + issuer/audience/expiry/signature validators;
3. `JwtAuthenticationConverter` and `JwtGrantedAuthoritiesConverter`;
4. `ReactiveJwtAuthenticationConverterAdapter`;
5. `authorizeExchange` and controller.

No external IdP or JWK Set URL is needed. Never put an HMAC secret in a frontend; the fixture here is strictly for the test environment.

### 7.1. Full Test File

`src/test/java/demo/jwtauth/JwtAuthoritiesTests.java`:

```java
package demo.jwtauth;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JwtAuthoritiesTests {

    @Autowired
    WebTestClient client;

    private static String signed(Map<String, Object> claims) {
        return signed(
            claims, false, SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());
    }

    private static String signed(
            Map<String, Object> extras, boolean expired,
            String issuer, List<String> audience, SecretKey key) {

        Instant now = Instant.now();

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(expired ? now.minusSeconds(3600) : now)
            .notBefore(expired
                ? now.minusSeconds(3500) : now.minusSeconds(5))
            .expiresAt(expired
                ? now.minusSeconds(600) : now.plusSeconds(900));

        extras.forEach(claims::claim);

        NimbusJwtEncoder encoder =
            new NimbusJwtEncoder(new ImmutableSecret<>(key));

        return encoder.encode(
            JwtEncoderParameters.from(
                JwsHeader.with(MacAlgorithm.HS256).build(),
                claims.build()))
            .getTokenValue();
    }

    private static SecretKey otherKey() {
        return new SecretKeySpec(
            "other-key-only-for-testing-32-bytes-long"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");
    }

    @Test
    void publicRouteNeedsNoToken() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerGets401AndChallenge() {
        client.get().uri("/api/reports")
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                s -> assertTrue(s.startsWith("Bearer")));
    }

    @Test
    void scopeStringGrantsReportRead() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-visible");
    }

    @Test
    void scpArrayAlsoGrantsReportRead() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scp", List.of("reports.read")))))
            .exchange().expectStatus().isOk();
    }

    @Test
    void wrongScopeReturns403Not401() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.write"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void reportWriteAcceptsWriteScopeWithoutCsrfToken() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.write"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-created");
    }

    @Test
    void reportWriteRejectsReadOnlyScope() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void customPermissionsClaimGrantsCatalogRead() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "permissions", "catalog.read, catalog.write"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("catalog-visible");
    }

    @Test
    void customPermissionsClaimAbsentReturns403() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listPermissionsClaimIsAlsoSupported() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "permissions", List.of("catalog.read")))))
            .exchange().expectStatus().isOk();
    }

    @Test
    void scopeAndPermissionsAreMergedWithoutDroppingDefault() {
        client.get().uri("/api/inspect")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "scope", "reports.read",
                    "permissions", "catalog.read"))))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice")
            .jsonPath("$.authorities[0]")
                .isEqualTo("PERM_catalog.read")
            .jsonPath("$.authorities[1]")
                .isEqualTo("SCOPE_reports.read");
    }

    @Test
    void missingAllAuthoritiesStillAllowsAuthenticatedInspect() {
        client.get().uri("/api/inspect")
            .headers(h -> h.setBearerAuth(signed(Map.of())))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.authorities").isArray()
            .jsonPath("$.authorities.length()").isEqualTo(0);
    }

    @Test
    void scopeAdminIsNotAutomaticallyRoleAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "ADMIN"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredTokenIsRejectedBeforeAuthorityMapping() {
        String token = signed(
            Map.of("scope", "reports.read"),
            true,
            SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            "https://untrusted-issuer.example.invalid",
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            SecurityConfig.ISSUER,
            List.of("another-api"),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongSignatureIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            otherKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerIsRejected() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicCannotReplaceBearerJwt() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "anything"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void jwtCookieCannotReplaceAuthorizationHeader() {
        client.get().uri("/api/reports")
            .cookie("access_token",
                signed(Map.of("scope", "reports.read")))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unitDefaultConverterMapsWhitespaceSeparatedScope() {
        Jwt jwt = Jwt.withTokenValue("unsigned-unit-fixture")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("scope", "reports.read reports.write")
            .build();

        var values = SecurityConfig.scopeAuthorities()
            .convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("SCOPE_reports.read", "SCOPE_reports.write"),
            values);
    }

    @Test
    void unitCustomConverterSplitsCommasAndPrefixesPermissions() {
        Jwt jwt = Jwt.withTokenValue("unsigned-unit-fixture")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("permissions",
                "catalog.read, catalog.write")
            .build();

        var values = SecurityConfig.permissionAuthorities()
            .convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("PERM_catalog.read", "PERM_catalog.write"),
            values);
    }
}
```

Run:

```bash
mvn test
```

**Target: 22 tests** with matching JDK/Maven/dependencies. This is tutorial code to run yourself; **no claim is made that tests were executed in the learner's repository**. The `unitDefaultConverter...` and `unitCustomConverter...` tests use `Jwt` instances **without verified signatures** — strictly to test pure mapping functions. The `WebTestClient` tests send genuinely signed HS256 JWTs through the HTTP server and verify the Bearer/decoder/converter/authorization path, though the issuer/key remain local fixtures.

### 7.2. Test Groups and What Each Proves

| Group | What it proves |
| --- | --- |
| Missing Bearer, wrong signature, expired, invalid issuer/audience | Decoder/authentication rejects token → 401 |
| `scope` string and `scp` array | Default `JwtGrantedAuthoritiesConverter` emits `SCOPE_...` |
| Right/wrong scope on GET/POST | `hasAuthority` distinguishes read/write permissions → 200/403 |
| Custom `permissions` CSV string/array | Dedicated converter reads claim and emits `PERM_...` |
| Combined claims in `/api/inspect` | Default scopes are **not lost** when custom permissions are present |
| `scope=ADMIN` with `hasRole("ADMIN")` | `SCOPE_` is not auto-promoted to `ROLE_` |
| Cookie JWT and HTTP Basic | Bearer-header-only API does not auto-authenticate from ambient cookie/Basic |
| Unit converter | Claim/prefix/delimiter extraction logic; **does not** verify signatures |
| Signed JWT HTTP tests | Real validation/mapper/filter path, **not** merely mocked Authentication |

**Warning about `mockJwt()`:** In many Spring Security tests, `mutateWith(mockJwt().authorities(...))` is designed to bypass signature validation and inject a mock `Authentication` for testing authorization. It suits other unit/slice tests, yet **cannot** serve alone as proof that production's custom `jwtAuthenticationConverter()` is invoked. If using `mockJwt`, either invoke the custom converter explicitly or add signed-token E2E tests as above.

### 7.3. Why Are 401 and 403 Tests Especially Important?

If a token has the right scope but a bad signature, the status must be **401**; never extract `scope` prior to verification and allow entry to the route. If a token is valid but only has `reports.write` and calls a GET requiring `reports.read`, the status is **403**. Separating these helps clients and operations distinguish invalid credentials from missing permissions, avoiding wrong remediation such as trying to refresh a token when the user actually needs additional scope/consent.

## 8. Manual Testing with curl and Demo Tokens

Run:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Some requests without tokens:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/reports
curl -i -H 'Authorization: Bearer not-a-jwt' \
  http://localhost:8080/api/reports
curl -i -u alice:anything \
  http://localhost:8080/api/reports
curl -i -H 'Cookie: access_token=not-a-jwt' \
  http://localhost:8080/api/reports
```

Expected:

- `GET /public` → 200 `public`.
- `GET /api/reports` without Bearer → 401, `WWW-Authenticate: Bearer`.
- Non-valid JWT Bearer → 401.
- HTTP Basic is disabled → 401, grants no permissions from Basic.
- `access_token` cookie is not treated as a Bearer header by the demo Resource Server → 401.

To call protected routes with a valid token, use a **signed test JWT** generated by the test helper in Section 7 or a token from a real Authorization Server configured with the **matching issuer/audience/key**:

```bash
# Bracketed string is a placeholder only; DO NOT paste literally:
curl -i -H 'Authorization: Bearer <VALID_TEST_JWT>' \
  http://localhost:8080/api/reports
```

There is no token issuance endpoint in the demo app; intentionally, the Resource Server **only verifies tokens** and never issues them. `mvn test` generates HS256-signed JWTs in tests to check the happy path without an IdP. Never take the demo HMAC key to production, and never log JWTs/tokens in HTTP access logs, shell history, query strings, or client errors.

On Windows PowerShell, you may need `curl.exe` instead of the `curl` alias. In real systems, require HTTPS, reasonable token lifetimes, issuer/JWK trust, audiences, and rotation; never send real JWTs over plaintext HTTP outside localhost.

## 9. Upgrading from Demo to Real JWT Issuer/JWKS

In production, a Resource Server should rely on a trusted issuer/JWK Set URI rather than a hardcoded symmetric signing key. For example, when the IdP supports OIDC/OAuth2 metadata:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.org/issuer
```

Spring Security can automatically discover JWKS and validate issuer/timestamps from configuration. When avoiding startup dependency on the IdP, you can specify both `jwk-set-uri` (after verifying the trusted value) and `issuer-uri` to keep validating `iss`:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.org/issuer
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.org/issuer/.well-known/jwks.json
```

This is an **alternative configuration** replacing the local `@Bean ReactiveJwtDecoder`; do not mix two decoder sources uncontrollably. Add `OAuth2TokenValidator<Jwt>` instances for audience/token type/tenant/claims per the API contract and security policy.

### 9.1. Never Assume Audience Is Valid Just Because Issuer Matches

One issuer can issue access tokens for many Resource Servers. A validly signed JWT with `aud=other-service` must not be accepted by the reports API. The decoder example in Section 6 includes an audience validator to test wrong-audience tokens → 401. When switching to production `issuer-uri`, retain equivalent validation in your configured official decoder/validators. Never drop an existing audience rule when changing configuration style.

### 9.2. Authority Mapping Must Not Grant Unverified Privileges

Claims `scope`/`scp`/`permissions` become authorizations only if a **genuinely trusted issuer signed the token**, the token is unexpired, and audience and policy match. Never trust manually Base64-decoded payloads, `X-Scope` headers, or raw user-supplied JSON. When scopes depend on tenant context, check ownership in the service/repository; a converter does not replace domain policy.

### 9.3. OIDC ID Tokens Differ from JWT Access Tokens

Many people confuse them because both share the JWT format. An OIDC `id_token` proves an authentication event to the Relying Party; an access token is issued for the Resource Server. A Resource Server must not accept an ID Token in place of an access token merely because it has `sub`/`email`/`scope` and a valid JWS. Check audience, token type, issuer, and how the AS distinguishes tokens.

### 9.4. Expired Tokens Must Still Return 401 Even If Authority Mapping Matches

Expiry/`nbf` validation happens **before** mapped authorities are trusted. Adding `scope=reports.read` to an expired token does not make it valid. If the client holds a refresh token, it must request a new access token from the AS; the Resource Server does not refresh tokens on the client's behalf.

## 10. Choosing Scopes, Permissions, and Roles for Access Policies

Real APIs often have three layers:

- **Scope (OAuth2):** category of action delegated by the AS to the client, e.g., `reports.read`, `reports.write`. Matched via `SCOPE_reports.read`.
- **Permission (domain):** granular permission per product/resource, e.g., `catalog.read`. When issued by the AS in an agreed `permissions` claim, it can map to `PERM_catalog.read`.
- **Role (organization):** privilege group such as `ADMIN` or `SUPPORT`, usually mapped to `ROLE_ADMIN` after verifying issuer, tenant, and role allowlist. `hasRole("ADMIN")` checks for `ROLE_ADMIN`.

An endpoint may require **both a scope and a permission**; avoid collapsing everything into a broad “authenticated” check. At the reactive method security level, you can use `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` when `@EnableReactiveMethodSecurity` is enabled and returning a Publisher, though method security is not enabled automatically merely by having `@EnableWebFluxSecurity`. For controllers/services in this demo project, `authorizeExchange` authorization suffices for illustration.

### 10.1. Example Combined Permission Rule

A domain policy may require:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read') and " +
              "hasAuthority('PERM_catalog.read')")
public Mono<Report> readCombined(String id) {
    return reportRepository.findById(id);
}
```

**Fragment** requires a real `Report` class and repository, enabled annotation, and AOP proxy. Owner/tenant cases must still filter data after scopes/permissions pass, preventing user A's token from reading B's report solely because both have `SCOPE_reports.read`.

### 10.2. When Must Permissions Come from a Database?

JWT scopes/permissions are a **snapshot** issued by the issuer at minting time; if a user's privileges are later revoked, a self-contained JWT can still carry old authorities until expiration. For immediate revocation requirements, design introspection, short token lifetimes, revocation lists, or reactive authorization checks against live data sources. Never call blocking JDBC directly inside `JwtGrantedAuthoritiesConverter` on the event loop.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Token has `scope=reports.read` but gets 403 | Rule expects `ROLE_reports.read`, wrong prefix/case | Use `hasAuthority("SCOPE_reports.read")` |
| Token has `scp` but no authorities emitted | Claim type/decoder or custom claim override | Test `scp` array; avoid accidentally dropping default mapping |
| Custom claim `permissions` produces no authorities | Forgot `setAuthoritiesClaimName("permissions")` | Select the right claim; test format |
| Authority has extra space after comma | Delimiter was just `","` | Use regex `"\\s*,\\s*"` |
| Adding custom claim drops `SCOPE_` | Replaced default converter with custom-only | Merge both converters into one collection |
| `hasRole("ADMIN")` rejects `scope=admin` | `ROLE_` differs from `SCOPE_` | Design dedicated role mapping if policy allows |
| Token with bad signature/issuer/expiry gets 200 | Decoder mocked or validation skipped | Use real decoder + signed-token E2E |
| Wrong-audience token still passes | Missing audience validator | Add `aud` validator, test 401 |
| Mixing Servlet with WebFlux | Used sync converter where reactive type is expected | Use `ReactiveJwtAuthenticationConverterAdapter` |
| `jwtGrantedAuthoritiesConverter` performs blocking DB call | Synchronous I/O on event loop | Move dynamic authz to reactive policy |
| `mockJwt()` tests pass, production returns 403 | Test bypasses converter/custom claims | Test mapper directly and signed JWT E2E |
| Cookie JWT auto-authenticates API | Filter/gateway has cookie fallback | Review CSRF and auth sources; test cookie-only 401 |
| Valid token with scope still reads other tenant's data | Scope-only policy | Enforce owner/tenant in repository and service |
| Debug JSON leaks token/claims | Serializing entire `Jwt` object | Return only approved metadata DTOs |
| Arbitrarily mapping `SCOPE_` to `ROLE_` | Scope privilege escalation | Use explicit prefixes, role allowlists, and domain policy |
| Missing `permissions` yet catalog API returns 200 | Overly broad `authenticated()` matcher or unmatched route | Test 403 on missing permission and default deny |
| POST Bearer API returns 403 due to CSRF | Chain still enforces CSRF | Exempt only when truly bearer-header-only; never broaden to browser cookie routes |

### 11.1. Methodical 401/403 Diagnosis

1. Inspect HTTP status and `WWW-Authenticate`; do not guess solely from the response body.
2. On 401, check Bearer header format, signature algorithm/JWK/secret, `iss`, `aud`, `exp`, `nbf`, and clock skew. Never print full tokens to logs.
3. On 403, inspect Authentication authorities in a safe test environment (never publicly) and compare verbatim against `hasAuthority`/`hasRole`.
4. Check whether the actual JWT claim is `scope`, `scp`, or `permissions`, its string/list type, and delimiter.
5. Verify the converter is wired into `ServerHttpSecurity.oauth2ResourceServer().jwt().jwtAuthenticationConverter(...)`.
6. Check matcher ordering/catch-all and GET/POST methods so another rule does not intercept first.
7. Test that custom claims do not drop default scopes, expired tokens return 401, and missing authorities return 403.
8. Behind a gateway, verify ingress does not convert cookies/ID Tokens into Bearer tokens without a trust policy.

## 12. Secure Implementation Checklist

1. Pick a trusted issuer/AS, HTTPS/JWKS/allowed algorithms, and validate signature, `iss`, `exp`, `nbf`, and `aud`.
2. Document the claim contract: space-separated `scope` or `scp` list, custom CSV/list `permissions`, and case sensitivity.
3. Use default `JwtGrantedAuthoritiesConverter` for scopes; use prefix `SCOPE_` in `hasAuthority` rules.
4. When using custom claims, configure `setAuthoritiesClaimName`, `setAuthoritiesClaimDelimiter`, and `setAuthorityPrefix` appropriately.
5. When both scopes **and** permissions are needed, **merge two converters** instead of replacing the default and losing `SCOPE_`.
6. In WebFlux, use `ReactiveJwtAuthenticationConverterAdapter` or native `ReactiveJwtAuthenticationConverter`, never mixing Servlet signatures.
7. Never perform blocking I/O in conversion logic; handle DB/tenant authorization in reactive authorization/service layers.
8. Never auto-promote `SCOPE_admin` to `ROLE_ADMIN`; define a separate allowlisted role policy.
9. Default-deny route policy, separating read/write scopes and enforcing object-level ownership/tenant checks.
10. Bearer-only APIs must not accept session cookies/Basic automatically; if adding a cookie fallback, re-evaluate CSRF.
11. Unit-test `JwtGrantedAuthoritiesConverter` directly and test signed JWTs via `WebTestClient` to cover decoder/converter/authz together.
12. Include negative tests: 401 for missing/bad signature/wrong issuer/aud/expired, 403 for missing scope/permission/role; never test only 200s.
13. Never log `Authorization` headers or raw JWTs, never return tokens or full claims to browsers; store only redacted safe metadata.
14. When upgrading Spring Security versions or changing IdPs, re-run scope/scp/custom claim tests and verify authorities against a real Resource Server.

## 13. Self-Assessment Questions

**Q1.** Which authorities does JWT `scope="reports.read reports.write"` produce by default?  
`SCOPE_reports.read` and `SCOPE_reports.write`.

**Q2.** Does `hasRole("ADMIN")` accept `scope=admin`?  
Not by default. Scopes normally become `SCOPE_admin`, while `hasRole("ADMIN")` looks for `ROLE_ADMIN`.

**Q3.** If a provider emits `permissions=["catalog.read"]`, does the default converter read it automatically?  
Not with the default scope/scp settings. You need `setAuthoritiesClaimName("permissions")`.

**Q4.** Why do scopes disappear when changing `claimName` to `permissions`?  
A single converter reads only its configured claim. To keep both `SCOPE_` and `PERM_`, merge two converters.

**Q5.** When a `permissions` claim is CSV with spaces, what delimiter should be used?  
Use a regex like `"\\s*,\\s*"` to split on commas and surrounding whitespace.

**Q6.** Can you pass `JwtGrantedAuthoritiesConverter` directly into WebFlux's `jwtAuthenticationConverter(...)`?  
No, wrong contract. You need a converter from `Jwt` to reactive `Authentication`, such as `JwtAuthenticationConverter` wrapped in `ReactiveJwtAuthenticationConverterAdapter`.

**Q7.** Should a JWT with a matching scope but bad signature be authorized?  
No. `ReactiveJwtDecoder` must reject it with 401 before mapping authorities.

**Q8.** Why must `aud` be tested?  
Tokens from the same issuer could be meant for other APIs. The Resource Server must reject wrong-audience tokens.

**Q9.** Is `mockJwt()` sufficient to test real converter/JWT validation?  
No. It suits policy tests; add unit converter tests and signed-token E2E tests.

**Q10.** Is calling `setAuthorityPrefix("ROLE_")` on arbitrary scopes safe?  
Not by default. It can turn scopes into privileged roles; role-specific trust/allowlists and domain policies are required.

**Q11.** Does `hasAuthority("SCOPE_reports.read")` automatically verify owner and tenant?  
No. Per-resource authorization is needed, typically in the service/repository layer.

**Q12.** How do `401` and `403` differ in this lesson?  
401 when there is no valid JWT; 403 when authentication succeeds but authorities/policies are not satisfied.

### Official Documentation

- Spring Security 6.5, *Reactive Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5, *Reactive OAuth2 Resource Server Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security API, `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security API, `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security API, `ReactiveJwtAuthenticationConverterAdapter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- Spring Security API, `ReactiveJwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html
- Spring Security, *Testing JWT Authentication in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- RFC 6750, *OAuth 2.0 Bearer Token Usage*: https://www.rfc-editor.org/rfc/rfc6750
- RFC 9068, *JWT Profile for OAuth 2.0 Access Tokens*: https://www.rfc-editor.org/rfc/rfc9068

**Takeaway:** A JWT Resource Server in Spring WebFlux maps `scope`/`scp` into `SCOPE_...` authorities. Customize `JwtGrantedAuthoritiesConverter` to read other claims or change prefixes/delimiters, and **merge** with the default converter when preserving original scopes. Use `ReactiveJwtAuthenticationConverterAdapter` to plug into `SecurityWebFilterChain`, validate JWTs before granting privileges, test real signed JWTs alongside unit mapping tests, and never auto-convert scopes into roles or skip owner/tenant checks.