# Opaque Tokens and OpaqueTokenIntrospector in Spring Security Resource Server

**Module:** Spring Security – Servlet  
**Parent Topic:** Resource Server

## 1. What Will You Learn in This Lesson?

An **OAuth2 Resource Server** is an API that receives access tokens from clients and serves resources only when the token is accepted along with the required permissions. Access tokens typically appear in requests as:

~~~http
GET /api/reports HTTP/1.1
Authorization: Bearer <access-token>
~~~

In practice, an access token may be a **JWT** or an **opaque token**. When a token is opaque, the API usually cannot decode claims or verify a signature locally like a JWT. Instead, the Resource Server queries the **Authorization Server (AS)** via its **token introspection endpoint** to find out whether the token is active, who or which client uses it, what scopes it carries, and when it expires.

Spring Security Servlet provides the **`OpaqueTokenIntrospector`** interface to perform this step. This lesson teaches you to:

1. Identify opaque tokens and distinguish them from JWTs, refresh tokens, and ID Tokens.
2. Understand RFC 7662, the `active` response, and how a Resource Server decides between 401 and 403.
3. Enable `oauth2ResourceServer().opaqueToken()` in Spring Boot / Spring Security 6.
4. Understand `OAuth2AuthenticatedPrincipal`, `SCOPE_...` authorities, and how to use `hasAuthority`.
5. Customize `OpaqueTokenIntrospector` when verified claims must be mapped into application authorities.
6. Write tests without calling a live Authorization Server, and operate safely when introspection fails, tokens are revoked, or multiple APIs share an IdP.

**Core point:** introspection proves a token against the Authorization Server's policy; **authentication does not replace authorization**. An active token is not automatically allowed to call every endpoint.

## 2. What Is an Opaque Token?

An **opaque token** is a token string whose internal structure callers must not rely on to infer meaning. It might look like a random string:

~~~text
8opqC33hLtRna7Ftm9p4
~~~

The string above is **illustrative data** only, not a real token. Not all opaque tokens share the same length, character set, or prefix; formatting is an Authorization Server implementation detail.

**Its essence is not “a token without dots.”** One Authorization Server may issue JWT access tokens; another system may generate opaque values stored in a token store. A Resource Server should never guess its verification strategy by counting dots or Base64-decoding and trusting contents. What matters is the **token contract between the issuer and the Resource Server**.

| Property | Opaque Access Token (Introspection) | JWT Access Token (Local Validation) |
| --- | --- | --- |
| Resource Server check | Queries Authorization Server via introspection or an equivalent trusted mechanism. | Typically verifies signature/JWK, issuer, audience, expiration, and claims locally. |
| Does token carry API-readable claims? | Must not be assumed. Metadata comes from introspection. | JWT payload contains claims; base64url is **not** confidential encryption. |
| Token revocation | AS can return `active:false` immediately once revocation state updates; caching may add lag. | Self-validated JWTs usually remain usable until `exp` without another revocation/denylist mechanism. |
| Per-request cost | May add a network call, latency, and AS dependency. | No AS call needed per request once valid JWKS is cached. |
| Privacy | Detailed claims do not have to be exposed inside the token string crossing intermediaries. | Claims inside the payload can be read by whoever holds the token. |
| Deployment requirements | Trusted introspection endpoint, TLS, client credentials, timeouts, and error policy. | JWK/issuer/audience, allowed algorithms, signature and claim validation. |

**Opaque does not mean encrypted.** Being unreadable is only a token representation property. If leaked, a bearer token can still be used by an attacker while valid. Always protect access tokens as secrets: HTTPS, avoid logs, query strings, analytics, public clipboards, and unnecessary storage.

**Distinguishing tokens:**

- **Access token:** used by a client to call a Resource Server according to granted permissions.
- **Refresh token:** used with the Authorization Server to obtain new access tokens per allowed flows; never sent as a bearer token to ordinary APIs.
- **ID Token (OIDC):** used by a client to verify a login event and user identity; **never** substitute an ID Token for an access token to call a Resource Server.
- **Session cookie:** represents a web app login session; a stateless Resource Server accepting bearer tokens uses a different protection model.

## 3. Request Flow and Where OpaqueTokenIntrospector Fits

~~~text
Client app
   |
   | GET /api/reports
   | Authorization: Bearer opaque-value
   v
Spring Security Servlet
   |
   v
BearerTokenAuthenticationFilter
   | extracts Bearer token from request
   v
AuthenticationManager / OpaqueTokenAuthenticationProvider
   |
   | introspector.introspect(token)
   v
OpaqueTokenIntrospector
   |
   | HTTPS POST to AS introspection endpoint
   v
Authorization Server
   |-- authenticates Resource Server client credentials
   |-- looks up token, checks active/exp/revocation/policy
   |-- returns matching metadata
   v
OAuth2AuthenticatedPrincipal + authorities
   |
   v
BearerTokenAuthentication / SecurityContext
   |
   v
AuthorizationManager
   |-- sufficient authorities => invoke Controller
   |-- insufficient permissions => 403
   v
Response
~~~

Key components:

- **`BearerTokenAuthenticationFilter`**: locates the bearer token in the request and triggers authentication. Do not write a custom filter to parse tokens manually when framework configuration already covers it.
- **`OpaqueTokenAuthenticationProvider`**: invokes the introspector and produces the authentication result. If the token is invalid, authentication fails.
- **`OpaqueTokenIntrospector`**: contract with method `OAuth2AuthenticatedPrincipal introspect(String token)`. It does not enforce all API business rules; its primary job is validating the token and creating the corresponding principal and authorities.
- **`OAuth2AuthenticatedPrincipal`**: carries `name`, attributes, and `GrantedAuthority` instances obtained from introspection.
- **`BearerTokenAuthentication`**: the Authentication typically stored in SecurityContext for opaque bearer tokens.
- **Authorization**: matchers such as `hasAuthority("SCOPE_reports.read")` decide whether the endpoint may be called.

**Note:** an API can accept tokens solely from `Authorization: Bearer`, without reading JSON bodies or cookies as bearer tokens. Custom token resolvers must be evaluated to avoid leaking tokens via URLs or confusing tokens from untrusted sources.

## 4. RFC 7662: Introspection Request and Response

RFC 7662 describes how a Resource Server asks an Authorization Server about a token's status. An **illustrative** request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

`token_type_hint` is an **optional hint**, not something that determines success or failure; the Authorization Server must still verify the token. How the client authenticates to the introspection endpoint depends on the deployment contract; a common setup uses HTTP Basic with `client-id` and `client-secret`. Never embed real client secrets in documentation or source code.

**Example response for an active token:**

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "report-client",
  "scope": "reports.read reports.write",
  "token_type": "Bearer",
  "exp": 1794000000,
  "iss": "https://identity.example.test"
}
~~~

Not every claim is always present; `sub` may be absent in certain flows, `scope` can vary, and `aud`/tenant/client policies may require separate checks. The values above are examples, not mandatory responses from every IdP.

**Example response when a token is no longer accepted:**

~~~json
{"active": false}
~~~

A token may be inactive because it expired, was revoked, does not exist, or is not disclosed to the querying Resource Server. The system should not speculate on detailed state from `active:false` alone, nor send internal reasons back to the client.

Points to remember:

1. `active:true` comes from the **authenticated introspection endpoint**, not an `active` claim in a request that a client can forge.
2. The Resource Server must trust only its configured AS endpoint; verify TLS, endpoint identity, and client authentication. Never take an arbitrary introspection URL from a bearer token or request.
3. `active:true` **does not guarantee** the token was issued for the right **resource/audience/tenant**; if the AS returns `aud`, `iss`, `client_id`, `token_type`, or custom claims, application policy may need additional checks.
4. Revoked access tokens usually produce `active:false`, though immediacy also depends on the AS and **caching** in the Resource Server / gateway.
5. Error HTTP responses, timeouts, malformed responses, or AS unavailability **must never** be turned into successful authentication to “preserve user experience.”

### 4.1. Comparing 401 and 403

| Scenario | Typical API Outcome |
| --- | --- |
| Endpoint requires authentication but **no token** is sent | `401 Unauthorized` with an appropriate bearer challenge. |
| Malformed, nonexistent, or `active:false` token | `401 Unauthorized` when treated as an invalid bearer token. |
| Valid token lacking the required scope/authority | `403 Forbidden` (`insufficient_scope` may appear in the challenge). |
| Introspection service unreachable or returns malformed data | Access denied; exact HTTP status may depend on error handling and infrastructure, **not guaranteed to always be 401**. |
| Active token with scopes, accessing a resource outside ownership/tenant | Must be rejected at the business authorization layer, regardless of broad scopes. |

Do not use `403` to mask all authentication failures: distinguishing 401/403 helps clients and monitoring pinpoint issues, while **never putting token/secret contents** in error bodies.

## 5. Runnable Configuration: Spring Boot 3 + Spring Security 6 + Opaque Tokens

This example uses **Java 17+** and **Spring Boot 3.3.5**, matching Spring Security 6.x in this Boot BOM. Use supported versions and keep patches current in real systems.

This application is a **Servlet API**: a public GET, a GET requiring read scope, a POST requiring write scope, and a minimal endpoint to inspect principal info. It requires an RFC 7662-compliant Authorization Server for live calls.

**Directory structure:**

~~~text
opaque-demo/
├── pom.xml
└── src/
    ├── main/java/demo/OpaqueDemoApplication.java
    ├── main/resources/application.yml
    └── test/java/demo/OpaqueDemoApplicationTests.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>opaque-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
~~~

### 5.2. `src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

These are **Spring environment placeholders**, not hardcoded IDs/secrets. When running, set the three real environment variables:

- `INTROSPECTION_URI`: fixed HTTPS URL of the introspection endpoint provided by the IdP.
- `INTROSPECTION_CLIENT_ID`: client allowed by the Authorization Server to introspect.
- `INTROSPECTION_CLIENT_SECRET`: corresponding secret, loaded from environment/secret manager.

**Never** use `http://...` outside local secret-free test environments; never place client secrets in Git, log screenshots, or URL parameters. Some IdPs only allow introspection with a specific client authentication method; this example assumes the method configured by Spring Security's `client-id`/`client-secret`.

### 5.3. `src/main/java/demo/OpaqueDemoApplication.java`

~~~java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OpaqueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Suitable ONLY for a stateless API authenticating via bearer tokens
            // in the Authorization header, NOT authenticating via cookies.
            .csrf(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public")
        Map<String, String> publicEndpoint() {
            return Map.of("status", "public");
        }

        @GetMapping("/api/reports")
        Map<String, String> readReport() {
            return Map.of("status", "read-ok");
        }

        @PostMapping("/api/reports")
        Map<String, String> writeReport() {
            // Illustrates authority check; does not persist real data.
            return Map.of("status", "write-ok");
        }

        @GetMapping("/api/me")
        Map<String, Object> currentUser(Authentication authentication) {
            Set<String> authorities = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

            // Return minimal data for observation only.
            return Map.of(
                "principal", authentication.getName(),
                "authorities", authorities
            );
        }
    }
}
~~~

Configuration explanation:

- `oauth2ResourceServer(...opaqueToken(...))` instructs Spring Security to process bearer tokens via introspection. With the `opaquetoken` properties above, Spring Boot creates a suitable default introspector when no custom bean exists.
- `hasAuthority("SCOPE_reports.read")` and `hasAuthority("SCOPE_reports.write")` are endpoint authorization rules. `scope` from introspection is typically converted by Spring Security into authorities prefixed with **`SCOPE_`**.
- `SessionCreationPolicy.STATELESS` avoids creating security sessions as authentication state for this API. Securing bearer tokens **still requires HTTPS** and protecting tokens from leakage.
- `csrf.disable()` here **applies only to a pure stateless API receiving tokens in the Authorization header without relying on auto-sent cookies**. If the app also has session/cookie web login or browser auto-attached credentials on endpoints, evaluate CSRF separately rather than copying this blindly.
- For example, `GET /public` passes through the security filter chain as `permitAll`; `/api/me` requires a valid bearer token and returns only observational data. Production systems should avoid unnecessarily exposing authority lists.
- This example authorizes only by broad scopes. Real applications may also need **audience, tenant, owner, status**, and object-level authorization checks.

### 5.4. Running and Calling the API

From the project directory, after setting the three environment variables:

~~~bash
mvn spring-boot:run
~~~

Test the public endpoint:

~~~bash
curl -i http://localhost:8080/public
~~~

Expected HTTP 200, JSON `{"status":"public"}`. Localhost may use HTTP for practice without real tokens; deploying and testing with **real tokens requires HTTPS**.

Test a protected endpoint:

~~~bash
# ACCESS_TOKEN must be issued by the matching Authorization Server.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

Expected outcome depends on introspection: active token with `reports.read` scope → HTTP 200; missing/invalid token → typically 401; active token without read scope → 403. Environment variable syntax on Windows/PowerShell differs from Bash; `$ACCESS_TOKEN` in the example is Bash syntax.

Never put real tokens into command screenshots, potentially collected shell history, logging tools, or tickets. Use secret-management tools appropriate for your environment.

## 6. OpaqueTokenIntrospector: Interface and Return Value

Spring Security 6 defines the interface in package:

~~~java
org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector
~~~

Core method:

~~~java
OAuth2AuthenticatedPrincipal introspect(String token);
~~~

This is an **API signature for explanation**, not a standalone Java file. An implementation typically:

1. Receives the token string from the authentication provider.
2. Sends a request to the configured introspection endpoint.
3. Handles `active`, authentication errors, missing fields, or response metadata.
4. Maps metadata into an `OAuth2AuthenticatedPrincipal` and a set of `GrantedAuthority` instances.
5. Returns the principal when accepted, or throws an appropriate exception if rejected.

Example reading principal details in a controller/service:

~~~java
// Illustrative snippet inside a method with an Authentication parameter.
if (authentication.getPrincipal() instanceof
        org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal p) {
    String subject = p.getAttribute("sub");
    Object audience = p.getAttribute("aud");
    // Only use attributes after evaluating issuer/audience/tenant policies.
}
~~~

Never trust `authentication.getName()` as an immutable email or as globally unique across all issuers. With multiple IdPs, a stable identifier may be the **`issuer + subject`** pair, though you must confirm metadata and trust boundaries. `username` can change, and `sub` can carry different semantics per issuer.

## 7. Customizing the Introspector to Map Claims to Authorities

An API sometimes receives a valid response like:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "reports.read",
  "app_roles": ["auditor", "manager"]
}
~~~

The Resource Server wants to additionally emit:

- `app_roles: ["auditor"]` → `ROLE_AUDITOR`
- `app_roles: ["manager"]` → `ROLE_MANAGER`
- Any unknown value, wrong type, or missing claim → **grant no corresponding role**

Before mapping, confirm the contract that **the trusted Authorization Server itself populates `app_roles` in the introspection response**, and this API is authorized to rely on that claim. Never read `app_roles` from client-controlled request bodies, URLs, or headers.

### 7.1. Custom Bean (Add Only When Truly Needed)

Create the optional class **`src/main/java/demo/IntrospectionAuthoritiesConfiguration.java`**. This class uses `NimbusOpaqueTokenIntrospector` as a delegate to perform real introspection, preserves default authorities, and adds a role **allowlist**:

~~~java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionAuthoritiesConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, clientId, clientSecret);

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(principal.getAuthorities());

            Object raw = principal.getAttribute("app_roles");
            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (!(item instanceof String role)) {
                        continue;
                    }

                    switch (role.trim().toLowerCase(Locale.ROOT)) {
                        case "auditor" ->
                            mapped.add(new SimpleGrantedAuthority("ROLE_AUDITOR"));
                        case "manager" ->
                            mapped.add(new SimpleGrantedAuthority("ROLE_MANAGER"));
                        default -> {
                            // Unknown role: grant no authority.
                        }
                    }
                }
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                mapped
            );
        };
    }
}
~~~

**Usage:** add this class file when custom mapping is required; **omit it** when default scopes alone suffice. A custom-defined `OpaqueTokenIntrospector` bean is used by Spring Security for the corresponding resource server. Place the custom class in package `demo` so `@SpringBootApplication` scans it.

**Safety points:**

- Always call the delegate introspector before granting roles; **never** replace it with `token -> principal` trusting arbitrary client tokens.
- Only grant `ROLE_AUDITOR` / `ROLE_MANAGER` from an allowlist; never construct `ROLE_` from arbitrary claim strings.
- Missing or mistyped claims yield no roles; this is **fail closed for additional business authorities**.
- Keep `SCOPE_...` and original authorities produced by the delegate so verified read/write rights are not accidentally dropped.
- If sensitive roles depend on audience/tenant/issuer, enforce those checks **before granting the role**.
- When targeting a Spring Security version other than the one listed above, verify introspector constructors/deprecations for your version; never copy APIs from old tutorials without compiling.

Example role-based endpoint rule:

~~~java
// Illustrative line inside authorizeHttpRequests of SecurityFilterChain:
.requestMatchers("/api/audit").hasRole("AUDITOR")
~~~

`hasRole("AUDITOR")` by default checks for `ROLE_AUDITOR`, whereas `hasAuthority("SCOPE_reports.read")` checks the exact scope authority; the two concepts cannot be swapped arbitrarily.

### 7.2. When Extra Validation of the Introspection Response Is Needed

Beyond roles, an app may need to restrict tokens to the **right audience/resource**, `iss`/tenant, or token type. The `OpaqueTokenIntrospector` interface lets you add logic after the delegate validates introspection, but do so strictly:

- Reject the token if a mandatory claim is missing or outside the allowed set.
- Never match audience or issuer by substring; use explicit data types/schemas.
- If `aud` can be a string or an array, the API spec must define how both are handled.
- Do not equate `client_id` with user privileges unless business policy explicitly permits it.
- Evaluate metadata per grant type: `sub` does not always represent the same kind of principal.

**Policy example:** this Resource Server accepts only tokens confirmed by the AS for audience `reports-api`. If introspection returns an `aud` missing that audience, **reject even when active=true**. Exact code depends on claim data types and the AS's authorization model; the example in section 7.1 only demos role mapping and **does not implement audience checking**. Do not assume section 7.1 enforces audience bounds.

## 8. Security Testing Without a Running AS

Distinguish two testing levels:

- **Security test with a mocked `OpaqueTokenIntrospector`:** verifies Spring Security extracts bearer tokens, attaches authorities, and decides 401/403/200; makes no real HTTP introspection calls.
- **Integration test with a simulated AS/introspection endpoint:** verifies HTTP Basic client authentication, `token` form body, JSON parsing, `active:false`, timeouts, and secret rotation. Use a mock HTTP server suited to your test framework; ensure fake tokens can never be accepted in production.

### 8.1. MockMvc Test for Section 5's Configuration

**`src/test/java/demo/OpaqueDemoApplicationTests.java`:**

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/introspect",
    "spring.security.oauth2.resourceserver.opaquetoken.client-id=test-client",
    "spring.security.oauth2.resourceserver.opaquetoken.client-secret=test-secret"
})
@AutoConfigureMockMvc
class OpaqueDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    OpaqueTokenIntrospector introspector;

    @BeforeEach
    void setUp() {
        var reader = new DefaultOAuth2AuthenticatedPrincipal(
            "user-reader",
            Map.of("sub", "user-reader", "scope", "reports.read"),
            List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
        );
        var writer = new DefaultOAuth2AuthenticatedPrincipal(
            "user-writer",
            Map.of("sub", "user-writer", "scope", "reports.write"),
            List.of(new SimpleGrantedAuthority("SCOPE_reports.write"))
        );
        when(introspector.introspect("reader-token")).thenReturn(reader);
        when(introspector.introspect("writer-token")).thenReturn(writer);
        when(introspector.introspect("revoked-token"))
            .thenThrow(new BadOpaqueTokenException("Inactive token"));
    }

    @Test
    void publicEndpointDoesNotRequireToken() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public"));
    }

    @Test
    void missingOrRevokedTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer revoked-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanReadButCannotWrite() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer reader-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("read-ok"));

        mvc.perform(post("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer reader-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCanWriteButCannotRead() throws Exception {
        mvc.perform(post("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer writer-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("write-ok"));

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer writer-token"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expected:** four tests pass. This is the expectation for the sample code, not output captured from a live run. The mock bean replaces network introspection: the tests prove Spring Security **uses the introspector's outcome** and checks authorities, **not** that a real Authorization Server returns accurate metadata.

**Note when enabling the optional class from section 7.1:** because that class declares its own introspector bean, your test suite must also be structured to override/mock beans cleanly. To unit test custom mapping logic in isolation, inject the delegate as a dependency so you can test with a fake principal—covering unknown roles, mistyped claims, and ensuring privileges cannot escalate beyond the allowlist.

### 8.2. Other Tests You Should Have

| Test Case | Purpose |
| --- | --- |
| AS returns `active:false` | Ensure the API does not build a valid authentication. |
| AS returns 401/403 to introspection client | Detect bad `client-id`/`secret`; never treat token as active. |
| AS timeout, TLS error, 5xx, JSON missing `active` | Fail closed, monitor, and handle errors properly. |
| Empty scope string, mistyped claims | Invent no authorities; return results per policy. |
| User with `SCOPE_reports.read` accessing another tenant's resource | Object-level authorization denies if unpermitted. |
| Roles claim contains `superadmin` outside allowlist | Does not auto-grant `ROLE_SUPERADMIN`. |
| Revoked token while caching is enabled | Verify stale-cache window falls within acceptable risk. |
| Token issued for another API | Reject when policy requires a specific audience/resource. |
| Multiple security filter chains | Ensure the Resource Server's matcher targets the right endpoints. |
| HTTPS behind reverse proxy/CDN | Tokens and client secrets never leak in logs or accidental HTTP links. |

## 9. Caching, Latency, and Revocation: The Core Trade-off of Introspection

If a Resource Server queries the Authorization Server on **every request**, aggregate load can grow large. For instance, 500 requests/second means up to roughly 500 introspection calls/second without caching or another load-reduction tier. Actual numbers depend on system architecture.

### 9.1. When to Cache?

Some systems cache introspection outcomes per token to cut latency and AS load. However:

- Caching an `active:true` result too long can keep allowing a **revoked** token.
- TTL must never exceed token `exp` and must respect near-immediate revocation requirements; strict policies may **forbid caching**.
- Never cache indefinitely; account for role/scope config changes, multi-node deployments, clock skew, and tenants.
- Cache keys contain tokens (secrets). If caching, protect keys/entries, partition or securely hash keys by design, and avoid logging tokens.
- Negative caching for invalid tokens also carries memory/DoS risks if clients flood arbitrary strings; enforce size bounds and eviction.
- Caching `active:true` without checking `audience`, scopes, or updated policies can cause authorization bugs even while tokens remain unexpired.

**Do not** hand-roll a cache with an unbounded global `Map<String, OAuth2AuthenticatedPrincipal>` lacking TTL, memory limits, and revocation policy.

### 9.2. AS Availability and Error Handling

Introspection depends on the network. You need:

1. Sensible **connection and read timeouts**, never letting API requests hang indefinitely.
2. Appropriate connection pooling / reuse / circuit breakers, while **never falling back to allow-all** when the service fails.
3. Controlled retries to avoid amplifying load during an AS outage; distinguish network failures from invalid tokens.
4. Monitoring for 401/403 rates, introspection latency, TLS failures, 5xx responses, and cache hit/miss ratios if cached.
5. Deliberate degradation: sensitive endpoints must **deny access when verification fails**; public endpoints can continue operating independently of tokens.

**Fail closed:** when token validity cannot be proven, **never grant authorities** just to boost availability. Return appropriate operational errors to clients without exposing tokens or client secrets.

## 10. Common Implementation Mistakes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| API returns 401 on a freshly issued token | Wrong introspection URI, token from another issuer, AS rejects client credentials, inactive or expired token. | Verify server-side issuer/endpoint/credentials, check safe logs, compare AS response in test env. |
| API returns 403 for an active token | Missing required `SCOPE_...` or token fails resource policy. | Check scopes/authorities, matchers, audience, and resource-level rights. |
| Token looks like a JSON JWT yet opaque is configured | System chose introspection strategy regardless of token shape. | Confirm contract with issuer; never switch decoders based on token appearance. |
| `scope` is `reports.read` yet rule uses `hasRole("reports.read")` | Role prefix differs from scope authority. | Use `hasAuthority("SCOPE_reports.read")` per default mapping. |
| AS returns `app_roles` yet `ROLE_AUDITOR` is missing | Default does not map arbitrary claims to business roles. | Write a custom allowlist introspector with verified source claims. |
| Public endpoint still triggers network introspection when sent a bad bearer token | Filter processes bearer tokens sent even on `permitAll` requests. | Avoid sending unnecessary bearer tokens to public endpoints; understand `permitAll` does not bypass filters. |
| AS outage breaks all protected endpoints | Introspection sits on the authentication path. | Timeouts, monitoring, HA architecture, policy-backed caching; never fail open. |
| Revoked token still accepted | Cache still valid or AS state propagation lagged. | Shorten TTL, design purge/revocation, and test revocation SLAs. |
| 401 after secret rotation | Resource Server still uses old credentials. | Secret manager, safe distribution/rotation, watch client-auth errors. |
| Tokens appear in logs | Full Authorization header, query parameter, or exception payload logged. | Redact Authorization, disable sensitive logging, restrict log access. |
| API 200 with scope yet returns another tenant's data | Checked scope only, not object ownership. | Enforce ownership, tenant, and per-resource policies in the service layer. |

## 11. Production Security and Operations

### 11.1. End-to-End Protection of Bearer Tokens

- Use **HTTPS** from client to API and from API to introspection endpoint; verify certificates and hostnames properly.
- Never pass bearer tokens in query parameters, and never put tokens in logs, analytics, or error messages.
- Consider short token lifetimes, minimal scopes, rotation, and revocation.
- Restrict who may introspect, and ensure the AS returns only the minimum metadata needed by that API.
- Introspection credentials are **Resource Server secrets**, not user tokens; manage them in a secret store and rotate them.
- CORS is neither a token validation mechanism nor an access barrier for arbitrary API callers. Never use `Access-Control-Allow-Origin: *` to “fix” authentication failures.

### 11.2. Scopes, Roles, and Object-Level Authorization

`active:true` alone **is not enough**. Every endpoint needs a complete policy:

~~~text
1. Is the Bearer token valid?
2. Was it issued for the right API / audience / issuer / tenant?
3. Does it hold the required scope/role?
4. Is the principal authorized for the specific resource ID and data state?
5. Does the business flow require extra checks, transactions, or auditing?
~~~

If an API exposes `/api/accounts/{id}`, a token with `SCOPE_accounts.read` still does not guarantee the caller may view **every** account. Bind the user/client to resource IDs, tenants, or system policies.

### 11.3. Resource Server and Web Application Sharing One Backend

If one system acts as both an **OAuth2 Client** logging users in via sessions/cookies and a **Resource Server** receiving bearer tokens, you likely need **multiple SecurityFilterChain beans** separated by path and `@Order`. The `csrf.disable()` setup of a pure bearer-token API **must never be applied blindly** to cookie/session forms. Bearer-token and cookie authentication have different CSRF models.

### 11.4. Introspection and Metadata Privacy

Responses may include `sub`, `username`, `client_id`, `scope`, `aud`, and custom claims. Keep/expose only necessary data. When multiple IdPs issue tokens, identify trusted issuers and namespace identities; never merge identical `sub` strings from two different issuers into the same person.

## 12. Step-by-Step Verification Procedure

**Step 1 — Identify access token type.** Ask the AS team whether introspection is supported, the URI, client auth method, and claim schema. Never guess from the token string.

**Step 2 — Minimal configuration.** Use the resource server starter, the three `opaquetoken` properties, and `oauth2ResourceServer().opaqueToken()`. Never write a custom token parser.

**Step 3 — Test a valid test token.** Confirm `active:true`, right scopes, and authorized endpoint returning 200. Never put real tokens in public docs.

**Step 4 — Test failures.** Missing token, bad/revoked token, AS error, token lacking scope, wrong audience, cross-tenant resource.

**Step 5 — Verify mapping.** Safely log/print **authority names** in a test environment (never log tokens), checking `SCOPE_reports.read` and any allowlisted roles.

**Step 6 — Latency and revocation.** Measure real network latency, configure timeouts, and verify revocation effectiveness and cache TTLs against risk tolerance.

**Step 7 — Monitoring and operations.** Audit and metrics with minimal data; verify secret rotation, AS high availability, HTTPS certificates, and fail-closed behavior.

## 13. Self-Check Questions

**Question 1:** Must an opaque token always be a random string with no embedded information?

**Answer:** Not necessarily. “Opaque” means the Resource Server **does not rely on token structure to parse and verify it locally**. The AS decides how to generate/store tokens and returns metadata via introspection.

**Question 2:** If introspection returns `active:true`, should every endpoint return 200?

**Answer:** No. The API must still check scopes/roles, audience/resource, tenant, and object-level authorization.

**Question 3:** When 401 and when 403?

**Answer:** Normally missing or invalid token → 401; valid token with insufficient permissions → 403. Introspection infrastructure failures may go through separate error handling and should not be assumed to always return 401.

**Question 4:** Should `OpaqueTokenIntrospector` decode a JWT payload to extract roles?

**Answer:** No. It takes the token and relies on introspection results or the designated verification source. If a Resource Server uses local JWT validation, the corresponding setup is `jwt()` and JWT converters.

**Question 5:** Why not cache `active:true` for one hour for every token?

**Answer:** A token may expire or be revoked before an hour passes; stale cache creates a window accepting invalid tokens. TTL, capacity, key protection, and revocation SLAs must be designed explicitly.

**Question 6:** When the Authorization Server temporarily loses network connectivity, should the API assume tokens are valid?

**Answer:** No. If a token cannot be verified, never grant shortcut access; handle errors, timeouts, availability, and operational monitoring cleanly.

---

**Conclusion:** In Spring Security Servlet Resource Server, opaque tokens are verified via **`OpaqueTokenIntrospector`** and a trusted introspection endpoint. **`active` proves token status, not permission for every action**. After authentication, enforce `SCOPE_...`/allowlisted roles, bind audience/tenant/resource, handle revocation/caching responsibly, protect credentials, and **never fail open** when introspection is unavailable.