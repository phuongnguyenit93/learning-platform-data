# AuthenticationManagerResolver for Multiple Issuers with a Trusted Allowlist in Spring Security Servlet

## 1. The Multi-Issuer Resource Server Problem

In a multi-organization system, an API may accept access tokens issued by multiple independent Authorization Servers or realms. For example, an order management application accepts users from organizations A and B:

- **Issuer A:** https://id-a.example.org/realms/a.
- **Issuer B:** https://id-b.example.org/realms/b.
- **Resource Server:** a Spring MVC API at https://api.example.org.

Both clients send access tokens in requests:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

The Bearer token snippet above only illustrates structure. Real access tokens are sensitive credentials; never copy tokens into source code, query strings, tickets, or logs.

With a single issuer, a Resource Server typically configures one **JwtDecoder** based on issuer-uri. With multiple issuers, each issuer may have its own JWK Set, signing keys, policies, tenants, and metadata. You need a mechanism that decides **which AuthenticationManager checks the current token** without bypassing validation.

**AuthenticationManagerResolver<T>** is the Spring Security interface that makes that choice. On the Servlet stack, T is usually **HttpServletRequest**. **JwtIssuerAuthenticationManagerResolver** is the specialized JWT implementation: it inspects the **iss** claim to pick the corresponding manager.

The most important point: the iss value is read **before the JWT signature is verified**. It is merely an untrusted routing hint, **not proof** that the token came from a legitimate issuer. The system must reject issuers outside a curated list and only use the matching decoder/JWK for approved issuers.

The goal of this lesson is to understand FilterChainProxy, BearerTokenAuthenticationFilter, resolvers, trust mechanisms, Java 17+ code with Spring Boot 3.x / Spring Security 6.x, testing, and troubleshooting.

## 2. Distinguishing Resolver, Authentication, and Authorization

| Concept | Question It Answers |
| --- | --- |
| AuthenticationManagerResolver | Which manager should verify the credential on this request? |
| AuthenticationManager | Does the credential prove a valid identity? |
| JwtAuthenticationProvider | Uses a JWT decoder to verify signature/claims and create Authentication |
| JwtDecoder | Does the JWT have a valid signature, issuer, lifetime, and claims per policy? |
| AuthorizationFilter | Is the authenticated principal permitted to call the endpoint? |
| Business authorization | Is the principal permitted to access that specific record or tenant? |

For example, an access token from A may be valid and have scope orders.read. That does not mean it is permitted to read tenant B's orders. The resolver selects how to verify the token, and then API-layer and business-layer authorization must still enforce permissions on resources.

**A Resource Server never issues access tokens itself.** The Authorization Server issues tokens; the OAuth client obtains and sends tokens; the Resource Server only verifies them and decides access to protected resources.

**An access token is not an ID token.** OpenID Connect ID tokens are meant for login clients; APIs must require access tokens with the right audience, issuer, token profile, and permissions.

## 3. Processing Flow in FilterChainProxy

~~~text
Client sends Authorization: Bearer <token>
                  |
                  v
Servlet container (Tomcat/Jetty...)
                  |
                  v
DelegatingFilterProxy -> FilterChainProxy
                  |
                  v
Matching SecurityFilterChain
                  |
                  v
BearerTokenAuthenticationFilter
                  |
                  +--> BearerTokenResolver reads Authorization header
                  |
                  +--> BearerTokenAuthenticationToken (unauthenticated)
                  |
                  +--> AuthenticationManagerResolver<HttpServletRequest>
                          |
                          v
                     Reads iss from JWT
                     SIGNATURE NOT YET VERIFIED
                          |
                     Exact allowlist lookup
                      /             \
                  Unknown issuer   Approved Issuer A/B
                    |                 |
                  Reject        AuthenticationManager A/B
                                      |
                                 JwtAuthenticationProvider
                                      |
                                 JwtDecoder A/B
                                      |
                      Verifies signature, exp, nbf, iss, aud
                                      |
                          JwtAuthenticationToken
                                      |
                                SecurityContext
                                      |
                              AuthorizationFilter
                               /             \
                    Missing permission   Sufficient permission
                           -> 403              |
                                              v
                                  DispatcherServlet/Controller
~~~

This diagram shows functional steps; relative positions of other filters may vary by configuration. BearerTokenAuthenticationFilter lives in the security filter chain created by Spring Security when **oauth2ResourceServer(...)** is enabled.

If no token is present, BearerTokenAuthenticationFilter usually lets the request proceed. A permitAll endpoint can work; an endpoint requiring authentication receives a 401 challenge at the authorization layer. If a malformed or untrusted token is present, authentication fails before the controller executes.

**The resolver does not directly sign, decode, or verify JWTs.** It chooses an AuthenticationManager; that manager must perform cryptographic verification and token validators.

## 4. Why Must iss Be Treated as Untrusted?

A JWS-formatted JWT normally has three parts:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Example payload:

~~~json
{
  "iss": "https://id-a.example.org/realms/a",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000000
}
~~~

Anyone can **craft these claims** as a JSON string and Base64URL-encode them. The iss claim is trustworthy only after the JWT's signature is verified and appropriate validators have run. With JwtIssuerAuthenticationManagerResolver, the framework reads iss first to know which decoder to try; that step is not authentication.

Consider a flawed design:

~~~java
// UNSAFE idea; getIssuerUnverified is an illustrative placeholder method name.
String issuer = getIssuerUnverified(token);
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

The snippet above is not a standalone compilable Java file. The risk lies in taking an issuer from an unverified token and **fetching issuer metadata/JWK dynamically**. An attacker can supply an address they control to make the API trust their keys, or point to internal hosts causing SSRF. Thousands of forged issuers could also spawn excessive decoders or discovery requests.

Safety rules:

1. The trusted issuer set must exist prior to requests and be approved by the system.
2. The iss claim is only used to **look up** in this set, never to add new issuers.
3. Unapproved issuers must be rejected; never fetch metadata/JWKs from unknown URLs.
4. Approved issuers select the AuthenticationManager bound to that issuer's own keys and validators.
5. The chosen decoder must still verify **the signature and actual iss**. Never treat lookup success as authentication.

## 5. Designing a Trusted Issuer Allowlist

Configuration example:

~~~text
TRUSTED:
  https://id-a.example.org/realms/a
  https://id-b.example.org/realms/b

LOOKUP:
  iss=https://id-a.example.org/realms/a  -> manager A
  iss=https://id-b.example.org/realms/b  -> manager B
  iss=https://evil.example.net          -> no manager
  iss=http://127.0.0.1:8080             -> no manager
~~~

The allowlist must **match the entire issuer URI string exactly**—never use startsWith, contains, or shared suffixes. Prefix matching can mistakenly trust URIs with extra hostnames, paths, or realms outside policy. Trailing slashes must also match the Authorization Server's metadata/contract rather than being arbitrarily stripped/normalized from client tokens.

Never allow clients to supply issuers via X-Issuer, query parameters, JWT payloads, or paths. Trusted configuration sources can be managed application config, an approved onboarding registry, or an internal admin-controlled database. Onboarding an issuer must verify ownership, HTTPS, JWK Set URI, algorithms, audience, token profile, and operational owner.

Do not confuse **issuer identifier** with **JWK Set URI**. The issuer is the value matched against the iss claim; the JWK Set URI is the controlled source of public keys for signature verification. Never take jku or x5u from JWT headers to decide where to fetch keys.

## 6. Spring Security: Single Issuer vs. Multiple Issuers

Typical configuration for a single issuer:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://id-a.example.org/realms/a
~~~

And DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(org.springframework.security.config.Customizer.withDefaults())
);
~~~

With multiple issuers, the Resource Server uses a resolver:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(trustedIssuerResolver)
);
~~~

Here **trustedIssuerResolver** has type AuthenticationManagerResolver<HttpServletRequest>. Each request carrying a JWT from an issuer gets its own manager. You do not need to manually register BearerTokenAuthenticationFilter with addFilterBefore; the Resource Server DSL adds the required filter.

**Do not select a manager by trying every decoder until one succeeds.** That adds latency and blurs boundaries across issuers, keys, and audiences. With issuer-based routing, select the exact trusted issuer first and require that issuer's own manager to verify the token.

## 7. Spring Boot 3.x / Spring Security 6.x / Java 17+ Example

This example uses **two fixed issuers**, one shared API, and the orders-api audience. The example.org domains are illustrative only, not live token-issuing systems. To run end-to-end, replace issuers and JWK URIs with real data from active Authorization Servers and obtain real access tokens.

### 7.1. Dependencies

In build.gradle of a Spring Boot project with the Boot plugin/BOM configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Use a Spring Security version compatible with the Spring Boot BOM; do not mix arbitrary versions. This example uses Servlet API **jakarta.servlet**, not legacy javax.servlet.

### 7.2. Main Application

File src/main/java/demo/multiissuer/MultiIssuerApplication.java:

~~~java
package demo.multiissuer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiIssuerApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiIssuerApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: Map issuer → manager → decoder

File src/main/java/demo/multiissuer/SecurityConfig.java:

~~~java
package demo.multiissuer;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    private static final String ISSUER_A =
        "https://id-a.example.org/realms/a";
    private static final String ISSUER_B =
        "https://id-b.example.org/realms/b";

    private static final String JWK_A =
        "https://id-a.example.org/realms/a/certs";
    private static final String JWK_B =
        "https://id-b.example.org/realms/b/certs";

    private static final String API_AUDIENCE = "orders-api";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            trustedIssuerResolver() {
        Map<String, AuthenticationManager> managers = Map.of(
            ISSUER_A, managerFor(ISSUER_A, JWK_A),
            ISSUER_B, managerFor(ISSUER_B, JWK_B)
        );

        // Only return a manager for issuers present in the server-managed map.
        return new JwtIssuerAuthenticationManagerResolver(managers::get);
    }

    private static AuthenticationManager managerFor(
            String issuer, String trustedJwkSetUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null
                    && values.contains(API_AUDIENCE)
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        return provider::authenticate;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest>
                    trustedIssuerResolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/health"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(trustedIssuerResolver)
            )
            .build();
    }
}
~~~

**Line-by-line analysis of the code:**

- Map.of holds two fixed issuers and accepts no client input. A JWT claiming any other issuer will find no manager.
- JwtIssuerAuthenticationManagerResolver reads the unverified iss claim for lookup; picking A does not prove the token was issued by A.
- Manager A owns a decoder bound to JWK A; B owns a decoder bound to JWK B. Both JWK URLs come from trusted server configuration.
- JwtValidators.createDefaultWithIssuer(issuer) includes default checks and verifies the matching iss claim. Never replace it with an audience-only validator that skips issuer and expiration checks.
- The audience validator requires aud to contain orders-api. A token from issuer A meant for another application still cannot call this API even with a valid signature.
- JwtAuthenticationProvider creates a JwtAuthenticationToken from the JWT once accepted by the decoder; scope/scp are typically mapped to GrantedAuthority instances with prefix SCOPE_.
- The orders rule requires SCOPE_orders.read, other API paths require authentication, and URLs outside the example scope hit denyAll.
- STATELESS is the session policy for Bearer APIs. **csrf.disable() is appropriate only when the example genuinely uses client-attached Bearer tokens without cookie/session auto-attached authentication on state-changing operations.** Applications with browser sessions need dedicated CSRF protection or separate SecurityFilterChains.

**Runnability note:** the class above compiles with compatible Spring Boot 3 / Security 6 versions. However, example.org addresses are illustrative data; successful JWT verification requires configuring real issuers, JWK URIs, algorithms, audiences, and access tokens from approved AS instances. Each issuer may need a specific algorithm policy if it does not use the decoder's default algorithm.

### 7.4. Controller to Observe Verified Principals

File src/main/java/demo/multiissuer/ApiController.java:

~~~java
package demo.multiissuer;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "issuer", jwt.getIssuer().toString(),
            "subject", String.valueOf(jwt.getSubject())
        );
    }

    @GetMapping("/orders")
    public Map<String, String> orders() {
        return Map.of("result", "read-permitted");
    }
}
~~~

GET /api/public/health requires no token. GET /api/me requires a valid token from a trusted issuer. GET /api/orders additionally requires the orders.read scope. In real applications, avoid returning full JWTs/claims to clients; checking permission to view **specific orders** still belongs in the business layer.

With a project having a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Call the API over HTTPS after replacing illustrative URIs with real configuration:

~~~bash
curl -i https://api.example.org/api/public/health
curl -i https://api.example.org/api/me \
  -H "Authorization: Bearer $TOKEN_FROM_A"
curl -i https://api.example.org/api/orders \
  -H "Authorization: Bearer $TOKEN_FROM_B"
~~~

Never put tokens directly into source files; environment variables, terminal history, APM, and proxy logs still need protection. If token B is valid, has aud=orders-api, and carries scope orders.read, the orders endpoint can return 200. If token B is valid yet lacks that scope, authorization returns 403.

## 8. Validators That Must Not Be Skipped

### 8.1. Signature and Algorithm

A JWS-signed JWT does not mean the payload is encrypted. The decoder must verify the signature using public keys from a **trusted** JWK Set, restrict signing algorithms per the issuer's policy, and never blindly trust alg, jku, or x5u parameters sent by the token. If the token carries a kid, kid only helps locate a key in the trusted JWK Set; it is not an instruction to download keys from the Internet.

### 8.2. Issuer After Manager Selection

The issuer lookup in the resolver is only a routing hint. When the decoder runs, it must verify that the iss claim matches **the exact issuer of the selected manager**. A token signed with key B that claims iss=A must fail in decoder A.

### 8.3. Timestamps

Normally you must check exp and nbf per the framework's clock skew policy. iat may need separate constraints per token profile. An expired token is invalid even if its signature remains valid.

### 8.4. Audience

The API must verify that aud contains its own API identifier, such as orders-api. A properly signed token issued for frontend-client, analytics-api, or another resource server should not be accepted. **issuer-uri alone does not replace audience validation** when policy requires an audience.

### 8.5. Token Type

A Resource Server accepts **access tokens**, not arbitrarily OpenID Connect ID tokens meant for login clients. If the system follows a specific token profile, verify claim/type per contract. Never accept a JWT simply because it has three parts and decodes as JSON.

### 8.6. Scopes and Authorities

Spring Security typically converts scope/scp claims into GrantedAuthority instances like SCOPE_orders.read. Thus a hasAuthority("SCOPE_orders.read") rule requires the token to carry scope orders.read per the configured converter. Custom roles from issuer A do not automatically equate to ROLE_ADMIN or roles from issuer B.

## 9. Alternate Form: the fromTrustedIssuers Factory

In Spring Security versions that support it, you can build a resolver directly from a list of trusted issuers using the factory:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id-a.example.org/realms/a",
        "https://id-b.example.org/realms/b"
    );
~~~

This snippet shows a **Spring Security version-dependent** API. Check the library version you use; some earlier 6.x releases had different constructors or mechanisms. If you need per-issuer audiences, custom converters, or pinned JWK URIs, the issuer → AuthenticationManager map in section 7 expresses policy more explicitly.

**Whether using the factory or a map, never accept arbitrary issuers.** Trust policy must be server-controlled. A convenient factory does not mean tokens from a valid issuer automatically have the right audience or sufficient business permissions.

## 10. Multi-Tenant: Issuers, Subjects, and Resource Ownership

At least three architectural patterns are easily confused:

1. **One issuer per tenant:** tenant A tokens have iss=A, tenant B tokens have iss=B. The resolver knows which manager to pick, but reading tenant data must still be checked on the backend.
2. **One shared issuer, multiple tenants:** iss is identical; a tenant_id or organization_id claim separates tenants. An issuer-based resolver alone is not enough to isolate tenant data.
3. **Multiple issuers for one organization:** different identity providers may both be permitted to call one API. Clear account-linking and permission rules are required.

Two issuers can both assign sub="42" to two completely different people. Never treat **sub alone** as a globally unique identifier. You typically need an **(issuer, subject)** namespace or map subjects to verified internal IDs.

Never treat X-Tenant-ID, query tenant parameters, or path /tenants/A as identity proof. Those values describe the resource the client wants to act on; the system must cross-check them against the decoder-verified principal and per-record authorization rules. Scope orders.read is only a broad read privilege; it does not prove ownership of every order.

## 11. Controlled Dynamic Issuer Updates

With two fixed issuers, Map.of is easy to audit. With hundreds of tenants, you can maintain a trusted registry updated by an admin team. A lazy resolver can:

1. Read the unverified iss.
2. Check **exact membership** in a trusted registry snapshot.
3. If absent or disabled, reject immediately.
4. If present, create or retrieve the AuthenticationManager from the **JWK URI/validators configured in the registry**.
5. Cache managers by trusted issuer and policy version.
6. When an issuer is revoked, update the registry and invalidate managers/caches per procedure.

Cap decoder counts, protect concurrency, and set timeouts and retries. Writing computeIfAbsent on an un-allowlisted iss lets attackers spawn thousands of managers or force the API to call internal URLs. The registry must be admin-managed, never accepting writes from JWTs or request headers.

When adding an issuer, verify the operational owner, domain ownership, TLS, metadata, JWK, algorithms, audience, scope semantics, and key/revocation plan. When removing an issuer, ensure running app instances do not keep stale trusted snapshots beyond a controlled rollout window.

## 12. Multi-Layer Testing

### 12.1. Testing Exact Allowlist Policy with Standalone JDK 17

The code below tests membership logic only; it does not decode JWTs. File TrustedIssuerDemo.java:

~~~java
import java.util.Set;

public class TrustedIssuerDemo {
    public static void main(String[] args) {
        Set<String> trusted = Set.of(
            "https://id-a.example.org/realms/a",
            "https://id-b.example.org/realms/b"
        );

        System.out.println(
            trusted.contains("https://id-a.example.org/realms/a")
        );
        System.out.println(
            trusted.contains("https://evil.example.net")
        );
        System.out.println(
            trusted.contains("https://id-a.example.org/realms/a.evil")
        );
    }
}
~~~

Run:

~~~bash
javac TrustedIssuerDemo.java
java TrustedIssuerDemo
~~~

Exact stdout:

~~~text
true
false
false
~~~

This example shows exact matching blocking unknown issuers and prefix-alike strings. It cannot replace testing JwtIssuerAuthenticationManagerResolver or signatures.

### 12.2. Testing Spring Security Authorization with MockMvc

With spring-security-test, the **jwt()** postprocessor creates a simulated JWT Authentication. It is suitable for testing scope rules and controllers, but **skips** Bearer token extraction, manager resolution, and signature verification.

In a Spring Boot test that already has a matching SecurityFilterChain, test:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "profile.read"))))
    .andExpect(status().isForbidden());
~~~

This is an **abbreviated test snippet** placed inside a @Test method with an mvc MockMvc field and corresponding static imports, not a standalone Java file. Because jwt() bypasses real authentication, even a forged iss claim would pass if the test grants sufficient authorities. Never cite it as proof that the allowlist works.

### 12.3. Tests That Actually Traverse the Bearer Filter and Resolver

Use an HTTPS test issuer/JWK endpoint or test fixtures with matching signing keys, and issue HTTP requests with Authorization: Bearer. Essential matrix:

| Request | Correct Outcome |
| --- | --- |
| JWT A signed with key A, iss=A, aud=orders-api, scope=orders.read | Authentication A succeeds; /api/orders permitted |
| JWT B signed with key B, iss=B, aud=orders-api, scope=orders.read | Authentication B succeeds; /api/orders permitted |
| JWT whose issuer is not in the allowlist | 401; no metadata/JWK fetched for the unknown issuer |
| JWT claiming iss=A yet signed with key B | Decoder A rejects signature |
| Properly signed JWT with wrong aud | Authentication fails |
| Expired or not-yet-valid (nbf) JWT | Authentication fails |
| Valid JWT lacking orders.read | 403 at authorization |
| JWT without iss / malformed JSON / malformed header | Never falls back to a default manager |
| Valid JWT A accessing tenant B's order | Object-level authorization must deny |
| JWK endpoint A times out | Never skips signature verification to fall back open |

Integration tests must verify status codes, WWW-Authenticate where appropriate, zero controller side effects on blocked cases, zero outbound network calls to unknown issuers, and correct chain routing. You can run a dedicated mock HTTP server to serve test metadata/JWKs under trusted config; never use URLs supplied inside unverified payloads.

### 12.4. Testing Multiple SecurityFilterChains

If an application has one chain for APIs and another for form login, **only the first matching chain** is chosen by FilterChainProxy. Test both /api/** URLs and fallback routes. A resolver does not protect requests outside a configured chain. Order specialized chains properly and define a safe fallback.

## 13. Distinguishing 401, 403, and Network Errors

| Scenario | Typical Response | Layer to Inspect |
| --- | --- | --- |
| Missing Bearer token on protected endpoint | 401 Unauthorized | Security entry point |
| Untrusted issuer | 401 Unauthorized | JwtIssuerAuthenticationManagerResolver |
| Bad JWT signature, expired, wrong aud or iss | 401 Unauthorized | JwtDecoder / JwtAuthenticationProvider |
| Valid JWT yet missing scope | 403 Forbidden | AuthorizationFilter / method security |
| Valid JWT yet resource belongs to another tenant | 403 or 404 depending on resource-hiding policy | Business authorization |
| JWK endpoint unavailable | Depends on verification error and exception handling | Network, decoder, metrics |
| Malformed Bearer header | 400 or 401 depending on error type | BearerTokenResolver / entry point |

Example Bearer challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When a token is invalid, it may include:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Do not assume every 401 means an unknown issuer; a proxy may have stripped the Authorization header, or the request may have hit a different SecurityFilterChain. Do not assume every 403 means a missing scope, because CSRF, authorization rules, and method security can also block requests.

## 14. Operations: JWK Rotation, Observability, and Safety

- **TLS and token hygiene:** transmit Bearer tokens only over HTTPS; never log Authorization headers, refresh tokens, client secrets, or private keys. Redact tokens in APM, exceptions, proxy logs, and tracing.
- **Key rotation:** a trusted issuer's JWK Set can rotate keys/kids. Configure sensible caching and refresh, reliable TLS connectivity, and key transition overlap if required by the Authorization Server.
- **Availability:** local JWT validation avoids introspection on every request yet still depends on JWK refreshes. When an AS fails, never pass unverified tokens; design timeouts, bounded retries, alerting, and per-issuer observability.
- **Token revocation:** unexpired JWTs may still be accepted without extra revocation mechanisms. If business rules require fast revocation, consider short token TTLs, denylists/introspection, or a contract-appropriate architecture.
- **Bounded caching:** never instantiate a new decoder per request or arbitrary issuer. Cache managers only for issuers in the trusted registry.
- **Authorization policy:** issuer A's scopes do not automatically equate to issuer B's roles. Normalize claims intentionally and enforce data ownership in services.
- **Auditing:** log authentication results, verified issuer, request ID, timestamp, and error category without logging raw tokens or sensitive claims.
- **Blocking untrusted resources:** never read jku/x5u or metadata URLs from unverified JWTs; outbound network calls go only to trusted configured JWK endpoints.

## 15. Common Design Mistakes

**Mistake 1 — Accepting any HTTPS issuer.** HTTPS only secures transport to that host; it does not authorize that host as a trusted Authorization Server for your API. An allowlist is mandatory.

**Mistake 2 — Running discovery from an unverified iss.** Can cause SSRF and trust attacker keys. Always match against the trusted registry first, then use the server-managed JWK URI.

**Mistake 3 — Matching issuer in the resolver and skipping issuer validation.** Lookup does not verify the token; the decoder must still verify iss after signature verification using default validators.

**Mistake 4 — Forgetting audience.** A token from issuer A meant for a frontend must not be accepted by the orders API. Configure an aud validator matching the resource server.

**Mistake 5 — Treating sub as a globally unique ID.** Two issuers can assign the same sub. Use an issuer + subject namespace or safely linked internal IDs.

**Mistake 6 — Blindly equating one issuer's roles/scopes with another's.** You need a per-issuer contract and converter, especially in multi-tenant applications.

**Mistake 7 — Using MockMvc jwt() to claim fake-issuer protection works.** jwt() mainly mocks Authentication; it does not prove the resolver, signature, or JWK trust. Add end-to-end Bearer tests.

**Mistake 8 — Disabling CSRF across an app that also has cookie login.** Stateless Bearer APIs can usually disable CSRF under that credential model, while cookie-based browser flows still need separate evaluation and protection.

**Mistake 9 — Using multiple chains without a fallback.** Some URLs may bypass intended protections. Review FilterChainProxy match order and deny-by-default rules.

**Mistake 10 — Removing an issuer from a dashboard while its manager remains in runtime cache.** You need a refresh/invalidation policy when revoking a trusted issuer.

## 16. Checklist and Conclusion

- [ ] Issuers are approved before accepting requests; use an exact allowlist instead of prefix/suffix matching.
- [ ] The resolver treats iss strictly as an **untrusted routing hint**; unknown issuers never trigger discovery.
- [ ] Each issuer has its own manager, decoder, JWK source, and contract-aligned validators.
- [ ] JWTs are verified for signature, issuer, lifetime, and audience; algorithms are never taken blindly from the JWT.
- [ ] Scope and tenant claims are interpreted safely; object-level authorization is enforced.
- [ ] SecurityFilterChain selects the right resolver and fallbacks leave no unprotected URLs.
- [ ] Bearer tokens travel only over HTTPS and never leak via query strings/logs/tracing.
- [ ] Allowlist unit tests, authorization tests, and real Bearer/JWK integration tests exist for valid and unknown issuers.
- [ ] Processes for issuer onboarding/revocation, key rotation, JWK outage monitoring, and manager caching are audited.
- [ ] Operations distinguishes 401 authentication errors, 403 authorization errors, and JWK/network errors.

**Remember:** AuthenticationManagerResolver solves **selecting who verifies the token**, rather than replacing token verification itself. With multiple issuers, the right flow is **allow only issuers on the trusted allowlist → select the corresponding manager → decoder verifies signature and claims → authorization decides resource permissions**.
