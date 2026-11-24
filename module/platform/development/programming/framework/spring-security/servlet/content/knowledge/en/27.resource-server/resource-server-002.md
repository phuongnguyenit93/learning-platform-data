# oauth2ResourceServer and Bearer Token Processing Flow in Spring Security Servlet

## 1. What Problem Does a Resource Server Solve?

An API needs to know **which requests are allowed and with what permissions**. When using OAuth 2.0, a client (a web app, mobile app, or another service) obtains an **access token** from an Authorization Server after an appropriate authorization grant flow, and then sends that token when calling the API. The API acts as the **OAuth 2.0 Resource Server**: it receives the access token, verifies that the token is valid, converts the token's information into an Authentication object, and enforces authorization rules.

In Spring Security Servlet, configuring **http.oauth2ResourceServer(...)** enables the set of components that handle this type of request. Tokens are commonly sent according to RFC 6750:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
Accept: application/json
~~~

The truncated token above only illustrates the header shape. An actual access token is a secret string that must be protected. A Resource Server **does not issue tokens itself**, does not perform OAuth 2.0 login flows itself, does not refresh access tokens itself, and does not turn a client into an Authorization Server.

This lesson covers **Spring Security Servlet / Spring MVC** (Spring Boot 3.x, Spring Security 6.x, Java 17+). The focus is on how **BearerTokenAuthenticationFilter** receives tokens, how JWT/opaque tokens are verified, how the SecurityContext is populated, and how AuthorizationFilter makes access decisions.

Learning objectives:

- Distinguish OAuth 2.0 **client**, **Authorization Server**, **Resource Server**, and **protected resource**.
- Understand that a Bearer token is a credential based on **token possession**, and why HTTPS is required.
- Trace the full path Authorization header → filter → AuthenticationManager → JWT decoder or opaque introspector → SecurityContext → authorization → controller.
- Configure a JWT Resource Server with issuer, JWK, and claims; understand how it differs from opaque token introspection.
- Interpret 401/403 status codes and the WWW-Authenticate header when a token is invalid or lacks scope.
- Write configurations and tests respecting the boundary between **mocked JWT authorization tests** and **real Bearer decoding/verification tests**.

## 2. The Four Roles and Responsibility Boundaries

| Role | Responsibility | Example |
| --- | --- | --- |
| Resource Owner | Owner of the data or permission to use the resource | User with profiles, invoices |
| Client | Obtains an access token via an OAuth 2.0 flow and calls the API | Web frontend, mobile app, service |
| Authorization Server | Authenticates/authorizes, issues access tokens, publishes keys or an introspection endpoint | Identity provider |
| Resource Server | Protects the API, verifies tokens, and decides access to data | Spring MVC REST API |

Illustrative system:

~~~text
                   (1) OAuth 2.0 grant
 Client --------------------------------------> Authorization Server
   |                                                   |
   |               (2) access token                    |
   |<--------------------------------------------------|
   |
   | (3) GET /api/reports
   |     Authorization: Bearer <access token>
   v
 Resource Server (Spring Security Servlet)
   |  - extract Bearer token from request
   |  - verify JWT signature or query introspection endpoint
   |  - convert claims/scopes into Authentication
   |  - evaluate authorization rules
   v
 Protected resource / Controller
   |
   +--> (4) response when allowed
~~~

The **Bearer** designation means anyone who possesses a valid token string can use it within its issued lifetime and scope. The token is not cryptographically bound to a single device simply because the Bearer scheme is used. Never place tokens in URLs/query strings, never log token values, and never put them in public documentation or screenshots. Transmit tokens over **HTTPS** and store them on the client using an appropriate security model.

**An access token is different from an ID token.** An OpenID Connect ID token primarily describes an authentication event for the client, with the audience typically set to the client_id. A Resource Server must accept an **access token intended for its API** and verify audience/issuer according to the contract. Never treat a login ID token as a valid access token merely because it is also a properly signed JWT.

## 3. Bearer Request Processing Flow in the Servlet Filter Chain

A request flows through the servlet container and Spring Security in the following general order:

~~~text
HTTP request
    |
    v
DelegatingFilterProxy("springSecurityFilterChain")
    |
    v
FilterChainProxy -> matching SecurityFilterChain
    |
    +--> SecurityContextHolderFilter and related filters
    |
    +--> BearerTokenAuthenticationFilter
    |       |
    |       +--> BearerTokenResolver reads Authorization: Bearer ...
    |       |
    |       +--> AuthenticationManager
    |                 |
    |                 +--> JWT: JwtAuthenticationProvider
    |                 |         -> JwtDecoder -> JwtAuthenticationToken
    |                 |
    |                 +--> opaque: OpaqueTokenAuthenticationProvider
    |                           -> OpaqueTokenIntrospector
    |                           -> BearerTokenAuthentication
    |
    +--> Other filters (e.g., ExceptionTranslationFilter)
    |
    +--> AuthorizationFilter: checks authority/scope/role
    |
    v
DispatcherServlet -> Controller (if allowed)
~~~

This diagram only reflects the **functional** positions you need to learn; it does not list every internal filter across all versions or the exact relative ordering among all other filters. Configuring form login, CSRF, CORS, or multiple SecurityFilterChains changes the detailed filter list.

### 3.1. No Bearer Token Present

By default, **DefaultBearerTokenResolver** looks for a token in the Authorization header with the Bearer scheme. If no token is present, BearerTokenAuthenticationFilter normally **does not create a login session itself**, and lets the request continue. At authorization time, a public endpoint may return 200; an endpoint requiring authentication will be blocked and typically return **401 Unauthorized** with WWW-Authenticate: Bearer.

That is very different from “the filter must immediately throw an error when a request lacks a token.” Whether authentication is required is an endpoint-level policy.

### 3.2. Bearer Token Present

BearerTokenAuthenticationFilter extracts the token and creates a **BearerTokenAuthenticationToken** (an unauthenticated Authentication). The filter passes this object to the appropriate AuthenticationManager.

- For JWTs, **JwtAuthenticationProvider** calls **JwtDecoder** to parse and verify the JWT, then maps it into a **JwtAuthenticationToken** containing a Jwt principal and authorities.
- For opaque tokens, **OpaqueTokenAuthenticationProvider** calls **OpaqueTokenIntrospector** to validate the token via introspection, then creates a **BearerTokenAuthentication** with an OAuth2AuthenticatedPrincipal principal.

Upon success, the filter places the authenticated Authentication in **SecurityContextHolder** for request processing. Spring MVC and method security can then use that principal, its claims, and its authorities. Upon failure, the Resource Server's entry point handles the response instead of letting the controller run.

### 3.3. Checking Permissions After Authentication

AuthorizationFilter evaluates rules such as authenticated(), hasAuthority("SCOPE_reports.read"), and hasRole("ADMIN"). A **valid** Bearer token can still lack a scope or authority and be rejected with **403 Forbidden**. Token verification answers “did the client present trustworthy proof?”; authorization answers “does that proof have permission for this operation?”.

Having a SecurityContext for the request does not mean the server created an HTTP session. For Bearer-only APIs, stateless configuration is standard; subsequent requests must carry their own valid tokens.

## 4. Where Does the Token Come From? RFC 6750 and BearerTokenResolver

The standard and preferred method:

~~~http
Authorization: Bearer <access-token>
~~~

DefaultBearerTokenResolver reads the Authorization header. Distinguish these cases:

| Request Form | Typical Outcome |
| --- | --- |
| Authorization: Bearer valid-token | Can be authenticated after token validation |
| No Authorization header | Public endpoints may proceed; protected endpoints typically return 401 |
| Malformed Bearer token or ambiguous multiple token locations | May be rejected with an OAuth/Bearer request error |
| Well-formed Bearer token with bad signature, expired, or wrong issuer | Authentication fails, typically 401 |
| Valid token lacking the endpoint's required permission | Typically 403 |
| Basic header on a Resource Server-only API | Not a Bearer token; not accepted as an OAuth access token |

Some RFCs allow transporting tokens via form body or query parameters under certain conditions. However, **DefaultBearerTokenResolver discourages this and does not enable reading tokens from query parameters by default**. Query strings easily end up in browser history, proxy logs, monitoring, Referer headers, and support docs; avoid this approach. If a special compatibility requirement exists, assess the threat model before replacing BearerTokenResolver.

You can customize the header or resolver via the DSL, but standard systems should keep Authorization: Bearer so gateways, HTTP clients, and monitoring behave consistently.

## 5. JWT Resource Server: Format and Verification Steps

A **JWT (JSON Web Token)** typically has three dot-separated parts:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

A **signed** JWT does not mean its contents are **encrypted**. The header and payload of a typical JWS/JWT can be base64url-decoded and read. Never put passwords, private keys, or long-lived secrets in claims.

Illustrative payload of an access token:

~~~json
{
  "iss": "https://login.example.org/realms/lab",
  "sub": "account-42",
  "aud": ["reports-api"],
  "scope": "reports.read profile.read",
  "iat": 1750000000,
  "nbf": 1750000000,
  "exp": 1750003600
}
~~~

The timestamps above **only illustrate the claim structure** and do not represent a token usable at the time you read this lesson. A valid token must be issued by a real Authorization Server, carry a valid signature, and have appropriate validity timestamps.

Fields to understand:

- **iss (issuer):** the entity that issued the token. The Resource Server must compare it against a trusted issuer.
- **sub (subject):** the subject identity described by the token; often used as the principal name, though it does not itself grant admin rights.
- **aud (audience):** the API/target the access token is intended for. The Resource Server should require an audience belonging to its API.
- **exp / nbf / iat:** expiration, not-before, and issued-at timestamps. The decoder typically performs appropriate time validation; iat does not automatically enforce every freshness policy.
- **scope or scp:** the granted permission scopes. Spring Security has a default converter to turn them into authorities prefixed with **SCOPE_**.
- **kid/alg in the JWT header:** helps select the public key and signature verification algorithm. The Resource Server must configure trusted algorithms and key sources, never blindly accepting whatever algorithm the client requests.

JWT verification path:

1. BearerTokenAuthenticationFilter extracts the token.
2. JwtAuthenticationProvider asks JwtDecoder to verify the token.
3. The decoder parses the structure, verifies the signature using trusted public keys/JWKs, and runs validators for timestamps and configured claims.
4. JwtAuthenticationConverter turns the JWT into a JwtAuthenticationToken and authorities.
5. Authorization rules decide whether the request enters the controller.

**Verifying the signature alone is not enough.** A token for another application can still be signed by the same trusted Authorization Server. Therefore, you must validate the **audience** for your API; in many Spring Security setups, aud validation **is not enabled automatically from issuer-uri alone**. Similarly, do not rely on custom username or role claims without a defined mapping and trust contract.

### 5.1. JWK Set and Key Rotation

The Authorization Server can publish a **JWK Set URI** containing public keys. When a token is signed with the corresponding private key, JwtDecoder selects the public key based on JOSE header information (such as kid) and verifies the signature. The Resource Server needs to fetch new keys periodically when the issuer rotates keys. Ensure outbound connectivity to the JWK endpoint, valid HTTPS certificates, reasonable caching, and an overlap window between old and new keys.

Never store the private signing key in a Resource Server solely to verify asymmetrically signed JWTs. Cases where the issuer uses a shared secret key have their own contract; for most APIs and organizations, public-key verification provides cleaner separation of responsibilities.

## 6. Configuring JWT on Spring Boot 3.x and Spring Security 6.x

### 6.1. Dependencies

In a Spring Boot project managing dependency versions via the BOM, in build.gradle (Groovy):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Security needs resource-server and JWT JOSE support for the JWT branch; Spring Boot's Resource Server starter pulls in the matching dependency set. Do not declare a Spring Security version that diverges from the Boot BOM without an explicit compatibility reason.

### 6.2. Configuring the Issuer

File src/main/resources/application.properties:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.org/realms/lab
~~~

The URI above **is a placeholder example**; a real application must use the exact issuer provided by its Authorization Server. issuer-uri configures the decoder using the issuer's discovery metadata and checks iss via Spring Security's mechanism. Initializing the decoder via discovery may require the Authorization Server to be reachable at startup, depending on configuration mode.

If the system has a fixed JWK Set URI and you want to avoid relying on discovery at startup, you can set **both issuer-uri and jwk-set-uri** pointing to the endpoints of the same issuer:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.org/realms/lab
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://login.example.org/realms/lab/protocol/openid-connect/certs
~~~

Both URIs are architectural examples only. Spring Security must still verify the signature against the JWK set and check the issuer; supplying a JWK Set URI does not automatically trust tokens from arbitrary issuers.

### 6.3. Configuring SecurityFilterChain

File src/main/java/demo/resourceserver/SecurityConfig.java:

~~~java
package demo.resourceserver;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Explanation:

- **oauth2ResourceServer(...jwt(...))** enables Bearer token processing and JWT validation for this chain. This is an API receiving access tokens, not an OAuth login client.
- **STATELESS** tells Spring Security not to create or use an HTTP session to store the SecurityContext for the API. New requests must bring their own tokens.
- **permitAll()** allows the health endpoint; the reports endpoint requires **SCOPE_reports.read**; other APIs require authentication; URLs outside /api/** are denied in this example.
- **csrf.disable()** only makes sense for an API designed to **authenticate solely via a Bearer token explicitly placed in the Authorization header**, without cookies automatically sent to authenticate state-changing operations. If the same app also has session/cookie login or a browser mechanism that auto-attaches credentials, evaluate CSRF properly—potentially splitting into multiple SecurityFilterChains instead of disabling it globally.

You do not need to manually register BearerTokenAuthenticationFilter with addFilterBefore: the Resource Server DSL creates the required components. When multiple SecurityFilterChains exist, JWT configuration, session policy, and endpoint matchers must be placed on the chain that actually protects the API; only the first matching chain is used.

### 6.4. A Java Application and Controller to Observe the Principal

File src/main/java/demo/resourceserver/ResourceServerApplication.java:

~~~java
package demo.resourceserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}
~~~

File src/main/java/demo/resourceserver/ApiController.java:

~~~java
package demo.resourceserver;

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
    public Identity me(@AuthenticationPrincipal Jwt jwt) {
        return new Identity(
            jwt.getSubject(),
            jwt.getIssuer() == null ? "" : jwt.getIssuer().toString()
        );
    }

    @GetMapping("/reports")
    public Map<String, String> reports() {
        return Map.of("report", "visible-to-reports.read");
    }

    public record Identity(String subject, String issuer) {}
}
~~~

This is a standalone Spring Boot example at the application/controller/security level, requiring a real issuer and an access token issued by that issuer to test protected endpoints. Do not use an empty “bearer” value or fake tokens when testing. The /api/me endpoint only returns a few principal fields for learning; in real products avoid returning full tokens or sensitive claims.

When running over real HTTPS with a valid access token placed in the shell environment variable TOKEN, for example:

~~~bash
curl -i https://api.example.com/api/public/health
curl -i https://api.example.com/api/me -H "Authorization: Bearer $TOKEN"
curl -i https://api.example.com/api/reports -H "Authorization: Bearer $TOKEN"
~~~

Using a shell variable avoids writing raw tokens directly into shared examples; shell history, runtime environments, proxies, and CI logs also need to be controlled. Illustrative paths and hostnames must point to a deployment with matching certificates and issuer.

If a valid token has the reports.read scope, GET /api/reports can return HTTP 200 with JSON containing the report. If a valid token lacks this scope, the reports endpoint will be rejected with 403 even though /api/me may still succeed.

## 7. JWT Authorities: Scopes Differ from Roles and Other Claims Governing Authorization

With the default JwtAuthenticationProvider, Spring Security uses **JwtAuthenticationConverter** and a component that extracts authorities from claims. Typically, scope or scp claims are mapped as follows:

~~~text
JWT claim:  "scope": "reports.read profile.read"
     |
     v
GrantedAuthority("SCOPE_reports.read")
GrantedAuthority("SCOPE_profile.read")
~~~

Therefore:

~~~java
.requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
~~~

matches a scope-based resource server. **hasAuthority("reports.read")** will not match because it lacks the prefix when using the default converter. **hasRole("ADMIN")** typically checks for the authority ROLE_ADMIN; custom roles in a JWT will not automatically become ROLE_ADMIN unless you configure a converter.

If an issuer has a custom contract such as roles, permissions, or custom scopes, write/register a JwtAuthenticationConverter with clear rules. Do not merge untrusted claims into high-privilege authorities. Also never use information from request parameters to assign roles.

**Audience validation is independent of scope.** A token with the reports.read scope whose aud targets another service must still not be accepted by the reports API.

### 7.1. Example Adding an Audience Validator

When the API requires aud to contain reports-api, you can explicitly create a decoder with validators for issuer and audience, backed by the configured JWK endpoint. This is an **alternative to letting Boot auto-create JwtDecoder** when you want full control over validators.

In the same package, an illustrative Java configuration:

~~~java
package demo.resourceserver;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("https://login.example.org/realms/lab") String issuer,
            @Value("https://login.example.org/realms/lab/protocol/openid-connect/certs")
                    String jwkSetUri) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> defaultAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("reports-api")
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultAndIssuer, audience
            )
        );
        return decoder;
    }
}
~~~

The example uses @Value with **illustrative URI values** to show structure, not as a recommendation to hard-code issuer/JWK endpoints in production. Real applications must load configuration from controlled environment sources and ensure **issuer and JWK are trusted endpoints under the same contract**. If the application already defines its own JwtDecoder bean, update or replace the existing bean rather than declaring two conflicting decoder beans.

JwtValidators.createDefaultWithIssuer combines default checks (including timestamps per supported policy) with issuer validation. The audience validator requires the aud claim to contain reports-api. When an API serves multiple audiences or trusts multiple issuers, build explicit policies for each case; never skip audience checks to “accept all tokens.”

**Do not assume** that a Resource Server uses token introspection or instant revocation when running in JWT mode. As long as a JWT remains unexpired and its key/signature/claims are valid, it may continue to be accepted until expiration or until blocked by additional system-designed controls.

## 8. Opaque Tokens: Verification via Introspection Instead of JWT Decoding

An **opaque access token** can be an arbitrary string without a readable three-part structure. The Resource Server cannot verify claims and signatures locally like a JWT; instead, it typically calls the Authorization Server's **OAuth 2.0 Token Introspection Endpoint** (RFC 7662). The endpoint returns fields such as active, scope, client_id, sub, exp, etc., depending on the contract.

Flow:

~~~text
Client -> Resource Server
         Authorization: Bearer token
              |
              v
        BearerTokenAuthenticationFilter
              |
              v
        OpaqueTokenAuthenticationProvider
              |
              v
        OpaqueTokenIntrospector
              |
              +---- HTTPS request (token + client credentials)
              |               |
              |               v
              |        Introspection Endpoint
              |               |
              +<--- active + claims/scope
              |
              +--> if token is active and policy is valid:
                   create Authentication, then check authorities
~~~

Example introspection response:

~~~json
{
  "active": true,
  "sub": "account-42",
  "scope": "reports.read",
  "client_id": "dashboard-client",
  "exp": 1750003600
}
~~~

All values are structural examples, not a real API response. **Introspection client credentials are a secret belonging to the Resource Server**, separate from the user's Bearer access token; never send either credential type to a browser.

Configuration replacing JWT mode:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.org/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=reports-resource-server
~~~

In addition to these properties, you must provide **client-secret** through a secret manager or Spring Boot environment variable; never place real secrets in the repository. The SecurityFilterChain bean uses:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(org.springframework.security.config.Customizer.withDefaults())
)
~~~

This is a **replacement for the .jwt(...) configuration**, not something to copy alongside the previous JWT example. With opaque tokens, controllers do not default to receiving a Jwt principal via @AuthenticationPrincipal Jwt; use Authentication or OAuth2AuthenticatedPrincipal accordingly.

**Tradeoff**: introspection lets the Authorization Server decide whether a token is still active at check time and can support near-real-time token revocation, but each request may require a network call; plan for latency, timeouts, availability, and caching if policy allows. Do not assume the API will always return 401 when the Authorization Server loses connectivity: token-verification infrastructure failures may manifest differently depending on exception handling and fallback configuration.

JWT and opaque are **two verification strategies**, not names of client flows: access tokens issued via client credentials or authorization code flows can be either JWT or opaque, depending on the Authorization Server.

## 9. Authentication, 401/403, and WWW-Authenticate

Easily confused statuses:

| Scenario | Typical Result | Meaning |
| --- | --- | --- |
| GET public endpoint, no token | 200 if controller succeeds | Security does not require authentication on that endpoint |
| GET protected endpoint, no token | 401 + WWW-Authenticate: Bearer | Client needs to supply a token |
| Syntactically valid Bearer with bad signature/issuer/timestamps | 401, possibly with error=invalid_token | Authentication failed |
| Malformed Bearer token or invalid transport | 400 or 401 depending on error; Bearer header describes error | Malformed token request |
| Valid access token, insufficient scope | 403, possibly with error=insufficient_scope | Authenticated, but lacks permission |
| Valid access token, endpoint allowed | 200/2xx or business-appropriate status | Request reached the controller |

Example authentication challenge header (structural illustration):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

With an invalid token, the server may return equivalent details:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

If scope is missing, some responses may contain:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Do not treat any status as absolute: reverse proxies, CORS, firewall request rejections, custom entry points, controller exceptions, and multiple SecurityFilterChains can alter responses. **401** does not prove no token was sent; **403** does not prove CSRF failed. Use error types, logs, and the actual filter chain to diagnose.

For Bearer Authentication, Spring Security provides dedicated components such as **BearerTokenAuthenticationEntryPoint** and **BearerTokenAccessDeniedHandler**. They express OAuth Bearer semantics when authentication or authorization fails. An application should not always redirect API clients to a login form.

## 10. Testing a Resource Server with MockMvc and spring-security-test

A critical point: **tests using the jwt() request postprocessor simulate an already-authenticated JWT Authentication**. It is well suited for testing authorization, scopes, and controllers, but it does not actually decode JWTs via JwtDecoder and does not prove that real-world JWK/issuer configuration works.

Given the classes from section 6 and the test starter, create src/test/java/demo/resourceserver/ResourceServerSecurityTest.java:

~~~java
package demo.resourceserver;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void publicHealthDoesNotRequireToken() throws Exception {
        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void protectedEndpointRejectsMissingToken() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportsRequireScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(j -> j
                    .claim("sub", "alice")
                    .claim("scope", "profile.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void reportsAcceptCorrectScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().jwt(j -> j
                    .claim("sub", "alice")
                    .claim("scope", "reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectedBearerFromDecoderReturnsUnauthorized() throws Exception {
        when(decoder.decode("bad.token.value"))
            .thenThrow(new BadJwtException("Signature invalid"));

        mvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer bad.token.value"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

In Spring Boot 3.3, @MockBean replaces JwtDecoder with a mock so the test context does not need to call a real issuer; in newer Boot versions, mock bean APIs may change—use the annotation appropriate for the version you are running.

Explanation of each test group:

- Public and missing-token tests verify matchers and the entry point.
- The two tests using jwt() verify how authorities are extracted from scope and checked by AuthorizationFilter; **they bypass real JWT signature decoding**.
- The final test sends an actual Authorization header through BearerTokenAuthenticationFilter and forces the mock JwtDecoder to reject the token; it observes the filter path's 401 response.
- These tests still **do not prove** discovery URL, JWK download, TLS, key rotation, audience contract, or real introspection. You must have separate integration tests with a trusted issuer/test keys or an end-to-end environment.

Run command, if the project has a standard Gradle wrapper:

~~~bash
./gradlew test
~~~

Do not state fabricated stdout because actual output depends on the environment, plugins, and other tests. When verifying end-to-end, obtain tokens from a real test Authorization Server with the right issuer, audience, scope, and timestamps; never manually edit a token and expect its signature to remain valid.

## 11. Integration Testing and Required Case Matrix

In an integration environment using HTTPS, verify at minimum:

| Request | What to Verify |
| --- | --- |
| /api/public/health without token | Reaches public endpoint, 200 |
| /api/me without token | 401 with Bearer challenge |
| /api/me valid token, right issuer/aud/time | Returns expected principal |
| /api/reports valid token with reports.read | Reaches controller, business result |
| /api/reports valid token lacking reports.read | Rejected with 403, protected logic does not run |
| Token with bad signature / unknown kid | Rejected with 401, never accepted just because payload has permissions |
| Expired or not-yet-valid (nbf) token | Rejected |
| Token from another issuer | Rejected |
| Token with another API's audience | Rejected when an audience validator is configured |
| Token in query string | Rejected under secure default configuration |
| Browser OPTIONS preflight | Not wrongly blocked by authentication; check CORS policy separately |
| Introspection endpoint unavailable (if opaque) | Failure handled and monitored, never grants access when verification fails |

Tests distinguishing 401 and 403 must verify **response status, appropriate headers, and that the controller produces no side effects** when blocked. With multiple filter chains, verify which matcher selected the chain containing oauth2ResourceServer.

To evaluate performance and operations, test JWK/introspection query latency, timeouts, cache policy, behavior when the Authorization Server rotates keys, token expiry, and concurrent requests. A Resource Server must never silently skip token verification when upstream fails.

## 12. Common Scenarios and Real Root Causes

### 12.1. 401 Even Though the Token Looks Like a Valid JWT

A three-part JWT only means the string looks like a JWT. Check the **Authorization Bearer header**, issuer-uri, signature, kid/JWK URI, trusted alg, exp/nbf, audience, and access token type. Never copy a frontend ID token to use as an API access token.

### 12.2. 403 Even Though Signature and Issuer Are Valid

The token authenticated, but may lack an authority. Spring Security normally maps scope to **SCOPE_...**; verify the real token carries scope/scp claims matching the contract and that rules use hasAuthority("SCOPE_reports.read"). Custom JWT roles are not automatically mapped to ROLE_ADMIN. AuthorizationFilter or method security may also enforce independent constraints.

### 12.3. Missing JwtDecoder Bean or Startup Failure Due to Issuer

JWT mode requires a JwtDecoder. With Spring Boot, include the starter/resource-server JWT dependency and configure the exact issuer-uri/JWK URI; if the project defines a custom JwtDecoder, supply appropriate validators. Discovery metadata from the issuer or egress to the issuer can affect startup; inspect the stack trace and truststore/network instead of disabling validation.

### 12.4. Wrongly Choosing JWT Configuration for an Opaque Token

An opaque string does not contain JWT header.payload.signature. It requires introspection configuration and the opaqueToken DSL with secure client credentials. Conversely, arbitrarily using introspection for JWTs adds network dependencies even though an API can verify JWT signatures locally.

### 12.5. Valid Token Yet the API Still Sees Anonymous

Check whether the Authorization header actually reaches the backend; whether a proxy/WAF strips the header; whether multiple SecurityFilterChains cause the request to fall into a chain without resource server configured; or whether a custom filter overwrites the SecurityContext. A permitAll endpoint does not prove authentication works: it can run even without a token.

### 12.6. Client Sends a Token Intended for Another API

Each Resource Server should specify its allowed audience. A token with broad scopes whose aud belongs to another service should not be valid. Add an audience validator; never skip validation because of “same issuer.”

### 12.7. Stateless API Yet Sessions/Cookies Still Exist

SessionCreationPolicy.STATELESS governs where Spring Security stores the security context; it does not guarantee every part of the application creates no sessions, emits no cookies, or has no cookie-based authentication. CSRF decisions must be based on whether browsers can auto-attach credentials; only disable CSRF when you confirm the API truly relies on client-controlled Authorization Bearer headers and has no cookie-authenticated state-changing paths.

### 12.8. Confusing Resource Server with OAuth2 Login

**oauth2Login()** serves applications acting as OAuth clients with browser login/sessions. **oauth2ResourceServer()** serves APIs accepting access tokens. One application can have both, but must separate SecurityFilterChains, entry points, sessions, and CSRF clearly. Do not enable oauth2Login() expecting BearerTokenAuthenticationFilter to appear for an API.

### 12.9. CORS Preflight Rejected

Browsers send an OPTIONS preflight before certain cross-origin requests without carrying the Bearer token from the real request. Handle CORS at the proper layer and explicitly declare allowed origins, methods, and the Authorization header; permit preflight if needed. CORS does not replace Bearer token validation on the actual API request.

### 12.10. Logging Raw JWTs for Debugging

JWTs can carry personal data, and a signed token itself is a usable credential until it expires. Log **request ID, trusted issuer, sanitized subject, validation outcome, and error code**; avoid logging the Authorization header, token body, client secrets, and refresh tokens. Redact tokens in tracing/APM/reverse proxies as well.

## 13. Accompanying Security and Operational Controls

**HTTPS across public boundaries.** A stolen Bearer token can usually be replayed. Use TLS, set reasonable token lifetimes, minimal scopes, exact audiences, and risk-appropriate rotation/revocation mechanisms.

**Least privilege.** A token issued for reports.read should not be usable to delete reports. Separate read/write permissions and check ownership/resource IDs in the business layer; scopes cannot replace object-level authorization.

**Trusted issuer and JWK sources.** Never take jwk-set-uri from a claim or query parameter sent by the client. A client-controlled kid in a token may only look up a key within an already-trusted JWK set. For multi-tenancy, use AuthenticationManagerResolver with a trusted issuer allowlist and explicit tenant rules; never trust arbitrary URLs provided by a token.

**Audience.** When multiple APIs share an issuer, enforce aud for your API. If the Resource Server must enforce token type, scope, or tenant, add contract-based validation rather than relying on the signature alone.

**Rate limits and fault behavior.** Introspection depends on network availability and JWK refresh depends on HTTP egress; design bounded timeouts, caching, and retries. Failure to verify a token must never turn into default access.

**Layered defenses.** The Resource Server is one part of the pipeline; continue enforcing security headers, CORS, input validation, auditing, SSRF/injection defenses, sensitive data controls, CSRF wherever cookie authentication exists, and object-level authorization tests.

## 14. Glossary and Checklist

| Concept | Key Meaning |
| --- | --- |
| BearerTokenAuthenticationFilter | Extracts Bearer token from the request and invokes AuthenticationManager |
| DefaultBearerTokenResolver | Reads the token from the Authorization header using default rules |
| JwtDecoder | Parses/verifies a JWT and runs token validators |
| JwtAuthenticationProvider | Authenticates a JWT and converts it into a JwtAuthenticationToken |
| OpaqueTokenIntrospector | Validates a token via an introspection endpoint |
| OAuth2AuthenticatedPrincipal | Principal holding attributes/authorities for an opaque token |
| SecurityContextHolder | Accesses the Authentication for the current request |
| JwtGrantedAuthoritiesConverter | Maps scope/scp into authorities prefixed with SCOPE_ |
| BearerTokenAuthenticationEntryPoint | Responds with an authentication challenge using Bearer semantics |
| AuthorizationFilter | Decides whether an authenticated request is authorized to access the resource |

Self-check before concluding an API is secure:

- [ ] The API accepts access tokens via **Authorization: Bearer** over HTTPS; tokens are not passed in query strings.
- [ ] It is clear whether the API uses **local JWT validation** or **opaque introspection**.
- [ ] JWTs are validated for signature, issuer, timestamps, and **API audience**.
- [ ] scope → SCOPE_ authority rules are tested, not confused with ROLE_ or custom claims.
- [ ] Public, authenticated, and scope-protected endpoints return the expected status codes.
- [ ] Authentication failures return 401; valid tokens lacking permissions return 403 per policy.
- [ ] Session and CSRF are configured for the actual credential model, never disabling CSRF solely because it is labeled an “API.”
- [ ] Both MockMvc authorization tests and integration tests verifying real tokens/issuer/JWK/introspection exist.
- [ ] Proxies, ingress, CORS, and SecurityFilterChain all handle the Authorization header properly.
- [ ] Access tokens and client secrets are never logged; token expiry, key rotation, and Authorization Server outage handling policies exist.

**Remember:** oauth2ResourceServer enables **Bearer access token authentication** for Servlet applications. BearerTokenAuthenticationFilter receives the token; JwtDecoder or OpaqueTokenIntrospector decides whether the credential is valid; Spring Security builds the Authentication; and finally authorization decides which resources may be accessed. Properly protecting an API requires checking **token source, intended target (audience), validity window, scope, and business permissions**, rather than treating a token as merely a signed string.
